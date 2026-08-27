'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Clock, Loader2, CheckCircle2, Lock } from 'lucide-react'
import { getJob, getLibrary, getLibraryAccess, getLibraryEligible, getVideoUrl, getLibraryJobResolutions, requestLibraryResolution, formatDuration, LibraryItem, Job, ResolutionOption } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import VideoPlayer from '@/components/VideoPlayer'

const POLL_INTERVAL_MS = 4000

export default function LibraryWatchPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { isLoggedIn, loading: authLoading } = useAuth()

  const [job, setJob] = useState<Job | null>(null)
  const [items, setItems] = useState<LibraryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [videoSrc, setVideoSrc] = useState<string | null>(null)
  const [resolutions, setResolutions] = useState<ResolutionOption[] | null>(null)
  const [activeResolution, setActiveResolution] = useState('720p')
  const [switching, setSwitching] = useState<string | null>(null)

  useEffect(() => {
    if (authLoading) return
    if (!isLoggedIn) {
      router.replace('/login')
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([getLibraryAccess(), getLibraryEligible(id), getJob(id), getLibrary(24, 0)])
      .then(([access, eligible, jobData, list]) => {
        if (cancelled) return
        if (!access.has_access || !eligible.eligible) {
          router.replace('/library')
          return
        }
        setJob(jobData)
        setItems(list)
        setVideoSrc(getVideoUrl(jobData.job_id))
        setActiveResolution('720p')
      })
      .catch(() => {
        if (!cancelled) setError("Videoni yuklashda xatolik yuz berdi.")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [id, isLoggedIn, authLoading, router])

  useEffect(() => {
    if (!job) return
    getLibraryJobResolutions(job.job_id).then((res) => setResolutions(res.resolutions)).catch(() => {})
  }, [job])

  const handleSelectResolution = async (opt: ResolutionOption) => {
    if (!job || !opt.available || switching) return
    setSwitching(opt.resolution)
    try {
      const res = await requestLibraryResolution(job.job_id, opt.resolution, false)
      if (res.status === 'ready' && res.download_url) {
        setVideoSrc(res.download_url)
        setActiveResolution(opt.resolution)
        setSwitching(null)
      } else {
        const poll = setInterval(async () => {
          try {
            const updated = await getLibraryJobResolutions(job.job_id)
            setResolutions(updated.resolutions)
            const found = updated.resolutions.find((r) => r.resolution === opt.resolution)
            if (found && found.status === 'ready') {
              const again = await requestLibraryResolution(job.job_id, opt.resolution, false)
              if (again.download_url) {
                setVideoSrc(again.download_url)
                setActiveResolution(opt.resolution)
              }
              clearInterval(poll)
              setSwitching(null)
            } else if (found && found.status === 'failed') {
              clearInterval(poll)
              setSwitching(null)
            }
          } catch {
            clearInterval(poll)
            setSwitching(null)
          }
        }, POLL_INTERVAL_MS)
      }
    } catch {
      setSwitching(null)
    }
  }

  const otherItems = items.filter((item) => item.job_id !== id)

  return (
    <div className="min-h-screen bg-white dark:bg-[#070202] transition-colors duration-300">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <Link
          href="/library"
          className="inline-flex items-center gap-2 text-xs font-semibold text-gray-500 dark:text-slate-400 hover:text-gray-900 dark:hover:text-white transition duration-200 mb-5"
        >
          <ArrowLeft className="w-4 h-4" /> Ommaviy videolarga qaytish
        </Link>

        {loading && (
          <div className="py-24 flex flex-col items-center gap-3 text-gray-400 dark:text-slate-500">
            <Loader2 className="w-7 h-7 animate-spin" />
            <p className="text-xs font-semibold">Yuklanmoqda...</p>
          </div>
        )}

        {!loading && error && (
          <div className="py-24 text-center text-sm text-red-500 dark:text-red-400 font-semibold">{error}</div>
        )}

        {!loading && !error && job && videoSrc && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 lg:gap-8">
            <div className="lg:col-span-2 space-y-4">
              <div className="rounded-2xl overflow-hidden shadow-lg relative">
                <VideoPlayer key={videoSrc} src={videoSrc} subtitlesContent={job.uzbek_srt_content} />
              </div>
              <div className="space-y-2">
                <h1 className="text-lg sm:text-xl font-black text-gray-900 dark:text-white leading-snug">
                  {job.video_title || 'Nomsiz video'}
                </h1>
                <div className="flex items-center gap-3 text-xs font-semibold text-gray-500 dark:text-slate-400">
                  <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Dublyaj qilingan
                  </span>
                  {job.video_duration != null && (
                    <span className="inline-flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" /> {formatDuration(job.video_duration)}
                    </span>
                  )}
                </div>

                {resolutions && (
                  <div className="flex items-center gap-2 pt-1">
                    <span className="text-[10px] font-bold text-gray-400 dark:text-slate-500 uppercase tracking-widest">Sifat:</span>
                    <div className="flex gap-1.5">
                      {resolutions.map((opt) => {
                        const isActive = activeResolution === opt.resolution
                        const isBusy = switching === opt.resolution
                        if (!opt.available) {
                          return (
                            <Link
                              key={opt.resolution}
                              href="/pricing"
                              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-bold bg-black/[0.03] dark:bg-white/5 text-gray-400 dark:text-slate-500 border border-black/5 dark:border-white/10"
                              title="Bu sifat yuqoriroq tarif rejasida mavjud"
                            >
                              <Lock className="w-3 h-3" /> {opt.resolution}
                            </Link>
                          )
                        }
                        return (
                          <button
                            key={opt.resolution}
                            onClick={() => handleSelectResolution(opt)}
                            disabled={isBusy}
                            className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-bold border transition disabled:opacity-60 ${
                              isActive
                                ? "bg-violet-600 text-white border-violet-600"
                                : "bg-black/[0.03] dark:bg-white/5 text-gray-600 dark:text-slate-300 border-black/5 dark:border-white/10 hover:bg-black/[0.06] dark:hover:bg-white/10"
                            }`}
                          >
                            {isBusy && <Loader2 className="w-3 h-3 animate-spin" />}
                            {opt.resolution}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="lg:col-span-1 space-y-3">
              <h2 className="text-xs font-bold text-gray-400 dark:text-slate-500 uppercase tracking-widest px-1">
                Boshqa ommaviy videolar
              </h2>
              <div className="space-y-2">
                {otherItems.length === 0 && (
                  <p className="text-xs text-gray-400 dark:text-slate-500 px-1">Boshqa video hozircha yo'q.</p>
                )}
                {otherItems.map((item) => (
                  <Link
                    key={item.job_id}
                    href={`/library/${item.job_id}`}
                    className="flex gap-3 p-2 rounded-xl hover:bg-black/[0.03] dark:hover:bg-white/[0.05] transition"
                  >
                    <div className="relative w-32 sm:w-40 aspect-video shrink-0 rounded-lg overflow-hidden bg-black/10 dark:bg-black/30">
                      {item.video_thumbnail && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={item.video_thumbnail} alt={item.video_title || ''} loading="lazy" className="w-full h-full object-cover" />
                      )}
                      {item.video_duration != null && (
                        <span className="absolute bottom-1 right-1 px-1.5 py-0.5 rounded bg-black/70 text-white text-[9px] font-bold">
                          {formatDuration(item.video_duration)}
                        </span>
                      )}
                    </div>
                    <div className="min-w-0 flex-1 py-0.5">
                      <p className="text-xs font-bold text-gray-900 dark:text-white line-clamp-2 leading-snug">
                        {item.video_title || 'Nomsiz video'}
                      </p>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
