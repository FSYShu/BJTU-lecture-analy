"""解析任务状态/重试。P0-02/08。"""
import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Course, Lecture, ParseTask, User
from app.db.session import SessionLocal, get_db
from app.schemas.task import ActiveTaskOut, TaskOut
from app.pipeline import proc_registry
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


ACTIVE_TASK_STATUSES = (
    "queued",
    "downloading",
    "extracting_audio",
    "asr_running",
    "llm_running",
    "persisting",
)


@router.get("/active", response_model=list[ActiveTaskOut])
def list_active_tasks(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ActiveTaskOut]:
    """列出排队中/进行中的解析任务，供右上角进度弹窗展示“正在解析哪个、还有哪些在排队”。"""
    rows = (
        db.query(ParseTask, Course.title, Lecture.teach_time_str)
        .outerjoin(Course, Course.id == ParseTask.course_id)
        .outerjoin(Lecture, Lecture.id == ParseTask.lecture_id)
        .filter(ParseTask.status.in_(ACTIVE_TASK_STATUSES))
        .order_by(ParseTask.id.asc())
        .all()
    )
    return [
        ActiveTaskOut(
            id=task.id,
            course_id=task.course_id,
            lecture_id=task.lecture_id,
            status=task.status,
            progress=task.progress,
            current_step=task.current_step,
            error_code=task.error_code,
            error_message=task.error_message,
            retry_count=task.retry_count,
            course_title=course_title,
            teach_time_str=teach_time_str,
        )
        for task, course_title, teach_time_str in rows
    ]


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

@router.post("/{task_id}/cancel", response_model=TaskOut)
def cancel_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ParseTask:
    """用户取消解析：标记 failed+CANCELLED 并终止正在运行的 ffmpeg。

    即使任务已被标记为 failed（例如被启动清理误判），也可能仍有工作线程/ffmpeg
    在运行，所以不能直接返回，必须继续终止子进程并让流水线在检查点退出。
    """
    task = db.get(ParseTask, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status == "succeeded":
        return task
    if task.status != "failed":
        task_service.mark_failed(db, task_id, "CANCELLED", "用户取消")
    proc_registry.terminate(task_id)
    return db.get(ParseTask, task_id)