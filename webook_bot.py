# webook_bot.py — يفتح WeBook، يبحث "حديقة السويدي"، يرفض الكوكيز، يدخل صفحة الفعالية،
# يضغط "Book tickets/Booking now/احجز الآن"، ثم يحاول إكمال الحجز (وقت + 5 تذاكر + الشروط).

import os, re, random, time
from datetime import datetime, timedelta, date
from playwright.sync_api import sync_playwright

TIMEOUT = 60000

def log(m): print(m, flush=True)
def nap(a=0.35,b=0.95): time.sleep(random.uniform(a,b))

# ============== تواريخ (لو أردت الحجز لأيام محددة) ==============
START_DATE = os.getenv("START_DATE", "").strip()
END_DATE   = os.getenv("END_DATE", "").strip()
SEARCH_QUERY = os.getenv("SEARCH_QUERY", "حديقة السويدي").strip()
WEBOOK_EMAIL = os.getenv("WEBOOK_EMAIL","").strip()
WEBOOK_PASSWORD = os.getenv("WEBOOK_PASSWORD","").strip()

AR_DIGITS = str.maketrans("0123456789","٠١٢٣٤٥٦٧٨٩")
MONTHS_EN_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
MONTHS_EN_LONG  = ["January","February","March","April","May","June","July","August","September","October","November","December"]
AR_MONTH = {1:"يناير",2:"فبراير",3:"مارس",4:"أبريل",5:"مايو",6:"يونيو",7:"يوليو",8:"أغسطس",9:"سبتمبر",10:"أكتوبر",11:"نوفمبر",12:"ديسمبر"}

def parse_iso(s):
    try: return datetime.strptime(s, "%Y-%m-%d").date()
    except: return None

def date_variants(d: date):
    day2=f"{d.day:02d}"; day1=str(d.day)
    day_ar2=day2.translate(AR_DIGITS); day_ar1=day1.translate(AR_DIGITS)
    en_s=MONTHS_EN_SHORT[d.month-1]; en_l=MONTHS_EN_LONG[d.month-1]; ar_l=AR_MONTH[d.month]
    iso=d.strftime("%Y-%m-%d")
    return list({iso, f"{day2} {en_s}", f"{day1} {en_s}", f"{day2} {en_l}", f"{day1} {en_l}",
                 f"{day2} {ar_l}", f"{day1} {ar_l}", f"{day_ar2} {ar_l}", f"{day_ar1} {ar_l}",
                 day2, day1})

# ============== الكوكيز ==============
def handle_cookies(page):
    # جرّب الرفض أولاً
    reject = [
        "button:has-text('رفض')","button:has-text('رفض الكل')","button:has-text('Reject')",
        "button:has-text('Reject All')","[aria-label*='Reject']","button:has-text('Decline')",
    ]
    for sel in reject:
        try:
            b = page.locator(sel).first
            if b.count() and b.is_visible():
                b.click(timeout=2000); nap(); log("✅ تم رفض الكوكيز"); return
        except: pass
    # إن لم نجد الرفض، اقبل
    accept = [
        "button:has-text('قبول')","button:has-text('أوافق')","button:has-text('Accept')",
        "button:has-text('Agree')","[aria-label*='Accept']",
    ]
    for sel in accept:
        try:
            b = page.locator(sel).first
            if b.count() and b.is_visible():
                b.click(timeout=2000); nap(); log("ℹ️ قبلت الكوكيز (للسماح بالتفاعل)"); return
        except: pass
    log("ℹ️ لا توجد نافذة كوكيز أو لم تظهر أزرارها")

# ============== بحث الفعالية من الرئيسية ==============
def search_event_from_home(context, page, query="حديقة السويدي"):
    log("🏠 فتح الصفحة الرئيسية...")
    page.goto("https://webook.com/", wait_until="domcontentloaded", timeout=TIMEOUT)
    nap(0.9,1.6)
    handle_cookies(page); nap(0.5,1.0)

    # افتح أيقونة البحث إن لزم
    for sel in ["button[aria-label*='بحث']","button[aria-label*='search']","button:has(svg)","button:has-text('بحث')","[data-testid*='search']"]:
        try:
            ic = page.locator(sel).first
            if ic.count() and ic.is_visible():
                ic.click(timeout=1500); nap(0.2,0.5); break
        except: pass

    # حقل البحث
    search = None
    for sel in ["input[type='search']","input[placeholder*='بحث']","input[placeholder*='Search']",
                "input[name='q']","input[aria-label*='بحث']","input[aria-label*='search']"]:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible(): search = loc; break
    if not search:
        log("❌ لم أجد مربع البحث"); return None

    search.click(); nap(0.2,0.5)
    search.fill("")
    search.type(query, delay=random.randint(20,60))
    page.keyboard.press("Enter"); nap(1.0,2.0)

    # التقط نتيجة فيها “حديقة” أو “suwaidi-park”
    target = None
    for loc in [page.get_by_role("link", name=re.compile(r"حديقة|Suwaidi", re.I)),
                page.locator("a[href*='suwaidi-park']"),
                page.locator("a:has-text('حديقة')")]:
        if loc.count(): target = loc.first; break
    if not target:
        any_res = page.locator("a, [role=link], article, div.card").filter(has_text=re.compile(r"حديقة|Suwaidi", re.I)).first
        if any_res.count(): target = any_res
    if not target:
        log("❌ لم أجد نتيجة مناسبة"); return None

    # انقر وتعامل مع تبويب جديد أو نفس التبويب
    active_page = page
    for attempt in range(1,4):
        try:
            with context.expect_page() as pp:
                target.click(timeout=3000)
            newp = pp.value
            newp.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
            active_page = newp; log("🆕 فُتح تبويب جديد.")
        except Exception:
            try:
                active_page.wait_for_url(re.compile(r"/zones/.+"), timeout=TIMEOUT)
                log("↪️ النقل داخل نفس التبويب (SPA).")
            except Exception:
                try: target.scroll_into_view_if_needed(timeout=1500)
                except: pass
                nap(0.3,0.7); continue
        break

    log(f"📍 الآن في: {active_page.url}")
    return active_page

