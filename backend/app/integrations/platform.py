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


def _cookies_to_dict(cookies: list[dict]) -> dict[str, str]:
    """将完整 cookie 对象列表转为 {name: value} 字典，供 httpx 使用。"""
    return {c["name"]: c["value"] for c in cookies}


async def _submit_login(page, username: str) -> tuple[list[dict], int]:
    """点击登录按钮并等待跳转，返回 (完整 Cookie 对象列表, user_id)。

    仅完成 CAS 认证并导出 cookies，不导航到 VE 课程平台。
    user_id 直接取用户输入的学号/教工号（即 CAS 登录用户名）。
    课程同步由 sync_courses_from_ve() 单独完成。
    """

    dialog_text = ""

    async def _on_dialog(dialog):
        nonlocal dialog_text
        dialog_text = dialog.message
        await dialog.dismiss()

    page.on("dialog", _on_dialog)

    await page.click('button:has-text("登录")')
    try:
        await page.wait_for_url("**/mis.bjtu.edu.cn/home/**", timeout=10000)
    except Exception:
        from app.core.exceptions import AppError

        if dialog_text:
            raise AppError(code="CAS_LOGIN_FAILED", message=dialog_text, status_code=400)

        error_text = await page.evaluate(
            """() => {
                const body = document.body.innerText || '';
                const patterns = [
                    /验证码[^\\n]{0,20}/,
                    /密码[^\\n]{0,20}错误/,
                    /用户名[^\\n]{0,20}错误/,
                    /账号[^\\n]{0,20}错误/,
                    /登录失败[^\\n]{0,20}/,
                    /错误[^\\n]{0,30}/,
                ];
                for (const p of patterns) {
                    const m = body.match(p);
                    if (m) return m[0];
                }
                return '';
            }"""
        )
        raise AppError(
            code="CAS_LOGIN_FAILED",
            message=error_text or "登录失败，请检查账号密码和验证码",
            status_code=400,
        )

    user_id = int(username)
    cookies = await page.context.cookies()
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


async def init_cas_captcha() -> tuple[str, str]:
    """打开 CAS 登录页并截图验证码，返回 (captcha_image_base64, session_key)。

    manual 模式第一步：仅打开页面抓取验证码图片，不填写账号密码。
    账号密码与验证码在 submit_cas_captcha 一次性提交。
    """
    from playwright.async_api import async_playwright

    p = await async_playwright().start()
    browser = None
    try:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = await browser.new_page()
        await page.goto(settings.platform_cas_login_url, wait_until="domcontentloaded")

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


async def submit_cas_captcha(
    session_key: str, username: str, password: str, captcha_code: str
) -> tuple[list[dict], int]:
    """用 session_key 恢复页面，填入账号密码与验证码完成登录，返回 (完整 Cookie 对象列表, user_id)。

    manual 模式第二步：消费 init_cas_captcha 返回的 session_key，
    一次性填入账号、密码、验证码后提交登录。仅完成 CAS 认证，不加载课程。
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
        if not username or not password:
            raise RuntimeError("CAS 用户名/密码未提供")
        if not captcha_code:
            raise RuntimeError("验证码不能为空")
        await page.fill('#id_loginname', username)
        await page.fill('#id_password', password)
        await page.fill('#id_captcha_1', captcha_code)
        return await _submit_login(page, username)
    finally:
        await browser.close()
        await p.stop()


async def cas_login(
    username: str = "",
    password: str = "",
    captcha_code: str | None = None,
    session_key: str | None = None,
) -> tuple[list[dict], int]:
    """CAS 登录，返回 (完整 Cookie 对象列表, user_id) 供后续复用。

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
        return await submit_cas_captcha(session_key, username, password, captcha_code or "")

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("未安装 Playwright，请执行 uv add playwright && uv run playwright install chromium") from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            page = await browser.new_page()
            await page.goto(settings.platform_cas_login_url, wait_until="domcontentloaded")
            await page.fill('#id_loginname', username)
            await page.fill('#id_password', password)

            if settings.platform_captcha_mode == "ocr":
                captcha_code = await _recognize_captcha(page)
            if captcha_code:
                await page.fill('#id_captcha_1', captcha_code)

            return await _submit_login(page, username)
        finally:
            await browser.close()


