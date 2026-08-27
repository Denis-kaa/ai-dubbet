import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: "Dublyaj natijasi",
  description: "Dublyaj qilingan video natijasi.",
  // Ephemeral per-job result pages — no lasting search value.
  robots: { index: false, follow: false },
}

export default function VideoLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
