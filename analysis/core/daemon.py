"""执行器 daemon（对应 ANALYSIS-DESIGN.md §4）

- ensure_daemon：pid 文件 + 进程存活检测，未运行则 detached 拉起
- daemon_loop：FIFO 消费 queued 任务（全局串行）；空闲 TTL 自动退出
- 崩溃恢复：启动时将孤儿 running 任务标记 failed(interrupted)
- 与 Web 解耦（REQ §4.3）：daemon 独立于 Web 进程
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from analysis.core import config
from analysis.core.models import SubtaskStatus, TaskStatus, now_iso
from analysis.core.orchestrator import Orchestrator
from analysis.core.store import TaskStore


def _analyze_bin() -> Path:
    return config.ANALYSIS_ROOT / "bin" / "analyze"


def ensure_daemon(store: TaskStore, verbose: bool = False) -> tuple[bool, int | None]:
    """确保 daemon 在运行。返回 (是否本次拉起, pid)"""
    if store.is_daemon_alive():
        return False, store.read_pid()

    # 清理 stale pid 文件
    store.clear_pid()
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)

    log_f = open(config.DAEMON_LOG_FILE, "a", encoding="utf-8")
    log_f.write(f"\n===== daemon started {now_iso()} =====\n")
    log_f.flush()

    proc = subprocess.Popen(
        [sys.executable, str(_analyze_bin()), "_daemon"],
        stdin=subprocess.DEVNULL,
        stdout=log_f,
        stderr=log_f,
        start_new_session=True,          # detached：CLI 退出不影响
        cwd=str(config.PROJECT_ROOT),
    )
    log_f.close()                        # 子进程已继承 fd，父进程关闭自己的句柄

    # 等待 pid 文件就绪（最多 5s）
    for _ in range(50):
        if store.is_daemon_alive():
            if verbose:
                print(f"daemon 已拉起 (pid={proc.pid})")
            return True, proc.pid
        if proc.poll() is not None:
            raise RuntimeError(
                f"daemon 启动失败（exit={proc.returncode}），查看日志: {config.DAEMON_LOG_FILE}")
        time.sleep(0.1)
    raise RuntimeError(f"daemon 启动超时，查看日志: {config.DAEMON_LOG_FILE}")


def recover_interrupted_tasks(store: TaskStore) -> int:
    """中断恢复（REQ v6 / 决策 D11）：running 孤儿任务自动重新入队续跑。

    调用时机安全性：仅在确认 daemon 不存活时调用（daemon 启动时旧 daemon 必已死，
    由 pid 检测 + flock 保证），因此 running 状态必为中断残留。
    被中断的子任务重置为 queued（attempts 归零——中断非业务失败）；
    已完成子任务保留（幂等重入跳过）；cancel_requested 意图保留。
    """
    recovered = 0
    for task in store.list_tasks():
        if task.status == TaskStatus.RUNNING:
            for st in task.subtasks.values():
                if st.status == SubtaskStatus.RUNNING:
                    st.status = SubtaskStatus.QUEUED
                    st.attempts = 0
                    st.error = None
                    st.started_at = None
            task.status = TaskStatus.QUEUED
            store.save_task(task)
            store.append_event(task.task_id, "task_queued",
                               message="中断恢复：检测到执行器中断（休眠/重启/进程终止），"
                                       "自动重新入队续跑（已完成子任务不重复执行）")
            recovered += 1
    return recovered


def recover_and_ensure(store: TaskStore, verbose: bool = False) -> int:
    """恢复入口（resume/ui 命令用）：daemon 未运行时恢复孤儿任务并按需拉起"""
    if store.is_daemon_alive():
        return 0
    n = recover_interrupted_tasks(store)
    if n or store.queued_tasks():
        ensure_daemon(store, verbose)
    return n


def daemon_loop(store: TaskStore) -> None:
    """daemon 主循环（在 _daemon 子命令中调用）"""
    if not store.acquire_daemon_lock():
        print(f"[{now_iso()}] 另一 daemon 已在运行（flock），本进程退出", flush=True)
        return
    store.write_pid(os.getpid())
    print(f"[{now_iso()}] daemon 启动 pid={os.getpid()}", flush=True)
    n = recover_interrupted_tasks(store)
    if n:
        print(f"[{now_iso()}] 中断恢复：{n} 个任务自动重新入队", flush=True)

    orchestrator = Orchestrator(store)
    idle_since: float | None = None
    last_heartbeat = 0.0
    current_task_id: str | None = None

    try:
        while True:
            now = time.monotonic()
            if now - last_heartbeat >= config.HEARTBEAT_INTERVAL:
                store.write_heartbeat(current_task_id)
                last_heartbeat = now
            queued = store.queued_tasks()
            if queued:
                idle_since = None
                task = queued[0]                      # FIFO（created_at 升序）
                current_task_id = task.task_id
                store.write_heartbeat(current_task_id)
                print(f"[{now_iso()}] 执行任务 {task.task_id}", flush=True)
                try:
                    orchestrator.run_task(task)
                except Exception:
                    import traceback
                    traceback.print_exc()
                    # run_task 内部已兜底；这里防御性标记
                    try:
                        t = store.load_task(task.task_id)
                        if t.status == TaskStatus.RUNNING:
                            t.status = TaskStatus.FAILED
                            t.error = "daemon 未捕获异常"
                            t.finished_at = now_iso()
                            store.save_task(t)
                            store.append_event(task.task_id, "task_failed", message=t.error)
                    except Exception:
                        pass
                finally:
                    current_task_id = None
            else:
                if idle_since is None:
                    idle_since = time.monotonic()
                elif time.monotonic() - idle_since > config.DAEMON_IDLE_TTL:
                    print(f"[{now_iso()}] 空闲超过 TTL，daemon 退出", flush=True)
                    break
            time.sleep(config.DAEMON_POLL_INTERVAL)
    finally:
        store.clear_pid()
        print(f"[{now_iso()}] daemon 退出", flush=True)
