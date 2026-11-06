"""任务状态 SSE 推送（docs/11 优化 4，替代前端固定轮询）。

设计要点：
- **只在状态快照变化时发帧**，前端不必处理重复状态；
- 长任务里若一直没变化，每 ``heartbeat_seconds`` 发一个注释帧，避免中间层判定空闲；
- 状态到达 ``succeeded`` / ``failed`` 即结束流，前端随之关闭连接；
- 查询用的是独立 ``SessionLocal``，不复用请求作用域会话：SSE 连接可能活很久，
  请求级会话缓存会让前端永远看到第一次的状态。
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from loguru import logger

TERMINAL_STATUSES = ("succeeded", "failed")

#: 单条 SSE 连接的最长存活时间，兜底防止任务卡死时连接永久驻留。
MAX_STREAM_SECONDS = 1800.0


def task_snapshot(session_factory: Callable[[], Any], task_id: int) -> dict[str, Any] | None:
    """用一次性会话读任务快照；返回 None 表示任务不存在。"""
    from app.db.models import ParseTask
    from app.schemas.task import TaskOut

    db = session_factory()
    try:
        task = db.get(ParseTask, task_id)
        if task is None:
            return None
        return TaskOut.model_validate(task).model_dump(mode="json")
    finally:
        db.close()


def _frame(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def task_events(
    task_id: int,
    session_factory: Callable[[], Any] | None = None,
    sleep: Callable[[float], Any] = asyncio.sleep,
    interval: float = 1.0,
    heartbeat_seconds: float = 15.0,
    max_seconds: float = MAX_STREAM_SECONDS,
) -> AsyncIterator[str]:
    """产出 SSE 帧：状态变化时发 ``data:``，否则按心跳间隔发注释帧。"""
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    started = time.monotonic()
    last_payload: str | None = None
    silent_for = 0.0

    while True:
        try:
            snapshot = await asyncio.to_thread(task_snapshot, session_factory, task_id)
        except Exception:  # noqa: BLE001 - 流内异常不能把整条连接炸掉
            logger.exception("[sse] 读取任务 {} 状态失败", task_id)
            yield 'event: error\ndata: {"message": "读取任务状态失败"}\n\n'
            return

        if snapshot is None:
            yield 'event: error\ndata: {"message": "任务不存在"}\n\n'
            return

        payload = json.dumps(snapshot, ensure_ascii=False)
        if payload != last_payload:
            yield _frame(snapshot)
            last_payload = payload
            silent_for = 0.0
        else:
            silent_for += interval
            if silent_for >= heartbeat_seconds:
                yield ": keep-alive\n\n"
                silent_for = 0.0

        if snapshot.get("status") in TERMINAL_STATUSES:
            return

        if time.monotonic() - started > max_seconds:
            logger.info("[sse] 任务 {} 推送超过 {}s，主动关闭连接", task_id, max_seconds)
            yield 'event: error\ndata: {"message": "状态推送超时，请刷新页面"}\n\n'
            return

        await sleep(interval)
