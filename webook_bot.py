# webook_bot.py
# سكربت الحجز التلقائي يدعم التواريخ العربية والإنجليزية وصيغ ISO
import os, re, sys, time
from datetime import datetime, timedelta, date
from typing import List
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ========== إعدادات من المتغيرات ==========
EMAIL = os.getenv("WEBOOK_EMAIL", "").strip()
PASSWORD = os.getenv("WEBOOK_PASSWORD", "").strip()
EVENT_URL = os.getenv("EVENT_URL", "").strip()

START_DATE = os.getenv("START_DATE", "").strip()   # مثال: 2025-11-03
END_DATE   = os.getenv("END_DATE", "").strip()     # مثال: 2025-11-06
TIME_RANGE = os.getenv("TIME_RANGE", "00:00 - 16:00").strip()

if not EMAIL or not PASSWORD:
    print("❌ ERROR: WEBOOK_EMAIL / WEBOOK_PASSWORD غير مهيأة.")
    sys.exit(2)
if not EVENT_URL:
    print("❌ ERROR: EVENT_URL غير مهيأ.")
    sys.exit(2)

def parse_iso(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()

try:
    start_date = parse_iso(START_DATE)
    end_date   = parse_iso(END_DATE) if END_DATE else start_date
except Exception as e:
    print(f"❌ ERROR: تاريخ غير صالح: {e}")
    sys.exit(2)

if end_date < start_date:
    start_date, end_date = end_date, start_date

# ========== أسماء الأشهر ==========
AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")

MONTHS_EN_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
MONTHS_EN_LONG  = ["January","February","March","April","May","June","July","August","September","October","November","December"]
MONTHS_AR_LONG  = ["يناير","فبراير","مارس","أبريل","ابريل","مايو","يونيو","يوليو","أغسطس","اغسطس","سبتمبر","أكتوبر","اكتوبر","نوفمبر","ديسمبر"]

def month_ar(month_num: int) -> str:
    mapping = {
        1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
        5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
        9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"
    }
    return mapping.get(month_num, "")

def day_variants(d: date) -> List[str]:
    """ترجع كل الصيغ المحتملة لزر التاريخ"""
    day = f"{d.day:02d}"
    dd_ar = day.translate(AR_DIGITS)
    month_en_s = MONTHS_EN_SHORT[d.month-1]
    month_en_l = MONTHS_EN_LONG[d.month-1]
    month_ar_l = month_ar(d.month)
    iso = d.strftime("%Y-%m-%d")

    variants = [
        f"{day} {month_en_s}", f"{day} {month_en_s.upper()}",
        f"{day} {month_en_l}", f"{day} {month_en_l.upper()}",
        f"{day} {month_ar_l}", f"{dd_ar} {month_ar_l}",
        day, dd_ar, iso
    ]
    return list(set(variants))

def click_date(page, d: date, timeout_ms=60000) -> bool:
    """يحاول نقر اليوم بكل الصيغ الممكنة"""
    variants = day_variants(d)
    iso = d.strftime("%Y-%m-%d")

    selectors = []
    for v in variants:
        selectors += [
            f'[data-date="{v}"]', f'[aria-label*="{v}"]',
            f'button[aria-label*="{v}"]', f'[data-day*="{v}"]',
        ]
    selectors.append(f'[data-date="{iso}"]')

    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_enabled():
                loc.click(timeout=timeout_ms)
                print(f"✅ Clicked via selector: {sel}")
                return True
        except Exception:
            pass

    for v in variants:
        try:
            loc = page.get_by_role("button", name=re.compile(v, re.I)).first
            if loc.count() and loc.is_enabled():
                loc.click(timeout=timeout_ms)
                print(f"✅ Clicked by role/button: {v}")
                return True
        except Exception:
            pass

    for v in variants:
        try:
            loc = page.get_by_text(re.compile(v, re.I)).first
            if loc.count() and loc.is_enabled():
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
        context = browser.new_context(locale="ar-SA")
        page = context.new_page()

        print(f"🌐 فتح الصفحة: {EVENT_URL}")
        page.goto(EVENT_URL, timeout=120_000)
        page.wait_for_load_state("networkidle", timeout=120_000)

        # محاولة قبول الكوكيز إن وجدت
        try:
            page.get_by_role("button", name=re.compile("قبول|أوافق|Accept", re.I)).click(timeout=3000)
            print("✅ تم قبول الكوكيز")
        except:
            pass

        # اختيار النطاق الزمني
        if TIME_RANGE:
            try:
                page.get_by_text(TIME_RANGE, exact=False).first.click(timeout=3000)
                print(f"⏰ اخترت الفترة: {TIME_RANGE}")
            except:
                print("ℹ️ لم يتم العثور على عنصر الفترة الزمنية")

        # الحجز
        cur = start_date
        while cur <= end_date:
            print(f"--- محاولة الحجز لـ {cur.isoformat()} ---")
            if not click_date(page, cur):
                print(f"⚠️ فشل في النقر على {cur}")
            cur += timedelta(days=1)

        # التقاط صورة نهائية
        try:
            os.makedirs("artifacts", exist_ok=True)
            page.screenshot(path="artifacts/final.png", full_page=True)
            print("📸 تم حفظ لقطة الشاشة في artifacts/final.png")
        except Exception as e:
            print(f"⚠️ لم أستطع حفظ الصورة: {e}")

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
