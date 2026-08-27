"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { getLibrary, LibraryItem } from "@/lib/api";

export default function SocialProofSection() {
  const [items, setItems] = useState<LibraryItem[]>([]);

  useEffect(() => {
    getLibrary(6, 0)
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  if (items.length === 0) return null;

  return (
    <section className="w-full max-w-4xl mt-14 px-4 z-10">
      <div className="flex items-center justify-between mb-6 sm:mb-8">
        <h2 className="text-lg sm:text-2xl font-black text-gray-900 dark:text-white">
          GapirAI bilan dublyaj qilingan videolar
        </h2>
        <Link
          href="/library"
          className="hidden sm:inline-flex items-center gap-1 text-xs font-bold text-blue-600 dark:text-blue-400 hover:underline shrink-0"
        >
          Barchasini ko'rish <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4">
        {items.map((item) => (
          <Link
            key={item.job_id}
            href={`/library/${item.job_id}`}
            className="group rounded-2xl overflow-hidden bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/10 hover:border-violet-500/30 transition"
          >
            <div className="relative aspect-video bg-black/10 dark:bg-black/30">
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
            </div>
            <p className="px-2.5 py-2 text-[11px] font-semibold text-gray-700 dark:text-gray-300 line-clamp-2 leading-snug">
              {item.video_title || "Nomsiz video"}
            </p>
          </Link>
        ))}
      </div>
      <Link
        href="/library"
        className="sm:hidden mt-4 flex items-center justify-center gap-1 text-xs font-bold text-blue-600 dark:text-blue-400"
      >
        Barchasini ko'rish <ArrowRight className="w-3.5 h-3.5" />
      </Link>
    </section>
  );
}
