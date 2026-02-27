"""
판례 트렌드 분석 Tool.

특정 법률 분야의 판례를 대량 수집하여
판결 경향(트렌드)을 분석합니다.

사용 방법:
  - action="analyze": 판례 트렌드 분석 (연도별 건수, 승소율 등)
  - action="summary": 특정 판례 요약
  - action="risk": 특정 사업/행위의 법적 리스크 분석

필요 환경변수: 없음 (법제처 API는 무료, 키 불필요)
의존 라이브러리: httpx

주의: 이 도구의 분석은 참고용이며, 실제 법률 문제는 변호사와 상담하세요.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any
from xml.etree import ElementTree

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.precedent_analyzer")

LAW_API_BASE = "https://www.law.go.kr/DRF/lawSearch.do"
_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 분석은 참고용이며, "
    "실제 법률 문제는 반드시 변호사와 상담하세요."
)


class PrecedentAnalyzerTool(BaseTool):
    """판례 트렌드 분석 도구 (CLO 법무IP처 소속)."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "analyze")

        if action == "analyze":
            return await self._analyze_trend(kwargs)
        elif action == "summary":
            return await self._summarize_case(kwargs)
        elif action == "risk":
            return await self._assess_risk(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "analyze, summary, risk 중 하나를 사용하세요."
            )

    # ── 판례 트렌드 분석 ──

    async def _analyze_trend(self, kwargs: dict[str, Any]) -> str:
        """판례 트렌드 분석: 연도별 건수, 승소율, 배상금, 키워드 등."""
        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요. 예: query='저작권 침해', query='개인정보 유출'"

        years = int(kwargs.get("years", 5))
        count = int(kwargs.get("count", 50))

        # 판례 대량 수집
        cases = await self._fetch_precedents(query, count)

        if not cases:
            return f"'{query}' 관련 판례를 찾을 수 없습니다."

        # 분석 수행
        now_year = datetime.now().year
        cutoff_year = now_year - years

        # 1) 연도별 건수
        yearly_counts: dict[int, int] = defaultdict(int)
        for case in cases:
            date_str = case.get("선고일자", "")
            year = self._extract_year(date_str)
            if year and year >= cutoff_year:
                yearly_counts[year] += 1

        # 2) 판결 유형 분류 (원고 승/패)
        plaintiff_win = 0
        defendant_win = 0
        for case in cases:
            result = case.get("판결유형", "") + case.get("사건명", "")
            if any(kw in result for kw in ["인용", "승소", "원고승"]):
                plaintiff_win += 1
            elif any(kw in result for kw in ["기각", "각하", "패소", "피고승"]):
                defendant_win += 1

        # 3) 금액 추출 (배상금)
        amounts: list[int] = []
        for case in cases:
            text = case.get("판시사항", "") + case.get("사건명", "")
            found = re.findall(r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:만원|원)", text)
            for amt_str in found:
                cleaned = amt_str.replace(",", "").split(".")[0]
                if cleaned.isdigit():
                    amounts.append(int(cleaned))

        # 4) 자주 인용되는 법 조문
        statute_refs: list[str] = []
        for case in cases:
            text = case.get("판시사항", "") + case.get("참조조문", "")
            refs = re.findall(r"(?:제\d+조(?:의\d+)?)", text)
            statute_refs.extend(refs)
        statute_counter = Counter(statute_refs).most_common(10)

        # 5) 핵심 키워드 빈도
        all_text = " ".join(
            case.get("판시사항", "") + " " + case.get("사건명", "")
            for case in cases
        )
        # 2글자 이상 한글 단어 추출
        words = re.findall(r"[가-힣]{2,}", all_text)
        # 불용어 제외
        stopwords = {"대하여", "있는", "하는", "것으로", "경우", "사건", "대한", "의한", "관한", "있다", "없다", "이에", "같은", "위한", "따른", "에서"}
        words = [w for w in words if w not in stopwords]
        keyword_counter = Counter(words).most_common(15)

        # 결과 포맷
        lines = [f"## 판례 트렌드 분석: '{query}'\n"]
        lines.append(f"분석 대상: {len(cases)}건 (최근 {years}년)\n")

        # 연도별 건수 표
        lines.append("### 연도별 판례 건수")
        lines.append("| 연도 | 건수 |")
        lines.append("|------|------|")
        for yr in sorted(yearly_counts.keys()):
            lines.append(f"| {yr} | {yearly_counts[yr]}건 |")

        # 승소율
        total_judged = plaintiff_win + defendant_win
        lines.append(f"\n### 판결 결과 분포")
        if total_judged > 0:
            lines.append(f"- 원고 승소(인용): {plaintiff_win}건 ({plaintiff_win / total_judged * 100:.1f}%)")
            lines.append(f"- 피고 승소(기각/각하): {defendant_win}건 ({defendant_win / total_judged * 100:.1f}%)")
        else:
            lines.append("- 판결 유형 정보 부족")

        # 배상금
        if amounts:
            lines.append(f"\n### 배상금 정보")
            lines.append(f"- 평균: {sum(amounts) / len(amounts):,.0f}원")
            lines.append(f"- 최소: {min(amounts):,}원 / 최대: {max(amounts):,}원")

        # 자주 인용 조문
        if statute_counter:
            lines.append(f"\n### 자주 인용되는 법 조문 (상위 {len(statute_counter)}개)")
            for ref, cnt in statute_counter:
                lines.append(f"- {ref}: {cnt}회")

        # 핵심 키워드
        if keyword_counter:
            lines.append(f"\n### 핵심 키워드 (상위 {len(keyword_counter)}개)")
            for kw, cnt in keyword_counter:
                lines.append(f"- {kw}: {cnt}회")

        formatted = "\n".join(lines)

        # LLM 종합 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 법률 트렌드 분석 전문가입니다.\n"
                "판례 통계 데이터를 기반으로 다음을 분석하세요:\n\n"
                "1. **법적 트렌드 요약**: 판례 증감 추이, 법원 판단 경향\n"
                "2. **사업 리스크 평가**: 이 분야에서 소송 위험도\n"
                "3. **대응 전략 제안**: 사전 예방 조치, 계약서 보완 사항\n"
                "4. **주목할 판례**: 특히 중요한 판례 2~3건 언급\n\n"
                "한국어로 구체적으로 답변하세요.\n"
                "주의: 이 분석은 참고용이며, 실제 법률 문제는 변호사와 상담하세요."
            ),
            user_prompt=f"검색 키워드: {query}\n\n{formatted}",
        )

        return f"{formatted}\n\n---\n\n## 종합 분석\n\n{analysis}{_DISCLAIMER}"

    # ── 특정 판례 요약 ──

    async def _summarize_case(self, kwargs: dict[str, Any]) -> str:
        """특정 판례 번호로 판례를 요약."""
        case_id = kwargs.get("case_id", "")
        if not case_id:
            return "판례 번호(case_id)를 입력해주세요. 예: case_id='2023다12345'"

        # 판례 검색
        cases = await self._fetch_precedents(case_id, 5)

        if not cases:
            return f"'{case_id}' 판례를 찾을 수 없습니다."

        # 가장 관련도 높은 판례 선택
        target = cases[0]
        case_text = "\n".join(f"- {k}: {v}" for k, v in target.items() if v)

        summary = await self._llm_call(
            system_prompt=(
                "당신은 판례 분석 전문가입니다.\n"
                "주어진 판례를 다음 구조로 요약하세요:\n\n"
                "1. **사건 개요**: 당사자, 사건 경위\n"
                "2. **쟁점**: 핵심 법적 쟁점\n"
                "3. **판결 요지**: 법원의 판단 결과\n"
                "4. **시사점**: 이 판례의 의미와 영향\n\n"
                "한국어로 답변하세요.\n"
                "주의: 이 요약은 참고용이며, 실제 법률 문제는 변호사와 상담하세요."
            ),
            user_prompt=case_text,
        )

        return f"## 판례 요약: {case_id}\n\n{summary}{_DISCLAIMER}"

    # ── 법적 리스크 분석 ──

    async def _assess_risk(self, kwargs: dict[str, Any]) -> str:
        """특정 사업/행위의 법적 리스크 분석."""
        topic = kwargs.get("topic", "")
        if not topic:
            return "분석 주제(topic)를 입력해주세요. 예: topic='AI 생성 콘텐츠 저작권'"

        # 관련 판례 수집
        cases = await self._fetch_precedents(topic, 30)

        # 리스크 수준 판정
        case_count = len(cases)
        if case_count >= 20:
            risk_level = "상 (높음)"
            risk_desc = "관련 판례가 다수 존재하여 소송 위험이 높은 분야입니다."
        elif case_count >= 5:
            risk_level = "중 (보통)"
            risk_desc = "관련 판례가 일부 존재하며, 주의가 필요한 분야입니다."
        else:
            risk_level = "하 (낮음)"
            risk_desc = "관련 판례가 적어 법적 분쟁이 빈번하지 않은 분야입니다."

        lines = [f"## 법적 리스크 분석: '{topic}'\n"]
        lines.append(f"- 관련 판례 수: {case_count}건")
        lines.append(f"- 리스크 수준: **{risk_level}**")
        lines.append(f"- 판단 근거: {risk_desc}")

        if cases:
            lines.append(f"\n### 주요 관련 판례 (상위 5건)")
            for i, case in enumerate(cases[:5], 1):
                lines.append(
                    f"  [{i}] {case.get('사건명', '제목 없음')}\n"
                    f"      사건번호: {case.get('사건번호', '')} | "
                    f"선고일: {case.get('선고일자', '')}"
                )

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 법률 리스크 평가 전문가입니다.\n"
                "주어진 주제와 관련 판례를 기반으로 다음을 분석하세요:\n\n"
                "1. **핵심 법적 리스크**: 이 사업/행위에서 발생 가능한 법적 문제\n"
                "2. **관련 법률**: 적용되는 주요 법률/조문\n"
                "3. **사전 대비 방안**: 리스크를 줄이기 위한 구체적 조치\n"
                "4. **최악의 시나리오**: 법적 분쟁 시 예상되는 결과\n"
                "5. **권고사항**: CEO에게 드리는 실질적 조언\n\n"
                "한국어로 구체적으로 답변하세요.\n"
                "주의: 이 분석은 참고용이며, 실제 법률 문제는 변호사와 상담하세요."
            ),
            user_prompt=f"분석 주제: {topic}\n\n{formatted}",
        )

        return f"{formatted}\n\n---\n\n## 상세 리스크 분석\n\n{analysis}{_DISCLAIMER}"

    # ── 판례 수집 (법제처 API) ──

    async def _fetch_precedents(self, query: str, count: int) -> list[dict[str, str]]:
        """법제처 API에서 판례를 대량 수집."""
        all_cases: list[dict[str, str]] = []
        page_size = min(count, 20)
        total_pages = (count + page_size - 1) // page_size

        try:
            async with httpx.AsyncClient() as client:
                for page in range(1, total_pages + 1):
                    resp = await client.get(
                        LAW_API_BASE,
                        params={
                            "OC": "test",
                            "target": "prec",
                            "type": "XML",
                            "query": query,
                            "display": str(page_size),
                            "page": str(page),
                        },
                        timeout=15,
                    )
                    if resp.status_code != 200:
                        logger.warning("[판례분석] API HTTP %d (페이지 %d)", resp.status_code, page)
                        break

                    cases = self._parse_precedent_xml(resp.text)
                    if not cases:
                        break

                    all_cases.extend(cases)

                    if len(all_cases) >= count:
                        break

        except httpx.HTTPError as e:
            logger.warning("[판례분석] API 호출 실패: %s", e)

        logger.info("[판례분석] '%s' → %d건 수집", query, len(all_cases))
        return all_cases[:count]

    # ── XML 파싱 ──

    def _parse_precedent_xml(self, xml_text: str) -> list[dict[str, str]]:
        """판례 XML 응답을 딕셔너리 리스트로 변환."""
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.error("[판례분석] XML 파싱 실패")
            return []

        items: list[dict[str, str]] = []
        for prec in root.iter("prec"):
            item: dict[str, str] = {}
            for child in prec:
                if child.text:
                    item[child.tag] = child.text.strip()
            if item:
                items.append(item)
        return items

    # ── 유틸 ──

    @staticmethod
    def _extract_year(date_str: str) -> int | None:
        """날짜 문자열에서 연도 추출."""
        match = re.search(r"(\d{4})", date_str)
        if match:
            return int(match.group(1))
        return None
