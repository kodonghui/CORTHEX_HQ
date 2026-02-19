"""
실적 서프라이즈 분석 도구 (Earnings Surprise) — 실적 발표 전후 주가 패턴 분석.

"이번에 어닝 서프라이즈 날 확률은?" 과거 패턴으로 예측합니다.

학술 근거:
  - PEAD 이론 (Ball & Brown, 1968 — Post-Earnings Announcement Drift)
  - 어닝 서프라이즈와 주가 모멘텀 (Bernard & Thomas, 1989)
  - SUE (Standardized Unexpected Earnings)

사용 방법:
  - action="full"          : 종합 실적 분석 (과거 패턴 + 예측)
  - action="history"       : 과거 실적 발표 후 주가 반응 이력
  - action="pattern"       : 실적 시즌 주가 패턴
  - action="estimate"      : 실적 서프라이즈 가능성 추정

필요 환경변수: DART_API_KEY (공시 데이터)
필요 라이브러리: pykrx, pandas, numpy
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.earnings_surprise")


def _import_pykrx():
    try:
        from pykrx import stock
        return stock
    except ImportError:
        return None


class EarningsSurpriseTool(BaseTool):
    """실적 서프라이즈 분석 도구 — 실적 발표 전후 패턴 + PEAD 분석."""

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        if query and not kwargs.get("name") and not kwargs.get("ticker"):
            kwargs["name"] = query

        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_analysis,
            "history": self._earnings_history,
            "pattern": self._earnings_pattern,
            "estimate": self._surprise_estimate,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return f"알 수 없는 action: {action}. full, history, pattern, estimate 중 하나."

    # ── 공통 데이터 ──────────────────────────

    async def _load_data(self, kwargs: dict) -> tuple:
        stock = _import_pykrx()
        if stock is None:
            return None, None, None, "pykrx 필요"

        ticker = kwargs.get("ticker", "")
        name = kwargs.get("name", "")
        if not ticker and not name:
            return None, None, None, "종목코드 또는 종목명을 입력하세요."

        if name and not ticker:
            ticker = await self._resolve_ticker(stock, name)
            if not ticker:
                return None, None, None, f"'{name}' 종목을 찾을 수 없습니다."

        stock_name = await self._get_stock_name(stock, ticker)

        # 2년 데이터
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")

        try:
            ohlcv = await asyncio.to_thread(stock.get_market_ohlcv_by_date, start, end, ticker)
            fund = await asyncio.to_thread(stock.get_market_fundamental, start, end, ticker)
        except Exception as e:
            return None, None, None, f"데이터 조회 실패: {e}"

        if ohlcv.empty:
            return None, None, None, "가격 데이터가 없습니다."

        return stock_name, {"ohlcv": ohlcv, "fund": fund}, ticker, None

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

    async def _get_stock_name(self, stock, ticker: str) -> str:
        try:
            return await asyncio.to_thread(stock.get_market_ticker_name, ticker)
        except Exception:
            return ticker

    # ── 1. 종합 실적 분석 ────────────────────

    async def _full_analysis(self, kwargs: dict) -> str:
        name, data, ticker, err = await self._load_data(kwargs)
        if err:
            return err

        ohlcv = data["ohlcv"]
        fund = data["fund"]
        current_price = int(ohlcv["종가"].iloc[-1])

        # EPS 변화 추이 (분기별)
        eps_data = fund["EPS"].dropna()
        quarterly_eps = eps_data.resample("QE").last().dropna()

        results = [f"{'='*55}"]
        results.append(f"📊 {name} 실적 서프라이즈 분석")
        results.append(f"{'='*55}")
        results.append(f"현재가: {current_price:,}원\n")

        # EPS 추이
        if len(quarterly_eps) >= 2:
            results.append("▸ 분기별 EPS 추이:")
            for date, eps in quarterly_eps.items():
                yoy = ""
                prev_year = date - timedelta(days=365)
                nearest = quarterly_eps[quarterly_eps.index <= prev_year]
                if not nearest.empty and nearest.iloc[-1] != 0:
                    change = (eps / nearest.iloc[-1] - 1) * 100
                    yoy = f" (YoY {change:+.1f}%)"
                results.append(f"  {date.strftime('%Y-Q')}{(date.month-1)//3+1}: {eps:,.0f}원{yoy}")

        # EPS 성장률 트렌드
        if len(quarterly_eps) >= 4:
            recent_4q = quarterly_eps.iloc[-4:]
            prev_4q = quarterly_eps.iloc[-8:-4] if len(quarterly_eps) >= 8 else None
            if prev_4q is not None and not prev_4q.empty:
                ttm_current = recent_4q.sum()
                ttm_prev = prev_4q.sum()
                if ttm_prev != 0:
                    yoy_growth = (ttm_current / ttm_prev - 1) * 100
                    results.append(f"\n▸ 연간 EPS 성장률 (TTM): {yoy_growth:+.1f}%")

        # 실적 발표 전후 주가 변동 패턴
        # 분기말 근처(1,4,7,10월 중순)의 주가 변동 분석
        earning_months = [1, 4, 7, 10]  # 실적 발표 시즌
        returns = ohlcv["종가"].pct_change()

        season_returns = []
        for month in earning_months:
            month_data = returns[returns.index.month == month]
            if not month_data.empty:
                avg_ret = month_data.mean() * 100
                season_returns.append((month, avg_ret))

        if season_returns:
            results.append(f"\n▸ 실적 시즌 평균 일간 수익률:")
            for month, ret in season_returns:
                month_name = {1: "1월(4Q)", 4: "4월(1Q)", 7: "7월(2Q)", 10: "10월(3Q)"}
                results.append(f"  {month_name.get(month, f'{month}월')}: {ret:+.3f}%")

        # PER 밴드
        per_data = fund["PER"].replace(0, np.nan).dropna()
        if not per_data.empty:
            results.append(f"\n▸ PER 밴드:")
            results.append(f"  현재 PER: {per_data.iloc[-1]:.1f}배")
            results.append(f"  평균 PER: {per_data.mean():.1f}배")
            results.append(f"  최저 PER: {per_data.min():.1f}배 / 최고: {per_data.max():.1f}배")

        raw_text = "\n".join(results)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 실적 분석 전문가입니다. Ball & Brown(1968)의 PEAD 이론과 "
                "Bernard & Thomas(1989)의 어닝 모멘텀 연구를 참고하여, "
                "이 종목의 다음 실적 발표 시 서프라이즈 가능성과 "
                "주가 반응을 예측하세요. 구체적인 숫자 근거로. 한국어."
            ),
            user_prompt=raw_text,
            caller_model=kwargs.get("_caller_model"),
        )
        return f"{raw_text}\n\n{'='*55}\n🎓 교수급 실적 분석\n{'='*55}\n{analysis}"

    # ── 2. 과거 실적 후 주가 반응 ────────────

    async def _earnings_history(self, kwargs: dict) -> str:
        name, data, ticker, err = await self._load_data(kwargs)
        if err:
            return err

        ohlcv = data["ohlcv"]
        returns = ohlcv["종가"].pct_change()

        # 분기말 발표일 근처(각 분기 첫째 달 중순) 5일간 수익률
        results = [f"📊 {name} 실적 발표 후 주가 반응 이력"]
        results.append(f"\n실적 시즌별 ±5일 수익률:")

        earning_windows = []
        for year in range(ohlcv.index[0].year, ohlcv.index[-1].year + 1):
            for month in [1, 4, 7, 10]:
                target = datetime(year, month, 15)
                window = ohlcv[(ohlcv.index >= target - timedelta(days=7)) &
                               (ohlcv.index <= target + timedelta(days=7))]
                if len(window) >= 3:
                    ret = (window["종가"].iloc[-1] / window["종가"].iloc[0] - 1) * 100
                    quarter = {1: "4Q", 4: "1Q", 7: "2Q", 10: "3Q"}[month]
                    earning_windows.append((f"{year}-{quarter}", ret))

        for label, ret in earning_windows:
            emoji = "🟢" if ret > 0 else "🔴"
            results.append(f"  {emoji} {label}: {ret:+.1f}%")

        if earning_windows:
            avg = sum(r for _, r in earning_windows) / len(earning_windows)
            pos_rate = sum(1 for _, r in earning_windows if r > 0) / len(earning_windows) * 100
            results.append(f"\n평균: {avg:+.1f}% / 양의 반응 비율: {pos_rate:.0f}%")

        return "\n".join(results)

    # ── 3. 실적 시즌 패턴 ────────────────────

    async def _earnings_pattern(self, kwargs: dict) -> str:
        name, data, ticker, err = await self._load_data(kwargs)
        if err:
            return err

        ohlcv = data["ohlcv"]
        returns = ohlcv["종가"].pct_change().dropna()

        # 월별 평균 수익률
        monthly_avg = returns.groupby(returns.index.month).mean() * 100

        results = [f"📊 {name} 월별 수익률 패턴"]
        results.append(f"\n월별 평균 일간 수익률:")
        months_kr = {1:"1월",2:"2월",3:"3월",4:"4월",5:"5월",6:"6월",
                     7:"7월",8:"8월",9:"9월",10:"10월",11:"11월",12:"12월"}
        for month in range(1, 13):
            if month in monthly_avg.index:
                ret = monthly_avg[month]
                bar = "█" * max(1, int(abs(ret) * 50))
                emoji = "🟢" if ret > 0 else "🔴"
                results.append(f"  {emoji} {months_kr[month]}: {ret:+.3f}% {bar}")

        # 실적 시즌 강조
        results.append(f"\n* 실적 발표 시즌: 1월(4Q), 4월(1Q), 7월(2Q), 10월(3Q)")

        return "\n".join(results)

    # ── 4. 서프라이즈 추정 ───────────────────

    async def _surprise_estimate(self, kwargs: dict) -> str:
        name, data, ticker, err = await self._load_data(kwargs)
        if err:
            return err

        fund = data["fund"]
        eps_data = fund["EPS"].dropna()
        quarterly_eps = eps_data.resample("QE").last().dropna()

        results = [f"📊 {name} 실적 서프라이즈 가능성 추정"]

        if len(quarterly_eps) < 4:
            results.append("EPS 데이터가 부족합니다 (최소 4분기 필요).")
            return "\n".join(results)

        # EPS 트렌드
        recent = quarterly_eps.iloc[-4:]
        growth_rates = recent.pct_change().dropna()
        avg_growth = growth_rates.mean() * 100

        results.append(f"\n최근 4분기 EPS:")
        for date, eps in recent.items():
            results.append(f"  {date.strftime('%Y')}-Q{(date.month-1)//3+1}: {eps:,.0f}원")

        results.append(f"\n분기별 평균 성장률: {avg_growth:+.1f}%")

        # 추정 (마지막 EPS * (1 + 평균 성장률))
        next_eps = recent.iloc[-1] * (1 + avg_growth / 100)
        results.append(f"다음 분기 예상 EPS: {next_eps:,.0f}원")

        # 서프라이즈 확률 추정
        surprise_pct = min(90, max(10, 50 + avg_growth * 2))
        results.append(f"\n어닝 서프라이즈 가능성: {surprise_pct:.0f}%")
        if surprise_pct > 60:
            results.append("→ 실적 호전 가능성 높음 (PEAD 매수 전략 고려)")
        elif surprise_pct < 40:
            results.append("→ 실적 부진 가능성 (실적 발표 전 리스크 관리)")
        else:
            results.append("→ 방향성 불확실 (관망)")

        return "\n".join(results)
