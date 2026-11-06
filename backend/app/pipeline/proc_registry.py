"""运行中 ffmpeg 子进程注册表：取消任务时能找到并终止对应进程。"""
from __future__ import annotations

import subprocess
import threading

from loguru import logger

_lock = threading.Lock()
_procs: dict[int, subprocess.Popen] = {}
_killed: set[int] = set()


def register(task_id: int, proc: subprocess.Popen) -> None:
    with _lock:
        _procs[task_id] = proc


def unregister(task_id: int) -> None:
    with _lock:
        _procs.pop(task_id, None)


def was_killed(task_id: int) -> bool:
    with _lock:
        return task_id in _killed


def clear_killed(task_id: int) -> None:
    with _lock:
        _killed.discard(task_id)


def terminate(task_id: int) -> None:
    """终止指定任务的 ffmpeg 子进程（若仍在运行）。"""
    with _lock:
        proc = _procs.pop(task_id, None)
        if proc is None:
            return
        _killed.add(task_id)
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
        logger.info("[task={}] ffmpeg 子进程已终止", task_id)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        logger.warning("[task={}] ffmpeg terminate 超时，已 kill", task_id)
    except Exception:  # noqa: BLE001
        logger.warning("[task={}] 终止 ffmpeg 子进程时出错", task_id)