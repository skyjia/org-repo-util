"""M3/M5 单元测试：scoring 评分模型 + 归档 JSON 组装"""

import pytest

from analysis.core import config
from analysis.core.models import SubtaskState, SubtaskStatus, Task
from analysis.core.scoring import compute_scores
from analysis.reporters.json_report import aggregate_issues, build_report


# ---------- scoring ----------

def test_all_missing_graceful():
    result = compute_scores({})
    assert result["total"] is None
    assert result["grade"] is None
    assert len(result["missing_dimensions"]) == 9
    for dim, v in result["dimensions"].items():
        assert v["score"] is None
        assert v["weight"] == config.SCORE_WEIGHTS[dim]


def test_grade_thresholds():
    good = {
        "collect.structure": {"total_files": 10, "primary_language": "Go",
                              "longest_files": [], "categories": {
                                  "production": {"lines": 1000}, "test": {"lines": 300},
                                  "generated_or_vendored": {"lines": 0}}},
        "collect.dependencies": {"manifests_detected": ["go.mod"], "dependency_count": {"total": 10},
                                 "unpinned_versions": {"count": 0}, "pinned_ratio": 1.0,
                                 "dependency_graph": {"tool": "go mod graph", "nodes": [], "edges": []}},
        "collect.quality": {"style_lint": {"source": None, "found": False},
                            "complexity": {"functions_analyzed": 100, "average_ccn": 3,
                                           "high_ccn_ratio": 0.0, "high_ccn_count": 0,
                                           "long_functions": []},
                            "code_smells": []},
        "collect.security": {"dependency_vulnerabilities": {"found": True, "vulnerable": [], "queried": 10},
                             "audit_security": {"found": False},
                             "static_heuristics": {"patterns_matched": {}, "hits": {}},
                             "best_practices": {"lockfile_present": True, "env_file_committed": False,
                                                "no_private_key_files": True}},
        "collect.performance": {"total_suspected": 0, "boundary_declaration": "x",
                                "antipattern_counts": {}},
        "collect.docs": {"readme": {"found": True, "completeness": 1.0},
                         "overall_comment_ratio": 0.12,
                         "api_docs": {"found": True}, "public_api_docs": {},
                         "doc_files": {"CHANGELOG.md": True, "CONTRIBUTING.md": True}},
        "collect.tests": {"test_to_production_ratio": 0.3,
                          "ci": {"runs_tests_in_ci": True},
                          "coverage_artifacts": {"found": True},
                          "frameworks": {"go test": True},
                          "empty_or_assertion_free_tests": [], "skipped_test_markers": 0},
        "ai.architecture": {"score": 85, "score_reasons": ["r1"]},
        "ai.business_knowledge": {"score": 80, "score_reasons": ["r1"],
                                  "readiness": {"completeness": 80, "accuracy": 80,
                                                "consistency": 80, "conclusion": "x"}},
    }
    result = compute_scores(good)
    assert result["total"] is not None
    assert result["grade"] in ("A", "B")
    assert result["missing_dimensions"] == []
    assert result["dimensions"]["architecture"]["source"] == "ai"


def test_security_affected_packages_penalized():
    base = {
        "collect.security": {
            "dependency_vulnerabilities": {
                "found": True, "queried": 20,
                "affected_package_count": 12, "vulnerability_entries": 30,
                "affected_packages": [{"package": "p", "version": "1.0",
                                       "vuln_ids": ["GHSA-x"], "urls": []}],
            },
            "audit_security": {"found": False},
            "static_heuristics": {"patterns_matched": {"hardcoded_secret": 3},
                                  "hits": {"hardcoded_secret": [
                                      {"severity": "high", "is_test_file": False}] * 3}},
            "best_practices": {"lockfile_present": True, "env_file_committed": True,
                               "no_private_key_files": True},
        },
    }
    result = compute_scores(base)
    sec = result["dimensions"]["security"]
    # -20（12 包×2 封顶 20）-4.5（3 高危模式×1.5）-10（.env 入库）→ <70
    assert sec["score"] < 70
    assert any("依赖已知漏洞" in f["factor"] for f in sec["factors"])
    assert any(".env" in f["factor"] for f in sec["factors"])