async def sso_login(username: str, password: str) -> tuple[list[dict], int]:
    """SSO 统一身份认证登录（无验证码），返回 (完整 Cookie 对象列表, user_id)。

    访问 mis.bjtu.edu.cn 自动重定向到 sso.bjtu.edu.cn 登录页，
    通过页面内置 doLogin() 函数完成 SM2 加密并提交表单，
    登录成功后重定向回 mis.bjtu.edu.cn，导出 cookies。
    user_id 直接取用户输入的学号/教工号。
    """
    from loguru import logger

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("未安装 Playwright，请执行 uv add playwright && uv run playwright install chromium") from exc

    if not username or not password:
        raise RuntimeError("SSO 用户名/密码未提供")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            page = await browser.new_page()
            logger.info("[platform] SSO 登录：访问 {}", settings.platform_cas_login_url)
            await page.goto(settings.platform_cas_login_url, wait_until="domcontentloaded", timeout=30000)
            logger.info("[platform] SSO 登录：已跳转到 {}", page.url)

            await page.wait_for_function("typeof doLogin === 'function'", timeout=10000)

            await page.evaluate(
                """(args) => doLogin({
                    username: args[0],
                    password: args[1],
                    type: 'username_password'
                })""",
                [username, password],
            )
            logger.info("[platform] SSO 登录：已调用 doLogin 提交表单")

            try:
                await page.wait_for_function(
                    "() => window.location.hostname === 'mis.bjtu.edu.cn'",
                    timeout=15000,
                )
                logger.info("[platform] SSO 登录成功，当前 URL: {}", page.url)
            except Exception:
                from app.core.exceptions import AppError

                error_text = await page.evaluate(
                    """() => {
                        if (typeof error !== 'undefined' && error) return String(error);
                        const body = document.body.innerText || '';
                        const patterns = [
                            /密码[^\\n]{0,20}错误/,
                            /用户名[^\\n]{0,20}错误/,
                            /账号[^\\n]{0,20}错误/,
                            /登录失败[^\\n]{0,20}/,
                            /错误[^\\n]{0,30}/,
                        ];
                        for (const p of patterns) {
                            const m = body.match(p);
                            if (m) return m[0];
                        }
                        return '';
                    }"""
                )
                raise AppError(
                    code="SSO_LOGIN_FAILED",
                    message=error_text or "登录失败，请检查账号密码",
                    status_code=400,
                )

            user_id = int(username)
            cookies = await page.context.cookies()
            return cookies, user_id
        finally:
            await browser.close()


async def sync_courses_from_ve(cookies: list[dict]) -> tuple[list[dict], list[dict], int | None]:
    """用已存的 cookies 重新打开浏览器，导航到 VE 课程平台并提取课程列表。

    登录后异步调用：设置 cookies（保留原始 domain）到浏览器 context，
    访问 mis /module/module/28/ 触发 SSO 跳转获取 VE session，
    等待 .courseItem DOM 渲染后提取课程数据。
    返回 (课程列表, 更新后的完整 cookies, VE 内部用户 ID)。
    """
    from loguru import logger

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("未安装 Playwright，请执行 uv add playwright && uv run playwright install chromium") from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            context = await browser.new_context()
            await context.add_cookies(cookies)
            page = await context.new_page()

            await page.goto(
                "https://mis.bjtu.edu.cn/module/module/28/",
                wait_until="load",
                timeout=15000,
            )
            logger.info("[platform] 同步课程：通过 mis 课程平台入口跳转，当前 URL: {}", page.url)

            try:
                await page.wait_for_selector(".courseItem", timeout=10000)
            except Exception:
                logger.warning("[platform] 等待 .courseItem 超时，课程列表可能未渲染")

            courses = await page.evaluate(
                """() => Array.from(document.querySelectorAll('.courseItem')).map(el => {
                    const onclick = el.getAttribute('onclick') || '';
                    const match = onclick.match(/goPage\\('(\\d+)','([^']+)','([^']+)','([^']+)'\\)/);
                    const texts = el.querySelectorAll('.course-text');
                    return {
                        cId: match ? parseInt(match[1]) : 0,
                        courseId: match ? match[2] : '',
                        courseName: texts[0] ? (texts[0].getAttribute('title') || texts[0].textContent.trim()) : '',
                        xkhId: match ? match[3] : '',
                        xqCode: match ? match[4] : '',
                    };
                })"""
            )
            logger.info("[platform] 从 VE 页面 DOM 提取 {} 门课程", len(courses))
            if courses:
                logger.info("[platform] 前 3 门: {}", courses[:3])

            updated_cookies = await context.cookies()

            return courses, updated_cookies, None
        finally:
            await browser.close()


