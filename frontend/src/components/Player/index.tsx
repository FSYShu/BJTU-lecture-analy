import { createContext, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import ArtPlayer from 'artplayer';
import Hls from 'hls.js';
import type { Transcript } from '@/types';

export type SeekFn = (t: number) => void;
export const SeekContext = createContext<SeekFn | null>(null);

interface PlayerProps {
  src: string;
  transcripts?: Transcript[];
  loading?: boolean;
  initialTime?: number;
  onTimeUpdate?: (t: number) => void;
  onSeekReady?: (seek: SeekFn) => void;
  children?: ReactNode;
}

function secToVttTime(sec: number): string {
  const safe = Math.max(0, Number.isFinite(sec) ? sec : 0);
  const ms = Math.floor((safe % 1) * 1000);
  const total = Math.floor(safe);
  const s = total % 60;
  const m = Math.floor(total / 60) % 60;
  const h = Math.floor(total / 3600);
  const pad = (n: number, w: number) => n.toString().padStart(w, '0');
  return `${pad(h, 2)}:${pad(m, 2)}:${pad(s, 2)}.${pad(ms, 3)}`;
}

function escapeVtt(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function transcriptsToVtt(transcripts: Transcript[]): string {
  const lines: string[] = ['WEBVTT', ''];
  for (const t of transcripts) {
    const text = t.text?.trim();
    if (!text) continue;
    lines.push(`${secToVttTime(t.start_sec)} --> ${secToVttTime(t.end_sec)}`);
    lines.push(escapeVtt(text));
    lines.push('');
  }
  return lines.join('\n');
}

export default function Player({ src, transcripts, loading, initialTime, onTimeUpdate, onSeekReady, children }: PlayerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const artRef = useRef<ArtPlayer | null>(null);
  const pendingSeekRef = useRef<number | null>(null);
  const subtitleUrlRef = useRef<string>('');
  const transcriptsRef = useRef<Transcript[] | undefined>(undefined);
  const hlsRef = useRef<Hls | null>(null);
  const [error, setError] = useState<string | null>(null);

  const seek = useCallback((t: number) => {
    if (!Number.isFinite(t) || t < 0) return;
    const art = artRef.current;
    if (!art) {
      pendingSeekRef.current = t;
      return;
    }
    art.currentTime = t;
  }, []);

  useEffect(() => {
    transcriptsRef.current = transcripts;
  }, [transcripts]);

  const setupSubtitles = useCallback(async () => {
    const art = artRef.current;
    if (!art) return;

    const currentTranscripts = transcriptsRef.current;

    if (!currentTranscripts || currentTranscripts.length === 0) {
      if (subtitleUrlRef.current) {
        URL.revokeObjectURL(subtitleUrlRef.current);
        subtitleUrlRef.current = '';
      }
      try { art.subtitle.show = false; } catch { /* noop */ }
      return;
    }

    const vtt = transcriptsToVtt(currentTranscripts);
    if (!vtt.trim() || vtt === 'WEBVTT') return;

    if (subtitleUrlRef.current) {
      URL.revokeObjectURL(subtitleUrlRef.current);
    }

    const blob = new Blob([vtt], { type: 'text/vtt' });
    const url = URL.createObjectURL(blob);
    subtitleUrlRef.current = url;

    try {
      await art.subtitle.switch(url, { type: 'vtt' });
      art.subtitle.show = true;
    } catch { /* noop */ }
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    if (artRef.current) {
      try { artRef.current.destroy(); } catch { /* noop */ }
      artRef.current = null;
    }
    if (hlsRef.current) {
      try { hlsRef.current.destroy(); } catch { /* noop */ }
      hlsRef.current = null;
    }

    pendingSeekRef.current = null;

    if (!src) return;

    if (initialTime && initialTime > 0) {
      pendingSeekRef.current = initialTime;
    }

    setError(null);

    const isM3u8 = src.includes('.m3u8');

    try {
      const art = new ArtPlayer({
        container,
        url: src,
        type: isM3u8 ? 'm3u8' : '',
        customType: {
          m3u8: (video: HTMLVideoElement, url: string) => {
            if (Hls.isSupported()) {
              const hls = new Hls();
              hlsRef.current = hls;
              hls.loadSource(url);
              hls.attachMedia(video);
            } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
              video.src = url;
            }
          },
        },
        volume: 1,
        autoplay: false,
        pip: true,
        setting: true,
        playbackRate: true,
        fullscreen: true,
        fullscreenWeb: true,
        mutex: true,
        backdrop: true,
        playsInline: true,
        theme: '#3b82f6',
        lang: 'zh-cn',
        moreVideoAttr: {
          crossOrigin: 'anonymous',
        },
      });

      artRef.current = art;

      art.on('ready', () => {
        if (pendingSeekRef.current !== null) {
          const t = pendingSeekRef.current;
          pendingSeekRef.current = null;
          art.currentTime = t;
        }
        setupSubtitles();
      });

      art.on('video:timeupdate', () => {
        onTimeUpdate?.(art.currentTime);
      });

      art.on('video:loadedmetadata', () => {
        if (pendingSeekRef.current !== null) {
          const t = pendingSeekRef.current;
          pendingSeekRef.current = null;
          art.currentTime = t;
        }
      });

      art.on('error', () => {
        setError('视频加载失败，可能需要先在浏览器中打开视频地址信任证书');
      });
    } catch (err) {
      console.error('[Player] ArtPlayer init error:', err);
      setError('播放器初始化失败');
    }

    return () => {
      if (hlsRef.current) {
        try { hlsRef.current.destroy(); } catch { /* noop */ }
        hlsRef.current = null;
      }
      try { artRef.current?.destroy(); } catch { /* noop */ }
      artRef.current = null;
      if (subtitleUrlRef.current) {
        URL.revokeObjectURL(subtitleUrlRef.current);
        subtitleUrlRef.current = '';
      }
      if (container) {
        container.innerHTML = '';
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  useEffect(() => {
    if (artRef.current) {
      setupSubtitles();
    }
  }, [transcripts, setupSubtitles]);

  useEffect(() => {
    onSeekReady?.(seek);
  }, [seek, onSeekReady]);

  return (
    <SeekContext.Provider value={seek}>
      <div key={src} ref={containerRef} style={{ aspectRatio: '16 / 9', position: 'relative' }} />
      {!src && (
        <div className="absolute inset-0 flex items-center justify-center text-gray-400 bg-black">
          {loading ? '加载视频中...' : '暂无视频'}
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-red-400 bg-black/80 z-10 p-4 text-center">
          {error}
        </div>
      )}
      {children}
    </SeekContext.Provider>
  );
}
