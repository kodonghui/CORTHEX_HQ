"""
배당 캘린더 Tool (Dividend Calendar).

pykrx와 DART API를 활용하여 기업 배당 일정, 배당 이력,
배당수익률 상위 종목을 조회합니다.

사용 방법:
  - action="calendar": 월별 배당 관련 종목 정보
    - month: 대상 월 (기본: 현재 월, 형식: "2026-03")
  - action="history": 특정 기업의 과거 배당 이력
    - company: 기업명
    - years: 조회 연수 (기본: 5)
  - action="top": 배당수익률 상위 종목
    - market: "KOSPI"/"KOSDAQ"/"ALL" (기본: "ALL")
    - top_n: 상위 N개 (기본: 20)

필요 환경변수:
  - DART_API_KEY (선택): 배당 공시 조회 시 사용. 없어도 pykrx만으로 기본 기능 동작
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.dividend_calendar")

DART_BASE = "https://opendart.fss.or.kr/api"
CORP_CODE_CACHE = Path("data/dart_corp_codes.json")


def _import_pykrx():
    try:
        from pykrx import stock
        return stock
    except ImportError:
        return None


def _import_pandas():
    try:
        import pandas as pd
        return pd
    except ImportError:
        return None


class DividendCalendarTool(BaseTool):
    """배당 일정 및 배당 분석 도구."""

    _corp_codes: dict[str, str] | None = None

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "top")

        if action == "calendar":
            return await self._calendar(kwargs)
        elif action == "history":
            return await self._history(kwargs)
        elif action == "top":
            return await self._top(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "calendar, history, top 중 하나를 사용하세요."
            )

    # ── 월별 배당 종목 정보 ──

    async def _calendar(self, kwargs: dict[str, Any]) -> str:
        stock = _import_pykrx()
        pd = _import_pandas()
        if stock is None:
            return self._install_msg("pykrx")
        if pd is None:
            return self._install_msg("pandas")

        month_str = kwargs.get("month", datetime.now().strftime("%Y-%m"))

        try:
            year, month = month_str.split("-")
            year = int(year)
            month = int(month)
        except (ValueError, AttributeError):
            return "month 형식이 올바르지 않습니다. 예: month='2026-03'"

        # 해당 월의 마지막 거래일 기준 배당 데이터 조회
        # 12월 결산 기업이 대부분이므로, 12월/3월/6월/9월이 배당 시즌
        date = await self._get_latest_trading_date(stock, year, month)
        if not date:
            return f"{month_str}의 거래 데이터를 가져올 수 없습니다."

        # 배당수익률이 있는 종목 조회
        markets = ["KOSPI", "KOSDAQ"]
        dividend_stocks: list[dict] = []

        for mkt in markets:
            try:
                fund_df = await asyncio.to_thread(
                    stock.get_market_fundamental_by_ticker, date, market=mkt
                )
                if fund_df is not None and not fund_df.empty:
                    for ticker, row in fund_df.iterrows():
                        div_yield = row.get("DIV", 0)
                        if div_yield > 0:
                            try:
                                name = await asyncio.to_thread(
                                    stock.get_market_ticker_name, ticker
                                )
                            except Exception:
                                name = ticker
                            dividend_stocks.append({
                                "ticker": ticker,
                                "name": name,
                                "div_yield": div_yield,
                                "per": row.get("PER", 0),
                                "pbr": row.get("PBR", 0),
                                "market": mkt,
                            })
            except Exception as e:
                logger.warning("[DividendCalendar] %s 데이터 조회 실패: %s", mkt, e)

        if not dividend_stocks:
            return f"{month_str} 기준 배당 종목 정보가 없습니다."

        # 배당수익률 순 정렬
        dividend_stocks.sort(key=lambda x: x["div_yield"], reverse=True)
        top_stocks = dividend_stocks[:30]

        lines = [f"### 배당 캘린더 — {month_str} ({date} 기준)"]
        lines.append(f"  배당 지급 종목 수: {len(dividend_stocks)}개")
        lines.append(f"\n  ▶ 배당수익률 상위 30개")
        lines.append(f"  {'순위':>4} {'종목':>10} {'배당률':>7} {'PER':>7} {'시장':>7}")
        lines.append("  " + "-" * 50)

        for rank, s in enumerate(top_stocks, 1):
            lines.append(
                f"  {rank:>3}. {s['name']:>10}  {s['div_yield']:>5.1f}%  "
                f"{s['per']:>7.1f}  {s['market']:>6}"
            )

        formatted = "\n".join(lines)

        # 배당 시즌 안내
        season_note = ""
        if month in [12, 1]:
            season_note = "12월은 대부분의 기업 배당 기준일이 있는 핵심 배당 시즌입니다."
        elif month in [3, 4]:
            season_note = "3~4월은 전년도 배당금이 실제로 지급되는 시기입니다."
        elif month in [6, 7]:
            season_note = "6월은 중간배당 기준일이 있는 기업이 있습니다."

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 배당 투자 전문가입니다.\n"
                "배당 데이터를 분석하여 다음을 정리하세요:\n"
                "1. 이번 달 배당 시장 현황 요약\n"
                "2. 배당수익률 상위 종목 중 주목할 종목 5개와 이유\n"
                "3. 배당 투자 전략 제안 (배당 시즌 고려)\n"
                "한국어로 답변하세요."
            ),
            user_prompt=f"{formatted}\n\n참고: {season_note}" if season_note else formatted,
        )

        return f"## 배당 캘린더\n\n{formatted}\n\n---\n\n## 배당 투자 분석\n\n{analysis}"

    # ── 기업별 배당 이력 ──

    async def _history(self, kwargs: dict[str, Any]) -> str:
        stock = _import_pykrx()
        pd = _import_pandas()
        if stock is None:
            return self._install_msg("pykrx")
        if pd is None:
            return self._install_msg("pandas")

        company = kwargs.get("company", "")
        if not company:
            return "기업명(company)을 입력해주세요. 예: company='삼성전자'"

        years = int(kwargs.get("years", 5))

        # 종목코드 변환
        ticker = await self._resolve_ticker_by_name(stock, company)
        if not ticker:
            return f"'{company}' 종목을 찾을 수 없습니다."

        stock_name = await self._get_stock_name(stock, ticker)

        # 연도별 배당 데이터 조회
        current_year = datetime.now().year
        history: list[dict] = []

        for yr in range(current_year - years, current_year + 1):
            # 각 연도 12월 마지막 거래일 기준
            date = f"{yr}1231"
            try:
                fund_df = await asyncio.to_thread(
                    stock.get_market_fundamental_by_ticker, date
                )
                if fund_df is not None and ticker in fund_df.index:
                    row = fund_df.loc[ticker]
                    div_yield = row.get("DIV", 0)
                    history.append({
                        "year": yr,
                        "div_yield": div_yield,
                        "per": row.get("PER", 0),
                        "pbr": row.get("PBR", 0),
                    })
            except Exception:
                continue

        if not history:
            return f"'{company}'의 배당 이력 데이터를 가져올 수 없습니다."

        lines = [f"### {stock_name} ({ticker}) 배당 이력 (최근 {years}년)"]
        lines.append(f"  {'연도':>6} {'배당수익률':>10} {'PER':>8} {'PBR':>6}")
        lines.append("  " + "-" * 40)

        for h in history:
            lines.append(
                f"  {h['year']:>6}  {h['div_yield']:>8.2f}%  "
                f"{h['per']:>8.1f}  {h['pbr']:>6.2f}"
            )

        # 배당 추이 분석
        if len(history) >= 2:
            avg_div = sum(h["div_yield"] for h in history) / len(history)
            lines.append(f"\n  평균 배당수익률: {avg_div:.2f}%")
            recent = history[-1]["div_yield"]
            if recent > avg_div:
                lines.append(f"  현재 배당수익률({recent:.2f}%)이 평균 대비 높음 → 매력적")
            else:
                lines.append(f"  현재 배당수익률({recent:.2f}%)이 평균 대비 낮음")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 배당 투자 분석가입니다.\n"
                "기업의 배당 이력을 분석하여 다음을 정리하세요:\n"
                "1. 배당 정책 변화 추이 (안정적/증가/감소)\n"
                "2. 배당성향 평가 (주주 친화적인가?)\n"
                "3. 배당 투자 관점에서의 매력도\n"
                "4. 현재 시점 투자 의견\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 배당 이력\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 배당수익률 상위 종목 ──

    async def _top(self, kwargs: dict[str, Any]) -> str:
        stock = _import_pykrx()
        pd = _import_pandas()
        if stock is None:
            return self._install_msg("pykrx")
        if pd is None:
            return self._install_msg("pandas")

        market = kwargs.get("market", "ALL")
        top_n = int(kwargs.get("top_n", 20))

        date = await self._get_latest_trading_date_now(stock)
        if not date:
            return "최근 거래일 데이터를 가져올 수 없습니다."

        markets = ["KOSPI", "KOSDAQ"] if market == "ALL" else [market]
        all_stocks: list[dict] = []

        for mkt in markets:
            try:
                fund_df = await asyncio.to_thread(
                    stock.get_market_fundamental_by_ticker, date, market=mkt
                )
                cap_df = await asyncio.to_thread(
                    stock.get_market_cap_by_ticker, date, market=mkt
                )
                if fund_df is not None and not fund_df.empty:
                    for ticker in fund_df.index:
                        div_yield = fund_df.loc[ticker].get("DIV", 0)
                        if div_yield > 0:
                            try:
                                name = await asyncio.to_thread(
                                    stock.get_market_ticker_name, ticker
                                )
                            except Exception:
                                name = ticker
                            cap = 0
                            if cap_df is not None and ticker in cap_df.index:
                                cap = cap_df.loc[ticker].get("시가총액", 0) / 1_0000_0000
                            all_stocks.append({
                                "ticker": ticker,
                                "name": name,
                                "div_yield": div_yield,
                                "per": fund_df.loc[ticker].get("PER", 0),
                                "pbr": fund_df.loc[ticker].get("PBR", 0),
                                "market_cap": cap,
                                "market": mkt,
                            })
            except Exception as e:
                logger.warning("[DividendCalendar] %s 데이터 조회 실패: %s", mkt, e)

        if not all_stocks:
            return "배당 데이터를 가져올 수 없습니다."

        all_stocks.sort(key=lambda x: x["div_yield"], reverse=True)
        top_list = all_stocks[:top_n]

        lines = [f"### 배당수익률 TOP {top_n} ({date} 기준, {market})"]
        lines.append(f"  {'순위':>4} {'종목':>10} {'배당률':>7} {'PER':>7} {'시총(억)':>10} {'시장':>7}")
        lines.append("  " + "-" * 60)

        for rank, s in enumerate(top_list, 1):
            lines.append(
                f"  {rank:>3}. {s['name']:>10}  {s['div_yield']:>5.1f}%  "
                f"{s['per']:>7.1f}  {s['market_cap']:>9,.0f}  {s['market']:>6}"
            )

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 배당 투자 전문가입니다.\n"
                "배당수익률 상위 종목 리스트를 분석하여 다음을 정리하세요:\n"
                "1. 상위 종목들의 공통 특징 (업종, 규모 등)\n"
                "2. 실질적으로 투자할 만한 우량 배당주 5개 선정 (너무 소형주/지나치게 높은 배당률은 함정 가능)\n"
                "3. 배당 투자 시 주의사항 (배당 함정, 배당 지속성)\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 배당 TOP 종목\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 헬퍼 ──

    async def _get_latest_trading_date(self, stock_module: Any, year: int, month: int) -> str:
        """특정 연월의 마지막 거래일 찾기."""
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        for d in range(last_day, 0, -1):
            date = f"{year}{month:02d}{d:02d}"
            try:
                df = await asyncio.to_thread(
                    stock_module.get_market_fundamental_by_ticker, date, market="KOSPI"
                )
                if df is not None and not df.empty:
                    return date
            except Exception:
                continue
        return ""

    async def _get_latest_trading_date_now(self, stock_module: Any) -> str:
        """오늘 기준 최근 거래일 찾기."""
        for i in range(7):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            try:
                df = await asyncio.to_thread(
                    stock_module.get_market_fundamental_by_ticker, date, market="KOSPI"
                )
                if df is not None and not df.empty:
                    return date
            except Exception:
                continue
        return ""

    async def _resolve_ticker_by_name(self, stock_module: Any, name: str) -> str:
        """종목명 → 종목코드."""
        try:
            date = datetime.now().strftime("%Y%m%d")
            tickers = await asyncio.to_thread(
                stock_module.get_market_ticker_list, date, market="ALL"
            )
            for t in tickers:
                t_name = await asyncio.to_thread(
                    stock_module.get_market_ticker_name, t
                )
                if t_name == name:
                    return t
        except Exception as e:
            logger.warning("[DividendCalendar] 종목명 변환 실패: %s", e)
        return ""

    async def _get_stock_name(self, stock_module: Any, ticker: str) -> str:
        """종목코드 → 종목명."""
        try:
            return await asyncio.to_thread(
                stock_module.get_market_ticker_name, ticker
            )
        except Exception:
            return ticker

    @staticmethod
    def _install_msg(package: str) -> str:
        return (
            f"{package} 라이브러리가 설치되지 않았습니다.\n"
            f"터미널에서 다음 명령어로 설치하세요:\n"
            f"  pip install {package}"
        )
