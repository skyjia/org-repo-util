"""归档 JSON 组装（REQ §5.3 schema v1，待决策项 #1 落定）"""

from __future__ import annotations

from typing import Any, Optional

from analysis import __version__
from analysis.core import config
from analysis.core.models import Task

SEVERITY_TO_PRIORITY = {"critical": "P0", "high": "P1", "medium": "P2", "low": "P2"}

# 报告章节 → 产物子任务映射（REQ 第 3 章 11 个章节）
CHAPTER_SOURCES = {
    "overview": ["collect.overview"],
    "structure": ["collect.structure"],
    "dependencies": ["collect.dependencies"],
    "quality": ["collect.quality", "ai.conclusions:quality"],
    "security": ["collect.security", "ai.conclusions:security"],
    "performance": ["collect.performance", "ai.conclusions:performance"],
    "docs": ["collect.docs", "ai.conclusions:docs"],
    "tests": ["collect.tests", "ai.conclusions:tests"],
    "architecture": ["ai.architecture"],
    "business_knowledge": ["ai.business_knowledge"],
    "summary": ["ai.summary", "scoring"],
}


def _conclusion_slice(conclusions: Optional[dict], dim: str) -> Optional[dict]:
    if not conclusions:
        return None
    return (conclusions.get("dimensions") or {}).get(dim)


def build_chapters(outputs: dict[str, Optional[dict]]) -> dict[str, dict]:
    """组装 11 章内容：采集数据 + AI 结论合并"""
    conclusions = outputs.get("ai.conclusions")
    chapters: dict[str, dict] = {}

    chapters["overview"] = {"data": outputs.get("collect.overview")}
    for dim, subtask in (("structure", "collect.structure"),
                         ("dependencies", "collect.dependencies")):
        chapters[dim] = {
            "data": outputs.get(subtask),
            "conclusion": _conclusion_slice(conclusions, dim),
        }
    chapters["quality"] = {"data": outputs.get("collect.quality"),
                           "conclusion": _conclusion_slice(conclusions, "quality")}
    chapters["security"] = {"data": outputs.get("collect.security"),
                            "conclusion": _conclusion_slice(conclusions, "security")}
    chapters["performance"] = {
        "data": outputs.get("collect.performance"),
        "conclusion": _conclusion_slice(conclusions, "performance"),
        "boundary_declaration": (outputs.get("collect.performance") or {}).get(
            "boundary_declaration"),
    }
    chapters["docs"] = {"data": outputs.get("collect.docs"),
                        "conclusion": _conclusion_slice(conclusions, "docs")}
    chapters["tests"] = {"data": outputs.get("collect.tests"),
                         "conclusion": _conclusion_slice(conclusions, "tests")}
    chapters["architecture"] = {"data": outputs.get("ai.architecture")}
    chapters["business_knowledge"] = {"data": outputs.get("ai.business_knowledge")}
    chapters["summary"] = {"data": outputs.get("ai.summary"),
                           "scoring": outputs.get("scoring")}
    return chapters


