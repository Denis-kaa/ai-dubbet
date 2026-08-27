import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: "Videoni tomosha qilish | GapirAI.uz",
  description: "GapirAI.uz kutubxonasidan video.",
  // Login + to'lov talab qiladigan sahifa — Googlebot bunga kira olmaydi,
  // shuning uchun /library (ro'yxat) dan farqli, index qilinmasin.
  robots: { index: false, follow: false },
}

export default function LibraryItemLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
