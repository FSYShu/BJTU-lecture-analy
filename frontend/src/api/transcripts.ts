import { client } from './client';
import type { Transcript } from '@/types';

export const listTranscripts = (lectureId: number) =>
  client.get<Transcript[]>(`/lectures/${lectureId}/transcripts`).then((r) => r.data);