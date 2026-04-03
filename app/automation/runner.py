"""DSJ Automation orchestrator and manager."""

import asyncio
import logging
from typing import Dict, Any
from functools import partial
from playwright.async_api import TimeoutError as PlaywrightTimeout

from app.automation.constants import (
    AutomationError, MAX_RETRIES, RETRY_DELAY, STEP_DELAY,
)
from app.automation.browser_manager import init_browser, cleanup_browser, take_screenshot
from app.automation import dsj_steps

logger = logging.getLogger(__name__)


class DSJAutomation:
    """Chạy automation cho 1 account DSJ"""

    def __init__(self, email: str, password: str, order_code: str,
                 account_code: str = None, site_domain: str = "dsj079.com"):
        self.email = email
        self.password = password
        self.order_code = order_code
        self.account_code = account_code
        self.site_domain = site_domain

        self.pw = None
        self.browser = None
        self.page = None

        self.is_running = False
        self.is_cancelled = False
        self.current_step = ""
        self.balance: float = None
        self.screenshot_path: str = None

    async def _screenshot(self, name: str):
        return await take_screenshot(self.page, name, self.email)

    async def _retry_step(self, step_func, step_name: str) -> bool:
        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            if self.is_cancelled:
                return False
            try:
                self.current_step = step_name
                result = await step_func()
                if result is not None and result is not False:
                    await asyncio.sleep(STEP_DELAY)
                    return True
                raise AutomationError("Step returned False")
            except PlaywrightTimeout as e:
                last_error = f"Timeout: {e}"
            except Exception as e:
                last_error = str(e)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)

        logger.error(f"[{self.email}] Step '{step_name}' failed: {last_error}")
        return False

    async def run(self, headless: bool = True) -> Dict[str, Any]:
        result = {
            "success": False, "message": "", "account_code": None,
            "balance": None, "screenshot": None, "error": None, "failed_step": None,
        }
        self.is_running = True
        self.is_cancelled = False
        p = self.page  # will be set after init

        try:
            self.pw, self.browser, self.page = await init_browser(headless)
            p = self.page
            d = self.site_domain

            steps = [
                (partial(dsj_steps.step_go_to_login, p, d), "go_to_login"),
                (partial(dsj_steps.step_enter_email, p, self.email), "enter_email"),
                (partial(dsj_steps.step_enter_password, p, self.password), "enter_password"),
                (partial(dsj_steps.step_click_login, p), "click_login"),
                (partial(dsj_steps.step_verify_login, p, self.account_code), "verify_login"),
                (partial(dsj_steps.step_go_to_transaction, p, d), "go_to_transaction"),
                (partial(dsj_steps.step_click_invited_me, p), "click_invited_me"),
            ]

            for step_func, step_name in steps:
                if self.is_cancelled:
                    result["error"] = "Automation cancelled"
                    result["failed_step"] = step_name
                    break
                success = await self._retry_step(step_func, step_name)
                if not success:
                    result["error"] = f"Failed at step: {step_name}"
                    result["failed_step"] = step_name
                    result["screenshot"] = await self._screenshot(f"failed_{step_name}")
                    break
            else:
                # Enter code & confirm (special: may return screenshot path)
                if not self.is_cancelled:
                    try:
                        self.current_step = "enter_code_confirm"
                        screenshot = await dsj_steps.step_enter_code_and_confirm(
                            p, self.order_code, self._screenshot
                        )
                        if screenshot:
                            self.screenshot_path = screenshot
                    except Exception as e:
                        result["error"] = f"Failed at step: enter_code_confirm"
                        result["failed_step"] = "enter_code_confirm"
                        result["screenshot"] = await self._screenshot("failed_enter_code_confirm")

                # Get balance
                if not result["error"] and not self.is_cancelled:
                    self.current_step = "get_balance"
                    self.balance = await dsj_steps.step_get_balance(p, d)

                if not result["error"]:
                    result["success"] = True
                    result["message"] = "Thành công"
                    if self.screenshot_path:
                        result["screenshot"] = self.screenshot_path

            result["account_code"] = self.account_code
            result["balance"] = self.balance

        except AutomationError as e:
            result["error"] = str(e)
            result["screenshot"] = await self._screenshot("error")
        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)}"
            result["screenshot"] = await self._screenshot("unexpected_error")
        finally:
            self.is_running = False
            await cleanup_browser(self.pw, self.browser, self.page)
            self.pw = self.browser = self.page = None

        return result

    def cancel(self):
        self.is_cancelled = True


class AutomationManager:
    """Quản lý instances automation đang chạy — ngăn chạy trùng cùng account+order."""

    def __init__(self):
        self.running: Dict[str, DSJAutomation] = {}

    async def run_for_account(self, email: str, password: str,
                              order_code: str, account_code: str = None,
                              headless: bool = True,
                              site_domain: str = "dsj079.com") -> Dict[str, Any]:
        key = f"{email}_{order_code}"
        if key in self.running:
            return {"success": False, "error": "Already running for this account"}

        auto = DSJAutomation(email, password, order_code, account_code, site_domain=site_domain)
        self.running[key] = auto
        try:
            return await auto.run(headless=headless)
        finally:
            self.running.pop(key, None)


automation_manager = AutomationManager()


async def run_automation_for_account(email: str, password: str, order_code: str,
                                     account_code: str = None, headless: bool = True,
                                     site_domain: str = "dsj079.com") -> Dict[str, Any]:
    return await automation_manager.run_for_account(
        email=email, password=password, order_code=order_code,
        account_code=account_code, headless=headless, site_domain=site_domain,
    )
