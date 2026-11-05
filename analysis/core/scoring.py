"""健康度评分（REQ §3.11 已决策权重 + ANALYSIS-DESIGN.md §7）

- 7 个维度规则评分（基线 100 扣分制 / 分项累加制，factors 因子明细可解释，决策 D9）
- 2 个维度取 AI 评分（architecture / business_knowledge）
- 缺失维度 score=null，加权时按剩余权重归一化（决策 D4）
"""

from __future__ import annotations

from typing import Any, Optional

from analysis.core import config

# 子任务产物 → 评分维度
DIMENSION_SOURCE = {
    "structure": "collect.structure",
    "dependencies": "collect.dependencies",
    "quality": "collect.quality",
    "security": "collect.security",
    "performance": "collect.performance",
    "docs": "collect.docs",
    "tests": "collect.tests",
    "architecture": "ai.architecture",
    "business_knowledge": "ai.business_knowledge",
}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _f(name: str, impact: float, detail: str) -> dict:
    return {"factor": name, "impact": round(impact, 1), "detail": detail}


def _missing(reason: str) -> dict:
    return {"score": None, "source": "unavailable", "factors": [],
            "missing_reason": reason}


# ---------- 规则评分 ×7 ----------

def _score_structure(d: Optional[dict]) -> dict:
    if not d:
        return _missing("collect.structure 产物缺失")
    score = 100.0
    factors = []
    long_files = len(d.get("longest_files", []))
    if long_files:
        impact = -min(20, long_files * 2)
        score += impact
        factors.append(_f("超长文件", impact, f"TOP 榜中 {long_files} 个文件（>800 行），每个 -2"))
    cats = d.get("categories", {})
    total = sum(c.get("lines", 0) for c in cats.values()) or 1
    gen_ratio = cats.get("generated_or_vendored", {}).get("lines", 0) / total
    if gen_ratio > 0.5:
        score -= 5
        factors.append(_f("生成代码占比高", -5, f"生成/vendored 代码占 {gen_ratio:.0%}，仓库卫生影响可读性"))
    if not d.get("primary_language"):
        score -= 10
        factors.append(_f("未识别主语言", -10, "行数统计未识别到代码语言"))
    return {"score": round(_clamp(score), 1), "source": "rule", "factors": factors}


def _score_dependencies(d: Optional[dict]) -> dict:
    if not d:
        return _missing("collect.dependencies 产物缺失")
    score = 100.0
    factors = []
    unp = d.get("unpinned_versions", {}).get("count", 0)
    ratio = d.get("pinned_ratio")
    if ratio is not None:
        impact = -round((1 - ratio) * 25, 1)
        score += impact
        factors.append(_f("版本未锁定", impact, f"{unp} 个依赖使用范围版本（锁定率 {ratio:.0%}），构建可复现性风险"))
    total = d.get("dependency_count", {}).get("total", 0)
    if total > 800:
        score -= 5
        factors.append(_f("依赖数量庞大", -5, f"共 {total} 个直接依赖，供应链面大"))
    elif total > 300:
        score -= 2
        factors.append(_f("依赖数量较多", -2, f"共 {total} 个直接依赖"))
    graph = d.get("dependency_graph")
    if isinstance(graph, dict) and graph.get("found") is False:
        score -= 5
        factors.append(_f("依赖图缺失", -5, graph.get("reason", "必出项降级（REQ §3.3）")))
    if not d.get("manifests_detected") or (
            isinstance(d.get("manifests_detected"), list)
            and d["manifests_detected"] and isinstance(d["manifests_detected"][0], dict)
            and d["manifests_detected"][0].get("found") is False):
        return _missing("未检测到依赖清单")
    return {"score": round(_clamp(score), 1), "source": "rule", "factors": factors}


