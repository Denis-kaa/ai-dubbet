'use client'
import Link from 'next/link'
import { ArrowLeft, Shield } from 'lucide-react'

export default function PrivacyPage() {
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
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl sm:text-2xl font-black text-gray-900 dark:text-white">Maxfiylik siyosati</h1>
              <p className="text-xs text-gray-500 dark:text-slate-500">Oxirgi yangilanish: 2026-yil 20-avgust</p>
            </div>
          </div>

          <div className="text-xs sm:text-sm text-gray-600 dark:text-slate-300 leading-relaxed space-y-6">
            <section className="space-y-2">
              <h2 className="text-base font-bold text-gray-900 dark:text-white">1. Biz to'playdigan ma'lumotlar</h2>
              <p>
                Platformamizdan foydalanganingizda, xizmat ko'rsatish sifatini oshirish maqsadida quyidagi ma'lumotlarni to'playmiz:
              </p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Siz kiritgan YouTube video manzillari va davomiyligi;</li>
                <li>Tizimga kirish uchun foydalanadigan login, elektron pochta manzili yoki telefon raqami;</li>
                <li>To'lov tafsilotlari (to'lovlar bevosita Click yoki Payme to'lov tizimlari orqali amalga oshiriladi va biz kartangiz ma'lumotlarini saqlamaymiz).</li>
              </ul>
            </section>

            <section className="space-y-2">
              <h2 className="text-base font-bold text-gray-900 dark:text-white">2. Ma'lumotlardan foydalanish</h2>
              <p>To'plangan ma'lumotlar faqat quyidagi maqsadlarda ishlatiladi:</p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Dublyaj va tarjima jarayonini amalga oshirish;</li>
                <li>Hisob-kitoblar va to'lovlarni amalga oshirish hamda tasdiqlash;</li>
                <li>Texnik muammolarni bartaraf etish va foydalanuvchilarni qo'llab-quvvatlash.</li>
              </ul>
            </section>

            <section className="space-y-2">
              <h2 className="text-base font-bold text-gray-900 dark:text-white">3. Ma'lumotlar xavfsizligi</h2>
              <p>
                Biz sizning shaxsiy ma'lumotlaringiz xavfsizligini ta'minlash uchun SSL shifrlash va zamonaviy xavfsizlik protokollaridan foydalanamiz. Biroq, internet orqali ma'lumot uzatishning 100% xavfsizligini kafolatlab bo'lmaydi.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-base font-bold text-gray-900 dark:text-white">4. Uchinchi shaxslarga ma'lumot uzatish</h2>
              <p>
                Xizmat ko'rsatish jarayonida matnlarni tarjima qilish uchun OpenAI va nutq sintezi uchun Microsoft Azure xizmatlariga faqatgina videodagi matnli ma'lumotlar uzatiladi. Pullik videolar uchun to'lov ma'lumotlari Click yoki Payme to'lov tizimlariga (siz tanlagan usulga qarab) uzatiladi. Sizning shaxsiy ma'lumotlaringiz uchinchi shaxslarga sotilmaydi.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-base font-bold text-gray-900 dark:text-white">5. Ma'lumotlarni saqlash va o'chirish muddati</h2>
              <ul className="list-disc pl-5 space-y-1">
                <li>Asl yuklab olingan YouTube video va oraliq audio fayllar faqat dublyaj jarayoni davomida serverimizda vaqtincha saqlanadi va jarayon tugashi bilan (muvaffaqiyatli yoki xatolik bilan) darhol o'chiriladi;</li>
                <li>Tayyor dublyaj qilingan video va audio fayllar bulutli xotirada (AWS S3) saqlanadi va yaratilgan kundan boshlab <strong>3 kun</strong> o'tgach avtomatik ravishda butunlay o'chiriladi — shu muddat ichida video/audioni yuklab olishingizni tavsiya qilamiz;</li>
                <li>Subtitr matni va job haqidagi ma'lumotlar (video nomi, holati, sana) hisobingiz tarixi sifatida saqlanadi; ularni "Dashboard" bo'limidan istalgan vaqtda o'chirishingiz mumkin;</li>
                <li>Hisob ma'lumotlaringiz (ism, email, telefon) hisobingiz faol bo'lgan davomida saqlanadi.</li>
              </ul>
            </section>
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
