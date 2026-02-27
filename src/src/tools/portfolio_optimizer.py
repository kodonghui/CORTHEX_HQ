"""
포트폴리오 최적화 도구 (Portfolio Optimizer) — 마코위츠 현대포트폴리오이론.

"어떤 종목에 얼마씩 넣어야 위험 대비 수익이 최대인가?"를 수학적으로 계산합니다.

학술 근거:
  - Harry Markowitz, "Portfolio Selection" (1952, 노벨경제학상)
  - 효율적 프론티어 (Efficient Frontier)
  - 샤프 비율 (William Sharpe, 1966)

사용 방법:
  - action="optimize"      : 최적 비중 계산 (최대 샤프 비율)
  - action="min_risk"      : 최소 위험 포트폴리오
  - action="equal_weight"  : 동일 비중 대비 비교
  - action="efficient_frontier" : 효율적 프론티어 5개 포인트
  - action="full"          : 종합 분석 (위 전부 포함)

필요 환경변수: 없음 (pykrx 무료)
필요 라이브러리: pykrx, pandas, numpy, scipy
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.portfolio_optimizer")


def _import_pykrx():
    try:
        from pykrx import stock
        return stock
    except ImportError:
        return None


class PortfolioOptimizerTool(BaseTool):
    """마코위츠 포트폴리오 최적화 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_analysis,
            "optimize": self._optimize,
            "min_risk": self._min_risk,
            "equal_weight": self._equal_weight,
            "efficient_frontier": self._efficient_frontier,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return f"알 수 없는 action: {action}. full, optimize, min_risk, equal_weight, efficient_frontier 중 하나."

    # ── 공통: 다종목 수익률 데이터 로드 ─────────

    async def _load_returns(self, kwargs: dict) -> tuple:
        """여러 종목의 일간 수익률 DataFrame을 로드합니다."""
        stock = _import_pykrx()
        if stock is None:
            return None, None, "pykrx 라이브러리가 필요합니다.\npip install pykrx"

        # tickers: 쉼표 구분 문자열 또는 리스트
        tickers_raw = kwargs.get("tickers", "") or kwargs.get("names", "") or kwargs.get("query", "")
        if not tickers_raw:
            return None, None, "종목 목록을 입력해주세요. 예: names='삼성전자,카카오,현대차'"

        if isinstance(tickers_raw, str):
            names = [n.strip() for n in tickers_raw.split(",") if n.strip()]
        else:
            names = list(tickers_raw)

        if len(names) < 2:
            return None, None, "최소 2개 이상의 종목이 필요합니다."
        if len(names) > 20:
            return None, None, "최대 20개 종목까지 가능합니다."

        days = int(kwargs.get("days", 365))
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        import pandas as pd
        prices = {}
        resolved_names = {}

        for name in names:
            ticker = await self._resolve_ticker(stock, name)
            if not ticker:
                return None, None, f"'{name}' 종목을 찾을 수 없습니다."
            try:
                df = await asyncio.to_thread(stock.get_market_ohlcv_by_date, start, end, ticker)
                if df.empty or len(df) < 20:
                    return None, None, f"'{name}' 데이터가 부족합니다."
                prices[name] = df["종가"]
                resolved_names[name] = ticker
            except Exception as e:
                return None, None, f"'{name}' 데이터 조회 실패: {e}"

        price_df = pd.DataFrame(prices).dropna()
        returns_df = price_df.pct_change().dropna()

        if len(returns_df) < 20:
            return None, None, "수익률 데이터가 부족합니다 (최소 20일 필요)."

        return names, returns_df, None

    async def _resolve_ticker(self, stock, name: str) -> str | None:
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

    @staticmethod
    def _fmt(val, decimals=1) -> str:
        if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
            return "N/A"
        return f"{val:.{decimals}f}"

    # ── 포트폴리오 계산 엔진 ─────────────────

    @staticmethod
    def _portfolio_stats(weights, mean_returns, cov_matrix) -> tuple:
        """(연간 수익률, 연간 변동성, 샤프비율) 계산."""
        port_return = np.sum(mean_returns * weights) * 252
        port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix * 252, weights)))
        sharpe = port_return / port_vol if port_vol > 0 else 0
        return port_return, port_vol, sharpe

    def _max_sharpe(self, mean_returns, cov_matrix, n: int) -> np.ndarray:
        """최대 샤프 비율 포트폴리오 (몬테카를로 시뮬레이션)."""
        best_sharpe = -999
        best_weights = np.ones(n) / n
        np.random.seed(42)

        for _ in range(10000):
            w = np.random.random(n)
            w /= w.sum()
            _, _, sharpe = self._portfolio_stats(w, mean_returns, cov_matrix)
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_weights = w
        return best_weights

    def _min_variance(self, mean_returns, cov_matrix, n: int) -> np.ndarray:
        """최소 분산 포트폴리오."""
        best_vol = 999
        best_weights = np.ones(n) / n
        np.random.seed(42)

        for _ in range(10000):
            w = np.random.random(n)
            w /= w.sum()
            _, vol, _ = self._portfolio_stats(w, mean_returns, cov_matrix)
            if vol < best_vol:
                best_vol = vol
                best_weights = w
        return best_weights

    # ── 1. 종합 분석 ────────────────────────

    async def _full_analysis(self, kwargs: dict) -> str:
        names, returns_df, err = await self._load_returns(kwargs)
        if err:
            return err

        mean_ret = returns_df.mean()
        cov = returns_df.cov()
        n = len(names)

        # 최적 비중
        opt_w = self._max_sharpe(mean_ret.values, cov.values, n)
        opt_ret, opt_vol, opt_sharpe = self._portfolio_stats(opt_w, mean_ret.values, cov.values)

        # 최소 위험
        min_w = self._min_variance(mean_ret.values, cov.values, n)
        min_ret, min_vol, min_sharpe = self._portfolio_stats(min_w, mean_ret.values, cov.values)

        # 동일 비중
        eq_w = np.ones(n) / n
        eq_ret, eq_vol, eq_sharpe = self._portfolio_stats(eq_w, mean_ret.values, cov.values)

        # 개별 종목 수익률
        ann_returns = mean_ret * 252
        ann_vols = returns_df.std() * np.sqrt(252)

        results = [f"{'='*55}"]
        results.append(f"📊 포트폴리오 최적화 ({', '.join(names)})")
        results.append(f"{'='*55}\n")

        results.append("▸ 개별 종목 성과 (연간):")
        for nm in names:
            results.append(f"  {nm}: 수익률 {ann_returns[nm]*100:+.1f}%, 변동성 {ann_vols[nm]*100:.1f}%")

        results.append(f"\n▸ 상관관계 매트릭스:")
        corr = returns_df.corr()
        header = "         " + "  ".join(f"{nm[:4]:>6}" for nm in names)
        results.append(header)
        for i, nm in enumerate(names):
            row = f"  {nm[:6]:>6} " + "  ".join(f"{corr.iloc[i, j]:6.2f}" for j in range(n))
            results.append(row)

        results.append(f"\n{'─'*55}")
        results.append("▸ 최적 포트폴리오 (최대 샤프):")
        for i, nm in enumerate(names):
            results.append(f"  {nm}: {opt_w[i]*100:.1f}%")
        results.append(f"  → 예상 수익률: {opt_ret*100:+.1f}%, 변동성: {opt_vol*100:.1f}%, 샤프: {opt_sharpe:.2f}")

        results.append(f"\n▸ 최소 위험 포트폴리오:")
        for i, nm in enumerate(names):
            results.append(f"  {nm}: {min_w[i]*100:.1f}%")
        results.append(f"  → 예상 수익률: {min_ret*100:+.1f}%, 변동성: {min_vol*100:.1f}%, 샤프: {min_sharpe:.2f}")

        results.append(f"\n▸ 동일 비중 (벤치마크):")
        results.append(f"  → 예상 수익률: {eq_ret*100:+.1f}%, 변동성: {eq_vol*100:.1f}%, 샤프: {eq_sharpe:.2f}")

        raw_text = "\n".join(results)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 Harry Markowitz 교수 수준의 포트폴리오 이론 전문가입니다. "
                "최적화 결과를 해석하고, 투자자에게 실행 가능한 배분 전략을 제안하세요. "
                "상관관계와 분산 효과를 강조하세요. 한국어로 답변."
            ),
            user_prompt=raw_text,
            caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
        )
        return f"{raw_text}\n\n{'='*55}\n🎓 교수급 종합 분석\n{'='*55}\n{analysis}"

    # ── 2. 최적 비중 ────────────────────────

    async def _optimize(self, kwargs: dict) -> str:
        names, returns_df, err = await self._load_returns(kwargs)
        if err:
            return err

        mean_ret = returns_df.mean()
        cov = returns_df.cov()
        n = len(names)
        opt_w = self._max_sharpe(mean_ret.values, cov.values, n)
        opt_ret, opt_vol, opt_sharpe = self._portfolio_stats(opt_w, mean_ret.values, cov.values)

        results = [f"📊 최적 포트폴리오 비중 (최대 샤프 비율)"]
        for i, nm in enumerate(names):
            results.append(f"  {nm}: {opt_w[i]*100:.1f}%")
        results.append(f"\n예상 연간 수익률: {opt_ret*100:+.1f}%")
        results.append(f"예상 연간 변동성: {opt_vol*100:.1f}%")
        results.append(f"샤프 비율: {opt_sharpe:.2f}")
        return "\n".join(results)

    # ── 3. 최소 위험 ────────────────────────

    async def _min_risk(self, kwargs: dict) -> str:
        names, returns_df, err = await self._load_returns(kwargs)
        if err:
            return err

        mean_ret = returns_df.mean()
        cov = returns_df.cov()
        n = len(names)
        min_w = self._min_variance(mean_ret.values, cov.values, n)
        min_ret, min_vol, min_sharpe = self._portfolio_stats(min_w, mean_ret.values, cov.values)

        results = [f"📊 최소 위험 포트폴리오"]
        for i, nm in enumerate(names):
            results.append(f"  {nm}: {min_w[i]*100:.1f}%")
        results.append(f"\n예상 연간 수익률: {min_ret*100:+.1f}%")
        results.append(f"예상 연간 변동성: {min_vol*100:.1f}%")
        results.append(f"샤프 비율: {min_sharpe:.2f}")
        return "\n".join(results)

    # ── 4. 동일 비중 비교 ───────────────────

    async def _equal_weight(self, kwargs: dict) -> str:
        names, returns_df, err = await self._load_returns(kwargs)
        if err:
            return err

        mean_ret = returns_df.mean()
        cov = returns_df.cov()
        n = len(names)
        eq_w = np.ones(n) / n
        eq_ret, eq_vol, eq_sharpe = self._portfolio_stats(eq_w, mean_ret.values, cov.values)

        opt_w = self._max_sharpe(mean_ret.values, cov.values, n)
        opt_ret, opt_vol, opt_sharpe = self._portfolio_stats(opt_w, mean_ret.values, cov.values)

        results = [f"📊 동일 비중 vs 최적 비중 비교"]
        results.append(f"\n동일 비중 ({100/n:.0f}%씩):")
        results.append(f"  수익률: {eq_ret*100:+.1f}%, 변동성: {eq_vol*100:.1f}%, 샤프: {eq_sharpe:.2f}")
        results.append(f"\n최적 비중:")
        for i, nm in enumerate(names):
            results.append(f"  {nm}: {opt_w[i]*100:.1f}%")
        results.append(f"  수익률: {opt_ret*100:+.1f}%, 변동성: {opt_vol*100:.1f}%, 샤프: {opt_sharpe:.2f}")
        diff = (opt_sharpe - eq_sharpe) / eq_sharpe * 100 if eq_sharpe != 0 else 0
        results.append(f"\n→ 최적화로 샤프 비율 {diff:+.1f}% 개선")
        return "\n".join(results)

    # ── 5. 효율적 프론티어 ──────────────────

    async def _efficient_frontier(self, kwargs: dict) -> str:
        names, returns_df, err = await self._load_returns(kwargs)
        if err:
            return err

        mean_ret = returns_df.mean().values
        cov = returns_df.cov().values
        n = len(names)

        # 타겟 수익률 범위에서 5개 포인트
        min_w = self._min_variance(mean_ret, cov, n)
        min_ret, _, _ = self._portfolio_stats(min_w, mean_ret, cov)
        opt_w = self._max_sharpe(mean_ret, cov, n)
        max_ret, _, _ = self._portfolio_stats(opt_w, mean_ret, cov)

        targets = np.linspace(min_ret, max_ret * 1.2, 5)
        results = [f"📊 효율적 프론티어 (5개 포인트)"]
        results.append(f"{'수익률':>8} | {'변동성':>8} | {'샤프':>6} | 비중 배분")
        results.append("-" * 60)

        np.random.seed(42)
        for target in targets:
            best_vol = 999
            best_w = np.ones(n) / n
            for _ in range(5000):
                w = np.random.random(n)
                w /= w.sum()
                ret, vol, _ = self._portfolio_stats(w, mean_ret, cov)
                if abs(ret - target) < 0.02 and vol < best_vol:
                    best_vol = vol
                    best_w = w

            ret, vol, sharpe = self._portfolio_stats(best_w, mean_ret, cov)
            alloc = ", ".join(f"{names[i][:3]}:{best_w[i]*100:.0f}%" for i in range(n))
            results.append(f"  {ret*100:+5.1f}%  |  {vol*100:5.1f}%  | {sharpe:5.2f} | {alloc}")

        return "\n".join(results)
