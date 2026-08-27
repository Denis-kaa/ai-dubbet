import type { Metadata } from 'next'
import { FAQS } from './faqs'

export const metadata: Metadata = {
  title: "Yordam va tez-tez so'raladigan savollar (FAQ)",
  description: "GapirAI.uz orqali YouTube videolarni o'zbek tiliga dublyaj qilish haqida eng ko'p beriladigan savollarga javoblar: narx, davomiylik, xatoliklar.",
  alternates: { canonical: '/faq' },
}

const faqSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": FAQS.map((faq) => ({
    "@type": "Question",
    "name": faq.q,
    "acceptedAnswer": { "@type": "Answer", "text": faq.a },
  })),
}

export default function FaqLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }}
      />
      {children}
    </>
  )
}
