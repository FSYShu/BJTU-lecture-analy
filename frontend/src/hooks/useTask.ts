import { useEffect, useState } from 'react';
import { getTask } from '@/api/tasks';
import type { Task } from '@/types';

export function useTask(taskId: number | null) {
  const [task, setTask] = useState<Task | null>(null);
  useEffect(() => {
    if (!taskId) return;
    let timer: ReturnType<typeof setInterval>;
    const poll = async () => {
      const t = await getTask(taskId);
      setTask(t);
      if (t.status === 'succeeded' || t.status === 'failed') clearInterval(timer);
    };
    poll();
    timer = setInterval(poll, 2000);
    return () => clearInterval(timer);
  }, [taskId]);
  return task;
}