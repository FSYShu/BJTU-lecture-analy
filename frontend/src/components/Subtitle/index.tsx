import { useContext, useEffect, useRef, useState } from 'react';
import type { Transcript } from '@/types';
import { formatTime } from '@/utils/time';
import { SeekContext } from '@/components/Player';

interface SubtitleProps {
  transcripts: Transcript[];
  currentSec: number;
  onSeek?: (t: number) => void;
}

export default function Subtitle({ transcripts, currentSec, onSeek }: SubtitleProps) {
  const seek = useContext(SeekContext) ?? onSeek;
  const active = transcripts.find((t) => currentSec >= t.start_sec && currentSec <= t.end_sec);
  const activeRef = useRef<HTMLDivElement>(null);
  const [collapsed, setCollapsed] = useState(true);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [active?.id]);

  const hasAi = transcripts.some((t) => t.ai_generated);

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="flex items-center justify-between w-full px-4 py-2 border-b dark:border-gray-700"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">字幕</span>
          {hasAi && <span className="text-[10px] text-accent-500 dark:text-accent-200 bg-accent-50 dark:bg-accent-700/30 px-1 rounded">AI</span>}
        </div>
        <svg
          width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round"
          className={`text-gray-400 transition-transform ${collapsed ? '' : 'rotate-180'}`}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {!collapsed && (
        <div className="h-32 overflow-y-auto p-2">
          {transcripts.length === 0 ? (
            <div className="text-gray-400 dark:text-gray-500 text-sm text-center py-8">解析完成后自动生成</div>
          ) : (
            transcripts.map((t) => (
              <div
                key={t.id}
                ref={t.id === active?.id ? activeRef : undefined}
                onClick={() => seek?.(t.start_sec)}
                className={`cursor-pointer px-2 py-1 rounded ${t.id === active?.id ? 'bg-primary-100 dark:bg-primary-900/40' : 'hover:bg-gray-100 dark:hover:bg-gray-700'}`}
              >
                <span className="text-xs text-gray-500 dark:text-gray-400">{formatTime(t.start_sec)}</span>
                <span className="ml-2">{t.text}</span>

              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
