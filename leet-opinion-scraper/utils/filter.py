"""
Filtering logic: negative expression matching, ad filtering, LEET relevance check.
"""

import logging
from config import (
    NEGATIVE_PATTERNS,
    AD_TITLE_KEYWORDS,
    AD_AUTHOR_PATTERNS,
    LEET_CONTEXT_KEYWORDS,
)

logger = logging.getLogger(__name__)


def match_negative_patterns(text: str) -> list[str]:
    """Return list of negative patterns found in text."""
    if not text:
        return []
    return [pat for pat in NEGATIVE_PATTERNS if pat in text]


def is_negative_post(title: str, content: str) -> tuple[bool, list[str]]:
    """Check if a post is negative. Returns (is_negative, matched_patterns)."""
    combined = f"{content or ''} {title or ''}"
    matched = match_negative_patterns(combined)
    return len(matched) > 0, matched


def is_ad_post(title: str, author: str) -> bool:
    """Check if a post is an ad/spam."""
    title = title or ""
    author = author or ""
    if any(kw in title for kw in AD_TITLE_KEYWORDS):
        return True
    if any(pat in author for pat in AD_AUTHOR_PATTERNS):
        return True
    return False


def is_leet_relevant(title: str, content: str) -> bool:
    """Check if a post is LEET-related (not CSAT/civil service etc)."""
    combined = f"{content or ''} {title or ''}"
    return any(kw in combined for kw in LEET_CONTEXT_KEYWORDS)
