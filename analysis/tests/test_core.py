"""M1 核心单元测试：store / registry / orchestrator"""

import json
import subprocess
import time
from pathlib import Path

import pytest

from analysis.core import config
from analysis.core.models import SubtaskState, SubtaskStatus, Task, TaskStatus
from analysis.core.orchestrator import Orchestrator, SubtaskTimeout
from analysis.core.registry import HANDLERS, SPECS_BY_NAME, SUBTASK_SPECS, topo_order
from analysis.core.store import TaskNotFoundError, TaskStore


# ---------- fixtures ----------

@pytest.fixture(autouse=True)
def clean_handlers():
    yield
    HANDLERS.clear()


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch):
    """测试中将重试退避置零（生产默认 det 5s / AI 30s）"""
    monkeypatch.setattr(config, "RETRY_DELAY_DET", 0)
    monkeypatch.setattr(config, "RETRY_DELAY_AI", 0)


@pytest.fixture
def store(tmp_path):
    return TaskStore(tasks_dir=tmp_path / "tasks", state_dir=tmp_path)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True, capture_output=True)
    return r


def make_task(store, repo, task_id="t1", mock=True, ref=None):
    task = Task(task_id=task_id, org="o", repo="r",
                repo_path=str(repo), ref=ref, commit_sha=None, mock=mock)
    task.subtasks = {s.name: SubtaskState(name=s.name, type=s.type) for s in SUBTASK_SPECS}
    return store.create_task(task)


# ---------- registry ----------

def test_topo_order_complete_and_acyclic():
    order = topo_order()
    assert len(order) == len(SUBTASK_SPECS) == 15
    pos = {n: i for i, n in enumerate(order)}
    for spec in SUBTASK_SPECS:
        for dep in spec.deps:
            assert pos[dep] < pos[spec.name], f"{dep} 应在 {spec.name} 之前"


def test_all_deps_declared():
    names = {s.name for s in SUBTASK_SPECS}
    for spec in SUBTASK_SPECS:
        for dep in spec.deps:
            assert dep in names


def test_archive_depends_on_all():
    spec = SPECS_BY_NAME["report.archive"]
    assert set(spec.deps) == {s.name for s in SUBTASK_SPECS if s.name != "report.archive"}
    assert spec.always_run


# ---------- store ----------

def test_task_roundtrip(store, repo):
    task = make_task(store, repo)
    loaded = store.load_task("t1")
    assert loaded.task_id == task.task_id
    assert loaded.status == TaskStatus.QUEUED
    assert len(loaded.subtasks) == 15
    assert loaded.subtasks["collect.overview"].status == SubtaskStatus.QUEUED


def test_load_missing_raises(store):
    with pytest.raises(TaskNotFoundError):
        store.load_task("nope")


def test_find_task_prefix(store, repo):
    make_task(store, repo, task_id="20261105_120000-abc")
    assert store.find_task("20261105_120000").task_id == "20261105_120000-abc"
    with pytest.raises(TaskNotFoundError):
        store.find_task("zzz")


def test_events_seq_monotonic_and_incremental(store, repo):
    make_task(store, repo)  # create_task 写入 task_queued 事件
    s1 = store.append_event("t1", "log", message="a")
    s2 = store.append_event("t1", "log", message="b")
    assert s2 == s1 + 1
    assert len(store.read_events("t1")) == 3          # queued + 2 log
    assert len(store.read_events("t1", since_seq=s1)) == 1
    assert store.read_events("t1", since_seq=s1)[0]["message"] == "b"


def test_save_task_atomic_valid_json(store, repo):
    task = make_task(store, repo)
    task.status = TaskStatus.RUNNING
    store.save_task(task)
    raw = json.loads(store.task_file("t1").read_text())
    assert raw["status"] == "running"
    assert not list(store.task_dir("t1").glob("*.tmp"))


