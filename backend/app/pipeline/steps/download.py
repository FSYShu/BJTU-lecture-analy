"""Step 2：视频下载。支持 MP4/FLV/HLS。"""
from pathlib import Path

from app.config import settings
from app.pipeline.retry import with_retry

_MIN_FREE_BYTES = 5 * 1024**3  # 下载前至少预留 5GB 可用空间


def _ensure_free_space(out_dir: Path) -> None:
    """下载前检查磁盘可用空间，不足则抛 OSError 触发重试/失败。"""
    import shutil

    free = shutil.disk_usage(out_dir).free
    if free < _MIN_FREE_BYTES:
        raise OSError(f"磁盘可用空间不足：{free // 1024**3}GB < {_MIN_FREE_BYTES // 1024**3}GB")


@with_retry(max_attempts=2, exceptions=(TimeoutError, OSError), step_name="download")
def download_video(url: str, task_id: int) -> str:
    """用 ffmpeg 拉流下载视频 → mp4。

    HLS/MP4/FLV 统一走 ffmpeg `-c copy`：HLS 自动合并 .ts 分片，MP4/FLV 直接 remux。
    MVP 优先教师流 teaStreamHlsUrl。流地址可能有时效性，失败抛 OSError 由 with_retry 退避重试。
    """
    if not url:
        raise ValueError("视频地址为空，无法下载")

    out_dir = Path(settings.video_cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{task_id}.mp4"
    _ensure_free_space(out_dir)

    import ffmpeg

    try:
        (
            ffmpeg.input(url, protocol_whitelist="https,http,tcp,tls")
            .output(str(out_path), codec="copy")
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        stderr = (exc.stderr or b"").decode(errors="ignore")
        raise OSError(f"视频下载失败：{stderr[-500:]}") from exc
    return str(out_path)

@with_retry(max_attempts=2, exceptions=(TimeoutError, OSError), step_name="download_audio")
def download_audio_from_url(url: str, task_id: int) -> str:
    """直接从 HLS/MP4 URL 提取音频 → 16kHz 单声道 WAV + afftdn 降噪。

    跳过完整视频下载，大幅减少 I/O 和磁盘占用（音频通常比视频小 ~20 倍）。
    等价于合并 download_video + extract_and_denoise 两步。
    """
    if not url:
        raise ValueError("视频地址为空，无法提取音频")

    out_dir = Path(settings.audio_cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{task_id}.wav"

    import ffmpeg

    try:
        (
            ffmpeg.input(url, protocol_whitelist="https,http,tcp,tls")
            .audio.filter("afftdn")
            .output(str(out_path), acodec="pcm_s16le", ar="16000", ac=1)
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        stderr = (exc.stderr or b"").decode(errors="ignore")
        raise OSError(f"音频提取失败：{stderr[-500:]}") from exc
    return str(out_path)
