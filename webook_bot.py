# -*- coding: utf-8 -*-
import os, re, time, random, sys
from datetime import datetime, timedelta, date
from typing import Optional
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Error as PWError

# ================= إعدادات من البيئة =================
TIMEOUT_MS     = int(os.getenv("TIMEOUT_MS", "120000"))  # مهلة عامة طويلة
HOLD_SECONDS   = float(os.getenv("HOLD_SECONDS", "6"))   # انتظار قبل الإغلاق
HEADLESS       = os.getenv("HEADLESS", "1") != "0"

EMAIL          = os.getenv("WEBOOK_EMAIL", "").strip()
PASSWORD       = os.getenv("WEBOOK_PASSWORD", "").strip()
START_DATE     = os.getenv("START_DATE", "").strip()     # اختياري YYYY-MM-DD
END_DATE       = os.getenv("END_DATE", "").strip()       # اختياري YYYY-MM-DD
SEARCH_QUERY   = os.getenv("SEARCH_QUERY", "حديقة السويدي").strip()

HOME_URL       = "https://webook.com/"
ART_DIR        = "artifacts"

# ================= أدوات مساعدة عامة =================
def log(msg: str): print(msg, flush=True)
def snooze(a=0.35, b=0.95): time.sleep(random.uniform(a, b))

def wait_idle(page, extra_sleep=(0.4, 1.0)):
    try: page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_MS)
    except: pass
    try: page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
    except: pass
    snooze(*extra_sleep)

def wait_for_visible(scope, selector: str, timeout: Optional[int] = None):
    timeout = timeout or TIMEOUT_MS
    loc = scope.locator(selector).first
    loc.wait_for(state="visible", timeout=timeout)
    return loc

def click_with_retry(scope, selector: str, retries=3, name="element"):
    last_err = None
    for i in range(1, retries+1):
        try:
            loc = wait_for_visible(scope, selector)
            try: loc.scroll_into_view_if_needed(timeout=min(5000, TIMEOUT_MS))
            except: pass
            loc.click(timeout=TIMEOUT_MS)
            log(f"🖱️ CLICK {name} (try {i})")
            wait_idle(loc.page)
            return True
        except Exception as e:
            last_err = e
            log(f"⏳ waiting {name} (try {i})… {e}")
            snooze(0.5, 1.2)
    log(f"❌ FAILED CLICK {name}: {last_err}")
    return False

def fill_with_retry(scope, selector: str, text: str, retries=3, name="input"):
    last_err = None
    for i in range(1, retries+1):
        try:
            loc = wait_for_visible(scope, selector)
            try: loc.scroll_into_view_if_needed(timeout=min(5000, TIMEOUT_MS))
            except: pass
            loc.click(timeout=TIMEOUT_MS)
            loc.fill("")
            for ch in text: loc.type(ch, delay=random.randint(15, 45))
            log(f"⌨️ FILL {name} (try {i})")
            return True
        except Exception as e:
            last_err = e
            log(f"⏳ waiting {name} (try {i})… {e}")
            snooze(0.5, 1.2)
    log(f"❌ FAILED FILL {name}: {last_err}")
    return False

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

def parse_iso(s):
    try: return datetime.strptime(s, "%Y-%m-%d").date()
    except: return None

# ================= التعامل مع الكوكيز =================
def handle_cookies(page):
    reject = [
        "button:has-text('رفض')","button:has-text('رفض الكل')",
        "button:has-text('Decline')","button:has-text('Reject')","button:has-text('Reject All')",
        "[aria-label*='Reject']",
    ]
    accept = [
        "button:has-text('قبول')","button:has-text('أوافق')",
        "button:has-text('Accept')","button:has-text('Agree')","[aria-label*='Accept']",
    ]
    for sel in reject:
        if click_with_retry(page, sel, name="Reject Cookies"): 
            log("✅ Cookies: Rejected"); return
    for sel in accept:
        if click_with_retry(page, sel, name="Accept Cookies"):
            log("ℹ️ Cookies: Accepted"); return
    log("ℹ️ Cookies banner not found.")

# ================= دخول الصفحة الرئيسية والبحث =================
def open_home(page):
    log("🏠 OPEN HOME")
    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
    reload_if_404(page)
    wait_idle(page)
    handle_cookies(page)