def test_security_legacy_vuln_structure_compat():
    """兼容旧结构（无 affected_package_count 时按 vulnerable 列表去重包数）"""
    base = {
        "collect.security": {
            "dependency_vulnerabilities": {"found": True, "queried": 5, "vulnerable": [
                {"id": "GHSA-x", "package": "p1", "version": "1.0", "severity": None},
                {"id": "GHSA-y", "package": "p1", "version": "1.0", "severity": None},
                {"id": "GHSA-z", "package": "p2", "version": "2.0", "severity": None}]},
            "audit_security": {"found": False},
            "static_heuristics": {"patterns_matched": {}, "hits": {}},
            "best_practices": {"lockfile_present": True, "env_file_committed": False,
                               "no_private_key_files": True},
        },
    }
    sec = compute_scores(base)["dimensions"]["security"]
    assert sec["score"] == 96.0   # 100 - 2包×2


def test_missing_dimension_normalized():
    partial = {
        "collect.structure": {"total_files": 1, "primary_language": "Go", "longest_files": [],
                              "categories": {"production": {"lines": 10}, "test": {"lines": 0},
                                             "generated_or_vendored": {"lines": 0}}},
    }
    result = compute_scores(partial)
    # 仅 structure 有分：总分 = structure 得分（权重归一化）
    assert result["total"] == result["dimensions"]["structure"]["score"]
    assert len(result["missing_dimensions"]) == 8
    assert "归一化" in result["normalization_note"]


# ---------- json report ----------

def _make_task():
    task = Task(task_id="t1", org="augmn", repo="demo", repo_path="repos/augmn/demo",
                commit_sha="abc123")
    task.subtasks = {"collect.overview": SubtaskState(name="collect.overview", type="det",
                                                      status=SubtaskStatus.COMPLETED)}
    return task


def test_build_report_structure():
    task = _make_task()
    outputs = {"collect.overview": {"name": "demo", "git": {"total_commits": 5}}}
    report = build_report(task, outputs)
    assert report["metadata"]["org"] == "augmn"
    assert report["metadata"]["commit_sha"] == "abc123"
    assert report["metadata"]["schema_version"] == config.SCHEMA_VERSION
    assert len(report["metadata"]["limitations"]) >= 4
    assert set(report["chapters"].keys()) == {
        "overview", "structure", "dependencies", "quality", "security",
        "performance", "docs", "tests", "architecture", "business_knowledge", "summary"}
    assert report["chapters"]["overview"]["data"]["name"] == "demo"
    assert report["issues"] == []


def test_aggregate_issues_dedupe_and_order():
    outputs = {
        "ai.summary": {"top_issues": [
            {"priority": "P0", "dimension": "security", "title": "严重漏洞", "detail": "d"},
            {"priority": "P2", "dimension": "docs", "title": "文档缺失"}]},
        "ai.conclusions": {"dimensions": {
            "quality": {"summary": "s", "findings": [
                {"severity": "high", "title": "复杂度高", "detail": "x", "evidence": ["a.go:1"]}],
                "suggestions": []}}},
        "ai.business_knowledge": {"contradictions": [
            {"type": "doc_vs_code", "description": "README 与实现矛盾", "severity": "medium"}]},
        "collect.security": {
            "dependency_vulnerabilities": {"vulnerable": [
                {"id": "GHSA-1", "package": "p", "version": "1.0", "severity": "HIGH"}]},
            "static_heuristics": {"hits": {
                "dangerous_eval": [{"severity": "high", "is_test_file": False,
                                    "file": "x.js", "line": 3, "note": "eval", "evidence": "eval("}]}}},
    }
    issues = aggregate_issues(outputs)
    priorities = [i["priority"] for i in issues]
    assert priorities == sorted(priorities, key=lambda p: {"P0": 0, "P1": 1, "P2": 2}[p])
    titles = [i["title"] for i in issues]
    assert len(titles) == len(set((i["dimension"], t) for i, t in zip(issues, titles)))
    assert any(i["source"] == "osv" for i in issues)
    assert any(i["source"] == "static_heuristic" for i in issues)
    assert any(i["dimension"] == "business_knowledge" for i in issues)
