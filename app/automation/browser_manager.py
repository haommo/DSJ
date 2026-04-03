"""Browser lifecycle management: init, cleanup, screenshots."""

import os
import re
from datetime import datetime
from typing import Optional, Tuple
from playwright.async_api import async_playwright, Page, Browser, Playwright

from app.automation.constants import AutomationError, DEFAULT_TIMEOUT, SCREENSHOT_DIR

os.makedirs(SCREENSHOT_DIR, exist_ok=True)


async def init_browser(headless: bool = True) -> Tuple[Playwright, Browser, Page]:
    """Launch Chromium and return (playwright, browser, page)."""
    pw = None
    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=headless, slow_mo=200,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        page = await browser.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT)
        return pw, browser, page
    except Exception as e:
        if pw:
            try:
                await pw.stop()
            except Exception:
                pass
        raise AutomationError(f"Browser initialization failed: {e}")


async def cleanup_browser(pw: Playwright, browser: Browser, page: Page):
    """Safely close all browser resources."""
    for resource in [page, browser]:
        try:
            if resource:
                await resource.close()
        except Exception:
            pass
    try:
        if pw:
            await pw.stop()
    except Exception:
        pass


async def take_screenshot(page: Page, name: str, email: str) -> Optional[str]:
    """Take a screenshot and return the file path."""
    try:
        if not page:
            return None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_email = re.sub(r'[^a-zA-Z0-9]', '_', email.split('@')[0])
        # Sanitize name to prevent path traversal
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        filename = f"{SCREENSHOT_DIR}/{safe_name}_{safe_email}_{ts}.png"
        await page.screenshot(path=filename)
        return filename
    except Exception:
        return None
