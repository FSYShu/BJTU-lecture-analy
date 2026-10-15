"""BackgroundTasks 入口：执行整条流水线，单任务独立 try/except 失败隔离。"""
from loguru import logger

from app.pipeline.orchestrator import run_pipeline


def run(task_id: int) -> None:
    logger.info("开始执行解析任务 task_id={}", task_id)
    run_pipeline(task_id)