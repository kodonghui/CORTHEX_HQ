"""
상표 유사도 검사 Tool.

브랜드명/상표명이 기존 등록 상표와 얼마나 유사한지
글자·발음·외관 3가지 기준으로 자동 판별합니다.

사용 방법:
  - action="check": 상표 유사도 검사 (단건)
  - action="batch": 여러 후보 상표명 일괄 검사

필요 환경변수: KIPRIS_API_KEY (특허정보원 KIPRIS Plus API)
의존 라이브러리: httpx

주의: 이 검사는 참고용이며, 실제 상표 등록은 변리사와 상담하세요.
"""
from __future__ import annotations

import logging
import os
from typing import Any
from xml.etree import ElementTree

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.trademark_similarity")

KIPRIS_BASE = "http://plus.kipris.or.kr/kipo-api/kipi"

# ── 한글 자모 분리를 위한 상수 (직접 구현, 외부 라이브러리 없음) ──

CHOSUNG = [
    'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ',
    'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ',
]
JUNGSUNG = [
    'ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', 'ㅘ',
    'ㅙ', 'ㅚ', 'ㅛ', 'ㅜ', 'ㅝ', 'ㅞ', 'ㅟ', 'ㅠ', 'ㅡ', 'ㅢ', 'ㅣ',
]
JONGSUNG = [
    '', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ',
    'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ',
    'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ',
]

# 한글 → 영문 발음 변환 테이블 (외관 유사도 비교용)
_KO_TO_EN: dict[str, str] = {
    'ㄱ': 'g', 'ㄲ': 'kk', 'ㄴ': 'n', 'ㄷ': 'd', 'ㄸ': 'tt',
    'ㄹ': 'r', 'ㅁ': 'm', 'ㅂ': 'b', 'ㅃ': 'pp', 'ㅅ': 's',
    'ㅆ': 'ss', 'ㅇ': '', 'ㅈ': 'j', 'ㅉ': 'jj', 'ㅊ': 'ch',
    'ㅋ': 'k', 'ㅌ': 't', 'ㅍ': 'p', 'ㅎ': 'h',
    'ㅏ': 'a', 'ㅐ': 'ae', 'ㅑ': 'ya', 'ㅒ': 'yae',
    'ㅓ': 'eo', 'ㅔ': 'e', 'ㅕ': 'yeo', 'ㅖ': 'ye',
    'ㅗ': 'o', 'ㅘ': 'wa', 'ㅙ': 'wae', 'ㅚ': 'oe',
    'ㅛ': 'yo', 'ㅜ': 'u', 'ㅝ': 'wo', 'ㅞ': 'we',
    'ㅟ': 'wi', 'ㅠ': 'yu', 'ㅡ': 'eu', 'ㅢ': 'ui', 'ㅣ': 'i',
}

_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 검사는 참고용이며, "
    "실제 상표 등록은 변리사와 상담하세요."
)


