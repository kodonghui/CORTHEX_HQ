"""
미국주식 기술적 분석 전용 도구 — 다중시간프레임, Ichimoku, 엘리엇 파동.

학술/실무 근거:
  - Dow Theory (Charles Dow, 1900): 주추세/중기추세/단기변동 3단계
  - Ichimoku Kinko Hyo (一目均衡表, Goichi Hosoda, 1969): 구름(Kumo) 기반 추세/지지/저항
  - Bollinger Bands (John Bollinger, 2001): 20일 SMA ± 2σ, Squeeze = 변동성 수축 → 폭발 예고
  - Elliott Wave (R.N. Elliott, 1938): 충격 5파 + 조정 3파, 피보나치 비율
  - ATR (Wilder, 1978): Average True Range — 변동성 측정, 포지션 사이징
  - 다중 지표 합의: RSI+MACD+볼린저+MA+거래량 5개 중 3개 이상 일치 시 시그널

사용 방법:
  - action="multi_timeframe": 일/주/월봉 다중 시간프레임 분석
  - action="ichimoku": 일목균형표 분석 (구름/전환선/기준선)
  - action="fibonacci": 피보나치 되돌림 + 엘리엇 파동 참고
  - action="consensus": 다중 지표 합의 분석 (5개 지표 동시)
  - action="full": 전체 기술적 분석

필요 환경변수: 없음
의존 라이브러리: yfinance, numpy, pandas_ta (선택)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.us_technical_analyzer")


def _yf():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        return None


def _np():
    try:
        import numpy as np
        return np
    except ImportError:
        return None


def _pd():
    try:
        import pandas as pd
        return pd
    except ImportError:
        return None


class UsTechnicalAnalyzerTool(BaseTool):
    """미국주식 기술적 분석 전용 — 다중시간프레임, Ichimoku, 엘리엇."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "full")
        if "query" in kwargs and "symbol" not in kwargs:
            kwargs["symbol"] = kwargs["query"]

        dispatch = {
            "multi_timeframe": self._multi_timeframe,
            "ichimoku": self._ichimoku,
            "fibonacci": self._fibonacci,
            "consensus": self._consensus,
            "full": self._full,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"알 수 없는 action: {action}\n사용 가능: multi_timeframe, ichimoku, fibonacci, consensus, full"
        return await handler(kwargs)

    # ── 공통: 기술 지표 계산 헬퍼 ──
    def _calc_rsi(self, prices, period=14):
        np = _np()
        if np is None or len(prices) < period + 1:
            return None
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calc_macd(self, prices, fast=12, slow=26, signal=9):
        if len(prices) < slow + signal:
            return None, None, None
        def ema(data, n):
            k = 2 / (n + 1)
            result = [data[0]]
            for i in range(1, len(data)):
                result.append(data[i] * k + result[-1] * (1 - k))
            return result
        ema_fast = ema(prices, fast)
        ema_slow = ema(prices, slow)
        macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(prices))]
        signal_line = ema(macd_line[slow-1:], signal)
        # 패딩
        signal_padded = [0] * (slow - 1) + signal_line
        histogram = [macd_line[i] - signal_padded[i] for i in range(len(macd_line))]
        return macd_line[-1], signal_padded[-1] if len(signal_padded) > 0 else 0, histogram[-1]

    def _calc_bollinger(self, prices, period=20, std_dev=2):
        np = _np()
        if np is None or len(prices) < period:
            return None, None, None
        sma = sum(prices[-period:]) / period
        std = float(np.std(prices[-period:]))
        return sma - std_dev * std, sma, sma + std_dev * std

    # ── 1. 다중 시간프레임 분석 ──
    async def _multi_timeframe(self, kw: dict) -> str:
        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            name = info.get("longName") or symbol

            lines = [
                f"## {name} ({symbol}) — 다중 시간프레임 분석 (Dow Theory)\n",
                "### Dow Theory 핵심: \"추세는 명확한 반전 신호까지 지속된다\"\n",
            ]

            timeframes = [
                ("일봉 (단기)", "3mo", "1d"),
                ("주봉 (중기)", "1y", "1wk"),
                ("월봉 (장기)", "5y", "1mo"),
            ]

            for tf_name, period, interval in timeframes:
                hist = t.history(period=period, interval=interval)
                if hist.empty:
                    lines.append(f"\n#### {tf_name}: 데이터 없음")
                    continue

                closes = hist["Close"].tolist()
                volumes = hist["Volume"].tolist()
                current = closes[-1]

                # MA
                ma20 = sum(closes[-20:]) / min(20, len(closes)) if len(closes) >= 5 else current
                ma50 = sum(closes[-50:]) / min(50, len(closes)) if len(closes) >= 10 else current
                ma200 = sum(closes[-200:]) / min(200, len(closes)) if len(closes) >= 50 else current

                # RSI
                rsi = self._calc_rsi(closes) or 50

                # MACD
                macd, signal, hist_val = self._calc_macd(closes)

                # 추세 판단
                if current > ma20 > ma50:
                    trend = "🟢 상승 (정배열)"
                elif current < ma20 < ma50:
                    trend = "🔴 하락 (역배열)"
                else:
                    trend = "🟡 횡보/전환"

                # MA 크로스
                ma_cross = ""
                if len(closes) >= 51:
                    prev_ma20 = sum(closes[-21:-1]) / 20
                    prev_ma50 = sum(closes[-51:-1]) / 50
                    if prev_ma20 < prev_ma50 and ma20 > ma50:
                        ma_cross = " ✨ **골든크로스**"
                    elif prev_ma20 > prev_ma50 and ma20 < ma50:
                        ma_cross = " ⚡ **데드크로스**"

                lines.append(f"\n#### {tf_name}")
                lines.append(f"- 추세: {trend}{ma_cross}")
                lines.append(f"- 현재가: ${current:,.2f} | MA20: ${ma20:,.2f} | MA50: ${ma50:,.2f}")
                lines.append(f"- RSI({14}): {rsi:.1f} {'(과매수)' if rsi > 70 else ('(과매도)' if rsi < 30 else '')}")
                if macd is not None:
                    macd_state = "골든크로스" if macd > signal else "데드크로스"
                    lines.append(f"- MACD: {macd:.4f} / Signal: {signal:.4f} → {macd_state}")

            return "\n".join(lines)
        except Exception as e:
            return f"다중 시간프레임 분석 실패: {e}"

    # ── 2. Ichimoku 일목균형표 ──
    async def _ichimoku(self, kw: dict) -> str:
        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            name = info.get("longName") or symbol
            hist = t.history(period="6mo", interval="1d")
            if hist.empty or len(hist) < 52:
                return f"{symbol}: 6개월 이상 데이터 필요 (Ichimoku)"

            highs = hist["High"].tolist()
            lows = hist["Low"].tolist()
            closes = hist["Close"].tolist()
            current = closes[-1]

            # Ichimoku 계산 (Goichi Hosoda 원본 파라미터)
            def midpoint(h, l, n, i):
                seg_h = max(h[max(0,i-n+1):i+1])
                seg_l = min(l[max(0,i-n+1):i+1])
                return (seg_h + seg_l) / 2

            n = len(closes) - 1
            tenkan = midpoint(highs, lows, 9, n)    # 전환선 (9일)
            kijun = midpoint(highs, lows, 26, n)    # 기준선 (26일)
            senkou_a = (tenkan + kijun) / 2          # 선행스팬 A (26일 선행)
            senkou_b = midpoint(highs, lows, 52, n)  # 선행스팬 B (52일 기준, 26일 선행)
            chikou = closes[-26] if len(closes) >= 26 else closes[0]  # 후행스팬

            # 구름(Kumo) 분석
            kumo_top = max(senkou_a, senkou_b)
            kumo_bottom = min(senkou_a, senkou_b)
            kumo_thick = kumo_top - kumo_bottom

            if current > kumo_top:
                position = "🟢 구름 위 (강세)"
            elif current < kumo_bottom:
                position = "🔴 구름 아래 (약세)"
            else:
                position = "🟡 구름 안 (횡보/전환)"

            cloud_color = "양운(Senkou A > B)" if senkou_a > senkou_b else "음운(Senkou B > A)"

            # 3역 호전/역전 (Ichimoku 핵심 매매 시그널)
            signals = []
            if tenkan > kijun:
                signals.append("전환선 > 기준선 (매수)")
            else:
                signals.append("전환선 < 기준선 (매도)")

            if current > kumo_top:
                signals.append("가격 > 구름 (강세 확인)")
            elif current < kumo_bottom:
                signals.append("가격 < 구름 (약세 확인)")

            if chikou > closes[-26] if len(closes) >= 52 else False:
                signals.append("후행스팬 > 26일전 가격 (강세)")

            lines = [
                f"## {name} ({symbol}) — 일목균형표 (Ichimoku Kinko Hyo)\n",
                "### 일목균형표란? (Hosoda, 1969)",
                "\"한 눈에(一目) 균형(均衡)을 본다\" — 추세/지지/저항/타이밍을 동시 파악\n",
                f"### 현재 지표",
                f"| 항목 | 값 | 의미 |",
                f"|------|------|------|",
                f"| 현재가 | ${current:,.2f} | |",
                f"| 전환선 (9일) | ${tenkan:,.2f} | 단기 균형가 |",
                f"| 기준선 (26일) | ${kijun:,.2f} | 중기 균형가/지지 |",
                f"| 선행스팬 A | ${senkou_a:,.2f} | 구름 상단/하단 |",
                f"| 선행스팬 B | ${senkou_b:,.2f} | 구름 상단/하단 |",
                f"| 구름 두께 | ${kumo_thick:,.2f} | {'두꺼움(강한 지지/저항)' if kumo_thick > current*0.03 else '얇음(돌파 쉬움)'} |",
                f"\n### 포지션: {position}",
                f"- 구름 색상: {cloud_color}",
                f"\n### Ichimoku 시그널",
            ]
            for s in signals:
                lines.append(f"- {s}")

            buy_signals = sum(1 for s in signals if "매수" in s or "강세" in s)
            sell_signals = sum(1 for s in signals if "매도" in s or "약세" in s)

            if buy_signals >= 2:
                lines.append(f"\n**종합: 🟢 매수 우위 ({buy_signals}/{len(signals)} 시그널)**")
            elif sell_signals >= 2:
                lines.append(f"\n**종합: 🔴 매도 우위 ({sell_signals}/{len(signals)} 시그널)**")
            else:
                lines.append(f"\n**종합: 🟡 중립/혼재**")

            return "\n".join(lines)
        except Exception as e:
            return f"Ichimoku 분석 실패: {e}"

    # ── 3. 피보나치 되돌림 + 엘리엇 참고 ──
    async def _fibonacci(self, kw: dict) -> str:
        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            name = info.get("longName") or symbol
            hist = t.history(period="1y", interval="1d")
            if hist.empty:
                return f"{symbol} 데이터 없음"

            closes = hist["Close"].tolist()
            highs = hist["High"].tolist()
            lows = hist["Low"].tolist()
            current = closes[-1]

            # 52주 고저
            high_52 = max(highs)
            low_52 = min(lows)
            diff = high_52 - low_52

            # 피보나치 되돌림 레벨
            fib_levels = {
                "0% (고점)": high_52,
                "23.6%": high_52 - diff * 0.236,
                "38.2%": high_52 - diff * 0.382,
                "50.0%": high_52 - diff * 0.500,
                "61.8% (황금비)": high_52 - diff * 0.618,
                "78.6%": high_52 - diff * 0.786,
                "100% (저점)": low_52,
            }

            # 현재 위치 확인
            pct_from_high = (high_52 - current) / diff * 100 if diff > 0 else 0

            lines = [
                f"## {name} ({symbol}) — 피보나치 되돌림 + 엘리엇 파동\n",
                "### 피보나치 되돌림 (52주 기준)",
                f"52주 고점: ${high_52:,.2f} | 52주 저점: ${low_52:,.2f}\n",
                "| 레벨 | 가격 | 현재가 위치 |",
                "|------|------|-----------|",
            ]

            for level_name, price in fib_levels.items():
                marker = " ◀ **현재**" if abs(current - price) / current < 0.02 else ""
                lines.append(f"| {level_name} | ${price:,.2f} | {marker} |")

            lines.append(f"\n현재가 ${current:,.2f} — 고점 대비 {pct_from_high:.1f}% 하락 위치")

            # 지지/저항 분석
            nearest_support = max((p for p in fib_levels.values() if p < current), default=low_52)
            nearest_resist = min((p for p in fib_levels.values() if p > current), default=high_52)
            lines.append(f"\n### 핵심 지지/저항")
            lines.append(f"- 가장 가까운 지지: ${nearest_support:,.2f}")
            lines.append(f"- 가장 가까운 저항: ${nearest_resist:,.2f}")

            # 엘리엇 파동 참고
            lines.append(f"\n### 엘리엇 파동 참고 (단독 판단 금지!)")
            lines.append("- Wave 이론: 충격 5파(1-2-3-4-5) + 조정 3파(A-B-C)")
            lines.append("- Wave 3 = Wave 1의 1.618배 (피보나치 확장)")
            lines.append("- Wave 2 되돌림: 보통 Wave 1의 50~61.8%")
            lines.append("- Wave 4 되돌림: 보통 Wave 3의 23.6~38.2%")
            lines.append("- ⚠️ 엘리엇 파동은 사후 해석은 정확하나 실시간 파동 카운팅은 주관적")
            lines.append("  — 반드시 다른 지표(RSI, MACD, 볼린저)와 교차검증 필수")

            return "\n".join(lines)
        except Exception as e:
            return f"피보나치 분석 실패: {e}"

    # ── 4. 다중 지표 합의 분석 ──
    async def _consensus(self, kw: dict) -> str:
        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            name = info.get("longName") or symbol
            hist = t.history(period="6mo", interval="1d")
            if hist.empty or len(hist) < 50:
                return f"{symbol}: 최소 50거래일 데이터 필요"

            closes = hist["Close"].tolist()
            volumes = hist["Volume"].tolist()
            current = closes[-1]

            buy_signals = 0
            sell_signals = 0
            details = []

            # 1. RSI
            rsi = self._calc_rsi(closes)
            if rsi:
                if rsi < 30:
                    buy_signals += 1
                    details.append(f"RSI {rsi:.1f}: 🟢 과매도 → 매수")
                elif rsi > 70:
                    sell_signals += 1
                    details.append(f"RSI {rsi:.1f}: 🔴 과매수 → 매도")
                elif rsi < 45:
                    buy_signals += 0.5
                    details.append(f"RSI {rsi:.1f}: 🟢 매수 쪽 (약)")
                elif rsi > 55:
                    sell_signals += 0.5
                    details.append(f"RSI {rsi:.1f}: 🔴 매도 쪽 (약)")
                else:
                    details.append(f"RSI {rsi:.1f}: ⚪ 중립")

            # 2. MACD
            macd, signal, hist_val = self._calc_macd(closes)
            if macd is not None:
                if macd > signal:
                    buy_signals += 1
                    details.append(f"MACD: 🟢 골든크로스 (MACD > Signal)")
                else:
                    sell_signals += 1
                    details.append(f"MACD: 🔴 데드크로스 (MACD < Signal)")

            # 3. 볼린저 밴드
            bb_lower, bb_mid, bb_upper = self._calc_bollinger(closes)
            if bb_lower is not None:
                if current <= bb_lower:
                    buy_signals += 1
                    details.append(f"볼린저: 🟢 하단 터치 (과매도)")
                elif current >= bb_upper:
                    sell_signals += 1
                    details.append(f"볼린저: 🔴 상단 터치 (과매수)")
                else:
                    pct_b = (current - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5
                    if pct_b < 0.3:
                        buy_signals += 0.5
                        details.append(f"볼린저: 🟢 하단 근접 (%B={pct_b:.2f})")
                    elif pct_b > 0.7:
                        sell_signals += 0.5
                        details.append(f"볼린저: 🔴 상단 근접 (%B={pct_b:.2f})")
                    else:
                        details.append(f"볼린저: ⚪ 중간 (%B={pct_b:.2f})")

            # 4. 이동평균 (20/50)
            ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else current
            ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else current
            if current > ma20 > ma50:
                buy_signals += 1
                details.append(f"MA: 🟢 정배열 (가격 > MA20 > MA50)")
            elif current < ma20 < ma50:
                sell_signals += 1
                details.append(f"MA: 🔴 역배열 (가격 < MA20 < MA50)")
            else:
                details.append(f"MA: ⚪ 혼재")

            # 5. 거래량
            avg_vol_20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 0
            recent_vol = volumes[-1] if volumes else 0
            vol_ratio = recent_vol / avg_vol_20 if avg_vol_20 > 0 else 1

            price_change = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) >= 2 else 0
            if vol_ratio > 1.5 and price_change > 0:
                buy_signals += 1
                details.append(f"거래량: 🟢 평균 대비 {vol_ratio:.1f}배 + 상승 (매집 가능)")
            elif vol_ratio > 1.5 and price_change < 0:
                sell_signals += 1
                details.append(f"거래량: 🔴 평균 대비 {vol_ratio:.1f}배 + 하락 (매도 압력)")
            else:
                details.append(f"거래량: ⚪ 평균 수준 ({vol_ratio:.1f}배)")

            # ATR 기반 포지션 사이징
            np = _np()
            atr = None
            if np and len(closes) >= 15:
                trs = []
                for i in range(1, min(15, len(closes))):
                    h = hist["High"].tolist()[-(15-i)]
                    l = hist["Low"].tolist()[-(15-i)]
                    pc = closes[-(15-i+1)]
                    tr = max(h - l, abs(h - pc), abs(l - pc))
                    trs.append(tr)
                atr = sum(trs) / len(trs)

            # 종합
            total = buy_signals + sell_signals
            lines = [
                f"## {name} ({symbol}) — 다중 지표 합의 분석\n",
                f"### 현재가: ${current:,.2f}\n",
                "### 5개 지표 점검",
            ]
            for d in details:
                lines.append(f"- {d}")

            lines.append(f"\n### 합의 결과")
            lines.append(f"- 매수 시그널: {buy_signals:.1f}/5")
            lines.append(f"- 매도 시그널: {sell_signals:.1f}/5")

            if buy_signals >= 3:
                strength = "강" if buy_signals >= 4 else "중"
                lines.append(f"\n**🟢 매수 합의 ({buy_signals:.0f}/5) — 강도: {strength}**")
            elif sell_signals >= 3:
                strength = "강" if sell_signals >= 4 else "중"
                lines.append(f"\n**🔴 매도 합의 ({sell_signals:.0f}/5) — 강도: {strength}**")
            else:
                lines.append(f"\n**🟡 합의 부족 — 관망 권장 (최소 3/5 필요)**")

            if atr:
                lines.append(f"\n### ATR 기반 포지션 (Wilder, 1978)")
                lines.append(f"- ATR(14): ${atr:,.2f}")
                lines.append(f"- 진입가: ${current:,.2f}")
                lines.append(f"- 손절(2×ATR): ${current - 2*atr:,.2f}")
                lines.append(f"- 목표(3×ATR): ${current + 3*atr:,.2f}")
                lines.append(f"- 리스크/리워드: 1:1.5")

            return "\n".join(lines)
        except Exception as e:
            return f"합의 분석 실패: {e}"

    # ── 전체 분석 ──
    async def _full(self, kw: dict) -> str:
        parts = []
        for fn in [self._consensus, self._multi_timeframe, self._ichimoku, self._fibonacci]:
            try:
                parts.append(await fn(kw))
            except Exception as e:
                parts.append(f"[분석 일부 실패: {e}]")
        return "\n\n---\n\n".join(parts)
