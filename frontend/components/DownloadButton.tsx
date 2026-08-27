"use client"

import { useCallback, useRef, useState } from "react"
import { Download, Loader2, CheckCircle2, AlertTriangle, X } from "lucide-react"
import { downloadWithProgress, DownloadProgress, isSameOrigin } from "@/lib/download"

interface DownloadButtonProps {
  url: string
  filename: string
  label?: string
  hint?: string
}

type DlState =
  | { phase: "idle" }
  | { phase: "downloading"; percent: number; received: number; total: number }
  | { phase: "done" }
  | { phase: "error"; message: string }

function formatMb(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function DownloadButton({ url, filename, label = "Yuklab olish", hint }: DownloadButtonProps) {
  const [state, setState] = useState<DlState>({ phase: "idle" })
  const controllerRef = useRef<AbortController | null>(null)

  const start = useCallback(() => {
    if (!url || state.phase === "downloading") return
    if (!isSameOrigin(url)) {
      // S3 presigned (cross-origin) — fetch не пройдёт CORS, обычная ссылка.
      const a = document.createElement("a")
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      return
    }
    setState({ phase: "downloading", percent: 0, received: 0, total: 0 })
    controllerRef.current = downloadWithProgress(
      url,
      filename,
      (p: DownloadProgress) =>
        setState((s) =>
          s.phase === "downloading"
            ? { phase: "downloading", percent: p.percent, received: p.received, total: p.total }
            : s,
        ),
      () => setState({ phase: "done" }),
      (err) => setState({ phase: "error", message: err.message }),
    )
  }, [url, filename, state.phase])

  const cancel = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    setState({ phase: "idle" })
  }, [])

  return (
    <div className="space-y-2">
      {state.phase === "downloading" ? (
        <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
          <div className="flex items-center justify-between text-xs text-slate-300 mb-2 gap-2">
            <span className="flex items-center gap-2 font-semibold shrink-0">
              <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
              Yuklanmoqda... {state.percent.toFixed(0)}%
            </span>
            <span className="text-slate-500 font-mono shrink-0">
              {formatMb(state.received)}
              {state.total > 0 ? ` / ${formatMb(state.total)}` : ""}
            </span>
          </div>
          <div className="h-2 rounded-full bg-white/10 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 transition-all duration-200"
              style={{ width: `${state.percent}%` }}
            />
          </div>
          <button
            onClick={cancel}
            className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400 hover:text-white transition"
          >
            <X className="w-3.5 h-3.5" /> Bekor qilish
          </button>
        </div>
      ) : (
        <button
          onClick={start}
          disabled={!url}
          className={`w-full flex items-center justify-center gap-2 rounded-2xl py-3.5 text-sm font-bold transition duration-200 disabled:opacity-50 ${
            state.phase === "done"
              ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
              : "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-lg"
          }`}
        >
          {state.phase === "done" ? <CheckCircle2 className="w-4 h-4" /> : <Download className="w-4 h-4" />}
          {state.phase === "done" ? "Yuklab olindi!" : label}
        </button>
      )}

      {state.phase === "error" && (
        <div className="flex items-start gap-2 text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span>
            Yuklab olishda xatolik: {state.message}. Agar brauzer bloklasa — Chrome/Safari'da ochib qayta urinib ko'ring.
          </span>
        </div>
      )}

      {hint && state.phase !== "downloading" && (
        <p className="text-[10px] text-slate-500 px-1">{hint}</p>
      )}
    </div>
  )
}
