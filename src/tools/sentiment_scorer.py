"""
시장 감성 분석 도구 (Sentiment Scorer) — 뉴스/공시 텍스트 감성 점수 매기기.

"이 종목에 대한 시장 분위기가 좋은가 나쁜가?"를 NLP로 측정합니다.

학술 근거:
  - NLP 감성분석 (FinBERT, Loughran-McDonald Dictionary)
  - 뉴스 감성과 주가 수익률 상관관계 (Tetlock, 2007)
  - 소셜미디어 감성과 주가 예측 (Bollen et al., 2011)

사용 방법:
  - action="full"     : 종합 감성 분석 (뉴스 + 공시 + 종합)
  - action="news"     : 뉴스 헤드라인 감성 분석
  - action="market"   : 시장 전체 분위기 (공포/탐욕 지수)
  - action="keyword"  : 키워드별 감성 트렌드

필요 환경변수: NAVER_CLIENT_ID, NAVER_CLIENT_SECRET (네이버 뉴스 검색)
필요 라이브러리: aiohttp
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import re
from datetime import datetime, timedelta
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.sentiment_scorer")


# 한국어 금융 감성 사전 (Loughran-McDonald 한국어 버전 + 추가)
POSITIVE_WORDS = {
    "상승", "급등", "호조", "성장", "개선", "흑자", "최고", "기대", "호실적",
    "서프라이즈", "돌파", "반등", "회복", "확대", "수혜", "호재", "강세",
    "신고가", "매수", "추천", "목표가상향", "실적개선", "턴어라운드", "수주",
    "계약", "합의", "승인", "특허", "혁신", "인수", "투자", "확장",
}

NEGATIVE_WORDS = {
    "하락", "급락", "부진", "감소", "적자", "최저", "우려", "악재", "실적부진",
    "쇼크", "이탈", "폭락", "위축", "축소", "리스크", "약세", "신저가",
    "매도", "하향", "목표가하향", "실적악화", "부실", "손실", "제재",
    "소송", "파산", "해고", "철수", "중단", "논란", "의혹",
}


class SentimentScorerTool(BaseTool):
    """시장 감성 분석 도구 — 뉴스 기반 긍정/부정 감성 점수."""

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        if query and not kwargs.get("name"):
            kwargs["name"] = query

        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_sentiment,
            "news": self._news_sentiment,
            "market": self._market_sentiment,
            "keyword": self._keyword_sentiment,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return f"알 수 없는 action: {action}. full, news, market, keyword 중 하나."

    # ── 뉴스 검색 (네이버 API) ────────────────

    async def _search_news(self, query: str, count: int = 30) -> list[dict]:
        """네이버 뉴스 검색 API를 사용하여 뉴스 목록을 가져옵니다."""
        client_id = os.getenv("NAVER_CLIENT_ID", "")
        client_secret = os.getenv("NAVER_CLIENT_SECRET", "")

        if not client_id or not client_secret:
            return []

        try:
            import aiohttp
        except ImportError:
            return []

        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }
        params = {"query": query, "display": count, "sort": "date"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("items", [])
        except Exception as e:
            logger.warning("뉴스 검색 실패: %s", e)

        return []

    @staticmethod
    def _clean_html(text: str) -> str:
        """HTML 태그 제거."""
        return re.sub(r"<[^>]+>", "", text).replace("&quot;", '"').replace("&amp;", "&")

    def _score_text(self, text: str) -> tuple[float, list[str], list[str]]:
        """텍스트의 감성 점수 (-1 ~ +1) 계산. (점수, 긍정단어들, 부정단어들) 반환."""
        positive_found = [w for w in POSITIVE_WORDS if w in text]
        negative_found = [w for w in NEGATIVE_WORDS if w in text]
        pos_count = len(positive_found)
        neg_count = len(negative_found)
        total = pos_count + neg_count
        if total == 0:
            return 0.0, [], []
        score = (pos_count - neg_count) / total
        return score, positive_found, negative_found

    # ── 1. 종합 감성 분석 ────────────────────

    async def _full_sentiment(self, kwargs: dict) -> str:
        name = kwargs.get("name", "")
        if not name:
            return "종목명(name)을 입력해주세요. 예: name='삼성전자'"

        news = await self._search_news(f"{name} 주식", 30)

        if not news:
            # 뉴스 API 없으면 LLM으로 감성 분석
            analysis = await self._llm_call(
                system_prompt=(
                    "당신은 금융 시장 감성 분석 전문가입니다. "
                    f"'{name}'에 대한 최근 시장 분위기를 분석해주세요. "
                    "긍정/부정/중립 비율, 주요 이슈, 감성 점수(0~100)를 제시하세요. 한국어."
                ),
                user_prompt=f"{name}의 최근 시장 감성을 분석해주세요.",
                caller_model=kwargs.get("_caller_model"),
            )
            return f"📊 {name} 시장 감성 분석 (LLM 기반)\n\n{analysis}"

        # 뉴스 감성 분석
        scores = []
        pos_total = []
        neg_total = []
        headlines = []

        for item in news:
            title = self._clean_html(item.get("title", ""))
            desc = self._clean_html(item.get("description", ""))
            text = f"{title} {desc}"
            score, pos, neg = self._score_text(text)
            scores.append(score)
            pos_total.extend(pos)
            neg_total.extend(neg)
            emoji = "🟢" if score > 0.2 else "🔴" if score < -0.2 else "⚪"
            headlines.append(f"  {emoji} {title[:50]}")

        avg_score = sum(scores) / len(scores) if scores else 0
        pos_pct = sum(1 for s in scores if s > 0.1) / len(scores) * 100 if scores else 0
        neg_pct = sum(1 for s in scores if s < -0.1) / len(scores) * 100 if scores else 0
        neu_pct = 100 - pos_pct - neg_pct

        # 감성 점수를 0~100으로 정규화
        sentiment_100 = int((avg_score + 1) * 50)

        results = [f"{'='*55}"]
        results.append(f"📊 {name} 시장 감성 분석 ({len(news)}건 뉴스)")
        results.append(f"{'='*55}\n")
        results.append(f"▸ 종합 감성 점수: {sentiment_100}/100 점")

        if sentiment_100 >= 70:
            results.append(f"  → 🟢 매우 긍정적 (강한 매수 분위기)")
        elif sentiment_100 >= 55:
            results.append(f"  → 🟢 긍정적 (매수 우위)")
        elif sentiment_100 >= 45:
            results.append(f"  → ⚪ 중립 (관망)")
        elif sentiment_100 >= 30:
            results.append(f"  → 🔴 부정적 (매도 우위)")
        else:
            results.append(f"  → 🔴 매우 부정적 (강한 매도 분위기)")

        results.append(f"\n▸ 감성 비율: 긍정 {pos_pct:.0f}% / 중립 {neu_pct:.0f}% / 부정 {neg_pct:.0f}%")

        # 자주 나오는 키워드
        from collections import Counter
        pos_counter = Counter(pos_total)
        neg_counter = Counter(neg_total)
        if pos_counter:
            results.append(f"\n▸ 긍정 키워드: {', '.join(f'{w}({c})' for w, c in pos_counter.most_common(5))}")
        if neg_counter:
            results.append(f"▸ 부정 키워드: {', '.join(f'{w}({c})' for w, c in neg_counter.most_common(5))}")

        results.append(f"\n▸ 최근 뉴스 헤드라인:")
        results.extend(headlines[:10])

        raw_text = "\n".join(results)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 금융 NLP 감성분석 전문가입니다. "
                "뉴스 기반 감성 분석 결과를 해석하고, "
                "감성 지표가 주가에 미치는 영향을 예측하세요. "
                "Tetlock(2007)의 연구를 참고하여 분석하세요. 한국어."
            ),
            user_prompt=raw_text,
            caller_model=kwargs.get("_caller_model"),
        )
        return f"{raw_text}\n\n{'='*55}\n🎓 교수급 감성 분석\n{'='*55}\n{analysis}"

    # ── 2. 뉴스 감성 분석 ────────────────────

    async def _news_sentiment(self, kwargs: dict) -> str:
        return await self._full_sentiment(kwargs)

    # ── 3. 시장 전체 분위기 ──────────────────

    async def _market_sentiment(self, kwargs: dict) -> str:
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 시장 심리 분석 전문가입니다. "
                "현재(2026년 2월) 한국 주식시장의 공포/탐욕 지수를 0~100으로 매기고, "
                "KOSPI, 원달러 환율, 금리, 외인 매매 동향을 종합하여 "
                "시장 전체 분위기를 분석하세요. 구체적인 숫자로. 한국어."
            ),
            user_prompt="현재 한국 주식시장 공포/탐욕 지수와 시장 분위기 분석",
            caller_model=kwargs.get("_caller_model"),
        )
        return f"📊 시장 전체 감성 분석 (공포/탐욕 지수)\n\n{analysis}"

    # ── 4. 키워드 감성 트렌드 ────────────────

    async def _keyword_sentiment(self, kwargs: dict) -> str:
        keyword = kwargs.get("name", "") or kwargs.get("keyword", "") or kwargs.get("query", "")
        if not keyword:
            return "키워드를 입력해주세요. 예: keyword='반도체'"

        news = await self._search_news(keyword, 20)
        if not news:
            analysis = await self._llm_call(
                system_prompt=f"'{keyword}' 키워드에 대한 최근 시장 감성 트렌드를 분석해주세요. 한국어.",
                user_prompt=f"'{keyword}' 감성 분석",
                caller_model=kwargs.get("_caller_model"),
            )
            return f"📊 '{keyword}' 감성 트렌드 (LLM 기반)\n\n{analysis}"

        scores = []
        for item in news:
            text = self._clean_html(f"{item.get('title', '')} {item.get('description', '')}")
            score, _, _ = self._score_text(text)
            scores.append(score)

        avg = sum(scores) / len(scores) if scores else 0
        score_100 = int((avg + 1) * 50)

        return f"📊 '{keyword}' 감성 점수: {score_100}/100 ({len(news)}건 분석)\n→ {'긍정' if score_100 > 55 else '부정' if score_100 < 45 else '중립'}"
