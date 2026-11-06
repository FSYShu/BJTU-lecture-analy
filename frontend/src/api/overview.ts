import { client } from './client';
import type { LectureOverview } from '@/types';

/**
 * 课次首屏聚合：重点 + 总结 + 导图 + 转写元信息 + 最新任务，一次往返。
 * 见 docs/11 流量优化 F4。
 */
export const getLectureOverview = (lectureId: number) =>
  client.get<LectureOverview>(`/lectures/${lectureId}/overview`).then((r) => r.data);
