import { client } from './client';
import type { Keypoint } from '@/types';

export const listKeypoints = (lectureId: number) =>
  client.get<Keypoint[]>(`/lectures/${lectureId}/keypoints`).then((r) => r.data);