"""硅基流动 HTTP 连接复用：进程内单例 ``httpx.Client`` + 连接池。

为什么要复用（P0「httpx 客户端复用」）：

- 原来每次 ``_chat`` 都 ``with httpx.Client(...)``：新建连接池、请求完再关闭，
  下一次调用必须重新做 TCP + TLS 握手。一次解析任务要发
  「3 个子任务 × N 个分段」次 LLM 请求，ASR 还要上传多个分片，
  握手与连接建立的开销会直接叠加到端到端时延上。
- 复用同一个 Client 后，LLM 与 ASR 共享 keep-alive 连接；连接总数由
  ``SILICONFLOW_HTTP_MAX_CONNECTIONS`` 统一封顶，并发被放大时也不会打爆对端限流。

线程安全：``httpx.Client``（同步）内部连接池带锁，多个线程并发调用 ``post()`` 是常规用法，
因此本模块只把关「单例创建 / 关闭」这一层；若部署环境对共享实例有疑虑，把
``SILICONFLOW_LLM_TASK_WORKERS`` / ``SILICONFLOW_LLM_WORKERS`` 设为 1 即退化为串行。
"""
from __future__ import annotations

import atexit
import threading

import httpx
from loguru import logger

from app.config import settings

_lock = threading.Lock()
_client: httpx.Client | None = None


def get_client() -> httpx.Client:
    """返回进程内共享的硅基流动客户端（首次调用时惰性创建）。

    超时按请求传入（LLM 与 ASR 的超时不同），这里只配置连接池与兜底超时，
    因此同一个 Client 可以同时服务两类调用。
    """
    global _client
    client = _client
    if client is not None:
        return client
    with _lock:
        if _client is None:
            _client = _build()
            logger.info(
                "[http] 创建共享 httpx 客户端：max_connections={} max_keepalive={} keepalive_expiry={}s",
                settings.siliconflow_http_max_connections,
                settings.siliconflow_http_max_keepalive,
                settings.siliconflow_http_keepalive_expiry,
            )
        return _client


def _build() -> httpx.Client:
    limits = httpx.Limits(
        max_connections=max(1, int(settings.siliconflow_http_max_connections)),
        max_keepalive_connections=max(1, int(settings.siliconflow_http_max_keepalive)),
        keepalive_expiry=max(1.0, float(settings.siliconflow_http_keepalive_expiry)),
    )
    return httpx.Client(
        timeout=httpx.Timeout(settings.siliconflow_timeout, connect=10.0),
        limits=limits,
        headers={"User-Agent": f"{settings.app_name}/1.0"},
    )


def close() -> None:
    """关闭并丢弃共享客户端（应用退出、测试清理）。

    关闭后再次调用 ``get_client()`` 会重新创建，因此本函数可重复调用。
    """
    global _client
    with _lock:
        client, _client = _client, None
    if client is None:
        return
    try:
        client.close()
        logger.info("[http] 共享 httpx 客户端已关闭")
    except Exception as exc:  # noqa: BLE001 - 退出阶段不应影响进程终止
        logger.warning("[http] 关闭共享客户端失败：{}", exc)


atexit.register(close)
