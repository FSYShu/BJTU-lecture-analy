import { useEffect, useRef, useState } from 'react';
import videojs from 'video.js';
import 'video.js/dist/video-js.css';

interface PlayerProps {
  src: string;
  onTimeUpdate?: (t: number) => void;
}

export default function Player({ src, onTimeUpdate }: PlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<any>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!videoRef.current) return;
    playerRef.current = videojs(videoRef.current, { controls: true, fluid: true, sources: [{ src }] });
    playerRef.current.on('timeupdate', () => onTimeUpdate?.(playerRef.current.currentTime()));
    setReady(true);
    return () => playerRef.current?.dispose();
  }, [src]);

  // 暴露跳转能力
  const seek = (t: number) => playerRef.current?.currentTime(t);

  return (
    <div data-vjs-player>
      <video ref={videoRef} className="video-js" />
      {ready && <SeekContext.Provider value={seek}>{null}</SeekContext.Provider>}
    </div>
  );
}

import { createContext } from 'react';
export const SeekContext = createContext<(t: number) => void>(() => {});