def _score_quality(d: Optional[dict]) -> dict:
    if not d:
        return _missing("collect.quality 产物缺失")
    score = 100.0
    factors = []
    lint = d.get("style_lint", {})
    if lint.get("source") == "audit":
        kloc = max((lint.get("lines_scanned") or 0) / 1000, 0.1) if lint.get("lines_scanned") else 1
        sev = lint.get("by_severity", {})
        density = (sev.get("high", 0) * 3 + sev.get("medium", 0) * 1
                   + sev.get("low", 0) * 0.3) / kloc
        impact = -min(35, round(density * 2, 1))
        score += impact
        factors.append(_f("lint 问题密度", impact,
                          f"audit 桥接：{lint.get('total', 0)} 个问题 / {kloc:.1f} KLOC（high×3 + medium×1 加权）"))
    else:
        factors.append(_f("lint 数据缺失", 0, "audit 产物不可用，本项不计扣分（结论中已标注数据缺失）"))
    cx = d.get("complexity", {})
    if isinstance(cx, dict) and cx.get("functions_analyzed"):
        hr = cx.get("high_ccn_ratio") or 0
        impact = -min(25, round(hr * 150, 1))
        score += impact
        factors.append(_f("高复杂度函数占比", impact,
                          f"CCN>{25} 占比 {hr:.1%}（{cx.get('high_ccn_count')} 个）"))
        avg = cx.get("average_ccn") or 0
        if avg > 10:
            score -= 10
            factors.append(_f("平均复杂度高", -10, f"平均 CCN {avg}"))
        lf = len(cx.get("long_functions", []))
        if lf:
            impact = -min(10, lf * 0.5)
            score += impact
            factors.append(_f("超长函数", impact, f"TOP 榜中 {lf} 个函数（>100 行）"))
    return {"score": round(_clamp(score), 1), "source": "rule", "factors": factors}


def _score_security(d: Optional[dict]) -> dict:
    if not d:
        return _missing("collect.security 产物缺失")
    score = 100.0
    factors = []
    osv = d.get("dependency_vulnerabilities", {})
    if osv.get("found"):
        crit = high = other = 0
        for v in osv.get("vulnerable", []):
            sev = str(v.get("severity") or "").upper()
            if "CRIT" in sev:
                crit += 1
            elif "HIGH" in sev:
                high += 1
            else:
                other += 1
        impact = -(min(40, crit * 20) + min(30, high * 10) + min(12, other * 3))
        score += impact
        factors.append(_f("依赖已知漏洞", impact,
                          f"OSV 匹配：critical={crit} high={high} 其他={other}（共查询 {osv.get('queried')} 个精确版本依赖）"))
    elif osv.get("degraded"):
        factors.append(_f("OSV 降级", 0, osv.get("reason", "漏洞库不可达，本项不计扣分")))
    audit_sec = d.get("audit_security", {})
    if audit_sec.get("source") == "audit" and audit_sec.get("total"):
        sev = audit_sec.get("by_severity", {})
        impact = -min(25, sev.get("high", 0) * 3 + sev.get("medium", 0) * 1)
        score += impact
        factors.append(_f("audit 安全问题", impact, f"桥接 audit：{audit_sec.get('total')} 个安全问题"))
    heur = d.get("static_heuristics", {}).get("patterns_matched", {})
    hits = d.get("static_heuristics", {}).get("hits", {})
    crit_hits = sum(len(hits.get(p, [])) for p in ("private_key_material",) if p in hits)
    high_hits = sum(heur.get(p, 0) for p in
                    ("hardcoded_secret", "dangerous_eval", "py_os_system", "py_subprocess_shell",
                     "py_pickle", "js_shell_exec", "go_exec_command", "cs_sql_concat"))
    if crit_hits:
        score -= min(20, crit_hits * 10)
        factors.append(_f("私钥材料入库", -min(20, crit_hits * 10), f"{crit_hits} 处命中（critical）"))
    if high_hits:
        impact = -min(15, high_hits * 1.5)
        score += impact
        factors.append(_f("高危静态模式", impact, f"{high_hits} 处疑似高危模式命中（需人工复核）"))
    bp = d.get("best_practices", {})
    if bp.get("env_file_committed"):
        score -= 10
        factors.append(_f(".env 文件入库", -10, "环境文件已提交，存在凭据泄露风险"))
    if not bp.get("lockfile_present"):
        score -= 5
        factors.append(_f("缺少 lockfile", -5, "依赖版本未锁定，供应链攻击面增大"))
    if not bp.get("no_private_key_files", True):
        score -= 10
        factors.append(_f("密钥文件入库", -10, "发现 .pem/.key/.p12 文件"))
    return {"score": round(_clamp(score), 1), "source": "rule", "factors": factors}


