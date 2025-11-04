import os, time
from datetime import datetime
from typing import List
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ========= إعدادات من المتغيرات =========
BASE_URL    = os.getenv("BASE_URL", "https://webook.com/ar").strip()
EVENT_QUERY = os.getenv("EVENT_QUERY", "حديقة السويدي").strip()
START_DATE  = os.getenv("START_DATE", "").strip()
END_DATE    = os.getenv("END_DATE", "").strip()
TIME_TEXT   = os.getenv("TIME_TEXT", "16:00").strip()

EMAIL = os.getenv("WEBOOK_EMAIL", "").strip()
PASS  = os.getenv("WEBOOK_PASSWORD", "").strip()

ART_DIR = "artifacts"

# ========= أدوات صغيرة =========
def log(msg: str):
    print(msg, flush=True)

def snooze(a=0.7, b=1.5):
    t = a if b <= a else (a + (b-a) * 0.6)
    time.sleep(t)

def save_shot(page, name="shot"):
    path = f"{ART_DIR}/{name}.png"
    try:
        page.screenshot(path=path, full_page=True)
        log(f"📸 saved: {path}")
    except Exception as e:
        log(f"⚠️ screenshot error: {e}")

def wait_idle(page, ms=1200):
    # انتظار بسيط بين الخطوات (تجنّب الحظر/التحميل الجزئي)
    page.wait_for_timeout(ms)

def click_first(page, selectors: List[str], timeout=4000) -> bool:
    """يحاول العثور على أول محدد موجود والضغط عليه"""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.wait_for(state="visible", timeout=timeout)
                loc.click()
                return True
        except PWTimeout:
            continue
        except Exception:
            continue
    return False

def click_text(page, texts: List[str], timeout=4000) -> bool:
    """اضغط على أول زر/رابط نصّه من القائمة"""
    for t in texts:
        try:
            loc = page.locator(f"button:has-text('{t}'), a:has-text('{t}')").first
            if loc.count() > 0:
                loc.wait_for(state="visible", timeout=timeout)
                loc.click()
                return True
        except PWTimeout:
            continue
        except Exception:
            continue
    return False

def fill_login_if_needed(page):
    # إذا ظهرت صفحة تسجيل الدخول — عبّئ الحقول واضغط "تسجيل الدخول"
    try:
        email_f = page.locator("input[name*=email], input[type='email']").first
        pass_f  = page.locator("input[name*=password], input[type='password']").first
        if email_f.count() and pass_f.count():
            log("🏷️ صفحة تسجيل الدخول مكتشفة")
            email_f.fill(EMAIL)
            pass_f.fill(PASS)
            snooze(0.5, 1.0)
            # أزرار محتملة
            if not click_text(page, ["تسجيل الدخول","Login","Sign in","الدخول"], timeout=5000):
                # زر عام داخل الفورم
                click_first(page, ["form button[type=submit]","button[type=submit]"], timeout=5000)
            wait_idle(page, 1500)
            save_shot(page, "after_login")
    except Exception as e:
        log(f"⚠️ login skip: {e}")

def reject_cookies(page):
    # أزرار محتملة لرفض الكوكيز
    cookie_texts = ["رفض", "أرفض", "رفض الكل", "رفض الكوكيز", "Reject", "Reject all"]
    if click_text(page, cookie_texts, timeout=2500):
        log("🍪 تم رفض الكوكيز")
        wait_idle(page, 800)

def handle_404_refresh(page, tries=5):
    for i in range(tries):
        if page.locator(":text('404')").first.count() == 0:
            return True
        log(f"↻ صفحة 404 — محاولة تحديث ({i+1}/{tries})")
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        wait_idle(page, 1200)
    return False

