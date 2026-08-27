"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Check } from "lucide-react";
import { getPlans, PlanDef } from "@/lib/api";

export default function PricingPreviewSection() {
  const [plans, setPlans] = useState<PlanDef[] | null>(null);

  useEffect(() => {
    getPlans()
      .then((res) => setPlans(res.plans.filter((p) => !p.id.endsWith("_yearly"))))
      .catch(() => setPlans(null));
  }, []);

  if (!plans || plans.length === 0) return null;

  return (
    <section className="w-full max-w-4xl mt-14 px-4 z-10">
      <h2 className="text-lg sm:text-2xl font-black text-gray-900 dark:text-white text-center mb-2">
        Tarif rejalari
      </h2>
      <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 text-center mb-6 sm:mb-8">
        45 daqiqadan qisqa videolar har doim bepul.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {plans.map((plan) => (
          <div
            key={plan.id}
            className="glass-card rounded-[20px] p-5 border border-black/5 dark:border-white/10 text-left"
          >
            <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-1">{plan.name}</h3>
            <p className="text-xl font-black text-gray-900 dark:text-white mb-3">
              {plan.price === 0 ? "Bepul" : `${plan.price.toLocaleString("uz-UZ")} so'm`}
              {plan.price > 0 && <span className="text-xs font-medium text-gray-400">/oy</span>}
            </p>
            <ul className="space-y-1.5 text-xs text-gray-500 dark:text-gray-400">
              <li className="flex items-center gap-1.5">
                <Check className="w-3.5 h-3.5 text-emerald-500 shrink-0" /> Oyiga {plan.videos_per_period} ta video
              </li>
              <li className="flex items-center gap-1.5">
                <Check className="w-3.5 h-3.5 text-emerald-500 shrink-0" /> {plan.max_resolution} gacha sifat
              </li>
            </ul>
          </div>
        ))}
      </div>
      <div className="flex justify-center mt-6">
        <Link
          href="/pricing"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-2xl bg-black/[0.03] dark:bg-white/[0.03] hover:bg-black/[0.06] dark:hover:bg-white/[0.06] border border-black/10 dark:border-white/10 text-gray-800 dark:text-gray-200 font-bold text-xs transition"
        >
          Barcha tariflarni ko'rish
        </Link>
      </div>
    </section>
  );
}
