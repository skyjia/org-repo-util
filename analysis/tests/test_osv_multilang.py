"""OSV 生态映射 / 版本归一化 与 测试框架启发式（M7 T706 验证期间修复）"""

from collections import Counter


# ---------- OSV 查询构造 ----------

def test_osv_query_normalizes_pinned_requirements(monkeypatch):
    """requirements.txt 的 '==5.2.0' 约束必须归一化为可查版本；范围版本仍跳过

    修复前：PyPI 依赖全部被 `^\\d+\\.\\d+` 拦在门外 → 22 个 Python 仓库的
    依赖漏洞匹配静默 found:false（实测 ops-mdm 修复后 45 入查 / 11 包受影响）。
    """
    import requests

    from analysis.collectors import security

    captured = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"results": [{"vulns": [{"id": "GHSA-1"}]}, {}]}

    def fake_post(url, json=None, timeout=None):
        captured["payload"] = json
        return FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    out = security._osv_query({
        "celery[redis]": {"version": "==5.3.6", "manifest": "requirements.txt/pyproject.toml"},
        "django": {"version": ">=4.0", "manifest": "requirements.txt/pyproject.toml"},
    })
    assert captured["payload"]["queries"] == [
        {"package": {"name": "celery", "ecosystem": "PyPI"}, "version": "5.3.6"}]
    assert out["found"] is True and out["queried"] == 1
    assert out["affected_packages"][0]["package"] == "celery"


def test_osv_query_new_ecosystems_mapped(monkeypatch):
    """M7 新增生态（Pub / Maven / RubyGems）的精确版本进入查询，非版本值跳过"""
    import requests

    from analysis.collectors import security

    captured = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"results": [{}, {}, {}]}

    monkeypatch.setattr(requests, "post",
                        lambda url, json=None, timeout=None: (
                            captured.__setitem__("payload", json), FakeResp())[1])
    out = security._osv_query({
        "http": {"version": "1.2.0", "manifest": "pubspec.yaml"},
        "org.springframework.boot:spring-boot": {"version": "3.2.0", "manifest": "pom.xml"},
        "rake": {"version": "13.0.6", "manifest": "Gemfile.lock"},
        "flutter": {"version": "(source-ref)", "manifest": "pubspec.yaml"},
    })
    ecosystems = {q["package"]["ecosystem"] for q in captured["payload"]["queries"]}
    assert ecosystems == {"Pub", "Maven", "RubyGems"}
    assert out["found"] is True and out["queried"] == 3


# ---------- 测试框架启发式（按主语言给建议 + CI 步骤识别） ----------

def test_framework_hint_follows_dominant_language():
    from analysis.collectors.tests import _framework_hint

    assert "bats" in _framework_hint(Counter({".sh": 40, ".py": 2}))
    assert "pytest" in _framework_hint(Counter({".py": 40}))
    assert "rspec" in _framework_hint(Counter({".rb": 12}))
    # 未知/无代码：退回通用清单，不硬编码某一生态
    generic = _framework_hint(Counter())
    assert "pytest" in generic and "vitest" in generic


def test_ci_test_steps_recognize_multilang_commands(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(
        "jobs:\n  t:\n    steps:\n      - run: bats tests/\n      - run: flutter test\n"
        "      - run: mvn -B test\n      - run: rspec\n")
    from analysis.collectors.tests import _ci_test_steps

    out = _ci_test_steps(tmp_path)
    assert out["found"] is True and out["runs_tests_in_ci"] is True
    hits = " ".join(out["workflows"][0]["test_steps_found"])
    for cmd in ("bats", "flutter test", "rspec"):
        assert cmd in hits, cmd
