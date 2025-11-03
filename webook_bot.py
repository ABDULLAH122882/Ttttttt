# webook_bot.py
# يفتح ويبـوك من الصفحة الرئيسية -> يبحث "حديقة السويدي" -> يدخل الفعالية -> يحاول الحجز
# مع سلوك بشري + تسجيل فيديو + رفع لقطات وتشخيص

import os, re, sys, time, random
from datetime import datetime, timedelta, date
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ============== إعدادات من الـ env ==============
START_DATE = os.getenv("START_DATE", "").strip()   # مثال: 2025-11-03
END_DATE   = os.getenv("END_DATE", "").strip()     # مثال: 2025-11-06
SEARCH_QUERY = os.getenv("SEARCH_QUERY", "حديقة السويدي").strip()
PROXY_URL  = os.getenv("PROXY_URL", "").strip()    # اختياري
TIMEOUT = 60000  # ms

# ============== أدوات صغيرة ==============
def log(msg): print(msg, flush=True)
def human_sleep(a=0.4, b=1.2): time.sleep(random.uniform(a, b))

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
]
def choose_ua(): return random.choice(UA_POOL)

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || { runtime: {} };
const originalQuery = navigator.permissions && navigator.permissions.query;
if (originalQuery) {
  navigator.permissions.query = p => (p && p.name === 'notifications')
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(p);
}
"""

def human_move_and_click(page, locator, steps=14):
    try:
        box = locator.bounding_box()
    except Exception:
        box = None
    if not box:
        try:
            locator.click()
        except: pass
        return
    tx = box["x"] + box["width"] * random.uniform(0.35, 0.65)
    ty = box["y"] + box["height"] * random.uniform(0.35, 0.65)
    sx = max(0, tx - random.uniform(40, 160))
    sy = max(0, ty - random.uniform(40, 160))
    for i in range(steps):
        t = (i+1)/steps
        nx = sx + (tx - sx) * (t**0.9) + random.uniform(-2,2)
        ny = sy + (ty - sy) * (t**0.9) + random.uniform(-2,2)
        try: page.mouse.move(nx, ny)
        except: pass
        time.sleep(random.uniform(0.004, 0.02))
        sx, sy = nx, ny
    try:
        page.mouse.click(tx, ty, delay=random.uniform(20,120))
    except:
        try: locator.click()
        except: pass

# ============== تواريخ (عربي/إنجليزي) ==============
AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
MONTHS_EN_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
MONTHS_EN_LONG  = ["January","February","March","April","May","June","July","August","September","October","November","December"]
AR_MONTH = {1:"يناير",2:"فبراير",3:"مارس",4:"أبريل",5:"مايو",6:"يونيو",7:"يوليو",8:"أغسطس",9:"سبتمبر",10:"أكتوبر",11:"نوفمبر",12:"ديسمبر"}

def parse_iso(s):
    try: return datetime.strptime(s, "%Y-%m-%d").date()
    except: return None

def date_variants(d: date):
    day2 = f"{d.day:02d}"; day1 = str(d.day)
    day_ar2 = day2.translate(AR_DIGITS); day_ar1 = day1.translate(AR_DIGITS)
    en_s = MONTHS_EN_SHORT[d.month-1]; en_l = MONTHS_EN_LONG[d.month-1]; ar_l = AR_MONTH[d.month]
    iso  = d.strftime("%Y-%m-%d")
    return list({iso, f"{day2} {en_s}", f"{day1} {en_s}", f"{day2} {en_l}", f"{day1} {en_l}",
                 f"{day2} {ar_l}", f"{day1} {ar_l}", f"{day_ar2} {ar_l}", f"{day_ar1} {ar_l}",
                 day2, day1})

# ============== تعاملات صفحة ==============
def accept_cookies(scope):
    candidates = [
        scope.get_by_role("button", name=re.compile(r"قبول|أوافق|حسناً|أفهم|Accept|Agree|رفض|Reject", re.I)),
        scope.locator("button:has-text('قبول')"),
        scope.locator("button:has-text('Accept')"),
        scope.locator("text=قبول"),
    ]
    for c in candidates:
        try:
            if c.count() and c.first.is_visible():
                human_move_and_click(scope, c.first); human_sleep(0.5, 1.0)
                log("✅ تعاملت مع الكوكيز")
                return True
        except: pass
    return False

def search_event_from_home(page, query="حديقة السويدي"):
    """
    يفتح الصفحة الرئيسية، يقبل الكوكيز، يبحث عن 'حديقة السويدي'،
    ثم ينقر على نتيجة تحتوي 'حديقة' و/أو 'Suwaidi' ويدخل صفحة الحجز.
    """
    log("🏠 فتح الصفحة الرئيسية...")
    page.goto("https://webook.com/", wait_until="domcontentloaded", timeout=TIMEOUT)
    human_sleep(0.8, 1.6)
    accept_cookies(page)
    human_sleep(0.6, 1.2)

    # ابحث عن صندوق البحث (احتمالات متعددة)
    search_candidates = [
        "input[type='search']",
        "input[placeholder*='بحث']",
        "input[placeholder*='Search']",
        "input[name='q']",
        "input[aria-label*='بحث'], input[aria-label*='search']",
    ]
    search = None
    for sel in search_candidates:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            search = loc
            break
    if not search:
        # أحيانًا زر/أيقونة البحث يُظهر الحقل
        try:
            icon = page.locator("button:has(svg), button:has-text('بحث'), [role=button]:has-text('بحث')").first
            if icon.count():
                human_move_and_click(page, icon); human_sleep(0.4,0.9)
                # جرّب مرة ثانية
                for sel in search_candidates:
                    loc = page.locator(sel).first
                    if loc.count() and loc.is_visible():
                        search = loc; break
        except: pass

    if not search:
        log("❌ لم أجد مربع البحث على الصفحة الرئيسية.")
        return False

    # اكتب النص واضغط Enter
    search.click()
    search.fill(query)
    human_sleep(0.3, 0.8)
    page.keyboard.press("Enter")
    human_sleep(1.0, 2.0)

    # انتظر نتائج البحث، ثم اختر النتيجة الصحيحة
    # نحاول روابط/بطاقات فيها "حديقة" أو "Suwaidi" أو "suwaidi-park"
    result_locators = [
        page.get_by_role("link", name=re.compile(r"حديقة|Suwaidi", re.I)),
        page.locator("a[href*='suwaidi-park']"),
        page.locator("a:has-text('حديقة')"),
    ]
    target = None
    for loc in result_locators:
        if loc.count():
            target = loc.first
            break

    if not target:
        # جرب أي بطاقة/عنصر يحتوي نص البحث
        try:
            any_res = page.locator("a, [role=link], article, div.card").filter(
                has_text=re.compile(r"حديقة|Suwaidi", re.I)
            ).first
            if any_res.count(): target = any_res
        except: pass

    if not target:
        log("❌ لم أجد نتيجة مناسبة لحديقة السويدي.")
        return False

    human_move_and_click(page, target); human_sleep(0.8, 1.6)

    # إذا لم نصل لصفحة /zones/.. /book، نحاول إيجاد زر/رابط "احجز الآن" أو ما شابه
    if "/zones/" not in page.url:
        try:
            book_btn = page.get_by_role("link", name=re.compile(r"احجز|احجز الآن|Book|حجز", re.I)).first
            if book_btn.count():
                human_move_and_click(page, book_btn); human_sleep(0.8,1.4)
        except: pass

    # لو كان رابط المنطقة بدون /book، نجرّب إضافة /book
    if "/zones/" in page.url and "/book" not in page.url:
        try:
            page.goto(page.url.rstrip("/") + "/book", wait_until="domcontentloaded", timeout=TIMEOUT)
            human_sleep(0.8, 1.4)
        except: pass

    log(f"📍 وصلنا: {page.url}")
    return ("/zones/" in page.url and "/book" in page.url)

def find_booking_scope(page):
    frames = page.frames
    log(f"🔎 عدد الإطارات: {len(frames)}")
    for fr in frames:
        u = (fr.url or "").lower()
        if any(k in u for k in ["webook", "booking", "calendar", "zone", "book", "suwaidi"]):
            log("✅ اخترت iframe:", fr.url)
            return fr
    log("ℹ️ استخدام الصفحة نفسها كـ scope.")
    return page

def click_date(scope, d: date) -> bool:
    variants = date_variants(d)
    iso = d.strftime("%Y-%m-%d")
    # data-date أولاً
    for sel in [f'[data-date="{iso}"]', f'button[data-date="{iso}"]',
                f'[aria-label*="{iso}"]', f'button[aria-label*="{iso}"]']:
        try:
            loc = scope.locator(sel).first
            if loc.count() and loc.is_enabled():
                human_move_and_click(scope, loc); human_sleep(0.6, 1.2)
                log(f"✅ اخترت التاريخ via {sel}")
                return True
        except: pass
    # by role / by text
    for v in variants:
        try:
            loc = scope.get_by_role("button", name=re.compile(re.escape(v), re.I)).first
            if loc.count() and loc.is_enabled():
                human_move_and_click(scope, loc); human_sleep(0.6,1.2)
                log(f"✅ اخترت التاريخ: {v} (role)")
                return True
        except: pass
        try:
            loc = scope.get_by_text(re.compile(re.escape(v), re.I)).first
            if loc.count() and loc.is_enabled():
                human_move_and_click(scope, loc); human_sleep(0.6,1.2)
                log(f"✅ اخترت التاريخ: {v} (text)")
                return True
        except: pass
    log(f"⚠️ لم أجد اليوم {d.isoformat()}")
    return False

def pick_time_and_tickets(scope):
    # اختر أي وقت متاح (زر فيه HH:MM)
    try:
        btn = scope.locator("button, [role=button]").filter(
            has_text=re.compile(r"\b\d{1,2}:\d{2}\b")
        ).first
        if btn.count() and btn.is_enabled():
            human_move_and_click(scope, btn); human_sleep(0.6, 1.2)
            log("⏰ اخترت وقتاً متاحاً")
    except: pass

    # اجعل التذاكر = 5 (إما عبر input أو زر +)
    target = 5
    try:
        qty = scope.locator("input[type='number'], input[name*='qty'], input[id*='qty']").first
        if qty.count():
            qty.fill(str(target)); human_sleep(0.3,0.7)
            log("🎟️ ضبطت التذاكر عبر input =", target)
    except: pass

    plus_candidates = [
        "button[aria-label*='increase']", "button[aria-label*='plus']",
        "button[class*='plus']", "button[class*='increment']",
        "button:has-text('+')"
    ]
    for sel in plus_candidates:
        try:
            b = scope.locator(sel).first
            if b.count():
                # اضغط حتى 5 مرات احتياطًا
                for _ in range(target):
                    human_move_and_click(scope, b); human_sleep(0.25, 0.6)
                log("🎟️ رفعت التذاكر عبر زر +")
                break
        except: pass

    # وافق على الشروط إن وُجدت
    try:
        chk = scope.locator("input[type='checkbox'], input[name*='terms'], input[id*='terms']").first
        if chk.count():
            if not chk.is_checked():
                human_move_and_click(scope, chk); human_sleep(0.2,0.6)
                log("☑️ وافقت على الشروط")
    except: pass

    # إكمال الحجز
    try:
        finish = scope.get_by_role("button", name=re.compile(r"إكمال|إتمام|confirm|complete|حجز|Checkout|Book", re.I)).first
        if finish.count():
            human_move_and_click(scope, finish); human_sleep(1.0, 2.0)
            log("✅ ضغطت زر إكمال الحجز")
            return True
    except: pass
    return False

# ============== التشغيل الرئيسي ==============
def run():
    sd = parse_iso(START_DATE) if START_DATE else date.today()
    ed = parse_iso(END_DATE) if END_DATE else sd
    if ed < sd: sd, ed = ed, sd

    os.makedirs("artifacts/videos", exist_ok=True)

    with sync_playwright() as p:
        launch_kwargs = {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
            ],
            "slow_mo": 30,
        }
        if PROXY_URL:
            launch_kwargs["proxy"] = {"server": PROXY_URL}
            log("🧭 استخدام بروكسي:", PROXY_URL.split("@")[-1])

        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            user_agent=choose_ua(),
            viewport={"width": random.choice([1200,1280,1366,1440]), "height": random.choice([720,768,800,900])},
            locale="ar-SA", timezone_id="Asia/Riyadh",
            record_video_dir="artifacts/videos",
            record_video_size={"width": 1366, "height": 768},
            extra_http_headers={
                "Accept-Language": "ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": "https://webook.com/",
                "DNT": "1",
            },
        )
        context.add_init_script(STEALTH_JS)
        context.tracing.start(screenshots=True, snapshots=True, sources=False)

        page = context.new_page()
        page.on("response", lambda r: log(f"[HTTP] {r.status} {r.url}"))

        try:
            ok = search_event_from_home(page, SEARCH_QUERY)
            if not ok:
                log("❌ تعذر الوصول لصفحة الفعالية من البحث. حفظت لقطة.")
                page.screenshot(path="artifacts/final.png", full_page=True)
                return

            # التعامل مع iframe/الصفحة
            scope = find_booking_scope(page)
            accept_cookies(scope); human_sleep(0.5,1.0)

            # حلقة على الأيام
            cur = sd
            while cur <= ed:
                log(f"=== محاولة {cur.isoformat()} ===")
                if not click_date(scope, cur):
                    # لو فشلت، خذ لقطة ونروح لليوم التالي
                    try: scope.screenshot(path=f"artifacts/fail_{cur.strftime('%Y%m%d')}.png", full_page=True)
                    except: pass
                    cur += timedelta(days=1)
                    continue

                human_sleep(0.6,1.2)
                booked = pick_time_and_tickets(scope)
                if booked:
                    log(f"✅ تم الضغط على إكمال الحجز لليوم {cur.isoformat()}")
                    human_sleep(1.0, 2.0)
                else:
                    log(f"⚠️ لم يكتمل الحجز تلقائيًا لليوم {cur.isoformat()} — لقطة للتشخيص")
                    try: scope.screenshot(path=f"artifacts/after_{cur.strftime('%Y%m%d')}.png", full_page=True)
                    except: pass

                cur += timedelta(days=1)
                human_sleep(0.8, 1.6)

            try:
                page.screenshot(path="artifacts/final.png", full_page=True)
                log("📸 حفظت artifacts/final.png")
            except: pass

        finally:
            try:
                context.tracing.stop(path="trace.zip")
                log("🧭 Saved trace.zip")
            except Exception as e:
                log("ℹ️ trace stop err:", e)

            # احفظ الفيديو باسم ثابت
            try:
                video = page.video
            except Exception:
                video = None
            try:
                page.close()
            except: pass
            try:
                if video:
                    video.save_as("artifacts/videos/session.webm")
                    log("🎥 Saved video -> artifacts/videos/session.webm")
            except Exception as e:
                log("⚠️ video save err:", e)

            try: context.close()
            except: pass
            browser.close()

if __name__ == "__main__":
    try:
        run(); sys.exit(0)
    except PWTimeout as e:
        log(f"⛔ Timeout: {e}"); sys.exit(1)
    except Exception as e:
        log(f"❌ خطأ: {e}"); sys.exit(1)
