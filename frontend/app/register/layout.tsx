import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: "Ro'yxatdan o'tish",
  description: "GapirAI.uz platformasida bepul hisob yarating.",
  alternates: { canonical: '/register' },
  robots: { index: false, follow: true },
}

export default function RegisterLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
