"""课程平台对接端点（CAS 验证码两步流程）。P0。"""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db.models import User
from app.integrations import platform
from app.schemas.platform import (
    CaptchaInitIn,
    CaptchaInitOut,
    CaptchaSubmitIn,
    CaptchaSubmitOut,
)

router = APIRouter()


@router.post("/captcha/init", response_model=CaptchaInitOut)
async def captcha_init(
    body: CaptchaInitIn, user: User = Depends(get_current_user)
) -> CaptchaInitOut:
    """打开 CAS 登录页并截图验证码，返回 base64 图片 + session_key。"""
    image_b64, session_key = await platform.init_cas_captcha(body.username, body.password)
    return CaptchaInitOut(captcha_image_base64=image_b64, session_key=session_key)


@router.post("/captcha/submit", response_model=CaptchaSubmitOut)
async def captcha_submit(
    body: CaptchaSubmitIn, user: User = Depends(get_current_user)
) -> CaptchaSubmitOut:
    """填入验证码完成 CAS 登录，返回 user_id + cookies（供后续平台 API 复用）。"""
    cookies, user_id = await platform.submit_cas_captcha(body.session_key, body.captcha_code)
    return CaptchaSubmitOut(user_id=user_id, cookies=cookies)
