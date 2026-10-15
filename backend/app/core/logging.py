"""日志配置。输出到 storage/logs，按大小轮转。"""
import sys
from pathlib import Path

from loguru import logger

from app.config import settings


def setup_logging() -> None:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(sys.stderr, level=settings.app_log_level)
    logger.add(
        log_dir / "app.log",
        level=settings.app_log_level,
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8",
        enqueue=True,
    )