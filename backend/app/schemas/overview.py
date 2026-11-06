"""课次解析结果聚合 schema（docs/11 流量优化 F4）。

前端进入课程详情时原本要分别请求 transcripts / keypoints / summary / mindmap /
latest-task，聚合端点把它们压成一次往返；全量转写仍走分页接口按需拉取。
"""
from pydantic import BaseModel

from app.schemas.keypoint import KeypointOut
from app.schemas.mindmap import MindmapOut
from app.schemas.summary import SummaryOut
from app.schemas.task import TaskOut
from app.schemas.transcript import TranscriptOut


class TranscriptMeta(BaseModel):
    """转写概览：总句数 + 首末句，避免为了首屏把整份转写拉下来。"""

    total: int = 0
    first: TranscriptOut | None = None
    last: TranscriptOut | None = None


class LectureOverview(BaseModel):
    lecture_id: int
    keypoints: list[KeypointOut] = []
    summary: SummaryOut | None = None
    mindmap: MindmapOut | None = None
    transcript_meta: TranscriptMeta
    task: TaskOut | None = None
