"""Step 1：拉取回放元数据。"""
import asyncio

from sqlalchemy.orm import Session

from app.db.models import Course
from app.integrations import platform


def fetch_metadata(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if not course:
        raise ValueError("课程不存在")
    if course.source == "platform":
        meta = asyncio.run(platform.fetch_course_meta(course.platform_course_id))
        course.title = meta.get("title", course.title)
        course.duration_sec = meta.get("duration_sec", course.duration_sec)
        db.commit()
    return course