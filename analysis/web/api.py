"""REST + SSE API（ANALYSIS-DESIGN.md §9.1）"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from analysis.core import service
from analysis.core.store import TaskNotFoundError, TaskStore

router = APIRouter()
_store = TaskStore()


class CreateTaskBody(BaseModel):
    target: str                 # <org>/<repo> 或 <repo>
    ref: str | None = None
    mock: bool = False
    no_ai: bool = False         # M7：跳过全部 AI 子任务（零 AI 成本，与 CLI --no-ai 同义）
    ai_stub: bool = False       # M7：AI 子任务走 schema-valid 桩（$0，报告不归档，DESIGN D17）


class RetryBody(BaseModel):
    subtask: str | None = None


@router.get("/api/health")
def health():
    from analysis import __version__
    return {"ok": True, "version": __version__,
            "daemon_alive": _store.is_daemon_alive(),
            "daemon_pid": _store.read_pid()}


@router.get("/api/tasks")
def list_tasks():
    return {"tasks": [t.to_dict() for t in reversed(_store.list_tasks())]}


@router.post("/api/tasks")
def create_task(body: CreateTaskBody):
    try:
        task = service.create_analysis_task(body.target, body.ref, body.mock, store=_store,
                                            no_ai=body.no_ai, ai_stub=body.ai_stub)
    except service.ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"task_id": task.task_id}


@router.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    try:
        return _store.find_task(task_id).to_dict()
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/tasks/{task_id}/events")
def get_events(task_id: str, since_seq: int = 0):
    try:
        task = _store.find_task(task_id)   # 解析前缀 → 完整 task_id
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"events": _store.read_events(task.task_id, since_seq=since_seq)}


@router.get("/api/tasks/{task_id}/stream")
def stream_events(task_id: str):
    """SSE：实时执行节奏（tail events.jsonl；任务终态后自动结束）"""
    try:
        task = _store.find_task(task_id)
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    full_id = task.task_id

    def gen():
        for ev in _store.tail_events(full_id, poll_interval=0.5):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/api/tasks/{task_id}/preview")
def preview(task_id: str):
    try:
        task = _store.find_task(task_id)
        return service.build_preview(_store, task.task_id)
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/tasks/{task_id}/cancel")
def cancel(task_id: str):
    try:
        task = service.set_cancel(_store, task_id)
    except (TaskNotFoundError, service.ServiceError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "status": task.status.value}


@router.post("/api/tasks/{task_id}/retry")
def retry(task_id: str, body: RetryBody | None = None):
    try:
        task = service.set_retry(_store, task_id, body.subtask if body else None)
    except (TaskNotFoundError, service.ServiceError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "status": task.status.value}
