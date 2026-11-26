import { useState, useEffect, useRef } from 'react';
import { useTaskStore } from '@/store/task';
import { cancelTask, listActiveTasks } from '@/api/tasks';
import type { Task } from '@/types';

const ACTIVE_STATUSES = new Set([
  'queued', 'downloading', 'extracting_audio', 'asr_running', 'llm_running', 'persisting',
]);

const STATUS_LABEL: Record<string, string> = {
  queued: '排队中',
  downloading: '获取元数据',
  extracting_audio: '提取音频',
  asr_running: '语音识别',
  llm_running: 'AI 解析',
  persisting: '保存结果',
  succeeded: '解析完成',
  failed: '解析失败',
};

const LLM_STEP_LABEL: Record<string, string> = {
  keypoints: '生成重点',
  summary: '生成总结',
  mindmap: '生成导图',
};

function getStepLabel(status: string, currentStep?: string): string {
  if (status === 'llm_running' && currentStep) {
    const parts = currentStep.split('|');
    if (parts[0] === 'llm' && parts[1] && LLM_STEP_LABEL[parts[1]]) {
      return LLM_STEP_LABEL[parts[1]];
    }
  }
  return STATUS_LABEL[status] || status;
}

function formatTime(raw: string): string {
  const match = raw.match(/(\d+):(\d+):(\d+)/);
  if (!match) return raw;
  const [, h, m, s] = match;
  if (h === '00') return `${m}:${s}`;
  return `${h}:${m}:${s}`;
}

function parseStepDetail(currentStep?: string): string | null {
  if (!currentStep) return null;
  const parts = currentStep.split('|');
  const type = parts[0];
  if (type === 'audio' && parts.length >= 2) return `已处理 ${formatTime(parts[1])}`;
  if (type === 'asr' && parts.length >= 2) return `分片 ${parts[1]}`;
  return null;
}

/** 课次时间可能是 20261117 / 2026-11-17，统一显示为 11-17。 */
function formatTeachTime(raw?: string | null): string {
  if (!raw) return '';
  const digits = raw.replace(/\D/g, '');
  if (digits.length >= 8) return `${digits.slice(4, 6)}-${digits.slice(6, 8)}`;
  return raw;
}

/** 展示“在解析哪个”：优先课程名 + 课次日期。 */
function taskLabel(task: Task): string {
  const date = formatTeachTime(task.teach_time_str);
  if (task.course_title && date) return `${task.course_title} · ${date}`;
  if (task.course_title) return task.course_title;
  if (date) return date;
  if (task.lecture_id) return `课次 #${task.lecture_id}`;
  return `课程 #${task.course_id}`;
}

