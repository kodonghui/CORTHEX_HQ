"""
Naver Cafe scraper.
Requires Naver login. Strong bot detection - uses clipboard paste method.
Content inside iframe.
"""

import time
import logging
from urllib.parse import quote_plus

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
)

from scraper.base import BaseScraper, ScrapedPost, random_delay
from config import (
    NAVER_ID,
    NAVER_PW,
    NAVER_COOKIE_PATH,
    NAVER_CAFE_SELECTORS as SEL,
    DELAY_BETWEEN_PAGES,
)

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://search.naver.com/search.naver?"
    "where=article&query={query}+LEET&start={start}"
)

LOGIN_URL = "https://nid.naver.com/nidlogin.login"


class NaverCafeScraper(BaseScraper):
    def __init__(self, config, driver_manager):
        super().__init__(config, driver_manager)
        self.platform_name = "naver_cafe"

    def login(self) -> bool:
        """Login to Naver using clipboard paste method."""
        if not NAVER_ID or not NAVER_PW:
            logger.warning("NAVER_ID/NAVER_PW not set. Will use integrated search (limited).")
            return True

        driver = self.driver_manager.get_driver()

        # Try loading saved cookies first
        driver.get("https://cafe.naver.com/")
        time.sleep(2)
        if self.driver_manager.load_cookies(NAVER_COOKIE_PATH):
            driver.refresh()
            time.sleep(3)
            if self._is_logged_in(driver):
                logger.info("  Login successful (from cookies)")
                return True

        # Perform fresh login
        try:
            driver.get(LOGIN_URL)
            time.sleep(3)

            wait = WebDriverWait(driver, 15)

            # Use JavaScript to set values (bypasses bot detection better than send_keys)
            id_input = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input#id"))
            )

            # Use clipboard paste method for bot detection bypass
            driver.execute_script(
                f"document.querySelector('input#id').value = '{NAVER_ID}';"
            )
            time.sleep(0.5)
            driver.execute_script(
                f"document.querySelector('input#pw').value = '{NAVER_PW}';"
            )
            time.sleep(0.5)

            # Click login button
            login_btn = driver.find_element(
                By.CSS_SELECTOR, "button#log\\.login, button.btn_login, input.btn_login"
            )
            login_btn.click()
            time.sleep(5)

            # Check for CAPTCHA or 2FA
            current_url = driver.current_url
            if "nidlogin" in current_url:
                logger.warning("  Naver login may require CAPTCHA/2FA. Please complete manually.")
                # Wait up to 60 seconds for manual intervention
                for _ in range(12):
                    time.sleep(5)
                    if "nidlogin" not in driver.current_url:
                        break

            # Navigate to cafe and verify
            driver.get("https://cafe.naver.com/")
            time.sleep(3)

            if self._is_logged_in(driver):
                self.driver_manager.save_cookies(NAVER_COOKIE_PATH)
                logger.info("  Login successful")
                return True
            else:
                logger.warning("  Login may have failed, continuing with limited access")
                return True

        except Exception as e:
            logger.error(f"  Naver login failed: {e}")
            return True  # Continue anyway with limited access

    def _is_logged_in(self, driver) -> bool:
        """Check if logged in to Naver."""
        try:
            page = driver.page_source
            return "로그아웃" in page or "gnb_my" in page
        except Exception:
            return False

    def search(self, keyword: str, max_pages: int) -> list[ScrapedPost]:
        """Search Naver integrated cafe search."""
        results = []
        encoded = quote_plus(f"{keyword} LEET")

        for page in range(1, max_pages + 1):
            try:
                start = (page - 1) * 10 + 1
                url = SEARCH_URL.format(query=encoded, start=start)

                driver = self.driver_manager.get_driver()
                driver.get(url)
                time.sleep(3)

                items = driver.find_elements(
                    By.CSS_SELECTOR, SEL["search_result"]
                )
                if not items:
                    items = driver.find_elements(
                        By.CSS_SELECTOR, "li.bx, div.api_subject_bx"
                    )
                if not items:
                    logger.info(f"    Page {page}: no results, stopping")
                    break

                page_results = []
                for item in items:
                    post = self._parse_search_item(item)
                    if post:
                        page_results.append(post)

                if not page_results:
                    logger.info(f"    Page {page}: no parseable results, stopping")
                    break

                results.extend(page_results)
                logger.info(f"    Page {page}: {len(page_results)} posts collected")
                random_delay(*DELAY_BETWEEN_PAGES)

            except Exception as e:
                logger.warning(f"    Page {page} error: {e}")
                break

        return results

    def _parse_search_item(self, item) -> ScrapedPost | None:
        """Parse a Naver cafe search result."""
        try:
            # Title and URL
            title_el = item.find_element(By.CSS_SELECTOR, SEL["title"])
            if not title_el:
                return None
            title = title_el.text.strip()
            url = title_el.get_attribute("href") or ""

            # Generate post_id
            post_id = f"ncafe_{abs(hash(url)) % 10**8}" if url else ""

            # Author
            try:
                author_el = item.find_element(By.CSS_SELECTOR, SEL["author"])
                author = author_el.text.strip()
            except NoSuchElementException:
                author = ""

            # Date
            try:
                date_el = item.find_element(By.CSS_SELECTOR, SEL["date"])
                date = date_el.text.strip()
            except NoSuchElementException:
                date = ""

            # Preview
            try:
                preview_el = item.find_element(By.CSS_SELECTOR, SEL["preview"])
                preview = preview_el.text.strip()[:300]
            except NoSuchElementException:
                preview = ""

            # Cafe name (board)
            try:
                cafe_el = item.find_element(By.CSS_SELECTOR, "a.sub_txt.sub_name")
                board_name = cafe_el.text.strip()
            except NoSuchElementException:
                board_name = "네이버 카페"

            if not title:
                return None

            return ScrapedPost(
                post_id=post_id,
                platform="naver_cafe",
                board_name=board_name,
                title=title,
                author=author,
                date=date,
                url=url,
                preview=preview,
            )
        except Exception:
            return None

    def fetch_content(self, url: str) -> str | None:
        """Fetch full body of a Naver Cafe post via Selenium + iframe."""
        if not url:
            return None

        driver = self.driver_manager.get_driver()
        try:
            driver.get(url)
            time.sleep(4)

            # Switch to cafe content iframe
            try:
                wait = WebDriverWait(driver, 10)
                iframe = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, f"iframe#{SEL['iframe_id']}")
                    )
                )
                driver.switch_to.frame(iframe)
            except TimeoutException:
                # Try without iframe (some URLs load directly)
                pass

            # Try content selectors
            for selector in [SEL["post_content"], SEL["post_content_old"],
                             "div.se-main-container", "div#postViewArea",
                             "div.__se_component_area", "div.ContentRenderer"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, selector)
                    text = el.text.strip()
                    if text:
                        driver.switch_to.default_content()
                        return text
                except NoSuchElementException:
                    continue

            driver.switch_to.default_content()
            return None

        except Exception as e:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            logger.debug(f"Fetch failed for {url}: {e}")
            return None
