"""课程总结 schema。"""
from datetime import datetime

from pydantic import BaseModel


class SummaryOut(BaseModel):
    id: int
    overview: str | None = None
    chapter_points: str | None = None
    key_details: str | None = None
    review_hints: str | None = None
    ai_generated: bool
    source_model: str | None = None
    generated_at: datetime

    class Config:
        from_attributes = True