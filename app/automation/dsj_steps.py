"""DSJ automation step functions for browser login and transaction flow."""

import asyncio
import re
import logging
from playwright.async_api import Page
from typing import Optional

from app.automation.constants import (
    SELECTOR_EMAIL_INPUT, SELECTOR_PASSWORD_INPUT, SELECTOR_LOGIN_BTN,
    SELECTOR_ORDER_CODE_INPUT, SELECTOR_BALANCE, SELECTORS_INVITED_ME,
    build_login_url, build_transaction_url, build_assets_url,
    VERIFY_TIMEOUT, INVITED_TAB_TIMEOUT, CONFIRM_TIMEOUT, BG_SIGNAL_TIMEOUT,
    BALANCE_TIMEOUT, FOLLOW_TIMEOUT,
)

logger = logging.getLogger(__name__)


async def _find_visible_by_text(page: Page, text: str, timeout: int) -> tuple:
    """Find a visible element matching text. Returns (is_visible, locator).

    Handles case where multiple elements match but only nth one is visible.
    """
    locator = page.locator(f'text={text}')
    try:
        await locator.first.wait_for(state="attached", timeout=timeout)
        count = await locator.count()
        logger.info(f"[bg_signal] text='{text}' → {count} element(s) found in DOM")
        for i in range(count):
            el = locator.nth(i)
            visible = await el.is_visible()
            logger.info(f"[bg_signal] Element {i}: visible={visible}")
            if visible:
                return True, el
        logger.warning(f"[bg_signal] All {count} element(s) matching '{text}' are NOT visible")
        return False, locator.first
    except Exception as e:
        logger.info(f"[bg_signal] No elements found for text='{text}' within {timeout}ms: {e}")
        return False, locator.first


async def step_go_to_login(page: Page, site_domain: str) -> bool:
    url = build_login_url(site_domain)
    await page.goto(url, wait_until="networkidle")
    await asyncio.sleep(1)
    return True


async def step_enter_email(page: Page, email: str) -> bool:
    el = page.locator(SELECTOR_EMAIL_INPUT)
    await el.wait_for(state="visible")
    await el.clear()
    await el.fill(email)
    return True


async def step_enter_password(page: Page, password: str) -> bool:
    el = page.locator(SELECTOR_PASSWORD_INPUT)
    await el.wait_for(state="visible")
    await el.clear()
    await el.fill(password)
    return True


async def step_click_login(page: Page) -> bool:
    await asyncio.sleep(3)
    btn = page.locator(SELECTOR_LOGIN_BTN)
    await btn.wait_for(state="visible")
    await btn.click()
    return True


async def step_verify_login(page: Page, account_code: str) -> bool:
    await asyncio.sleep(3)
    # New UI verification: login is considered successful only when Markets tab is visible.
    markets_span = page.locator("//span[contains(@class, 'mt-5') and normalize-space()='Markets']").first
    await markets_span.wait_for(state="visible", timeout=VERIFY_TIMEOUT)
    return True


async def step_go_to_transaction(page: Page, site_domain: str) -> bool:
    url = build_transaction_url(site_domain)
    await page.goto(url, wait_until="networkidle")
    await asyncio.sleep(2)
    return True


async def step_click_invited_me(page: Page) -> bool:
    clicked = False
    for selector in SELECTORS_INVITED_ME:
        try:
            el = page.locator(selector).first
            await el.wait_for(state="visible", timeout=INVITED_TAB_TIMEOUT)
            await el.click()
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        raise Exception("Could not find 'invited me' element")

    code_input = page.locator(SELECTOR_ORDER_CODE_INPUT)
    try:
        await code_input.wait_for(state="visible", timeout=CONFIRM_TIMEOUT)
    except Exception:
        for selector in SELECTORS_INVITED_ME:
            try:
                el = page.locator(selector).first
                await el.click()
                await code_input.wait_for(state="visible", timeout=INVITED_TAB_TIMEOUT)
                break
            except Exception:
                continue
        else:
            raise Exception("Code input did not appear")
    return True


