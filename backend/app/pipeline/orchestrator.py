"""流水线编排。依次调度 steps，更新任务状态，失败隔离（A3/A4）。

对应 docs/04-data-flow.md 六步数据流、docs/05-risk-handling.md 降级与重试：

- 固定错误码：步骤抛 ``StepError``，统一写入 ``parse_tasks.error_code``（docs/03:79）；
- 整任务超时：每个步骤前检查 ``TASK_TOTAL_TIMEOUT`` 预算，超时标 ``TOTAL_TIMEOUT``（docs/05:23）；
- 缓存复用：重试任务复用父任务已落库的转写/重点/总结/导图，避免重复消耗 ASR/LLM 额度（docs/04:115）；
- 平台字幕优先：平台 VTT 覆盖足够时直接用，否则走 ASR（docs/10:948）；
- 部分失败降级：LLM 部分子任务失败时仍先落库已完成的部分，再把任务标记为 failed 供重试（docs/05:10）。
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Keypoint, Mindmap, ParseTask, Summary, Transcript
from app.db.session import SessionLocal
from app.pipeline.errors import StepError, error_code_for, error_message_for
from app.pipeline.steps import asr, audio, download, llm, metadata, persist, platform_assets
from app.pipeline.steps.metadata import CourseContext
from app.services import task_service

# LLM 部分失败时的错误码（成功项已落库，任务仍为 failed 供重试）
LLM_PARTIAL_FAIL = "LLM_PARTIAL_FAIL"


def run_pipeline(task_id: int) -> None:
    db: Session = SessionLocal()
    task = db.get(ParseTask, task_id)
    if not task:
        logger.error("任务 {} 不存在", task_id)
        db.close()
        return

    deadline = time.monotonic() + max(60, settings.task_total_timeout)
    try:
        task.started_at = datetime.now(timezone.utc)
        db.commit()

        # ---------- Step 1 元数据（含平台字幕/知识点预取） ----------
        _ensure_deadline(deadline)
        task_service.update_status(db, task_id, "downloading", 5, "metadata")
        ctx = metadata.fetch_metadata(db, task.course_id)
        course = ctx.course
        reused = _load_parent_results(db, task)

        # ---------- Step 2+3 直接从 URL 提取音频（跳过完整视频下载） ----------
        task_service.update_status(db, task_id, "downloading", 15, "download")
        audio_path = _reuse_cached(task.audio_cache_path)
        if not audio_path:
            task_service.update_status(db, task_id, "extracting_audio", 25, "audio")
            audio_path = download.download_audio_from_url(course.video_url, task.id)
            task.audio_cache_path = audio_path
            db.commit()

        # ---------- Step 4 转写：优先平台 VTT，否则 ASR ----------
        _ensure_deadline(deadline)
        task_service.update_status(db, task_id, "asr_running", 50, "asr")
        transcripts = reused["transcripts"] or _resolve_transcripts(ctx, audio_path, task.id)

        # ---------- Step 5 大模型语义解析 ----------
        _ensure_deadline(deadline)
        task_service.update_status(db, task_id, "llm_running", 75, "llm")
        if reused["complete"]:
            logger.info("[task={}] 复用父任务 {} 的解析结果，跳过 LLM 调用", task_id, task.parent_task_id)
            keypoints, summary, mindmap = reused["keypoints"], reused["summary"], reused["mindmap"]
            failures: list[str] = []
        else:
            keypoints, summary, mindmap, failures = llm.run_llm(transcripts, course, task.id)

        keypoints = llm.link_source_transcripts(keypoints, transcripts)
        keypoints = platform_assets.align_keypoints(keypoints, ctx.zsd_items)

        # ---------- Step 6 持久化 ----------
        _ensure_deadline(deadline)
        task_service.update_status(db, task_id, "persisting", 90, "persist")
        persist.save_results(db, task_id, task.course_id, transcripts, keypoints, summary, mindmap)

        if failures:
            task_service.mark_failed(db, task_id, LLM_PARTIAL_FAIL,
                                     "部分解析失败：" + "；".join(failures)[:400])
            logger.warning("[task={}] 部分解析失败，已完成的结果已落库：{}", task_id, failures)
            return

        task_service.update_status(db, task_id, "succeeded", 100, "done")
        task.finished_at = datetime.now(timezone.utc)
        db.commit()

        if settings.cleanup_audio_after_task and audio_path:
            from app.core.cleanup import cleanup_audio_file
            cleanup_audio_file(audio_path)

    except Exception as exc:  # noqa: BLE001 - 失败隔离：只影响本任务
        logger.exception("[task={}] 流水线失败", task_id)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.warning("[task={}] 回滚失败，继续标记任务状态", task_id)
        task_service.mark_failed(db, task_id, error_code_for(exc), error_message_for(exc))
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 内部工具
# --------------------------------------------------------------------------- #
def _ensure_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise StepError(
            "TOTAL_TIMEOUT",
            f"任务整体超时（TASK_TOTAL_TIMEOUT={settings.task_total_timeout}s）",
            step="orchestrator",
        )


def _reuse_cached(path: str | None) -> str | None:
    """缓存文件仍存在则复用，跳过下载/音频提取（docs/04:115）。"""
    if not path:
        return None
    candidate = Path(path)
    try:
        if candidate.is_file() and candidate.stat().st_size > 0:
            logger.info("[pipeline] 复用缓存文件：{}", candidate)
            return str(candidate)
    except OSError as exc:
        logger.warning("[pipeline] 缓存文件不可用（{}），重新生成", exc)
    return None


def _resolve_transcripts(ctx: CourseContext, audio_path: str, task_id: int) -> list[dict]:
    """平台 VTT 覆盖足够时直接使用，否则调用 ASR（docs/10:948）。"""
    duration = ctx.course.duration_sec or 0
    if ctx.vtt_sentences:
        coverage = platform_assets.vtt_coverage(ctx.vtt_sentences, duration)
        if coverage >= settings.vtt_min_coverage:
            logger.info("[pipeline] 使用平台字幕 {} 句（覆盖 {:.0%}），跳过 ASR",
                        len(ctx.vtt_sentences), coverage)
            return list(ctx.vtt_sentences)
        logger.warning("[pipeline] 平台字幕覆盖仅 {:.0%}（阈值 {:.0%}），改用 ASR 生成",
                       coverage, settings.vtt_min_coverage)
    return asr.run_asr(audio_path, task_id)


def _load_parent_results(db: Session, task: ParseTask) -> dict:
    """重试任务复用父任务已落库的结果，实现"从失败步骤继续"。"""
    empty = {"transcripts": [], "keypoints": [], "summary": {}, "mindmap": {}, "complete": False}
    parent_id = task.parent_task_id
    if not parent_id:
        return empty

    transcript_rows = (
        db.query(Transcript)
        .filter(Transcript.task_id == parent_id)
        .order_by(Transcript.seq_index)
        .all()
    )
    if not transcript_rows:
        return empty

    keypoint_rows = (
        db.query(Keypoint)
        .filter(Keypoint.task_id == parent_id)
        .order_by(Keypoint.timestamp_sec)
        .all()
    )
    summary_row = (
        db.query(Summary)
        .filter(Summary.task_id == parent_id)
        .order_by(Summary.generated_at.desc())
        .first()
    )
    mindmap_row = (
        db.query(Mindmap)
        .filter(Mindmap.task_id == parent_id)
        .order_by(Mindmap.generated_at.desc())
        .first()
    )

    logger.info("[task={}] 复用父任务 {} 的结果：转写 {} 句 / 重点 {} 条 / 总结 {} / 导图 {}",
                task.id, parent_id, len(transcript_rows), len(keypoint_rows),
                bool(summary_row), bool(mindmap_row))

    return {
        "transcripts": [_transcript_to_dict(row) for row in transcript_rows],
        "keypoints": [_keypoint_to_dict(row) for row in keypoint_rows],
        "summary": _summary_to_dict(summary_row),
        "mindmap": _mindmap_to_dict(mindmap_row),
        "complete": bool(keypoint_rows and summary_row and mindmap_row),
    }


def _transcript_to_dict(row: Transcript) -> dict:
    return {
        "text": row.text,
        "start_sec": row.start_sec,
        "end_sec": row.end_sec,
        "ai_generated": row.ai_generated,
        "source_model": row.source_model,
    }


def _keypoint_to_dict(row: Keypoint) -> dict:
    return {
        "title": row.title,
        "category": row.category,
        "summary": row.summary,
        "timestamp_sec": row.timestamp_sec,
        "ai_generated": row.ai_generated,
        "source_model": row.source_model,
    }


def _summary_to_dict(row: Summary | None) -> dict:
    if row is None:
        return {}
    return {
        "overview": row.overview,
        "chapter_points": _loads(row.chapter_points),
        "key_details": _loads(row.key_details),
        "review_hints": _loads(row.review_hints),
    }


def _mindmap_to_dict(row: Mindmap | None) -> dict:
    if row is None:
        return {}
    return {"root_topic": row.root_topic, "nodes": _loads(row.nodes)}


def _loads(value: str | None) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else [parsed]
