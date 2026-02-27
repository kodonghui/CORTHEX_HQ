"""
법령/판례 검색 Tool.

국가법령정보센터 Open API를 사용하여
법령 조문과 판례를 검색합니다.

사용 방법:
  - action="law": 법령 검색 (법률명, 조문 키워드)
  - action="precedent": 판례 검색 (키워드, 법원, 사건유형)

필요 환경변수:
  - LAW_API_KEY: 법제처 (https://open.law.go.kr/) 무료 발급
"""
from __future__ import annotations

import logging
import os
from typing import Any
from xml.etree import ElementTree

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.law_search")

LAW_API_BASE = "https://www.law.go.kr/DRF/lawSearch.do"


class LawSearchTool(BaseTool):
    """국가법령정보센터 법령/판례 검색 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "law")

        if action == "law":
            return await self._search_law(kwargs)
        elif action == "precedent":
            return await self._search_precedent(kwargs)
        else:
            return f"알 수 없는 action: {action}. law 또는 precedent를 사용하세요."

    # ── 법령 검색 ──

    async def _search_law(self, kwargs: dict[str, Any]) -> str:
        api_key = os.getenv("LAW_API_KEY")
        if not api_key:
            return self._key_msg()

        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요. 예: query='저작권법', query='개인정보 보호'"

        display = int(kwargs.get("size", 10))

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    LAW_API_BASE,
                    params={
                        "OC": api_key,
                        "target": "law",
                        "type": "XML",
                        "query": query,
                        "display": str(display),
                    },
                    timeout=15,
                )
        except httpx.HTTPError as e:
            return f"법령정보 API 호출 실패: {e}"

        if resp.status_code != 200:
            return f"법령정보 API 오류 ({resp.status_code}): {resp.text[:200]}"

        # XML 파싱
        items = self._parse_law_xml(resp.text)

        if not items:
            return f"'{query}' 관련 법령을 찾을 수 없습니다."

        lines = [f"### 법령 검색 결과: '{query}' ({len(items)}건)"]
        for i, item in enumerate(items, 1):
            lines.append(
                f"  [{i}] {item.get('법령명한글', '')}\n"
                f"      시행일: {item.get('시행일자', '')} | "
                f"법령구분: {item.get('법령구분명', '')}\n"
                f"      소관부처: {item.get('소관부처명', '')}"
            )

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 법률 리서치 전문가입니다.\n"
                "법령 검색 결과를 분석하여 다음을 정리하세요:\n"
                "1. 가장 관련성 높은 법령 2~3개 선정 및 핵심 내용 요약\n"
                "2. 해당 법령의 주요 조문 (추정)\n"
                "3. 사업/서비스에 적용되는 법적 요건\n"
                "4. 주의해야 할 법적 리스크\n"
                "주의: 이 분석은 참고용이며, 실제 법률 문제는 변호사와 상담하세요.\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 법령 검색\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 판례 검색 ──

    async def _search_precedent(self, kwargs: dict[str, Any]) -> str:
        api_key = os.getenv("LAW_API_KEY")
        if not api_key:
            return self._key_msg()

        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요. 예: query='저작권 침해', query='영업비밀'"

        display = int(kwargs.get("size", 10))

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    LAW_API_BASE,
                    params={
                        "OC": api_key,
                        "target": "prec",
                        "type": "XML",
                        "query": query,
                        "display": str(display),
                    },
                    timeout=15,
                )
        except httpx.HTTPError as e:
            return f"판례 검색 API 호출 실패: {e}"

        if resp.status_code != 200:
            return f"판례 검색 오류 ({resp.status_code}): {resp.text[:200]}"

        # XML 파싱
        items = self._parse_precedent_xml(resp.text)

        if not items:
            return f"'{query}' 관련 판례를 찾을 수 없습니다."

        lines = [f"### 판례 검색 결과: '{query}' ({len(items)}건)"]
        for i, item in enumerate(items, 1):
            lines.append(
                f"  [{i}] {item.get('사건명', '')}\n"
                f"      사건번호: {item.get('사건번호', '')} | "
                f"선고일: {item.get('선고일자', '')}\n"
                f"      법원: {item.get('법원명', '')} | "
                f"판결유형: {item.get('판결유형', '')}"
            )

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 판례 분석 전문가입니다.\n"
                "판례 검색 결과를 분석하여 다음을 정리하세요:\n"
                "1. 주요 판례 2~3개 선정 및 판시 사항 요약\n"
                "2. 판례에서 도출되는 법적 원칙/기준\n"
                "3. 유사 사건에 적용할 수 있는 시사점\n"
                "주의: 이 분석은 참고용이며, 실제 법률 문제는 변호사와 상담하세요.\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 판례 검색\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── XML 파싱 ──

    def _parse_law_xml(self, xml_text: str) -> list[dict[str, str]]:
        """법령 검색 XML 결과를 딕셔너리 리스트로 변환."""
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.error("[LawSearch] XML 파싱 실패")
            return []

        items = []
        for law in root.iter("law"):
            item: dict[str, str] = {}
            for child in law:
                if child.text:
                    item[child.tag] = child.text.strip()
            if item:
                items.append(item)
        return items

    def _parse_precedent_xml(self, xml_text: str) -> list[dict[str, str]]:
        """판례 검색 XML 결과를 딕셔너리 리스트로 변환."""
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.error("[LawSearch] 판례 XML 파싱 실패")
            return []

        items = []
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
    def _key_msg() -> str:
        return (
            "LAW_API_KEY가 설정되지 않았습니다.\n"
            "국가법령정보센터(https://open.law.go.kr/)에서 "
            "무료 인증키를 발급받은 뒤 .env에 추가하세요.\n"
            "예: LAW_API_KEY=your-law-api-key"
        )
