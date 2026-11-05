"""开发/回归成本控制：--ai-stub 桩执行与单任务 AI 预算护栏（DESIGN D17/D18）

本项目的 token 消耗要在两处控住：工具运行时（采集层零 AI / 预算护栏）与
开发测试过程（全流程用桩，真实 AI 只在 prompt/schema 变更时抽检）。
"""

import json
from pathlib import Path

import pytest

from analysis.core import config
from analysis.core.models import SubtaskState, SubtaskStatus, Task
from analysis.core.orchestrator import Orchestrator
from analysis.core.registry import HANDLERS, SUBTASK_SPECS
from analysis.core.store import TaskStore

AI_TEMPLATES = ("architecture", "business_knowledge", "conclusions", "summary")


@pytest.fixture(autouse=True)
def clean_handlers():
    yield
    HANDLERS.clear()


@pytest.fixture
def store(tmp_path):
    return TaskStore(tasks_dir=tmp_path / "tasks", state_dir=tmp_path)


class _StubCtx:
    """AI/report handler 的最小执行上下文"""

    def __init__(self, task: Task, store: TaskStore, root: Path):
        self.task, self.store = task, store
        self.org, self.repo = task.org, task.repo
        self.repo_path, self.commit_sha = root, "deadbeef"
        self.subtask, self.mock = "test", False
        self.logs: list[str] = []

    def log(self, message: str) -> None:
        self.logs.append(message)

    def read_dependency_output(self, subtask_name: str):
        return None


@pytest.fixture
def repo(tmp_path):
    """_prepare_workspace 需要真实 git 目录"""
    import subprocess

    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True, capture_output=True)
    return r


def _make_store_task(store, repo, **fields) -> Task:
    task = Task(task_id="dev1", org="o", repo="r", repo_path=str(repo),
                mock=True, **fields)
    task.subtasks = {s.name: SubtaskState(name=s.name, type=s.type) for s in SUBTASK_SPECS}
    store.create_task(task)
    return store.load_task("dev1")


# ---------- 桩产物与 schema ----------

def test_stub_outputs_pass_schemas():
    """桩产物必须逐字通过各自 jsonschema：schema 一改此处立刻红（等真实 AI 抽检才发现就贵了）"""
    from analysis.ai.tasks import _stub_output, _validate

    for name in AI_TEMPLATES:
        _validate(name, _stub_output(name))       # 未附 _ai_meta 的原始形态


def test_stub_outputs_are_marked_non_real():
    from analysis.ai.tasks import _stub_output

    for name in AI_TEMPLATES:
        text = json.dumps(_stub_output(name), ensure_ascii=False)
        assert "桩" in text, f"{name} 桩产物缺少「桩」标注，易被误读为真实结论"


# ---------- _run_ai 桩分支 ----------

def test_run_ai_stub_never_calls_engine(tmp_path):
    from analysis.ai import tasks

    def _boom(*a, **k):
        raise AssertionError("桩执行不应调用 claude headless")

    task = Task(task_id="dev1", org="augmn", repo="demo", repo_path="repos/augmn/demo",
                commit_sha="abc", ai_stub=True)
    task.subtasks = {s.name: SubtaskState(name=s.name, type=s.type) for s in SUBTASK_SPECS}
    ctx = _StubCtx(task, TaskStore(tasks_dir=tmp_path / "t", state_dir=tmp_path), tmp_path)
    monkey = pytest.MonkeyPatch()
    monkey.setattr(tasks.ENGINE, "run", _boom)
    try:
        data = tasks._run_ai(
            ctx, "summary", allowed_tools="",
            architecture_summary="{}", business_summary="{}", conclusions_summary="{}",
            scoring_summary="{}", overview_summary="{}")
    finally:
        monkey.undo()

    meta = data["_ai_meta"]
    assert meta["stub"] is True and meta["engine"] == "stub(--ai-stub)"
    assert meta["total_cost_usd"] == 0.0 and meta["nondeterministic"] is False
    assert meta["prompt_chars"] > 200        # prompt 仍完整渲染（模板错误照常暴露）
    assert data["executive_summary"].startswith("（桩数据")
    assert any("桩执行" in m for m in ctx.logs)


def test_no_ai_takes_precedence_over_stub(repo, store):
    """同时给 --no-ai 与 --ai-stub：no_ai 优先（AI 子任务直接跳过，连桩都不生成）"""
    task = _make_store_task(store, repo, no_ai=True, ai_stub=True)
    out = store.output_path("dev1", "collected/structure.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"categories": {"production": {"lines": 5000, "files": 10}}}))
    Orchestrator(store).run_task(task)
    task = store.load_task("dev1")
    for s in SUBTASK_SPECS:
        if s.type == "ai":
            assert task.subtasks[s.name].status == SubtaskStatus.SKIPPED
            assert not (store.task_dir("dev1") / s.output_file).exists()


# ---------- 预算护栏 ----------

def test_budget_guard_skips_remaining_ai(repo, store):
    from analysis.core.scoring import register_scoring_handler
    register_scoring_handler()

    _make_store_task(store, repo)
    structure = store.output_path("dev1", "collected/structure.json")
    structure.parent.mkdir(parents=True, exist_ok=True)
    structure.write_text(json.dumps(
        {"categories": {"production": {"lines": 5000, "files": 10}}}))
    arch = store.output_path("dev1", "ai/architecture.json")
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text(json.dumps({"score": 60, "_ai_meta": {"total_cost_usd": 6.0}}))

    t = store.load_task("dev1")
    t.subtasks["collect.structure"].status = SubtaskStatus.COMPLETED
    t.subtasks["ai.architecture"].status = SubtaskStatus.COMPLETED
    t.subtasks["ai.architecture"].output_file = "ai/architecture.json"
    store.save_task(t)

    assert store.ai_cost_usd(t) == 6.0
    assert store.ai_cost_usd(t) >= config.MAX_TASK_AI_COST_USD

    Orchestrator(store).run_task(t)
    done = store.load_task("dev1")
    for name in ("ai.business_knowledge", "ai.conclusions", "ai.summary"):
        st = done.subtasks[name]
        assert st.status == SubtaskStatus.SKIPPED, name
        assert st.skip_reason.startswith(config.SKIP_TAG_BUDGET), name
        assert st.attempts == 0, f"{name} 在预算触顶后仍被调用"
    # 计划跳过不阻塞评分：仍有归一化总分与归档报告
    assert done.subtasks["scoring"].status == SubtaskStatus.COMPLETED
    assert done.subtasks["report.archive"].status == SubtaskStatus.COMPLETED


# ---------- 桩报告不归档 ----------

def test_stub_report_skips_reports_dir(repo, tmp_path, store):
    from analysis.reporters.archive import archive_handler

    task = _make_store_task(store, repo, ai_stub=True)
    ctx = _StubCtx(task, store, tmp_path)
    result = archive_handler(ctx)

    assert result["archived"] is False
    html = Path(result["html"])
    assert str(html).startswith(str(store.task_dir("dev1"))), "桩报告应落在任务目录内"
    assert not (config.REPORTS_DIR / "o" / "r" / "analysis" / html.name).exists(), \
        "桩报告不应写入 reports/ 归档目录"
    assert any("不归档" in m for m in ctx.logs)
