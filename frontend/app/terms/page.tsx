'use client'
import Link from 'next/link'
import { ArrowLeft, FileText } from 'lucide-react'

export default function TermsPage() {
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
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl sm:text-2xl font-black text-gray-900 dark:text-white">Foydalanish shartlari</h1>
              <p className="text-xs text-gray-500 dark:text-slate-500">Oxirgi yangilanish: 2026-yil 4-avgust</p>
            </div>
          </div>

          <div className="text-xs sm:text-sm text-gray-600 dark:text-slate-300 leading-relaxed space-y-6">
            <section className="space-y-2">
              <h2 className="text-base font-bold text-gray-900 dark:text-white">1. Umumiy qoidalar</h2>
              <p>
                GapirAI.uz platformasidan foydalanish orqali siz mazkur Foydalanish shartlariga to'liq rozilik bildirasiz. Agar siz ushbu shartlarga rozi bo'lmasangiz, platforma xizmatlaridan foydalanmasligingiz so'raladi.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-base font-bold text-gray-900 dark:text-white">2. Xizmat tavsifi</h2>
              <p>
                GapirAI.uz foydalanuvchilarga YouTube va boshqa manbalardagi xorijiy video kontentlarni o'zbek tiliga sun'iy intellekt (AI) yordamida avtomatik ravishda tarjima va dublyaj qilish imkonini beradi. Tizim tarjima natijasini kafolatlamaydi va sinxron ovozlashtirishda kichik xatolar bo'lishi tabiiy hol hisoblanadi.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-base font-bold text-gray-900 dark:text-white">3. Foydalanish cheklovlari</h2>
              <p>Foydalanuvchilarga quyidagilarni dublyaj qilish qat'iyan tavsiya etilmaydi:</p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Qonunga xilof, zo'ravonlik, nafrat uyg'otuvchi, terrorizm/ekstremizmni targ'ib qiluvchi yoki kattalar (18+) uchun mo'ljallangan kontent;</li>
                <li>Bolalarga nisbatan jinsiy zo'ravonlik/ekspluatatsiya tasvirlangan kontent (CSAM) — bunday kontent uchun dublyaj so'rovi <strong>hech qanday holatda</strong> bajarilmaydi va hisob qaydnomasi bloklanishi mumkin;</li>
                <li>Platforma infratuzilmasiga zarar yetkazish, sun'iy yuklamalar (DDoS) hosil qilish yoki tizimni skanerlash;</li>
                <li>Dublyaj natijalarini uchinchi shaxslarning mualliflik huquqlarini buzgan holda tijoriy maqsadlarda tarqatish.</li>
              </ul>
              <p>
                Yuqoridagi diniy, 18+, zo'ravonlik va shunga o'xshash kategoriyalar (CSAM bundan mustasno) uchun dublyaj
                jarayonining o'zi to'xtatilmaydi — video shaxsiy foydalanish uchun tayyorlanadi. Lekin bunday video hech qachon
                "Ommaviy videolar" ochiq kutubxonasiga chiqarilmaydi va boshqa foydalanuvchilarga ko'rsatilmaydi.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-base font-bold text-gray-900 dark:text-white">4. To'lovlar va qaytarish shartlari</h2>
              <p>
                Davomiyligi 45 daqiqadan kam bo'lgan videolar bepul taqdim etiladi. 45 daqiqadan ortiq davom etadigan videolarni qayta ishlash uchun Click yoki Payme to'lov tizimlaridan biri orqali to'lov amalga oshirilishi lozim (daqiqasiga 500 so'm). Xizmat ko'rsatilgandan so'ng, to'langan mablag'lar qaytarilmaydi.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-base font-bold text-gray-900 dark:text-white">5. Javobgarlikni cheklash</h2>
              <p>
                GapirAI.uz ma'lumotlar yo'qolishi, uchinchi shaxslar tomonidan kontent bloklanishi yoki platformadan foydalanish natijasida kelib chiqadigan bilvosita zararlar uchun javobgarlikni o'z zimmasiga olmaydi.
              </p>
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
