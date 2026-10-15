"""课程相关 schema。"""
from pydantic import BaseModel


class CourseOut(BaseModel):
    id: int
    title: str
    teacher_name: str | None = None
    session_label: str | None = None
    duration_sec: int | None = None
    video_url: str
    video_format: str | None = None
    source: str
    platform_course_id: str | None = None
    platform_replay_id: str | None = None

    class Config:
        from_attributes = True


class CourseImportIn(BaseModel):
    title: str
    video_url: str
    teacher_name: str | None = None
    session_label: str | None = None
    duration_sec: int | None = None
    video_format: str | None = None