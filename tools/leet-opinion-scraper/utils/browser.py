"""
Shared Selenium WebDriver manager.
"""

import os
import pickle
import logging

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)


class BrowserManager:
    """Shared Selenium WebDriver manager with anti-detection."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.driver = None

    def get_driver(self) -> webdriver.Chrome:
        if self.driver is None:
            self._init_driver()
        return self.driver

    def _init_driver(self):
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options,
        )

        # Remove navigator.webdriver flag
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
        self.driver.implicitly_wait(5)
        logger.debug("ChromeDriver initialized successfully")

    def save_cookies(self, filepath: str):
        """Save current session cookies to file."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        cookies = self.driver.get_cookies()
        with open(filepath, "wb") as f:
            pickle.dump(cookies, f)
        logger.debug(f"Cookies saved to {filepath}")

    def load_cookies(self, filepath: str) -> bool:
        """Load cookies from file. Returns True if successful."""
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, "rb") as f:
                cookies = pickle.load(f)
            for cookie in cookies:
                cookie.pop("sameSite", None)
                cookie.pop("expiry", None)
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
                    pass
            logger.debug(f"Cookies loaded from {filepath}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load cookies from {filepath}: {e}")
            return False

    def restart_driver(self):
        """Restart driver (e.g. after session expiry)."""
        logger.info("Restarting WebDriver...")
        self.quit()
        self._init_driver()

    def quit(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            logger.debug("WebDriver closed")
