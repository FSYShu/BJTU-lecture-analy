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
        logger.error("[task={}] 任务不存在", task_id)
        db.close()
        return

    deadline = time.monotonic() + max(60, settings.task_total_timeout)
    try:
        task.started_at = datetime.now(timezone.utc)
        db.commit()

        # ---------- Step 1 元数据（含平台字幕/知识点预取） ----------
        _ensure_deadline(deadline)
        _check_cancelled(db, task_id)
        task_service.update_status(db, task_id, "downloading", 5, "metadata")
        logger.info("[task={}] Step 1/6 元数据", task_id)
        ctx = metadata.fetch_metadata(db, task.course_id)
        course = ctx.course
        reused = _load_parent_results(db, task)

        # ---------- 已有字幕则跳过音频提取与 ASR ----------
        db_transcripts: list[dict] = []
        seq_to_id: dict[int, int] = {}
        if task.lecture_id and not reused["transcripts"]:
            rows = (
                db.query(Transcript)
                .filter(Transcript.lecture_id == task.lecture_id)
                .order_by(Transcript.start_sec)
                .all()
            )
            if rows:
                db_transcripts = [_transcript_to_dict(r) for r in rows]
                seq_to_id = {i: r.id for i, r in enumerate(rows)}
                logger.info("[task={}] 已有字幕 {} 句，跳过音频提取与 ASR", task_id, len(rows))

        audio_path: str | None = None
        if db_transcripts:
            transcripts = db_transcripts
            task_service.update_status(db, task_id, "asr_running", 50, "asr")
        else:
            # ---------- Step 2+3 直接从 URL 提取音频（跳过完整视频下载） ----------
            _check_cancelled(db, task_id)
            task_service.update_status(db, task_id, "downloading", 10, "download")
            audio_path = _reuse_cached(task.audio_cache_path)
            if not audio_path:
                task_service.update_status(db, task_id, "extracting_audio", 12, "audio")
                logger.info("[task={}] Step 2/6 提取音频（ffmpeg 16kHz WAV）", task_id)

                def _on_audio_progress(out_time: str, speed: str, size_kb: int):
                    _check_cancelled(db, task_id)
                    detail = f"audio|{out_time}|{speed}x|{size_kb}KB"
                    task_service.update_status(db, task_id, "extracting_audio", None, detail)

                audio_path = download.download_audio_from_url(
                    course.video_url, task.id, progress_callback=_on_audio_progress,
                )
                task.audio_cache_path = audio_path
                db.commit()
                audio_mb = Path(audio_path).stat().st_size / 1024 / 1024
                logger.info("[task={}] 音频提取完成：{} ({:.1f}MB)", task_id, audio_path, audio_mb)
            task_service.update_status(db, task_id, "extracting_audio", 20, "audio")

            # ---------- Step 4 转写：优先平台 VTT，否则 ASR ----------
            _ensure_deadline(deadline)
            _check_cancelled(db, task_id)
            task_service.update_status(db, task_id, "asr_running", 25, "asr")
            if reused["transcripts"]:
                logger.info("[task={}] Step 3/6 转写（复用父任务）", task_id)
            transcripts = reused["transcripts"] or _resolve_transcripts(ctx, audio_path, task_id, db, task_id)
            logger.info("[task={}] 转写完成：{} 句", task_id, len(transcripts))
            task_service.update_status(db, task_id, "asr_running", 50, "asr")

        # ---------- 转写完成立即落库 ----------
        if not reused["complete"] and not db_transcripts:
            seq_to_id = persist.save_transcripts(db, task_id, task.course_id, transcripts, lecture_id=task.lecture_id)
            logger.info("[task={}] 转写已落库：{} 句", task_id, len(transcripts))

        # ---------- Step 5 大模型语义解析（每子任务完成即落库） ----------
        _ensure_deadline(deadline)
        _check_cancelled(db, task_id)
        task_service.update_status(db, task_id, "llm_running", 55, "llm")
        failures: list[str] = []
        if reused["complete"]:
            logger.info("[task={}] Step 4/6 LLM（复用父任务 {}）", task_id, task.parent_task_id)
            _ensure_deadline(deadline)
            _check_cancelled(db, task_id)
            task_service.update_status(db, task_id, "persisting", 90, "persist")
            kp = llm.link_source_transcripts(reused["keypoints"], transcripts)
            kp = platform_assets.align_keypoints(kp, ctx.zsd_items)
            persist.save_results(db, task_id, task.course_id, transcripts, kp, reused["summary"], reused["mindmap"], lecture_id=task.lecture_id)
        else:
            logger.info("[task={}] Step 4/6 LLM 语义解析", task_id)

            def _on_llm_result(key: str, result: Any) -> None:
                if key == "keypoints":
                    kp = llm.link_source_transcripts(result, transcripts)
                    kp = platform_assets.align_keypoints(kp, ctx.zsd_items)
                    persist.save_keypoints(db, task_id, task.course_id, kp, seq_to_id, lecture_id=task.lecture_id)
                    task_service.update_status(db, task_id, "llm_running", None, "llm|keypoints")
                    logger.info("[task={}] 重点已落库：{} 条", task_id, len(kp))
                elif key == "summary":
                    persist.save_summary(db, task_id, task.course_id, result, lecture_id=task.lecture_id)
                    task_service.update_status(db, task_id, "llm_running", None, "llm|summary")
                    logger.info("[task={}] 总结已落库", task_id)
                elif key == "mindmap":
                    persist.save_mindmap(db, task_id, task.course_id, result, lecture_id=task.lecture_id)
                    task_service.update_status(db, task_id, "llm_running", None, "llm|mindmap")
                    logger.info("[task={}] 导图已落库", task_id)

            _, _, _, failures = llm.run_llm(
                transcripts, course, task.id,
                cancel_check=lambda: _check_cancelled(db, task_id),
                on_result=_on_llm_result,
            )
        logger.info("[task={}] Step 6/6 完成", task_id)

        if failures:
            task_service.mark_failed(db, task_id, LLM_PARTIAL_FAIL,
                                     "部分解析失败：" + "；".join(failures)[:400])
            logger.warning("[task={}] 部分解析失败，已完成的结果已落库：{}", task_id, failures)
            return

        _check_cancelled(db, task_id)
        task_service.update_status(db, task_id, "succeeded", 100, "done")
        task.finished_at = datetime.now(timezone.utc)
        db.commit()

        if settings.cleanup_audio_after_task and audio_path:
            from app.core.cleanup import cleanup_audio_file
            cleanup_audio_file(audio_path)

    except Exception as exc:  # noqa: BLE001 - 失败隔离：只影响本任务
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.warning("[task={}] 回滚失败，继续标记任务状态", task_id)
        current = db.get(ParseTask, task_id)
        if current and current.status == "failed" and current.error_code == "CANCELLED":
            logger.info("[task={}] 用户取消", task_id)
        else:
            logger.exception("[task={}] 流水线失败", task_id)
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


def _check_cancelled(db: Session, task_id: int) -> None:
    """用户取消后任务被标记为 failed+CANCELLED，流水线在阶段切换处主动检查并退出。"""
    task = db.get(ParseTask, task_id)
    if task and task.status == "failed" and task.error_code == "CANCELLED":
        raise StepError("CANCELLED", "用户取消", step="orchestrator")


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


def _resolve_transcripts(ctx: CourseContext, audio_path: str, task_id: int, db: Session = None, tid: int = None) -> list[dict]:
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

    def on_progress(current, total, msg):
        _check_cancelled(db, tid)
        pct = 25 + int(25 * current / max(1, total))
        if db and tid:
            detail = f"asr|{current}/{total}|{msg or ''}"
            task_service.update_status(db, tid, "asr_running", pct, detail)
        logger.info("[task={}] ASR 进度 {}/{} ({}%)", tid, current, total, pct)

    return asr.run_asr(audio_path, task_id, on_progress)


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
