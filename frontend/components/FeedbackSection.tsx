'use client'

import { useState } from 'react'
import { Star, Send, CheckCircle2, Loader2, MessageSquare, ThumbsUp, ThumbsDown } from 'lucide-react'
import { submitFeedback } from '@/lib/api'

interface FeedbackSectionProps {
  jobId: string
  initialRating?: number
  initialComment?: string
}

type OkValue = boolean | null

function ThumbsQuestion({ label, value, onChange }: { label: string; value: OkValue; onChange: (v: OkValue) => void }) {
  return (
    <div className="flex items-center justify-between gap-3 bg-white/5 border border-white/5 rounded-xl px-3.5 py-2.5">
      <span className="text-xs text-slate-300 font-medium">{label}</span>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => onChange(value === true ? null : true)}
          aria-label={`${label}: yaxshi`}
          className={`p-1.5 rounded-lg transition ${
            value === true ? 'bg-emerald-500/20 text-emerald-400' : 'text-slate-500 hover:text-emerald-400 hover:bg-emerald-500/10'
          }`}
        >
          <ThumbsUp className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => onChange(value === false ? null : false)}
          aria-label={`${label}: yomon`}
          className={`p-1.5 rounded-lg transition ${
            value === false ? 'bg-violet-500/20 text-violet-400' : 'text-slate-500 hover:text-violet-400 hover:bg-violet-500/10'
          }`}
        >
          <ThumbsDown className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

export default function FeedbackSection({ jobId, initialRating, initialComment }: FeedbackSectionProps) {
  const [rating, setRating] = useState<number>(initialRating || 0)
  const [hoverRating, setHoverRating] = useState<number>(0)
  const [comment, setComment] = useState<string>(initialComment || '')
  const [voiceOk, setVoiceOk] = useState<OkValue>(null)
  const [translationOk, setTranslationOk] = useState<OkValue>(null)
  const [speedOk, setSpeedOk] = useState<OkValue>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(Boolean(initialRating))
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (rating === 0) {
      setError("Iltimos, kamida 1 ta yulduzcha tanlang.")
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      await submitFeedback(jobId, rating, comment, { voice_ok: voiceOk, translation_ok: translationOk, speed_ok: speedOk })
      setSubmitted(true)
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Fikr yuborishda xatolik yuz berdi. Qayta urinib ko'ring.")
    } finally {
      setSubmitting(false)
    }
  }

  const activeStars = hoverRating || rating

  return (
    <div className="bg-gradient-to-br from-slate-900/90 to-slate-800/80 border border-white/10 rounded-2xl p-6 shadow-xl backdrop-blur-sm space-y-4">
      <div className="flex items-center justify-between border-b border-white/10 pb-3">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-amber-500/10 rounded-xl text-amber-400">
            <Star className="w-5 h-5 fill-amber-400" />
          </div>
          <div>
            <h3 className="text-white font-bold text-base">Dublyaj sifatini baholang</h3>
            <p className="text-xs text-slate-400">Sizning fikringiz biz uchun juda muhim</p>
          </div>
        </div>
        {submitted && (
          <span className="flex items-center gap-1 text-xs font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1 rounded-full">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Fikr qabul qilindi
          </span>
        )}
      </div>

      {submitted ? (
        <div className="text-center py-4 space-y-3">
          <div className="flex justify-center gap-1.5">
            {[1, 2, 3, 4, 5].map((star) => (
              <Star
                key={star}
                className={`w-7 h-7 ${
                  star <= rating
                    ? 'text-amber-400 fill-amber-400 drop-shadow-[0_0_8px_rgba(251,191,36,0.5)]'
                    : 'text-slate-600'
                }`}
              />
            ))}
          </div>
          {comment && (
            <p className="text-sm text-slate-300 italic bg-white/5 border border-white/5 rounded-xl p-3 max-w-lg mx-auto">
              "{comment}"
            </p>
          )}
          <p className="text-xs text-emerald-400 font-medium">
            Katta rahmat! Fikringiz Telegram botimizga yuborildi. ⭐️
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4 pt-1">
          {/* Star Interactive Rating */}
          <div className="flex flex-col items-center justify-center space-y-2 py-2">
            <div className="flex items-center gap-2">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  type="button"
                  onClick={() => {
                    setRating(star)
                    setError(null)
                  }}
                  onMouseEnter={() => setHoverRating(star)}
                  onMouseLeave={() => setHoverRating(0)}
                  className="p-1 rounded-lg transition-transform duration-150 transform hover:scale-125 focus:outline-none"
                >
                  <Star
                    className={`w-8 h-8 transition-colors duration-150 ${
                      star <= activeStars
                        ? 'text-amber-400 fill-amber-400 drop-shadow-[0_0_10px_rgba(251,191,36,0.6)]'
                        : 'text-slate-600 hover:text-slate-400'
                    }`}
                  />
                </button>
              ))}
            </div>
            <p className="text-xs font-semibold text-amber-300/80 h-4">
              {activeStars === 1 && "Yomon 😞"}
              {activeStars === 2 && "Qoniqarsiz 😐"}
              {activeStars === 3 && "Yaxshi 🙂"}
              {activeStars === 4 && "Juda yaxshi 😊"}
              {activeStars === 5 && "Ajoyib, mukammal! 🤩"}
            </p>
          </div>

          {/* Structured questions */}
          <div className="space-y-2">
            <ThumbsQuestion label="Ovoz sifati" value={voiceOk} onChange={setVoiceOk} />
            <ThumbsQuestion label="Tarjima sifati" value={translationOk} onChange={setTranslationOk} />
            <ThumbsQuestion label="Tezlik (sinxronlik)" value={speedOk} onChange={setSpeedOk} />
          </div>

          {/* Comment Textarea */}
          <div className="space-y-1.5">
            <label className="text-xs text-slate-300 font-medium flex items-center gap-1.5">
              <MessageSquare className="w-3.5 h-3.5 text-blue-400" />
              Izoh (ixtiyoriy)
            </label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Ovoz sifati, tarjima yoki boshqa fikrlaringizni yozing..."
              rows={2}
              className="w-full bg-slate-950/60 border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition duration-200 resize-none"
            />
          </div>

          {error && (
            <p className="text-xs font-semibold text-violet-400 bg-violet-500/10 border border-violet-500/20 rounded-lg p-2.5 text-center">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting || rating === 0}
            className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-amber-500 to-yellow-600 hover:from-amber-400 hover:to-yellow-500 text-slate-950 font-bold py-3 px-4 rounded-xl transition duration-200 shadow-lg shadow-amber-500/10 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            {submitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <Send className="w-4 h-4" />
                Fikr va bahoni yuborish
              </>
            )}
          </button>
        </form>
      )}
    </div>
  )
}
