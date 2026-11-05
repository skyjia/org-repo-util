"""M7 多语言支持单元测试：守护/fork 预检/新解析器/lint 工具"""

import json
import subprocess
from pathlib import Path

import pytest

from analysis.core import config
from analysis.core.models import SubtaskState, SubtaskStatus, Task, TaskStatus
from analysis.core.orchestrator import Orchestrator
from analysis.core.registry import HANDLERS, SUBTASK_SPECS
from analysis.core.store import TaskStore
from analysis.collectors.lint_tools import _ruff_severity


@pytest.fixture(autouse=True)
def clean_handlers():
    yield
    HANDLERS.clear()


@pytest.fixture
def store(tmp_path):
    return TaskStore(tasks_dir=tmp_path / "tasks", state_dir=tmp_path)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True, capture_output=True)
    return r


def _make_task_with_structure(store, repo, prod_lines, task_id="t1"):
    task = Task(task_id=task_id, org="o", repo="r", repo_path=str(repo), mock=True)
    task.subtasks = {s.name: SubtaskState(name=s.name, type=s.type) for s in SUBTASK_SPECS}
    store.create_task(task)
    # 预置 structure 产物（守护检查数据源）
    out = store.output_path(task_id, "collected/structure.json")
    out.write_text(json.dumps({
        "total_files": 5, "primary_language": None,
        "categories": {"production": {"lines": prod_lines, "files": 3},
                       "test": {"lines": 0, "files": 0},
                       "generated_or_vendored": {"lines": 0, "files": 0}},
    }))
    # structure 标记 completed（模拟已采集）
    t = store.load_task(task_id)
    t.subtasks["collect.structure"].status = SubtaskStatus.COMPLETED
    store.save_task(t)
    return task


# ---------- 空仓库守护 ----------

def test_no_code_guard_skips_ai_and_scoring(store, repo):
    _make_task_with_structure(store, repo, prod_lines=50)   # < 100 阈值
    task = Orchestrator(store).run_task(store.load_task("t1"))

    for name, st in task.subtasks.items():
        spec_type = st.type
        if spec_type == "ai" or name == "scoring":
            assert st.status == SubtaskStatus.SKIPPED, name
            assert "空仓库守护" in (st.skip_reason or "")
    # archive 照常（简版报告路径）
    assert task.subtasks["report.archive"].status == SubtaskStatus.COMPLETED
    assert task.status == TaskStatus.COMPLETED


def test_code_repo_guard_not_triggered(store, repo):
    _make_task_with_structure(store, repo, prod_lines=5000, task_id="t2")
    task = Orchestrator(store).run_task(store.load_task("t2"))
    # mock 模式下 AI 子任务照常执行（mock handler）
    assert task.subtasks["ai.architecture"].status == SubtaskStatus.COMPLETED
    assert task.subtasks["scoring"].status == SubtaskStatus.COMPLETED


# ---------- --no-ai 计划跳过 ----------

def test_no_ai_skips_ai_but_keeps_scoring_and_archive(store, repo):
    """--no-ai：AI 子任务全部 skipped，scoring 与 report.archive 照常（零 AI 成本验证路径）"""
    from analysis.core.scoring import register_scoring_handler
    register_scoring_handler()          # mock 模式下 scoring 属 passthrough，需真实 handler
    _make_task_with_structure(store, repo, prod_lines=5000, task_id="t3")
    t = store.load_task("t3")
    t.no_ai = True
    store.save_task(t)

    task = Orchestrator(store).run_task(t)
    ai_names = [s.name for s in SUBTASK_SPECS if s.type == "ai"]
    for name in ai_names:
        st = task.subtasks[name]
        assert st.status == SubtaskStatus.SKIPPED, name
        assert st.skip_reason.startswith(config.SKIP_TAG_NO_AI), name
    # AI 依赖属「计划跳过」，不阻塞评分（缺失维度按剩余权重归一化，决策 D4）
    assert task.subtasks["scoring"].status == SubtaskStatus.COMPLETED
    assert task.subtasks["report.archive"].status == SubtaskStatus.COMPLETED
    assert task.status == TaskStatus.COMPLETED
    scoring = json.loads(
        (store.task_dir("t3") / "collected" / "scoring.json").read_text(encoding="utf-8"))
    assert "_mock" not in scoring          # 走的是真实评分链路
    assert {"architecture", "business_knowledge"} <= set(scoring["missing_dimensions"])
    assert scoring["total"] is not None    # 缺失维度归一化后仍有分数


