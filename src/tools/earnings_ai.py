"""
AI 실적 예측 도구 — Whisper Number, 어닝 서프라이즈, PEAD, 리비전 모멘텀.

학술/실무 근거:
  - PEAD (Post-Earnings Announcement Drift, Ball & Brown, 1968):
    어닝 서프라이즈 후 60~90 거래일간 같은 방향 드리프트.
    가장 오래되고 가장 강건한 시장 이상(anomaly). 행동경제학(underreaction) 기반
  - Whisper Number: 공식 컨센서스보다 높은 비공식 기대치.
    실제 실적이 컨센서스 상회해도 Whisper 하회 시 주가 하락 가능
  - Earnings Revision Momentum (Hawkins et al, 1984):
    분석가 추정치 상향 조정 지속 → 주가 상승. Estimate Momentum Factor
  - SUE (Standardized Unexpected Earnings, Latané & Jones, 1979):
    SUE = (실제EPS - 예상EPS) / σ(과거서프라이즈). |SUE| > 2 = 강한 시그널
  - Earnings Quality (Sloan, 1996): 발생액(Accruals) 비중 높으면 이익의 질 낮음
    CFO/순이익 > 1.0 = 양질의 이익 (현금흐름이 이익 뒷받침)
  - Pre-Earnings Vol Crush: IV가 실적 발표 전 상승 → 발표 후 급락 (옵션 매도 기회)

사용 방법:
  - action="upcoming": 실적 발표 임박 종목 + IV 분석
  - action="surprise_history": 과거 어닝 서프라이즈 패턴 분석
  - action="quality": 이익의 질 (발생액 vs 현금흐름)
  - action="full": 전체 실적 분석

필요 환경변수: 없음
의존 라이브러리: yfinance
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.earnings_ai")


def _yf():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        return None


def _to_yf_symbol(sym: str) -> str:
    """한국 6자리 숫자 종목코드에 .KS 접미사를 추가."""
    sym = sym.strip()
    if sym.isdigit() and len(sym) == 6:
        return sym + ".KS"
    return sym


class EarningsAiTool(BaseTool):
    """AI 실적 예측 — 어닝 서프라이즈, PEAD, 이익의 질."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "full")
        if "query" in kwargs and "symbol" not in kwargs:
            kwargs["symbol"] = kwargs["query"]

        dispatch = {
            "upcoming": self._upcoming,
            "surprise_history": self._surprise_history,
            "quality": self._earnings_quality,
            "full": self._full,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"알 수 없는 action: {action}\n사용 가능: upcoming, surprise_history, quality, full"
        return await handler(kwargs)

    # ── 1. 실적 발표 임박 종목 분석 ──
    async def _upcoming(self, kw: dict) -> str:
        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        try:
            t = yf.Ticker(_to_yf_symbol(symbol))
            info = t.info or {}
            name = info.get("longName") or symbol
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

            lines = [
                f"## {name} ({symbol}) — 실적 발표 분석\n",
                f"현재가: ${price:,.2f}\n",
            ]

            # 다음 실적 발표일
            cal = t.calendar
            if cal is not None:
                if isinstance(cal, dict):
                    earn_date = cal.get("Earnings Date")
                    if earn_date:
                        if isinstance(earn_date, list) and len(earn_date) > 0:
                            ed = earn_date[0]
                        else:
                            ed = earn_date
                        lines.append(f"### 다음 실적 발표일: **{ed}**\n")

                        # D-day 계산
                        try:
                            if hasattr(ed, "date"):
                                ed_date = ed.date()
                            else:
                                ed_date = datetime.strptime(str(ed)[:10], "%Y-%m-%d").date()
                            days_to = (ed_date - datetime.now().date()).days
                            if days_to >= 0:
                                lines.append(f"📅 D-{days_to}일\n")
                                if days_to <= 7:
                                    lines.append("⚠️ **실적 발표 임박** — IV 상승 구간, 옵션 프리미엄 주의\n")
                        except Exception:
                            pass

            # 컨센서스 EPS
            eps_est = info.get("epsForward") or info.get("epsCurrentYear")
            eps_trail = info.get("trailingEps")
            rev_est = info.get("revenueEstimate") or info.get("totalRevenue")

            if eps_est or eps_trail:
                lines.append("### EPS 추정")
                if eps_trail:
                    lines.append(f"- 최근 12개월 실적 EPS: **${eps_trail:.2f}**")
                if eps_est:
                    lines.append(f"- 컨센서스 Forward EPS: **${eps_est:.2f}**")
                    if eps_trail and eps_trail > 0:
                        growth = (eps_est - eps_trail) / abs(eps_trail) * 100
                        lines.append(f"- 예상 EPS 성장률: {growth:+.1f}%")

            # Forward P/E
            fwd_pe = info.get("forwardPE")
            trail_pe = info.get("trailingPE")
            if fwd_pe:
                lines.append(f"\n### 밸류에이션")
                if trail_pe:
                    lines.append(f"- Trailing P/E: {trail_pe:.1f}x")
                lines.append(f"- Forward P/E: {fwd_pe:.1f}x")
                if trail_pe and fwd_pe < trail_pe:
                    lines.append("- 📉 Forward P/E < Trailing P/E → 이익 성장 기대")
                elif trail_pe and fwd_pe > trail_pe * 1.2:
                    lines.append("- ⚠️ Forward P/E > Trailing P/E → 이익 둔화 우려")

            # 옵션 IV 확인 (실적 전 IV 상승)
            try:
                exps = t.options
                if exps:
                    chain = t.option_chain(exps[0])
                    atm_calls = chain.calls[
                        (chain.calls["strike"] >= price * 0.95) &
                        (chain.calls["strike"] <= price * 1.05)
                    ]
                    if len(atm_calls) > 0 and "impliedVolatility" in atm_calls.columns:
                        avg_iv = float(atm_calls["impliedVolatility"].mean()) * 100
                        lines.append(f"\n### 옵션 IV (최근 만기 ATM)")
                        lines.append(f"- 내재변동성: **{avg_iv:.1f}%**")
                        if avg_iv > 60:
                            lines.append("- 🔥 IV 매우 높음 — 실적 발표 전 프리미엄 최대")
                            lines.append("  - 전략: 실적 발표 전 스트래들/스트랭글 매도 (IV Crush 수익)")
                        elif avg_iv > 40:
                            lines.append("- 🟡 IV 높음 — 실적 기대감/불확실성 반영")
                        else:
                            lines.append("- ⚪ IV 보통 — 큰 서프라이즈 기대 낮음")
            except Exception:
                pass

            return "\n".join(lines)
        except Exception as e:
            return f"실적 분석 실패: {e}"

    # ── 2. 어닝 서프라이즈 히스토리 (PEAD 분석) ──
    async def _surprise_history(self, kw: dict) -> str:
        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        try:
            t = yf.Ticker(_to_yf_symbol(symbol))
            info = t.info or {}
            name = info.get("longName") or symbol

            lines = [
                f"## {name} ({symbol}) — 어닝 서프라이즈 히스토리\n",
                "### Ball & Brown(1968) PEAD: 서프라이즈 방향으로 60~90일 드리프트\n",
            ]

            # 실적 히스토리
            earnings = t.earnings_history
            if earnings is not None and not earnings.empty:
                lines.append("| 분기 | 예상 EPS | 실제 EPS | 서프라이즈 | SUE |")
                lines.append("|------|---------|---------|-----------|-----|")

                beat_count = 0
                miss_count = 0
                surprises = []

                for _, row in earnings.iterrows():
                    est = row.get("epsEstimate") or row.get("epsexpected")
                    act = row.get("epsActual") or row.get("epsactual")
                    date_val = row.get("quarter") or row.name

                    if est is None or act is None:
                        continue

                    est = float(est)
                    act = float(act)
                    surprise_pct = ((act - est) / abs(est) * 100) if est != 0 else 0
                    surprises.append(surprise_pct)

                    # SUE 근사 (과거 서프라이즈의 표준편차 사용)
                    sue = "N/A"
                    if len(surprises) >= 2:
                        import statistics
                        std = statistics.stdev(surprises[:-1]) if len(surprises) > 2 else abs(surprises[0]) or 1
                        if std > 0:
                            sue_val = surprise_pct / std
                            sue = f"{sue_val:+.1f}"

                    if act > est:
                        beat_count += 1
                        icon = "🟢"
                    elif act < est:
                        miss_count += 1
                        icon = "🔴"
                    else:
                        icon = "⚪"

                    date_str = str(date_val)[:10] if date_val is not None else "?"
                    lines.append(
                        f"| {date_str} | ${est:.2f} | ${act:.2f} | "
                        f"{icon} {surprise_pct:+.1f}% | {sue} |"
                    )

                total = beat_count + miss_count
                if total > 0:
                    beat_rate = beat_count / total * 100
                    lines.append(f"\n### 서프라이즈 패턴")
                    lines.append(f"- Beat 횟수: **{beat_count}/{total}** ({beat_rate:.0f}%)")
                    lines.append(f"- Miss 횟수: {miss_count}/{total}")

                    if beat_rate >= 75:
                        lines.append("- 🟢 **일관적 Beat** — 보수적 가이던스 성향, PEAD 상승 기대")
                    elif beat_rate >= 50:
                        lines.append("- 🟡 혼합 — 특정 패턴 없음")
                    else:
                        lines.append("- 🔴 **빈번한 Miss** — 실적 하방 리스크 주의")

                    if surprises:
                        avg_surprise = sum(surprises) / len(surprises)
                        lines.append(f"- 평균 서프라이즈: {avg_surprise:+.1f}%")
                        if avg_surprise > 5:
                            lines.append("  → 분석가 추정치가 보수적 (Whisper > 컨센서스 가능)")
            else:
                lines.append("실적 히스토리 데이터 없음")

            # 실적 발표일 전후 주가 반응
            try:
                hist = t.history(period="2y")
                if not hist.empty and earnings is not None and not earnings.empty:
                    lines.append(f"\n### PEAD 참고")
                    lines.append("- Ball & Brown(1968): 서프라이즈 방향으로 60~90일 추가 드리프트")
                    lines.append("- Latané & Jones(1979): |SUE| > 2 = 강한 시그널")
                    lines.append("- 실적 Beat 후 매수 → 다음 분기까지 보유 = PEAD 전략의 핵심")
            except Exception:
                pass

            return "\n".join(lines)
        except Exception as e:
            return f"서프라이즈 히스토리 분석 실패: {e}"

    # ── 3. 이익의 질 (Earnings Quality) ──
    async def _earnings_quality(self, kw: dict) -> str:
        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        try:
            t = yf.Ticker(_to_yf_symbol(symbol))
            info = t.info or {}
            name = info.get("longName") or symbol

            lines = [
                f"## {name} ({symbol}) — 이익의 질 분석\n",
                "### Sloan(1996): 발생액 비중 높으면 이익의 질 낮음 → 미래 수익 하락\n",
            ]

            # 재무제표에서 데이터 추출
            cf = t.cashflow
            income = t.income_stmt

            if cf is None or cf.empty or income is None or income.empty:
                return f"{symbol}의 재무 데이터를 가져올 수 없습니다."

            # 최근 3년 분석
            lines.append("| 항목 | " + " | ".join(str(c)[:4] for c in income.columns[:3]) + " |")
            lines.append("|------|" + "|".join(["------"] * min(3, len(income.columns))) + "|")

            # 순이익
            ni_row = None
            for label in ["Net Income", "NetIncome", "Net Income Common Stockholders"]:
                if label in income.index:
                    ni_row = income.loc[label]
                    break

            # 영업활동 현금흐름
            cfo_row = None
            for label in ["Operating Cash Flow", "Total Cash From Operating Activities",
                          "Cash Flow From Continuing Operating Activities"]:
                if label in cf.index:
                    cfo_row = cf.loc[label]
                    break

            if ni_row is not None:
                vals = [f"${float(ni_row.iloc[i]):,.0f}" if i < len(ni_row) else "N/A" for i in range(3)]
                lines.append(f"| 순이익 | " + " | ".join(vals) + " |")

            if cfo_row is not None:
                vals = [f"${float(cfo_row.iloc[i]):,.0f}" if i < len(cfo_row) else "N/A" for i in range(3)]
                lines.append(f"| 영업CF | " + " | ".join(vals) + " |")

            # CFO/NI 비율 (이익의 질 핵심 지표)
            if ni_row is not None and cfo_row is not None:
                ratios = []
                for i in range(min(3, len(ni_row), len(cfo_row))):
                    ni = float(ni_row.iloc[i]) if ni_row.iloc[i] else 0
                    cfo = float(cfo_row.iloc[i]) if cfo_row.iloc[i] else 0
                    if ni != 0:
                        ratio = cfo / ni
                        ratios.append(ratio)
                    else:
                        ratios.append(None)

                vals = [f"{r:.2f}x" if r is not None else "N/A" for r in ratios]
                lines.append(f"| CFO/NI | " + " | ".join(vals) + " |")

                # 발생액 (Accruals = NI - CFO)
                accruals = []
                for i in range(min(3, len(ni_row), len(cfo_row))):
                    ni = float(ni_row.iloc[i]) if ni_row.iloc[i] else 0
                    cfo = float(cfo_row.iloc[i]) if cfo_row.iloc[i] else 0
                    accruals.append(ni - cfo)

                vals = [f"${a:,.0f}" for a in accruals]
                lines.append(f"| 발생액 | " + " | ".join(vals) + " |")

                # 판정
                lines.append(f"\n### 이익의 질 판정")
                latest_ratio = ratios[0] if ratios else None
                if latest_ratio is not None:
                    if latest_ratio >= 1.2:
                        lines.append(f"- 🟢 **최고 품질** (CFO/NI = {latest_ratio:.2f}x)")
                        lines.append("  - 현금흐름이 회계이익을 크게 상회 → 이익이 현금으로 뒷받침됨")
                    elif latest_ratio >= 0.8:
                        lines.append(f"- ✅ **양호** (CFO/NI = {latest_ratio:.2f}x)")
                        lines.append("  - 이익과 현금흐름 대체로 일치")
                    elif latest_ratio >= 0.5:
                        lines.append(f"- 🟡 **주의** (CFO/NI = {latest_ratio:.2f}x)")
                        lines.append("  - 발생액 비중 높음 → Sloan(1996) 기준 미래 수익 하락 가능")
                    else:
                        lines.append(f"- 🔴 **경고** (CFO/NI = {latest_ratio:.2f}x)")
                        lines.append("  - 이익 대부분이 발생액 → 분식회계 또는 일시적 이익 가능성")

                # 추세 분석
                valid_ratios = [r for r in ratios if r is not None]
                if len(valid_ratios) >= 2:
                    if valid_ratios[0] > valid_ratios[1]:
                        lines.append("- 📈 이익의 질 **개선** 추세")
                    elif valid_ratios[0] < valid_ratios[1]:
                        lines.append("- 📉 이익의 질 **악화** 추세")

            # 추가 품질 지표
            total_assets_row = None
            bs = t.balance_sheet
            if bs is not None and not bs.empty:
                for label in ["Total Assets", "TotalAssets"]:
                    if label in bs.index:
                        total_assets_row = bs.loc[label]
                        break

            if total_assets_row is not None and ni_row is not None:
                ta = float(total_assets_row.iloc[0]) if total_assets_row.iloc[0] else 0
                ni = float(ni_row.iloc[0]) if ni_row.iloc[0] else 0
                if ta > 0:
                    roa = ni / ta * 100
                    lines.append(f"\n### 추가 품질 지표")
                    lines.append(f"- ROA: {roa:.1f}% {'🟢' if roa > 10 else ('🟡' if roa > 5 else '🔴')}")

            lines.append("\n### 해석 가이드")
            lines.append("- **CFO/NI > 1.0**: 이익이 현금으로 뒷받침 → 지속 가능")
            lines.append("- **CFO/NI < 0.5**: 발생액 의존 → Sloan Accrual Anomaly 해당")
            lines.append("- **발생액 증가 추세**: 이익 조작(Earnings Management) 의심 시그널")
            lines.append("- **Beneish M-Score**(참고): -1.78 이상이면 이익 조작 확률 높음")

            return "\n".join(lines)
        except Exception as e:
            return f"이익의 질 분석 실패: {e}"

    # ── 전체 분석 ──
    async def _full(self, kw: dict) -> str:
        parts = []
        for fn in [self._upcoming, self._surprise_history, self._earnings_quality]:
            try:
                parts.append(await fn(kw))
            except Exception as e:
                parts.append(f"[분석 일부 실패: {e}]")
        return "\n\n---\n\n".join(parts)
