"""课程表。对应 docs/03-data-model.md §2。"""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (Index("ix_courses_platform_id", "platform_course_id", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    teacher_name: Mapped[str | None] = mapped_column(String(64))
    session_label: Mapped[str | None] = mapped_column(String(64))
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    video_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    video_format: Mapped[str | None] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(16), default="manual")
    platform_course_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())