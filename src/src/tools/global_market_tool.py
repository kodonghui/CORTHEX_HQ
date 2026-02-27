"""글로벌 시장 도구 — 미국주식/지수/암호화폐/환율 조회."""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.global_market_tool")


def _get_yfinance():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        return None


def _get_httpx():
    try:
        import httpx
        return httpx
    except ImportError:
        return None


# 주요 글로벌 지수 심볼
MAJOR_INDICES = {
    "S&P500": "^GSPC",
    "나스닥": "^IXIC",
    "다우존스": "^DJI",
    "니케이225": "^N225",
    "항셍": "^HSI",
    "유로스톡스50": "^STOXX50E",
    "DAX": "^GDAXI",
    "FTSE100": "^FTSE",
}


class GlobalMarketTool(BaseTool):
    """글로벌 주식/지수/암호화폐/환율 조회 도구."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "")
        if not action:
            return (
                "action 파라미터가 필요합니다.\n"
                "사용 가능한 action:\n"
                "- stock: 개별 주식 조회 (symbol 필요, 예: symbol='AAPL')\n"
                "- index: 주요 지수 조회 (indices 선택, 예: indices='S&P500,나스닥')\n"
                "- crypto: 암호화폐 조회 (coins 선택, 예: coins='bitcoin,ethereum')\n"
                "- forex: 환율 조회\n"
                "- compare: 한국/글로벌 비교"
            )
        if action == "stock":
            return await self._stock(kwargs)
        elif action == "index":
            return await self._index(kwargs)
        elif action == "crypto":
            return await self._crypto(kwargs)
        elif action == "forex":
            return await self._forex(kwargs)
        elif action == "compare":
            return await self._compare(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: stock(주식), index(지수), crypto(암호화폐), "
                "forex(환율), compare(한국/글로벌 비교)"
            )

    async def _stock(self, kwargs: dict) -> str:
        """글로벌 주식 시세 조회."""
        yf = _get_yfinance()
        if yf is None:
            return "yfinance 라이브러리가 설치되지 않았습니다. pip install yfinance"

        symbol = kwargs.get("symbol", "")
        if not symbol:
            return "symbol 파라미터가 필요합니다. 예: symbol='AAPL' (Apple), 'TSLA' (Tesla), 'MSFT' (Microsoft)"
        period = kwargs.get("period", "1mo")

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            hist = ticker.history(period=period)

            if hist.empty:
                return f"'{symbol}' 종목 데이터를 찾을 수 없습니다."

            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else latest
            change = latest["Close"] - prev["Close"]
            change_pct = (change / prev["Close"]) * 100 if prev["Close"] else 0

            lines = [
                f"## {info.get('longName', symbol)} ({symbol})\n",
                f"| 항목 | 값 |",
                f"|------|------|",
                f"| 현재가 | ${latest['Close']:,.2f} |",
                f"| 전일 대비 | {'▲' if change >= 0 else '▼'} ${abs(change):,.2f} ({change_pct:+.2f}%) |",
                f"| 시가 | ${latest['Open']:,.2f} |",
                f"| 고가 | ${latest['High']:,.2f} |",
                f"| 저가 | ${latest['Low']:,.2f} |",
                f"| 거래량 | {latest['Volume']:,.0f} |",
            ]

            # 추가 정보
            market_cap = info.get("marketCap")
            pe_ratio = info.get("trailingPE")
            dividend = info.get("dividendYield")
            sector = info.get("sector", "")

            if market_cap:
                lines.append(f"| 시가총액 | ${market_cap / 1e9:,.1f}B |")
            if pe_ratio:
                lines.append(f"| PER | {pe_ratio:.1f} |")
            if dividend:
                lines.append(f"| 배당수익률 | {dividend * 100:.2f}% |")
            if sector:
                lines.append(f"| 섹터 | {sector} |")

            # 기간 성과
            period_return = ((latest["Close"] - hist.iloc[0]["Close"]) / hist.iloc[0]["Close"]) * 100
            lines.append(f"\n**{period} 수익률:** {period_return:+.2f}%")

            return "\n".join(lines)

        except Exception as e:
            logger.error("주식 조회 실패: %s", e)
            return f"주식 데이터 조회 실패: {e}"

    async def _index(self, kwargs: dict) -> str:
        """주요 글로벌 지수 조회."""
        yf = _get_yfinance()
        if yf is None:
            return "yfinance 라이브러리가 설치되지 않았습니다. pip install yfinance"

        indices = kwargs.get("indices")
        if indices:
            if isinstance(indices, str):
                indices = [i.strip() for i in indices.split(",")]
        else:
            indices = list(MAJOR_INDICES.keys())

        lines = ["## 글로벌 주요 지수 현황\n"]
        lines.append("| 지수 | 현재 | 전일 대비 | 등락률 |")
        lines.append("|------|------|---------|--------|")

        for name in indices:
            symbol = MAJOR_INDICES.get(name, name)
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d")
                if hist.empty or len(hist) < 2:
                    lines.append(f"| {name} | 데이터 없음 | - | - |")
                    continue
                latest = hist.iloc[-1]["Close"]
                prev = hist.iloc[-2]["Close"]
                change = latest - prev
                change_pct = (change / prev) * 100
                arrow = "▲" if change >= 0 else "▼"
                lines.append(
                    f"| {name} | {latest:,.2f} | {arrow} {abs(change):,.2f} | {change_pct:+.2f}% |"
                )
            except Exception:
                lines.append(f"| {name} | 조회 실패 | - | - |")

        return "\n".join(lines)

    async def _crypto(self, kwargs: dict) -> str:
        """암호화폐 시세 조회 (CoinGecko API)."""
        httpx = _get_httpx()
        if httpx is None:
            return "httpx 라이브러리가 설치되지 않았습니다. pip install httpx"

        coins = kwargs.get("coins", "bitcoin,ethereum")
        if isinstance(coins, list):
            coins = ",".join(coins)
        currency = kwargs.get("currency", "usd")

        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                "ids": coins,
                "vs_currencies": currency,
                "include_market_cap": "true",
                "include_24hr_vol": "true",
                "include_24hr_change": "true",
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            if not data:
                return "암호화폐 데이터를 가져올 수 없습니다."

            cur = currency.upper()
            lines = [f"## 암호화폐 시세 ({cur})\n"]
            lines.append("| 코인 | 가격 | 24h 변동 | 시가총액 | 24h 거래량 |")
            lines.append("|------|------|---------|---------|----------|")

            for coin_id, info in data.items():
                price = info.get(currency, 0)
                change_24h = info.get(f"{currency}_24h_change", 0)
                market_cap = info.get(f"{currency}_market_cap", 0)
                volume = info.get(f"{currency}_24h_vol", 0)

                arrow = "▲" if change_24h >= 0 else "▼"
                lines.append(
                    f"| {coin_id.title()} | ${price:,.2f} | {arrow} {abs(change_24h):.2f}% | "
                    f"${market_cap / 1e9:,.1f}B | ${volume / 1e6:,.0f}M |"
                )

            return "\n".join(lines)

        except Exception as e:
            logger.error("암호화폐 조회 실패: %s", e)
            return f"암호화폐 데이터 조회 실패: {e}"

    async def _forex(self, kwargs: dict) -> str:
        """환율 조회."""
        yf = _get_yfinance()
        if yf is None:
            return "yfinance 라이브러리가 설치되지 않았습니다. pip install yfinance"

        pairs = kwargs.get("pairs", ["USDKRW=X", "EURUSD=X", "USDJPY=X", "GBPUSD=X"])
        if isinstance(pairs, str):
            pairs = [p.strip() for p in pairs.split(",")]

        pair_names = {
            "USDKRW=X": "달러/원",
            "EURUSD=X": "유로/달러",
            "USDJPY=X": "달러/엔",
            "GBPUSD=X": "파운드/달러",
            "EURJPY=X": "유로/엔",
            "CNYKRW=X": "위안/원",
        }

        lines = ["## 주요 환율 현황\n"]
        lines.append("| 환율 | 현재 | 전일 대비 | 등락률 |")
        lines.append("|------|------|---------|--------|")

        for pair in pairs:
            try:
                ticker = yf.Ticker(pair)
                hist = ticker.history(period="5d")
                if hist.empty or len(hist) < 2:
                    lines.append(f"| {pair_names.get(pair, pair)} | 데이터 없음 | - | - |")
                    continue
                latest = hist.iloc[-1]["Close"]
                prev = hist.iloc[-2]["Close"]
                change = latest - prev
                change_pct = (change / prev) * 100
                arrow = "▲" if change >= 0 else "▼"
                name = pair_names.get(pair, pair.replace("=X", ""))
                lines.append(f"| {name} | {latest:,.2f} | {arrow} {abs(change):.2f} | {change_pct:+.2f}% |")
            except Exception:
                lines.append(f"| {pair_names.get(pair, pair)} | 조회 실패 | - | - |")

        return "\n".join(lines)

    async def _compare(self, kwargs: dict) -> str:
        """한국 vs 글로벌 시장 비교 분석."""
        yf = _get_yfinance()
        if yf is None:
            return "yfinance 라이브러리가 설치되지 않았습니다. pip install yfinance"

        period = kwargs.get("period", "1mo")
        targets = {
            "KOSPI": "^KS11",
            "KOSDAQ": "^KQ11",
            "S&P500": "^GSPC",
            "나스닥": "^IXIC",
            "니케이225": "^N225",
        }

        lines = [f"## 한국 vs 글로벌 시장 비교 ({period})\n"]
        lines.append("| 지수 | 현재 | 기간 수익률 | 최고 | 최저 |")
        lines.append("|------|------|---------|------|------|")

        for name, symbol in targets.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=period)
                if hist.empty:
                    continue
                latest = hist.iloc[-1]["Close"]
                first = hist.iloc[0]["Close"]
                ret = ((latest - first) / first) * 100
                high = hist["High"].max()
                low = hist["Low"].min()
                lines.append(f"| {name} | {latest:,.2f} | {ret:+.2f}% | {high:,.2f} | {low:,.2f} |")
            except Exception:
                lines.append(f"| {name} | 조회 실패 | - | - | - |")

        # LLM 분석
        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 글로벌 시장 분석 전문가입니다. "
                "한국과 글로벌 시장 데이터를 비교하여 핵심 인사이트를 한국어로 제공하세요."
            ),
            user_prompt=formatted,
        )

        return f"{formatted}\n\n---\n\n### 분석\n\n{analysis}"
