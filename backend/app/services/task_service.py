"""任务服务。P0-02/08，失败重试。"""
from loguru import logger
from sqlalchemy.orm import Session

from app.db.models import Course, ParseTask
from app.db.models.task import TASK_STATUSES


def ensure_parse_ready(course: Course) -> None:
    """建任务前的配置前置校验（docs/09 A4-2）。

    缺凭证时立刻返回可读错误，而不是等流水线跑到 ASR/LLM 步骤才失败——
    那时任务已创建、视频可能已下载，浪费磁盘与时间。
    """
    from app.config import settings
    from app.core.exceptions import AppError

    missing: list[str] = []
    if not settings.siliconflow_api_key:
        missing.append("SILICONFLOW_API_KEY（ASR 与 LLM 共用）")
    if course.source == "platform":
        if not settings.platform_base_url:
            missing.append("PLATFORM_BASE_URL")
        if not (settings.platform_username and settings.platform_password):
            missing.append(
                "PLATFORM_USERNAME / PLATFORM_PASSWORD"
                "（后台解析需自动登录课程平台；也可改用人工导入课程再解析）"
            )
    if missing:
        raise AppError("AI_CREDENTIALS_MISSING", "解析任务缺少必要配置：" + "、".join(missing), 400)

    if not (course.video_url or "").strip():
        raise AppError("VIDEO_URL_MISSING", "课程缺少视频地址，无法开始解析", 400)


def create_task(db: Session, course_id: int, user_id: int) -> ParseTask:
    task = ParseTask(course_id=course_id, initiated_by=user_id, status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def retry_task(db: Session, failed_task_id: int, user_id: int) -> ParseTask:
    """失败任务重试：新建任务并指向父任务，同时带上已下载的视频/音频缓存。

    缓存路径带到新任务后，``orchestrator`` 会跳过 Step 2/3，
    并复用父任务已落库的解析结果，避免重复消耗 ASR/LLM 额度（docs/04:115）。
    """
    original = db.get(ParseTask, failed_task_id)
    if not original or original.status != "failed":
        from app.core.exceptions import AppError
        raise AppError("TASK_NOT_RETRYABLE", "仅失败任务可重试", 422)
    new_task = ParseTask(
        course_id=original.course_id,
        initiated_by=user_id,
        status="queued",
        retry_count=original.retry_count + 1,
        parent_task_id=original.id,
        video_cache_path=original.video_cache_path,
        audio_cache_path=original.audio_cache_path,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task


def get_latest_task_by_course(db: Session, course_id: int) -> ParseTask | None:
    """按课程查最新一条解析任务（用于详情页展示进度）。"""
    return (
        db.query(ParseTask)
        .filter(ParseTask.course_id == course_id)
        .order_by(ParseTask.id.desc())
        .first()
    )


def update_status(db: Session, task_id: int, status: str, progress: int | None = None, current_step: str | None = None) -> None:
    """更新任务状态机。

    状态取值必须落在 ``TASK_STATUSES``（docs/03:76）；非法值只告警、不落库，
    避免状态机出现文档之外的值导致前端无法匹配进度展示。
    """
    if status not in TASK_STATUSES:
        logger.warning("[task={}] 非法任务状态被忽略：{}（允许值：{}）",
                       task_id, status, "/".join(TASK_STATUSES))
        return

    task = db.get(ParseTask, task_id)
    if not task:
        return
    task.status = status
    if progress is not None:
        task.progress = max(0, min(100, int(progress)))
    if current_step:
        task.current_step = current_step
    db.commit()


def mark_failed(db: Session, task_id: int, error_code: str, error_message: str) -> None:
    from datetime import datetime, timezone
    task = db.get(ParseTask, task_id)
    if not task:
        return
    task.status = "failed"
    task.error_code = error_code
    task.error_message = error_message
    task.finished_at = datetime.now(timezone.utc)
    db.commit()
