# Pricing & Business Logic Audit — GapirAI.uz

**Sana:** 2026-08-20
**Usul:** Read-only kod tekshiruvi — backend/services/plans.py, click_service.py, job_creation.py, routes.py, payme_routes.py ni "ground truth" (haqiqiy manba) sifatida olib, frontend/, mobile/ dagi barcha narx/limit matnlari shu bilan solishtirildi.
**Natija:** Hech qanday moliyaviy xavfli nomuvofiqlik topilmadi. Hech qanday kod bu auditda o'zgartirilmadi.

---

## 1. Haqiqiy narxlash mantig'i (ground truth)

Bu bo'lim — kodning o'zi qanday ishlashini tasvirlaydi, taxmin emas.

### Bepul chegarasi — 45 daqiqa
`backend/services/plans.py` — `_FREE_THRESHOLD_MINUTES = 45.0`

**Qoida:** 45 daqiqadan qisqa video — **har doim, har qanday foydalanuvchi uchun, tarifidan qat'i nazar bepul**. Bu `check_quota()` va `consume_quota()` funksiyalarida markazlashtirilgan.

### 45+ daqiqa uchun narx — 500 so'm/daqiqa
`backend/services/click_service.py` — `math.ceil(duration_minutes) * 500`

Bu formula pullik (bir martalik) video uchun ishlatiladi — obunasiz, aniq shu videoni dublyaj qilish uchun.

### Tarif rejalari (`PLANS` lug'ati, `plans.py`)

| Tarif | Narx | Video/oy | `free_minutes` | Rezolyutsiya |
|---|---|---|---|---|
| `free` | 0 so'm | 1 | 45.0 | 360p |
| `standard` | 49,000 so'm/oy | 8 | 60.0 | 720p |
| `standard_yearly` | 490,000 so'm/yil | 8 | 60.0 | 720p |
| `pro` | 149,000 so'm/oy | 30 | 90.0 | 1080p |
| `pro_yearly` | 1,490,000 so'm/yil | 30 | 90.0 | 1080p |

**Muhim nozik nuqta:** `standard`/`pro` tariflaridagi `free_minutes` (60/90) — bu haqiqiy davomiylik chegarasi **emas**. Kodning o'z izohi (`plans.py`, 2026-08-13 sanasi bilan) buni aniq tasdiqlaydi: pullik obunachilar uchun video davomiyligi **cheklanmagan** — faqat oyiga nechta video (`videos_per_period`) cheklanadi. `free_minutes` faqat narxlar sahifasida ko'rsatiladigan, marketing/ma'lumot maqsadidagi raqam, real enforcement emas. Bu — chalkashtirib bo'ladigan joy, lekin frontend bu haqiqatga to'g'ri mos: "cheklovsiz davomiylik" deb yozilgan, va bu to'g'ri.

### Boshqa doimiy narxlar

- **`CACHE_HIT_PRICE = 5,000 so'm`** (`job_creation.py`) — agar video allaqachon boshqa foydalanuvchi tomonidan dublyaj qilingan bo'lsa (kesh orqali qayta ishlatilsa) va bepul kvota qoplamasa, shu qat'iy narx qo'llaniladi (davomiylikka bog'liq emas).
- **`LIBRARY_ACCESS_PRICE = 5,000 so'm`** (`routes.py`) — kutubxonaga umrbod, bir martalik kirish narxi.
- **`MAX_VIDEO_DURATION_MINUTES = 180`** (`job_creation.py`) — barcha uchun qat'iy tavan (3 soat), tarifidan qat'i nazar. Hech qanday video bundan uzun qabul qilinmaydi.

### Vaqtinchalik, hozir FAOL bo'lgan istisno