def search_event(page, query="حديقة السويدي"):
    log(f"🔎 SEARCH: {query}")
    # قد تكون أيقونة بحث
    for sel in [
        "button[aria-label*='بحث']","button[aria-label*='search']",
        "button:has(svg)","button:has-text('بحث')","[data-testid*='search']"
    ]:
        try:
            if page.locator(sel).first.count() and page.locator(sel).first.is_visible():
                page.locator(sel).first.click()
                wait_idle(page)
                break
        except: pass

    # حقول البحث
    inputs = [
        "input[type='search']","input[placeholder*='بحث']","input[placeholder*='Search']",
        "input[name='q']","input[aria-label*='بحث']","input[aria-label*='search']",
    ]
    for sel in inputs:
        if fill_with_retry(page, sel, query, name="search box"):
            page.keyboard.press("Enter")
            wait_idle(page, (1.0, 2.0))
            break
    else:
        log("❌ search box not found"); 
        return False

    # افتح نتيجة تحتوي السويدي/حديقة
    result_sels = [
        "a[href*='suwaidi-park']",
        "a:has-text('حديقة')",
        "a:has-text('Suwaidi')",
        "[role=link]:has-text('حديقة')",
    ]
    for sel in result_sels:
        if click_with_retry(page, sel, name="result card/link"):
            wait_idle(page)
            return True

    # بديل: أول بطاقة/رابط يحتوي كلمة
    try:
        any_res = page.locator("a, [role=link], article, div.card").filter(
            has_text=re.compile(r"حديقة|Suwaidi", re.I)
        ).first
        if any_res.count() and any_res.is_visible():
            any_res.click()
            wait_idle(page)
            return True
    except: pass

    log("❌ no result link opened")
    return False

