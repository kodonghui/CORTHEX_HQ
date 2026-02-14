"""
네이버 데이터랩 검색 트렌드 Tool.

네이버 데이터랩 API를 사용하여 키워드 검색량 추이를 조회하고
시장 트렌드를 분석합니다.

사용 방법:
  - action="trend": 키워드 검색량 추이 (최대 5개 키워드 비교)
  - action="shopping": 쇼핑 인사이트 카테고리별 트렌드

필요 환경변수:
  - NAVER_CLIENT_ID: 네이버 개발자센터 (https://developers.naver.com)
  - NAVER_CLIENT_SECRET: 위와 동일
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.naver_datalab")

DATALAB_SEARCH_API = "https://openapi.naver.com/v1/datalab/search"
DATALAB_SHOPPING_API = "https://openapi.naver.com/v1/datalab/shopping/categories"


class NaverDatalabTool(BaseTool):
    """네이버 데이터랩 검색 트렌드 분석 도구."""

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-Naver-Client-Id": os.getenv("NAVER_CLIENT_ID", ""),
            "X-Naver-Client-Secret": os.getenv("NAVER_CLIENT_SECRET", ""),
            "Content-Type": "application/json",
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "trend")

        if action == "trend":
            return await self._get_trend(kwargs)
        elif action == "shopping":
            return await self._get_shopping_trend(kwargs)
        else:
            return f"알 수 없는 action: {action}. trend 또는 shopping을 사용하세요."

    # ── 검색 트렌드 ──

    async def _get_trend(self, kwargs: dict[str, Any]) -> str:
        if not os.getenv("NAVER_CLIENT_ID"):
            return self._key_msg()

        keywords = kwargs.get("keywords", "")
        if not keywords:
            return (
                "검색어(keywords)를 입력해주세요.\n"
                "예: keywords='LEET,로스쿨,법학적성시험' (쉼표로 구분, 최대 5개)"
            )

        keyword_list = [k.strip() for k in keywords.split(",")][:5]

        # 기간 설정
        months = int(kwargs.get("months", 12))
        time_unit = kwargs.get("time_unit", "month")  # date, week, month
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months * 31)

        # 키워드 그룹 구성
        keyword_groups = []
        for kw in keyword_list:
            keyword_groups.append({
                "groupName": kw,
                "keywords": [kw],
            })

        body = {
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "timeUnit": time_unit,
            "keywordGroups": keyword_groups,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    DATALAB_SEARCH_API,
                    headers=self._headers,
                    json=body,
                    timeout=15,
                )
        except httpx.HTTPError as e:
            return f"네이버 데이터랩 API 호출 실패: {e}"

        if resp.status_code == 401:
            return "네이버 API 인증 실패 (401). NAVER_CLIENT_ID/SECRET을 확인하세요."

        if resp.status_code != 200:
            logger.error("[DataLab] 요청 실패 (%d): %s", resp.status_code, resp.text)
            return f"네이버 데이터랩 오류 ({resp.status_code}): {resp.text[:200]}"

        data = resp.json()
        results = data.get("results", [])

        if not results:
            return f"'{keywords}' 검색 트렌드 데이터가 없습니다."

        # 결과 포맷팅
        period_label = {"date": "일별", "week": "주별", "month": "월별"}.get(time_unit, time_unit)
        lines = [
            f"### 네이버 검색 트렌드 ({period_label})",
            f"  기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}",
            f"  키워드: {', '.join(keyword_list)}",
            "",
        ]

        for result in results:
            title = result.get("title", "")
            data_points = result.get("data", [])
            lines.append(f"  ▶ {title}")
            # 최근 6개 데이터만 표시
            for dp in data_points[-6:]:
                period = dp.get("period", "")
                ratio = dp.get("ratio", 0)
                bar = "█" * int(ratio / 5) if ratio else ""
                lines.append(f"    {period}: {ratio:>6.1f} {bar}")
            lines.append("")

        formatted = "\n".join(lines)

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 시장 트렌드 분석 전문가입니다.\n"
                "네이버 검색 트렌드 데이터를 분석하여 다음을 정리하세요:\n"
                "1. 각 키워드의 검색량 추이 (상승/하락/안정)\n"
                "2. 키워드 간 상대적 인기도 비교\n"
                "3. 계절성 또는 특이 패턴 발견\n"
                "4. 사업/마케팅에 활용 가능한 인사이트\n"
                "수치는 상대값(0~100)이며, 가장 높은 시점이 100입니다.\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 네이버 검색 트렌드\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 쇼핑 트렌드 ──

    async def _get_shopping_trend(self, kwargs: dict[str, Any]) -> str:
        if not os.getenv("NAVER_CLIENT_ID"):
            return self._key_msg()

        category = kwargs.get("category", "")
        if not category:
            return (
                "쇼핑 카테고리(category)를 입력해주세요.\n"
                "예: category='50000000' (패션의류)\n"
                "주요 카테고리: 50000000(패션), 50000001(디지털), "
                "50000002(생활), 50000003(식품)"
            )

        months = int(kwargs.get("months", 12))
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months * 31)

        body = {
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "timeUnit": "month",
            "category": [{"name": "카테고리", "param": [category]}],
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    DATALAB_SHOPPING_API,
                    headers=self._headers,
                    json=body,
                    timeout=15,
                )
        except httpx.HTTPError as e:
            return f"네이버 쇼핑 인사이트 API 호출 실패: {e}"

        if resp.status_code != 200:
            return f"네이버 쇼핑 인사이트 오류 ({resp.status_code}): {resp.text[:200]}"

        data = resp.json()
        results = data.get("results", [])

        if not results:
            return f"카테고리 '{category}' 쇼핑 트렌드 데이터가 없습니다."

        lines = [f"### 쇼핑 카테고리 트렌드 (카테고리: {category})"]
        for result in results:
            for dp in result.get("data", [])[-6:]:
                lines.append(f"  {dp.get('period', '')}: {dp.get('ratio', 0):.1f}")

        return "\n".join(lines)

    # ── 유틸 ──

    @staticmethod
    def _key_msg() -> str:
        return (
            "NAVER_CLIENT_ID가 설정되지 않았습니다.\n"
            "네이버 개발자센터(https://developers.naver.com)에서 "
            "애플리케이션을 등록하고 '데이터랩' API를 활성화한 뒤,\n"
            "Client ID와 Secret을 .env에 추가하세요."
        )
