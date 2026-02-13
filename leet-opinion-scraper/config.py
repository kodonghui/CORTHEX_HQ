"""
LEET Multi-Platform Negative Opinion Scraper - Configuration
All constants, keywords, patterns, and URLs.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# .env.local 우선 → .env 폴백 (AnySign4PC .env 잠금 방지)
_env_local = Path(__file__).resolve().parent.parent / ".env.local"
if _env_local.exists():
    load_dotenv(_env_local)
else:
    load_dotenv()

# ── Login credentials ──────────────────────────────────────────────
KAKAO_ID = os.getenv("KAKAO_ID", "")
KAKAO_PW = os.getenv("KAKAO_PW", "")
NAVER_ID = os.getenv("NAVER_ID", "")
NAVER_PW = os.getenv("NAVER_PW", "")
ORBI_ID = os.getenv("ORBI_ID", "")
ORBI_PW = os.getenv("ORBI_PW", "")

# ── Search keywords ────────────────────────────────────────────────
SEARCH_KEYWORDS = [
    # direct "해설" criticism
    "해설 다르다", "해설 이상", "해설 별로", "해설 틀린",
    "해설 오류", "해설 부실", "해설 납득", "해설 논란",
    "해설 의문", "해설 잘못", "해설 엉터리", "해설 불만",
    "해설 수긍", "해설 맞나", "해설 문제",
    # 해설집/해설서
    "해설집 오류", "해설집 다르", "해설집 부실",
    "해설서 오류", "해설서 문제",
    # 기출 + 해설 combo
    "기출 해설 오류", "기출 해설 다른",
    "LEET 해설 오류", "리트 해설 오류",
    "LEET 해설 다르", "리트 해설 다른",
    # official explanation
    "공식해설", "공식 해설",
    # instructor explanation
    "강사 해설", "강사해설",
    # answer discrepancy
    "답 다른", "답이 다른", "답이 틀린",
    # publisher/academy specific
    "메가 해설", "피트 해설", "진학사 해설",
    "메가로스쿨 해설", "이그잼포유 해설",
]

# ── LEET context keywords (at least one must appear) ───────────────
LEET_CONTEXT_KEYWORDS = [
    "LEET", "리트", "법학적성", "법적성", "로스쿨", "법학전문대학원",
    "법전원", "추리논증", "언어이해", "논술",
]

# ── Negative expression patterns ──────────────────────────────────
NEGATIVE_PATTERNS = [
    # direct criticism of 해설
    "해설이 다르", "해설이 틀", "해설이 이상", "해설이 잘못",
    "해설 오류", "해설이 부실", "해설 납득", "해설이 별로",
    "해설 믿을 수", "해설 엉터리", "해설 수긍",
    # discrepancy across sources
    "회사마다 다르", "출판사마다 다르", "학원마다 다르",
    "강사마다 다르", "책마다 다르", "업체마다 다르",
    # official explanation criticism
    "공식 해설이 별로", "공식해설 문제", "공식 해설 이상",
    # answer issues
    "답이 다르", "답이 틀", "오답",
    # 해설서/해설집 criticism
    "해설서 불만", "해설집 문제", "해설서 부실", "해설집 이상",
    # cannot understand/accept
    "이해가 안", "납득이 안", "수긍이 안",
    "이해 안 ", "납득 안 ", "수긍 안 ",
    # general negative
    "논란", "의문",
]

# ── Ad/spam filter keywords ───────────────────────────────────────
AD_TITLE_KEYWORDS = [
    "모집합니다", "수강생 모집", "과외 모집", "개강 안내",
    "수강료", "할인", "이벤트", "무료 강의", "설명회",
    "광고", "홍보", "제휴", "의뢰", "스폰서",
]

AD_AUTHOR_PATTERNS = [
    "메가로스쿨", "피트", "진학사", "이그잼", "법률저널",
    "에듀", "학원", "아카데미", "공식",
]

# ── Rate limiting delays (seconds) ────────────────────────────────
DELAY_BETWEEN_SEARCHES = (2.0, 4.0)
DELAY_BETWEEN_POSTS = (2.0, 3.5)
DELAY_BETWEEN_PAGES = (1.5, 3.0)
DELAY_BETWEEN_PLATFORMS = 30
MAX_POSTS_PER_HOUR = 500
MAX_CONCURRENT_REQUESTS = 1

# ── Platform-specific CSS selectors ──────────────────────────────

DAUM_CAFE_SELECTORS = {
    "search_result_item": "ul.list_search li",
    "title_link": "a.link_tit",
    "author": "span.txt_nick",
    "date": "span.txt_date",
    "preview": "p.txt_detail",
    "post_content": "div.article_view",
    "iframe_id": "down",
}

NAVER_CAFE_SELECTORS = {
    "search_result": "ul.lst_total li.bx",
    "title": "a.api_txt_lines",
    "author": "a.txt_sub",
    "date": "span.sub_time",
    "preview": "div.api_txt_lines.dsc_txt",
    "post_content": "div.se-main-container",
    "post_content_old": "div#postViewArea",
    "iframe_id": "cafe_main",
}

NAVER_BLOG_SELECTORS = {
    "search_result": "li.bx",
    "title": "a.api_txt_lines.total_tit",
    "author": "a.sub_txt",
    "date": "span.sub_time",
    "preview": "div.api_txt_lines.dsc_txt",
    "post_content": "div.se-main-container",
    "post_content_old": "div#postViewArea",
}

ORBI_SELECTORS = {
    "search_item": "div.search-result-item",
    "title": "a.title-link",
    "author": "span.author",
    "date": "span.date",
    "post_content": "div.content-area",
    "post_content_alt": "div.fr-view",
}

DCINSIDE_SELECTORS = {
    "post_list_row": "tr.ub-content",
    "title": "td.gall_tit a",
    "author": "td.gall_writer",
    "date": "td.gall_date",
    "view_count": "td.gall_count",
    "post_content": "div.write_div",
    "post_content_alt": "div.writing_view_box",
}

TISTORY_SELECTORS = {
    "search_item": "div.cont_inner",
    "title": "a.f_link_b",
    "author": "span.f_nb",
    "date": "span.date",
    "preview": "p.f_eb.desc",
    "content_selectors": [
        "div.entry-content",
        "div.article_view",
        "div.area_view",
        "div#content",
        "div.post-content",
        "article",
        "div.tt_article_useless_p_margin",
        "div.contents_style",
    ],
}

# ── Daum Cafe board codes ─────────────────────────────────────────
DAUM_CAFE_BOARDS = {
    "4KSj": "로스쿨 수험생 게시판",
    "HhJP": "문제토론방(Q&A)",
    "LGSH": "수험교재/학원강의",
}

# ── DCInside gallery IDs to try ───────────────────────────────────
DCINSIDE_GALLERIES = [
    ("lawschool", "로스쿨 갤러리"),
    ("law", "법학 갤러리"),
]

# ── Cookie file paths ─────────────────────────────────────────────
COOKIE_DIR = "cookies"
DAUM_COOKIE_PATH = os.path.join(COOKIE_DIR, "daum_cafe.pkl")
NAVER_COOKIE_PATH = os.path.join(COOKIE_DIR, "naver_cafe.pkl")
ORBI_COOKIE_PATH = os.path.join(COOKIE_DIR, "orbi.pkl")
