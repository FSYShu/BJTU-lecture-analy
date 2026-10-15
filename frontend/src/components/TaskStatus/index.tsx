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

export default function TaskStatus({ task, onRetry }: TaskStatusProps) {
  if (!task) return null;
  return (
    <div className="border rounded p-3">
      <div className="flex items-center justify-between">
        <span className="font-medium">{STATUS_LABEL[task.status] || task.status}</span>
        {task.status === 'failed' && (
          <button onClick={onRetry} className="text-sm text-blue-600 hover:underline">重试</button>
        )}
      </div>
      <div className="mt-2 h-2 bg-gray-200 rounded">
        <div className="h-2 bg-blue-500 rounded" style={{ width: `${task.progress}%` }} />
      </div>
      {task.status === 'failed' && task.error_message && (
        <div className="mt-2 text-sm text-red-600">{task.error_message}</div>
      )}
    </div>
  );
}