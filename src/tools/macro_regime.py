"""
경기 국면 판단 도구 (Macro Regime) — 금리/경기 사이클 국면 분류.

"지금 금리상승기야? 경기확장이야? 침체야?" 거시경제 데이터로 판단합니다.

학술 근거:
  - Merrill Lynch Investment Clock (경기순환시계)
  - 경기순환이론 (NBER Business Cycle Dating)
  - 금리-경기 4분면 모델 (Growth + Inflation regime)

사용 방법:
  - action="full"       : 종합 국면 판단 (금리+경기+투자전략)
  - action="regime"     : 현재 경기 국면 분류 (4분면)
  - action="rates"      : 금리 환경 분석
  - action="leading"    : 선행지표 분석
  - action="strategy"   : 국면별 투자 전략 추천

필요 환경변수: ECOS_API_KEY (한국은행 경제통계)
필요 라이브러리: aiohttp (또는 LLM 기반 분석)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.macro_regime")


class MacroRegimeTool(BaseTool):
    """경기 국면 판단 도구 — 4분면 분류 + 금리 환경 + 투자 전략."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_regime,
            "regime": self._classify_regime,
            "rates": self._rate_analysis,
            "leading": self._leading_indicators,
            "strategy": self._regime_strategy,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return f"알 수 없는 action: {action}. full, regime, rates, leading, strategy 중 하나."

    # ── 1. 종합 국면 판단 ────────────────────

    async def _full_regime(self, kwargs: dict) -> str:
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 거시경제 분석의 최고 전문가입니다. "
                "Merrill Lynch Investment Clock과 NBER 경기순환 이론을 기반으로 "
                "현재(2026년 2월) 한국 경제의 경기 국면을 종합 판단하세요.\n\n"
                "반드시 아래 항목을 포함하세요:\n"
                "1. 현재 경기 국면 (4분면 중 하나): "
                "   ① 회복기(Recovery) ② 확장기(Expansion) ③ 과열기(Overheating) ④ 침체기(Recession)\n"
                "2. 근거 데이터: 기준금리, GDP 성장률, CPI, 실업률, PMI, 원달러 환율\n"
                "3. 금리 방향: 인상 사이클/동결/인하 사이클\n"
                "4. 선행지표 신호: OECD 경기선행지수(CLI), 장단기금리차\n"
                "5. 국면별 추천 자산: 주식(성장주/가치주), 채권, 금, 부동산 등\n"
                "6. 업종 추천: 현재 국면에서 유리한/불리한 업종\n"
                "7. 주요 리스크 요인\n\n"
                "구체적인 숫자와 근거를 들어 설명하세요. 한국어로 답변."
            ),
            user_prompt=(
                "2026년 2월 현재 한국 경제의 거시경제 국면을 종합 판단해주세요. "
                "최신 경제 데이터를 기반으로 분석하고, 투자 전략을 제안해주세요."
            ),
            caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
        )

        header = (
            f"{'='*55}\n"
            f"📊 거시경제 국면 종합 분석 (Macro Regime)\n"
            f"{'='*55}\n"
            f"분석 기준일: {datetime.now().strftime('%Y년 %m월 %d일')}\n"
            f"이론적 프레임워크: Merrill Lynch Investment Clock\n"
            f"{'='*55}\n"
        )
        return f"{header}\n{analysis}"

    # ── 2. 경기 국면 분류 ────────────────────

    async def _classify_regime(self, kwargs: dict) -> str:
        analysis = await self._llm_call(
            system_prompt=(
                "거시경제 전문가로서 현재 한국 경기 국면을 4분면으로 분류하세요.\n"
                "4분면 모델:\n"
                "  ① 회복기 (성장↑ + 인플레↓): 주식 > 채권 > 원자재 > 현금\n"
                "  ② 확장기 (성장↑ + 인플레↑): 원자재 > 주식 > 현금 > 채권\n"
                "  ③ 과열기 (성장↓ + 인플레↑): 현금 > 원자재 > 채권 > 주식\n"
                "  ④ 침체기 (성장↓ + 인플레↓): 채권 > 현금 > 주식 > 원자재\n\n"
                "현재 국면을 하나 선택하고 근거를 제시하세요. 한국어."
            ),
            user_prompt="현재 한국 경기 국면을 4분면으로 분류해주세요.",
            caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
        )

        results = [f"📊 경기 국면 4분면 분류"]
        results.append(f"\n투자시계 (Merrill Lynch Investment Clock):")
        results.append(f"  ① 회복기: 주식 최고 / ② 확장기: 원자재 최고")
        results.append(f"  ③ 과열기: 현금 최고 / ④ 침체기: 채권 최고")
        results.append(f"\n{'─'*55}")
        results.append(f"\n🎓 현재 국면 판단:\n{analysis}")
        return "\n".join(results)

    # ── 3. 금리 환경 분석 ────────────────────

    async def _rate_analysis(self, kwargs: dict) -> str:
        analysis = await self._llm_call(
            system_prompt=(
                "금리 환경 분석 전문가입니다. 현재(2026년 2월) 한국의 금리 환경을 분석하세요.\n"
                "포함 항목:\n"
                "1. 한국은행 기준금리 현재 수준 + 최근 변동\n"
                "2. 국고채 3년/10년 금리\n"
                "3. 장단기금리차 (10년-2년)\n"
                "4. 미국 연준 금리와의 차이\n"
                "5. 금리 방향 전망 (인상/동결/인하)\n"
                "6. 금리 환경이 주식시장에 미치는 영향\n"
                "한국어로 구체적 숫자와 함께."
            ),
            user_prompt="2026년 2월 한국 금리 환경을 분석해주세요.",
            caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
        )
        return f"📊 금리 환경 분석\n\n{analysis}"

    # ── 4. 선행지표 분석 ─────────────────────

    async def _leading_indicators(self, kwargs: dict) -> str:
        analysis = await self._llm_call(
            system_prompt=(
                "선행지표 분석 전문가입니다. 현재(2026년 2월) 한국 경기 선행지표를 분석하세요.\n"
                "포함 항목:\n"
                "1. OECD 경기선행지수 (CLI) 한국\n"
                "2. 제조업 PMI (구매관리자지수)\n"
                "3. 소비자신뢰지수\n"
                "4. 재고순환지표\n"
                "5. 수출입 동향\n"
                "6. 종합 판단: 경기 상승/하강 국면 예측\n"
                "한국어로 구체적 숫자와 함께."
            ),
            user_prompt="2026년 2월 한국 경기 선행지표를 분석해주세요.",
            caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
        )
        return f"📊 경기 선행지표 분석\n\n{analysis}"

    # ── 5. 국면별 투자 전략 ──────────────────

    async def _regime_strategy(self, kwargs: dict) -> str:
        analysis = await self._llm_call(
            system_prompt=(
                "자산배분 전문가입니다. 현재 경기 국면에 맞는 투자 전략을 제안하세요.\n"
                "포함 항목:\n"
                "1. 현재 국면 요약 (1줄)\n"
                "2. 추천 자산 배분 비율 (주식/채권/원자재/현금/대안)\n"
                "3. 주식 내 스타일 (성장주 vs 가치주 vs 배당주)\n"
                "4. 추천 업종 TOP 5 + 이유\n"
                "5. 비추천 업종 TOP 3 + 이유\n"
                "6. 헷지 전략 (위험 관리)\n"
                "7. 다음 6개월 시나리오 (낙관/기본/비관)\n"
                "한국어로 구체적으로."
            ),
            user_prompt="현재 경기 국면에 맞는 투자 전략을 제안해주세요.",
            caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
        )
        return f"📊 경기 국면별 투자 전략\n\n{analysis}"
