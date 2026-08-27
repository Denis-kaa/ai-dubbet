"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Play } from "lucide-react";
import { getLibrary, formatDuration, LibraryItem } from "@/lib/api";

export default function BeforeAfterSection() {
  const [item, setItem] = useState<LibraryItem | null>(null);

  useEffect(() => {
    getLibrary(1, 0)
      .then((res) => setItem(res[0] ?? null))
      .catch(() => setItem(null));
  }, []);

  if (!item) return null;

  return (
    <section className="w-full max-w-4xl mt-14 px-4 z-10">
      <h2 className="text-lg sm:text-2xl font-black text-gray-900 dark:text-white text-center mb-2">
        Natijani ko'ring
      </h2>
      <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 text-center mb-6 sm:mb-8 max-w-lg mx-auto">
        Kutubxonamizdagi haqiqiy, GapirAI orqali dublyaj qilingan videolardan biri:
      </p>
      <Link
        href={`/library/${item.job_id}`}
        className="group glass-card rounded-[24px] p-4 sm:p-5 border border-black/5 dark:border-white/10 flex flex-col sm:flex-row items-center gap-4 sm:gap-5 max-w-xl mx-auto hover:border-violet-500/30 transition"
      >
        <div className="relative w-full sm:w-48 aspect-video shrink-0 rounded-2xl overflow-hidden bg-black/10 dark:bg-black/30">
          {item.video_thumbnail && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={item.video_thumbnail}
              alt={item.video_title || ""}
              className="w-full h-full object-cover"
              onError={(e) => { e.currentTarget.style.display = "none"; }}
              onLoad={(e) => {
                // YouTube javob bermasa ham 404'ni 120x90 placeholder rasm bilan qaytaradi
                if (e.currentTarget.naturalWidth <= 120) e.currentTarget.style.display = "none";
              }}
            />
          )}
          <div className="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/30 transition">
            <div className="w-10 h-10 rounded-full bg-white/90 flex items-center justify-center">
              <Play className="w-4 h-4 text-gray-900 ml-0.5" fill="currentColor" />
            </div>
          </div>
          {item.video_duration != null && (
            <span className="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 rounded bg-black/70 text-white text-[10px] font-bold">
              {formatDuration(item.video_duration)}
            </span>
          )}
        </div>
        <div className="min-w-0 flex-1 text-left">
          <p className="text-xs font-bold text-violet-600 dark:text-violet-400 uppercase tracking-widest mb-1">
            O'zbekcha dublyaj
          </p>
          <h3 className="text-sm font-bold text-gray-900 dark:text-white line-clamp-2 mb-1">
            {item.video_title || "Nomsiz video"}
          </h3>
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 dark:text-blue-400">
            Tomosha qilish <ArrowRight className="w-3.5 h-3.5" />
          </span>
        </div>
      </Link>
    </section>
  );
}
