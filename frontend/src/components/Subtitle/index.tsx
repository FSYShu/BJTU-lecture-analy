import type { Transcript } from '@/types';

interface SubtitleProps {
  transcripts: Transcript[];
  currentSec: number;
  onSeek?: (t: number) => void;
}

export default function Subtitle({ transcripts, currentSec, onSeek }: SubtitleProps) {
  const active = transcripts.find((t) => currentSec >= t.start_sec && currentSec <= t.end_sec);
  return (
    <div className="border rounded p-3 h-48 overflow-auto">
      {transcripts.map((t) => (
        <div
          key={t.id}
          onClick={() => onSeek?.(t.start_sec)}
          className={`cursor-pointer px-2 py-1 rounded ${t.id === active?.id ? 'bg-blue-100' : 'hover:bg-gray-100'}`}
        >
          <span className="text-xs text-gray-500">{formatTime(t.start_sec)}</span>
          <span className="ml-2">{t.text}</span>
          {t.ai_generated && <span className="ml-1 text-[10px] text-gray-400">AI</span>}
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