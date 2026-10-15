"""任务相关 schema。"""
from pydantic import BaseModel


class TaskOut(BaseModel):
    id: int
    course_id: int
    status: str
    progress: int
    current_step: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_count: int

    class Config:
        from_attributes = True