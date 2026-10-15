import { client } from './client';
import type { Keypoint } from '@/types';

export const listKeypoints = (courseId: number) =>
  client.get<Keypoint[]>(`/courses/${courseId}/keypoints`).then((r) => r.data);