"""
Orbi (orbi.kr) scraper.
Primarily CSAT community, LEET filtering critical.
Server-side rendered, requests+BS4 should work.
"""

import time
import logging
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from scraper.base import BaseScraper, ScrapedPost, random_delay
from config import (
    ORBI_ID,
    ORBI_PW,
    ORBI_SELECTORS as SEL,
    DELAY_BETWEEN_PAGES,
)

logger = logging.getLogger(__name__)

SEARCH_URL = "https://orbi.kr/search?q={query}&page={page}"
POST_BASE = "https://orbi.kr"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://orbi.kr/",
}


class OrbiScraper(BaseScraper):
    def __init__(self, config, driver_manager):
        super().__init__(config, driver_manager)
        self.platform_name = "orbi"
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.use_selenium = False

    def login(self) -> bool:
        """Login to Orbi (optional, most posts are public)."""
        if not ORBI_ID or not ORBI_PW:
            logger.info("  No Orbi credentials, using public access")
            return True

        try:
            login_url = "https://orbi.kr/login"
            resp = self.session.get(login_url, timeout=10)

            # Extract CSRF token if present
            soup = BeautifulSoup(resp.text, "html.parser")
            csrf = soup.select_one("input[name='_token']")
            token = csrf.get("value", "") if csrf else ""

            login_data = {
                "email": ORBI_ID,
                "password": ORBI_PW,
                "_token": token,
            }
            resp = self.session.post(
                "https://orbi.kr/login",
                data=login_data,
                timeout=15,
                allow_redirects=True,
            )

            if resp.status_code == 200 and "logout" in resp.text.lower():
                logger.info("  Orbi login successful")
                return True
            else:
                logger.warning("  Orbi login may have failed, continuing with public access")
                return True

        except Exception as e:
            logger.warning(f"  Orbi login failed: {e}, continuing with public access")
            return True

    def search(self, keyword: str, max_pages: int) -> list[ScrapedPost]:
        """Search Orbi for keyword."""
        results = []
        encoded = quote_plus(keyword)

        for page in range(1, max_pages + 1):
            try:
                url = SEARCH_URL.format(query=encoded, page=page)
                resp = self.session.get(url, timeout=15)

                if resp.status_code != 200:
                    logger.warning(f"    Page {page}: HTTP {resp.status_code}")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                # Try multiple selectors for search results
                items = soup.select(SEL["search_item"])
                if not items:
                    items = soup.select("div.list-item, article.post-item, div.board-list-item")
                if not items:
                    # Fallback: try Selenium
                    if not self.use_selenium:
                        items_sel = self._search_selenium(keyword, page)
                        if items_sel:
                            results.extend(items_sel)
                            self.use_selenium = True
                            continue
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

    def _search_selenium(self, keyword: str, page: int) -> list[ScrapedPost]:
        """Fallback: search using Selenium for JS-rendered content."""
        try:
            driver = self.driver_manager.get_driver()
            encoded = quote_plus(keyword)
            url = SEARCH_URL.format(query=encoded, page=page)
            driver.get(url)
            time.sleep(4)

            from selenium.webdriver.common.by import By

            items = driver.find_elements(
                By.CSS_SELECTOR,
                "div.search-result-item, div.list-item, article.post-item"
            )
            results = []
            for item in items:
                try:
                    title_el = item.find_element(By.CSS_SELECTOR, "a")
                    title = title_el.text.strip()
                    href = title_el.get_attribute("href") or ""
                    post_id = href.rstrip("/").split("/")[-1] if href else ""

                    results.append(ScrapedPost(
                        post_id=f"orbi_{post_id}",
                        platform="orbi",
                        board_name="오르비",
                        title=title,
                        url=href,
                    ))
                except Exception:
                    continue
            return results
        except Exception as e:
            logger.debug(f"Selenium fallback failed: {e}")
            return []

    def _parse_search_item(self, item) -> ScrapedPost | None:
        """Parse a search result item from BeautifulSoup."""
        try:
            # Title and URL
            title_el = item.select_one(SEL["title"])
            if not title_el:
                title_el = item.select_one("a")
            if not title_el:
                return None

            title = title_el.text.strip()
            href = title_el.get("href", "")
            if href and not href.startswith("http"):
                href = POST_BASE + href

            post_id = href.rstrip("/").split("/")[-1] if href else ""

            # Author
            author_el = item.select_one(SEL["author"])
            if not author_el:
                author_el = item.select_one("span.nickname, span.user-name")
            author = author_el.text.strip() if author_el else ""

            # Date
            date_el = item.select_one(SEL["date"])
            if not date_el:
                date_el = item.select_one("time, span.time, span.created")
            date = date_el.text.strip() if date_el else ""

            # Preview
            preview_el = item.select_one("p.preview, div.content-preview, p.desc")
            preview = preview_el.text.strip()[:300] if preview_el else ""

            if not title:
                return None

            return ScrapedPost(
                post_id=f"orbi_{post_id}",
                platform="orbi",
                board_name="오르비",
                title=title,
                author=author,
                date=date,
                url=href,
                preview=preview,
            )
        except Exception:
            return None

    def fetch_content(self, url: str) -> str | None:
        """Fetch full body text of an Orbi post."""
        if not url:
            return None

        # Try requests first
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                return self._fetch_selenium(url)

            soup = BeautifulSoup(resp.text, "html.parser")

            for selector in [SEL["post_content"], SEL["post_content_alt"],
                             "div.content-area", "div.fr-view",
                             "div.post-content", "article"]:
                el = soup.select_one(selector)
                if el:
                    for tag in el.select("script, style, .ad"):
                        tag.decompose()
                    text = el.get_text(separator="\n", strip=True)
                    if text:
                        return text

            # Fallback to Selenium
            return self._fetch_selenium(url)

        except Exception:
            return self._fetch_selenium(url)

    def _fetch_selenium(self, url: str) -> str | None:
        """Fetch post content using Selenium."""
        try:
            driver = self.driver_manager.get_driver()
            driver.get(url)
            time.sleep(3)

            from selenium.webdriver.common.by import By

            for selector in ["div.content-area", "div.fr-view",
                             "div.post-content", "article"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, selector)
                    text = el.text.strip()
                    if text:
                        return text
                except Exception:
                    continue
            return None
        except Exception as e:
            logger.debug(f"Selenium fetch failed for {url}: {e}")
            return None
