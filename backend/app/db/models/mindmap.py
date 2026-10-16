"""思维导图表。对应 docs/03-data-model.md §8，FR-06，两级结构。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Mindmap(Base):
    __tablename__ = "mindmaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("parse_tasks.id"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    lecture_id: Mapped[int | None] = mapped_column(Integer, index=True)
    root_topic: Mapped[str] = mapped_column(String(255), nullable=False)
    nodes: Mapped[str] = mapped_column(Text, nullable=False)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    source_model: Mapped[str | None] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())