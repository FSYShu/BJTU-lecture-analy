"""课次回放表。每节回放对应独立的 AI 解析结果。"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Lecture(Base):
    __tablename__ = "lectures"
    __table_args__ = (
        Index("ix_lectures_course_replay", "course_id", "platform_replay_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    platform_replay_id: Mapped[str] = mapped_column(String(64), nullable=False)
    video_url: Mapped[str | None] = mapped_column(String(1024))
    teach_time_str: Mapped[str | None] = mapped_column(String(64))
    class_room: Mapped[str | None] = mapped_column(String(64))
    course_between: Mapped[str | None] = mapped_column(String(64))
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())