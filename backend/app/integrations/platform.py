"""北交大课程平台对接客户端。

对接 docs/10-platform-feasibility-analysis.md 中的 API 1/2/3/6 与 CAS 登录。
- CAS 登录需 Playwright（可选依赖：uv add playwright && uv run playwright install chromium）
- 登录成功后导出 Cookie 给 httpx.AsyncClient 复用，后续 API 与视频下载共用会话
- 视频服务器 lmt5.bjtu.edu.cn:8880 的 m3u8/.ts 无需认证，直接 200

对应需求：FR-17 回放列表读取 / FR-18 批量视频拉取 / FR-19 格式兼容。
"""
from __future__ import annotations

import httpx

from app.config import settings

_TEACH_CALENDAR = "/back/rp/common/teachCalendar.shtml"
_QXKT = "/webservices/qxkt.shtml"


def _client(cookies: dict | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.platform_base_url,
        cookies=cookies,
        timeout=settings.platform_request_timeout,
    )


async def cas_login(username: str, password: str, captcha_code: str | None = None) -> tuple[dict, int]:
    """CAS 登录，返回 (Cookie 字典, user_id) 供后续 httpx 复用。

    username/password 由用户在前端登录页手动输入，通过 API 传入。
    captcha_code 由前端验证码输入框透传（manual 模式）。
    user_id 从登录后页面/cookie 中自动提取。
    需要 Playwright 无头浏览器处理图形验证码。验证码策略：
    - ocr: 自动识别（准确率 ~70%，失败重试 3 次后回退 manual）
    - manual: 前端弹出让学生手动输入（最可靠，MVP 默认）
    Cookie 有效期由 PLATFORM_COOKIE_TTL 控制，过期需重新登录。
    """
    if not username or not password:
        raise RuntimeError("CAS 用户名/密码未提供")
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("未安装 Playwright，请执行 uv add playwright && uv run playwright install chromium") from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(settings.platform_cas_login_url)
        await page.fill('input[placeholder="用户名"]', username)
        await page.fill('input[placeholder="密码"]', password)

        if settings.platform_captcha_mode == "ocr":
            captcha_img = await page.query_selector('img[alt="captcha"]')
            if captcha_img:
                await captcha_img.screenshot(path="captcha.png")
                # TODO: captcha_code = ocr_recognize("captcha.png")
                raise NotImplementedError("OCR 验证码识别待接入")
        elif captcha_code:
            await page.fill('input[placeholder="验证码"]', captcha_code)
        else:
            raise NotImplementedError("manual 模式需前端透传验证码，由 API 接收后填入")

        await page.click('button:has-text("登录")')
        await page.wait_for_url("**/mis.bjtu.edu.cn/home/**")
        cookies = {c["name"]: c["value"] for c in await page.context.cookies()}
        user_id = await _extract_user_id(page)
        await browser.close()
        return cookies, user_id


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
    """供 pipeline/steps/metadata.py 调用：返回课程元数据。

    实际实现应先 cas_login() 取 (cookies, user_id)，再 list_user_courses() 获取 cId，
    然后 list_replay_courses(cookies, cId) + get_stream_map(cookies, sched_id, user_id)。
    pipeline 同步上下文中需用 asyncio.run() 包装本协程。
    """
    if not platform_course_id or not settings.platform_base_url:
        return {}
    raise NotImplementedError("请用 asyncio.run 包装 cas_login + list_user_courses + list_replay_courses + get_stream_map 链式调用")


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

    平台已有字幕时可直接用，作为讯飞 ASR 结果的补充/校验；无则走 ASR 生成。
    返回 WebVTT 文本。
    """
    async with _client(cookies) as c:
        resp = await c.get(_QXKT, params={"method": "getSubtitleFile", "rpId": rp_id, "type": "vtt"})
        resp.raise_for_status()
        return resp.text