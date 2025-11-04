# -*- coding: utf-8 -*-
import os, re, sys, time, random
from datetime import datetime, timedelta, date
from typing import Optional, List
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ===================== بيئة قابلة للتهيئة عبر Actions =====================
HEADLESS      = os.getenv("HEADLESS", "1") != "0"   # اتركه 1 داخل Actions
TIMEOUT_MS    = int(os.getenv("TIMEOUT_MS", "120000"))   # مهلة عامة لكل انتظار
HOLD_SECONDS  = float(os.getenv("HOLD_SECONDS", "6"))    # انتظار قبل الإغلاق
MAX_RUN_MIN   = int(os.getenv("MAX_RUN_MIN", "10"))      # حد أقصى لدقائق التشغيل

# انتظار قصير متكرر للأزرار العنيدة:
PER_TRY_MS    = int(os.getenv("PER_TRY_MS", "20000"))    # 20 ثانية لكل محاولة
TRY_COUNT     = int(os.getenv("TRY_COUNT", "6"))         # 6 محاولات

# أسرار الدخول (من Secrets)
EMAIL         = os.getenv("WEBOOK_EMAIL", "").strip()
PASSWORD      = os.getenv("WEBOOK_PASSWORD", "").strip()

# نطاق الحجز والتاريخ/الوقت
SEARCH_QUERY  = os.getenv("SEARCH_QUERY", "حديقة السويدي").strip()
START_DATE    = os.getenv("START_DATE", "").strip()  # YYYY-MM-DD (اختياري)
END_DATE      = os.getenv("END_DATE", "").strip()    # YYYY-MM-DD (اختياري)
WANTED_TIME   = os.getenv("TIME_RANGE", "00:00 - 16:00").strip()

# مسارات
HOME_URL      = "https://webook.com/ar"
ART_DIR       = "artifacts"
VIDEO_DIR     = f"{ART_DIR}/videos"
os.makedirs(ART_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

# ===================== أدوات عامة =====================
def log(msg: str): print(msg, flush=True)
def snooze(a=0.35, b=0.95): time.sleep(random.uniform(a, b))

DEADLINE = time.monotonic() + MAX_RUN_MIN * 60
def deadline_guard(page=None):
    if time.monotonic() > DEADLINE:
        try:
            if page: page.screenshot(path=f"{ART_DIR}/timeout.png", full_page=True)
        except: pass
        log("⏱️ انتهت مهلة التشغيل — إيقاف آمن.")
        sys.exit(0)

def wait_idle(page, extra_sleep=(0.4, 1.0)):
    try: page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_MS)
    except: pass
    try: page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
    except: pass
    snooze(*extra_sleep)

def arabic2latin(s: str) -> str:
    return s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))

# ===================== نقر/ملء مع إعادة محاولات =====================
def short_wait_and_click(page, selectors: List[str], tries=TRY_COUNT, per_try_ms=PER_TRY_MS, name_for_log="target"):
    for i in range(1, tries+1):
        deadline_guard(page)
        for sel in selectors:
            loc = page.locator(sel).first
            try:
                loc.wait_for(state="visible", timeout=per_try_ms)
                try: loc.scroll_into_view_if_needed(timeout=min(5000, TIMEOUT_MS))
                except: pass
                loc.click(timeout=per_try_ms)
                log(f"✅ CLICK {name_for_log} via {sel} (try {i})")
                wait_idle(page)
                return True
            except Exception:
                pass
        log(f"⏳ waiting '{name_for_log}' (try {i})…")
    log(f"❌ FAILED CLICK '{name_for_log}'")
    return False

def fill_with_retry(page, selector: str, text: str, tries=TRY_COUNT, per_try_ms=PER_TRY_MS, name_for_log="input"):
    for i in range(1, tries+1):
        deadline_guard(page)
        loc = page.locator(selector).first
        try:
            loc.wait_for(state="visible", timeout=per_try_ms)
            try: loc.scroll_into_view_if_needed(timeout=min(5000, TIMEOUT_MS))
            except: pass
            loc.click(timeout=per_try_ms)
            loc.fill("")
            for ch in text: loc.type(ch, delay=random.randint(15, 45))
            log(f"⌨️ FILL {name_for_log} (try {i})")
            return True
        except Exception:
            log(f"⏳ waiting {name_for_log} (try {i})…")
            snooze(0.4, 1.0)
    log(f"❌ FAILED FILL {name_for_log}")
    return False

