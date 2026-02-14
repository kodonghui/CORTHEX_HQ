"""SNS 감정 분석기 — 특정 키워드에 대한 온라인 여론의 긍정/부정을 분석하는 도구.

네이버 뉴스/블로그 검색 API로 글을 수집한 뒤,
한국어 감정 사전 기반으로 긍정·부정·중립을 자동 판별합니다.
"""
from __future__ import annotations

import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.sentiment_analyzer")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# ─── 한국어 감정 사전 ───
POSITIVE_WORDS = [
    "좋다", "좋은", "좋아", "훌륭", "추천", "만족", "최고", "편리", "유용", "도움",
    "잘했", "대박", "짱", "꿀팁", "강추", "괜찮", "나이스", "굿", "효과적", "깔끔",
    "정확", "친절", "빠르", "쉽다", "알차", "유익", "감동", "기대", "완벽", "뛰어나",
    "성공", "혁신", "안정", "신뢰", "합리", "저렴", "세련", "멋지", "탁월", "우수",
]

NEGATIVE_WORDS = [
    "별로", "실망", "불만", "최악", "짜증", "부족", "비싸", "불편", "쓰레기", "후회",
    "거지", "노답", "폐급", "사기", "망했", "느리", "어렵", "복잡", "불친절", "에러",
    "오류", "버그", "허접", "형편없", "안좋", "나쁘", "구리", "별점", "환불", "해지",
    "답답", "짜증", "의문", "아쉽", "허술", "미흡", "위험", "피해", "불신", "역겹",
]


