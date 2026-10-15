"""流水线异常：带固定错误码，写入 ``parse_tasks.error_code``。

对应 docs/03-data-model.md:79 与 docs/04-data-flow.md 各步骤的错误码约定
（``ASR_TIMEOUT`` / ``ASR_ERROR`` / ``LLM_TIMEOUT`` / ``LLM_ERROR`` / ``PERSIST_FAIL`` 等）。
"""
from __future__ import annotations


class StepError(Exception):
    """流水线步骤失败。``code`` 直接作为任务的 error_code 落库。"""

    def __init__(self, code: str, message: str, *, step: str | None = None) -> None:
        self.code = code
        self.step = step
        super().__init__(message)

    def __str__(self) -> str:
        return f"[{self.code}] {super().__str__()}"


# 非 StepError 异常的兜底映射（保持 docs 中的固定错误码口径）
_FALLBACK_CODES: dict[str, str] = {
    "TimeoutError": "TIMEOUT",
    "OSError": "IO_ERROR",
    "ValueError": "INVALID_INPUT",
    "HTTPStatusError": "EXTERNAL_API_ERROR",
}


def error_code_for(exc: BaseException, default: str = "PIPELINE_ERROR") -> str:
    """把任意异常翻译成错误码：优先用 StepError.code，其余按异常类名映射。"""
    if isinstance(exc, StepError):
        return exc.code
    return _FALLBACK_CODES.get(type(exc).__name__, default)


def error_message_for(exc: BaseException) -> str:
    return str(exc)[:500]
