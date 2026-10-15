"""北交大课程平台对接客户端。

对接 docs/10-platform-feasibility-analysis.md 中的 API 1/2/3/6 与 CAS 登录。
- CAS 登录需 Playwright（可选依赖：uv add playwright && uv run playwright install chromium）
- 登录成功后导出 Cookie 给 httpx.AsyncClient 复用，后续 API 与视频下载共用会话
- 视频服务器 lmt5.bjtu.edu.cn:8880 的 m3u8/.ts 无需认证，直接 200

对应需求：FR-17 回放列表读取 / FR-18 批量视频拉取 / FR-19 格式兼容。
"""
from __future__ import annotations

import base64
import secrets
import time

import httpx

from app.config import settings

_TEACH_CALENDAR = "/back/rp/common/teachCalendar.shtml"
_QXKT = "/webservices/qxkt.shtml"

_CAPTCHA_SESSION_TTL = 300  # 验证码会话有效期（秒），超时需重新初始化

# 内存态验证码会话：session_key -> Playwright 句柄（init 阶段暂存，submit 阶段消费后销毁）。
# MVP 单实例进程内即可；多实例部署时应迁移到 Redis 等共享存储。
_captcha_sessions: dict[str, dict] = {}


def _client(cookies: dict | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.platform_base_url,
        cookies=cookies,
        timeout=settings.platform_request_timeout,
    )


async def _submit_login(page) -> tuple[dict, int]:
    """点击登录按钮并等待跳转，返回 (Cookie 字典, user_id)。"""
    await page.click('button:has-text("登录")')
    await page.wait_for_url("**/mis.bjtu.edu.cn/home/**")
    cookies = {c["name"]: c["value"] for c in await page.context.cookies()}
    user_id = await _extract_user_id(page)
    return cookies, user_id


async def _recognize_captcha(page, attempts: int = 3) -> str:
    """截图验证码并用 ddddocr 识别；识别失败则点击验证码刷新后重试。"""
    try:
        import ddddocr
    except ImportError as exc:
        raise RuntimeError("OCR 模式需安装 ddddocr：pip install ddddocr") from exc

    ocr = ddddocr.DdddOcr(show_ad=False)
    for _ in range(attempts):
        captcha_img = await page.query_selector('img[alt="captcha"]')
        if captcha_img is None:
            raise RuntimeError("CAS 页面未找到验证码图片")
        code = ocr.classification(await captcha_img.screenshot())
        if code:
            return code
        await captcha_img.click()  # 识别失败刷新验证码
        await page.wait_for_timeout(500)
    return ""


async def init_cas_captcha(username: str, password: str) -> tuple[str, str]:
    """打开 CAS 登录页并截图验证码，返回 (captcha_image_base64, session_key)。

    manual 模式第一步：将返回的 base64 图片展示给前端，用户输入验证码后
    通过 submit_cas_captcha 完成登录。
    """
    if not username or not password:
        raise RuntimeError("CAS 用户名/密码未提供")

    from playwright.async_api import async_playwright

    p = await async_playwright().start()
    browser = None
    try:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(settings.platform_cas_login_url)
        await page.fill('input[placeholder="用户名"]', username)
        await page.fill('input[placeholder="密码"]', password)

        captcha_img = await page.query_selector('img[alt="captcha"]')
        if captcha_img is None:
            raise RuntimeError("CAS 页面未找到验证码图片")
        png = await captcha_img.screenshot()

        session_key = secrets.token_urlsafe(32)
        _captcha_sessions[session_key] = {
            "p": p,
            "browser": browser,
            "page": page,
            "created_at": time.monotonic(),
        }
        return base64.b64encode(png).decode(), session_key
    except Exception:
        if browser is not None:
            await browser.close()
        await p.stop()
        raise


async def submit_cas_captcha(session_key: str, captcha_code: str) -> tuple[dict, int]:
    """用 session_key 恢复页面，填入验证码完成登录，返回 (Cookie 字典, user_id)。

    manual 模式第二步：消费 init_cas_captcha 返回的 session_key。
    """
    session = _captcha_sessions.pop(session_key, None)
    expired = (
        session is not None
        and time.monotonic() - session["created_at"] > _CAPTCHA_SESSION_TTL
    )
    if session is None or expired:
        if session is not None:
            await session["browser"].close()
            await session["p"].stop()
        raise RuntimeError("验证码会话不存在或已过期，请重新初始化")

    p = session["p"]
    browser = session["browser"]
    page = session["page"]
    try:
        if not captcha_code:
            raise RuntimeError("验证码不能为空")
        await page.fill('input[placeholder="验证码"]', captcha_code)
        return await _submit_login(page)
    finally:
        await browser.close()
        await p.stop()


async def cas_login(
    username: str = "",
    password: str = "",
    captcha_code: str | None = None,
    session_key: str | None = None,
) -> tuple[dict, int]:
    """CAS 登录，返回 (Cookie 字典, user_id) 供后续 httpx 复用。

    凭证优先取参数，其次回退 settings.platform_username/password（后台自动登录）。
    验证码策略：
    - manual（MVP 默认）：配合 init_cas_captcha/submit_cas_captcha 两步走，
      或直接传入 captcha_code 一次性完成登录。
    - ocr：截图后 ddddocr 自动识别（失败重试 3 次）。
    Cookie 有效期由 PLATFORM_COOKIE_TTL 控制，过期需重新登录。
    """
    username = username or settings.platform_username
    password = password or settings.platform_password
    if not username or not password:
        raise RuntimeError("CAS 用户名/密码未提供")

    if session_key:
        return await submit_cas_captcha(session_key, captcha_code or "")

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("未安装 Playwright，请执行 uv add playwright && uv run playwright install chromium") from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(settings.platform_cas_login_url)
            await page.fill('input[placeholder="用户名"]', username)
            await page.fill('input[placeholder="密码"]', password)

            if settings.platform_captcha_mode == "ocr":
                captcha_code = await _recognize_captcha(page)
            if captcha_code:
                await page.fill('input[placeholder="验证码"]', captcha_code)

            return await _submit_login(page)
        finally:
            await browser.close()


