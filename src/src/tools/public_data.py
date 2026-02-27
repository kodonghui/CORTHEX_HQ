"""
공공데이터포털 Tool.

공공데이터포털 API를 사용하여 인구, 교육, 경제 등
정부 통계 데이터를 조회합니다.

사용 방법:
  - action="search": 데이터셋 검색
  - action="stats": 주요 통계 API 호출 (인구통계, 교육통계 등)
  - action="custom": 사용자 지정 API 엔드포인트 호출

필요 환경변수:
  - PUBLIC_DATA_API_KEY: 공공데이터포털 (https://www.data.go.kr/) 무료 발급
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.public_data")

# 자주 사용하는 공공데이터 API 프리셋
STAT_PRESETS: dict[str, dict[str, str]] = {
    "인구": {
        "url": "https://apis.data.go.kr/1240000/IndicatorService/getPopulation",
        "desc": "통계청 인구 현황",
    },
    "고용": {
        "url": "https://apis.data.go.kr/1240000/IndicatorService/getEmployment",
        "desc": "고용률/실업률 현황",
    },
    "물가": {
        "url": "https://apis.data.go.kr/1240000/IndicatorService/getConsumerPrice",
        "desc": "소비자물가지수",
    },
    "교육": {
        "url": "https://apis.data.go.kr/B552061/lgScoTrfcAcdntIfo/getRestLgScoTrfcAcdntIfo",
        "desc": "교육 관련 통계",
    },
}

DATASET_SEARCH_API = "https://apis.data.go.kr/1320000/LosfService/getLosfList"


class PublicDataTool(BaseTool):
    """공공데이터포털 통계 데이터 조회 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "search")

        if action == "search":
            return await self._search_dataset(kwargs)
        elif action == "stats":
            return await self._get_stats(kwargs)
        elif action == "custom":
            return await self._custom_api(kwargs)
        else:
            return f"알 수 없는 action: {action}. search, stats, custom 중 하나를 사용하세요."

    # ── 데이터셋 검색 ──

    async def _search_dataset(self, kwargs: dict[str, Any]) -> str:
        api_key = os.getenv("PUBLIC_DATA_API_KEY")
        if not api_key:
            return self._key_msg()

        query = kwargs.get("query", "")
        if not query:
            return (
                "검색어(query)를 입력해주세요.\n"
                "예: query='로스쿨 경쟁률', query='인구 통계', query='대학 입학'"
            )

        page_size = int(kwargs.get("size", 10))

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    DATASET_SEARCH_API,
                    params={
                        "serviceKey": api_key,
                        "query": query,
                        "numOfRows": str(page_size),
                        "pageNo": "1",
                        "type": "json",
                    },
                    timeout=15,
                )
        except httpx.HTTPError as e:
            return f"공공데이터포털 API 호출 실패: {e}"

        if resp.status_code == 401:
            return "공공데이터포털 인증 실패 (401). PUBLIC_DATA_API_KEY를 확인하세요."

        if resp.status_code != 200:
            return f"공공데이터포털 오류 ({resp.status_code}): {resp.text[:200]}"

        try:
            data = resp.json()
        except Exception:
            # 일부 API는 XML로 응답할 수 있음
            return f"응답 파싱 실패. XML 형식일 수 있습니다.\n응답 일부: {resp.text[:500]}"

        # 결과 포맷팅 (API 응답 구조가 다양하므로 유연하게 처리)
        body = data.get("response", {}).get("body", data.get("body", data))
        items = body.get("items", body.get("item", []))

        if isinstance(items, dict):
            items = items.get("item", [])
        if not isinstance(items, list):
            items = [items] if items else []

        if not items:
            return f"'{query}' 관련 공공데이터를 찾을 수 없습니다."

        lines = [f"### 공공데이터 검색 결과: '{query}'"]
        for i, item in enumerate(items[:page_size], 1):
            if isinstance(item, dict):
                title = item.get("title", item.get("dataNm", str(item)))
                desc = item.get("description", item.get("dataDesc", ""))
                lines.append(f"  [{i}] {title}")
                if desc:
                    lines.append(f"      설명: {desc}")
            else:
                lines.append(f"  [{i}] {item}")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 공공데이터 분석 전문가입니다.\n"
                "검색 결과를 분석하여 다음을 정리하세요:\n"
                "1. 가장 관련성 높은 데이터셋 2~3개 추천\n"
                "2. 각 데이터셋으로 알 수 있는 정보\n"
                "3. 사업 기획에 활용할 수 있는 인사이트\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 공공데이터 검색\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 주요 통계 조회 ──

    async def _get_stats(self, kwargs: dict[str, Any]) -> str:
        api_key = os.getenv("PUBLIC_DATA_API_KEY")
        if not api_key:
            return self._key_msg()

        category = kwargs.get("category", "")
        if not category:
            preset_list = "\n".join(
                f"  - {k}: {v['desc']}" for k, v in STAT_PRESETS.items()
            )
            return (
                f"통계 카테고리(category)를 입력해주세요.\n"
                f"사용 가능한 프리셋:\n{preset_list}\n"
                f"예: category='인구'"
            )

        preset = STAT_PRESETS.get(category)
        if not preset:
            return (
                f"'{category}' 프리셋이 없습니다.\n"
                f"사용 가능: {', '.join(STAT_PRESETS.keys())}\n"
                f"또는 action='custom', url='...' 으로 직접 API를 호출할 수 있습니다."
            )

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    preset["url"],
                    params={
                        "serviceKey": api_key,
                        "numOfRows": "20",
                        "pageNo": "1",
                        "type": "json",
                    },
                    timeout=15,
                )
        except httpx.HTTPError as e:
            return f"공공데이터 API 호출 실패: {e}"

        if resp.status_code != 200:
            return f"공공데이터 오류 ({resp.status_code}): {resp.text[:200]}"

        try:
            data = resp.json()
        except Exception:
            return f"응답 파싱 실패.\n응답 일부: {resp.text[:500]}"

        formatted = f"### {preset['desc']} 통계\n\n{self._format_json_data(data)}"

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 통계 데이터 분석 전문가입니다.\n"
                "공공데이터 통계를 분석하여 핵심 수치와 "
                "사업에 활용 가능한 인사이트를 정리하세요.\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 공공데이터 통계\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 사용자 지정 API ──

    async def _custom_api(self, kwargs: dict[str, Any]) -> str:
        api_key = os.getenv("PUBLIC_DATA_API_KEY")
        if not api_key:
            return self._key_msg()

        url = kwargs.get("url", "")
        if not url:
            return "API URL(url)을 입력해주세요."

        params = kwargs.get("params", {})
        if isinstance(params, str):
            # "key1=val1&key2=val2" 형식 파싱
            params = dict(p.split("=", 1) for p in params.split("&") if "=" in p)

        params["serviceKey"] = api_key
        params.setdefault("type", "json")
        params.setdefault("numOfRows", "20")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params, timeout=15)
        except httpx.HTTPError as e:
            return f"API 호출 실패: {e}"

        if resp.status_code != 200:
            return f"API 오류 ({resp.status_code}): {resp.text[:200]}"

        try:
            data = resp.json()
            return f"## API 응답\n\n{self._format_json_data(data)}"
        except Exception:
            return f"## API 응답 (원문)\n\n{resp.text[:2000]}"

    # ── 유틸 ──

    @staticmethod
    def _format_json_data(data: Any, indent: int = 0) -> str:
        """JSON 데이터를 읽기 쉬운 텍스트로 변환."""
        prefix = "  " * indent
        if isinstance(data, dict):
            lines = []
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"{prefix}{k}:")
                    lines.append(PublicDataTool._format_json_data(v, indent + 1))
                else:
                    lines.append(f"{prefix}{k}: {v}")
            return "\n".join(lines)
        elif isinstance(data, list):
            lines = []
            for i, item in enumerate(data[:20], 1):  # 최대 20개
                lines.append(f"{prefix}[{i}]")
                lines.append(PublicDataTool._format_json_data(item, indent + 1))
            return "\n".join(lines)
        else:
            return f"{prefix}{data}"

    @staticmethod
    def _key_msg() -> str:
        return (
            "PUBLIC_DATA_API_KEY가 설정되지 않았습니다.\n"
            "공공데이터포털(https://www.data.go.kr/)에서 "
            "무료 활용 신청 후 인증키를 .env에 추가하세요.\n"
            "예: PUBLIC_DATA_API_KEY=your-api-key"
        )