# ============== الضغط على Book tickets / Booking now / احجز الآن ==============
def click_book_cta(page):
    """
    يحاول ضغط زر الحجز أياً كان نصه، أو يضيف /book للعنوان.
    يرجع True إذا وصلنا لصفحة /book.
    """
    # لو نحن بالفعل في /book نرجع نجاح
    if "/zones/" in page.url and "/book" in page.url: return True

    # أزرار وروابط شائعة
    ctas = [
        "a:has-text('Book tickets')","button:has-text('Book tickets')",
        "a:has-text('Booking now')","button:has-text('Booking now')",
        "a:has-text('Book Now')","button:has-text('Book Now')",
        "a:has-text('احجز')","button:has-text('احجز')",
        "a:has-text('احجز الآن')","button:has-text('احجز الآن')",
        "a:has-text('حجز التذاكر')","button:has-text('حجز التذاكر')",
        "a[href*='/book']","[role=link][href*='/book']",
    ]
    for sel in ctas:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                el.scroll_into_view_if_needed(timeout=2000)
                el.click(timeout=4000); nap(0.8,1.6)
                # انتظر URL
                try:
                    page.wait_for_url(re.compile(r"/zones/.+/book"), timeout=TIMEOUT)
                except: pass
                if "/zones/" in page.url and "/book" in page.url:
                    log("✅ تم الضغط على زر الحجز ووصلنا /book"); return True
        except Exception: pass

    # لو ما نجح، أضف /book يدويًا
    try:
        if "/zones/" in page.url and "/book" not in page.url:
            page.goto(page.url.rstrip("/") + "/book", wait_until="domcontentloaded", timeout=TIMEOUT)
            nap(0.6,1.2)
            if "/zones/" in page.url and "/book" in page.url:
                log("✅ أضفت /book للعنوان ووصلت لصفحة الحجز"); return True
    except Exception as e:
        log(f"⚠️ فشل الانتقال اليدوي إلى /book: {e}")

    log("⚠️ لم أتمكن من الوصول إلى صفحة /book عبر الأزرار أو الإضافة اليدوية.")
    return False

# ============== اختيار اليوم/الوقت/التذاكر ==============
def click_date(scope, d: date) -> bool:
    variants = date_variants(d); iso = d.strftime("%Y-%m-%d")
    for sel in [f'[data-date="{iso}"]', f'button[data-date="{iso}"]', f'[aria-label*="{iso}"]', f'button[aria-label*="{iso}"]']:
        loc = scope.locator(sel).first
        if loc.count() and loc.is_enabled():
            loc.click(timeout=5000); nap(0.5,1.0); return True
    for v in variants:
        for loc in [scope.get_by_role("button", name=re.compile(re.escape(v), re.I)).first,
                    scope.get_by_text(re.compile(re.escape(v), re.I)).first]:
            if loc.count() and loc.is_enabled():
                loc.click(timeout=5000); nap(0.5,1.0); return True
    return False

def pick_time_and_tickets(scope) -> bool:
    # وقت
    try:
        t = scope.locator("button, [role=button]").filter(has_text=re.compile(r"\b\d{1,2}:\d{2}\b")).first
        if t.count() and t.is_enabled():
            t.click(timeout=4000); nap(0.6,1.2)
    except: pass
    # تذاكر = 5
    try:
        qty = scope.locator("input[type='number'], input[name*='qty'], input[id*='qty']").first
        if qty.count(): qty.fill("5"); nap(0.2,0.5)
    except: pass
    for sel in ["button[aria-label*='increase']","button[aria-label*='plus']","button:has-text('+')","button[class*='plus']"]:
        b = scope.locator(sel).first
        if b.count():
            for _ in range(5): 
                b.click(); nap(0.15,0.35)
            break
    # الشروط
    try:
        chk = scope.locator("input[type='checkbox'], input[name*='terms'], input[id*='terms']").first
        if chk.count() and not chk.is_checked(): chk.check(); nap(0.2,0.5)
    except: pass
    # إكمال
    finish = scope.get_by_role("button", name=re.compile(r"إكمال|إتمام|confirm|complete|حجز|Checkout|Book", re.I)).first
    if finish.count():
        finish.click(timeout=5000); nap(1.0,2.0); return True
    return False

