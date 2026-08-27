"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

declare global {
  interface Window {
    YT: any;
    onYouTubeIframeAPIReady: () => void;
  }
}

export interface YouTubePlayerHandle {
  seekTo: (seconds: number) => void;
}

interface Props {
  videoId: string;
  className?: string;
}

let apiLoadPromise: Promise<void> | null = null;

function loadYouTubeApi(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.YT && window.YT.Player) return Promise.resolve();
  if (apiLoadPromise) return apiLoadPromise;

  apiLoadPromise = new Promise((resolve) => {
    const prevReady = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      prevReady?.();
      resolve();
    };
    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(script);
  });
  return apiLoadPromise;
}

const YouTubePlayer = forwardRef<YouTubePlayerHandle, Props>(({ videoId, className }, ref) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<any>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadYouTubeApi().then(() => {
      if (cancelled || !containerRef.current) return;
      playerRef.current = new window.YT.Player(containerRef.current, {
        videoId,
        playerVars: { rel: 0, modestbranding: 1 },
        events: {
          onReady: () => setReady(true),
        },
      });
    });
    return () => {
      cancelled = true;
      playerRef.current?.destroy?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId]);

  useImperativeHandle(ref, () => ({
    seekTo: (seconds: number) => {
      if (!ready || !playerRef.current) return;
      playerRef.current.seekTo(seconds, true);
      playerRef.current.playVideo();
    },
  }));

  return (
    <div className={`relative w-full aspect-video bg-black rounded-2xl overflow-hidden ${className || ""}`}>
      <div ref={containerRef} className="absolute inset-0 w-full h-full" />
    </div>
  );
});

YouTubePlayer.displayName = "YouTubePlayer";
export default YouTubePlayer;
