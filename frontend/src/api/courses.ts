import { client } from './client';
import type { Course, Replay } from '@/types';

export const listCourses = () => client.get<Course[]>('/courses').then((r) => r.data);
export const getCourse = (id: number) => client.get<Course>(`/courses/${id}`).then((r) => r.data);
export const importCourse = (body: Partial<Course> & { title: string; video_url: string }) =>
  client.post<Course>('/courses/import', body).then((r) => r.data);
export const startParse = (courseId: number) =>
  client.post(`/courses/${courseId}/parse`).then((r) => r.data);
export const parseReplay = (courseId: number, replayId: number) =>
  client.post(`/platform/courses/${courseId}/replays/${replayId}/parse`).then((r) => r.data);
export const fetchReplayStream = (courseId: number, replayId: number) =>
  client.post<{ video_url: string }>(`/platform/courses/${courseId}/replays/${replayId}/stream`).then((r) => r.data);
export const syncCourses = () =>
  client.post<{ synced: number; total: number }>('/platform/sync-courses').then((r) => r.data);
export const fetchReplays = (courseId: number) =>
  client.get<Replay[]>(`/platform/courses/${courseId}/replays`).then((r) => r.data);
