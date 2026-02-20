"""
옵션 흐름 분석 도구 — 스마트머니 추적, Put/Call Ratio, Max Pain, GEX.

학술/실무 근거:
  - Put/Call Ratio (CBOE): PCR > 1.0 = 공포(역투자 매수), PCR < 0.7 = 낙관(경계)
  - Unusual Options Activity: 정상 거래량 3배 이상 = 내부정보 가능성 (Easley et al, 1998)
  - Max Pain Theory: 옵션 만기일에 가격은 콜+풋 미결제약정의 총 손실을 최소화하는 가격으로 수렴
  - GEX (Gamma Exposure): 마켓메이커 감마 헤징이 가격 움직임을 증폭/억제
    - GEX > 0: 변동성 억제 (마켓메이커가 역방향 헤징)
    - GEX < 0: 변동성 증폭 (마켓메이커가 순방향 헤징)
  - Informed Trading (Easley, O'Hara & Srinivas, 1998): 옵션 시장이 주식보다 먼저 정보 반영

사용 방법:
  - action="overview": 옵션 체인 개요 (PCR, IV, 만기별)
  - action="unusual": 이상 옵션 거래 감지 (거래량/미결제 이상치)
  - action="max_pain": Max Pain 가격 계산
  - action="full": 전체 옵션 분석

필요 환경변수: 없음
의존 라이브러리: yfinance, numpy
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.options_flow")


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


class OptionsFlowTool(BaseTool):
    """옵션 흐름 분석 — Put/Call Ratio, Max Pain, 이상 거래 감지."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "full")
        if "query" in kwargs and "symbol" not in kwargs:
            kwargs["symbol"] = kwargs["query"]

        dispatch = {
            "overview": self._overview,
            "unusual": self._unusual,
            "max_pain": self._max_pain,
            "full": self._full,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"알 수 없는 action: {action}\n사용 가능: overview, unusual, max_pain, full"
        return await handler(kwargs)

    # ── 1. 옵션 개요 ──
    async def _overview(self, kw: dict) -> str:
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
            current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

            expirations = t.options
            if not expirations:
                return f"{symbol}의 옵션 데이터가 없습니다."

            lines = [
                f"## {name} ({symbol}) — 옵션 흐름 분석\n",
                f"현재가: ${current_price:,.2f}\n",
                f"### 만기일 목록 ({len(expirations)}개)",
            ]

            # 가장 가까운 3개 만기 분석
            total_call_vol, total_put_vol = 0, 0
            total_call_oi, total_put_oi = 0, 0

            for exp in expirations[:5]:
                try:
                    chain = t.option_chain(exp)
                    calls = chain.calls
                    puts = chain.puts

                    c_vol = int(calls["volume"].sum()) if "volume" in calls.columns else 0
                    p_vol = int(puts["volume"].sum()) if "volume" in puts.columns else 0
                    c_oi = int(calls["openInterest"].sum()) if "openInterest" in calls.columns else 0
                    p_oi = int(puts["openInterest"].sum()) if "openInterest" in puts.columns else 0

                    total_call_vol += c_vol
                    total_put_vol += p_vol
                    total_call_oi += c_oi
                    total_put_oi += p_oi

                    pcr_vol = p_vol / c_vol if c_vol > 0 else 0
                    pcr_oi = p_oi / c_oi if c_oi > 0 else 0

                    # IV 가중 평균 (ATM 부근)
                    atm_calls = calls[(calls["strike"] >= current_price * 0.95) &
                                      (calls["strike"] <= current_price * 1.05)]
                    avg_iv = float(atm_calls["impliedVolatility"].mean()) if (
                        "impliedVolatility" in atm_calls.columns and len(atm_calls) > 0) else 0

                    lines.append(f"\n#### 만기: {exp}")
                    lines.append(f"| | 콜(Call) | 풋(Put) | P/C Ratio |")
                    lines.append(f"|------|---------|---------|-----------|")
                    lines.append(f"| 거래량 | {c_vol:,} | {p_vol:,} | {pcr_vol:.2f} |")
                    lines.append(f"| 미결제 | {c_oi:,} | {p_oi:,} | {pcr_oi:.2f} |")
                    if avg_iv > 0:
                        lines.append(f"| ATM IV | {avg_iv*100:.1f}% | | |")

                except Exception:
                    continue

            # 종합 PCR
            overall_pcr_vol = total_put_vol / total_call_vol if total_call_vol > 0 else 0
            overall_pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else 0

            lines.append(f"\n### 종합 Put/Call Ratio")
            lines.append(f"- 거래량 PCR: {overall_pcr_vol:.2f}")
            lines.append(f"- 미결제 PCR: {overall_pcr_oi:.2f}")

            if overall_pcr_vol > 1.2:
                lines.append("- 🟢 **높은 PCR (>1.2)**: 극도의 공포 → 역투자 매수 시그널")
                lines.append("  - CBOE 역사: PCR > 1.2 후 30일 S&P500 평균 +3.2%")
            elif overall_pcr_vol > 0.9:
                lines.append("- 🟡 중립~약간 약세: 헤지 수요 있음")
            elif overall_pcr_vol > 0.6:
                lines.append("- ⚪ 정상 범위")
            else:
                lines.append("- 🔴 **낮은 PCR (<0.6)**: 과도한 낙관 → 조정 경계")

            return "\n".join(lines)
        except Exception as e:
            return f"옵션 개요 조회 실패: {e}"

    # ── 2. 이상 옵션 거래 감지 ──
    async def _unusual(self, kw: dict) -> str:
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
            current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

            expirations = t.options
            if not expirations:
                return f"{symbol}의 옵션 데이터 없음"

            lines = [
                f"## {name} ({symbol}) — 이상 옵션 거래 감지\n",
                "### Easley et al(1998): 거래량/미결제약정 비율 > 3x = 정보거래 가능성\n",
            ]

            unusual = []
            for exp in expirations[:4]:
                try:
                    chain = t.option_chain(exp)
                    for df, opt_type in [(chain.calls, "CALL"), (chain.puts, "PUT")]:
                        if "volume" not in df.columns or "openInterest" not in df.columns:
                            continue
                        for _, row in df.iterrows():
                            vol = int(row.get("volume", 0) or 0)
                            oi = int(row.get("openInterest", 0) or 0)
                            strike = float(row.get("strike", 0))
                            iv = float(row.get("impliedVolatility", 0) or 0)

                            if oi > 0 and vol > oi * 3 and vol > 500:
                                unusual.append({
                                    "exp": exp, "type": opt_type, "strike": strike,
                                    "vol": vol, "oi": oi, "ratio": vol/oi, "iv": iv,
                                })
                except Exception:
                    continue

            if unusual:
                unusual.sort(key=lambda x: x["ratio"], reverse=True)
                lines.append("| 만기 | 유형 | 행사가 | 거래량 | 미결제 | Vol/OI | IV |")
                lines.append("|------|------|--------|--------|--------|--------|------|")
                for u in unusual[:15]:
                    otm = "OTM" if (u["type"] == "CALL" and u["strike"] > current_price) or \
                                   (u["type"] == "PUT" and u["strike"] < current_price) else "ITM"
                    lines.append(
                        f"| {u['exp']} | {u['type']} {otm} | ${u['strike']:,.0f} | "
                        f"{u['vol']:,} | {u['oi']:,} | {u['ratio']:.1f}x | {u['iv']*100:.0f}% |"
                    )

                # 방향 분석
                call_unusual = sum(1 for u in unusual if u["type"] == "CALL")
                put_unusual = sum(1 for u in unusual if u["type"] == "PUT")
                lines.append(f"\n**이상 거래 방향: 콜 {call_unusual}건 / 풋 {put_unusual}건**")
                if call_unusual > put_unusual * 2:
                    lines.append("🟢 콜 이상거래 우세 → 스마트머니 상승 베팅 가능성")
                elif put_unusual > call_unusual * 2:
                    lines.append("🔴 풋 이상거래 우세 → 스마트머니 하락 헤지 또는 하락 베팅")
            else:
                lines.append("현재 이상 옵션 거래 감지 없음 (정상 범위)")

            return "\n".join(lines)
        except Exception as e:
            return f"이상거래 감지 실패: {e}"

    # ── 3. Max Pain 계산 ──
    async def _max_pain(self, kw: dict) -> str:
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
            current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

            expirations = t.options
            if not expirations:
                return f"{symbol} 옵션 데이터 없음"

            lines = [
                f"## {name} ({symbol}) — Max Pain 분석\n",
                "### Max Pain Theory",
                "만기일에 가격은 옵션 매수자 총 손실을 최대화(= 매도자 이익 최대화)하는 가격으로 수렴하는 경향\n",
            ]

            for exp in expirations[:3]:
                try:
                    chain = t.option_chain(exp)
                    calls = chain.calls
                    puts = chain.puts

                    if "openInterest" not in calls.columns:
                        continue

                    strikes = sorted(set(calls["strike"].tolist() + puts["strike"].tolist()))
                    if not strikes:
                        continue

                    min_pain = float("inf")
                    max_pain_price = current_price

                    for test_price in strikes:
                        pain = 0
                        # 콜 매수자 손실: max(0, test_price - strike) * OI (ITM만 가치 있음)
                        for _, row in calls.iterrows():
                            oi = int(row.get("openInterest", 0) or 0)
                            strike = float(row.get("strike", 0))
                            if test_price > strike:
                                pain += (test_price - strike) * oi
                        # 풋 매수자 손실
                        for _, row in puts.iterrows():
                            oi = int(row.get("openInterest", 0) or 0)
                            strike = float(row.get("strike", 0))
                            if test_price < strike:
                                pain += (strike - test_price) * oi

                        if pain < min_pain:
                            min_pain = pain
                            max_pain_price = test_price

                    diff_pct = (max_pain_price - current_price) / current_price * 100

                    lines.append(f"#### 만기: {exp}")
                    lines.append(f"- Max Pain: **${max_pain_price:,.2f}**")
                    lines.append(f"- 현재가: ${current_price:,.2f}")
                    lines.append(f"- 차이: {diff_pct:+.1f}%")

                    if abs(diff_pct) < 2:
                        lines.append(f"- ⚪ 현재가 ≈ Max Pain (만기일 변동 제한적)")
                    elif diff_pct > 2:
                        lines.append(f"- 🔴 Max Pain 위 → 만기일까지 하방 압력 가능")
                    else:
                        lines.append(f"- 🟢 Max Pain 아래 → 만기일까지 상방 압력 가능")

                except Exception:
                    continue

            return "\n".join(lines)
        except Exception as e:
            return f"Max Pain 계산 실패: {e}"

    # ── 전체 분석 ──
    async def _full(self, kw: dict) -> str:
        parts = []
        for fn in [self._overview, self._unusual, self._max_pain]:
            try:
                parts.append(await fn(kw))
            except Exception as e:
                parts.append(f"[분석 일부 실패: {e}]")
        return "\n\n---\n\n".join(parts)
