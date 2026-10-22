"""课程平台对接 schema（CAS 验证码两步流程）。"""
from pydantic import BaseModel

from app.schemas.user import UserOut


class CaptchaInitOut(BaseModel):
    captcha_image_base64: str
    session_key: str


class CaptchaSubmitIn(BaseModel):
    session_key: str
    username: str
    password: str
    captcha_code: str


class CaptchaSubmitOut(BaseModel):
    user_id: int
    access_token: str
    user: UserOut


class SsoLoginIn(BaseModel):
    username: str
    password: str


class SsoLoginOut(BaseModel):
    user_id: int
    access_token: str
    user: UserOut


class SyncCoursesOut(BaseModel):
    synced: int
    total: int

class ReplayOut(BaseModel):
    id: int
    lecture_id: int | None = None
    video_id: str | None = None
    class_room: str | None = None
    course_name: str | None = None
    teacher_name: str | None = None
    teach_time_str: str | None = None
    class_begin_time: str | None = None
    class_end_time: str | None = None
    course_between: str | None = None
    uuid: str | None = None

class ReplayStreamOut(BaseModel):
    video_url: str
