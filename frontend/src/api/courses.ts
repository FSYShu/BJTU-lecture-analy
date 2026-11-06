import { client } from './client';
import type { Course, Replay } from '@/types';

export const courseKey = (c: Course) => `${c.course_num}-${c.fz_id?.slice(-2)}`;

export const listCourses = () => client.get<Course[]>('/courses').then((r) => r.data);
export const getCourse = (key: string) => client.get<Course>(`/courses/${key}`).then((r) => r.data);
export const importCourse = (body: Partial<Course> & { title: string; video_url: string }) =>
  client.post<Course>('/courses/import', body).then((r) => r.data);
export const startParse = (key: string) =>
  client.post(`/courses/${key}/parse`).then((r) => r.data);
export const parseReplay = (key: string, replayId: number) =>
  client.post(`/platform/courses/${key}/replays/${replayId}/parse`).then((r) => r.data);
export const fetchReplayStream = (key: string, replayId: number) =>
  client.post<{ video_url: string }>(`/platform/courses/${key}/replays/${replayId}/stream`, {}, { timeout: 120000 }).then((r) => r.data);
export const syncCourses = () =>
  client.post<{ synced: number; total: number }>('/platform/sync-courses').then((r) => r.data);
export const fetchReplays = (key: string) =>
  client.get<Replay[]>(`/platform/courses/${key}/replays`).then((r) => r.data);
