"""课程授权服务。P0-09，FR-13。"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import CourseAuthorization


def grant(db: Session, course_id: int, user_id: int, granted_by: int, valid_until: datetime | None) -> CourseAuthorization:
    now = datetime.now(timezone.utc)
    auth = CourseAuthorization(
        course_id=course_id,
        user_id=user_id,
        granted_by=granted_by,
        valid_from=now,
        valid_until=valid_until,
    )
    db.add(auth)
    db.commit()
    db.refresh(auth)
    return auth


def revoke(db: Session, auth_id: int) -> None:
    auth = db.get(CourseAuthorization, auth_id)
    if not auth:
        from app.core.exceptions import AppError
        raise AppError("AUTH_NOT_FOUND", "授权记录不存在", 404)
    auth.is_revoked = True
    auth.revoked_at = datetime.now(timezone.utc)
    db.commit()