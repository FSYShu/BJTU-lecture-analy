"""课程总结表。对应 docs/03-data-model.md §7，FR-05，分层。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("parse_tasks.id"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    lecture_id: Mapped[int | None] = mapped_column(Integer, index=True)
    overview: Mapped[str | None] = mapped_column(Text)
    chapter_points: Mapped[str | None] = mapped_column(Text)
    key_details: Mapped[str | None] = mapped_column(Text)
    review_hints: Mapped[str | None] = mapped_column(Text)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    source_model: Mapped[str | None] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())