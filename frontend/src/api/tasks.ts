import { API_BASE_URL, authHeaders, client } from './client';
import type { Task } from '@/types';

export const getTask = (id: number) => client.get<Task>(`/tasks/${id}`).then((r) => r.data);
export const getLatestTask = (lectureId: number) =>
  client.get<Task>(`/tasks/latest`, { params: { lecture_id: lectureId } }).then((r) => r.data);
export const retryTask = (id: number) => client.post<Task>(`/tasks/${id}/retry`).then((r) => r.data);

/**
 * 订阅任务状态（SSE，docs/11 优化 4）。
 *
 * 用 `fetch` + `ReadableStream` 而不是 `EventSource`：EventSource 不能带自定义头，
 * 只能把 JWT 塞进 query，会漏进访问日志。这里沿用 Authorization 头。
 * 流在任务终态时正常结束并 resolve；连接失败或服务端发 error 事件时 reject，
 * 由调用方决定是否退回轮询。
 */
export async function streamTask(
  id: number,
  onTask: (task: Task) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(`${API_BASE_URL}/tasks/${id}/stream`, {
    headers: { ...authHeaders(), Accept: 'text/event-stream' },
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`SSE 连接失败：HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      if (block.startsWith('event: error')) {
        const message = block.split('\n').find((l) => l.startsWith('data:'))?.slice(5).trim() || '状态推送中断';
        throw new Error(message);
      }

      const data = block
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim())
        .join('\n');
      if (data) onTask(JSON.parse(data) as Task);

      boundary = buffer.indexOf('\n\n');
    }
  }
}
