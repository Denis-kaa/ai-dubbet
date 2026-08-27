"""Диагностика: что происходит на /login после клика."""
from playwright.sync_api import sync_playwright

BASE_URL = "http://185.233.184.192"
EMAIL = "test@gapirai.uz"
PASSWORD = "test123"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    page.on("request", lambda r: print(f"  REQ {r.method} {r.url[:110]}"))
    page.on("response", lambda r: print(f"  RES {r.status} {r.url[:110]}"))
    page.on("console", lambda m: print(f"  CON[{m.type}] {m.text[:160]}"))

    print(">>> open /login")
    page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=30000)

    print(">>> inputs visible?")
    email_input = page.locator('input[type="email"]')
    print("  email count:", email_input.count(), "visible:", email_input.is_visible())

    print(">>> fill + click")
    email_input.fill(EMAIL)
    page.locator('input[type="password"]').fill(PASSWORD)
    btns = page.locator('button[type="submit"]')
    print("  submit buttons:", btns.count())
    for i in range(btns.count()):
        b = btns.nth(i)
        print(f"    btn[{i}] visible={b.is_visible()} text={b.inner_text()!r}")
    # кликаем по видимому
    for i in range(btns.count()):
        if btns.nth(i).is_visible():
            print(f"  clicking btn[{i}]")
            btns.nth(i).click()
            break

    page.wait_for_timeout(5000)
    print(">>> after wait, url:", page.url)
    body = page.inner_text("body")
    print(">>> page text (600 chars):")
    print(body[:600])
    page.screenshot(path="/tmp/e2e_login/diag.png", full_page=True)
    browser.close()
