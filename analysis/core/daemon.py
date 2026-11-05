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


def recover_orphan_tasks(store: TaskStore) -> None:
    """daemon 启动时：running 状态的任务必为孤儿（旧 daemon 已死）"""
    for task in store.list_tasks():
        if task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.FAILED
            task.finished_at = now_iso()
            task.error = "daemon 中断（进程异常退出），可执行 retry 恢复"
            for st in task.subtasks.values():
                if st.status == SubtaskStatus.RUNNING:
                    st.status = SubtaskStatus.FAILED
                    st.error = "daemon 中断"
            store.save_task(task)
            store.append_event(task.task_id, "task_failed",
                               message="daemon 中断，任务标记为失败（可 retry）")


def daemon_loop(store: TaskStore) -> None:
    """daemon 主循环（在 _daemon 子命令中调用）"""
    store.write_pid(os.getpid())
    print(f"[{now_iso()}] daemon 启动 pid={os.getpid()}", flush=True)
    recover_orphan_tasks(store)

    orchestrator = Orchestrator(store)
    idle_since: float | None = None

    try:
        while True:
            queued = store.queued_tasks()
            if queued:
                idle_since = None
                task = queued[0]                      # FIFO（created_at 升序）
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
