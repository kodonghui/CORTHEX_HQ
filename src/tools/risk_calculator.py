"""
리스크 계산 도구 (Risk Calculator) — VaR, MDD, 변동성, 샤프비율 등 위험 측정.

"최악의 경우 얼마까지 잃을 수 있나?"를 정량적으로 계산합니다.

학술 근거:
  - JP Morgan RiskMetrics (1996)
  - VaR (Value at Risk) — Philippe Jorion
  - Conditional VaR (CVaR/Expected Shortfall)
  - Maximum Drawdown, Sharpe Ratio, Sortino Ratio

사용 방법:
  - action="full"       : 전체 리스크 종합 (VaR+MDD+비율)
  - action="var"        : VaR (일일/월간 최대예상손실)
  - action="drawdown"   : 최대낙폭(MDD) + 낙폭 이력
  - action="volatility" : 변동성 분석 (역사적/실현/내재)
  - action="ratios"     : 위험조정수익률 (샤프/소르티노/칼마)
  - action="stress"     : 스트레스 테스트 (과거 위기 시나리오)

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

logger = logging.getLogger("corthex.tools.risk_calculator")


def _import_pykrx():
    try:
        from pykrx import stock
        return stock
    except ImportError:
        return None


class RiskCalculatorTool(BaseTool):
    """리스크 측정 도구 — VaR, MDD, 변동성, 위험조정수익률."""

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        if query and not kwargs.get("name") and not kwargs.get("ticker"):
            kwargs["name"] = query

        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_risk,
            "var": self._var_analysis,
            "drawdown": self._drawdown_analysis,
            "volatility": self._volatility_analysis,
            "ratios": self._ratio_analysis,
            "stress": self._stress_test,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return f"알 수 없는 action: {action}. full, var, drawdown, volatility, ratios, stress 중 하나."

    # ── 공통 데이터 로드 ─────────────────────

    async def _load_data(self, kwargs: dict) -> tuple:
        stock = _import_pykrx()
        if stock is None:
            return None, None, None, "pykrx 라이브러리가 필요합니다."

        ticker = kwargs.get("ticker", "")
        name = kwargs.get("name", "")
        if not ticker and not name:
            return None, None, None, "종목코드(ticker) 또는 종목명(name)을 입력해주세요."

        if name and not ticker:
            ticker = await self._resolve_ticker(stock, name)
            if not ticker:
                return None, None, None, f"'{name}' 종목을 찾을 수 없습니다."

        stock_name = await self._get_stock_name(stock, ticker)
        days = int(kwargs.get("days", 500))
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        try:
            df = await asyncio.to_thread(stock.get_market_ohlcv_by_date, start, end, ticker)
        except Exception as e:
            return None, None, None, f"데이터 조회 실패: {e}"

        if df.empty or len(df) < 30:
            return None, None, None, f"'{stock_name}' 데이터가 부족합니다 (최소 30일)."

        returns = df["종가"].pct_change().dropna()
        return stock_name, df, returns, None

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

    async def _get_stock_name(self, stock, ticker: str) -> str:
        try:
            return await asyncio.to_thread(stock.get_market_ticker_name, ticker)
        except Exception:
            return ticker

    @staticmethod
    def _fmt(val, decimals=1) -> str:
        if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
            return "N/A"
        if abs(val) >= 1000:
            return f"{val:,.0f}"
        return f"{val:.{decimals}f}"

    # ── 1. 전체 리스크 종합 ──────────────────

    async def _full_risk(self, kwargs: dict) -> str:
        name, df, returns, err = await self._load_data(kwargs)
        if err:
            return err

        current_price = int(df["종가"].iloc[-1])
        investment = int(kwargs.get("investment", 10_000_000))  # 기본 1000만원

        # VaR 계산
        var_95 = np.percentile(returns, 5)
        var_99 = np.percentile(returns, 1)
        cvar_95 = returns[returns <= var_95].mean()

        # MDD 계산
        prices = df["종가"]
        cummax = prices.cummax()
        drawdown = (prices - cummax) / cummax
        mdd = drawdown.min()
        mdd_date = drawdown.idxmin()

        # 변동성
        daily_vol = returns.std()
        annual_vol = daily_vol * np.sqrt(252)

        # 수익률 비율
        annual_return = returns.mean() * 252
        rf = 0.035  # 무위험 수익률 3.5%
        sharpe = (annual_return - rf) / annual_vol if annual_vol > 0 else 0
        downside = returns[returns < 0].std() * np.sqrt(252)
        sortino = (annual_return - rf) / downside if downside > 0 else 0
        calmar = annual_return / abs(mdd) if mdd != 0 else 0

        results = [f"{'='*55}"]
        results.append(f"📊 {name} 종합 리스크 분석")
        results.append(f"{'='*55}")
        results.append(f"현재가: {current_price:,}원 / 투자금: {investment:,}원\n")

        results.append("▸ VaR (최대예상손실):")
        results.append(f"  일일 VaR 95%: {var_95*100:.2f}% (약 {int(investment * abs(var_95)):,}원)")
        results.append(f"  일일 VaR 99%: {var_99*100:.2f}% (약 {int(investment * abs(var_99)):,}원)")
        results.append(f"  CVaR 95% (평균 꼬리손실): {cvar_95*100:.2f}%")

        results.append(f"\n▸ 최대낙폭 (MDD):")
        results.append(f"  MDD: {mdd*100:.1f}% (발생일: {mdd_date.strftime('%Y-%m-%d') if hasattr(mdd_date, 'strftime') else mdd_date})")
        results.append(f"  투자금 {investment:,}원 기준 최대 손실: {int(investment * abs(mdd)):,}원")

        results.append(f"\n▸ 변동성:")
        results.append(f"  일간 변동성: {daily_vol*100:.2f}%")
        results.append(f"  연간 변동성: {annual_vol*100:.1f}%")

        results.append(f"\n▸ 위험조정수익률:")
        results.append(f"  연간 수익률: {annual_return*100:+.1f}%")
        results.append(f"  샤프 비율: {sharpe:.2f} ({'우수' if sharpe > 1 else '양호' if sharpe > 0.5 else '부진'})")
        results.append(f"  소르티노 비율: {sortino:.2f}")
        results.append(f"  칼마 비율: {calmar:.2f}")

        # 위험 등급
        if annual_vol < 0.2:
            grade = "🟢 낮음 (보수적 투자 적합)"
        elif annual_vol < 0.35:
            grade = "🟡 중간 (일반 투자자)"
        else:
            grade = "🔴 높음 (고위험 감수 가능자만)"
        results.append(f"\n▸ 위험 등급: {grade}")

        raw_text = "\n".join(results)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 JP Morgan RiskMetrics 수준의 리스크 관리 전문가입니다. "
                "VaR, MDD, 변동성, 위험조정수익률을 종합 해석하고 "
                "투자자의 위험 관리 전략을 구체적으로 제안하세요. 한국어로 답변."
            ),
            user_prompt=raw_text,
            caller_model=kwargs.get("_caller_model"),
        )
        return f"{raw_text}\n\n{'='*55}\n🎓 교수급 리스크 분석\n{'='*55}\n{analysis}"

    # ── 2. VaR 분석 ──────────────────────────

    async def _var_analysis(self, kwargs: dict) -> str:
        name, df, returns, err = await self._load_data(kwargs)
        if err:
            return err

        investment = int(kwargs.get("investment", 10_000_000))

        var_90 = np.percentile(returns, 10)
        var_95 = np.percentile(returns, 5)
        var_99 = np.percentile(returns, 1)
        cvar_95 = returns[returns <= var_95].mean()

        # 월간 VaR (√21 스케일링)
        monthly_var_95 = var_95 * np.sqrt(21)

        results = [f"📊 {name} VaR (Value at Risk) 분석"]
        results.append(f"투자금: {investment:,}원\n")
        results.append("일일 VaR:")
        results.append(f"  90% 신뢰도: {var_90*100:.2f}% (약 {int(investment*abs(var_90)):,}원)")
        results.append(f"  95% 신뢰도: {var_95*100:.2f}% (약 {int(investment*abs(var_95)):,}원)")
        results.append(f"  99% 신뢰도: {var_99*100:.2f}% (약 {int(investment*abs(var_99)):,}원)")
        results.append(f"\nCVaR 95% (Expected Shortfall): {cvar_95*100:.2f}%")
        results.append(f"  → 95% VaR를 넘는 날의 평균 손실: {int(investment*abs(cvar_95)):,}원")
        results.append(f"\n월간 VaR 95%: {monthly_var_95*100:.1f}% (약 {int(investment*abs(monthly_var_95)):,}원)")
        results.append(f"\n해석: '100거래일 중 5일은 {int(investment*abs(var_95)):,}원 이상 손실 가능'")
        return "\n".join(results)

    # ── 3. 최대낙폭 분석 ─────────────────────

    async def _drawdown_analysis(self, kwargs: dict) -> str:
        name, df, returns, err = await self._load_data(kwargs)
        if err:
            return err

        prices = df["종가"]
        cummax = prices.cummax()
        drawdown = (prices - cummax) / cummax

        mdd = drawdown.min()
        mdd_date = drawdown.idxmin()

        # 낙폭 이력 (10% 이상)
        in_dd = False
        dd_list = []
        dd_start = None

        for date, dd in drawdown.items():
            if dd < -0.10 and not in_dd:
                in_dd = True
                dd_start = date
            elif dd > -0.05 and in_dd:
                in_dd = False
                min_dd = drawdown[dd_start:date].min()
                dd_list.append((dd_start, date, min_dd))

        results = [f"📊 {name} 최대낙폭 (MDD) 분석"]
        results.append(f"전체 MDD: {mdd*100:.1f}% ({mdd_date.strftime('%Y-%m-%d') if hasattr(mdd_date, 'strftime') else mdd_date})")
        results.append(f"\n현재 낙폭: {drawdown.iloc[-1]*100:.1f}%")

        if dd_list:
            results.append(f"\n10% 이상 낙폭 이력:")
            for s, e, d in dd_list[-5:]:  # 최근 5건
                s_str = s.strftime('%Y-%m-%d') if hasattr(s, 'strftime') else str(s)
                e_str = e.strftime('%Y-%m-%d') if hasattr(e, 'strftime') else str(e)
                results.append(f"  {s_str} ~ {e_str}: {d*100:.1f}%")

        # 회복 시간
        if mdd < -0.10:
            peak_date = cummax[:mdd_date].idxmax() if hasattr(cummax[:mdd_date], 'idxmax') else None
            recovery = prices[mdd_date:][prices[mdd_date:] >= cummax[mdd_date]]
            if not recovery.empty:
                rec_date = recovery.index[0]
                rec_days = (rec_date - mdd_date).days if hasattr(rec_date, '__sub__') else "N/A"
                results.append(f"\nMDD 회복 소요: {rec_days}일")
            else:
                results.append(f"\nMDD 아직 미회복")

        return "\n".join(results)

    # ── 4. 변동성 분석 ───────────────────────

    async def _volatility_analysis(self, kwargs: dict) -> str:
        name, df, returns, err = await self._load_data(kwargs)
        if err:
            return err

        daily_vol = returns.std()
        annual_vol = daily_vol * np.sqrt(252)

        # 롤링 변동성 (20일, 60일)
        vol_20 = returns.rolling(20).std().iloc[-1] * np.sqrt(252) if len(returns) >= 20 else None
        vol_60 = returns.rolling(60).std().iloc[-1] * np.sqrt(252) if len(returns) >= 60 else None

        # 첨도/왜도
        skew = returns.skew()
        kurt = returns.kurtosis()

        results = [f"📊 {name} 변동성 분석"]
        results.append(f"\n일간 변동성: {daily_vol*100:.2f}%")
        results.append(f"연간 변동성: {annual_vol*100:.1f}%")
        if vol_20:
            results.append(f"20일 롤링 변동성: {vol_20*100:.1f}%")
        if vol_60:
            results.append(f"60일 롤링 변동성: {vol_60*100:.1f}%")

        results.append(f"\n수익률 분포:")
        results.append(f"  왜도(Skewness): {skew:.2f} ({'좌편향(하락 위험↑)' if skew < -0.5 else '우편향(상승 유리)' if skew > 0.5 else '대칭'})")
        results.append(f"  첨도(Kurtosis): {kurt:.2f} ({'꼬리 위험 높음(극단적 변동↑)' if kurt > 3 else '정상'})")

        if vol_20 and vol_60:
            if vol_20 > vol_60 * 1.3:
                results.append(f"\n⚠️ 단기 변동성이 장기 대비 급등 → 주의 필요")
            elif vol_20 < vol_60 * 0.7:
                results.append(f"\n📌 단기 변동성 축소 → 큰 움직임 대비")

        return "\n".join(results)

    # ── 5. 위험조정수익률 ────────────────────

    async def _ratio_analysis(self, kwargs: dict) -> str:
        name, df, returns, err = await self._load_data(kwargs)
        if err:
            return err

        rf = float(kwargs.get("rf", 0.035))  # 무위험 수익률
        annual_return = returns.mean() * 252
        annual_vol = returns.std() * np.sqrt(252)
        downside_vol = returns[returns < 0].std() * np.sqrt(252)
        mdd = ((df["종가"] - df["종가"].cummax()) / df["종가"].cummax()).min()

        sharpe = (annual_return - rf) / annual_vol if annual_vol > 0 else 0
        sortino = (annual_return - rf) / downside_vol if downside_vol > 0 else 0
        calmar = annual_return / abs(mdd) if mdd != 0 else 0

        # 승률
        win_rate = (returns > 0).sum() / len(returns) * 100
        avg_win = returns[returns > 0].mean() * 100 if (returns > 0).any() else 0
        avg_loss = returns[returns < 0].mean() * 100 if (returns < 0).any() else 0

        results = [f"📊 {name} 위험조정수익률"]
        results.append(f"\n연간 수익률: {annual_return*100:+.1f}%")
        results.append(f"연간 변동성: {annual_vol*100:.1f}%")
        results.append(f"무위험 수익률: {rf*100:.1f}%")
        results.append(f"\n샤프 비율: {sharpe:.2f}")
        results.append(f"  해석: {'🟢 우수(>1)' if sharpe > 1 else '🟡 양호(>0.5)' if sharpe > 0.5 else '🔴 부진(<0.5)'}")
        results.append(f"소르티노 비율: {sortino:.2f}")
        results.append(f"  해석: {'🟢 우수(>2)' if sortino > 2 else '🟡 양호(>1)' if sortino > 1 else '🔴 부진(<1)'}")
        results.append(f"칼마 비율: {calmar:.2f}")
        results.append(f"  해석: {'🟢 우수(>1)' if calmar > 1 else '🟡 양호(>0.5)' if calmar > 0.5 else '🔴 부진(<0.5)'}")
        results.append(f"\n승률: {win_rate:.1f}%")
        results.append(f"평균 이익: {avg_win:.2f}% / 평균 손실: {avg_loss:.2f}%")
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        results.append(f"손익비: {profit_factor:.2f}")
        return "\n".join(results)

    # ── 6. 스트레스 테스트 ───────────────────

    async def _stress_test(self, kwargs: dict) -> str:
        name, df, returns, err = await self._load_data(kwargs)
        if err:
            return err

        current_price = int(df["종가"].iloc[-1])
        investment = int(kwargs.get("investment", 10_000_000))

        # 과거 위기 시나리오
        scenarios = [
            ("코로나 쇼크 (-30%)", -0.30),
            ("금리 급등 시나리오 (-20%)", -0.20),
            ("리먼 브라더스급 (-50%)", -0.50),
            ("일반 조정 (-10%)", -0.10),
            ("블랙 먼데이급 (-20% 일일)", -0.20),
        ]

        results = [f"📊 {name} 스트레스 테스트"]
        results.append(f"현재가: {current_price:,}원 / 투자금: {investment:,}원\n")
        results.append(f"{'시나리오':<25} | {'하락률':>6} | {'예상 주가':>10} | {'예상 손실':>12}")
        results.append("-" * 65)

        for scenario, drop in scenarios:
            est_price = int(current_price * (1 + drop))
            est_loss = int(investment * abs(drop))
            results.append(f"  {scenario:<23} | {drop*100:>5.0f}% | {est_price:>9,}원 | -{est_loss:>10,}원")

        # 역사적 최악의 주간/월간 손실
        weekly_ret = returns.resample("W").sum() if len(returns) > 5 else returns
        monthly_ret = returns.resample("ME").sum() if len(returns) > 20 else returns

        worst_day = returns.min()
        worst_week = weekly_ret.min() if not weekly_ret.empty else 0
        worst_month = monthly_ret.min() if not monthly_ret.empty else 0

        results.append(f"\n▸ 역사적 최악 기록:")
        results.append(f"  최악의 하루: {worst_day*100:.2f}% (약 {int(investment*abs(worst_day)):,}원)")
        results.append(f"  최악의 주간: {worst_week*100:.1f}%")
        results.append(f"  최악의 월간: {worst_month*100:.1f}%")

        raw_text = "\n".join(results)
        analysis = await self._llm_call(
            system_prompt="리스크관리 전문가로서 스트레스 테스트 결과를 해석하고 대비 전략을 제안하세요. 한국어.",
            user_prompt=raw_text,
            caller_model=kwargs.get("_caller_model"),
        )
        return f"{raw_text}\n\n🎓 분석:\n{analysis}"