def test_no_ai_report_marked_deterministic_only(store, repo):
    from analysis.reporters.json_report import build_metadata

    _make_task_with_structure(store, repo, prod_lines=5000, task_id="t4")
    t = store.load_task("t4")
    t.no_ai = True
    store.save_task(t)
    Orchestrator(store).run_task(t)
    meta = build_metadata(store.load_task("t4"), {})
    assert meta["analysis_scope"] == "deterministic_only"
    assert meta["repository_class"] == "code"      # 非空仓库，仅范围收窄


def test_no_ai_survives_retry(store, repo, monkeypatch):
    """回归（T706 实测踩坑 $1.52）：retry 未级联到的 AI 子任务仍是上轮的 skipped，
    若据此放行就会在 --no-ai 任务上真实调用 AI。断言 AI 在任何状态下都不执行。"""
    from analysis.core import daemon as daemon_mod
    from analysis.core.service import set_retry

    monkeypatch.setattr(daemon_mod, "ensure_daemon", lambda *a, **k: None)
    _make_task_with_structure(store, repo, prod_lines=5000, task_id="t6")
    t = store.load_task("t6")
    t.no_ai = True
    store.save_task(t)
    Orchestrator(store).run_task(t)

    set_retry(store, "t6", subtask="collect.security")     # 仅重置 security 及其下游
    t = store.load_task("t6")
    assert t.subtasks["ai.architecture"].status == SubtaskStatus.SKIPPED   # 未列入级联
    task = Orchestrator(store).run_task(t)

    for name in ("ai.architecture", "ai.business_knowledge", "ai.conclusions", "ai.summary"):
        st = task.subtasks[name]
        assert st.status == SubtaskStatus.SKIPPED, (name, st.status)
        assert st.duration_seconds is None, f"{name} 被真实执行了（应零 AI 成本）"
        assert st.attempts == 0, f"{name} attempts={st.attempts}"


# ---------- fork 预检 ----------

def _fake_gh(stdout="", stderr="", rc=0):
    """构造 gh api 替身（返回 fork/archived 两字段）"""
    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr=stderr)
    return run


def test_check_fork_detection(monkeypatch):
    from analysis.core import service

    monkeypatch.setattr(subprocess, "run", _fake_gh(stdout="true false\n"))
    is_fork, note = service.check_fork("augmn", "sqlfluff")
    assert is_fork is True and note is None


def test_repo_flags_fork_and_archived(monkeypatch):
    from analysis.core import service

    monkeypatch.setattr(subprocess, "run", _fake_gh(stdout="true true\n"))
    assert service.repo_flags("augmn", "x") == (True, True, None)

    monkeypatch.setattr(subprocess, "run", _fake_gh(stdout="false true\n"))
    assert service.repo_flags("augmn", "y") == (False, True, None)

    monkeypatch.setattr(subprocess, "run", _fake_gh(stdout="false false\n"))
    assert service.repo_flags("augmn", "z") == (False, False, None)


def test_check_fork_api_unreachable(monkeypatch):
    from analysis.core import service

    monkeypatch.setattr(subprocess, "run", _fake_gh(rc=1, stderr="network error"))
    is_fork, note = service.check_fork("augmn", "x")
    assert is_fork is None and "预检跳过" in note


def test_repo_flags_unknown_repo_404(monkeypatch):
    """非 GitHub 托管仓库（本地/fixture）404：不拒绝，只标注"""
    from analysis.core import service

    monkeypatch.setattr(subprocess, "run", _fake_gh(rc=1, stderr="HTTP 404: Not Found"))
    is_fork, is_archived, note = service.repo_flags("local", "x")
    assert (is_fork, is_archived) == (None, None)
    assert "GitHub 无 local/x 记录" in note


def _repo_with_git(tmp_path, monkeypatch, name="demo"):
    """在临时 repos/ 下造一个 git 仓库并把 config.REPOS_DIR 指过去"""
    root = tmp_path / "repos"
    repo = root / "augmn" / name
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "init"],
                   check=True, capture_output=True)
    monkeypatch.setattr(config, "REPOS_DIR", root)
    return repo


