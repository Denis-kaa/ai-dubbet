'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/hooks/useAuth'
import { Eye, EyeOff, Loader2, ArrowLeft } from 'lucide-react'

function MeshBackground() {
  return (
    <div className="mesh-gradient">
      <div className="mesh-gradient-blob blob-1" />
      <div className="mesh-gradient-blob blob-2" />
      <div className="mesh-gradient-blob blob-3" />
    </div>
  )
}

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [step, setStep] = useState<'email' | 'reset'>('email')
  const [resendLoading, setResendLoading] = useState(false)
  const [resendMessage, setResendMessage] = useState('')
  const { forgotPassword, resetPassword } = useAuth()
  const router = useRouter()

  async function handleRequestCode(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await forgotPassword(email)
      setStep('reset')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Xatolik yuz berdi.')
    } finally {
      setLoading(false)
    }
  }

  async function handleReset(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await resetPassword(email, code, newPassword)
      router.push('/dashboard')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Kod noto\'g\'ri yoki muddati tugagan')
    } finally {
      setLoading(false)
    }
  }

  async function handleResend() {
    setError('')
    setResendMessage('')
    setResendLoading(true)
    try {
      await forgotPassword(email)
      setResendMessage('Yangi kod yuborildi.')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Kodni qayta yuborishda xatolik')
    } finally {
      setResendLoading(false)
    }
  }

  return (
    <div className="min-h-screen relative flex items-center justify-center p-6 transition-colors duration-300">
      <MeshBackground />

      <Link href="/login" className="absolute top-6 left-6 flex items-center gap-2 text-gray-500 hover:text-blue-600 dark:hover:text-blue-400 font-bold transition text-xs uppercase tracking-widest">
        <ArrowLeft className="w-4 h-4" />
        Kirish
      </Link>

      <div className="w-full max-w-md z-10">
        <div className="text-center mb-8">
          <div className="flex flex-col items-center gap-3">
            <div className="p-2 transition duration-300 hover:scale-[1.02]">
              <img src="/logo.webp" alt="GapirAI.uz Logo" width={160} height={80} className="h-20 w-auto object-contain dark:hidden" />
              <img src="/logodark.webp" alt="GapirAI.uz Logo" width={160} height={80} className="h-20 w-auto object-contain hidden dark:block" />
            </div>
            <p className="text-xs text-blue-600/80 dark:text-blue-400/80 font-bold uppercase tracking-widest mt-2">Parolni tiklash</p>
          </div>
        </div>

        <div className="glass-card rounded-[32px] p-8 sm:p-10">
          {step === 'email' ? (
            <form onSubmit={handleRequestCode} className="space-y-6">
              <div className="text-center space-y-1 mb-2">
                <p className="text-sm font-bold text-black dark:text-white">Parolingizni unutdingizmi?</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">Emailingizni kiriting, tiklash kodini yuboramiz.</p>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest ml-1">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="email@example.com"
                  required
                  className="w-full bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/10 rounded-2xl px-5 py-3.5 text-sm text-black dark:text-white placeholder-slate-400 dark:placeholder-gray-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all font-medium"
                />
              </div>

              {error && (
                <div className="bg-blue-500/10 border border-blue-500/20 rounded-2xl px-5 py-4 text-blue-600 dark:text-blue-400 text-xs font-semibold leading-relaxed">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-500 hover:to-violet-500 active:scale-[0.99] text-white font-extrabold py-3.5 rounded-2xl transition-all duration-300 flex items-center justify-center gap-2 text-sm shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 disabled:opacity-50 cursor-pointer"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {loading ? 'Yuborilmoqda...' : 'Tiklash kodini yuborish'}
              </button>
            </form>
          ) : (
            <form onSubmit={handleReset} className="space-y-6">
              <div className="text-center space-y-1">
                <p className="text-sm font-bold text-black dark:text-white">Tiklash kodi yuborildi</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  <span className="font-semibold text-blue-600 dark:text-blue-400">{email}</span> manziliga 6 xonali kod yubordik.
                </p>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest ml-1">Tasdiqlash kodi</label>
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                  placeholder="000000"
                  required
                  autoFocus
                  className="w-full bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/10 rounded-2xl px-5 py-3.5 text-center text-2xl tracking-[0.5em] text-black dark:text-white placeholder-slate-400 dark:placeholder-gray-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all font-bold"
                />
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest ml-1">Yangi parol</label>
                <div className="relative">
                  <input
                    type={showPass ? 'text' : 'password'}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    minLength={6}
                    className="w-full bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/10 rounded-2xl px-5 py-3.5 pr-12 text-sm text-black dark:text-white placeholder-slate-400 dark:placeholder-gray-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all font-medium"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition"
                  >
                    {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {error && (
                <div className="bg-blue-500/10 border border-blue-500/20 rounded-2xl px-5 py-4 text-blue-600 dark:text-blue-400 text-xs font-semibold leading-relaxed">
                  {error}
                </div>
              )}
              {resendMessage && (
                <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-2xl px-5 py-4 text-emerald-600 dark:text-emerald-400 text-xs font-semibold leading-relaxed">
                  {resendMessage}
                </div>
              )}

              <button
                type="submit"
                disabled={loading || code.length !== 6 || newPassword.length < 6}
                className="w-full bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-500 hover:to-violet-500 active:scale-[0.99] text-white font-extrabold py-3.5 rounded-2xl transition-all duration-300 flex items-center justify-center gap-2 text-sm shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 disabled:opacity-50 cursor-pointer"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {loading ? 'Yangilanmoqda...' : 'Parolni yangilash'}
              </button>

              <div className="flex items-center justify-between text-xs">
                <button
                  type="button"
                  onClick={() => setStep('email')}
                  className="text-gray-500 dark:text-gray-400 font-bold hover:text-blue-600 dark:hover:text-blue-400 transition"
                >
                  Orqaga
                </button>
                <button
                  type="button"
                  onClick={handleResend}
                  disabled={resendLoading}
                  className="text-blue-600 dark:text-blue-400 font-bold hover:underline disabled:opacity-50"
                >
                  {resendLoading ? 'Yuborilmoqda...' : "Kodni qayta yuborish"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