def test_progress_recalc(store, repo):
    task = make_task(store, repo)
    task.subtasks["collect.overview"].status = SubtaskStatus.COMPLETED
    task.subtasks["collect.structure"].status = SubtaskStatus.FAILED
    store.save_task(task)
    loaded = store.load_task("t1")
    assert loaded.progress == {"total": 15, "completed": 1, "failed": 1, "skipped": 0}


# ---------- orchestrator ----------

def test_mock_full_run_completes(store, repo):
    make_task(store, repo, mock=True)
    task = Orchestrator(store).run_task(store.load_task("t1"))
    assert task.status == TaskStatus.COMPLETED
    assert task.progress["completed"] == 15
    assert task.duration_seconds is not None
    # mock 产物落盘
    mock_out = store.task_dir("t1") / "collected" / "overview.json"
    assert json.loads(mock_out.read_text())["_mock"] is True
    # 事件流包含 task_started / task_completed
    types = {e["type"] for e in store.read_events("t1")}
    assert {"task_started", "task_completed"} <= types


def test_not_implemented_fails_subtask(store, repo):
    make_task(store, repo, mock=False)
    task = Orchestrator(store).run_task(store.load_task("t1"))
    st = task.subtasks["collect.overview"]
    assert st.status == SubtaskStatus.FAILED
    assert "未实现" in st.error
    # handler 缺失属实现问题，重试无意义：直接 failed，不消耗重试次数
    assert st.attempts == 1


def _inject_success_all(except_name=None):
    """为全部子任务注入成功 handler（测试用，代替 task.mock）"""
    for spec in SUBTASK_SPECS:
        if spec.name == except_name:
            continue

        def ok(ctx, _n=spec.name):
            return {"_test_mock": True, "subtask": _n}

        HANDLERS[spec.name] = ok


def test_failure_propagation_and_always_run(store, repo):
    calls = {"n": 0}

    def failing(ctx):
        calls["n"] += 1
        raise ValueError("boom")

    _inject_success_all(except_name="collect.structure")
    HANDLERS["collect.structure"] = failing
    make_task(store, repo, mock=False)
    task = Orchestrator(store).run_task(store.load_task("t1"))

    assert calls["n"] == config.SUBTASK_MAX_ATTEMPTS      # 自动重试一次
    assert task.subtasks["collect.structure"].status == SubtaskStatus.FAILED
    # 直接下游 skipped
    assert task.subtasks["collect.dependencies"].status == SubtaskStatus.SKIPPED
    assert "collect.structure" in task.subtasks["collect.dependencies"].skip_reason
    # 传递下游 skipped（ai.architecture 依赖 structure）
    assert task.subtasks["ai.architecture"].status == SubtaskStatus.SKIPPED
    # 无依赖子任务正常
    assert task.subtasks["collect.overview"].status == SubtaskStatus.COMPLETED
    # always_run 仍执行（注入的成功 handler）
    assert task.subtasks["report.archive"].status == SubtaskStatus.COMPLETED
    assert task.subtasks["ai.summary"].status == SubtaskStatus.COMPLETED
    # 任务整体 completed（archive 成功）但标注部分失败
    assert task.status == TaskStatus.COMPLETED
    assert "部分子任务未成功" in task.error


def test_retry_reentry_skips_completed(store, repo):
    def failing(ctx):
        raise ValueError("boom")

    _inject_success_all(except_name="collect.structure")
    HANDLERS["collect.structure"] = failing
    make_task(store, repo, mock=False)
    Orchestrator(store).run_task(store.load_task("t1"))

    # 模拟 CLI retry：修复 handler，重置 failed/skipped
    def now_ok(ctx):
        return {"_test_mock": True, "subtask": "collect.structure"}

    HANDLERS["collect.structure"] = now_ok
    task = store.load_task("t1")
    for st in task.subtasks.values():
        if st.status in (SubtaskStatus.FAILED, SubtaskStatus.SKIPPED):
            st.status = SubtaskStatus.QUEUED
            st.attempts = 0
            st.error = None
            st.skip_reason = None
    task.status = TaskStatus.QUEUED
    task.error = None
    store.save_task(task)

    before = store.load_task("t1").subtasks["collect.overview"].attempts
    task = Orchestrator(store).run_task(store.load_task("t1"))
    after = task.subtasks["collect.overview"].attempts

    assert task.status == TaskStatus.COMPLETED
    assert task.progress["completed"] == 15
    assert after == before  # 已完成的子任务未重复执行


