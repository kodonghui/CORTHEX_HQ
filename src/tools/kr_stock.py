"""
한국 주식 데이터 Tool.

pykrx(한국거래소 데이터) + pandas-ta(기술적 지표) 라이브러리를 사용하여
한국 주식 시장의 주가, 거래량, 기술적 지표를 조회하고 분석합니다.

사용 방법:
  - action="price": 종목 주가/거래량 조회 (일봉 기준)
  - action="ohlcv": 기간별 OHLCV(시가/고가/저가/종가/거래량) 데이터
  - action="indicators": RSI, MACD, 볼린저밴드 등 기술적 지표 자동 계산
  - action="market_cap": 시가총액/거래대금 상위 종목

필요 환경변수: 없음 (pykrx는 무료, API 키 불필요)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.kr_stock")


def _import_pykrx():
    """pykrx 라이브러리 임포트 (설치 안 되어 있으면 안내 메시지)."""
    try:
        from pykrx import stock
        return stock
    except ImportError:
        return None


def _import_pandas_ta():
    """pandas-ta 라이브러리 임포트."""
    try:
        import pandas_ta as ta
        return ta
    except ImportError:
        return None


class KrStockTool(BaseTool):
    """한국 주식 데이터 조회 및 기술적 분석 도구."""

    async def execute(self, **kwargs: Any) -> str:
        # query 파라미터로 호출된 경우 (tools.yaml에 parameters 스키마 미정의 시 폴백)
        # query 값을 name으로 매핑하여 정상 처리되도록 함
        query = kwargs.get("query", "")
        if query and not kwargs.get("name") and not kwargs.get("ticker"):
            kwargs["name"] = query

        action = kwargs.get("action", "price")

        if action == "price":
            return await self._get_price(kwargs)
        elif action == "ohlcv":
            return await self._get_ohlcv(kwargs)
        elif action == "indicators":
            return await self._get_indicators(kwargs)
        elif action == "market_cap":
            return await self._get_market_cap(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "price, ohlcv, indicators, market_cap 중 하나를 사용하세요."
            )

    # ── 종목 주가 조회 ──

    async def _get_price(self, kwargs: dict[str, Any]) -> str:
        stock = _import_pykrx()
        if stock is None:
            return self._install_msg("pykrx")

        ticker = kwargs.get("ticker", "")
        name = kwargs.get("name", "")
        if not ticker and not name:
            return "종목코드(ticker) 또는 종목명(name)을 입력해주세요. 예: ticker='005930' 또는 name='삼성전자'"

        if name and not ticker:
            ticker = await self._resolve_ticker(stock, name)
            if not ticker:
                return f"'{name}' 종목을 찾을 수 없습니다. 종목명을 확인해주세요."

        days = int(kwargs.get("days", 30))
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        try:
            df = await asyncio.to_thread(
                stock.get_market_ohlcv_by_date, start, end, ticker
            )
        except Exception as e:
            return f"주가 데이터 조회 실패: {e}"

        if df.empty:
            return f"종목코드 {ticker}의 데이터가 없습니다. 종목코드를 확인해주세요."

        # 종목명 가져오기
        stock_name = await self._get_stock_name(stock, ticker)

        # 최근 5일 + 요약
        recent = df.tail(5)
        lines = [f"### {stock_name} ({ticker}) 최근 {days}일 주가"]
        lines.append(f"  현재가: {df.iloc[-1]['종가']:,.0f}원")
        lines.append(f"  최고가: {df['고가'].max():,.0f}원")
        lines.append(f"  최저가: {df['저가'].min():,.0f}원")

        if len(df) >= 2:
            change = df.iloc[-1]["종가"] - df.iloc[-2]["종가"]
            pct = (change / df.iloc[-2]["종가"]) * 100
            lines.append(f"  전일 대비: {change:+,.0f}원 ({pct:+.2f}%)")

        lines.append(f"\n  최근 5일:")
        for date, row in recent.iterrows():
            date_str = date.strftime("%m/%d")
            lines.append(
                f"    {date_str}: 종가 {row['종가']:,.0f} "
                f"(거래량 {row['거래량']:,.0f})"
            )

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 주식 시장 분석가입니다.\n"
                "주가 데이터를 분석하여 다음을 정리하세요:\n"
                "1. 최근 주가 추이 (상승/하락/횡보)\n"
                "2. 거래량 변화 특이점\n"
                "3. 단기 전망\n"
                "구체적 수치를 포함하여 한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 주가 데이터\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── OHLCV 데이터 ──

    async def _get_ohlcv(self, kwargs: dict[str, Any]) -> str:
        stock = _import_pykrx()
        if stock is None:
            return self._install_msg("pykrx")

        ticker = kwargs.get("ticker", "")
        name = kwargs.get("name", "")
        if not ticker and not name:
            return "종목코드(ticker) 또는 종목명(name)을 입력해주세요."

        if name and not ticker:
            ticker = await self._resolve_ticker(stock, name)
            if not ticker:
                return f"'{name}' 종목을 찾을 수 없습니다."

        fromdate = kwargs.get("fromdate", (datetime.now() - timedelta(days=90)).strftime("%Y%m%d"))
        todate = kwargs.get("todate", datetime.now().strftime("%Y%m%d"))

        try:
            df = await asyncio.to_thread(
                stock.get_market_ohlcv_by_date, fromdate, todate, ticker
            )
        except Exception as e:
            return f"OHLCV 데이터 조회 실패: {e}"

        if df.empty:
            return f"종목코드 {ticker}의 데이터가 없습니다."

        stock_name = await self._get_stock_name(stock, ticker)
        lines = [f"### {stock_name} ({ticker}) OHLCV ({fromdate}~{todate})"]
        lines.append(f"  거래일수: {len(df)}일")
        lines.append(f"  시작가: {df.iloc[0]['시가']:,.0f}원 → 종가: {df.iloc[-1]['종가']:,.0f}원")

        change_pct = ((df.iloc[-1]["종가"] - df.iloc[0]["시가"]) / df.iloc[0]["시가"]) * 100
        lines.append(f"  수익률: {change_pct:+.2f}%")
        lines.append(f"  최고가: {df['고가'].max():,.0f}원 / 최저가: {df['저가'].min():,.0f}원")
        lines.append(f"  평균 거래량: {df['거래량'].mean():,.0f}주")

        return "\n".join(lines)

    # ── 기술적 지표 ──

    async def _get_indicators(self, kwargs: dict[str, Any]) -> str:
        stock = _import_pykrx()
        if stock is None:
            return self._install_msg("pykrx")

        ta = _import_pandas_ta()
        if ta is None:
            return self._install_msg("pandas-ta")

        ticker = kwargs.get("ticker", "")
        name = kwargs.get("name", "")
        if not ticker and not name:
            return "종목코드(ticker) 또는 종목명(name)을 입력해주세요."

        if name and not ticker:
            ticker = await self._resolve_ticker(stock, name)
            if not ticker:
                return f"'{name}' 종목을 찾을 수 없습니다."

        days = int(kwargs.get("days", 120))
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        try:
            df = await asyncio.to_thread(
                stock.get_market_ohlcv_by_date, start, end, ticker
            )
        except Exception as e:
            return f"데이터 조회 실패: {e}"

        if df.empty or len(df) < 20:
            return f"종목코드 {ticker}의 데이터가 부족합니다 (최소 20일 필요)."

        stock_name = await self._get_stock_name(stock, ticker)

        # 기술적 지표 계산
        close = df["종가"]

        # 이동평균선
        ma5 = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1] if len(df) >= 60 else None

        # RSI
        rsi_series = ta.rsi(close, length=14)
        rsi = rsi_series.iloc[-1] if rsi_series is not None and not rsi_series.empty else None

        # MACD
        macd_df = ta.macd(close)
        macd_val = None
        macd_signal = None
        if macd_df is not None and not macd_df.empty:
            cols = macd_df.columns
            macd_val = macd_df[cols[0]].iloc[-1]
            macd_signal = macd_df[cols[1]].iloc[-1]

        # 볼린저밴드
        bb_df = ta.bbands(close, length=20)
        bb_upper = bb_lower = bb_mid = None
        if bb_df is not None and not bb_df.empty:
            cols = bb_df.columns
            bb_lower = bb_df[cols[0]].iloc[-1]
            bb_mid = bb_df[cols[1]].iloc[-1]
            bb_upper = bb_df[cols[2]].iloc[-1]

        current = close.iloc[-1]

        lines = [f"### {stock_name} ({ticker}) 기술적 지표"]
        lines.append(f"  현재가: {current:,.0f}원")
        lines.append(f"\n  ▶ 이동평균선")
        lines.append(f"    5일: {ma5:,.0f}원 {'▲' if current > ma5 else '▼'}")
        lines.append(f"    20일: {ma20:,.0f}원 {'▲' if current > ma20 else '▼'}")
        if ma60:
            lines.append(f"    60일: {ma60:,.0f}원 {'▲' if current > ma60 else '▼'}")

        if rsi is not None:
            rsi_status = "과매수" if rsi > 70 else "과매도" if rsi < 30 else "중립"
            lines.append(f"\n  ▶ RSI (14일): {rsi:.1f} ({rsi_status})")

        if macd_val is not None:
            macd_status = "매수 시그널" if macd_val > macd_signal else "매도 시그널"
            lines.append(f"\n  ▶ MACD: {macd_val:,.0f} / Signal: {macd_signal:,.0f} ({macd_status})")

        if bb_upper is not None:
            lines.append(f"\n  ▶ 볼린저밴드")
            lines.append(f"    상단: {bb_upper:,.0f}원 / 중간: {bb_mid:,.0f}원 / 하단: {bb_lower:,.0f}원")
            if current > bb_upper:
                lines.append(f"    현재가가 상단 돌파 → 과매수 가능성")
            elif current < bb_lower:
                lines.append(f"    현재가가 하단 이탈 → 과매도 가능성")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 기술적 분석 전문가입니다.\n"
                "기술적 지표를 종합 분석하여 다음을 정리하세요:\n"
                "1. 현재 기술적 상태 (강세/약세/중립)\n"
                "2. 이동평균선 배열 분석 (정배열/역배열)\n"
                "3. RSI + MACD + 볼린저밴드 종합 판단\n"
                "4. 매매 타이밍 의견 (진입/관망/청산)\n"
                "5. 지지선/저항선 가격대\n"
                "구체적 수치를 포함하여 한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 기술적 분석\n\n{formatted}\n\n---\n\n## 종합 분석\n\n{analysis}"

    # ── 시가총액 상위 ──

    async def _get_market_cap(self, kwargs: dict[str, Any]) -> str:
        stock = _import_pykrx()
        if stock is None:
            return self._install_msg("pykrx")

        top_n = int(kwargs.get("top_n", 20))
        market = kwargs.get("market", "KOSPI")  # KOSPI, KOSDAQ

        date = datetime.now().strftime("%Y%m%d")

        try:
            df = await asyncio.to_thread(
                stock.get_market_cap_by_ticker, date, market=market
            )
        except Exception as e:
            return f"시가총액 데이터 조회 실패: {e}"

        if df.empty:
            # 주말/공휴일인 경우 이전 영업일 시도
            for i in range(1, 5):
                prev = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
                try:
                    df = await asyncio.to_thread(
                        stock.get_market_cap_by_ticker, prev, market=market
                    )
                    if not df.empty:
                        date = prev
                        break
                except Exception:
                    continue

        if df.empty:
            return "시가총액 데이터를 가져오지 못했습니다. (주말/공휴일일 수 있습니다)"

        df = df.sort_values("시가총액", ascending=False).head(top_n)

        lines = [f"### {market} 시가총액 상위 {top_n}개 ({date})"]
        lines.append(f"{'순위':>4} {'종목코드':>8}  {'시가총액(억원)':>14}  {'종가':>10}  {'거래량':>12}")
        lines.append("  " + "-" * 60)

        for rank, (ticker, row) in enumerate(df.iterrows(), 1):
            cap_eok = row["시가총액"] / 1_0000_0000  # 원 → 억원
            lines.append(
                f"  {rank:>3}. {ticker}  {cap_eok:>13,.0f}  "
                f"{row['종가']:>10,.0f}  {row['거래량']:>12,.0f}"
            )

        return "\n".join(lines)

    # ── 헬퍼 ──

    async def _resolve_ticker(self, stock_module: Any, name: str) -> str:
        """종목명 → 종목코드 변환."""
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
            logger.warning("[KrStock] 종목명 변환 실패: %s", e)
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
