"""
업종 순환 분석 도구 (Sector Rotator) — 업종별 강세/약세 순환 분석.

"지금 어떤 업종이 뜨고 있나? 돈이 어디로 몰리고 있나?"를 분석합니다.

학술 근거:
  - Sam Stovall, "Standard & Poor's Guide to Sector Investing" (업종순환이론)
  - 경기순환과 업종 회전 (Sector Rotation Theory)
  - 상대강도 분석 (Relative Strength)

사용 방법:
  - action="full"        : 전체 업종 종합 분석
  - action="ranking"     : 업종별 수익률 순위
  - action="momentum"    : 업종 모멘텀 (자금 유입/유출)
  - action="rotation"    : 업종 순환 사이클 판단
  - action="compare"     : 특정 업종 vs KOSPI 비교

필요 환경변수: 없음
필요 라이브러리: pykrx, pandas, numpy
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.sector_rotator")


def _import_pykrx():
    try:
        from pykrx import stock
        return stock
    except ImportError:
        return None


class SectorRotatorTool(BaseTool):
    """업종 순환 분석 도구 — 업종별 강세/약세 + 자금 흐름 + 순환 판단."""

    # 코스피 주요 업종 (pykrx 기준)
    SECTORS = [
        "음식료품", "섬유의복", "종이목재", "화학", "의약품",
        "비금속광물", "철강금속", "기계", "전기전자", "의료정밀",
        "운수장비", "유통업", "전기가스업", "건설업", "운수창고업",
        "통신업", "금융업", "은행", "증권", "보험",
        "서비스업",
    ]

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_analysis,
            "ranking": self._sector_ranking,
            "momentum": self._sector_momentum,
            "rotation": self._rotation_cycle,
            "compare": self._sector_compare,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return f"알 수 없는 action: {action}. full, ranking, momentum, rotation, compare 중 하나."

    # ── 공통: 업종 데이터 로드 ────────────────

    async def _load_sector_data(self, kwargs: dict) -> tuple:
        stock = _import_pykrx()
        if stock is None:
            return None, "pykrx 라이브러리가 필요합니다."

        days = int(kwargs.get("days", 90))
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        import pandas as pd
        sector_data = {}

        for sector in self.SECTORS:
            try:
                df = await asyncio.to_thread(
                    stock.get_index_ohlcv_by_date, start, end, "1001", sector
                )
                if df is not None and not df.empty and len(df) > 5:
                    sector_data[sector] = df
            except Exception:
                # pykrx 업종 지수 방식에 따라 다를 수 있음
                pass

        # 업종 지수가 안 되면 시가총액 기준 업종별 종목 조회
        if not sector_data:
            try:
                today_str = datetime.now().strftime("%Y%m%d")
                # 코스피 전체 지수
                kospi = await asyncio.to_thread(
                    stock.get_index_ohlcv_by_date, start, end, "1001"
                )
                if kospi is not None and not kospi.empty:
                    sector_data["KOSPI"] = kospi
            except Exception:
                pass

        if not sector_data:
            return None, "업종 데이터를 가져올 수 없습니다."

        return sector_data, None

    async def _load_market_data(self, kwargs: dict) -> tuple:
        """코스피 업종별 등락률 데이터 (대안 방식)."""
        stock = _import_pykrx()
        if stock is None:
            return None, "pykrx 필요"

        import pandas as pd
        end = datetime.now().strftime("%Y%m%d")
        periods = {
            "1주": 7, "1개월": 30, "3개월": 90, "6개월": 180,
        }

        results = {}
        for period_name, days in periods.items():
            start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            try:
                # 업종별 시가총액 상위 종목으로 대리 분석
                tickers = await asyncio.to_thread(
                    stock.get_market_ticker_list, end, market="KOSPI"
                )
                sector_returns = {}
                for t in tickers[:100]:  # 상위 100종목
                    try:
                        name = await asyncio.to_thread(stock.get_market_ticker_name, t)
                        ohlcv = await asyncio.to_thread(
                            stock.get_market_ohlcv_by_date, start, end, t
                        )
                        if not ohlcv.empty and len(ohlcv) > 2:
                            ret = (ohlcv["종가"].iloc[-1] / ohlcv["종가"].iloc[0] - 1) * 100
                            sector_returns[name] = ret
                    except Exception:
                        continue
                results[period_name] = sector_returns
            except Exception:
                continue

        return results, None

    # ── 1. 전체 업종 종합 분석 ────────────────

    async def _full_analysis(self, kwargs: dict) -> str:
        stock = _import_pykrx()
        if stock is None:
            return "pykrx 라이브러리가 필요합니다."

        end = datetime.now().strftime("%Y%m%d")
        import pandas as pd

        # 코스피 시가총액 상위 종목의 업종별 분류
        periods = {"1개월": 30, "3개월": 90}
        sector_perf = {}

        for period_name, days in periods.items():
            start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            try:
                cap_df = await asyncio.to_thread(
                    stock.get_market_cap_by_ticker, end, market="KOSPI"
                )
                top_tickers = cap_df.nlargest(50, "시가총액").index.tolist()

                for t in top_tickers:
                    try:
                        name = await asyncio.to_thread(stock.get_market_ticker_name, t)
                        ohlcv = await asyncio.to_thread(
                            stock.get_market_ohlcv_by_date, start, end, t
                        )
                        if not ohlcv.empty and len(ohlcv) > 2:
                            ret = (ohlcv["종가"].iloc[-1] / ohlcv["종가"].iloc[0] - 1) * 100
                            if name not in sector_perf:
                                sector_perf[name] = {}
                            sector_perf[name][period_name] = ret
                    except Exception:
                        continue
            except Exception:
                continue

        if not sector_perf:
            return "데이터를 가져올 수 없습니다."

        # 정렬 (3개월 수익률 기준)
        sorted_stocks = sorted(
            sector_perf.items(),
            key=lambda x: x[1].get("3개월", 0),
            reverse=True
        )

        results = [f"{'='*60}"]
        results.append(f"📊 KOSPI 시총 상위 50 — 기간별 수익률 순위")
        results.append(f"{'='*60}\n")
        results.append(f"{'순위':>3} {'종목':>10} | {'1개월':>8} | {'3개월':>8}")
        results.append("-" * 45)

        for i, (name, perf) in enumerate(sorted_stocks[:30], 1):
            m1 = perf.get("1개월", 0)
            m3 = perf.get("3개월", 0)
            results.append(f"  {i:>2}. {name:>8} | {m1:>+6.1f}% | {m3:>+6.1f}%")

        # 강세/약세 분류
        strong = [n for n, p in sorted_stocks[:10]]
        weak = [n for n, p in sorted_stocks[-10:]]
        results.append(f"\n▸ 강세 TOP 10: {', '.join(strong)}")
        results.append(f"▸ 약세 BOTTOM 10: {', '.join(weak)}")

        raw_text = "\n".join(results)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 Sam Stovall 수준의 업종 순환 분석 전문가입니다. "
                "업종별 수익률 데이터를 보고 현재 경기 사이클에서 어떤 업종이 유리한지, "
                "자금 로테이션이 어디로 향하고 있는지 분석하세요. "
                "투자자에게 업종 배분 전략을 제안하세요. 한국어로 답변."
            ),
            user_prompt=raw_text,
            caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
        )
        return f"{raw_text}\n\n{'='*60}\n🎓 교수급 업종 분석\n{'='*60}\n{analysis}"

    # ── 2. 업종 수익률 순위 ──────────────────

    async def _sector_ranking(self, kwargs: dict) -> str:
        # full과 동일한 데이터를 간략화
        return await self._full_analysis(kwargs)

    # ── 3. 업종 모멘텀 ───────────────────────

    async def _sector_momentum(self, kwargs: dict) -> str:
        stock = _import_pykrx()
        if stock is None:
            return "pykrx 필요"

        end = datetime.now().strftime("%Y%m%d")
        start_1m = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")

        try:
            cap_df = await asyncio.to_thread(
                stock.get_market_cap_by_ticker, end, market="KOSPI"
            )
            top_tickers = cap_df.nlargest(30, "시가총액").index.tolist()
        except Exception:
            return "시가총액 데이터 조회 실패"

        momentum = []
        for t in top_tickers:
            try:
                name = await asyncio.to_thread(stock.get_market_ticker_name, t)
                ohlcv = await asyncio.to_thread(
                    stock.get_market_ohlcv_by_date, start_1m, end, t
                )
                if not ohlcv.empty and len(ohlcv) > 5:
                    ret = (ohlcv["종가"].iloc[-1] / ohlcv["종가"].iloc[0] - 1) * 100
                    avg_vol = ohlcv["거래량"].mean()
                    recent_vol = ohlcv["거래량"].iloc[-5:].mean()
                    vol_change = (recent_vol / avg_vol - 1) * 100 if avg_vol > 0 else 0
                    momentum.append({
                        "name": name, "return": ret,
                        "vol_change": vol_change, "score": ret + vol_change * 0.3
                    })
            except Exception:
                continue

        momentum.sort(key=lambda x: x["score"], reverse=True)

        results = [f"📊 KOSPI 대형주 모멘텀 분석 (30종목)"]
        results.append(f"\n{'종목':>10} | {'수익률':>8} | {'거래량변화':>10} | {'모멘텀점수':>10}")
        results.append("-" * 50)
        for m in momentum[:20]:
            results.append(
                f"  {m['name']:>8} | {m['return']:>+6.1f}% | {m['vol_change']:>+8.0f}% | {m['score']:>8.1f}"
            )

        results.append(f"\n▸ 모멘텀 상승: {', '.join(m['name'] for m in momentum[:5])}")
        results.append(f"▸ 모멘텀 하락: {', '.join(m['name'] for m in momentum[-5:])}")
        return "\n".join(results)

    # ── 4. 업종 순환 사이클 ──────────────────

    async def _rotation_cycle(self, kwargs: dict) -> str:
        results = [f"📊 업종 순환 사이클 이론 (Sam Stovall)"]
        results.append(f"\n경기 사이클별 유리한 업종:")
        results.append(f"  ① 경기 회복기 (Recovery): 금융, 부동산, 경기소비재")
        results.append(f"  ② 경기 확장기 (Expansion): IT/반도체, 산업재, 소재")
        results.append(f"  ③ 경기 과열기 (Late Cycle): 에너지, 소재, 필수소비재")
        results.append(f"  ④ 경기 침체기 (Recession): 필수소비재, 유틸리티, 헬스케어")

        # LLM으로 현재 국면 판단
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 업종 순환 이론 전문가입니다. "
                "현재 한국 경제 상황(2026년 2월 기준)을 고려하여 "
                "경기 사이클의 어느 국면에 있는지 판단하고, "
                "유리한 업종과 불리한 업종을 구체적으로 제시하세요. 한국어."
            ),
            user_prompt="현재 한국 경기 사이클 국면 판단 + 업종 추천을 해주세요.",
            caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
        )
        results.append(f"\n🎓 현재 국면 분석:\n{analysis}")
        return "\n".join(results)

    # ── 5. 업종 vs KOSPI 비교 ────────────────

    async def _sector_compare(self, kwargs: dict) -> str:
        name = kwargs.get("name", "") or kwargs.get("query", "")
        if not name:
            return "비교할 종목명을 입력하세요. 예: name='삼성전자'"

        stock = _import_pykrx()
        if stock is None:
            return "pykrx 필요"

        ticker = await self._resolve_ticker(stock, name)
        if not ticker:
            return f"'{name}' 종목을 찾을 수 없습니다."

        end = datetime.now().strftime("%Y%m%d")
        periods = {"1개월": 30, "3개월": 90, "6개월": 180}
        results = [f"📊 {name} vs KOSPI 상대 강도 비교"]

        for period_name, days in periods.items():
            start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            try:
                stock_ohlcv = await asyncio.to_thread(
                    stock.get_market_ohlcv_by_date, start, end, ticker
                )
                kospi = await asyncio.to_thread(
                    stock.get_index_ohlcv_by_date, start, end, "1001"
                )
                if not stock_ohlcv.empty and not kospi.empty:
                    stock_ret = (stock_ohlcv["종가"].iloc[-1] / stock_ohlcv["종가"].iloc[0] - 1) * 100
                    kospi_ret = (kospi["종가"].iloc[-1] / kospi["종가"].iloc[0] - 1) * 100
                    alpha = stock_ret - kospi_ret
                    results.append(f"\n{period_name}:")
                    results.append(f"  {name}: {stock_ret:+.1f}% / KOSPI: {kospi_ret:+.1f}% / 초과수익: {alpha:+.1f}%")
            except Exception:
                continue

        return "\n".join(results)

    async def _resolve_ticker(self, stock, name: str) -> str | None:
        try:
            today = datetime.now().strftime("%Y%m%d")
            tickers = await asyncio.to_thread(stock.get_market_ticker_list, today, market="ALL")
            for t in tickers:
                if await asyncio.to_thread(stock.get_market_ticker_name, t) == name:
                    return t
        except Exception:
            pass
        return None
