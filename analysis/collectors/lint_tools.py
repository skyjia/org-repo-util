"""本地 lint 工具桥（M7 T702/T704）：ruff（Python）+ shellcheck（Shell）

- 均为本地运行、零 API 成本；工具不可用时返回 None（采集器走 found:false 兜底）
- 输出结构与 audit 桥接一致（total/by_severity/top_rules/sample），便于评分与模板复用
- ruff S 系列（bandit 安全规则）单独统计，供 security 采集器引用
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

from analysis.core import config


def _ruff_severity(code: str) -> str:
    if code.startswith(("E9", "F821", "F811", "F702")):
        return "high"          # 语法级/未定义名等硬错误
    if code.startswith(("F", "B", "S", "C4")):
        return "medium"        # pyflakes / bugbear / bandit / comprehensions
    return "low"               # E/W 风格类


def _summarize(items: list[dict], source: str, repo: Path,
               extra: dict | None = None) -> dict:
    sev = Counter(i.get("severity", "unknown") for i in items)
    rules = Counter(i.get("rule", "unknown") for i in items)
    sample = []
    for i in items[:20]:
        f = i.get("file", "")
        try:
            f = str(Path(f).relative_to(repo))
        except (ValueError, OSError):
            pass
        sample.append({"file": f, "line": i.get("line"), "severity": i.get("severity"),
                       "rule": i.get("rule"), "message": (i.get("message") or "")[:160]})
    out = {
        "source": source,
        "total": len(items),
        "by_severity": dict(sev),
        "top_rules": [{"rule": r, "count": c} for r, c in rules.most_common(15)],
        "sample": sample,
    }
    if extra:
        out.update(extra)
    return out


def run_ruff(repo: Path) -> dict | None:
    """对 Python 仓库运行 ruff；返回聚合结果或 None（不可用/无 Python 文件）"""
    # 快速探测 Python 文件（限深，避免大仓库全遍历）
    has_py = next(iter(repo.glob("*.py")), None) or next(iter(repo.glob("*/*.py")), None) \
        or next(iter(repo.glob("*/*/*.py")), None)
    if not has_py:
        return None
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--output-format", "json",
             "--select", config.RUFF_SELECT, "--no-fix", "--quiet", "."],
            cwd=str(repo), capture_output=True, text=True,
            timeout=config.RUFF_TIMEOUT)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    # ruff: exit 0=干净, 1=发现问题（正常）, 2+=执行错误
    if proc.returncode not in (0, 1):
        return {"source": "ruff", "error": (proc.stderr or "")[:200], "total": 0,
                "by_severity": {}, "top_rules": [], "sample": []}
    try:
        raw = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None

    items = []
    s_items = []
    for r in raw:
        code = r.get("code") or ""
        item = {"file": r.get("filename", ""), "line": r.get("row"),
                "column": r.get("column"), "rule": code,
                "message": r.get("message", ""),
                "severity": _ruff_severity(code)}
        items.append(item)
        if code.startswith("S"):
            s_items.append(item)
    extra = {
        "bandit_security_rules": {   # S 系列（security 维度复用）
            "total": len(s_items),
            "by_rule": dict(Counter(i["rule"] for i in s_items).most_common(15)),
            "sample": [{k: i[k] for k in ("file", "line", "rule", "message")}
                       for i in s_items[:10]],
        },
        "select": config.RUFF_SELECT,
    }
    return _summarize(items, "ruff", repo, extra)


def run_shellcheck(repo: Path, max_files: int | None = None) -> dict | None:
    """对 Shell 仓库运行 shellcheck；返回聚合结果或 None（不可用/无 shell 文件）"""
    if not shutil.which("shellcheck"):
        return None
    files: list[Path] = []
    limit = max_files or config.SHELLCHECK_MAX_FILES
    for pat in ("*.sh", "*.bash", "*.ksh"):
        for p in repo.rglob(pat):
            if not any(x in p.parts for x in ("node_modules", ".git", "vendor")):
                files.append(p)
                if len(files) >= limit:
                    break
        if len(files) >= limit:
            break
    if not files:
        return None

    items = []
    errors = []
    sev_map = {"error": "high", "warning": "medium", "info": "low", "style": "info"}
    batch_size = 50
    try:
        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            proc = subprocess.run(
                ["shellcheck", "-f", "json1", *[str(p) for p in batch]],
                cwd=str(repo), capture_output=True, text=True,
                timeout=config.SHELLCHECK_TIMEOUT)
            # shellcheck: exit 1=发现问题（正常）
            if proc.returncode not in (0, 1):
                errors.append((batch[0].name, (proc.stderr or "")[:100]))
                continue
            try:
                comments = json.loads(proc.stdout or "{}").get("comments", [])
            except json.JSONDecodeError:
                continue
            for c in comments:
                items.append({
                    "file": c.get("file", ""), "line": c.get("line"),
                    "column": c.get("column"), "rule": f"SC{c.get('code')}",
                    "message": c.get("message", ""),
                    "severity": sev_map.get(c.get("level"), "info"),
                })
    except (subprocess.TimeoutExpired, OSError):
        return None

    extra = {"files_checked": len(files)}
    if errors:
        extra["batch_errors"] = errors[:5]
    return _summarize(items, "shellcheck", repo, extra)
