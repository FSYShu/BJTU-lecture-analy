import { client } from './client';
import type { Summary } from '@/types';

export const getSummary = (courseId: number) =>
  client.get<Summary>(`/courses/${courseId}/summary`).then((r) => r.data);