# ===================== 404 + كوكيز =====================
def looks_like_404(page) -> bool:
    try:
        t = (page.title() or "").lower()
        if "404" in t: return True
        if page.locator("text=404").first.count() and page.locator("text=404").first.is_visible():
            return True
    except: pass
    return False

def reload_if_404(page, attempts=3):
    for i in range(attempts):
        if not looks_like_404(page): return
        log(f"⚠️ 404 detected → reload ({i+1}/{attempts})")
        page.reload(wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        wait_idle(page)

def handle_cookies(page):
    # حاول الرفض أولًا، وإلا اقبل حتى لا يحجب البانر الصفحة
    reject = [
        "button:has-text('رفض')","button:has-text('رفض الكل')",
        "button:has-text('Decline')","button:has-text('Reject')","button:has-text('Reject All')",
        "[aria-label*='Reject']",
    ]
    accept = [
        "button:has-text('قبول')","button:has-text('أوافق')",
        "button:has-text('Accept')","button:has-text('Agree')","[aria-label*='Accept']",
    ]
    if short_wait_and_click(page, reject, tries=2, per_try_ms=5000, name_for_log="cookies reject"):
        log("✅ Cookies: Rejected"); return
    if short_wait_and_click(page, accept, tries=2, per_try_ms=5000, name_for_log="cookies accept"):
        log("ℹ️ Cookies: Accepted"); return
    log("ℹ️ Cookies banner not found.")

# ===================== بحث وفتح الفعالية =====================
def search_and_open_event(context, page, query: str) -> bool:
    log("🏠 فتح الرئيسية")
    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
    reload_if_404(page); wait_idle(page); handle_cookies(page); wait_idle(page)

    # افتح البحث (أيقونة/زر)
    short_wait_and_click(page, [
        "button[aria-label*='بحث']","button[aria-label*='search']",
        "button:has(svg)","button:has-text('بحث')","[data-testid*='search']"
    ], tries=1, per_try_ms=3000, name_for_log="search icon")

    # اكتب الاستعلام
    if not fill_with_retry(page,
        "input[type='search'], input[placeholder*='بحث'], input[placeholder*='Search'], input[name='q']",
        query, name_for_log="search box"):
        log("❌ search box not found"); return False
    page.keyboard.press("Enter"); wait_idle(page, (1.0, 2.0))

    # انتظر نتائج
    try:
        page.wait_for_selector("a[href*='/zones/'], a:has-text('حديقة'), a:has-text('Suwaidi')", timeout=20000)
    except: pass

    # اختر نتيجة مناسبة (أولوية: suwaidi-park)
    targets = [
        "a[href*='suwaidi-park']",
        "a:has-text('حديقة السويدي')",
        "a:has-text('السويدي')",
        "a:has-text('Suwaidi')",
        "a[href*='/zones/']",
    ]
    target = None
    for sel in targets:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            target = loc; break
    if not target:
        log("❌ no result link opened"); return False

    # انقر والتقط تبويب جديد أو SPA
    active = page
    try:
        with context.expect_page() as popup:
            target.click(timeout=10000)
        newp = popup.value
        newp.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_MS)
        wait_idle(newp)
        active = newp
        log("🆕 تبويب فعالية جديد.")
    except Exception:
        try:
            page.wait_for_url(re.compile(r"/zones/"), timeout=TIMEOUT_MS)
            wait_idle(page); active = page
            log("↪️ انتقال داخل نفس التبويب (SPA).")
        except Exception as e:
            log(f"❌ فشل فتح صفحة الفعالية: {e}")
            return False

    # إذا لسنا في /book أضفها
    try:
        if "/zones/" in active.url and "/book" not in active.url:
            active.goto(active.url.rstrip("/") + "/book", wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            wait_idle(active)
    except Exception as e:
        log(f"⚠️ إضافة /book يدويًا فشلت: {e}")

    log(f"📍 الآن في: {active.url}")
    return "/zones/" in active.url

# ===================== اختيار الوقت =====================
def click_time_slot(page, wanted_text: str, max_tries=6) -> bool:
    log(f"⏰ اختيار وقت: {wanted_text}")
    variants = {
        wanted_text,
        arabic2latin(wanted_text),
        "16:00", "16.00", "16٫00",
        "00:00 - 16:00", "00:00–16:00", "00:00 — 16:00",
        "00:00 - 16.00", "00:00 - 16٫00",
        "٠٠:٠٠ - ١٦:٠٠", "٠٠:٠٠–١٦:٠٠",
    }
    arab = "٠١٢٣٤٥٦٧٨٩"; digit = f"[0-9{arab}]"; sep = r"[:٫\.]"
    space = r"[ \u00A0\u2009\u200A\u200F-]*"
    rx_any = re.compile(fr"{digit}{digit}{sep}{digit}{digit}")   # HH:MM بجميع الأشكال
    rx_16  = re.compile(fr"{space}(16|١٦){sep}(00|٠٠){space}")

    for i in range(1, max_tries+1):
        deadline_guard(page)
        # حاول إبراز منطقة "اختر الوقت"
        try:
            sec = page.get_by_text("اختر الوقت", exact=False).first
            if sec.count(): sec.scroll_into_view_if_needed(timeout=2000)
        except: pass

        # 1) بالنص المباشر
        for txt in variants:
            for q in [
                f"button:has-text('{txt}')", f"[role='option']:has-text('{txt}')",
                f"div:has-text('{txt}')", f"span:has-text('{txt}')", f"text={txt}"
            ]:
                loc = page.locator(q).first
                try:
                    if loc.count():
                        loc.scroll_into_view_if_needed(timeout=2000)
                        loc.wait_for(state="visible", timeout=6000)
                        try: loc.click(timeout=5000)
                        except: page.evaluate("(el)=>el.click()", loc)
                        wait_idle(page)
                        log(f"✅ اخترت الوقت عبر النص: {txt}")
                        return True
                except: pass

        # 2) Regex مرن
        cands = page.locator("button, [role='button'], [role='option'], div, span")
        try: cnt = cands.count()
        except: cnt = 0
        for k in range(min(cnt, 250)):
            try:
                el = cands.nth(k)
                txt = el.inner_text(timeout=800) or ""
                t = arabic2latin(txt)
                if rx_16.search(t) or ("16" in t and rx_any.search(t)):
                    el.scroll_into_view_if_needed(timeout=2000)
                    el.wait_for(state="visible", timeout=5000)
                    try: el.click(timeout=5000)
                    except: page.evaluate("(el)=>el.click()", el)
                    wait_idle(page)
                    log("✅ اخترت وقتًا يطابق 16:00 (Regex).")
                    return True
            except: continue

        # محاولات إضافية: Scroll ولقطة
        page.mouse.wheel(0, 600)
        page.wait_for_timeout(900)
        try: page.screenshot(path=f"{ART_DIR}/time_try_{i}.png", full_page=False)
        except: pass

    try: page.screenshot(path=f"{ART_DIR}/time_failed.png", full_page=True)
    except: pass
    log("❌ لم أجد خانة الوقت المطلوبة")
    return False

# ===================== تسجيل الدخول إن لزم =====================
def ensure_login_if_needed(page) -> bool:
    login_found = (
        page.locator("input[type='password'], input[name*='pass']").first.count() or
        "login" in page.url.lower()
    )
    if not login_found: return True

    if not EMAIL or not PASSWORD:
        log("❌ WEBOOK_EMAIL/WEBOOK_PASSWORD غير متوفرة في Secrets.")
        return False

    if not fill_with_retry(page,
        "input[type='email'], input[name='email'], input[name*='email'], input[id*='email']",
        EMAIL, name_for_log="email"):
        return False
    snooze(0.2, 0.6)

    if not fill_with_retry(page,
        "input[type='password'], input[name='password'], input[name*='pass'], input[id*='password']",
        PASSWORD, name_for_log="password"):
        return False
    snooze(0.3, 0.8)

    short_wait_and_click(page, [
        "button:has-text('تسجيل الدخول')",
        "button:has-text('Log in')",
        "button:has-text('Login')",
        "input[type='submit']"
    ], name_for_log="login button")

    # انتظر زوال نموذج الدخول
    for _ in range(15):
        if page.locator("input[type='password']").count()==0 and "login" not in page.url.lower():
            log("🔐 تم تسجيل الدخول.")
            wait_idle(page)
            return True
        snooze(0.4, 0.8)

    log("ℹ️ لا يزال نموذج الدخول ظاهرًا (قد يكون OTP).")
    return True

# ===================== كمية التذاكر + متابعة =====================
def bump_tickets(page, count=5) -> bool:
    log(f"🎟️ زيادة التذاكر: +{count}")
    plus_sels = [
        "button[aria-label*='increase']",
        "button[aria-label*='plus']",
        "button:has-text('+')",
        "button[class*='plus']",
        "[role=button]:has-text('+')",
        "[data-testid*='plus']",
    ]
    btn = None
    for sel in plus_sels:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible(): btn = loc; break
    if not btn:
        # مسح سريع عن عناصر فيها +
        loc = page.locator("button, [role='button'], span, div").filter(has_text="+").first
        if loc.count(): btn = loc
    if not btn:
        log("⚠️ لم أجد زر +"); 
        try: page.screenshot(path=f"{ART_DIR}/no_plus.png")
        except: pass
        return False

    for i in range(count):
        try:
            btn.click(timeout=5000)
            log(f"➕ plus {i+1}/{count}")
            page.wait_for_timeout(150)
        except Exception as e:
            try: page.evaluate("(el)=>el.click()", btn)
            except: pass
            page.wait_for_timeout(120)
    return True

def proceed_next(page) -> bool:
    return short_wait_and_click(page, [
        "button:has-text('متابعة')","a:has-text('متابعة')",
        "button:has-text('التالي')","a:has-text('التالي')",
        "button:has-text('Continue')","a:has-text('Continue')",
        "button:has-text('Checkout')","a:has-text('Checkout')",
        "button:has-text('Confirm')","a:has-text('Confirm')",
        "button:has-text('إتمام')","a:has-text('إتمام')",
        "button:has-text('حجز')","a:has-text('حجز')",
    ], name_for_log="Continue/Next")

# ===================== التشغيل الرئيسي =====================
def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu",
                  "--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={"width":1366,"height":768},
            locale="ar-SA", timezone_id="Asia/Riyadh",
            record_video_dir=VIDEO_DIR,
            record_video_size={"width":1366,"height":768},
            extra_http_headers={"Accept-Language":"ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7"}
        )
        context.set_default_timeout(TIMEOUT_MS)
        page = context.new_page()
        page.on("response", lambda r: log(f"[HTTP] {r.status} {r.url}"))

        try:
            # 1) بحث + فتح الفعالية (تبويب جديد أو نفس التبويب) → /book
            if not search_and_open_event(context, page, SEARCH_QUERY):
                log("⚠️ البحث فشل؛ سنحاول رابط المنطقة مباشرةً")
                page.goto("https://webook.com/ar/zones/suwaidi-park-rs25/book", wait_until="domcontentloaded", timeout=TIMEOUT_MS)
                reload_if_404(page); wait_idle(page)

            # 2) رفض كوكيز لو ظهرت متأخرة
            handle_cookies(page)

            # 3) اختيار الوقت 16:00 (محاولتان)
            if not click_time_slot(page, WANTED_TIME):
                snooze(0.8, 1.3)
                click_time_slot(page, WANTED_TIME)

            # 4) زيادة الكمية +5
            bump_tickets(page, count=5)

            # 5) متابعة/التالي
            proceed_next(page)

            # 6) تسجيل الدخول إن طُلب
            ensure_login_if_needed(page)

            # 7) لقطة نهائية
            page.screenshot(path=f"{ART_DIR}/final.png", full_page=True)
            log("📸 saved artifacts/final.png")

            # إبقاء المتصفح قليلًا قبل الإغلاق (يفيد الفيديو)
            log(f"⏳ holding {HOLD_SECONDS}s before close…")
            time.sleep(HOLD_SECONDS)

        finally:
            try:
                v = page.video
            except Exception:
                v = None
            try: page.close()
            except: pass
            try:
                if v: v.save_as(f"{VIDEO_DIR}/session.webm")
            except Exception as e:
                log(f"⚠️ video save err: {e}")
            context.close(); browser.close()
            log("✅ done.")

if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        log(f"❌ unexpected error: {e}")
        try:
            with open(os.path.join(ART_DIR, "crash.txt"), "w", encoding="utf-8") as f:
                f.write(str(e))
        except: pass
        sys.exit(1)
