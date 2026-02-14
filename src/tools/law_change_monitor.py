"""
법령 변경 알리미 Tool.

관련 법령의 개정/신설/폐지를 자동 감지하고,
사업에 미치는 영향을 분석합니다.

사용 방법:
  - action="watch": 감시 법령 등록
  - action="unwatch": 감시 해제
  - action="check": 등록된 법령의 변경사항 확인
  - action="list": 감시 중인 법령 목록
  - action="recent": 최근 개정된 주요 법령 목록

필요 환경변수: 없음 (법제처 API 무료)
의존 라이브러리: httpx

주의: 이 분석은 참고용이며, 실제 법률 문제는 변호사와 상담하세요.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.law_change_monitor")

LAW_API_BASE = "https://www.law.go.kr/DRF/lawSearch.do"
WATCHLIST_PATH = Path("data/law_watchlist.json")

_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 분석은 참고용이며, "
    "실제 법률 문제는 반드시 변호사와 상담하세요."
)

# 법령 카테고리 매핑
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "교육": ["교육", "학교", "대학", "학원", "평생교육", "직업훈련"],
    "정보통신": ["정보통신", "전자상거래", "개인정보", "저작권", "인터넷", "소프트웨어", "AI", "데이터"],
    "금융": ["금융", "은행", "보험", "증권", "투자", "자본시장"],
}


class LawChangeMonitorTool(BaseTool):
    """법령 변경 알리미 도구 (CLO 법무IP처 소속)."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "check")

        if action == "watch":
            return await self._watch(kwargs)
        elif action == "unwatch":
            return await self._unwatch(kwargs)
        elif action == "check":
            return await self._check(kwargs)
        elif action == "list":
            return self._list_watched()
        elif action == "recent":
            return await self._recent(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "watch, unwatch, check, list, recent 중 하나를 사용하세요."
            )

    # ── 감시 법령 등록 ──

    async def _watch(self, kwargs: dict[str, Any]) -> str:
        """감시 법령 등록."""
        law_name = kwargs.get("law_name", "")
        if not law_name:
            return "감시할 법령명(law_name)을 입력해주세요. 예: law_name='저작권법'"

        watchlist = self._load_watchlist()

        # 이미 등록되어 있는지 확인
        for item in watchlist:
            if item["law_name"] == law_name:
                return f"'{law_name}'은(는) 이미 감시 목록에 있습니다."

        # 법제처 API에서 현재 법령 정보 조회
        law_info = await self._fetch_law_info(law_name)

        entry = {
            "law_name": law_name,
            "last_revision": law_info.get("시행일자", ""),
            "law_id": law_info.get("법령ID", ""),
            "law_type": law_info.get("법령구분명", ""),
            "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        watchlist.append(entry)
        self._save_watchlist(watchlist)

        return (
            f"## 법령 감시 등록 완료\n\n"
            f"- 법령명: **{law_name}**\n"
            f"- 법령 구분: {entry['law_type']}\n"
            f"- 현재 시행일: {entry['last_revision']}\n"
            f"- 등록 일시: {entry['registered_at']}\n\n"
            f"현재 감시 중인 법령: {len(watchlist)}건"
        )

    # ── 감시 해제 ──

    async def _unwatch(self, kwargs: dict[str, Any]) -> str:
        """감시 해제."""
        law_name = kwargs.get("law_name", "")
        if not law_name:
            return "해제할 법령명(law_name)을 입력해주세요."

        watchlist = self._load_watchlist()
        original_len = len(watchlist)
        watchlist = [item for item in watchlist if item["law_name"] != law_name]

        if len(watchlist) == original_len:
            return f"'{law_name}'은(는) 감시 목록에 없습니다."

        self._save_watchlist(watchlist)
        return f"'{law_name}' 감시를 해제했습니다. 남은 감시 법령: {len(watchlist)}건"

    # ── 변경사항 확인 ──

    async def _check(self, kwargs: dict[str, Any]) -> str:
        """등록된 법령의 변경사항 확인."""
        watchlist = self._load_watchlist()

        if not watchlist:
            return (
                "감시 중인 법령이 없습니다.\n"
                "먼저 action='watch', law_name='법령명'으로 등록해주세요."
            )

        lines = ["## 법령 변경사항 확인\n"]
        lines.append(f"감시 중인 법령: {len(watchlist)}건\n")
        lines.append(f"확인 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

        changes_found: list[dict] = []
        no_change: list[str] = []

        for item in watchlist:
            law_name = item["law_name"]
            saved_revision = item.get("last_revision", "")

            # 현재 법령 정보 조회
            current_info = await self._fetch_law_info(law_name)
            current_revision = current_info.get("시행일자", "")

            if current_revision and current_revision != saved_revision:
                changes_found.append({
                    "law_name": law_name,
                    "old_revision": saved_revision,
                    "new_revision": current_revision,
                    "info": current_info,
                })
                # 감시 목록 업데이트
                item["last_revision"] = current_revision
            else:
                no_change.append(law_name)

        # 변경 목록 업데이트 저장
        if changes_found:
            self._save_watchlist(watchlist)

        # 변경 감지 결과
        if changes_found:
            lines.append(f"### [변경 감지] {len(changes_found)}건\n")
            for c in changes_found:
                lines.append(f"**{c['law_name']}**")
                lines.append(f"  - 이전 시행일: {c['old_revision']}")
                lines.append(f"  - 현재 시행일: {c['new_revision']}")
                lines.append(f"  - 소관부처: {c['info'].get('소관부처명', '미확인')}")
                lines.append("")
        else:
            lines.append("### 변경 감지: 없음\n")

        if no_change:
            lines.append(f"### 변경 없음 ({len(no_change)}건)")
            for name in no_change:
                lines.append(f"  - {name}")

        formatted = "\n".join(lines)

        # 변경 사항이 있으면 LLM 분석 추가
        if changes_found:
            change_summary = "\n".join(
                f"- {c['law_name']}: {c['old_revision']} → {c['new_revision']}"
                for c in changes_found
            )
            analysis = await self._llm_call(
                system_prompt=(
                    "당신은 법률 변경 영향 분석 전문가입니다.\n"
                    "법령 개정 사항을 분석하여 다음을 답변하세요:\n\n"
                    "1. **개정 내용 추정**: 이 법령이 개정된 주요 이유/배경\n"
                    "2. **사업 영향 분석**: 우리 사업(교육 서비스)에 미치는 영향\n"
                    "3. **필요 조치**: 개정에 대응하기 위해 해야 할 일\n"
                    "4. **시급도 판단**: 즉시/1개월내/3개월내 중 어느 수준인지\n\n"
                    "한국어로 구체적으로 답변하세요.\n"
                    "주의: 이 분석은 참고용이며, 실제 법률 문제는 변호사와 상담하세요."
                ),
                user_prompt=f"변경된 법령:\n{change_summary}",
            )
            return f"{formatted}\n\n---\n\n## 영향 분석\n\n{analysis}{_DISCLAIMER}"

        return formatted

    # ── 감시 목록 조회 ──

    def _list_watched(self) -> str:
        """감시 중인 법령 목록 표시."""
        watchlist = self._load_watchlist()

        if not watchlist:
            return (
                "감시 중인 법령이 없습니다.\n"
                "action='watch', law_name='법령명'으로 등록해주세요."
            )

        lines = ["## 감시 중인 법령 목록\n"]
        lines.append(f"총 {len(watchlist)}건\n")
        lines.append("| # | 법령명 | 마지막 시행일 | 등록일 |")
        lines.append("|---|--------|-------------|--------|")
        for i, item in enumerate(watchlist, 1):
            lines.append(
                f"| {i} | {item['law_name']} | "
                f"{item.get('last_revision', '-')} | "
                f"{item.get('registered_at', '-')} |"
            )

        return "\n".join(lines)

    # ── 최근 개정 법령 ──

    async def _recent(self, kwargs: dict[str, Any]) -> str:
        """최근 개정된 주요 법령 목록."""
        days = int(kwargs.get("days", 30))
        category = kwargs.get("category", "전체")

        # 카테고리별 검색 키워드
        search_queries = []
        if category != "전체" and category in _CATEGORY_KEYWORDS:
            search_queries = _CATEGORY_KEYWORDS[category][:3]
        else:
            search_queries = ["교육", "정보통신", "저작권", "개인정보", "전자상거래"]

        all_laws: list[dict] = []
        for query in search_queries:
            laws = await self._search_recent_laws(query)
            all_laws.extend(laws)

        if not all_laws:
            return f"최근 {days}일간 '{category}' 분야 법령 변경을 찾을 수 없습니다."

        # 중복 제거 (법령명 기준)
        seen: set[str] = set()
        unique_laws: list[dict] = []
        for law in all_laws:
            name = law.get("법령명한글", "")
            if name and name not in seen:
                seen.add(name)
                unique_laws.append(law)

        # 시행일 기준 정렬 (최신 순)
        unique_laws.sort(key=lambda x: x.get("시행일자", ""), reverse=True)

        lines = [f"## 최근 개정 법령 ({category} 분야)\n"]
        lines.append(f"조회 범위: 최근 {days}일 / 총 {len(unique_laws)}건\n")

        lines.append("| # | 법령명 | 시행일 | 구분 | 소관부처 |")
        lines.append("|---|--------|--------|------|---------|")
        for i, law in enumerate(unique_laws[:20], 1):
            lines.append(
                f"| {i} | {law.get('법령명한글', '')} | "
                f"{law.get('시행일자', '')} | "
                f"{law.get('법령구분명', '')} | "
                f"{law.get('소관부처명', '')} |"
            )

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 법률 모니터링 전문가입니다.\n"
                "최근 개정된 법령 목록을 분석하여 다음을 답변하세요:\n\n"
                "1. **주요 법령 변경 트렌드**: 어떤 분야에서 법 개정이 활발한지\n"
                "2. **교육/IT 사업 관련**: 우리 사업에 영향을 줄 수 있는 법령\n"
                "3. **대응 권고**: 주목해야 할 법령과 이유\n\n"
                "한국어로 답변하세요.\n"
                "주의: 이 분석은 참고용이며, 실제 법률 문제는 변호사와 상담하세요."
            ),
            user_prompt=formatted,
        )

        return f"{formatted}\n\n---\n\n## 트렌드 분석\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  법제처 API 호출
    # ══════════════════════════════════════════

    async def _fetch_law_info(self, law_name: str) -> dict[str, str]:
        """법제처 API에서 법령 정보 조회."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    LAW_API_BASE,
                    params={
                        "OC": "test",
                        "target": "law",
                        "type": "XML",
                        "query": law_name,
                        "display": "1",
                    },
                    timeout=15,
                )
        except httpx.HTTPError as e:
            logger.warning("[법령알리미] API 호출 실패: %s", e)
            return {}

        if resp.status_code != 200:
            return {}

        return self._parse_first_law(resp.text)

    async def _search_recent_laws(self, query: str) -> list[dict[str, str]]:
        """법제처 API에서 법령 검색."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    LAW_API_BASE,
                    params={
                        "OC": "test",
                        "target": "law",
                        "type": "XML",
                        "query": query,
                        "display": "20",
                    },
                    timeout=15,
                )
        except httpx.HTTPError as e:
            logger.warning("[법령알리미] 법령 검색 실패: %s", e)
            return []

        if resp.status_code != 200:
            return []

        return self._parse_laws_xml(resp.text)

    # ══════════════════════════════════════════
    #  XML 파싱
    # ══════════════════════════════════════════

    def _parse_first_law(self, xml_text: str) -> dict[str, str]:
        """XML에서 첫 번째 법령 정보 추출."""
        laws = self._parse_laws_xml(xml_text)
        return laws[0] if laws else {}

    def _parse_laws_xml(self, xml_text: str) -> list[dict[str, str]]:
        """법령 XML 응답을 딕셔너리 리스트로 변환."""
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.error("[법령알리미] XML 파싱 실패")
            return []

        items: list[dict[str, str]] = []
        for law in root.iter("law"):
            item: dict[str, str] = {}
            for child in law:
                if child.text:
                    item[child.tag] = child.text.strip()
            if item:
                items.append(item)
        return items

    # ══════════════════════════════════════════
    #  감시 목록 파일 관리
    # ══════════════════════════════════════════

    @staticmethod
    def _load_watchlist() -> list[dict]:
        """감시 목록 JSON 파일 로드."""
        if not WATCHLIST_PATH.exists():
            return []
        try:
            return json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    @staticmethod
    def _save_watchlist(watchlist: list[dict]) -> None:
        """감시 목록 JSON 파일 저장."""
        WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        WATCHLIST_PATH.write_text(
            json.dumps(watchlist, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
