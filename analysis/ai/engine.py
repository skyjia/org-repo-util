"""AI 引擎：Claude Code headless 封装（ANALYSIS-DESIGN.md §6.1）

安全与成本边界：
- --allowedTools 只读白名单（Read/Grep/Glob）；解读型子任务传空白名单（纯数据解读，
  禁止代码探索，1-2 轮完成）
- --strict-mcp-config + 空 mcpServers：屏蔽宿主终端环境（如 cmux）向 headless 会话
  注入的 MCP 服务器与工具定义——实测系统上下文 16.7K → 5.5K tokens（省 67%）
- 子进程环境剔除 CMUX_* 注入变量（settings/hooks/wrapper shim）
- 失败取证：解析 stdout envelope（stop_reason/num_turns/result）+ 过滤无害警告的
  stderr 尾部（第三方 provider 的 unrecognized_model 为噪音）
- 观测：返回 num_turns / cost / usage，写入产物 _ai_meta（token 调优的数据基础）
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional


class AIEngineError(Exception):
    pass


# 第三方 provider 场景下 headless 模式的无害警告（stderr 噪音，过滤后不入错误信息）
_NOISE_PREFIXES = ("[claude-code:unrecognized_model]",)


class AIEngine:
    def __init__(self, allowed_tools: str = "Read,Grep,Glob", max_turns: int = 120):
        self.allowed_tools = allowed_tools
        self.max_turns = max_turns

    @staticmethod
    def available() -> tuple[bool, str]:
        exe = shutil.which("claude")
        if not exe:
            return False, "claude CLI 未安装或不在 PATH"
        return True, exe

    @staticmethod
    def _clean_env() -> dict:
        """剔除宿主终端（cmux 等）注入变量，防止 headless 会话被附加
        settings/hooks/MCP wrapper（token 与启动耗时浪费）"""
        env = os.environ.copy()
        for k in list(env):
            if k.startswith("CMUX_"):
                env.pop(k)
        return env

    def run(self, prompt_text: str, repo_path: Path, timeout: int,
            allowed_tools: Optional[str] = None) -> tuple[dict, dict]:
        """执行一次 AI 分析。返回 (解析后的 JSON dict, 观测 meta)"""
        ok, info = self.available()
        if not ok:
            raise AIEngineError(info)

        tools = self.allowed_tools if allowed_tools is None else allowed_tools
        cmd = [
            "claude", "-p",
            "--output-format", "json",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        ]
        if tools:
            cmd += ["--allowedTools", tools]
        else:
            # 空白名单：物理禁止一切工具调用（解读型任务，防探索发散）
            cmd += ["--allowedTools", ""]
        cmd += ["--max-turns", str(self.max_turns)]

        try:
            proc = subprocess.run(
                cmd, input=prompt_text, capture_output=True, text=True,
                timeout=timeout, cwd=str(repo_path), env=self._clean_env())
        except subprocess.TimeoutExpired:
            raise AIEngineError(f"claude 执行超时（>{timeout}s）")

        if proc.returncode != 0:
            raise AIEngineError(
                f"claude 退出码 {proc.returncode}: {self._failure_detail(proc)}")

        envelope = self._parse_envelope(proc.stdout)
        if envelope.get("is_error"):
            raise AIEngineError(
                f"claude 返回错误 (stop_reason={envelope.get('stop_reason')}, "
                f"turns={envelope.get('num_turns')}): {str(envelope.get('result'))[:400]}")
        text = envelope.get("result") or ""
        if not text.strip():
            raise AIEngineError(
                f"claude 返回空结果 (stop_reason={envelope.get('stop_reason')}, "
                f"turns={envelope.get('num_turns')})")

        usage = envelope.get("usage") or {}
        meta = {
            "num_turns": envelope.get("num_turns"),
            "stop_reason": envelope.get("stop_reason"),
            "duration_api_ms": envelope.get("duration_api_ms"),
            "total_cost_usd": envelope.get("total_cost_usd"),
            "input_tokens": usage.get("input_tokens"),
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
            "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
            "output_tokens": usage.get("output_tokens"),
        }
        return extract_json(text), meta

    @staticmethod
    def _failure_detail(proc: subprocess.CompletedProcess) -> str:
        """失败取证：stdout envelope 解析（stop_reason/num_turns/result）+ 过滤噪音后的 stderr 尾部"""
        parts = []
        try:
            env = json.loads(proc.stdout)
            sr = env.get("stop_reason")
            parts.append(f"stop_reason={sr}, turns={env.get('num_turns')}")
            if sr == "max_turns":
                parts.append("已达 max-turns 上限（任务过重，考虑精简输入或调大 --max-turns）")
            if env.get("result"):
                parts.append(f"result: {str(env['result'])[:300]}")
        except (json.JSONDecodeError, TypeError):
            if proc.stdout and proc.stdout.strip():
                parts.append(f"stdout 尾部: {proc.stdout.strip()[-200:]}")
        err_lines = [l for l in (proc.stderr or "").splitlines()
                     if l.strip() and not l.startswith(_NOISE_PREFIXES)]
        if err_lines:
            parts.append("stderr: " + " | ".join(err_lines[-3:])[:400])
        return "; ".join(parts) or "(无错误输出)"

    @staticmethod
    def _parse_envelope(stdout: str) -> dict:
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            # 非 JSON envelope（旧版本/异常输出）：把 stdout 当纯文本结果
            return {"result": stdout, "is_error": False}


_JSON_BLOCK = re.compile(r"```(?:json)?\s*\n(.*?)```", re.S)


def extract_json(text: str) -> dict:
    """从 AI 返回文本提取 JSON：优先 ```json 代码块，其次裸 JSON 对象"""
    candidates = []
    for m in _JSON_BLOCK.finditer(text):
        candidates.append(m.group(1))
    candidates.append(text)
    # 裸文本中截取首个 { 到末个 }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    for cand in candidates:
        try:
            data = json.loads(cand.strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    raise AIEngineError(f"无法从 AI 返回中提取合法 JSON: {text[:300]}")
