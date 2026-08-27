"use client";
import { ArrowUp } from "lucide-react";

export default function FinalCtaSection() {
  const scrollToStart = () => {
    document.getElementById("start")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <section className="w-full max-w-2xl mt-16 px-4 z-10">
      <div className="glass-card rounded-[24px] sm:rounded-[32px] p-8 sm:p-10 border border-black/5 dark:border-white/10 text-center">
        <h2 className="text-xl sm:text-2xl font-black text-gray-900 dark:text-white mb-2">
          Videongizni hoziroq o'zbekchalashtiring
        </h2>
        <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 mb-6 max-w-md mx-auto">
          45 daqiqagacha bo'lgan videolar bepul. YouTube havolasini kiriting va bir necha daqiqada tayyor bo'lsin.
        </p>
        <button
          type="button"
          onClick={scrollToStart}
          className="btn-premium inline-flex items-center gap-2 px-6 py-3.5 rounded-2xl font-bold text-sm"
        >
          <ArrowUp className="w-4 h-4" /> Boshlash
        </button>
      </div>
    </section>
  );
}