@pytest.mark.parametrize("flags,expect", [
    ((True, False, None), "fork 仓库按策略不分析"),        # sqlfluff 现场案例
    ((False, True, None), "archived（已归档）仓库按策略不分析"),   # 归档仓库决策
])
def test_create_task_policy_rejection(monkeypatch, tmp_path, flags, expect):
    from analysis.core import service

    _repo_with_git(tmp_path, monkeypatch, "target")
    monkeypatch.setattr(service, "repo_flags", lambda org, repo: flags)
    with pytest.raises(service.ServiceError, match=expect):
        service.create_analysis_task(
            "augmn/target", store=TaskStore(tasks_dir=tmp_path / "tasks", state_dir=tmp_path))


def test_create_task_policy_unreachable_passes_with_note(monkeypatch, tmp_path):
    """预检不可得（gh 不可达 / 非 GitHub 仓库）：放行并落一条标注事件"""
    from analysis.core import service

    _repo_with_git(tmp_path, monkeypatch, "local-only")
    monkeypatch.setattr(service, "repo_flags",
                        lambda org, repo: (None, None, "gh api 不可达：预检跳过"))
    store = TaskStore(tasks_dir=tmp_path / "tasks", state_dir=tmp_path)
    task = service.create_analysis_task("augmn/local-only", store=store, start_daemon=False)
    messages = [e.get("message", "") for e in store.read_events(task.task_id)]
    assert any("预检跳过" in m for m in messages)


def test_create_task_no_ai_persisted(monkeypatch, tmp_path):
    from analysis.core import service

    _repo_with_git(tmp_path, monkeypatch, "code")
    monkeypatch.setattr(service, "repo_flags", lambda org, repo: (False, False, None))
    store = TaskStore(tasks_dir=tmp_path / "tasks", state_dir=tmp_path)
    task = service.create_analysis_task("augmn/code", store=store,
                                        start_daemon=False, no_ai=True)
    assert store.load_task(task.task_id).no_ai is True
    messages = [e.get("message", "") for e in store.read_events(task.task_id)]
    assert any("--no-ai" in m for m in messages)


# ---------- Java / Ruby 采集层集成（T705 已搁置：保留零成本 fixture 回归） ----------

class _StubCtx:
    """采集器最小执行上下文（不入库、不写事件）"""

    def __init__(self, root: Path):
        self.repo_path, self.org, self.repo = root, "fixture", "javaruby"
        self.commit_sha, self.task, self.subtask = "HEAD", None, "collect"
        self.outputs: dict[str, dict] = {}      # 按 DAG 顺序回填上游产物

    def log(self, message: str) -> None:
        pass

    def read_dependency_output(self, subtask_name: str):
        return self.outputs.get(subtask_name)


@pytest.fixture
def javaruby_repo(tmp_path):
    r = tmp_path / "javaruby"
    (r / "src/main/java/com/x").mkdir(parents=True)
    (r / "src/test/java/com/x").mkdir(parents=True)
    (r / "lib").mkdir()
    (r / "spec/models").mkdir(parents=True)
    (r / "pom.xml").write_text(
        '<project><dependencies>'
        '<dependency><groupId>org.springframework.boot</groupId>'
        '<artifactId>spring-boot-starter</artifactId><version>3.2.0</version></dependency>'
        '<dependency><groupId>junit</groupId><artifactId>junit</artifactId>'
        '<version>4.13.2</version></dependency>'
        '</dependencies></project>')
    (r / "src/main/java/com/x/App.java").write_text(
        "package com.x;\n/** 订单服务入口，负责校验与派发。 */\n"
        "public class App {\n"
        "  /** 执行外部命令 */\n  public void run(String cmd) throws Exception {\n"
        "    Runtime.getRuntime().exec(cmd);\n  }\n}\n")
    (r / "src/test/java/com/x/AppTest.java").write_text(
        "package com.x;\nimport org.junit.Test;\nimport static org.junit.Assert.*;\n"
        "public class AppTest {\n  @Test public void t() { assertEquals(1, 1); }\n}\n")
    (r / "Gemfile").write_text(
        "source 'https://rubygems.org'\ngem 'rake', '13.0.6'\n"
        "group :development do\n  gem 'rspec', '3.12.0'\nend\n")
    (r / "Gemfile.lock").write_text(
        "GEM\n  remote: https://rubygems.org/\n  specs:\n    rake (13.0.6)\n"
        "    rspec (3.12.0)\n\nPLATFORMS\n  ruby\n")
    (r / "lib/thing.rb").write_text('''# frozen_string_literal: true

# 小部件：把名字转成大写。
class Thing
  # @param [String] name
  def initialize(name)
    @name = name
  end

  def shout
    eval("@name.upcase")
  end
end
''')
    (r / "spec/models/thing_spec.rb").write_text(
        "RSpec.describe Thing do\n  it 'upcases' do\n    expect(Thing.new('a').shout).to eq('A')\n"
        "  end\nend\n")
    return r


