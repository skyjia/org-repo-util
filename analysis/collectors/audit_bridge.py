"""AuditBridge — 读取现有 audit 扫描产物（REQ §1.3 复用决策）

audit 报告结构（reports/<org>/<repo>/latest/report.json）：
{metadata: {generated_at, total_repos},
 results: [{repo, language, analyzer, issues: [{file, line, column, severity,
            message, rule, tool, dimension, suggestion}],
            files_scanned, lines_scanned, duration_seconds, error}]}

引用规范（REQ §1.3）：
- 标注 audit 时间与对应 commit（audit 产物无 commit 字段 → 标注「基线未知，结果可能过期」）
- audit 未覆盖语言/仓库 → found:false + 建议（REQ §2.3）
"""

from __future__ import annotations

import json
from pathlib import Path

from analysis.core import config

AUDIT_COVERED_LANGUAGES = {"javascript", "typescript", "go", "csharp", "c#", "vue"}


def load_audit_report(org: str, repo: str) -> dict:
    """返回 {found, ...} 结构"""
    latest = config.REPORTS_DIR / org / repo / "latest" / "report.json"
    if not latest.exists():
        # latest 是符号链接目录时解析真实路径
        alt = config.REPORTS_DIR / org / repo / "latest"
        if alt.is_symlink():
            target = (alt.parent / alt.readlink()).resolve() / "report.json"
            if target.exists():
                latest = target
    if not latest.exists():
        return {
            "found": False,
            "what": "audit 扫描产物",
            "suggestion": f"未找到 {config.REPORTS_DIR}/{org}/{repo}/latest/report.json；"
                          "先运行 audit（audit/bin/audit repo <path> --save）再重跑本分析，"
                          "或接受本报告中质量/安全维度仅含静态启发式结果",
            "checked_path": str(latest),
        }
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"found": False, "what": "audit 扫描产物",
                "suggestion": f"audit 报告损坏（{e}），请重新运行 audit"}

    results = data.get("results", [])
    if not results:
        return {"found": False, "what": "audit 扫描结果",
                "suggestion": "audit 报告 results 为空，请重新运行 audit"}

    r = results[0]
    lang = (r.get("language") or "").lower()
    return {
        "found": True,
        "path": str(latest),
        "audit_generated_at": data.get("metadata", {}).get("generated_at"),
        "audit_commit": None,   # audit 产物不含 commit 字段
        "staleness_note": "audit 产物未记录对应 commit，无法与本次分析基线比对——结果可能过期（REQ §1.3）",
        "language": r.get("language"),
        "language_covered_by_audit": lang in AUDIT_COVERED_LANGUAGES,
        "analyzer": r.get("analyzer"),
        "files_scanned": r.get("files_scanned"),
        "lines_scanned": r.get("lines_scanned"),
        "duration_seconds": r.get("duration_seconds"),
        "issues": r.get("issues", []),
    }


def split_issues_by_dimension(audit: dict) -> tuple[list, list]:
    """按 dimension 分流：(code_style/lint 类, security 类)"""
    if not audit.get("found"):
        return [], []
    lint, sec = [], []
    for issue in audit.get("issues", []):
        dim = (issue.get("dimension") or "").lower()
        if "secur" in dim:
            sec.append(issue)
        else:
            lint.append(issue)
    return lint, sec


def summarize_issues(issues: list, rel_root: Path | None = None) -> dict:
    """issues 汇总统计（数量按 severity/rule，路径转相对）"""
    from collections import Counter
    sev = Counter(i.get("severity", "unknown") for i in issues)
    rules = Counter(i.get("rule", "unknown") for i in issues)
    sample = []
    for i in issues[:20]:
        f = i.get("file", "")
        if rel_root:
            try:
                f = str(Path(f).relative_to(rel_root))
            except ValueError:
                pass
        sample.append({"file": f, "line": i.get("line"), "severity": i.get("severity"),
                       "rule": i.get("rule"), "message": (i.get("message") or "")[:160]})
    return {
        "total": len(issues),
        "by_severity": dict(sev),
        "top_rules": [{"rule": r, "count": c} for r, c in rules.most_common(15)],
        "sample": sample,
    }
