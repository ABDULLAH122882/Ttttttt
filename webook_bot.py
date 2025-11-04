# -*- coding: utf-8 -*-
import os, re, sys, time, random, urllib.parse
from typing import List
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

HEADLESS = os.getenv("HEADLESS", "1") != "0"
TIMEOUT_MS = int(os.getenv("TIMEOUT_MS", "120000"))
EMAIL = os.getenv("WEBOOK_EMAIL", "")
PASSWORD = os.getenv("WEBOOK_PASSWORD", "")
BASE_HOME = "https://webook.com/ar"
ART_DIR = "artifacts"
VIDEO_DIR = f"{ART_DIR}/videos"
os.makedirs(ART_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

def log(m): print(m, flush=True)
def snooze(a=0.4, b=1.2): time.sleep(random.uniform(a, b))

def wait_idle(page): 
    try: page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
    except: pass

def handle_cookies(page):
    try:
        btns = page.locator("button:has-text('رفض'), button:has-text('قبول'), button:has-text('Accept'), button:has-text('Reject')")
        if btns.count():
            btns.first.click()
            log("✅ تعامل مع الكوكيز")
            snooze()
    except: pass

def ensure_login(page):
    if page.locator("input[type='email']").count():
        page.fill("input[type='email']", EMAIL)
        page.fill("input[type='password']", PASSWORD)
        log("✅ أدخل البريد وكلمة المرور")
        snooze(1,2)
        page.click("button:has-text('تسجيل الدخول'), button:has-text('Log in')")
        wait_idle(page)
        snooze(2,3)

def bump_tickets(page, count=5):
    log("🎟️ محاولة الضغط على زر + خمس مرات")
    plus_selectors = [
        "button:has(svg)", "button[aria-label*='plus']",
        "button:has-text('+')", "[role=button]:has-text('+')",
        "button:has-text('زيادة')", "div:has-text('+')", "span:has-text('+')"
    ]
    for sel in plus_selectors:
        try:
            btn = page.locator(sel).first
            if btn.count():
                for i in range(count):
                    btn.click()
                    log(f"➕ ضغطة رقم {i+1}")
                    snooze(0.6, 1.0)
                return True
        except: pass

    # محاولة احتياطية بالنقر حول الرقم 0
    try:
        zero = page.locator("text='0'").first
        box = zero.locator("xpath=..").first
        btns = box.locator("button, div, span")
        for i in range(min(5, btns.count())):
            btns.nth(i).click()
            log(f"🔁 ضغطة احتياطية {i+1}")
            snooze(0.6, 1.0)
        return True
    except Exception as e:
        log(f"⚠️ لم يتم العثور على زر + : {e}")
        return False

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(record_video_dir=VIDEO_DIR)
        page = context.new_page()
        page.goto(f"{BASE_HOME}/zones/suwaidi-park-rs25/book")
        wait_idle(page)
        handle_cookies(page)
        ensure_login(page)
        bump_tickets(page, 5)
        page.screenshot(path=f"{ART_DIR}/final.png", full_page=True)
        log("📸 تم حفظ لقطة الشاشة النهائية")
        context.close()
        browser.close()

if __name__ == "__main__":
    run()
