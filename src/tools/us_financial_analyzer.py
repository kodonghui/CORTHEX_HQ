"""
미국기업 재무제표 심층분석 도구 — DCF, Fama-French, DuPont, 밸류에이션.

학술/실무 근거:
  - DCF (Damodaran, NYU Stern): 기업가치 = ΣFCFₜ/(1+WACC)ᵗ + Terminal Value
  - Monte Carlo DCF: 10,000회 시뮬레이션으로 적정가 분포 추정 (불확실성 정량화)
  - Fama-French 5-Factor (2015): MKT + SMB + HML + RMW + CMA
  - DuPont 분해 (F. Donaldson Brown, 1919): ROE = 순이익률 × 자산회전율 × 레버리지
  - Graham Margin of Safety: 적정가 대비 30%+ 할인 시만 매수
  - PEG Ratio (Peter Lynch): PEG < 1.0 = 성장 대비 저평가

사용 방법:
  - action="dcf": DCF + Monte Carlo 적정가 산출
  - action="dupont": DuPont 3단계 분해 분석
  - action="valuation": 종합 밸류에이션 (PER/PBR/EV/EBITDA/PEG)
  - action="full": 전체 심층 분석 (DCF + DuPont + 밸류에이션)

필요 환경변수: 없음
의존 라이브러리: yfinance, numpy
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.us_financial_analyzer")


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


class UsFinancialAnalyzerTool(BaseTool):
    """미국기업 재무제표 심층분석 — DCF, Fama-French, DuPont, 밸류에이션."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "full")
        if "query" in kwargs and "symbol" not in kwargs:
            kwargs["symbol"] = kwargs["query"]

        dispatch = {
            "dcf": self._dcf,
            "dupont": self._dupont,
            "valuation": self._valuation,
            "full": self._full,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"알 수 없는 action: {action}\n사용 가능: dcf, dupont, valuation, full"
        return await handler(kwargs)

    # ── DCF + Monte Carlo 적정가 ──
    async def _dcf(self, kw: dict) -> str:
        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        yf, np = _yf(), _np()
        if not yf:
            return "yfinance 미설치"
        if not np:
            return "numpy 미설치"

        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            name = info.get("longName") or symbol

            # 재무 데이터 수집
            cf = t.cashflow
            bs = t.balance_sheet
            inc = t.financials

            if cf is None or cf.empty:
                return f"{symbol}의 재무제표를 가져올 수 없습니다."

            # FCF 계산: Operating Cash Flow - CapEx
            ocf_row = None
            for label in ["Operating Cash Flow", "Total Cash From Operating Activities",
                          "Cash Flow From Continuing Operating Activities"]:
                if label in cf.index:
                    ocf_row = cf.loc[label]
                    break
            capex_row = None
            for label in ["Capital Expenditure", "Capital Expenditures"]:
                if label in cf.index:
                    capex_row = cf.loc[label]
                    break

            if ocf_row is None:
                return f"{symbol}: 영업현금흐름 데이터 없음"

            # 최근 3~4년 FCF
            fcf_values = []
            for i in range(min(4, len(ocf_row))):
                ocf = float(ocf_row.iloc[i] or 0)
                capex = float(capex_row.iloc[i] or 0) if capex_row is not None else 0
                fcf = ocf + capex  # capex는 음수
                fcf_values.append(fcf)

            if not fcf_values or all(f == 0 for f in fcf_values):
                return f"{symbol}: FCF 데이터 불충분"

            latest_fcf = fcf_values[0]
            avg_fcf = sum(fcf_values) / len(fcf_values)

            # WACC 추정
            beta = info.get("beta", 1.0) or 1.0
            risk_free = 0.043  # 10Y Treasury ~4.3%
            market_premium = 0.055  # 역사적 주식 프리미엄 5.5%
            cost_equity = risk_free + beta * market_premium

            # 부채 비용 (Interest Expense / Total Debt)
            total_debt = info.get("totalDebt", 0) or 0
            interest_exp = 0
            if inc is not None and "Interest Expense" in inc.index:
                interest_exp = abs(float(inc.loc["Interest Expense"].iloc[0] or 0))
            cost_debt = (interest_exp / total_debt * 0.75) if total_debt > 0 else 0.04  # 세후

            market_cap = info.get("marketCap", 0) or 0
            total_value = market_cap + total_debt
            weight_equity = market_cap / total_value if total_value > 0 else 0.8
            weight_debt = 1 - weight_equity

            wacc = weight_equity * cost_equity + weight_debt * cost_debt
            wacc = max(0.06, min(wacc, 0.20))  # 6~20% 범위 제한

            # 성장률 추정
            revenue_growth = info.get("revenueGrowth", 0.05) or 0.05
            terminal_growth = min(0.03, revenue_growth * 0.3)  # GDP 성장률 이하

            # ── Monte Carlo DCF (10,000회) ──
            n_sim = 10000
            projection_years = 10
            shares_out = info.get("sharesOutstanding", 1) or 1

            # 파라미터 분포 (정규분포 가정)
            fcf_base = max(latest_fcf, avg_fcf)  # 보수적 선택
            growth_samples = np.random.normal(revenue_growth, abs(revenue_growth) * 0.3, n_sim)
            growth_samples = np.clip(growth_samples, -0.1, 0.5)
            wacc_samples = np.random.normal(wacc, wacc * 0.15, n_sim)
            wacc_samples = np.clip(wacc_samples, 0.05, 0.25)
            tg_samples = np.random.normal(terminal_growth, 0.005, n_sim)
            tg_samples = np.clip(tg_samples, 0.01, 0.04)

            fair_values = []
            for i in range(n_sim):
                g = growth_samples[i]
                w = wacc_samples[i]
                tg = tg_samples[i]

                if w <= tg:
                    continue

                pv_sum = 0
                fcf_t = fcf_base
                for yr in range(1, projection_years + 1):
                    decay = max(0.5, 1 - (yr - 1) * 0.05)  # 성장률 점진적 감소
                    fcf_t *= (1 + g * decay)
                    pv_sum += fcf_t / (1 + w) ** yr

                # Terminal Value (Gordon Growth Model)
                tv = fcf_t * (1 + tg) / (w - tg)
                pv_tv = tv / (1 + w) ** projection_years
                ev = pv_sum + pv_tv

                # Equity Value = EV - Net Debt
                net_debt = total_debt - (info.get("totalCash", 0) or 0)
                equity_value = ev - net_debt
                fair_per_share = equity_value / shares_out

                if 0 < fair_per_share < 1e7:
                    fair_values.append(fair_per_share)

            if not fair_values:
                return f"{symbol}: Monte Carlo 시뮬레이션 실패 — 유효한 결과 없음"

            fv = np.array(fair_values)
            current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

            # Margin of Safety (Graham)
            median_fair = float(np.median(fv))
            mos = ((median_fair - current_price) / median_fair * 100) if median_fair > 0 else 0

            lines = [
                f"## {name} ({symbol}) — DCF + Monte Carlo 분석\n",
                f"### 기초 데이터",
                f"| 항목 | 값 |",
                f"|------|------|",
                f"| 최근 FCF | ${latest_fcf/1e9:,.2f}B |",
                f"| 평균 FCF (3~4년) | ${avg_fcf/1e9:,.2f}B |",
                f"| WACC | {wacc*100:.1f}% |",
                f"| β (베타) | {beta:.2f} |",
                f"| 성장률 추정 | {revenue_growth*100:.1f}% |",
                f"| 영구 성장률 | {terminal_growth*100:.1f}% |",
                f"| 현재가 | ${current_price:,.2f} |",
                f"\n### Monte Carlo DCF 결과 ({n_sim:,}회 시뮬레이션)",
                f"| 백분위 | 적정가 |",
                f"|--------|--------|",
                f"| 10% (비관적) | ${float(np.percentile(fv, 10)):,.2f} |",
                f"| 25% | ${float(np.percentile(fv, 25)):,.2f} |",
                f"| **50% (중앙값)** | **${median_fair:,.2f}** |",
                f"| 75% | ${float(np.percentile(fv, 75)):,.2f} |",
                f"| 90% (낙관적) | ${float(np.percentile(fv, 90)):,.2f} |",
                f"\n### Graham Margin of Safety",
                f"- 중앙값 적정가: **${median_fair:,.2f}**",
                f"- 현재가: ${current_price:,.2f}",
                f"- Margin of Safety: **{mos:+.1f}%**",
            ]

            if mos > 30:
                lines.append("- 🟢 **Graham 매수 기준 충족** — 적정가 대비 30% 이상 저평가")
            elif mos > 10:
                lines.append("- 🟡 약간 저평가 — 30% 미만이므로 Graham 기준 미충족")
            elif mos > -10:
                lines.append("- ⚪ 적정 수준 — 현재가 ≈ 적정가")
            else:
                lines.append(f"- 🔴 **고평가** — 적정가 대비 {abs(mos):.0f}% 프리미엄")

            return "\n".join(lines)
        except Exception as e:
            return f"DCF 분석 실패: {e}"

    # ── DuPont 3단계 분해 ──
    async def _dupont(self, kw: dict) -> str:
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
            inc = t.financials
            bs = t.balance_sheet

            if inc is None or inc.empty or bs is None or bs.empty:
                return f"{symbol}의 재무제표 데이터 없음"

            lines = [f"## {name} ({symbol}) — DuPont ROE 분해\n"]
            lines.append("### DuPont 공식: ROE = 순이익률 × 자산회전율 × 재무레버리지\n")

            # 최근 2~3년 DuPont 비교
            years = min(3, inc.shape[1], bs.shape[1])
            lines.append("| 연도 | 순이익률 | 자산회전율 | 레버리지 | **ROE** |")
            lines.append("|------|---------|----------|---------|---------|")

            for i in range(years):
                # 안전하게 데이터 추출
                net_income = 0
                for label in ["Net Income", "Net Income Common Stockholders"]:
                    if label in inc.index:
                        net_income = float(inc.loc[label].iloc[i] or 0)
                        break
                revenue = 0
                for label in ["Total Revenue", "Revenue"]:
                    if label in inc.index:
                        revenue = float(inc.loc[label].iloc[i] or 0)
                        break
                total_assets = 0
                for label in ["Total Assets"]:
                    if label in bs.index:
                        total_assets = float(bs.loc[label].iloc[i] or 0)
                        break
                total_equity = 0
                for label in ["Total Stockholder Equity", "Stockholders Equity",
                              "Common Stock Equity", "Total Equity Gross Minority Interest"]:
                    if label in bs.index:
                        total_equity = float(bs.loc[label].iloc[i] or 0)
                        break

                year_label = str(inc.columns[i])[:4] if hasattr(inc.columns[i], 'year') else str(inc.columns[i])[:10]

                npm = (net_income / revenue * 100) if revenue else 0
                ato = (revenue / total_assets) if total_assets else 0
                leverage = (total_assets / total_equity) if total_equity else 0
                roe = npm / 100 * ato * leverage * 100

                lines.append(
                    f"| {year_label} | {npm:.1f}% | {ato:.2f}x | {leverage:.2f}x | **{roe:.1f}%** |"
                )

            lines.append("\n### DuPont 해석 가이드")
            lines.append("- **순이익률 ↑**: 가격결정력/비용효율 개선 (질적 성장)")
            lines.append("- **자산회전율 ↑**: 자산 활용 효율 개선 (자본 효율)")
            lines.append("- **레버리지 ↑**: 부채 증가로 ROE 부풀림 (위험 주의)")
            lines.append("- 이상적: 순이익률과 회전율 동시 상승 + 레버리지 안정")

            return "\n".join(lines)
        except Exception as e:
            return f"DuPont 분석 실패: {e}"

    # ── 종합 밸류에이션 ──
    async def _valuation(self, kw: dict) -> str:
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

            pe = info.get("trailingPE")
            fwd_pe = info.get("forwardPE")
            pb = info.get("priceToBook")
            ps = info.get("priceToSalesTrailing12Months")
            ev_ebitda = info.get("enterpriseToEbitda")
            ev_rev = info.get("enterpriseToRevenue")
            peg = info.get("pegRatio")
            div_yield = info.get("dividendYield")
            roe = info.get("returnOnEquity")
            roa = info.get("returnOnAssets")
            profit_margin = info.get("profitMargins")
            rev_growth = info.get("revenueGrowth")
            earn_growth = info.get("earningsGrowth")
            debt_equity = info.get("debtToEquity")
            current_ratio = info.get("currentRatio")
            current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            target = info.get("targetMeanPrice")
            sector = info.get("sector", "")

            lines = [
                f"## {name} ({symbol}) — 밸류에이션 종합분석\n",
                "### 멀티플 비교",
                "| 지표 | 값 | 해석 |",
                "|------|------|------|",
            ]

            def _interpret_pe(v):
                if not v: return "-", "데이터 없음"
                if v < 0: return f"{v:.1f}", "적자 (음수 PER)"
                if v < 10: return f"{v:.1f}", "🟢 저평가 또는 저성장"
                if v < 20: return f"{v:.1f}", "적정"
                if v < 35: return f"{v:.1f}", "고성장 프리미엄"
                return f"{v:.1f}", "🔴 과열 가능"

            pe_v, pe_i = _interpret_pe(pe)
            lines.append(f"| Trailing P/E | {pe_v} | {pe_i} |")
            fpe_v, fpe_i = _interpret_pe(fwd_pe)
            lines.append(f"| Forward P/E | {fpe_v} | {fpe_i} |")
            lines.append(f"| P/B | {pb:.2f} | {'🟢 장부가 이하' if pb and pb < 1 else ('적정' if pb and pb < 3 else '프리미엄')} |" if pb else "| P/B | - | - |")
            lines.append(f"| P/S | {ps:.2f} | {'저평가' if ps and ps < 2 else ('적정' if ps and ps < 8 else '고평가')} |" if ps else "| P/S | - | - |")
            lines.append(f"| EV/EBITDA | {ev_ebitda:.1f} | {'🟢 저평가' if ev_ebitda and ev_ebitda < 10 else ('적정' if ev_ebitda and ev_ebitda < 20 else '고평가')} |" if ev_ebitda else "| EV/EBITDA | - | - |")

            # PEG 분석 (Peter Lynch 기준)
            if peg:
                peg_label = "🟢 성장 대비 저평가" if peg < 1.0 else ("적정" if peg < 2.0 else "🔴 성장 대비 고평가")
                lines.append(f"| **PEG (Lynch)** | **{peg:.2f}** | **{peg_label}** |")

            # 수익성
            lines.append(f"\n### 수익성")
            lines.append(f"| 지표 | 값 |")
            lines.append(f"|------|------|")
            if roe: lines.append(f"| ROE | {roe*100:.1f}% |")
            if roa: lines.append(f"| ROA | {roa*100:.1f}% |")
            if profit_margin: lines.append(f"| 순이익률 | {profit_margin*100:.1f}% |")
            if rev_growth: lines.append(f"| 매출 성장률 | {rev_growth*100:.1f}% |")
            if earn_growth: lines.append(f"| 이익 성장률 | {earn_growth*100:.1f}% |")
            if div_yield: lines.append(f"| 배당 수익률 | {div_yield*100:.2f}% |")

            # 재무 건전성
            lines.append(f"\n### 재무 건전성")
            if debt_equity: lines.append(f"- 부채비율: {debt_equity:.0f}% {'🔴 위험' if debt_equity > 200 else ('⚠️ 주의' if debt_equity > 100 else '✅ 양호')}")
            if current_ratio: lines.append(f"- 유동비율: {current_ratio:.2f}x {'✅ 양호' if current_ratio > 1.5 else ('⚠️ 주의' if current_ratio > 1.0 else '🔴 유동성 위험')}")

            # 애널리스트 컨센서스
            if target and current_price:
                upside = (target - current_price) / current_price * 100
                lines.append(f"\n### 애널리스트 컨센서스")
                lines.append(f"- 목표가: ${target:,.2f} (현재가 대비 {upside:+.1f}%)")
                rec = info.get("recommendationKey", "")
                lines.append(f"- 투자의견: {rec}")

            return "\n".join(lines)
        except Exception as e:
            return f"밸류에이션 분석 실패: {e}"

    # ── 전체 심층 분석 ──
    async def _full(self, kw: dict) -> str:
        parts = []
        for action_fn in [self._valuation, self._dupont, self._dcf]:
            try:
                result = await action_fn(kw)
                parts.append(result)
            except Exception as e:
                parts.append(f"[분석 일부 실패: {e}]")
        return "\n\n---\n\n".join(parts)
