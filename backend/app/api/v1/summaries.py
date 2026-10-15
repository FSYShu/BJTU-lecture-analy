"""课程总结查询。P0-05。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_course_access
from app.db.models import Summary, User
from app.db.session import get_db
from app.schemas.summary import SummaryOut

router = APIRouter()


@router.get("/{course_id}/summary", response_model=SummaryOut)
def get_summary(course_id: int, user: User = Depends(require_course_access), db: Session = Depends(get_db)) -> Summary:
    stmt = select(Summary).where(Summary.course_id == course_id).order_by(Summary.generated_at.desc())
    summary = db.execute(stmt).scalars().first()
    if not summary:
        raise HTTPException(404, "课程总结尚未生成")
    return summary