import { createContext, useCallback, useEffect, useRef } from 'react';
import videojs from 'video.js';
import 'video.js/dist/video-js.css';

// 播放器跳转能力上下文。由 CourseDetail 提供 seek 函数，供字幕/重点/导图消费。
export const SeekContext = createContext<(t: number) => void>(() => {});

interface PlayerProps {
  src: string;
  onTimeUpdate?: (t: number) => void;
  onSeekReady?: (seek: (t: number) => void) => void;
}

export default function Player({ src, onTimeUpdate, onSeekReady }: PlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<any>(null);

  const seek = useCallback((t: number) => {
    playerRef.current?.currentTime(t);
  }, []);

  useEffect(() => {
    if (!videoRef.current || !src) return;
    playerRef.current = videojs(videoRef.current, {
      controls: true,
      fluid: true,
      sources: [{ src }],
    });
    playerRef.current.on('timeupdate', () => onTimeUpdate?.(playerRef.current.currentTime()));
    return () => {
      playerRef.current?.dispose();
      playerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  // 把 seek 函数上报给父组件（父组件再通过 SeekContext 下发）
  useEffect(() => {
    onSeekReady?.(seek);
  }, [seek, onSeekReady]);

  if (!src) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400 bg-black">
        暂无视频
      </div>
    );
  }

  return (
    <div data-vjs-player>
      <video ref={videoRef} className="video-js" />
    </div>
  );
}