async def _extract_user_id(page) -> int:
    """从登录后页面中提取 userId（API 2 参数）。

    平台首页 JS 变量或 DOM 中包含 userId，如 duringParam_userId='24301060'。
    """
    raw = await page.evaluate("() => window.duringParam_userId || ''")
    if not raw:
        raise RuntimeError("登录后未能自动提取 userId")
    return int(raw)


async def list_user_courses(cookies: dict) -> list[dict]:
    """登录后自动获取用户可访问的所有课程列表（含 cId）。

    解析课程平台首页 HTML，从每个 courseItem 的 onclick=goPage(cId,...) 中提取。
    返回 [{cId, courseId, courseName, xkhId, xqCode}, ...]。
    cId 即 API 1 的 courseId 参数，无需手动配置 PLATFORM_DEFAULT_COURSE_ID。
    """
    async with _client(cookies) as c:
        resp = await c.get("/back/coursePlatform/coursePlatform.shtml", params={"method": "toCoursePlatform"})
        resp.raise_for_status()
        html = resp.text
    import re
    pattern = re.compile(r"goPage\('(\d+)','([^']+)','([^']+)','([^']+)'")
    courses = []
    for m in pattern.finditer(html):
        courses.append({
            "cId": int(m.group(1)),
            "courseId": m.group(2),
            "xkhId": m.group(3),
            "xqCode": m.group(4),
        })
    return courses


async def list_replay_courses(cookies: dict, course_id: int) -> list[dict]:
    """API 1：获取课程录像课次列表。

    course_id 为 cId，由 list_user_courses() 自动获取，无需手动配置。
    返回 [{id, uuid, videoId, classBeginTime, teacherName, teachTimeStr, ...}]。
    id=courseSchedId 用于 get_stream_map；uuid=timeTableId 用于知识点 API。
    """
    async with _client(cookies) as c:
        resp = await c.get(_TEACH_CALENDAR, params={"method": "toDisplyTeachCourses", "courseId": course_id})
        resp.raise_for_status()
        return resp.json().get("courseSchedList", [])


async def get_stream_map(cookies: dict, course_sched_id: int, user_id: int) -> dict:
    """API 2：获取三路视频流地址（教师/学生/课件 HLS + RTMP）。

    user_id 由 cas_login() 自动提取，无需手动配置。
    返回 streamMap，含 teaStreamHlsUrl / stuStreamHlsUrl / vgaStreamHlsUrl。
    本项目 MVP 优先使用 teaStreamHlsUrl（教师音轨最清晰）。
    """
    async with _client(cookies) as c:
        resp = await c.get(
            _TEACH_CALENDAR,
            params={"method": "toDisplyCourseSchedDetail", "courseSchedId": course_sched_id, "userLevel": 1, "userId": user_id},
        )
        resp.raise_for_status()
        return resp.json()["res"]["streamMap"]


async def fetch_course_meta(platform_course_id: str | None) -> dict:
    """供 pipeline/steps/metadata.py 调用：返回课程元数据与三路流。

    链式编排：cas_login → list_user_courses → list_replay_courses → get_stream_map。
    pipeline 同步上下文中需用 asyncio.run() 包装本协程。
    """
    if not platform_course_id or not settings.platform_base_url:
        return {}

    cookies, user_id = await cas_login()
    courses = await list_user_courses(cookies)
    target = next((c for c in courses if str(c["cId"]) == str(platform_course_id)), None)
    if target is None:
        raise ValueError(f"课程 cId={platform_course_id} 不在用户课程列表中")

    replays = await list_replay_courses(cookies, target["cId"])
    result = []
    for r in replays:
        stream_map = await get_stream_map(cookies, r["id"], user_id)
        result.append({"replay": r, "stream_map": stream_map})

    return {
        "cookies": cookies,
        "user_id": user_id,
        "course": target,
        "replays": result,
    }


async def list_keypoints(cookies: dict, rp_id: str) -> list[dict]:
    """API 3：获取平台已有知识点（章节标记）。

    可作为 LLM 抽取重点的补充/校验来源，zsd_wait_time 与 LLM 重点做时间点对齐校验（偏差 ≤ 2 秒）。
    返回 [{zsd_name, zsd_wait_time, sfm}]。
    """
    async with _client(cookies) as c:
        resp = await c.get(_QXKT, params={"method": "queryVeRpInfoZsd", "rpId": rp_id})
        resp.raise_for_status()
        return resp.json().get("zsdJson", [])


async def get_subtitle_vtt(cookies: dict, rp_id: str) -> str:
    """API 6：获取平台已有 VTT 字幕。

    平台已有字幕时可直接用，作为硅基流动 ASR 结果的补充/校验；无则走 ASR 生成。
    返回 WebVTT 文本。
    """
    async with _client(cookies) as c:
        resp = await c.get(_QXKT, params={"method": "getSubtitleFile", "rpId": rp_id, "type": "vtt"})
        resp.raise_for_status()
        return resp.text