def search_event(page):
    # ابحث عن الفعالية من الصفحة الرئيسية
    log(f"🔎 البحث عن: {EVENT_QUERY}")
    # بعض المواقع لديها أيقونة/حقل بحث مختلف
    # نحاول فتح شريط البحث ثم نكتب ونضغط Enter
    variants = [
        "input[placeholder*='ابحث'], input[placeholder*='بحث'], input[type='search']",
        "input[name='q']", "input[role='searchbox']"
    ]
    opened = False
    # أحياناً زر البحث يجب الضغط عليه لإظهار الحقل
    click_text(page, ["بحث", "ابحث", "Search"], timeout=1500)

    for sel in variants:
        try:
            inp = page.locator(sel).first
            if inp.count():
                inp.click()
                inp.fill(EVENT_QUERY)
                inp.press("Enter")
                opened = True
                break
        except Exception:
            continue

    if not opened:
        # محاولة أخيرة: Ctrl+K أو '/'
        page.keyboard.press("/")
        snooze(0.4, 0.6)
        page.keyboard.type(EVENT_QUERY)
        page.keyboard.press("Enter")

    wait_idle(page, 1500)
    save_shot(page, "after_search")

    # افتح أول نتيجة مناسبة تحتوي نص الفعالية
    try:
        res = page.locator(f"a:has-text('{EVENT_QUERY}')").first
        res.wait_for(state="visible", timeout=8000)
        res.click()
        wait_idle(page, 1200)
        return True
    except Exception:
        # افتح أي بطاقة تقود للحجز
        return click_text(page, ["احجز الآن", "احجز", "Book now", "Book tickets"], timeout=6000)

def pick_date_and_time(page):
    # اختر تاريخاً بين START_DATE و END_DATE إن توفرت
    try:
        if START_DATE:
            target = datetime.fromisoformat(START_DATE).day
            btn = page.locator(f"button:has-text('{target}')").first
            if btn.count():
                btn.click()
                wait_idle(page, 800)
        save_shot(page, "date_selected")
    except Exception:
        pass

    # اختر الوقت — إن كان هناك شريط أوقات
    try:
        # حاول بالنص المحدد (مثل 16:00) ثم بدائل
        time_texts = [TIME_TEXT, "16:00", "16", "00:00 - 16:00", "16:00 - 00:00"]
        if click_text(page, time_texts, timeout=3000):
            log("⏰ تم اختيار الوقت")
        else:
            # إن لم يوجد، اضغط أول خيار وقت ظاهر
            any_time = page.locator("button:has-text('00:00'), button:has-text('16'), div:has-text('16:00')").first
            if any_time.count():
                any_time.click()
        wait_idle(page, 900)
        save_shot(page, "time_selected")
    except Exception:
        pass

def add_tickets(page, qty=5):
    # أزرار زيادة التذاكر (+)
    plus_selectors = [
        "button:has-text('+')",
        "button[aria-label*='زيد'], button[aria-label*='زيادة'], button[aria-label*='increase']",
        "button:has(svg[aria-label*='+'])",
    ]
    for _ in range(qty):
        if click_first(page, plus_selectors, timeout=2500):
            snooze(0.25, 0.5)
        else:
            break
    save_shot(page, "after_plus")

def press_continue(page):
    # اضغط التالي/استمرار/متابعة/Continue
    cont_texts = ["استمرار","التالي","متابعة","Continue","Next","أكمل الحجز"]
    if click_text(page, cont_texts, timeout=7000):
        log("➡️ تم الضغط على زر المتابعة")
        wait_idle(page, 1200)
        save_shot(page, "after_continue")
    else:
        log("⚠️ لم أجد زر المتابعة")

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
            log(f"🌐 فتح: {BASE_URL}")
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            wait_idle(page, 1000)

            # 404؟
            if not handle_404_refresh(page, tries=3):
                save_shot(page, "still_404")
                raise RuntimeError("صفحة 404 مستمرة")

            reject_cookies(page)
            save_shot(page, "home")

            # ابحث ثم افتح صفحة الفعالية
            if not search_event(page):
                raise RuntimeError("تعذر العثور على الفعالية من البحث")
            wait_idle(page, 1200)

            # إن ظهرت صفحة تسجيل الدخول هنا:
            fill_login_if_needed(page)

            # بعض المواقع تعرض زر "Book" في صفحة الحدث
            click_text(page, ["احجز الآن","احجز","Book now","Book tickets"], timeout=5000)
            wait_idle(page, 1000)

            # اختيار التاريخ/الوقت
            pick_date_and_time(page)

            # إضافة 5 تذاكر
            add_tickets(page, qty=5)

            # تابع
            press_continue(page)

            # لو أعادنا لصفحة دخول ثانية
            fill_login_if_needed(page)

            save_shot(page, "final")
            log("✅ انتهى التشغيل")

        except Exception as e:
            log(f"❌ خطأ: {e}")
            save_shot(page, "error")
        finally:
            try:
                ctx.close()
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    run()
