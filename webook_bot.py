# -*- coding: utf-8 -*-
import os, re, random, sys, time
from datetime import datetime
from typing import List

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ===================== إعدادات عامة =====================
BASE_URL = "https://webook.com/ar"
EVENT_QUERY = "حديقة السويدي"  # ما يتم البحث عنه في مربع البحث
WANTED_TIME = os.getenv("TIME_RANGE", "00:00 - 16:00").strip()
START_DATE = os.getenv("START_DATE", "").strip()  # YYYY-MM-DD
END_DATE   = os.getenv("END_DATE", "").strip()
EMAIL      = os.getenv("WEBOOK_EMAIL", "").strip()
PASSWORD   = os.getenv("WEBOOK_PASSWORD", "").strip()
HEADLESS   = os.getenv("HEADLESS", "true").lower() != "false"

ARTIFACTS = "artifacts"
os.makedirs(ARTIFACTS, exist_ok=True)

def log(msg: str):
    print(msg, flush=True)

def snooze(a=400, b=900):
    # تأخير صغير عشوائي (ms) لتقليد المستخدم
    t = random.randint(a, b) / 1000.0
    time.sleep(t)

def wait_idle(page):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    except Exception:
        pass
    snooze(200, 450)

# ===================== أدوات نص/أرقام =====================
def arabic_to_latin_digits(s: str) -> str:
    return s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))

# ===================== أدوات عناصر =====================
def safe_click_texts(page, texts: List[str], timeout=8_000) -> bool:
    """
    اضغط أول عنصر يظهر من قائمة نصوص محتملة.
    يجرب زر/لينك/ديف، وإذا فشل Click عادي يجرب JS click.
    """
    for txt in texts:
        locs = [
            page.get_by_text(txt, exact=True),
            page.locator(f"button:has-text('{txt}')"),
            page.locator(f"a:has-text('{txt}')"),
            page.locator(f"[role='button']:has-text('{txt}')"),
            page.locator(f"div:has-text('{txt}')"),
        ]
        for loc in locs:
            try:
                if loc.count():
                    el = loc.first
                    el.scroll_into_view_if_needed(timeout=3_000)
                    el.wait_for(state="visible", timeout=timeout)
                    try:
                        el.click(timeout=timeout)
                    except Exception:
                        page.evaluate("(el)=>el.click()", el)
                    snooze()
                    return True
            except Exception:
                continue
    return False

def click_time_slot(page, wanted_text=WANTED_TIME, max_tries=6) -> bool:
    """
    يختار خانة الوقت حتى مع اختلاف صياغة النص/الأرقام.
    يلتقط لقطات debug: artifacts/time_try_X.png و time_failed.png
    """
    variants = {
        wanted_text,
        arabic_to_latin_digits(wanted_text),
        "16:00", "16.00", "16٫00",
        "00:00 - 16:00", "00:00–16:00", "00:00 — 16:00",
        "00:00 - 16.00", "00:00 - 16٫00",
        "٠٠:٠٠ - ١٦:٠٠", "٠٠:٠٠–١٦:٠٠",
    }
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    digit = f"[0-9{arabic_digits}]"
    sep = r"[:٫\.]"
    space = r"[ \u00A0\u2009\u200A\u200F-]*"
    rx_any_time = re.compile(fr"{digit}{digit}{sep}{digit}{digit}")
    rx_just_16  = re.compile(fr"{space}(16|١٦){sep}(00|٠٠){space}")

    for i in range(1, max_tries + 1):
        wait_idle(page)
        try:
            sec = page.locator("text=اختر الوقت, text=Select time").first
            if sec.count():
                sec.scroll_into_view_if_needed(timeout=3_000)
        except Exception:
            pass

        # نص مباشر
        for txt in variants:
            locs = [
                page.get_by_text(txt, exact=True),
                page.locator(f"text={txt}"),
                page.locator(f"button:has-text('{txt}')"),
                page.locator(f"div:has-text('{txt}')"),
                page.locator(f"[role='button']:has-text('{txt}')"),
            ]
            for loc in locs:
                try:
                    if loc.count():
                        el = loc.first
                        el.scroll_into_view_if_needed(timeout=2_000)
                        el.wait_for(state="visible", timeout=6_000)
                        try:
                            el.click(timeout=5_000)
                        except Exception:
                            page.evaluate("(el)=>el.click()", el)
                        snooze()
                        return True
                except Exception:
                    pass

        # Regex مرن
        cands = page.locator("button, [role='button'], div, span")
        try:
            count = cands.count()
        except Exception:
            count = 0
        for idx in range(min(count, 250)):
            try:
                el = cands.nth(idx)
                txt = el.inner_text(timeout=800) or ""
                tnorm = arabic_to_latin_digits(txt)
                if rx_just_16.search(tnorm) or ("16" in tnorm and rx_any_time.search(tnorm)):
                    el.scroll_into_view_if_needed(timeout=2_000)
                    el.wait_for(state="visible", timeout=5_000)
                    try:
                        el.click(timeout=5_000)
                    except Exception:
                        page.evaluate("(el)=>el.click()", el)
                    snooze()
                    return True
            except Exception:
                continue

        # لم ننجح — Scroll ولقطة
        page.mouse.wheel(0, 600)
        page.wait_for_timeout(1200)
        try:
            page.screenshot(path=f"{ARTIFACTS}/time_try_{i}.png", full_page=False)
        except Exception:
            pass

    try:
        page.screenshot(path=f"{ARTIFACTS}/time_failed.png", full_page=True)
    except Exception:
        pass
    return False

