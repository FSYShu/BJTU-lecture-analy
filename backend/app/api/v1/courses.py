"""课程回放入口。P0-01。"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Course, CourseAuthorization, ParseTask, User
from app.db.session import get_db
from app.schemas.course import CourseImportIn, CourseOut
from app.schemas.task import TaskOut
from app.services import course_service, task_service
from app.workers.parse_worker import run as parse_worker_run

router = APIRouter()


@router.get("", response_model=list[CourseOut])
def list_courses(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Course]:
    return course_service.list_accessible_courses(db, user)


@router.get("/{course_id}", response_model=CourseOut)
def get_course(course_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Course:
    course = course_service.get_accessible_course(db, user, course_id)
    if not course:
        raise HTTPException(404, "课程不存在或未授权")
    return course


@router.post("/import", response_model=CourseOut, status_code=201)
def import_course(body: CourseImportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Course:
    return course_service.import_course(db, body, user)


@router.post("/{course_id}/parse", response_model=TaskOut, status_code=201)
def start_parse(course_id: int, bg: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ParseTask:
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(404, "课程不存在")
    task_service.ensure_parse_ready(course)
    task = task_service.create_task(db, course_id, user.id)
    import threading
    threading.Thread(target=parse_worker_run, args=(task.id,), daemon=True).start()
    return task