# webook_bot.py
import os, re, time, sys
from typing import Optional
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL         = os.getenv("EVENT_URL", "").strip() or "https://webook.com/ar/..."
START_DATE  = os.getenv("START_DATE", "").strip()  # "2025-11-03"
END_DATE    = os.getenv("END_DATE", "").strip()    # "2025-11-06"
TIME_RANGE  = os.getenv("TIME_RANGE", "00:00 - 16:00").strip()
HEADLESS_ENV= os.getenv("HEADLESS", "1").strip().lower()
HEADLESS    = HEADLESS_ENV in ("1","true","yes","y","on")

# إعدادات عامة
MAX_OPEN_RETRIES = 3          # محاولات فتح الرابط إذا كان 404
MAX_RELOAD_404   = 5          # مرات إعادة التحميل عند اكتشاف 404 بعد الفتح
CLICK_TIMEOUT    = 6000       # ms
WAIT_TIMEOUT     = 10000      # ms

def log(msg): 
    print(msg, flush=True)

def norm_date_str(d: datetime) -> list[str]:
    # أشكال نصية محتملة لزر التاريخ في الواجهة
    day = d.day
    day_ar = f"{day:02d}".replace("0","٠").replace("1","١").replace("2","٢").replace("3","٣").replace("4","٤").replace("5","٥").replace("6","٦").replace("7","٧").replace("8","٨").replace("9","٩")
    month_ar = "نوفمبر"
    month_en = "NOV"
    return [
        f"{day:02d} {month_ar}",
        f"{day} {month_ar}",
        f"{day:02d} {month_en}",
        f"{day} {month_en}",
        f"{day_ar} {month_ar}",
    ]

def within_dates(d: datetime, start: Optional[datetime], end: Optional[datetime]) -> bool:
    if start and d < start: return False
    if end and d > end: return False
    return True

def parse_date(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None

def open_with_retries(page, url) -> bool:
    # جرّب فتح الصفحة… إذا رجعت 404، جرّب reload/re-open
    for attempt in range(1, MAX_OPEN_RETRIES+1):
        log(f"🌐 فتح الصفحة (محاولة {attempt}/{MAX_OPEN_RETRIES}): {url}")
        resp = page.goto(url, wait_until="domcontentloaded", timeout=WAIT_TIMEOUT)
        status = resp.status if resp else None
        if status != 404:
            return True
        log("⚠️ الصفحة 404 عند الفتح — سنعيد التحميل عدّة مرات …")
        for r in range(1, MAX_RELOAD_404+1):
            try:
                page.reload(wait_until="domcontentloaded", timeout=WAIT_TIMEOUT)
                # إذا تغيّر العنوان/المحتوى نحاول تقييم سريع لوجود BODY
                if page.frame_locator("body"):
                    if "404" not in (page.title() or ""):
                        log(f"✅ اختفت 404 بعد إعادة التحميل ({r}/{MAX_RELOAD_404})")
                        return True
            except PWTimeout:
                pass
            log(f"… ما زالت 404 ({r}/{MAX_RELOAD_404})")
        # تجربة فتح الرابط من جديد
    log("❌ بقيت الصفحة 404 بعد كل المحاولات.")
    return False

def click_if_appears(page, locator, name: str, timeout=CLICK_TIMEOUT) -> bool:
    try:
        locator.wait_for(state="visible", timeout=timeout)
        locator.first.click(timeout=timeout)
        log(f"✅ Clicked: {name}")
        return True
    except PWTimeout:
        log(f"⚠️ لم يظهر العنصر: {name}")
        return False
    except Exception as e:
        log(f"⚠️ تعذر الضغط على {name}: {e}")
        return False

def accept_cookies_if_any(page):
    # أزرار قبول متعددة الاحتمالات
    buttons = [
        page.get_by_role("button", name=re.compile(r"قبول|أوافق|حسناً|أفهم|Accept|Agree", re.I)),
        page.locator("button:has-text('قبول')"),
        page.locator("text=قبول"),
    ]
    for b in buttons:
        if click_if_appears(page, b, "زر الكوكيز", timeout=3000):
            return

def pick_time_range(page, time_range: str) -> bool:
    # جرّب إيجاد نص الفترة كما هو، أو أجزاءه
    candidates = [
        page.get_by_text(time_range, exact=True),
        page.locator(f"text={time_range}"),
        page.locator("button, div, span").filter(has_text=re.compile(r"00:00|16:00|الوقت", re.I)),
    ]
    for idx, c in enumerate(candidates, 1):
        if click_if_appears(page, c, f"الفترة الزمنية (محاولة {idx})"):
            return True
    log("ℹ️ لم يتم العثور على عنصر الفترة الزمنية — سنتابع للمحاولة على التواريخ مباشرة")
    return False

def click_day_variants(page, date_texts: list[str]) -> bool:
    for t in date_texts:
        locs = [
            page.get_by_text(t, exact=True),
            page.locator(f"text={t}"),
            page.locator("button, div, span").filter(has_text=re.compile(rf"^{re.escape(t)}$", re.I)),
        ]
        for loc in locs:
            if click_if_appears(page, loc, f"اليوم: {t}"):
                return True
    return False

def main():
    start = parse_date(START_DATE)
    end   = parse_date(END_DATE)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=["--no-sandbox","--disable-dev-shm-usage"])
        context = browser.new_context(
            record_video_dir="videos",
            record_video_size={"width": 720, "height": 1280},
            locale="ar-SA",
            timezone_id="Asia/Riyadh",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121 Safari/537.36"
        )
        page = context.new_page()

        try:
            if not open_with_retries(page, URL):
                page.screenshot(path="final.png", full_page=True)
                log("📸 تم حفظ لقطة الشاشة في final.png")
                return

            accept_cookies_if_any(page)
            pick_time_range(page, TIME_RANGE)

            # جرّب الأيام ضمن النطاق
            today = datetime.now()
            tried_any = False
            for delta in range(0, 10):  # حدّ أقصى 10 أيام للأمام — عدّل إذا تحتاج
                d = datetime(today.year, today.month, today.day)  # اليوم
                d = d.replace(day=d.day)  # تثبيت اليوم
                target = today.replace(day=today.day) + (d - d)  # template
                target = today.replace(day=today.day + delta)
                if not within_dates(target, start, end):
                    continue
                tried_any = True
                label_variants = norm_date_str(target)
                log(f"--- تجربة الحجز لـ {target.strftime('%d-%m-%Y')} ---")
                if not click_day_variants(page, label_variants):
                    log("⚠️ لم يُعثر على اليوم بالنصوص المحتملة، ننتقل لليوم التالي.")
                    continue

                # TODO: هنا ضع منطق إكمال الحجز إذا كان عندك خطوات إضافية
                # مثال: الضغط على “استمرار/التالي/أضف للسلة” إلخ.
                # نكتفي الآن بتأكيد الضغط والتصوير:
                page.wait_for_timeout(800)  # نصف ثانية تقريبًا
                page.screenshot(path=f"snap_{target.strftime('%Y%m%d')}.png", full_page=True)
                log(f"📸 تم حفظ snapshot لليوم {target.strftime('%Y-%m-%d')}")
                # إذا نجح الضغط ووصلت لزر “التالي”، أكمل هنا…

            if not tried_any:
                log("ℹ️ لم نجد أيامًا ضمن النطاق المطلوب؛ راجع START_DATE/END_DATE.")
            page.screenshot(path="final.png", full_page=True)
            log("📸 تم حفظ لقطة نهائية final.png")

        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    sys.exit(main() or 0)
