import { createContext, useCallback, useEffect, useRef, useState } from 'react';
import videojs from 'video.js';
import 'video.js/dist/video-js.css';

export const SeekContext = createContext<(t: number) => void>(() => {});

interface PlayerProps {
  src: string;
  onTimeUpdate?: (t: number) => void;
  onSeekReady?: (seek: (t: number) => void) => void;
}

export default function Player({ src, onTimeUpdate, onSeekReady }: PlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<any>(null);
  const [error, setError] = useState<string | null>(null);

  const seek = useCallback((t: number) => {
    playerRef.current?.currentTime(t);
  }, []);

  useEffect(() => {
    if (!videoRef.current) return;

    if (playerRef.current) {
      playerRef.current.dispose();
      playerRef.current = null;
    }

    if (!src) return;

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
      playerRef.current.on('error', () => {
        const code = playerRef.current?.error()?.code;
        setError(`视频加载失败 (错误码 ${code})，可能需要先在浏览器中打开视频地址信任证书`);
      });
    } catch (err) {
      console.error('[Player] video.js init error:', err);
      setError('播放器初始化失败');
    }
    return () => {
      playerRef.current?.dispose();
      playerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  useEffect(() => {
    onSeekReady?.(seek);
  }, [seek, onSeekReady]);

  return (
    <div data-vjs-player style={{ minHeight: '360px', position: 'relative' }}>
      <video ref={videoRef} className="video-js vjs-big-play-centered" playsInline />
      {!src && (
        <div className="absolute inset-0 flex items-center justify-center text-gray-400 bg-black">
          暂无视频
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
