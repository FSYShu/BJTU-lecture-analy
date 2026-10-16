"""Step 2：视频下载。支持 MP4/FLV/HLS。"""
import subprocess
import time
from pathlib import Path

from loguru import logger

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
            ffmpeg.input(
                url,
                protocol_whitelist="https,http,tcp,tls",
                rw_timeout=30_000_000,
                reconnect=1,
                reconnect_streamed=1,
                reconnect_delay_max=5,
                tls_verify=0,
            )
            .output(str(out_path), codec="copy")
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        stderr = (exc.stderr or b"").decode(errors="ignore")
        raise OSError(f"视频下载失败：{stderr[-500:]}") from exc
    return str(out_path)

@with_retry(max_attempts=2, exceptions=(TimeoutError, OSError), step_name="download_audio")
def download_audio_from_url(url: str, task_id: int, progress_callback=None) -> str:
    """直接从 HLS/MP4 URL 提取音频 → 16kHz 单声道 WAV。

    跳过完整视频下载和降噪处理，大幅减少 I/O 和 CPU 占用。
    对 HLS 流添加 rw_timeout（30s 无数据即退出）和自动重连，防止网络抖动卡死。
    用 subprocess 直接调 ffmpeg + -progress pipe:2 实时输出进度日志。
    progress_callback(out_time: str, speed: str, size_kb: int) 用于上报进度。
    """
    if not url:
        raise ValueError("视频地址为空，无法提取音频")

    out_dir = Path(settings.audio_cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{task_id}.wav"

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",
        "-y",
        "-protocol_whitelist", "https,http,tcp,tls",
        "-rw_timeout", "30000000",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-tls_verify", "0",
        "-http_persistent", "1",
        "-i", url,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-progress", "pipe:2",
        str(out_path),
    ]

    logger.info("[task={}] 启动 ffmpeg 提取音频", task_id)

    try:
        proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        last_log = time.monotonic()
        progress_data: dict[str, str] = {}
        for line in proc.stderr:
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, _, value = line.partition("=")
            progress_data[key] = value
            if key == "progress":
                now = time.monotonic()
                if now - last_log >= 5:
                    out_time = progress_data.get("out_time", "N/A")
                    speed = progress_data.get("speed", "N/A")
                    total_size = int(progress_data.get("total_size", 0)) // 1024
                    logger.info(
                        "[task={}] ffmpeg 进度: time={} speed={}x size={}KB",
                        task_id, out_time, speed, total_size,
                    )
                    if progress_callback:
                        try:
                            progress_callback(out_time, speed, total_size)
                        except Exception:  # noqa: BLE001
                            pass
                    last_log = now
                progress_data = {}
        proc.wait()
        if proc.returncode != 0:
            raise OSError(f"音频提取失败，ffmpeg 返回码 {proc.returncode}")
    except FileNotFoundError as exc:
        raise OSError("ffmpeg 未安装") from exc

    return str(out_path)
