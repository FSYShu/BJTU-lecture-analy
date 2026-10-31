"""按课次回放查询 AI 解析结果。每节回放对应独立的解析。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_lecture_access
from app.db.models import Keypoint, Lecture, Mindmap, Summary, Transcript
from app.db.session import get_db
from app.schemas.keypoint import KeypointOut
from app.schemas.mindmap import MindmapOut
from app.schemas.overview import LectureOverview, TranscriptMeta
from app.schemas.summary import SummaryOut
from app.schemas.transcript import TranscriptOut
from app.services import task_service

router = APIRouter()


@router.get("/{lecture_id}/transcripts", response_model=list[TranscriptOut])
def list_transcripts(
    lecture_id: int,
    _lecture: Lecture = Depends(require_lecture_access),
    db: Session = Depends(get_db),
) -> list[Transcript]:
    stmt = select(Transcript).where(Transcript.lecture_id == lecture_id).order_by(Transcript.start_sec)
    return list(db.execute(stmt).scalars())


@router.get("/{lecture_id}/keypoints", response_model=list[KeypointOut])
def list_keypoints(
    lecture_id: int,
    _lecture: Lecture = Depends(require_lecture_access),
    db: Session = Depends(get_db),
) -> list[Keypoint]:
    stmt = select(Keypoint).where(Keypoint.lecture_id == lecture_id).order_by(Keypoint.timestamp_sec)
    return list(db.execute(stmt).scalars())


@router.get("/{lecture_id}/summary", response_model=SummaryOut)
def get_summary(
    lecture_id: int,
    _lecture: Lecture = Depends(require_lecture_access),
    db: Session = Depends(get_db),
) -> Summary:
    stmt = select(Summary).where(Summary.lecture_id == lecture_id).order_by(Summary.generated_at.desc())
    summary = db.execute(stmt).scalars().first()
    if not summary:
        raise HTTPException(404, "课程总结尚未生成")
    return summary


@router.get("/{lecture_id}/mindmap", response_model=MindmapOut)
def get_mindmap(
    lecture_id: int,
    _lecture: Lecture = Depends(require_lecture_access),
    db: Session = Depends(get_db),
) -> Mindmap:
    stmt = select(Mindmap).where(Mindmap.lecture_id == lecture_id).order_by(Mindmap.generated_at.desc())
    mindmap = db.execute(stmt).scalars().first()
    if not mindmap:
        raise HTTPException(404, "思维导图尚未生成")
    return mindmap


@router.get("/{lecture_id}/overview", response_model=LectureOverview)
def get_overview(
    lecture_id: int,
    _lecture: Lecture = Depends(require_lecture_access),
    db: Session = Depends(get_db),
) -> LectureOverview:
    """一次返回首屏所需的全部解析结果（docs/11 流量优化 F4）。

    替代前端进入详情页时的 4 次往返（重点 / 总结 / 导图 / 最新任务）。
    未生成的部分返回 ``null`` 而不是 404：解析可能只完成了一半，
    首屏仍然要能把已生成的结果渲染出来。
    """
    keypoints = list(
        db.execute(
            select(Keypoint)
            .where(Keypoint.lecture_id == lecture_id)
            .order_by(Keypoint.timestamp_sec)
        ).scalars()
    )

    summary = db.execute(
        select(Summary)
        .where(Summary.lecture_id == lecture_id)
        .order_by(Summary.generated_at.desc())
    ).scalars().first()
    mindmap = db.execute(
        select(Mindmap)
        .where(Mindmap.lecture_id == lecture_id)
        .order_by(Mindmap.generated_at.desc())
    ).scalars().first()

    total = db.scalar(
        select(func.count()).select_from(Transcript).where(Transcript.lecture_id == lecture_id)
    ) or 0
    first = db.execute(
        select(Transcript).where(Transcript.lecture_id == lecture_id)
        .order_by(Transcript.start_sec).limit(1)
    ).scalars().first()
    last = db.execute(
        select(Transcript).where(Transcript.lecture_id == lecture_id)
        .order_by(Transcript.start_sec.desc()).limit(1)
    ).scalars().first()

    return LectureOverview(
        lecture_id=lecture_id,
        keypoints=keypoints,
        summary=summary,
        mindmap=mindmap,
        transcript_meta=TranscriptMeta(total=total, first=first, last=last),
        task=task_service.get_latest_task_by_lecture(db, lecture_id),
    )