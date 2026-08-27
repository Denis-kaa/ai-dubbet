import { Clock, Users2, Captions, MonitorPlay, Volume2, Ban } from "lucide-react";

const FEATURES = [
  {
    icon: Clock,
    title: "45 daqiqagacha bepul",
    desc: "Davomiyligi 45 daqiqadan qisqa videolarni istalgancha, to'lovsiz dublyaj qiling.",
  },
  {
    icon: Users2,
    title: "Spiker jinsini avtomatik aniqlash",
    desc: "Tizim video ovozini tahlil qilib, erkak yoki ayol ovoziga mos dublyaj tanlaydi — xohlasangiz qo'lda ham belgilash mumkin.",
  },
  {
    icon: Captions,
    title: "O'zbekcha subtitr",
    desc: "Har bir dublyaj bilan birga video pleyerda yoqib-o'chirish mumkin bo'lgan o'zbekcha subtitr ham tayyorlanadi.",
  },
  {
    icon: MonitorPlay,
    title: "Turli video sifatlari",
    desc: "Tarifingizga qarab 360p dan 1080p gacha sifatda yuklab olish imkoniyati.",
  },
  {
    icon: Volume2,
    title: "Original fon saqlanadi",
    desc: "Dublyaj original video ovozini butunlay o'chirmaydi — fon musiqasi va effektlar tabiiy tarzda pasaytirilib qoldiriladi.",
  },
  {
    icon: Ban,
    title: "Qo'shimcha dastursiz",
    desc: "Hech qanday dastur o'rnatish shart emas — barcha qayta ishlash bulutli serverlarda amalga oshiriladi.",
  },
];

export default function FeaturesSection() {
  return (
    <section className="w-full max-w-4xl mt-14 px-4 z-10">
      <h2 className="text-lg sm:text-2xl font-black text-gray-900 dark:text-white text-center mb-6 sm:mb-8">
        Imkoniyatlar
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {FEATURES.map((f) => (
          <div
            key={f.title}
            className="glass-card rounded-[20px] p-5 border border-black/5 dark:border-white/10 flex items-start gap-3.5 text-left"
          >
            <div className="w-9 h-9 shrink-0 rounded-xl bg-blue-500/10 dark:bg-blue-500/15 flex items-center justify-center">
              <f.icon className="w-4.5 h-4.5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-1">{f.title}</h3>
              <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{f.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
