"""Step 1：拉取回放元数据，并预取平台字幕/知识点（A3）。

对应 docs/04-data-flow.md Step 1 与 docs/10-platform-feasibility-analysis.md §11.1：

- 修正原先的键名不匹配（``fetch_course_meta`` 返回 ``{"cookies","user_id","course","replays"}``），
  把课程标题/教师/课次/时长与教师流 HLS 地址写入 ``courses``；
- 保存回放 id（``rpId``）到 ``courses.platform_replay_id``，供 API 3 / API 6 复用；
- 同一次登录会话内预取平台 VTT 字幕与 zsd 知识点，失败不阻塞流水线（降级为 ASR + LLM）。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy.orm import Session

from app.db.models import Course
from app.integrations import platform
from app.pipeline.errors import StepError
from app.pipeline.steps import platform_assets


@dataclass
class CourseContext:
    """Step 1 产物：课程实体 + 平台侧可复用的字幕/知识点。"""

    course: Course
    replay_id: str | None = None
    vtt_sentences: list[dict] = field(default_factory=list)
    zsd_items: list[dict] = field(default_factory=list)
    platform_error: str | None = None


def fetch_metadata(db: Session, course_id: int) -> CourseContext:
    course = db.get(Course, course_id)
    if not course:
        raise StepError("INVALID_INPUT", f"课程不存在：id={course_id}", step="metadata")

    # 人工导入的课程：video_url 已存在，无需访问课程平台
    if course.source != "platform":
        return CourseContext(course=course)

    if not course.platform_course_id:
        raise StepError("PLATFORM_UNRECOGNIZED", "平台课程缺少 platform_course_id", step="metadata")

    try:
        meta = asyncio.run(platform.fetch_course_meta(course.platform_course_id))
    except Exception as exc:  # noqa: BLE001 - 统一翻译为平台错误码
        raise StepError("PLATFORM_UNREACHABLE", f"课程平台元数据拉取失败：{exc}", step="metadata") from exc

    if not meta:
        raise StepError("PLATFORM_UNREACHABLE", "课程平台未返回元数据（检查 PLATFORM_BASE_URL 与登录凭证）", step="metadata")

    entry = _select_replay(meta, course.platform_replay_id)
    if entry is None:
        raise StepError("PLATFORM_UNRECOGNIZED", "课程平台未返回任何课次（回放）", step="metadata")

    replay_id = _apply_meta(course, meta, entry)
    db.commit()

    ctx = CourseContext(course=course, replay_id=replay_id)
    _prefetch_platform_assets(ctx, meta)
    return ctx


def _select_replay(meta: dict, replay_id: str | None) -> dict | None:
    """按已保存的 rpId 选课次；没有则取第一节课次。"""
    replays = [item for item in (meta.get("replays") or []) if isinstance(item, dict)]
    if not replays:
        return None
    if replay_id:
        for item in replays:
            if _replay_id_of(item) == str(replay_id):
                return item
        logger.warning("[metadata] 未找到 rpId={} 对应的课次，回退为第一节", replay_id)
    return replays[0]


def _replay_id_of(entry: dict) -> str | None:
    replay = entry.get("replay") or {}
    for key in ("videoId", "rpId", "rp_id", "id"):
        value = replay.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _apply_meta(course: Course, meta: dict, entry: dict) -> str | None:
    """把平台元数据写入 courses：标题/教师/课次/时长/教师流地址/rpId。"""
    target = meta.get("course") or {}
    replay = entry.get("replay") or {}
    stream_map = entry.get("stream_map") or {}

    title = target.get("courseName") or replay.get("courseName")
    if title:
        course.title = str(title)[:255]

    teacher = replay.get("teacherName") or target.get("teacherName")
    if teacher:
        course.teacher_name = str(teacher)[:64]

    label = replay.get("teachTimeStr") or replay.get("courseBetween") or target.get("courseBetween")
    if label:
        course.session_label = str(label)[:64]

    duration = _duration_seconds(replay) or _duration_seconds(target)
    if duration:
        course.duration_sec = int(duration)

    video_url = (
        stream_map.get("teaStreamHlsUrl")
        or stream_map.get("teaStreamUrl")
        or stream_map.get("stuStreamHlsUrl")
    )
    if video_url:
        course.video_url = str(video_url)[:1024]
        course.video_format = "hls"

    replay_id = _replay_id_of(entry)
    if replay_id:
        course.platform_replay_id = replay_id[:64]

    logger.info("[metadata] 平台课程已更新：title={} rpId={} duration={}s video_url={}",
                course.title, course.platform_replay_id, course.duration_sec,
                (course.video_url or "")[:60])
    return replay_id


def _duration_seconds(payload: dict) -> float | None:
    """按 docs/10:964-975：``classEndTime - classBeginTime``；兼容毫秒与 ``durationSec``。"""
    for key in ("durationSec", "duration", "rpDuration"):
        value = payload.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)

    begin = payload.get("classBeginTime")
    end = payload.get("classEndTime")
    if isinstance(begin, (int, float)) and isinstance(end, (int, float)):
        diff = float(end) - float(begin)
        if diff <= 0:
            return None
        if diff > 86_400:  # 毫秒时间戳
            diff /= 1000.0
        return diff
    return None


def _prefetch_platform_assets(ctx: CourseContext, meta: dict) -> None:
    """预取平台 VTT 与 zsd；任一失败只记 warning，不阻塞流水线。"""
    replay_id = ctx.replay_id
    cookies = meta.get("cookies") or {}
    if not replay_id or not cookies:
        return

    duration = ctx.course.duration_sec

    try:
        vtt_text = asyncio.run(platform.get_subtitle_vtt(cookies, replay_id))
        ctx.vtt_sentences = platform_assets.parse_vtt(vtt_text)
        logger.info("[metadata] 平台字幕预取：{} 句", len(ctx.vtt_sentences))
    except Exception as exc:  # noqa: BLE001
        ctx.platform_error = str(exc)
        logger.warning("[metadata] 平台字幕预取失败（将走 ASR）：{}", exc)

    try:
        zsd = asyncio.run(platform.list_keypoints(cookies, replay_id))
        ctx.zsd_items = platform_assets.map_zsd(zsd, duration)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[metadata] 平台知识点预取失败（将只用 LLM 结果）：{}", exc)
