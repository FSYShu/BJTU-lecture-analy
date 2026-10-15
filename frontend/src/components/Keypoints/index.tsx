import type { Keypoint } from '@/types';
import { formatTime } from '@/utils/time';
import Empty from '@/components/Empty';

interface KeypointsProps {
  keypoints: Keypoint[];
  onSeek?: (t: number) => void;
}

const CATEGORY_LABEL: Record<string, string> = {
  concept: '概念', formula: '公式', example: '例题', exam_point: '考点',
};

const CATEGORY_STYLE: Record<string, string> = {
  concept: 'bg-blue-50 text-blue-600',
  formula: 'bg-purple-50 text-purple-600',
  example: 'bg-green-50 text-green-600',
  exam_point: 'bg-orange-50 text-orange-600',
};

export default function Keypoints({ keypoints, onSeek }: KeypointsProps) {
  return (
    <div className="border border-gray-200 rounded-lg">
      <div className="px-4 py-2 border-b text-sm font-medium">重点列表</div>
      <div className="h-64 overflow-y-auto">
        {keypoints.length === 0 ? (
          <Empty text="暂无可用重点" />
        ) : (
          keypoints.map((k) => (
            <div
              key={k.id}
              onClick={() => onSeek?.(k.timestamp_sec)}
              className="cursor-pointer py-2 px-4 border-b last:border-0 hover:bg-gray-50"
            >
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-primary-600 font-medium">{formatTime(k.timestamp_sec)}</span>
                {k.category && (
                  <span className={`text-xs px-1.5 py-0.5 rounded ${CATEGORY_STYLE[k.category] || 'bg-gray-100 text-gray-600'}`}>
                    {CATEGORY_LABEL[k.category] || k.category}
                  </span>
                )}
                <span className="font-medium text-gray-800">{k.title}</span>
                {k.ai_generated && <span className="text-[10px] text-accent-500 bg-accent-50 px-1 rounded">AI</span>}
              </div>
              {k.summary && <div className="text-sm text-gray-600 mt-1">{k.summary}</div>}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
