"""路由聚合。"""
from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    courses,
    health,
    keypoints,
    mindmaps,
    platform,
    summaries,
    tasks,
    transcripts,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(courses.router, prefix="/courses", tags=["courses"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(transcripts.router, prefix="/courses", tags=["transcripts"])
api_router.include_router(keypoints.router, prefix="/courses", tags=["keypoints"])
api_router.include_router(summaries.router, prefix="/courses", tags=["summaries"])
api_router.include_router(mindmaps.router, prefix="/courses", tags=["mindmaps"])
api_router.include_router(platform.router, prefix="/platform", tags=["platform"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])