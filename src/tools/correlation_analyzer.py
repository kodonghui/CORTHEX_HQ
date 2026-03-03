"""
자산 상관관계 + 위기 감지 도구 — 동적 상관관계, Tail Dependence, VIX Term Structure.

학술/실무 근거:
  - DCC-GARCH (Engle, 2002):
    Dynamic Conditional Correlation. 상관관계가 시간에 따라 변함을 모형화.
    위기 시 상관관계 급등(Correlation Breakdown) → 분산 효과 소실 감지
  - Tail Dependence (Embrechts et al, 2002):
    극단적 하락 시 자산 간 동시 하락 확률. 정규분포 가정의 위험성.
    평상시 상관 0.3 → 위기 시 0.8+ 급등 현상
  - VIX Term Structure:
    Contango(정상): 원월물 > 근월물 → 안정. 시장이 미래 불확실성을 정상 반영
    Backwardation(역전): 근월물 > 원월물 → 위기! 당장의 공포 > 미래 공포
    2008, 2020 위기 시 Backwardation 발생
  - Contagion Effect (Forbes & Rigobon, 2002):
    위기 전파: 한 시장 급락 → 다른 시장으로 전파. 상관관계 구조 변화로 감지
  - Regime Change Detection:
    변동성 레짐 전환 감지 → 리스크 관리 전략 전환 시그널

사용 방법:
  - action="correlation": 자산 간 상관관계 매트릭스 + 시간별 변화
  - action="crisis_detection": 위기 감지 대시보드 (VIX Term Structure + 상관관계)
  - action="tail_risk": 꼬리 위험 분석 (극단적 동시 하락 확률)
  - action="full": 전체 분석

필요 환경변수: 없음
의존 라이브러리: yfinance, numpy
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.correlation_analyzer")


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


def _to_yf_symbol(sym: str) -> str:
    """한국 6자리 숫자 종목코드에 .KS 접미사를 추가."""
    sym = sym.strip()
    if sym.isdigit() and len(sym) == 6:
        return sym + ".KS"
    return sym


# 주요 글로벌 자산 ETF (상관관계 분석 기본 세트)
DEFAULT_ASSETS = {
    "SPY": "S&P 500",
    "QQQ": "NASDAQ 100",
    "IWM": "Russell 2000",
    "EFA": "선진국 주식",
    "EEM": "이머징 주식",
    "TLT": "미국 장기국채",
    "GLD": "금",
    "USO": "원유",
    "UUP": "미국 달러",
    "HYG": "하이일드 채권",
}


class CorrelationAnalyzerTool(BaseTool):
    """자산 상관관계 + 위기 감지 — DCC, Tail Risk, VIX Term Structure."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "full")
        dispatch = {
            "correlation": self._correlation,
            "crisis_detection": self._crisis_detection,
            "tail_risk": self._tail_risk,
            "full": self._full,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"알 수 없는 action: {action}\n사용 가능: correlation, crisis_detection, tail_risk, full"
        return await handler(kwargs)

    def _parse_symbols(self, kw: dict) -> list:
        symbols = kw.get("symbols") or kw.get("symbol") or kw.get("query") or ""
        if isinstance(symbols, list):
            return [s.upper().strip() for s in symbols if s.strip()]
        parsed = [s.upper().strip() for s in str(symbols).replace(",", " ").split() if s.strip()]
        if not parsed:
            return list(DEFAULT_ASSETS.keys())
        return parsed

    # ── 1. 상관관계 매트릭스 ──
    async def _correlation(self, kw: dict) -> str:
        symbols = self._parse_symbols(kw)
        yf = _yf()
        np = _np()
        if not yf or not np:
            return "yfinance/numpy 미설치"

        import pandas as pd

        try:
            # 가격 데이터 수집
            prices = {}
            for sym in symbols:
                try:
                    t = yf.Ticker(_to_yf_symbol(sym))
                    h = t.history(period="1y")
                    if not h.empty and len(h) > 50:
                        prices[sym] = h["Close"]
                except Exception:
                    continue

            if len(prices) < 2:
                return "최소 2개 자산의 데이터가 필요합니다."

            df = pd.DataFrame(prices).dropna()
            returns = df.pct_change().dropna()
            valid = list(returns.columns)
            n = len(valid)

            # 전체 기간 상관관계
            corr_full = returns.corr()

            # 최근 1개월 상관관계 (동적 비교)
            recent = returns.tail(21)
            corr_recent = recent.corr()

            lines = [
                "## 자산 간 상관관계 분석\n",
                "### Engle(2002) DCC-GARCH: 상관관계는 시간에 따라 변함\n",
                f"### 1년 상관관계 매트릭스 ({n}개 자산)",
            ]

            # 상관행렬 테이블
            header = "| | " + " | ".join(valid) + " |"
            sep = "|---|" + "|".join(["---"] * n) + "|"
            lines.append(header)
            lines.append(sep)
            for i, sym_i in enumerate(valid):
                row = f"| **{sym_i}** |"
                for j, sym_j in enumerate(valid):
                    val = float(corr_full.loc[sym_i, sym_j])
                    if i == j:
                        row += " 1.00 |"
                    elif val > 0.7:
                        row += f" 🔴{val:.2f} |"
                    elif val > 0.3:
                        row += f" 🟡{val:.2f} |"
                    elif val < -0.3:
                        row += f" 🟢{val:.2f} |"
                    else:
                        row += f" {val:.2f} |"
                lines.append(row)

            # 상관관계 변화 (1년 vs 최근 1개월)
            lines.append(f"\n### 상관관계 변화 (1년 → 최근 1개월)")
            lines.append("_상관관계 급등 = 분산 효과 소실 위험 (Forbes & Rigobon, 2002)_\n")

            significant_changes = []
            for i in range(n):
                for j in range(i+1, n):
                    sym_i, sym_j = valid[i], valid[j]
                    full_val = float(corr_full.loc[sym_i, sym_j])
                    recent_val = float(corr_recent.loc[sym_i, sym_j])
                    change = recent_val - full_val

                    if abs(change) > 0.15:
                        significant_changes.append({
                            "pair": f"{sym_i}-{sym_j}",
                            "full": full_val,
                            "recent": recent_val,
                            "change": change,
                        })

            if significant_changes:
                significant_changes.sort(key=lambda x: abs(x["change"]), reverse=True)
                lines.append("| 자산 쌍 | 1년 | 최근 1개월 | 변화 | 의미 |")
                lines.append("|---------|-----|----------|------|------|")
                for sc in significant_changes[:8]:
                    if sc["change"] > 0:
                        meaning = "⚠️ 동조화↑ (분산효과↓)"
                    else:
                        meaning = "✅ 분산효과↑"
                    lines.append(
                        f"| {sc['pair']} | {sc['full']:.2f} | {sc['recent']:.2f} | "
                        f"{sc['change']:+.2f} | {meaning} |"
                    )
            else:
                lines.append("최근 상관관계 변화 미미 (안정적)")

            # 분산 효과 점수
            # 평균 상관관계가 낮을수록 분산 효과 좋음
            off_diag = []
            for i in range(n):
                for j in range(i+1, n):
                    off_diag.append(float(corr_recent.iloc[i, j]))
            avg_corr = sum(off_diag) / len(off_diag) if off_diag else 0

            lines.append(f"\n### 분산 효과 점수")
            lines.append(f"- 평균 상관관계: **{avg_corr:.2f}**")
            if avg_corr < 0.2:
                lines.append("- 🟢 **우수** — 분산 효과 극대화")
            elif avg_corr < 0.4:
                lines.append("- ✅ **양호** — 적절한 분산")
            elif avg_corr < 0.6:
                lines.append("- 🟡 **보통** — 분산 효과 제한적")
            else:
                lines.append("- 🔴 **위험** — 동조화 심각, 위기 시 동시 하락 가능")

            return "\n".join(lines)
        except Exception as e:
            return f"상관관계 분석 실패: {e}"

    # ── 2. 위기 감지 대시보드 ──
    async def _crisis_detection(self, kw: dict) -> str:
        yf = _yf()
        np = _np()
        if not yf or not np:
            return "yfinance/numpy 미설치"

        try:
            crisis_signals = []
            lines = [
                "## 시장 위기 감지 대시보드\n",
            ]

            # 1) VIX 수준
            vix_t = yf.Ticker("^VIX")
            vix_h = vix_t.history(period="1mo")
            if not vix_h.empty:
                vix_current = float(vix_h["Close"].iloc[-1])
                vix_avg = float(vix_h["Close"].mean())
                vix_max = float(vix_h["Close"].max())

                if vix_current >= 35:
                    crisis_signals.append(("🔴 위기", f"VIX {vix_current:.1f} (극공포)"))
                elif vix_current >= 25:
                    crisis_signals.append(("🟡 경계", f"VIX {vix_current:.1f} (공포)"))
                elif vix_current >= 20:
                    crisis_signals.append(("🟡 주의", f"VIX {vix_current:.1f} (불안)"))
                else:
                    crisis_signals.append(("🟢 안정", f"VIX {vix_current:.1f} (정상)"))

            # 2) VIX Term Structure (근월 vs 원월)
            # VIX 근월(VIX) vs 3개월(VIX3M 근사)
            try:
                vix3m_t = yf.Ticker("^VIX3M")
                vix3m_h = vix3m_t.history(period="5d")
                if not vix3m_h.empty and not vix_h.empty:
                    vix_spot = float(vix_h["Close"].iloc[-1])
                    vix_3m = float(vix3m_h["Close"].iloc[-1])
                    term_spread = vix_3m - vix_spot

                    if term_spread < -2:
                        crisis_signals.append(("🔴 위기", f"VIX 역전(Backwardation) {term_spread:+.1f}"))
                    elif term_spread < 0:
                        crisis_signals.append(("🟡 경계", f"VIX 약한 역전 {term_spread:+.1f}"))
                    else:
                        crisis_signals.append(("🟢 안정", f"VIX 정상(Contango) {term_spread:+.1f}"))
            except Exception:
                pass

            # 3) 크레딧 스프레드 (HYG vs LQD)
            try:
                hyg_t = yf.Ticker("HYG")
                lqd_t = yf.Ticker("LQD")
                hyg_h = hyg_t.history(period="1mo")
                lqd_h = lqd_t.history(period="1mo")
                if not hyg_h.empty and not lqd_h.empty:
                    hyg_ret = float(hyg_h["Close"].iloc[-1] / hyg_h["Close"].iloc[0] - 1) * 100
                    lqd_ret = float(lqd_h["Close"].iloc[-1] / lqd_h["Close"].iloc[0] - 1) * 100
                    credit = hyg_ret - lqd_ret
                    if credit < -3:
                        crisis_signals.append(("🔴 위기", f"크레딧 스프레드 확대 (HYG-LQD: {credit:+.1f}%)"))
                    elif credit < -1:
                        crisis_signals.append(("🟡 경계", f"크레딧 스프레드 소폭 확대 ({credit:+.1f}%)"))
                    else:
                        crisis_signals.append(("🟢 안정", f"크레딧 스프레드 안정 ({credit:+.1f}%)"))
            except Exception:
                pass

            # 4) 안전자산 쏠림 (금/주식 상대 성과)
            try:
                gld_t = yf.Ticker("GLD")
                spy_t = yf.Ticker("SPY")
                gld_h = gld_t.history(period="1mo")
                spy_h = spy_t.history(period="1mo")
                if not gld_h.empty and not spy_h.empty:
                    gld_ret = float(gld_h["Close"].iloc[-1] / gld_h["Close"].iloc[0] - 1) * 100
                    spy_ret = float(spy_h["Close"].iloc[-1] / spy_h["Close"].iloc[0] - 1) * 100
                    flight = gld_ret - spy_ret
                    if flight > 8:
                        crisis_signals.append(("🔴 위기", f"안전자산 극심한 쏠림 (금-SPY: {flight:+.1f}%)"))
                    elif flight > 3:
                        crisis_signals.append(("🟡 경계", f"안전자산 쏠림 (금-SPY: {flight:+.1f}%)"))
                    else:
                        crisis_signals.append(("🟢 안정", f"안전자산 쏠림 없음 (금-SPY: {flight:+.1f}%)"))
            except Exception:
                pass

            # 5) 시장 폭 (S&P500 vs Russell2000)
            try:
                iwm_t = yf.Ticker("IWM")
                iwm_h = iwm_t.history(period="1mo")
                if not iwm_h.empty and not spy_h.empty:
                    iwm_ret = float(iwm_h["Close"].iloc[-1] / iwm_h["Close"].iloc[0] - 1) * 100
                    spy_ret2 = float(spy_h["Close"].iloc[-1] / spy_h["Close"].iloc[0] - 1) * 100
                    breadth = iwm_ret - spy_ret2
                    if breadth < -5:
                        crisis_signals.append(("🟡 경계", f"소형주 급약세 (IWM-SPY: {breadth:+.1f}%)"))
                    else:
                        crisis_signals.append(("🟢 안정", f"시장 폭 정상 (IWM-SPY: {breadth:+.1f}%)"))
            except Exception:
                pass

            # 6) S&P500 200일 MA
            try:
                spy_1y = spy_t.history(period="1y")
                if not spy_1y.empty and len(spy_1y) >= 200:
                    current = float(spy_1y["Close"].iloc[-1])
                    ma200 = float(spy_1y["Close"].tail(200).mean())
                    pct_from_ma = (current - ma200) / ma200 * 100
                    if pct_from_ma < -10:
                        crisis_signals.append(("🔴 위기", f"S&P500 200일MA {pct_from_ma:+.1f}% 하회"))
                    elif pct_from_ma < 0:
                        crisis_signals.append(("🟡 경계", f"S&P500 200일MA 소폭 하회 ({pct_from_ma:+.1f}%)"))
                    else:
                        crisis_signals.append(("🟢 안정", f"S&P500 200일MA 상회 ({pct_from_ma:+.1f}%)"))
            except Exception:
                pass

            # 종합 판정
            crisis_count = sum(1 for s in crisis_signals if "위기" in s[0])
            warn_count = sum(1 for s in crisis_signals if "경계" in s[0] or "주의" in s[0])
            total = len(crisis_signals)

            if crisis_count >= 3:
                overall = "🔴🔴 **위기 단계** — 포트폴리오 방어 모드 전환 권장"
                risk_score = 90
            elif crisis_count >= 2:
                overall = "🔴 **고위험** — 리스크 축소 + 안전자산 비중 확대"
                risk_score = 70
            elif warn_count >= 3:
                overall = "🟡 **경계** — 모니터링 강화, 신규 매수 신중"
                risk_score = 50
            elif warn_count >= 1:
                overall = "🟡 **주의** — 일부 경계 신호 존재"
                risk_score = 35
            else:
                overall = "🟢 **안정** — 정상적 시장 환경"
                risk_score = 15

            lines.append(f"### 종합 위기 수준: {overall}")
            lines.append(f"### 위기 지수: **{risk_score}/100**\n")

            lines.append("### 세부 지표")
            lines.append("| 상태 | 지표 |")
            lines.append("|------|------|")
            for status, desc in crisis_signals:
                lines.append(f"| {status} | {desc} |")

            # 대응 전략
            lines.append(f"\n### 레짐별 대응 전략")
            if risk_score >= 70:
                lines.append("| 전략 | 설명 |")
                lines.append("|------|------|")
                lines.append("| 현금 비중 확대 | 포트폴리오의 20~40%를 현금/단기채로 |")
                lines.append("| 풋옵션 헤지 | SPY 풋 또는 VIX 콜로 테일리스크 헤지 |")
                lines.append("| 안전자산 이동 | TLT(장기국채), GLD(금) 비중 확대 |")
                lines.append("| 레버리지 축소 | 마진 사용 중이면 즉시 축소 |")
            elif risk_score >= 40:
                lines.append("- 포지션 신규 진입 자제, 기존 포지션 유지")
                lines.append("- 손절선 타이트하게 조정")
                lines.append("- 방어적 섹터(XLP, XLV, XLU) 비중 점검")
            else:
                lines.append("- 정상적 투자 전략 유지")
                lines.append("- 포트폴리오 리밸런싱 적기")
                lines.append("- 다만 VIX < 15 시 자기만족 경계 (헤지 비용 저렴할 때 보험 가입)")

            return "\n".join(lines)
        except Exception as e:
            return f"위기 감지 실패: {e}"

    # ── 3. 꼬리 위험 분석 ──
    async def _tail_risk(self, kw: dict) -> str:
        symbols = self._parse_symbols(kw)
        yf = _yf()
        np = _np()
        if not yf or not np:
            return "yfinance/numpy 미설치"

        import pandas as pd

        try:
            prices = {}
            names = {}
            for sym in symbols[:8]:  # 최대 8개
                try:
                    t = yf.Ticker(_to_yf_symbol(sym))
                    h = t.history(period="2y")
                    if not h.empty and len(h) > 100:
                        prices[sym] = h["Close"]
                        info = t.info or {}
                        names[sym] = info.get("shortName") or sym
                except Exception:
                    continue

            if len(prices) < 2:
                return "최소 2개 자산 데이터 필요"

            df = pd.DataFrame(prices).dropna()
            returns = df.pct_change().dropna()
            valid = list(returns.columns)
            n = len(valid)

            lines = [
                "## 꼬리 위험(Tail Risk) 분석\n",
                "### Embrechts et al(2002): 극단적 하락 시 자산 동시 하락 확률\n",
            ]

            # 개별 자산 꼬리 통계
            lines.append("### 개별 자산 꼬리 위험")
            lines.append("| 자산 | VaR 5% | CVaR 5% | 최대낙폭 | 왜도 | 첨도 |")
            lines.append("|------|--------|---------|---------|------|------|")

            for sym in valid:
                r = returns[sym].values
                var_5 = float(np.percentile(r, 5)) * 100
                cvar_5 = float(r[r <= np.percentile(r, 5)].mean()) * 100 if len(r[r <= np.percentile(r, 5)]) > 0 else var_5

                # 최대 낙폭 (MDD)
                cum = (1 + returns[sym]).cumprod()
                peak = cum.cummax()
                dd = (cum - peak) / peak
                mdd = float(dd.min()) * 100

                # 왜도/첨도
                skew = float(returns[sym].skew())
                kurt = float(returns[sym].kurtosis())

                lines.append(
                    f"| {names.get(sym,sym)} ({sym}) | {var_5:.2f}% | {cvar_5:.2f}% | "
                    f"{mdd:.1f}% | {skew:.2f} | {kurt:.1f} |"
                )

            # Tail Dependence: 하위 5% 동시 발생 비율
            lines.append(f"\n### Tail Dependence (하위 5% 동시 하락)")
            lines.append("_평상시 상관 vs 위기 시 동시 하락 확률 비교_\n")

            if n <= 6:
                header = "| | " + " | ".join(valid) + " |"
                sep_line = "|---|" + "|".join(["---"] * n) + "|"
                lines.append(header)
                lines.append(sep_line)

                for i in range(n):
                    row = f"| **{valid[i]}** |"
                    for j in range(n):
                        if i == j:
                            row += " - |"
                        else:
                            r_i = returns[valid[i]].values
                            r_j = returns[valid[j]].values
                            threshold_i = np.percentile(r_i, 5)
                            threshold_j = np.percentile(r_j, 5)
                            joint_tail = np.mean(
                                (r_i <= threshold_i) & (r_j <= threshold_j)
                            ) * 100
                            # 독립이면 0.25% (5% × 5%)
                            if joint_tail > 1.0:
                                row += f" 🔴{joint_tail:.1f}% |"
                            elif joint_tail > 0.5:
                                row += f" 🟡{joint_tail:.1f}% |"
                            else:
                                row += f" {joint_tail:.1f}% |"
                    lines.append(row)

                lines.append("\n_독립 가정 시 0.25% (5%×5%). 그 이상이면 Tail Dependence 존재_")
            else:
                # 자산이 많으면 주요 쌍만
                pairs = []
                for i in range(n):
                    for j in range(i+1, n):
                        r_i = returns[valid[i]].values
                        r_j = returns[valid[j]].values
                        t_i = np.percentile(r_i, 5)
                        t_j = np.percentile(r_j, 5)
                        joint = float(np.mean((r_i <= t_i) & (r_j <= t_j))) * 100
                        pairs.append((valid[i], valid[j], joint))

                pairs.sort(key=lambda x: x[2], reverse=True)
                lines.append("| 자산 쌍 | 동시 하락 확률 | 위험도 |")
                lines.append("|---------|-------------|--------|")
                for a, b, jt in pairs[:10]:
                    risk = "🔴 높음" if jt > 1.0 else ("🟡 보통" if jt > 0.5 else "🟢 낮음")
                    lines.append(f"| {a}-{b} | {jt:.2f}% | {risk} |")

            # 위기 시 상관관계 vs 평상시
            lines.append(f"\n### 위기 시 상관관계 변화")
            # 하위 10% 수익률일 때의 상관 vs 전체 상관
            spy_returns = returns.get("SPY")
            if spy_returns is not None:
                threshold = np.percentile(spy_returns.values, 10)
                crisis_mask = spy_returns <= threshold
                normal_mask = spy_returns > threshold

                crisis_days = int(crisis_mask.sum())
                normal_days = int(normal_mask.sum())

                if crisis_days > 10 and normal_days > 10:
                    lines.append(f"_S&P500 하위 10% 거래일({crisis_days}일) vs 정상({normal_days}일)_\n")
                    lines.append("| 자산 | 정상 시 상관 | 위기 시 상관 | 변화 |")
                    lines.append("|------|-----------|-----------|------|")

                    for sym in valid:
                        if sym == "SPY":
                            continue
                        normal_corr = float(returns.loc[normal_mask, ["SPY", sym]].corr().iloc[0, 1])
                        crisis_corr = float(returns.loc[crisis_mask, ["SPY", sym]].corr().iloc[0, 1])
                        change = crisis_corr - normal_corr

                        arrow = "↑" if change > 0 else "↓"
                        emoji = "⚠️" if change > 0.2 else ("✅" if change < -0.1 else "")
                        lines.append(
                            f"| {names.get(sym,sym)} ({sym}) | {normal_corr:.2f} | "
                            f"{crisis_corr:.2f} | {change:+.2f} {arrow} {emoji} |"
                        )

                    lines.append("\n- ⚠️ 위기 시 상관관계 ↑ = **분산 효과 소실** (가장 필요할 때 무력화)")
                    lines.append("- ✅ 위기 시 상관관계 ↓ = **진정한 헤지** (금, 국채 등)")

            return "\n".join(lines)
        except Exception as e:
            return f"꼬리 위험 분석 실패: {e}"

    # ── 전체 분석 ──
    async def _full(self, kw: dict) -> str:
        parts = []
        for fn in [self._crisis_detection, self._correlation, self._tail_risk]:
            try:
                parts.append(await fn(kw))
            except Exception as e:
                parts.append(f"[분석 일부 실패: {e}]")
        return "\n\n---\n\n".join(parts)
