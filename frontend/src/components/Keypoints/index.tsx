import { useContext, useMemo } from 'react';
import type { Keypoint } from '@/types';
import { formatTime } from '@/utils/time';
import Empty from '@/components/Empty';
import { SeekContext } from '@/components/Player';

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
  concept: 'bg-blue-50 text-blue-600 dark:bg-blue-900/40 dark:text-blue-300',
  formula: 'bg-purple-50 text-purple-600 dark:bg-purple-900/40 dark:text-purple-300',
  example: 'bg-green-50 text-green-600 dark:bg-green-900/40 dark:text-green-300',
  exam_point: 'bg-orange-50 text-orange-600 dark:bg-orange-900/40 dark:text-orange-300',
};

export default function Keypoints({ keypoints, currentSec, onSeek }: KeypointsProps) {
  const seek = useContext(SeekContext) ?? onSeek;
  // 接口按 timestamp_sec 升序返回，取最后一条「已经开始讲」的即当前重点
  const activeId = useMemo(() => {
    if (currentSec === undefined) return null;
    let id: number | null = null;
    for (const k of keypoints) {
      if (k.timestamp_sec <= currentSec) id = k.id;
    }
    return id;
  }, [keypoints, currentSec]);

  const hasAi = keypoints.some((k) => k.ai_generated);

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800">
      <div className="flex items-center gap-2 px-4 py-2 border-b dark:border-gray-700">
        <span className="text-sm font-medium">重点列表</span>
        {hasAi && <span className="text-[10px] text-accent-500 dark:text-accent-200 bg-accent-50 dark:bg-accent-700/30 px-1 rounded">AI</span>}
      </div>
      <div className="h-64 overflow-y-auto">
        {keypoints.length === 0 ? (
          <Empty text="暂无可用重点" />
        ) : (
          keypoints.map((k) => (
            <div
              key={k.id}
              onClick={() => seek?.(k.timestamp_sec)}
              className={`cursor-pointer py-2 px-4 border-b dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700/50 ${
                k.id === activeId ? 'bg-primary-50 dark:bg-primary-900/40' : ''
              }`}
            >
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    seek?.(k.timestamp_sec);
                  }}
                  title={`跳转到 ${formatTime(k.timestamp_sec)}`}
                  aria-label={`跳转到 ${formatTime(k.timestamp_sec)}`}
                  className="text-xs text-primary-600 dark:text-primary-400 font-medium rounded px-0.5 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-300"
                >
                  {formatTime(k.timestamp_sec)}
                </button>
                {k.category && (
                  <span className={`text-xs px-1.5 py-0.5 rounded ${CATEGORY_STYLE[k.category] || 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'}`}>
                    {CATEGORY_LABEL[k.category] || k.category}
                  </span>
                )}
                <span className="font-medium text-gray-800 dark:text-gray-100">{k.title}</span>
              </div>
              {k.summary && <div className="text-sm text-gray-600 dark:text-gray-300 mt-1">{k.summary}</div>}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
