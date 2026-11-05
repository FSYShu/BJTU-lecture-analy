"""进程内并发小工具：受控并行的**有序** map。

LLM 解析需要在两个层级并行（对应 P0「LLM 三子任务并行化」「LLM 分段 map 并行化」）：

- 三个子任务（重点 / 分层总结 / 两级导图）彼此独立，可同时发起；
- 单个子任务内部的长转写分段（map 阶段）彼此独立，可同时发起。

流水线本身是同步实现（BackgroundTasks + 同步 httpx），所以这里统一用线程池。
``map_ordered`` 的关键约束是**结果必须按输入顺序返回**：分段结果的顺序决定
章节顺序与要点顺序，并发完成顺序不能污染最终结果。
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar, cast

T = TypeVar("T")
R = TypeVar("R")


def map_ordered(
    func: Callable[[int, T], R],
    items: Sequence[T],
    workers: int,
    *,
    thread_name_prefix: str = "worker",
) -> list[R]:
    """并行执行 ``func(index, item)``，按输入顺序返回结果。

    - ``workers <= 1`` 或只有一项时退化为串行，便于调试、低成本环境与单测；
    - 任一任务抛错则整体失败：取消尚未开始的任务并向上抛出异常，
      与串行版本「一段失败即整体失败」的语义一致，上层按整段重试即可；
    - 已启动的任务会在退出线程池时被等待结束，不会留下悬空线程。
    """
    total = len(items)
    if total == 0:
        return []

    limit = max(1, min(int(workers), total))
    if limit == 1:
        return [func(index, item) for index, item in enumerate(items)]

    results: list[R | None] = [None] * total
    with ThreadPoolExecutor(max_workers=limit, thread_name_prefix=thread_name_prefix) as executor:
        futures = {executor.submit(func, index, item): index for index, item in enumerate(items)}
        try:
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        finally:
            for future in futures:
                future.cancel()

    return cast("list[R]", results)
