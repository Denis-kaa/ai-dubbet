'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { Download, Loader2, Lock, RotateCw, AlertCircle, CheckCircle2, AlertTriangle, X } from 'lucide-react'
import { getJobResolutions, requestResolution, ResolutionOption } from '@/lib/api'
import { trackEvent } from '@/lib/analytics'
import { downloadWithProgress, DownloadProgress, isSameOrigin, safeFileName } from '@/lib/download'

interface ResolutionDownloadButtonsProps {
  jobId: string
}

const POLL_INTERVAL_MS = 4000

type DlState =
  | { phase: 'idle' }
  | { phase: 'downloading'; percent: number; received: number; total: number }
  | { phase: 'done' }
  | { phase: 'error'; message: string }

function formatMb(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function triggerDownload(url: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
}

export default function ResolutionDownloadButtons({ jobId }: ResolutionDownloadButtonsProps) {
  const [resolutions, setResolutions] = useState<ResolutionOption[] | null>(null)
  const [busy, setBusy] = useState<Record<string, boolean>>({})
  const [dl, setDl] = useState<Record<string, DlState>>({})
  const pollTimers = useRef<Record<string, ReturnType<typeof setInterval>>>({})
  const controllers = useRef<Record<string, AbortController>>({})

  const refresh = async () => {
    try {
      const res = await getJobResolutions(jobId)
      setResolutions(res.resolutions)
      return res.resolutions
    } catch {
      return null
    }
  }

  useEffect(() => {
    refresh()
    return () => {
      Object.values(pollTimers.current).forEach(clearInterval)
      Object.values(controllers.current).forEach((c) => c.abort())
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId])

  const startPolling = (resolution: string) => {
    if (pollTimers.current[resolution]) return
    pollTimers.current[resolution] = setInterval(async () => {
      const updated = await refresh()
      const opt = updated?.find((r) => r.resolution === resolution)
      if (opt && (opt.status === 'ready' || opt.status === 'failed')) {
        clearInterval(pollTimers.current[resolution])
        delete pollTimers.current[resolution]
        setBusy((b) => ({ ...b, [resolution]: false }))
      }
    }, POLL_INTERVAL_MS)
  }

  const startDownload = (url: string, resolution: string) => {
    const filename = safeFileName(undefined, jobId, resolution)
    if (isSameOrigin(url)) {
      // Same-origin (/api/outputs/...): качаем через fetch с прогрессом.
      setDl((d) => ({ ...d, [resolution]: { phase: 'downloading', percent: 0, received: 0, total: 0 } }))
      controllers.current[resolution] = downloadWithProgress(
        url,
        filename,
        (p: DownloadProgress) =>
          setDl((d) => ({ ...d, [resolution]: { phase: 'downloading', percent: p.percent, received: p.received, total: p.total } })),
        () => setDl((d) => ({ ...d, [resolution]: { phase: 'done' } })),
        (err) => setDl((d) => ({ ...d, [resolution]: { phase: 'error', message: err.message } })),
      )
    } else {
      // S3 presigned (cross-origin) — fetch не пройдёт CORS, обычная ссылка.
      triggerDownload(url)
    }
  }

  const cancelDownload = (resolution: string) => {
    controllers.current[resolution]?.abort()
    delete controllers.current[resolution]
    setDl((d) => ({ ...d, [resolution]: { phase: 'idle' } }))
  }

  const handleClick = async (opt: ResolutionOption) => {
    if (!opt.available) return
    setBusy((b) => ({ ...b, [opt.resolution]: true }))
    try {
      const res = await requestResolution(jobId, opt.resolution)
      if (res.status === 'ready' && res.download_url) {
        trackEvent('video_downloaded', { format: 'video', resolution: opt.resolution })
        startDownload(res.download_url, opt.resolution)
        setBusy((b) => ({ ...b, [opt.resolution]: false }))
        refresh()
      } else {
        startPolling(opt.resolution)
        refresh()
      }
    } catch {
      // Masalan 410 (fayl saqlash muddati tugagan) -- GET qayta chaqirilsa
      // backend haqiqiy "expired" holatini qaytaradi, shu orqali tugma
      // to'g'ri ko'rinishga o'tadi.
      setBusy((b) => ({ ...b, [opt.resolution]: false }))
      refresh()
    }
  }

  if (!resolutions) {
    return (
      <div className="inline-flex items-center gap-2 text-slate-400 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" />
        Sifat variantlari yuklanmoqda...
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {resolutions.map((opt) => {
          const isBusy = busy[opt.resolution] || opt.status === 'processing'
          const isReady = opt.status === 'ready'
          const isFailed = opt.status === 'failed'
          const state = dl[opt.resolution] || { phase: 'idle' as const }

          if (!opt.available) {
            return (
              <Link
                key={opt.resolution}
                href="/pricing"
                className="inline-flex items-center gap-2 bg-white/5 hover:bg-white/10 text-slate-400 px-5 py-3 rounded-xl font-bold border border-white/10 transition"
                title="Bu sifat yuqoriroq tarif rejasida mavjud"
              >
                <Lock className="w-4 h-4" />
                {opt.resolution}
              </Link>
            )
          }

          if (opt.status === 'expired') {
            return (
              <div
                key={opt.resolution}
                className="inline-flex items-center gap-2 bg-white/5 text-slate-500 px-5 py-3 rounded-xl font-bold border border-white/10 cursor-default"
                title="Video fayli saqlash muddati tugagani sababli endi mavjud emas"
              >
                <AlertCircle className="w-4 h-4" />
                {opt.resolution}
                <span className="text-xs font-normal">muddati tugagan</span>
              </div>
            )
          }

          return (
            <button
              key={opt.resolution}
              onClick={() => handleClick(opt)}
              disabled={isBusy || state.phase === 'downloading'}
              className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-70 text-white px-5 py-3 rounded-xl font-bold shadow-lg shadow-blue-500/20 transition hover:scale-105 disabled:hover:scale-100"
            >
              {isBusy ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : isFailed ? (
                <RotateCw className="w-4 h-4" />
              ) : (
                <Download className="w-4 h-4" />
              )}
              {opt.resolution}
              {isBusy && !isReady && (
                <span className="text-xs font-normal text-blue-100">tayyorlanmoqda...</span>
              )}
              {isFailed && !isBusy && (
                <span className="text-xs font-normal text-blue-100">qayta urinish</span>
              )}
            </button>
          )
        })}
      </div>

      {/* Прогресс скачивания выбранного качества */}
      {resolutions.map((opt) => {
        const state = dl[opt.resolution] || { phase: 'idle' as const }
        if (state.phase === 'idle') return null
        if (state.phase === 'downloading') {
          return (
            <div key={`dl-${opt.resolution}`} className="bg-white/5 border border-white/10 rounded-2xl p-4">
              <div className="flex items-center justify-between text-xs text-slate-300 mb-2 gap-2">
                <span className="flex items-center gap-2 font-semibold shrink-0">
                  <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
                  {opt.resolution} yuklanmoqda... {state.percent.toFixed(0)}%
                </span>
                <span className="text-slate-500 font-mono shrink-0">
                  {formatMb(state.received)}
                  {state.total > 0 ? ` / ${formatMb(state.total)}` : ''}
                </span>
              </div>
              <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 transition-all duration-200"
                  style={{ width: `${state.percent}%` }}
                />
              </div>
              <button
                onClick={() => cancelDownload(opt.resolution)}
                className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400 hover:text-white transition"
              >
                <X className="w-3.5 h-3.5" /> Bekor qilish
              </button>
            </div>
          )
        }
        if (state.phase === 'done') {
          return (
            <div key={`dl-${opt.resolution}`} className="flex items-center gap-2 text-xs font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-2xl px-4 py-3">
              <CheckCircle2 className="w-4 h-4" />
              {opt.resolution} yuklab olindi!
            </div>
          )
        }
        return (
          <div key={`dl-${opt.resolution}`} className="flex items-start gap-2 text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            <span>
              Yuklab olishda xatolik: {state.message}. Agar brauzer bloklasa — Chrome/Safari'da ochib qayta urinib ko'ring.
            </span>
          </div>
        )
      })}
    </div>
  )
}
