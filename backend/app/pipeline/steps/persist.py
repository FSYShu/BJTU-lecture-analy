"""Step 6：持久化结构化结果。事务写入，失败回滚但原任务记录保留（A4-1）。

- 转写/重点的来源标识（``ai_generated``、``source_model``）由生成方决定：
  ASR 结果写 ``siliconflow-asr``，平台 VTT/zsd 写 ``platform-vtt`` / ``platform-zsd``；
- 时间戳越界丢弃并**告警**（docs/05:51、AC-03-03），``category`` 走白名单（docs/03:121）；
- 重点的 ``source_transcript_ids`` 由本地 seq → 真实转写 id 换算（docs/03:126 溯源）；
- 部分失败时允许 summary / mindmap 缺省：不写空记录，前端按 AC-04-07 / AC-05-06 显示"尚未生成"。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Course, Keypoint, Mindmap, Summary, Transcript
from app.db.models.keypoint import KEYPOINT_CATEGORIES
from app.pipeline.errors import StepError

_GAP_WARN_SEC = 10.0


def save_results(
    db: Session,
    task_id: int,
    course_id: int,
    transcripts: list[dict],
    keypoints: list[dict],
    summary: dict,
    mindmap: dict,
    lecture_id: int | None = None,
) -> None:
    course = db.get(Course, course_id)
    duration = float(course.duration_sec or 0)
    now = datetime.now(timezone.utc)

    try:
        seq_to_id = _save_transcripts(db, task_id, course_id, transcripts, duration, now, lecture_id)
        _save_keypoints(db, task_id, course_id, keypoints, duration, now, seq_to_id, lecture_id)
        _save_summary(db, task_id, course_id, summary, now, lecture_id)
        _save_mindmap(db, task_id, course_id, mindmap, course, now, lecture_id)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - 统一翻译为 PERSIST_FAIL
        db.rollback()
        raise StepError("PERSIST_FAIL", f"解析结果落库失败：{exc}", step="persist") from exc


def _save_transcripts(
    db: Session,
    task_id: int,
    course_id: int,
    transcripts: list[dict],
    duration: float,
    now: datetime,
    lecture_id: int | None = None,
) -> dict[int, int]:
    """写入转写，返回 ``{seq_index: transcript.id}`` 供重点溯源。"""
    rows: list[Transcript] = []
    for index, item in enumerate(transcripts or []):
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        start = max(0.0, float(item.get("start_sec", 0.0) or 0.0))
        end = float(item.get("end_sec", 0.0) or 0.0)
        if end <= start:
            end = start + 0.5
        if duration and end > duration:
            logger.warning("[persist] 字幕越界已截断：{:.1f}s → {:.1f}s（时长 {:.0f}s）", end, duration, duration)
            end = duration
            if end <= start:
                logger.warning("[persist] 字幕起点越界，已丢弃：{:.1f}s", start)
                continue

        row = Transcript(
            task_id=task_id,
            course_id=course_id,
            lecture_id=lecture_id,
            seq_index=len(rows),
            text=text,
            start_sec=round(start, 2),
            end_sec=round(end, 2),
            ai_generated=bool(item.get("ai_generated", True)),
            source_model=item.get("source_model") or settings.siliconflow_asr_model,
            generated_at=now,
        )
        db.add(row)
        rows.append(row)

    db.flush()  # 取得自增主键，供重点时间点溯源
    _warn_gaps(rows)
    return {index: row.id for index, row in enumerate(rows)}


def _warn_gaps(rows: list[Transcript]) -> None:
    for prev, cur in zip(rows, rows[1:]):
        gap = float(cur.start_sec) - float(prev.end_sec)
        if gap > _GAP_WARN_SEC:
            logger.warning("[persist] 发现字幕空洞 {:.1f}s（{:.1f}s → {:.1f}s）",
                           gap, prev.end_sec, cur.start_sec)


def _save_keypoints(
    db: Session,
    task_id: int,
    course_id: int,
    keypoints: list[dict],
    duration: float,
    now: datetime,
    seq_to_id: dict[int, int],
    lecture_id: int | None = None,
) -> None:
    ordered = sorted(
        (item for item in (keypoints or []) if isinstance(item, dict)),
        key=lambda item: float(item.get("timestamp_sec", 0.0) or 0.0),
    )
    saved = 0
    for item in ordered:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        timestamp = float(item.get("timestamp_sec", 0.0) or 0.0)
        if timestamp < 0 or (duration and timestamp > duration):
            logger.warning("[persist] 丢弃越界重点：{} @ {:.1f}s（时长 {:.0f}s）", title, timestamp, duration)
            continue

        category = item.get("category")
        if category not in KEYPOINT_CATEGORIES:
            if category:
                logger.warning("[persist] 重点类型非法，归为 concept：{}", category)
            category = "concept"

        db.add(Keypoint(
            task_id=task_id,
            course_id=course_id,
            lecture_id=lecture_id,
            seq_index=saved,
            title=title[:255],
            category=category,
            summary=item.get("summary"),
            timestamp_sec=round(timestamp, 2),
            ai_generated=bool(item.get("ai_generated", True)),
            source_model=item.get("source_model") or settings.siliconflow_model,
            source_transcript_ids=json.dumps(_resolve_source_ids(item, seq_to_id), ensure_ascii=False),
            generated_at=now,
        ))
        saved += 1


def _resolve_source_ids(item: dict, seq_to_id: dict[int, int]) -> list[int]:
    """把本地匹配出的转写句序号换算成真实主键；兼容直接给出 id 的情况。"""
    ids: list[int] = []
    for seq in item.get("source_transcript_seqs") or []:
        resolved = seq_to_id.get(int(seq))
        if resolved is not None:
            ids.append(resolved)
    if not ids:
        for value in item.get("source_transcript_ids") or []:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
    return ids


def _save_summary(db: Session, task_id: int, course_id: int, summary: dict, now: datetime, lecture_id: int | None = None) -> None:
    if not isinstance(summary, dict) or not any(
        summary.get(key) for key in ("overview", "chapter_points", "key_details", "review_hints")
    ):
        logger.warning("[persist] 课程总结为空，跳过写入（前端按“尚未生成”展示）")
        return

    db.add(Summary(
        task_id=task_id,
        course_id=course_id,
        lecture_id=lecture_id,
        overview=summary.get("overview"),
        chapter_points=json.dumps(summary.get("chapter_points", []), ensure_ascii=False),
        key_details=json.dumps(summary.get("key_details", []), ensure_ascii=False),
        review_hints=json.dumps(summary.get("review_hints", []), ensure_ascii=False),
        ai_generated=True,
        source_model=settings.siliconflow_model,
        generated_at=now,
    ))


def _save_mindmap(
    db: Session,
    task_id: int,
    course_id: int,
    mindmap: dict,
    course: Course | None,
    now: datetime,
    lecture_id: int | None = None,
) -> None:
    if not isinstance(mindmap, dict) or not mindmap.get("nodes"):
        logger.warning("[persist] 思维导图为空，跳过写入（前端按“尚未生成”展示）")
        return

    db.add(Mindmap(
        task_id=task_id,
        course_id=course_id,
        lecture_id=lecture_id,
        root_topic=str(mindmap.get("root_topic") or (course.title if course else ""))[:255],
        nodes=json.dumps(mindmap.get("nodes", []), ensure_ascii=False),
        ai_generated=True,
        source_model=settings.siliconflow_model,
        generated_at=now,
    ))
