"""数据模型：Task / SubtaskState（对应 ANALYSIS-DESIGN.md §3.3 task.json）"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from analysis.core.config import SCHEMA_VERSION


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class SubtaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


TERMINAL_TASK_STATUSES = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELED}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class SubtaskState:
    name: str
    type: str                              # "det" | "ai"
    status: SubtaskStatus = SubtaskStatus.QUEUED
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    attempts: int = 0
    error: Optional[str] = None
    skip_reason: Optional[str] = None
    output_file: Optional[str] = None      # 相对任务目录，如 collected/overview.json

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SubtaskState":
        d = dict(d)
        d["status"] = SubtaskStatus(d["status"])
        return cls(**d)


@dataclass
class Task:
    task_id: str
    org: str
    repo: str
    repo_path: str                         # 相对项目根，如 repos/augmn/xxx
    ref: Optional[str] = None              # 用户指定的 branch/tag/commit；None=当前 HEAD
    commit_sha: Optional[str] = None       # 解析后的实际分析基线
    status: TaskStatus = TaskStatus.QUEUED
    cancel_requested: bool = False
    mock: bool = False                     # M1 联调用：handler 未实现时以 sleep 模拟
    schema_version: str = SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    daemon_pid: Optional[int] = None       # 执行本任务的 daemon（孤儿检测用）
    worktree_path: Optional[str] = None    # --ref 非当前 HEAD 时的临时 worktree
    progress: dict[str, int] = field(
        default_factory=lambda: {"total": 0, "completed": 0, "failed": 0, "skipped": 0}
    )
    subtasks: dict[str, SubtaskState] = field(default_factory=dict)
    report: dict[str, Optional[str]] = field(
        default_factory=lambda: {"html": None, "json": None}
    )
    error: Optional[str] = None

    # ---------- 序列化 ----------
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["subtasks"] = {k: v.to_dict() for k, v in self.subtasks.items()}
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Task":
        d = dict(d)
        d["status"] = TaskStatus(d["status"])
        d["subtasks"] = {
            k: SubtaskState.from_dict(v) if isinstance(v, dict) else v
            for k, v in d.get("subtasks", {}).items()
        }
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    # ---------- 便捷方法 ----------
    def recalc_progress(self) -> None:
        self.progress = {
            "total": len(self.subtasks),
            "completed": sum(1 for s in self.subtasks.values() if s.status == SubtaskStatus.COMPLETED),
            "failed": sum(1 for s in self.subtasks.values() if s.status == SubtaskStatus.FAILED),
            "skipped": sum(1 for s in self.subtasks.values() if s.status == SubtaskStatus.SKIPPED),
        }

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_TASK_STATUSES
