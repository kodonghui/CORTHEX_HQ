"""
미국 주식 데이터 Tool.

yfinance 라이브러리를 사용하여 미국 주식 시장의 주가, 재무제표,
기술적 지표, 동종업체 비교, 실적 서프라이즈를 조회하고 분석합니다.

사용 방법:
  - action="quote": 종목 시세 + 기본 정보 조회
  - action="financials": 재무제표 (손익/대차/현금흐름)
  - action="ohlcv": 기간별 OHLCV 데이터
  - action="indicators": RSI, MACD, 볼린저밴드 등 기술적 지표
  - action="peers": 동종업체 비교 (PER, PBR, ROE 등)
  - action="earnings": 실적 서프라이즈 (예상 vs 실제 EPS)
  - action="screener": 섹터/시총 기반 종목 스크리닝

필요 환경변수: 없음 (yfinance는 무료)
의존 라이브러리: yfinance, pandas_ta (선택)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.us_stock")


def _yf():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        return None


def _ta():
    try:
        import pandas_ta as ta
        return ta
    except ImportError:
        return None


# ══════════════════════════════════════════
#  S&P500 섹터 분류 (GICS 기준)
# ══════════════════════════════════════════
SECTOR_KO = {
    "Technology": "기술",
    "Healthcare": "헬스케어",
    "Financial Services": "금융",
    "Financials": "금융",
    "Consumer Cyclical": "경기소비재",
    "Consumer Defensive": "필수소비재",
    "Communication Services": "커뮤니케이션",
    "Industrials": "산업재",
    "Energy": "에너지",
    "Utilities": "유틸리티",
    "Real Estate": "부동산",
    "Basic Materials": "소재",
}

# 대표 종목 (섹터별 + 지수)
POPULAR = {
    "기술대형": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"],
    "반도체": ["NVDA", "AMD", "INTC", "AVGO", "QCOM", "TSM", "MU"],
    "금융": ["JPM", "BAC", "GS", "MS", "WFC", "BRK-B", "V"],
    "헬스케어": ["UNH", "JNJ", "PFE", "ABBV", "LLY", "MRK", "TMO"],
    "에너지": ["XOM", "CVX", "COP", "SLB", "EOG"],
    "지수ETF": ["SPY", "QQQ", "DIA", "IWM", "VTI"],
}

# 52주 기준 거래일
TRADING_DAYS_1Y = 252


class UsStockTool(BaseTool):
    """미국 주식 데이터 조회 및 분석 도구."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "quote")

        # query 파라미터 폴백
        if "query" in kwargs and "symbol" not in kwargs:
            kwargs["symbol"] = kwargs["query"]

        dispatch = {
            "quote": self._quote,
            "financials": self._financials,
            "ohlcv": self._ohlcv,
            "indicators": self._indicators,
            "peers": self._peers,
            "earnings": self._earnings,
            "screener": self._screener,
        }
        handler = dispatch.get(action)
        if handler is None:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능: quote, financials, ohlcv, indicators, peers, earnings, screener"
            )
        return await handler(kwargs)

    # ── quote: 시세 + 기본 정보 ──────────────
    async def _quote(self, kw: dict) -> str:
        yf = _yf()
        if not yf:
            return "yfinance 미설치. pip install yfinance"

        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return (
                "symbol 파라미터가 필요합니다.\n"
                "예: symbol='AAPL', symbol='TSLA', symbol='NVDA'\n\n"
                "**인기 종목:**\n"
                + "\n".join(f"- {cat}: {', '.join(syms)}" for cat, syms in POPULAR.items())
            )

        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            hist = t.history(period="5d")

            if hist.empty:
                return f"'{symbol}' 데이터를 찾을 수 없습니다. 심볼을 확인해주세요."

            cur = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else cur
            chg = cur["Close"] - prev["Close"]
            chg_pct = (chg / prev["Close"]) * 100 if prev["Close"] else 0
            arrow = "▲" if chg >= 0 else "▼"

            name = info.get("longName") or info.get("shortName") or symbol
            sector = info.get("sector", "")
            sector_ko = SECTOR_KO.get(sector, sector)
            industry = info.get("industry", "")
            mcap = info.get("marketCap")
            pe = info.get("trailingPE")
            fwd_pe = info.get("forwardPE")
            pb = info.get("priceToBook")
            div_yield = info.get("dividendYield")
            w52_hi = info.get("fiftyTwoWeekHigh")
            w52_lo = info.get("fiftyTwoWeekLow")
            avg_vol = info.get("averageVolume")
            beta = info.get("beta")
            eps = info.get("trailingEps")
            target = info.get("targetMeanPrice")

            lines = [
                f"## {name} ({symbol})\n",
                f"| 항목 | 값 |",
                f"|------|------|",
                f"| 현재가 | ${cur['Close']:,.2f} |",
                f"| 전일 대비 | {arrow} ${abs(chg):,.2f} ({chg_pct:+.2f}%) |",
                f"| 시가/고가/저가 | ${cur['Open']:,.2f} / ${cur['High']:,.2f} / ${cur['Low']:,.2f} |",
                f"| 거래량 | {cur['Volume']:,.0f} |",
            ]

            if mcap:
                if mcap >= 1e12:
                    lines.append(f"| 시가총액 | ${mcap / 1e12:,.2f}T |")
                else:
                    lines.append(f"| 시가총액 | ${mcap / 1e9:,.1f}B |")
            if sector_ko:
                lines.append(f"| 섹터 | {sector_ko} ({industry}) |")
            if pe:
                lines.append(f"| PER (현재) | {pe:.1f}배 |")
            if fwd_pe:
                lines.append(f"| PER (예상) | {fwd_pe:.1f}배 |")
            if pb:
                lines.append(f"| PBR | {pb:.2f}배 |")
            if eps:
                lines.append(f"| EPS | ${eps:,.2f} |")
            if div_yield:
                lines.append(f"| 배당수익률 | {div_yield * 100:.2f}% |")
            if beta:
                lines.append(f"| 베타 | {beta:.2f} |")
            if w52_hi and w52_lo:
                cur_price = cur["Close"]
                from_hi = ((cur_price - w52_hi) / w52_hi) * 100
                from_lo = ((cur_price - w52_lo) / w52_lo) * 100
                lines.append(f"| 52주 고가 | ${w52_hi:,.2f} ({from_hi:+.1f}%) |")
                lines.append(f"| 52주 저가 | ${w52_lo:,.2f} ({from_lo:+.1f}%) |")
            if avg_vol:
                lines.append(f"| 평균 거래량 | {avg_vol:,.0f} |")
            if target:
                upside = ((target - cur["Close"]) / cur["Close"]) * 100
                lines.append(f"| 애널리스트 목표가 | ${target:,.2f} ({upside:+.1f}%) |")

            return "\n".join(lines)

        except Exception as e:
            logger.error("quote 실패 %s: %s", symbol, e)
            return f"조회 실패 ({symbol}): {e}"

    # ── financials: 재무제표 ─────────────────
    async def _financials(self, kw: dict) -> str:
        yf = _yf()
        if not yf:
            return "yfinance 미설치. pip install yfinance"

        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다. 예: symbol='AAPL'"

        stmt_type = kw.get("type", "income")  # income, balance, cashflow
        period = kw.get("period", "annual")  # annual, quarterly

        try:
            t = yf.Ticker(symbol)
            name = (t.info or {}).get("longName", symbol)

            if stmt_type == "income":
                df = t.quarterly_income_stmt if period == "quarterly" else t.income_stmt
                title = "손익계산서"
            elif stmt_type == "balance":
                df = t.quarterly_balance_sheet if period == "quarterly" else t.balance_sheet
                title = "대차대조표"
            elif stmt_type == "cashflow":
                df = t.quarterly_cashflow if period == "quarterly" else t.cashflow
                title = "현금흐름표"
            else:
                return f"type은 income/balance/cashflow 중 하나. 입력값: {stmt_type}"

            if df is None or df.empty:
                return f"{symbol}의 {title} 데이터가 없습니다."

            # 최근 4기만
            df = df.iloc[:, :4]

            period_label = "분기" if period == "quarterly" else "연간"
            lines = [f"## {name} ({symbol}) — {title} ({period_label})\n"]

            # 컬럼 헤더 (날짜)
            cols = [c.strftime("%Y-%m") if hasattr(c, "strftime") else str(c) for c in df.columns]
            header = "| 항목 | " + " | ".join(cols) + " |"
            sep = "|------|" + "|".join(["------"] * len(cols)) + "|"
            lines.append(header)
            lines.append(sep)

            # 주요 항목만 선택
            key_items_map = {
                "income": [
                    "Total Revenue", "Gross Profit", "Operating Income",
                    "Net Income", "EBITDA", "Basic EPS",
                ],
                "balance": [
                    "Total Assets", "Total Liabilities Net Minority Interest",
                    "Stockholders Equity", "Total Debt", "Cash And Cash Equivalents",
                ],
                "cashflow": [
                    "Operating Cash Flow", "Capital Expenditure",
                    "Free Cash Flow", "Financing Cash Flow",
                ],
            }
            key_items = key_items_map.get(stmt_type, [])

            for item in key_items:
                if item in df.index:
                    vals = []
                    for v in df.loc[item]:
                        if v is not None and v == v:  # not NaN
                            if abs(v) >= 1e9:
                                vals.append(f"${v / 1e9:,.1f}B")
                            elif abs(v) >= 1e6:
                                vals.append(f"${v / 1e6:,.0f}M")
                            else:
                                vals.append(f"${v:,.0f}")
                        else:
                            vals.append("-")
                    item_ko = self._translate_item(item)
                    lines.append(f"| {item_ko} | " + " | ".join(vals) + " |")

            return "\n".join(lines)

        except Exception as e:
            logger.error("financials 실패 %s: %s", symbol, e)
            return f"재무제표 조회 실패 ({symbol}): {e}"

    # ── ohlcv: OHLCV 데이터 ──────────────────
    async def _ohlcv(self, kw: dict) -> str:
        yf = _yf()
        if not yf:
            return "yfinance 미설치. pip install yfinance"

        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        period = kw.get("period", "3mo")
        interval = kw.get("interval", "1d")

        try:
            t = yf.Ticker(symbol)
            hist = t.history(period=period, interval=interval)

            if hist.empty:
                return f"'{symbol}' OHLCV 데이터가 없습니다."

            name = (t.info or {}).get("longName", symbol)
            total_return = ((hist.iloc[-1]["Close"] - hist.iloc[0]["Close"]) / hist.iloc[0]["Close"]) * 100
            high_max = hist["High"].max()
            low_min = hist["Low"].min()
            avg_vol = hist["Volume"].mean()

            lines = [
                f"## {name} ({symbol}) OHLCV — {period} / {interval}\n",
                f"**기간 수익률:** {total_return:+.2f}%  ",
                f"**기간 최고:** ${high_max:,.2f} | **최저:** ${low_min:,.2f}  ",
                f"**평균 거래량:** {avg_vol:,.0f}\n",
            ]

            # 최근 20개 데이터만 표시
            show = hist.tail(20)
            lines.append("| 날짜 | 시가 | 고가 | 저가 | 종가 | 거래량 |")
            lines.append("|------|------|------|------|------|--------|")

            for idx, row in show.iterrows():
                dt = idx.strftime("%m/%d") if hasattr(idx, "strftime") else str(idx)[:10]
                lines.append(
                    f"| {dt} | ${row['Open']:,.2f} | ${row['High']:,.2f} | "
                    f"${row['Low']:,.2f} | ${row['Close']:,.2f} | {row['Volume']:,.0f} |"
                )

            return "\n".join(lines)

        except Exception as e:
            logger.error("ohlcv 실패 %s: %s", symbol, e)
            return f"OHLCV 조회 실패 ({symbol}): {e}"

    # ── indicators: 기술적 지표 ──────────────
    async def _indicators(self, kw: dict) -> str:
        yf = _yf()
        if not yf:
            return "yfinance 미설치. pip install yfinance"

        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        days = int(kw.get("days", 120))

        try:
            t = yf.Ticker(symbol)
            hist = t.history(period=f"{days}d")

            if hist.empty or len(hist) < 20:
                return f"'{symbol}' 충분한 데이터가 없습니다 (최소 20일 필요)."

            name = (t.info or {}).get("longName", symbol)
            close = hist["Close"]
            high = hist["High"]
            low = hist["Low"]
            volume = hist["Volume"]

            # 이동평균
            ma5 = close.rolling(5).mean()
            ma20 = close.rolling(20).mean()
            ma60 = close.rolling(60).mean() if len(close) >= 60 else None

            # RSI (14일)
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            # MACD
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9).mean()
            macd_hist = macd_line - signal_line

            # 볼린저밴드
            bb_mid = close.rolling(20).mean()
            bb_std = close.rolling(20).std()
            bb_upper = bb_mid + 2 * bb_std
            bb_lower = bb_mid - 2 * bb_std

            # 최신 값
            cur_price = close.iloc[-1]
            cur_rsi = rsi.iloc[-1]
            cur_macd = macd_line.iloc[-1]
            cur_signal = signal_line.iloc[-1]
            cur_bb_upper = bb_upper.iloc[-1]
            cur_bb_lower = bb_lower.iloc[-1]
            cur_ma5 = ma5.iloc[-1]
            cur_ma20 = ma20.iloc[-1]
            cur_ma60 = ma60.iloc[-1] if ma60 is not None and len(ma60.dropna()) > 0 else None

            # 거래량 분석
            vol_avg20 = volume.rolling(20).mean().iloc[-1]
            vol_ratio = volume.iloc[-1] / vol_avg20 if vol_avg20 > 0 else 0

            # RSI 판정
            if cur_rsi >= 70:
                rsi_signal = "과매수 (매도 주의)"
            elif cur_rsi <= 30:
                rsi_signal = "과매도 (매수 기회)"
            else:
                rsi_signal = "중립"

            # MACD 판정
            macd_signal = "매수 시그널 (골든크로스)" if cur_macd > cur_signal else "매도 시그널 (데드크로스)"

            # 볼린저밴드 위치
            bb_pos = ((cur_price - cur_bb_lower) / (cur_bb_upper - cur_bb_lower)) * 100 if (cur_bb_upper - cur_bb_lower) > 0 else 50

            lines = [
                f"## {name} ({symbol}) 기술적 지표\n",
                f"| 지표 | 값 | 판정 |",
                f"|------|------|------|",
                f"| 현재가 | ${cur_price:,.2f} | - |",
                f"| RSI (14) | {cur_rsi:.1f} | {rsi_signal} |",
                f"| MACD | {cur_macd:.2f} | {macd_signal} |",
                f"| MACD 시그널 | {cur_signal:.2f} | - |",
                f"| 볼린저 상단 | ${cur_bb_upper:,.2f} | - |",
                f"| 볼린저 하단 | ${cur_bb_lower:,.2f} | - |",
                f"| BB 위치 | {bb_pos:.0f}% | {'상단 근접' if bb_pos > 80 else '하단 근접' if bb_pos < 20 else '중간'} |",
                f"| MA5 | ${cur_ma5:,.2f} | {'위' if cur_price > cur_ma5 else '아래'} |",
                f"| MA20 | ${cur_ma20:,.2f} | {'위' if cur_price > cur_ma20 else '아래'} |",
            ]
            if cur_ma60 is not None:
                lines.append(f"| MA60 | ${cur_ma60:,.2f} | {'위' if cur_price > cur_ma60 else '아래'} |")

            lines.append(f"| 거래량 비율 | {vol_ratio:.2f}x | {'급증' if vol_ratio > 2 else '보통' if vol_ratio > 0.5 else '급감'} |")

            # 종합 시그널 카운트
            bullish = 0
            bearish = 0
            if cur_rsi <= 30:
                bullish += 1
            elif cur_rsi >= 70:
                bearish += 1
            if cur_macd > cur_signal:
                bullish += 1
            else:
                bearish += 1
            if cur_price > cur_ma20:
                bullish += 1
            else:
                bearish += 1
            if bb_pos < 20:
                bullish += 1
            elif bb_pos > 80:
                bearish += 1

            total = bullish + bearish
            if total > 0:
                if bullish > bearish:
                    verdict = f"매수 우세 ({bullish}/{total})"
                elif bearish > bullish:
                    verdict = f"매도 우세 ({bearish}/{total})"
                else:
                    verdict = "중립"
            else:
                verdict = "판단 불가"

            lines.append(f"\n**종합 판정:** {verdict}")

            # LLM 분석
            data_summary = "\n".join(lines)
            analysis = await self._llm_call(
                system_prompt=(
                    "당신은 미국 주식 기술적분석 전문가입니다. "
                    "주어진 기술적 지표를 종합 분석하여 단기(1주) 방향성과 "
                    "주요 지지/저항 수준을 한국어로 제시하세요. 간결하게 5줄 이내."
                ),
                user_prompt=data_summary,
            )
            lines.append(f"\n---\n### AI 분석\n{analysis}")

            return "\n".join(lines)

        except Exception as e:
            logger.error("indicators 실패 %s: %s", symbol, e)
            return f"기술적 지표 조회 실패 ({symbol}): {e}"

    # ── peers: 동종업체 비교 ─────────────────
    async def _peers(self, kw: dict) -> str:
        yf = _yf()
        if not yf:
            return "yfinance 미설치. pip install yfinance"

        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        peers_str = kw.get("peers", "")
        if peers_str:
            if isinstance(peers_str, list):
                peer_list = [s.upper().strip() for s in peers_str]
            else:
                peer_list = [s.upper().strip() for s in peers_str.split(",")]
        else:
            # 같은 섹터 대표종목 자동 매칭
            t = yf.Ticker(symbol)
            sector = (t.info or {}).get("sector", "")
            peer_list = self._get_sector_peers(symbol, sector)

        all_symbols = [symbol] + [p for p in peer_list if p != symbol]

        lines = [f"## {symbol} 동종업체 비교\n"]
        lines.append("| 종목 | 현재가 | 시총 | PER | PBR | 배당률 | 베타 | 52주 수익률 |")
        lines.append("|------|--------|------|-----|-----|--------|------|-----------|")

        for sym in all_symbols[:8]:  # 최대 8개
            try:
                t = yf.Ticker(sym)
                info = t.info or {}
                price_data = t.history(period="5d")
                cur_price = price_data.iloc[-1]["Close"] if not price_data.empty else 0

                mcap = info.get("marketCap", 0)
                mcap_str = f"${mcap / 1e12:,.1f}T" if mcap >= 1e12 else f"${mcap / 1e9:,.0f}B" if mcap else "-"
                pe = info.get("trailingPE")
                pe_str = f"{pe:.1f}" if pe else "-"
                pb = info.get("priceToBook")
                pb_str = f"{pb:.2f}" if pb else "-"
                div_y = info.get("dividendYield")
                div_str = f"{div_y * 100:.1f}%" if div_y else "-"
                beta = info.get("beta")
                beta_str = f"{beta:.2f}" if beta else "-"

                # 52주 수익률
                hist_1y = t.history(period="1y")
                if not hist_1y.empty and len(hist_1y) > 1:
                    ret_1y = ((hist_1y.iloc[-1]["Close"] - hist_1y.iloc[0]["Close"]) / hist_1y.iloc[0]["Close"]) * 100
                    ret_str = f"{ret_1y:+.1f}%"
                else:
                    ret_str = "-"

                mark = " **←**" if sym == symbol else ""
                lines.append(
                    f"| {sym}{mark} | ${cur_price:,.2f} | {mcap_str} | {pe_str} | "
                    f"{pb_str} | {div_str} | {beta_str} | {ret_str} |"
                )
            except Exception:
                lines.append(f"| {sym} | 조회실패 | - | - | - | - | - | - |")

        return "\n".join(lines)

    # ── earnings: 실적 서프라이즈 ─────────────
    async def _earnings(self, kw: dict) -> str:
        yf = _yf()
        if not yf:
            return "yfinance 미설치. pip install yfinance"

        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        try:
            t = yf.Ticker(symbol)
            name = (t.info or {}).get("longName", symbol)

            # 분기별 실적
            earnings = getattr(t, "quarterly_earnings", None)
            if earnings is not None and not earnings.empty:
                lines = [f"## {name} ({symbol}) 실적 서프라이즈\n"]
                lines.append("| 분기 | 실제 EPS | 예상 EPS | 서프라이즈 |")
                lines.append("|------|---------|---------|----------|")

                for idx, row in earnings.iterrows():
                    actual = row.get("Actual") or row.get("Revenue")
                    estimate = row.get("Estimate")
                    if actual is not None and estimate is not None and estimate != 0:
                        surprise_pct = ((actual - estimate) / abs(estimate)) * 100
                        emoji = "Beat" if surprise_pct > 0 else "Miss"
                        lines.append(
                            f"| {idx} | ${actual:,.2f} | ${estimate:,.2f} | "
                            f"{emoji} {surprise_pct:+.1f}% |"
                        )
                    elif actual is not None:
                        lines.append(f"| {idx} | ${actual:,.2f} | - | - |")

                return "\n".join(lines)

            # earnings_dates 폴백
            dates = getattr(t, "earnings_dates", None)
            if dates is not None and not dates.empty:
                lines = [f"## {name} ({symbol}) 실적 발표 일정\n"]
                lines.append("| 발표일 | 예상 EPS | 실제 EPS | 서프라이즈 |")
                lines.append("|--------|---------|---------|----------|")

                for idx, row in dates.head(8).iterrows():
                    dt = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                    est = row.get("EPS Estimate")
                    act = row.get("Reported EPS")
                    if act is not None and est is not None and est != 0:
                        surp = ((act - est) / abs(est)) * 100
                        lines.append(f"| {dt} | ${est:,.2f} | ${act:,.2f} | {surp:+.1f}% |")
                    elif est is not None:
                        lines.append(f"| {dt} | ${est:,.2f} | 미발표 | - |")
                    else:
                        lines.append(f"| {dt} | - | - | - |")

                return "\n".join(lines)

            return f"{symbol}의 실적 데이터가 없습니다."

        except Exception as e:
            logger.error("earnings 실패 %s: %s", symbol, e)
            return f"실적 조회 실패 ({symbol}): {e}"

    # ── screener: 종목 스크리닝 ──────────────
    async def _screener(self, kw: dict) -> str:
        yf = _yf()
        if not yf:
            return "yfinance 미설치. pip install yfinance"

        category = kw.get("category", "기술대형")

        if category not in POPULAR:
            return (
                f"카테고리: {category} 없음.\n"
                "사용 가능: " + ", ".join(POPULAR.keys())
            )

        symbols = POPULAR[category]
        lines = [f"## {category} 종목 스크리닝\n"]
        lines.append("| 종목 | 이름 | 현재가 | 등락률 | 시총 | PER |")
        lines.append("|------|------|--------|--------|------|-----|")

        for sym in symbols:
            try:
                t = yf.Ticker(sym)
                info = t.info or {}
                hist = t.history(period="5d")
                if hist.empty:
                    continue
                cur = hist.iloc[-1]["Close"]
                prev = hist.iloc[-2]["Close"] if len(hist) > 1 else cur
                chg = ((cur - prev) / prev) * 100 if prev else 0
                name_short = (info.get("shortName") or sym)[:15]
                mcap = info.get("marketCap", 0)
                mcap_s = f"${mcap / 1e12:,.1f}T" if mcap >= 1e12 else f"${mcap / 1e9:,.0f}B" if mcap else "-"
                pe = info.get("trailingPE")
                pe_s = f"{pe:.1f}" if pe else "-"
                arrow = "▲" if chg >= 0 else "▼"
                lines.append(f"| {sym} | {name_short} | ${cur:,.2f} | {arrow}{abs(chg):.2f}% | {mcap_s} | {pe_s} |")
            except Exception:
                lines.append(f"| {sym} | - | - | - | - | - |")

        return "\n".join(lines)

    # ── 헬퍼 함수들 ─────────────────────────
    def _translate_item(self, item: str) -> str:
        """재무제표 항목명 한국어 변환."""
        trans = {
            "Total Revenue": "매출",
            "Gross Profit": "매출총이익",
            "Operating Income": "영업이익",
            "Net Income": "순이익",
            "EBITDA": "EBITDA",
            "Basic EPS": "주당순이익(EPS)",
            "Total Assets": "총자산",
            "Total Liabilities Net Minority Interest": "총부채",
            "Stockholders Equity": "자기자본",
            "Total Debt": "총차입금",
            "Cash And Cash Equivalents": "현금성자산",
            "Operating Cash Flow": "영업현금흐름",
            "Capital Expenditure": "설비투자(CAPEX)",
            "Free Cash Flow": "잉여현금흐름(FCF)",
            "Financing Cash Flow": "재무현금흐름",
        }
        return trans.get(item, item)

    def _get_sector_peers(self, symbol: str, sector: str) -> list[str]:
        """섹터 기반 동종업체 자동 매칭."""
        sector_map = {
            "Technology": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META"],
            "Healthcare": ["UNH", "JNJ", "PFE", "ABBV", "LLY", "MRK"],
            "Financial Services": ["JPM", "BAC", "GS", "MS", "WFC", "BRK-B"],
            "Financials": ["JPM", "BAC", "GS", "MS", "WFC", "BRK-B"],
            "Consumer Cyclical": ["AMZN", "TSLA", "HD", "NKE", "MCD", "SBUX"],
            "Consumer Defensive": ["PG", "KO", "PEP", "WMT", "COST", "CL"],
            "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "CMCSA"],
            "Industrials": ["CAT", "BA", "HON", "UPS", "GE", "MMM"],
            "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
            "Utilities": ["NEE", "DUK", "SO", "D", "AEP"],
            "Real Estate": ["PLD", "AMT", "CCI", "EQIX", "SPG"],
            "Basic Materials": ["LIN", "APD", "SHW", "ECL", "FCX"],
        }
        peers = sector_map.get(sector, ["SPY", "QQQ"])
        return [p for p in peers if p != symbol][:5]
