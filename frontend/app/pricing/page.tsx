'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Check, Crown, Loader2, Sparkles, Zap } from 'lucide-react'
import { getPlans, subscribeToPlan, subscribeToPlanPayme, PlanDef, CurrentSubscription } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { trackEvent } from '@/lib/analytics'

const PLAN_ICONS: Record<string, any> = { free: Sparkles, standard: Zap, pro: Crown }

export default function PricingPage() {
  const router = useRouter()
  const { isLoggedIn, loading: authLoading } = useAuth()
  const [plans, setPlans] = useState<PlanDef[]>([])
  const [current, setCurrent] = useState<CurrentSubscription | null>(null)
  const [loading, setLoading] = useState(true)
  const [subscribing, setSubscribing] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'yearly'>('monthly')

  useEffect(() => {
    if (authLoading) return
    getPlans()
      .then((res) => {
        setPlans(res.plans)
        setCurrent(res.current)
      })
      .catch(() => setError("Tariflarni yuklashda xatolik yuz berdi."))
      .finally(() => setLoading(false))
  }, [authLoading])

  const handleSubscribe = async (planId: string, provider: 'click' | 'payme' = 'click') => {
    if (!isLoggedIn) {
      router.push('/login')
      return
    }
    setSubscribing(planId)
    setError(null)
    const paymentWindow = typeof window !== 'undefined' ? window.open('about:blank', '_blank') : null
    try {
      const res = await (provider === 'payme' ? subscribeToPlanPayme(planId) : subscribeToPlan(planId))
      if (res.success && res.payment_url) {
        trackEvent('payment_started', { provider, plan: planId })
        try { sessionStorage.setItem('pending_subscription_payment', planId) } catch {}
        if (paymentWindow) paymentWindow.location.href = res.payment_url
        else window.location.href = res.payment_url
      } else {
        if (paymentWindow) paymentWindow.close()
        setError("To'lov havolasini yaratishda xatolik yuz berdi.")
      }
    } catch {
      if (paymentWindow) paymentWindow.close()
      setError("To'lov havolasini yaratishda xatolik yuz berdi.")
    } finally {
      setSubscribing(null)
    }
  }

  return (
    <div className="min-h-screen relative flex flex-col items-center py-12 px-4 sm:px-6 transition-colors duration-300">
      <MeshBackground />

      <div className="w-full max-w-5xl z-10 space-y-8">
        <Link href="/" className="inline-flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-slate-400 hover:text-gray-900 dark:hover:text-white transition duration-200">
          <ArrowLeft className="w-4 h-4" /> Bosh sahifaga qaytish
        </Link>

        <div className="text-center space-y-3">
          <h1 className="text-2xl sm:text-3xl font-black text-gray-900 dark:text-white">Tarif rejalari</h1>
          <p className="text-sm text-gray-500 dark:text-slate-400 max-w-xl mx-auto">
            45 daqiqadan qisqa videolar har doim bepul. Uzunroq videolarni tez-tez dublyaj qilsangiz, oylik tarif arzonroq bo'ladi.
          </p>
        </div>

        {!isLoggedIn && !authLoading && (
          <p className="text-center text-sm text-amber-600 dark:text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-2xl px-4 py-3 max-w-md mx-auto">
            Tarifga obuna bo'lish uchun{' '}
            <Link href="/login" className="underline hover:text-amber-700 dark:hover:text-amber-300">kiring</Link>
            {' '}yoki{' '}
            <Link href="/register" className="underline hover:text-amber-700 dark:hover:text-amber-300">ro'yxatdan o'ting</Link>.
          </p>
        )}

        {error && (
          <p className="text-center text-sm text-red-600 dark:text-red-400 bg-red-500/10 border border-red-500/20 rounded-2xl px-4 py-3 max-w-md mx-auto">{error}</p>
        )}

        <div className="flex items-center justify-center gap-3">
          <span className={`text-sm font-semibold transition ${billingCycle === 'monthly' ? 'text-gray-900 dark:text-white' : 'text-gray-400 dark:text-slate-500'}`}>Oylik</span>
          <button
            onClick={() => setBillingCycle(billingCycle === 'monthly' ? 'yearly' : 'monthly')}
            className="relative w-12 h-7 rounded-full bg-violet-500/20 border border-violet-500/30 transition"
            aria-label="To'lov davrini almashtirish"
          >
            <span
              className={`absolute left-0.5 top-0.5 w-5 h-5 rounded-full bg-violet-500 transition-transform ${
                billingCycle === 'yearly' ? 'translate-x-[22px]' : 'translate-x-0'
              }`}
            />
          </button>
          <span className={`text-sm font-semibold transition flex items-center gap-1.5 ${billingCycle === 'yearly' ? 'text-gray-900 dark:text-white' : 'text-gray-400 dark:text-slate-500'}`}>
            Yillik
            <span className="text-[10px] font-bold uppercase tracking-widest bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 px-2 py-0.5 rounded-full">2 oy bepul</span>
          </span>
        </div>

        {loading ? (
          <div className="flex justify-center py-16"><Loader2 className="w-8 h-8 animate-spin text-violet-400" /></div>
        ) : (
          <div className="grid sm:grid-cols-3 gap-5">
            {(plans.length ? plans : DEFAULT_PLANS)
              .filter((plan) => plan.tier === 'free' || plan.period_days === (billingCycle === 'yearly' ? 365 : 30))
              .map((plan) => {
              const Icon = PLAN_ICONS[plan.tier] || Sparkles
              const isCurrent = current?.plan === plan.tier
              const isPro = plan.tier === 'pro'
              const monthlyEquivalent = plan.period_days === 365 ? Math.round(plan.price / 12) : null
              return (
                <div
                  key={plan.id}
                  className={`glass-card relative border rounded-[28px] p-6 flex flex-col gap-5 ${
                    isPro ? 'border-violet-500/50 shadow-[0_0_40px_-10px] shadow-violet-500/30' : 'border-black/5 dark:border-white/5'
                  }`}
                >
                  {isPro && (
                    <span className="absolute -top-3 left-1/2 -translate-x-1/2 text-[10px] font-bold uppercase tracking-widest bg-violet-500 text-white px-3 py-1 rounded-full">
                      Tavsiya etiladi
                    </span>
                  )}
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-violet-500/10 text-violet-500 dark:text-violet-400 flex items-center justify-center">
                      <Icon className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-lg font-black text-gray-900 dark:text-white">{plan.name}</h3>
                      {isCurrent && <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-widest">Joriy tarif</span>}
                    </div>
                  </div>

                  <div>
                    <span className="text-3xl font-black text-gray-900 dark:text-white">
                      {plan.price === 0 ? 'Bepul' : (monthlyEquivalent ?? plan.price).toLocaleString('uz-UZ')}
                    </span>
                    {plan.price > 0 && <span className="text-sm text-gray-500 dark:text-slate-400"> so'm/oy</span>}
                    {monthlyEquivalent !== null && (
                      <p className="text-xs text-gray-500 dark:text-slate-400 mt-0.5">
                        {plan.price.toLocaleString('uz-UZ')} so'm/yil to'lanadi
                      </p>
                    )}
                  </div>

                  <ul className="space-y-2.5 text-sm text-gray-600 dark:text-slate-300 flex-1">
                    <li className="flex items-center gap-2"><Check className="w-4 h-4 text-violet-500 dark:text-violet-400 shrink-0" /> Oyiga {plan.videos_per_period} ta video{plan.price === 0 ? `, ${plan.free_minutes} daqiqagacha` : ', cheklovsiz davomiylik'}</li>
                    <li className="flex items-center gap-2"><Check className="w-4 h-4 text-violet-500 dark:text-violet-400 shrink-0" /> {plan.priority ? 'Ustuvor navbat' : 'Standart navbat'}</li>
                    <li className="flex items-center gap-2"><Check className="w-4 h-4 text-violet-500 dark:text-violet-400 shrink-0" /> {plan.tts_tier === 'premium' ? 'Premium ovoz sifati' : "Standart ovoz (Edge)"}</li>
                    <li className="flex items-center gap-2"><Check className="w-4 h-4 text-violet-500 dark:text-violet-400 shrink-0" /> Yuklab olish sifati: {plan.max_resolution} gacha</li>
                    <li className="flex items-center gap-2"><Check className="w-4 h-4 text-violet-500 dark:text-violet-400 shrink-0" /> Video tahlil — cheklovsiz</li>
                  </ul>

                  <button
                    onClick={() => plan.id !== 'free' && handleSubscribe(plan.id, 'click')}
                    disabled={plan.id === 'free' || isCurrent || subscribing === plan.id}
                    className={`w-full py-3 rounded-2xl font-bold text-sm transition flex items-center justify-center gap-2 ${
                      plan.id === 'free' || isCurrent
                        ? 'bg-black/5 dark:bg-white/5 text-gray-400 dark:text-slate-500 cursor-not-allowed'
                        : 'bg-gradient-to-r from-violet-500 to-indigo-500 text-white hover:opacity-90'
                    }`}
                  >
                    {subscribing === plan.id ? (
                      <><Loader2 className="w-4 h-4 animate-spin" /> Kutilmoqda...</>
                    ) : isCurrent ? 'Joriy tarif' : plan.id === 'free' ? "Hozirgi tarif" : 'Click orqali tanlash'}
                  </button>
                  {plan.id !== 'free' && !isCurrent && (
                    <button
                      onClick={() => handleSubscribe(plan.id, 'payme')}
                      disabled={subscribing === plan.id}
                      className="w-full py-2.5 rounded-2xl font-bold text-xs text-gray-500 dark:text-slate-400 hover:text-gray-800 dark:hover:text-slate-200 border border-black/10 dark:border-white/10 transition"
                    >
                      Payme orqali to'lash
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        )}
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

// Login qilinmagan foydalanuvchiga ham tarif tuzilmasini ko'rsatish uchun
// (backend /api/plans login talab qiladi) — narxlar backend/services/plans.py
// bilan bir xil, faqat ko'rsatish uchun.
const DEFAULT_PLANS: PlanDef[] = [
  { id: 'free', name: 'Bepul', price: 0, videos_per_period: 1, free_minutes: 45, priority: false, tts_tier: 'edge', tier: 'free', period_days: 30, max_resolution: '360p' },
  { id: 'standard', name: 'Standart', price: 49000, videos_per_period: 8, free_minutes: 60, priority: false, tts_tier: 'edge', tier: 'standard', period_days: 30, max_resolution: '720p' },
  { id: 'standard_yearly', name: "Standart (yillik)", price: 490000, videos_per_period: 8, free_minutes: 60, priority: false, tts_tier: 'edge', tier: 'standard', period_days: 365, max_resolution: '720p' },
  { id: 'pro', name: 'Pro', price: 149000, videos_per_period: 30, free_minutes: 90, priority: true, tts_tier: 'premium', tier: 'pro', period_days: 30, max_resolution: '1080p' },
  { id: 'pro_yearly', name: 'Pro (yillik)', price: 1490000, videos_per_period: 30, free_minutes: 90, priority: true, tts_tier: 'premium', tier: 'pro', period_days: 365, max_resolution: '1080p' },
]
