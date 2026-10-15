import { client } from './client';
import type { Transcript } from '@/types';

export const listTranscripts = (courseId: number) =>
  client.get<Transcript[]>(`/courses/${courseId}/transcripts`).then((r) => r.data);