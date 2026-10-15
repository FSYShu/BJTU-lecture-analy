"""Step 6：持久化结构化结果。事务写入，失败回滚但原任务记录保留。"""
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Course, Keypoint, Mindmap, Summary, Transcript


def save_results(
    db: Session,
    task_id: int,
    course_id: int,
    transcripts: list[dict],
    keypoints: list[dict],
    summary: dict,
    mindmap: dict,
) -> None:
    course = db.get(Course, course_id)
    duration = course.duration_sec or 0
    now = datetime.now(timezone.utc)

    for i, t in enumerate(transcripts):
        db.add(Transcript(
            task_id=task_id, course_id=course_id, seq_index=i,
            text=t["text"], start_sec=t["start_sec"], end_sec=t["end_sec"],
            ai_generated=True, source_model="xfyun-asr", generated_at=now,
        ))

    for i, k in enumerate(keypoints):
        ts = k.get("timestamp_sec", 0)
        if duration and (ts < 0 or ts > duration):
            continue
        db.add(Keypoint(
            task_id=task_id, course_id=course_id, seq_index=i,
            title=k["title"], category=k.get("category"), summary=k.get("summary"),
            timestamp_sec=ts, ai_generated=True,
            source_model=settings.siliconflow_model, generated_at=now,
            source_transcript_ids=json.dumps(k.get("source_transcript_ids", [])),
        ))

    db.add(Summary(
        task_id=task_id, course_id=course_id,
        overview=summary.get("overview"),
        chapter_points=json.dumps(summary.get("chapter_points", []), ensure_ascii=False),
        key_details=json.dumps(summary.get("key_details", []), ensure_ascii=False),
        review_hints=json.dumps(summary.get("review_hints", []), ensure_ascii=False),
        ai_generated=True, source_model=settings.siliconflow_model, generated_at=now,
    ))

    db.add(Mindmap(
        task_id=task_id, course_id=course_id,
        root_topic=mindmap.get("root_topic", course.title if course else ""),
        nodes=json.dumps(mindmap.get("nodes", []), ensure_ascii=False),
        ai_generated=True, source_model=settings.siliconflow_model, generated_at=now,
    ))

    db.commit()