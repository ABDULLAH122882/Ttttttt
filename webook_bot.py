# webook_bot.py
# Bot مهيأ لحجز فعاليات WeBook مع سلوك بشري + فيديو + trace
# ------------------------------------------------------------
# Usage:
# - ضع هذا الملف في نفس مجلد المشروع.
# - اضبط المتغيرات البيئية في GitHub Actions أو محلياً:
#    EVENT_URL (مثلاً "https://webook.com/ar/zones/suwaidi-park-rs25/book")
#    START_DATE  (YYYY-MM-DD) مثلاً "2025-11-03"
#    END_DATE    (YYYY-MM-DD) مثلاً "2025-11-06"
#    WEBOOK_EMAIL, WEBOOK_PASSWORD  (اختياري: لتسجيل الدخول)
#    PROXY_URL   (اختياري: http://user:pass@host:port)
# - شغّل: python webook_bot.py
# ------------------------------------------------------------

import os, re, sys, time, math, random
from datetime import datetime, timedelta, date
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------- إعدادات من environment ----------
EVENT_URL = os.getenv("EVENT_URL", "https://webook.com/ar/zones/suwaidi-park-rs25/book").strip()
START_DATE = os.getenv("START_DATE", "").strip()   # e.g. "2025-11-03"
END_DATE   = os.getenv("END_DATE", "").strip()     # e.g. "2025-11-06"
WEBOOK_EMAIL = os.getenv("WEBOOK_EMAIL", "").strip()
WEBOOK_PASSWORD = os.getenv("WEBOOK_PASSWORD", "").strip()
PROXY_URL = os.getenv("PROXY_URL", "").strip()
TIMEOUT = 60000  # ms

# ---------- Helpers ----------
def log(*a, **k):
    print(*a, **k, flush=True)

def human_sleep(a=0.4, b=1.2):
    time.sleep(random.uniform(a, b))

# user-agent pool
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
]
def choose_ua():
    return random.choice(UA_POOL)

