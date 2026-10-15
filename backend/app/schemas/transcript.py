"""转写字幕 schema。"""
from datetime import datetime

from pydantic import BaseModel


class TranscriptOut(BaseModel):
    id: int
    seq_index: int
    text: str
    start_sec: float
    end_sec: float
    ai_generated: bool
    source_model: str | None = None
    generated_at: datetime

    class Config:
        from_attributes = True