# webook_bot.py — فتح الموقع > رفض الكوكيز > فتح مربع البحث > البحث عن "حديقة السويدي" > دخول الفعالية
import os, re, sys, time, random
from datetime import datetime, timedelta, date
from playwright.sync_api import sync_playwright

# ===== الإعدادات =====
SEARCH_QUERY = os.getenv("SEARCH_QUERY", "حديقة السويدي").strip()
START_DATE = os.getenv("START_DATE", "").strip()
END_DATE   = os.getenv("END_DATE", "").strip()
TIMEOUT = 60000  # ms

def log(msg): print(msg, flush=True)
def snooze(a=0.35, b=0.95): time.sleep(random.uniform(a, b))

# تواريخ (إذا احتجتها لاحقًا)
def parse_iso(s):
    try: return datetime.strptime(s, "%Y-%m-%d").date()
    except: return None

# ===== التعامل مع الكوكيز (رفض الكل) =====
def handle_cookies(page):
    """
    يحاول رفض الكوكيز صراحةً (Reject All)، مع محاولات بديلة:
    - أزرار "رفض"، "رفض الكل"، "رفض جميع" (عربي/إنجليزي)
    - إذا لم يجد، يحاول "قبول" فقط حتى لا يحجب التفاعل
    """
    selectors_reject = [
        "button:has-text('رفض')",
        "button:has-text('رفض الكل')",
        "button:has-text('رفض جميع')",
        "button:has-text('Reject')",
        "button:has-text('Reject All')",
        "button[aria-label*='Reject']",
    ]
    selectors_accept = [
        "button:has-text('قبول')",
        "button:has-text('أوافق')",
        "button:has-text('حسناً')",
        "button:has-text('Accept')",
        "button:has-text('Agree')",
        "button[aria-label*='Accept']",
    ]
    # جرّب الرفض أولاً
    for sel in selectors_reject:
        try:
            btn = page.locator(sel).first
            if btn.count() and btn.is_visible():
                btn.click(timeout=3000); snooze()
                log("✅ تم رفض الكوكيز (Reject All).")
                return True
        except: pass
    # إن لم نجد الرفض، اقبل حتى نقدر نتفاعل
    for sel in selectors_accept:
        try:
            btn = page.locator(sel).first
            if btn.count() and btn.is_visible():
                btn.click(timeout=3000); snooze()
                log("ℹ️ لم أجد رفض، قبلت الكوكيز لتسهيل التفاعل.")
                return True
        except: pass
    log("ℹ️ لم أتعامل مع الكوكيز (لم أجد نافذة/أزرار).")
    return False

# ===== فتح مربع البحث ثم البحث =====
def open_search_box(page):
    """
    بعض المواقع تخفي الحقل خلف أيقونة "بحث".
    نحاول:
    1) الضغط على أيقونة/زر البحث
    2) إيجاد input الحقل والتركيز عليه
    """
    # 1) حاول أيقونة البحث
    candidates_icon = [
        "button[aria-label*='بحث']",
        "button[aria-label*='search']",
        "button:has(svg)",
        "button:has-text('بحث')",
        "[role=button]:has-text('بحث')",
        "a[aria-label*='بحث']",
        "[data-testid*='search']",
    ]
    for sel in candidates_icon:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                el.click(timeout=3000); snooze()
                break
        except: pass

    # 2) ابحث عن حقل الإدخال
    candidates_input = [
        "input[type='search']",
        "input[placeholder*='بحث']",
        "input[placeholder*='Search']",
        "input[name='q']",
        "input[aria-label*='بحث']",
        "input[aria-label*='search']",
    ]
    for sel in candidates_input:
        inp = page.locator(sel).first
        if inp.count() and inp.is_visible():
            # تأكد أن الحقل قابل للكتابة
            try:
                inp.click(timeout=3000); snooze(0.2,0.5)
                return inp
            except: pass

    # 3) محاولة إجبارية عبر JavaScript (في حال وجود shadow DOM بنية بسيطة)
    try:
        # ركّز أول input[type=search] تجده
        page.evaluate("""
            () => {
              const cand = document.querySelector("input[type='search'], input[placeholder*='بحث'], input[placeholder*='Search']");
              if (cand) cand.focus();
            }
        """)
        inp = page.locator("input:focus").first
        if inp.count():
            return inp
    except: pass

    return None

