import { client } from './client';
import type { Task } from '@/types';

export const getTask = (id: number) => client.get<Task>(`/tasks/${id}`).then((r) => r.data);
export const retryTask = (id: number) => client.post<Task>(`/tasks/${id}/retry`).then((r) => r.data);