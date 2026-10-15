import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Player, { SeekContext } from '@/components/Player';
import Subtitle from '@/components/Subtitle';
import Keypoints from '@/components/Keypoints';
import SummaryView from '@/components/Summary';
import MindmapView from '@/components/Mindmap';
import TaskStatus from '@/components/TaskStatus';
import Empty from '@/components/Empty';
import { getCourse } from '@/api/courses';
import { getLatestTask, retryTask } from '@/api/tasks';
import { useTask } from '@/hooks/useTask';
import { listTranscripts, listKeypoints, getSummary, getMindmap } from '@/api';
import type { Course, Transcript, Keypoint, Summary, Mindmap } from '@/types';

export default function CourseDetail() {
  const { id } = useParams<{ id: string }>();
  const courseId = Number(id);
  const [course, setCourse] = useState<Course | null>(null);
  const [currentSec, setCurrentSec] = useState(0);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [keypoints, setKeypoints] = useState<Keypoint[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [mindmap, setMindmap] = useState<Mindmap | null>(null);
  const [taskId, setTaskId] = useState<number | null>(null);
  const [seek, setSeek] = useState<(t: number) => void>(() => {});

  useEffect(() => {
    getCourse(courseId).then(setCourse).catch(() => {});
    listTranscripts(courseId).then(setTranscripts).catch(() => {});
    listKeypoints(courseId).then(setKeypoints).catch(() => {});
    getSummary(courseId).then(setSummary).catch(() => {});
    getMindmap(courseId).then(setMindmap).catch(() => {});
    getLatestTask(courseId)
      .then((t) => setTaskId(t.id))
      .catch(() => setTaskId(null));
  }, [courseId]);

  const task = useTask(taskId);

  const handleRetry = useCallback(() => {
    if (!task) return;
    retryTask(task.id).then((t) => setTaskId(t.id)).catch(() => {});
  }, [task]);

  return (
    <SeekContext.Provider value={seek}>
      <div className="space-y-6">
        {/* 顶部标题栏 */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-4 min-w-0">
            <Link to="/" className="text-gray-400 hover:text-gray-600 shrink-0">← 返回</Link>
            <h1 className="text-2xl font-bold truncate">{course?.title ?? '课程详情'}</h1>
            {course && (
              <span className="text-sm text-gray-500 shrink-0">
                {course.teacher_name} · {course.session_label}
              </span>
            )}
          </div>
          {task && <TaskStatus task={task} onRetry={handleRetry} />}
        </div>

        {/* 主体三栏布局（<1024px 单栏） */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 lg:gap-6">
          {/* 左侧：播放器 + 字幕 */}
          <div className="lg:col-span-2 space-y-4">
            <div className="border border-gray-200 rounded-lg overflow-hidden bg-black">
              <Player src={course?.video_url || ''} onTimeUpdate={setCurrentSec} onSeekReady={setSeek} />
            </div>
            {transcripts.length > 0 ? (
              <Subtitle transcripts={transcripts} currentSec={currentSec} onSeek={seek} />
            ) : (
              <div className="border border-gray-200 rounded-lg">
                <Empty text="暂无字幕" />
              </div>
            )}
          </div>

          {/* 右侧：重点 + 总结 + 导图 */}
          <div className="space-y-4">
            <Keypoints keypoints={keypoints} onSeek={seek} />
            {summary && <SummaryView summary={summary} />}
            {mindmap && <MindmapView mindmap={mindmap} onSeek={seek} />}
          </div>
        </div>
      </div>
    </SeekContext.Provider>
  );
}
