"""AI 子任务 handler（ANALYSIS-DESIGN.md §6.2）

流程：读取前序采集产物 → 字段级裁剪注入 prompt → claude headless 执行
→ JSON 提取 + jsonschema 校验 → 附 _ai_meta（含 token/耗时观测）落盘。

成本分层：
- 探索型（architecture / business_knowledge）：只读工具白名单 + 探索预算指导
- 解读型（conclusions / summary）：**空白名单**（物理禁止探索）+ 精简注入，
  单轮完成，耗时与 token 大幅下降
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
from jinja2 import Environment, FileSystemLoader

from analysis.ai.engine import AIEngine
from analysis.core import config
from analysis.core.models import now_iso
from analysis.core.registry import register

AI_DIR = Path(__file__).parent
_jinja = Environment(loader=FileSystemLoader(str(AI_DIR / "prompts")))
ENGINE = AIEngine()

# engine subprocess 超时早于 orchestrator SIGALRM，保证超时走可重试异常路径
_ENGINE_GRACE = 60
_TRIM_LIMIT = 6000


def _prompt_version(name: str) -> str:
    tpl = (AI_DIR / "prompts" / f"{name}.md.j2").read_bytes()
    return hashlib.md5(tpl).hexdigest()[:8]


def _dumps(obj) -> str:
    if obj is None:
        return "null（前序采集缺失，结论中请如实标注数据缺失）"
    return json.dumps(obj, ensure_ascii=False, default=str)


def _trim(obj, limit: int = _TRIM_LIMIT) -> str:
    """兜底截断（字段级裁剪之后仍超限时）"""
    text = _dumps(obj)
    if len(text) > limit:
        text = text[:limit] + f"\n…（已截断，原始 {len(text)} 字符）"
    return text


# ---------- 字段级裁剪（token 优化：只注入决策所需字段） ----------

def _prune_structure(d, max_dirs=25, max_longest=10):
    if not d:
        return None
    return {
        "total_files": d.get("total_files"),
        "primary_language": d.get("primary_language"),
        "languages": dict(list((d.get("languages") or {}).items())[:10]),
        "categories": d.get("categories"),
        "test_to_production_ratio": d.get("test_to_production_ratio"),
        "top_level_dirs": dict(list((d.get("top_level_dirs") or {}).items())[:max_dirs]),
        "longest_files": (d.get("longest_files") or [])[:max_longest],
    }


def _prune_deps(d, max_deps=60, max_nodes=80, max_edges=120):
    if not d:
        return None
    ext = d.get("external_dependencies") or {}
    g = d.get("dependency_graph")
    graph = None
    if isinstance(g, dict) and g.get("found") is not False and g.get("nodes"):
        graph = {"tool": g.get("tool"),
                 "node_count": len(g.get("nodes") or []),
                 "nodes": [{"id": n.get("id")} for n in (g.get("nodes") or [])[:max_nodes]],
                 "edges": (g.get("edges") or [])[:max_edges]}
    elif isinstance(g, dict):
        graph = {"found": False, "reason": g.get("reason")}
    return {
        "manifests_detected": d.get("manifests_detected"),
        "dependency_count": d.get("dependency_count"),
        "pinned_ratio": d.get("pinned_ratio"),
        "unpinned_count": (d.get("unpinned_versions") or {}).get("count"),
        "top_dependencies": dict(list(ext.items())[:max_deps]),
        "dependency_graph": graph,
    }


def _prune_git(d, recent=30, older=80, words=25):
    if not d:
        return None
    return {
        "total_commits_analyzed": d.get("total_commits_analyzed"),
        "first_commit": d.get("first_commit"),
        "commits_per_year": d.get("commits_per_year"),
        "recent_commits": (d.get("recent_commits") or [])[:recent],
        "older_commit_messages": (d.get("older_commit_messages") or [])[:older],
        "frequent_message_words": (d.get("frequent_message_words") or [])[:words],
        "tags": (d.get("tags") or [])[:15],
    }


def _prune_quality(d):
    if not d:
        return None
    lint = d.get("style_lint") or {}
    cx = d.get("complexity") or {}
    return {
        "style_lint": {k: lint.get(k) for k in
                       ("source", "audit_generated_at", "staleness_note", "total",
                        "by_severity", "top_rules", "suggestion")} if lint else None,
        "complexity": {k: cx.get(k) for k in
                       ("tool", "functions_analyzed", "average_ccn", "high_ccn_count",
                        "medium_ccn_count", "high_ccn_ratio", "suggestion")} if cx else None,
        "top_complex_functions": (cx.get("top_complex_functions") or [])[:10],
        "long_functions": (cx.get("long_functions") or [])[:10],
        "code_smells": d.get("code_smells"),
    }


def _prune_security(d):
    if not d:
        return None
    osv = d.get("dependency_vulnerabilities") or {}
    asec = d.get("audit_security") or {}
    sh = d.get("static_heuristics") or {}
    return {
        "dependency_vulnerabilities": {
            "found": osv.get("found"), "queried": osv.get("queried"),
            "affected_package_count": osv.get("affected_package_count"),
            "vulnerability_entries": osv.get("vulnerability_entries"),
            "affected_packages": (osv.get("affected_packages") or [])[:15],
            "reason": osv.get("reason"), "suggestion": osv.get("suggestion")},
        "audit_security": {k: asec.get(k) for k in
                           ("source", "audit_generated_at", "staleness_note", "total",
                            "by_severity", "top_rules", "suggestion")},
        "static_heuristics": {
            "boundary_note": sh.get("boundary_note"),
            "patterns_matched": sh.get("patterns_matched"),
            "hit_samples": {k: v[:5] for k, v in (sh.get("hits") or {}).items()}},
        "best_practices": d.get("best_practices"),
    }


def _prune_generic(d, limit=3500):
    """docs/tests/performance/overview：保留全部关键统计，兜底截断"""
    return _trim(d, limit)


# ---------- 解读型任务的深度裁剪（L3：只留统计值与 TOP 少数，砍明细样例） ----------

def _prune_structure_lite(d):
    if not d:
        return None
    return {
        "total_files": d.get("total_files"),
        "primary_language": d.get("primary_language"),
        "languages": {k: v.get("lines") for k, v in list((d.get("languages") or {}).items())[:6]},
        "categories": d.get("categories"),
        "test_to_production_ratio": d.get("test_to_production_ratio"),
        "top_dirs": list((d.get("top_level_dirs") or {}).keys())[:10],
        "longest_files": (d.get("longest_files") or [])[:5],
    }


def _prune_deps_lite(d):
    if not d:
        return None
    g = d.get("dependency_graph") or {}
    return {
        "manifests_detected": d.get("manifests_detected"),
        "dependency_count": d.get("dependency_count"),
        "pinned_ratio": d.get("pinned_ratio"),
        "unpinned_count": (d.get("unpinned_versions") or {}).get("count"),
        "graph": {"tool": g.get("tool"), "nodes": len(g.get("nodes") or []),
                  "edges": len(g.get("edges") or []), "reason": g.get("reason")} if g else None,
    }


def _prune_quality_lite(d):
    if not d:
        return None
    lint = d.get("style_lint") or {}
    cx = d.get("complexity") or {}
    return {
        "style_lint": {k: lint.get(k) for k in ("source", "audit_generated_at", "staleness_note",
                                                "total", "by_severity", "suggestion")},
        "top_rules": (lint.get("top_rules") or [])[:5],
        "complexity": {k: cx.get(k) for k in ("functions_analyzed", "average_ccn",
                                              "high_ccn_count", "medium_ccn_count",
                                              "high_ccn_ratio", "suggestion")},
        "top_complex_functions": (cx.get("top_complex_functions") or [])[:3],
        "long_file_count": len(cx.get("long_files") or []),
        "code_smells": d.get("code_smells"),
    }


def _prune_security_lite(d):
    if not d:
        return None
    osv = d.get("dependency_vulnerabilities") or {}
    asec = d.get("audit_security") or {}
    sh = d.get("static_heuristics") or {}
    return {
        "osv": {"found": osv.get("found"), "queried": osv.get("queried"),
                "affected_package_count": osv.get("affected_package_count"),
                "vulnerability_entries": osv.get("vulnerability_entries"),
                "top_affected": [{k: p.get(k) for k in ("package", "version")}
                                 | {"vuln_count": len(p.get("vuln_ids") or [])}
                                 for p in (osv.get("affected_packages") or [])[:5]],
                "note": osv.get("reason") or osv.get("suggestion")},
        "audit_security": {k: asec.get(k) for k in ("source", "total", "by_severity",
                                                    "audit_generated_at", "suggestion")},
        "static_patterns_matched": sh.get("patterns_matched"),
        "best_practices": d.get("best_practices"),
    }


def _prune_scoring_lite(d):
    if not d:
        return None
    dims = {}
    for dim, v in (d.get("dimensions") or {}).items():
        factors = sorted((f for f in (v.get("factors") or [])
                          if isinstance(f.get("impact"), (int, float)) and f["impact"] < 0),
                         key=lambda f: f["impact"])[:2]
        dims[dim] = {"score": v.get("score"), "weight": v.get("weight"),
                     "source": v.get("source"),
                     "top_deductions": [f["factor"] for f in factors],
                     "missing_reason": v.get("missing_reason")}
    return {"total": d.get("total"), "grade": d.get("grade"),
            "missing_dimensions": d.get("missing_dimensions"), "dimensions": dims}


def _prune_conclusions_lite(d):
    if not d:
        return None
    dims = {}
    for dim, c in (d.get("dimensions") or {}).items():
        dims[dim] = {"summary": c.get("summary"),
                     "top_findings": [{k: f.get(k) for k in ("severity", "title")}
                                      for f in (c.get("findings") or [])[:2]]}
    return {"dimensions": dims}


def _prune_arch_lite(d):
    if not d:
        return None
    return {"overview": d.get("overview"), "score": d.get("score"),
            "top_issues": [{k: i.get(k) for k in ("severity", "title")}
                           for i in (d.get("issues") or [])[:5]],
            "doc_completeness": (d.get("doc_assessment") or {}).get("completeness")}


def _prune_bk_lite(d):
    if not d:
        return None
    confs = sorted(k.get("confidence") or 0 for k in (d.get("knowledge") or []))
    return {"readiness": d.get("readiness"), "score": d.get("score"),
            "knowledge_count": len(d.get("knowledge") or []),
            "confidence_min_median_max": [confs[0], confs[len(confs) // 2], confs[-1]] if confs else None,
            "gap_count": len(d.get("gaps") or []),
            "top_gaps": [{k: g.get(k) for k in ("topic", "impact")}
                         for g in (d.get("gaps") or [])[:4]],
            "contradiction_count": len(d.get("contradictions") or [])}


def _validate(name: str, data: dict) -> None:
    schema = json.loads((AI_DIR / "schemas" / f"{name}.json").read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)


def _run_ai(ctx, template: str, allowed_tools: str | None = None, **variables) -> dict:
    mode = "探索型（只读白名单）" if allowed_tools is None else "解读型（无工具，单轮）"
    ctx.log(f"AI 子任务启动: {template}（claude headless，{mode}）")
    prompt = _jinja.get_template(f"{template}.md.j2").render(
        org=ctx.org, repo=ctx.repo, commit_sha=ctx.commit_sha, **variables)
    data, meta = ENGINE.run(
        prompt, ctx.repo_path,
        timeout=config.AI_SUBTASK_TIMEOUT - _ENGINE_GRACE,
        allowed_tools=allowed_tools)
    _validate(template, data)
    ctx.log(f"AI 子任务完成: {template}（turns={meta.get('num_turns')}, "
            f"cost=${meta.get('total_cost_usd')}, tokens in/out="
            f"{meta.get('input_tokens')}/{meta.get('output_tokens')}）")
    data["_ai_meta"] = {
        "engine": "claude-code-headless",
        "prompt_version": _prompt_version(template),
        "generated_at": now_iso(),
        "nondeterministic": True,
        "note": "AI 生成内容，相同输入下不保证完全可复现（REQ §4.4）",
        **meta,
    }
    return data


# ---------- 探索型子任务（需要 Read/Grep 查证代码） ----------

@register("ai.architecture")
def ai_architecture(ctx) -> dict:
    return _run_ai(
        ctx, "architecture",
        structure_summary=_dumps(_prune_structure(ctx.read_dependency_output("collect.structure"))),
        deps_summary=_trim(_prune_deps(ctx.read_dependency_output("collect.dependencies"),
                                       max_deps=40, max_nodes=60, max_edges=80), 5000),
        git_summary=_trim(_prune_git(ctx.read_dependency_output("collect.git_context"),
                                     recent=20, older=40, words=20), 3000))


@register("ai.business_knowledge")
def ai_business_knowledge(ctx) -> dict:
    return _run_ai(
        ctx, "business_knowledge",
        structure_summary=_trim(_prune_structure(ctx.read_dependency_output("collect.structure")), 3000),
        docs_summary=_prune_generic(ctx.read_dependency_output("collect.docs"), 2500),
        git_summary=_trim(_prune_git(ctx.read_dependency_output("collect.git_context"),
                                     recent=25, older=40, words=25), 4500))


# ---------- 解读型子任务（空白名单 + 深度裁剪注入：只留统计值与 TOP 少数） ----------

@register("ai.conclusions")
def ai_conclusions(ctx) -> dict:
    return _run_ai(
        ctx, "conclusions", allowed_tools="",
        structure_summary=_dumps(_prune_structure_lite(ctx.read_dependency_output("collect.structure"))),
        deps_summary=_dumps(_prune_deps_lite(ctx.read_dependency_output("collect.dependencies"))),
        quality_summary=_dumps(_prune_quality_lite(ctx.read_dependency_output("collect.quality"))),
        security_summary=_dumps(_prune_security_lite(ctx.read_dependency_output("collect.security"))),
        performance_summary=_prune_generic(ctx.read_dependency_output("collect.performance"), 1800),
        docs_summary=_prune_generic(ctx.read_dependency_output("collect.docs"), 1800),
        tests_summary=_prune_generic(ctx.read_dependency_output("collect.tests"), 1800))


@register("ai.summary")
def ai_summary(ctx) -> dict:
    return _run_ai(
        ctx, "summary", allowed_tools="",
        scoring_summary=_dumps(_prune_scoring_lite(ctx.read_dependency_output("scoring"))),
        conclusions_summary=_dumps(_prune_conclusions_lite(ctx.read_dependency_output("ai.conclusions"))),
        architecture_summary=_dumps(_prune_arch_lite(ctx.read_dependency_output("ai.architecture"))),
        business_summary=_dumps(_prune_bk_lite(ctx.read_dependency_output("ai.business_knowledge"))),
        overview_summary=_prune_generic(ctx.read_dependency_output("collect.overview"), 1500))
