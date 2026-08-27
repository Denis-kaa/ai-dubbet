"use client";

import {
  useEffect, useRef, useState, useCallback, useMemo
} from "react";
import {
  Play, Pause, Volume2, VolumeX, Maximize, Minimize,
  Settings, RectangleHorizontal, Rows3
} from "lucide-react";
import { trackEvent } from "@/lib/analytics";

/* ── VTT ──────────────────────────────────────────── */
interface Cue { start: number; end: number; text: string }
const vttToSec = (t: string) =>
  t.trim().split(":").reduce((a, p) => a * 60 + parseFloat(p.replace(",", ".")), 0);

function parseVTT(vtt: string): Cue[] {
  const out: Cue[] = [];
  for (const blk of vtt.replace(/\r/g, "").split(/\n\n+/)) {
    const lines = blk.trim().split("\n");
    const ti = lines.findIndex(l => l.includes("-->"));
    if (ti < 0) continue;
    const [s, e] = lines[ti].split(" --> ");
    const text = lines.slice(ti + 1).filter(l => l.trim()).join(" ");
    if (text) out.push({ start: vttToSec(s), end: vttToSec(e), text });
  }
  return out;
}

/* ── Subtitle settings ────────────────────────────── */
interface SubSettings {
  fontSize: number;     // rem: 0.75 / 0.95 / 1.15 / 1.4
  bgOpacity: number;    // 0 – 1
  textColor: string;    // hex
  textOpacity: number;  // 0.7 / 0.85 / 1
}
const DEFAULT_SUB: SubSettings = {
  fontSize: 0.95, bgOpacity: 0.8, textColor: "#ffffff", textOpacity: 1,
};
const SUB_KEY = "dubber_sub_settings";

function loadSubSettings(): SubSettings {
  if (typeof window === "undefined") return DEFAULT_SUB;
  try { return { ...DEFAULT_SUB, ...JSON.parse(localStorage.getItem(SUB_KEY) || "{}") }; }
  catch { return DEFAULT_SUB; }
}

/* ── Icons ────────────────────────────────────────── */
function CcIcon({ on }: { on: boolean }) {
  return (
    <span
      className={`text-[10px] font-extrabold border-2 rounded px-[3px] py-[1px] leading-none tracking-tight select-none transition-colors ${
        on ? "border-blue-400 text-blue-400" : "border-white/40 text-white/40"
      }`}
    >
      CC
    </span>
  );
}

function HeadphonesIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 18v-6a9 9 0 0 1 18 0v6"/>
      <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3z"/>
      <path d="M3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/>
    </svg>
  );
}

