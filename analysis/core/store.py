"""状态存储：task.json 原子读写 + events.jsonl 追加（对应 ANALYSIS-DESIGN.md §3.3/§3.4）

设计要点（决策 D1）：
- 纯文件存储（JSON/JSONL），无数据库；task.json 为状态唯一事实源
- 原子写：tmp + os.replace，避免 Web/CLI 读到半截 JSON
- events.jsonl 追加写，seq 单调递增（按行号）
"""

from __future__ import annotations

import json
import os
import signal
import tempfile
from pathlib import Path
from typing import Any, Iterator, Optional

from analysis.core import config
from analysis.core.models import Task, TaskStatus, now_iso


class TaskNotFoundError(Exception):
    pass


class TaskStore:
    def __init__(self, tasks_dir: Optional[Path] = None, state_dir: Optional[Path] = None):
        self.state_dir = Path(state_dir) if state_dir else config.STATE_DIR
        self.tasks_dir = Path(tasks_dir) if tasks_dir else config.TASKS_DIR
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 路径 ----------
    def task_dir(self, task_id: str) -> Path:
        return self.tasks_dir / task_id

    def task_file(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "task.json"

    def events_file(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "events.jsonl"

    def output_path(self, task_id: str, rel_path: str) -> Path:
        """子任务产物绝对路径（rel_path 如 collected/overview.json）"""
        p = self.task_dir(task_id) / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    # ---------- 任务 CRUD ----------
    def create_task(self, task: Task) -> Task:
        tdir = self.task_dir(task.task_id)
        if tdir.exists():
            raise FileExistsError(f"任务目录已存在: {tdir}")
        (tdir / "collected").mkdir(parents=True)
        (tdir / "ai").mkdir(parents=True)
        self.save_task(task)
        self.append_event(task.task_id, "task_queued",
                          message=f"任务已创建: {task.org}/{task.repo}"
                                  + (f"@{task.ref}" if task.ref else ""))
        return task

    def save_task(self, task: Task) -> None:
        """原子写 task.json"""
        task.recalc_progress()
        path = self.task_file(task.task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(task.to_dict(), f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def load_task(self, task_id: str) -> Task:
        path = self.task_file(task_id)
        if not path.exists():
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        with open(path, encoding="utf-8") as f:
            return Task.from_dict(json.load(f))

    def list_tasks(self) -> list[Task]:
        """全部任务，按 created_at 升序"""
        tasks = []
        for d in sorted(self.tasks_dir.iterdir()):
            tf = d / "task.json"
            if d.is_dir() and tf.exists():
                try:
                    tasks.append(Task.from_dict(json.loads(tf.read_text(encoding="utf-8"))))
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue  # 损坏的任务目录跳过（不阻塞列表）
        tasks.sort(key=lambda t: t.created_at)
        return tasks

    def queued_tasks(self) -> list[Task]:
        return [t for t in self.list_tasks() if t.status == TaskStatus.QUEUED]

    def latest_task(self) -> Optional[Task]:
        tasks = self.list_tasks()
        return tasks[-1] if tasks else None

    def find_task(self, task_id_prefix: str) -> Task:
        """支持前缀匹配 task_id"""
        try:
            return self.load_task(task_id_prefix)
        except TaskNotFoundError:
            matches = [t for t in self.list_tasks() if t.task_id.startswith(task_id_prefix)]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise TaskNotFoundError(
                    f"前缀 '{task_id_prefix}' 匹配到多个任务: {[t.task_id for t in matches]}")
            raise

    # ---------- 事件流 ----------
    def append_event(self, task_id: str, event_type: str, **fields: Any) -> int:
        """追加事件，返回 seq。事件行结构见 DESIGN §3.4"""
        path = self.events_file(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        seq = self._event_count(path) + 1
        event = {"seq": seq, "ts": now_iso(), "type": event_type, **fields}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return seq

    @staticmethod
    def _event_count(path: Path) -> int:
        if not path.exists():
            return 0
        with open(path, "rb") as f:
            return sum(1 for _ in f)

    def read_events(self, task_id: str, since_seq: int = 0) -> list[dict[str, Any]]:
        path = self.events_file(task_id)
        if not path.exists():
            return []
        events = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 半行（写入中）跳过，下次轮询再取
                if ev.get("seq", 0) > since_seq:
                    events.append(ev)
        return events

    def tail_events(self, task_id: str, poll_interval: float = 0.5) -> Iterator[dict[str, Any]]:
        """生成器：持续 tail 事件流（Web SSE 用）。任务终态后推完剩余事件即结束。"""
        import time
        last_seq = 0
        while True:
            events = self.read_events(task_id, since_seq=last_seq)
            for ev in events:
                last_seq = ev.get("seq", last_seq)
                yield ev
            try:
                task = self.load_task(task_id)
                if task.is_terminal and not events:
                    return
            except TaskNotFoundError:
                return
            time.sleep(poll_interval)

    # ---------- 取消标志（独立文件，修复 task.json 竞态覆盖） ----------
    def cancel_flag_path(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "cancel.flag"

    def request_cancel(self, task_id: str) -> None:
        self.task_dir(task_id).mkdir(parents=True, exist_ok=True)
        self.cancel_flag_path(task_id).write_text(now_iso())

    def is_cancel_requested(self, task_id: str) -> bool:
        return self.cancel_flag_path(task_id).exists()

    def clear_cancel(self, task_id: str) -> None:
        self.cancel_flag_path(task_id).unlink(missing_ok=True)

    # ---------- daemon 心跳与锁（中断恢复，REQ v6） ----------
    @property
    def heartbeat_file(self) -> Path:
        return self.state_dir / "daemon.heartbeat"

    @property
    def lock_file(self) -> Path:
        return self.state_dir / "daemon.lock"

    def write_heartbeat(self, current_task: Optional[str] = None) -> None:
        import time
        self.heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"pid": os.getpid(), "ts": time.time(), "current_task": current_task}
        fd, tmp = tempfile.mkstemp(dir=str(self.heartbeat_file.parent), suffix=".hb.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, self.heartbeat_file)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def read_heartbeat(self) -> Optional[dict]:
        try:
            return json.loads(self.heartbeat_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def acquire_daemon_lock(self) -> bool:
        """flock 独占锁防双 daemon（决策 D2/DESIGN §4）；锁随进程退出自动释放"""
        import fcntl
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.lock_file, "w")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self._lock_fh = fh          # 持有句柄至进程退出
        fh.write(str(os.getpid()))
        fh.flush()
        return True

    # ---------- daemon pid ----------
    @property
    def pid_file(self) -> Path:
        return self.state_dir / "daemon.pid"

    def write_pid(self, pid: int) -> None:
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(pid))

    def read_pid(self) -> Optional[int]:
        try:
            return int(self.pid_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None

    def clear_pid(self) -> None:
        self.pid_file.unlink(missing_ok=True)

    def is_daemon_alive(self) -> bool:
        pid = self.read_pid()
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
