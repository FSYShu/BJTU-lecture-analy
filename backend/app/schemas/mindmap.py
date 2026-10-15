"""思维导图 schema。"""
from datetime import datetime

from pydantic import BaseModel


class MindmapOut(BaseModel):
    id: int
    root_topic: str
    nodes: str
    ai_generated: bool
    source_model: str | None = None
    generated_at: datetime

    class Config:
        from_attributes = True