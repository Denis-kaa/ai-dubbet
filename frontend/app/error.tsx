'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { AlertTriangle, RotateCcw } from 'lucide-react'

// Next.js App Router error boundary -- ushbu segment ichida (yoki uning
// bolalarida) render vaqtida ushlanmagan xato yuz bersa shu ko'rsatiladi.
// Avval bunday holat Next.js'ning standart (brendlanmagan, dasturchiga
// mo'ljallangan) xato ekranini ko'rsatardi -- bu fayl mavjud bo'lmagani
// aniqlangan (2026-08-20).
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Brauzer konsoliga to'liq xatoni yozamiz (dasturchi debug uchun) --
    // foydalanuvchiga esa faqat xavfsiz umumiy matn ko'rsatiladi.
    console.error(error)
  }, [error])

  return (
    <div className="min-h-screen flex items-center justify-center px-4 transition-colors">
      <div className="glass-card rounded-[24px] p-8 max-w-md w-full text-center space-y-5">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-blue-500/10 text-blue-500 mx-auto">
          <AlertTriangle className="w-7 h-7" />
        </div>
        <div className="space-y-2">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">Nimadur noto'g'ri ketdi</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">
            Sahifani yuklashda kutilmagan xatolik yuz berdi. Qaytadan urinib ko'ring — muammo davom etsa, bosh sahifaga qayting.
          </p>
          {error.digest && (
            <p className="text-[10px] text-gray-400 dark:text-gray-600 font-mono">Xato ID: {error.digest}</p>
          )}
        </div>
        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={reset}
            className="btn-premium flex-1 py-3 rounded-2xl font-bold text-sm inline-flex items-center justify-center gap-2"
          >
            <RotateCcw className="w-4 h-4" /> Qaytadan urinish
          </button>
          <Link
            href="/"
            className="flex-1 py-3 glass-input rounded-2xl font-bold text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-all text-sm inline-flex items-center justify-center"
          >
            Bosh sahifa
          </Link>
        </div>
      </div>
    </div>
  )
}
