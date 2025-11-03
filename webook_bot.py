# webook_bot.py (تحديث: إدخال الإيميل والباسورد + تسجيل الدخول)
import os, re, time, random
from datetime import datetime
from playwright.sync_api import sync_playwright

def log(m): print(m, flush=True)
def snooze(a=0.4, b=0.9): time.sleep(random.uniform(a, b))
def wait_idle(page):
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except: pass
    snooze()

def run():
    email = os.getenv("WEBOOK_EMAIL", "").strip()
    password = os.getenv("WEBOOK_PASSWORD", "").strip()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width":1366,"height":768}, record_video_dir="artifacts/videos")
        page = context.new_page()

        # فتح صفحة الحجز
        page.goto("https://webook.com/ar/zones/suwaidi-park-rs25/book", wait_until="domcontentloaded")
        wait_idle(page)

        # رفض أو قبول الكوكيز
        for txt in ["رفض","رفض الكل","Decline","Reject","Accept","قبول"]:
            btn = page.locator(f"button:has-text('{txt}')").first
            if btn.count() and btn.is_visible():
                btn.click()
                log(f"✅ تم الضغط على زر {txt}")
                break
        wait_idle(page)

        # إذا ظهرت صفحة تسجيل الدخول:
        if page.locator("input[name*='email'], input[placeholder*='email']").count():
            log("📥 صفحة تسجيل الدخول مكتشفة")

            try:
                email_field = page.locator("input[name*='email'], input[placeholder*='email']").first
                pass_field = page.locator("input[type='password']").first
                email_field.fill(email)
                pass_field.fill(password)
                log("✅ تم إدخال البريد وكلمة المرور")

                snooze(1, 1.5)
                # الضغط على زر تسجيل الدخول
                for btn_text in ["تسجيل الدخول","Login","Sign in"]:
                    btn = page.locator(f"button:has-text('{btn_text}')").first
                    if btn.count():
                        btn.click()
                        log(f"🟢 تم الضغط على زر {btn_text}")
                        break

                wait_idle(page)
            except Exception as e:
                log(f"⚠️ خطأ أثناء إدخال بيانات الدخول: {e}")

        # حفظ لقطة بعد الدخول
        snooze(3, 5)
        page.screenshot(path="artifacts/final.png", full_page=True)
        log("📸 تم حفظ لقطة الشاشة")

        context.close()
        browser.close()

if __name__ == "__main__":
    run()
