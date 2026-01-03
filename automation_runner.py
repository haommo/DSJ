import asyncio
from playwright.async_api import async_playwright, Page, Browser, Playwright, TimeoutError as PlaywrightTimeout
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import os
import re
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AutomationError(Exception):
    """Custom exception for automation errors"""
    pass


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class DSJAutomation:
    """
    Class chạy automation cho một account
    Với error handling và retry mechanism
    """
    
    # Cấu hình
    DEFAULT_TIMEOUT = 15000  # 15 seconds
    MAX_RETRIES = 1
    RETRY_DELAY = 2  # seconds
    STEP_DELAY = 2  # seconds - delay sau mỗi step
    
    def __init__(self, email: str, password: str, order_code: str, account_code: str = None):
        self.email = email
        self.password = password
        self.order_code = order_code
        
        # Browser instances
        self.playwright: Playwright = None
        self.browser: Browser = None
        self.page: Page = None
        
        # State
        self.is_running = False
        self.is_cancelled = False
        self.current_step = ""
        
        # Results
        self.account_code: str = account_code
        self.balance: float = None
        self.screenshot_path: str = None  # Lưu path screenshot
        self.screenshot_dir = "screenshots"
        
        # Tạo thư mục screenshots
        os.makedirs(self.screenshot_dir, exist_ok=True)

    async def _init_browser(self, headless: bool = True) -> bool:
        """Khởi tạo browser với error handling"""
        try:
            logger.info(f"[{self.email}] Initializing browser...")
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=headless,
                slow_mo=200,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            self.page = await self.browser.new_page()
            
            # Set default timeout
            self.page.set_default_timeout(self.DEFAULT_TIMEOUT)
            
            logger.info(f"[{self.email}] Browser initialized successfully")
            return True
        except Exception as e:
            logger.error(f"[{self.email}] Failed to initialize browser: {e}")
            await self._cleanup()
            raise AutomationError(f"Browser initialization failed: {e}")

    async def _cleanup(self):
        """Dọn dẹp resources"""
        try:
            if self.page:
                await self.page.close()
        except:
            pass
        
        try:
            if self.browser:
                await self.browser.close()
        except:
            pass
        
        try:
            if self.playwright:
                await self.playwright.stop()
        except:
            pass
        
        self.page = None
        self.browser = None
        self.playwright = None

    async def _take_screenshot(self, name: str) -> Optional[str]:
        """Chụp screenshot với error handling"""
        try:
            if not self.page:
                return None
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_email = re.sub(r'[^a-zA-Z0-9]', '_', self.email.split('@')[0])
            filename = f"{self.screenshot_dir}/{name}_{safe_email}_{timestamp}.png"
            await self.page.screenshot(path=filename)
            logger.info(f"[{self.email}] Screenshot saved: {filename}")
            return filename
        except Exception as e:
            logger.warning(f"[{self.email}] Failed to take screenshot: {e}")
            return None

    async def _retry_step(self, step_func, step_name: str, max_retries: int = None) -> bool:
        """
        Retry một step với số lần thử tối đa
        """
        retries = max_retries or self.MAX_RETRIES
        last_error = None
        
        for attempt in range(retries + 1):
            if self.is_cancelled:
                logger.info(f"[{self.email}] Automation cancelled at step: {step_name}")
                return False
            
            try:
                self.current_step = step_name
                logger.info(f"[{self.email}] Step '{step_name}' - Attempt {attempt + 1}/{retries + 1}")
                
                result = await step_func()
                
                if result:
                    logger.info(f"[{self.email}] Step '{step_name}' completed successfully")
                    # Sleep 3s sau mỗi step thành công
                    await asyncio.sleep(self.STEP_DELAY)
                    return True
                else:
                    raise AutomationError(f"Step returned False")
                    
            except PlaywrightTimeout as e:
                last_error = f"Timeout: {e}"
                logger.warning(f"[{self.email}] Step '{step_name}' timeout (attempt {attempt + 1})")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[{self.email}] Step '{step_name}' failed (attempt {attempt + 1}): {e}")
            
            # Retry delay
            if attempt < retries:
                await asyncio.sleep(self.RETRY_DELAY)
        
        logger.error(f"[{self.email}] Step '{step_name}' failed after {retries + 1} attempts: {last_error}")
        return False

    # ============== AUTOMATION STEPS ==============

    async def _step_go_to_login(self) -> bool:
        """Bước 1: Truy cập trang login"""
        await self.page.goto("https://dsj079.com/pc/#/login", wait_until="networkidle")
        await asyncio.sleep(1)
        return True

    async def _step_enter_email(self) -> bool:
        """Bước 2: Nhập email"""
        email_input = self.page.locator('//input[@placeholder="Please enter your email address"]')
        await email_input.wait_for(state="visible")
        await email_input.clear()
        await email_input.fill(self.email)
        return True

    async def _step_enter_password(self) -> bool:
        """Bước 3: Nhập password"""
        password_input = self.page.locator('//input[@placeholder="Please enter your password"]')
        await password_input.wait_for(state="visible")
        await password_input.clear()
        await password_input.fill(self.password)
        return True

    async def _step_wait_and_click_login(self) -> bool:
        """Bước 4: Đợi và click login"""
        await asyncio.sleep(3)  # Đợi 3s theo yêu cầu
        
        login_btn = self.page.locator('//div[contains(@class, "login-btn")]')
        await login_btn.wait_for(state="visible")
        await login_btn.click()
        return True

    async def _step_verify_login(self) -> bool:
        """Bước 5: Xác nhận đăng nhập thành công"""
        await asyncio.sleep(3)
        
        # Chờ account_code xuất hiện trên trang
        if not self.account_code:
            raise Exception("account_code is required for verification")
        
        # Dùng state="attached" thay vì "visible" vì element có thể bị hidden bởi CSS
        # nhưng vẫn tồn tại trong DOM = đăng nhập thành công
        account_span = self.page.locator(f'text={self.account_code}')
        await account_span.wait_for(state="attached", timeout=15000)
        logger.info(f"[{self.email}] Logged in as: {self.account_code}")
        
        return True

    async def _step_go_to_transaction(self) -> bool:
        """Bước 6: Truy cập trang transaction"""
        await self.page.goto(
            "https://dsj079.com/pc/#/contractTransaction?symbolId=52946918015242240",
            wait_until="networkidle"
        )
        await asyncio.sleep(2)
        return True

    async def _step_click_invited_me(self) -> bool:
        """Bước 7: Click 'invited me' và chờ input xuất hiện"""
        # Thử nhiều selector để tìm "invited me"
        selectors = [
            'text=invited me',
            "//div[contains(@class, 'title') and contains(normalize-space(), 'invited me')]",
        ]
        
        clicked = False
        for selector in selectors:
            try:
                element = self.page.locator(selector).first
                await element.wait_for(state="visible", timeout=10000)
                await element.click()
                logger.info(f"[{self.email}] Clicked 'invited me' using selector: {selector}")
                clicked = True
                break
            except Exception as e:
                logger.warning(f"[{self.email}] Selector '{selector}' failed: {e}")
                continue
        
        if not clicked:
            raise Exception("Could not find or click 'invited me' element")
        
        # Chờ input code xuất hiện để xác nhận click thành công
        code_input = self.page.locator('//input[@placeholder="Please enter the order code"]')
        try:
            await code_input.wait_for(state="visible", timeout=15000)
            logger.info(f"[{self.email}] Code input appeared - click successful")
        except:
            # Thử click lại một lần nữa
            logger.warning(f"[{self.email}] Code input not appeared, trying to click again...")
            for selector in selectors:
                try:
                    element = self.page.locator(selector).first
                    await element.click()
                    await code_input.wait_for(state="visible", timeout=10000)
                    logger.info(f"[{self.email}] Second click successful")
                    break
                except:
                    continue
            else:
                raise Exception("Code input did not appear after clicking 'invited me'")
        
        return True

    async def _step_enter_code_and_confirm(self) -> bool:
        """Bước 8: Nhập code và confirm"""
        # Kiểm tra xem "BG Wealth Signal" đã xuất hiện chưa (đã làm rồi)
        bg_signal = self.page.locator('text=BG Wealth Signal')
        try:
            await bg_signal.wait_for(state="visible", timeout=5000)
            # Đã xuất hiện = đã làm task này rồi
            logger.info(f"[{self.email}] 'BG Wealth Signal' already exists - Task already completed!")
            
            # Chụp screenshot và lưu vào self để trả về trong result
            await asyncio.sleep(1)
            self.screenshot_path = await self._take_screenshot("already_completed")
            
            # Đánh dấu là đã hoàn thành từ trước
            self.already_completed = True
            return True
            
        except:
            # Chưa xuất hiện = chưa làm, tiếp tục nhập code
            logger.info(f"[{self.email}] 'BG Wealth Signal' not found - Proceeding to enter code...")
        
        # Input đã được verify ở step trước, lấy lại
        code_input = self.page.locator('//input[@placeholder="Please enter the order code"]')
        await code_input.wait_for(state="visible", timeout=5000)
        
        # Nhập code
        await code_input.clear()
        await code_input.fill(self.order_code)
        await asyncio.sleep(2)
        
        # Click Confirm - dùng get_by_role để tìm button chính xác
        confirm_btn = self.page.get_by_role("button", name="Confirm").first
        await confirm_btn.wait_for(state="visible")
        logger.info(f"[{self.email}] Clicking 'Confirm' now...")
        await confirm_btn.click()
        
        # Chờ xuất hiện "BG Wealth Signal" để xác nhận thành công
        logger.info(f"[{self.email}] Waiting for 'BG Wealth Signal' to appear...")
        
        await bg_signal.wait_for(state="visible", timeout=15000)
        
        logger.info(f"[{self.email}] 'BG Wealth Signal' appeared - Confirm successful!")
        
        # Chụp screenshot sau khi confirm thành công
        await asyncio.sleep(1)
        self.screenshot_path = await self._take_screenshot("confirm_success")
        
        return True

    async def _step_get_balance(self) -> bool:
        """Bước 9: Truy cập trang assets và lấy số dư tài khoản"""
        try:
            # Truy cập trang assets
            await self.page.goto("https://dsj079.com/pc/#/assets", wait_until="networkidle")
            await asyncio.sleep(3)
            
            # Tìm span có class="total-money" bằng XPath
            balance_span = self.page.locator('//span[contains(@class, "total-money")]')
            await balance_span.wait_for(state="visible", timeout=10000)
            
            # Lấy text content
            balance_text = await balance_span.text_content()
            
            if balance_text:
                # Parse số từ text (loại bỏ khoảng trắng, dấu phẩy)
                clean_text = balance_text.strip().replace(',', '')
                match = re.search(r'([\d]+\.?\d*)', clean_text)
                
                if match:
                    self.balance = float(match.group(1))
                    logger.info(f"[{self.email}] Balance found: ${self.balance}")
                    return True
            
            logger.warning(f"[{self.email}] Could not parse balance from: {balance_text}")
            return True  # Không có balance không phải lỗi critical
            
        except PlaywrightTimeout:
            logger.warning(f"[{self.email}] Timeout waiting for balance element")
            return True  # Cho qua nếu không tìm thấy balance
            
        except Exception as e:
            logger.warning(f"[{self.email}] Error getting balance: {e}")
            return True

    # ============== MAIN RUN METHOD ==============

    async def run(self, headless: bool = True) -> Dict[str, Any]:
        """
        Chạy toàn bộ automation với error handling
        Returns: dict với kết quả chi tiết
        """
        result = {
            "success": False,
            "message": "",
            "account_code": None,
            "balance": None,
            "screenshot": None,
            "error": None,
            "failed_step": None
        }
        
        self.is_running = True
        self.is_cancelled = False
        
        try:
            # Khởi tạo browser
            await self._init_browser(headless=headless)
            
            # Định nghĩa các steps
            steps = [
                (self._step_go_to_login, "go_to_login"),
                (self._step_enter_email, "enter_email"),
                (self._step_enter_password, "enter_password"),
                (self._step_wait_and_click_login, "click_login"),
                (self._step_verify_login, "verify_login"),
                (self._step_go_to_transaction, "go_to_transaction"),
                (self._step_click_invited_me, "click_invited_me"),
                (self._step_enter_code_and_confirm, "enter_code_confirm"),
                (self._step_get_balance, "get_balance"),
            ]
            
            # Chạy từng step
            for step_func, step_name in steps:
                if self.is_cancelled:
                    result["error"] = "Automation cancelled"
                    result["failed_step"] = step_name
                    break
                
                success = await self._retry_step(step_func, step_name)
                
                if not success:
                    result["error"] = f"Failed at step: {step_name}"
                    result["failed_step"] = step_name
                    result["screenshot"] = await self._take_screenshot(f"failed_{step_name}")
                    break
            else:
                # Tất cả steps thành công
                result["success"] = True
                result["message"] = "Thành công"
                # Lấy screenshot nếu đã chụp (ví dụ: already_completed)
                if self.screenshot_path:
                    result["screenshot"] = self.screenshot_path
            
            # Cập nhật kết quả
            result["account_code"] = self.account_code
            result["balance"] = self.balance
            
        except AutomationError as e:
            result["error"] = str(e)
            result["screenshot"] = await self._take_screenshot("error")
            logger.error(f"[{self.email}] Automation error: {e}")
            
        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)}"
            result["screenshot"] = await self._take_screenshot("unexpected_error")
            logger.error(f"[{self.email}] Unexpected error: {e}")
            
        finally:
            self.is_running = False
            await self._cleanup()
            
        return result

    def cancel(self):
        """Hủy automation đang chạy"""
        self.is_cancelled = True
        logger.info(f"[{self.email}] Cancellation requested")


