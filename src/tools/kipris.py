"""
KIPRIS 특허/상표 검색 Tool.

특허정보원 KIPRIS Plus API를 사용하여
특허, 상표, 디자인을 검색하고 분석합니다.

사용 방법:
  - action="patent": 특허 검색 (키워드, 출원인)
  - action="trademark": 상표 검색 (상표명, 출원인)
  - action="design": 디자인 검색

필요 환경변수:
  - KIPRIS_API_KEY: 특허정보원 (http://plus.kipris.or.kr/) 무료 발급
"""
from __future__ import annotations

import logging
import os
from typing import Any
from xml.etree import ElementTree

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.kipris")

KIPRIS_BASE = "http://plus.kipris.or.kr/kipo-api/kipi"


class KiprisTool(BaseTool):
    """KIPRIS 특허/상표/디자인 검색 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "patent")

        if action == "patent":
            return await self._search_patent(kwargs)
        elif action == "trademark":
            return await self._search_trademark(kwargs)
        elif action == "design":
            return await self._search_design(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "patent, trademark, design 중 하나를 사용하세요."
            )

    # ── 특허 검색 ──

    async def _search_patent(self, kwargs: dict[str, Any]) -> str:
        api_key = os.getenv("KIPRIS_API_KEY")
        if not api_key:
            return self._key_msg()

        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요. 예: query='AI 교육 시스템', query='자연어 처리'"

        num_of_rows = int(kwargs.get("size", 10))

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{KIPRIS_BASE}/patUtiModInfoSearchSevice/getAdvancedSearch",
                    params={
                        "ServiceKey": api_key,
                        "word": query,
                        "numOfRows": str(num_of_rows),
                        "pageNo": "1",
                    },
                    timeout=20,
                )
        except httpx.HTTPError as e:
            return f"KIPRIS API 호출 실패: {e}"

        if resp.status_code == 401 or resp.status_code == 403:
            return "KIPRIS API 인증 실패. KIPRIS_API_KEY를 확인하세요."

        if resp.status_code != 200:
            return f"KIPRIS API 오류 ({resp.status_code}): {resp.text[:200]}"

        items = self._parse_patent_xml(resp.text)

        if not items:
            return f"'{query}' 관련 특허를 찾을 수 없습니다."

        lines = [f"### 특허 검색 결과: '{query}' ({len(items)}건)"]
        for i, item in enumerate(items, 1):
            lines.append(
                f"  [{i}] {item.get('inventionTitle', '제목 없음')}\n"
                f"      출원번호: {item.get('applicationNumber', '')} | "
                f"출원일: {item.get('applicationDate', '')}\n"
                f"      출원인: {item.get('applicantName', '')} | "
                f"IPC: {item.get('ipcNumber', '')}"
            )

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 특허 분석 전문가입니다.\n"
                "특허 검색 결과를 분석하여 다음을 정리하세요:\n"
                "1. 주요 특허 2~3개의 핵심 기술 내용 요약\n"
                "2. 기술 동향/트렌드 분석\n"
                "3. 유사 기술의 특허 침해 가능성 판단\n"
                "4. 우리 사업에 대한 시사점 (기회/위협)\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 특허 검색\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 상표 검색 ──

    async def _search_trademark(self, kwargs: dict[str, Any]) -> str:
        api_key = os.getenv("KIPRIS_API_KEY")
        if not api_key:
            return self._key_msg()

        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요. 예: query='CORTHEX', query='리트마스터'"

        num_of_rows = int(kwargs.get("size", 10))

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{KIPRIS_BASE}/trademarkInfoSearchService/getAdvancedSearch",
                    params={
                        "ServiceKey": api_key,
                        "searchString": query,
                        "numOfRows": str(num_of_rows),
                        "pageNo": "1",
                    },
                    timeout=20,
                )
        except httpx.HTTPError as e:
            return f"KIPRIS 상표 검색 실패: {e}"

        if resp.status_code != 200:
            return f"KIPRIS 오류 ({resp.status_code}): {resp.text[:200]}"

        items = self._parse_trademark_xml(resp.text)

        if not items:
            return f"'{query}' 관련 상표를 찾을 수 없습니다."

        lines = [f"### 상표 검색 결과: '{query}' ({len(items)}건)"]
        for i, item in enumerate(items, 1):
            lines.append(
                f"  [{i}] {item.get('title', '제목 없음')}\n"
                f"      출원번호: {item.get('applicationNumber', '')} | "
                f"출원일: {item.get('applicationDate', '')}\n"
                f"      출원인: {item.get('applicantName', '')} | "
                f"상태: {item.get('applicationStatus', '')}"
            )

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 상표 분석 전문가입니다.\n"
                "상표 검색 결과를 분석하여 다음을 정리하세요:\n"
                "1. 유사 상표 존재 여부 및 충돌 가능성\n"
                "2. 상표 등록 가능성 판단\n"
                "3. 주의해야 할 기존 상표\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 상표 검색\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 디자인 검색 ──

    async def _search_design(self, kwargs: dict[str, Any]) -> str:
        api_key = os.getenv("KIPRIS_API_KEY")
        if not api_key:
            return self._key_msg()

        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요."

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{KIPRIS_BASE}/designInfoSearchService/getAdvancedSearch",
                    params={
                        "ServiceKey": api_key,
                        "word": query,
                        "numOfRows": "10",
                        "pageNo": "1",
                    },
                    timeout=20,
                )
        except httpx.HTTPError as e:
            return f"KIPRIS 디자인 검색 실패: {e}"

        if resp.status_code != 200:
            return f"KIPRIS 오류 ({resp.status_code}): {resp.text[:200]}"

        items = self._parse_generic_xml(resp.text)

        if not items:
            return f"'{query}' 관련 디자인 등록을 찾을 수 없습니다."

        lines = [f"### 디자인 검색 결과: '{query}' ({len(items)}건)"]
        for i, item in enumerate(items, 1):
            title = item.get("articleName", item.get("title", "제목 없음"))
            lines.append(f"  [{i}] {title}")
            for k, v in item.items():
                if k not in ("articleName", "title"):
                    lines.append(f"      {k}: {v}")

        return "\n".join(lines)

    # ── XML 파싱 ──

    def _parse_patent_xml(self, xml_text: str) -> list[dict[str, str]]:
        """특허 검색 XML을 딕셔너리 리스트로 변환."""
        return self._parse_generic_xml(xml_text)

    def _parse_trademark_xml(self, xml_text: str) -> list[dict[str, str]]:
        """상표 검색 XML을 딕셔너리 리스트로 변환."""
        return self._parse_generic_xml(xml_text)

    def _parse_generic_xml(self, xml_text: str) -> list[dict[str, str]]:
        """KIPRIS XML 응답을 범용적으로 파싱."""
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.error("[KIPRIS] XML 파싱 실패")
            return []

        items = []
        # body/items/item 구조 탐색
        for item_tag in ("item", "PatentUtilityInfo", "TrademarkInfo", "DesignInfo"):
            for elem in root.iter(item_tag):
                item: dict[str, str] = {}
                for child in elem:
                    if child.text:
                        item[child.tag] = child.text.strip()
                if item:
                    items.append(item)

        return items

    # ── 유틸 ──

    @staticmethod
    def _key_msg() -> str:
        return (
            "KIPRIS_API_KEY가 설정되지 않았습니다.\n"
            "특허정보원 KIPRIS Plus(http://plus.kipris.or.kr/)에서 "
            "무료 인증키를 발급받은 뒤 .env에 추가하세요.\n"
            "예: KIPRIS_API_KEY=your-kipris-api-key"
        )
