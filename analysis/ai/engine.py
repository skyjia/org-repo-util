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


class AIEngine:
    def __init__(self, allowed_tools: str = "Read,Grep,Glob", max_turns: int = 60):
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
                f"claude 退出码 {proc.returncode}: {(proc.stderr or proc.stdout)[:400]}")

        envelope = self._parse_envelope(proc.stdout)
        if envelope.get("is_error"):
            raise AIEngineError(f"claude 返回错误: {str(envelope.get('result'))[:400]}")
        text = envelope.get("result") or ""
        if not text.strip():
            raise AIEngineError("claude 返回空结果")
        return extract_json(text)

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