# ================= الذهاب لصفحة الحجز =================
def open_booking(page):
    # إن وصلنا لصفحة منطقة بدون /book أضفها
    if "/zones/" in page.url and "/book" not in page.url:
        try:
            page.goto(page.url.rstrip("/") + "/book", wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            wait_idle(page)
        except: pass

    if "/zones/" in page.url and "/book" in page.url: 
        log("🎫 already at /book"); 
        return True

    # أزرار الحجز
    ctas = [
        "a:has-text('Book tickets')","button:has-text('Book tickets')",
        "a:has-text('Book now')","button:has-text('Book now')",
        "a:has-text('Booking now')","button:has-text('Booking now')",
        "a:has-text('احجز')","button:has-text('احجز')",
        "a:has-text('احجز الآن')","button:has-text('احجز الآن')",
        "a:has-text('حجز التذاكر')","button:has-text('حجز التذاكر')",
        "a[href*='/book']","[role=link][href*='/book']",
    ]
    for sel in ctas:
        if click_with_retry(page, sel, name="CTA Book"):
            try: page.wait_for_url(re.compile(r"/zones/.+/book"), timeout=TIMEOUT_MS)
            except: pass
            wait_idle(page)
            break

    # لو لا زلنا لسنا في /book أضفها يدويًا
    if "/zones/" in page.url and "/book" not in page.url:
        try:
            page.goto(page.url.rstrip("/") + "/book", wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            wait_idle(page)
        except: pass

    ok = ("/zones/" in page.url and "/book" in page.url)
    log("🎫 /book reached" if ok else "⚠️ failed to reach /book")
    return ok

# ================= تسجيل الدخول إن طُلب =================
def ensure_login_if_needed(page) -> bool:
    # هل تظهر حقول دخول؟
    has_login = (
        page.locator("input[type='password']").first.count() or
        page.locator("input[name*='password']").first.count()
    )
    if ("login" in page.url.lower()) or has_login:
        if not EMAIL or not PASSWORD:
            log("❌ WEBOOK_EMAIL/WEBOOK_PASSWORD missing."); 
            return False

        # البريد
        if not fill_with_retry(page,
            "input[type='email'], input[name='email'], input[name*='email'], input[id*='email'], input[placeholder*='البريد']",
            EMAIL, name="email"):
            return False
        snooze(0.2, 0.5)

        # كلمة المرور
        if not fill_with_retry(page,
            "input[type='password'], input[name='password'], input[name*='pass'], input[id*='password'], input[placeholder*='كلمة']",
            PASSWORD, name="password"):
            return False
        snooze(0.3, 0.7)

        # زر الدخول
        if not click_with_retry(page,
            "button:has-text('تسجيل الدخول'), button:has-text('Log in'), button:has-text('Login'), input[type='submit']",
            name="login button"):
            # جرّب Enter
            try:
                page.locator("input[type='password']").first.press("Enter")
            except: pass
        # انتظر اختفاء حقول الدخول/تغير العنوان
        for _ in range(15):
            if page.locator("input[type='password']").count()==0 and "login" not in page.url.lower():
                log("🔐 logged in.")
                wait_idle(page)
                return True
            snooze(0.4, 0.8)
        log("ℹ️ login form still visible (maybe OTP).")
        return True
    return True

# ================= اختيار وقت 16:00 =================
def choose_time_slot(page):
    log("⏰ choose time 16:00…")
    candidates = ["16:00", "16.00", "04:00 PM", "00:00 - 16:00", "00:00–16:00", "00:00 – 16:00"]
    # افتح لائحة الأوقات إن وجدت
    for opener in ["اختر الوقت","Select time","Choose time","اختَر الوقت"]:
        try:
            if page.get_by_text(opener, exact=False).first.count():
                page.get_by_text(opener, exact=False).first.click(); wait_idle(page); break
        except: pass

    # جرّب الصيغ المختلفة
    for label in candidates:
        xpath = (
            f"//button[normalize-space()='{label}' or contains(., '{label}')]"
            f"|//div[normalize-space()='{label}' or contains(., '{label}')]"
            f"|//span[normalize-space()='{label}' or contains(., '{label}')]"
            f"|//*[@role='option' and (normalize-space()='{label}' or contains(., '{label}'))]"
        )
        try:
            loc = page.locator(xpath).first
            if loc.count():
                try: loc.scroll_into_view_if_needed(timeout=4000)
                except: pass
                loc.click(timeout=TIMEOUT_MS)
                wait_idle(page)
                log(f"✅ picked time: {label}")
                return True
        except: pass

    # احتياط: أي زر فيه نقطتا الوقت
    try:
        any_slot = page.locator("button:has-text(':'), [role='option']:has-text(':')").first
        if any_slot.count():
            any_slot.click(timeout=TIMEOUT_MS); wait_idle(page)
            log("✅ picked a visible time slot (fallback).")
            return True
    except: pass

    log("⚠️ no time slot found")
    return False

# ================= زيادة التذاكر +5 =================
def bump_tickets(page, count=5):
    log(f"🎟️ increase tickets by {count} …")
    selectors = [
        "button[aria-label*='increase']",
        "button[aria-label*='plus']",
        "button:has-text('+')",
        "button[class*='plus']",
        "[role=button]:has-text('+')",
        "[data-testid*='plus']",
    ]
    plus = None
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            plus = loc; break

    if not plus:
        log("⚠️ plus button not found")
        return False

    for i in range(count):
        try:
            plus.click(timeout=TIMEOUT_MS)
            log(f"➕ plus click {i+1}/{count}")
            snooze(0.15, 0.35)
        except Exception as e:
            log(f"⚠️ plus click failed {i+1}: {e}")
    return True

# ================= متابعة/التالي =================
def proceed_next(page):
    labels = ["متابعة","التالي","استمرار","Checkout","Continue","التالي ›","Confirm","إتمام","حجز"]
    for txt in labels:
        if click_with_retry(page, f"button:has-text('{txt}'), a:has-text('{txt}')", name=f"'{txt}'"):
            return True
    log("⚠️ next/continue button not found")
    return False

# ================= التشغيل الرئيسي =================
def run():
    os.makedirs(f"{ART_DIR}/videos", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"]
        )
        context = browser.new_context(
            viewport={"width":1366,"height":768},
            locale="ar-SA",
            timezone_id="Asia/Riyadh",
            record_video_dir=f"{ART_DIR}/videos",
            record_video_size={"width":1366,"height":768},
            extra_http_headers={"Accept-Language":"ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7"}
        )
        context.set_default_timeout(TIMEOUT_MS)
        page = context.new_page()
        page.on("response", lambda r: log(f"[HTTP] {r.status} {r.url}"))

        try:
            # 1) الصفحة الرئيسية + كوكيز + بحث
            open_home(page)
            if not search_event(page, SEARCH_QUERY):
                log("⚠️ search failed, try direct zone URL")
                page.goto("https://webook.com/ar/zones/suwaidi-park-rs25", wait_until="domcontentloaded", timeout=TIMEOUT_MS)
                reload_if_404(page)
                wait_idle(page)

            # 2) الذهاب لصفحة الحجز
            if not open_booking(page):
                page.screenshot(path=f"{ART_DIR}/final.png", full_page=True)
                return

            # 3) تسجيل الدخول إن طُلب
            if not ensure_login_if_needed(page):
                page.screenshot(path=f"{ART_DIR}/final.png", full_page=True)
                return

            # 4) اختيار الوقت 16:00 (مرتين كمحاولة)
            if not choose_time_slot(page):
                snooze(0.8, 1.4)
                choose_time_slot(page)

            # 5) زيادة التذاكر +5
            bump_tickets(page, count=5)

            # 6) متابعة/التالي
            proceed_next(page)

            # لقطة نهائية
            page.screenshot(path=f"{ART_DIR}/final.png", full_page=True)
            log("📸 saved artifacts/final.png")

            # انتظر قليلًا قبل الإغلاق لرؤية النتيجة في الفيديو
            log(f"⏳ holding {HOLD_SECONDS}s before closing…")
            time.sleep(HOLD_SECONDS)

        finally:
            try:
                v = page.video
            except Exception:
                v = None
            try: page.close()
            except: pass
            try:
                if v: v.save_as(f"{ART_DIR}/videos/session.webm")
            except Exception as e:
                log(f"⚠️ video save err: {e}")
            context.close(); browser.close()
            log("✅ done.")

if __name__ == "__main__":
    run()
