# webook_bot.py
import os, re, sys, time
from datetime import datetime, timedelta, date
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

EVENT_URL = os.getenv("EVENT_URL", "").strip()
START_DATE = os.getenv("START_DATE", "").strip()
END_DATE   = os.getenv("END_DATE", "").strip()
TIME_RANGE = os.getenv("TIME_RANGE", "00:00 - 16:00").strip()
PROXY_URL  = os.getenv("PROXY_URL", "").strip()

if not EVENT_URL:
    print("❌ EVENT_URL مفقود."); sys.exit(2)

def parse_iso(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

try:
    start_date = parse_iso(START_DATE) if START_DATE else date.today()
    end_date   = parse_iso(END_DATE) if END_DATE else start_date
except Exception as e:
    print(f"❌ تاريخ غير صالح: {e}"); sys.exit(2)
if end_date < start_date:
    start_date, end_date = end_date, start_date

AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
MONTHS_EN_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
MONTHS_EN_LONG  = ["January","February","March","April","May","June","July","August","September","October","November","December"]
AR_MONTH = {1:"يناير",2:"فبراير",3:"مارس",4:"أبريل",5:"مايو",6:"يونيو",7:"يوليو",8:"أغسطس",9:"سبتمبر",10:"أكتوبر",11:"نوفمبر",12:"ديسمبر"}

def date_variants(d: date):
    day2=f"{d.day:02d}"; day1=str(d.day)
    day_ar2=day2.translate(AR_DIGITS); day_ar1=day1.translate(AR_DIGITS)
    en_s=MONTHS_EN_SHORT[d.month-1]; en_l=MONTHS_EN_LONG[d.month-1]; ar_l=AR_MONTH[d.month]
    iso=d.strftime("%Y-%m-%d")
    return list({
        iso,
        f"{day2} {en_s}", f"{day1} {en_s}", f"{day2} {en_s.upper()}",
        f"{day2} {en_l}", f"{day1} {en_l}",
        f"{day2} {ar_l}", f"{day1} {ar_l}", f"{day_ar2} {ar_l}", f"{day_ar1} {ar_l}",
        day2, day1, day_ar2, day_ar1
    })

def accept_cookies(scope):
    try:
        scope.get_by_role("button", name=re.compile(r"قبول|أوافق|رفض|Accept|Agree|Got it", re.I)).first.click(timeout=3000)
        print("✅ تعاملت مع الكوكيز")
    except Exception:
        pass

def open_with_fallback(page, url):
    print(f"🌐 فتح: {url}")
    resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    st = resp.status if resp else None       # ✅ status خاصية وليس دالة
    print(f"↪️ status={st} url={page.url}")
    tries = 0
    while st in (404, 500, 502, 503) and tries < 2:
        tries += 1
        alt = url.replace("/ar/", "/") if tries == 1 else url.replace("/ar/", "/en/")
        print(f"🔁 تجربة بديلة: {alt}")
        resp = page.goto(alt, wait_until="domcontentloaded", timeout=60000)
        st = resp.status if resp else None   # ✅
        print(f"↪️ status={st} url={page.url}")
    return st is not None and st < 400

def click_date(scope, d: date) -> bool:
    variants = date_variants(d)
    iso = d.strftime("%Y-%m-%d")

    # data-date أولاً
    for sel in [f'[data-date="{iso}"]', f'button[data-date="{iso}"]']:
        try:
            loc = scope.locator(sel).first
            if loc.count() and loc.is_enabled():
                loc.scroll_into_view_if_needed(); loc.click(timeout=6000)
                print(f"✅ Clicked via selector: {sel}")
                return True
        except Exception:
            pass

    # aria-label
    for v in variants:
        for sel in [f'[aria-label*="{v}"]', f'button[aria-label*="{v}"]']:
            try:
                loc = scope.locator(sel).first
                if loc.count() and loc.is_enabled():
                    loc.scroll_into_view_if_needed(); loc.click(timeout=6000)
                    print(f"✅ Clicked via selector: {sel}")
                    return True
            except Exception:
                pass

    # by role
    for v in variants:
        try:
            loc = scope.get_by_role("button", name=re.compile(re.escape(v), re.I)).first
            if loc.count() and loc.is_enabled():
                loc.scroll_into_view_if_needed(); loc.click(timeout=6000)
                print(f"✅ Clicked by role/button: {v}")
                return True
        except Exception:
            pass

    # بالنص الظاهر
    for v in variants:
        try:
            loc = scope.get_by_text(re.compile(re.escape(v), re.I)).first
            if loc.count() and loc.is_enabled():
                loc.scroll_into_view_if_needed(); loc.click(timeout=6000)
                print(f"✅ Clicked by text: {v}")
                return True
        except Exception:
            pass

    print(f"⚠️ لم يتم العثور على اليوم {d.isoformat()}")
    return False

def run():
    os.makedirs("artifacts/videos", exist_ok=True)
    with sync_playwright() as p:
        launch_kwargs = {
            "headless": True,
            "args": ["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"],
        }
        if PROXY_URL:
            launch_kwargs["proxy"]={"server": PROXY_URL}
            print("🧭 استخدام بروكسي:", PROXY_URL.split("@")[-1])

        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="ar-SA", timezone_id="Asia/Riyadh",
            record_video_dir="artifacts/videos",
            record_video_size={"width": 1366, "height": 768},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/127 Safari/537.36"),
        )
        page = context.new_page()

        # ✅ اجعل مستمع الـHTTP يستخدم status كخاصية
        def on_response(r):
            try:
                print(f"[HTTP] {r.status} {r.url}")   # ✅ بدون أقواس
            except Exception as e:
                print(f"[HTTP] log err: {e}")
        page.on("response", on_response)

        try:
            ok = open_with_fallback(page, EVENT_URL)
            accept_cookies(page)

            if not ok:
                print("❌ لم تفتح صفحة الحجز بشكل سليم.")
            else:
                print("✅ الصفحة فتحت — نبدأ اختيار الأيام")
                # اختياري: اختيار الفترة الزمنية
                try:
                    page.get_by_text(TIME_RANGE, exact=False).first.click(timeout=5000)
                    print(f"⏰ اخترت الفترة: {TIME_RANGE}")
                except Exception:
                    print("ℹ️ لم يتم العثور على عنصر الفترة — متابعة.")

                cur = start_date
                while cur <= end_date:
                    print(f"--- تجربة {cur.isoformat()} ---")
                    if not click_date(page, cur):
                        print(f"⚠️ فشل العثور على {cur} — نتابع.")
                    time.sleep(0.5)
                    cur += timedelta(days=1)

            # لقطة نهائية دائمًا
            try:
                page.screenshot(path="artifacts/final.png", full_page=True)
                print("📸 محفوظ: artifacts/final.png")
            except Exception as e:
                print(f"ℹ️ تعذّر حفظ الصورة: {e}")

        finally:
            # حفظ الفيديو باسم ثابت
            try:
                video = page.video
            except Exception:
                video = None
            try:
                page.close()
            except Exception:
                pass
            try:
                if video:
                    video.save_as("artifacts/videos/session.webm")
                    print("🎥 Saved video -> artifacts/videos/session.webm")
            except Exception as e:
                print(f"⚠️ video save err: {e}")

            context.close()
            browser.close()

if __name__ == "__main__":
    try:
        run(); sys.exit(0)
    except PWTimeout as e:
        print(f"⛔ Timeout: {e}"); sys.exit(1)
    except Exception as e:
        print(f"❌ خطأ: {e}"); sys.exit(1)
