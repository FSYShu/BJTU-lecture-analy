"""Step 3：音频提取 + 基础降噪（ffmpeg）。"""
from pathlib import Path

from app.config import settings


def extract_and_denoise(video_path: str, task_id: int) -> str:
    """从视频提取音频：16kHz 单声道 PCM WAV + afftdn 频域降噪（硅基流动 ASR 要求）。"""
    out_dir = Path(settings.audio_cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{task_id}.wav"

    import ffmpeg

    (
        ffmpeg.input(video_path)
        .audio.filter("afftdn")
        .output(str(out_path), acodec="pcm_s16le", ar="16000", ac=1)
        .overwrite_output()
        .run(quiet=True)
    )
    return str(out_path)
