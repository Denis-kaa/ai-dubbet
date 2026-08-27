'use client'
import { useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, HelpCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { motion } from 'framer-motion'
import { FAQS } from './faqs'

export default function FAQPage() {
  const [openIndex, setOpenIndex] = useState<number | null>(null)

  return (
    <div className="min-h-screen relative flex flex-col items-center py-12 px-4 sm:px-6 transition-colors duration-300">
      <MeshBackground />

      <div className="w-full max-w-3xl z-10 space-y-8">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-slate-400 hover:text-gray-900 dark:hover:text-white transition duration-200"
        >
          <ArrowLeft className="w-4 h-4" /> Bosh sahifaga qaytish
        </Link>

        <div className="glass-card border border-black/5 dark:border-white/5 rounded-[32px] p-6 sm:p-10 shadow-2xl space-y-6">
          <div className="flex items-center gap-3 border-b border-black/5 dark:border-slate-800/80 pb-6">
            <div className="w-10 h-10 rounded-xl bg-violet-500/10 text-violet-500 dark:text-violet-400 flex items-center justify-center">
              <HelpCircle className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl sm:text-2xl font-black text-gray-900 dark:text-white">Yordam va Savollar (FAQ)</h1>
              <p className="text-xs text-gray-500 dark:text-slate-500">Eng ko'p beriladigan savollarga javoblar</p>
            </div>
          </div>

          <div className="space-y-4">
            {FAQS.map((faq, i) => {
              const isOpen = openIndex === i
              return (
                <div
                  key={i}
                  className="border border-black/5 dark:border-slate-800/80 bg-black/[0.02] dark:bg-slate-950/40 rounded-2xl overflow-hidden transition-all duration-300"
                >
                  <button
                    onClick={() => setOpenIndex(isOpen ? null : i)}
                    aria-expanded={isOpen}
                    aria-controls={`faq-answer-${i}`}
                    className="w-full px-5 py-4 flex items-center justify-between text-left text-xs sm:text-sm font-bold text-gray-900 dark:text-slate-100 hover:text-gray-700 dark:hover:text-white transition"
                  >
                    <span>{faq.q}</span>
                    {isOpen ? <ChevronUp className="w-4 h-4 text-violet-500" /> : <ChevronDown className="w-4 h-4 text-gray-400 dark:text-slate-500" />}
                  </button>

                  {/* Always rendered so the answer text ships in the SSR HTML —
                      crawlers (and the FAQPage schema in layout.tsx) need it. */}
                  <motion.div
                    id={`faq-answer-${i}`}
                    initial={false}
                    animate={{ height: isOpen ? "auto" : 0 }}
                    transition={{ duration: 0.25 }}
                    className="overflow-hidden"
                  >
                    <div className="px-5 pb-5 pt-1 text-xs sm:text-sm text-gray-600 dark:text-slate-400 border-t border-black/5 dark:border-slate-800/40 leading-relaxed">
                      {faq.a}
                    </div>
                  </motion.div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

function MeshBackground() {
  return (
    <div className="mesh-gradient">
      <div className="mesh-gradient-blob blob-1" />
      <div className="mesh-gradient-blob blob-2" />
      <div className="mesh-gradient-blob blob-3" />
    </div>
  );
}