def test_javaruby_collectors_end_to_end(javaruby_repo, monkeypatch):
    """Java/Ruby 走同一套采集链路：依赖/测试/注释/公共 API/危险模式均应有数据"""
    import requests

    from analysis.collectors.dependencies import DependenciesCollector
    from analysis.collectors.docs import DocsCollector
    from analysis.collectors.quality import QualityCollector
    from analysis.collectors.security import SecurityCollector
    from analysis.collectors.structure import StructureCollector
    from analysis.collectors.tests import TestsCollector

    captured = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"results": [{} for _ in captured["payload"]["queries"]]}

    monkeypatch.setattr(requests, "post",
                        lambda url, json=None, timeout=None: (
                            captured.__setitem__("payload", json), FakeResp())[1])

    ctx = _StubCtx(javaruby_repo)
    st = StructureCollector().collect(ctx)
    ctx.outputs["collect.structure"] = st
    qua = QualityCollector().collect(ctx)
    ctx.outputs["collect.quality"] = qua
    dep = DependenciesCollector().collect(ctx)
    ctx.outputs["collect.dependencies"] = dep
    te = TestsCollector().collect(ctx)
    doc = DocsCollector().collect(ctx)
    sec = SecurityCollector().collect(ctx)

    assert {"Java", "Ruby"} <= set(st["languages"])
    manifests = {str(m) for m in dep["manifests_detected"]}
    assert any("pom.xml" in m for m in manifests)
    assert any("Gemfile" in m for m in manifests)
    deps = dep["external_dependencies"]
    assert deps["org.springframework.boot:spring-boot-starter"]["version"] == "3.2.0"
    assert deps["rake"]["version"] == "13.0.6"
    # OSV：Maven + RubyGems 精确版本进入查询
    assert {q["package"]["ecosystem"] for q in captured["payload"]["queries"]} \
        == {"Maven", "RubyGems"}
    # 测试：junit + rspec 识别，测试文件计数含两种语言
    fw = te["frameworks"]
    assert fw.get("junit") and fw.get("rspec")
    assert te["test_files_count"] >= 2
    # 注释与公共 API：Java javadoc / Ruby rdoc 风格注释
    assert doc["comment_stats"]["Java"]["comment_lines"] >= 2
    assert doc["comment_stats"]["Ruby"]["comment_lines"] >= 2
    assert {"Java", "Ruby"} <= set(doc["public_api_docs"])
    # 危险模式：java_runtime_exec + ruby_eval 命中
    matched = sec["static_heuristics"]["patterns_matched"]
    assert matched.get("java_runtime_exec", 0) >= 1 and matched.get("ruby_eval", 0) >= 1
    # 复杂度：lizard 支持 Java，应分析到函数
    assert qua["complexity"]["functions_analyzed"] >= 1


# ---------- lint 工具 ----------

def test_ruff_severity_mapping():
    assert _ruff_severity("E999") == "high"
    assert _ruff_severity("F821") == "high"
    assert _ruff_severity("F401") == "medium"
    assert _ruff_severity("S605") == "medium"
    assert _ruff_severity("B006") == "medium"
    assert _ruff_severity("E501") == "low"
    assert _ruff_severity("W291") == "low"


