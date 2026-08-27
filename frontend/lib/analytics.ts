// Product-analytics eventlar — mavjud Yandex Metrika integratsiyasi (app/layout.tsx)
// ustiga qurilgan, yangi backend/provider qo'shilmagan. `ym` global funksiyasi
// Metrika skripti yuklanmagan bo'lsa mavjud emas (masalan reklama blokerlari) --
// shuning uchun har doim mavjudligini tekshiramiz va sahifa ishlashiga
// xalaqit bermaydigan tarzda jim ishlaymiz.

declare global {
  interface Window {
    ym?: (...args: unknown[]) => void
  }
}

const YM_COUNTER_ID = 111361158

// Faqat PII bo'lmagan, kategoriyaviy qiymatlar yuborilishi kerak (masalan
// "resolution": "720p", "provider": "click") — email, telefon, video sarlavhasi,
// YouTube URL yoki foydalanuvchi ismi HECH QACHON shu orqali yuborilmasin.
type EventParams = Record<string, string | number | boolean>

export function trackEvent(name: string, params?: EventParams): void {
  if (typeof window === 'undefined' || typeof window.ym !== 'function') return
  try {
    window.ym(YM_COUNTER_ID, 'reachGoal', name, params)
  } catch {
    // Analitika kuzatuvi sahifa funksionalligiga hech qachon xalaqit bermasligi kerak.
  }
}

// Bir xil (jobId, event) juftligi uchun bir marta ishlaydi -- komponent
// qayta mount bo'lganda yoki poll har safar chaqirilganda takroriy
// yuborilishning oldini oladi. backend/workers'dagi haqiqiy bosqich emas,
// faqat frontend poll orqali kuzatilgan bosqich o'tishi asosida ishlaydi.
export function trackOnce(key: string, name: string, params?: EventParams): void {
  if (typeof window === 'undefined') return
  const storageKey = `ym_evt_${name}_${key}`
  try {
    if (sessionStorage.getItem(storageKey)) return
    sessionStorage.setItem(storageKey, '1')
  } catch {
    // sessionStorage mavjud bo'lmasa (masalan private mode) baribir yuboramiz.
  }
  trackEvent(name, params)
}