/* ── Subtitle settings panel ──────────────────────── */
function SubPanel({
  settings, onChange, onClose,
}: {
  settings: SubSettings;
  onChange: (s: SubSettings) => void;
  onClose: () => void;
}) {
  const update = (partial: Partial<SubSettings>) => {
    const next = { ...settings, ...partial };
    onChange(next);
    localStorage.setItem(SUB_KEY, JSON.stringify(next));
  };

  const SIZES   = [{ v: 0.75, l: "S" }, { v: 0.95, l: "M" }, { v: 1.15, l: "L" }, { v: 1.4, l: "XL" }];
  const BGOPTS  = [{ v: 0,   l: "Yo'q" }, { v: 0.35, l: "25%" }, { v: 0.6, l: "50%" }, { v: 0.8, l: "75%" }, { v: 0.95, l: "100%" }];
  const COLORS  = [
    { v: "#ffffff", label: "Oq" },
    { v: "#ffd700", label: "Sariq" },
    { v: "#00e5ff", label: "Moviy" },
    { v: "#a3e635", label: "Yashil" },
  ];
  const OPACITIES = [{ v: 0.65, l: "Past" }, { v: 0.85, l: "O'rta" }, { v: 1.0, l: "To'liq" }];

  return (
    <div className="absolute bottom-[72px] right-2 z-50 bg-black/95 border border-white/10 rounded-2xl p-4 w-72 shadow-2xl text-white text-xs">
      <div className="flex items-center justify-between mb-3">
        <span className="font-bold text-sm">Subtitr sozlamalari</span>
        <button onClick={onClose} className="text-white/40 hover:text-white transition">✕</button>
      </div>

      {/* Font size */}
      <div className="mb-3">
        <p className="text-white/50 mb-1.5 uppercase tracking-wider text-[10px]">Shrift o'lchami</p>
        <div className="flex gap-1.5">
          {SIZES.map(s => (
            <button key={s.v} onClick={() => update({ fontSize: s.v })}
              className={`flex-1 py-1.5 rounded-lg font-bold transition text-sm ${
                settings.fontSize === s.v
                  ? "bg-blue-500 text-white"
                  : "bg-white/10 text-white/60 hover:bg-white/20"
              }`}
            >{s.l}</button>
          ))}
        </div>
      </div>

      {/* Background opacity */}
      <div className="mb-3">
        <p className="text-white/50 mb-1.5 uppercase tracking-wider text-[10px]">Fon shaffoflik</p>
        <div className="flex gap-1.5">
          {BGOPTS.map(o => (
            <button key={o.v} onClick={() => update({ bgOpacity: o.v })}
              className={`flex-1 py-1.5 rounded-lg transition text-[10px] font-semibold ${
                settings.bgOpacity === o.v
                  ? "bg-blue-500 text-white"
                  : "bg-white/10 text-white/50 hover:bg-white/20"
              }`}
            >{o.l}</button>
          ))}
        </div>
      </div>

      {/* Text color */}
      <div className="mb-3">
        <p className="text-white/50 mb-1.5 uppercase tracking-wider text-[10px]">Matn rangi</p>
        <div className="flex gap-2">
          {COLORS.map(c => (
            <button key={c.v} onClick={() => update({ textColor: c.v })}
              title={c.label}
              className={`w-8 h-8 rounded-full transition border-2 ${
                settings.textColor === c.v ? "border-blue-400 scale-110" : "border-transparent hover:border-white/30"
              }`}
              style={{ backgroundColor: c.v }}
            />
          ))}
        </div>
      </div>

      {/* Text opacity */}
      <div>
        <p className="text-white/50 mb-1.5 uppercase tracking-wider text-[10px]">Matn aniqligi</p>
        <div className="flex gap-1.5">
          {OPACITIES.map(o => (
            <button key={o.v} onClick={() => update({ textOpacity: o.v })}
              className={`flex-1 py-1.5 rounded-lg transition text-[10px] font-semibold ${
                settings.textOpacity === o.v
                  ? "bg-blue-500 text-white"
                  : "bg-white/10 text-white/50 hover:bg-white/20"
              }`}
            >{o.l}</button>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Props ────────────────────────────────────────── */
export interface VideoPlayerProps {
  src: string;
  subtitlesContent?: string;
  audioDownloadUrl?: string;
  className?: string;
  theaterMode?: boolean;
  onTheaterToggle?: () => void;
}

/* ── VideoPlayer ──────────────────────────────────── */
export default function VideoPlayer({
  src, subtitlesContent, audioDownloadUrl,
  className = "", theaterMode = false, onTheaterToggle,
}: VideoPlayerProps) {
  const videoRef     = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const hideTimer    = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const [playing,      setPlaying]      = useState(false);
  const [muted,        setMuted]        = useState(false);
  const [volume,       setVolume]       = useState(1);
  const [progress,     setProgress]     = useState(0);
  const [duration,     setDuration]     = useState(0);
  const [buffered,     setBuffered]     = useState(0);
  const [fullscreen,   setFullscreen]   = useState(false);
  const [showControls, setShowControls] = useState(true);
  const [showSubs,     setShowSubs]     = useState(true);
  const [showPanel,    setShowPanel]    = useState(false);
  const [subSettings,  setSubSettings]  = useState<SubSettings>(loadSubSettings);

  /* ── Cues ─────────────────────────────────────── */
  const cues = useMemo<Cue[]>(() => {
    if (!subtitlesContent) return [];
    return parseVTT(subtitlesContent);
  }, [subtitlesContent]);

  const currentCue = useMemo(
    () => cues.find(c => progress >= c.start && progress <= c.end) ?? null,
    [cues, progress]
  );

  /* ── Events ───────────────────────────────────── */
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onTime = () => setProgress(v.currentTime);
    const onDur  = () => setDuration(v.duration);
    const onBuf  = () => v.buffered.length > 0 && setBuffered(v.buffered.end(v.buffered.length - 1));
    const onEnd  = () => setPlaying(false);
    const onFS   = () => setFullscreen(!!document.fullscreenElement);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("durationchange", onDur);
    v.addEventListener("progress", onBuf);
    v.addEventListener("ended", onEnd);
    document.addEventListener("fullscreenchange", onFS);
    return () => {
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("durationchange", onDur);
      v.removeEventListener("progress", onBuf);
      v.removeEventListener("ended", onEnd);
      document.removeEventListener("fullscreenchange", onFS);
    };
  }, []);

  const resetHideTimer = useCallback(() => {
    setShowControls(true);
    clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => {
      if (videoRef.current && !videoRef.current.paused) setShowControls(false);
    }, 3000);
  }, []);

  /* ── Controls ─────────────────────────────────── */
  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    v.paused ? (v.play(), setPlaying(true)) : (v.pause(), setPlaying(false));
    resetHideTimer();
  };

  const seek = (e: React.MouseEvent<HTMLDivElement>) => {
    const v = videoRef.current;
    if (!v || !duration) return;
    const r = e.currentTarget.getBoundingClientRect();
    v.currentTime = ((e.clientX - r.left) / r.width) * duration;
    resetHideTimer();
  };

  const toggleMute = () => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = !muted;
    setMuted(!muted);
  };

  const changeVol = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = videoRef.current;
    const val = parseFloat(e.target.value);
    if (v) { v.volume = val; v.muted = val === 0; }
    setVolume(val);
    setMuted(val === 0);
  };

  const toggleFS = async () => {
    if (!document.fullscreenElement) await containerRef.current?.requestFullscreen();
    else await document.exitFullscreen();
  };

  const fmt = (s: number) =>
    `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, "0")}`;

  const progressPct = duration ? (progress / duration) * 100 : 0;
  const bufferedPct = duration ? (buffered / duration) * 100 : 0;
  const ctrlVisible = showControls || !playing;
  const hasSubs     = cues.length > 0;

  /* ── Subtitle style ───────────────────────────── */
  const subStyle: React.CSSProperties = {
    fontSize: `${subSettings.fontSize}rem`,
    color: subSettings.textColor,
    opacity: subSettings.textOpacity,
    backgroundColor: `rgba(0,0,0,${subSettings.bgOpacity})`,
  };

  return (
    <div
      ref={containerRef}
      className={`relative bg-black overflow-hidden aspect-video group select-none ${className}`}
      onMouseMove={resetHideTimer}
      onMouseLeave={() => playing && setShowControls(false)}
      onKeyDown={e => {
        if (e.code === "Space") { e.preventDefault(); togglePlay(); }
        if (e.code === "ArrowRight") { if (videoRef.current) videoRef.current.currentTime += 5; }
        if (e.code === "ArrowLeft")  { if (videoRef.current) videoRef.current.currentTime -= 5; }
      }}
      tabIndex={0}
    >
      <video
        ref={videoRef}
        src={src}
        className="w-full h-full object-contain"
        onClick={togglePlay}
        onDoubleClick={toggleFS}
      />

      {/* Subtitle overlay */}
      {showSubs && currentCue && (
        <div
          className="absolute left-0 right-0 flex justify-center px-6 pointer-events-none"
          style={{
            bottom: ctrlVisible ? "76px" : "16px",
            transition: "bottom 0.25s ease",
            zIndex: 20,
          }}
        >
          <span
            className="inline-block px-4 py-1.5 rounded-lg text-center leading-snug max-w-[88%]"
            style={subStyle}
          >
            {currentCue.text}
          </span>
        </div>
      )}

      {/* Subtitle settings panel */}
      {showPanel && hasSubs && (
        <SubPanel
          settings={subSettings}
          onChange={setSubSettings}
          onClose={() => setShowPanel(false)}
        />
      )}

      {/* Big play button */}
      {!playing && (
        <div
          onClick={togglePlay}
          className="absolute inset-0 flex items-center justify-center z-10 cursor-pointer"
        >
          <div className="w-20 h-20 bg-white/20 backdrop-blur-sm rounded-full flex items-center justify-center hover:bg-white/30 transition-all hover:scale-110">
            <Play className="w-8 h-8 text-white ml-1" fill="white" />
          </div>
        </div>
      )}

      {/* Controls bar */}
      <div
        className="absolute bottom-0 left-0 right-0 z-30 transition-opacity duration-300"
        style={{ opacity: ctrlVisible ? 1 : 0, pointerEvents: ctrlVisible ? "auto" : "none" }}
      >
        <div className="absolute inset-0 bg-gradient-to-t from-black/95 via-black/50 to-transparent pointer-events-none" />
        <div className="relative px-4 pb-4 pt-10">
          {/* Progress */}
          <div className="mb-3 cursor-pointer group/bar" onClick={seek}>
            <div className="h-1 group-hover/bar:h-1.5 bg-white/20 rounded-full relative transition-all duration-100">
              <div className="absolute inset-y-0 left-0 bg-white/30 rounded-full" style={{ width: `${bufferedPct}%` }} />
              <div className="absolute inset-y-0 left-0 bg-blue-500 rounded-full transition-none" style={{ width: `${progressPct}%` }} />
              <div
                className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3.5 h-3.5 bg-white rounded-full shadow opacity-0 group-hover/bar:opacity-100 transition-opacity"
                style={{ left: `${progressPct}%` }}
              />
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            {/* Play/Pause */}
            <button onClick={togglePlay} className="text-white hover:text-blue-400 transition flex-shrink-0">
              {playing ? <Pause className="w-5 h-5" fill="currentColor" /> : <Play className="w-5 h-5" fill="currentColor" />}
            </button>

            {/* Volume */}
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <button onClick={toggleMute} className="text-white hover:text-blue-400 transition">
                {muted || volume === 0 ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
              </button>
              <input
                type="range" min="0" max="1" step="0.05"
                value={muted ? 0 : volume}
                onChange={changeVol}
                className="hidden sm:block w-20 accent-blue-500 cursor-pointer"
              />
            </div>

            {/* Time */}
            <span className="text-white/70 text-sm font-mono ml-auto flex-shrink-0">
              {fmt(progress)} / {fmt(duration)}
            </span>

            {/* CC */}
            {hasSubs && (
              <button
                onClick={() => { setShowSubs(s => !s); setShowPanel(false); }}
                title="Subtitr yoqish/o'chirish"
                className="flex-shrink-0 hover:opacity-80 transition"
              >
                <CcIcon on={showSubs} />
              </button>
            )}

            {/* Subtitle settings gear */}
            {hasSubs && (
              <button
                onClick={() => setShowPanel(p => !p)}
                title="Subtitr sozlamalari"
                className={`flex-shrink-0 transition ${showPanel ? "text-blue-400" : "text-white/50 hover:text-white"}`}
              >
                <Settings className="w-4 h-4" />
              </button>
            )}

            {/* Audio download */}
            {audioDownloadUrl && (
              <a
                href={audioDownloadUrl}
                download
                title="Audio yuklab olish (MP3)"
                className="flex-shrink-0 text-white/50 hover:text-white transition"
                onClick={e => { e.stopPropagation(); trackEvent("video_downloaded", { format: "audio" }); }}
              >
                <HeadphonesIcon />
              </a>
            )}

            {/* Theater mode — faqat onTheaterToggle berilgan bo'lsa */}
            {onTheaterToggle && (
              <button
                onClick={onTheaterToggle}
                title={theaterMode ? "Oddiy ko'rinish" : "Keng ekran (Theater)"}
                className="hidden sm:block flex-shrink-0 text-white/50 hover:text-white transition"
              >
                {theaterMode
                  ? <Rows3 className="w-5 h-5" />
                  : <RectangleHorizontal className="w-5 h-5" />}
              </button>
            )}

            {/* Fullscreen */}
            <button onClick={toggleFS} className="text-white hover:text-blue-400 transition flex-shrink-0">
              {fullscreen ? <Minimize className="w-5 h-5" /> : <Maximize className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
