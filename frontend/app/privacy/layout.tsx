import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: "Maxfiylik siyosati",
  description: "GapirAI.uz qanday shaxsiy ma'lumotlarni to'playdi, ularni qanday saqlaydi va himoya qiladi — maxfiylik siyosati.",
  alternates: { canonical: '/privacy' },
}

export default function PrivacyLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
