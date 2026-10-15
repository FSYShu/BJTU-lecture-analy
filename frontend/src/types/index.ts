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
  video_format?: string;
  source: string;
}

export interface Task {
  id: number;
  course_id: number;
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