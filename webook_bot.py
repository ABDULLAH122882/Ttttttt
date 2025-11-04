# -*- coding: utf-8 -*-
import os, sys, time, re, traceback
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

EMAIL = os.getenv("WEBOOK_EMAIL", "").strip()
PASSWORD = os.getenv("WEBOOK_PASSWORD", "").strip()
START_URL = "https://webook.com/ar"
EVENT_QUERY = os.getenv("EVENT_QUERY", "حديقة السويدي").strip()
TARGET_TIME = os.getenv("TARGET_TIME", "00:00 - 16:00").strip()
TICKETS_COUNT = int(os.getenv("TICKETS_COUNT", "5"))

ART_DIR = "artifacts"
VIDEO_DIR = os.path.join(ART_DIR, "video")
os.makedirs(ART_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def shot(page, label):
    path = os.path.join(ART_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{label}.png")
    try:
        page.screenshot(path=path, full_page=True)
        log(f"📸 {label}: {path}")
    except Exception as e:
        log(f"⚠️ screenshot error {label}: {e}")

def wait(page, ms=800):
    page.wait_for_timeout(ms)

def click_by_text(page, texts, timeout=7000):
    for t in texts:
        for sel in [f"button:has-text('{t}')", f"a:has-text('{t}')"]:
            loc = page.locator(sel).first
            try:
                if loc.count():
                    loc.click(timeout=timeout); return True
            except: pass
        try:
            loc = page.get_by_text(t, exact=False).first
            if loc.count():
                loc.click(timeout=timeout); return True
        except: pass
    return False

def find_search(page):
    sels = [
        "input[placeholder*='بحث']",
        "input[placeholder*='Search']",
        "input[type='search']",
        "input[name='search']",
    ]
    for s in sels:
        loc = page.locator(s).first
        if loc.count(): return loc
    # أحيانًا حقل البحث يفتح بزر
    click_by_text(page, ["بحث","Search"], timeout=2000)
    for s in sels:
        loc = page.locator(s).first
        if loc.count(): return loc
    return None

def do_login(page):
    # الذهاب لصفحة الدخول صراحة
    page.goto(f"{START_URL}/login", wait_until="domcontentloaded", timeout=120_000)
    wait(page, 800)
    email = page.locator("input[type='email'], input[name*=email], input[placeholder*='البريد']").first
    pwd   = page.locator("input[type='password'], input[name*=pass], input[placeholder*='كلمة']").first
    email.wait_for(timeout=15000); pwd.wait_for(timeout=15000)
    email.fill(EMAIL); pwd.fill(PASSWORD)
    shot(page, "login_filled")
    click_by_text(page, ["تسجيل الدخول","Login","Sign in","تسجيل الدّخول"], timeout=10000)
    # انتظار انتقال/رجوع
    for _ in range(20):
        if page.locator("input[type='password']").count()==0 and "login" not in (page.url.lower()):
            break
        wait(page, 400)
    shot(page, "after_login")
    log("✅ تم تسجيل الدخول (ما لم يطلب 2FA).")

def main():
    if not EMAIL or not PASSWORD:
        log("❌ يجب تمرير WEBOOK_EMAIL و WEBOOK_PASSWORD (من Run workflow).")
        sys.exit(1)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width":1366,"height":768}, record_video_dir=VIDEO_DIR)
        page = ctx.new_page()

        try:
            # 1) فتح الرئيسية ورفض الكوكيز
            log(f"🌐 فتح: {START_URL}")
            page.goto(START_URL, wait_until="domcontentloaded", timeout=120000)
            shot(page, "home")
            if click_by_text(page, ["رفض","رفض الكل","Decline","Reject","لا أوافق"], timeout=3000):
                log("🍪 رفض الكوكيز"); shot(page, "after_cookie")

            # 2) تسجيل الدخول أولًا
            log("🔐 تسجيل الدخول")
            do_login(page)

            # 3) البحث عن الفعالية
            log(f"🔎 البحث عن: {EVENT_QUERY}")
            page.goto(START_URL, wait_until="domcontentloaded", timeout=120000)
            sbox = find_search(page)
            if not sbox: raise RuntimeError("لم أجد حقل البحث.")
            sbox.click(); sbox.fill(EVENT_QUERY); page.keyboard.press("Enter")
            wait(page, 1500); shot(page, "after_search")

            # 4) فتح بطاقة الفعالية
            if not click_by_text(page, [EVENT_QUERY], timeout=12000):
                # بديل: أول عنصر يحوي النص
                card = page.get_by_text(EVENT_QUERY, exact=False).first
                if card.count(): card.click(timeout=10000)
                else: raise RuntimeError("تعذّر فتح بطاقة الفعالية.")
            wait(page, 1200); shot(page, "event_opened")

            # 5) الذهاب لصفحة الحجز (إن وجد زر)
            click_by_text(page, ["احجز الآن","احجز","Book tickets","Book now","احجز تذاكر"], timeout=8000)
            wait(page, 800); shot(page, "maybe_tickets")

            # 6) اختيار الوقت
            log(f"🕒 اختيار الوقت: {TARGET_TIME}")
            if not click_by_text(page, [TARGET_TIME], timeout=10000):
                try:
                    slot = page.get_by_text(TARGET_TIME, exact=False).first
                    if slot.count(): slot.click(timeout=8000)
                except: pass
            wait(page, 800); shot(page, "time_selected")

            # 7) الضغط على زر + مرات محددة
            log(f"➕ الضغط على + × {TICKETS_COUNT}")
            plus_sels = [
                "button:has-text('+')",
                "button[aria-label*='plus']",
                "button[aria-label*='زيادة']",
                "[role='button']:has-text('+')",
            ]
            added = 0
            for i in range(TICKETS_COUNT):
                clicked = False
                for sel in plus_sels:
                    loc = page.locator(sel).first
                    try:
                        if loc.count():
                            loc.click(timeout=4000); added += 1; clicked = True; break
                    except: pass
                if not clicked: break
                wait(page, 300)
            shot(page, f"after_plus_{added}")

            # 8) متابعة/التالي
            if click_by_text(page, ["استمرار","التالي","Continue","Next","متابعة","أكمل الحجز"], timeout=8000):
                log("✅ تابع الخطوة التالية"); wait(page, 800); shot(page, "after_continue")
            else:
                log("ℹ️ لم أجد زر المتابعة (قد يتطلب خطوة داخلية).")

            shot(page, "final")
            log("✅ تم التنفيذ — راجع مجلد artifacts")

        except PWTimeout as e:
            log(f"⛔ Timeout: {e}"); shot(page, "timeout")
        except Exception as e:
            log(f"❌ Error: {e}"); traceback.print_exc(); shot(page, "exception")
        finally:
            ctx.close(); browser.close()
            log("🟢 انتهى التشغيل.")

if __name__ == "__main__":
    main()
