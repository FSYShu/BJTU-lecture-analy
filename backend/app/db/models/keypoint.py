"""重点时间点表。对应 docs/03-data-model.md §6，FR-04。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

KEYPOINT_CATEGORIES = ("concept", "formula", "example", "exam_point")


class Keypoint(Base):
    __tablename__ = "keypoints"
    __table_args__ = (
        Index("ix_keypoints_course_ts", "course_id", "timestamp_sec"),
        Index("ix_keypoints_course_cat", "course_id", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("parse_tasks.id"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    seq_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(24))
    summary: Mapped[str | None] = mapped_column(Text)
    timestamp_sec: Mapped[float] = mapped_column(Float, nullable=False)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    source_model: Mapped[str | None] = mapped_column(String(64))
    source_transcript_ids: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())