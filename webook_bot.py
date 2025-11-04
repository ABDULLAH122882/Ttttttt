import os, time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE_URL    = os.getenv("BASE_URL", "https://webook.com/ar").strip()
EVENT_QUERY = os.getenv("EVENT_QUERY", "حديقة السويدي").strip()
START_DATE  = os.getenv("START_DATE", "").strip()
END_DATE    = os.getenv("END_DATE", "").strip()
TIME_TEXT   = os.getenv("TIME_TEXT", "16:00").strip()

EMAIL = os.getenv("WEBOOK_EMAIL", "").strip()
PASS  = os.getenv("WEBOOK_PASSWORD", "").strip()

ART_DIR = "artifacts"

def log(m): print(m, flush=True)
def wait(page, ms=900): page.wait_for_timeout(ms)
def shot(page, name): 
    try:
        page.screenshot(path=f"{ART_DIR}/{name}.png", full_page=True)
        log(f"📸 {name}.png")
    except Exception as e:
        log(f"⚠️ screenshot error: {e}")

def click_text(page, texts, timeout=4000):
    for t in texts:
        try:
            loc = page.locator(f"button:has-text('{t}'), a:has-text('{t}')").first
            if loc.count():
                loc.wait_for(state="visible", timeout=timeout)
                loc.click()
                return True
        except Exception:
            pass
    return False

def reject_cookies(page):
    cookie_texts = ["رفض", "أرفض", "رفض الكل", "Reject", "Reject all"]
    if click_text(page, cookie_texts, timeout=2500):
        log("🍪 رفض الكوكيز")
        wait(page, 600)

def ensure_login_if_prompted(page):
    try:
        email_f = page.locator("input[type='email'], input[name*=email]").first
        pass_f  = page.locator("input[type='password'], input[name*=password]").first
        if email_f.count() and pass_f.count():
            log("🔐 شاشة تسجيل الدخول ظاهرة — تعبئة الحقول")
            email_f.fill(EMAIL)
            pass_f.fill(PASS)
            wait(page, 400)
            click_text(page, ["تسجيل الدخول","الدخول","Login","Sign in"], timeout=5000)
            wait(page, 1200)
            shot(page, "after_login")
    except Exception as e:
        log(f"⚠️ login skip: {e}")

def search_event(page):
    log(f"🔎 البحث: {EVENT_QUERY}")
    # حاول فتح حقل البحث والكتابة
    opened = False
    for sel in [
        "input[placeholder*='بحث'], input[placeholder*='ابحث'], input[type=search]",
        "input[name='q']",
    ]:
        inp = page.locator(sel).first
        if inp.count():
            inp.click()
            inp.fill(EVENT_QUERY)
            inp.press("Enter")
            opened = True
            break
    if not opened:
        # fallback سريع
        page.keyboard.press("/")
        page.keyboard.type(EVENT_QUERY)
        page.keyboard.press("Enter")
    wait(page, 1200)
    shot(page, "after_search")

    # افتح كارت الفعالية
    try:
        link = page.locator(f"a:has-text('{EVENT_QUERY}')").first
        link.wait_for(state="visible", timeout=8000)
        link.click()
        wait(page, 900)
        return True
    except Exception:
        return False

def pick_date_time(page):
    # التاريخ اختياري
    try:
        if START_DATE:
            day = datetime.fromisoformat(START_DATE).day
            btn = page.locator(f"button:has-text('{day}')").first
            if btn.count():
                btn.click()
                wait(page, 600)
    except Exception: pass

    # الوقت
    try:
        if not click_text(page, [TIME_TEXT, "16:00", "00:00 - 16:00", "16"], timeout=3000):
            # اضغط أول خيار وقت واضح
            any_time = page.locator("button:has-text('16'), div:has-text('16:00')").first
            if any_time.count(): any_time.click()
        wait(page, 700)
    except Exception: pass

def run():
    os.makedirs(ART_DIR, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=ART_DIR, record_video_size={"width": 1280, "height": 720}
        )
        page = ctx.new_page()
        try:
            log(f"🌐 فتح {BASE_URL}")
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            wait(page, 900)
            reject_cookies(page)
            shot(page, "home")

            # البحث والدخول لصفحة الحدث
            if not search_event(page):
                raise RuntimeError("تعذر العثور على الفعالية")
            wait(page, 900)
            shot(page, "event_page")

            # إن طُلب دخول قبل الحجز:
            ensure_login_if_prompted(page)

            # اضغط احجز الآن / Book
            click_text(page, ["احجز الآن","احجز","Book now","Book tickets"], timeout=6000)
            wait(page, 1200)
            shot(page, "after_book_click")

            # اختيار التاريخ/الوقت (إن موجود)
            pick_date_time(page)
            shot(page, "date_time_selected")

            # وصلنا لصفحة التذاكر — **توقّف هنا** ولا تضغط +
            # هذا هو السلوك القديم المطلوب
            log("✅ الوصول لصفحة التذاكر — سيتم التوقّف قبل الضغط على +")
            shot(page, "before_plus_stop")

        except Exception as e:
            log(f"❌ Error: {e}")
            shot(page, "error")
        finally:
            try:
                ctx.close()
                browser.close()
            except Exception:
                pass

if __name__ == "__main__":
    run()
