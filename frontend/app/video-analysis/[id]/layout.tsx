import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: "Video tahlili",
  description: "Video tahlili natijasi.",
  // Ephemeral per-job result pages — no lasting search value (same treatment
  // as /video/[id]).
  robots: { index: false, follow: false },
}

export default function VideoAnalysisLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