def reject_cookies_if_any(page):
    texts = ["رفض", "عدم الموافقة", "Decline", "Reject", "Reject all", "لا أوافق"]
    safe_click_texts(page, texts, timeout=3_000)

def handle_404(page, url):
    """
    إذا ظهرت صفحة 404 نحاول إعادة التحميل عدة مرات، ثم نفتح الصفحة الرئيسية ونرجع True لو زبط.
    """
    tries = 3
    for i in range(tries):
        if "404" in (page.title() or "") or page.get_by_text("404").count():
            log(f"⚠️ صفحة 404 مكتشفة، إعادة تحميل ({i+1}/{tries})…")
            try:
                page.reload(timeout=10_000)
                wait_idle(page)
                if not ("404" in (page.title() or "") or page.get_by_text("404").count()):
                    return True
            except Exception:
                pass
        else:
            return True
    # فتح الرئيسية كحل أخير
    try:
        page.goto(BASE_URL, timeout=15_000)
        wait_idle(page)
        return True
    except Exception:
        return False

def search_and_open_event(page, query: str) -> bool:
    """
    من الصفحة الرئيسية: اضغط على العدسة/البحث، اكتب "حديقة السويدي"، افتح أول نتيجة.
    """
    wait_idle(page)
    reject_cookies_if_any(page)

    # افتح مربع البحث
    opened = safe_click_texts(page, ["بحث", "Search", "ابحث"], timeout=4_000)
    if not opened:
        # أحيانًا الأيقونة بدون نص
        try:
            icon = page.locator("button >> svg[aria-label='Search'], button:has(svg)").first
            if icon.count():
                icon.click(timeout=2_000)
                opened = True
        except Exception:
            pass

    # اكتب الاستعلام
    try:
        search_box = page.locator("input[type='search'], input[placeholder*='بحث'], input[placeholder*='Search']").first
        if search_box.count():
            search_box.fill("")
            snooze(120, 220)
            search_box.type(query, delay=random.randint(45, 80))
            snooze()
            # Enter أو أول نتيجة
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass
            wait_idle(page)
        else:
            log("⚠️ لم أعثر على مربع البحث")
    except Exception:
        pass

    # افتح نتيجة فيها النص المطلوب
    opened = safe_click_texts(page, [query, "حديقة السويدي 2025"], timeout=6_000)
    wait_idle(page)
    return opened

def select_date(page, ymd: str) -> bool:
    """
    يضغط على زر اليوم المطلوب مثل '03 نوفمبر' أو '03 NOV'
    """
    try:
        dt = datetime.strptime(ymd, "%Y-%m-%d")
    except Exception:
        return False

    d = dt.day
    # نصوص محتملة لزر اليوم
    arabic_month = dt.strftime("%m")  # سنعتمد على النص الموجود بالشاشة (أرقام عربية/لاتينية)
    candidates = [
        f"{d:02d}",
        f"{d}",
    ]
    # ابحث عن زر اليوم داخل بطاقات الأيام
    day_cards = page.locator("button, [role='button']")
    try:
        count = day_cards.count()
    except Exception:
        count = 0

    for i in range(count):
        try:
            el = day_cards.nth(i)
            txt = el.inner_text(timeout=400) or ""
            if str(d) in arabic_to_latin_digits(txt):
                el.scroll_into_view_if_needed(timeout=2_000)
                el.click(timeout=3_000)
                wait_idle(page)
                return True
        except Exception:
            continue
    # fallback: نصوص مباشرة
    return safe_click_texts(page, [f"{d:02d}", f"{d}"], timeout=3_000)

