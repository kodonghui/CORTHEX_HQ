"""
SNS 퍼블리셔용 Selenium 브라우저 유틸리티.

Selenium 기반 퍼블리셔들이 공유하는 브라우저 관리, 로그인, 안티-디텍션 기능.
leet-opinion-scraper/utils/browser.py 패턴을 기반으로 독립적으로 구현.
"""
from __future__ import annotations

import asyncio
import logging
import os
import pickle
import random
import time
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger("corthex.sns.browser")

COOKIE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "sns_cookies"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def random_delay(low: float = 1.0, high: float = 3.0) -> None:
    """Rate-limiting용 랜덤 지연."""
    time.sleep(random.uniform(low, high))


class SNSBrowserManager:
    """Selenium WebDriver 관리자 (안티디텍션 포함)."""

    def __init__(self, headless: bool = True) -> None:
        self.headless = headless
        self._driver: webdriver.Chrome | None = None

    @property
    def driver(self) -> webdriver.Chrome:
        if self._driver is None:
            self._init_driver()
        return self._driver

    def _init_driver(self) -> None:
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument(f"--user-agent={DEFAULT_USER_AGENT}")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        self._driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options,
        )

        # navigator.webdriver 플래그 제거
        self._driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
        self._driver.implicitly_wait(5)
        logger.debug("SNS ChromeDriver 초기화 완료")

    def save_cookies(self, name: str) -> None:
        """세션 쿠키 저장. name: 'naver', 'kakao' 등."""
        COOKIE_DIR.mkdir(parents=True, exist_ok=True)
        path = COOKIE_DIR / f"{name}_cookies.pkl"
        with open(path, "wb") as f:
            pickle.dump(self._driver.get_cookies(), f)
        logger.debug("쿠키 저장: %s", path)

    def load_cookies(self, name: str) -> bool:
        """저장된 쿠키 로드. 성공 시 True."""
        path = COOKIE_DIR / f"{name}_cookies.pkl"
        if not path.exists():
            return False
        try:
            with open(path, "rb") as f:
                cookies = pickle.load(f)
            for cookie in cookies:
                cookie.pop("sameSite", None)
                cookie.pop("expiry", None)
                try:
                    self._driver.add_cookie(cookie)
                except Exception:
                    pass
            logger.debug("쿠키 로드 성공: %s", path)
            return True
        except Exception as e:
            logger.warning("쿠키 로드 실패 (%s): %s", path, e)
            return False

    def quit(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
            logger.debug("SNS ChromeDriver 종료")
