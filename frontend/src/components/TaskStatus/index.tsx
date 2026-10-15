import type { Task } from '@/types';

interface TaskStatusProps {
  task?: Task;
  onRetry?: () => void;
}

const STATUS_LABEL: Record<string, string> = {
  queued: '排队中', downloading: '下载中', extracting_audio: '音频处理中',
  asr_running: '语音识别中', llm_running: '语义解析中', persisting: '保存中',
  succeeded: '已完成', failed: '失败',
};

function statusColor(status: string) {
  if (status === 'succeeded') return { text: 'text-success-600', bar: 'bg-success-500' };
  if (status === 'failed') return { text: 'text-danger-600', bar: 'bg-danger-500' };
  return { text: 'text-primary-600', bar: 'bg-primary-500' };
}

export default function TaskStatus({ task, onRetry }: TaskStatusProps) {
  if (!task) return null;
  const c = statusColor(task.status);
  return (
    <div className="border border-gray-200 rounded-lg p-3 min-w-48">
      <div className="flex items-center justify-between gap-3">
        <span className={`text-sm font-medium ${c.text}`}>
          {task.status === 'succeeded' ? '✓ ' : ''}{STATUS_LABEL[task.status] || task.status}
        </span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">{task.progress}%</span>
          {task.status === 'failed' && (
            <button onClick={onRetry} className="text-sm text-primary-600 hover:underline">重试</button>
          )}
        </div>
      </div>
      <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-2 rounded-full transition-all ${c.bar}`} style={{ width: `${task.progress}%` }} />
      </div>
      {task.status === 'failed' && task.error_message && (
        <div className="mt-2 text-sm text-danger-600">{task.error_message}</div>
      )}
    </div>
  );
}
