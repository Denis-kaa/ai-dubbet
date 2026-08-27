import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: "Admin panel",
  description: "GapirAI.uz admin paneli.",
  // Private, admin-only content — never index or follow.
  robots: { index: false, follow: false },
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
