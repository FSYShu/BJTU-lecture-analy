"""思维导图查询。P0-06。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_course_access
from app.db.models import Mindmap, User
from app.db.session import get_db
from app.schemas.mindmap import MindmapOut

router = APIRouter()


@router.get("/{course_id}/mindmap", response_model=MindmapOut)
def get_mindmap(course_id: int, user: User = Depends(require_course_access), db: Session = Depends(get_db)) -> Mindmap:
    stmt = select(Mindmap).where(Mindmap.course_id == course_id).order_by(Mindmap.generated_at.desc())
    mindmap = db.execute(stmt).scalars().first()
    if not mindmap:
        raise HTTPException(404, "思维导图尚未生成")
    return mindmap