import { useState, useEffect, useRef } from 'react';
import { useTaskStore } from '@/store/task';
import { cancelTask } from '@/api/tasks';

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

export default function TaskBadge() {
  const task = useTaskStore((s) => s.task);
  const setTask = useTaskStore((s) => s.setTask);
  const [open, setOpen] = useState(false);
  const [visible, setVisible] = useState(false);
  const dismissTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!task) {
      setVisible(false);
      setOpen(false);
      return;
    }
    setVisible(true);
    if (task.status === 'succeeded') {
      dismissTimer.current = window.setTimeout(() => setTask(null), 3000);
    }
    return () => {
      if (dismissTimer.current) clearTimeout(dismissTimer.current);
    };
  }, [task, setTask]);

  if (!task || !visible) return null;

  const isFailed = task.status === 'failed';
  const isSucceeded = task.status === 'succeeded';
  const isActive = ACTIVE_STATUSES.has(task.status);
  const label = STATUS_LABEL[task.status] || task.status;
  const detail = parseStepDetail(task.current_step);

  const handleCancel = async () => {
    if (!task) return;
    try {
      await cancelTask(task.id);
      setTask(null);
      setOpen(false);
    } catch {
      /* 静默 */
    }
  };

  return (
    <div className="relative flex items-center">
      <button
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all border ${
          isSucceeded
            ? 'bg-success-500/90 text-white border-success-500'
            : isFailed
            ? 'bg-danger-500/90 text-white border-danger-500'
            : 'bg-primary-500/90 text-white border-primary-500 hover:bg-primary-600/90'
        }`}
      >
        {isSucceeded && <span>✓</span>}
        {isFailed && <span>✕</span>}
        {isActive && <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />}
        <span>{label}</span>
        <span className="opacity-90">{task.progress}%</span>
      </button>
      {isFailed && (
        <button
          onClick={() => setTask(null)}
          className="ml-1 w-5 h-5 flex items-center justify-center rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 text-xs"
          aria-label="关闭"
        >
          ×
        </button>
      )}
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-2 w-72 rounded-xl border border-gray-200 bg-white/95 backdrop-blur-md shadow-lg z-50 p-4 space-y-3">
            <div className="flex items-center justify-between text-xs">
              <span className={`font-medium ${isSucceeded ? 'text-success-600' : isFailed ? 'text-danger-600' : 'text-gray-700'}`}>
                {label}
              </span>
              <span className="text-gray-400">{task.progress}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
              <div
                className={`h-2 rounded-full transition-all duration-500 relative ${
                  isFailed ? 'bg-danger-500' : isSucceeded ? 'bg-success-500' : 'bg-primary-500'
                }`}
                style={{ width: `${task.progress}%` }}
              >
                {isActive && (
                  <span className="absolute right-0 top-0 h-2 w-8 bg-gradient-to-r from-transparent to-white/50 animate-pulse" />
                )}
              </div>
            </div>
            {detail && isActive && (
              <div className="text-xs text-gray-500">{detail}</div>
            )}
            {isFailed && task.error_message && (
              <div className="text-xs text-danger-600">{task.error_message}</div>
            )}
            {isActive && (
              <button
                onClick={handleCancel}
                className="w-full text-xs py-1.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
              >
                取消解析
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}