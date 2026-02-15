"""
Daum Cafe (서로연: cafe.daum.net/snuleet) scraper.
Requires Kakao login. Content is inside iframe.
"""

import time
import logging
from urllib.parse import quote_plus

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)

from scraper.base import BaseScraper, ScrapedPost, random_delay
from config import (
    KAKAO_ID,
    KAKAO_PW,
    DAUM_COOKIE_PATH,
    DAUM_CAFE_SELECTORS as SEL,
    DELAY_BETWEEN_PAGES,
)

logger = logging.getLogger(__name__)

CAFE_ID = "snuleet"
CAFE_BASE = f"https://cafe.daum.net/{CAFE_ID}"
SEARCH_URL = f"https://cafe.daum.net/_search?cafe_id={CAFE_ID}&search_type=post&query="


class DaumCafeScraper(BaseScraper):
    def __init__(self, config, driver_manager):
        super().__init__(config, driver_manager)
        self.platform_name = "daum_cafe"

    def login(self) -> bool:
        """Login via Kakao account."""
        if not KAKAO_ID or not KAKAO_PW:
            logger.warning("KAKAO_ID/KAKAO_PW not set. Attempting without login.")
            return True

        driver = self.driver_manager.get_driver()

        # Try loading saved cookies first
        driver.get(CAFE_BASE)
        time.sleep(2)
        if self.driver_manager.load_cookies(DAUM_COOKIE_PATH):
            driver.refresh()
            time.sleep(3)
            if self._is_logged_in(driver):
                logger.info("  Login successful (from cookies)")
                return True

        # Perform fresh login
        try:
            driver.get("https://accounts.kakao.com/login/?continue=https://cafe.daum.net/")
            time.sleep(3)

            wait = WebDriverWait(driver, 15)

            # Enter credentials
            id_input = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='loginId'], input#loginId"))
            )
            id_input.clear()
            id_input.send_keys(KAKAO_ID)

            pw_input = driver.find_element(By.CSS_SELECTOR, "input[name='password'], input#password")
            pw_input.clear()
            pw_input.send_keys(KAKAO_PW)

            # Click login button
            login_btn = driver.find_element(
                By.CSS_SELECTOR, "button[type='submit'], button.btn_confirm"
            )
            login_btn.click()
            time.sleep(5)

            # Verify login
            driver.get(CAFE_BASE)
            time.sleep(3)

            if self._is_logged_in(driver):
                self.driver_manager.save_cookies(DAUM_COOKIE_PATH)
                logger.info("  Login successful")
                return True
            else:
                logger.warning("  Login may have failed, continuing anyway")
                return True

        except Exception as e:
            logger.error(f"  Kakao login failed: {e}")
            return False

    def _is_logged_in(self, driver) -> bool:
        """Check if currently logged in to Daum Cafe."""
        try:
            page_src = driver.page_source
            return "로그인" not in page_src[:2000] or "로그아웃" in page_src
        except Exception:
            return False

    def search(self, keyword: str, max_pages: int) -> list[ScrapedPost]:
        """Search cafe with keyword."""
        driver = self.driver_manager.get_driver()
        results = []
        encoded = quote_plus(keyword)

        for page in range(1, max_pages + 1):
            try:
                url = f"{SEARCH_URL}{encoded}&page={page}"
                driver.get(url)
                time.sleep(3)

                # Try to switch to iframe
                try:
                    driver.switch_to.frame(SEL["iframe_id"])
                except Exception:
                    pass

                items = driver.find_elements(By.CSS_SELECTOR, SEL["search_result_item"])
                if not items:
                    # Try alternate selectors
                    items = driver.find_elements(By.CSS_SELECTOR, "li.cont_item, div.search_item")

                if not items:
                    logger.info(f"    Page {page}: no results, stopping")
                    driver.switch_to.default_content()
                    break

                page_results = []
                for item in items:
                    try:
                        post = self._parse_search_item(item)
                        if post:
                            page_results.append(post)
                    except Exception as e:
                        logger.debug(f"    Failed to parse item: {e}")

                results.extend(page_results)
                logger.info(f"    Page {page}: {len(page_results)} posts collected")

                driver.switch_to.default_content()
                random_delay(*DELAY_BETWEEN_PAGES)

            except Exception as e:
                logger.warning(f"    Page {page} error: {e}")
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
                break

        return results

    def _parse_search_item(self, item) -> ScrapedPost | None:
        """Parse a single search result item into ScrapedPost."""
        try:
            # Title and URL
            link_el = item.find_element(By.CSS_SELECTOR, SEL["title_link"])
            title = link_el.text.strip()
            url = link_el.get_attribute("href") or ""

            # Extract post_id from URL
            post_id = url.rstrip("/").split("/")[-1] if url else ""

            # Author
            try:
                author = item.find_element(By.CSS_SELECTOR, SEL["author"]).text.strip()
            except NoSuchElementException:
                author = ""

            # Date
            try:
                date = item.find_element(By.CSS_SELECTOR, SEL["date"]).text.strip()
            except NoSuchElementException:
                date = ""

            # Preview
            try:
                preview = item.find_element(By.CSS_SELECTOR, SEL["preview"]).text.strip()
            except NoSuchElementException:
                preview = ""

            if not title:
                return None

            return ScrapedPost(
                post_id=f"daum_{post_id}",
                platform="daum_cafe",
                board_name="서로연",
                title=title,
                author=author,
                date=date,
                url=url,
                preview=preview[:300],
            )
        except Exception:
            return None

    def fetch_content(self, url: str) -> str | None:
        """Fetch full body text of a single Daum Cafe post."""
        if not url:
            return None

        driver = self.driver_manager.get_driver()
        try:
            driver.get(url)
            time.sleep(3)

            # Switch to content iframe
            try:
                driver.switch_to.frame(SEL["iframe_id"])
            except Exception:
                pass

            # Try multiple selectors for post content
            content = None
            for selector in [SEL["post_content"], "div#article_content", "div.article_view",
                             "div.content_article", "div#daumWrap"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, selector)
                    content = el.text.strip()
                    if content:
                        break
                except NoSuchElementException:
                    continue

            driver.switch_to.default_content()
            return content

        except Exception as e:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            raise e
