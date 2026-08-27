'use client'

import { Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { setToken, setStoredUser, apiMe } from '@/lib/auth'

function CallbackContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [status, setStatus] = useState('Autentifikatsiya qilinmoqda...')

  useEffect(() => {
    const token = searchParams.get('token')
    if (!token) {
      setStatus('Xato: token topilmadi. Linkni to\'g\'ri oching.')
      return
    }

    setToken(token)

    apiMe(token)
      .then((user) => {
        setStoredUser(user)
        setStatus('Muvaffaqiyatli! Dashboardga o\'tmoqda...')
        setTimeout(() => router.push('/dashboard'), 500)
      })
      .catch(() => {
        setStatus('Xato: token yaroqsiz yoki muddati o\'tgan.')
      })
  }, [searchParams, router])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white rounded-xl shadow-lg p-8 max-w-md w-full text-center">
        <div className="mb-4">
          <div className="animate-spin w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full mx-auto" />
        </div>
        <p className="text-gray-700 text-lg">{status}</p>
      </div>
    </div>
  )
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-500">Yuklanmoqda...</p>
      </div>
    }>
      <CallbackContent />
    </Suspense>
  )
}
