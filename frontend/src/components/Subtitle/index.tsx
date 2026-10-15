import { useEffect, useRef } from 'react';
import type { Transcript } from '@/types';
import { formatTime } from '@/utils/time';

interface SubtitleProps {
  transcripts: Transcript[];
  currentSec: number;
  onSeek?: (t: number) => void;
}

export default function Subtitle({ transcripts, currentSec, onSeek }: SubtitleProps) {
  const active = transcripts.find((t) => currentSec >= t.start_sec && currentSec <= t.end_sec);
  const activeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [active?.id]);

  return (
    <div className="border border-gray-200 rounded-lg">
      <div className="flex items-center justify-between px-4 py-2 border-b">
        <span className="text-sm font-medium">字幕</span>
      </div>
      <div className="h-48 overflow-y-auto p-2">
        {transcripts.map((t) => (
          <div
            key={t.id}
            ref={t.id === active?.id ? activeRef : undefined}
            onClick={() => onSeek?.(t.start_sec)}
            className={`cursor-pointer px-2 py-1 rounded ${t.id === active?.id ? 'bg-primary-100' : 'hover:bg-gray-100'}`}
          >
            <span className="text-xs text-gray-500">{formatTime(t.start_sec)}</span>
            <span className="ml-2">{t.text}</span>
            {t.ai_generated && <span className="ml-1 text-[10px] text-accent-500 bg-accent-50 px-1 rounded">AI</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
