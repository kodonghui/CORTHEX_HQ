"""
BaseScraper abstract class and ScrapedPost data model.
"""

import time
import random
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from config import (
    AD_TITLE_KEYWORDS,
    AD_AUTHOR_PATTERNS,
    NEGATIVE_PATTERNS,
    LEET_CONTEXT_KEYWORDS,
    DELAY_BETWEEN_SEARCHES,
    DELAY_BETWEEN_POSTS,
)
from utils.storage import save_intermediate_batch

logger = logging.getLogger(__name__)


def random_delay(low: float, high: float):
    """Sleep for a random duration between low and high seconds."""
    delay = random.uniform(low, high)
    time.sleep(delay)


@dataclass
class ScrapedPost:
    post_id: str = ""
    platform: str = ""
    board_name: str = ""
    title: str = ""
    author: str = ""
    date: str = ""
    view_count: int = 0
    url: str = ""
    preview: str = ""
    full_content: str = ""
    search_keywords: list[str] = field(default_factory=list)
    matched_negative: list[str] = field(default_factory=list)
    is_negative: bool = False


class BaseScraper(ABC):
    """Parent class for all platform scrapers."""

    def __init__(self, config, driver_manager):
        self.config = config
        self.driver_manager = driver_manager
        self.collected_posts: dict[str, ScrapedPost] = {}
        self.platform_name: str = ""
        self.output_dir: str = "./output"

    @abstractmethod
    def login(self) -> bool:
        """Perform login. Return True if login not needed or successful."""
        pass

    @abstractmethod
    def search(self, keyword: str, max_pages: int) -> list[ScrapedPost]:
        """Search with keyword, return list of ScrapedPost results."""
        pass

    @abstractmethod
    def fetch_content(self, url: str) -> str | None:
        """Fetch full body text of a single post."""
        pass

    def run(self, keywords: list[str], max_pages: int, keywords_only: bool):
        """Full collection process."""
        # Step 1: Login
        if not self.login():
            logger.error(f"{self.platform_name} login failed. Skipping.")
            return

        # Step 2: Search all keywords
        for i, keyword in enumerate(keywords, 1):
            logger.info(f"  [{i}/{len(keywords)}] Keyword: \"{keyword}\"")
            try:
                results = self.search(keyword, max_pages)
                self._merge_results(results, keyword)
            except Exception as e:
                logger.warning(f"  Search failed for \"{keyword}\": {e}")
            random_delay(*DELAY_BETWEEN_SEARCHES)

        logger.info(
            f"  Search complete: {len(self.collected_posts)} deduplicated posts"
        )

        # Step 3: Filter ads
        self._filter_ads()

        # Step 4: Fetch full content (unless --keywords-only)
        if not keywords_only:
            self._fetch_all_contents()

        # Step 5: Filter by negative patterns
        self._filter_negative()

        # Step 6: Filter by LEET relevance
        self._filter_leet_context()

        negative_count = sum(
            1 for p in self.collected_posts.values() if p.is_negative
        )
        logger.info(
            f"  {self.platform_name} complete: "
            f"{len(self.collected_posts)} posts, "
            f"{negative_count} negative"
        )

    def _merge_results(self, results: list[ScrapedPost], keyword: str):
        """Merge results, deduplicate by post_id, accumulate keywords."""
        for post in results:
            pid = post.post_id
            if not pid:
                continue
            if pid in self.collected_posts:
                existing = self.collected_posts[pid]
                if keyword not in existing.search_keywords:
                    existing.search_keywords.append(keyword)
            else:
                if keyword not in post.search_keywords:
                    post.search_keywords.append(keyword)
                self.collected_posts[pid] = post

    def _filter_ads(self):
        """Remove advertising / spam posts."""
        to_remove = []
        for pid, post in self.collected_posts.items():
            if any(kw in post.title for kw in AD_TITLE_KEYWORDS):
                to_remove.append(pid)
            elif any(pat in post.author for pat in AD_AUTHOR_PATTERNS):
                to_remove.append(pid)
        for pid in to_remove:
            del self.collected_posts[pid]
        if to_remove:
            logger.info(f"    Filtered {len(to_remove)} ad/spam posts")

    def _fetch_all_contents(self):
        """Fetch body text for all collected posts with delay."""
        posts = list(self.collected_posts.values())
        if not posts:
            return
        logger.info(f"  Fetching bodies ({len(posts)} posts)")
        for i, post in enumerate(posts, 1):
            logger.info(f"    [{i}/{len(posts)}] Fetching: {post.title[:40]}...")
            try:
                content = self.fetch_content(post.url)
            except Exception as e:
                logger.warning(f"    [{i}/{len(posts)}] Fetch failed: {e}")
                content = None

            if content:
                post.full_content = content
                post.preview = content[:300]
            else:
                post.full_content = ""
                if not post.preview:
                    post.preview = "(fetch failed)"

            random_delay(*DELAY_BETWEEN_POSTS)

            # Auto-save every 20 posts
            if i % 20 == 0:
                save_intermediate_batch(
                    posts[:i], self.platform_name, self.output_dir
                )
                logger.info(f"    Auto-saved ({i}/{len(posts)})")

    def _filter_negative(self):
        """Match negative expression patterns against body + title."""
        for post in self.collected_posts.values():
            text = f"{post.full_content or ''} {post.title or ''}"
            matched = [pat for pat in NEGATIVE_PATTERNS if pat in text]
            post.matched_negative = matched
            post.is_negative = len(matched) > 0

        negative_count = sum(
            1 for p in self.collected_posts.values() if p.is_negative
        )
        logger.info(
            f"    Negative filter: {negative_count}/{len(self.collected_posts)} posts matched"
        )

    def _filter_leet_context(self):
        """Remove posts not related to LEET."""
        to_remove = []
        for pid, post in self.collected_posts.items():
            text = f"{post.full_content or ''} {post.title or ''}"
            if not any(kw in text for kw in LEET_CONTEXT_KEYWORDS):
                to_remove.append(pid)
        for pid in to_remove:
            del self.collected_posts[pid]
        if to_remove:
            logger.info(f"    Removed {len(to_remove)} non-LEET posts")
