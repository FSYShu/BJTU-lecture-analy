import { useEffect, useRef, useState, useCallback } from 'react';
import { Link, useParams } from 'react-router-dom';
import Player, { SeekContext } from '@/components/Player';
import Subtitle from '@/components/Subtitle';
import Keypoints from '@/components/Keypoints';
import SummaryView from '@/components/Summary';
import MindmapView from '@/components/Mindmap';
import ProgressStepper from '@/components/ProgressStepper';
import { getCourse, fetchReplays, parseReplay, fetchReplayStream } from '@/api/courses';
import { getLectureOverview, listTranscripts } from '@/api';
import { useTaskWatcher } from '@/hooks/useTask';
import { toast } from '@/store/toast';
import type { Course, Replay, Transcript, Keypoint, Summary, Mindmap, Task, LectureOverview } from '@/types';

const ACTIVE_STATUSES = new Set(['queued', 'downloading', 'extracting_audio', 'asr_running', 'llm_running', 'persisting']);


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
  const [selectedReplayId, setSelectedReplayId] = useState<number | null>(null);

  const [replayVideoUrl, setReplayVideoUrl] = useState<string>('');
  const [loadingStream, setLoadingStream] = useState<number | null>(null);
  const [parsingId, setParsingId] = useState<number | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [taskStartTime, setTaskStartTime] = useState<number | null>(null);
  const [lastUpdateTime, setLastUpdateTime] = useState<number | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);

  // 任务订阅：当前在看哪个课次、订阅哪个任务
  const [activeLectureId, setActiveLectureId] = useState<number | null>(null);
  const [activeTaskId, setActiveTaskId] = useState<number | null>(null);
  const lastStepRef = useRef<string | null>(null);

  /** 首屏聚合：1 次 overview + 1 次转写（docs/11 流量优化 F4）。 */
  const refreshAll = useCallback(async (lectureId: number): Promise<LectureOverview | null> => {
    try {
      const [overview, transcriptList] = await Promise.all([
        getLectureOverview(lectureId),
        listTranscripts(lectureId),
      ]);
      setKeypoints(overview.keypoints);
      setSummary(overview.summary);
      setMindmap(overview.mindmap);
      setTranscripts(transcriptList);
      return overview;
    } catch {
      return null;
    }
  }, []);

  /** 解析进行中只想尽快看到新产生的转写，不动其它面板。 */
  const refreshBasic = useCallback((lectureId: number) => {
    listTranscripts(lectureId).then(setTranscripts).catch(() => {});
  }, []);

  useTaskWatcher(activeTaskId, {
    onTask: (t) => {
      setTask(t);
      setLastUpdateTime(Date.now());
      // 换步骤时才刷一次转写，避免 SSE 每帧都打接口
      if (t.current_step !== lastStepRef.current) {
        lastStepRef.current = t.current_step ?? null;
        if (activeLectureId) refreshBasic(activeLectureId);
      }
    },
    onTerminal: (t) => {
      setParsingId(null);
      setTaskStartTime(null);
      setActiveTaskId(null);
      if (t.status === 'succeeded') {
        if (activeLectureId) refreshAll(activeLectureId);
      } else {
        toast.error(t.error_message || '解析失败');
      }
    },
  });

  useEffect(() => {
    if (taskStartTime) {
      const timer = setInterval(() => setElapsedSec(Math.floor((Date.now() - taskStartTime) / 1000)), 1000);
      return () => clearInterval(timer);
    }
  }, [taskStartTime]);

  /** 订阅任务：非终态才订阅，终态直接展示。 */
  const watchTask = useCallback((latest: Task | null) => {
    if (latest && ACTIVE_STATUSES.has(latest.status)) {
      setTask(latest);
      setParsingId(-1);
      setTaskStartTime(Date.now());
      setLastUpdateTime(Date.now());
      lastStepRef.current = latest.current_step ?? null;
      setActiveTaskId(latest.id);
    } else {
      setTask(latest);
      setParsingId(null);
      setTaskStartTime(null);
    }
  }, []);

  // 进入详情：加载课程 + 回放列表，自动选中第一个回放并加载播放器与对应 AI 解析
  useEffect(() => {
    getCourse(courseId).then(setCourse).catch(() => {});
    fetchReplays(courseId)
      .then(async (list) => {
        setReplays(list);
        if (list.length > 0) {
          const first = list[0];
          setSelectedReplayId(first.id);

          setLoadingStream(first.id);
          try {
            const res = await fetchReplayStream(courseId, first.id);
            const url = typeof res === 'string' ? res : (res?.video_url || '');
            if (url) setReplayVideoUrl(url);
          } catch {
            /* 静默 */
          } finally {
            setLoadingStream(null);
          }
          const lid = first.lecture_id;
          if (lid) {
            setActiveLectureId(lid);
            const overview = await refreshAll(lid);
            watchTask(overview?.task ?? null);
          }
        }
      })
      .catch(() => {});

    return () => {
      setActiveTaskId(null);
    };
  }, [courseId, refreshAll, watchTask]);

  // 点击回放项：加载视频 + 对应 AI 解析
  const handleSelectReplay = async (r: Replay) => {
    if (loadingStream !== null) return;
    setSelectedReplayId(r.id);
    const lid = r.lecture_id ?? null;

    setLoadingStream(r.id);
    try {
      const res = await fetchReplayStream(courseId, r.id);
      const url = typeof res === 'string' ? res : (res?.video_url || '');
      if (url) {
        setReplayVideoUrl(url);
      } else {
        toast.error('未获取到视频地址');
      }
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.response?.data?.message || '获取视频流失败';
      toast.error(typeof msg === 'string' ? msg : '获取视频流失败');
      setReplayVideoUrl('');
    } finally {
      setLoadingStream(null);
    }
    if (lid) {
      setActiveLectureId(lid);
      const overview = await refreshAll(lid);
      watchTask(overview?.task ?? null);
    } else {
      setTranscripts([]);
      setKeypoints([]);
      setSummary(null);
      setMindmap(null);
      setTask(null);
      setParsingId(null);
      setActiveLectureId(null);
      setActiveTaskId(null);
    }
  };

  // 点击解析按钮：启动解析
  const handleParseReplay = async (r: Replay) => {
    if (parsingId !== null) return;
    setParsingId(r.id);
    try {
      const res: Task = await parseReplay(courseId, r.id);
      toast.success('已开始解析');
      if (r.lecture_id) setActiveLectureId(r.lecture_id);
      setTask(res);
      setTaskStartTime(Date.now());
      setLastUpdateTime(Date.now());
      lastStepRef.current = res.current_step ?? null;
      setActiveTaskId(res.id);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.response?.data?.message || '发起解析失败';
      toast.error(typeof msg === 'string' ? msg : '发起解析失败');
      setParsingId(null);
    }
  };

  const isParsing = task != null && ACTIVE_STATUSES.has(task.status);
  const videoUrl = replayVideoUrl || course?.video_url || '';

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
            <div className="border border-gray-200 rounded-lg overflow-hidden bg-black">
              <Player src={videoUrl} onTimeUpdate={setCurrentSec} onSeekReady={setSeek} />
            </div>
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
                    <div
                      key={r.id}
                      className={`w-full border rounded-lg px-3 py-2 transition-all text-left ${
                        selectedReplayId === r.id
                          ? 'border-primary-400 bg-primary-50'
                          : 'border-gray-200 hover:shadow-md hover:border-primary-300'
                      }`}
                    >
                      <button
                        onClick={() => handleSelectReplay(r)}
                        disabled={loadingStream !== null}
                        className="w-full text-left disabled:opacity-50 disabled:cursor-not-allowed"
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
                        {loadingStream === r.id && (
                          <div className="text-xs text-primary-600 mt-1">加载视频中...</div>
                        )}
                      </button>
                      <button
                        onClick={() => handleParseReplay(r)}
                        disabled={isParsing}
                        className="mt-2 w-full text-xs py-1 rounded border border-primary-300 text-primary-600 hover:bg-primary-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        {parsingId === r.id ? '解析中...' : isParsing ? '等待中' : '开始解析'}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {keypoints.length > 0 && (
              <Keypoints keypoints={keypoints} currentSec={currentSec} onSeek={seek} />
            )}
            {mindmap && <MindmapView mindmap={mindmap} onSeek={seek} />}
          </div>
        </div>

        {isParsing && task && (
          <ProgressStepper
            status={task.status}
            progress={task.progress}
            currentStep={task.current_step}
            elapsedSec={elapsedSec}
            lastUpdateSec={lastUpdateTime ? Math.floor((Date.now() - lastUpdateTime) / 1000) : -1}
          />
        )}
      </div>
    </SeekContext.Provider>
  );
}