def _score_performance(d: Optional[dict]) -> dict:
    if not d:
        return _missing("collect.performance 产物缺失")
    total = d.get("total_suspected", 0)
    factors = [_f("静态启发式", 0, d.get("boundary_declaration", "")[:120])]
    if total > 50:
        impact = -15
    elif total > 20:
        impact = -10
    elif total > 5:
        impact = -5
    else:
        impact = 0
    score = 100 + impact
    if impact:
        factors.append(_f("疑似性能反模式", impact, f"{total} 处疑似命中（均为 suspected，未运行测试）"))
    return {"score": round(_clamp(score), 1), "source": "rule", "factors": factors,
            "confidence_note": "静态启发式可信度低，权重已按 REQ §3.11 设为最小（6%）"}


def _score_docs(d: Optional[dict]) -> dict:
    if not d:
        return _missing("collect.docs 产物缺失")
    factors = []
    readme = d.get("readme", {})
    if readme.get("found"):
        part = round(readme.get("completeness", 0) * 35, 1)
        factors.append(_f("README 完整性", part - 35,
                          f"章节完整度 {readme.get('completeness', 0):.0%}，缺失: {readme.get('missing_sections') or '无'}"))
    else:
        part = 0
        factors.append(_f("README 缺失", -35, readme.get("suggestion", "")))
    ratio = d.get("overall_comment_ratio", 0)
    comment_part = min(25, round(ratio * 250, 1))
    factors.append(_f("注释率", comment_part - 25, f"总体注释率 {ratio:.1%}（10% 计满分）"))
    api = d.get("api_docs", {})
    api_part = 10 if api.get("found") else 0
    factors.append(_f("API 文档", api_part - 10, "已发现" if api.get("found") else "未发现 OpenAPI/Swagger"))
    pub = d.get("public_api_docs", {})
    ratios = [v.get("documented_ratio") for v in pub.values()
              if isinstance(v, dict) and v.get("documented_ratio") is not None]
    if ratios:
        pub_part = round(sum(ratios) / len(ratios) * 20, 1)
        factors.append(_f("公共 API 注释", pub_part - 20, f"文档注释比例均值 {sum(ratios)/len(ratios):.0%}"))
    else:
        pub_part = 10
        factors.append(_f("公共 API 注释", -10, "未识别到公共 API（取中位分）"))
    doc_files = d.get("doc_files", {})
    extra = sum(5 for k in ("CHANGELOG.md", "CONTRIBUTING.md") if doc_files.get(k))
    factors.append(_f("工程文档", min(10, extra) - 10, "CHANGELOG/CONTRIBUTING 各 +5"))
    score = part + comment_part + api_part + pub_part + min(10, extra)
    return {"score": round(_clamp(score), 1), "source": "rule", "factors": factors}


