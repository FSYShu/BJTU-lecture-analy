"""重点时间点 schema。"""
from datetime import datetime

from pydantic import BaseModel


class KeypointOut(BaseModel):
    id: int
    seq_index: int
    title: str
    category: str | None = None
    summary: str | None = None
    timestamp_sec: float
    ai_generated: bool
    source_model: str | None = None
    generated_at: datetime

    class Config:
        from_attributes = True