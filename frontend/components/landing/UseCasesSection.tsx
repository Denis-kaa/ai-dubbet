import { Video, GraduationCap, Newspaper } from "lucide-react";

const USE_CASES = [
  {
    icon: Video,
    title: "Kontent yaratuvchilar",
    desc: "Xorijiy videolaringizni o'zbek auditoriyasi uchun tushunarli qiling — YouTube kanalingizni kengaytiring.",
  },
  {
    icon: GraduationCap,
    title: "Ta'lim beruvchilar",
    desc: "Ingliz tilidagi dars va ma'ruzalarni o'quvchilaringiz uchun o'zbek tilida taqdim eting.",
  },
  {
    icon: Newspaper,
    title: "Media va bloggerlar",
    desc: "Xorijiy yangilik va sharhlarni tezkor ravishda o'zbek tilida auditoriyangizga yetkazing.",
  },
];

export default function UseCasesSection() {
  return (
    <section className="w-full max-w-4xl mt-14 px-4 z-10">
      <h2 className="text-lg sm:text-2xl font-black text-gray-900 dark:text-white text-center mb-6 sm:mb-8">
        Kimlar uchun mos?
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-5">
        {USE_CASES.map((u) => (
          <div
            key={u.title}
            className="glass-card rounded-[20px] p-5 sm:p-6 border border-black/5 dark:border-white/10 text-left"
          >
            <div className="w-10 h-10 rounded-2xl bg-violet-500/10 dark:bg-violet-500/15 flex items-center justify-center mb-3">
              <u.icon className="w-5 h-5 text-violet-600 dark:text-violet-400" />
            </div>
            <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-1.5">{u.title}</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{u.desc}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
