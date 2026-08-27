import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: "Tarif rejalari",
  description: "GapirAI.uz tarif rejalari — 45 daqiqagacha bo'lgan videolar bepul, undan uzun videolar uchun obuna va bir martalik to'lov variantlari.",
  alternates: { canonical: '/pricing' },
  openGraph: {
    title: "Tarif rejalari | GapirAI.uz",
    description: "45 daqiqagacha bo'lgan videolar bepul, undan uzun videolar uchun obuna va bir martalik to'lov variantlari.",
    url: "https://gapirai.uz/pricing",
    siteName: "GapirAI.uz",
    locale: "uz_UZ",
    type: "website",
    images: [{ url: "https://gapirai.uz/logo.webp", width: 256, height: 256, alt: "GapirAI.uz logotipi" }],
  },
  twitter: {
    card: "summary",
    title: "Tarif rejalari | GapirAI.uz",
    description: "45 daqiqagacha bo'lgan videolar bepul, undan uzun videolar uchun obuna va bir martalik to'lov variantlari.",
    images: ["https://gapirai.uz/logo.webp"],
  },
}

export default function PricingLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
