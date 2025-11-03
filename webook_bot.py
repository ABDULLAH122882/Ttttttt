# webook_bot.py (تحديث: ضغط زر التذاكر 5 مرات بشكل مؤكد)
import os, re, time, random
from datetime import datetime, timedelta, date
from playwright.sync_api import sync_playwright

def log(m): print(m, flush=True)
def snooze(a=0.4, b=0.9): time.sleep(random.uniform(a, b))

def wait_idle(page):
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except: pass
    snooze()

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width":1366,"height":768}, record_video_dir="artifacts/videos")
        page = context.new_page()

        # الدخول للصفحة مباشرة
        page.goto("https://webook.com/ar/zones/suwaidi-park-rs25/book", wait_until="domcontentloaded")
        wait_idle(page)

        # رفض أو قبول الكوكيز
        for txt in ["رفض","رفض الكل","Decline","Reject","Reject All","Accept","قبول","أوافق"]:
            btn = page.locator(f"button:has-text('{txt}')").first
            if btn.count() and btn.is_visible():
                btn.click()
                log(f"✅ تم الضغط على زر {txt}")
                break

        wait_idle(page)
        log("📍 في صفحة الحجز")

        # البحث عن زر "+"
        selectors = [
            "button[aria-label*='increase']",
            "button[aria-label*='plus']",
            "button:has-text('+')",
            "button[class*='plus']",
            "[role=button]:has-text('+')",
            "span:has-text('+')",
            "div:has-text('+')"
        ]
        plus_btn = None
        for sel in selectors:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                plus_btn = loc
                break

        if plus_btn:
            log("✅ تم العثور على زر +")
            for i in range(5):
                try:
                    plus_btn.click()
                    log(f"➕ ضغطة رقم {i+1}")
                    snooze(0.4, 0.8)
                except Exception as e:
                    log(f"⚠️ تعذّر الضغط رقم {i+1}: {e}")
        else:
            log("❌ لم يتم العثور على زر + في الصفحة")

        # بعد الضغط على + حاول الضغط على "إكمال" أو "متابعة"
        finish_btn = page.get_by_role("button", name=re.compile(r"إكمال|متابعة|Confirm|Continue|إتمام|حجز|Checkout|Book", re.I)).first
        if finish_btn.count():
            finish_btn.click()
            log("✅ تم الضغط على زر الإكمال/المتابعة")
        else:
            log("⚠️ لم يتم العثور على زر الإكمال")

        # حفظ لقطة الشاشة
        time.sleep(5)
        page.screenshot(path="artifacts/final.png", full_page=True)
        log("📸 تم حفظ لقطة الشاشة")

        # إغلاق بعد مهلة قصيرة
        time.sleep(4)
        context.close()
        browser.close()

if __name__ == "__main__":
    run()
