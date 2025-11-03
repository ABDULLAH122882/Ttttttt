# webook_bot.py
# سكربت حجز WeBook مع رصد 404 وتجديد الصفحة تلقائياً

import os, re, sys
from datetime import datetime, timedelta, date
from typing import List
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ===== قراءات من البيئة =====
EMAIL = os.getenv("WEBOOK_EMAIL", "").strip()
PASSWORD = os.getenv("WEBOOK_PASSWORD", "").strip()
EVENT_URL = os.getenv("EVENT_URL", "").strip()

START_DATE = os.getenv("START_DATE", "").strip()  # مثل: 2025-11-03
END_DATE   = os.getenv("END_DATE", "").strip()    # مثل: 2025-11-06
TIME_RANGE = os.getenv("TIME_RANGE", "00:00 - 16:00").strip()

if not EVENT_URL:
    print("❌ ERROR: EVENT_URL غير مهيأ.")
    sys.exit(2)

def parse_iso(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()

try:
    start_date = parse_iso(START_DATE) if START_DATE else date.today()
    end_date   = parse_iso(END_DATE) if END_DATE else start_date
except Exception as e:
    print(f"❌ ERROR: تاريخ غير صالح: {e}")
    sys.exit(2)

if end_date < start_date:
    start_date, end_date = end_date, start_date

# ===== مساعدات التاريخ (عربي/إنجليزي/ISO) =====
AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")

MONTHS_EN_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
MONTHS_EN_LONG  = ["January","February","March","April","May","June","July","August","September","October","November","December"]

def month_ar(month_num: int) -> str:
    mapping = {
        1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
        5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
        9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"
    }
    return mapping.get(month_num, "")

def day_variants(d: date):
    day2 = f"{d.day:02d}"           # 03
    day1 = str(d.day)               # 3
    day_ar2 = day2.translate(AR_DIGITS)  # ٠٣
    day_ar1 = day1.translate(AR_DIGITS)  # ٣
    en_s = MONTHS_EN_SHORT[d.month-1]    # Nov
    en_l = MONTHS_EN_LONG[d.month-1]     # November
    ar_l = month_ar(d.month)             # نوفمبر
    iso  = d.strftime("%Y-%m-%d")

    return list({  # unique
        f"{day2} {en_s}", f"{day1} {en_s}", f"{day2} {en_s.upper()}",
        f"{day2} {en_l}", f"{day1} {en_l}", f"{day2} {en_l.upper()}",
        f"{day2} {ar_l}", f"{day1} {ar_l}", f"{day_ar2} {ar_l}", f"{day_ar1} {ar_l}",
        day2, day1, day_ar2, day_ar1, iso
    })

# ===== رصد 404 وتجديد الصفحة =====
def looks_like_404(page) -> bool:
    """
    يتحقق إن كانت الصفحة 404 عبر العنوان أو النص الظاهر.
    """
    try:
        title = (page.title() or "").lower()
    except Exception:
        title = ""
    if "404" in title or "not found" in title:
        return True

    try:
        text_404 = page.get_by_text(re.compile(r"404|not found|غير موجود|الصفحة غير موجودة", re.I))
        if text_404.count() > 0:
            return True
    except Exception:
        pass
    return False

def refresh_until_ok(page, max_retries=5):
    """
    إذا كانت الصفحة 404، يعيد تحميل الصفحة حتى تختفي أو تنتهي المحاولات.
    """
    tries = 0
    while tries < max_retries and looks_like_404(page):
        tries += 1
        print(f"⚠️ صفحة 404 مُكتشفة — إعادة تحميل ({tries}/{max_retries}) ...")
        try:
            page.reload(timeout=30_000, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception as e:
            print(f"ℹ️ reload error: {e}")
    if looks_like_404(page):
        print("❌ بقيت صفحة 404 بعد كل المحاولات.")
        return False
    print("✅ الصفحة سليمة (ليست 404).")
    return True

# ===== اختيار التاريخ والوقت =====
def click_date(page, d: date, timeout_ms=60_000) -> bool:
    variants = day_variants(d)
    iso = d.strftime("%Y-%m-%d")

    # جرّب خصائص شائعة
    css_candidates = [
        f'[data-date="{iso}"]',
        f'button[data-date="{iso}"]',
        f'[aria-label*="{iso}"]',
        f'button[aria-label*="{iso}"]',
    ]
    for v in variants:
        css_candidates += [
            f'[aria-label*="{v}"]',
            f'button[aria-label*="{v}"]',
        ]

    for sel in css_candidates:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_enabled():
                loc.scroll_into_view_if_needed()
                loc.click(timeout=timeout_ms)
                print(f"✅ Clicked via selector: {sel}")
                return True
        except Exception:
            pass

    # by role name
    for v in variants:
        try:
            loc = page.get_by_role("button", name=re.compile(re.escape(v), re.I)).first
            if loc.count() and loc.is_enabled():
                loc.scroll_into_view_if_needed()
                loc.click(timeout=timeout_ms)
                print(f"✅ Clicked by role/button: {v}")
                return True
        except Exception:
            pass

    # by visible text
    for v in variants:
        try:
            loc = page.get_by_text(re.compile(re.escape(v), re.I)).first
            if loc.count() and loc.is_enabled():
                loc.scroll_into_view_if_needed()
                loc.click(timeout=timeout_ms)
                print(f"✅ Clicked by text: {v}")
                return True
        except Exception:
            pass

    print(f"⚠️ لم يتم العثور على اليوم {d.isoformat()}")
    return False

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(locale="ar-SA", viewport={"width":1280,"height":800})
        page = context.new_page()

        print(f"🌐 فتح الصفحة: {EVENT_URL}")
        page.goto(EVENT_URL, timeout=120_000, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=60_000)
        except PWTimeout:
            pass

        # تحقق من 404 بعد الدخول
        if not refresh_until_ok(page, max_retries=5):
            # حاول الذهاب مباشرة للرابط مرّة أخرى قبل الاستسلام
            try:
                print("↻ محاولة إعادة فتح الرابط مباشرة ...")
                page.goto(EVENT_URL, timeout=60_000, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle", timeout=60_000)
            except Exception:
                pass
            if not refresh_until_ok(page, max_retries=3):
                context.close(); browser.close()
                sys.exit(1)

        # قبول الكوكيز إن وُجد
        try:
            page.get_by_role("button", name=re.compile("قبول|أوافق|رفض الكل|رفض|Accept|Got it|Reject all", re.I)).click(timeout=3000)
            print("✅ تم التعامل مع الكوكيز")
        except Exception:
            pass

        # (اختياري) محاولة تحديد الفترة الزمنية
        if TIME_RANGE:
            try:
                page.get_by_role("button", name=re.compile(re.escape(TIME_RANGE), re.I)).first.click(timeout=5_000)
                print(f"⏰ اخترت الفترة: {TIME_RANGE}")
            except Exception:
                try:
                    page.get_by_text(re.compile(re.escape(TIME_RANGE), re.I)).first.click(timeout=5_000)
                    print(f"⏰ اخترت الفترة (بالنص): {TIME_RANGE}")
                except Exception:
                    print("ℹ️ لم يتم العثور على عنصر الفترة الزمنية — متابعة.")

        # حلقة الأيام المطلوبة
        cur = start_date
        while cur <= end_date:
            print(f"--- محاولة الحجز لـ {cur.isoformat()} ---")

            # لو ظهرت 404 لأي سبب خلال التصفح، جدّد الصفحة ثم تابع
            if looks_like_404(page):
                if not refresh_until_ok(page, max_retries=5):
                    print("❌ لا يمكن المتابعة بسبب 404.")
                    break

            ok = click_date(page, cur)
            if not ok:
                # جرب تحديث الصفحة مرة واحدة ثم إعادة المحاولة لنفس اليوم
                if refresh_until_ok(page, max_retries=2):
                    ok = click_date(page, cur)
                if not ok:
                    print(f"⚠️ فشل في النقر على {cur} — متابعة اليوم التالي.")
                    cur += timedelta(days=1)
                    continue

            # هنا أكمل خطواتك التالية (اختيار الوقت، عدد التذاكر، متابعة، ...)

            cur += timedelta(days=1)

        # حفظ صورة نهائية
        try:
            os.makedirs("artifacts", exist_ok=True)
            page.screenshot(path="artifacts/final.png", full_page=True)
            print("📸 تم حفظ لقطة الشاشة في artifacts/final.png")
        except Exception as e:
            print(f"ℹ️ لم أستطع حفظ الصورة: {e}")

        context.close()
        browser.close()

if __name__ == "__main__":
    try:
        run()
        sys.exit(0)
    except PWTimeout as e:
        print(f"❌ Timeout error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ خطأ عام: {e}")
        sys.exit(1)