`backend/api/routes.py` (259-317 qatorlar, 2026-08-19 sanasi bilan) — **kutubxona** (`/library/{job_id}/resolutions*`) endpointlarida barcha rezolyutsiyalar (1080p ham) **barcha tomoshabinlar uchun**, tarifidan qat'i nazar, bepul/ochiq qilib qo'yilgan — `get_max_resolution_for_user()` chetlab o'tilgan. Bu foydalanuvchining o'zi so'ragan, vaqtinchalik ("hozircha") qaror, hali ham kodda faol. Kutubxonaga aloqasi bo'lmagan oddiy job'lar (`/jobs/{job_id}/resolutions*`) uchun esa haqiqiy tarif-asosidagi cheklov ishlaydi.

---

## 2. Topilgan nomuvofiqliklar

**Yo'q.** Frontend (`frontend/app/**`), mobil ilova (`mobile/app/**`) va backend o'rtasida quyidagi barcha raqamlar to'liq mos tekshirildi:

- 45 daqiqa bepul chegarasi — hamma joyda mos (bosh sahifa, narxlar, FAQ, shartlar, video sahifasi, mobil ilova).
- 500 so'm/daqiqa formulasi — mos.
- Obuna narxlari va video kvotalari (49,000 / 149,000 / yillik variantlar) — mos.
- "Cheklovsiz davomiylik" da'vosi (pullik tariflar) — haqiqatga mos (yuqoridagi nozik nuqtaga qarang).
- Kutubxona kirish narxi (5,000 so'm) — mos.
- Rezolyutsiya cheklovlari — mos (va kutubxonadagi vaqtinchalik istisno hech qanday frontend matni bilan ziddiyatga kirmaydi, chunki qulflangan-rezolyutsiya UI'si hozircha "mavjud" holatga kelmaydi, shunchaki ishlatilmay turibdi).

### Oldin topilib, allaqachon tuzatilgan

- **`frontend/app/faq/faqs.ts`** — avval "1 soat (60 daqiqa)" deb yozilgan edi, bu audit boshlanishidan OLDIN, shu sessiya davomida **45 daqiqaga** tuzatilgan va serverga joylashtirilgan. Qayta tekshirildi — hozir to'g'ri.

## 3. Ziddiyat bo'lmagan, lekin e'tiborga molik kuzatuvlar

Bular **raqam nomuvofiqligi emas**, shunchaki kelajakda muammo bo'lishi mumkin bo'lgan joylar:

1. **Mobil ilovaning bepul-tarif fallback ro'yxati** (`mobile/app/pricing.tsx`) faqat 3 ta tarifni o'z ichiga oladi (yillik variantlar yo'q) va rezolyutsiya qatorini umuman ko'rsatmaydi — bu faqat login qilinmagan holatdagi zaxira ma'lumot, login qilingach haqiqiy backend ma'lumoti ishlatiladi. Noto'g'ri emas, shunchaki to'liqroq bo'lishi mumkin edi.
2. **`frontend/app/video/[id]/page.tsx:15`** — `TEST_PRICE_MULTIPLIER = 1.0` e'lon qilingan, lekin hech qayerda ishlatilmaydi (o'lik kod, funksional ta'siri yo'q, chunki qiymati 1.0).
3. **180 daqiqalik qat'iy tavan** (`MAX_VIDEO_DURATION_MINUTES`) frontend yoki mobil matnida umuman aytilmagan — foydalanuvchi shu chegaradan oshgan video yuborsa, nima uchun rad etilganini tushuntiruvchi maxsus matn yo'q (bu "raqamlar ziddiyati" emas, informatsion bo'shliq).

---

## Xulosa

Narxlash mantig'i **bitta markazda** (`backend/services/plans.py` + `click_service.py`) to'g'ri joylashtirilgan, va frontend/mobil bu manbadan og'ib ketmagan. Hech qanday darhol tuzatish talab qiladigan moliyaviy xavf topilmadi. Yagona keng ko'lamli, real kuzatuv — pullik tariflarda `free_minutes` maydonining "haqiqiy limit emas, faqat ko'rsatkich" ekanligi — bu chalkashtiruvchi nom, lekin xato emas, va kod izohida ataylab qilingan qaror sifatida hujjatlashtirilgan.