async def step_enter_code_and_confirm(
    page: Page, order_code: str, take_screenshot_fn,
    bg_signal_text: str = "BG Wealth Sharing",
) -> Optional[str]:
    """Enter code and confirm. Returns screenshot path if already completed."""
    logger.info(f"[enter_code_confirm] Checking bg_signal_text='{bg_signal_text}'")
    bg_visible, bg_el = await _find_visible_by_text(page, bg_signal_text, BG_SIGNAL_TIMEOUT)
    if bg_visible:
        await asyncio.sleep(1)
        screenshot = await take_screenshot_fn("already_completed")
        return screenshot  # Already completed

    code_input = page.locator(SELECTOR_ORDER_CODE_INPUT)
    await code_input.wait_for(state="visible", timeout=BG_SIGNAL_TIMEOUT)
    await code_input.clear()
    await code_input.fill(order_code)
    await asyncio.sleep(2)

    confirm_btn = page.get_by_role("button", name="Confirm").first
    await confirm_btn.wait_for(state="visible")
    await confirm_btn.click()

    bg_visible, bg_el = await _find_visible_by_text(page, bg_signal_text, CONFIRM_TIMEOUT)
    if not bg_visible:
        raise Exception(f"bg_signal '{bg_signal_text}' not visible after confirm")
    await asyncio.sleep(1)
    screenshot = await take_screenshot_fn("confirm_success")
    return screenshot


async def step_get_balance(page: Page, site_domain: str) -> Optional[float]:
    """Navigate to assets page and extract balance."""
    try:
        url = build_assets_url(site_domain)
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(3)
        el = page.locator(SELECTOR_BALANCE)
        await el.wait_for(state="visible", timeout=BALANCE_TIMEOUT)
        text = await el.text_content()
        if text:
            match = re.search(r'([\d]+\.?\d*)', text.strip().replace(',', ''))
            if match:
                return float(match.group(1))
    except Exception:
        pass
    return None


async def step_follow_order_confirm(
    page: Page,
    bg_signal_text: str,
    confirm_text: str,
    done_text: str,
    completed_text: str,
    take_screenshot_fn,
) -> dict:
    """Follow order flow with 3 cases after clicking 'invited me'.

    Returns dict: {"status": "success"|"already_done"|"not_eligible", "screenshot": path}
    """
    # Check bg_signal and confirm button presence
    logger.info(f"[follow_order] Checking bg_signal_text='{bg_signal_text}'")
    bg_visible, bg_el = await _find_visible_by_text(page, bg_signal_text, FOLLOW_TIMEOUT)

    confirm_visible = False
    if bg_visible:
        confirm_btn = page.locator(f'text={confirm_text}').first
        try:
            await confirm_btn.wait_for(state="visible", timeout=BG_SIGNAL_TIMEOUT)
            confirm_visible = True
        except Exception:
            pass

    # Case 2: bg_signal not visible → không đủ điều kiện
    if not bg_visible:
        await asyncio.sleep(1)
        screenshot = await take_screenshot_fn("not_eligible")
        return {"status": "not_eligible", "screenshot": screenshot}

    # Case 1: bg_signal visible but no confirm button → already done
    if bg_visible and not confirm_visible:
        await asyncio.sleep(1)
        screenshot = await take_screenshot_fn("already_completed")
        return {"status": "already_done", "screenshot": screenshot}

    # Case 3: both visible → click confirm → dialog confirm → wait completed
    await asyncio.sleep(1)
    await confirm_btn.click()
    logger.info(f"Clicked '{confirm_text}'")

    # Wait for dialog confirm button and click
    await asyncio.sleep(2)
    dialog_btn_xpath = f"//div[@role='dialog']//button[span[text()='{done_text}']]"
    dialog_btn = page.locator(dialog_btn_xpath).first
    await dialog_btn.wait_for(state="visible", timeout=FOLLOW_TIMEOUT)
    await asyncio.sleep(1)
    await dialog_btn.click()
    logger.info(f"Clicked dialog '{done_text}'")

    # Wait for completed signal
    await asyncio.sleep(2)
    completed_signal = page.locator(f'text={completed_text}').first
    await completed_signal.wait_for(state="visible", timeout=FOLLOW_TIMEOUT)
    logger.info(f"Follow order completed: '{completed_text}' visible")

    await asyncio.sleep(1)
    screenshot = await take_screenshot_fn("follow_completed")
    return {"status": "success", "screenshot": screenshot}
