"""课程服务。P0-01。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course, CourseAuthorization, User
from app.schemas.course import CourseImportIn


def list_accessible_courses(db: Session, user: User) -> list[Course]:
    if user.role in ("teacher", "admin"):
        return list(db.query(Course).all())
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    stmt = (
        select(Course)
        .join(CourseAuthorization, CourseAuthorization.course_id == Course.id)
        .where(
            CourseAuthorization.user_id == user.id,
            CourseAuthorization.is_revoked == False,  # noqa: E712
            CourseAuthorization.valid_from <= now,
        )
    )
    return list(db.execute(stmt).scalars())


def import_course(db: Session, body: CourseImportIn, user: User) -> Course:
    course = Course(
        title=body.title,
        teacher_name=body.teacher_name,
        session_label=body.session_label,
        duration_sec=body.duration_sec,
        video_url=body.video_url,
        video_format=body.video_format,
        source="manual",
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def import_from_platform(db: Session, platform_course_id: str, meta: dict) -> Course:
    """平台课程导入：按 platform_course_id 唯一索引去重，已存在则更新，不存在则新建。

    meta 需包含 title / video_url（Course 必填字段）；teacher_name、session_label、
    duration_sec、video_format 可选，值为 None 时跳过不覆盖。
    """
    existing = (
        db.query(Course).filter(Course.platform_course_id == platform_course_id).first()
    )
    if existing:
        for k, v in meta.items():
            if v is not None:
                setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing

    course = Course(
        platform_course_id=platform_course_id,
        source="platform",
        **meta,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course