class AutomationManager:
    """
    Quản lý các automation instances
    """
    
    def __init__(self):
        self.running_automations: Dict[str, DSJAutomation] = {}
    
    async def run_for_account(
        self,
        email: str,
        password: str,
        order_code: str,
        account_code: str = None,
        headless: bool = True
    ) -> Dict[str, Any]:
        """Chạy automation cho một account"""
        
        # Tạo unique key
        key = f"{email}_{order_code}"
        
        # Kiểm tra đang chạy
        if key in self.running_automations:
            return {
                "success": False,
                "error": "Automation already running for this account"
            }
        
        automation = DSJAutomation(email, password, order_code, account_code)
        self.running_automations[key] = automation
        
        try:
            result = await automation.run(headless=headless)
            return result
        finally:
            # Cleanup
            if key in self.running_automations:
                del self.running_automations[key]
    
    def cancel_for_account(self, email: str, order_code: str) -> bool:
        """Hủy automation cho một account"""
        key = f"{email}_{order_code}"
        
        if key in self.running_automations:
            self.running_automations[key].cancel()
            return True
        return False
    
    def get_running_count(self) -> int:
        """Số lượng automation đang chạy"""
        return len(self.running_automations)


# Singleton instance
automation_manager = AutomationManager()


async def run_automation_for_account(
    email: str,
    password: str,
    order_code: str,
    account_code: str = None,
    headless: bool = True
) -> Dict[str, Any]:
    """Helper function để chạy automation cho một account"""
    return await automation_manager.run_for_account(
        email=email,
        password=password,
        order_code=order_code,
        account_code=account_code,
        headless=headless
    )
