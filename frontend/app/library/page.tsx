'use client'
import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Library, Clock, Loader2, Lock, CheckCircle2, Copy, Check } from 'lucide-react'
import { motion } from 'framer-motion'
import { getLibrary, getLibraryAccess, purchaseLibraryAccess, purchaseLibraryAccessPayme, purchaseLibraryAccessUzum, formatDuration, LibraryItem } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'

const LIBRARY_ACCESS_PRICE = 5000

export default function LibraryPage() {
  const router = useRouter()
  const { isLoggedIn, loading: authLoading } = useAuth()

  const [items, setItems] = useState<LibraryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [hasAccess, setHasAccess] = useState<boolean | null>(null)
  const [purchaseLoading, setPurchaseLoading] = useState(false)
  const [openingId, setOpeningId] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [uzumAccount, setUzumAccount] = useState<{ account: number; amount: number } | null>(null)
  const [uzumCopied, setUzumCopied] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const PAGE_SIZE = 24

  useEffect(() => {
    getLibrary(PAGE_SIZE, 0)
      .then((res) => {
        setItems(res)
        setHasMore(res.length === PAGE_SIZE)
      })
      .catch(() => setError("Ro'yxatni yuklashda xatolik yuz berdi."))
      .finally(() => setLoading(false))
  }, [])

  const handleLoadMore = async () => {
    setLoadingMore(true)
    try {
      const res = await getLibrary(PAGE_SIZE, items.length)
      setItems((prev) => [...prev, ...res])
      setHasMore(res.length === PAGE_SIZE)
    } catch {
      setError("Ko'proq videolarni yuklashda xatolik yuz berdi.")
    } finally {
      setLoadingMore(false)
    }
  }

  useEffect(() => {
    if (authLoading || !isLoggedIn) return
    getLibraryAccess()
      .then((res) => setHasAccess(res.has_access))
      .catch(() => setHasAccess(false))
  }, [authLoading, isLoggedIn])

  const handlePurchase = async (provider: 'click' | 'payme' = 'click') => {
    if (!isLoggedIn) {
      router.push('/login')
      return
    }
    setPurchaseLoading(true)
    setError(null)
    try {
      const res = await (provider === 'payme' ? purchaseLibraryAccessPayme() : purchaseLibraryAccess())
      if (res.payment_url) {
        window.location.href = res.payment_url
      } else {
        setHasAccess(true)
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || "To'lovni boshlashda xatolik yuz berdi.")
    } finally {
      // window.location.href muvaffaqiyatli bo'lganda sahifa allaqachon
      // ketayotgan bo'ladi, shuning uchun bu zararsiz -- lekin agar
      // yo'naltirish sekin ketsa yoki umuman ishlamay qolsa (masalan
      // checkout provayderning o'zida vaqtinchalik xatolik, 2026-08-25da
      // Payme'da ko'rilgani kabi), tugmalar abadiy "disabled" holida
      // qotib qolmasligi uchun har doim qayta yoqiladi.
      setPurchaseLoading(false)
    }
  }

  // Uzum'da Click/Payme'dagidek checkout havolasi yo'q -- "account" raqami
  // ko'rsatiladi, foydalanuvchi Uzum ilovasida o'zi kiritib to'laydi.
  // Redirect bo'lmagani uchun (sahifa qayta yuklanmaydi), tasdiqni bu yerda
  // o'zimiz poll qilishimiz kerak -- video/[id]/page.tsx'da bu allaqachon
  // job-status pollingga "bepul qo'shilib" ketardi, bu yerda esa bunday poll
  // umuman yo'q edi (2026-08-24).
  const handleUzumPurchase = async () => {
    if (!isLoggedIn) {
      router.push('/login')
      return
    }
    setPurchaseLoading(true)
    setError(null)
    try {
      const res = await purchaseLibraryAccessUzum()
      if (res.success && res.account) {
        setUzumAccount({ account: res.account, amount: res.amount })
      } else if (res.amount === 0) {
        setHasAccess(true)
      } else {
        setError("To'lov ma'lumotlarini yaratishda xatolik yuz berdi.")
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || "To'lovni boshlashda xatolik yuz berdi.")
    } finally {
      setPurchaseLoading(false)
    }
  }

  const handleCopyUzumAccount = () => {
    if (!uzumAccount) return
    navigator.clipboard.writeText(String(uzumAccount.account)).then(() => {
      setUzumCopied(true)
      setTimeout(() => setUzumCopied(false), 2000)
    })
  }

  useEffect(() => {
    if (!uzumAccount) return
    pollRef.current = setInterval(() => {
      getLibraryAccess()
        .then((res) => {
          if (res.has_access) {
            setHasAccess(true)
            setUzumAccount(null)
            if (pollRef.current) clearInterval(pollRef.current)
          }
        })
        .catch(() => {})
    }, 4000)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [uzumAccount])

  const handleOpen = (item: LibraryItem) => {
    if (authLoading) return
    if (!isLoggedIn) {
      router.push('/login')
      return
    }
    if (!hasAccess) {
      handlePurchase()
      return
    }
    setOpeningId(item.job_id)
    router.push(`/library/${item.job_id}`)
  }

  return (
    <div className="min-h-screen relative flex flex-col items-center py-12 px-4 sm:px-6 transition-colors duration-300">
      <MeshBackground />

      <div className="w-full max-w-5xl z-10 space-y-8">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-slate-400 hover:text-gray-900 dark:hover:text-white transition duration-200"
        >
          <ArrowLeft className="w-4 h-4" /> Bosh sahifaga qaytish
        </Link>

        <div className="glass-card border border-black/5 dark:border-white/5 rounded-[32px] p-6 sm:p-10 shadow-2xl space-y-6">
          <div className="flex items-center gap-3 border-b border-black/5 dark:border-slate-800/80 pb-6">
            <div className="w-10 h-10 rounded-xl bg-violet-500/10 text-violet-500 dark:text-violet-400 flex items-center justify-center">
              <Library className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl sm:text-2xl font-black text-gray-900 dark:text-white">Ommaviy videolar</h1>
              <p className="text-xs text-gray-500 dark:text-slate-500">Boshqa foydalanuvchilar allaqachon dublyaj qilgan videolar</p>
            </div>
          </div>

          {!authLoading && hasAccess !== true && (
            <div className="flex flex-col sm:flex-row items-center gap-4 justify-between rounded-2xl border border-violet-500/20 bg-violet-500/5 dark:bg-violet-500/10 p-5">
              <div className="text-center sm:text-left">
                <p className="text-sm font-black text-gray-900 dark:text-white">Kutubxonaga umrbod kirish — {LIBRARY_ACCESS_PRICE.toLocaleString('uz-UZ')} so'm</p>
                <p className="text-xs text-gray-500 dark:text-slate-400 mt-0.5">Bir martalik to'lov — barcha (hozirgi va kelajakdagi) dublyaj qilingan videolarni cheksiz tomosha qiling</p>
              </div>
              <div className="shrink-0 flex items-center gap-2">
                {isLoggedIn ? (
                  <>
                    <button
                      onClick={() => handlePurchase('click')}
                      disabled={purchaseLoading}
                      title="Click orqali to'lash"
                      className="flex items-center justify-center h-12 px-4 rounded-2xl bg-white border border-black/10 dark:border-white/10 hover:border-black/20 dark:hover:border-white/30 hover:shadow-md transition disabled:opacity-50"
                    >
                      {purchaseLoading ? <Loader2 className="w-4 h-4 animate-spin text-gray-500" /> : (
                        <img src="/logos/click.png" alt="Click" className="h-5 w-auto object-contain" />
                      )}
                    </button>
                    <button
                      onClick={() => handlePurchase('payme')}
                      disabled={purchaseLoading}
                      title="Payme orqali to'lash"
                      className="flex items-center justify-center h-12 px-4 rounded-2xl bg-white border border-black/10 dark:border-white/10 hover:border-black/20 dark:hover:border-white/30 hover:shadow-md transition disabled:opacity-50"
                    >
                      <img src="/logos/payme.png" alt="Payme" className="h-5 w-auto object-contain" />
                    </button>
                    <button
                      onClick={handleUzumPurchase}
                      disabled={purchaseLoading}
                      title="Uzum orqali to'lash"
                      className="flex items-center justify-center h-12 px-4 rounded-2xl bg-white border border-black/10 dark:border-white/10 hover:border-black/20 dark:hover:border-white/30 hover:shadow-md transition disabled:opacity-50"
                    >
                      <img src="/logos/uzum.png" alt="Uzum" className="h-6 w-auto object-contain" />
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => handlePurchase('click')}
                    disabled={purchaseLoading}
                    className="flex items-center gap-2 px-5 py-3 rounded-2xl btn-premium font-extrabold text-xs uppercase tracking-wide disabled:opacity-60"
                  >
                    {purchaseLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />}
                    Kirib, huquq olish
                  </button>
                )}
              </div>
            </div>
          )}

          {uzumAccount && (
            <div className="bg-white/5 border border-violet-500/20 rounded-2xl p-5 text-left space-y-3">
              <p className="text-xs font-semibold text-gray-700 dark:text-slate-300">
                Uzum ilovasida to'lovlar bo'limidan quyidagi hisob raqamini kiriting va {uzumAccount.amount.toLocaleString('uz-UZ')} so'm to'lang:
              </p>
              <div className="flex items-center gap-2">
                <span className="flex-1 font-mono text-lg font-bold text-gray-900 dark:text-white bg-black/5 dark:bg-black/30 rounded-lg px-3 py-2 text-center tracking-wider">
                  {uzumAccount.account}
                </span>
                <button
                  onClick={handleCopyUzumAccount}
                  className="flex items-center justify-center w-10 h-10 rounded-lg bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/20 text-gray-700 dark:text-white transition flex-shrink-0"
                  title="Nusxalash"
                >
                  {uzumCopied ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
                </button>
              </div>
              <p className="text-[11px] text-gray-500 dark:text-slate-500">
                To'lov tasdiqlangach, bu sahifa avtomatik yangilanadi.
              </p>
            </div>
          )}

          {hasAccess === true && (
            <div className="flex items-center gap-2 text-xs font-bold text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="w-4 h-4" /> Kutubxonaga kirish huquqingiz bor — istalgan videoni bepul tomosha qiling
            </div>
          )}

          {loading && (
            <div className="py-16 flex flex-col items-center gap-3 text-gray-400 dark:text-slate-500">
              <Loader2 className="w-6 h-6 animate-spin" />
              <p className="text-xs font-semibold">Yuklanmoqda...</p>
            </div>
          )}

          {!loading && error && (
            <div className="py-3 text-center text-sm text-red-500 dark:text-red-400 font-semibold">{error}</div>
          )}

          {!loading && items.length === 0 && (
            <div className="py-16 text-center text-sm text-gray-400 dark:text-slate-500">
              Hozircha ommaviy videolar mavjud emas.
            </div>
          )}

          {!loading && items.length > 0 && (
            <>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
              {items.map((item) => (
                <motion.button
                  key={item.job_id}
                  onClick={() => handleOpen(item)}
                  disabled={openingId !== null}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="text-left rounded-2xl overflow-hidden bg-black/[0.02] dark:bg-slate-950/40 border border-black/5 dark:border-slate-800/80 hover:border-violet-400/50 transition disabled:opacity-60"
                >
                  <div className="relative aspect-video bg-black/10 dark:bg-black/30">
                    {item.video_thumbnail && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={item.video_thumbnail} alt={item.video_title || ''} loading="lazy" className="w-full h-full object-cover" />
                    )}
                    <span className="absolute top-2 left-2 flex items-center gap-1 px-2 py-1 rounded-lg bg-emerald-600/90 text-white text-[10px] font-bold">
                      <CheckCircle2 className="w-3 h-3" /> Dublyaj qilingan
                    </span>
                    {item.video_duration != null && (
                      <span className="absolute bottom-2 right-2 flex items-center gap-1 px-2 py-1 rounded-lg bg-black/70 text-white text-[10px] font-bold">
                        <Clock className="w-3 h-3" /> {formatDuration(item.video_duration)}
                      </span>
                    )}
                    {!hasAccess && (
                      <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                        <Lock className="w-6 h-6 text-white/90" />
                      </div>
                    )}
                    {openingId === item.job_id && (
                      <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                        <Loader2 className="w-6 h-6 text-white animate-spin" />
                      </div>
                    )}
                  </div>
                  <div className="p-3">
                    <p className="text-xs font-bold text-gray-900 dark:text-white line-clamp-2 leading-snug">{item.video_title || 'Nomsiz video'}</p>
                  </div>
                </motion.button>
              ))}
            </div>
            {hasMore && (
              <div className="flex justify-center pt-2">
                <button
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-2xl bg-black/[0.03] dark:bg-white/[0.05] hover:bg-black/[0.06] dark:hover:bg-white/10 border border-black/5 dark:border-white/10 text-xs font-bold text-gray-700 dark:text-slate-200 transition disabled:opacity-60"
                >
                  {loadingMore && <Loader2 className="w-4 h-4 animate-spin" />}
                  Ko'proq yuklash
                </button>
              </div>
            )}
            </>
          )}
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