def test_run_ruff_real(tmp_path):
    """对含问题的真实 Python 文件运行 ruff（venv 内已安装）"""
    from analysis.collectors.lint_tools import run_ruff
    (tmp_path / "bad.py").write_text(
        "import os\nimport sys\ndef f(x):\n    eval(x)\n    return 1\n")
    result = run_ruff(tmp_path)
    assert result is not None
    assert result["source"] == "ruff"
    assert result["total"] >= 2                      # F401 ×2 起步
    assert any(r["rule"].startswith("F401") for r in result["top_rules"])
    assert result["bandit_security_rules"]["total"] >= 1   # S307 eval


def test_run_ruff_no_python(tmp_path):
    from analysis.collectors.lint_tools import run_ruff
    (tmp_path / "readme.md").write_text("# hi")
    assert run_ruff(tmp_path) is None


# ---------- 新 manifest 解析器 ----------

def test_parse_pubspec(tmp_path):
    from analysis.collectors.dependencies import _parse_pubspec
    (tmp_path / "pubspec.yaml").write_text(
        "name: demo_app\ndependencies:\n  flutter:\n    sdk: flutter\n"
        "  http: ^1.2.0\ndev_dependencies:\n  flutter_test:\n    sdk: flutter\n")
    out = _parse_pubspec(tmp_path)
    assert out["runtime"]["http"] == "^1.2.0"
    assert out["runtime"]["flutter"] == "(source-ref)"
    assert "flutter_test" in out["development"]


def test_parse_pom(tmp_path):
    from analysis.collectors.dependencies import _parse_pom
    (tmp_path / "pom.xml").write_text(
        "<project><dependencies><dependency>"
        "<groupId>org.springframework.boot</groupId>"
        "<artifactId>spring-boot-starter</artifactId>"
        "<version>3.2.0</version></dependency>"
        "<dependency><groupId>junit</groupId><artifactId>junit</artifactId>"
        "<version>${junit.version}</version></dependency>"
        "</dependencies></project>")
    out = _parse_pom(tmp_path)
    assert out["runtime"]["org.springframework.boot:spring-boot-starter"] == "3.2.0"
    assert out["runtime"]["junit:junit"] == "(property-ref)"


def test_parse_gemfile_lock(tmp_path):
    from analysis.collectors.dependencies import _parse_gemfile
    (tmp_path / "Gemfile.lock").write_text(
        "GEM\n  remote: https://rubygems.org/\n  specs:\n"
        "    rake (13.0.6)\n    rspec (3.12.0)\n      rspec-core (~> 3.12.0)\n\n"
        "PLATFORMS\n  ruby\n")
    out = _parse_gemfile(tmp_path)
    assert out["runtime"]["rake"] == "13.0.6"
    assert out["runtime"]["rspec"] == "3.12.0"


def test_graph_dart(tmp_path):
    from analysis.collectors.dependencies import _graph_dart
    (tmp_path / "pubspec.yaml").write_text("name: demo_app\ndependencies:\n  http: ^1.0.0\n")
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "main.dart").write_text(
        "import 'package:http/http.dart';\nimport 'package:demo_app/x.dart';\nvoid main(){}")
    g = _graph_dart(tmp_path)
    assert g["nodes"][0]["id"] == "demo_app"
    assert {"source": "demo_app", "target": "http"} in g["edges"]
    assert all(e["target"] != "demo_app" for e in g["edges"])   # 自引用排除


def test_detect_frameworks_multilang(tmp_path):
    from analysis.collectors.tests import _detect_frameworks
    (tmp_path / "pubspec.yaml").write_text(
        "name: x\ndependencies:\n  flutter:\n    sdk: flutter\n"
        "dev_dependencies:\n  flutter_test:\n    sdk: flutter\n  mockito: ^5.0.0\n")
    found = _detect_frameworks(tmp_path)
    assert "flutter_test" in found and "mockito" in found


# ---------- is_test_path 扩展 ----------

def test_is_test_path_new_languages():
    from analysis.collectors.base import is_test_path
    assert is_test_path(Path("test/widget_test.dart"))
    assert is_test_path(Path("lib/widget_test.dart"))
    assert is_test_path(Path("tests/login.bats"))
    assert is_test_path(Path("spec/models/user_spec.rb"))
    assert not is_test_path(Path("lib/main.dart"))
