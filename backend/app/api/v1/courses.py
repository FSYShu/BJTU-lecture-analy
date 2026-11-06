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


@router.get("/{course_key}", response_model=CourseOut)
def get_course(course_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Course:
    course = course_service.find_course_by_key(db, course_key)
    if not course:
        raise HTTPException(404, "课程不存在")
    accessible = course_service.get_accessible_course(db, user, course.id)
    if not accessible:
        raise HTTPException(404, "课程不存在或未授权")
    return course


@router.post("/import", response_model=CourseOut, status_code=201)
def import_course(body: CourseImportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Course:
    return course_service.import_course(db, body, user)


@router.post("/{course_key}/parse", response_model=TaskOut, status_code=201)
def start_parse(course_key: str, bg: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ParseTask:
    course = course_service.find_course_by_key(db, course_key)
    if not course:
        raise HTTPException(404, "课程不存在")
    task_service.ensure_parse_ready(course)
    task = task_service.create_task(db, course.id, user.id)
    import threading
    threading.Thread(target=parse_worker_run, args=(task.id,), daemon=True).start()
    return task