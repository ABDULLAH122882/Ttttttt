# -*- coding: utf-8 -*-
import os, random, time, sys, re
from datetime import datetime
from typing import List
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ========= إعدادات عامّة =========
ART_DIR = "artifacts"
os.makedirs(ART_DIR, exist_ok=True)

EMAIL = os.getenv("WEBOOK_EMAIL", "").strip()
PASSWORD = os.getenv("WEBOOK_PASSWORD", "").strip()
START_DATE = os.getenv("START_DATE", "").strip()   # YYYY-MM-DD (اختياري)
END_DATE   = os.getenv("END_DATE", "").strip()     # YYYY-MM-DD (اختياري)
TIME_RANGE = os.getenv("TIME_RANGE", "00:00 - 16:00").strip()  # اختياري، نختار 16:00
HOME_URL   = "https://webook.com/ar"
SEARCH_QUERY = "حديقة السويدي"     # ما نبحث عنه
HEADLESS = True                     # اتركه True داخل GitHub Actions

# ========= أدوات مساعدة =========
def log(msg: str):
    print(msg, flush=True)

def snooze(a=0.4, b=1.2):
    time.sleep(random.uniform(a, b))

def wait_idle(page):
    # انتظار بسيط ليبدو طبيعي
    page.wait_for_timeout(500)
    snooze(0.4, 1.0)

def looks_like_404(page) -> bool:
    try:
        # عنوان فيه 404 أو وجود نص 404 في الصفحة
        t = (page.title() or "").lower()
        if "404" in t: 
            return True
        if page.locator("text=404").first.is_visible():
            return True
    except Exception:
        pass
    return False

def reload_if_404(page, attempts=3):
    for i in range(attempts):
        if not looks_like_404(page):
            return
        log(f"⚠️ صفحة 404 مكتشفة — إعادة تحميل ({i+1}/{attempts})")
        page.reload(wait_until="domcontentloaded")
        wait_idle(page)

def click_if_visible(page, locator_query: str, label_desc: str):
    loc = page.locator(locator_query)
    if loc.count() and loc.first.is_visible():
        loc.first.click()
        log(f"✅ تم الضغط على {label_desc}")
        wait_idle(page)
        return True
    return False

def human_type(el, text: str):
    # كتابة بشرية خفيفة
    for ch in text:
        el.type(ch, delay=random.randint(20, 70))
    snooze(0.2, 0.4)

# ========= الإجراءات الأساسية =========
def dismiss_cookies(page):
    # أزرار رفض/قبول شائعة
    candidates = [
        "button:has-text('رفض')",
        "button:has-text('رفض الكل')",
        "button:has-text('قبول')",
        "button:has-text('أوافق')",
        "[aria-label*='Cookies'] >> text=رفض",
    ]
    for q in candidates:
        try:
            if page.locator(q).count():
                page.locator(q).first.click()
                log("🍪 تم التعامل مع نافذة الكوكيز")
                wait_idle(page)
                return
        except Exception:
            pass

def go_home(page):
    page.goto(HOME_URL, wait_until="domcontentloaded")
    reload_if_404(page)
    wait_idle(page)
    dismiss_cookies(page)

def search_event(page, query: str):
    log("🔎 البحث عن الفعالية...")
    # حقول البحث المحتملة
    fields = page.locator("input[placeholder*='ابحث'], input[type='search'], input[role='searchbox'], input[placeholder*='Search']")
    if not fields.count():
        # بعض المواقع تظهر العدسة أولاً
        click_if_visible(page, "button:has([data-icon='search']), button:has-text('بحث')", "زر البحث")
        fields = page.locator("input[placeholder*='ابحث'], input[type='search'], input[role='searchbox'], input[placeholder*='Search']")
    if fields.count():
        fld = fields.first
        fld.click()
        fld.clear()
        human_type(fld, query)
        fld.press("Enter")
        wait_idle(page)
    else:
        log("⚠️ لم أجد مربع البحث — سأحاول مباشرة عبر روابط النتائج")

    # فتح بطاقة الفعالية
    result_texts = [
        "حديقة السويدي", "السويدي بارك", "Suwaidi Park", "Swede Park", "حديقة السويدي 2025"
    ]
    for t in result_texts:
        if click_if_visible(page, f"a:has-text('{t}'), div:has-text('{t}') >> a", f"رابط '{t}'"):
            return True
    # بديل: أول بطاقة في النتائج
    if click_if_visible(page, "a[href*='suwaidi']", "بطاقة السويدي (تخمين)"):
        return True
    log("❌ لم أتمكن من فتح صفحة الفعالية من نتائج البحث.")
    return False

def open_booking(page):
    log("🎫 فتح صفحة الحجز...")
    # أزرار الحجز المحتملة
    labels = ["احجز التذاكر", "احجز الآن", "حجز التذاكر", "Book tickets", "Book now", "Buy tickets"]
    for txt in labels:
        if click_if_visible(page, f"button:has-text('{txt}'), a:has-text('{txt}')", txt):
            return True
    log("⚠️ لم أجد زر الحجز — سأحاول الضغط على أول زر يشبه الحجز")
    return click_if_visible(page, "a[href*='book'], button[href*='book']", "زر حجز تخميني")

