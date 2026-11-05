"""任务编排器：DAG 调度、状态机、超时/重试/取消（对应 ANALYSIS-DESIGN.md §3.2/§4）

- 全局串行：子任务按拓扑序逐个执行（REQ §4.1 已决策）
- 超时：SIGALRM（daemon 主线程）；超时/异常 → 自动重试一次（REQ 第 7 章）
- 失败传播：下游子任务 skipped；always_run 子任务（ai.summary/report.archive）
  即使上游失败仍执行，报告呈现失败状态
- 取消：每个子任务边界检查 task.cancel_requested（CLI 写入）
- 幂等重入：retry 后跳过已 completed 的子任务（决策 D10）
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from analysis.core import config
from analysis.core.models import SubtaskState, SubtaskStatus, Task, TaskStatus, now_iso
from analysis.core.registry import (
    SPECS_BY_NAME,
    SubtaskNotImplemented,
    SubtaskSpec,
    resolve_handler,
    topo_order,
)
from analysis.core.store import TaskStore


class SubtaskTimeout(Exception):
    pass


class TaskCanceled(Exception):
    pass


@dataclass
class AnalysisContext:
    """传给 handler 的执行上下文"""
    task: Task
    store: TaskStore
    org: str
    repo: str
    repo_path: Path            # 绝对路径（worktree 或原始克隆）
    commit_sha: str
    subtask: str               # 当前子任务名
    mock: bool = False

    def log(self, message: str) -> None:
        """写执行日志事件（Web 执行节奏可见）"""
        self.store.append_event(self.task.task_id, "log",
                                subtask=self.subtask, message=message)

    def read_dependency_output(self, subtask_name: str) -> Optional[dict]:
        """读取前序子任务产物（AI 子任务注入采集数据用）"""
        spec = SPECS_BY_NAME.get(subtask_name)
        if not spec or not spec.output_file:
            return None
        path = self.store.task_dir(self.task.task_id) / spec.output_file
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None


class Orchestrator:
    def __init__(self, store: TaskStore):
        self.store = store

    # ---------- 主流程 ----------
    def run_task(self, task: Task) -> Task:
        task = self.store.load_task(task.task_id)  # 取最新状态
        task.status = TaskStatus.RUNNING
        task.started_at = task.started_at or now_iso()  # retry 时保留最早开始时间（总耗时累计）
        task.daemon_pid = os.getpid()
        self.store.save_task(task)
        self.store.append_event(task.task_id, "task_started",
                                message=f"开始分析 {task.org}/{task.repo}"
                                        + (f"@{task.ref}" if task.ref else ""))

        worktree_created = False
        try:
            repo_abs = self._prepare_workspace(task)
            worktree_created = task.worktree_path is not None

            for name in topo_order():
                task = self.store.load_task(task.task_id)  # 刷新 cancel_requested 等
                if task.cancel_requested:
                    raise TaskCanceled()

                spec = SPECS_BY_NAME[name]
                st = task.subtasks[name]
                if st.status == SubtaskStatus.COMPLETED:
                    continue  # 幂等重入：跳过已完成

                # 依赖检查
                blocked_by = self._failed_deps(task, spec)
                if blocked_by and not spec.always_run:
                    st.status = SubtaskStatus.SKIPPED
                    st.skip_reason = f"上游子任务未完成: {', '.join(blocked_by)}"
                    self.store.save_task(task)
                    self.store.append_event(task.task_id, "subtask_skipped",
                                            subtask=name, message=st.skip_reason)
                    continue

                ctx = AnalysisContext(
                    task=task, store=self.store, org=task.org, repo=task.repo,
                    repo_path=repo_abs, commit_sha=task.commit_sha or "HEAD",
                    subtask=name, mock=task.mock,
                )
                self._run_subtask(task, spec, ctx)

            task = self.store.load_task(task.task_id)
            self._finalize(task)
        except TaskCanceled:
            task = self.store.load_task(task.task_id)
            task.status = TaskStatus.CANCELED
            task.finished_at = now_iso()
            task.error = "用户取消"
            self.store.save_task(task)
            self.store.append_event(task.task_id, "task_canceled", message="任务已取消")
        except Exception as e:  # 任务级异常（工作区准备失败等）
            task = self.store.load_task(task.task_id)
            task.status = TaskStatus.FAILED
            task.finished_at = now_iso()
            task.error = f"{type(e).__name__}: {e}"
            self.store.save_task(task)
            self.store.append_event(task.task_id, "task_failed", message=task.error)
        finally:
            if worktree_created:
                self._cleanup_workspace(task)
        return self.store.load_task(task.task_id)

    # ---------- 子任务执行 ----------
    def _run_subtask(self, task: Task, spec: SubtaskSpec, ctx: AnalysisContext) -> None:
        st = task.subtasks[spec.name]
        handler: Optional[Callable] = None
        try:
            handler = resolve_handler(spec.name, mock=ctx.mock)
        except SubtaskNotImplemented as e:
            st.status = SubtaskStatus.FAILED
            st.error = str(e)
            st.attempts = 1
            self.store.save_task(task)
            self.store.append_event(task.task_id, "subtask_failed",
                                    subtask=spec.name, message=st.error)
            return

        while st.attempts < config.SUBTASK_MAX_ATTEMPTS:
            st.attempts += 1
            st.status = SubtaskStatus.RUNNING
            st.started_at = now_iso()
            st.error = None
            self.store.save_task(task)
            self.store.append_event(task.task_id, "subtask_started", subtask=spec.name,
                                    message=f"第 {st.attempts} 次执行"
                                            + (f"（重试）" if st.attempts > 1 else ""))
            t0 = time.monotonic()
            try:
                result = self._execute_with_timeout(handler, ctx, spec.timeout)
                st.duration_seconds = round(time.monotonic() - t0, 2)
                st.status = SubtaskStatus.COMPLETED
                st.finished_at = now_iso()
                if spec.output_file and result is not None:
                    out = self.store.output_path(task.task_id, spec.output_file)
                    out.write_text(
                        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                    st.output_file = spec.output_file
                self.store.save_task(task)
                self.store.append_event(task.task_id, "subtask_completed",
                                        subtask=spec.name,
                                        duration_seconds=st.duration_seconds)
                return
            except Exception as e:
                st.duration_seconds = round(time.monotonic() - t0, 2)
                st.error = f"{type(e).__name__}: {e}"
                if st.attempts < config.SUBTASK_MAX_ATTEMPTS:
                    delay = (config.RETRY_DELAY_AI if spec.type == "ai"
                             else config.RETRY_DELAY_DET)
                    self.store.save_task(task)
                    self.store.append_event(
                        task.task_id, "subtask_retry", subtask=spec.name,
                        message=f"{st.error}；{delay}s 退避后重试（容忍网络瞬断）")
                    if self._interruptible_sleep(task.task_id, delay):
                        raise TaskCanceled()
                else:
                    st.status = SubtaskStatus.FAILED
                    st.finished_at = now_iso()
                    self.store.save_task(task)
                    self.store.append_event(task.task_id, "subtask_failed",
                                            subtask=spec.name, message=st.error)

    def _interruptible_sleep(self, task_id: str, seconds: float) -> bool:
        """退避等待（每秒检查取消请求）；返回 True 表示收到取消"""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
            try:
                if self.store.load_task(task_id).cancel_requested:
                    return True
            except Exception:
                pass
        return False

    @staticmethod
    def _execute_with_timeout(handler: Callable, ctx: AnalysisContext, timeout: int) -> Any:
        """SIGALRM 超时（daemon 主线程）；非主线程环境降级为无超时"""
        def _on_alarm(signum, frame):
            raise SubtaskTimeout(f"执行超时（>{timeout}s）")

        use_alarm = False
        try:
            signal.getsignal(signal.SIGALRM)
            use_alarm = True
        except (AttributeError, ValueError):
            use_alarm = False

        if not use_alarm:
            return handler(ctx)

        old_handler = signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(timeout)
        try:
            return handler(ctx)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

    # ---------- 依赖 / 收尾 ----------
    @staticmethod
    def _failed_deps(task: Task, spec: SubtaskSpec) -> list[str]:
        bad = []
        for dep in spec.deps:
            dep_st = task.subtasks.get(dep)
            if dep_st is None or dep_st.status in (SubtaskStatus.FAILED, SubtaskStatus.SKIPPED):
                bad.append(dep)
        return bad

    def _finalize(self, task: Task) -> None:
        """任务终态：report.archive 成功 → completed；否则 failed"""
        archive = task.subtasks.get("report.archive")
        n_failed = sum(1 for s in task.subtasks.values() if s.status == SubtaskStatus.FAILED)
        n_skipped = sum(1 for s in task.subtasks.values() if s.status == SubtaskStatus.SKIPPED)

        if archive and archive.status == SubtaskStatus.COMPLETED:
            task.status = TaskStatus.COMPLETED
            if n_failed or n_skipped:
                task.error = f"部分子任务未成功（failed={n_failed}, skipped={n_skipped}），详见报告"
        else:
            task.status = TaskStatus.FAILED
            task.error = task.error or f"归档子任务未成功（failed={n_failed}, skipped={n_skipped}）"

        task.finished_at = now_iso()
        if task.started_at:
            t0 = datetime.fromisoformat(task.started_at)
            task.duration_seconds = round((datetime.now() - t0).total_seconds(), 1)
        self.store.save_task(task)
        self.store.append_event(
            task.task_id,
            "task_completed" if task.status == TaskStatus.COMPLETED else "task_failed",
            message=task.error or f"分析完成，耗时 {task.duration_seconds}s")

    # ---------- 工作区（--ref 支持，REQ §2.1） ----------
    def _prepare_workspace(self, task: Task) -> Path:
        """默认分析本地克隆当前状态；指定 ref 且非当前 HEAD 时创建临时 worktree"""
        repo_abs = (config.PROJECT_ROOT / task.repo_path).resolve()
        if not (repo_abs / ".git").exists():
            raise FileNotFoundError(f"仓库不存在或未克隆: {task.repo_path}")

        if not task.ref:
            return repo_abs

        head_sha = self._git(repo_abs, "rev-parse", "HEAD").strip()
        target_sha = (task.commit_sha or "").strip()
        if not target_sha or target_sha == head_sha:
            return repo_abs  # ref 即当前 HEAD（或未解析），无需 worktree

        wt_path = config.WORKTREES_DIR / task.task_id
        wt_path.parent.mkdir(parents=True, exist_ok=True)
        if wt_path.exists():
            self._git(repo_abs, "worktree", "remove", "--force", str(wt_path), check=False)
        self._git(repo_abs, "worktree", "add", "--detach", str(wt_path),
                  target_sha or task.ref)
        task.worktree_path = str(wt_path)
        self.store.save_task(task)
        self.store.append_event(task.task_id, "log",
                                message=f"已创建临时 worktree: {wt_path}（ref={task.ref}）")
        return wt_path

    def _cleanup_workspace(self, task: Task) -> None:
        if not task.worktree_path:
            return
        repo_abs = (config.PROJECT_ROOT / task.repo_path).resolve()
        self._git(repo_abs, "worktree", "remove", "--force", task.worktree_path, check=False)
        self._git(repo_abs, "worktree", "prune", check=False)
        task.worktree_path = None
        self.store.save_task(task)

    @staticmethod
    def _git(repo: Path, *args: str, check: bool = True) -> str:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=120)
        if check and proc.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} 失败: {proc.stderr.strip()}")
        return proc.stdout
