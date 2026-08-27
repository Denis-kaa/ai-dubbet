"use client";

import { useState } from "react";
import Link from "next/link";
import { ClipboardPaste, Loader2, Sparkles, Youtube } from "lucide-react";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { createAnalysis, saveAnalysisId, ANALYSIS_LANGUAGE_OPTIONS } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

export default function AnalysisUrlForm() {
  const router = useRouter();
  const { isLoggedIn } = useAuth();
  const [url, setUrl] = useState("");
  const [language, setLanguage] = useState("uz");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) setUrl(text);
    } catch {}
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    if (!isLoggedIn) {
      router.push("/login");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const { analysis_id } = await createAnalysis(url, language);
      saveAnalysisId(analysis_id);
      router.push(`/video-analysis/${analysis_id}`);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Xatolik yuz berdi. Qayta urinib ko'ring.");
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-2">
        <label className="text-[10px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest ml-1">
          YouTube Havolasi
        </label>
        <div className="glass-input flex items-center gap-2.5 sm:gap-3 px-3.5 sm:px-5 py-3 sm:py-4 rounded-2xl sm:rounded-3xl relative overflow-hidden group transition-all duration-300">
          <div className="absolute inset-0 bg-gradient-to-r from-blue-500/5 to-violet-500/5 opacity-0 group-focus-within:opacity-100 transition-opacity duration-300 pointer-events-none" />
          <Youtube className="w-5 h-5 sm:w-6 sm:h-6 text-blue-500 flex-shrink-0" />
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="YouTube havolasini kiriting..."
            className="flex-1 bg-transparent text-black dark:text-white placeholder-slate-400 dark:placeholder-gray-600 text-xs sm:text-sm focus:outline-none font-medium"
          />
          <button
            type="button"
            onClick={handlePaste}
            className="flex items-center gap-1.5 text-[10px] sm:text-[11px] font-bold text-blue-600 dark:text-blue-400 hover:text-blue-500 bg-blue-500/10 hover:bg-blue-500/20 rounded-xl px-3 sm:px-4 py-1.5 sm:py-2 transition-all flex-shrink-0"
          >
            <ClipboardPaste size={13} />
            <span className="inline">Nusxani qo'yish</span>
          </button>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-[10px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest ml-1">
          Tahlil tili
        </label>
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="glass-input w-full px-3.5 sm:px-5 py-3 sm:py-4 rounded-2xl sm:rounded-3xl text-black dark:text-white text-xs sm:text-sm font-medium focus:outline-none"
        >
          {ANALYSIS_LANGUAGE_OPTIONS.map((opt) => (
            <option key={opt.code} value={opt.code}>{opt.label}</option>
          ))}
        </select>
        <p className="text-[10px] text-slate-400 dark:text-gray-600 ml-1">
          Transkript doim video'ning original tilida qoladi — bu faqat xulosa, chapterlar, konspekt va test qaysi tilda chiqishini belgilaydi.
        </p>
      </div>

      {!isLoggedIn && (
        <p className="text-[11px] font-semibold text-amber-600 dark:text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-2xl px-4 py-3">
          Video tahlili uchun{" "}
          <Link href="/login" className="underline hover:text-amber-500">kiring</Link>
          {" "}yoki{" "}
          <Link href="/register" className="underline hover:text-amber-500">ro'yxatdan o'ting</Link>.
        </p>
      )}

      {error && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="bg-blue-500/10 border border-blue-500/20 rounded-2xl p-4 flex gap-3 items-center"
        >
          <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          <p className="text-xs font-semibold text-blue-600 dark:text-blue-400">{error}</p>
        </motion.div>
      )}

      <motion.button
        type="submit"
        disabled={loading || !url.trim()}
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.98 }}
        className="w-full flex items-center justify-center gap-3
                   btn-premium disabled:from-gray-300 disabled:to-gray-200 dark:disabled:from-gray-800 dark:disabled:to-gray-800 disabled:opacity-50 disabled:pointer-events-none
                   text-white font-extrabold py-4 sm:py-5 rounded-2xl sm:rounded-[24px]
                   transition-all duration-300 text-xs sm:text-sm shadow-xl"
      >
        {loading ? (
          <><Loader2 size={18} className="animate-spin" /> Tahlil boshlanmoqda...</>
        ) : (
          <><Sparkles size={18} /> Video tahlil qilish</>
        )}
      </motion.button>

      <div className="flex flex-wrap justify-center gap-4 sm:gap-8 pt-2">
        {["Xulosa", "Chapterlar", "Test", "Savol-javob"].map((label, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
            <span className="text-[10px] font-bold text-gray-400 dark:text-gray-600 uppercase tracking-tighter">{label}</span>
          </div>
        ))}
      </div>
    </form>
  );
}
