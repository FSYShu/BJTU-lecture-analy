import { useEffect, useRef } from 'react';
import { getTask, streamTask } from '@/api/tasks';
import type { Task } from '@/types';

const TERMINAL_STATUSES = new Set(['succeeded', 'failed']);

/** 轮询兜底：起步 2s，进度停滞时逐次拉长到 10s，有推进立刻回到 2s。 */
const POLL_START_MS = 2000;
const POLL_MAX_MS = 10000;
const STALL_TICKS = 3;

export interface TaskWatcherOptions {
  /** 每次拿到新状态（含终态）。 */
  onTask?: (task: Task) => void;
  /** 任务进入终态，订阅随之结束。 */
  onTerminal?: (task: Task) => void;
}

/**
 * 订阅解析任务状态：优先 SSE，失败时退回自适应轮询（docs/11 优化 4）。
 *
 * SSE 一条连接替代原本每 2s 一次的 GET（10-20 分钟任务约 300-600 次请求）；
 * 若浏览器 / 反向代理不支持流式响应，则退化为自适应间隔轮询，
 * 至少不会在任务停滞时还保持高频空轮询。
 */
export function useTaskWatcher(taskId: number | null, options: TaskWatcherOptions = {}) {
  const handlers = useRef(options);
  useEffect(() => {
    handlers.current = options;
  });

  useEffect(() => {
    if (!taskId) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();

    const emit = (task: Task): boolean => {
      if (cancelled) return true;
      handlers.current.onTask?.(task);
      if (TERMINAL_STATUSES.has(task.status)) {
        handlers.current.onTerminal?.(task);
        return true;
      }
      return false;
    };

    const startPolling = () => {
      let interval = POLL_START_MS;
      let lastProgress = -1;
      let stalledTicks = 0;

      const tick = async () => {
        if (cancelled) return;
        try {
          const task = await getTask(taskId);
          if (emit(task)) return;
          if (task.progress === lastProgress) {
            stalledTicks += 1;
          } else {
            stalledTicks = 0;
            lastProgress = task.progress;
          }
          interval =
            stalledTicks >= STALL_TICKS
              ? Math.min(Math.round(interval * 1.5), POLL_MAX_MS)
              : POLL_START_MS;
        } catch {
          interval = Math.min(interval * 2, POLL_MAX_MS);
        }
        if (!cancelled) timer = setTimeout(tick, interval);
      };

      void tick();
    };

    streamTask(taskId, emit, controller.signal).catch(() => {
      // 组件卸载 / 切换任务导致的中止不是故障，不再兜底轮询
      if (!cancelled) startPolling();
    });

    return () => {
      cancelled = true;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [taskId]);
}