export default function TaskBadge() {
  const task = useTaskStore((s) => s.task);
  const setTask = useTaskStore((s) => s.setTask);
  const activeTasks = useTaskStore((s) => s.activeTasks);
  const setActiveTasks = useTaskStore((s) => s.setActiveTasks);
  const [open, setOpen] = useState(false);
  const [visible, setVisible] = useState(false);
  const dismissTimer = useRef<number | undefined>(undefined);

  // 轮询服务端排队/进行中的任务，排队中的任务不依附于当前页面也能看到。
  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const tasks = await listActiveTasks();
        if (!cancelled) setActiveTasks(tasks);
      } catch {
        /* 轮询失败静默，下一轮重试 */
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [setActiveTasks]);

  useEffect(() => {
    if (!task && activeTasks.length === 0) {
      setVisible(false);
      setOpen(false);
      return;
    }
    setVisible(true);
  }, [task, activeTasks.length]);

  useEffect(() => {
    if (task?.status === 'succeeded') {
      dismissTimer.current = window.setTimeout(() => setTask(null), 3000);
    }
    return () => {
      if (dismissTimer.current) clearTimeout(dismissTimer.current);
    };
  }, [task, setTask]);

  if (!visible) return null;

  const terminalTask = task && !ACTIVE_STATUSES.has(task.status) ? task : null;

  const merged = new Map<number, Task>();
  for (const t of activeTasks) merged.set(t.id, t);
  if (task && ACTIVE_STATUSES.has(task.status)) {
    const existing = merged.get(task.id);
    merged.set(task.id, existing ? { ...task, ...existing } : task);
  }
  const actives = Array.from(merged.values()).sort((a, b) => {
    const aQueued = a.status === 'queued' ? 1 : 0;
    const bQueued = b.status === 'queued' ? 1 : 0;
    return aQueued - bQueued || a.id - b.id;
  });
  const running = actives.find((t) => t.status !== 'queued');
  const queuedCount = actives.filter((t) => t.status === 'queued').length;
  // 有排队/进行中的任务时优先展示它们，终态任务在弹窗内单独展示。
  const focused = running ?? actives[0] ?? terminalTask ?? null;

  if (!focused) return null;

  const isFailed = focused.status === 'failed';
  const isSucceeded = focused.status === 'succeeded';


  const terminalFailed = terminalTask?.status === 'failed';
  const terminalSucceeded = terminalTask?.status === 'succeeded';
  const terminalLabel = terminalTask ? STATUS_LABEL[terminalTask.status] || terminalTask.status : '';

  const handleCancel = async (id: number) => {
    try {
      await cancelTask(id);
      if (task?.id === id) setTask(null);
      setActiveTasks(activeTasks.filter((t) => t.id !== id));
      if (actives.length <= 1 && !terminalTask) setOpen(false);
    } catch {
      /* 静默 */
    }
  };

  return (
    <div className="relative flex items-center" onMouseLeave={() => setOpen(false)}>
      <button
        onMouseEnter={() => setOpen(true)}
        title={taskLabel(focused)}
        className={`relative flex items-center justify-center w-8 h-8 rounded-full transition-all ${
          isSucceeded
            ? 'text-success-500'
            : isFailed
            ? 'text-danger-500'
            : 'text-primary-500'
        }`}
      >
        <svg className="absolute inset-0 w-full h-full -rotate-90" viewBox="0 0 36 36">
          <circle cx="18" cy="18" r="15.5" fill="none" stroke="currentColor" strokeWidth="4" opacity="0.2" />
          <circle
            cx="18" cy="18" r="15.5" fill="none" stroke="currentColor" strokeWidth="4"
            strokeDasharray={`${(isSucceeded ? 100 : focused.progress) * 0.974} 100`}
            strokeLinecap="round"
            className="transition-all duration-500"
          />
        </svg>
        <span className="relative text-[10px] font-bold">
          {isSucceeded ? '✓' : isFailed ? '✕' : `${focused.progress}`}
        </span>
        {queuedCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 text-[8px] font-bold bg-amber-500 text-white rounded-full w-3.5 h-3.5 flex items-center justify-center">
            {queuedCount}
          </span>
        )}
      </button>
      {isFailed && (
        <button
          onClick={() => setTask(null)}
          className="ml-1 w-5 h-5 flex items-center justify-center rounded-full text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 text-xs"
          aria-label="关闭"
        >
          ×
        </button>
      )}
      {open && (
        <div className="absolute right-0 top-full pt-2 z-50">
          <div className="w-96 max-h-[70vh] overflow-y-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-800/95 backdrop-blur-md shadow-lg p-4 space-y-4">
            {actives.length > 0 && (
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-gray-700 dark:text-gray-200">解析任务</span>
                  <span className="text-gray-400 dark:text-gray-500">
                    进行中 {actives.length - queuedCount} · 排队 {queuedCount}
                  </span>
                </div>
                {actives.map((item) => {
                  const itemActive = ACTIVE_STATUSES.has(item.status);
                  const itemDetail = parseStepDetail(item.current_step);
                  return (
                    <div key={item.id} className="flex items-start gap-2">
                      <div className="flex-1 min-w-0 space-y-1.5">
                        <div className="flex items-center justify-between gap-2 text-xs">
                          <span
                            className="font-medium text-gray-700 dark:text-gray-200 truncate"
                            title={taskLabel(item)}
                          >
                            {taskLabel(item)}
                          </span>
                          <span className="shrink-0 text-gray-400 dark:text-gray-500">
                            {getStepLabel(item.status, item.current_step)}
                            {item.status !== 'queued' ? ` ${item.progress}%` : ''}
                            {itemDetail && itemActive ? ` · ${itemDetail}` : ''}
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                          <div
                            className={`h-2 rounded-full transition-all duration-500 relative ${
                              item.status === 'queued'
                                ? 'bg-gray-400 dark:bg-gray-500'
                                : 'bg-primary-500'
                            }`}
                            style={{ width: `${item.status === 'queued' ? 0 : item.progress}%` }}
                          >
                            {itemActive && item.status !== 'queued' && (
                              <span className="absolute right-0 top-0 h-2 w-8 bg-gradient-to-r from-transparent to-white/50 animate-pulse" />
                            )}
                          </div>
                        </div>
                        </div>
                      {itemActive && (
                        <button
                          onClick={() => handleCancel(item.id)}
                          className="shrink-0 w-6 h-6 flex items-center justify-center rounded text-gray-400 dark:text-gray-500 hover:text-danger-600 dark:hover:text-danger-500 transition-colors"
                          title="取消任务"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M18 6L6 18M6 6l12 12" />
                          </svg>
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {terminalTask && (
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span
                    className={`font-medium ${
                      terminalSucceeded
                        ? 'text-success-600 dark:text-success-500'
                        : 'text-danger-600 dark:text-danger-500'
                    }`}
                  >
                    {terminalLabel}
                  </span>
                  <span className="text-gray-400 dark:text-gray-500">{terminalTask.progress}%</span>
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-300 truncate" title={taskLabel(terminalTask)}>
                  {taskLabel(terminalTask)}
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                  <div
                    className={`h-2 rounded-full transition-all duration-500 ${
                      terminalFailed ? 'bg-danger-500' : 'bg-success-500'
                    }`}
                    style={{ width: `${terminalTask.progress}%` }}
                  />
                </div>
                {terminalFailed && terminalTask.error_message && (
                  <div className="text-xs text-danger-600 dark:text-danger-500">
                    {terminalTask.error_message}
                  </div>
                )}
                <button
                  onClick={() => setTask(null)}
                  className="w-full text-xs py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                >
                  关闭
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
