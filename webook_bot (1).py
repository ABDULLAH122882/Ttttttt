# -*- coding: utf-8 -*-
"""
webook_bot.py  —  Single-file Webook booking bot (Playwright)

How to run (locally / Replit):
1) pip install playwright
2) python -m playwright install --with-deps chromium
3) Set environment variables (recommended):
   - WEBOOK_EMAIL
   - WEBOOK_PASSWORD
4) python webook_bot.py

Notes:
- This script logs in to Webook, opens the Al-Suwaidi Park booking page,
  then books 5 tickets for each day listed in DAYS using TIME_TEXT.
- It tries to click "Reject all" cookies banner if present.
- Adjust DAYS / TIME_TEXT / TICKETS below if needed.
"""

import os
import sys
import asyncio
from playwright.async_api import async_playwright

LOGIN_URL = "https://webook.com/en/login?redirect=%2Fen%2Fzones%2Fsuwaidi-park-rs25"
EVENT_URL = "https://webook.com/en/zones/suwaidi-park-rs25/book"

# Read credentials from environment variables for safety
EMAIL = os.getenv("WEBOOK_EMAIL", "")
PASSWORD = os.getenv("WEBOOK_PASSWORD", "")

# --- Booking settings ---
DAYS = ["02 NOV", "03 NOV", "04 NOV", "05 NOV"]  # days to book
TIME_TEXT = "16:00 - 00:00"                      # time slot
TICKETS = 5                                      # tickets per day

async def click_if_visible(page, selector, timeout=2000):
    """Click a locator if it becomes visible; return True if clicked."""
    try:
        el = page.locator(selector)
        await el.first.wait_for(state="visible", timeout=timeout)
        await el.first.click()
        return True
    except Exception:
        return False

async def run():
    if not EMAIL or not PASSWORD:
        print("ERROR: Please set WEBOOK_EMAIL and WEBOOK_PASSWORD environment variables.", file=sys.stderr)
        sys.exit(2)

    async with async_playwright() as p:
        # Launch Chromium; --no-sandbox helps CI environments
        browser = await p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()

        # 1) Go to login page
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")

        # Try to reject cookies if banner appears
        for txt in ["Reject all", "Reject All", "رفض الكل"]:
            if await click_if_visible(page, f"text={txt}", timeout=2500):
                break

        # Fill login form (robust selectors)
        await page.fill('input[type="email"], input[autocomplete="username"], input[placeholder*="Email" i]', EMAIL)
        await page.fill('input[type="password"], input[autocomplete="current-password"], input[placeholder*="Password" i]', PASSWORD)

        # Click a likely login button
        for btn in ["Login", "Sign in", "تسجيل الدخول"]:
            if await click_if_visible(page, f"button:has-text('{btn}')", timeout=2000):
                break

        # Wait a bit for redirect
        await page.wait_for_timeout(3500)

        # 2) Open event booking page
        await page.goto(EVENT_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)

        # Attempt cookies rejection again on event page
        for txt in ["Reject all", "Reject All", "رفض الكل"]:
            if await click_if_visible(page, f"text={txt}", timeout=1500):
                break

        async def book_day(day_text: str):
            print(f"--- Booking {day_text} ---")

            # Select day
            await page.get_by_text(day_text, exact=False).first.click()
            await page.wait_for_timeout(800)

            # Select time slot
            await page.get_by_text(TIME_TEXT, exact=False).first.click()
            await page.wait_for_timeout(1200)

            # Ensure ticket count is 0 then increase to TICKETS
            minus = page.locator("button:has-text('-'), [aria-label='decrease'], button[title*='decrease' i]")
            for _ in range(6):
                try:
                    await minus.first.click(timeout=400)
                except Exception:
                    break

            plus = page.locator("button:has-text('+'), [aria-label='increase'], button[title*='increase' i]")
            for _ in range(TICKETS):
                await plus.first.click()
                await page.wait_for_timeout(120)

            # Go to checkout
            for txt in ["Next: Checkout", "Checkout", "Next", "التالي"]:
                if await click_if_visible(page, f"button:has-text('{txt}')", timeout=2000):
                    break
            await page.wait_for_timeout(1200)

            # Accept terms if present
            await page.mouse.wheel(0, 1600)
            terms = page.locator("input[type='checkbox']")
            try:
                if await terms.count() > 0:
                    await terms.first.check(timeout=1200)
            except Exception:
                await click_if_visible(page, "text=Terms", timeout=800)

            # Confirm / complete booking
            for txt in ["Complete booking", "Confirm", "Complete", "إتمام"]:
                if await click_if_visible(page, f"button:has-text('{txt}')", timeout=2000):
                    break

            # Back to event page for next day
            await page.wait_for_timeout(1500)
            await page.goto(EVENT_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(700)

        # Loop over all days
        for d in DAYS:
            try:
                await book_day(d)
                print(f"✅ Done {d}")
            except Exception as e:
                print(f"⚠️ Failed {d}: {e}", file=sys.stderr)

        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
