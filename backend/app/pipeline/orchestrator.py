"""流水线编排。依次调度 steps，更新任务状态，失败隔离。

对应 docs/04-data-flow.md 六步数据流。
"""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.db.models import ParseTask
from app.db.session import SessionLocal
from app.services import task_service
from app.pipeline.steps import asr, audio, download, llm, metadata, persist


def run_pipeline(task_id: int) -> None:
    db: Session = SessionLocal()
    task = db.get(ParseTask, task_id)
    if not task:
        logger.error("任务 {} 不存在", task_id)
        return

    try:
        task.started_at = datetime.now(timezone.utc)
        db.commit()

        task_service.update_status(db, task_id, "downloading", 5, "metadata")
        course = metadata.fetch_metadata(db, task.course_id)

        task_service.update_status(db, task_id, "downloading", 15, "download")
        video_path = download.download_video(course.video_url, task.id)

        task_service.update_status(db, task_id, "extracting_audio", 30, "audio")
        audio_path = audio.extract_and_denoise(video_path, task.id)
        task.audio_cache_path = audio_path
        task.video_cache_path = video_path
        db.commit()

        task_service.update_status(db, task_id, "asr_running", 50, "asr")
        transcripts = asr.run_asr(audio_path, task.id)

        task_service.update_status(db, task_id, "llm_running", 75, "llm")
        keypoints, summary, mindmap = llm.run_llm(transcripts, course, task.id)

        task_service.update_status(db, task_id, "persisting", 90, "persist")
        persist.save_results(db, task_id, task.course_id, transcripts, keypoints, summary, mindmap)

        task_service.update_status(db, task_id, "succeeded", 100, "done")
        task.finished_at = datetime.now(timezone.utc)
        db.commit()

        from app.config import settings
        if settings.cleanup_audio_after_task:
            from app.core.cleanup import cleanup_audio_file
            cleanup_audio_file(audio_path)

    except Exception as exc:
        logger.exception("[task={}] 流水线失败", task_id)
        task_service.mark_failed(db, task_id, type(exc).__name__.upper(), str(exc)[:500])
    finally:
        db.close()