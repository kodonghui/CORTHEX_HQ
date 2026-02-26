"""
기술적 분석 도구 (Technical Analyzer) — 교수급 30개 지표 + 캔들 패턴 + 종합 매매 판단.

기존 kr_stock의 indicators(RSI/MACD/BB 3개)를 확장하여,
금융공학 교수 수준의 체계적 기술적 분석을 제공합니다.

학술 근거:
  - 기술적 분석 이론 (John J. Murphy, "Technical Analysis of the Financial Markets")
  - 캔들 차트 분석 (Steve Nison, "Japanese Candlestick Charting Techniques")
  - 모멘텀 전략 (Jegadeesh & Titman, 1993)

사용 방법:
  - action="full"     : 30개 지표 종합 분석 (전체)
  - action="trend"    : 추세 지표 (MA, ADX, Ichimoku)
  - action="momentum" : 모멘텀 지표 (RSI, MACD, Stochastic, CCI 등)
  - action="volatility": 변동성 지표 (BB, ATR, Historical Vol)
  - action="volume"   : 거래량 지표 (OBV, VWAP, CMF 등)
  - action="pattern"  : 캔들 패턴 인식 (도지, 해머, 인걸핑 등)
  - action="support_resistance": 지지선/저항선 자동 계산
  - action="signal"   : 매매 신호 종합 (BUY/SELL/HOLD 스코어)

필요 환경변수: 없음 (pykrx 무료, API 키 불필요)
필요 라이브러리: pykrx, pandas, numpy, pandas-ta
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.technical_analyzer")


# ═══════════════════════════════════════════════════════
#  라이브러리 임포트 (설치 안 되어 있으면 안내)
# ═══════════════════════════════════════════════════════

def _import_pykrx():
    try:
        from pykrx import stock
        return stock
    except ImportError:
        return None


def _import_pandas_ta():
    try:
        import pandas_ta as ta
        return ta
    except ImportError:
        return None


# ═══════════════════════════════════════════════════════
#  TechnicalAnalyzerTool
# ═══════════════════════════════════════════════════════

class TechnicalAnalyzerTool(BaseTool):
    """교수급 기술적 분석 도구 — 30개 지표 + 캔들 패턴 + 종합 매매 판단."""

    # ── 메인 디스패처 ────────────────────────

    async def execute(self, **kwargs: Any) -> str:
        # query 폴백
        query = kwargs.get("query", "")
        if query and not kwargs.get("name") and not kwargs.get("ticker"):
            kwargs["name"] = query

        action = kwargs.get("action", "full")

        actions = {
            "full": self._full_analysis,
            "trend": self._trend_analysis,
            "momentum": self._momentum_analysis,
            "volatility": self._volatility_analysis,
            "volume": self._volume_analysis,
            "pattern": self._pattern_analysis,
            "support_resistance": self._support_resistance,
            "signal": self._signal_summary,
        }

        handler = actions.get(action)
        if handler:
            return await handler(kwargs)

        return (
            f"알 수 없는 action: {action}. "
            "full, trend, momentum, volatility, volume, pattern, "
            "support_resistance, signal 중 하나를 사용하세요."
        )

    # ── 공통: OHLCV 데이터 로드 ─────────────

    async def _load_ohlcv(self, kwargs: dict) -> tuple:
        """종목의 OHLCV 데이터를 로드합니다. (ticker, name, DataFrame) 반환.
        ARGOS DB 우선 → pykrx 폴백."""
        ticker = kwargs.get("ticker", "")
        name = kwargs.get("name", "")
        if not ticker and not name:
            return None, None, "종목코드(ticker) 또는 종목명(name)을 입력해주세요. 예: name='삼성전자'"

        stock = _import_pykrx()

        # 종목명만 있으면 ticker 변환 (pykrx 필요)
        if name and not ticker:
            if stock is None:
                return None, None, "pykrx 라이브러리가 필요합니다.\n터미널에서: pip install pykrx"
            ticker = await self._resolve_ticker(stock, name)
            if not ticker:
                return None, None, f"'{name}' 종목을 찾을 수 없습니다."

        days = int(kwargs.get("days", 200))  # 기본 200일 (장기 지표용)

        # ① ARGOS DB 우선 (서버 수집 캐시)
        try:
            from src.tools._argos_reader import get_price_dataframe
            argos_df = get_price_dataframe(ticker, days)
            if argos_df is not None and len(argos_df) >= 20:
                stock_name = name or (await self._get_stock_name(stock, ticker) if stock else ticker)
                logger.info("[ARGOS] %s OHLCV %d일 캐시 사용", ticker, len(argos_df))
                return ticker, stock_name, argos_df
        except Exception as e:
            logger.debug("ARGOS OHLCV fallback: %s", e)

        # ② pykrx 폴백
        if stock is None:
            return None, None, "pykrx 라이브러리가 필요합니다.\n터미널에서: pip install pykrx"

        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        try:
            df = await asyncio.to_thread(
                stock.get_market_ohlcv_by_date, start, end, ticker
            )
        except Exception as e:
            return None, None, f"데이터 조회 실패: {e}"

        if df.empty or len(df) < 20:
            return None, None, f"종목코드 {ticker}의 데이터가 부족합니다 (최소 20일 필요, 현재 {len(df)}일)."

        stock_name = await self._get_stock_name(stock, ticker)
        return ticker, stock_name, df

    async def _resolve_ticker(self, stock, name: str) -> str | None:
        """종목명 → 종목코드 변환."""
        try:
            today = datetime.now().strftime("%Y%m%d")
            tickers = await asyncio.to_thread(stock.get_market_ticker_list, today, market="ALL")
            for t in tickers:
                t_name = await asyncio.to_thread(stock.get_market_ticker_name, t)
                if t_name == name:
                    return t
        except Exception:
            pass
        return None

    async def _get_stock_name(self, stock, ticker: str) -> str:
        """종목코드 → 종목명 변환."""
        try:
            return await asyncio.to_thread(stock.get_market_ticker_name, ticker)
        except Exception:
            return ticker

    @staticmethod
    def _install_msg(lib: str) -> str:
        return f"{lib} 라이브러리가 설치되지 않았습니다.\n터미널에서: pip install {lib}"

    @staticmethod
    def _fmt(val, decimals=1) -> str:
        """숫자 포맷팅 (None 안전)."""
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return "N/A"
        if abs(val) >= 1000:
            return f"{val:,.0f}"
        return f"{val:.{decimals}f}"

    @staticmethod
    def _arrow(val) -> str:
        """양수면 ▲, 음수면 ▼, 0이면 ─."""
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return "─"
        return "▲" if val > 0 else "▼" if val < 0 else "─"

    # ═══════════════════════════════════════════
    #  1. 추세 분석 (Trend)
    # ═══════════════════════════════════════════

    async def _trend_analysis(self, kwargs: dict) -> str:
        ta = _import_pandas_ta()
        if ta is None:
            return self._install_msg("pandas-ta")

        ticker, name, result = await self._load_ohlcv(kwargs)
        if ticker is None:
            return result
        df = result

        close = df["종가"]
        high = df["고가"]
        low = df["저가"]
        current = close.iloc[-1]

        lines = [f"## {name} ({ticker}) 추세 분석\n"]
        lines.append(f"현재가: **{current:,.0f}원** | 분석일: {datetime.now().strftime('%Y-%m-%d')}\n")

        # ── 이동평균선 (SMA) ──
        lines.append("### 이동평균선 (SMA)")
        ma_periods = [5, 10, 20, 60, 120]
        ma_values = {}
        for p in ma_periods:
            if len(df) >= p:
                ma = close.rolling(p).mean().iloc[-1]
                ma_values[p] = ma
                pos = "위" if current > ma else "아래"
                lines.append(f"  {p}일선: {ma:,.0f}원 (현재가 {pos} {self._arrow(current - ma)})")

        # 정배열/역배열 판단
        avail = [ma_values[p] for p in sorted(ma_values.keys()) if p in ma_values]
        if len(avail) >= 3:
            if all(avail[i] >= avail[i + 1] for i in range(len(avail) - 1)):
                lines.append("  **→ 역배열 (단기 < 장기): 하락 추세**")
            elif all(avail[i] <= avail[i + 1] for i in range(len(avail) - 1)):
                lines.append("  **→ 정배열 (단기 > 장기): 상승 추세**")
            else:
                lines.append("  **→ 혼조세 (정배열도 역배열도 아님)**")

        # ── EMA ──
        lines.append("\n### 지수이동평균선 (EMA)")
        ema12 = ta.ema(close, length=12)
        ema26 = ta.ema(close, length=26)
        if ema12 is not None and ema26 is not None:
            e12 = ema12.iloc[-1]
            e26 = ema26.iloc[-1]
            lines.append(f"  EMA 12: {e12:,.0f}원 | EMA 26: {e26:,.0f}원")
            lines.append(f"  EMA 크로스: {'골든크로스 (매수)' if e12 > e26 else '데드크로스 (매도)'}")

        # ── ADX (추세 강도) ──
        lines.append("\n### ADX (추세 강도)")
        adx_df = ta.adx(high, low, close, length=14)
        if adx_df is not None and not adx_df.empty:
            adx_val = adx_df.iloc[-1, 0]  # ADX
            di_plus = adx_df.iloc[-1, 1]  # +DI
            di_minus = adx_df.iloc[-1, 2]  # -DI
            strength = "강한 추세" if adx_val > 25 else "약한 추세/횡보"
            direction = "상승" if di_plus > di_minus else "하락"
            lines.append(f"  ADX: {self._fmt(adx_val)} ({strength})")
            lines.append(f"  +DI: {self._fmt(di_plus)} | -DI: {self._fmt(di_minus)} → {direction} 방향")

        # ── Parabolic SAR ──
        lines.append("\n### Parabolic SAR")
        try:
            psar = ta.psar(high, low, close)
            if psar is not None and not psar.empty:
                # pandas-ta returns PSARl (long) and PSARs (short)
                cols = psar.columns
                long_col = [c for c in cols if 'long' in c.lower() or 'l_' in c.lower()]
                short_col = [c for c in cols if 'short' in c.lower() or 's_' in c.lower()]
                if long_col and not math.isnan(psar[long_col[0]].iloc[-1]):
                    lines.append(f"  SAR (롱): {psar[long_col[0]].iloc[-1]:,.0f}원 → **상승 추세 유지**")
                elif short_col and not math.isnan(psar[short_col[0]].iloc[-1]):
                    lines.append(f"  SAR (숏): {psar[short_col[0]].iloc[-1]:,.0f}원 → **하락 추세 유지**")
        except Exception:
            lines.append("  SAR: 계산 불가")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 금융공학 교수입니다. 추세 분석 데이터를 종합하여:\n"
                "1. 현재 추세 상태 (강한 상승/약한 상승/횡보/약한 하락/강한 하락)\n"
                "2. 이동평균선 배열이 의미하는 바\n"
                "3. ADX가 시사하는 추세 강도\n"
                "4. 향후 추세 전환 가능성\n"
                "구체적 수치를 포함하여 한국어로 간결하게 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 추세 종합 분석\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  2. 모멘텀 분석 (Momentum)
    # ═══════════════════════════════════════════

    async def _momentum_analysis(self, kwargs: dict) -> str:
        ta = _import_pandas_ta()
        if ta is None:
            return self._install_msg("pandas-ta")

        ticker, name, result = await self._load_ohlcv(kwargs)
        if ticker is None:
            return result
        df = result

        close = df["종가"]
        high = df["고가"]
        low = df["저가"]
        volume = df["거래량"]
        current = close.iloc[-1]

        lines = [f"## {name} ({ticker}) 모멘텀 분석\n"]
        lines.append(f"현재가: **{current:,.0f}원**\n")

        # ── RSI (14일) ──
        rsi_series = ta.rsi(close, length=14)
        rsi = rsi_series.iloc[-1] if rsi_series is not None and not rsi_series.empty else None
        if rsi is not None:
            zone = "과매수 (70+)" if rsi > 70 else "과매도 (30-)" if rsi < 30 else "중립"
            lines.append(f"### RSI (14일): {self._fmt(rsi)} — {zone}")
            lines.append(f"  해석: RSI {self._fmt(rsi)}은 {'매도 고려' if rsi > 70 else '매수 고려' if rsi < 30 else '방향성 없음'}")

        # ── MACD (12, 26, 9) ──
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            cols = macd_df.columns
            macd_val = macd_df[cols[0]].iloc[-1]
            macd_sig = macd_df[cols[1]].iloc[-1]
            macd_hist = macd_df[cols[2]].iloc[-1]
            cross = "골든크로스 (매수)" if macd_val > macd_sig else "데드크로스 (매도)"
            lines.append(f"\n### MACD (12,26,9)")
            lines.append(f"  MACD: {self._fmt(macd_val)} | Signal: {self._fmt(macd_sig)} | Histogram: {self._fmt(macd_hist)}")
            lines.append(f"  상태: **{cross}** | 히스토그램 {self._arrow(macd_hist)}")

        # ── Stochastic (14, 3, 3) ──
        stoch_df = ta.stoch(high, low, close, k=14, d=3, smooth_k=3)
        if stoch_df is not None and not stoch_df.empty:
            cols = stoch_df.columns
            k_val = stoch_df[cols[0]].iloc[-1]
            d_val = stoch_df[cols[1]].iloc[-1]
            zone = "과매수" if k_val > 80 else "과매도" if k_val < 20 else "중립"
            lines.append(f"\n### Stochastic (14,3,3)")
            lines.append(f"  %K: {self._fmt(k_val)} | %D: {self._fmt(d_val)} — {zone}")

        # ── CCI (20일) ──
        cci_series = ta.cci(high, low, close, length=20)
        if cci_series is not None and not cci_series.empty:
            cci = cci_series.iloc[-1]
            zone = "과매수 (100+)" if cci > 100 else "과매도 (-100-)" if cci < -100 else "중립"
            lines.append(f"\n### CCI (20일): {self._fmt(cci)} — {zone}")

        # ── Williams %R (14일) ──
        willr_series = ta.willr(high, low, close, length=14)
        if willr_series is not None and not willr_series.empty:
            willr = willr_series.iloc[-1]
            zone = "과매수" if willr > -20 else "과매도" if willr < -80 else "중립"
            lines.append(f"\n### Williams %R (14일): {self._fmt(willr)} — {zone}")

        # ── ROC (Rate of Change, 12일) ──
        roc_series = ta.roc(close, length=12)
        if roc_series is not None and not roc_series.empty:
            roc = roc_series.iloc[-1]
            lines.append(f"\n### ROC (12일): {self._fmt(roc)}% — 12일 전 대비 {'상승' if roc > 0 else '하락'}")

        # ── MFI (Money Flow Index, 14일) ──
        mfi_series = ta.mfi(high, low, close, volume, length=14)
        if mfi_series is not None and not mfi_series.empty:
            mfi = mfi_series.iloc[-1]
            zone = "자금 과열" if mfi > 80 else "자금 위축" if mfi < 20 else "중립"
            lines.append(f"\n### MFI (14일): {self._fmt(mfi)} — {zone}")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 금융공학 교수입니다. 모멘텀 지표를 종합하여:\n"
                "1. 현재 모멘텀 상태 (강한 매수/약한 매수/중립/약한 매도/강한 매도)\n"
                "2. 과매수/과매도 구간 진입 여부와 의미\n"
                "3. 다이버전스 가능성 (가격↑ + 지표↓ = 약세 다이버전스)\n"
                "4. 향후 모멘텀 전환 시기 예측\n"
                "구체적 수치를 포함하여 한국어로 간결하게 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 모멘텀 종합 분석\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  3. 변동성 분석 (Volatility)
    # ═══════════════════════════════════════════

    async def _volatility_analysis(self, kwargs: dict) -> str:
        ta = _import_pandas_ta()
        if ta is None:
            return self._install_msg("pandas-ta")

        ticker, name, result = await self._load_ohlcv(kwargs)
        if ticker is None:
            return result
        df = result

        close = df["종가"]
        high = df["고가"]
        low = df["저가"]
        current = close.iloc[-1]

        lines = [f"## {name} ({ticker}) 변동성 분석\n"]
        lines.append(f"현재가: **{current:,.0f}원**\n")

        # ── 볼린저밴드 (20, 2) ──
        bb_df = ta.bbands(close, length=20, std=2)
        if bb_df is not None and not bb_df.empty:
            cols = bb_df.columns
            bb_lower = bb_df[cols[0]].iloc[-1]
            bb_mid = bb_df[cols[1]].iloc[-1]
            bb_upper = bb_df[cols[2]].iloc[-1]
            bb_bandwidth = bb_df[cols[3]].iloc[-1] if len(cols) > 3 else (bb_upper - bb_lower) / bb_mid * 100
            bb_pctb = bb_df[cols[4]].iloc[-1] if len(cols) > 4 else (current - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5

            lines.append("### 볼린저밴드 (20, 2σ)")
            lines.append(f"  상단: {bb_upper:,.0f}원 | 중간: {bb_mid:,.0f}원 | 하단: {bb_lower:,.0f}원")
            lines.append(f"  %B: {self._fmt(bb_pctb)} (0=하단, 0.5=중간, 1=상단)")
            lines.append(f"  밴드폭: {self._fmt(bb_bandwidth)}%")

            if current > bb_upper:
                lines.append("  **→ 상단 돌파: 과매수 또는 강한 상승 추세**")
            elif current < bb_lower:
                lines.append("  **→ 하단 이탈: 과매도 또는 강한 하락 추세**")
            elif bb_bandwidth is not None and bb_bandwidth < 5:
                lines.append("  **→ 밴드 수축 (스퀴즈): 큰 움직임 임박 가능**")

        # ── ATR (Average True Range, 14일) ──
        atr_series = ta.atr(high, low, close, length=14)
        if atr_series is not None and not atr_series.empty:
            atr = atr_series.iloc[-1]
            atr_pct = atr / current * 100
            lines.append(f"\n### ATR (14일): {self._fmt(atr)}원 ({self._fmt(atr_pct)}%)")
            lines.append(f"  해석: 하루 평균 {self._fmt(atr)}원 변동 (현재가의 {self._fmt(atr_pct)}%)")
            if atr_pct > 3:
                lines.append("  **→ 고변동성 구간 (리스크 높음)**")
            elif atr_pct < 1:
                lines.append("  **→ 저변동성 구간 (안정적)**")

        # ── Historical Volatility (20일) ──
        returns = close.pct_change().dropna()
        if len(returns) >= 20:
            hvol_20 = returns.tail(20).std() * np.sqrt(252) * 100  # 연율화
            hvol_60 = returns.tail(60).std() * np.sqrt(252) * 100 if len(returns) >= 60 else None
            lines.append(f"\n### 역사적 변동성 (연율화)")
            lines.append(f"  20일: {self._fmt(hvol_20)}%")
            if hvol_60:
                lines.append(f"  60일: {self._fmt(hvol_60)}%")
                if hvol_20 > hvol_60 * 1.2:
                    lines.append("  **→ 단기 변동성 급증 (경계 필요)**")
                elif hvol_20 < hvol_60 * 0.8:
                    lines.append("  **→ 단기 변동성 감소 (변동성 확대 전 조용한 시기 가능)**")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 금융공학 교수입니다. 변동성 지표를 종합하여:\n"
                "1. 현재 변동성 수준 (높음/보통/낮음)\n"
                "2. 볼린저밴드 스퀴즈/확장이 의미하는 바\n"
                "3. ATR 기반 적정 손절폭 제안 (현재 ATR의 1.5~2배)\n"
                "4. 향후 변동성 전망\n"
                "구체적 수치를 포함하여 한국어로 간결하게 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 변동성 종합 분석\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  4. 거래량 분석 (Volume)
    # ═══════════════════════════════════════════

    async def _volume_analysis(self, kwargs: dict) -> str:
        ta = _import_pandas_ta()
        if ta is None:
            return self._install_msg("pandas-ta")

        ticker, name, result = await self._load_ohlcv(kwargs)
        if ticker is None:
            return result
        df = result

        close = df["종가"]
        high = df["고가"]
        low = df["저가"]
        volume = df["거래량"]
        current = close.iloc[-1]

        lines = [f"## {name} ({ticker}) 거래량 분석\n"]
        lines.append(f"현재가: **{current:,.0f}원** | 오늘 거래량: {volume.iloc[-1]:,.0f}주\n")

        # ── 거래량 이동평균 비교 ──
        vol_ma5 = volume.rolling(5).mean().iloc[-1]
        vol_ma20 = volume.rolling(20).mean().iloc[-1]
        vol_ratio = volume.iloc[-1] / vol_ma20 if vol_ma20 > 0 else 0

        lines.append("### 거래량 이동평균")
        lines.append(f"  5일 평균: {vol_ma5:,.0f}주 | 20일 평균: {vol_ma20:,.0f}주")
        lines.append(f"  오늘/20일평균 비율: {self._fmt(vol_ratio)}배")
        if vol_ratio > 2:
            lines.append("  **→ 거래량 폭증 (돌파/붕괴 신호 가능)**")
        elif vol_ratio < 0.5:
            lines.append("  **→ 거래량 급감 (관심 이탈 또는 에너지 축적)**")

        # ── OBV (On Balance Volume) ──
        obv_series = ta.obv(close, volume)
        if obv_series is not None and not obv_series.empty:
            obv = obv_series.iloc[-1]
            obv_ma = obv_series.rolling(20).mean().iloc[-1]
            lines.append(f"\n### OBV (On Balance Volume)")
            lines.append(f"  OBV: {obv:,.0f} | OBV 20일 MA: {obv_ma:,.0f}")
            if obv > obv_ma:
                lines.append("  **→ OBV 상승 추세: 매수세 우위**")
            else:
                lines.append("  **→ OBV 하락 추세: 매도세 우위**")

        # ── CMF (Chaikin Money Flow, 20일) ──
        cmf_series = ta.cmf(high, low, close, volume, length=20)
        if cmf_series is not None and not cmf_series.empty:
            cmf = cmf_series.iloc[-1]
            lines.append(f"\n### CMF (20일): {self._fmt(cmf)}")
            lines.append(f"  해석: {'자금 유입 (매수 압력)' if cmf > 0 else '자금 유출 (매도 압력)'}")

        # ── AD (Accumulation/Distribution) ──
        ad_series = ta.ad(high, low, close, volume)
        if ad_series is not None and not ad_series.empty:
            ad = ad_series.iloc[-1]
            ad_prev = ad_series.iloc[-5] if len(ad_series) >= 5 else ad_series.iloc[0]
            lines.append(f"\n### AD (Accumulation/Distribution)")
            lines.append(f"  AD: {ad:,.0f} | 5일 전: {ad_prev:,.0f}")
            lines.append(f"  추세: {'매집 (Accumulation)' if ad > ad_prev else '분산 (Distribution)'}")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 금융공학 교수입니다. 거래량 지표를 종합하여:\n"
                "1. 현재 거래량 상태 (활발/보통/침체)\n"
                "2. 가격-거래량 괴리 (가격↑+거래량↓ = 의심스러운 상승)\n"
                "3. 매집/분산 판단 (기관/외국인 흐름 추정)\n"
                "4. 향후 거래량 전망\n"
                "구체적 수치를 포함하여 한국어로 간결하게 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 거래량 종합 분석\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  5. 캔들 패턴 인식 (Pattern)
    # ═══════════════════════════════════════════

    async def _pattern_analysis(self, kwargs: dict) -> str:
        ticker, name, result = await self._load_ohlcv(kwargs)
        if ticker is None:
            return result
        df = result

        o = df["시가"]
        h = df["고가"]
        l = df["저가"]
        c = df["종가"]
        current = c.iloc[-1]

        lines = [f"## {name} ({ticker}) 캔들 패턴 분석\n"]
        lines.append(f"현재가: **{current:,.0f}원** | 최근 5일 캔들 패턴 인식\n")

        # 최근 5일 데이터로 패턴 인식
        patterns_found = []

        for i in range(-3, 0):  # 최근 3일 검사
            idx = len(df) + i
            if idx < 1:
                continue

            op, hi, lo, cl = o.iloc[idx], h.iloc[idx], l.iloc[idx], c.iloc[idx]
            body = abs(cl - op)
            total_range = hi - lo if hi - lo > 0 else 1
            upper_shadow = hi - max(cl, op)
            lower_shadow = min(cl, op) - lo
            date_str = df.index[idx].strftime("%m/%d") if hasattr(df.index[idx], 'strftime') else str(idx)

            # 도지 (Doji): 몸통이 전체의 10% 이하
            if body / total_range < 0.1:
                patterns_found.append(f"  {date_str}: **도지 (Doji)** — 매수/매도 균형, 추세 전환 가능")

            # 해머 (Hammer): 긴 아래꼬리 + 짧은 몸통 (하락 추세 끝에서 반전 신호)
            elif lower_shadow > body * 2 and upper_shadow < body * 0.5 and cl > op:
                patterns_found.append(f"  {date_str}: **해머 (Hammer)** — 하락 후 반등 신호 (양봉)")

            # 슈팅스타 (Shooting Star): 긴 윗꼬리 + 짧은 몸통 (상승 추세 끝에서 반전)
            elif upper_shadow > body * 2 and lower_shadow < body * 0.5 and cl < op:
                patterns_found.append(f"  {date_str}: **슈팅스타 (Shooting Star)** — 상승 후 하락 전환 신호")

            # 마루보즈 (Marubozu): 꼬리 없는 긴 몸통
            elif body / total_range > 0.9:
                mtype = "양봉" if cl > op else "음봉"
                patterns_found.append(f"  {date_str}: **마루보즈 ({mtype})** — 강한 {'매수' if cl > op else '매도'}세")

            # ── 2일 패턴 ──
            if idx >= 1:
                prev_op, prev_cl = o.iloc[idx - 1], c.iloc[idx - 1]
                prev_body = abs(prev_cl - prev_op)

                # 불리시 인걸핑 (Bullish Engulfing)
                if prev_cl < prev_op and cl > op and cl > prev_op and op < prev_cl and body > prev_body:
                    patterns_found.append(f"  {date_str}: **불리시 인걸핑** — 강한 상승 반전 (전일 음봉을 완전히 감쌈)")

                # 베어리시 인걸핑 (Bearish Engulfing)
                elif prev_cl > prev_op and cl < op and cl < prev_op and op > prev_cl and body > prev_body:
                    patterns_found.append(f"  {date_str}: **베어리시 인걸핑** — 강한 하락 반전 (전일 양봉을 완전히 감쌈)")

        if patterns_found:
            lines.append("### 발견된 패턴")
            lines.extend(patterns_found)
        else:
            lines.append("### 발견된 패턴")
            lines.append("  최근 3일간 뚜렷한 캔들 패턴이 발견되지 않았습니다.")

        # 최근 5일 캔들 요약
        lines.append("\n### 최근 5일 캔들 요약")
        for i in range(-5, 0):
            idx = len(df) + i
            if idx < 0:
                continue
            op, hi, lo, cl = o.iloc[idx], h.iloc[idx], l.iloc[idx], c.iloc[idx]
            change = (cl - op) / op * 100
            body_type = "양봉" if cl > op else "음봉" if cl < op else "보합"
            date_str = df.index[idx].strftime("%m/%d") if hasattr(df.index[idx], 'strftime') else str(idx)
            lines.append(f"  {date_str}: {body_type} {self._arrow(change)} {self._fmt(abs(change))}% | 시:{op:,.0f} 고:{hi:,.0f} 저:{lo:,.0f} 종:{cl:,.0f}")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 캔들 차트 분석 전문가입니다 (Steve Nison 방법론).\n"
                "캔들 패턴 데이터를 종합하여:\n"
                "1. 발견된 패턴의 신뢰도 (상/중/하)\n"
                "2. 해당 패턴의 역사적 적중률\n"
                "3. 현재 추세 맥락에서의 의미\n"
                "4. 향후 1~5일 예상 움직임\n"
                "구체적 수치를 포함하여 한국어로 간결하게 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 캔들 패턴 종합 분석\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  6. 지지/저항선 (Support & Resistance)
    # ═══════════════════════════════════════════

    async def _support_resistance(self, kwargs: dict) -> str:
        ticker, name, result = await self._load_ohlcv(kwargs)
        if ticker is None:
            return result
        df = result

        close = df["종가"]
        high = df["고가"]
        low = df["저가"]
        current = close.iloc[-1]

        lines = [f"## {name} ({ticker}) 지지선/저항선\n"]
        lines.append(f"현재가: **{current:,.0f}원**\n")

        # ── 피봇 포인트 (Pivot Point) ──
        prev_h = high.iloc[-2]
        prev_l = low.iloc[-2]
        prev_c = close.iloc[-2]
        pivot = (prev_h + prev_l + prev_c) / 3

        r1 = 2 * pivot - prev_l
        r2 = pivot + (prev_h - prev_l)
        r3 = prev_h + 2 * (pivot - prev_l)
        s1 = 2 * pivot - prev_h
        s2 = pivot - (prev_h - prev_l)
        s3 = prev_l - 2 * (prev_h - pivot)

        lines.append("### 피봇 포인트 (전일 기준)")
        lines.append(f"  R3 (저항3): {r3:,.0f}원")
        lines.append(f"  R2 (저항2): {r2:,.0f}원")
        lines.append(f"  R1 (저항1): {r1:,.0f}원")
        lines.append(f"  **피봇:      {pivot:,.0f}원**")
        lines.append(f"  S1 (지지1): {s1:,.0f}원")
        lines.append(f"  S2 (지지2): {s2:,.0f}원")
        lines.append(f"  S3 (지지3): {s3:,.0f}원")

        # ── 주요 가격대 (거래량 기반) ──
        lines.append("\n### 주요 가격대 (최근 60일)")

        # 최근 60일 고가/저가
        recent = df.tail(60)
        high_60 = recent["고가"].max()
        low_60 = recent["저가"].min()
        lines.append(f"  60일 최고가: {high_60:,.0f}원 (저항)")
        lines.append(f"  60일 최저가: {low_60:,.0f}원 (지지)")

        # 이동평균선 지지/저항
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1] if len(df) >= 60 else None
        ma120 = close.rolling(120).mean().iloc[-1] if len(df) >= 120 else None

        lines.append("\n### 이동평균선 지지/저항")
        lines.append(f"  20일선: {ma20:,.0f}원 {'(지지)' if current > ma20 else '(저항)'}")
        if ma60:
            lines.append(f"  60일선: {ma60:,.0f}원 {'(지지)' if current > ma60 else '(저항)'}")
        if ma120:
            lines.append(f"  120일선: {ma120:,.0f}원 {'(지지)' if current > ma120 else '(저항)'}")

        # ── 피보나치 되돌림 ──
        swing_high = recent["고가"].max()
        swing_low = recent["저가"].min()
        diff = swing_high - swing_low

        lines.append("\n### 피보나치 되돌림 (60일 고저 기준)")
        fib_levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        fib_names = ["0%", "23.6%", "38.2%", "50%", "61.8%", "78.6%", "100%"]
        for level, lname in zip(fib_levels, fib_names):
            price = swing_high - diff * level
            marker = " ◀ 현재가 근처" if abs(price - current) / current < 0.01 else ""
            lines.append(f"  {lname}: {price:,.0f}원{marker}")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 금융공학 교수입니다. 지지선/저항선 데이터를 종합하여:\n"
                "1. 현재가 위치 분석 (어떤 지지/저항 사이에 있는지)\n"
                "2. 가장 중요한 지지선 2개, 저항선 2개 선택\n"
                "3. 돌파/이탈 시 예상 목표가\n"
                "4. 매매 전략 제안 (지지선 매수, 저항선 매도 등)\n"
                "구체적 수치를 포함하여 한국어로 간결하게 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 지지/저항 종합 분석\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  7. 매매 신호 종합 (Signal Summary)
    # ═══════════════════════════════════════════

    async def _signal_summary(self, kwargs: dict) -> str:
        ta = _import_pandas_ta()
        if ta is None:
            return self._install_msg("pandas-ta")

        ticker, name, result = await self._load_ohlcv(kwargs)
        if ticker is None:
            return result
        df = result

        close = df["종가"]
        high = df["고가"]
        low = df["저가"]
        volume = df["거래량"]
        current = close.iloc[-1]

        # ── 각 지표별 매수/매도 점수 계산 ──
        signals = {}  # {지표명: (점수, 해석)}  점수: -2 ~ +2

        # 1) MA 크로스
        ma5 = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        if current > ma5 > ma20:
            signals["이동평균"] = (2, "정배열 상승")
        elif current > ma20:
            signals["이동평균"] = (1, "20일선 위")
        elif current < ma5 < ma20:
            signals["이동평균"] = (-2, "역배열 하락")
        else:
            signals["이동평균"] = (-1, "20일선 아래")

        # 2) RSI
        rsi_series = ta.rsi(close, length=14)
        if rsi_series is not None and not rsi_series.empty:
            rsi = rsi_series.iloc[-1]
            if rsi > 70:
                signals["RSI"] = (-1, f"과매수 {self._fmt(rsi)}")
            elif rsi < 30:
                signals["RSI"] = (1, f"과매도 {self._fmt(rsi)}")
            elif rsi > 50:
                signals["RSI"] = (1, f"매수세 우위 {self._fmt(rsi)}")
            else:
                signals["RSI"] = (-1, f"매도세 우위 {self._fmt(rsi)}")

        # 3) MACD
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            cols = macd_df.columns
            macd_val = macd_df[cols[0]].iloc[-1]
            macd_sig = macd_df[cols[1]].iloc[-1]
            macd_hist = macd_df[cols[2]].iloc[-1]
            if macd_val > macd_sig and macd_hist > 0:
                signals["MACD"] = (2, "골든크로스 + 히스토그램 양")
            elif macd_val > macd_sig:
                signals["MACD"] = (1, "골든크로스")
            elif macd_val < macd_sig and macd_hist < 0:
                signals["MACD"] = (-2, "데드크로스 + 히스토그램 음")
            else:
                signals["MACD"] = (-1, "데드크로스")

        # 4) 볼린저밴드
        bb_df = ta.bbands(close, length=20, std=2)
        if bb_df is not None and not bb_df.empty:
            cols = bb_df.columns
            bb_lower = bb_df[cols[0]].iloc[-1]
            bb_upper = bb_df[cols[2]].iloc[-1]
            if current > bb_upper:
                signals["볼린저"] = (-1, "상단 돌파 (과매수)")
            elif current < bb_lower:
                signals["볼린저"] = (1, "하단 이탈 (과매도)")
            else:
                pctb = (current - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5
                signals["볼린저"] = (1 if pctb > 0.5 else -1, f"%B={self._fmt(pctb)}")

        # 5) Stochastic
        stoch_df = ta.stoch(high, low, close, k=14, d=3, smooth_k=3)
        if stoch_df is not None and not stoch_df.empty:
            k_val = stoch_df.iloc[-1, 0]
            d_val = stoch_df.iloc[-1, 1]
            if k_val > 80:
                signals["스토캐스틱"] = (-1, f"과매수 %K={self._fmt(k_val)}")
            elif k_val < 20:
                signals["스토캐스틱"] = (1, f"과매도 %K={self._fmt(k_val)}")
            elif k_val > d_val:
                signals["스토캐스틱"] = (1, f"매수 교차 %K={self._fmt(k_val)}")
            else:
                signals["스토캐스틱"] = (-1, f"매도 교차 %K={self._fmt(k_val)}")

        # 6) OBV
        obv_series = ta.obv(close, volume)
        if obv_series is not None and not obv_series.empty:
            obv = obv_series.iloc[-1]
            obv_ma = obv_series.rolling(20).mean().iloc[-1]
            signals["OBV"] = (1 if obv > obv_ma else -1, "매수세" if obv > obv_ma else "매도세")

        # 7) ADX
        adx_df = ta.adx(high, low, close, length=14)
        if adx_df is not None and not adx_df.empty:
            adx_val = adx_df.iloc[-1, 0]
            di_plus = adx_df.iloc[-1, 1]
            di_minus = adx_df.iloc[-1, 2]
            if adx_val > 25 and di_plus > di_minus:
                signals["ADX"] = (2, f"강한 상승 추세 ADX={self._fmt(adx_val)}")
            elif adx_val > 25 and di_plus < di_minus:
                signals["ADX"] = (-2, f"강한 하락 추세 ADX={self._fmt(adx_val)}")
            else:
                signals["ADX"] = (0, f"약한 추세 ADX={self._fmt(adx_val)}")

        # 8) 거래량
        vol_ma20 = volume.rolling(20).mean().iloc[-1]
        vol_ratio = volume.iloc[-1] / vol_ma20 if vol_ma20 > 0 else 1
        change = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]
        if vol_ratio > 1.5 and change > 0:
            signals["거래량"] = (2, f"상승 + 거래량 증가 {self._fmt(vol_ratio)}배")
        elif vol_ratio > 1.5 and change < 0:
            signals["거래량"] = (-2, f"하락 + 거래량 증가 {self._fmt(vol_ratio)}배")
        elif vol_ratio < 0.5:
            signals["거래량"] = (0, f"거래 침체 {self._fmt(vol_ratio)}배")
        else:
            signals["거래량"] = (0, f"보통 {self._fmt(vol_ratio)}배")

        # ── 종합 스코어 계산 ──
        total_score = sum(s[0] for s in signals.values())
        max_possible = len(signals) * 2  # 각 지표 최대 +2
        min_possible = -max_possible
        # 0~100 스케일로 변환
        normalized = (total_score - min_possible) / (max_possible - min_possible) * 100 if max_possible != min_possible else 50

        if normalized >= 70:
            verdict = "강한 매수"
            emoji = "🟢🟢🟢"
        elif normalized >= 55:
            verdict = "매수"
            emoji = "🟢🟢"
        elif normalized >= 45:
            verdict = "관망"
            emoji = "🟡"
        elif normalized >= 30:
            verdict = "매도"
            emoji = "🔴🔴"
        else:
            verdict = "강한 매도"
            emoji = "🔴🔴🔴"

        lines = [f"## {name} ({ticker}) 매매 신호 종합\n"]
        lines.append(f"현재가: **{current:,.0f}원**\n")
        lines.append(f"### 종합 판단: {emoji} **{verdict}** (스코어: {normalized:.0f}/100)\n")

        # 지표별 상세
        lines.append("### 지표별 판단")
        lines.append("| 지표 | 신호 | 점수 | 근거 |")
        lines.append("|------|------|------|------|")
        for ind_name, (score, reason) in signals.items():
            signal_text = "매수" if score > 0 else "매도" if score < 0 else "중립"
            bar = "+" * abs(score) if score > 0 else "-" * abs(score) if score < 0 else "="
            lines.append(f"| {ind_name} | {signal_text} | {bar} | {reason} |")

        lines.append(f"\n  매수 지표: {sum(1 for s in signals.values() if s[0] > 0)}개")
        lines.append(f"  매도 지표: {sum(1 for s in signals.values() if s[0] < 0)}개")
        lines.append(f"  중립 지표: {sum(1 for s in signals.values() if s[0] == 0)}개")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 금융공학 교수이자 CFA 자격증 보유자입니다.\n"
                "모든 기술적 지표를 종합하여:\n"
                "1. 최종 매매 판단 (매수/관망/매도)과 확신도 (%)\n"
                "2. 가장 신뢰할 수 있는 지표 3개와 그 이유\n"
                "3. 주의해야 할 리스크 요인\n"
                "4. 구체적 매매 전략 (진입가, 손절가, 목표가)\n"
                "5. 추천 보유 기간 (단타/스윙/중장기)\n"
                "구체적 수치를 포함하여 한국어로 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 종합 매매 판단\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  8. 전체 분석 (Full — 모든 지표)
    # ═══════════════════════════════════════════

    async def _full_analysis(self, kwargs: dict) -> str:
        """모든 분석을 순차적으로 실행하고 하나의 리포트로 합칩니다."""
        ticker, name, result = await self._load_ohlcv(kwargs)
        if ticker is None:
            return result

        # 각 분석을 병렬 실행
        results = await asyncio.gather(
            self._trend_analysis(kwargs),
            self._momentum_analysis(kwargs),
            self._volatility_analysis(kwargs),
            self._volume_analysis(kwargs),
            self._pattern_analysis(kwargs),
            self._support_resistance(kwargs),
            self._signal_summary(kwargs),
            return_exceptions=True,
        )

        sections = [
            "# 종합 기술적 분석 리포트",
            f"**{name} ({ticker})** | 분석일: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
            "---",
        ]

        labels = ["추세 분석", "모멘텀 분석", "변동성 분석", "거래량 분석",
                   "캔들 패턴", "지지/저항선", "매매 신호 종합"]

        for label, res in zip(labels, results):
            if isinstance(res, Exception):
                sections.append(f"\n## {label}\n\n분석 실패: {res}")
            else:
                sections.append(f"\n{res}")
            sections.append("\n---")

        return "\n".join(sections)
