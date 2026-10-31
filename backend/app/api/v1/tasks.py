"""解析任务状态/重试。P0-02/08。"""
import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Course, ParseTask, User
from app.db.session import SessionLocal, get_db
from app.schemas.task import TaskOut
from app.services import task_service, task_stream
from app.workers.parse_worker import run as parse_worker_run

router = APIRouter()

#: SSE 必须禁用缓冲，否则 nginx / 代理会把事件攒到连接关闭才吐出来。
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get("/latest", response_model=TaskOut)
def get_latest_task(
    lecture_id: int | None = None,
    course_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ParseTask:
    if lecture_id:
        task = task_service.get_latest_task_by_lecture(db, lecture_id)
    else:
        task = task_service.get_latest_task_by_course(db, course_id or 0)
    if not task:
        raise HTTPException(404, "该课程暂无解析任务")
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ParseTask:
    task = db.get(ParseTask, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


@router.get("/{task_id}/stream")
async def stream_task(task_id: int, user: User = Depends(get_current_user)) -> StreamingResponse:
    """SSE 推送任务状态，替代前端固定间隔轮询（docs/11 优化 4）。

    先同步确认任务存在再开流：否则前端会拿到一个 "200 + 立即 error 帧"，
    没法区分「任务不存在」和「任务刚刚开始」。
    """
    snapshot = await asyncio.to_thread(task_stream.task_snapshot, SessionLocal, task_id)
    if snapshot is None:
        raise HTTPException(404, "任务不存在")
    return StreamingResponse(
        task_stream.task_events(task_id),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/{task_id}/retry", response_model=TaskOut, status_code=201)
def retry_task(task_id: int, bg: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ParseTask:
    original = db.get(ParseTask, task_id)
    if not original:
        raise HTTPException(404, "任务不存在")
    course = db.get(Course, original.course_id)
    if course is None:
        raise HTTPException(404, "任务对应的课程不存在")
    task_service.ensure_parse_ready(course)
    new_task = task_service.retry_task(db, task_id, user.id)
    import threading
    threading.Thread(target=parse_worker_run, args=(new_task.id,), daemon=True).start()
    return new_task