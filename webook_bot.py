# ===== البحث عن الفعالية عبر الصفحة الرئيسية =====
def search_event_from_home(context, page, query="حديقة السويدي"):
    """
    يفتح الرئيسية -> يرفض الكوكيز -> يبحث عن الفعالية (حديقة السويدي)
    ويتعامل مع:
      - نتيجة تفتح في تبويب جديد (popup)
      - أو نفس التبويب (SPA)
    ويرجع الصفحة النشطة التي تحتوي على /zones/.../book
    """
    log("🏠 فتح الصفحة الرئيسية...")
    page.goto("https://webook.com/", wait_until="domcontentloaded", timeout=TIMEOUT)
    snooze(0.8, 1.6)
    handle_cookies(page); snooze(0.5, 1.0)

    # افتح مربع البحث إن كان خلف أيقونة
    for sel in [
        "button[aria-label*='بحث']","button[aria-label*='search']",
        "button:has(svg)","button:has-text('بحث')","[data-testid*='search']"
    ]:
        try:
            icon = page.locator(sel).first
            if icon.count() and icon.is_visible():
                icon.click(timeout=2000); snooze(0.3,0.7); break
        except: pass

    # حقل البحث
    search = None
    for sel in [
        "input[type='search']","input[placeholder*='بحث']","input[placeholder*='Search']",
        "input[name='q']","input[aria-label*='بحث']","input[aria-label*='search']",
    ]:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            search = loc; break
    if not search:
        log("❌ لم أجد مربع البحث"); return None

    # اكتب وابحث
    search.click(); snooze(0.2,0.5)
    search.fill("")
    search.type(query, delay=random.randint(20,60))
    page.keyboard.press("Enter")
    snooze(1.0, 2.0)

    # التقط نتيجة مناسبة
    possible = [
        page.get_by_role("link", name=re.compile(r"حديقة|Suwaidi", re.I)),
        page.locator("a[href*='suwaidi-park']"),
        page.locator("a:has-text('حديقة')"),
    ]
    target = None
    for loc in possible:
        if loc.count():
            target = loc.first
            break
    if not target:
        any_res = page.locator("a, [role=link], article, div.card").filter(
            has_text=re.compile(r"حديقة|Suwaidi", re.I)
        ).first
        if any_res.count(): target = any_res
    if not target:
        log("❌ لم أجد نتيجة مطابقة"); return None

    # حاول النقر والتعامل مع popup أو نفس التبويب
    active_page = page
    for attempt in range(1, 4):
        log(f"🖱️ النقر على نتيجة البحث (محاولة {attempt}/3)")
        try:
            with context.expect_page() as popup_info:
                target.click(timeout=4000)
            new_page = popup_info.value
            new_page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
            active_page = new_page
            log("🆕 فُتح تبويب جديد للفعالية.")
        except Exception:
            # ربما نفس التبويب (SPA)
            try:
                active_page.wait_for_url(re.compile(r"/zones/.+"), timeout=TIMEOUT)
                log("↪️ تم النقل داخل نفس التبويب.")
            except Exception:
                try:
                    target.scroll_into_view_if_needed(timeout=2000)
                except: pass
                snooze(0.3,0.8)
                continue
        break

    # لو وصلنا /zones/ بدون /book، اضف /book
    try:
        if "/zones/" in active_page.url and "/book" not in active_page.url:
            active_page.goto(active_page.url.rstrip("/") + "/book",
                             wait_until="domcontentloaded", timeout=TIMEOUT)
            snooze(0.6, 1.2)
    except Exception as e:
        log(f"⚠️ فشل إضافة /book تلقائياً: {e}")

    log(f"📍 الصفحة الحالية: {active_page.url}")
    if "/zones/" in active_page.url and "/book" in active_page.url:
        return active_page
    else:
        log("❌ لم أصل إلى صفحة الحجز بعد النقر على النتيجة.")
        return None
