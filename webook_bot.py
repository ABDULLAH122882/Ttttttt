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

def parse_iso(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()

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

def day_variants(d: date):
    day2=f"{d.day:02d}"; day1=str(d.day)
    day_ar2=day2.translate(AR_DIGITS); day_ar1=day1.translate(AR_DIGITS)
    en_s=MONTHS_EN_SHORT[d.month-1]; en_l=MONTHS_EN_LONG[d.month-1]; ar_l=AR_MONTH[d.month]
    iso=d.strftime("%Y-%m-%d")
    return list({
        f"{day2} {en_s}", f"{day1} {en_s}", f"{day2} {en_s.upper()}",
        f"{day2} {en_l}", f"{day1} {en_l}", f"{day2} {en_l.upper()}",
        f"{day2} {ar_l}", f"{day1} {ar_l}", f"{day_ar2} {ar_l}", f"{day_ar1} {ar_l}",
        day2, day1, day_ar2, day_ar1, iso
    })

def looks_like_404(page)->bool:
    try:
        t=(page.title() or "").lower()
        if "404" in t or "not found" in t: return True
    except: pass
    try:
        if page.get_by_text(re.compile(r"404|not found|غير موجود|الصفحة غير موجودة", re.I)).count()>0:
            return True
    except: pass
    return False

def open_with_fallback(page,url,tries=3,label="primary"):
    print(f"🌐 فتح ({label}): {url}")
    resp=page.goto(url, wait_until="domcontentloaded", timeout=60000)
    status=resp.status() if resp else None
    print(f"↪️ status={status} final_url={page.url}")
    n=0
    while status in (404,500,502,503) and n<tries:
        n+=1; delay=1.0*n
        print(f"⚠️ {status} — إعادة تحميل ({n}/{tries}) بعد {delay:.1f}s")
        time.sleep(delay)
        resp=page.reload(wait_until="domcontentloaded", timeout=60000)
        status=resp.status() if resp else None
        print(f"↪️ بعد إعادة التحميل: status={status} url={page.url}")
    return status

def click_date(page,d:date,timeout_ms=60000)->bool:
    variants=day_variants(d); iso=d.strftime("%Y-%m-%d")
    css_candidates=[f'[data-date="{iso}"]', f'button[data-date="{iso}"]',
                    f'[aria-label*="{iso}"]', f'button[aria-label*="{iso}"]']
    for v in variants:
        css_candidates += [f'[aria-label*="{v}"]', f'button[aria-label*="{v}"]']
    for sel in css_candidates:
        try:
            loc=page.locator(sel).first
            if loc.count() and loc.is_enabled():
                loc.scroll_into_view_if_needed(); loc.click(timeout=timeout_ms)
                print(f"✅ Clicked via selector: {sel}"); return True
        except: pass
    for v in variants:
        try:
            loc=page.get_by_role("button", name=re.compile(re.escape(v), re.I)).first
            if loc.count() and loc.is_enabled():
                loc.scroll_into_view_if_needed(); loc.click(timeout=timeout_ms)
                print(f"✅ Clicked by role/button: {v}"); return True
        except: pass
    for v in variants:
        try:
            loc=page.get_by_text(re.compile(re.escape(v), re.I)).first
            if loc.count() and loc.is_enabled():
                loc.scroll_into_view_if_needed(); loc.click(timeout=timeout_ms)
                print(f"✅ Clicked by text: {v}"); return True
        except: pass
    print(f"⚠️ لم يتم العثور على اليوم {d.isoformat()}"); return False

def run_bot():
    os.makedirs("artifacts/videos", exist_ok=True)
    with sync_playwright() as p:
        launch_kwargs = {
            "headless": True,                      # ← هنا التعديل
            "args": ["--disable-blink-features=AutomationControlled","--no-sandbox","--disable-gpu"],
        }
        if PROXY_URL:
            launch_kwargs["proxy"]={"server": PROXY_URL}
            print("🧭 استخدام بروكسي:", PROXY_URL.split("@")[-1])
        browser = p.chromium.launch(**launch_kwargs)

        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/127.0.0.0 Safari/537.36"),
            viewport={"width":1366,"height":768},
            locale="ar-SA", timezone_id="Asia/Riyadh",
            record_video_dir="artifacts/videos",
            record_video_size={"width":1366,"height":768},
        )
        context.tracing.start(screenshots=True, snapshots=True, sources=False)
        page = context.new_page()
        page.on("response", lambda r: print(f"[HTTP] {r.status()} {r.url}"))

        try:
            print("🏠 فتح الصفحة الرئيسية...")
            page.goto("https://webook.com/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(1.0)
            try:
                cookie_btn = page.locator("button:has-text('قبول'), button:has-text('Accept'), button:has-text('رفض')")
                if cookie_btn.first.is_visible():
                    cookie_btn.first.click(); print("✅ تعاملت مع الكوكيز"); time.sleep(0.6)
            except: pass

            status = open_with_fallback(page, EVENT_URL, label="primary")
            if status == 404:
                no_locale = EVENT_URL.replace("/ar/", "/")
                print("🔁 تجربة بدون /ar/:", no_locale)
                status = open_with_fallback(page, no_locale, label="no-locale")
            if status == 404:
                en = EVENT_URL.replace("/ar/", "/en/")
                print("🔁 تجربة /en/:", en)
                status = open_with_fallback(page, en, label="en")

            if status == 200:
                print("✅ الصفحة فتحت — نبدأ اختيار الأيام")
                if TIME_RANGE:
                    try:
                        page.get_by_role("button", name=re.compile(re.escape(TIME_RANGE), re.I)).first.click(timeout=5000)
                        print(f"⏰ اخترت الفترة: {TIME_RANGE}")
                    except Exception:
                        try:
                            page.get_by_text(re.compile(re.escape(TIME_RANGE), re.I)).first.click(timeout=5000)
                            print(f"⏰ اخترت الفترة (بالنص): {TIME_RANGE}")
                        except Exception:
                            print("ℹ️ لم أجد عنصر الفترة — متابعة")
                cur=start_date
                while cur<=end_date:
                    print(f"--- محاولة الحجز لـ {cur.isoformat()} ---")
                    ok=click_date(page, cur)
                    if not ok: print(f"⚠️ فشل في النقر على {cur} — متابعة اليوم التالي.")
                    cur+=timedelta(days=1)
            else:
                print("❌ بقيت 404 — راجع الفيديو و trace.zip لمعرفة السبب.")

            try:
                page.screenshot(path="artifacts/final.png", full_page=True)
                print("📸 محفوظ: artifacts/final.png")
            except Exception as e:
                print(f"ℹ️ تعذّر حفظ الصورة: {e}")
        finally:
            try:
                context.tracing.stop(path="trace.zip"); print("🧭 Saved trace.zip")
            except Exception as e:
                print(f"ℹ️ trace stop err: {e}")
            video=None
            try: video=page.video
            except: pass
            try: page.close()
            except: pass
            try:
                if video:
                    video.save_as("artifacts/videos/session.webm")
                    print("🎥 Saved video -> artifacts/videos/session.webm")
            except Exception as e:
                print(f"⚠️ video save err: {e}")
            context.close(); browser.close()

if __name__ == "__main__":
    try:
        run_bot(); sys.exit(0)
    except PWTimeout as e:
        print(f"⛔ Timeout: {e}"); sys.exit(1)
    except Exception as e:
        print(f"❌ خطأ: {e}"); sys.exit(1)
