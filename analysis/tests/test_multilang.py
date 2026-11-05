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


# ---------- fork 预检 ----------

def test_check_fork_detection(monkeypatch):
    from analysis.core import service

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="true\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    is_fork, note = service.check_fork("augmn", "sqlfluff")
    assert is_fork is True and note is None


def test_check_fork_api_unreachable(monkeypatch):
    from analysis.core import service

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="network error")

    monkeypatch.setattr(subprocess, "run", fake_run)
    is_fork, note = service.check_fork("augmn", "x")
    assert is_fork is None and "fork 预检跳过" in note


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