def add_quantity(page, amount=5) -> bool:
    """
    اضغط على زر + amount مرات.
    """
    plus_candidates = [
        "button:has-text('+')",
        "button[aria-label*='+']",
        "button[aria-label*='plus']",
        "[role='button']:has-text('+')",
        "button:has(svg[aria-label*='plus'])",
    ]
    btn = None
    for sel in plus_candidates:
        loc = page.locator(sel)
        if loc.count():
            btn = loc.first
            break
    if not btn:
        # جرّب الأيقونة في بطاقة التذكرة
        loc = page.locator("button, [role='button']")
        n = min(loc.count(), 100)
        for i in range(n):
            el = loc.nth(i)
            try:
                txt = (el.inner_text(timeout=200) or "").strip()
                if txt in ["+", "﹢", "＋"]:
                    btn = el
                    break
            except Exception:
                continue
    if not btn:
        page.screenshot(path=f"{ARTIFACTS}/no_plus.png")
        return False

    for _ in range(amount):
        try:
            btn.scroll_into_view_if_needed(timeout=2_000)
            btn.click(timeout=3_000)
            snooze(120, 240)
        except Exception:
            try:
                page.evaluate("(el)=>el.click()", btn)
            except Exception:
                pass
    return True

def login_if_needed(page):
    # إذا ظهرت صفحة تسجيل الدخول
    if page.locator("input[name*=email], input[type='email']").count():
        log("🔐 صفحة تسجيل الدخول مكشوفة، سأملأ البيانات…")
        try:
            email_field = page.locator("input[name*=email], input[type='email']").first
            pass_field  = page.locator("input[name*=password], input[type='password']").first
            email_field.fill(EMAIL)
            snooze(100, 180)
            pass_field.fill(PASSWORD)
            snooze(150, 220)
            # زر الدخول
            safe_click_texts(page, ["تسجيل الدخول", "Log in", "Sign in", "Continue"])
            wait_idle(page)
        except Exception as e:
            log(f"⚠️ خطأ أثناء إدخال بيانات الدخول: {e}")

# ===================== السريان الرئيسي =====================
def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox", "--disable-dev-shm-usage",
        ])
        context = browser.new_context(
            locale="ar-SA",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            record_video_dir=ARTIFACTS,
        )
        page = context.new_page()

        # افتح الرابط (وإن ظهر 404 عالج)
        try:
            page.goto(BASE_URL, timeout=20_000)
        except Exception:
            pass
        if not handle_404(page, BASE_URL):
            log("❌ لم أستطع تجاوز 404")
            return

        reject_cookies_if_any(page)

        # ابحث وافتح الفعالية
        if not search_and_open_event(page, EVENT_QUERY):
            log("❌ فشل فتح صفحة الفعالية من البحث")
            page.screenshot(path=f"{ARTIFACTS}/open_event_failed.png", full_page=True)
            return

        wait_idle(page)
        reject_cookies_if_any(page)

        # لو ظهر زر "Book tickets" / "احجز التذاكر" اضغطه
        safe_click_texts(page, ["Book tickets", "احجز التذاكر", "Book now", "احجز الآن"], timeout=5_000)
        wait_idle(page)

        # اختر التاريخ
        target_dates = []
        if START_DATE:
            target_dates.append(START_DATE)
        if END_DATE and END_DATE != START_DATE:
            target_dates.append(END_DATE)

        # إن لم تُحدد، استخدم تاريخ اليوم
        if not target_dates:
            target_dates = [datetime.utcnow().strftime("%Y-%m-%d")]

        date_selected = False
        for ymd in target_dates:
            if select_date(page, ymd):
                log(f"📅 تم اختيار اليوم {ymd}")
                date_selected = True
                break
        if not date_selected:
            log("⚠️ لم أتمكن من اختيار اليوم — سأحاول المتابعة على اليوم الافتراضي الظاهر.")
        wait_idle(page)

        # اختر خانة الوقت 16:00 (مرن)
        if click_time_slot(page, WANTED_TIME):
            log("✅ تم اختيار خانة الوقت بنجاح")
        else:
            log("❌ لم أعثر على خانة الوقت المطلوبة")
            # لا نخرج فورًا — ربما الحجز لا يحتاج اختيار وقت

        # اضغط + خمس مرات
        if add_quantity(page, amount=5):
            log("✅ تم زيادة العدد إلى 5")
        else:
            log("⚠️ لم أجد زر + — لقطة موجودة artifacts/no_plus.png")

        # تابع
        safe_click_texts(page, ["متابعة", "Continue", "التالي", "Next"], timeout=6_000)
        wait_idle(page)

        # تسجيل الدخول إذا طُلب
        login_if_needed(page)
        wait_idle(page)

        # لقطة نهائية
        try:
            page.screenshot(path=f"{ARTIFACTS}/final.png", full_page=True)
            log("📸 تم حفظ لقطة الشاشة في artifacts/final.png")
        except Exception:
            pass

        # اغلاق أنيق
        context.close()
        browser.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ خطأ غير متوقع: {e}")
        try:
            # محاولة حفظ لقطة عند الخطأ
            with open(os.path.join(ARTIFACTS, "crash.txt"), "w", encoding="utf-8") as f:
                f.write(str(e))
        except Exception:
            pass
        sys.exit(1)
