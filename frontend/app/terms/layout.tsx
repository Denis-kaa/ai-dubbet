import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: "Foydalanish shartlari",
  description: "GapirAI.uz AI dublyaj platformasidan foydalanish shartlari, foydalanuvchi huquq va majburiyatlari hamda to'lov qoidalari.",
  alternates: { canonical: '/terms' },
}

export default function TermsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
