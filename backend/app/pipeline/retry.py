"""指数退避重试策略。对应 docs/05-risk-handling.md。"""
from collections.abc import Callable
from typing import TypeVar

from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

T = TypeVar("T")


def with_retry(max_attempts: int, exceptions: tuple[type[Exception], ...], step_name: str) -> Callable:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type(exceptions),
            reraise=True,
            before_sleep=lambda rs: logger.warning("[{}] 第{}次重试", step_name, rs.attempt_number),
        )
        def wrapper(*args, **kwargs) -> T:
            return func(*args, **kwargs)
        return wrapper
    return decorator