def _clean_html(text: str) -> str:
    """HTML 태그 및 특수 문자를 제거합니다."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return text.strip()


def analyze_sentiment(text: str) -> dict[str, Any]:
    """텍스트의 감정을 분석합니다.

    Returns:
        {"label": "긍정" | "부정" | "중립", "score": float, "pos": int, "neg": int}
    """
    positive_count = sum(1 for w in POSITIVE_WORDS if w in text)
    negative_count = sum(1 for w in NEGATIVE_WORDS if w in text)
    total = positive_count + negative_count
    if total == 0:
        return {"label": "중립", "score": 0.5, "pos": 0, "neg": 0}
    pos_ratio = positive_count / total
    if pos_ratio > 0.6:
        label = "긍정"
    elif pos_ratio < 0.4:
        label = "부정"
    else:
        label = "중립"
    return {"label": label, "score": round(pos_ratio, 3), "pos": positive_count, "neg": negative_count}


class SentimentAnalyzerTool(BaseTool):
    """특정 키워드에 대한 온라인 여론의 긍정/부정을 분석하는 도구."""

    async def execute(self, **kwargs: Any) -> str:
        """
        감정 분석 도구 실행.

        kwargs:
          - action: "analyze" | "trend" | "report"
          - keyword: 분석할 키워드
          - sources: 소스 (기본: "naver_news,naver_blog")
          - count: 수집할 글 수 (기본: 50)
          - days: 분석 기간 (기본: 30)
        """
        action = kwargs.get("action", "analyze")

        if action == "analyze":
            return await self._analyze(kwargs)
        elif action == "trend":
            return await self._trend(kwargs)
        elif action == "report":
            return await self._report(kwargs)
        else:
            return f"알 수 없는 action: {action}\n사용 가능: analyze, trend, report"

    # ──────────────────────────────────────
    #  내부: 네이버 API 호출
    # ──────────────────────────────────────

    def _get_naver_credentials(self) -> tuple[str, str]:
        """네이버 API 인증 정보를 환경변수에서 가져옵니다."""
        client_id = os.environ.get("NAVER_CLIENT_ID", "")
        client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
        return client_id, client_secret

    async def _search_naver(
        self, query: str, source: str = "news", count: int = 50
    ) -> list[dict[str, Any]]:
        """네이버 검색 API로 글을 수집합니다.

        Args:
            query: 검색어
            source: "news" 또는 "blog"
            count: 수집할 글 수 (최대 100)

        Returns:
            [{"title": ..., "description": ..., "link": ..., "pubDate": ...}, ...]
        """
        client_id, client_secret = self._get_naver_credentials()
        if not client_id or not client_secret:
            logger.warning("[sentiment_analyzer] 네이버 API 키가 설정되지 않았습니다.")
            return []

        url = f"https://openapi.naver.com/v1/search/{source}.json"
        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }
        all_items: list[dict[str, Any]] = []
        display = min(count, 100)
        start = 1

        async with httpx.AsyncClient(headers=_HEADERS, timeout=15.0) as client:
            while len(all_items) < count:
                params = {
                    "query": query,
                    "display": min(display, count - len(all_items)),
                    "start": start,
                    "sort": "date",
                }
                try:
                    resp = await client.get(url, params=params, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    items = data.get("items", [])
                    if not items:
                        break
                    all_items.extend(items)
                    start += len(items)
                    if start > 1000:  # 네이버 API 최대 start
                        break
                except Exception as e:
                    logger.error("[sentiment_analyzer] 네이버 API 오류: %s", e)
                    break

        return all_items[:count]

    # ──────────────────────────────────────
    #  내부: 분석 유틸
    # ──────────────────────────────────────

    def _analyze_items(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """수집된 글 목록의 감정을 분석합니다."""
        sentiments = []
        pos_words_counter: Counter[str] = Counter()
        neg_words_counter: Counter[str] = Counter()
        pos_examples: list[str] = []
        neg_examples: list[str] = []

        for item in items:
            text = _clean_html(item.get("title", "") + " " + item.get("description", ""))
            result = analyze_sentiment(text)
            sentiments.append(result)

            # 긍정/부정 키워드 카운트
            for w in POSITIVE_WORDS:
                if w in text:
                    pos_words_counter[w] += 1
            for w in NEGATIVE_WORDS:
                if w in text:
                    neg_words_counter[w] += 1

            # 대표 문장 수집
            if result["label"] == "긍정" and len(pos_examples) < 3:
                pos_examples.append(text[:100])
            elif result["label"] == "부정" and len(neg_examples) < 3:
                neg_examples.append(text[:100])

        total = len(sentiments)
        if total == 0:
            return {"total": 0, "positive": 0, "negative": 0, "neutral": 0}

        pos_count = sum(1 for s in sentiments if s["label"] == "긍정")
        neg_count = sum(1 for s in sentiments if s["label"] == "부정")
        neu_count = sum(1 for s in sentiments if s["label"] == "중립")

        return {
            "total": total,
            "positive": pos_count,
            "negative": neg_count,
            "neutral": neu_count,
            "pos_ratio": round(pos_count / total * 100, 1),
            "neg_ratio": round(neg_count / total * 100, 1),
            "neu_ratio": round(neu_count / total * 100, 1),
            "top_pos_words": pos_words_counter.most_common(10),
            "top_neg_words": neg_words_counter.most_common(10),
            "pos_examples": pos_examples,
            "neg_examples": neg_examples,
        }

    # ──────────────────────────────────────
    #  action: analyze
    # ──────────────────────────────────────

    async def _analyze(self, kwargs: dict[str, Any]) -> str:
        """키워드 감정 분석을 실행합니다."""
        keyword = kwargs.get("keyword", "")
        if not keyword:
            return "keyword 파라미터를 입력해주세요. 예: keyword='CORTHEX'"

        sources_str = kwargs.get("sources", "naver_news,naver_blog")
        count = int(kwargs.get("count", 50))

        logger.info("[sentiment_analyzer] analyze: keyword=%s, count=%d", keyword, count)

        # 네이버 API 키 확인
        client_id, _ = self._get_naver_credentials()
        if not client_id:
            return (
                "네이버 API 키가 설정되지 않았습니다.\n"
                "설정 방법:\n"
                "  export NAVER_CLIENT_ID=your_client_id\n"
                "  export NAVER_CLIENT_SECRET=your_client_secret\n"
                "발급: https://developers.naver.com/apps/"
            )

        # 데이터 수집
        sources = [s.strip() for s in sources_str.split(",")]
        all_items: list[dict[str, Any]] = []

        for source in sources:
            api_source = "news" if "news" in source else "blog"
            items = await self._search_naver(keyword, api_source, count // len(sources))
            all_items.extend(items)

        if not all_items:
            return f"'{keyword}' 관련 글을 찾을 수 없습니다."

        # 분석
        result = self._analyze_items(all_items)

        # 포맷팅
        lines = [
            f"## 감정 분석 결과: '{keyword}'",
            f"- 분석 대상: {result['total']}개 글 (소스: {sources_str})",
            "",
            "### 감정 비율",
            f"- 긍정: {result['positive']}개 ({result['pos_ratio']}%)",
            f"- 부정: {result['negative']}개 ({result['neg_ratio']}%)",
            f"- 중립: {result['neutral']}개 ({result['neu_ratio']}%)",
            "",
        ]

        if result.get("top_pos_words"):
            lines.append("### 자주 나오는 긍정 키워드")
            for word, cnt in result["top_pos_words"]:
                lines.append(f"  - {word}: {cnt}회")
            lines.append("")

        if result.get("top_neg_words"):
            lines.append("### 자주 나오는 부정 키워드")
            for word, cnt in result["top_neg_words"]:
                lines.append(f"  - {word}: {cnt}회")
            lines.append("")

        if result.get("pos_examples"):
            lines.append("### 대표 긍정 문장")
            for i, ex in enumerate(result["pos_examples"], 1):
                lines.append(f"  {i}. {ex}")
            lines.append("")

        if result.get("neg_examples"):
            lines.append("### 대표 부정 문장")
            for i, ex in enumerate(result["neg_examples"], 1):
                lines.append(f"  {i}. {ex}")
            lines.append("")

        result_text = "\n".join(lines)

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 PR(홍보) 전문가입니다. 아래 여론 분석 결과를 보고:\n"
                "1. 전반적인 여론 요약 (한 줄)\n"
                "2. 긍정 여론을 강화할 전략 2가지\n"
                "3. 부정 여론에 대한 대응 전략 2가지\n"
                "4. 주의해야 할 리스크 포인트\n"
                "를 한국어로 작성하세요."
            ),
            user_prompt=result_text,
        )

        return f"{result_text}\n---\n\n### AI 여론 대응 전략\n\n{analysis}"

    # ──────────────────────────────────────
    #  action: trend
    # ──────────────────────────────────────

    async def _trend(self, kwargs: dict[str, Any]) -> str:
        """시간별 감정 추이를 분석합니다."""
        keyword = kwargs.get("keyword", "")
        if not keyword:
            return "keyword 파라미터를 입력해주세요."

        days = int(kwargs.get("days", 30))
        logger.info("[sentiment_analyzer] trend: keyword=%s, days=%d", keyword, days)

        # 네이버 API 키 확인
        client_id, _ = self._get_naver_credentials()
        if not client_id:
            return (
                "네이버 API 키가 설정되지 않았습니다.\n"
                "설정: export NAVER_CLIENT_ID=... / export NAVER_CLIENT_SECRET=..."
            )

        # 뉴스 데이터 수집
        items = await self._search_naver(keyword, "news", 100)
        if not items:
            return f"'{keyword}' 관련 뉴스를 찾을 수 없습니다."

        # 날짜별 분류
        now = datetime.now()
        daily_sentiments: dict[str, list[dict]] = {}

        for item in items:
            pub_date_str = item.get("pubDate", "")
            try:
                pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %z")
                date_key = pub_date.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue

            text = _clean_html(item.get("title", "") + " " + item.get("description", ""))
            sentiment = analyze_sentiment(text)

            if date_key not in daily_sentiments:
                daily_sentiments[date_key] = []
            daily_sentiments[date_key].append(sentiment)

        if not daily_sentiments:
            return f"'{keyword}' 관련 날짜별 데이터를 분류할 수 없습니다."

        # 날짜별 긍정 비율 계산
        lines = [
            f"## 감정 추이: '{keyword}' (최근 {days}일)",
            "",
            "| 날짜 | 글 수 | 긍정 | 부정 | 중립 | 긍정률 |",
            "|------|-------|------|------|------|--------|",
        ]

        for date_key in sorted(daily_sentiments.keys()):
            sents = daily_sentiments[date_key]
            total = len(sents)
            pos = sum(1 for s in sents if s["label"] == "긍정")
            neg = sum(1 for s in sents if s["label"] == "부정")
            neu = sum(1 for s in sents if s["label"] == "중립")
            pos_rate = round(pos / total * 100, 1) if total > 0 else 0
            lines.append(f"| {date_key} | {total} | {pos} | {neg} | {neu} | {pos_rate}% |")

        result_text = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 여론 분석 전문가입니다. 아래 시간별 감정 추이를 분석하여:\n"
                "1. 전체 추이 요약 (상승세/하락세/안정)\n"
                "2. 특이한 변동이 있는 날짜와 원인 추측\n"
                "3. 향후 전망과 대비 전략\n"
                "을 한국어로 작성하세요."
            ),
            user_prompt=result_text,
        )

        return f"{result_text}\n\n---\n\n### AI 추이 분석\n\n{analysis}"

    # ──────────────────────────────────────
    #  action: report
    # ──────────────────────────────────────

    async def _report(self, kwargs: dict[str, Any]) -> str:
        """종합 여론 보고서를 생성합니다."""
        keyword = kwargs.get("keyword", "")
        if not keyword:
            return "keyword 파라미터를 입력해주세요."

        logger.info("[sentiment_analyzer] report: keyword=%s", keyword)

        # 네이버 API 키 확인
        client_id, _ = self._get_naver_credentials()
        if not client_id:
            return (
                "네이버 API 키가 설정되지 않았습니다.\n"
                "설정: export NAVER_CLIENT_ID=... / export NAVER_CLIENT_SECRET=..."
            )

        # 뉴스 + 블로그 모두 수집
        news_items = await self._search_naver(keyword, "news", 50)
        blog_items = await self._search_naver(keyword, "blog", 50)

        news_result = self._analyze_items(news_items) if news_items else None
        blog_result = self._analyze_items(blog_items) if blog_items else None

        lines = [
            f"## 종합 여론 보고서: '{keyword}'",
            f"- 보고서 생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        if news_result and news_result["total"] > 0:
            lines.extend([
                "### 1. 뉴스 여론",
                f"- 분석 대상: {news_result['total']}건",
                f"- 긍정 {news_result['pos_ratio']}% / 부정 {news_result['neg_ratio']}% / 중립 {news_result['neu_ratio']}%",
                "",
            ])

        if blog_result and blog_result["total"] > 0:
            lines.extend([
                "### 2. 블로그 여론",
                f"- 분석 대상: {blog_result['total']}건",
                f"- 긍정 {blog_result['pos_ratio']}% / 부정 {blog_result['neg_ratio']}% / 중립 {blog_result['neu_ratio']}%",
                "",
            ])

        # 통합 키워드
        all_items = (news_items or []) + (blog_items or [])
        combined = self._analyze_items(all_items)

        if combined["total"] > 0:
            lines.extend([
                "### 3. 종합 분석",
                f"- 전체 분석 대상: {combined['total']}건",
                f"- 긍정 {combined['pos_ratio']}% / 부정 {combined['neg_ratio']}% / 중립 {combined['neu_ratio']}%",
                "",
            ])

            if combined.get("top_pos_words"):
                lines.append("**긍정 키워드 Top 10:**")
                for word, cnt in combined["top_pos_words"]:
                    lines.append(f"  - {word} ({cnt}회)")
                lines.append("")

            if combined.get("top_neg_words"):
                lines.append("**부정 키워드 Top 10:**")
                for word, cnt in combined["top_neg_words"]:
                    lines.append(f"  - {word} ({cnt}회)")
                lines.append("")

        result_text = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 CMO(마케팅 최고 책임자)의 보좌관입니다.\n"
                "아래 여론 데이터를 기반으로 CEO에게 보고할 종합 보고서를 작성하세요:\n"
                "1. 핵심 요약 (3줄)\n"
                "2. 긍정 요인 분석\n"
                "3. 부정 요인 분석 및 위기 수준 판단 (낮음/보통/높음)\n"
                "4. 즉시 실행할 PR 액션 플랜 3가지\n"
                "5. 중장기 브랜드 관리 전략\n"
                "한국어로, 비개발자도 이해할 수 있게 작성하세요."
            ),
            user_prompt=result_text,
        )

        return f"{result_text}\n---\n\n### AI 종합 여론 보고서\n\n{analysis}"
