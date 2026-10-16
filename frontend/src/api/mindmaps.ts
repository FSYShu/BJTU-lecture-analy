import { client } from './client';
import type { Mindmap } from '@/types';

export const getMindmap = (lectureId: number) =>
  client.get<Mindmap>(`/lectures/${lectureId}/mindmap`).then((r) => r.data);