def search_for_term(page, term):
    """
    يكتب الاستعلام ويفتح أول نتيجة مرتبطة بـ 'حديقة' أو 'suwaidi-park'
    """
    inp = open_search_box(page)
    if not inp:
        log("❌ لم أجد مربع البحث لكتابة الاستعلام.")
        return False

    # اكتب الاستعلام واضغط Enter
    try:
        inp.fill("") ; snooze(0.15, 0.35)
        inp.type(term, delay=random.randint(20, 70))
        snooze(0.25, 0.6)
        page.keyboard.press("Enter")
        snooze(0.8, 1.6)
    except Exception as e:
        log(f"⚠️ تعذّر الكتابة في مربع البحث: {e}")
        return False

    # انتظر النتائج، ثم التقط نتيجة مناسبة
    result_locs = [
        page.get_by_role("link", name=re.compile(r"حديقة|Suwaidi", re.I)),
        page.locator("a[href*='suwaidi-park']"),
        page.locator("a:has-text('حديقة')"),
        page.locator("[role=link]:has-text('حديقة')"),
    ]
    target = None
    for loc in result_locs:
        try:
            if loc.count():
                target = loc.first
                break
        except: pass

    if not target:
        # التقط أي بطاقة/عنصر يحمل نفس الكلمات
        try:
            any_res = page.locator("a, [role=link], article, div.card").filter(
                has_text=re.compile(r"حديقة|Suwaidi", re.I)
            ).first
            if any_res.count():
                target = any_res
        except: pass

    if not target:
        log("❌ لم أجد نتيجة مطابقة لعبارة البحث.")
        return False

    try:
        target.scroll_into_view_if_needed(timeout=3000)
        target.click(timeout=4000)
        snooze(0.8, 1.6)
    except Exception as e:
        log(f"⚠️ تعذّر الضغط على نتيجة البحث: {e}")
        return False

    # لو ما زلنا لسنا في /zones/.../book نحاول الوصول لزر/رابط احجز الآن
    if "/zones/" not in page.url:
        try:
            book_btn = page.get_by_role("link", name=re.compile(r"احجز|احجز الآن|Book|حجز", re.I)).first
            if book_btn.count():
                book_btn.click(timeout=4000); snooze(0.8,1.4)
        except: pass

    # لو دخلنا منطقة لكن بدون /book، أضف /book
    if "/zones/" in page.url and "/book" not in page.url:
        try:
            page.goto(page.url.rstrip("/") + "/book", wait_until="domcontentloaded", timeout=TIMEOUT)
            snooze(0.8, 1.4)
        except: pass

    log(f"📍 وصلنا: {page.url}")
    return ("/zones/" in page.url and "/book" in page.url)

# ===== التشغيل =====
def run():
    os.makedirs("artifacts/videos", exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--disable-blink-features=AutomationControlled"],
            slow_mo=30,
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="ar-SA", timezone_id="Asia/Riyadh",
            record_video_dir="artifacts/videos",
            record_video_size={"width":1366,"height":768},
            extra_http_headers={
                "Accept-Language": "ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": "https://webook.com/",
                "DNT": "1",
            },
        )
        page = context.new_page()

        # سجّل جميع الاستجابات HTTP للتشخيص
        page.on("response", lambda r: log(f"[HTTP] {r.status} {r.url}"))

        try:
            # 1) افتح الصفحة الرئيسية
            log("🏠 فتح https://webook.com/")
            page.goto("https://webook.com/", wait_until="domcontentloaded", timeout=TIMEOUT)
            snooze(0.9, 1.7)

            # 2) رفض/التعامل مع الكوكيز
            handle_cookies(page); snooze(0.5, 1.0)

            # 3) ابحث عن "حديقة السويدي" وادخل صفحة الفعالية
            if not search_for_term(page, SEARCH_QUERY):
                log("❌ فشل البحث أو الدخول للفعالية من نتائج البحث.")
                page.screenshot(path="artifacts/final.png", full_page=True)
                return

            # (اختياري) هنا تكمل خطوات الضغط على التاريخ/الوقت ورفع التذاكر… إن أردت لاحقًا

            # لقطة أخيرة
            page.screenshot(path="artifacts/final.png", full_page=True)
            log("📸 حفظت artifacts/final.png")

        finally:
            # حفظ الفيديو باسم ثابت
            try:
                v = page.video
            except Exception:
                v = None
            try:
                page.close()
            except: pass
            try:
                if v:
                    v.save_as("artifacts/videos/session.webm")
                    log("🎥 Saved video -> artifacts/videos/session.webm")
            except Exception as e:
                log(f"⚠️ video save err: {e}")
            context.close()
            browser.close()

if __name__ == "__main__":
    try:
        run()
        sys.exit(0)
    except Exception as e:
        log(f"❌ خطأ:", e)
        sys.exit(1)
