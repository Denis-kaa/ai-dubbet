'use client'

import Link from 'next/link'
import { motion } from 'framer-motion'
import { ArrowLeft, Sparkles, Cpu, Mic, Zap, Shield, HeartHandshake, CheckCircle2 } from 'lucide-react'
import ThemeToggle from '@/components/ThemeToggle'
import Footer from '@/components/Footer'

function MeshBackground() {
  return (
    <div className="mesh-gradient">
      <div className="mesh-gradient-blob blob-1" />
      <div className="mesh-gradient-blob blob-2" />
      <div className="mesh-gradient-blob blob-3" />
    </div>
  )
}

export default function AboutClient() {
  return (
    <main className="relative min-h-screen flex flex-col items-center justify-between pt-24 sm:pt-28 pb-0 px-4 sm:px-8 overflow-x-hidden transition-colors duration-300">
      <MeshBackground />

      {/* Top Header Bar */}
      <header className="absolute top-3 sm:top-6 left-3 sm:left-6 right-3 sm:right-6 z-50 flex items-center justify-between pointer-events-none gap-2">
        <Link href="/" className="pointer-events-auto flex items-center transition duration-300 hover:scale-105">
          <img src="/logo.webp" alt="GapirAI.uz Logo" width={160} height={40} className="h-10 sm:h-16 md:h-24 w-auto object-contain dark:hidden drop-shadow-md" style={{ maxWidth: "calc(100vw - 150px)" }} />
          <img src="/logodark.webp" alt="GapirAI.uz Logo" width={160} height={40} className="h-10 sm:h-16 md:h-24 w-auto object-contain hidden dark:block drop-shadow-md" style={{ maxWidth: "calc(100vw - 150px)" }} />
        </Link>

        <div className="pointer-events-auto flex items-center gap-3">
          <Link
            href="/"
            className="flex items-center gap-2 h-10 px-4 bg-white/80 dark:bg-white/10 hover:bg-white dark:hover:bg-white/20 border border-blue-500/20 dark:border-white/15 text-gray-900 dark:text-white text-xs font-bold rounded-2xl shadow-sm transition backdrop-blur-md hover:scale-105 active:scale-95"
          >
            <ArrowLeft className="w-4 h-4 text-blue-500" />
            Bosh sahifa
          </Link>
          <ThemeToggle />
        </div>
      </header>

      {/* Main Content Container */}
      <div className="w-full max-w-4xl z-10 space-y-12 my-6">

        {/* Hero Banner Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="glass-card rounded-[32px] p-8 sm:p-12 text-center space-y-4 relative overflow-hidden"
        >
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-600 dark:text-blue-400 text-xs font-bold uppercase tracking-widest">
            <Sparkles className="w-4 h-4" /> Innovatsion Platforma
          </div>

          <h1 className="text-3xl sm:text-5xl font-black text-black dark:text-white tracking-tight leading-tight">
            GapirAI<span className="text-blue-500">.uz</span> haqida
          </h1>

          <p className="text-sm sm:text-base text-gray-600 dark:text-gray-300 max-w-2xl mx-auto leading-relaxed font-medium">
            <strong className="text-blue-600 dark:text-blue-400 font-semibold">GapirAI.uz</strong> (Gapir AI) — bu YouTube va turli manbalardagi videolarni Sun'iy Intellekt (AI) texnologiyalari yordamida soniyalar ichida avtomatik tarzda o'zbek tiliga dublyaj (dublaj) va tarjima qilib beruvchi eng ilg'or milliy dublyaj programmasi va platformadir.
          </p>

          <div className="pt-4 flex justify-center">
            <Link
              href="/"
              className="bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-500 hover:to-violet-500 text-white font-extrabold px-8 py-3.5 rounded-2xl transition duration-300 shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 active:scale-95 text-sm"
            >
              Dublyajni sinab ko'rish
            </Link>
          </div>
        </motion.div>

        {/* Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="glass-card rounded-[28px] p-6 sm:p-8 space-y-3"
          >
            <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-500">
              <Zap className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-black dark:text-white">Avtomatik va Tezkor</h3>
            <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed font-medium">
              Hech qanday qo'lda ishlov berish talab etilmaydi. YouTube havolasini kiritasiz va platformamiz avtomatik ravishda videoni yuklaydi, ovozini ajratadi va o'zbek tiliga dublyaj qiladi.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="glass-card rounded-[28px] p-6 sm:p-8 space-y-3"
          >
            <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-500">
              <Cpu className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-black dark:text-white">Whisper + GPT-4o mini Texnologiyasi</h3>
            <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed font-medium">
              OpenAI Whisper orqali nutq aniq matnga o'tkaziladi. GPT-4o mini esa o'zbek tilining boy va oqilona grammatikasiga mos holda matnni yuqori aniqlikda tarjima qiladi.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.3 }}
            className="glass-card rounded-[28px] p-6 sm:p-8 space-y-3"
          >
            <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-500">
              <Mic className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-black dark:text-white">Tabiiy Ovozlar (TTS)</h3>
            <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed font-medium">
              Azure Speech Neural texnologiyasi asosida erkak va ayol ovozlari tanlanadi yoki AI avtomatik tarzda suxandanning jinsini aniqlab unga mos tabiiy ovoz beradi.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.4 }}
            className="glass-card rounded-[28px] p-6 sm:p-8 space-y-3"
          >
            <div className="w-12 h-12 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-500">
              <Shield className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-black dark:text-white">Xavfsiz va Qulay Boshqaruv</h3>
            <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed font-medium">
              Tayyorlangan dublyaj qilingan videolaringiz shaxsiy panelingizda tartibli saqlanadi. Video va audio fayllar 3 kun davomida ko'rish va yuklab olish uchun mavjud bo'ladi.
            </p>
          </motion.div>
        </div>

        {/* Mission Statement Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.5 }}
          className="glass-card rounded-[32px] p-8 sm:p-10 space-y-6"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-500">
              <HeartHandshake className="w-5 h-5" />
            </div>
            <h2 className="text-xl font-black text-black dark:text-white">Bizning Maqsadimiz</h2>
          </div>

          <p className="text-xs sm:text-sm text-gray-600 dark:text-gray-300 leading-relaxed font-medium">
            Jahon ilmiy-ma'rifiy va ko'ngilochar video kontentlarini har bir o'zbekzabon foydalanuvchi uchun o'z ona tilida qulay va tushunarli qilishdir. Sun'iy intellekt kuchi bilan til to'siqlarini olib tashlash va bilimlarni o'zbek tilida keng yoyish loyihamizning bosh g'oyasidir.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2 border-t border-black/5 dark:border-white/10">
            <div className="flex items-center gap-2 text-xs font-bold text-black dark:text-white">
              <CheckCircle2 className="w-4 h-4 text-blue-500" /> 100% Avtomatik
            </div>
            <div className="flex items-center gap-2 text-xs font-bold text-black dark:text-white">
              <CheckCircle2 className="w-4 h-4 text-blue-500" /> Aniq Tarjima
            </div>
            <div className="flex items-center gap-2 text-xs font-bold text-black dark:text-white">
              <CheckCircle2 className="w-4 h-4 text-blue-500" /> HD Ovoz va Video
            </div>
          </div>
        </motion.div>

      </div>

      <Footer />
    </main>
  )
}
