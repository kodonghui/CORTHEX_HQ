"""
페어 트레이딩 분석 도구 (Pair Analyzer) — 두 종목 간 상관관계 + 차익거래 기회 탐색.

"삼성전자-SK하이닉스처럼 같이 움직이는 종목을 찾고,
차이가 벌어지면 매매 기회를 포착"합니다.

학술 근거:
  - 통계적 차익거래 (Gatev, Goetzmann & Rouwenhorst, 2006)
  - 공적분 분석 (Engle-Granger Cointegration)
  - 평균 회귀 전략 (Mean Reversion)

사용 방법:
  - action="full"        : 종합 페어 분석 (상관+스프레드+신호)
  - action="correlation"  : 두 종목 상관관계 분석
  - action="spread"       : 스프레드(가격차이) 분석
  - action="signal"       : 매매 신호 (진입/청산 타이밍)
  - action="scan"         : 페어 후보 자동 탐색 (대형주 중)

필요 환경변수: 없음
필요 라이브러리: pykrx, pandas, numpy
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.pair_analyzer")


def _import_pykrx():
    try:
        from pykrx import stock
        return stock
    except ImportError:
        return None


class PairAnalyzerTool(BaseTool):
    """페어 트레이딩 분석 도구 — 상관관계 + 스프레드 + 매매 신호."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_pair,
            "correlation": self._correlation,
            "spread": self._spread_analysis,
            "signal": self._pair_signal,
            "scan": self._pair_scan,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return f"알 수 없는 action: {action}. full, correlation, spread, signal, scan 중 하나."

    # ── 공통: 두 종목 가격 데이터 로드 ────────

    async def _load_pair(self, kwargs: dict) -> tuple:
        stock = _import_pykrx()
        if stock is None:
            return None, None, None, None, "pykrx 필요"

        import pandas as pd

        stock_a = kwargs.get("name_a", "") or kwargs.get("stock_a", "")
        stock_b = kwargs.get("name_b", "") or kwargs.get("stock_b", "")

        # "삼성전자,SK하이닉스" 형태도 지원
        names = kwargs.get("names", "") or kwargs.get("query", "")
        if names and not stock_a:
            parts = [n.strip() for n in str(names).split(",") if n.strip()]
            if len(parts) >= 2:
                stock_a, stock_b = parts[0], parts[1]

        if not stock_a or not stock_b:
            return None, None, None, None, (
                "두 종목을 입력해주세요.\n"
                "예: names='삼성전자,SK하이닉스' 또는 name_a='삼성전자', name_b='SK하이닉스'"
            )

        days = int(kwargs.get("days", 365))
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        ticker_a = await self._resolve_ticker(stock, stock_a)
        ticker_b = await self._resolve_ticker(stock, stock_b)
        if not ticker_a:
            return None, None, None, None, f"'{stock_a}' 종목을 찾을 수 없습니다."
        if not ticker_b:
            return None, None, None, None, f"'{stock_b}' 종목을 찾을 수 없습니다."

        try:
            df_a = await asyncio.to_thread(stock.get_market_ohlcv_by_date, start, end, ticker_a)
            df_b = await asyncio.to_thread(stock.get_market_ohlcv_by_date, start, end, ticker_b)
        except Exception as e:
            return None, None, None, None, f"데이터 조회 실패: {e}"

        if df_a.empty or df_b.empty or len(df_a) < 30 or len(df_b) < 30:
            return None, None, None, None, "데이터 부족 (최소 30일)"

        # 공통 날짜만
        common = df_a.index.intersection(df_b.index)
        prices_a = df_a.loc[common, "종가"]
        prices_b = df_b.loc[common, "종가"]

        return stock_a, stock_b, prices_a, prices_b, None

    async def _resolve_ticker(self, stock, name: str) -> str | None:
        try:
            today = datetime.now().strftime("%Y%m%d")
            tickers = await asyncio.to_thread(stock.get_market_ticker_list, today, market="ALL")
            for t in tickers:
                if await asyncio.to_thread(stock.get_market_ticker_name, t) == name:
                    return t
        except Exception:
            pass
        return None

    # ── 1. 종합 페어 분석 ────────────────────

    async def _full_pair(self, kwargs: dict) -> str:
        name_a, name_b, pa, pb, err = await self._load_pair(kwargs)
        if err:
            return err

        # 상관관계
        corr = pa.corr(pb)

        # 정규화 가격 비율 (스프레드)
        ratio = pa / pb
        spread = (ratio - ratio.mean()) / ratio.std()

        # 반감기 (Mean Reversion Half-Life)
        half_life = self._calc_half_life(spread)

        # 현재 스프레드 상태
        current_z = spread.iloc[-1]

        # 수익률 상관관계
        ret_a = pa.pct_change().dropna()
        ret_b = pb.pct_change().dropna()
        common_idx = ret_a.index.intersection(ret_b.index)
        ret_corr = ret_a[common_idx].corr(ret_b[common_idx])

        results = [f"{'='*55}"]
        results.append(f"📊 페어 분석: {name_a} ↔ {name_b}")
        results.append(f"{'='*55}\n")

        results.append(f"▸ 가격 상관관계: {corr:.3f} ({'강한 양의 상관' if corr > 0.7 else '약한 상관' if corr > 0.3 else '무상관'})")
        results.append(f"▸ 수익률 상관관계: {ret_corr:.3f}")
        results.append(f"▸ 평균 회귀 반감기: {half_life:.0f}일" if half_life > 0 else "▸ 평균 회귀 반감기: N/A")

        results.append(f"\n▸ 스프레드 (Z-score):")
        results.append(f"  현재: {current_z:.2f}")
        results.append(f"  평균: 0.00 / 표준편차 ±1.00")
        results.append(f"  최대: {spread.max():.2f} / 최소: {spread.min():.2f}")

        # 매매 신호
        if current_z > 2.0:
            signal = "🔴 강한 매도 A / 매수 B (스프레드 극단 확대)"
        elif current_z > 1.0:
            signal = "🟡 매도 A / 매수 B (스프레드 확대)"
        elif current_z < -2.0:
            signal = "🔴 강한 매수 A / 매도 B (스프레드 극단 축소)"
        elif current_z < -1.0:
            signal = "🟡 매수 A / 매도 B (스프레드 축소)"
        else:
            signal = "⚪ 중립 (스프레드 정상 범위)"

        results.append(f"\n▸ 페어 트레이딩 신호: {signal}")
        results.append(f"\n▸ 현재가:")
        results.append(f"  {name_a}: {int(pa.iloc[-1]):,}원")
        results.append(f"  {name_b}: {int(pb.iloc[-1]):,}원")
        results.append(f"  비율 (A/B): {ratio.iloc[-1]:.4f}")

        raw_text = "\n".join(results)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 통계적 차익거래(Statistical Arbitrage) 전문가입니다. "
                "페어 트레이딩 분석 결과를 해석하고, 구체적인 진입/청산 전략을 제안하세요. "
                "Gatev et al.(2006) 연구를 참고하세요. 한국어."
            ),
            user_prompt=raw_text,
            caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
        )
        return f"{raw_text}\n\n{'='*55}\n🎓 교수급 페어 분석\n{'='*55}\n{analysis}"

    # ── 2. 상관관계 ──────────────────────────

    async def _correlation(self, kwargs: dict) -> str:
        name_a, name_b, pa, pb, err = await self._load_pair(kwargs)
        if err:
            return err

        corr = pa.corr(pb)
        ret_a = pa.pct_change().dropna()
        ret_b = pb.pct_change().dropna()
        common = ret_a.index.intersection(ret_b.index)
        ret_corr = ret_a[common].corr(ret_b[common])

        # 롤링 상관관계 (60일)
        import pandas as pd
        rolling_corr = ret_a[common].rolling(60).corr(ret_b[common]).dropna()

        results = [f"📊 상관관계: {name_a} ↔ {name_b}"]
        results.append(f"\n가격 상관관계: {corr:.3f}")
        results.append(f"수익률 상관관계: {ret_corr:.3f}")
        if not rolling_corr.empty:
            results.append(f"60일 롤링 상관 (현재): {rolling_corr.iloc[-1]:.3f}")
            results.append(f"60일 롤링 상관 (평균): {rolling_corr.mean():.3f}")
            results.append(f"60일 롤링 상관 (최저): {rolling_corr.min():.3f}")

        if corr > 0.8:
            results.append(f"\n→ 매우 높은 상관관계 — 페어 트레이딩에 적합")
        elif corr > 0.5:
            results.append(f"\n→ 중간 상관관계 — 조건부 페어 가능")
        else:
            results.append(f"\n→ 낮은 상관관계 — 페어 트레이딩 부적합")

        return "\n".join(results)

    # ── 3. 스프레드 분석 ─────────────────────

    async def _spread_analysis(self, kwargs: dict) -> str:
        name_a, name_b, pa, pb, err = await self._load_pair(kwargs)
        if err:
            return err

        ratio = pa / pb
        spread = (ratio - ratio.mean()) / ratio.std()
        half_life = self._calc_half_life(spread)

        results = [f"📊 스프레드 분석: {name_a}/{name_b}"]
        results.append(f"\n비율 (A/B):")
        results.append(f"  현재: {ratio.iloc[-1]:.4f}")
        results.append(f"  평균: {ratio.mean():.4f}")
        results.append(f"  ±1σ: {ratio.mean()-ratio.std():.4f} ~ {ratio.mean()+ratio.std():.4f}")
        results.append(f"\nZ-score: {spread.iloc[-1]:.2f}")
        results.append(f"반감기: {half_life:.0f}일" if half_life > 0 else "반감기: N/A")

        # 스프레드 이력 (±2σ 이탈 횟수)
        extreme = (spread.abs() > 2).sum()
        results.append(f"\n±2σ 이탈 횟수: {extreme}회 (전체 {len(spread)}일 중)")

        return "\n".join(results)

    # ── 4. 매매 신호 ─────────────────────────

    async def _pair_signal(self, kwargs: dict) -> str:
        name_a, name_b, pa, pb, err = await self._load_pair(kwargs)
        if err:
            return err

        ratio = pa / pb
        spread = (ratio - ratio.mean()) / ratio.std()
        z = spread.iloc[-1]

        results = [f"📊 페어 트레이딩 신호: {name_a} ↔ {name_b}"]
        results.append(f"\n현재 Z-score: {z:.2f}")

        if z > 2.0:
            results.append(f"🔴 강한 신호: {name_a} 매도 + {name_b} 매수")
            results.append(f"  (스프레드가 +2σ 초과 — 평균으로 회귀할 가능성 높음)")
        elif z > 1.0:
            results.append(f"🟡 약한 신호: {name_a} 매도 + {name_b} 매수 고려")
        elif z < -2.0:
            results.append(f"🔴 강한 신호: {name_a} 매수 + {name_b} 매도")
            results.append(f"  (스프레드가 -2σ 미만 — 평균으로 회귀할 가능성 높음)")
        elif z < -1.0:
            results.append(f"🟡 약한 신호: {name_a} 매수 + {name_b} 매도 고려")
        else:
            results.append(f"⚪ 중립 — 포지션 없음 (스프레드 정상 범위)")

        results.append(f"\n진입 기준: Z > +2.0 or Z < -2.0")
        results.append(f"청산 기준: Z가 0 복귀")
        results.append(f"손절 기준: Z > +3.0 or Z < -3.0")

        return "\n".join(results)

    # ── 5. 페어 후보 자동 탐색 ───────────────

    async def _pair_scan(self, kwargs: dict) -> str:
        stock = _import_pykrx()
        if stock is None:
            return "pykrx 필요"

        import pandas as pd
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=180)).strftime("%Y%m%d")

        # 시총 상위 20종목
        try:
            cap_df = await asyncio.to_thread(stock.get_market_cap_by_ticker, end, market="KOSPI")
            top = cap_df.nlargest(20, "시가총액").index.tolist()
        except Exception:
            return "시가총액 데이터 조회 실패"

        prices = {}
        names = {}
        for t in top:
            try:
                nm = await asyncio.to_thread(stock.get_market_ticker_name, t)
                ohlcv = await asyncio.to_thread(stock.get_market_ohlcv_by_date, start, end, t)
                if not ohlcv.empty and len(ohlcv) > 30:
                    prices[t] = ohlcv["종가"]
                    names[t] = nm
            except Exception:
                continue

        if len(prices) < 2:
            return "충분한 종목 데이터를 가져올 수 없습니다."

        price_df = pd.DataFrame(prices).dropna()
        corr_matrix = price_df.corr()

        # 상관관계 높은 페어 찾기
        pairs = []
        tickers = list(prices.keys())
        for i in range(len(tickers)):
            for j in range(i + 1, len(tickers)):
                c = corr_matrix.loc[tickers[i], tickers[j]]
                if c > 0.7:
                    pairs.append((names[tickers[i]], names[tickers[j]], c))

        pairs.sort(key=lambda x: x[2], reverse=True)

        results = [f"📊 페어 트레이딩 후보 탐색 (KOSPI 대형주)"]
        results.append(f"\n상관관계 0.7 이상 페어 ({len(pairs)}쌍 발견):")
        results.append(f"\n{'종목 A':>10} ↔ {'종목 B':>10} | 상관계수")
        results.append("-" * 40)
        for a, b, c in pairs[:15]:
            results.append(f"  {a:>8} ↔ {b:>8} | {c:.3f}")

        if not pairs:
            results.append("  (상관관계 0.7 이상 페어 없음)")

        return "\n".join(results)

    # ── 유틸 ─────────────────────────────────

    @staticmethod
    def _calc_half_life(spread) -> float:
        """평균 회귀 반감기 (Ornstein-Uhlenbeck 모델)."""
        try:
            lag = spread.shift(1).dropna()
            delta = spread.diff().dropna()
            common = lag.index.intersection(delta.index)
            if len(common) < 10:
                return -1
            x = lag[common].values
            y = delta[common].values
            # OLS: delta_S = theta * (mu - S) + epsilon
            # 간단히 delta_S = beta * S_lag + alpha
            beta = np.cov(x, y)[0, 1] / np.var(x) if np.var(x) > 0 else 0
            if beta >= 0:
                return -1  # 평균 회귀 아님
            return -np.log(2) / beta
        except Exception:
            return -1
