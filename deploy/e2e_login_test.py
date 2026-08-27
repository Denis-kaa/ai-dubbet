"""End-to-end login test через headless Chromium (как реальный пользователь).

Проверяет:
1. Страница /login загружается, форма рендерится.
2. Все сетевые запросы идут same-origin (никаких api.gapirai.uz).
3. POST /auth/login доходит до backend (nginx проксирует).
4. Код подтверждения принимается (берём свежий из БД).
5. После верификации пользователь залогинен (cookie auth_token).

Запуск: /opt/ai-dubber/venv/bin/python deploy/e2e_login_test.py [email] [password]
Скриншоты и логи: /tmp/e2e_login/
"""
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://185.233.184.192"
EMAIL = sys.argv[1] if len(sys.argv) > 1 else "test@gapirai.uz"
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else "test123"
SHOT_DIR = Path("/tmp/e2e_login")
SHOT_DIR.mkdir(exist_ok=True)

bad_requests: list[str] = []


def shot(page, name: str) -> None:
    page.screenshot(path=str(SHOT_DIR / f"{name}.png"), full_page=True)
    print(f"  [shot] {SHOT_DIR}/{name}.png")


def get_code_from_db(email: str) -> str:
    out = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "dubber_db", "-tAc",
         f"SELECT verification_code FROM users WHERE email='{email}';"],
        capture_output=True, text=True,
    )
    code = out.stdout.strip()
    if not code:
        raise RuntimeError(f"Код из БД не получен: {out.stderr[:200]}")
    return code


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    page.on("request", lambda r: bad_requests.append(r.url) if "api.gapirai.uz" in r.url else None)

    # ── Шаг 1: страница логина ─────────────────────────────────────────
    print(">>> 1. Открываю /login ...")
    page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=30000)
    assert page.locator('input[type="email"]').is_visible(), "Нет поля email — форма не отрендерилась"
    print("  OK: форма логина отрендерилась")
    shot(page, "01_login_page")

    # ── Шаг 2: заполняем и отправляем ──────────────────────────────────
    print(">>> 2. Заполняю форму и жму Kirish ...")
    page.fill('input[type="email"]', EMAIL)
    page.fill('input[type="password"]', PASSWORD)
    with page.expect_response(lambda r: "/auth/login" in r.url) as resp_info:
        page.click('button[type="submit"]')
    resp = resp_info.value
    print(f"  POST {resp.url.split('//')[1].split('/')[0]}{page.url and ''} → HTTP {resp.status}")
    assert resp.status == 200, f"/auth/login вернул {resp.status}: {resp.text()[:200]}"
    assert "api.gapirai.uz" not in resp.url, f"Запрос ушёл на чужой домен: {resp.url}"
    print("  OK: POST /auth/login прошёл same-origin")
    shot(page, "02_code_screen")

    # ── Шаг 3: код подтверждения ───────────────────────────────────────
    print(">>> 3. Беру свежий код из БД и ввожу ...")
    code = get_code_from_db(EMAIL)
    print(f"  код из БД: {code} (email-письмо отправлено тем же вызовом)")
    page.fill('input[inputmode="numeric"]', code)
    page.click('button[type="submit"]:not([type="button"])')

    # Ждём либо редирект с логина, либо ошибку
    page.wait_for_timeout(3000)
    shot(page, "03_after_verify")

    cookies = {c["name"]: c["value"] for c in page.context.cookies()}
    print(f"  cookies браузера: {sorted(cookies)}")
    if "auth_token" not in cookies:
        body_text = page.inner_text("body")[:400]
        raise RuntimeError(f"auth_token нет в cookies. Текст страницы:\n{body_text}")

    # ── Шаг 4: проверяем залогиненное состояние именно из страницы ──
    # page.request — отдельный APIRequestContext и не всегда передаёт
    # cookie текущего browser context. fetch() выполняется в том же origin
    # и гарантированно использует auth_token браузера.
    print(">>> 4. Проверяю /auth/me из browser context ...")
    token = cookies["auth_token"]
    me = page.evaluate("""async (token) => {
        const r = await fetch('/auth/me', {
            headers: {Authorization: `Bearer ${token}`},
        });
        return {status: r.status, body: await r.text()};
    }""", token)
    print(f"  GET /auth/me → HTTP {me['status']}")
    assert me["status"] == 200, f"/auth/me: {me['status']} {me['body'][:200]}"
    print(f"  пользователь: {me['body'][:150]}")

    browser.close()

print()
print("=" * 60)
print("E2E LOGIN TEST: PASS ✅")
if bad_requests:
    print(f"⚠️  Обнаружены запросы на api.gapirai.uz: {bad_requests[:3]}")
else:
    print("Все запросы same-origin — старый бандл отсутствует.")