async def get_stream_map_via_browser(
    cookies: list[dict],
    course_sched_id: int,
    ve_user_id: int | None = None,
    platform_c_id: int | None = None,
) -> tuple[dict, int | None]:
    """用 Playwright 浏览器获取视频流地址（API 2）。

    返回 (streamMap, extracted_user_id)。extracted_user_id 为从页面提取的
    VE 内部用户 ID，调用方可持久化以避免重复提取。

    策略 1（优先）：通过 UI 点击导航到回放项，拦截平台自己发出的 API 2 请求响应。
    策略 2（fallback）：若已知 ve_user_id，直接调 API 2。
    """
    from loguru import logger

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("未安装 Playwright") from exc

    if platform_c_id:
        try:
            result, extracted_uid = await _get_stream_map_via_ui(
                cookies, platform_c_id, course_sched_id
            )
            if result:
                return result, extracted_uid
            logger.warning("[platform] UI 点击方式未获取到 streamMap，回退到直接调用")
        except Exception as e:
            logger.warning("[platform] UI 点击方式失败: {}，回退到直接调用", e)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            context = await browser.new_context()
            await context.add_cookies(cookies)
            page = await context.new_page()

            await page.goto(
                "https://mis.bjtu.edu.cn/module/module/28/",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            try:
                await page.wait_for_selector(".courseItem", timeout=10000)
            except Exception:
                pass

            extracted_uid = None
            if not ve_user_id:
                ve_user_id = await _extract_user_id_from_page(page)
                if ve_user_id:
                    logger.info("[platform] 从课程平台页面提取到 ve_user_id={}", ve_user_id)
                    extracted_uid = ve_user_id

            if not ve_user_id:
                from app.core.exceptions import AppError

                raise AppError(
                    code="NO_VE_USER_ID",
                    message="未能提取平台用户 ID，请重新登录",
                    status_code=400,
                )

            api_url = f"{settings.platform_base_url}{_TEACH_CALENDAR}?method=toDisplyCourseSchedDetail&courseSchedId={course_sched_id}&userLevel=1&userId={ve_user_id}"
            logger.info("[platform] API 2 via browser goto: {}", api_url)

            resp = await page.goto(api_url, wait_until="domcontentloaded", timeout=15000)
            body = await resp.text()
            import json as _json

            data = _json.loads(body)
            logger.info("[platform] API 2 响应 keys: {}", list(data.keys()) if isinstance(data, dict) else "not dict")

            if "res" not in data:
                logger.error("[platform] API 2 响应异常: {}", data)
                raise RuntimeError(f"平台返回异常响应: {data}")
            return data["res"]["streamMap"], extracted_uid
        finally:
            await browser.close()


async def _get_stream_map_via_ui(
    cookies: list[dict], platform_c_id: int, course_sched_id: int
) -> tuple[dict | None, int | None]:
    """通过 UI 导航获取 streamMap，让平台 JavaScript 自己处理 userId。

    返回 (streamMap, extracted_user_id)。

    课程平台 → 点击课程项 → 课程详情页 → 提取 newModuleGoTo 参数 →
    直接 goto 视频回放 URL → 等待回放列表加载 → 点击回放项 →
    拦截 API 2 响应 → 返回 streamMap。
    """
    from loguru import logger
    import asyncio
    import json as _json

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("未安装 Playwright") from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            context = await browser.new_context()
            await context.add_cookies(cookies)
            page = await context.new_page()

            await page.goto(
                "https://mis.bjtu.edu.cn/module/module/28/",
                wait_until="load",
                timeout=20000,
            )
            try:
                await page.wait_for_selector(".courseItem", timeout=10000)
            except Exception:
                logger.warning("[platform] UI 模式: .courseItem 未找到")
                return None, None

            course_items = await page.query_selector_all(".courseItem")
            target_item = None
            for item in course_items:
                onclick = await item.get_attribute("onclick") or ""
                if f"'{platform_c_id}'" in onclick:
                    target_item = item
                    break

            if target_item is None:
                logger.warning("[platform] UI 模式: 未找到 cId={} 的课程项", platform_c_id)
                return None, None

            logger.info("[platform] UI 模式: 点击课程项 cId={}", platform_c_id)
            async with context.expect_page(timeout=15000) as new_page_info:
                await target_item.click()
            detail_page = await new_page_info.value
            await detail_page.wait_for_load_state("domcontentloaded")
            logger.info("[platform] UI 模式: 详情页 URL={}", detail_page.url[:120])

            nav_params = await detail_page.evaluate(
                """() => {
                    let replayCourseToPage = null;
                    const menuItems = document.querySelectorAll('[onclick]');
                    for (const el of menuItems) {
                        const onclick = el.getAttribute('onclick') || '';
                        const text = (el.textContent || '').trim();
                        if (text === '视频回放') {
                            const m = onclick.match(/courseToPage=(\\d+)/);
                            if (m) replayCourseToPage = m[1];
                        }
                    }
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        const text = s.textContent || '';
                        if (text.includes('newModuleGoTo')) {
                            const courseId = (text.match(/courseId\\s*=\\s*['"]([^'"]+)/) || [])[1];
                            const cId = (text.match(/\\bcId\\s*=\\s*['"]([^'"]+)/) || [])[1];
                            const xkhId = (text.match(/xkhId\\s*=\\s*['"]([^'"]+)/) || [])[1];
                            const xqCode = (text.match(/xqCode\\s*=\\s*['"]([^'"]+)/) || [])[1];
                            const teacherId = (text.match(/teacherId\\s*=\\s*['"]([^'"]+)/) || [])[1];
                            if (courseId && cId) {
                                return {courseId, cId, xkhId, xqCode, teacherId, replayCourseToPage: replayCourseToPage || '10480'};
                            }
                        }
                    }
                    return null;
                }"""
            )

            if not nav_params:
                logger.warning("[platform] UI 模式: 未能从 newModuleGoTo 提取导航参数")
                await detail_page.close()
                return None, None

            logger.info("[platform] UI 模式: 提取到导航参数: {}", nav_params)

            replay_url = (
                f"http://123.121.147.7:88/ve/back/coursePlatform/coursePlatform.shtml"
                f"?method=toCoursePlatform&courseToPage={nav_params.get('replayCourseToPage', '10480')}"
                f"&courseId={nav_params['courseId']}&dataSource=1"
                f"&cId={nav_params['cId']}"
            )
            if nav_params.get("xkhId"):
                replay_url += f"&xkhId={nav_params['xkhId']}"
            if nav_params.get("xqCode"):
                replay_url += f"&xqCode={nav_params['xqCode']}"
            if nav_params.get("teacherId"):
                replay_url += f"&teacherId={nav_params['teacherId']}"

            logger.info("[platform] UI 模式: 直接导航到视频回放页: {}", replay_url[:120])

            api2_response_data = None

            async def _on_response(response):
                nonlocal api2_response_data
                if "toDisplyCourseSchedDetail" in response.url:
                    try:
                        body = await response.text()
                        api2_response_data = _json.loads(body)
                        logger.info("[platform] UI 模式: 拦截到 API 2 响应, keys={}", list(api2_response_data.keys()) if isinstance(api2_response_data, dict) else "N/A")
                    except Exception:
                        pass

            detail_page.on("response", _on_response)

            await detail_page.goto(replay_url, wait_until="load", timeout=20000)
            await asyncio.sleep(3)
            logger.info("[platform] UI 模式: 回放页加载完成, URL={}", detail_page.url[:120])

            page_title = await detail_page.title()
            logger.info("[platform] UI 模式: 回放页标题: {}", page_title)

            teacher_id_str = nav_params.get("teacherId", "")
            extracted_user_id = await detail_page.evaluate(
                """(teacherIdStr) => {
                    const scripts = document.querySelectorAll('script');
                    const allText = Array.from(scripts).map(s => s.textContent || '').join('\\n');

                    // Strategy 1: match userId: 'NNNNNN' (ajax data pattern in getScheInfo)
                    const ajaxMatches = [...allText.matchAll(/userId\\s*:\\s*['"](\\d{4,10})/g)];
                    const candidates = ajaxMatches.map(m => m[1]).filter(v => v !== teacherIdStr);

                    if (candidates.length > 0) {
                        // Pick the most frequent candidate
                        const counts = {};
                        for (const v of candidates) counts[v] = (counts[v] || 0) + 1;
                        const best = Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
                        return parseInt(best);
                    }

                    // Strategy 2: any userId pattern, exclude teacherId
                    const generalMatches = [...allText.matchAll(/userId['"]?\\s*[:=]\\s*['"]?(\\d{4,10})/g)];
                    const generalCandidates = generalMatches.map(m => m[1]).filter(v => v !== teacherIdStr);
                    if (generalCandidates.length > 0) {
                        const counts = {};
                        for (const v of generalCandidates) counts[v] = (counts[v] || 0) + 1;
                        const best = Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
                        return parseInt(best);
                    }
                    return null;
                }""",
                teacher_id_str,
            )
            if extracted_user_id:
                logger.info("[platform] UI 模式: 从回放页 JS 提取到 userId={}", extracted_user_id)

            if extracted_user_id:
                api_url = f"{settings.platform_base_url}{_TEACH_CALENDAR}?method=toDisplyCourseSchedDetail&courseSchedId={course_sched_id}&userLevel=1&userId={extracted_user_id}"
                logger.info("[platform] UI 模式: 直接调 API 2: {}", api_url[:120])
                resp = await detail_page.goto(api_url, wait_until="domcontentloaded", timeout=15000)
                body = await resp.text()
                data = _json.loads(body)
                logger.info("[platform] UI 模式: API 2 响应 keys: {}", list(data.keys()) if isinstance(data, dict) else "N/A")
                if "res" in data:
                    stream_map = data["res"]["streamMap"]
                    logger.info("[platform] UI 模式: 成功获取 streamMap, keys={}", list(stream_map.keys()))
                    await detail_page.close()
                    return stream_map, extracted_user_id
                else:
                    logger.error("[platform] UI 模式: API 2 响应异常: {}", data)

            logger.info("[platform] UI 模式: 尝试通过点击回放项拦截 API 2 响应")
            try:
                await detail_page.goto(replay_url, wait_until="load", timeout=20000)
                await detail_page.wait_for_selector(".teachingCalendarItem", timeout=15000)
                logger.info("[platform] UI 模式: 回放列表已渲染")
            except Exception:
                logger.warning("[platform] UI 模式: 等待 .teachingCalendarItem 超时")
                html = await detail_page.content()
                with open("storage/logs/replay_page.html", "w", encoding="utf-8") as f:
                    f.write(html)
                logger.info("[platform] 回放页 HTML 已保存到 storage/logs/replay_page.html")
                await detail_page.close()
                return None, None

            api2_response_data = None

            async def _on_response2(response):
                nonlocal api2_response_data
                if "toDisplyCourseSchedDetail" in response.url:
                    try:
                        body = await response.text()
                        api2_response_data = _json.loads(body)
                        logger.info("[platform] UI 模式: 拦截到 API 2 响应, keys={}", list(api2_response_data.keys()) if isinstance(api2_response_data, dict) else "N/A")
                    except Exception:
                        pass

            detail_page.on("response", _on_response2)

            target_selector = f"#sched_{course_sched_id}"
            target_el = await detail_page.query_selector(target_selector)
            if target_el:
                logger.info("[platform] UI 模式: 点击回放项 #{}", target_selector)
                await target_el.click()
            else:
                logger.warning("[platform] UI 模式: 未找到 {}，点击第一个回放项", target_selector)
                first_item = await detail_page.query_selector(".teachingCalendarItem")
                if first_item:
                    await first_item.click()
                else:
                    await detail_page.close()
                    return None, None

            for _ in range(30):
                if api2_response_data is not None:
                    break
                await asyncio.sleep(0.5)

            await detail_page.close()

            if api2_response_data is None:
                logger.warning("[platform] UI 模式: 未拦截到 API 2 响应")
                return None, None

            if "res" not in api2_response_data:
                logger.error("[platform] UI 模式: API 2 响应异常: {}", api2_response_data)
                return None, None

            stream_map = api2_response_data["res"]["streamMap"]
            logger.info("[platform] UI 模式: 成功获取 streamMap, keys={}", list(stream_map.keys()))
            return stream_map, extracted_user_id
        finally:
            await browser.close()


async def _extract_user_id_from_page(page) -> int | None:
    """从当前页面上下文 aggressively 提取 VE 平台内部用户 ID。

    依次尝试：URL 参数 → window 全局变量 → cookies → localStorage →
    script 标签内联代码 → 点击课程项进入详情页再提取。
    排除 teacherId 值（容易与 userId 混淆）。
    """
    from loguru import logger

    teacher_ids = await page.evaluate(
        """() => {
            const ids = new Set();
            try {
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                    const text = s.textContent || '';
                    const m = text.match(/teacherId['"]?\\s*[:=]\\s*['"]?(\\d{1,10})/);
                    if (m) ids.add(parseInt(m[1]));
                }
            } catch(e) {}
            return Array.from(ids);
        }"""
    )
    if teacher_ids:
        logger.info("[platform] 页面上发现的 teacherId 值: {}（将排除）", teacher_ids)

    ve_user_id = await page.evaluate(
        """(excludeIds) => {
            const url = window.location.href;
            for (const key of ['userId', 'user_id', 'uid', 'userid', 'id']) {
                const m = new RegExp('[?&]' + key + '=(\\\\d+)').exec(url);
                if (m && !excludeIds.includes(parseInt(m[1]))) return parseInt(m[1]);
            }
            for (const v of ['duringParam_userId','userId','user_id','USER_ID','uid','userid',
                              'currentUserId','loginUserId','g_userId','loginUser',
                              'veUserId','ve_user_id','platformUserId','memberId','empId']) {
                try {
                    const raw = String(window[v] || '');
                    if (raw && /^\\d{4,10}$/.test(raw) && !excludeIds.includes(parseInt(raw))) return parseInt(raw);
                } catch(e) {}
            }
            try {
                const cookies = document.cookie.split(';');
                for (const c of cookies) {
                    const parts = c.trim().split('=');
                    if (parts.length === 2 && /^\\d{4,10}$/.test(parts[1]) && !excludeIds.includes(parseInt(parts[1]))) return parseInt(parts[1]);
                }
            } catch(e) {}
            try {
                for (let i = 0; i < localStorage.length; i++) {
                    const v = localStorage.getItem(localStorage.key(i));
                    if (v && /^\\d{4,10}$/.test(v) && !excludeIds.includes(parseInt(v))) return parseInt(v);
                }
            } catch(e) {}
            try {
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                    const text = s.textContent || '';
                    const patterns = [
                        /\\buserId['"]?\\s*[:=]\\s*['"]?(\\d{4,10})/,
                        /\\buser_id['"]?\\s*[:=]\\s*['"]?(\\d{4,10})/,
                        /\\bloginUserId['"]?\\s*[:=]\\s*['"]?(\\d{4,10})/,
                        /\\bcurrentUserId['"]?\\s*[:=]\\s*['"]?(\\d{4,10})/,
                        /\\bmemberId['"]?\\s*[:=]\\s*['"]?(\\d{4,10})/,
                    ];
                    for (const p of patterns) {
                        const m = text.match(p);
                        if (m && !excludeIds.includes(parseInt(m[1]))) return parseInt(m[1]);
                    }
                }
            } catch(e) {}
            return null;
        }""",
        teacher_ids or [],
    )
    if ve_user_id:
        logger.info("[platform] 从课程列表页提取到 ve_user_id={}", ve_user_id)
        return ve_user_id

    try:
        course_items = await page.query_selector_all(".courseItem")
        if not course_items:
            return None

        async with page.context.expect_page(timeout=15000) as new_page_info:
            await course_items[0].click()
        detail_page = await new_page_info.value
        await detail_page.wait_for_load_state("domcontentloaded")
        logger.info("[platform] 打开课程详情页: {}", detail_page.url[:100])

        detail_teacher_ids = await detail_page.evaluate(
            """() => {
                const ids = new Set();
                try {
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        const text = s.textContent || '';
                        const m = text.match(/teacherId['"]?\\s*[:=]\\s*['"]?(\\d{1,10})/);
                        if (m) ids.add(parseInt(m[1]));
                    }
                } catch(e) {}
                return Array.from(ids);
            }"""
        )
        all_exclude = list(set((teacher_ids or []) + (detail_teacher_ids or [])))
        if detail_teacher_ids:
            logger.info("[platform] 详情页 teacherId 值: {}（将排除）", detail_teacher_ids)

        ve_user_id = await detail_page.evaluate(
            """(excludeIds) => {
                for (const v of ['userId','user_id','USER_ID','uid','userid',
                                  'currentUserId','loginUserId','g_userId','loginUser',
                                  'veUserId','ve_user_id','platformUserId','memberId','empId',
                                  'duringParam_userId']) {
                    try {
                        const raw = String(window[v] || '');
                        if (raw && /^\\d{4,10}$/.test(raw) && !excludeIds.includes(parseInt(raw))) return parseInt(raw);
                    } catch(e) {}
                }
                try {
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        const text = s.textContent || '';
                        const patterns = [
                            /\\buserId['"]?\\s*[:=]\\s*['"]?(\\d{4,10})/,
                            /\\buser_id['"]?\\s*[:=]\\s*['"]?(\\d{4,10})/,
                            /\\bloginUserId['"]?\\s*[:=]\\s*['"]?(\\d{4,10})/,
                            /\\bcurrentUserId['"]?\\s*[:=]\\s*['"]?(\\d{4,10})/,
                            /\\bmemberId['"]?\\s*[:=]\\s*['"]?(\\d{4,10})/,
                        ];
                        for (const p of patterns) {
                            const m = text.match(p);
                            if (m && !excludeIds.includes(parseInt(m[1]))) return parseInt(m[1]);
                        }
                    }
                } catch(e) {}
                return null;
            }""",
            all_exclude,
        )
        if ve_user_id:
            logger.info("[platform] 从课程详情页提取到 ve_user_id={}", ve_user_id)

        if not ve_user_id:
            captured = await _extract_user_id_from_replay_page(detail_page)
            ve_user_id = captured
            if ve_user_id:
                logger.info("[platform] 从视频回放页 AJAX 拦截到 ve_user_id={}", ve_user_id)

        await detail_page.close()
        return ve_user_id
    except Exception as e:
        logger.warning("[platform] 从课程详情页提取 ve_user_id 失败: {}", e)
        return None


async def _extract_user_id_from_replay_page(detail_page) -> int | None:
    """在课程详情页点击"视频回放"，拦截 AJAX 请求中的 userId。"""
    from loguru import logger
    import asyncio

    captured_user_id = None

    def _capture(request):
        nonlocal captured_user_id
        url = request.url
        if "userId=" in url:
            import re

            m = re.search(r"userId=(\d+)", url)
            if m:
                captured_user_id = int(m.group(1))

    detail_page.on("request", _capture)

    try:
        replay_menu = await detail_page.query_selector(
            'a:has-text("视频回放"), li:has-text("视频回放"), span:has-text("视频回放")'
        )
        if replay_menu is None:
            return None

        await replay_menu.click()
        await detail_page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception as e:
        logger.warning("[platform] 点击'视频回放'失败: {}", e)
        return None

    for _ in range(20):
        if captured_user_id is not None:
            break
        await asyncio.sleep(0.5)

    return captured_user_id


async def fetch_replays(cookies: list[dict], c_id: int) -> list[dict]:
    """获取某门课程的录像课次列表（API 1）。

    c_id 为平台 cId（courseItem onclick 第一个参数），由 sync_courses_from_ve 存入 Course.platform_c_id。
    返回 [{id, uuid, videoId, classBeginTime, classEndTime, teacherName, teachTime)Str, courseBetween, ...}]。
    """
    return await list_replay_courses(_cookies_to_dict(cookies), c_id)


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
    from loguru import logger
    from pathlib import Path

    pattern = re.compile(r"goPage\('(\d+)','([^']+)','([^']+)','([^']+)'")
    name_pattern = re.compile(r"goPage\('(\d+)','[^']+','[^']+','[^']+'\)[^>]*>\s*([^<]+?)\s*<")
    names = {int(m.group(1)): m.group(2).strip() for m in name_pattern.finditer(html)}
    courses = []
    for m in pattern.finditer(html):
        cId = int(m.group(1))
        courses.append({
            "cId": cId,
            "courseId": m.group(2),
            "courseName": names.get(cId, m.group(2)),
            "xkhId": m.group(3),
            "xqCode": m.group(4),
        })
    if not courses:
        log_dir = Path("storage/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "course_platform.html").write_text(html, encoding="utf-8")
        logger.warning(
            "[platform] 课程列表正则未匹配，HTML 已保存到 storage/logs/course_platform.html"
            "（长度 {}，含 goPage: {}）", len(html), "goPage" in html,
        )
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
    from loguru import logger

    async with _client(cookies) as c:
        resp = await c.get(
            _TEACH_CALENDAR,
            params={"method": "toDisplyCourseSchedDetail", "courseSchedId": course_sched_id, "userLevel": 1, "userId": user_id},
        )
        resp.raise_for_status()
        data = resp.json()
        if "res" not in data:
            logger.error("[platform] get_stream_map 响应异常: {}", data)
            raise RuntimeError(f"平台返回异常响应: {data}")
        return data["res"]["streamMap"]


async def fetch_course_meta(platform_course_id: str | None) -> dict:
    """供 pipeline/steps/metadata.py 调用：返回课程元数据与三路流。

    链式编排：cas_login → list_user_courses → list_replay_courses → get_stream_map。
    pipeline 同步上下文中需用 asyncio.run() 包装本协程。
    """
    if not platform_course_id or not settings.platform_base_url:
        return {}

    cookies, user_id = await cas_login()
    cookie_dict = _cookies_to_dict(cookies)
    courses = await list_user_courses(cookie_dict)
    target = next((c for c in courses if str(c["cId"]) == str(platform_course_id)), None)
    if target is None:
        raise ValueError(f"课程 cId={platform_course_id} 不在用户课程列表中")

    replays = await list_replay_courses(cookie_dict, target["cId"])
    result = []
    for r in replays:
        stream_map = await get_stream_map(cookie_dict, r["id"], user_id)
        result.append({"replay": r, "stream_map": stream_map})

    return {
        "cookies": cookie_dict,
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