def _score_tests(d: Optional[dict]) -> dict:
    if not d:
        return _missing("collect.tests 产物缺失")
    factors = []
    ratio = d.get("test_to_production_ratio", 0)
    if ratio >= 0.25:
        part = 45
    elif ratio >= 0.15:
        part = 35
    elif ratio >= 0.05:
        part = 20
    elif ratio > 0:
        part = 10
    else:
        part = 0
    factors.append(_f("测试代码占比", part - 45, f"测试/生产代码行比 {ratio:.1%}（≥25% 计满分）"))
    ci = d.get("ci", {})
    ci_part = 20 if ci.get("runs_tests_in_ci") else 0
    factors.append(_f("CI 自动化测试", ci_part - 20,
                      "CI 中已配置测试执行" if ci_part else "CI 未发现测试执行配置"))
    cov = d.get("coverage_artifacts", {})
    cov_part = 15 if cov.get("found") else 0
    factors.append(_f("覆盖率产物", cov_part - 15,
                      "仓库存在覆盖率报告" if cov_part else "未发现覆盖率报告产物"))
    fw = d.get("frameworks", {})
    fw_part = 10 if isinstance(fw, dict) and fw.get("found") is not False and fw else 0
    factors.append(_f("测试框架", fw_part - 10, "已识别测试框架" if fw_part else "未识别到测试框架"))
    empty = len(d.get("empty_or_assertion_free_tests", []))
    penalty = -min(9, empty * 3)
    factors.append(_f("空测试", penalty, f"{empty} 个测试文件未检出断言"))
    score = part + ci_part + cov_part + fw_part + penalty
    if d.get("skipped_test_markers", 0) > 20:
        score -= 5
        factors.append(_f("跳过的测试过多", -5, f"{d['skipped_test_markers']} 处 skip 标记"))
    return {"score": round(_clamp(score), 1), "source": "rule", "factors": factors}


# ---------- AI 评分 ×2 ----------

def _score_from_ai(d: Optional[dict], dim: str) -> dict:
    if not d or d.get("score") is None:
        return _missing(f"{dim} AI 子任务产物缺失")
    return {"score": round(_clamp(float(d["score"])), 1), "source": "ai",
            "factors": [{"factor": r, "impact": None, "detail": "AI 评分理由"}
                        for r in d.get("score_reasons", [])],
            "nondeterministic": True}


# ---------- 汇总 ----------

def compute_scores(outputs: dict[str, Optional[dict]]) -> dict:
    """outputs: {子任务名: 产物 dict 或 None}"""
    rule_fns = {
        "structure": _score_structure, "dependencies": _score_dependencies,
        "quality": _score_quality, "security": _score_security,
        "performance": _score_performance, "docs": _score_docs, "tests": _score_tests,
    }
    dims: dict[str, Any] = {}
    for dim, fn in rule_fns.items():
        dims[dim] = fn(outputs.get(DIMENSION_SOURCE[dim]))
    for dim in ("architecture", "business_knowledge"):
        dims[dim] = _score_from_ai(outputs.get(DIMENSION_SOURCE[dim]), dim)

    for dim, v in dims.items():
        v["weight"] = config.SCORE_WEIGHTS[dim]

    valid = {k: v for k, v in dims.items() if v.get("score") is not None}
    missing = sorted(k for k in dims if dims[k].get("score") is None)
    total_weight = sum(config.SCORE_WEIGHTS[k] for k in valid)
    if total_weight:
        total = round(sum(v["score"] * config.SCORE_WEIGHTS[k] for k, v in valid.items())
                      / total_weight, 1)
        grade = _grade(total)
    else:
        total, grade = None, None

    return {
        "schema_version": config.SCHEMA_VERSION,
        "dimensions": dims,
        "total": total,
        "grade": grade,
        "missing_dimensions": missing,
        "normalization_note": (
            f"维度 {missing} 数据缺失，总分按剩余 {total_weight}% 权重归一化计算（决策 D4）"
            if missing else "全部 9 个维度参与加权"),
    }


def _grade(total: Optional[float]) -> Optional[str]:
    if total is None:
        return None
    for threshold, grade in config.GRADE_THRESHOLDS:
        if total >= threshold:
            return grade
    return "F"


# ---------- scoring 子任务 handler ----------

def register_scoring_handler() -> None:
    from analysis.core.registry import register

    @register("scoring")
    def scoring_handler(ctx) -> dict:
        outputs = {}
        for dim, subtask in DIMENSION_SOURCE.items():
            outputs[subtask] = ctx.read_dependency_output(subtask)
        result = compute_scores(outputs)
        ctx.log(f"评分完成: 总分 {result['total']} 等级 {result['grade']}"
                + (f"（缺失维度: {result['missing_dimensions']}）" if result["missing_dimensions"] else ""))
        return result
