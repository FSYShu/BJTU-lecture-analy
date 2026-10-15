import { client } from './client';
import type { Course } from '@/types';

export const listCourses = () => client.get<Course[]>('/courses').then((r) => r.data);
export const importCourse = (body: Partial<Course> & { title: string; video_url: string }) =>
  client.post<Course>('/courses/import', body).then((r) => r.data);
export const startParse = (courseId: number) =>
  client.post(`/courses/${courseId}/parse`).then((r) => r.data);