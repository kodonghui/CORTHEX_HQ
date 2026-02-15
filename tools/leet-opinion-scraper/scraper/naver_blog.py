"""
Naver Blog scraper.
No login required. Uses Naver search blog tab.
Blog content may be in iframe; use mobile URL to avoid.
"""

import re
import time
import logging
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from scraper.base import BaseScraper, ScrapedPost, random_delay
from config import (
    NAVER_BLOG_SELECTORS as SEL,
    DELAY_BETWEEN_PAGES,
)

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://search.naver.com/search.naver?"
    "where=blog&query={query}&start={start}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.naver.com/",
}


class NaverBlogScraper(BaseScraper):
    def __init__(self, config, driver_manager):
        super().__init__(config, driver_manager)
        self.platform_name = "naver_blog"
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def login(self) -> bool:
        """No login required for Naver Blog search."""
        logger.info("  No login required")
        return True

    def search(self, keyword: str, max_pages: int) -> list[ScrapedPost]:
        """Search Naver blog tab."""
        results = []
        query = f"{keyword} LEET 해설"
        encoded = quote_plus(query)

        for page in range(1, max_pages + 1):
            try:
                start = (page - 1) * 10 + 1
                url = SEARCH_URL.format(query=encoded, start=start)
                resp = self.session.get(url, timeout=15)

                if resp.status_code != 200:
                    logger.warning(f"    Page {page}: HTTP {resp.status_code}")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                items = soup.select(SEL["search_result"])
                if not items:
                    items = soup.select("li.bx, div.api_txt_lines")
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
        """Parse a Naver blog search result item."""
        try:
            # Title and URL
            title_el = item.select_one(SEL["title"])
            if not title_el:
                title_el = item.select_one("a.api_txt_lines, a.title_link, a")
            if not title_el:
                return None

            title = title_el.text.strip()
            url = title_el.get("href", "")

            # Generate post_id from URL
            post_id = ""
            if "blog.naver.com" in url:
                parts = url.rstrip("/").split("/")
                post_id = f"nblog_{'_'.join(parts[-2:])}" if len(parts) >= 2 else url
            else:
                post_id = f"nblog_{abs(hash(url)) % 10**8}"

            # Author
            author_el = item.select_one(SEL["author"])
            if not author_el:
                author_el = item.select_one("a.sub_txt, span.author, a.name")
            author = author_el.text.strip() if author_el else ""

            # Date
            date_el = item.select_one(SEL["date"])
            if not date_el:
                date_el = item.select_one("span.sub_time, span.date, span.time")
            date = date_el.text.strip() if date_el else ""

            # Preview
            preview_el = item.select_one(SEL["preview"])
            if not preview_el:
                preview_el = item.select_one("div.api_txt_lines.dsc_txt, p.desc, div.dsc_txt")
            preview = preview_el.text.strip()[:300] if preview_el else ""

            if not title:
                return None

            return ScrapedPost(
                post_id=post_id,
                platform="naver_blog",
                board_name="네이버 블로그",
                title=title,
                author=author,
                date=date,
                url=url,
                preview=preview,
            )
        except Exception:
            return None

    def fetch_content(self, url: str) -> str | None:
        """Fetch full body text of a Naver Blog post. Uses mobile URL."""
        if not url:
            return None

        # Convert to mobile URL to avoid iframe
        mobile_url = self._to_mobile_url(url)

        try:
            resp = self.session.get(mobile_url, timeout=15)
            if resp.status_code != 200:
                return self._fetch_selenium(url)

            soup = BeautifulSoup(resp.text, "html.parser")

            for selector in [SEL["post_content"], SEL["post_content_old"],
                             "div.se-main-container", "div#postViewArea",
                             "div.__se_component_area", "div.post_ct"]:
                el = soup.select_one(selector)
                if el:
                    for tag in el.select("script, style"):
                        tag.decompose()
                    text = el.get_text(separator="\n", strip=True)
                    if text:
                        return text

            return self._fetch_selenium(url)

        except Exception:
            return self._fetch_selenium(url)

    def _to_mobile_url(self, url: str) -> str:
        """Convert desktop Naver blog URL to mobile URL."""
        # blog.naver.com/blogid/postno -> m.blog.naver.com/blogid/postno
        if "blog.naver.com" in url and "m.blog.naver.com" not in url:
            return url.replace("blog.naver.com", "m.blog.naver.com")
        # PostView.naver?blogId=xxx&logNo=yyy -> m.blog.naver.com/xxx/yyy
        match = re.search(r"blogId=([^&]+).*logNo=(\d+)", url)
        if match:
            return f"https://m.blog.naver.com/{match.group(1)}/{match.group(2)}"
        return url

    def _fetch_selenium(self, url: str) -> str | None:
        """Fallback: fetch using Selenium with iframe handling."""
        try:
            driver = self.driver_manager.get_driver()
            mobile_url = self._to_mobile_url(url)
            driver.get(mobile_url)
            time.sleep(3)

            from selenium.webdriver.common.by import By

            for selector in ["div.se-main-container", "div#postViewArea",
                             "div.post_ct", "div.__se_component_area"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, selector)
                    text = el.text.strip()
                    if text:
                        return text
                except Exception:
                    continue

            # Try iframe approach on desktop URL
            driver.get(url)
            time.sleep(3)
            try:
                driver.switch_to.frame("mainFrame")
                for selector in ["div.se-main-container", "div#postViewArea"]:
                    try:
                        el = driver.find_element(By.CSS_SELECTOR, selector)
                        text = el.text.strip()
                        if text:
                            driver.switch_to.default_content()
                            return text
                    except Exception:
                        continue
                driver.switch_to.default_content()
            except Exception:
                pass

            return None

        except Exception as e:
            logger.debug(f"Selenium fetch failed for {url}: {e}")
            return None
