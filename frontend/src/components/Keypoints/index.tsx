import type { Keypoint } from '@/types';

interface KeypointsProps {
  keypoints: Keypoint[];
  onSeek?: (t: number) => void;
}

const CATEGORY_LABEL: Record<string, string> = {
  concept: '概念', formula: '公式', example: '例题', exam_point: '考点',
};

export default function Keypoints({ keypoints, onSeek }: KeypointsProps) {
  if (!keypoints.length) return <div className="text-gray-400 p-3">暂无可用重点</div>;
  return (
    <div className="border rounded p-3 h-64 overflow-auto">
      {keypoints.map((k) => (
        <div key={k.id} onClick={() => onSeek?.(k.timestamp_sec)} className="cursor-pointer py-2 border-b last:border-0 hover:bg-gray-50">
          <div className="flex items-center gap-2">
            <span className="text-xs text-blue-600">{formatTime(k.timestamp_sec)}</span>
            <span className="text-xs px-1 rounded bg-gray-100">{CATEGORY_LABEL[k.category || ''] || k.category}</span>
            <span className="font-medium">{k.title}</span>
            {k.ai_generated && <span className="text-[10px] text-gray-400">AI</span>}
          </div>
          {k.summary && <div className="text-sm text-gray-600 mt-1">{k.summary}</div>}
        </div>
      ))}
    </div>
  );
}

function formatTime(sec: number) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}