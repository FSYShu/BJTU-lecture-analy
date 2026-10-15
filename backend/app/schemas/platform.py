"""课程平台对接 schema（CAS 验证码两步流程）。"""
from pydantic import BaseModel


class CaptchaInitIn(BaseModel):
    username: str
    password: str


class CaptchaInitOut(BaseModel):
    captcha_image_base64: str
    session_key: str


class CaptchaSubmitIn(BaseModel):
    session_key: str
    captcha_code: str


class CaptchaSubmitOut(BaseModel):
    user_id: int
    cookies: dict[str, str]
