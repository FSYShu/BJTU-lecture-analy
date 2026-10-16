"""视频/音频缓存自动清理策略。

对应 docs/05-risk-handling.md 资源清理；docs/04-data-flow.md 缓存清理。
"""
import time
from pathlib import Path

from loguru import logger

from app.config import settings


def cleanup_dir(dir_path: str, retention_days: int) -> int:
    target = Path(dir_path)
    if not target.exists():
        return 0
    threshold = time.time() - retention_days * 86400
    removed = 0
    for f in target.glob("*"):
        if f.name == ".gitkeep" or not f.is_file():
            continue
        try:
            if f.stat().st_mtime < threshold:
                f.unlink()
                removed += 1
        except OSError as e:
            logger.warning("[cleanup] 清理失败 {}: {}", f, e)
    return removed


def cleanup_audio_file(audio_path: str) -> None:
    if not audio_path:
        return
    p = Path(audio_path)
    if p.exists():
        try:
            p.unlink()
            logger.info("[cleanup] 已清理中间音频: {}", p)
        except OSError as e:
            logger.warning("[cleanup] 清理音频失败 {}: {}", p, e)


def run_scheduled_cleanup() -> dict[str, int]:
    days = settings.cache_retention_days
    return {
        "videos": cleanup_dir(settings.video_cache_dir, days),
        "audios": cleanup_dir(settings.audio_cache_dir, days),
        "exports": cleanup_dir(settings.export_dir, days),
    }