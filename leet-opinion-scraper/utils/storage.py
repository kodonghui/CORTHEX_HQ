"""
CSV/JSON save logic with intermediate save support.
"""

import os
import json
import logging
from datetime import datetime
from dataclasses import asdict

import pandas as pd

logger = logging.getLogger(__name__)


def save_platform_results(posts: dict, platform_name: str, output_dir: str):
    """Save per-platform intermediate results as JSON."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(output_dir, f"intermediate_{platform_name}_{timestamp}.json")

    data = []
    for post in posts.values():
        if hasattr(post, "__dataclass_fields__"):
            data.append(asdict(post))
        elif isinstance(post, dict):
            data.append(post)
        else:
            data.append(vars(post))

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"  Intermediate results saved: {filepath} ({len(data)} posts)")


def save_combined_results(all_posts: list, output_dir: str, keywords_only: bool):
    """Save combined CSV and JSON results."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Convert posts to dicts
    posts_data = []
    for post in all_posts:
        if hasattr(post, "__dataclass_fields__"):
            posts_data.append(asdict(post))
        elif isinstance(post, dict):
            posts_data.append(post)
        else:
            posts_data.append(vars(post))

    # ── Save CSV ──
    csv_path = os.path.join(output_dir, f"results_{timestamp}.csv")
    csv_rows = []
    for p in posts_data:
        csv_rows.append({
            "post_id": p.get("post_id", ""),
            "platform": p.get("platform", ""),
            "board_name": p.get("board_name", ""),
            "title": p.get("title", ""),
            "author": p.get("author", ""),
            "date": p.get("date", ""),
            "view_count": p.get("view_count", 0),
            "url": p.get("url", ""),
            "search_keywords": ", ".join(p.get("search_keywords", [])),
            "matched_negative": ", ".join(p.get("matched_negative", [])),
            "is_negative": p.get("is_negative", False),
            "preview": p.get("preview", ""),
        })
    df = pd.DataFrame(csv_rows)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logger.info(f"CSV saved: {csv_path}")

    # ── Build summary ──
    platform_summary = {}
    keyword_summary = {}
    for p in posts_data:
        plat = p.get("platform", "unknown")
        if plat not in platform_summary:
            platform_summary[plat] = {"collected": 0, "negative": 0}
        platform_summary[plat]["collected"] += 1
        if p.get("is_negative"):
            platform_summary[plat]["negative"] += 1

        for kw in p.get("search_keywords", []):
            keyword_summary[kw] = keyword_summary.get(kw, 0) + 1

    # Sort keyword_summary by count descending
    keyword_summary = dict(sorted(keyword_summary.items(), key=lambda x: x[1], reverse=True))

    total_negative = sum(1 for p in posts_data if p.get("is_negative"))

    # ── Save JSON ──
    json_path = os.path.join(output_dir, f"results_{timestamp}.json")
    platforms_used = list(set(p.get("platform", "") for p in posts_data))
    output_json = {
        "collection_datetime": datetime.now().isoformat(timespec="seconds"),
        "settings": {
            "platforms": sorted(platforms_used),
            "max_pages": 5,
            "keyword_count": len(set(
                kw for p in posts_data for kw in p.get("search_keywords", [])
            )),
            "body_collected": not keywords_only,
        },
        "summary": {
            "total_collected": len(posts_data),
            "total_negative": total_negative,
            "by_platform": platform_summary,
            "by_keyword": keyword_summary,
        },
        "posts": posts_data,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_json, f, ensure_ascii=False, indent=2)
    logger.info(f"JSON saved: {json_path}")

    return csv_path, json_path


def save_intermediate_batch(posts: list, platform_name: str, output_dir: str):
    """Auto-save a batch of posts (called every 20 posts)."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(output_dir, f"autosave_{platform_name}_{timestamp}.json")

    data = []
    for post in posts:
        if hasattr(post, "__dataclass_fields__"):
            data.append(asdict(post))
        elif isinstance(post, dict):
            data.append(post)
        else:
            data.append(vars(post))

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.debug(f"Auto-save: {filepath} ({len(data)} posts)")
