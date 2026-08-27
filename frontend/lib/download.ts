"use client"

/**
 * Скачивание файлов с прогрессом + детект встроенных браузеров.
 *
 * Зачем: обычная навигация по `<a download>` не даёт прогресса и молча
 * блокируется в вебвью мессенджеров. Здесь файл качается через fetch
 * (прогресс по Content-Length), собирается в Blob и сохраняется —
 * плюс UI предупреждает, когда пользователь сидит во встроенном
 * браузере (Telegram/WhatsApp/Instagram и т.п.), где скачивание
 * ненадёжно.
 */

const IN_APP_PATTERNS: Array<[string, RegExp]> = [
  ["Telegram", /Telegram/i],
  ["WhatsApp", /WhatsApp/i],
  ["Instagram", /Instagram/i],
  ["Facebook", /FBAN|FBAV|Facebook/i],
  ["Messenger", /Messenger|MSGR/i],
  ["TikTok", /TikTok/i],
  ["WeChat", /MicroMessenger|WeChat/i],
  ["VK", /VKAndroidApp|VKShare|VKontakte/i],
  ["Line", /Line\//i],
]

export interface InAppInfo {
  inApp: boolean
  app: string | null
}

/** Определяет, открыт ли сайт во встроенном браузере приложения. */
export function detectInAppBrowser(ua?: string): InAppInfo {
  const source = ua ?? (typeof navigator !== "undefined" ? navigator.userAgent : "")
  for (const [app, re] of IN_APP_PATTERNS) {
    if (re.test(source)) return { inApp: true, app }
  }
  // Голый Android WebView без явных маркеров приложений.
  if (
    /Android/i.test(source) &&
    /wv/i.test(source) &&
    !/Chrome\/\d{2,}/i.test(source)
  ) {
    return { inApp: true, app: "WebView" }
  }
  return { inApp: false, app: null }
}

/** Безопасное имя файла из названия видео. */
export function safeFileName(title: string | null | undefined, fallback: string, resolution?: string): string {
  const base =
    (title || "")
      .replace(/[^\w\s\-а-яА-ЯёЁўЎқҚғҒҳҲ]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 60) || fallback
  return `dubbed_${base}${resolution ? `_${resolution}` : ""}.mp4`
}

/** Same-origin ли URL? Для таких URL fetch-скачивание с прогрессом работает без CORS. */
export function isSameOrigin(url: string): boolean {
  if (typeof window === "undefined") return false
  try {
    return new URL(url, window.location.href).origin === window.location.origin
  } catch {
    return false
  }
}

export interface DownloadProgress {
  received: number
  total: number
  percent: number
}

/**
 * Качает файл через fetch с прогрессом и сохраняет как Blob.
 * Возвращает AbortController для отмены.
 */
export function downloadWithProgress(
  url: string,
  filename: string,
  onProgress: (p: DownloadProgress) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): AbortController {
  const controller = new AbortController()
  const signal = controller.signal

  ;(async () => {
    try {
      const res = await fetch(url, { signal, cache: "no-store" })
      if (!res.ok && res.status !== 206) {
        throw new Error(`HTTP ${res.status}`)
      }
      const total = Number(res.headers.get("Content-Length") || 0)
      if (!res.body) {
        throw new Error("Javobda ma'lumot yo'q")
      }
      const reader = res.body.getReader()
      const chunks: Uint8Array[] = []
      let received = 0
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        chunks.push(value)
        received += value.byteLength
        if (total > 0) {
          onProgress({ received, total, percent: Math.min(100, (received / total) * 100) })
        }
      }
      // Собираем все чанки в один буфер (TS: Uint8Array<ArrayBufferLike> не
      // принимается как BlobPart — явный merge в Uint8Array<ArrayBuffer>).
      const merged = new Uint8Array(received)
      let offset = 0
      for (const chunk of chunks) {
        merged.set(chunk, offset)
        offset += chunk.byteLength
      }
      const blob = new Blob([merged.buffer], { type: "video/mp4" })
      const objectUrl = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = objectUrl
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(objectUrl), 15000)
      onDone()
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return
      onError(err instanceof Error ? err : new Error(String(err)))
    }
  })()

  return controller
}
