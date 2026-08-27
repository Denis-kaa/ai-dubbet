import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: "Kirish",
  description: "GapirAI.uz hisobingizga kiring.",
  alternates: { canonical: '/login' },
  // Thin, duplicate-prone auth page — keep it out of the index but let Google
  // follow the links on it.
  robots: { index: false, follow: true },
}

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
