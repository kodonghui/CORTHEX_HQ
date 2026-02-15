"""
DCInside (dcinside.com) scraper.
No login required. Heavy ad filtering needed.
"""

import time
import logging
import random
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from scraper.base import BaseScraper, ScrapedPost, random_delay
from config import (
    DCINSIDE_SELECTORS as SEL,
    DCINSIDE_GALLERIES,
    DELAY_BETWEEN_PAGES,
)

logger = logging.getLogger(__name__)

SEARCH_URL = "https://search.dcinside.com/post/p/{page}/sort/accuracy/q/{query}"
GALLERY_SEARCH_URL = (
    "https://gall.dcinside.com/mgallery/board/lists?"
    "id={gallery_id}&s_type=search_subject_memo&s_keyword={query}&page={page}"
)
POST_URL = "https://gall.dcinside.com/mgallery/board/view/?id={gallery_id}&no={post_no}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.dcinside.com/",
}


class DCInsideScraper(BaseScraper):
    def __init__(self, config, driver_manager):
        super().__init__(config, driver_manager)
        self.platform_name = "dcinside"
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.active_gallery = None

    def login(self) -> bool:
        """No login required for DCInside."""
        logger.info("  No login required")
        self._detect_gallery()
        return True

    def _detect_gallery(self):
        """Find which gallery ID actually exists."""
        for gallery_id, gallery_name in DCINSIDE_GALLERIES:
            try:
                url = f"https://gall.dcinside.com/mgallery/board/lists?id={gallery_id}"
                resp = self.session.get(url, timeout=10)
                if resp.status_code == 200 and "갤러리" in resp.text:
                    self.active_gallery = (gallery_id, gallery_name)
                    logger.info(f"  Active gallery found: {gallery_name} ({gallery_id})")
                    return
            except Exception:
                continue

        logger.info("  No specific gallery found, will use integrated search")
        self.active_gallery = None

    def search(self, keyword: str, max_pages: int) -> list[ScrapedPost]:
        """Search DCInside for keyword."""
        if self.active_gallery:
            return self._search_gallery(keyword, max_pages)
        return self._search_integrated(keyword, max_pages)

    def _search_gallery(self, keyword: str, max_pages: int) -> list[ScrapedPost]:
        """Search within a specific gallery."""
        results = []
        gallery_id, gallery_name = self.active_gallery
        encoded = quote_plus(keyword)

        for page in range(1, max_pages + 1):
            try:
                url = GALLERY_SEARCH_URL.format(
                    gallery_id=gallery_id, query=encoded, page=page
                )
                resp = self.session.get(url, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"    Page {page}: HTTP {resp.status_code}")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                rows = soup.select(SEL["post_list_row"])

                if not rows:
                    logger.info(f"    Page {page}: no results, stopping")
                    break

                page_results = []
                for row in rows:
                    post = self._parse_gallery_row(row, gallery_id, gallery_name)
                    if post:
                        page_results.append(post)

                results.extend(page_results)
                logger.info(f"    Page {page}: {len(page_results)} posts collected")
                random_delay(*DELAY_BETWEEN_PAGES)

            except Exception as e:
                logger.warning(f"    Page {page} error: {e}")
                break

        return results

    def _search_integrated(self, keyword: str, max_pages: int) -> list[ScrapedPost]:
        """Search using DCInside integrated search."""
        results = []
        encoded = quote_plus(keyword)

        for page in range(1, max_pages + 1):
            try:
                url = SEARCH_URL.format(page=page, query=encoded)
                resp = self.session.get(url, timeout=15)
                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select("li.sch_result_item, div.search_result")

                if not items:
                    logger.info(f"    Page {page}: no results, stopping")
                    break

                page_results = []
                for item in items:
                    post = self._parse_search_item(item)
                    if post:
                        page_results.append(post)

                results.extend(page_results)
                logger.info(f"    Page {page}: {len(page_results)} posts collected")
                random_delay(*DELAY_BETWEEN_PAGES)

            except Exception as e:
                logger.warning(f"    Page {page} error: {e}")
                break

        return results

    def _parse_gallery_row(self, row, gallery_id: str, gallery_name: str) -> ScrapedPost | None:
        """Parse a gallery list row."""
        try:
            # Skip notice/ad rows
            row_class = row.get("class", [])
            if isinstance(row_class, list):
                row_class = " ".join(row_class)
            if "notice" in row_class:
                return None

            # Title
            title_el = row.select_one(SEL["title"])
            if not title_el:
                return None
            title = title_el.text.strip()
            href = title_el.get("href", "")

            # Extract post number
            post_no = ""
            if "no=" in href:
                post_no = href.split("no=")[-1].split("&")[0]
            elif href:
                post_no = href.rstrip("/").split("/")[-1]

            url = POST_URL.format(gallery_id=gallery_id, post_no=post_no)

            # Author
            try:
                author_el = row.select_one(SEL["author"])
                author = author_el.text.strip() if author_el else ""
            except Exception:
                author = ""

            # Date
            try:
                date_el = row.select_one(SEL["date"])
                date = date_el.get("title", date_el.text.strip()) if date_el else ""
            except Exception:
                date = ""

            # View count
            try:
                view_el = row.select_one(SEL["view_count"])
                view_count = int(view_el.text.strip()) if view_el else 0
            except (ValueError, AttributeError):
                view_count = 0

            if not title:
                return None

            return ScrapedPost(
                post_id=f"dc_{gallery_id}_{post_no}",
                platform="dcinside",
                board_name=gallery_name,
                title=title,
                author=author,
                date=date,
                view_count=view_count,
                url=url,
            )
        except Exception:
            return None

    def _parse_search_item(self, item) -> ScrapedPost | None:
        """Parse integrated search result."""
        try:
            title_el = item.select_one("a.tit_txt, a")
            if not title_el:
                return None
            title = title_el.text.strip()
            url = title_el.get("href", "")

            post_id = url.rstrip("/").split("/")[-1] if url else str(random.randint(10000, 99999))

            author = ""
            date = ""
            preview = ""

            auth_el = item.select_one("span.author, span.writer")
            if auth_el:
                author = auth_el.text.strip()
            date_el = item.select_one("span.date, span.time")
            if date_el:
                date = date_el.text.strip()
            preview_el = item.select_one("p.txt, div.dsc")
            if preview_el:
                preview = preview_el.text.strip()[:300]

            return ScrapedPost(
                post_id=f"dc_search_{post_id}",
                platform="dcinside",
                board_name="통합검색",
                title=title,
                author=author,
                date=date,
                url=url,
                preview=preview,
            )
        except Exception:
            return None

    def fetch_content(self, url: str) -> str | None:
        """Fetch full body text of a DCInside post."""
        if not url:
            return None

        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")

            # Try multiple content selectors
            for selector in [SEL["post_content"], SEL["post_content_alt"],
                             "div.write_div", "div.writing_view_box"]:
                el = soup.select_one(selector)
                if el:
                    # Remove script/style/ad elements
                    for tag in el.select("script, style, .ad_wrap, .adv_box"):
                        tag.decompose()
                    text = el.get_text(separator="\n", strip=True)
                    if text:
                        return text

            return None

        except Exception as e:
            logger.debug(f"Fetch failed for {url}: {e}")
            return None
