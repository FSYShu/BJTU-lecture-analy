"""课程服务。P0-01。"""
from sqlalchemy import or_, select
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


def get_accessible_course(db: Session, user: User, course_id: int) -> Course | None:
    """单条课程查询（带授权校验）。未授权返回 None。"""
    if user.role in ("teacher", "admin"):
        return db.get(Course, course_id)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    stmt = (
        select(Course)
        .join(CourseAuthorization, CourseAuthorization.course_id == Course.id)
        .where(
            Course.id == course_id,
            CourseAuthorization.user_id == user.id,
            CourseAuthorization.is_revoked == False,  # noqa: E712
            CourseAuthorization.valid_from <= now,
        )
    )
    return db.execute(stmt).scalars().first()


def _pick_unique_course(rows: list[Course], course_key: str) -> Course | None:
    """命中唯一课程时返回；命中多门时拒绝，避免把数据串到别的课程。"""
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    from app.core.exceptions import AppError

    raise AppError(
        code="COURSE_KEY_AMBIGUOUS",
        message=f"课程标识 {course_key} 对应多门课程，请使用完整课程标识访问",
        status_code=409,
    )


def find_course_by_key(db: Session, course_key: str) -> Course | None:
    """按课程唯一标识查找课程。

    支持的 course_key（按优先级）：
    1. 纯数字：本地课程主键 ``Course.id``（唯一）。
    2. 完整平台标识：``fz_id`` 或 ``platform_course_id``（即 xkhId，唯一）。
    3. ``{course_num}-{完整 fz_id}`` / ``{course_num}-{platform_course_id}``。
    4. 旧版 ``{course_num}-{课序号}``：仅为兼容历史前端保留，不再固定截取
       fz_id 后两位；改为在 course_num 相同的课程中做完整后缀匹配，且只有
       唯一命中才返回。命中多门时抛 ``COURSE_KEY_AMBIGUOUS``，不再静默返回
       任意一门导致不同课程共用同一份回放列表。
    """
    key = (course_key or "").strip()
    if not key:
        return None

    # 1) 本地主键
    if key.isdigit():
        return db.get(Course, int(key))

    # 2) 完整平台标识
    direct = (
        db.query(Course)
        .filter(or_(Course.fz_id == key, Course.platform_course_id == key))
        .all()
    )
    if direct:
        return _pick_unique_course(direct, key)

    # 3) {course_num}-{完整标识}
    course_num = key.split("-", 1)[0]
    rows = db.query(Course).filter(Course.course_num == course_num).all()
    for row in rows:
        if key in (
            f"{row.course_num}-{row.fz_id}",
            f"{row.course_num}-{row.platform_course_id}",
        ):
            return row

    # 4) 旧版 {course_num}-{课序号}：完整后缀匹配 + 唯一性校验
    _, sep, suffix = key.rpartition("-")
    if not sep or not suffix:
        return None

    exact = [r for r in rows if r.fz_id == suffix or r.platform_course_id == suffix]
    if exact:
        return _pick_unique_course(exact, key)

    tail_matched = [
        r
        for r in rows
        if (r.fz_id or "")[-len(suffix):] == suffix
        or (r.platform_course_id or "")[-len(suffix):] == suffix
    ]
    return _pick_unique_course(tail_matched, key)


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