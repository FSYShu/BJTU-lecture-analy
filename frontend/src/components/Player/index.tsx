import { createContext, useCallback, useEffect, useRef, useState } from 'react';
import videojs from 'video.js';
import 'video.js/dist/video-js.css';
import type { Transcript } from '@/types';

export const SeekContext = createContext<(t: number) => void>(() => {});

interface PlayerProps {
  src: string;
  transcripts?: Transcript[];
  loading?: boolean;
  initialTime?: number;
  onTimeUpdate?: (t: number) => void;
  onSeekReady?: (seek: (t: number) => void) => void;
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

export default function Player({ src, transcripts, loading, initialTime, onTimeUpdate, onSeekReady }: PlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<any>(null);
  const pendingSeekRef = useRef<number | null>(null);
  const remoteTrackRef = useRef<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [playerReady, setPlayerReady] = useState(false);

  // 元数据没就绪时 currentTime() 会失效：先记下来，等 loadedmetadata 再跳。
  const seek = useCallback((t: number) => {
    if (!Number.isFinite(t) || t < 0) return;
    const player = playerRef.current;
    if (!player || player.readyState() === 0) {
      pendingSeekRef.current = t;
      return;
    }
    player.currentTime(t);
  }, []);

  useEffect(() => {
    if (!videoRef.current) return;

    if (playerRef.current) {
      playerRef.current.dispose();
      playerRef.current = null;
      remoteTrackRef.current = null;
    }
    pendingSeekRef.current = null;
    setPlayerReady(false);

    if (!src) return;

    if (initialTime && initialTime > 0) {
      pendingSeekRef.current = initialTime;
    }

    setError(null);
    try {
      playerRef.current = videojs(videoRef.current, {
        controls: true,
        fluid: true,
        sources: [{
          src,
          type: src.includes('.m3u8') ? 'application/x-mpegURL' : undefined,
        }],
      });
      playerRef.current.on('timeupdate', () => onTimeUpdate?.(playerRef.current.currentTime()));
      playerRef.current.on('loadedmetadata', () => {
        const pending = pendingSeekRef.current;
        if (pending === null) return;
        pendingSeekRef.current = null;
        const duration = playerRef.current?.duration?.() ?? 0;
        playerRef.current?.currentTime(duration > 0 ? Math.min(pending, duration) : pending);
      });
      playerRef.current.on('error', () => {
        const code = playerRef.current?.error()?.code;
        setError(`视频加载失败 (错误码 ${code})，可能需要先在浏览器中打开视频地址信任证书`);
      });
      setPlayerReady(true);
    } catch (err) {
      console.error('[Player] video.js init error:', err);
      setError('播放器初始化失败');
    }
    return () => {
      playerRef.current?.dispose();
      playerRef.current = null;
      remoteTrackRef.current = null;
      setPlayerReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  // 字幕轨道：transcripts 或 player 变化时动态添加，不重新初始化播放器。
  useEffect(() => {
    if (!playerReady) return;
    const player = playerRef.current;
    if (!player) return;

    let disposed = false;
    let createdUrl: string | null = null;
    let createdTrack: any = null;

    const setup = () => {
      if (disposed) return;

      if (remoteTrackRef.current) {
        try { player.removeRemoteTextTrack(remoteTrackRef.current); } catch { /* noop */ }
        remoteTrackRef.current = null;
      }
      if (!transcripts || transcripts.length === 0) return;

      const vtt = transcriptsToVtt(transcripts);
      if (!vtt.trim() || vtt === 'WEBVTT') return;

      const blob = new Blob([vtt], { type: 'text/vtt' });
      const url = URL.createObjectURL(blob);
      createdUrl = url;

      const track = player.addRemoteTextTrack({
        kind: 'subtitles',
        src: url,
        srclang: 'zh',
        label: '中文',
      }, false);
      createdTrack = track;
      remoteTrackRef.current = track;
      if (track) track.mode = 'showing';
    };

    player.ready(setup);

    return () => {
      disposed = true;
      if (createdTrack) {
        try { player.removeRemoteTextTrack(createdTrack); } catch { /* noop */ }
      }
      if (createdUrl) URL.revokeObjectURL(createdUrl);
      if (remoteTrackRef.current === createdTrack) remoteTrackRef.current = null;
    };
  }, [transcripts, playerReady]);

  useEffect(() => {
    onSeekReady?.(seek);
  }, [seek, onSeekReady]);

  return (
    <div data-vjs-player style={{ minHeight: '360px', position: 'relative' }}>
      <video ref={videoRef} className="video-js vjs-big-play-centered" playsInline />
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
    </div>
  );
}
