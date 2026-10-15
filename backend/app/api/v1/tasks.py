"""解析任务状态/重试。P0-02/08。"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import ParseTask, User
from app.db.session import get_db
from app.schemas.task import TaskOut
from app.services import task_service
from app.workers.parse_worker import run as parse_worker_run

router = APIRouter()


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ParseTask:
    task = db.get(ParseTask, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


@router.post("/{task_id}/retry", response_model=TaskOut, status_code=201)
def retry_task(task_id: int, bg: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ParseTask:
    new_task = task_service.retry_task(db, task_id, user.id)
    bg.add_task(parse_worker_run, new_task.id)
    return new_task