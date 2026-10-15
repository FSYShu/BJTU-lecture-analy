"""指数退避重试策略，并支持 HTTP 429 按 ``Retry-After`` 等待。

对应 docs/05-risk-handling.md：
- 外部 API 异常降级（ASR / 大模型 / 课程平台）
- ``API 限流/429 | retry.py 识别 429 状态码，按 Retry-After 头等待后重试``

除调用方传入的异常类型外，默认还会重试：
- ``httpx.TimeoutException`` / ``httpx.TransportError``（超时、连接重置）
- ``httpx.HTTPStatusError`` 且状态码为 429 或 5xx（4xx 中的参数/鉴权错误不重试）
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar

import httpx
from loguru import logger
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

T = TypeVar("T")

DEFAULT_EXCEPTIONS: tuple[type[Exception], ...] = (TimeoutError, RuntimeError)

_MAX_WAIT_SEC = 120.0


def _retry_after_seconds(exc: BaseException) -> float | None:
    """解析 429 响应的 ``Retry-After``（秒数或 HTTP 日期）。"""
    response = getattr(exc, "response", None)
    if response is None or getattr(response, "status_code", None) != 429:
        return None
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, min(_MAX_WAIT_SEC, float(raw)))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(raw)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        delta = (target - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, min(_MAX_WAIT_SEC, delta))
    except (TypeError, ValueError):
        return None


def _should_retry(exc: BaseException, exceptions: tuple[type[Exception], ...]) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, exceptions)


def _wait(retry_state) -> float:
    outcome = getattr(retry_state, "outcome", None)
    exc = outcome.exception() if outcome is not None else None
    if isinstance(exc, BaseException):
        after = _retry_after_seconds(exc)
        if after is not None:
            logger.warning("[retry] 命中 429，按 Retry-After 等待 {:.0f}s", after)
            return after
    return wait_exponential(multiplier=1, min=2, max=30)(retry_state)


def with_retry(
    max_attempts: int,
    exceptions: tuple[type[Exception], ...] = DEFAULT_EXCEPTIONS,
    step_name: str = "step",
) -> Callable:
    """生成重试装饰器：tenacity 指数退避，最多 ``max_attempts`` 次，保留最后一次异常。"""
    attempts = max(1, int(max_attempts))

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @retry(
            stop=stop_after_attempt(attempts),
            wait=_wait,
            retry=retry_if_exception(lambda exc: _should_retry(exc, exceptions)),
            reraise=True,
            before_sleep=lambda rs: logger.warning("[{}] 第{}次重试", step_name, rs.attempt_number),
        )
        def wrapper(*args, **kwargs) -> T:
            return func(*args, **kwargs)

        return wrapper

    return decorator
