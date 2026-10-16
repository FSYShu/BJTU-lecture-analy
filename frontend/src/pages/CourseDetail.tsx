import { useEffect, useState, useRef, useCallback } from 'react';
import { Link, useParams } from 'react-router-dom';
import Player, { SeekContext } from '@/components/Player';
import Subtitle from '@/components/Subtitle';
import Keypoints from '@/components/Keypoints';
import SummaryView from '@/components/Summary';
import MindmapView from '@/components/Mindmap';
import { getCourse, fetchReplays, parseReplay } from '@/api/courses';
import { listTranscripts, listKeypoints, getSummary, getMindmap, getTask, getLatestTask } from '@/api';
import { toast } from '@/store/toast';
import type { Course, Replay, Transcript, Keypoint, Summary, Mindmap, Task } from '@/types';

const ACTIVE_STATUSES = new Set(['queued', 'downloading', 'extracting_audio', 'asr_running', 'llm_running', 'persisting']);

const STEP_LABELS: Record<string, string> = {
  queued: '排队中',
  downloading: '下载音频',
  extracting_audio: '提取音频',
  asr_running: '语音识别',
  llm_running: 'AI 解析',
  persisting: '保存结果',
};

export default function CourseDetail() {
  const { id } = useParams<{ id: string }>();
  const courseId = Number(id);
  const [course, setCourse] = useState<Course | null>(null);
  const [currentSec, setCurrentSec] = useState(0);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [keypoints, setKeypoints] = useState<Keypoint[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [mindmap, setMindmap] = useState<Mindmap | null>(null);

  const [seek, setSeek] = useState<(t: number) => void>(() => {});
  const [replays, setReplays] = useState<Replay[]>([]);
  const [parsingId, setParsingId] = useState<number | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [taskStartTime, setTaskStartTime] = useState<number | null>(null);
  const [lastUpdateTime, setLastUpdateTime] = useState<number | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshAll = useCallback(() => {
    getCourse(courseId).then(setCourse).catch(() => {});
    listTranscripts(courseId).then(setTranscripts).catch(() => {});
    listKeypoints(courseId).then(setKeypoints).catch(() => {});
    getSummary(courseId).then(setSummary).catch(() => {});
    getMindmap(courseId).then(setMindmap).catch(() => {});
  }, [courseId]);

  const startPolling = useCallback((taskId: number) => {
    if (pollRef.current) clearInterval(pollRef.current);
    setTaskStartTime(Date.now());
    setLastUpdateTime(Date.now());
    pollRef.current = setInterval(async () => {
      try {
        const t = await getTask(taskId);
        setTask(t);
        setLastUpdateTime(Date.now());
        if (t.status === 'succeeded') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setParsingId(null);
          setTaskStartTime(null);
          refreshAll();
        } else if (t.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setParsingId(null);
          setTaskStartTime(null);
          toast.error(t.error_message || '解析失败');
        } else {
          refreshAll();
        }
      } catch {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        setParsingId(null);
        setTaskStartTime(null);
      }
    }, 3000);
  }, [refreshAll]);

  useEffect(() => {
    if (taskStartTime) {
      const timer = setInterval(() => setElapsedSec(Math.floor((Date.now() - taskStartTime) / 1000)), 1000);
      return () => clearInterval(timer);
    }
  }, [taskStartTime]);

  useEffect(() => {
    refreshAll();
    fetchReplays(courseId)
      .then((list) => setReplays(list))
      .catch(() => {});

    getLatestTask(courseId)
      .then((t) => {
        if (t && ACTIVE_STATUSES.has(t.status)) {
          setTask(t);
          setParsingId(-1);
          startPolling(t.id);
        }
      })
      .catch(() => {});

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [courseId, refreshAll, startPolling]);

  const handleParseReplay = async (r: Replay) => {
    if (parsingId !== null) return;
    setParsingId(r.id);
    try {
      const res: Task = await parseReplay(courseId, r.id);
      toast.success('已开始解析');
      setTask(res);
      getCourse(courseId).then(setCourse).catch(() => {});
      startPolling(res.id);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.response?.data?.message || '发起解析失败';
      toast.error(typeof msg === 'string' ? msg : '发起解析失败');
      setParsingId(null);
    }
  };

  const isParsing = task != null && ACTIVE_STATUSES.has(task.status);

  return (
    <SeekContext.Provider value={seek}>
      <div className="space-y-6">
        <div className="flex items-center gap-4 min-w-0">
          <Link to="/" className="text-gray-400 hover:text-gray-600 shrink-0">← 返回</Link>
          <h1 className="text-2xl font-bold truncate">{course?.title ?? '课程详情'}</h1>
          {course && (
            <span className="text-sm text-gray-500 shrink-0">
              {course.teacher_name} · {course.session_label}
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 lg:gap-6">
          {/* 左侧：播放器 + 字幕 + 课程概览 */}
          <div className="lg:col-span-2 space-y-4">
            {course?.video_url && (
              <div className="border border-gray-200 rounded-lg overflow-hidden bg-black">
                <Player src={course.video_url} onTimeUpdate={setCurrentSec} onSeekReady={setSeek} />
              </div>
            )}
            {transcripts.length > 0 && (
              <Subtitle transcripts={transcripts} currentSec={currentSec} onSeek={seek} />
            )}
            {summary && <SummaryView summary={summary} />}
          </div>

          {/* 右侧：回放列表 + 重点 + 导图 */}
          <div className="space-y-4">
            {replays.length > 0 && (
              <div className="space-y-2">
                <h2 className="text-sm font-semibold text-gray-500">回放列表</h2>
                <div className="space-y-1">
                  {replays.map((r) => (
                    <button
                      key={r.id}
                      onClick={() => handleParseReplay(r)}
                      disabled={isParsing}
                      className="w-full border border-gray-200 rounded-lg px-3 py-2 hover:shadow-md hover:border-primary-300 transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <div className="text-sm font-medium text-gray-800">
                        {r.teach_time_str || (r.class_begin_time?.split(' ')[0] ?? '—')}
                      </div>
                      <div className="text-xs text-gray-400">
                        {r.course_between || ''}
                      </div>
                      <div className="text-xs text-gray-400">
                        {r.class_room || ''}
                      </div>
                      <div className="text-xs text-primary-600 mt-1">
                        {parsingId === r.id ? '解析中...' : isParsing ? '等待中' : '开始解析'}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {keypoints.length > 0 && <Keypoints keypoints={keypoints} onSeek={seek} />}
            {mindmap && <MindmapView mindmap={mindmap} onSeek={seek} />}
          </div>
        </div>

        {isParsing && task && (
          <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-700 flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full bg-primary-500 animate-pulse" />
                {STEP_LABELS[task.status] || task.current_step || task.status}
              </span>
              <span className="text-sm text-gray-500">
                {task.progress}% · 已用 {Math.floor(elapsedSec / 60)}:{String(elapsedSec % 60).padStart(2, '0')}
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
              <div
                className="bg-primary-500 h-2 rounded-full transition-all duration-500 relative"
                style={{ width: `${task.progress}%` }}
              >
                <span className="absolute right-0 top-0 h-2 w-8 bg-gradient-to-r from-transparent to-white/50 animate-pulse" />
              </div>
            </div>
            <p className="text-xs text-gray-400 mt-2">
              {lastUpdateTime ? `最后更新 ${Math.floor((Date.now() - lastUpdateTime) / 1000)}s 前` : ''} · 切换应用后自动恢复
            </p>
          </div>
        )}
      </div>
    </SeekContext.Provider>
  );
}
