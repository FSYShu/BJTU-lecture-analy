"""Step 4：调用硅基流动 ASR 转写，输出句级时间戳（A1）。"""
from __future__ import annotations

import httpx

from app.config import settings
from app.integrations import siliconflow_asr
from app.pipeline.errors import StepError
from app.pipeline.retry import with_retry


@with_retry(
    max_attempts=settings.siliconflow_asr_max_retry,
    exceptions=(TimeoutError, RuntimeError),
    step_name="asr",
)
def _transcribe(audio_path: str) -> list[dict]:
    return siliconflow_asr.transcribe(audio_path)


def run_asr(audio_path: str, task_id: int) -> list[dict]:
    """ASR 步骤入口。

    重试由 ``_transcribe`` 的装饰器完成（指数退避 + 429 Retry-After），
    重试耗尽后在这里翻译成 docs/03:79 约定的固定错误码：
    ``ASR_TIMEOUT`` / ``ASR_ERROR``。
    """
    try:
        return _transcribe(audio_path)
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise StepError("ASR_TIMEOUT", f"ASR 转写超时：{exc}", step="asr") from exc
    except StepError:
        raise
    except Exception as exc:
        raise StepError("ASR_ERROR", f"ASR 转写失败：{exc}", step="asr") from exc
