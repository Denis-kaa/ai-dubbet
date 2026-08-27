import { Link2, Cpu, Download } from "lucide-react";

const STEPS = [
  {
    icon: Link2,
    title: "1. Video havolasini kiriting",
    desc: "YouTube video havolasini yuqoridagi maydonga joylashtiring va dublyaj qilish tugmasini bosing.",
  },
  {
    icon: Cpu,
    title: "2. AI videoni qayta ishlaydi",
    desc: "Nutq matnga aylantiriladi, o'zbek tiliga tarjima qilinadi, so'ng tabiiy o'zbekcha ovozga aylantiriladi.",
  },
  {
    icon: Download,
    title: "3. Tayyor videoni yuklab oling",
    desc: "O'zbekcha dublyaj qilingan MP4 videoni to'g'ridan-to'g'ri saytdan yuklab olasiz.",
  },
];

export default function HowItWorksSection() {
  return (
    <section className="w-full max-w-4xl mt-10 px-4 z-10">
      <h2 className="text-lg sm:text-2xl font-black text-gray-900 dark:text-white text-center mb-6 sm:mb-8">
        Qanday ishlaydi?
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-5">
        {STEPS.map((step) => (
          <div
            key={step.title}
            className="glass-card rounded-[20px] p-5 sm:p-6 border border-black/5 dark:border-white/10 text-left"
          >
            <div className="w-10 h-10 rounded-2xl bg-violet-500/10 dark:bg-violet-500/15 flex items-center justify-center mb-3">
              <step.icon className="w-5 h-5 text-violet-600 dark:text-violet-400" />
            </div>
            <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-1.5">{step.title}</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{step.desc}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
