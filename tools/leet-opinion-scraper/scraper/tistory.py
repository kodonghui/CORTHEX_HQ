"""
Tistory (tistory.com) scraper.
No login required. Uses Daum search blog tab.
Every Tistory blog has different HTML structure.
"""

import time
import logging
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from scraper.base import BaseScraper, ScrapedPost, random_delay
from config import (
    TISTORY_SELECTORS as SEL,
    DELAY_BETWEEN_PAGES,
)

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://search.daum.net/search?"
    "w=blog&q={query}&p={page}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.daum.net/",
}


class TistoryScraper(BaseScraper):
    def __init__(self, config, driver_manager):
        super().__init__(config, driver_manager)
        self.platform_name = "tistory"
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def login(self) -> bool:
        """No login required for Tistory."""
        logger.info("  No login required")
        return True

    def search(self, keyword: str, max_pages: int) -> list[ScrapedPost]:
        """Search Daum blog tab for Tistory posts."""
        results = []
        query = f"site:tistory.com {keyword} LEET 해설"
        encoded = quote_plus(query)

        for page in range(1, max_pages + 1):
            try:
                url = SEARCH_URL.format(query=encoded, page=page)
                resp = self.session.get(url, timeout=15)

                if resp.status_code != 200:
                    logger.warning(f"    Page {page}: HTTP {resp.status_code}")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                items = soup.select(SEL["search_item"])
                if not items:
                    items = soup.select("div.cont_inner, div.c-item-doc, li.fst")
                if not items:
                    logger.info(f"    Page {page}: no results, stopping")
                    break

                page_results = []
                for item in items:
                    post = self._parse_search_item(item)
                    if post:
                        # Only include tistory.com URLs
                        if "tistory.com" in post.url:
                            page_results.append(post)

                if not page_results:
                    logger.info(f"    Page {page}: no Tistory results, stopping")
                    break

                results.extend(page_results)
                logger.info(f"    Page {page}: {len(page_results)} posts collected")
                random_delay(*DELAY_BETWEEN_PAGES)

            except Exception as e:
                logger.warning(f"    Page {page} error: {e}")
                break

        return results

    def _parse_search_item(self, item) -> ScrapedPost | None:
        """Parse a Daum search result item."""
        try:
            # Title and URL
            title_el = item.select_one(SEL["title"])
            if not title_el:
                title_el = item.select_one("a.f_link_b, a.tit_main, a")
            if not title_el:
                return None

            title = title_el.text.strip()
            url = title_el.get("href", "")

            # Generate post_id from URL
            post_id = ""
            if "tistory.com" in url:
                parts = url.rstrip("/").split("/")
                blog_name = ""
                post_no = parts[-1] if parts else ""
                for p in parts:
                    if "tistory.com" in p:
                        blog_name = p.replace(".tistory.com", "")
                        break
                post_id = f"tistory_{blog_name}_{post_no}"
            else:
                post_id = f"tistory_{abs(hash(url)) % 10**8}"

            # Author
            author_el = item.select_one(SEL["author"])
            if not author_el:
                author_el = item.select_one("span.f_nb, span.author, a.f_nb")
            author = author_el.text.strip() if author_el else ""

            # Date
            date_el = item.select_one(SEL["date"])
            if not date_el:
                date_el = item.select_one("span.date, span.f_eb")
            date = date_el.text.strip() if date_el else ""

            # Preview
            preview_el = item.select_one(SEL["preview"])
            if not preview_el:
                preview_el = item.select_one("p.f_eb.desc, p.desc, div.desc")
            preview = preview_el.text.strip()[:300] if preview_el else ""

            if not title:
                return None

            return ScrapedPost(
                post_id=post_id,
                platform="tistory",
                board_name="티스토리",
                title=title,
                author=author,
                date=date,
                url=url,
                preview=preview,
            )
        except Exception:
            return None

    def fetch_content(self, url: str) -> str | None:
        """Fetch full body text of a Tistory post.
        Uses multiple CSS selectors due to varying Tistory skins.
        """
        if not url:
            return None

        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                return self._fetch_selenium(url)

            soup = BeautifulSoup(resp.text, "html.parser")

            # Try each content selector in order
            for selector in SEL["content_selectors"]:
                el = soup.select_one(selector)
                if el:
                    for tag in el.select("script, style, .another_category, .container_postbtn"):
                        tag.decompose()
                    text = el.get_text(separator="\n", strip=True)
                    if text and len(text) > 50:
                        return text

            # Last resort: try body with cleanup
            body = soup.select_one("body")
            if body:
                for tag in body.select(
                    "script, style, header, footer, nav, aside, "
                    ".sidebar, .comment, .reply, #comment, .ad"
                ):
                    tag.decompose()
                text = body.get_text(separator="\n", strip=True)
                if text and len(text) > 100:
                    return text[:5000]

            return self._fetch_selenium(url)

        except Exception:
            return self._fetch_selenium(url)

    def _fetch_selenium(self, url: str) -> str | None:
        """Fallback: fetch using Selenium."""
        try:
            driver = self.driver_manager.get_driver()
            driver.get(url)
            time.sleep(3)

            from selenium.webdriver.common.by import By

            for selector in SEL["content_selectors"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, selector)
                    text = el.text.strip()
                    if text and len(text) > 50:
                        return text
                except Exception:
                    continue

            # Try article or main content area
            for selector in ["article", "main", "div.post"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, selector)
                    text = el.text.strip()
                    if text and len(text) > 100:
                        return text[:5000]
                except Exception:
                    continue

            return None

        except Exception as e:
            logger.debug(f"Selenium fetch failed for {url}: {e}")
            return None
