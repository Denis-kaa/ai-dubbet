"""
YouTube cookie manager.
Playwright orqali headless Chrome bilan YouTube ga login qilib,
cookilarni avtomatik yangilab turadi.

2026-08-25 audit tuzatishi (AUDIT_STABILITY.md §2):
- `cookies_are_fresh()` endi sun'iy meta-faylga emas, cookie faylning
  O'ZIDAGI eng kech `expires` qiymatiga qaraydi (meta-fayl eski
  dizaynda konteynerning effemer qatlamida yashardi va qayta ishga
  tushishda yo'qolardi).
- `_save_cookies_netscape()` endi atomik yozadi (tmp + os.replace) —
  yarim yozilgan fayl hech qachon yt-dlp'ga ko'rinmaydi.
- Qo'shildi `min_cookie_expiry()` — tashqi monitoring uchun foydali
  (health-check: "kuки истекут через N дней").
"""
import asyncio
import json
import os
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

COOKIES_FILE = "/app/cookies.txt"
COOKIES_META_FILE = "/app/cookies_meta.json"
REFRESH_INTERVAL_HOURS = 12  # Har 12 soatda yangilash (meta-fayl eski dizaynidan qolgan)
# Freshness kuki: eng erta expires'dan shuncha kun oldin "eski" deb hisoblanadi.
# YouTube sessiya kukilarining typik qiymati "expires=0" bo'ladi (sessiya) — ular
# hisobga olinmaydi; faqat aniq sanali kukilar (SAPISID/SSID kabi) hisobga olinadi.
COOKIE_FRESH_DAYS = 7


def min_cookie_expiry() -> float:
    """Eng erta (minimal) expires qiymatini qaytaradi (epoch seconds).
    Fayl yo'q yoki sanali kuки yo'q bo'lsa 0 qaytaradi."""
    if not os.path.exists(COOKIES_FILE):
        return 0.0
    expires_vals = []
    try:
        with open(COOKIES_FILE) as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 5 and parts[4].isdigit():
                    val = int(parts[4])
                    if val > 0:
                        expires_vals.append(val)
    except Exception:
        return 0.0
    return float(min(expires_vals)) if expires_vals else 0.0


def cookies_are_fresh() -> bool:
    """Cookie fayl yengilligi: eng erta expires hali ham COOKIE_FRESH_DAYS
    kelajagida. Bu meta-fayldan emas — fayl o'zida haqiqiy expiry
    (AUDIT_STABILITY.md §2.1)."""
    expiry = min_cookie_expiry()
    if expiry <= 0:
        return False
    return expiry > time.time() + COOKIE_FRESH_DAYS * 86400


async def refresh_cookies(youtube_email: str, youtube_password: str) -> bool:
    """
    Playwright orqali YouTube ga login qilib cookilarni yangilash.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright o'rnatilmagan. pip install playwright && playwright install chromium")
        return False

    logger.info("YouTube cookielari yangilanmoqda...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            ignore_default_args=["--enable-automation"],
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--disable-infobars",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = await context.new_page()

        try:
            # YouTube ga o'tib, Sign in tugmasini bosish
            await page.goto("https://www.youtube.com", timeout=60000)
            await page.wait_for_timeout(3000)

            # Cookie consent modal bo'lsa qabul qilish
            try:
                accept_btn = await page.wait_for_selector(
                    'button[aria-label*="Accept"], button:has-text("Accept all")', timeout=5000
                )
                await accept_btn.click()
                await page.wait_for_timeout(2000)
            except Exception:
                pass

            # Sign in tugmasi yoki to'g'ri login sahifasi
            try:
                signin_btn = await page.wait_for_selector('a[aria-label*="Sign in"], a[href*="ServiceLogin"]', timeout=5000)
                await signin_btn.click()
                await page.wait_for_timeout(3000)
            except Exception:
                await page.goto("https://accounts.google.com/ServiceLogin?service=youtube", timeout=60000)

            # Email kiritish
            email_inp = await page.wait_for_selector('input[name="identifier"], input[type="email"]', timeout=30000)
            await email_inp.fill(youtube_email)
            await page.click('button:has-text("Next"), #identifierNext')
            await page.wait_for_timeout(3000)

            # Parol kiritish
            pwd_inp = await page.wait_for_selector('input[name="Passwd"], input[name="password"], input[type="password"]', timeout=30000)
            await pwd_inp.fill(youtube_password)
            await page.click('button:has-text("Next"), #passwordNext')
            await page.wait_for_timeout(5000)

            # YouTube ga o'tish tekshiruvi
            if "youtube.com" not in page.url:
                await page.goto("https://www.youtube.com", timeout=60000)
                await page.wait_for_timeout(3000)

            # Cookilarni Netscape formatida saqlash
            cookies = await context.cookies()
            _save_cookies_netscape(cookies, COOKIES_FILE)

            # Meta ma'lumot saqlash
            with open(COOKIES_META_FILE, "w") as f:
                json.dump({"updated_at": datetime.utcnow().isoformat()}, f)

            logger.info(f"Cookie yangilandi: {len(cookies)} ta cookie saqlandi.")
            return True

        except Exception as e:
            logger.error(f"Cookie yangilashda xatolik: {e}")
            return False
        finally:
            await browser.close()


def _save_cookies_netscape(cookies: list, filepath: str) -> None:
    """Playwright cookilarini Netscape/Mozilla formatiga aylantirish (yt-dlp uchun)."""
    lines = ["# Netscape HTTP Cookie File\n"]
    for c in cookies:
        domain = c.get("domain", "")
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure", False) else "FALSE"
        exp_raw = c.get("expires", 0)
        expires = int(exp_raw) if exp_raw and exp_raw > 0 else 0
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")

    # Atomik yozish: oldin tmp — keyin os.replace(). Agar jarayon ortada
    # qulasa, eski fay nigina buzilmay qoladi; yt-dlp hech qachon yarim
    # yozilgan faylni o'qimaydi. (AUDIT_STABILITY.md §2.2)
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "w") as f:
        f.writelines(lines)
    os.replace(tmp_path, filepath)


def get_or_refresh_cookies_sync(email: str, password: str) -> str | None:
    """
    Sync wrapper — agar cookie eski bo'lsa yangilaydi.
    Celery task dan chaqirish uchun.
    Returns: cookie fayl yo'li yoki None
    """
    if not cookies_are_fresh():
        asyncio.run(refresh_cookies(email, password))

    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        return COOKIES_FILE
    return None
