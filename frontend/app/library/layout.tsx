import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: "Ommaviy videolar",
  description: "Boshqa foydalanuvchilar tomonidan allaqachon o'zbek tiliga dublyaj qilingan videolar kutubxonasi — GapirAI.uz.",
  alternates: { canonical: '/library' },
  openGraph: {
    title: "Ommaviy videolar | GapirAI.uz",
    description: "Boshqa foydalanuvchilar tomonidan allaqachon o'zbek tiliga dublyaj qilingan videolar kutubxonasi.",
    url: "https://gapirai.uz/library",
    siteName: "GapirAI.uz",
    locale: "uz_UZ",
    type: "website",
    images: [{ url: "https://gapirai.uz/logo.webp", width: 256, height: 256, alt: "GapirAI.uz logotipi" }],
  },
  twitter: {
    card: "summary",
    title: "Ommaviy videolar | GapirAI.uz",
    description: "Boshqa foydalanuvchilar tomonidan allaqachon o'zbek tiliga dublyaj qilingan videolar kutubxonasi.",
    images: ["https://gapirai.uz/logo.webp"],
  },
}

export default function LibraryLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
