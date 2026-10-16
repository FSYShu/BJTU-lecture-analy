import { client } from './client';
import type { Summary } from '@/types';

export const getSummary = (lectureId: number) =>
  client.get<Summary>(`/lectures/${lectureId}/summary`).then((r) => r.data);