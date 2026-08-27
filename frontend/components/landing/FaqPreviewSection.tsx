"use client";
import { useState } from "react";
import Link from "next/link";
import { ChevronDown, ArrowRight } from "lucide-react";
import { FAQS } from "@/app/faq/faqs";

export default function FaqPreviewSection() {
  const [open, setOpen] = useState<number | null>(0);
  const preview = FAQS.slice(0, 4);

  return (
    <section className="w-full max-w-4xl mt-14 px-4 z-10">
      <h2 className="text-lg sm:text-2xl font-black text-gray-900 dark:text-white text-center mb-6 sm:mb-8">
        Ko'p so'raladigan savollar
      </h2>
      <div className="glass-card rounded-[24px] border border-black/5 dark:border-white/10 divide-y divide-black/5 dark:divide-white/10 max-w-2xl mx-auto overflow-hidden">
        {preview.map((item, i) => {
          const isOpen = open === i;
          return (
            <div key={item.q}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : i)}
                aria-expanded={isOpen}
                className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left"
              >
                <span className="text-sm font-bold text-gray-900 dark:text-white">{item.q}</span>
                <ChevronDown
                  className={`w-4 h-4 shrink-0 text-gray-400 transition-transform ${isOpen ? "rotate-180" : ""}`}
                />
              </button>
              {isOpen && (
                <p className="px-5 pb-4 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{item.a}</p>
              )}
            </div>
          );
        })}
      </div>
      <div className="flex justify-center mt-6">
        <Link
          href="/faq"
          className="inline-flex items-center gap-1.5 text-xs font-bold text-blue-600 dark:text-blue-400 hover:underline"
        >
          Barcha savollarni ko'rish <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </section>
  );
}
