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

    # 경기순환 업종 분류 (pykrx 업종명 기준)
    CYCLICAL_SECTORS = ["전기전자", "운수장비", "건설업", "화학"]
    DEFENSIVE_SECTORS = ["전기가스업", "음식료품", "의약품"]

    async def _rotation_cycle(self, kwargs: dict) -> str:
        """데이터 기반 업종 순환 사이클 판단 (Stovall Sector Rotation).

        방법: 3개월간 경기민감 업종 vs 방어 업종의 상대강도비율(RSR)을 계산하여
        경기 국면을 정량적으로 분류한 뒤, LLM에 데이터를 공급해 전문가 코멘터리 생성.
        """
        stock = _import_pykrx()
        if stock is None:
            return "pykrx 라이브러리가 필요합니다."

        import pandas as pd

        end = datetime.now().strftime("%Y%m%d")
        start_3m = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
        start_1m = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")

        # ── 업종별 3개월 수익률 계산 ──
        async def _sector_return(sector_name: str, start: str, end: str) -> float | None:
            """pykrx 시가총액 상위 종목에서 업종 대리 수익률 계산."""
            try:
                cap_df = await asyncio.to_thread(
                    stock.get_market_cap_by_ticker, end, market="KOSPI"
                )
                tickers = cap_df.nlargest(200, "시가총액").index.tolist()

                sector_returns = []
                for t in tickers:
                    try:
                        # pykrx에서 업종 분류 확인
                        t_sector = await asyncio.to_thread(
                            stock.get_market_ticker_name, t
                        )
                        # 업종 지수 직접 사용 시도
                        pass
                    except Exception:
                        continue
                return None
            except Exception:
                return None

        # pykrx 업종 지수 방식으로 수익률 직접 조회
        sector_returns_3m = {}
        sector_returns_1m = {}
        all_sectors = list(set(self.CYCLICAL_SECTORS + self.DEFENSIVE_SECTORS))

        for sector in all_sectors:
            try:
                df_3m = await asyncio.to_thread(
                    stock.get_index_ohlcv_by_date, start_3m, end, "1001", sector
                )
                if df_3m is not None and not df_3m.empty and len(df_3m) > 5:
                    ret_3m = (df_3m["종가"].iloc[-1] / df_3m["종가"].iloc[0] - 1) * 100
                    sector_returns_3m[sector] = ret_3m
            except Exception:
                pass
            try:
                df_1m = await asyncio.to_thread(
                    stock.get_index_ohlcv_by_date, start_1m, end, "1001", sector
                )
                if df_1m is not None and not df_1m.empty and len(df_1m) > 5:
                    ret_1m = (df_1m["종가"].iloc[-1] / df_1m["종가"].iloc[0] - 1) * 100
                    sector_returns_1m[sector] = ret_1m
            except Exception:
                pass

        # 업종 지수 실패 시 → 시총 상위 종목 기반 대리 수익률 계산
        if len(sector_returns_3m) < 4:
            sector_returns_3m, sector_returns_1m = await self._fallback_sector_returns(
                stock, start_3m, start_1m, end
            )

        # ── 상대강도비율(RSR) 계산 ──
        cyc_rets_3m = [sector_returns_3m[s] for s in self.CYCLICAL_SECTORS if s in sector_returns_3m]
        def_rets_3m = [sector_returns_3m[s] for s in self.DEFENSIVE_SECTORS if s in sector_returns_3m]

        results = [f"{'='*60}"]
        results.append(f"📊 업종 순환 사이클 분석 (데이터 기반)")
        results.append(f"{'='*60}")

        # 개별 업종 수익률 표
        results.append(f"\n▸ 3개월 업종별 수익률:")
        results.append(f"  {'업종':>8} | {'3개월':>8} | {'1개월':>8} | {'분류':>6}")
        results.append(f"  {'-'*42}")
        for sector in all_sectors:
            r3 = sector_returns_3m.get(sector)
            r1 = sector_returns_1m.get(sector)
            cat = "경기민감" if sector in self.CYCLICAL_SECTORS else "방어"
            if r3 is not None:
                r1_str = f"{r1:+6.1f}%" if r1 is not None else "   N/A"
                results.append(f"  {sector:>8} | {r3:>+6.1f}% | {r1_str} | {cat:>6}")

        if cyc_rets_3m and def_rets_3m:
            avg_cyc = sum(cyc_rets_3m) / len(cyc_rets_3m)
            avg_def = sum(def_rets_3m) / len(def_rets_3m)

            # RSR = 경기민감 평균 수익률 / 방어 평균 수익률 (부호 보정)
            # 두 값 모두 음수이면 비율 해석이 반전되므로 차이 기반으로도 판단
            if avg_def != 0:
                rsr = (1 + avg_cyc / 100) / (1 + avg_def / 100)
            else:
                rsr = 1.0 + (avg_cyc / 100)

            spread = avg_cyc - avg_def  # 경기민감 - 방어 스프레드

            # ── 경기 국면 분류 (3단계: Stovall Sector Rotation 기반) ──
            # RSR > 1.20 → 경기민감 업종이 방어 대비 20%+ 초과 → 명확한 확장
            # 0.80 < RSR ≤ 1.20 → 혼조, 전환 구간
            # RSR ≤ 0.80 → 방어 업종이 압도적 우위 → 침체/방어 국면
            if rsr > 1.20:
                phase = "경기 확장기 (Expansion)"
                phase_detail = "경기민감 업종이 방어 업종을 20%+ 상회 → 시장이 경기 확장을 반영"
                phase_advice = "IT/반도체, 산업재, 소재 비중 확대 유리. 방어주 축소"
            elif rsr > 0.80:
                phase = "경기 전환기 (Transition)"
                phase_detail = "경기민감 vs 방어 혼조 → 방향 탐색 구간, 순환 전환점 가능성"
                phase_advice = "업종 중립 유지, 개별 종목 선별 중심. 양쪽 균형 배분"
            else:
                phase = "경기 침체/방어 (Defensive/Recession)"
                phase_detail = "방어 업종이 경기민감 대비 크게 우위 → 시장이 경기 둔화/침체 반영"
                phase_advice = "필수소비재, 유틸리티, 헬스케어 비중 확대. 경기민감 축소"

            results.append(f"\n▸ 상대강도비율 (RSR):")
            results.append(f"  경기민감 평균 수익률: {avg_cyc:+.2f}% ({', '.join(self.CYCLICAL_SECTORS)})")
            results.append(f"  방어 업종 평균 수익률: {avg_def:+.2f}% ({', '.join(self.DEFENSIVE_SECTORS)})")
            results.append(f"  RSR = {rsr:.3f}  (스프레드: {spread:+.2f}%p)")
            results.append(f"\n▸ 판정 기준 (Stovall Sector Rotation):")
            results.append(f"  RSR > 1.20 → 경기 확장기 | 0.80 < RSR ≤ 1.20 → 경기 전환기 | RSR ≤ 0.80 → 경기 침체/방어")
            results.append(f"\n{'─'*60}")
            results.append(f"  ▶ 현재 국면: {phase}")
            results.append(f"  ▶ 해석: {phase_detail}")
            results.append(f"  ▶ 전략: {phase_advice}")
            results.append(f"{'─'*60}")

            # 1개월 모멘텀 방향 확인 (추세 가속/감속 판단)
            cyc_rets_1m = [sector_returns_1m[s] for s in self.CYCLICAL_SECTORS if s in sector_returns_1m]
            def_rets_1m = [sector_returns_1m[s] for s in self.DEFENSIVE_SECTORS if s in sector_returns_1m]
            if cyc_rets_1m and def_rets_1m:
                avg_cyc_1m = sum(cyc_rets_1m) / len(cyc_rets_1m)
                avg_def_1m = sum(def_rets_1m) / len(def_rets_1m)
                spread_1m = avg_cyc_1m - avg_def_1m
                if spread_1m > spread / 3:
                    trend = "경기민감 쪽으로 가속 중 (확장 방향)"
                elif spread_1m < -abs(spread / 3):
                    trend = "방어 쪽으로 전환 중 (둔화 방향)"
                else:
                    trend = "현 국면 유지 중"
                results.append(f"\n▸ 1개월 추세 방향: {trend}")
                results.append(f"  (1개월 스프레드: {spread_1m:+.2f}%p vs 3개월: {spread:+.2f}%p)")

            # ── LLM에 데이터를 공급하여 전문가 코멘터리 생성 ──
            data_for_llm = "\n".join(results)
            analysis = await self._llm_call(
                system_prompt=(
                    "당신은 Sam Stovall 수준의 업종 순환 분석 전문가입니다. "
                    "아래는 실제 pykrx 시장 데이터로 계산한 경기민감 vs 방어 업종 상대강도비율(RSR)과 "
                    "자동 분류된 경기 국면입니다. 이 데이터를 기반으로:\n"
                    "1) 분류가 타당한지 전문가 관점에서 검증하세요\n"
                    "2) 현재 국면에서 구체적 업종 배분 전략(비중 %포함)을 제안하세요\n"
                    "3) 향후 1~3개월 국면 전환 가능성과 선행 시그널을 제시하세요\n"
                    "데이터에 없는 내용을 지어내지 마세요. 한국어로 답변."
                ),
                user_prompt=data_for_llm,
                caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
            )
            results.append(f"\n{'='*60}\n🎓 교수급 업종 순환 분석\n{'='*60}\n{analysis}")
        else:
            results.append("\n⚠ 업종 데이터 부족으로 RSR 계산 불가. 최소 경기민감 1개 + 방어 1개 필요.")
            results.append("경기 사이클별 유리한 업종 (이론):")
            results.append("  ① 경기 회복기: 금융, 부동산, 경기소비재")
            results.append("  ② 경기 확장기: IT/반도체, 산업재, 소재")
            results.append("  ③ 경기 과열기: 에너지, 소재, 필수소비재")
            results.append("  ④ 경기 침체기: 필수소비재, 유틸리티, 헬스케어")

        return "\n".join(results)

    async def _fallback_sector_returns(self, stock, start_3m: str, start_1m: str, end: str) -> tuple[dict, dict]:
        """업종 지수 직접 조회 실패 시, 시총 상위 종목의 업종 분류로 대리 수익률 계산."""
        # 업종별 대표 종목 매핑 (pykrx 종목명 기준)
        sector_proxy = {
            "전기전자": ["삼성전자", "SK하이닉스", "LG전자"],
            "운수장비": ["현대차", "기아"],
            "건설업": ["현대건설", "대우건설", "GS건설"],
            "화학": ["LG화학", "롯데케미칼", "한화솔루션"],
            "전기가스업": ["한국전력", "한국가스공사"],
            "음식료품": ["CJ제일제당", "오뚜기", "농심"],
            "의약품": ["삼성바이오로직스", "셀트리온", "유한양행"],
        }

        returns_3m = {}
        returns_1m = {}

        for sector, proxies in sector_proxy.items():
            rets_3 = []
            rets_1 = []
            for pname in proxies:
                try:
                    ticker = None
                    today = datetime.now().strftime("%Y%m%d")
                    tickers = await asyncio.to_thread(stock.get_market_ticker_list, today, market="KOSPI")
                    for t in tickers:
                        n = await asyncio.to_thread(stock.get_market_ticker_name, t)
                        if n == pname:
                            ticker = t
                            break
                    if not ticker:
                        continue

                    ohlcv_3 = await asyncio.to_thread(
                        stock.get_market_ohlcv_by_date, start_3m, end, ticker
                    )
                    if not ohlcv_3.empty and len(ohlcv_3) > 5:
                        r3 = (ohlcv_3["종가"].iloc[-1] / ohlcv_3["종가"].iloc[0] - 1) * 100
                        rets_3.append(r3)

                    ohlcv_1 = await asyncio.to_thread(
                        stock.get_market_ohlcv_by_date, start_1m, end, ticker
                    )
                    if not ohlcv_1.empty and len(ohlcv_1) > 5:
                        r1 = (ohlcv_1["종가"].iloc[-1] / ohlcv_1["종가"].iloc[0] - 1) * 100
                        rets_1.append(r1)
                except Exception:
                    continue

            if rets_3:
                returns_3m[sector] = sum(rets_3) / len(rets_3)
            if rets_1:
                returns_1m[sector] = sum(rets_1) / len(rets_1)

        return returns_3m, returns_1m

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
