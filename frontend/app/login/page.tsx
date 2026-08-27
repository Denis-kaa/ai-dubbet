'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/hooks/useAuth'
import GoogleSignInButton from '@/components/GoogleSignInButton'
import { Eye, EyeOff, Loader2, Youtube, ArrowLeft, Phone } from 'lucide-react'
import { trackEvent } from '@/lib/analytics'

const PHONE_RE = /^\+998\d{9}$/

function MeshBackground() {
  return (
    <div className="mesh-gradient">
      <div className="mesh-gradient-blob blob-1" />
      <div className="mesh-gradient-blob blob-2" />
      <div className="mesh-gradient-blob blob-3" />
    </div>
  )
}

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [step, setStep] = useState<'form' | 'code' | 'phone-form' | 'phone-code'>('form')
  const [code, setCode] = useState('')
  const [resendLoading, setResendLoading] = useState(false)
  const [resendMessage, setResendMessage] = useState('')
  const [phone, setPhone] = useState('+998')
  const [phoneCode, setPhoneCode] = useState('')
  const { login, verifyCode, resendCode, googleAuth, requestPhoneCode, verifyPhoneCode } = useAuth()
  const router = useRouter()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const result = await login(email, password)
      if (result && 'id' in result) {
        // Verified user — login() qaytardi User object (id, name, email, role)
        trackEvent('login')
        router.push('/dashboard')
      } else {
        // Unverified — PendingVerification qaytadi (pending_verification, email, message)
        setStep('code')
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Xatolik yuz berdi.')
    } finally {
      setLoading(false)
    }
  }

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await verifyCode(email, code)
      trackEvent('login')
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
      await resendCode(email)
      setResendMessage('Yangi kod yuborildi.')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Kodni qayta yuborishda xatolik')
    } finally {
      setResendLoading(false)
    }
  }

  async function handleGoogleCredential(credential: string) {
    setError('')
    setLoading(true)
    try {
      await googleAuth(credential)
      trackEvent('login')
      router.push('/dashboard')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Google orqali kirishda xatolik yuz berdi.')
    } finally {
      setLoading(false)
    }
  }

  async function handlePhoneRequestCode(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (!PHONE_RE.test(phone)) {
      setError("Telefon raqami +998XXXXXXXXX formatida bo'lishi kerak.")
      return
    }
    setLoading(true)
    try {
      await requestPhoneCode(phone)
      setStep('phone-code')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Xatolik yuz berdi.')
    } finally {
      setLoading(false)
    }
  }

  async function handlePhoneVerify(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await verifyPhoneCode(phone, phoneCode)
      trackEvent('login')
      router.push('/dashboard')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Kod noto\'g\'ri yoki muddati tugagan')
    } finally {
      setLoading(false)
    }
  }

  async function handlePhoneResend() {
    setError('')
    setResendMessage('')
    setResendLoading(true)
    try {
      await requestPhoneCode(phone)
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

      {/* Orqaga */}
      <Link href="/" className="absolute top-6 left-6 flex items-center gap-2 text-gray-500 hover:text-blue-600 dark:hover:text-blue-400 font-bold transition text-xs uppercase tracking-widest">
        <ArrowLeft className="w-4 h-4" />
        Bosh sahifa
      </Link>

      <div className="w-full max-w-md z-10">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="flex flex-col items-center gap-3">
            <div className="p-2 transition duration-300 hover:scale-[1.02]">
              <img src="/logo.webp" alt="GapirAI.uz Logo" width={160} height={80} className="h-20 w-auto object-contain dark:hidden" />
              <img src="/logodark.webp" alt="GapirAI.uz Logo" width={160} height={80} className="h-20 w-auto object-contain hidden dark:block" />
            </div>
            <p className="text-xs text-blue-600/80 dark:text-blue-400/80 font-bold uppercase tracking-widest mt-2">Hisobingizga kiring</p>
          </div>
        </div>

        {/* Card */}
        <div className="glass-card rounded-[32px] p-8 sm:p-10">
          {step === 'form' && (
            <div className="space-y-6 mb-6">
              <GoogleSignInButton onCredential={handleGoogleCredential} />
              <div className="flex items-center gap-3">
                <div className="h-px flex-1 bg-black/10 dark:bg-white/10" />
                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">yoki</span>
                <div className="h-px flex-1 bg-black/10 dark:bg-white/10" />
              </div>
            </div>
          )}

          {step === 'form' && (
            <form onSubmit={handleSubmit} className="space-y-6">
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

              <div className="space-y-2">
                <div className="flex items-center justify-between ml-1 mr-1">
                  <label className="text-[10px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest">Parol</label>
                  <Link href="/forgot-password" className="text-[10px] font-bold text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition">
                    Parolni unutdingizmi?
                  </Link>
                </div>
                <div className="relative">
                  <input
                    type={showPass ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    required
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

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-500 hover:to-violet-500 active:scale-[0.99] text-white font-extrabold py-3.5 rounded-2xl transition-all duration-300 flex items-center justify-center gap-2 text-sm shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 disabled:opacity-50 cursor-pointer"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {loading ? 'Kirilmoqda...' : 'Kirish'}
              </button>

              <button
                type="button"
                onClick={() => { setStep('phone-form'); setError('') }}
                className="w-full flex items-center justify-center gap-2 text-xs font-bold text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition"
              >
                <Phone className="w-3.5 h-3.5" />
                Telefon orqali kirish
              </button>
            </form>
          )}

          {step === 'code' && (
            <form onSubmit={handleVerify} className="space-y-6">
              <div className="text-center space-y-1">
                <p className="text-sm font-bold text-black dark:text-white">Tasdiqlash kodi yuborildi</p>
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
                disabled={loading || code.length !== 6}
                className="w-full bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-500 hover:to-violet-500 active:scale-[0.99] text-white font-extrabold py-3.5 rounded-2xl transition-all duration-300 flex items-center justify-center gap-2 text-sm shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 disabled:opacity-50 cursor-pointer"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {loading ? 'Tekshirilmoqda...' : 'Tasdiqlash'}
              </button>

              <div className="flex items-center justify-between text-xs">
                <button
                  type="button"
                  onClick={() => setStep('form')}
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

          {step === 'phone-form' && (
            <form onSubmit={handlePhoneRequestCode} className="space-y-6">
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest ml-1">Telefon raqami</label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+998901234567"
                  required
                  autoFocus
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
                {loading ? 'Yuborilmoqda...' : 'Kod yuborish'}
              </button>

              <button
                type="button"
                onClick={() => { setStep('form'); setError('') }}
                className="w-full text-center text-xs font-bold text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition"
              >
                Orqaga
              </button>
            </form>
          )}

          {step === 'phone-code' && (
            <form onSubmit={handlePhoneVerify} className="space-y-6">
              <div className="text-center space-y-1">
                <p className="text-sm font-bold text-black dark:text-white">Tasdiqlash kodi yuborildi</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  <span className="font-semibold text-blue-600 dark:text-blue-400">{phone}</span> raqamiga 6 xonali kod yubordik.
                </p>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest ml-1">Tasdiqlash kodi</label>
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={phoneCode}
                  onChange={(e) => setPhoneCode(e.target.value.replace(/\D/g, ''))}
                  placeholder="000000"
                  required
                  autoFocus
                  className="w-full bg-black/[0.02] dark:bg-white/[0.02] border border-black/5 dark:border-white/10 rounded-2xl px-5 py-3.5 text-center text-2xl tracking-[0.5em] text-black dark:text-white placeholder-slate-400 dark:placeholder-gray-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all font-bold"
                />
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
                disabled={loading || phoneCode.length !== 6}
                className="w-full bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-500 hover:to-violet-500 active:scale-[0.99] text-white font-extrabold py-3.5 rounded-2xl transition-all duration-300 flex items-center justify-center gap-2 text-sm shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 disabled:opacity-50 cursor-pointer"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {loading ? 'Tekshirilmoqda...' : 'Tasdiqlash'}
              </button>

              <div className="flex items-center justify-between text-xs">
                <button
                  type="button"
                  onClick={() => setStep('phone-form')}
                  className="text-gray-500 dark:text-gray-400 font-bold hover:text-blue-600 dark:hover:text-blue-400 transition"
                >
                  Orqaga
                </button>
                <button
                  type="button"
                  onClick={handlePhoneResend}
                  disabled={resendLoading}
                  className="text-blue-600 dark:text-blue-400 font-bold hover:underline disabled:opacity-50"
                >
                  {resendLoading ? 'Yuborilmoqda...' : "Kodni qayta yuborish"}
                </button>
              </div>
            </form>
          )}

          {step === 'form' && (
            <p className="text-center text-gray-500 dark:text-gray-400 text-xs font-bold mt-8">
              Hisobingiz yo'qmi?{' '}
              <Link href="/register" className="text-blue-600 dark:text-blue-400 hover:underline">
                Ro'yxatdan o'ting
              </Link>
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
