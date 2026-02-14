"""
종목 스크리너 Tool (Stock Screener).

pykrx 라이브러리를 사용하여 한국 상장사를 조건별로 자동 필터링합니다.
PER, PBR, 시가총액, 거래량, 배당수익률 등 다양한 조건으로 스크리닝합니다.

사용 방법:
  - action="screen": 조건 필터링 실행
    - market: "KOSPI"/"KOSDAQ"/"ALL" (기본: "ALL")
    - min_market_cap: 최소 시가총액 (억원, 예: 1000)
    - max_per: 최대 PER (예: 10)
    - min_per: 최소 PER (예: 0, 적자 기업 제외)
    - min_volume: 최소 일평균 거래량
    - top_n: 결과 개수 (기본: 20)
  - action="preset": 미리 정의된 전략으로 스크리닝
    - strategy: "value"(저평가), "growth"(성장), "dividend"(배당), "momentum"(모멘텀)

필요 환경변수: 없음 (pykrx는 무료, API 키 불필요)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.stock_screener")


def _import_pykrx():
    """pykrx 라이브러리 임포트."""
    try:
        from pykrx import stock
        return stock
    except ImportError:
        return None


def _import_pandas():
    """pandas 라이브러리 임포트."""
    try:
        import pandas as pd
        return pd
    except ImportError:
        return None


class StockScreenerTool(BaseTool):
    """한국 주식 종목 스크리너 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "screen")

        if action == "screen":
            return await self._screen(kwargs)
        elif action == "preset":
            return await self._preset(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "screen, preset 중 하나를 사용하세요."
            )

    # ── 조건 필터링 ──

    async def _screen(self, kwargs: dict[str, Any]) -> str:
        stock = _import_pykrx()
        pd = _import_pandas()
        if stock is None:
            return self._install_msg("pykrx")
        if pd is None:
            return self._install_msg("pandas")

        market = kwargs.get("market", "ALL")
        min_market_cap = float(kwargs.get("min_market_cap", 0))  # 억원
        max_per = float(kwargs.get("max_per", 9999))
        min_per = float(kwargs.get("min_per", 0))
        min_volume = int(kwargs.get("min_volume", 0))
        top_n = int(kwargs.get("top_n", 20))

        date = await self._get_latest_trading_date(stock)
        if not date:
            return "최근 거래일 데이터를 가져올 수 없습니다."

        # 시가총액/거래량 데이터
        markets = ["KOSPI", "KOSDAQ"] if market == "ALL" else [market]
        cap_frames = []
        fund_frames = []

        for mkt in markets:
            try:
                cap_df = await asyncio.to_thread(
                    stock.get_market_cap_by_ticker, date, market=mkt
                )
                fund_df = await asyncio.to_thread(
                    stock.get_market_fundamental_by_ticker, date, market=mkt
                )
                if not cap_df.empty:
                    cap_df["시장"] = mkt
                    cap_frames.append(cap_df)
                if not fund_df.empty:
                    fund_frames.append(fund_df)
            except Exception as e:
                logger.warning("[StockScreener] %s 데이터 조회 실패: %s", mkt, e)

        if not cap_frames or not fund_frames:
            return "시장 데이터를 가져오지 못했습니다."

        cap_all = pd.concat(cap_frames)
        fund_all = pd.concat(fund_frames)

        # 데이터 병합
        df = cap_all.join(fund_all, how="inner")

        # 시가총액을 억원 단위로 변환
        df["시가총액_억"] = df["시가총액"] / 1_0000_0000

        # 필터링
        mask = pd.Series(True, index=df.index)
        if min_market_cap > 0:
            mask &= df["시가총액_억"] >= min_market_cap
        if max_per < 9999:
            mask &= df["PER"] <= max_per
        if min_per > 0:
            mask &= df["PER"] >= min_per
        if min_volume > 0:
            mask &= df["거래량"] >= min_volume

        filtered = df[mask].sort_values("시가총액", ascending=False).head(top_n)

        if filtered.empty:
            return "조건에 맞는 종목이 없습니다. 필터 조건을 완화해보세요."

        # 종목명 매핑
        lines = [f"### 종목 스크리닝 결과 ({date} 기준, {len(filtered)}개)"]
        lines.append(f"  조건: 시가총액≥{min_market_cap}억, PER {min_per}~{max_per}, 거래량≥{min_volume:,}")
        lines.append("")
        lines.append(f"  {'순위':>4} {'종목코드':>8} {'종목명':>10}  {'시가총액(억)':>12}  {'PER':>8}  {'PBR':>6}  {'배당률':>6}")
        lines.append("  " + "-" * 70)

        for rank, (ticker, row) in enumerate(filtered.iterrows(), 1):
            try:
                name = await asyncio.to_thread(
                    stock.get_market_ticker_name, ticker
                )
            except Exception:
                name = ticker
            per = row.get("PER", 0)
            pbr = row.get("PBR", 0)
            div_yield = row.get("DIV", 0)
            cap = row["시가총액_억"]
            lines.append(
                f"  {rank:>3}. {ticker}  {name:>10}  {cap:>11,.0f}  "
                f"{per:>8.1f}  {pbr:>6.2f}  {div_yield:>5.1f}%"
            )

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 가치투자 분석가입니다.\n"
                "스크리닝 결과를 분석하여 다음을 정리하세요:\n"
                "1. 결과 종목들의 공통 특징\n"
                "2. 특히 주목할 만한 종목 3~5개와 그 이유\n"
                "3. 스크리닝 전략에 대한 의견\n"
                "한국어로 간결하게 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 종목 스크리닝\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 프리셋 전략 ──

    async def _preset(self, kwargs: dict[str, Any]) -> str:
        strategy = kwargs.get("strategy", "value")

        presets = {
            "value": {
                "label": "가치주 (저PER + 저PBR + 고배당)",
                "min_market_cap": 1000,
                "max_per": 10,
                "min_per": 0.1,
                "min_volume": 10000,
                "top_n": 20,
            },
            "growth": {
                "label": "성장주 (중대형 + 적정 밸류에이션)",
                "min_market_cap": 500,
                "max_per": 30,
                "min_per": 5,
                "min_volume": 50000,
                "top_n": 20,
            },
            "dividend": {
                "label": "배당주 (대형 + 안정적 배당)",
                "min_market_cap": 3000,
                "max_per": 20,
                "min_per": 0.1,
                "min_volume": 10000,
                "top_n": 20,
            },
            "momentum": {
                "label": "모멘텀 (대형 + 고거래량)",
                "min_market_cap": 1000,
                "max_per": 50,
                "min_per": 0.1,
                "min_volume": 500000,
                "top_n": 20,
            },
        }

        if strategy not in presets:
            available = ", ".join(presets.keys())
            return f"알 수 없는 전략: {strategy}. 사용 가능: {available}"

        preset = presets[strategy]
        label = preset.pop("label")
        preset["market"] = kwargs.get("market", "ALL")

        result = await self._screen(preset)
        return f"## 프리셋 전략: {label}\n\n{result}"

    # ── 최근 거래일 조회 ──

    async def _get_latest_trading_date(self, stock_module: Any) -> str:
        """주말/공휴일을 피해 최근 거래일을 찾음."""
        pd = _import_pandas()
        for i in range(7):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            try:
                df = await asyncio.to_thread(
                    stock_module.get_market_cap_by_ticker, date, market="KOSPI"
                )
                if df is not None and not df.empty:
                    return date
            except Exception:
                continue
        return ""

    @staticmethod
    def _install_msg(package: str) -> str:
        return (
            f"{package} 라이브러리가 설치되지 않았습니다.\n"
            f"터미널에서 다음 명령어로 설치하세요:\n"
            f"  pip install {package}"
        )
