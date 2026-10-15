"""重点时间点查询。P0-04。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_course_access
from app.db.models import Keypoint, User
from app.db.session import get_db
from app.schemas.keypoint import KeypointOut

router = APIRouter()


@router.get("/{course_id}/keypoints", response_model=list[KeypointOut])
def list_keypoints(course_id: int, user: User = Depends(require_course_access), db: Session = Depends(get_db)) -> list[Keypoint]:
    stmt = select(Keypoint).where(Keypoint.course_id == course_id).order_by(Keypoint.timestamp_sec)
    return list(db.execute(stmt).scalars())