def pick_time_slot(page):
    preferred = ["16:00", "16.00"]
    log("⏰ محاولة اختيار وقت الحجز...")
    for t in preferred:
        if click_if_visible(page, f"button:has-text('{t}')", f"الوقت {t}"):
            return True
        # أحيانًا كـ span داخل button
        loc = page.locator(f"text='{t}'")
        if loc.count() and loc.first.is_visible():
            loc.first.click()
            log(f"✅ تم اختيار الوقت {t}")
            wait_idle(page)
            return True
    # بديل: أي خيار ضمن النطاق
    any16 = page.locator("button:has-text('16')")  # احتياط
    if any16.count():
        any16.first.click()
        log("✅ تم اختيار وقت ضمن نطاق 16")
        wait_idle(page)
        return True
    log("⚠️ لم أجد خانة الوقت 16:00")
    return False

def ensure_login_if_needed(page):
    # إذا ظهرت صفحة تسجيل الدخول، املأها
    if page.locator("input[name*='email'], input[type='email']").count() and page.locator("input[type='password'], input[name*='pass']").count():
        log("🔐 صفحة تسجيل الدخول مكتشفة")
        if not EMAIL or not PASSWORD:
            log("❌ لا توجد بيانات WEBOOK_EMAIL/WEBOOK_PASSWORD في الأسرار.")
            return False
        try:
            email_field = page.locator("input[name*='email'], input[type='email']").first
            pass_field  = page.locator("input[type='password'], input[name*='pass']").first
            email_field.click()
            human_type(email_field, EMAIL)
            snooze(0.2, 0.5)
            pass_field.click()
            human_type(pass_field, PASSWORD)
            log("✅ تم إدخال البريد وكلمة المرور")
            snooze(0.5, 1.0)

            # أزرار "تسجيل الدخول"
            for btn_txt in ["تسجيل الدخول", "Log in", "Sign in", "دخول"]:
                if click_if_visible(page, f"button:has-text('{btn_txt}'), input[type='submit'][value*='{btn_txt}']", "زر تسجيل الدخول"):
                    break

            # انتظر انتقال أو ظهور عناصر ما بعد الدخول
            page.wait_for_timeout(1500)
            wait_idle(page)
        except Exception as e:
            log(f"⚠️ خطأ أثناء إدخال بيانات الدخول: {e}")
            return False
    return True

def bump_tickets(page, count=5):
    # زر +
    plus_candidates = [
        "button:has-text('+')",
        "button[aria-label*='+']",
        "button[aria-label*='زيادة']",
        "button[aria-label*='زيد']",
        "[data-testid*='plus']",
    ]
    for q in plus_candidates:
        loc = page.locator(q)
        if loc.count() and loc.first.is_visible():
            btn = loc.first
            for i in range(count):
                btn.click()
                snooze(0.15, 0.35)
            log(f"✅ تم زيادة العداد {count} مرات")
            return True
    log("⚠️ لم أجد زر +")
    return False

def proceed_next(page):
    # متابعة / التالي / الدفع
    labels = ["متابعة", "التالي", "استمرار", "Checkout", "Continue", "الدفع"]
    for txt in labels:
        if click_if_visible(page, f"button:has-text('{txt}'), a:has-text('{txt}')", txt):
            return True
    return False

# ========= التشغيل الرئيسي =========
def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
            ],
        )
        context = browser.new_context(
            locale="ar-SA",
            timezone_id="Asia/Riyadh",
            record_video_dir=ART_DIR,
            record_video_size={"width": 1280, "height": 720},
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            log("🌐 فتح الصفحة الرئيسية")
            go_home(page)

            # إذا واجه 404 مباشرة، حاول الذهاب إلى الصفحة العربية مجددًا
            if looks_like_404(page):
                page.goto(HOME_URL, wait_until="domcontentloaded")
                reload_if_404(page)

            # بحث وفتح الفعالية
            if not search_event(page, SEARCH_QUERY):
                # محاولة أخيرة بفتح مسار الفعالية مباشرة
                page.goto("https://webook.com/ar/zones/suwaidi-park-rs25", wait_until="domcontentloaded")
                reload_if_404(page)
                wait_idle(page)

            # فتح صفحة الحجز
            if not open_booking(page):
                log("❌ لم أستطع فتح صفحة الحجز")
            else:
                wait_idle(page)

            # اختيار وقت 16:00
            pick_time_slot(page)

            # لو ظهر تسجيل الدخول — أدخله
            ensure_login_if_needed(page)

            # جرّب زيادة التذاكر 5 مرات
            bump_tickets(page, count=5)

            # تابع/التالي إن وُجد
            proceed_next(page)

            # لقطة نهائية
            page.screenshot(path=f"{ART_DIR}/final.png", full_page=True)
            log("📸 تم حفظ لقطة الشاشة في artifacts/final.png")

        finally:
            try:
                # أعطِ بعض الوقت ليُحفظ الفيديو
                page.wait_for_timeout(1200)
            except Exception:
                pass
            context.close()
            browser.close()
            log("✅ انتهى تشغيل البوت")

if __name__ == "__main__":
    run()
