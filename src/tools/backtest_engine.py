"""
포트폴리오 백테스터 Tool (Backtest Engine).

pykrx + pandas-ta를 사용하여 투자 전략을 과거 데이터로 시뮬레이션합니다.
골든크로스, RSI, MACD, 바이앤홀드 전략을 백테스트합니다.

사용 방법:
  - action="backtest": 단일 전략 백테스트
    - ticker/name: 종목코드/종목명
    - strategy: "golden_cross", "rsi", "macd", "buy_and_hold"
    - start_date: 시작일 (YYYYMMDD, 기본: 1년 전)
    - end_date: 종료일 (YYYYMMDD, 기본: 오늘)
    - initial_capital: 초기 자금 (기본: 10,000,000원)
  - action="compare": 여러 전략 비교
    - ticker/name: 종목코드/종목명
    - strategies: 쉼표 구분 전략명 (예: "golden_cross,rsi,buy_and_hold")

필요 환경변수: 없음
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.backtest_engine")


def _import_pykrx():
    try:
        from pykrx import stock
        return stock
    except ImportError:
        return None


def _import_pandas():
    try:
        import pandas as pd
        return pd
    except ImportError:
        return None


def _import_pandas_ta():
    try:
        import pandas_ta as ta
        return ta
    except ImportError:
        return None


class BacktestEngineTool(BaseTool):
    """투자 전략 백테스트 시뮬레이션 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "backtest")

        if action == "backtest":
            return await self._backtest(kwargs)
        elif action == "compare":
            return await self._compare(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "backtest, compare 중 하나를 사용하세요."
            )

    # ── 단일 전략 백테스트 ──

    async def _backtest(self, kwargs: dict[str, Any]) -> str:
        stock = _import_pykrx()
        pd = _import_pandas()
        ta = _import_pandas_ta()
        if stock is None:
            return self._install_msg("pykrx")
        if pd is None:
            return self._install_msg("pandas")
        if ta is None:
            return self._install_msg("pandas-ta")

        # 파라미터 파싱
        ticker = kwargs.get("ticker", "")
        name = kwargs.get("name", "")
        if not ticker and not name:
            return "종목코드(ticker) 또는 종목명(name)을 입력해주세요."

        if name and not ticker:
            ticker = await self._resolve_ticker(stock, name)
            if not ticker:
                return f"'{name}' 종목을 찾을 수 없습니다."

        strategy = kwargs.get("strategy", "golden_cross")
        valid_strategies = ["golden_cross", "rsi", "macd", "buy_and_hold"]
        if strategy not in valid_strategies:
            return f"알 수 없는 전략: {strategy}. 사용 가능: {', '.join(valid_strategies)}"

        end_date = kwargs.get("end_date", datetime.now().strftime("%Y%m%d"))
        start_date = kwargs.get("start_date", (datetime.now() - timedelta(days=365)).strftime("%Y%m%d"))
        initial_capital = int(kwargs.get("initial_capital", 10_000_000))

        # 데이터 로드 (지표 계산용 여유 기간 포함)
        buffer_start = (datetime.strptime(start_date, "%Y%m%d") - timedelta(days=60)).strftime("%Y%m%d")
        try:
            df = await asyncio.to_thread(
                stock.get_market_ohlcv_by_date, buffer_start, end_date, ticker
            )
        except Exception as e:
            return f"주가 데이터 조회 실패: {e}"

        if df.empty or len(df) < 30:
            return f"종목코드 {ticker}의 데이터가 부족합니다 (최소 30일 필요)."

        stock_name = await self._get_stock_name(stock, ticker)

        # 시그널 생성
        df = self._generate_signals(df, strategy, ta)

        # 실제 백테스트 기간으로 자르기
        df = df[df.index >= start_date]
        if df.empty:
            return "백테스트 기간에 해당하는 데이터가 없습니다."

        # 시뮬레이션
        result = self._simulate(df, initial_capital)

        # 결과 포맷팅
        formatted = self._format_result(stock_name, ticker, strategy, start_date, end_date, initial_capital, result)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 퀀트(계량투자) 전문가입니다.\n"
                "백테스트 결과를 분석하여 다음을 정리하세요:\n"
                "1. 전략 성과 평가 (수익률, MDD, 샤프비율 종합)\n"
                "2. 전략의 강점과 약점\n"
                "3. 실전 적용 시 주의사항\n"
                "4. 전략 개선 제안\n"
                "한국어로 구체적 수치를 포함하여 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 백테스트 결과\n\n{formatted}\n\n---\n\n## 전략 분석\n\n{analysis}"

    # ── 전략 비교 ──

    async def _compare(self, kwargs: dict[str, Any]) -> str:
        strategies_str = kwargs.get("strategies", "golden_cross,rsi,macd,buy_and_hold")
        strategies = [s.strip() for s in strategies_str.split(",")]

        results: list[str] = []
        for strat in strategies:
            kwargs_copy = dict(kwargs)
            kwargs_copy["strategy"] = strat
            kwargs_copy["action"] = "backtest"
            result = await self._backtest(kwargs_copy)
            results.append(result)

        combined = "\n\n" + ("=" * 60 + "\n\n").join(results)

        return f"## 전략 비교 ({', '.join(strategies)})\n{combined}"

    # ── 시그널 생성 ──

    def _generate_signals(self, df: Any, strategy: str, ta: Any) -> Any:
        """전략에 따라 매수/매도 시그널 컬럼 추가."""
        pd = _import_pandas()
        close = df["종가"]
        df["signal"] = 0  # 0: 관망, 1: 매수, -1: 매도

        if strategy == "golden_cross":
            df["ma5"] = close.rolling(5).mean()
            df["ma20"] = close.rolling(20).mean()
            for i in range(1, len(df)):
                if (df["ma5"].iloc[i] > df["ma20"].iloc[i] and
                        df["ma5"].iloc[i - 1] <= df["ma20"].iloc[i - 1]):
                    df.iloc[i, df.columns.get_loc("signal")] = 1  # 골든크로스 → 매수
                elif (df["ma5"].iloc[i] < df["ma20"].iloc[i] and
                      df["ma5"].iloc[i - 1] >= df["ma20"].iloc[i - 1]):
                    df.iloc[i, df.columns.get_loc("signal")] = -1  # 데드크로스 → 매도

        elif strategy == "rsi":
            rsi = ta.rsi(close, length=14)
            if rsi is not None:
                df["rsi"] = rsi
                for i in range(1, len(df)):
                    if df["rsi"].iloc[i] < 30 and df["rsi"].iloc[i - 1] >= 30:
                        df.iloc[i, df.columns.get_loc("signal")] = 1
                    elif df["rsi"].iloc[i] > 70 and df["rsi"].iloc[i - 1] <= 70:
                        df.iloc[i, df.columns.get_loc("signal")] = -1

        elif strategy == "macd":
            macd_df = ta.macd(close)
            if macd_df is not None and not macd_df.empty:
                cols = macd_df.columns
                df["macd_line"] = macd_df[cols[0]]
                df["macd_signal"] = macd_df[cols[1]]
                for i in range(1, len(df)):
                    if (df["macd_line"].iloc[i] > df["macd_signal"].iloc[i] and
                            df["macd_line"].iloc[i - 1] <= df["macd_signal"].iloc[i - 1]):
                        df.iloc[i, df.columns.get_loc("signal")] = 1
                    elif (df["macd_line"].iloc[i] < df["macd_signal"].iloc[i] and
                          df["macd_line"].iloc[i - 1] >= df["macd_signal"].iloc[i - 1]):
                        df.iloc[i, df.columns.get_loc("signal")] = -1

        elif strategy == "buy_and_hold":
            if len(df) > 0:
                df.iloc[0, df.columns.get_loc("signal")] = 1  # 첫날 매수

        return df

    # ── 시뮬레이션 ──

    def _simulate(self, df: Any, initial_capital: int) -> dict[str, Any]:
        """매매 시뮬레이션 실행."""
        cash = initial_capital
        shares = 0
        trades: list[dict] = []
        portfolio_values: list[float] = []

        for date, row in df.iterrows():
            price = row["종가"]
            signal = row["signal"]

            if signal == 1 and cash > price:
                # 매수: 전액 투자
                buy_shares = int(cash // price)
                if buy_shares > 0:
                    cost = buy_shares * price
                    cash -= cost
                    shares += buy_shares
                    trades.append({
                        "날짜": date.strftime("%Y-%m-%d"),
                        "유형": "매수",
                        "가격": price,
                        "수량": buy_shares,
                        "잔고": cash + shares * price,
                    })

            elif signal == -1 and shares > 0:
                # 매도: 전량 매도
                revenue = shares * price
                cash += revenue
                trades.append({
                    "날짜": date.strftime("%Y-%m-%d"),
                    "유형": "매도",
                    "가격": price,
                    "수량": shares,
                    "잔고": cash,
                })
                shares = 0

            portfolio_values.append(cash + shares * price)

        final_value = cash + shares * df.iloc[-1]["종가"]
        total_return = ((final_value - initial_capital) / initial_capital) * 100

        # CAGR 계산
        days = len(df)
        years = days / 252  # 거래일 기준
        cagr = ((final_value / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0

        # MDD 계산
        peak = initial_capital
        max_drawdown = 0
        for val in portfolio_values:
            if val > peak:
                peak = val
            drawdown = (peak - val) / peak * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # 승률 계산
        buy_trades = [t for t in trades if t["유형"] == "매수"]
        sell_trades = [t for t in trades if t["유형"] == "매도"]
        wins = 0
        for i in range(min(len(buy_trades), len(sell_trades))):
            if sell_trades[i]["가격"] > buy_trades[i]["가격"]:
                wins += 1
        total_completed = min(len(buy_trades), len(sell_trades))
        win_rate = (wins / total_completed * 100) if total_completed > 0 else 0

        # 샤프 비율
        pd = _import_pandas()
        if pd and len(portfolio_values) > 1:
            returns = pd.Series(portfolio_values).pct_change().dropna()
            if returns.std() > 0:
                sharpe = (returns.mean() / returns.std()) * math.sqrt(252)
            else:
                sharpe = 0
        else:
            sharpe = 0

        return {
            "final_value": final_value,
            "total_return": total_return,
            "cagr": cagr,
            "mdd": max_drawdown,
            "win_rate": win_rate,
            "sharpe": sharpe,
            "total_trades": len(trades),
            "trades": trades[-10:],  # 최근 10건만
        }

    # ── 결과 포맷팅 ──

    def _format_result(
        self, stock_name: str, ticker: str, strategy: str,
        start_date: str, end_date: str, initial_capital: int,
        result: dict[str, Any],
    ) -> str:
        strategy_names = {
            "golden_cross": "골든크로스 (5일/20일 이동평균)",
            "rsi": "RSI (과매수/과매도)",
            "macd": "MACD (시그널선 돌파)",
            "buy_and_hold": "바이앤홀드 (매수 후 보유)",
        }

        lines = [
            f"### {stock_name} ({ticker}) 백테스트",
            f"  전략: {strategy_names.get(strategy, strategy)}",
            f"  기간: {start_date} ~ {end_date}",
            f"  초기 자금: {initial_capital:,.0f}원",
            "",
            f"  ▶ 성과 지표",
            f"    최종 자산: {result['final_value']:,.0f}원",
            f"    총 수익률: {result['total_return']:+.2f}%",
            f"    연환산 수익률(CAGR): {result['cagr']:+.2f}%",
            f"    최대 낙폭(MDD): -{result['mdd']:.2f}%",
            f"    승률: {result['win_rate']:.1f}%",
            f"    샤프 비율: {result['sharpe']:.2f}",
            f"    총 거래 횟수: {result['total_trades']}회",
        ]

        if result["trades"]:
            lines.append("\n  ▶ 최근 거래 내역")
            for t in result["trades"]:
                lines.append(
                    f"    {t['날짜']} {t['유형']} "
                    f"{t['가격']:,.0f}원 × {t['수량']}주 "
                    f"(잔고: {t['잔고']:,.0f}원)"
                )

        return "\n".join(lines)

    # ── 헬퍼 ──

    async def _resolve_ticker(self, stock_module: Any, name: str) -> str:
        """종목명 → 종목코드 변환."""
        try:
            date = datetime.now().strftime("%Y%m%d")
            tickers = await asyncio.to_thread(
                stock_module.get_market_ticker_list, date, market="ALL"
            )
            for t in tickers:
                t_name = await asyncio.to_thread(
                    stock_module.get_market_ticker_name, t
                )
                if t_name == name:
                    return t
        except Exception as e:
            logger.warning("[BacktestEngine] 종목명 변환 실패: %s", e)
        return ""

    async def _get_stock_name(self, stock_module: Any, ticker: str) -> str:
        """종목코드 → 종목명."""
        try:
            return await asyncio.to_thread(
                stock_module.get_market_ticker_name, ticker
            )
        except Exception:
            return ticker

    @staticmethod
    def _install_msg(package: str) -> str:
        return (
            f"{package} 라이브러리가 설치되지 않았습니다.\n"
            f"터미널에서 다음 명령어로 설치하세요:\n"
            f"  pip install {package}"
        )
