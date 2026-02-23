"""
한국은행 ECOS 경제 지표 Tool.

한국은행 경제통계시스템(ECOS) API를 사용하여
금리, GDP, CPI, 환율 등 주요 거시경제 지표를 조회합니다.

사용 방법:
  - action="indicator": 주요 거시경제 지표 조회 (금리, GDP, CPI 등)
  - action="exchange_rate": 원/달러, 원/엔, 원/유로 환율 조회

필요 환경변수:
  - ECOS_API_KEY: 한국은행 ECOS API (https://ecos.bok.or.kr/api/) 무료 발급
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.ecos_macro")

ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"

# 주요 통계표 코드
STAT_CODES: dict[str, dict[str, str]] = {
    "기준금리": {"code": "722Y001", "item": "0101000", "cycle": "M"},
    "콜금리": {"code": "817Y002", "item": "010101000", "cycle": "M"},
    "GDP성장률": {"code": "200Y002", "item": "10111", "cycle": "Q"},
    "소비자물가지수": {"code": "021Y125", "item": "0", "cycle": "M"},
    "실업률": {"code": "901Y027", "item": "3120000", "cycle": "M"},
    "수출": {"code": "301Y013", "item": "100000", "cycle": "M"},
    "수입": {"code": "301Y013", "item": "200000", "cycle": "M"},
}

EXCHANGE_CODES: dict[str, dict[str, str]] = {
    "원/달러": {"code": "731Y003", "item": "0000001", "cycle": "M"},
    "원/엔(100엔)": {"code": "731Y003", "item": "0000002", "cycle": "M"},
    "원/유로": {"code": "731Y003", "item": "0000003", "cycle": "M"},
    "원/위안": {"code": "731Y003", "item": "0000053", "cycle": "M"},
}


class EcosMacroTool(BaseTool):
    """한국은행 ECOS 거시경제 지표 조회 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "indicator")

        if action == "indicator":
            return await self._get_indicators(kwargs)
        elif action == "exchange_rate":
            return await self._get_exchange_rates(kwargs)
        else:
            return f"알 수 없는 action: {action}. indicator 또는 exchange_rate를 사용하세요."

    # ── 거시경제 지표 조회 ──

    async def _get_indicators(self, kwargs: dict[str, Any]) -> str:
        api_key = os.getenv("ECOS_API_KEY")
        if not api_key:
            return (
                "ECOS_API_KEY가 설정되지 않았습니다.\n"
                "한국은행 ECOS(https://ecos.bok.or.kr/api/)에서 "
                "무료 인증키를 발급받은 뒤 .env에 추가하세요.\n"
                "예: ECOS_API_KEY=your-ecos-api-key"
            )

        # 조회할 지표 선택
        names = kwargs.get("indicators", "")
        if names:
            selected = {k: v for k, v in STAT_CODES.items() if k in names}
        else:
            selected = STAT_CODES  # 전부 조회

        # 기간 설정 (최근 12개월)
        months = int(kwargs.get("months", 12))
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months * 31)

        results = []
        for name, info in selected.items():
            data = await self._fetch_stat(
                api_key, info["code"], info["cycle"],
                start_date, end_date, info["item"],
            )
            if data:
                results.append(f"### {name}\n{data}")
            else:
                results.append(f"### {name}\n데이터 없음")

        formatted = "\n\n".join(results)

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 거시경제 분석 전문가입니다.\n"
                "한국은행 경제 지표를 분석하여 다음을 정리하세요:\n"
                "1. 각 지표의 최근 추이 (상승/하락/보합)\n"
                "2. 현재 경제 상황 종합 진단\n"
                "3. 투자 시장에 미치는 영향\n"
                "4. 향후 전망 (낙관/중립/비관)\n"
                "구체적인 수치를 포함하여 한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 한국은행 ECOS 경제 지표\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 환율 조회 ──

    async def _get_exchange_rates(self, kwargs: dict[str, Any]) -> str:
        api_key = os.getenv("ECOS_API_KEY")
        if not api_key:
            return (
                "ECOS_API_KEY가 설정되지 않았습니다.\n"
                "한국은행 ECOS(https://ecos.bok.or.kr/api/)에서 "
                "무료 인증키를 발급받은 뒤 .env에 추가하세요."
            )

        months = int(kwargs.get("months", 6))
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months * 31)

        results = []
        for name, info in EXCHANGE_CODES.items():
            data = await self._fetch_stat(
                api_key, info["code"], info["cycle"],
                start_date, end_date, info["item"],
            )
            if data:
                results.append(f"### {name}\n{data}")

        formatted = "\n\n".join(results) if results else "환율 데이터를 가져오지 못했습니다."

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 외환 시장 분석 전문가입니다.\n"
                "환율 데이터를 분석하여 다음을 정리하세요:\n"
                "1. 각 통화 대비 원화 환율 추이\n"
                "2. 원화 강세/약세 판단 및 원인\n"
                "3. 수출입 기업에 미치는 영향\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 환율 현황\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── API 호출 헬퍼 ──

    async def _fetch_stat(
        self,
        api_key: str,
        stat_code: str,
        cycle: str,
        start_date: datetime,
        end_date: datetime,
        item_code: str,
    ) -> str:
        """ECOS API에서 통계 데이터를 가져와 텍스트로 포맷팅."""
        fmt_start = start_date.strftime("%Y%m")
        fmt_end = end_date.strftime("%Y%m")
        if cycle == "Q":
            fmt_start = start_date.strftime("%Y") + "Q1"
            # 미래 분기 요청 방지: 현재 완료된 분기까지만 요청
            from datetime import datetime as _dt
            now = _dt.now()
            current_q = (now.month - 1) // 3  # 0=Q1진행중, 1=Q1완료, 2=Q2완료, 3=Q3완료
            if end_date.year > now.year or (end_date.year == now.year):
                # 올해면 직전 완료 분기까지, 미래면 작년 Q4까지
                if end_date.year >= now.year:
                    if current_q == 0:
                        fmt_end = str(now.year - 1) + "Q4"
                    else:
                        fmt_end = str(now.year) + f"Q{current_q}"
                else:
                    fmt_end = end_date.strftime("%Y") + "Q4"
            else:
                fmt_end = end_date.strftime("%Y") + "Q4"

        url = (
            f"{ECOS_BASE}/{api_key}/json/kr/1/100"
            f"/{stat_code}/{cycle}/{fmt_start}/{fmt_end}/{item_code}"
        )

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=15)
        except httpx.HTTPError as e:
            logger.error("[ECOS] API 호출 실패: %s", e)
            return ""

        if resp.status_code != 200:
            logger.error("[ECOS] HTTP %d: %s", resp.status_code, resp.text[:200])
            return ""

        data = resp.json()
        stat_data = data.get("StatisticSearch", {})

        if "row" not in stat_data:
            # ECOS 에러 응답 처리
            error = data.get("RESULT", {})
            if error:
                logger.warning("[ECOS] %s: %s", error.get("CODE"), error.get("MESSAGE"))
            return ""

        rows = stat_data["row"]
        lines = []
        for row in rows[-12:]:  # 최근 12개 데이터만
            period = row.get("TIME", "")
            value = row.get("DATA_VALUE", "")
            unit = row.get("UNIT_NAME", "")
            lines.append(f"  {period}: {value} {unit}")

        return "\n".join(lines)