class TrademarkSimilarityTool(BaseTool):
    """상표 유사도 검사 도구 (CLO 법무IP처 소속)."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "check")

        if action == "check":
            return await self._check_single(kwargs)
        elif action == "batch":
            return await self._check_batch(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "check 또는 batch를 사용하세요."
            )

    # ── 단건 검사 ──

    async def _check_single(self, kwargs: dict[str, Any]) -> str:
        """단일 상표명의 유사도 검사."""
        name = kwargs.get("name", "")
        if not name:
            return "검사할 상표명(name)을 입력해주세요. 예: name='CORTHEX'"

        nice_class = kwargs.get("nice_class", "")

        # KIPRIS에서 유사 상표 검색
        existing_marks = await self._search_trademarks(name)

        if not existing_marks:
            result = (
                f"## 상표 유사도 검사: '{name}'\n\n"
                f"KIPRIS 검색 결과 유사 상표가 발견되지 않았습니다.\n"
                f"- 리스크 수준: **안전 — 유사 상표 없음**\n"
            )
            analysis = await self._llm_call(
                system_prompt=(
                    "당신은 상표 전문 변리사입니다.\n"
                    "유사 상표가 발견되지 않은 상표에 대해 다음을 답변하세요:\n"
                    "1. 상표 등록 가능성 평가\n"
                    "2. 상표 강도(식별력) 평가\n"
                    "3. 등록 진행 시 주의사항\n"
                    "한국어로 답변하세요."
                ),
                user_prompt=f"상표명: {name}, 니스분류: {nice_class or '미지정'}",
            )
            return f"{result}\n{analysis}{_DISCLAIMER}"

        # 각 기존 상표와 유사도 비교
        comparisons: list[dict] = []
        for mark in existing_marks[:10]:
            mark_name = mark.get("title", mark.get("상표명", ""))
            if not mark_name:
                continue

            text_sim = self._levenshtein_similarity(name, mark_name)
            pron_sim = self._pronunciation_similarity(name, mark_name)
            appearance_sim = self._appearance_similarity(name, mark_name)

            total = text_sim * 0.4 + pron_sim * 0.4 + appearance_sim * 0.2
            total_score = round(total * 100, 1)

            risk = self._risk_level(total_score)

            comparisons.append({
                "existing_name": mark_name,
                "text_sim": round(text_sim * 100, 1),
                "pron_sim": round(pron_sim * 100, 1),
                "appearance_sim": round(appearance_sim * 100, 1),
                "total_score": total_score,
                "risk": risk,
                "status": mark.get("applicationStatus", mark.get("상태", "")),
                "app_number": mark.get("applicationNumber", mark.get("출원번호", "")),
            })

        # 점수 높은 순 정렬
        comparisons.sort(key=lambda x: x["total_score"], reverse=True)

        # 결과 포맷
        lines = [f"## 상표 유사도 검사: '{name}'\n"]
        if nice_class:
            lines.append(f"니스 분류: {nice_class}류\n")
        lines.append(f"유사 상표 {len(comparisons)}건 발견\n")

        lines.append("| 기존 상표 | 글자 | 발음 | 외관 | **종합** | 위험도 |")
        lines.append("|-----------|------|------|------|----------|--------|")
        for c in comparisons:
            lines.append(
                f"| {c['existing_name']} | "
                f"{c['text_sim']}% | "
                f"{c['pron_sim']}% | "
                f"{c['appearance_sim']}% | "
                f"**{c['total_score']}%** | "
                f"{c['risk']} |"
            )

        # 최고 유사도 기준 종합 판정
        max_score = comparisons[0]["total_score"] if comparisons else 0
        overall_risk = self._risk_level(max_score)
        lines.append(f"\n### 종합 판정: {overall_risk}")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 상표 전문 변리사입니다.\n"
                "상표 유사도 검사 결과를 분석하여 다음을 답변하세요:\n\n"
                "1. **상표 등록 가능성 판단**: 거절 가능성, 이의 신청 가능성\n"
                "2. **가장 위험한 유사 상표**: 어떤 상표와 왜 충돌하는지\n"
                "3. **대안 브랜드명 제안**: 3~5개 대안 상표명\n"
                "4. **등록 전략**: 니스 분류 전략, 출원 시 주의사항\n\n"
                "한국어로 구체적으로 답변하세요.\n"
                "주의: 이 분석은 참고용이며, 실제 상표 등록은 변리사와 상담하세요."
            ),
            user_prompt=f"검사 상표명: {name}\n\n{formatted}",
        )

        return f"{formatted}\n\n---\n\n## 전문가 분석\n\n{analysis}{_DISCLAIMER}"

    # ── 일괄 검사 ──

    async def _check_batch(self, kwargs: dict[str, Any]) -> str:
        """여러 후보 상표명 일괄 검사."""
        names_str = kwargs.get("names", "")
        if not names_str:
            return "검사할 상표명 목록(names)을 입력해주세요. 예: names='CORTHEX,코텍스,CORTEX HQ'"

        names = [n.strip() for n in names_str.split(",") if n.strip()]
        if not names:
            return "유효한 상표명이 없습니다."

        lines = ["## 상표 일괄 유사도 검사\n"]
        lines.append(f"검사 대상: {len(names)}건\n")
        lines.append("| 후보 상표명 | 가장 유사한 기존 상표 | 종합 점수 | 위험도 |")
        lines.append("|------------|---------------------|----------|--------|")

        results_detail: list[str] = []

        for name in names:
            existing_marks = await self._search_trademarks(name)

            if not existing_marks:
                lines.append(f"| {name} | (유사 상표 없음) | 0% | 안전 |")
                continue

            best_score = 0.0
            best_mark = ""
            for mark in existing_marks[:5]:
                mark_name = mark.get("title", mark.get("상표명", ""))
                if not mark_name:
                    continue
                text_sim = self._levenshtein_similarity(name, mark_name)
                pron_sim = self._pronunciation_similarity(name, mark_name)
                appearance_sim = self._appearance_similarity(name, mark_name)
                total = text_sim * 0.4 + pron_sim * 0.4 + appearance_sim * 0.2
                score = round(total * 100, 1)
                if score > best_score:
                    best_score = score
                    best_mark = mark_name

            risk = self._risk_level(best_score)
            lines.append(f"| {name} | {best_mark} | {best_score}% | {risk} |")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 상표 전문 변리사입니다.\n"
                "여러 후보 상표의 유사도 검사 결과를 비교 분석하세요:\n"
                "1. 가장 안전한(등록 가능성 높은) 상표명 추천\n"
                "2. 피해야 할 상표명과 그 이유\n"
                "3. 추가 대안 상표명 제안\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"{formatted}\n\n---\n\n## 종합 비교 분석\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  유사도 알고리즘 (3가지)
    # ══════════════════════════════════════════

    # ── 1) 글자 유사도 (Levenshtein Distance) ──

    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        """DP(동적프로그래밍)로 편집 거리 계산."""
        len1, len2 = len(s1), len(s2)
        # dp[i][j] = s1[:i]와 s2[:j]의 편집 거리
        dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]

        for i in range(len1 + 1):
            dp[i][0] = i
        for j in range(len2 + 1):
            dp[0][j] = j

        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if s1[i - 1] == s2[j - 1] else 1
                dp[i][j] = min(
                    dp[i - 1][j] + 1,      # 삭제
                    dp[i][j - 1] + 1,      # 삽입
                    dp[i - 1][j - 1] + cost,  # 교체
                )

        return dp[len1][len2]

    @classmethod
    def _levenshtein_similarity(cls, s1: str, s2: str) -> float:
        """편집 거리 기반 유사도 (0.0 ~ 1.0)."""
        if not s1 and not s2:
            return 1.0
        max_len = max(len(s1), len(s2))
        if max_len == 0:
            return 1.0
        distance = cls._levenshtein_distance(s1.lower(), s2.lower())
        return 1.0 - (distance / max_len)

    # ── 2) 발음 유사도 (한글 자모 분리 비교) ──

    @staticmethod
    def _decompose_hangul(text: str) -> str:
        """한글 문자열을 초성+중성+종성 자모로 분해.

        예: "코텍스" → "ㅋㅗㅌㅔㄱㅅㅡ"
        """
        result: list[str] = []
        for ch in text:
            code = ord(ch)
            if 0xAC00 <= code <= 0xD7A3:
                # 한글 음절 분해
                offset = code - 0xAC00
                cho_idx = offset // (21 * 28)
                jung_idx = (offset % (21 * 28)) // 28
                jong_idx = offset % 28

                result.append(CHOSUNG[cho_idx])
                result.append(JUNGSUNG[jung_idx])
                if jong_idx > 0:
                    result.append(JONGSUNG[jong_idx])
            else:
                # 한글이 아닌 문자는 그대로
                result.append(ch.lower())

        return "".join(result)

    @classmethod
    def _pronunciation_similarity(cls, s1: str, s2: str) -> float:
        """자모 분리 후 편집 거리 기반 발음 유사도 (0.0 ~ 1.0)."""
        decomp1 = cls._decompose_hangul(s1)
        decomp2 = cls._decompose_hangul(s2)
        return cls._levenshtein_similarity(decomp1, decomp2)

    # ── 3) 외관 유사도 (영문 변환 비교) ──

    @classmethod
    def _to_romanized(cls, text: str) -> str:
        """한글을 로마자 발음으로 변환.

        예: "코텍스" → "kotekseu"
        """
        decomposed = cls._decompose_hangul(text)
        result: list[str] = []
        for ch in decomposed:
            if ch in _KO_TO_EN:
                result.append(_KO_TO_EN[ch])
            else:
                result.append(ch.lower())
        return "".join(result)

    @classmethod
    def _appearance_similarity(cls, s1: str, s2: str) -> float:
        """외관 유사도: 대소문자 무시 + 한글↔영문 발음 변환 비교."""
        # 1) 영문 대소문자 무시 직접 비교
        direct_sim = cls._levenshtein_similarity(s1.lower(), s2.lower())

        # 2) 한글→영문 발음 변환 후 비교
        roman1 = cls._to_romanized(s1)
        roman2 = cls._to_romanized(s2)
        roman_sim = cls._levenshtein_similarity(roman1, roman2)

        # 둘 중 더 높은 유사도 사용
        return max(direct_sim, roman_sim)

    # ── 위험 수준 판정 ──

    @staticmethod
    def _risk_level(score: float) -> str:
        """종합 점수에 따른 위험 수준 판정."""
        if score >= 80:
            return "위험 -- 등록 거절 가능성 매우 높음"
        elif score >= 60:
            return "주의 -- 유사 상표 존재, 전문가 검토 필요"
        elif score >= 40:
            return "보통 -- 일부 유사성 있으나 구분 가능"
        else:
            return "안전 -- 유사 상표 없음"

    # ── KIPRIS 상표 검색 ──

    async def _search_trademarks(self, query: str) -> list[dict[str, str]]:
        """KIPRIS API로 유사 상표 검색."""
        api_key = os.getenv("KIPRIS_API_KEY", "")
        if not api_key:
            logger.warning("[상표유사도] KIPRIS_API_KEY 미설정")
            return []

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{KIPRIS_BASE}/trademarkInfoSearchService/getAdvancedSearch",
                    params={
                        "ServiceKey": api_key,
                        "searchString": query,
                        "numOfRows": "20",
                        "pageNo": "1",
                    },
                    timeout=20,
                )
        except httpx.HTTPError as e:
            logger.warning("[상표유사도] KIPRIS 호출 실패: %s", e)
            return []

        if resp.status_code != 200:
            logger.warning("[상표유사도] KIPRIS HTTP %d", resp.status_code)
            return []

        return self._parse_trademark_xml(resp.text)

    def _parse_trademark_xml(self, xml_text: str) -> list[dict[str, str]]:
        """KIPRIS 상표 검색 XML 응답 파싱."""
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.error("[상표유사도] XML 파싱 실패")
            return []

        items: list[dict[str, str]] = []
        for tag_name in ("item", "TrademarkInfo"):
            for elem in root.iter(tag_name):
                item: dict[str, str] = {}
                for child in elem:
                    if child.text:
                        item[child.tag] = child.text.strip()
                if item:
                    items.append(item)
        return items
