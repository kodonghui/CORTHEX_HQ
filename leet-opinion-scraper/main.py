#!/usr/bin/env python3
"""
LEET Multi-Platform Negative Opinion Scraper
=============================================
Collects negative opinions about LEET exam answer explanations
from 6 major Korean online communities.

Usage:
    python main.py                                    # all platforms, full collection
    python main.py --platforms daum_cafe,orbi          # specific platforms only
    python main.py --keywords-only                     # search results only (no body)
    python main.py --max-pages 10                      # search up to 10 pages
    python main.py --headless                          # no browser window
    python main.py --output-dir ./my_results           # custom output directory
"""

import sys
import os
import time
import logging
import argparse
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import SEARCH_KEYWORDS
from utils.browser import BrowserManager
from utils.storage import save_platform_results, save_combined_results
from scraper.daum_cafe import DaumCafeScraper
from scraper.naver_cafe import NaverCafeScraper
from scraper.naver_blog import NaverBlogScraper
from scraper.orbi import OrbiScraper
from scraper.dcinside import DCInsideScraper
from scraper.tistory import TistoryScraper

# ── Platform registry ──────────────────────────────────────────────
PLATFORM_MAP = {
    "daum_cafe": DaumCafeScraper,
    "naver_cafe": NaverCafeScraper,
    "naver_blog": NaverBlogScraper,
    "orbi": OrbiScraper,
    "dcinside": DCInsideScraper,
    "tistory": TistoryScraper,
}

# ── Logging setup ──────────────────────────────────────────────────
def setup_logging(output_dir: str):
    """Configure console (INFO) and file (DEBUG) logging."""
    os.makedirs(output_dir, exist_ok=True)
    log_file = os.path.join(output_dir, "scraper.log")

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console handler: INFO
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    root_logger.addHandler(console)

    # File handler: DEBUG
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root_logger.addHandler(file_handler)

    return root_logger


def main():
    parser = argparse.ArgumentParser(
        description="LEET Answer Explanation Negative Opinion Multi-Platform Scraper"
    )
    parser.add_argument(
        "--platforms", default="all",
        help=(
            "Platforms to scrape (comma-separated). "
            "Options: daum_cafe,naver_cafe,naver_blog,orbi,dcinside,tistory. "
            "Default: all"
        ),
    )
    parser.add_argument(
        "--keywords-only", action="store_true",
        help="Only collect search results, skip body fetching",
    )
    parser.add_argument(
        "--max-pages", type=int, default=5,
        help="Max search result pages per keyword (default: 5)",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run browser in headless mode",
    )
    parser.add_argument(
        "--output-dir", default="./output",
        help="Directory to save results (default: ./output)",
    )
    args = parser.parse_args()

    # ── Setup logging ──
    logger = setup_logging(args.output_dir)

    # ── Select platforms ──
    if args.platforms == "all":
        platforms = list(PLATFORM_MAP.keys())
    else:
        platforms = [p.strip() for p in args.platforms.split(",")]
        invalid = [p for p in platforms if p not in PLATFORM_MAP]
        if invalid:
            print(f"Unknown platforms: {invalid}")
            print(f"Available: {list(PLATFORM_MAP.keys())}")
            sys.exit(1)

    # ── Print banner ──
    logger.info("=" * 60)
    logger.info("LEET Multi-Platform Negative Opinion Scraper Started")
    logger.info(f"Platforms: {', '.join(platforms)}")
    logger.info(f"Keywords: {len(SEARCH_KEYWORDS)}")
    logger.info(f"Max pages per keyword: {args.max_pages}")
    logger.info(f"Headless: {args.headless}")
    logger.info(f"Keywords only: {args.keywords_only}")
    logger.info(f"Output dir: {args.output_dir}")
    logger.info("=" * 60)

    # ── Initialize browser manager ──
    browser = BrowserManager(headless=args.headless)

    # ── Run each platform scraper ──
    all_results = []
    for i, platform_name in enumerate(platforms, 1):
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"[{i}/{len(platforms)}] Starting: {platform_name}")
        logger.info("=" * 60)

        try:
            scraper_cls = PLATFORM_MAP[platform_name]
            scraper = scraper_cls(config=None, driver_manager=browser)
            scraper.output_dir = args.output_dir

            scraper.run(
                keywords=SEARCH_KEYWORDS,
                max_pages=args.max_pages,
                keywords_only=args.keywords_only,
            )

            all_results.extend(scraper.collected_posts.values())

            # Save per-platform intermediate results
            save_platform_results(
                scraper.collected_posts, platform_name, args.output_dir
            )

        except Exception as e:
            logger.error(f"  {platform_name} failed with error: {e}", exc_info=True)

        # Rest between platforms
        if i < len(platforms):
            logger.info(f"Resting {30} seconds before next platform...")
            time.sleep(30)

    # ── Save combined results ──
    if all_results:
        csv_path, json_path = save_combined_results(
            all_results, args.output_dir, args.keywords_only
        )
        logger.info("")
        logger.info("=" * 60)
        logger.info("COLLECTION COMPLETE")
        logger.info(f"Total: {len(all_results)} posts collected")
        negative_count = sum(
            1 for p in all_results
            if (p.is_negative if hasattr(p, "is_negative") else p.get("is_negative", False))
        )
        logger.info(f"Negative: {negative_count} posts")
        logger.info(f"CSV: {csv_path}")
        logger.info(f"JSON: {json_path}")
        logger.info("=" * 60)
    else:
        logger.info("")
        logger.info("No results collected.")

    # ── Cleanup ──
    browser.quit()
    logger.info("Done!")


if __name__ == "__main__":
    main()
