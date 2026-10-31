export interface User {
  id: number;
  username: string;
  role: 'student' | 'teacher' | 'admin';
  display_name?: string;
}

export interface Course {
  id: number;
  title: string;
  teacher_name?: string;
  session_label?: string;
  duration_sec?: number;
  video_url?: string;
  video_format?: string;
  platform_course_id?: string;
  course_num?: string;
  fz_id?: string;
  platform_c_id?: number;
  source: string;
}

export interface Replay {
  id: number;
  lecture_id?: number;
  teach_time_str?: string;
  class_begin_time?: string;
  class_end_time?: string;
  course_between?: string;
  class_room?: string;
  uuid?: string;
}

export interface Task {
  id: number;
  course_id: number;
  lecture_id?: number;
  status: string;
  progress: number;
  current_step?: string;
  error_code?: string;
  error_message?: string;
  retry_count: number;
}

export interface Transcript {
  id: number;
  seq_index: number;
  text: string;
  start_sec: number;
  end_sec: number;
  ai_generated: boolean;
  source_model?: string;
  generated_at: string;
}

export interface Keypoint {
  id: number;
  seq_index: number;
  title: string;
  category?: string;
  summary?: string;
  timestamp_sec: number;
  ai_generated: boolean;
  source_model?: string;
  generated_at: string;
}

export interface Summary {
  id: number;
  overview?: string;
  chapter_points?: string;
  key_details?: string;
  review_hints?: string;
  ai_generated: boolean;
  source_model?: string;
  generated_at: string;
}

export interface Mindmap {
  id: number;
  root_topic: string;
  nodes: string;
  ai_generated: boolean;
  source_model?: string;
  generated_at: string;
}

/** 转写概览：首末句 + 总句数，不含全量转写（全量走分页接口）。 */
export interface TranscriptMeta {
  total: number;
  first: Transcript | null;
  last: Transcript | null;
}

/** 课次首屏聚合结果（docs/11 流量优化 F4）。 */
export interface LectureOverview {
  lecture_id: number;
  keypoints: Keypoint[];
  summary: Summary | null;
  mindmap: Mindmap | null;
  transcript_meta: TranscriptMeta;
  task: Task | null;
}