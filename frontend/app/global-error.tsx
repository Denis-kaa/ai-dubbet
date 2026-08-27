'use client'

// Next.js talabi: global-error.tsx ROOT layout'ning o'zida xato yuz bersa
// ishlaydi (error.tsx buni ushlay olmaydi, chunki u ham shu layout ichida
// render qilinadi) -- shuning uchun o'z <html>/<body>'sini o'zi belgilashi
// SHART, va Tailwind/global CSS pipeline'ga tayanmasligi kerak (root layout
// buzilgan bo'lishi mumkin bo'lgan holatda ishlashi kerak).
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="uz">
      <body style={{ margin: 0, fontFamily: 'system-ui, -apple-system, sans-serif' }}>
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1rem',
            background: '#f8f8fb',
          }}
        >
          <div style={{ textAlign: 'center', maxWidth: 400 }}>
            <h2 style={{ fontWeight: 700, fontSize: '1.25rem', marginBottom: '0.5rem', color: '#111827' }}>
              Nimadur noto'g'ri ketdi
            </h2>
            <p style={{ color: '#6b7280', fontSize: '0.875rem', marginBottom: '1.5rem', lineHeight: 1.6 }}>
              Ilovani yuklashda jiddiy xatolik yuz berdi. Qaytadan urinib ko'ring.
            </p>
            <button
              onClick={reset}
              style={{
                padding: '0.75rem 1.75rem',
                borderRadius: '1rem',
                background: '#4338ca',
                color: 'white',
                fontWeight: 700,
                fontSize: '0.875rem',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              Qaytadan urinish
            </button>
          </div>
        </div>
      </body>
    </html>
  )
}
