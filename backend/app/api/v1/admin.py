"""教师/管理员：授权管理与异常处理。P0-09/14，FR-13。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import Course, CourseAuthorization, ParseTask, User
from app.db.session import get_db
from app.services import authorization_service

router = APIRouter()


class GrantIn(BaseModel):
    course_id: int
    user_id: int
    valid_until: datetime | None = None


@router.get("/authorizations")
def list_authorizations(admin: User = Depends(require_role("teacher", "admin")), db: Session = Depends(get_db)) -> list[dict]:
    rows = (
        db.query(CourseAuthorization, Course.title, User.username)
        .join(Course, Course.id == CourseAuthorization.course_id)
        .join(User, User.id == CourseAuthorization.user_id)
        .order_by(CourseAuthorization.id.desc())
        .all()
    )
    return [
        {
            "id": a.id,
            "course_id": a.course_id,
            "user_id": a.user_id,
            "course_title": title,
            "student_name": username,
            "is_revoked": a.is_revoked,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a, title, username in rows
    ]


@router.post("/authorizations", status_code=201)
def grant(body: GrantIn, admin: User = Depends(require_role("teacher", "admin")), db: Session = Depends(get_db)) -> dict:
    auth = authorization_service.grant(db, body.course_id, body.user_id, admin.id, body.valid_until)
    return {"id": auth.id, "course_id": auth.course_id, "user_id": auth.user_id}


@router.post("/authorizations/{auth_id}/revoke")
def revoke(auth_id: int, admin: User = Depends(require_role("teacher", "admin")), db: Session = Depends(get_db)) -> dict:
    authorization_service.revoke(db, auth_id)
    return {"id": auth_id, "is_revoked": True}


@router.get("/tasks/failed", response_model=list[dict])
def list_failed_tasks(admin: User = Depends(require_role("teacher", "admin")), db: Session = Depends(get_db)) -> list[ParseTask]:
    tasks = db.query(ParseTask).filter(ParseTask.status == "failed").all()
    return [
        {"id": t.id, "course_id": t.course_id, "error_code": t.error_code, "error_message": t.error_message}
        for t in tasks
    ]