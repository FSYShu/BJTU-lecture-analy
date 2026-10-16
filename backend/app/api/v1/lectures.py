"""按课次回放查询 AI 解析结果。每节回放对应独立的解析。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_lecture_access
from app.db.models import Keypoint, Lecture, Mindmap, Summary, Transcript
from app.db.session import get_db
from app.schemas.keypoint import KeypointOut
from app.schemas.mindmap import MindmapOut
from app.schemas.summary import SummaryOut
from app.schemas.transcript import TranscriptOut

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