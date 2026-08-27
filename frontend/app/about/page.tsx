import type { Metadata } from 'next'
import AboutClient from './AboutClient'

export const metadata: Metadata = {
  title: "Loyiha haqida",
  description: "GapirAI.uz platformasi va sun'iy intellekt yordamida videolarni o'zbek tiliga avtomatik dublyaj qilish loyihasi haqida batafsil ma'lumot.",
  keywords: [
    "gapirai haqida",
    "gapir ai haqida",
    "dublyaj dasturi",
    "dublaj dasturi",
    "dublyaj programmasi",
    "dublaj programmasi",
    "ai dublyaj texnologiyasi",
    "o'zbekcha ai dublyaj",
  ],
  alternates: {
    canonical: "/about",
  },
  openGraph: {
    title: "Loyiha haqida | GapirAI.uz",
    description: "YouTube va boshqa videolarni sun'iy intellekt yordamida o'zbek tiliga avtomatik dublyaj qiluvchi loyiha haqida.",
    url: "https://gapirai.uz/about",
    siteName: "GapirAI.uz",
    locale: "uz_UZ",
    type: "website",
    images: [{ url: "https://gapirai.uz/logo.webp", width: 256, height: 256, alt: "GapirAI.uz logotipi" }],
  },
  twitter: {
    card: "summary",
    title: "Loyiha haqida | GapirAI.uz",
    description: "Videolarni AI yordamida o'zbek tiliga dublyaj qiluvchi platforma haqida.",
    images: ["https://gapirai.uz/logo.webp"],
  },
}

export default function AboutPage() {
  return <AboutClient />
}
