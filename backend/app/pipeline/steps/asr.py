"""Step 4：调用讯飞 ASR 转写，输出句级时间戳。"""
from app.config import settings
from app.integrations import xfyun_asr
from app.pipeline.retry import with_retry


@with_retry(
    max_attempts=settings.xfyun_asr_max_retry,
    exceptions=(TimeoutError, RuntimeError),
    step_name="asr",
)
def run_asr(audio_path: str, task_id: int) -> list[dict]:
    return xfyun_asr.transcribe(audio_path)