def test_cancel_before_run(store, repo):
    task = make_task(store, repo, mock=True)
    task.cancel_requested = True
    store.save_task(task)
    task = Orchestrator(store).run_task(store.load_task("t1"))
    assert task.status == TaskStatus.CANCELED
    assert all(st.status == SubtaskStatus.QUEUED for st in task.subtasks.values())


def test_execute_with_timeout():
    def slow(ctx):
        time.sleep(3)
        return {}

    with pytest.raises(SubtaskTimeout):
        Orchestrator._execute_with_timeout(slow, None, timeout=1)


def test_execute_no_timeout_needed():
    def fast(ctx):
        return {"ok": True}

    assert Orchestrator._execute_with_timeout(fast, None, timeout=5) == {"ok": True}


# ---------- 中断恢复（REQ v6 / T551-T553） ----------

def test_recover_interrupted_tasks(store, repo):
    from analysis.core.daemon import recover_interrupted_tasks

    make_task(store, repo, mock=True)
    task = store.load_task("t1")
    # 模拟中断现场：任务 running，一个子任务已完成、一个卡在 running
    task.status = TaskStatus.RUNNING
    task.subtasks["collect.overview"].status = SubtaskStatus.COMPLETED
    st = task.subtasks["collect.structure"]
    st.status = SubtaskStatus.RUNNING
    st.attempts = 1
    st.started_at = "2026-11-05T00:00:00"
    store.save_task(task)

    n = recover_interrupted_tasks(store)
    assert n == 1
    t = store.load_task("t1")
    assert t.status == TaskStatus.QUEUED                    # 自动重新入队（决策 D11）
    assert t.subtasks["collect.structure"].status == SubtaskStatus.QUEUED
    assert t.subtasks["collect.structure"].attempts == 0    # 中断非业务失败，计数归零
    assert t.subtasks["collect.overview"].status == SubtaskStatus.COMPLETED
    # 事件流记录恢复
    assert any(e["type"] == "task_queued" and "中断恢复" in e.get("message", "")
               for e in store.read_events("t1"))

    # 续跑：幂等重入，最终完成
    t2 = Orchestrator(store).run_task(t)
    assert t2.status == TaskStatus.COMPLETED
    assert t2.progress["completed"] == 15


def test_recover_preserves_cancel_intent(store, repo):
    from analysis.core.daemon import recover_interrupted_tasks

    make_task(store, repo, mock=True)
    task = store.load_task("t1")
    task.status = TaskStatus.RUNNING
    task.cancel_requested = True    # 中断前用户已请求取消
    task.subtasks["collect.overview"].status = SubtaskStatus.RUNNING
    store.save_task(task)

    recover_interrupted_tasks(store)
    t = store.load_task("t1")
    assert t.status == TaskStatus.QUEUED
    assert t.cancel_requested is True   # 取消意图保留 → 续跑时立即生效

    t2 = Orchestrator(store).run_task(t)
    assert t2.status == TaskStatus.CANCELED


def test_no_orphan_no_recovery(store, repo):
    from analysis.core.daemon import recover_interrupted_tasks

    make_task(store, repo, mock=True)
    assert recover_interrupted_tasks(store) == 0    # queued 任务不受影响
    assert store.load_task("t1").status == TaskStatus.QUEUED


def test_daemon_lock_exclusive(store):
    assert store.acquire_daemon_lock() is True
    store2 = TaskStore(tasks_dir=store.tasks_dir, state_dir=store.state_dir)
    assert store2.acquire_daemon_lock() is False    # flock 独占：第二个 daemon 拒绝启动


def test_heartbeat_roundtrip(store):
    store.write_heartbeat("task-x")
    hb = store.read_heartbeat()
    assert hb and hb["current_task"] == "task-x"
    assert hb["ts"] > 0
