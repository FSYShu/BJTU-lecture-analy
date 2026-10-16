"""解析任务状态/重试。P0-02/08。"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Course, ParseTask, User
from app.db.session import get_db
from app.schemas.task import TaskOut
from app.services import task_service
from app.workers.parse_worker import run as parse_worker_run

router = APIRouter()


@router.get("/latest", response_model=TaskOut)
def get_latest_task(course_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ParseTask:
    task = task_service.get_latest_task_by_course(db, course_id)
    if not task:
        raise HTTPException(404, "该课程暂无解析任务")
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ParseTask:
    task = db.get(ParseTask, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


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