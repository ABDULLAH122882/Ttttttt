import re, random, time, os
from playwright.sync_api import sync_playwright

TIMEOUT = 15000

def log(msg):
    print(msg, flush=True)

def snooze(a, b): 
    time.sleep(random.uniform(a, b))

def handle_cookies(page):
    for sel in ["button:has-text('رفض')", "button:has-text('Decline')", "[id*='reject']", "button:has-text('إغلاق')"]:
        try:
            btn = page.locator(sel).first
            if btn.count() and btn.is_visible():
                btn.click(timeout=1000)
                log("✅ تم رفض الكوكيز")
                return True
        except: pass
    return False


def search_event_from_home(context, page, query="حديقة السويدي"):
    log("🏠 فتح الصفحة الرئيسية...")
    page.goto("https://webook.com/", wait_until="domcontentloaded", timeout=TIMEOUT)
    snooze(1,2)
    handle_cookies(page)
    snooze(1,2)

    # مربع البحث
    try:
        search = page.locator("input[type='search'], input[placeholder*='بحث']").first
        search.click()
        search.fill(query)
        page.keyboard.press("Enter")
        log(f"🔎 تم البحث عن: {query}")
        snooze(3,4)
    except Exception as e:
        log(f"❌ فشل في كتابة البحث: {e}")
        return None

    # النتيجة
    try:
        target = page.locator("a[href*='suwaidi'], a:has-text('حديقة')").first
        target.click()
        log("🖱️ تم الضغط على النتيجة")
        snooze(3,4)
    except Exception as e:
        log(f"❌ لم يتم العثور على النتيجة: {e}")
        return None

    # التعامل مع تبويب جديد
    try:
        new_page = context.pages[-1]
        new_page.bring_to_front()
        if "/zones/" in new_page.url:
            log(f"✅ تم فتح صفحة الفعالية: {new_page.url}")
            return new_page
    except:
        pass
    return page


def run():
    log("🚀 بدء تشغيل البوت...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # فتح الصفحة والبحث
        active = search_event_from_home(context, page)
        if not active:
            log("❌ لم يتم الوصول إلى صفحة الفعالية.")
        else:
            log("✅ البحث تم بنجاح.")

        # حفظ صورة
        try:
            active.screenshot(path="artifacts/final.png", full_page=True)
        except:
            page.screenshot(path="artifacts/final.png", full_page=True)

        browser.close()
    log("🏁 انتهى التنفيذ.")


if __name__ == "__main__":
    run()