# stealth JS لتقليل اكتشاف headless
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || { runtime: {} };
const originalQuery = navigator.permissions && navigator.permissions.query;
if (originalQuery) {
  navigator.permissions.query = params => {
    if (params && params.name === 'notifications') {
      return Promise.resolve({ state: Notification.permission });
    }
    return originalQuery(params);
  };
}
"""

# حركة ماوس بشرية ومنحنية ثم نقرة
def human_move_and_click(page, locator_or_box, steps=14):
    try:
        # locator_or_box can be a locator or bounding box dict
        if isinstance(locator_or_box, dict):
            box = locator_or_box
        else:
            box = locator_or_box.bounding_box()
    except Exception:
        box = None

    if not box:
        try:
            # fallback to direct click
            locator_or_box.click()
            return
        except:
            return

    target_x = box["x"] + box["width"] * random.uniform(0.35, 0.65)
    target_y = box["y"] + box["height"] * random.uniform(0.35, 0.65)
    # start point: a bit away
    cur_x = random.uniform(max(0, target_x-160), max(0, target_x-40))
    cur_y = random.uniform(max(0, target_y-160), max(0, target_y-40))
    for i in range(steps):
        t = (i+1)/steps
        # small curve
        step_x = cur_x + (target_x - cur_x) * (t**0.9) + random.uniform(-3,3)
        step_y = cur_y + (target_y - cur_y) * (t**0.9) + random.uniform(-3,3)
        try:
            page.mouse.move(step_x, step_y)
        except:
            pass
        time.sleep(random.uniform(0.004, 0.02))
        cur_x, cur_y = step_x, step_y
    try:
        page.mouse.click(target_x, target_y, delay=random.uniform(20,120))
    except:
        try:
            # fallback locator click
            if not isinstance(locator_or_box, dict):
                locator_or_box.click()
        except:
            pass

# دوال للتاريخ (صيغ عربية وانجليزية وأرقام عربية)
AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
MONTHS_EN_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
MONTHS_EN_LONG  = ["January","February","March","April","May","June","July","August","September","October","November","December"]
AR_MONTH = {1:"يناير",2:"فبراير",3:"مارس",4:"أبريل",5:"مايو",6:"يونيو",7:"يوليو",8:"أغسطس",9:"سبتمبر",10:"أكتوبر",11:"نوفمبر",12:"ديسمبر"}

def parse_iso(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

from datetime import datetime
def date_variants(d: date):
    day2 = f"{d.day:02d}"
    day1 = str(d.day)
    day_ar2 = day2.translate(AR_DIGITS)
    day_ar1 = day1.translate(AR_DIGITS)
    en_s = MONTHS_EN_SHORT[d.month-1]
    en_l = MONTHS_EN_LONG[d.month-1]
    ar_l = AR_MONTH[d.month]
    iso = d.strftime("%Y-%m-%d")
    return list({iso, f"{day2} {en_s}", f"{day1} {en_s}", f"{day2} {en_l}", f"{day1} {en_l}",
                 f"{day2} {ar_l}", f"{day1} {ar_l}", f"{day_ar2} {ar_l}", f"{day_ar1} {ar_l}", day2, day1})

# ---------- إجراءات الصفحة ----------
def accept_cookies(page):
    # Try multiple variants
    candidates = [
        page.get_by_role("button", name=re.compile(r"قبول|أوافق|حسناً|أفهم|Accept|Agree", re.I)),
        page.locator("button:has-text('قبول')"),
        page.locator("button:has-text('Accept')"),
        page.locator("button:has-text('رفض')"),
        page.locator("text=قبول"),
    ]
    for c in candidates:
        try:
            if c.count() and c.first.is_visible():
                human_move_and_click(page, c.first)
                human_sleep(0.5, 1.0)
                log("✅ تعاملت مع الكوكيز")
                return True
        except Exception:
            pass
    return False

def login_if_needed(page):
    # If login form present, fill and submit
    try:
        # Look for login form fields
        email = page.locator("input[type='email'], input[name='email'], input[id*='email']").first
        pwd   = page.locator("input[type='password'], input[name='password'], input[id*='password']").first
        btn   = page.get_by_role("button", name=re.compile(r"Login|تسجيل الدخول|Sign in|Log in", re.I)).first
        if email.count() and pwd.count():
            if not WEBOOK_EMAIL or not WEBOOK_PASSWORD:
                log("ℹ️ نموذج تسجيل دخول موجود لكن لم توفّر WEBOOK_EMAIL/WEBOOK_PASSWORD في الـenv.")
                return False
            try:
                email.fill(WEBOOK_EMAIL, timeout=5000)
                human_sleep(0.2, 0.6)
                pwd.fill(WEBOOK_PASSWORD, timeout=5000)
                human_sleep(0.3, 0.7)
                human_move_and_click(page, btn)
                human_sleep(2.0, 4.0)
                log("🔐 تم محاولة تسجيل الدخول")
                return True
            except Exception as e:
                log("⚠️ خطأ أثناء ملء نموذج الدخول:", e)
    except Exception:
        pass
    return False

def open_event_with_fallback(page, url):
    # open event page with retries and try alt locales
    log("🌐 فتح الحدث:", url)
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT)
        st = resp.status if resp else None
        log(f"↪️ status={st} url={page.url}")
    except Exception as e:
        log("⚠️ goto error:", e)
        st = None

    if st in (404, 500, 502, 503) or st is None:
        # try without /ar/ then /en/
        alt1 = url.replace("/ar/", "/")
        alt2 = url.replace("/ar/", "/en/")
        for alt in (alt1, alt2):
            try:
                log("🔁 تجربة بديلة:", alt)
                resp = page.goto(alt, wait_until="domcontentloaded", timeout=TIMEOUT)
                st = resp.status if resp else None
                log(f"↪️ status={st} url={page.url}")
                if st and st < 400:
                    return True
            except Exception as e:
                log("⚠️ alt goto error:", e)
    return (st is not None and st < 400)

def find_booking_scope(page):
    # If booking UI is inside iframe, return that frame; else return page
    frames = page.frames
    log(f"🔎 عدد الإطارات: {len(frames)}")
    for fr in frames:
        u = (fr.url or "").lower()
        if any(k in u for k in ["webook", "booking", "calendar", "zone", "book", "suwaidi"]):
            log("✅ اخترت iframe:", fr.url)
            return fr
    log("ℹ️ استخدام الصفحة الرئيسية كـ scope.")
    return page

def dump_buttons(scope, label="page"):
    try:
        btns = scope.locator("button, [role=button], a, [aria-label], [data-date]")
        cnt = btns.count()
        lines = []
        for i in range(min(cnt, 2000)):
            el = btns.nth(i)
            try:
                t = el.inner_text().strip()
            except:
                t = ""
            try:
                al = el.get_attribute("aria-label") or ""
            except:
                al = ""
            try:
                dd = el.get_attribute("data-date") or ""
            except:
                dd = ""
            if t or al or dd:
                lines.append(f"{i:04d} | txt='{t}' | aria-label='{al}' | data-date='{dd}'")
        with open("artifacts/page_buttons.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        log("🧾 حفظت artifacts/page_buttons.txt (أبرز الأزرار)")
    except Exception as e:
        log("⚠️ لم أتمكن من حفظ page_buttons:", e)

# ---------- الحجز ليوم واحد ----------
def book_for_date(scope, target_date: date):
    variants = date_variants(target_date)
    log("🔎 محاولات نصوص اليوم:", variants)
    # 1) حاول data-date
    iso = target_date.strftime("%Y-%m-%d")
    selectors = [f'[data-date="{iso}"]', f'button[data-date="{iso}"]']
    for sel in selectors:
        try:
            loc = scope.locator(sel).first
            if loc.count() and loc.is_enabled():
                human_move_and_click(scope, loc)
                human_sleep(0.8, 1.4)
                log(f"✅ ضغطت التاريخ عبر {sel}")
                return True
        except Exception:
            pass

    # 2) حاول aria-label/text/role
    for v in variants:
        try:
            # by aria-label
            loc = scope.locator(f'[aria-label*="{v}"]').first
            if loc.count() and loc.is_enabled():
                human_move_and_click(scope, loc); human_sleep(0.8,1.4)
                log(f"✅ ضغطت التاريخ aria-label {v}"); return True
        except Exception:
            pass
        try:
            # by button role (text)
            loc = scope.get_by_role("button", name=re.compile(re.escape(v), re.I)).first
            if loc.count() and loc.is_enabled():
                human_move_and_click(scope, loc); human_sleep(0.8,1.4)
                log(f"✅ ضغطت التاريخ role/button {v}"); return True
        except Exception:
            pass
        try:
            loc = scope.get_by_text(re.compile(re.escape(v), re.I)).first
            if loc.count() and loc.is_enabled():
                human_move_and_click(scope, loc); human_sleep(0.8,1.4)
                log(f"✅ ضغطت التاريخ by text {v}"); return True
        except Exception:
            pass

    log("⚠️ لم أتمكن من الضغط على التاريخ — حفظت الأزرار للتشخيص.")
    dump_buttons(scope, "page")
    return False

def pick_time_and_tickets(scope):
    # بعد الضغط على التاريخ عادة تظهر أوقات في الأسفل — نحاول اختيار أول وقت متاح
    try:
        # common selectors for time slots — نهج متعدد
        slot_selectors = [
            "div.times button", "div.time-slot button", "button.time", "button[class*='slot']",
            "button:has-text('00:')", "button:has-text(':00')"
        ]
        for sel in slot_selectors:
            try:
                btn = scope.locator(sel).filter(has_text=re.compile(r"\d{1,2}:\d{2}", re.I)).first
                if btn.count() and btn.is_enabled():
                    human_move_and_click(scope, btn); human_sleep(0.6, 1.2)
                    log("✅ ضغطت وقت عبر selector:", sel)
                    break
            except Exception:
                pass
        # بعد اختيار الوقت، قد يظهر عدد التذاكر مع أزرار زائد/ناقص
        # حاول رفع العدد إلى 5
        plus_selectors = [
            "button[aria-label*='increase'], button[aria-label*='plus'], button:has-text('+')",
            "button[class*='plus'], button[class*='increment']"
        ]
        target_tickets = 5
        # بعض الواجهات تظهر قيمة في input[type=number] أو span
        try:
            # احاول إيجاد input قيمة التذاكر
            num_input = scope.locator("input[type='number'], input[name*='qty'], input[id*='qty']").first
            if num_input.count():
                # اكتب القيمة مباشرة إذا ممكن
                try:
                    num_input.fill(str(target_tickets), timeout=2000)
                    log(f"✅ ضبطت عدد التذاكر عبر input => {target_tickets}")
                    human_sleep(0.4,0.8)
                except:
                    pass
        except Exception:
            pass
        # إن لم ينجح، اضغط على زر + عدة مرات حتى 5
        for sel in plus_selectors:
            try:
                btn = scope.locator(sel).first
                if btn.count():
                    for i in range(target_tickets):
                        human_move_and_click(scope, btn); human_sleep(0.25, 0.6)
                    log("✅ رفعت التذاكر عبر زر +")
                    break
            except Exception:
                pass

        # بعد ذلك اضغط زر "إكمال الحجز" أو "Complete" أو "Confirm"
        try:
            finish = scope.get_by_role("button", name=re.compile(r"إكمال|إتمام|confirm|complete|حجز|حفظ|Checkout|Book", re.I)).first
            if finish.count():
                # قبل الضغط، تأكد وجود مربع الشروط إن وُجد ووافق عليه
                try:
                    chk = scope.locator("input[type='checkbox'], input[name*='terms'], input[id*='terms']").first
                    if chk.count():
                        try:
                            if not chk.is_checked():
                                human_move_and_click(scope, chk); human_sleep(0.2,0.6)
                                log("✅ وافقت على الشروط")
                        except Exception:
                            pass
                except Exception:
                    pass
                human_move_and_click(scope, finish); human_sleep(1.0, 2.0)
                log("✅ ضغطت زر إكمال الحجز")
                return True
        except Exception:
            pass

    except Exception as e:
        log("⚠️ خطأ أثناء اختيار الوقت/التذاكر:", e)
    return False

# ---------- Main flow ----------
def run():
    if not EVENT_URL:
        log("❌ لم تُحدد EVENT_URL"); return

    # parse dates
    sd = parse_iso(START_DATE) if START_DATE else date.today()
    ed = parse_iso(END_DATE) if END_DATE else sd
    if ed < sd:
        sd, ed = ed, sd

    os.makedirs("artifacts", exist_ok=True)
    os.makedirs("artifacts/videos", exist_ok=True)

    with sync_playwright() as p:
        launch_kwargs = {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
            "slow_mo": 30,  # يبطئ الأوامر قليلاً ليبدو طبيعي
        }
        if PROXY_URL:
            launch_kwargs["proxy"] = {"server": PROXY_URL}
            log("🧭 استخدام بروكسي:", PROXY_URL.split("@")[-1])

        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            user_agent=choose_ua(),
            viewport={"width": random.choice([1200,1280,1366,1440]), "height": random.choice([700,768,800,900])},
            locale="ar-SA",
            timezone_id="Asia/Riyadh",
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
            # 1) افتح الصفحة الرئيسية لتوليد الجلسة
            log("🏠 فتح الصفحة الرئيسية...")
            try:
                page.goto("https://webook.com/", wait_until="domcontentloaded", timeout=TIMEOUT)
            except Exception as e:
                log("⚠️ خطأ فتح الهوم:", e)
            human_sleep(0.8, 1.6)
            accept_cookies(page)
            human_sleep(0.6, 1.2)

            # 2) افتح رابط الفعالية مع fallback
            ok = open_event_with_fallback(page, EVENT_URL)
            if not ok:
                log("❌ الفعالية لم تفتح بنجاح داخل البوت (404 أو خطأ). حفظت لقطة.")
                page.screenshot(path="artifacts/final.png", full_page=True)
                return

            human_sleep(0.8, 1.6)
            # 3) تسجيل الدخول إن كان مطلوبًا
            login_if_needed(page)
            human_sleep(1.0, 2.0)

            # 4) حدد النطاق scope (iframe أو الصفحة)
            scope = find_booking_scope(page)
            # save DOM/buttons for diagnosis if needed
            try:
                with open("artifacts/page.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
                log("📝 حفظ page.html للـ diagnosis")
            except Exception:
                pass
            try:
                dump_buttons(scope, "page")
            except Exception:
                pass

            # 5) Loop over dates
            cur = sd
            while cur <= ed:
                log(f"=== محاولة الحجز لـ {cur.isoformat()} ===")
                # refresh event page each loop (robustness)
                try:
                    page.goto(EVENT_URL, wait_until="domcontentloaded", timeout=TIMEOUT)
                    human_sleep(0.6, 1.2)
                except Exception:
                    pass

                scope = find_booking_scope(page)
                accept_cookies(scope)
                human_sleep(0.5, 1.0)

                if not book_for_date(scope, cur):
                    log(f"⚠️ فشل الضغط على {cur.isoformat()}، سأنقل لليوم التالي.")
                    # احفظ لقطة مفصلة
                    try:
                        scope.screenshot(path=f"artifacts/fail_{cur.strftime('%Y%m%d')}.png", full_page=True)
                    except:
                        pass
                    cur += timedelta(days=1)
                    continue

                human_sleep(0.6, 1.2)
                # بعد الضغط على اليوم، ننتظر ونحاول اختيار الوقت والرفع للتذاكر
                success_booking = pick_time_and_tickets(scope)
                if success_booking:
                    log(f"✅ حاولت الحجز لـ {cur.isoformat()} (تم الضغط على إكمال).")
                    # optionally: wait for confirmation page or message
                    human_sleep(1.5, 3.0)
                else:
                    log(f"⚠️ لم يكتمل الحجز تلقائياً لـ {cur.isoformat()}. حفظت لقطة للتشخيص.")
                    try:
                        scope.screenshot(path=f"artifacts/after_click_{cur.strftime('%Y%m%d')}.png", full_page=True)
                    except:
                        pass

                # انتظر قليلاً ثم اذهب لليوم التالي
                cur += timedelta(days=1)
                human_sleep(1.0, 2.0)

            # نهاية اللوب: لقطة نهائية
            try:
                page.screenshot(path="artifacts/final.png", full_page=True)
                log("📸 حفظت artifacts/final.png")
            except Exception:
                pass

        finally:
            # حفظ trace و الفيديو
            try:
                context.tracing.stop(path="trace.zip")
                log("🧭 Saved trace.zip")
            except Exception as e:
                log("ℹ️ trace stop err:", e)
            # حفظ الفيديو باسم ثابت (Playwright يولّد ملف داخل artifacts/videos)
            try:
                video = page.video
            except Exception:
                video = None
            try:
                page.close()
            except:
                pass
            try:
                if video:
                    video.save_as("artifacts/videos/session.webm")
                    log("🎥 Saved video -> artifacts/videos/session.webm")
            except Exception as e:
                log("⚠️ video save err:", e)
            try:
                context.close()
            except:
                pass
            browser.close()

if __name__ == "__main__":
    try:
        run()
        sys.exit(0)
    except PWTimeout as e:
        log("⛔ Timeout:", e)
        sys.exit(1)
    except Exception as e:
        log("❌ خطأ:", e)
        sys.exit(1)