def find_scope(page):
    for fr in page.frames:
        try:
            u = (fr.url or "").lower()
            if any(k in u for k in ["webook","booking","calendar","zone","book","suwaidi"]):
                return fr
        except: pass
    return page

# ============== تسجيل الدخول (عند الطلب) ==============
def ensure_logged_in(page) -> bool:
    # إن ظهرت صفحة/مودال دخول
    if ("login" in page.url.lower()) or page.locator("input[type='password']").first.count():
        if not WEBOOK_EMAIL or not WEBOOK_PASSWORD:
            log("❌ مطلوب WEBOOK_EMAIL/WEBOOK_PASSWORD في Secrets."); return False
        try:
            email = page.locator("input[type='email'], input[name='email'], input[id*='email']").first
            pwd   = page.locator("input[type='password'], input[name='password'], input[id*='password']").first
            if email.count(): email.fill(WEBOOK_EMAIL); nap(0.2,0.5)
            if pwd.count():   pwd.fill(WEBOOK_PASSWORD); nap(0.3,0.7)
            btn = page.get_by_role("button", name=re.compile(r"Login|Log in|تسجيل الدخول", re.I)).first
            if btn.count(): btn.click(timeout=4000)
            else: pwd.press("Enter")
            # انتظر اختفاء النموذج
            for _ in range(12):
                if page.locator("input[type='password']").count()==0 and "login" not in page.url.lower():
                    log("🔐 تم تسجيل الدخول."); return True
                nap(0.4,0.8)
            log("ℹ️ ربما تحقق إضافي (OTP)."); return True
        except Exception as e:
            log(f"⚠️ فشل تسجيل الدخول: {e}")
            return False
    return True

# ============== التشغيل الرئيسي ==============
def run():
    sd = parse_iso(START_DATE) if START_DATE else date.today()
    ed = parse_iso(END_DATE) if END_DATE else sd
    if ed and sd and ed < sd: sd, ed = ed, sd

    os.makedirs("artifacts/videos", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        context = browser.new_context(
            viewport={"width":1366,"height":768},
            locale="ar-SA", timezone_id="Asia/Riyadh",
            record_video_dir="artifacts/videos",
            record_video_size={"width":1366,"height":768},
            extra_http_headers={"Accept-Language":"ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7","Referer":"https://webook.com/"},
        )
        page = context.new_page()
        page.on("response", lambda r: log(f"[HTTP] {r.status} {r.url}"))

        try:
            active = search_event_from_home(context, page, SEARCH_QUERY)
            if not active:
                log("❌ فشل الوصول لصفحة الفعالية عبر البحث"); page.screenshot(path="artifacts/final.png", full_page=True); return
            page = active

            # اضغط زر Book tickets / Booking now / احجز الآن
            if not click_book_cta(page):
                page.screenshot(path="artifacts/final.png", full_page=True)
                return

            # لو طُلب تسجيل الدخول هنا، نفّذ
            if not ensure_logged_in(page):
                page.screenshot(path="artifacts/final.png", full_page=True)
                return

            # بعد الدخول، تأكد أنك ما زلت في صفحة /book
            if "/zones/" in page.url and "/book" not in page.url:
                page.goto(page.url.rstrip("/") + "/book", wait_until="domcontentloaded", timeout=TIMEOUT)
                nap(0.6,1.2)

            scope = find_scope(page)

            # جرّب الحجز لمدى التواريخ لو محدد
            cur = sd or date.today()
            last = ed or cur
            while cur <= last:
                log(f"=== محاولة {cur.isoformat()} ===")
                if not click_date(scope, cur):
                    log("⚠️ لم أجد زر اليوم—ننتقل لليوم التالي.")
                    cur += timedelta(days=1); continue

                if not ensure_logged_in(page):
                    log("❌ فشل تسجيل الدخول أثناء الحجز"); break

                success = pick_time_and_tickets(scope)
                if not success:
                    log("⚠️ لم يكتمل الحجز لليوم هذا (قد لا توجد أوقات/سعة).")
                cur += timedelta(days=1)
                nap(0.8,1.6)

            page.screenshot(path="artifacts/final.png", full_page=True)
            log("📸 حفظت artifacts/final.png")

        finally:
            # احفظ الفيديو
            try:
                v = page.video
            except Exception:
                v = None
            try:
                page.close()
            except: pass
            try:
                if v: v.save_as("artifacts/videos/session.webm")
            except Exception as e:
                log(f"⚠️ video save err: {e}")
            context.close(); browser.close()

if __name__ == "__main__":
    run()
