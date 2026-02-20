"""
글로벌 포트폴리오 최적화 도구 — Markowitz, Black-Litterman, Risk Parity, Kelly Criterion.

학술/실무 근거:
  - Markowitz(1952) Mean-Variance Optimization (MVO):
    효율적 프론티어 위의 최적 자산배분. 노벨경제학상 수상.
    한계: 입력 민감도 높음 → Black-Litterman으로 보완
  - Black-Litterman(1992):
    시장 균형 수익률(CAPM)을 사전분포로, 투자자 견해(Views)를 반영.
    Markowitz의 극단적 비중 문제 해결. Goldman Sachs 자산배분팀 개발
  - Risk Parity (Qian, 2005 "Risk Parity Portfolios"):
    각 자산의 리스크 기여도를 균등화. Bridgewater All Weather Fund 핵심 전략.
    변동성 기준 배분 → 안정적 성과, 시장 중립적
  - Kelly Criterion (Kelly, 1956):
    f* = (bp - q) / b (b=배당률, p=승률, q=패률). 장기 복리 성장 최대화.
    Half-Kelly(f*/2) = 실무에서 리스크 50% 감소, 성장의 75% 유지
  - Sharpe Ratio (Sharpe, 1966): (Rp - Rf) / σp.
    최적화의 핵심 목적함수. SR > 1.0 = 우수, > 2.0 = 탁월

사용 방법:
  - action="optimize": 포트폴리오 최적화 (Markowitz + Risk Parity)
  - action="kelly": Kelly Criterion 최적 비중
  - action="efficient_frontier": 효율적 프론티어 시뮬레이션
  - action="full": 전체 분석

필요 환경변수: 없음
의존 라이브러리: yfinance, numpy
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.portfolio_optimizer_v2")


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


class PortfolioOptimizerV2Tool(BaseTool):
    """글로벌 포트폴리오 최적화 — Markowitz, Risk Parity, Kelly."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "full")
        dispatch = {
            "optimize": self._optimize,
            "kelly": self._kelly,
            "efficient_frontier": self._efficient_frontier,
            "full": self._full,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"알 수 없는 action: {action}\n사용 가능: optimize, kelly, efficient_frontier, full"
        return await handler(kwargs)

    def _parse_symbols(self, kw: dict) -> list:
        """심볼 리스트 파싱."""
        symbols = kw.get("symbols") or kw.get("symbol") or kw.get("query") or ""
        if isinstance(symbols, list):
            return [s.upper().strip() for s in symbols if s.strip()]
        return [s.upper().strip() for s in str(symbols).replace(",", " ").split() if s.strip()]

    async def _get_returns(self, symbols: list, period: str = "1y"):
        """종목별 수익률 데이터 수집."""
        yf = _yf()
        np = _np()
        if not yf or not np:
            return None, None, None

        import pandas as pd

        prices_dict = {}
        names = {}
        for sym in symbols:
            try:
                t = yf.Ticker(sym)
                hist = t.history(period=period)
                if not hist.empty and len(hist) > 20:
                    prices_dict[sym] = hist["Close"]
                    info = t.info or {}
                    names[sym] = info.get("shortName") or info.get("longName") or sym
            except Exception:
                continue

        if len(prices_dict) < 2:
            return None, None, None

        prices = pd.DataFrame(prices_dict).dropna()
        returns = prices.pct_change().dropna()

        return returns, prices, names

    # ── 1. 포트폴리오 최적화 ──
    async def _optimize(self, kw: dict) -> str:
        symbols = self._parse_symbols(kw)
        if len(symbols) < 2:
            return "최소 2개 이상의 심볼이 필요합니다. (예: symbols=\"AAPL MSFT GOOGL\")"

        np = _np()
        if not np:
            return "numpy 미설치"

        returns, prices, names = await self._get_returns(symbols)
        if returns is None:
            return "가격 데이터 조회 실패 (최소 2개 종목 필요)"

        n = len(returns.columns)
        mean_returns = returns.mean().values * 252  # 연환산
        cov_matrix = returns.cov().values * 252
        valid_symbols = list(returns.columns)

        lines = [
            "## 포트폴리오 최적화 분석\n",
            f"### 대상: {', '.join(f'{names.get(s,s)}({s})' for s in valid_symbols)}",
            f"_기간: 최근 1년 일일 수익률 기반_\n",
        ]

        # 개별 종목 통계
        lines.append("### 개별 종목 통계")
        lines.append("| 종목 | 연환산 수익률 | 연환산 변동성 | Sharpe |")
        lines.append("|------|-------------|-------------|--------|")

        rf = 0.045  # 무위험 이자율 (미국 T-Bill 근사)
        for i, sym in enumerate(valid_symbols):
            ret = mean_returns[i] * 100
            vol = float(np.sqrt(cov_matrix[i][i])) * 100
            sharpe = (mean_returns[i] - rf) / float(np.sqrt(cov_matrix[i][i])) if cov_matrix[i][i] > 0 else 0
            lines.append(f"| {names.get(sym,sym)} ({sym}) | {ret:+.1f}% | {vol:.1f}% | {sharpe:.2f} |")

        # ── Markowitz 최적화 (Monte Carlo 10000 시뮬레이션) ──
        num_sim = 10000
        best_sharpe = -999
        best_weights_sharpe = None
        min_vol = 999
        best_weights_minvol = None

        for _ in range(num_sim):
            w = np.random.dirichlet(np.ones(n))
            port_ret = float(np.dot(w, mean_returns))
            port_vol = float(np.sqrt(np.dot(w.T, np.dot(cov_matrix, w))))
            sharpe = (port_ret - rf) / port_vol if port_vol > 0 else 0

            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_weights_sharpe = w.copy()

            if port_vol < min_vol:
                min_vol = port_vol
                best_weights_minvol = w.copy()

        # ── Risk Parity (역변동성 비중) ──
        vols = np.array([np.sqrt(cov_matrix[i][i]) for i in range(n)])
        inv_vols = 1.0 / vols
        rp_weights = inv_vols / inv_vols.sum()

        # 결과 출력
        lines.append(f"\n### 1. Markowitz 최대 Sharpe 포트폴리오 (10,000 시뮬레이션)")
        if best_weights_sharpe is not None:
            port_ret = float(np.dot(best_weights_sharpe, mean_returns)) * 100
            port_vol = float(np.sqrt(np.dot(best_weights_sharpe.T, np.dot(cov_matrix, best_weights_sharpe)))) * 100
            lines.append(f"- 예상 수익률: **{port_ret:+.1f}%** | 변동성: {port_vol:.1f}% | Sharpe: **{best_sharpe:.2f}**")
            lines.append("| 종목 | 비중 |")
            lines.append("|------|------|")
            for i, sym in enumerate(valid_symbols):
                w = best_weights_sharpe[i] * 100
                bar = "█" * int(w / 5)
                lines.append(f"| {sym} | {bar} {w:.1f}% |")

        lines.append(f"\n### 2. 최소 변동성 포트폴리오")
        if best_weights_minvol is not None:
            port_ret = float(np.dot(best_weights_minvol, mean_returns)) * 100
            port_vol = min_vol * 100
            sharpe_mv = (float(np.dot(best_weights_minvol, mean_returns)) - rf) / min_vol if min_vol > 0 else 0
            lines.append(f"- 예상 수익률: {port_ret:+.1f}% | 변동성: **{port_vol:.1f}%** | Sharpe: {sharpe_mv:.2f}")
            lines.append("| 종목 | 비중 |")
            lines.append("|------|------|")
            for i, sym in enumerate(valid_symbols):
                w = best_weights_minvol[i] * 100
                bar = "█" * int(w / 5)
                lines.append(f"| {sym} | {bar} {w:.1f}% |")

        lines.append(f"\n### 3. Risk Parity 포트폴리오 (Qian, 2005)")
        rp_ret = float(np.dot(rp_weights, mean_returns)) * 100
        rp_vol = float(np.sqrt(np.dot(rp_weights.T, np.dot(cov_matrix, rp_weights)))) * 100
        rp_sharpe = (float(np.dot(rp_weights, mean_returns)) - rf) / (rp_vol / 100) if rp_vol > 0 else 0
        lines.append(f"- 예상 수익률: {rp_ret:+.1f}% | 변동성: {rp_vol:.1f}% | Sharpe: {rp_sharpe:.2f}")
        lines.append("| 종목 | 비중 | 개별 변동성 |")
        lines.append("|------|------|-----------|")
        for i, sym in enumerate(valid_symbols):
            w = rp_weights[i] * 100
            v = vols[i] * 100
            bar = "█" * int(w / 5)
            lines.append(f"| {sym} | {bar} {w:.1f}% | {v:.1f}% |")

        # 상관행렬
        corr = returns.corr()
        lines.append(f"\n### 상관행렬")
        header = "| | " + " | ".join(valid_symbols) + " |"
        sep = "|---|" + "|".join(["---"] * n) + "|"
        lines.append(header)
        lines.append(sep)
        for i, sym_i in enumerate(valid_symbols):
            row = f"| {sym_i} |"
            for j, sym_j in enumerate(valid_symbols):
                val = float(corr.iloc[i, j])
                row += f" {val:.2f} |"
            lines.append(row)

        lines.append("\n### 포트폴리오 선택 가이드")
        lines.append("- **최대 Sharpe**: 위험 대비 수익 최적. 적극적 투자자")
        lines.append("- **최소 변동성**: 안정성 최우선. 보수적 투자자")
        lines.append("- **Risk Parity**: 리스크 균등 배분. All-Weather 전략")

        return "\n".join(lines)

    # ── 2. Kelly Criterion ──
    async def _kelly(self, kw: dict) -> str:
        symbols = self._parse_symbols(kw)
        if not symbols:
            return "symbol 파라미터가 필요합니다."

        np = _np()
        if not np:
            return "numpy 미설치"

        returns, prices, names = await self._get_returns(symbols)
        if returns is None:
            return "가격 데이터 조회 실패"

        lines = [
            "## Kelly Criterion 최적 비중\n",
            "### Kelly(1956): 장기 복리 성장률 최대화 공식\n",
            "f* = μ / σ² (연속형 근사, Thorp 2006)\n",
        ]

        rf = 0.045

        lines.append("| 종목 | 연수익률 | 변동성 | Full Kelly | Half Kelly | 판정 |")
        lines.append("|------|---------|--------|-----------|-----------|------|")

        for sym in returns.columns:
            daily_ret = returns[sym]
            ann_ret = float(daily_ret.mean() * 252)
            ann_vol = float(daily_ret.std() * np.sqrt(252))
            excess = ann_ret - rf

            # Kelly fraction: f* = (μ - rf) / σ²
            kelly_f = excess / (ann_vol ** 2) if ann_vol > 0 else 0
            half_kelly = kelly_f / 2

            # 판정
            if kelly_f <= 0:
                verdict = "🔴 투자 부적합"
            elif kelly_f > 2.0:
                verdict = "⚠️ 레버리지 시그널"
            elif half_kelly > 0.5:
                verdict = "🟢 강한 매수"
            elif half_kelly > 0.2:
                verdict = "✅ 매수 적합"
            else:
                verdict = "🟡 소규모 배분"

            lines.append(
                f"| {names.get(sym,sym)} ({sym}) | {ann_ret*100:+.1f}% | {ann_vol*100:.1f}% | "
                f"{kelly_f*100:.1f}% | **{half_kelly*100:.1f}%** | {verdict} |"
            )

        lines.append("\n### Kelly 해석 가이드")
        lines.append("- **Full Kelly**: 이론적 최적이나 변동성 극대 → 실전 부적합")
        lines.append("- **Half Kelly**: 성장의 75% 유지하면서 리스크 50% 감소 (Thorp 권장)")
        lines.append("- **Quarter Kelly**: 초보자 또는 불확실성 높을 때")
        lines.append("- Kelly < 0: 해당 자산 **투자하지 말 것** (기대수익 < 무위험)")
        lines.append("- Kelly > 100%: 레버리지 시그널이나, 실전에서는 Max 25~30% 권장")

        return "\n".join(lines)

    # ── 3. 효율적 프론티어 ──
    async def _efficient_frontier(self, kw: dict) -> str:
        symbols = self._parse_symbols(kw)
        if len(symbols) < 2:
            return "최소 2개 이상의 심볼이 필요합니다."

        np = _np()
        if not np:
            return "numpy 미설치"

        returns, prices, names = await self._get_returns(symbols)
        if returns is None:
            return "가격 데이터 조회 실패"

        n = len(returns.columns)
        mean_returns = returns.mean().values * 252
        cov_matrix = returns.cov().values * 252
        rf = 0.045

        # 5000 포트폴리오 시뮬레이션
        results = []
        for _ in range(5000):
            w = np.random.dirichlet(np.ones(n))
            ret = float(np.dot(w, mean_returns))
            vol = float(np.sqrt(np.dot(w.T, np.dot(cov_matrix, w))))
            sharpe = (ret - rf) / vol if vol > 0 else 0
            results.append({"ret": ret, "vol": vol, "sharpe": sharpe, "weights": w})

        # 효율적 프론티어 포인트 (변동성 구간별 최대 수익)
        vol_range = np.linspace(
            min(r["vol"] for r in results),
            max(r["vol"] for r in results),
            10
        )

        lines = [
            "## 효율적 프론티어 (Markowitz, 1952)\n",
            f"### {', '.join(returns.columns)} — 5,000 시뮬레이션\n",
            "### 효율적 프론티어 포인트",
            "| 변동성 | 수익률 | Sharpe | 그래프 |",
            "|--------|--------|--------|--------|",
        ]

        for i in range(len(vol_range) - 1):
            in_range = [r for r in results if vol_range[i] <= r["vol"] < vol_range[i+1]]
            if in_range:
                best = max(in_range, key=lambda x: x["ret"])
                bar_ret = "█" * max(1, int(best["ret"] * 50))
                lines.append(
                    f"| {best['vol']*100:.1f}% | {best['ret']*100:+.1f}% | "
                    f"{best['sharpe']:.2f} | {bar_ret} |"
                )

        # 최적 포인트
        optimal = max(results, key=lambda x: x["sharpe"])
        min_vol_port = min(results, key=lambda x: x["vol"])

        lines.append(f"\n### 핵심 포인트")
        lines.append(f"- ⭐ **최대 Sharpe**: 수익 {optimal['ret']*100:+.1f}%, 변동성 {optimal['vol']*100:.1f}%, SR {optimal['sharpe']:.2f}")
        lines.append(f"- 🛡️ **최소 변동성**: 수익 {min_vol_port['ret']*100:+.1f}%, 변동성 {min_vol_port['vol']*100:.1f}%")

        lines.append(f"\n### ⭐ 최대 Sharpe 비중 상세")
        for i, sym in enumerate(returns.columns):
            w = optimal["weights"][i] * 100
            lines.append(f"- {names.get(sym,sym)} ({sym}): **{w:.1f}%**")

        lines.append("\n### Capital Market Line (CML)")
        lines.append(f"- 무위험 이자율: {rf*100:.1f}% (미국 T-Bill)")
        lines.append("- CML 기울기 = 최대 Sharpe Ratio")
        lines.append("- CML 위의 포인트 = 무위험자산 + 접점 포트폴리오 혼합")

        return "\n".join(lines)

    # ── 전체 분석 ──
    async def _full(self, kw: dict) -> str:
        parts = []
        for fn in [self._optimize, self._kelly, self._efficient_frontier]:
            try:
                parts.append(await fn(kw))
            except Exception as e:
                parts.append(f"[분석 일부 실패: {e}]")
        return "\n\n---\n\n".join(parts)
