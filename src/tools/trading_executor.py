"""
매매 주문 실행 도구 — VECTOR (Trading Order Executor).

CIO가 분석 후 매수/매도 주문을 실행하는 도구입니다.
paper_trading 모드에서는 가상 포트폴리오만 업데이트하고,
실거래 모드에서는 KIS API를 통해 실제 주문을 넣습니다.

사용 방법:
  - action="buy", ticker="005930", qty=10, market="KR"
  - action="sell", ticker="AAPL", qty=5, price=185.50, market="US"
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger(__name__)


class TradingExecutorTool(BaseTool):
    """CIO가 매수/매도 주문을 실행하는 도구 (VECTOR)."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        ticker = kwargs.get("ticker", "").strip()
        qty = int(kwargs.get("qty", 0))
        price = float(kwargs.get("price", 0))
        market = kwargs.get("market", "KR").upper()
        reason = kwargs.get("reason", "CIO 분석 결과")

        # 입력 검증
        if action not in ("buy", "sell"):
            return "❌ action은 buy 또는 sell이어야 합니다."
        if not ticker:
            return "❌ ticker(종목코드)를 입력해주세요."
        if qty <= 0:
            return "❌ qty(수량)는 1 이상이어야 합니다."
        if market == "US" and price <= 0:
            return "❌ 미국주식은 지정가(price)가 필수입니다."

        try:
            import importlib
            ms = importlib.import_module("web.arm_server")
            from web.arm_server import load_setting, save_setting, KST

            settings = ms._load_data("trading_settings", ms._default_trading_settings())

            # 일일 거래 횟수 체크
            max_daily = settings.get("max_daily_trades", 10)
            today_str = datetime.now(KST).strftime("%Y-%m-%d")
            history = load_setting("trading_history", [])
            today_trades = [t for t in history if t.get("date", "").startswith(today_str)]
            if len(today_trades) >= max_daily:
                return f"❌ 일일 최대 거래 횟수({max_daily}회) 도달. 오늘은 더 이상 주문할 수 없습니다."

            paper_mode = settings.get("paper_trading", True)
            action_ko = "매수" if action == "buy" else "매도"

            if paper_mode:
                return await self._paper_trade(
                    ms, action, ticker, qty, price, market, reason, action_ko
                )
            else:
                return await self._real_trade(
                    ms, action, ticker, qty, price, market, reason, action_ko
                )

        except Exception as e:
            logger.error("[VECTOR] 주문 실행 실패: %s", e, exc_info=True)
            return f"❌ 주문 실행 중 오류: {e}"

    async def _real_trade(
        self, ms, action, ticker, qty, price, market, reason, action_ko
    ) -> str:
        """KIS API를 통한 실제 주문."""
        from web.arm_server import load_setting, save_setting, KST

        # KIS 가용 여부 확인
        if not ms._KIS_AVAILABLE:
            return "❌ KIS 모듈이 설치되지 않았습니다. 실거래 불가."
        if not ms._kis_configured():
            return "❌ KIS API가 설정되지 않았습니다. 실거래 불가."

        # 주문 실행
        if market == "US":
            order_result = await ms._kis_us_order(
                ticker, action, qty, price=price
            )
        else:
            order_result = await ms._kis_order(
                ticker, action, qty, price=int(price)
            )

        if not order_result.get("success"):
            msg = order_result.get("message", "알 수 없는 오류")
            return f"❌ KIS 주문 실패: {msg}"

        order_no = order_result.get("order_no", "")
        mode = order_result.get("mode", "")

        # 거래 기록 저장
        now = datetime.now(KST)
        trade_record = {
            "id": f"vector_{now.strftime('%Y%m%d%H%M%S')}_{ticker}",
            "date": now.isoformat(),
            "ticker": ticker,
            "name": ticker,
            "action": action,
            "qty": qty,
            "price": int(price) if market == "KR" else price,
            "total": qty * (int(price) if market == "KR" else price),
            "pnl": 0,
            "strategy": "vector",
            "status": "executed",
            "order_no": order_no,
            "market": market,
            "reason": reason,
        }
        history = load_setting("trading_history", [])
        history.insert(0, trade_record)
        if len(history) > 200:
            history = history[:200]
        save_setting("trading_history", history)

        # 활동 로그
        ms.save_activity_log(
            "fin_analyst",
            f"🎯 VECTOR {action_ko} 실행: {ticker} {qty}주 (주문번호: {order_no}, {mode})",
            "info",
        )

        return (
            f"✅ {action_ko} 주문 완료\n"
            f"- 종목: {ticker}\n"
            f"- 수량: {qty}주\n"
            f"- 주문번호: {order_no}\n"
            f"- 모드: {mode}\n"
            f"- 사유: {reason}"
        )

    async def _paper_trade(
        self, ms, action, ticker, qty, price, market, reason, action_ko
    ) -> str:
        """가상 포트폴리오(Paper Trading) 업데이트."""
        from web.arm_server import load_setting, save_setting, KST

        portfolio = ms._load_data("trading_portfolio", ms._default_portfolio())
        now = datetime.now(KST)

        # 현재가 조회 (price가 0이면)
        if price <= 0:
            try:
                if market == "US":
                    price_data = await ms._kis_us_price(ticker)
                else:
                    price_data = await ms._kis_price(ticker)
                price = float(price_data.get("price", 0))
            except Exception:
                pass
            if price <= 0:
                return "❌ 현재가를 조회할 수 없습니다. price를 직접 입력해주세요."

        total_cost = qty * price
        holdings = portfolio.get("holdings", [])
        cash = portfolio.get("cash", 0)

        if action == "buy":
            if cash < total_cost:
                return f"❌ 잔고 부족. 필요: {int(total_cost):,}원, 보유: {int(cash):,}원"
            # 기존 보유 종목이면 평단가 업데이트
            existing = next((h for h in holdings if h["ticker"] == ticker), None)
            if existing:
                old_qty = existing["qty"]
                old_avg = existing["avg_price"]
                new_qty = old_qty + qty
                existing["avg_price"] = (old_avg * old_qty + price * qty) / new_qty
                existing["qty"] = new_qty
                existing["current_price"] = price
            else:
                holdings.append({
                    "ticker": ticker,
                    "name": ticker,
                    "qty": qty,
                    "avg_price": price,
                    "current_price": price,
                })
            portfolio["cash"] = cash - total_cost

        elif action == "sell":
            existing = next((h for h in holdings if h["ticker"] == ticker), None)
            if not existing or existing["qty"] < qty:
                have = existing["qty"] if existing else 0
                return f"❌ 보유 수량 부족. 보유: {have}주, 매도 요청: {qty}주"
            existing["qty"] -= qty
            existing["current_price"] = price
            if existing["qty"] == 0:
                holdings.remove(existing)
            portfolio["cash"] = cash + total_cost

        portfolio["holdings"] = holdings
        portfolio["updated_at"] = now.isoformat()
        ms._save_data("trading_portfolio", portfolio)

        # 거래 기록
        trade_record = {
            "id": f"vector_{now.strftime('%Y%m%d%H%M%S')}_{ticker}",
            "date": now.isoformat(),
            "ticker": ticker,
            "name": ticker,
            "action": action,
            "qty": qty,
            "price": int(price) if market == "KR" else price,
            "total": int(total_cost) if market == "KR" else total_cost,
            "pnl": 0,
            "strategy": "vector",
            "status": "paper",
            "market": market,
            "reason": reason,
        }
        history = load_setting("trading_history", [])
        history.insert(0, trade_record)
        if len(history) > 200:
            history = history[:200]
        save_setting("trading_history", history)

        ms.save_activity_log(
            "fin_analyst",
            f"📝 VECTOR {action_ko} (가상): {ticker} {qty}주 @ {price:,.0f}",
            "info",
        )

        return (
            f"✅ {action_ko} 완료 (가상 포트폴리오)\n"
            f"- 종목: {ticker}\n"
            f"- 수량: {qty}주\n"
            f"- 가격: {price:,.0f}\n"
            f"- 잔여 현금: {portfolio['cash']:,.0f}\n"
            f"- 사유: {reason}"
        )
