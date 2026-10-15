"""任务服务。P0-02/08，失败重试。"""
from sqlalchemy.orm import Session

from app.db.models import ParseTask


def create_task(db: Session, course_id: int, user_id: int) -> ParseTask:
    task = ParseTask(course_id=course_id, initiated_by=user_id, status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def retry_task(db: Session, failed_task_id: int, user_id: int) -> ParseTask:
    original = db.get(ParseTask, failed_task_id)
    if not original or original.status != "failed":
        from app.core.exceptions import AppError
        raise AppError("TASK_NOT_RETRYABLE", "仅失败任务可重试", 422)
    new_task = ParseTask(
        course_id=original.course_id,
        initiated_by=user_id,
        status="queued",
        retry_count=original.retry_count + 1,
        parent_task_id=original.id,
        video_cache_path=original.video_cache_path,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task


def get_latest_task_by_course(db: Session, course_id: int) -> ParseTask | None:
    """按课程查最新一条解析任务（用于详情页展示进度）。"""
    return (
        db.query(ParseTask)
        .filter(ParseTask.course_id == course_id)
        .order_by(ParseTask.id.desc())
        .first()
    )


def update_status(db: Session, task_id: int, status: str, progress: int | None = None, current_step: str | None = None) -> None:
    task = db.get(ParseTask, task_id)
    if not task:
        return
    task.status = status
    if progress is not None:
        task.progress = progress
    if current_step:
        task.current_step = current_step
    db.commit()


def mark_failed(db: Session, task_id: int, error_code: str, error_message: str) -> None:
    from datetime import datetime, timezone
    task = db.get(ParseTask, task_id)
    if not task:
        return
    task.status = "failed"
    task.error_code = error_code
    task.error_message = error_message
    task.finished_at = datetime.now(timezone.utc)
    db.commit()