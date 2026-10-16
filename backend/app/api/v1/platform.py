"""课程平台对接端点（CAS 验证码两步流程）。P0。

CAS 登录是系统主入口（无需预先持有本系统 Token）：init 打开 CAS 页截图验证码，
submit 完成登录后按北交大学号 upsert 本系统用户并签发 JWT，前端据此进入系统。
课程同步由 /sync-courses 单独完成，登录时只做 CAS 认证 + 签发 JWT，快速返回。
"""
import json
import secrets as _secrets
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from loguru import logger
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password
from app.db.models import Course, User
from app.db.session import get_db
from app.integrations import platform
from app.schemas.platform import (
    CaptchaInitOut,
    CaptchaSubmitIn,
    CaptchaSubmitOut,
    ReplayOut,
    SyncCoursesOut,
)
from app.schemas.task import TaskOut
from app.schemas.user import UserOut
from app.services import course_service, task_service
from app.workers.parse_worker import run as parse_worker_run

router = APIRouter()


def _normalize_cookies(raw: list | dict) -> list[dict]:
    """将旧格式 cookie dict 规范化为完整 cookie 对象 list。"""
    if isinstance(raw, list):
        return raw
    return [
        {"name": k, "value": v, "domain": ".bjtu.edu.cn", "path": "/"}
        for k, v in raw.items()
    ]


@router.post("/captcha/init", response_model=CaptchaInitOut)
async def captcha_init() -> CaptchaInitOut:
    """打开 CAS 登录页并截图验证码，返回 base64 图片 + session_key。"""
    image_b64, session_key = await platform.init_cas_captcha()
    return CaptchaInitOut(captcha_image_base64=image_b64, session_key=session_key)


@router.post("/captcha/submit", response_model=CaptchaSubmitOut)
async def captcha_submit(
    body: CaptchaSubmitIn, db: Session = Depends(get_db)
) -> CaptchaSubmitOut:
    """填入账号密码与验证码完成 CAS 登录，返回 user_id + 本系统访问令牌。

    仅完成 CAS 认证 + 持久化 cookies + 签发 JWT，不加载课程。
    前端拿到 JWT 后进入主页，由 /sync-courses 异步加载课程。
    """
    cookies, platform_user_id = await platform.submit_cas_captcha(
        body.session_key, body.username, body.password, body.captcha_code
    )

    username = str(platform_user_id)
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        user = User(
            username=username,
            hashed_password=hash_password(_secrets.token_urlsafe(32)),
            role="teacher",
            display_name=f"北交大 {platform_user_id}",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    user.platform_user_id = platform_user_id
    user.platform_cookies = json.dumps(cookies, ensure_ascii=False)
    user.cookies_updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, {"role": user.role})
    return CaptchaSubmitOut(
        user_id=platform_user_id,
        access_token=token,
        user=UserOut.model_validate(user),
    )


@router.post("/sync-courses", response_model=SyncCoursesOut)
async def sync_courses(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SyncCoursesOut:
    """用已存的平台 cookies 重新打开浏览器，从 VE 课程平台同步课程到本地。

    前端进入主页后调用此端点异步加载课程，登录时不再等待课程同步。
    同步后更新 user.platform_cookies 以包含 VE session cookies。
    """
    if not user.platform_cookies:
        from app.core.exceptions import AppError

        raise AppError(code="NO_PLATFORM_COOKIES", message="未找到平台登录凭证，请重新登录", status_code=400)

    cookies = _normalize_cookies(json.loads(user.platform_cookies))
    courses, updated_cookies, ve_user_id = await platform.sync_courses_from_ve(cookies)

    user.platform_cookies = json.dumps(updated_cookies, ensure_ascii=False)
    user.cookies_updated_at = datetime.now(timezone.utc)
    if ve_user_id:
        user.ve_user_id = ve_user_id
    db.commit()

    synced = 0
    for c in courses:
        course_service.import_from_platform(
            db,
            str(c["xkhId"]),
            {
                "title": c.get("courseName") or c.get("courseId") or str(c["cId"]),
                "course_num": c.get("courseId"),
                "fz_id": c.get("xkhId"),
                "platform_c_id": c.get("cId") or None,
                "video_url": "",
            },
        )
        synced += 1
    logger.info(f"用户 {user.username} 同步平台课程 {synced} 门到本地")
    return SyncCoursesOut(synced=synced, total=len(courses))


@router.get("/courses/{course_id}/replays", response_model=list[ReplayOut])
async def get_course_replays(
    course_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReplayOut]:
    """获取某门课程的录像课次列表（API 1）。

    前端进入课程详情页后调用此端点加载回放列表。
    """
    from app.core.exceptions import AppError

    course = db.get(Course, course_id)
    if not course or not course.platform_c_id:
        raise AppError(code="NO_COURSE_ID", message="课程不存在或缺少平台 cId", status_code=400)

    if not user.platform_cookies:
        raise AppError(code="NO_PLATFORM_COOKIES", message="未找到平台登录凭证，请重新登录", status_code=400)

    cookies = _normalize_cookies(json.loads(user.platform_cookies))
    replays = await platform.fetch_replays(cookies, course.platform_c_id)
    return [
        ReplayOut(
            id=r.get("id", 0),
            video_id=r.get("videoId"),
            class_room=r.get("classRoom"),
            course_name=r.get("courseName"),
            teacher_name=r.get("teacherName"),
            teach_time_str=r.get("teachTimeStr"),
            class_begin_time=r.get("classBeginTime"),
            class_end_time=r.get("classEndTime"),
            course_between=r.get("courseBetween"),
            uuid=r.get("uuid"),
        )
        for r in replays
    ]

@router.post("/courses/{course_id}/replays/{replay_id}/parse", response_model=TaskOut, status_code=201)
async def parse_replay(
    course_id: int,
    replay_id: int,
    bg: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取指定课次的视频流 URL 并开始解析。

    前端点击回放列表中某一项时调用：先通过 API 2 获取教师路 HLS 地址，
    写入 course.video_url，再创建解析任务。
    """
    from app.core.exceptions import AppError

    course = db.get(Course, course_id)
    if not course:
        raise AppError(code="NOT_FOUND", message="课程不存在", status_code=404)

    if not user.platform_cookies:
        raise AppError(code="NO_PLATFORM_COOKIES", message="未找到平台登录凭证，请重新登录", status_code=400)

    cookies = _normalize_cookies(json.loads(user.platform_cookies))

    if not user.ve_user_id:
        logger.info(f"ve_user_id 缺失，尝试 UI 模式获取 streamMap")

    logger.info(f"parse_replay: course_id={course_id}, replay_id={replay_id}, ve_user_id={user.ve_user_id}, platform_c_id={course.platform_c_id}")
    stream_map, extracted_uid = await platform.get_stream_map_via_browser(
        cookies, replay_id, user.ve_user_id, course.platform_c_id
    )
    video_url = stream_map.get("teaStreamHlsUrl") or stream_map.get("stuStreamHlsUrl") or ""
    if not video_url:
        raise AppError(code="NO_VIDEO_STREAM", message="未能获取视频流地址", status_code=400)

    logger.info(f"parse_replay: video_url={video_url[:80]}...")
    course.video_url = video_url

    if extracted_uid and not user.ve_user_id:
        user.ve_user_id = extracted_uid
        logger.info(f"parse_replay: 保存提取到的 ve_user_id={extracted_uid}")

    db.commit()

    task_service.ensure_parse_ready(course)
    task = task_service.create_task(db, course_id, user.id)

    import threading
    threading.Thread(target=parse_worker_run, args=(task.id,), daemon=True).start()
    return task
