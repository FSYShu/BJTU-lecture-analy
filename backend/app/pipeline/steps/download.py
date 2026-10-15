"""Step 2：视频下载。支持 MP4/FLV/HLS。"""
from pathlib import Path

from app.config import settings
from app.pipeline.retry import with_retry


@with_retry(max_attempts=2, exceptions=(TimeoutError, OSError), step_name="download")
def download_video(url: str, task_id: int) -> str:
    out_dir = Path(settings.video_cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{task_id}.mp4"
    # TODO: 根据 url 协议（mp4/flv/hls）选择下载策略，使用 httpx 流式下载或 ffmpeg 拉流
    # MVP 占位：实际实现需处理超时、断点、HLS 合并
    raise NotImplementedError("视频下载实现待补充：需根据 PLATFORM_VIDEO_FORMATS 分派")