"""BackgroundTasks 入口：执行整条流水线，单任务独立 try/except 失败隔离。

``TASK_MAX_CONCURRENT`` 限制并发解析任务数：超出上限的任务在这里排队等待
（docs/05:24「超出排队」、docs/10:1016 IP 并发限流）。
"""
from __future__ import annotations

import threading

from loguru import logger

from app.config import settings
from app.pipeline.orchestrator import run_pipeline

# BackgroundTasks 在线程池中执行，用信号量实现进程内并发上限 + 排队
_task_slots = threading.BoundedSemaphore(max(1, settings.task_max_concurrent))
_running = 0
_running_lock = threading.Lock()


def run(task_id: int) -> None:
    logger.info("[worker] 解析任务 {} 进入队列（并发上限 {}）", task_id, settings.task_max_concurrent)
    with _task_slots:
        _mark_started(task_id)
        try:
            run_pipeline(task_id)
        finally:
            _mark_finished(task_id)


def _mark_started(task_id: int) -> None:
    global _running
    with _running_lock:
        _running += 1
        logger.info("[worker] 开始执行解析任务 task_id={}（当前并发 {}）", task_id, _running)


def _mark_finished(task_id: int) -> None:
    global _running
    with _running_lock:
        _running = max(0, _running - 1)
        logger.info("[worker] 解析任务 task_id={} 结束（当前并发 {}）", task_id, _running)
