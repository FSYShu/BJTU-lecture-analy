"""字幕查询。P0-03。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_course_access
from app.db.models import Transcript, User
from app.db.session import get_db
from app.schemas.transcript import TranscriptOut

router = APIRouter()


@router.get("/{course_id}/transcripts", response_model=list[TranscriptOut])
def list_transcripts(course_id: int, user: User = Depends(require_course_access), db: Session = Depends(get_db)) -> list[Transcript]:
    stmt = select(Transcript).where(Transcript.course_id == course_id).order_by(Transcript.start_sec)
    return list(db.execute(stmt).scalars())