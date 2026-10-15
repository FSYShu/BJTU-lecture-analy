import { client } from './client';
import type { Mindmap } from '@/types';

export const getMindmap = (courseId: number) =>
  client.get<Mindmap>(`/courses/${courseId}/mindmap`).then((r) => r.data);