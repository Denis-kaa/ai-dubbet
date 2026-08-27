import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: "Parolni tiklash",
  description: "GapirAI.uz hisobingiz parolini tiklang.",
  alternates: { canonical: '/forgot-password' },
  // Thin, duplicate-prone auth page — keep it out of the index but let Google
  // follow the links on it (same treatment as /login and /register).
  robots: { index: false, follow: true },
}

export default function ForgotPasswordLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
