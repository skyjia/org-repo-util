"""AI 引擎：Claude Code headless 封装（ANALYSIS-DESIGN.md §6.1）

安全边界（设计决策 D3）：
- --allowedTools 仅 Read/Grep/Glob（只读；git 上下文由 collect.git_context 预先注入）
- 不开放 Bash/Write/Edit，AI 无法修改仓库或执行命令
"""

from __future__ import annotations

import json
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

    def run(self, prompt_text: str, repo_path: Path, timeout: int) -> dict:
        """执行一次 AI 分析，返回解析后的 JSON dict"""
        ok, info = self.available()
        if not ok:
            raise AIEngineError(info)

        cmd = [
            "claude", "-p",
            "--output-format", "json",
            "--allowedTools", self.allowed_tools,
            "--max-turns", str(self.max_turns),
        ]
        try:
            proc = subprocess.run(
                cmd, input=prompt_text, capture_output=True, text=True,
                timeout=timeout, cwd=str(repo_path))
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
        return extract_json(text)

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