def aggregate_issues(outputs: dict[str, Optional[dict]]) -> list[dict]:
    """跨维度问题清单汇总（统一 severity/priority/dimension/location）"""
    issues: list[dict] = []

    def add(dimension, severity, title, detail=None, evidence=None, source=None, priority=None):
        issues.append({
            "dimension": dimension,
            "severity": severity,
            "priority": priority or SEVERITY_TO_PRIORITY.get(str(severity).lower(), "P2"),
            "title": title,
            "detail": detail,
            "evidence": evidence or [],
            "source": source,
        })

    # AI 总结的 TOP 问题（已含优先级）
    for it in (outputs.get("ai.summary") or {}).get("top_issues", []):
        add(it.get("dimension", "summary"), it.get("severity", "high"),
            it.get("title"), it.get("detail"), it.get("evidence"),
            source="ai.summary", priority=it.get("priority"))

    # 各维度 AI 结论 findings
    for dim, c in ((outputs.get("ai.conclusions") or {}).get("dimensions") or {}).items():
        for f in c.get("findings", []):
            add(dim, f.get("severity", "medium"), f.get("title"), f.get("detail"),
                f.get("evidence"), source="ai.conclusions")

    # 架构问题
    for f in (outputs.get("ai.architecture") or {}).get("issues", []):
        add("architecture", f.get("severity", "medium"), f.get("title"), f.get("detail"),
            f.get("evidence"), source="ai.architecture")

    # 依赖漏洞（OSV）
    for v in (outputs.get("collect.security") or {}).get(
            "dependency_vulnerabilities", {}).get("vulnerable", []):
        sev = str(v.get("severity") or "unknown").lower()
        add("security", sev if sev in ("critical", "high", "medium", "low") else "medium",
            f"依赖漏洞 {v.get('id')}: {v.get('package')}@{v.get('version')}",
            v.get("url"), source="osv")

    # 安全静态启发式（仅 critical/high）
    hits = (outputs.get("collect.security") or {}).get("static_heuristics", {}).get("hits", {})
    for pattern, items in hits.items():
        for h in items:
            if h.get("severity") in ("critical", "high") and not h.get("is_test_file"):
                add("security", h["severity"], f"{pattern}: {h.get('note', '')}",
                    h.get("evidence"), [f"{h.get('file')}:{h.get('line')}"],
                    source="static_heuristic")

    # 一致性矛盾（业务知识还原）
    for c in (outputs.get("ai.business_knowledge") or {}).get("contradictions", []):
        add("business_knowledge", c.get("severity", "medium"),
            f"[{c.get('type')}] {c.get('description', '')[:80]}",
            c.get("description"), c.get("evidence"), source="ai.business_knowledge")

    # 去重（同 dimension+title）
    seen, unique = set(), []
    for it in issues:
        key = (it["dimension"], it["title"])
        if key not in seen:
            seen.add(key)
            unique.append(it)
    order = {"P0": 0, "P1": 1, "P2": 2}
    unique.sort(key=lambda x: order.get(x["priority"], 3))
    return unique


def build_metadata(task: Task, outputs: dict[str, Optional[dict]]) -> dict:
    prompt_versions = {}
    for name, data in outputs.items():
        if isinstance(data, dict) and "_ai_meta" in data:
            prompt_versions[name] = data["_ai_meta"].get("prompt_version")

    audit_refs = []
    for dim in ("quality", "security"):
        d = outputs.get(f"collect.{dim if dim != 'quality' else 'quality'}") or {}
        for key in ("style_lint", "audit_security"):
            ref = d.get(key)
            if isinstance(ref, dict) and ref.get("source") == "audit":
                audit_refs.append({
                    "dimension": dim,
                    "audit_generated_at": ref.get("audit_generated_at"),
                    "staleness_note": ref.get("staleness_note"),
                })

    return {
        "schema_version": config.SCHEMA_VERSION,
        "org": task.org,
        "repo": task.repo,
        "task_id": task.task_id,
        "ref": task.ref,
        "commit_sha": task.commit_sha,
        "analyzed_at": task.finished_at or task.started_at,
        "duration_seconds": task.duration_seconds,
        "generator": {
            "name": config.GENERATOR_NAME,
            "version": __version__,
            "prompt_versions": prompt_versions,
        },
        "data_sources": [
            "静态代码分析", "本地 git 历史（不含人员信息）", "GitHub API",
            "仓库内已有产物文件", "现有 audit 扫描产物",
        ],
        "audit_refs": audit_refs,
        "limitations": [
            "纯静态分析：未运行目标仓库任何代码（构建/测试/benchmark 均未执行）",
            "测试覆盖率为静态代理指标或引用仓库已有产物",
            "性能分析为静态启发式，结论仅方向性参考",
            "AI 生成章节（架构/业务知识还原/结论/总结）具非确定性，已标注 _ai_meta",
            "不分析贡献者等人员维度（REQ §1.2）",
        ],
    }


def build_report(task: Task, outputs: dict[str, Optional[dict]]) -> dict:
    """完整归档 JSON（REQ §5.3）"""
    bk = outputs.get("ai.business_knowledge") or {}
    return {
        "metadata": build_metadata(task, outputs),
        "scores": outputs.get("scoring"),
        "chapters": build_chapters(outputs),
        "issues": aggregate_issues(outputs),
        "knowledge": {
            "list": bk.get("knowledge", []),
            "gaps": bk.get("gaps", []),
            "contradictions": bk.get("contradictions", []),
            "readiness": bk.get("readiness"),
        },
        "subtasks_status": {
            name: st.to_dict() for name, st in task.subtasks.items()
        },
    }
