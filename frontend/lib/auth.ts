import Cookies from 'js-cookie'
import axios from 'axios'
import { getApiUrl } from './runtime-config'

const API_URL = getApiUrl()

export interface User {
  id: string
  name: string
  email: string | null
  role?: string
}

export interface AuthState {
  user: User | null
  token: string | null
}

// Cookie domain'siz login qilingan host'ga bog'lanib qoladi (masalan
// gapirai.uz), shuning uchun admin.gapirai.uz sessiyani ko'rmaydi. Barcha
// gapirai.uz subdomainlari o'rtasida bo'lishish uchun ".gapirai.uz"
// ishlatiladi -- localhost'da esa domain berilmaydi (browser rad etadi).
function cookieDomain(): string | undefined {
  if (typeof window === 'undefined') return undefined
  const host = window.location.hostname
  return host.endsWith('gapirai.uz') ? '.gapirai.uz' : undefined
}

export function getToken(): string | null {
  return Cookies.get('auth_token') || null
}

// Domain fikslanishidan oldin (shu fayldagi cookieDomain() qo'shilishidan
// oldin) login qilgan foydalanuvchilarda domainSIZ (host-only) "auth_token"
// cookie hali ham brauzerda turibdi. Endi faqat domain'li variantni
// tozalasak, ikkalasi BIR VAQTDA mavjud bo'lib qoladi -- brauzer ikkala
// qiymatni ham "auth_token=eski; auth_token=yangi" tarzida yuboradi va
// Cookies.get() qaysi birini qaytarishi noaniq (ba'zan eski, allaqachon
// yaroqsiz token qaytadi -- qayta login qilingandan keyin ham "Token
// yaroqsiz" xatosi shu sababdan davom etardi, 2026-08-25). Shuning uchun
// har doim IKKALA variantni ham (host-only VA domain'li) tozalab/yozib
// qo'yamiz -- eskisi mavjud bo'lmasa, remove() shunchaki hech narsa
// qilmaydi.
export function setToken(token: string) {
  Cookies.remove('auth_token')
  Cookies.remove('auth_token', { domain: cookieDomain() })
  Cookies.set('auth_token', token, { expires: 7, sameSite: 'lax', domain: cookieDomain() })
}

export function removeToken() {
  Cookies.remove('auth_token')
  Cookies.remove('auth_token', { domain: cookieDomain() })
}

export function getStoredUser(): User | null {
  try {
    const raw = localStorage.getItem('auth_user')
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setStoredUser(user: User) {
  localStorage.setItem('auth_user', JSON.stringify(user))
}

export function clearAuth() {
  removeToken()
  localStorage.removeItem('auth_user')
}

export interface PendingVerification {
  pending_verification: true
  email: string
  message: string
}

export async function apiRegister(name: string, email: string, password: string): Promise<PendingVerification> {
  const res = await axios.post(`${API_URL}/auth/register`, { name, email, password })
  return res.data
}

export async function apiLogin(email: string, password: string): Promise<PendingVerification | AuthResult> {
  const res = await axios.post(`${API_URL}/auth/login`, { email, password })
  return res.data
}

export async function apiVerifyCode(email: string, code: string) {
  const res = await axios.post(`${API_URL}/auth/verify-code`, { email, code })
  return res.data
}

export async function apiResendCode(email: string): Promise<PendingVerification> {
  const res = await axios.post(`${API_URL}/auth/resend-code`, { email })
  return res.data
}

export async function apiForgotPassword(email: string): Promise<PendingVerification> {
  const res = await axios.post(`${API_URL}/auth/forgot-password`, { email })
  return res.data
}

export async function apiResetPassword(email: string, code: string, newPassword: string) {
  const res = await axios.post(`${API_URL}/auth/reset-password`, { email, code, new_password: newPassword })
  return res.data
}

export async function apiMe(token: string): Promise<User> {
  const res = await axios.get(`${API_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.data
}

export interface AuthResult {
  access_token: string
  token_type: string
  user: User
}

export async function apiGoogleAuth(credential: string): Promise<AuthResult> {
  const res = await axios.post(`${API_URL}/auth/google`, { credential })
  return res.data
}

export interface PhonePendingVerification {
  pending_verification: true
  phone: string
  message: string
}

export async function apiRequestPhoneCode(phone: string): Promise<PhonePendingVerification> {
  const res = await axios.post(`${API_URL}/auth/phone/request-code`, { phone })
  return res.data
}

export async function apiVerifyPhoneCode(phone: string, code: string): Promise<AuthResult> {
  const res = await axios.post(`${API_URL}/auth/phone/verify-code`, { phone, code })
  return res.data
}
