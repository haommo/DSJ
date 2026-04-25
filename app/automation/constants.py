"""Constants for DSJ automation: selectors, URLs, timeouts."""

from urllib.parse import urlparse


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
SELECTOR_BALANCE = '//div[contains(@class, "my-assets")]//span[contains(@class, "fs-24") and contains(@class, "fw-700")]'

# Text-based selectors for "invited me" tab
SELECTORS_INVITED_ME = [
    'text=invited me',
    "//div[contains(@class, 'title') and contains(normalize-space(), 'invited me')]",
]

# URL templates (new site schema uses /h5/ios#/...)
URL_LOGIN = "https://{domain}/h5/ios#/login"
URL_TRANSACTION = "https://{domain}/h5/ios#/trade"
URL_ASSETS = "https://{domain}/h5/ios#/assets"


def normalize_site_domain(site_domain: str) -> str:
    """Normalize site input to a hostname only.

    Accepts values like:
    - sjexvip.cc
    - sjexvip.cc/h5/ios
    - https://sjexvip.cc/h5/ios#/login
    """
    raw = (site_domain or "").strip()
    if not raw:
        return ""

    host_candidate = raw
    if "://" in raw:
        parsed = urlparse(raw)
        host_candidate = parsed.netloc or parsed.path

    host_candidate = host_candidate.split("#", 1)[0].split("?", 1)[0].strip().strip("/")
    if "/" in host_candidate:
        host_candidate = host_candidate.split("/", 1)[0]

    return host_candidate


def build_login_url(site_domain: str) -> str:
    return URL_LOGIN.format(domain=normalize_site_domain(site_domain))


def build_transaction_url(site_domain: str) -> str:
    return URL_TRANSACTION.format(domain=normalize_site_domain(site_domain))


def build_assets_url(site_domain: str) -> str:
    return URL_ASSETS.format(domain=normalize_site_domain(site_domain))

# Screenshots directory
SCREENSHOT_DIR = "screenshots"
