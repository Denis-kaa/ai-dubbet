'use client'
import { useState, useEffect, useCallback } from 'react'
import { User, getToken, setToken, setStoredUser, getStoredUser, clearAuth, apiLogin, apiRegister, apiMe, apiVerifyCode, apiResendCode, apiForgotPassword, apiResetPassword, apiGoogleAuth, apiRequestPhoneCode, apiVerifyPhoneCode } from '@/lib/auth'

export function useAuth() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = getToken()
    if (token) {
      const stored = getStoredUser()
      if (stored) {
        setUser(stored)
        setLoading(false)
      } else {
        apiMe(token)
          .then((u) => { setUser(u); setStoredUser(u) })
          .catch(() => clearAuth())
          .finally(() => setLoading(false))
      }
    } else {
      setLoading(false)
    }
  }, [])

  // Agar foydalanuvchi allaqachon verified bo'lsa, backend JWT qaytaradi
  // (pending_verification qaytmaydi). Verified bo'lmasa — email-kodi oqimi.
  const login = useCallback(async (email: string, password: string) => {
    const data = await apiLogin(email, password)
    if ('access_token' in data) {
      // Verified user — darhol kirish
      setToken(data.access_token)
      setStoredUser(data.user)
      setUser(data.user)
      return data.user
    }
    // Unverified — email-kodi kerak
    return data
  }, [])

  const register = useCallback(async (name: string, email: string, password: string) => {
    return apiRegister(name, email, password)
  }, [])

  const verifyCode = useCallback(async (email: string, code: string) => {
    const data = await apiVerifyCode(email, code)
    setToken(data.access_token)
    setStoredUser(data.user)
    setUser(data.user)
    return data.user
  }, [])

  const resendCode = useCallback(async (email: string) => {
    return apiResendCode(email)
  }, [])

  const forgotPassword = useCallback(async (email: string) => {
    return apiForgotPassword(email)
  }, [])

  const resetPassword = useCallback(async (email: string, code: string, newPassword: string) => {
    const data = await apiResetPassword(email, code, newPassword)
    setToken(data.access_token)
    setStoredUser(data.user)
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(() => {
    clearAuth()
    setUser(null)
  }, [])

  // Google va telefon kirishi bir bosqichli — email kodidan farqli, token
  // darhol qaytadi.
  const googleAuth = useCallback(async (credential: string) => {
    const data = await apiGoogleAuth(credential)
    setToken(data.access_token)
    setStoredUser(data.user)
    setUser(data.user)
    return data.user
  }, [])

  const requestPhoneCode = useCallback(async (phone: string) => {
    return apiRequestPhoneCode(phone)
  }, [])

  const verifyPhoneCode = useCallback(async (phone: string, code: string) => {
    const data = await apiVerifyPhoneCode(phone, code)
    setToken(data.access_token)
    setStoredUser(data.user)
    setUser(data.user)
    return data.user
  }, [])

  return {
    user, loading, login, register, verifyCode, resendCode, forgotPassword, resetPassword, logout,
    googleAuth, requestPhoneCode, verifyPhoneCode,
    isLoggedIn: !!user,
  }
}
