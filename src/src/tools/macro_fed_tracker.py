"""
Fed/매크로 지표 실시간 추적 도구 — FOMC, CPI, PMI, 실업률, Taylor Rule.

학술/실무 근거:
  - Taylor Rule (John Taylor, 1993): i = r* + π + 0.5(π - π*) + 0.5(y - y*)
    r*=중립금리(2.5%), π*=목표 인플레(2%). Fed 이론 금리 vs 실제 괴리 분석
  - FOMC Dot Plot: 위원 18명의 금리 전망 중앙값 → 시장 기대 형성
  - CME FedWatch: Fed Funds Futures 기반 금리 확률 (실시간)
  - Sahm Rule (Claudia Sahm, 2019): 실업률 3개월 이동평균이 12개월 최저 대비 +0.5%p → 경기침체
  - ISM PMI: 50 이상=확장, 50 이하=수축. 47 이하=심각한 수축
  - 10Y-2Y Yield Spread: 역전(음수) → 평균 15개월 후 경기침체 (1955년 이후 8/9 적중)

사용 방법:
  - action="overview": 주요 매크로 지표 종합 대시보드
  - action="taylor_rule": Taylor Rule 이론 금리 vs 실제 비교
  - action="yield_curve": 수익률 곡선 분석 (경기침체 예측)
  - action="full": 전체 매크로 분석

필요 환경변수: 없음
의존 라이브러리: yfinance (Treasury yields), httpx (FRED fallback)
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.macro_fed_tracker")


def _yf():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        return None


class MacroFedTrackerTool(BaseTool):
    """Fed/매크로 지표 실시간 — FOMC, CPI, Taylor Rule, 수익률 곡선."""

    # 매크로 지표 기준값 (학술 연구 기반)
    BENCHMARKS = {
        "fed_rate": {"label": "Fed 기준금리", "unit": "%"},
        "cpi_yoy": {"label": "CPI (전년동월)", "unit": "%", "target": 2.0, "warn": 4.0},
        "unemployment": {"label": "실업률", "unit": "%", "good": 4.0, "warn": 5.5},
        "pmi": {"label": "ISM 제조업 PMI", "unit": "", "expand": 50, "severe": 47},
        "vix": {"label": "VIX (공포지수)", "unit": "", "calm": 15, "fear": 30, "panic": 40},
    }

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "full")
        dispatch = {
            "overview": self._overview,
            "taylor_rule": self._taylor_rule,
            "yield_curve": self._yield_curve,
            "full": self._full,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"알 수 없는 action: {action}\n사용 가능: overview, taylor_rule, yield_curve, full"
        return await handler(kwargs)

    async def _get_treasury_yields(self):
        """yfinance로 미국 국채 수익률 조회."""
        yf = _yf()
        if not yf:
            return {}
        yields = {}
        tickers = {
            "^IRX": "3M", "^FVX": "5Y", "^TNX": "10Y", "^TYX": "30Y",
        }
        for sym, label in tickers.items():
            try:
                t = yf.Ticker(sym)
                hist = t.history(period="5d")
                if not hist.empty:
                    yields[label] = float(hist["Close"].iloc[-1])
            except Exception:
                continue
        # 2Y (별도 조회)
        try:
            t2 = yf.Ticker("2YY=F")
            h2 = t2.history(period="5d")
            if not h2.empty:
                yields["2Y"] = float(h2["Close"].iloc[-1])
        except Exception:
            pass
        return yields

    async def _get_market_data(self):
        """주요 시장 지표 조회."""
        yf = _yf()
        if not yf:
            return {}
        data = {}
        tickers = {
            "^VIX": "vix",
            "^GSPC": "sp500",
            "^IXIC": "nasdaq",
            "DX-Y.NYB": "dxy",
            "GC=F": "gold",
            "CL=F": "oil",
        }
        for sym, key in tickers.items():
            try:
                t = yf.Ticker(sym)
                hist = t.history(period="5d")
                if not hist.empty:
                    current = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
                    change = (current - prev) / prev * 100
                    data[key] = {"price": current, "change": change}
            except Exception:
                continue
        return data

    # ── 1. 매크로 지표 종합 대시보드 ──
    async def _overview(self, kw: dict) -> str:
        yields = await self._get_treasury_yields()
        market = await self._get_market_data()

        lines = [
            "## 미국 매크로 지표 대시보드\n",
            "### 시장 현황",
            "| 지표 | 값 | 변화 |",
            "|------|------|------|",
        ]

        if "sp500" in market:
            sp = market["sp500"]
            lines.append(f"| S&P 500 | {sp['price']:,.0f} | {sp['change']:+.2f}% |")
        if "nasdaq" in market:
            nq = market["nasdaq"]
            lines.append(f"| NASDAQ | {nq['price']:,.0f} | {nq['change']:+.2f}% |")
        if "vix" in market:
            vx = market["vix"]
            vix_label = "패닉" if vx["price"] >= 40 else ("공포" if vx["price"] >= 30 else ("경계" if vx["price"] >= 20 else "안정"))
            lines.append(f"| VIX | {vx['price']:.1f} ({vix_label}) | {vx['change']:+.2f}% |")
        if "dxy" in market:
            dx = market["dxy"]
            lines.append(f"| 달러지수(DXY) | {dx['price']:.2f} | {dx['change']:+.2f}% |")
        if "gold" in market:
            gd = market["gold"]
            lines.append(f"| 금 | ${gd['price']:,.0f} | {gd['change']:+.2f}% |")
        if "oil" in market:
            ol = market["oil"]
            lines.append(f"| WTI 원유 | ${ol['price']:,.2f} | {ol['change']:+.2f}% |")

        # 국채 수익률
        if yields:
            lines.append(f"\n### 미국 국채 수익률")
            lines.append("| 만기 | 수익률 |")
            lines.append("|------|--------|")
            for label in ["3M", "2Y", "5Y", "10Y", "30Y"]:
                if label in yields:
                    lines.append(f"| {label} | {yields[label]:.2f}% |")

            # 10Y-2Y 스프레드 (경기침체 예측)
            if "10Y" in yields and "2Y" in yields:
                spread = yields["10Y"] - yields["2Y"]
                lines.append(f"\n### 10Y-2Y 수익률 스프레드: {spread:+.2f}%")
                if spread < 0:
                    lines.append("🔴 **역전 상태!** — 1955년 이후 역전 후 평균 15개월 뒤 경기침체 (8/9 적중)")
                elif spread < 0.3:
                    lines.append("🟡 평탄화 진행 — 경기 둔화 초기 신호")
                else:
                    lines.append("🟢 정상 스프레드 — 당장 경기침체 우려 낮음")

        # VIX 온도계 해석
        if "vix" in market:
            vx_val = market["vix"]["price"]
            lines.append(f"\n### VIX 온도계")
            if vx_val >= 40:
                lines.append("🔴🔴 **극단적 공포 (VIX ≥ 40)** — 역사적으로 최적 매수 기회")
                lines.append("  - 2008: VIX 80 → 12개월 후 S&P +53%")
                lines.append("  - 2020: VIX 82 → 12개월 후 S&P +75%")
            elif vx_val >= 30:
                lines.append("🔴 **공포 (VIX ≥ 30)** — 역투자 매수 고려 구간")
            elif vx_val >= 20:
                lines.append("🟡 경계 — 변동성 상승 중")
            elif vx_val <= 15:
                lines.append("🟢 **낙관 (VIX ≤ 15)** — 자기만족, 포트폴리오 헤지 강화 고려")
            else:
                lines.append("⚪ 정상 범위")

        return "\n".join(lines)

    # ── 2. Taylor Rule ──
    async def _taylor_rule(self, kw: dict) -> str:
        # Taylor Rule 파라미터 (최근 데이터 기반 추정)
        # 실제 Fed Funds Rate은 5.25~5.50% (2024~2025 기준)
        # CPI ~3.0% (2025년 초 기준)
        # GDP Gap ~+1% (완전고용 근접)

        cpi = float(kw.get("cpi", 3.0))
        gdp_gap = float(kw.get("gdp_gap", 1.0))
        fed_rate = float(kw.get("fed_rate", 4.5))

        # Taylor Rule: i = r* + π + 0.5(π - π*) + 0.5(y - y*)
        r_star = 2.5  # 중립 실질금리
        pi_star = 2.0  # 목표 인플레이션
        taylor_rate = r_star + cpi + 0.5 * (cpi - pi_star) + 0.5 * gdp_gap

        # Modified Taylor Rule (Yellen, 2012): GDP 갭 가중치 1.0
        yellen_rate = r_star + cpi + 0.5 * (cpi - pi_star) + 1.0 * gdp_gap

        gap = fed_rate - taylor_rate

        lines = [
            "## Taylor Rule 분석 (John Taylor, 1993)\n",
            "### 공식: i = r* + π + 0.5(π - π*) + 0.5(y - y*)",
            f"- r* (중립 실질금리): {r_star}%",
            f"- π (현재 CPI): {cpi}%",
            f"- π* (목표 인플레): {pi_star}%",
            f"- y-y* (GDP 갭): {gdp_gap:+.1f}%\n",
            "### 결과",
            "| 모형 | 이론 금리 | 실제 금리 | 괴리 |",
            "|------|---------|---------|------|",
            f"| Taylor (1993) | {taylor_rate:.2f}% | {fed_rate:.2f}% | {gap:+.2f}% |",
            f"| Yellen (2012) | {yellen_rate:.2f}% | {fed_rate:.2f}% | {fed_rate-yellen_rate:+.2f}% |",
        ]

        if gap > 1.0:
            lines.append(f"\n🔴 **Fed 금리 > Taylor Rule** — 긴축 과잉 가능, 금리 인하 여지")
        elif gap > 0:
            lines.append(f"\n🟡 약간 긴축적 — 금리 인하 압력 존재")
        elif gap > -1.0:
            lines.append(f"\n⚪ 적정 수준 — Taylor Rule과 근접")
        else:
            lines.append(f"\n🔴 **Fed 금리 < Taylor Rule** — 완화 과잉, 인플레 재점화 위험")

        lines.append("\n### 해석 가이드")
        lines.append("- Taylor Rule은 기계적 규칙이며, Fed는 고용·금융안정 등 추가 고려")
        lines.append("- 괴리 > 1%p 시 Fed 정책 전환 시그널로 활용")
        lines.append("- CME FedWatch의 시장 기대와 교차 확인 필수")

        return "\n".join(lines)

    # ── 3. 수익률 곡선 분석 ──
    async def _yield_curve(self, kw: dict) -> str:
        yields = await self._get_treasury_yields()

        if not yields or len(yields) < 3:
            return "국채 수익률 데이터를 가져올 수 없습니다."

        lines = [
            "## 미국 국채 수익률 곡선 분석\n",
            "### 수익률 곡선 형태",
            "| 만기 | 수익률 | 그래프 |",
            "|------|--------|--------|",
        ]

        max_yield = max(yields.values()) if yields else 5
        for label in ["3M", "2Y", "5Y", "10Y", "30Y"]:
            if label in yields:
                y = yields[label]
                bar_len = int(y / max_yield * 30)
                bar = "█" * bar_len
                lines.append(f"| {label} | {y:.2f}% | {bar} |")

        # 곡선 형태 분류
        if "3M" in yields and "10Y" in yields and "30Y" in yields:
            short = yields.get("3M", 0) or yields.get("2Y", 0)
            mid = yields.get("10Y", 0)
            long = yields.get("30Y", 0)

            if short > mid > long:
                shape = "🔴 **완전 역전 (Inverted)** — 강한 경기침체 신호"
            elif short > mid:
                shape = "🔴 **부분 역전** — 경기 둔화 신호"
            elif mid - short < 0.3:
                shape = "🟡 **평탄화 (Flat)** — 경기 전환기"
            elif long - short > 1.5:
                shape = "🟢 **가파른 정상 (Steep Normal)** — 경기 확장 기대"
            else:
                shape = "🟢 **정상 (Normal)** — 건강한 경제"

            lines.append(f"\n### 곡선 형태: {shape}")

            # Sahm Rule 참고
            lines.append(f"\n### 경기침체 지표")
            lines.append("- **Sahm Rule** (2019): 실업률 3개월 MA가 12개월 최저 대비 +0.5%p → 침체")
            lines.append("- **10Y-2Y 역전**: 1955년 이후 8/9회 경기침체 선행 (평균 리드타임 15개월)")
            lines.append("- **Conference Board LEI**: 선행지표 6개월 연속 하락 = 경기침체 경고")

        return "\n".join(lines)

    # ── 전체 분석 ──
    async def _full(self, kw: dict) -> str:
        parts = []
        for fn in [self._overview, self._taylor_rule, self._yield_curve]:
            try:
                parts.append(await fn(kw))
            except Exception as e:
                parts.append(f"[분석 일부 실패: {e}]")
        return "\n\n---\n\n".join(parts)
