import { useMemo } from 'react';
import type { Keypoint } from '@/types';
import { formatTime } from '@/utils/time';
import Empty from '@/components/Empty';

interface KeypointsProps {
  keypoints: Keypoint[];
  /** 当前播放位置：用于高亮正在讲的那条重点，跳转后能立刻看到落点。 */
  currentSec?: number;
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

export default function Keypoints({ keypoints, currentSec, onSeek }: KeypointsProps) {
  // 接口按 timestamp_sec 升序返回，取最后一条「已经开始讲」的即当前重点
  const activeId = useMemo(() => {
    if (currentSec === undefined) return null;
    let id: number | null = null;
    for (const k of keypoints) {
      if (k.timestamp_sec <= currentSec) id = k.id;
    }
    return id;
  }, [keypoints, currentSec]);

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
              className={`cursor-pointer py-2 px-4 border-b last:border-0 hover:bg-gray-50 ${
                k.id === activeId ? 'bg-primary-50' : ''
              }`}
            >
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSeek?.(k.timestamp_sec);
                  }}
                  title={`跳转到 ${formatTime(k.timestamp_sec)}`}
                  aria-label={`跳转到 ${formatTime(k.timestamp_sec)}`}
                  className="text-xs text-primary-600 font-medium rounded px-0.5 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-300"
                >
                  {formatTime(k.timestamp_sec)}
                </button>
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
