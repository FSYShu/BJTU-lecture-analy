"""任务相关 schema。"""
from pydantic import BaseModel


class TaskOut(BaseModel):
    id: int
    course_id: int
    lecture_id: int | None = None
    status: str
    progress: int
    current_step: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_count: int
    parent_task_id: int | None = None

    class Config:
        from_attributes = True


class ActiveTaskOut(TaskOut):
    """排队中/进行中的任务，附带课程与课次信息，便于前端展示“正在解析哪个”。"""

    course_title: str | None = None
    teach_time_str: str | None = None