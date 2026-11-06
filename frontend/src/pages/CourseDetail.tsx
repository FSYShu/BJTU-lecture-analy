import { useEffect, useRef, useState, useCallback } from 'react';
import { Link, useParams } from 'react-router-dom';
import Player, { SeekContext } from '@/components/Player';
import Subtitle from '@/components/Subtitle';
import Keypoints from '@/components/Keypoints';
import SummaryView from '@/components/Summary';
import MindmapView from '@/components/Mindmap';
import { getCourse, fetchReplays, parseReplay, fetchReplayStream } from '@/api/courses';
import { getLectureOverview, listTranscripts } from '@/api';
import { getTask } from '@/api/tasks';
import { useTaskWatcher } from '@/hooks/useTask';
import { toast } from '@/store/toast';
import { useTaskStore } from '@/store/task';
import { useCourseCacheStore, loadCurrentSec, saveCurrentSec } from '@/store/courseCache';
import type { Course, Replay, Transcript, Keypoint, Summary, Mindmap, Task, LectureOverview } from '@/types';

const ACTIVE_STATUSES = new Set(['queued', 'downloading', 'extracting_audio', 'asr_running', 'llm_running', 'persisting']);


export default function CourseDetail() {
  const { courseKey = '' } = useParams<{ courseKey: string }>();
  const [course, setCourse] = useState<Course | null>(null);
  const [currentSec, setCurrentSec] = useState(0);
  const currentSecRef = useRef(0);
  const lastSaveSecRef = useRef(0);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [keypoints, setKeypoints] = useState<Keypoint[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [mindmap, setMindmap] = useState<Mindmap | null>(null);

  const [seek, setSeek] = useState<(t: number) => void>(() => {});
  const [replays, setReplays] = useState<Replay[]>([]);
  const [loadingReplays, setLoadingReplays] = useState(true);
  const [selectedReplayId, setSelectedReplayId] = useState<number | null>(null);

  const [replayVideoUrl, setReplayVideoUrl] = useState<string>('');
  const [loadingStream, setLoadingStream] = useState<number | null>(null);
  const setTask = useTaskStore((s) => s.setTask);
  const parseQueueRef = useRef<Replay[]>([]);

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

  /** LLM 阶段每子任务完成即刷 overview（重点/总结/导图），不动转写。 */
  const refreshOverview = useCallback(async (lectureId: number) => {
    try {
      const overview = await getLectureOverview(lectureId);
      setKeypoints(overview.keypoints);
      setSummary(overview.summary);
      setMindmap(overview.mindmap);
    } catch {}
  }, []);

  /** 发起解析：调 parseReplay 后写入全局 task store 并订阅。 */
  const startParse = async (r: Replay) => {
    try {
      const res: Task = await parseReplay(courseKey, r.id);
      setTask(res);
      lastStepRef.current = res.current_step ?? null;
      setActiveTaskId(res.id);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.response?.data?.message || '发起解析失败';
      toast.error(typeof msg === 'string' ? msg : '发起解析失败');
    }
  };

  /** 入队解析：当前无任务在跑则立即解析，否则排队等终态后触发。 */
  const enqueueParse = (r: Replay) => {
    const current = useTaskStore.getState().task;
    const running = current != null && ACTIVE_STATUSES.has(current.status);
    if (running) {
      if (!parseQueueRef.current.some((q) => q.id === r.id)) {
        parseQueueRef.current.push(r);
      }
    } else {
      void startParse(r);
    }
  };

  useTaskWatcher(activeTaskId, {
    onTask: (t) => {
      if (t.status === 'failed' && t.error_code === 'CANCELLED') {
        setTask(null);
        return;
      }
      setTask(t);
      // 换步骤时才刷一次，避免 SSE 每帧都打接口
      if (t.current_step !== lastStepRef.current) {
        lastStepRef.current = t.current_step ?? null;
        if (t.lecture_id && t.lecture_id === activeLectureId) {
          if (t.current_step?.startsWith('llm')) {
            refreshOverview(t.lecture_id);
          } else {
            refreshBasic(t.lecture_id);
          }
        }
      }
    },
    onTerminal: (t) => {
      setActiveTaskId(null);
      if (t.status === 'succeeded') {
        if (t.lecture_id && t.lecture_id === activeLectureId) refreshAll(t.lecture_id);
      } else if (t.error_code !== 'CANCELLED') {
        toast.error(t.error_message || '解析失败');
      }
      const next = parseQueueRef.current.shift();
      if (next) void startParse(next);
    },
  });

  /** 订阅任务：非终态才订阅，终态直接展示。 */
  const watchTask = useCallback((latest: Task | null) => {
    if (latest && ACTIVE_STATUSES.has(latest.status)) {
      setTask(latest);
      lastStepRef.current = latest.current_step ?? null;
      setActiveTaskId(latest.id);
    } else {
      setTask(latest);
    }
  }, [setTask]);

  // 进入详情：加载课程 + 回放列表，自动选中第一个回放并加载播放器与对应 AI 解析
  useEffect(() => {
    let cancelled = false;

    const restoredSec = loadCurrentSec(courseKey);
    setCurrentSec(restoredSec);
    currentSecRef.current = restoredSec;
    lastSaveSecRef.current = restoredSec;

    const cached = useCourseCacheStore.getState().cache[courseKey];
    if (cached && cached.course) {
      setCourse(cached.course);
      setTranscripts(cached.transcripts);
      setKeypoints(cached.keypoints);
      setSummary(cached.summary);
      setMindmap(cached.mindmap);
      setReplays(cached.replays);
      setSelectedReplayId(cached.selectedReplayId);
      setReplayVideoUrl(cached.replayVideoUrl);
      setActiveLectureId(cached.activeLectureId);
      setActiveTaskId(cached.activeTaskId);
      lastStepRef.current = cached.lastStep;
      setLoadingReplays(false);

      if (cached.activeTaskId) {
        getTask(cached.activeTaskId)
          .then((t) => {
            if (cancelled) return;
            if (ACTIVE_STATUSES.has(t.status)) {
              setTask(t);
              lastStepRef.current = t.current_step ?? null;
            } else {
              setActiveTaskId(null);
              if (t.status === 'succeeded' && cached.activeLectureId) {
                refreshAll(cached.activeLectureId);
              } else {
                setTask(null);
              }
            }
          })
          .catch(() => {
            if (!cancelled) setActiveTaskId(null);
          });
      }

      return () => {
        cancelled = true;
        saveCurrentSec(courseKey, currentSecRef.current);
      };
    }

    getCourse(courseKey).then((c) => { if (!cancelled) setCourse(c); }).catch(() => {});
    setLoadingReplays(true);
    fetchReplays(courseKey)
      .then(async (list) => {
        if (cancelled) return;
        const reversed = [...list].reverse();
        setReplays(reversed);
        setLoadingReplays(false);
        if (reversed.length > 0) {
          const first = reversed[0];
          setSelectedReplayId(first.id);

          setLoadingStream(first.id);
          try {
            const res = await fetchReplayStream(courseKey, first.id);
            if (cancelled) return;
            const url = typeof res === 'string' ? res : (res?.video_url || '');
            if (url) setReplayVideoUrl(url);
          } catch (err: any) {
            if (cancelled) return;
            const msg = err?.response?.data?.detail || err?.response?.data?.message || '获取视频流失败';
            toast.error(typeof msg === 'string' ? msg : '获取视频流失败');
          } finally {
            if (!cancelled) setLoadingStream(null);
          }
          if (cancelled) return;
          const lid = first.lecture_id;
          if (lid) {
            setActiveLectureId(lid);
            const overview = await refreshAll(lid);
            if (cancelled) return;
            const latest = overview?.task ?? null;
            watchTask(latest);
            const hasResult = (overview?.keypoints?.length ?? 0) > 0 || !!overview?.summary || !!overview?.mindmap || (overview?.transcript_meta?.total ?? 0) > 0;
            const isActive = latest && ACTIVE_STATUSES.has(latest.status);
            if (!isActive && !hasResult) {
              enqueueParse(first);
            }
          }
        }
      })
      .catch(() => {
        if (cancelled) return;
        setLoadingReplays(false);
        toast.error('回放列表加载失败');
      });

    return () => {
      cancelled = true;
      setActiveTaskId(null);
      saveCurrentSec(courseKey, currentSecRef.current);
    };
  }, [courseKey, refreshAll, watchTask]);

  // 业务状态变化时同步写入缓存（currentSec 高频变化，单独处理不进此 effect）
  useEffect(() => {
    if (course || transcripts.length > 0 || replays.length > 0) {
      useCourseCacheStore.getState().patch(courseKey, {
        course, transcripts, keypoints, summary, mindmap,
        replays, selectedReplayId, replayVideoUrl,
        activeLectureId, activeTaskId,
        lastStep: lastStepRef.current,
      });
    }
  }, [course, transcripts, keypoints, summary, mindmap, replays, selectedReplayId, replayVideoUrl, activeLectureId, activeTaskId, courseKey]);

  // 浏览器刷新/关闭前保存播放进度
  useEffect(() => {
    const handler = () => saveCurrentSec(courseKey, currentSecRef.current);
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [courseKey]);

  const handleTimeUpdate = useCallback((t: number) => {
    setCurrentSec(t);
    currentSecRef.current = t;
    if (t - lastSaveSecRef.current >= 1) {
      lastSaveSecRef.current = t;
      saveCurrentSec(courseKey, t);
    }
  }, [courseKey]);

  // 点击回放项：加载视频 + 对应 AI 解析
  const handleSelectReplay = async (r: Replay) => {
    if (loadingStream !== null) return;
    setSelectedReplayId(r.id);
    const lid = r.lecture_id ?? null;

    setLoadingStream(r.id);
    try {
      const res = await fetchReplayStream(courseKey, r.id);
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
      const latest = overview?.task ?? null;
      watchTask(latest);
      const hasResult = (overview?.keypoints?.length ?? 0) > 0 || !!overview?.summary || !!overview?.mindmap || (overview?.transcript_meta?.total ?? 0) > 0;
      const isActive = latest && ACTIVE_STATUSES.has(latest.status);
      if (!isActive && !hasResult) {
        enqueueParse(r);
      }
    } else {
      setTranscripts([]);
      setKeypoints([]);
      setSummary(null);
      setMindmap(null);
      setTask(null);
      setActiveLectureId(null);
      setActiveTaskId(null);
    }
  };


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
              <Player src={videoUrl} transcripts={transcripts} loading={loadingReplays || loadingStream !== null} initialTime={currentSec} onTimeUpdate={handleTimeUpdate} onSeekReady={setSeek} />
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
                      {r.has_result && (
                        <button
                          onClick={() => enqueueParse(r)}
                          className="mt-1 text-xs text-primary-600 hover:text-primary-700 font-medium"
                        >
                          重新生成
                        </button>
                      )}
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

      </div>
    </SeekContext.Provider>
  );
}
