"""解析任务表。对应 docs/03-data-model.md §4，FR-07/14。"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TASK_STATUSES = (
    "queued", "downloading", "extracting_audio",
    "asr_running", "llm_running", "persisting",
    "succeeded", "failed",
)


class ParseTask(Base):
    __tablename__ = "parse_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    lecture_id: Mapped[int | None] = mapped_column(Integer, index=True)
    initiated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True, default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str | None] = mapped_column(String(48))
    error_code: Mapped[str | None] = mapped_column(String(48))
    error_message: Mapped[str | None] = mapped_column(String(512))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    parent_task_id: Mapped[int | None] = mapped_column(ForeignKey("parse_tasks.id"))
    video_cache_path: Mapped[str | None] = mapped_column(String(512))
    audio_cache_path: Mapped[str | None] = mapped_column(String(512))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())