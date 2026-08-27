import axios from 'axios'
import { getToken, clearAuth } from './auth'
import { getApiUrl } from './runtime-config'

const API_URL = getApiUrl()

export const apiClient = axios.create({ baseURL: API_URL })

// Har bir so'rovga token qo'shish
apiClient.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Token yaroqsiz bo'lib qolsa (masalan server tomonda imzolash kaliti
// almashtirilsa) useAuth ilgari cache'langan foydalanuvchini ko'rsatishda
// davom etardi -- "kirgan" ko'rinib, har bir so'rov jimgina 401 bilan
// muvaffaqiyatsiz tugardi. Endi shu yerda bir joyda tozalanadi va foydalanuvchi
// qayta kirish sahifasiga yo'naltiriladi.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error?.response?.status === 401 &&
      typeof window !== 'undefined' &&
      !window.location.pathname.startsWith('/login')
    ) {
      clearAuth()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

/**
 * Har qanday API xatosini (axios error) foydalanuvchiga xavfsiz ko'rsatish
 * mumkin bo'lgan shaklga keltiradi -- "nima bo'ldi" (message), "qayta
 * urinish mumkinmi" (retryable) va tarmoq xatosimi (isNetworkError).
 *
 * Backend'ning `detail` matnlari allaqachon o'zbek tilida va xavfsiz
 * (backend/api/*.py) -- bu funksiya ularni o'zgartirmaydi, faqat:
 *   1. Javob umuman kelmagan holatni (tarmoq/timeout) alohida aniqlaydi
 *      -- avval bu ham xuddi 5xx bilan bir xil umumiy xabar olardi
 *      (frontend/hooks/useJobPolling.ts'dagi eski xatti-harakat).
 *   2. `detail` maydoni yo'q/matn bo'lmagan holatlar uchun xavfsiz
 *      standart xabar beradi (hech qachon xom axios/tarmoq ichki
 *      xabarini ko'rsatmaydi).
 */
export interface ApiErrorInfo {
  message: string
  retryable: boolean
  isNetworkError: boolean
  status?: number
}

export function parseApiError(err: unknown): ApiErrorInfo {
  const anyErr = err as any

  if (!anyErr?.response) {
    // Javob umuman kelmadi -- tarmoq uzilgan, so'rov muddati tugagan yoki
    // server butunlay ishlamayapti.
    return {
      message: "Server bilan aloqa o'rnatib bo'lmadi. Internet aloqangizni tekshiring va qaytadan urinib ko'ring.",
      retryable: true,
      isNetworkError: true,
    }
  }

  const status: number = anyErr.response.status
  const detail = anyErr.response.data?.detail

  if (status >= 500) {
    return {
      message: typeof detail === 'string' && detail ? detail : "Serverda kutilmagan xatolik yuz berdi. Birozdan so'ng qaytadan urinib ko'ring.",
      retryable: true,
      isNetworkError: false,
      status,
    }
  }

  return {
    message: typeof detail === 'string' && detail ? detail : "So'rovda xatolik yuz berdi.",
    retryable: status === 429, // faqat "juda ko'p so'rov" holatida qayta urinish mantiqiy
    isNetworkError: false,
    status,
  }
}

export interface VideoInfo {
  title: string
  duration: number
  thumbnail: string
  uploader: string
}

export interface Job {
  job_id: string
  status: JobStatus
  progress: number
  status_message?: string
  youtube_url?: string
  video_title?: string
  video_duration?: number
  video_thumbnail?: string
  output_video_url?: string
  transcript_text?: string
  translated_text?: string
  error_message?: string
  created_at?: string
  speaker_gender?: string
  voice_gender_setting?: string
  audio_mix_mode?: 'dubbed_only' | 'ducked_mix'
  uzbek_srt_content?: string
  expected_end_time?: string
  rating?: number
  feedback_comment?: string
  content_flagged?: boolean
}

export type JobStatus =
  | 'pending'
  | 'awaiting_payment'
  | 'downloading'
  | 'transcribing'
  | 'translating'
  | 'syncing'
  | 'synthesizing'
  | 'merging'
  | 'completed'
  | 'failed'

export const STATUS_LABELS: Record<JobStatus, string> = {
  pending: 'Navbatda',
  awaiting_payment: 'To\'lov kutilmoqda',
  downloading: 'Yuklanmoqda',
  transcribing: 'Matnga aylantirilmoqda',
  translating: 'Tarjima qilinmoqda',
  syncing: 'Talaffuzga moslashtirilmoqda',
  synthesizing: 'Ovoz yaratilmoqda',
  merging: 'Birlashtirilmoqda',
  completed: 'Tayyor',
  failed: 'Xatolik',
}

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export async function getVideoInfo(url: string): Promise<VideoInfo> {
  const res = await apiClient.get('/api/video-info', { params: { url } })
  return res.data
}

export async function createJob(
  youtube_url: string,
  voice_gender: string = 'auto',
  audio_mix_mode: 'dubbed_only' | 'ducked_mix' = 'dubbed_only',
): Promise<{ job_id: string; status: string }> {
  const res = await apiClient.post('/api/jobs', {
    youtube_url,
    target_language: 'uz',
    voice_gender,
    audio_mix_mode,
  })
  return res.data
}

export async function getJob(jobId: string): Promise<Job> {
  const res = await apiClient.get(`/api/jobs/${jobId}`)
  return res.data
}

export async function listJobs(): Promise<Job[]> {
  const res = await apiClient.get('/api/jobs')
  return res.data
}

export async function deleteJob(jobId: string): Promise<void> {
  await apiClient.delete(`/api/jobs/${jobId}`)
}

export interface LibraryItem {
  job_id: string
  youtube_url: string
  video_title: string | null
  video_duration: number | null
  video_thumbnail: string | null
  speaker_gender: string | null
  created_at: string | null
}

export async function getLibrary(limit: number = 24, offset: number = 0): Promise<LibraryItem[]> {
  const res = await apiClient.get('/api/library', { params: { limit, offset } })
  return res.data
}

export async function getLibraryAccess(): Promise<{ has_access: boolean }> {
  const res = await apiClient.get('/api/library/access')
  return res.data
}

export async function getLibraryEligible(jobId: string): Promise<{ eligible: boolean }> {
  const res = await apiClient.get(`/api/library/${jobId}/eligible`)
  return res.data
}

export async function purchaseLibraryAccess(): Promise<{ success: boolean; payment_url?: string; payment_id?: string; amount: number; message?: string }> {
  const res = await apiClient.post('/api/library/purchase')
  return res.data
}

export async function purchaseLibraryAccessPayme(): Promise<{ success: boolean; payment_url?: string; payment_id?: string; amount: number; message?: string }> {
  const res = await apiClient.post('/api/payments/payme/initiate-library')
  return res.data
}

// Uzum'da checkout havolasi yo'q -- initiateUzumPayment bilan bir xil sabab
// (backend/api/uzum_routes.py:initiate_library_payment). "account" raqami
// qaytadi, payment_url emas.
export async function purchaseLibraryAccessUzum(): Promise<{ success: boolean; account?: number; payment_id?: string; amount: number; message?: string }> {
  const res = await apiClient.post('/api/payments/uzum/initiate-library')
  return res.data
}

export async function initiateClickPayment(jobId: string): Promise<{ success: boolean; payment_url: string; payment_id?: string; amount: number }> {
  const res = await apiClient.post('/api/payments/click/initiate', { job_id: jobId })
  return res.data
}

export async function initiatePaymePayment(jobId: string): Promise<{ success: boolean; payment_url: string; payment_id?: string; amount: number }> {
  const res = await apiClient.post('/api/payments/payme/initiate', { job_id: jobId })
  return res.data
}

// Uzum'da checkout havolasi yo'q -- foydalanuvchi Uzum ilovasida shu "account"
// raqamini o'zi kiritib to'laydi (backend/api/uzum_routes.py). amount===0
// bo'lsa video allaqachon bepul/kvota bilan qoplangan (payment_url'siz holat
// bilan bir xil semantik).
export async function initiateUzumPayment(jobId: string): Promise<{ success: boolean; account?: number; payment_id?: string; amount: number }> {
  const res = await apiClient.post('/api/payments/uzum/initiate', { job_id: jobId })
  return res.data
}

export function getDownloadUrl(jobId: string): string {
  return `${API_URL}/api/outputs/${jobId}/video?download=1`
}

export interface ResolutionOption {
  resolution: string
  available: boolean
  status: string
}

export async function getJobResolutions(jobId: string): Promise<{ resolutions: ResolutionOption[] }> {
  const res = await apiClient.get(`/api/jobs/${jobId}/resolutions`)
  return res.data
}

export async function requestResolution(
  jobId: string,
  resolution: string,
  download: boolean = true,
): Promise<{ status: string; download_url?: string }> {
  const res = await apiClient.post(`/api/jobs/${jobId}/resolutions/${resolution}`, null, { params: { download } })
  return res.data
}

// Kutubxona (Ommaviy videolar) uchun -- sifat cheklovi TOMOSHABIN tarifiga
// qarab hisoblanadi, video egasiniki emas (backend/api/routes.py:
// list_library_resolutions / request_library_resolution).
export async function getLibraryJobResolutions(jobId: string): Promise<{ resolutions: ResolutionOption[] }> {
  const res = await apiClient.get(`/api/library/${jobId}/resolutions`)
  return res.data
}

export async function requestLibraryResolution(
  jobId: string,
  resolution: string,
  download: boolean = true,
): Promise<{ status: string; download_url?: string }> {
  const res = await apiClient.post(`/api/library/${jobId}/resolutions/${resolution}`, null, { params: { download } })
  return res.data
}

export interface PlanDef {
  id: string
  name: string
  price: number
  videos_per_period: number
  free_minutes: number
  priority: boolean
  tts_tier: string
  tier: string
  period_days: number
  max_resolution: string
}

export interface CurrentSubscription {
  plan: string
  expires_at: string | null
  videos_used_this_period: number
}

export async function getPlans(): Promise<{ plans: PlanDef[]; current: CurrentSubscription }> {
  const res = await apiClient.get('/api/plans')
  return res.data
}

export async function subscribeToPlan(plan: string): Promise<{ success: boolean; payment_url: string; payment_id?: string; amount: number }> {
  const res = await apiClient.post('/api/plans/subscribe', { plan })
  return res.data
}

export async function subscribeToPlanPayme(plan: string): Promise<{ success: boolean; payment_url: string; payment_id?: string; amount: number }> {
  const res = await apiClient.post('/api/payments/payme/initiate-subscription', { plan })
  return res.data
}

export function getVideoUrl(jobId: string): string {
  // /api/outputs/{id}/video (routes.py) S3'da bo'lsa presigned URL'ga
  // yo'naltiradi, mavjud bo'lmasa lokal faylga tushadi — statik
  // /outputs/{id}/... mount'idan farqli, S3'ga yuklangandan keyin lokal
  // nusxa o'chirilgan videolar uchun ham ishlaydi.
  return `${API_URL}/api/outputs/${jobId}/video`
}

export function getAudioUrl(jobId: string): string {
  return `${API_URL}/api/outputs/${jobId}/audio`
}

const JOB_KEY = "dubber_last_job"

export function saveJobId(id: string) {
  if (typeof window === "undefined") return
  localStorage.setItem(JOB_KEY, JSON.stringify({ id, ts: Date.now() }))
}

export function loadJobId(): string | null {
  if (typeof window === "undefined") return null
  try {
    const raw = localStorage.getItem(JOB_KEY)
    if (!raw) return null
    const { id, ts } = JSON.parse(raw)
    if (Date.now() - ts > 24 * 60 * 60 * 1000) {
      localStorage.removeItem(JOB_KEY)
      return null
    }
    return id ?? null
  } catch {
    return null
  }
}

export function clearJobId() {
  if (typeof window === "undefined") return
  localStorage.removeItem(JOB_KEY)
}

export async function cancelJob(jobId: string): Promise<{ success: boolean; message: string }> {
  const res = await apiClient.post(`/api/jobs/${jobId}/cancel`)
  return res.data
}

export async function submitFeedback(
  jobId: string,
  rating: number,
  comment?: string,
  extra?: { voice_ok?: boolean | null; translation_ok?: boolean | null; speed_ok?: boolean | null }
): Promise<{ success: boolean; message: string }> {
  const res = await apiClient.post(`/api/jobs/${jobId}/feedback`, { rating, comment, ...extra })
  return res.data
}

export async function submitPlatformFeedback(
  message: string,
  rating?: number
): Promise<{ success: boolean; message: string }> {
  const res = await apiClient.post(`/api/platform-feedback`, { message, rating })
  return res.data
}

/* ── Video Analysis ────────────────────────────────────────── */

export type AnalysisStatus =
  | 'pending'
  | 'downloading'
  | 'extracting_audio'
  | 'transcribing'
  | 'analyzing'
  | 'generating_results'
  | 'completed'
  | 'failed'

export const ANALYSIS_STATUS_LABELS: Record<AnalysisStatus, string> = {
  pending: 'Navbatda',
  downloading: 'Yuklanmoqda',
  extracting_audio: 'Audio ajratilmoqda',
  transcribing: 'Matnga aylantirilmoqda',
  analyzing: 'AI tahlil qilinmoqda',
  generating_results: 'Natijalar tayyorlanmoqda',
  completed: 'Tayyor',
  failed: 'Xatolik',
}

// Tahlil tili — video tilidan mustaqil: video qaysi tilda bo'lishidan qat'iy
// nazar, foydalanuvchi tahlil (summary/key_points/chapters/notes/quiz) qaysi
// tilda chiqishini shu ro'yxatdan tanlaydi. Transcript esa doim video'ning
// original tilida qoladi. "original" tanlansa, tahlil ham video tilida chiqadi.
export const ANALYSIS_LANGUAGE_OPTIONS: { code: string; label: string }[] = [
  { code: 'uz', label: "🇺🇿 O'zbekcha" },
  { code: 'en', label: '🇬🇧 English' },
  { code: 'ru', label: '🇷🇺 Русский' },
  { code: 'tr', label: '🇹🇷 Türkçe' },
  { code: 'kk', label: '🇰🇿 Қазақша' },
  { code: 'original', label: '🌐 Original tilda' },
]

export const LANGUAGE_DISPLAY: Record<string, string> = {
  uz: "🇺🇿 O'zbekcha", en: '🇬🇧 English', ru: '🇷🇺 Русский', tr: '🇹🇷 Türkçe', kk: '🇰🇿 Қазақша',
  es: '🇪🇸 Español', fr: '🇫🇷 Français', de: '🇩🇪 Deutsch', ko: '🇰🇷 한국어', ja: '🇯🇵 日本語',
  zh: '🇨🇳 中文', ar: '🇸🇦 العربية', pt: '🇵🇹 Português', it: '🇮🇹 Italiano', hi: '🇮🇳 हिन्दी',
}

export function displayLanguage(code?: string | null): string {
  if (!code) return ''
  return LANGUAGE_DISPLAY[code] || code
}

export interface TranscriptSegment {
  start: number
  end: number
  text: string
}

export interface KeyPoint {
  title: string
  description: string
  timestamp: number
}

export interface Chapter {
  title: string
  start: number
  end: number
}

export interface QuizQuestion {
  question: string
  options: string[]
  correct_answer: number
  explanation: string
  timestamp: number
}

export interface QAEntry {
  question: string
  answer: string
  timestamps: number[]
  asked_at: string
}

export interface BilingualSegment {
  start: number
  end: number
  original: string
  translated: string
}

export interface VideoAnalysisSummary {
  short: string
  medium: string
  detailed: string
}

export interface VideoAnalysis {
  id: string
  status: AnalysisStatus
  progress: number
  status_message?: string
  youtube_url: string
  video_title?: string
  video_duration?: number
  video_thumbnail?: string
  language: string
  video_language?: string
  summary?: VideoAnalysisSummary
  key_points?: KeyPoint[]
  chapters?: Chapter[]
  notes?: string
  quiz?: QuizQuestion[]
  qa_history: QAEntry[]
  error_message?: string
  error_code?: string
  created_at?: string
}

export async function createAnalysis(youtube_url: string, language: string = 'uz'): Promise<{ analysis_id: string; status: string }> {
  const res = await apiClient.post('/api/video-analysis', { youtube_url, language })
  return res.data
}

export async function getAnalysis(analysisId: string): Promise<VideoAnalysis> {
  const res = await apiClient.get(`/api/video-analysis/${analysisId}`)
  return res.data
}

export async function getTranscript(analysisId: string): Promise<{ segments: TranscriptSegment[] }> {
  const res = await apiClient.get(`/api/video-analysis/${analysisId}/transcript`)
  return res.data
}

export async function askQuestion(analysisId: string, question: string): Promise<QAEntry> {
  const res = await apiClient.post(`/api/video-analysis/${analysisId}/question`, { question })
  return res.data
}

export async function generateQuiz(analysisId: string): Promise<{ quiz: QuizQuestion[] }> {
  const res = await apiClient.post(`/api/video-analysis/${analysisId}/quiz`)
  return res.data
}

export async function generateNotes(analysisId: string): Promise<{ notes: string }> {
  const res = await apiClient.post(`/api/video-analysis/${analysisId}/notes`)
  return res.data
}

export async function generateBilingual(analysisId: string): Promise<{ segments: BilingualSegment[] }> {
  const res = await apiClient.post(`/api/video-analysis/${analysisId}/bilingual`)
  return res.data
}

export async function searchTranscript(analysisId: string, query: string): Promise<{ results: TranscriptSegment[] }> {
  const res = await apiClient.get(`/api/video-analysis/${analysisId}/search`, { params: { q: query } })
  return res.data
}

const ANALYSIS_KEY = "dubber_last_analysis"

export function saveAnalysisId(id: string) {
  if (typeof window === "undefined") return
  localStorage.setItem(ANALYSIS_KEY, JSON.stringify({ id, ts: Date.now() }))
}

export function loadAnalysisId(): string | null {
  if (typeof window === "undefined") return null
  try {
    const raw = localStorage.getItem(ANALYSIS_KEY)
    if (!raw) return null
    const { id, ts } = JSON.parse(raw)
    if (Date.now() - ts > 24 * 60 * 60 * 1000) {
      localStorage.removeItem(ANALYSIS_KEY)
      return null
    }
    return id ?? null
  } catch {
    return null
  }
}

export function clearAnalysisId() {
  if (typeof window === "undefined") return
  localStorage.removeItem(ANALYSIS_KEY)
}
