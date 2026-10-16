"""ORM 模型聚合。对应 docs/03-data-model.md。"""
from app.db.models.authorization import CourseAuthorization
from app.db.models.course import Course
from app.db.models.keypoint import Keypoint
from app.db.models.lecture import Lecture
from app.db.models.mindmap import Mindmap
from app.db.models.summary import Summary
from app.db.models.task import ParseTask
from app.db.models.transcript import Transcript
from app.db.models.user import User

__all__ = [
    "User",
    "Course",
    "CourseAuthorization",
    "Lecture",
    "ParseTask",
    "Transcript",
    "Keypoint",
    "Summary",
    "Mindmap",
]