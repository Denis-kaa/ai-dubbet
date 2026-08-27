"use client";

import { RotateCcw, ChevronDown, CheckCircle2, Share2, Check, ShieldAlert } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Job, getDownloadUrl, getVideoUrl, formatDuration } from "@/lib/api";
import { useState, useEffect } from "react";
import VideoPlayer from "@/components/VideoPlayer";
import DownloadButton from "@/components/DownloadButton";
import { safeFileName } from "@/lib/download";
import { trackEvent } from "@/lib/analytics";

interface Props {
  job: Job;
  onReset: () => void;
}

export default function VideoResult({ job, onReset }: Props) {
  const [showText, setShowText] = useState(false);
  const [copied, setCopied] = useState(false);
  const videoUrl = getVideoUrl(job.job_id);
  const downloadUrl = getDownloadUrl(job.job_id);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 120, behavior: "smooth" });
    }
  }, []);

  const handleShare = async () => {
    const shareUrl = typeof window !== "undefined"
      ? `${window.location.origin}/video/${job.job_id}`
      : "";
    const title = job.video_title || "Dublyaj qilingan video";

    if (typeof navigator !== "undefined" && navigator.share) {
      try {
        await navigator.share({
          title,
          text: "GapirAI.uz orqali o'zbek tiliga dublyaj qilingan videoni ko'ring!",
          url: shareUrl || window.location.href,
        });
        return;
      } catch (err) {
        // User canceled or web share failed, fallback to copy
      }
    }

    if (typeof navigator !== "undefined" && navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(shareUrl || window.location.href);
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      } catch (err) {
        console.error("Clipboard copy failed:", err);
      }
    }
  };

  return (
    <div className="space-y-6">
      {/* ── Success Header ────────────────────────── */}
      <motion.div 
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-4 bg-emerald-500/10 border border-emerald-500/20 rounded-3xl px-6 py-4 transition-colors"
      >
        <div className="relative">
           <CheckCircle2 className="w-8 h-8 text-emerald-600 dark:text-emerald-500 transition-colors" strokeWidth={2.5} />
           <motion.div 
             className="absolute inset-0 bg-emerald-500 rounded-full blur-lg opacity-20"
             animate={{ scale: [1, 1.5, 1] }}
             transition={{ duration: 2, repeat: Infinity }}
           />
        </div>
        <div>
          <h3 className="text-sm font-black text-emerald-600 dark:text-emerald-400 uppercase tracking-widest transition-colors">Dublyaj Tayyor!</h3>
          <p className="text-[11px] text-emerald-600/60 dark:text-emerald-400/60 font-medium transition-colors">Video muvaffaqiyatli qayta ishlandi</p>
        </div>
      </motion.div>

      {job.content_flagged && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-start gap-3 bg-amber-500/10 border border-amber-500/20 rounded-3xl px-6 py-4 transition-colors"
        >
          <ShieldAlert className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <p className="text-xs text-amber-700 dark:text-amber-400 leading-relaxed">
            Video tayyor va shaxsiy foydalanish uchun mavjud, lekin kontent siyosatimizga ko'ra
            (diniy, 18+, zo'ravonlik yoki shunga o'xshash kategoriya) <strong>Ommaviy videolar</strong> kutubxonasiga
            chiqarilmaydi. Iltimos, keyingi safar bunday kontentni yubormaslikni so'raymiz.
          </p>
        </motion.div>
      )}

      {/* ── Video Player ──────────────────────────── */}
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.1 }}
        className="rounded-3xl overflow-hidden shadow-2xl ring-1 ring-black/5 dark:ring-white/10"
      >
        <VideoPlayer
          key={videoUrl}
          src={videoUrl}
          subtitlesContent={job.uzbek_srt_content}
          className="rounded-3xl"
        />
      </motion.div>

      {/* ── Info & Actions ────────────────────────── */}
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-6 px-1">
          <div className="space-y-1">
            <h4 className="text-base font-bold text-gray-900 dark:text-white line-clamp-2 leading-tight transition-colors">
              {job.video_title || "Dublyaj qilingan video"}
            </h4>
            <div className="flex items-center gap-2">
               <span className="text-[10px] font-bold text-gray-400 dark:text-gray-500 uppercase transition-colors">Davomiyligi</span>
               <span className="text-[10px] font-mono text-blue-600 dark:text-blue-400 transition-colors">{formatDuration(job.video_duration || 0)}</span>
            </div>
          </div>
          
          <div className="flex gap-2">
            <motion.button 
              onClick={handleShare}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="px-3.5 py-3 bg-black/5 dark:bg-white/[0.03] border border-black/5 dark:border-white/[0.05] rounded-2xl hover:bg-black/10 dark:hover:bg-white/[0.08] transition-all flex items-center gap-1.5"
              title="Ulashish"
            >
              {copied ? (
                <>
                  <Check size={18} className="text-emerald-500 transition-colors" />
                  <span className="text-xs font-bold text-emerald-500">Nusxalandi!</span>
                </>
              ) : (
                <Share2 size={18} className="text-gray-500 dark:text-gray-400 transition-colors" />
              )}
            </motion.button>
          </div>
        </div>

        <DownloadButton
          url={downloadUrl}
          filename={safeFileName(job.video_title, "video")}
          label="Videoni yuklab olish"
          hint="Katta fayl bo'lsa, yuklab olish bir necha daqiqa davom etishi mumkin."
        />
      </div>

      {/* ── Translation Text Accordion ────────────── */}
      {job.translated_text && (
        <div className="glass-input rounded-2xl overflow-hidden border border-black/5 dark:border-white/[0.03] transition-colors">
          <button 
            onClick={() => setShowText(!showText)}
            className="w-full flex items-center justify-between px-6 py-4 hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition-colors"
          >
            <div className="flex items-center gap-3">
               <div className="w-1.5 h-1.5 rounded-full bg-blue-500"></div>
               <span className="text-[11px] font-bold text-gray-500 uppercase tracking-widest transition-colors">O'zbekcha matn</span>
            </div>
            <ChevronDown 
              size={14} 
              className={`text-gray-400 dark:text-gray-600 transition-transform duration-300 ${showText ? "rotate-180" : ""}`} 
            />
          </button>
          
          <AnimatePresence>
            {showText && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="px-6 pb-6 pt-1 text-xs text-gray-600 dark:text-gray-400 leading-relaxed max-h-48 overflow-y-auto">
                   <p className="whitespace-pre-wrap transition-colors">{job.translated_text}</p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* ── Reset Button ──────────────────────────── */}
      <motion.button
        onClick={onReset}
        whileHover={{ scale: 1.01 }}
        className="w-full flex items-center justify-center gap-3
                   py-4 rounded-[22px] border border-black/5 dark:border-white/[0.04]
                   text-gray-400 dark:text-gray-500 hover:text-gray-900 dark:hover:text-white hover:bg-black/[0.02] dark:hover:bg-white/[0.02]
                   transition-all duration-300 text-[11px] font-bold uppercase tracking-widest"
      >
        <RotateCcw size={14} />
        Yangi video dublyaj qilish
      </motion.button>
    </div>
  );
}
