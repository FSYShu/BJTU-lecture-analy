"""Step 3：音频提取 + 基础降噪（ffmpeg）。"""
from pathlib import Path

from app.config import settings


def extract_and_denoise(video_path: str, task_id: int) -> str:
    out_dir = Path(settings.audio_cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{task_id}.wav"
    # TODO: 调用 ffmpeg 抽取人声轨 + 基础降噪（afftdn/highpass）输出 16kHz 单声道 wav
    # ffmpeg-python: ffmpeg.input(video_path).output(out_path, ar=16000, ac=1, af='afftdn').run()
    raise NotImplementedError("音频提取降噪实现待补充：调用 ffmpeg-python")