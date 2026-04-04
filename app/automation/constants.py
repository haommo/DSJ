"""Constants for DSJ automation: selectors, URLs, timeouts."""


class AutomationError(Exception):
    pass


# Timeouts (ms)
DEFAULT_TIMEOUT = 15000
BALANCE_TIMEOUT = 10000
VERIFY_TIMEOUT = 15000
INVITED_TAB_TIMEOUT = 10000
CONFIRM_TIMEOUT = 15000
BG_SIGNAL_TIMEOUT = 5000
FOLLOW_TIMEOUT = 15000

# Retry config
MAX_RETRIES = 1
RETRY_DELAY = 2  # seconds
STEP_DELAY = 2  # seconds

# XPath selectors
SELECTOR_EMAIL_INPUT = '//input[@placeholder="Please enter your email address"]'
SELECTOR_PASSWORD_INPUT = '//input[@placeholder="Please enter your password"]'
SELECTOR_LOGIN_BTN = '//div[contains(@class, "login-btn")]'
SELECTOR_ORDER_CODE_INPUT = '//input[@placeholder="Please enter the order code"]'
SELECTOR_BALANCE = '//span[contains(@class, "total-money")]'

# Text-based selectors for "invited me" tab
SELECTORS_INVITED_ME = [
    'text=invited me',
    "//div[contains(@class, 'title') and contains(normalize-space(), 'invited me')]",
]

# URL templates
URL_LOGIN = "https://{domain}/pc/#/login"
URL_TRANSACTION = "https://{domain}/pc/#/contractTransaction?symbolId=52946918015242240"
URL_ASSETS = "https://{domain}/pc/#/assets"

# Screenshots directory
SCREENSHOT_DIR = "screenshots"
