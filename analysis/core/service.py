"""共享服务层：CLI 与 Web API 复用的任务发起逻辑（设计决策 D8）"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from analysis.core import config
from analysis.core import daemon as daemon_mod
from analysis.core.models import SubtaskState, Task
from analysis.core.registry import SUBTASK_SPECS
from analysis.core.store import TaskStore


class ServiceError(Exception):
    pass


def resolve_target(target: str) -> tuple[str, str]:
    """解析 <org>/<repo> 或 <repo>（repos/ 下唯一匹配时推断 org）"""
    parts = target.strip("/").split("/")
    if len(parts) == 2 and all(parts):
        return parts[0], parts[1]
    if len(parts) == 1 and parts[0]:
        candidates = sorted(c for c in config.REPOS_DIR.glob(f"*/{parts[0]}") if c.is_dir())
        if len(candidates) == 1:
            return candidates[0].parent.name, parts[0]
        if not candidates:
            raise ServiceError(f"未在 repos/ 下找到仓库 '{parts[0]}'，请用 <org>/<repo> 格式")
        orgs = [c.parent.name for c in candidates]
        raise ServiceError(f"仓库名 '{parts[0]}' 存在于多个组织 {orgs}，请用 <org>/<repo>")
    raise ServiceError(f"无法解析目标: {target}（格式 <org>/<repo>）")


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise ServiceError(f"git {' '.join(args)} 失败: {proc.stderr.strip()}")
    return proc.stdout.strip()


def check_fork(org: str, repo: str) -> tuple[bool | None, str | None]:
    """fork 预检（M7 用户决策：fork 仓库完全不分析）。

    返回 (is_fork, note)；gh api 不可达时 (None, 原因)——放行并在任务事件中标注。
    """
    try:
        proc = subprocess.run(
            ["gh", "api", f"repos/{org}/{repo}", "--jq", ".fork"],
            capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            return proc.stdout.strip() == "true", None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None, "gh api 不可达：fork 预检跳过（如为 fork 仓库，报告中请人工甄别）"


def create_analysis_task(target: str, ref: str | None = None,
                         mock: bool = False, store: TaskStore | None = None,
                         start_daemon: bool = True) -> Task:
    """创建分析任务并确保 daemon 运行；立即返回（REQ 第 7 章即时响应）"""
    store = store or TaskStore()
    org, repo = resolve_target(target)
    repo_path = config.REPOS_DIR / org / repo
    if not repo_path.exists():
        raise ServiceError(f"仓库未克隆: {repo_path}（先执行 fish src/main.fish clone {org}）")

    # fork 预检（用户决策 2026-11-05：fork 仓库完全不分析）
    fork_note = None
    if config.FORK_POLICY_REJECT and not mock:
        is_fork, fork_note = check_fork(org, repo)
        if is_fork:
            raise ServiceError(
                f"fork 仓库按策略不分析（需求方决策 2026-11-05）: {org}/{repo}；"
                f"如需分析请调整 config.FORK_POLICY_REJECT")

    if ref:
        _git(repo_path, "rev-parse", "--verify", f"{ref}^{{commit}}")  # 校验 ref 有效
    commit_sha = _git(repo_path, "rev-parse", ref or "HEAD")

    task_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}-{repo}"
    if store.task_dir(task_id).exists():  # 同秒冲突防御
        task_id += f"-{datetime.now().microsecond // 1000:03d}"

    task = Task(task_id=task_id, org=org, repo=repo,
                repo_path=f"repos/{org}/{repo}", ref=ref,
                commit_sha=commit_sha, mock=mock)
    task.subtasks = {s.name: SubtaskState(name=s.name, type=s.type) for s in SUBTASK_SPECS}
    store.create_task(task)
    if fork_note:
        store.append_event(task.task_id, "log", message=fork_note)

    if start_daemon:
        daemon_mod.ensure_daemon(store)
    return task


def set_cancel(store: TaskStore, task_id: str) -> Task:
    """取消任务。RUNNING 任务写独立 cancel.flag（不写 task.json，避免被
    orchestrator 的状态保存竞态覆盖）；flag 在子任务边界与重试退避中生效。"""
    from analysis.core.models import TaskStatus
    task = store.find_task(task_id)
    if task.is_terminal:
        raise ServiceError(f"任务已处于终态: {task.status.value}")
    if task.status == TaskStatus.QUEUED:
        task.status = TaskStatus.CANCELED
        task.error = "用户取消（未开始执行）"
        store.save_task(task)
        store.append_event(task.task_id, "task_canceled", message="排队中取消")
    else:
        store.request_cancel(task.task_id)
        store.append_event(task.task_id, "log",
                           message="已请求取消（当前子任务边界生效；AI 子任务执行中时"
                                   "可 kill headless claude 进程立即中断，取消意图不会丢失）")
    return task


def downstream_of(name: str) -> set[str]:
    """DAG 传递下游（含直接/间接依赖 name 的全部子任务）"""
    from analysis.core.registry import SUBTASK_SPECS
    children: dict[str, list[str]] = {s.name: [] for s in SUBTASK_SPECS}
    for s in SUBTASK_SPECS:
        for dep in s.deps:
            children[dep].append(s.name)
    seen, stack = set(), [name]
    while stack:
        n = stack.pop()
        for c in children.get(n, []):
            if c not in seen:
                seen.add(c)
                stack.append(c)
    return seen


def set_retry(store: TaskStore, task_id: str, subtask: str | None = None,
              cascade: bool = True) -> Task:
    """重试。指定 --subtask 时默认级联重置其全部下游（上游数据变化后下游结论必须重算）"""
    from analysis.core.models import SubtaskStatus, TaskStatus
    task = store.find_task(task_id)
    if task.status == TaskStatus.RUNNING:
        raise ServiceError("任务执行中，不能 retry（可先 cancel）")
    if subtask and subtask not in task.subtasks:
        raise ServiceError(f"无此子任务: {subtask}")

    if subtask:
        names = [subtask] + (sorted(downstream_of(subtask)) if cascade else [])
        allow_any_state = True      # 指定子任务：completed 也重置（数据可能已过期）
    else:
        names = list(task.subtasks.keys())
        allow_any_state = False     # 默认：仅重置 failed/skipped

    resettable = [SubtaskStatus.FAILED, SubtaskStatus.SKIPPED]
    if task.status in (TaskStatus.CANCELED, TaskStatus.FAILED):
        resettable.append(SubtaskStatus.RUNNING)   # 终态任务遗留的 running 孤儿一并重置

    reset = 0
    for name in names:
        st = task.subtasks[name]
        if allow_any_state or st.status in resettable:
            st.status = SubtaskStatus.QUEUED
            st.error = None
            st.skip_reason = None
            st.attempts = 0
            st.started_at = None
            st.finished_at = None
            st.duration_seconds = None
            reset += 1

    has_queued = any(st.status == SubtaskStatus.QUEUED for st in task.subtasks.values())
    if reset == 0 and not has_queued:
        raise ServiceError("没有可重试的子任务（全部已完成）")

    task.status = TaskStatus.QUEUED
    task.cancel_requested = False
    task.error = None
    task.finished_at = None
    store.clear_cancel(task.task_id)
    store.save_task(task)
    store.append_event(task.task_id, "task_queued", message=f"retry：重置 {reset} 个子任务")
    daemon_mod.ensure_daemon(store)
    return task


def build_preview(store: TaskStore, task_id: str) -> dict:
    """增量报告预览数据：completed 子任务产物摘要 + 未完成状态占位（REQ §4.3）"""
    import json
    from analysis.core.registry import SPECS_BY_NAME

    task = store.find_task(task_id)
    task_dir = store.task_dir(task.task_id)   # 用完整 id 定位目录（调用方可能传前缀）
    chapters = {}
    for spec in SPECS_BY_NAME.values():
        st = task.subtasks.get(spec.name)
        entry: dict = {
            "status": st.status.value if st else "unknown",
            "type": spec.type,
            "description": spec.description,
            "duration_seconds": st.duration_seconds if st else None,
            "error": (st.error if st else None) or (st.skip_reason if st else None),
            "data": None,
        }
        if st and st.output_file:
            path = task_dir / st.output_file
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    entry["data"] = _summarize_output(raw)
                except json.JSONDecodeError:
                    entry["data"] = {"_error": "产物解析失败"}
        chapters[spec.name] = entry
    return {"task": task.to_dict(), "chapters": chapters}


def _summarize_output(raw: dict, limit: int = 4000) -> dict:
    """产物摘要（控制 preview 响应体积）：截断大数组/长文本"""
    import json

    def shrink(obj, depth=0):
        if depth > 4:
            return "…"
        if isinstance(obj, dict):
            return {k: shrink(v, depth + 1) for k, v in list(obj.items())[:40]}
        if isinstance(obj, list):
            head = [shrink(v, depth + 1) for v in obj[:10]]
            if len(obj) > 10:
                head.append(f"…（共 {len(obj)} 项）")
            return head
        if isinstance(obj, str) and len(obj) > 400:
            return obj[:400] + "…"
        return obj

    text = json.dumps(shrink(raw), ensure_ascii=False)
    if len(text) > limit * 4:
        return {"_truncated": True, **{k: shrink(v) for k, v in list(raw.items())[:20]}}
    return shrink(raw)
