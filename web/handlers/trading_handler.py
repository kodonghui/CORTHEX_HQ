"""트레이딩 API — 포트폴리오·관심종목·전략·주문·잔고·시그널 CRUD.

비유: 재무팀 — 투자 관련 데이터 조회·저장·주문 실행을 담당하는 곳.

추출 제외 (mini_server.py에 남음):
  - /api/trading/signals/generate (CIO 분석 파이프라인)
  - /api/trading/bot/toggle (봇 루프 시작/중지)
  - /api/trading/bot/run-now (_run_trading_now_inner)
  - /api/trading/kis/debug, debug-us (깊은 KIS 내부 디버깅)
  - /api/trading/cio/debug, debug-tools (CIO 디버깅)
"""
import asyncio
import json
import logging
import time
import uuid as _uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from db import save_setting, load_setting, save_activity_log
from state import app_state
from ws_manager import wm

try:
    from kis_client import (
        get_current_price as _kis_price,
        place_order as _kis_order,
        get_balance as _kis_balance,
        is_configured as _kis_configured,
        get_overseas_price as _kis_us_price,
        place_overseas_order as _kis_us_order,
        KIS_IS_MOCK,
    )
    _KIS_AVAILABLE = True
except ImportError:
    _KIS_AVAILABLE = False
    KIS_IS_MOCK = True
    async def _kis_price(ticker): return 0
    async def _kis_order(ticker, action, qty, price=0): return {"success": False, "message": "kis_client 미설치", "order_no": ""}
    async def _kis_balance(): return {"success": False, "cash": 0, "holdings": [], "total_eval": 0}
    def _kis_configured(): return False
    async def _kis_us_price(symbol, exchange=""): return {"success": False, "price": 0}
    async def _kis_us_order(symbol, action, qty, price=0, exchange=""): return {"success": False, "message": "kis_client 미설치", "order_no": ""}

logger = logging.getLogger("corthex.trading")
KST = timezone(timedelta(hours=9))

# 시세 캐시 → app_state에서 가져오기
_price_cache = app_state.price_cache
_price_cache_lock = app_state.price_cache_lock

router = APIRouter(tags=["trading"])


# ═══════════════════════════════════════════════════════════════
# 헬퍼 함수
# ═══════════════════════════════════════════════════════════════

def _load_data(name: str, default=None):
    """DB에서 설정 데이터 로드. (mini_server._load_data와 동일)"""
    db_val = load_setting(name)
    if db_val is not None:
        return db_val
    return default if default is not None else {}


def _save_data(name: str, data) -> None:
    """DB에 설정 데이터 저장."""
    save_setting(name, data)


def _default_portfolio() -> dict:
    """기본 포트폴리오 데이터."""
    return {
        "cash": 50_000_000,
        "initial_cash": 50_000_000,
        "holdings": [],
        "updated_at": datetime.now(KST).isoformat(),
    }


# ── 투자 성향 시스템 (CEO B안 승인: 성향 + CIO 자율) ──

RISK_PROFILES = {
    "aggressive": {
        "label": "공격적", "emoji": "🔥",
        "cash_reserve":       {"min": 5,  "max": 20,  "default": 10},
        "max_position_pct":   {"min": 15, "max": 35,  "default": 30},
        "min_confidence":     {"min": 50, "max": 75,  "default": 55},
        "default_stop_loss":  {"min": -12,"max": -3,  "default": -8},
        "default_take_profit":{"min": 5,  "max": 40,  "default": 15},
        "max_daily_trades":   {"min": 5,  "max": 20,  "default": 15},
        "max_daily_loss_pct": {"min": 2,  "max": 8,   "default": 5},
        "order_size":         {"min": 0,  "max": 10_000_000, "default": 0},
    },
    "balanced": {
        "label": "균형", "emoji": "⚖️",
        "cash_reserve":       {"min": 15, "max": 35,  "default": 20},
        "max_position_pct":   {"min": 10, "max": 25,  "default": 20},
        "min_confidence":     {"min": 55, "max": 80,  "default": 65},
        "default_stop_loss":  {"min": -8, "max": -2,  "default": -5},
        "default_take_profit":{"min": 5,  "max": 25,  "default": 10},
        "max_daily_trades":   {"min": 3,  "max": 15,  "default": 10},
        "max_daily_loss_pct": {"min": 1,  "max": 5,   "default": 3},
        "order_size":         {"min": 0,  "max": 5_000_000, "default": 0},
    },
    "conservative": {
        "label": "보수적", "emoji": "🐢",
        "cash_reserve":       {"min": 30, "max": 60,  "default": 40},
        "max_position_pct":   {"min": 5,  "max": 15,  "default": 10},
        "min_confidence":     {"min": 65, "max": 90,  "default": 75},
        "default_stop_loss":  {"min": -5, "max": -1,  "default": -3},
        "default_take_profit":{"min": 3,  "max": 15,  "default": 8},
        "max_daily_trades":   {"min": 1,  "max": 8,   "default": 5},
        "max_daily_loss_pct": {"min": 1,  "max": 3,   "default": 2},
        "order_size":         {"min": 0,  "max": 2_000_000, "default": 0},
    },
}


def _get_risk_profile() -> str:
    """현재 투자 성향 조회 (DB에서)."""
    return load_setting("trading_risk_profile", "aggressive")


def _clamp_setting(key: str, value, profile: str = None) -> float | int:
    """설정값을 현재 투자 성향의 안전 범위 내로 클램핑합니다."""
    if profile is None:
        profile = _get_risk_profile()
    ranges = RISK_PROFILES.get(profile, RISK_PROFILES["balanced"])
    r = ranges.get(key)
    if r is None:
        return value
    return max(r["min"], min(r["max"], value))


def _default_trading_settings() -> dict:
    """기본 자동매매 설정."""
    return {
        "max_position_pct": 20,
        "max_daily_trades": 10,
        "max_daily_loss_pct": 3,
        "default_stop_loss_pct": -5,
        "default_take_profit_pct": 10,
        "order_size": 0,
        "trading_hours_kr": {"start": "09:00", "end": "15:20"},
        "trading_hours_us": {"start": "22:30", "end": "05:00"},
        "trading_hours": {"start": "09:00", "end": "15:20"},
        "auto_stop_loss": True,
        "auto_take_profit": True,
        "auto_execute": False,
        "min_confidence": 65,
        "kis_connected": False,
        "paper_trading": True,
        "enable_real": True,
        "enable_mock": False,
        "calibration_enabled": True,
        "calibration_lookback": 20,
    }


def _compute_calibration_factor(lookback: int = 20) -> dict:
    """실제 승률 vs 예측 신뢰도 비율로 AI 자기보정 계수를 계산합니다."""
    import re as _re
    history = _load_data("trading_history", [])
    bot_trades = [
        h for h in history
        if h.get("auto_bot", False) or "신뢰도" in h.get("strategy", "")
    ]
    recent = bot_trades[:lookback]

    if len(recent) < 5:
        return {
            "factor": 1.0, "win_rate": None, "avg_confidence": None,
            "n": len(recent), "note": f"데이터 부족 ({len(recent)}건, 최소 5건 필요) — 보정 미적용",
        }

    closed = [h for h in recent if h.get("action") == "sell" and "pnl" in h]
    if not closed:
        return {
            "factor": 1.0, "win_rate": None, "avg_confidence": None,
            "n": 0, "note": "평가 가능한 매도 기록 없음 — 보정 미적용",
        }

    wins = sum(1 for t in closed if t.get("pnl", 0) > 0)
    actual_win_rate = wins / len(closed)

    confidences = []
    for t in closed:
        m = _re.search(r"신뢰도\s*(\d+)", t.get("strategy", ""))
        if m:
            confidences.append(int(m.group(1)) / 100.0)

    if not confidences:
        return {
            "factor": 1.0, "win_rate": round(actual_win_rate * 100, 1),
            "avg_confidence": None, "n": len(closed),
            "note": "신뢰도 기록 없음 — 보정 미적용",
        }

    avg_confidence = sum(confidences) / len(confidences)
    raw_factor = actual_win_rate / avg_confidence if avg_confidence > 0 else 1.0
    factor = round(max(0.5, min(1.5, raw_factor)), 3)

    diff = actual_win_rate * 100 - avg_confidence * 100
    if diff < -5:
        note = f"AI 과신 (예측 {avg_confidence*100:.0f}% → 실제 {actual_win_rate*100:.0f}%) → 신뢰도 {factor:.2f}배 하향 보정"
    elif diff > 5:
        note = f"AI 겸손 (예측 {avg_confidence*100:.0f}% → 실제 {actual_win_rate*100:.0f}%) → 신뢰도 {factor:.2f}배 상향 보정"
    else:
        note = f"AI 보정 미미 (예측≒실제, factor={factor:.2f})"

    return {
        "factor": factor,
        "win_rate": round(actual_win_rate * 100, 1),
        "avg_confidence": round(avg_confidence * 100, 1),
        "n": len(closed),
        "note": note,
    }


def _get_fx_rate() -> float:
    """USD/KRW 환율 반환. DB 설정값 우선, 없으면 1450 폴백."""
    try:
        rate = load_setting("fx_rate_usd_krw", 1450)
        if isinstance(rate, (int, float)) and 1000 < rate < 2000:
            return float(rate)
    except Exception as e:
        logger.debug("환율 조회 실패: %s", e)
    return 1450.0


def _enrich_overseas_balance_with_krw(result: dict) -> dict:
    """해외 잔고 결과에 KRW 환산 필드를 추가합니다."""
    if not result.get("success"):
        return result
    fx = _get_fx_rate()
    result["fx_rate"] = fx
    for h in result.get("holdings", []):
        eval_usd = h.get("eval_amt", h.get("qty", 0) * h.get("current_price", 0))
        h["eval_amt_krw"] = round(eval_usd * fx)
        h["eval_profit_krw"] = round(h.get("eval_profit", 0) * fx)
    total_usd = result.get("total_eval_usd", 0)
    result["total_eval_krw"] = round(total_usd * fx)
    cash_usd = result.get("cash_usd", 0)
    result["cash_krw"] = round(cash_usd * fx)
    return result


def _is_us_dst() -> bool:
    """미국 서머타임(EDT) 여부 판정."""
    now = datetime.now(KST)
    y = now.year
    mar1_wd = datetime(y, 3, 1).weekday()
    second_sun_mar = 1 + (6 - mar1_wd) % 7 + 7
    nov1_wd = datetime(y, 11, 1).weekday()
    first_sun_nov = 1 + (6 - nov1_wd) % 7
    mar_date = datetime(y, 3, second_sun_mar, tzinfo=KST)
    nov_date = datetime(y, 11, first_sun_nov, tzinfo=KST)
    return mar_date <= now < nov_date


def _us_analysis_time_kst() -> tuple[int, int]:
    """미국장 분석 실행 시각 (KST, 장 오픈 10분 후)."""
    return (22, 40) if _is_us_dst() else (23, 40)


# ═══════════════════════════════════════════════════════════════
# /api/trading/* 엔드포인트
# ═══════════════════════════════════════════════════════════════

@router.get("/api/trading/summary")
async def get_trading_summary():
    """트레이딩 대시보드 요약 데이터."""
    portfolio = _load_data("trading_portfolio", _default_portfolio())
    strategies = _load_data("trading_strategies", [])
    watchlist = _load_data("trading_watchlist", [])
    history = _load_data("trading_history", [])
    signals = _load_data("trading_signals", [])
    settings = _load_data("trading_settings", _default_trading_settings())

    # KIS 연결 상태 — DB 설정값 무시하고 실시간으로 확인
    settings["kis_connected"] = bool(_KIS_AVAILABLE and _kis_configured())

    # KIS 실계좌 잔고 조회 (연결된 경우에만)
    kis_balance = None
    if settings["kis_connected"]:
        try:
            kis_balance = await _kis_balance()
        except Exception as e:
            logger.warning("[KIS] summary 잔고 조회 실패: %s", e)
            kis_balance = None

    # 포트폴리오 평가 계산
    holdings = portfolio.get("holdings", [])
    total_eval = sum(h.get("current_price", 0) * h.get("qty", 0) for h in holdings)
    total_buy_cost = sum(h.get("avg_price", 0) * h.get("qty", 0) for h in holdings)
    cash = portfolio.get("cash", 0)
    total_asset = cash + total_eval
    total_pnl = total_eval - total_buy_cost
    pnl_pct = (total_pnl / total_buy_cost * 100) if total_buy_cost > 0 else 0

    # 오늘 거래 집계
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    today_trades = [t for t in history if t.get("date", "").startswith(today_str)]
    today_pnl = sum(t.get("pnl", 0) for t in today_trades)

    active_strategies = [s for s in strategies if s.get("active")]

    return {
        "portfolio": {
            "cash": cash,
            "total_eval": total_eval,
            "total_asset": total_asset,
            "total_pnl": total_pnl,
            "pnl_pct": round(pnl_pct, 2),
            "holdings_count": len(holdings),
            "initial_cash": portfolio.get("initial_cash", 50_000_000),
        },
        "strategies": {
            "total": len(strategies),
            "active": len(active_strategies),
        },
        "watchlist_count": len(watchlist),
        "today": {
            "trades": len(today_trades),
            "pnl": today_pnl,
        },
        "signals_count": len(signals),
        "settings": settings,
        "bot_active": app_state.trading_bot_active,
        "kis_balance": kis_balance,
    }


@router.get("/api/trading/portfolio")
async def get_trading_portfolio():
    """실거래 KIS 잔고 기반 포트폴리오 조회 — 한국장 + 미국장 통합 (C안)"""
    try:
        from kis_client import get_balance, get_overseas_balance, KIS_APP_KEY
        from db import save_setting as _ss, save_portfolio_snapshot
        import asyncio as _aio

        if not KIS_APP_KEY:
            return {"available": False, "reason": "KIS 미설정"}

        # 한국장 + 미국장 동시 조회
        kr_bal, us_bal = await _aio.gather(
            get_balance(),
            get_overseas_balance(),
            return_exceptions=True,
        )
        if isinstance(kr_bal, Exception):
            kr_bal = {"success": False, "error": str(kr_bal)}
        if isinstance(us_bal, Exception):
            us_bal = {"success": False, "error": str(us_bal)}

        kr_ok = kr_bal.get("success", False)
        us_ok = us_bal.get("success", False)

        if not kr_ok and not us_ok:
            return {"available": False, "reason": "한국장/미국장 모두 조회 실패"}

        # 환율 (DB → 폴백 1450)
        fx_rate = _get_fx_rate()

        # ── 한국장 ──
        kr_cash = kr_bal.get("cash", 0) if kr_ok else 0
        kr_holdings = kr_bal.get("holdings", []) if kr_ok else []
        kr_total = kr_bal.get("total_eval", kr_cash) if kr_ok else 0
        kr_holdings_pnl = sum(h.get("eval_profit", 0) for h in kr_holdings)
        kr_purchase_total = sum(h.get("purchase_amount", 0) for h in kr_holdings)
        kr_pnl = kr_holdings_pnl
        kr_pnl_pct = round((kr_pnl / kr_purchase_total * 100), 2) if kr_purchase_total > 0 else 0.0
        kr_initial = load_setting("portfolio_initial_capital", None)
        if kr_initial is None and kr_ok:
            kr_initial = kr_total if kr_total > 0 else kr_cash
            save_setting("portfolio_initial_capital", kr_initial)
        kr_initial = kr_initial or 0

        # ── 미국장 ──
        us_cash_usd = us_bal.get("cash_usd", 0) if us_ok else 0
        us_holdings = us_bal.get("holdings", []) if us_ok else []
        us_total_usd = us_bal.get("total_eval_usd", us_cash_usd) if us_ok else 0
        for h in us_holdings:
            eval_usd = h.get("eval_amt", h.get("qty", 0) * h.get("current_price", 0))
            h["eval_amt_krw"] = round(eval_usd * fx_rate)
            h["eval_profit_krw"] = round(h.get("eval_profit", 0) * fx_rate)
        us_holdings_pnl = sum(h.get("eval_profit", 0) for h in us_holdings)
        us_purchase_total = sum(h.get("qty", 0) * h.get("avg_price", 0) for h in us_holdings)
        us_pnl_usd = us_holdings_pnl
        us_pnl_pct = round((us_pnl_usd / us_purchase_total * 100), 2) if us_purchase_total > 0 else 0.0
        us_initial_usd = load_setting("portfolio_initial_capital_usd", None)
        if us_initial_usd is None and us_ok and us_total_usd > 0:
            us_initial_usd = us_total_usd
            save_setting("portfolio_initial_capital_usd", us_initial_usd)
        us_initial_usd = us_initial_usd or 0

        # ── 총합 (원화 환산) ──
        us_total_krw = us_total_usd * fx_rate
        grand_total = kr_total + us_total_krw
        total_deposit = load_setting("portfolio_total_deposit", None)
        if total_deposit is None:
            us_initial_krw = us_initial_usd * fx_rate
            fallback = kr_initial + us_initial_krw
            total_deposit = fallback if fallback > 0 else grand_total
            save_setting("portfolio_total_deposit", total_deposit)
        grand_initial = total_deposit
        grand_pnl = grand_total - grand_initial
        grand_pnl_pct = round((grand_pnl / grand_initial * 100), 2) if grand_initial > 0 else 0.0

        # 스냅샷 저장 (총합 기준)
        save_portfolio_snapshot(kr_cash, grand_total, grand_pnl, grand_pnl_pct)

        return {
            "available": True,
            "fx_rate": fx_rate,
            "kr": {
                "cash": kr_cash, "holdings": kr_holdings, "total_eval": kr_total,
                "initial_capital": kr_initial, "pnl": kr_pnl, "pnl_pct": kr_pnl_pct,
                "available": kr_ok,
            },
            "us": {
                "cash_usd": us_cash_usd, "holdings": us_holdings, "total_eval_usd": us_total_usd,
                "initial_capital_usd": us_initial_usd, "pnl_usd": us_pnl_usd, "pnl_pct": us_pnl_pct,
                "total_eval_krw": us_total_krw, "available": us_ok,
            },
            "cash": kr_cash,
            "holdings": kr_holdings,
            "total_eval": grand_total,
            "initial_capital": grand_initial,
            "pnl": grand_pnl,
            "pnl_pct": grand_pnl_pct,
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}


@router.post("/api/trading/portfolio")
async def update_trading_portfolio(request: Request):
    """포트폴리오 업데이트 (초기 자금 설정 등)."""
    body = await request.json()
    portfolio = _load_data("trading_portfolio", _default_portfolio())

    if "cash" in body:
        portfolio["cash"] = body["cash"]
    if "initial_cash" in body:
        portfolio["initial_cash"] = body["initial_cash"]
        portfolio["cash"] = body["initial_cash"]
        portfolio["holdings"] = []
    portfolio["updated_at"] = datetime.now(KST).isoformat()

    _save_data("trading_portfolio", portfolio)
    save_activity_log("system", f"💰 포트폴리오 업데이트: 현금 {portfolio['cash']:,.0f}원", "info")
    return {"success": True, "portfolio": portfolio}


@router.get("/api/trading/strategies")
async def get_trading_strategies():
    """매매 전략 목록."""
    return _load_data("trading_strategies", [])


@router.post("/api/trading/strategies")
async def save_trading_strategy(request: Request):
    """매매 전략 추가/수정."""
    body = await request.json()
    strategies = _load_data("trading_strategies", [])

    strategy_id = body.get("id") or f"strat_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{len(strategies)}"

    existing = next((s for s in strategies if s.get("id") == strategy_id), None)
    if existing:
        existing.update({
            "name": body.get("name", existing.get("name", "")),
            "type": body.get("type", existing.get("type", "manual")),
            "indicator": body.get("indicator", existing.get("indicator", "")),
            "buy_condition": body.get("buy_condition", existing.get("buy_condition", "")),
            "sell_condition": body.get("sell_condition", existing.get("sell_condition", "")),
            "target_tickers": body.get("target_tickers", existing.get("target_tickers", [])),
            "stop_loss_pct": body.get("stop_loss_pct", existing.get("stop_loss_pct", -5)),
            "take_profit_pct": body.get("take_profit_pct", existing.get("take_profit_pct", 10)),
            "order_size": body.get("order_size", existing.get("order_size", 1_000_000)),
            "active": body.get("active", existing.get("active", True)),
            "updated_at": datetime.now(KST).isoformat(),
        })
    else:
        strategy = {
            "id": strategy_id,
            "name": body.get("name", "새 전략"),
            "type": body.get("type", "manual"),
            "indicator": body.get("indicator", ""),
            "buy_condition": body.get("buy_condition", ""),
            "sell_condition": body.get("sell_condition", ""),
            "target_tickers": body.get("target_tickers", []),
            "stop_loss_pct": body.get("stop_loss_pct", -5),
            "take_profit_pct": body.get("take_profit_pct", 10),
            "order_size": body.get("order_size", 1_000_000),
            "active": body.get("active", True),
            "created_at": datetime.now(KST).isoformat(),
            "updated_at": datetime.now(KST).isoformat(),
        }
        strategies.append(strategy)

    _save_data("trading_strategies", strategies)
    save_activity_log("system", f"📊 매매 전략 저장: {body.get('name', strategy_id)}", "info")
    return {"success": True, "strategies": strategies}


@router.delete("/api/trading/strategies/{strategy_id}")
async def delete_trading_strategy(strategy_id: str):
    """매매 전략 삭제."""
    strategies = _load_data("trading_strategies", [])
    strategies = [s for s in strategies if s.get("id") != strategy_id]
    _save_data("trading_strategies", strategies)
    return {"success": True}


@router.put("/api/trading/strategies/{strategy_id}/toggle")
async def toggle_trading_strategy(strategy_id: str):
    """매매 전략 활성/비활성 토글."""
    strategies = _load_data("trading_strategies", [])
    for s in strategies:
        if s.get("id") == strategy_id:
            s["active"] = not s.get("active", True)
            _save_data("trading_strategies", strategies)
            return {"success": True, "active": s["active"]}
    return {"success": False, "error": "전략을 찾을 수 없습니다"}


@router.get("/api/trading/watchlist")
async def get_trading_watchlist():
    """관심 종목 목록."""
    return _load_data("trading_watchlist", [])


@router.post("/api/trading/watchlist")
async def add_trading_watchlist(request: Request):
    """관심 종목 추가."""
    body = await request.json()
    watchlist = _load_data("trading_watchlist", [])

    ticker = body.get("ticker", "")
    if not ticker:
        return {"success": False, "error": "종목코드 필수"}

    # 중복 체크
    if any(w.get("ticker") == ticker for w in watchlist):
        return {"success": False, "error": "이미 등록된 종목"}

    item = {
        "ticker": ticker,
        "name": body.get("name", ticker),
        "market": body.get("market", "KR"),
        "target_price": body.get("target_price", 0),
        "alert_type": body.get("alert_type", "above"),
        "notes": body.get("notes", ""),
        "added_at": datetime.now(KST).isoformat(),
    }
    watchlist.append(item)
    _save_data("trading_watchlist", watchlist)
    save_activity_log("system", f"👁️ 관심종목 추가: {item['name']} ({ticker})", "info")
    return {"success": True, "watchlist": watchlist}


@router.put("/api/trading/watchlist/{ticker}")
async def update_trading_watchlist(ticker: str, request: Request):
    """관심 종목 수정 (목표가, 알림 유형, 메모)."""
    body = await request.json()
    watchlist = _load_data("trading_watchlist", [])
    item = next((w for w in watchlist if w.get("ticker") == ticker), None)
    if not item:
        return {"success": False, "error": "종목을 찾을 수 없습니다"}
    if "target_price" in body:
        item["target_price"] = body["target_price"]
    if "alert_type" in body:
        item["alert_type"] = body["alert_type"]
    if "notes" in body:
        item["notes"] = body["notes"]
    _save_data("trading_watchlist", watchlist)
    save_activity_log("system", f"👁️ 관심종목 수정: {item.get('name', ticker)} ({ticker})", "info")
    return {"success": True, "watchlist": watchlist}


@router.delete("/api/trading/watchlist/{ticker}")
async def remove_trading_watchlist(ticker: str):
    """관심 종목 삭제."""
    ticker = unquote(ticker).strip()
    watchlist = _load_data("trading_watchlist", [])
    original_len = len(watchlist)
    watchlist = [w for w in watchlist if w.get("ticker") != ticker]
    _save_data("trading_watchlist", watchlist)
    removed = original_len - len(watchlist)
    logger.info("[관심종목] 삭제: %s (제거 %d건, 남은 %d건)", ticker, removed, len(watchlist))
    return {"success": True, "removed": removed, "watchlist": watchlist}


@router.put("/api/trading/watchlist/reorder")
async def reorder_watchlist(request: Request):
    """관심종목 순서 저장 (드래그 후 호출)."""
    body = await request.json()
    tickers = body.get("tickers", [])
    watchlist = _load_data("trading_watchlist", [])
    ticker_map = {w["ticker"]: w for w in watchlist}
    new_watchlist = [ticker_map[t] for t in tickers if t in ticker_map]
    # 누락된 항목도 뒤에 붙이기 (안전장치)
    existing = {t for t in tickers}
    for w in watchlist:
        if w["ticker"] not in existing:
            new_watchlist.append(w)
    _save_data("trading_watchlist", new_watchlist)
    return {"success": True}


@router.get("/api/trading/watchlist/prices")
async def get_watchlist_prices():
    """관심종목의 실시간 현재가를 조회.

    한국 주식: pykrx 라이브러리 (한국거래소 무료 데이터)
    미국 주식: yfinance 라이브러리 (Yahoo Finance 무료 데이터)
    """
    watchlist = _load_data("trading_watchlist", [])
    if not watchlist:
        return {"prices": {}, "updated_at": datetime.now(KST).isoformat()}

    prices = {}

    # --- 한국 주식 (pykrx) ---
    kr_tickers = [w for w in watchlist if w.get("market", "KR") == "KR"]
    if kr_tickers:
        try:
            from pykrx import stock as pykrx_stock
            today = datetime.now(KST).strftime("%Y%m%d")
            start = (datetime.now(KST) - timedelta(days=7)).strftime("%Y%m%d")
            for w in kr_tickers:
                try:
                    df = await asyncio.to_thread(
                        pykrx_stock.get_market_ohlcv_by_date, start, today, w["ticker"]
                    )
                    if df is not None and not df.empty:
                        latest = df.iloc[-1]
                        prev = df.iloc[-2] if len(df) >= 2 else latest
                        close = int(latest["종가"])
                        prev_close = int(prev["종가"])
                        change = close - prev_close
                        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
                        prices[w["ticker"]] = {
                            "current_price": close,
                            "prev_close": prev_close,
                            "change": change,
                            "change_pct": change_pct,
                            "volume": int(latest.get("거래량", 0)),
                            "high": int(latest.get("고가", 0)),
                            "low": int(latest.get("저가", 0)),
                            "currency": "KRW",
                        }
                except Exception as e:
                    logger.warning("한국 주가 조회 실패 %s: %s", w["ticker"], e)
                    prices[w["ticker"]] = {"error": str(e)}
        except ImportError:
            for w in kr_tickers:
                prices[w["ticker"]] = {"error": "pykrx 미설치"}

    # --- 미국 주식 (yfinance) ---
    us_tickers = [w for w in watchlist if w.get("market") == "US"]
    if us_tickers:
        try:
            import yfinance as yf
            for w in us_tickers:
                try:
                    ticker_obj = yf.Ticker(w["ticker"])
                    hist = await asyncio.to_thread(
                        lambda t=ticker_obj: t.history(period="5d")
                    )
                    if hist is not None and not hist.empty:
                        latest = hist.iloc[-1]
                        prev = hist.iloc[-2] if len(hist) >= 2 else latest
                        close = round(float(latest["Close"]), 2)
                        prev_close = round(float(prev["Close"]), 2)
                        change = round(close - prev_close, 2)
                        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
                        prices[w["ticker"]] = {
                            "current_price": close,
                            "prev_close": prev_close,
                            "change": change,
                            "change_pct": change_pct,
                            "volume": int(latest.get("Volume", 0)),
                            "high": round(float(latest.get("High", 0)), 2),
                            "low": round(float(latest.get("Low", 0)), 2),
                            "currency": "USD",
                        }
                except Exception as e:
                    logger.warning("미국 주가 조회 실패 %s: %s", w["ticker"], e)
                    prices[w["ticker"]] = {"error": str(e)}
        except ImportError:
            for w in us_tickers:
                prices[w["ticker"]] = {"error": "yfinance 미설치"}

    # 캐시에 있는 종목은 캐시값으로 보완 (실시간 조회 실패 시 대체)
    async with _price_cache_lock:
        for ticker_key, cached in _price_cache.items():
            if ticker_key not in prices or "error" in prices.get(ticker_key, {}):
                prices[ticker_key] = {
                    "current_price": cached.get("price", 0),
                    "change_pct": cached.get("change_pct", 0),
                    "updated_at": cached.get("updated_at", ""),
                    "from_cache": True,
                }

    return {"prices": prices, "updated_at": datetime.now(KST).isoformat()}


@router.get("/api/trading/prices/cached")
async def get_cached_prices():
    """1분 자동 갱신된 시세 캐시를 즉시 반환 (실시간 조회 없이 빠르게 응답)."""
    async with _price_cache_lock:
        return {"success": True, "data": dict(_price_cache)}


@router.get("/api/trading/watchlist/chart/{ticker}")
async def get_watchlist_chart(ticker: str, market: str = "KR", days: int = 30):
    """관심종목의 일별 가격 데이터 (차트용)."""
    chart_data = []

    if market == "KR":
        try:
            from pykrx import stock as pykrx_stock
            end = datetime.now(KST).strftime("%Y%m%d")
            start = (datetime.now(KST) - timedelta(days=days + 10)).strftime("%Y%m%d")
            df = await asyncio.to_thread(
                pykrx_stock.get_market_ohlcv_by_date, start, end, ticker
            )
            if df is not None and not df.empty:
                for date, row in df.tail(days).iterrows():
                    chart_data.append({
                        "date": date.strftime("%m/%d"),
                        "close": int(row["종가"]),
                        "volume": int(row.get("거래량", 0)),
                    })
        except ImportError:
            return {"ticker": ticker, "chart": [], "error": "pykrx 미설치"}
        except Exception as e:
            return {"ticker": ticker, "chart": [], "error": str(e)}
    else:
        try:
            import yfinance as yf
            ticker_obj = yf.Ticker(ticker)
            period = "1mo" if days <= 30 else "3mo"
            hist = await asyncio.to_thread(
                lambda t=ticker_obj, p=period: t.history(period=p)
            )
            if hist is not None and not hist.empty:
                for date, row in hist.tail(days).iterrows():
                    chart_data.append({
                        "date": date.strftime("%m/%d"),
                        "close": round(float(row["Close"]), 2),
                        "volume": int(row.get("Volume", 0)),
                    })
        except ImportError:
            return {"ticker": ticker, "chart": [], "error": "yfinance 미설치"}
        except Exception as e:
            return {"ticker": ticker, "chart": [], "error": str(e)}

    return {"ticker": ticker, "chart": chart_data}


@router.post("/api/trading/order")
async def execute_trading_order(request: Request):
    """CEO 수동 주문 실행 (매수/매도).

    paper_trading=True → 가상 포트폴리오만 업데이트
    paper_trading=False → KIS API로 실제 주문
    """
    body = await request.json()
    action = body.get("action", "")
    ticker = body.get("ticker", "")
    name = body.get("name", ticker)
    qty = int(body.get("qty", 0))
    price = int(body.get("price", 0))
    market = body.get("market", "KR").upper()

    if not all([action in ("buy", "sell"), ticker, qty > 0, price > 0]):
        return {"success": False, "error": "매수/매도, 종목코드, 수량, 가격 필수"}

    settings = _load_data("trading_settings", _default_trading_settings())
    paper_mode = settings.get("paper_trading", True)
    use_kis = _KIS_AVAILABLE and not paper_mode and _kis_configured()

    order_no = ""
    mode = "가상" if not use_kis else "실거래"

    # ── KIS 실주문 ──
    if use_kis:
        try:
            if market == "US":
                order_result = await _kis_us_order(ticker, action, qty, price=price)
            else:
                order_result = await _kis_order(ticker, action, qty, price=price)

            if not order_result.get("success"):
                msg = order_result.get("message", "알 수 없는 오류")
                return {"success": False, "error": f"KIS 주문 실패: {msg}"}

            order_no = order_result.get("order_no", "")
            mode = order_result.get("mode", "실거래")
        except Exception as e:
            return {"success": False, "error": f"KIS 주문 오류: {e}"}

    # ── 가상 포트폴리오 업데이트 (paper_trading일 때만) ──
    pnl = 0
    if not use_kis:
        portfolio = _load_data("trading_portfolio", _default_portfolio())
        total_amount = qty * price

        if action == "buy":
            if portfolio["cash"] < total_amount:
                return {"success": False, "error": f"현금 부족: 필요 {total_amount:,.0f}원, 보유 {portfolio['cash']:,.0f}원"}

            holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
            if holding:
                old_total = holding["avg_price"] * holding["qty"]
                new_total = old_total + total_amount
                holding["qty"] += qty
                holding["avg_price"] = int(new_total / holding["qty"])
                holding["current_price"] = price
            else:
                portfolio["holdings"].append({
                    "ticker": ticker, "name": name,
                    "qty": qty, "avg_price": price, "current_price": price,
                })
            portfolio["cash"] -= total_amount

        elif action == "sell":
            holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
            if not holding:
                return {"success": False, "error": f"{name} 보유하지 않음"}
            if holding["qty"] < qty:
                return {"success": False, "error": f"보유 수량 부족: 보유 {holding['qty']}주, 매도 {qty}주"}
            pnl = (price - holding["avg_price"]) * qty
            holding["qty"] -= qty
            holding["current_price"] = price
            if holding["qty"] == 0:
                portfolio["holdings"] = [h for h in portfolio["holdings"] if h["ticker"] != ticker]
            portfolio["cash"] += total_amount

        portfolio["updated_at"] = datetime.now(KST).isoformat()
        _save_data("trading_portfolio", portfolio)

    total_amount = qty * price

    # ── 거래 내역 저장 ──
    history = _load_data("trading_history", [])
    trade = {
        "id": f"trade_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{len(history)}",
        "date": datetime.now(KST).isoformat(),
        "ticker": ticker,
        "name": name,
        "action": action,
        "qty": qty,
        "price": price,
        "total": total_amount,
        "pnl": pnl if action == "sell" else 0,
        "strategy": body.get("strategy", "manual"),
        "status": "executed" if use_kis else "paper",
        "order_no": order_no,
        "market": market,
        "mode": mode,
    }
    history.insert(0, trade)
    if len(history) > 500:
        history = history[:500]
    _save_data("trading_history", history)

    action_ko = "매수" if action == "buy" else "매도"
    pnl_str = f" (손익: {pnl:+,.0f}원)" if action == "sell" else ""
    mode_tag = f" [{mode}]" if use_kis else " [가상]"
    order_tag = f" 주문#{order_no}" if order_no else ""
    save_activity_log("system",
        f"{'📈' if action == 'buy' else '📉'} CEO {action_ko}{mode_tag}: {name} {qty}주 × {price:,.0f}원 = {total_amount:,.0f}원{pnl_str}{order_tag}",
        "info")

    return {"success": True, "trade": trade, "mode": mode, "order_no": order_no}


@router.get("/api/trading/history")
async def get_trading_history():
    """거래 내역."""
    return _load_data("trading_history", [])


@router.get("/api/trading/signals")
async def get_trading_signals():
    """매매 시그널 목록."""
    return _load_data("trading_signals", [])


@router.get("/api/trading/decisions")
async def get_trading_decisions():
    """매매 결정 일지 반환 (최근 50건)."""
    decisions = load_setting("trading_decisions", [])
    return {"decisions": decisions[-50:]}


@router.delete("/api/trading/decisions/{decision_id}")
async def delete_trading_decision(decision_id: str):
    """개별 매매 결정 삭제."""
    decisions = load_setting("trading_decisions", [])
    before = len(decisions)
    decisions = [d for d in decisions if d.get("id") != decision_id]
    if len(decisions) == before:
        return {"success": False, "error": "해당 결정을 찾을 수 없습니다"}
    save_setting("trading_decisions", decisions)
    return {"success": True, "remaining": len(decisions)}


@router.delete("/api/trading/decisions")
async def delete_all_trading_decisions():
    """매매 결정 일지 전체 삭제."""
    save_setting("trading_decisions", [])
    return {"success": True, "message": "전체 삭제 완료"}


@router.delete("/api/trading/signals/{signal_id}")
async def delete_trading_signal(signal_id: str):
    """개별 매매 시그널 삭제."""
    signals = _load_data("trading_signals", [])
    new_signals = [s for s in signals if s.get("id") != signal_id]
    if len(new_signals) == len(signals):
        return {"success": False, "error": "시그널을 찾을 수 없습니다"}
    _save_data("trading_signals", new_signals)
    return {"success": True}


@router.get("/api/trading/settings")
async def get_trading_settings():
    """자동매매 설정."""
    return _load_data("trading_settings", _default_trading_settings())


@router.post("/api/trading/settings")
async def save_trading_settings(request: Request):
    """자동매매 설정 저장."""
    body = await request.json()
    settings = _load_data("trading_settings", _default_trading_settings())
    settings.update(body)
    _save_data("trading_settings", settings)
    save_activity_log("system", "⚙️ 자동매매 설정 업데이트", "info")
    return {"success": True, "settings": settings}


# ── 투자 성향 API ──

@router.get("/api/trading/risk-profile")
async def get_risk_profile():
    """현재 투자 성향 + 안전 범위 조회."""
    profile = _get_risk_profile()
    ranges = RISK_PROFILES.get(profile, RISK_PROFILES["balanced"])
    settings = _load_data("trading_settings", _default_trading_settings())
    history = load_setting("trading_settings_history", [])
    return {
        "profile": profile,
        "label": ranges["label"],
        "emoji": ranges["emoji"],
        "ranges": {k: v for k, v in ranges.items() if k not in ("label", "emoji")},
        "current_settings": settings,
        "change_history": history[-20:],
    }


@router.post("/api/trading/risk-profile")
async def set_risk_profile(request: Request):
    """투자 성향 변경 (CEO만 변경 가능)."""
    body = await request.json()
    profile = body.get("profile", "balanced")
    if profile not in RISK_PROFILES:
        return {"success": False, "error": f"유효하지 않은 성향: {profile}. aggressive/balanced/conservative 중 선택"}
    save_setting("trading_risk_profile", profile)
    # 성향 변경 시 현재 설정을 새 성향의 기본값으로 리셋
    ranges = RISK_PROFILES[profile]
    settings = _load_data("trading_settings", _default_trading_settings())
    for key in ("max_position_pct", "min_confidence", "max_daily_trades", "max_daily_loss_pct", "order_size"):
        if key in ranges:
            settings[key] = ranges[key]["default"]
    settings["default_stop_loss_pct"] = ranges["default_stop_loss"]["default"]
    settings["default_take_profit_pct"] = ranges["default_take_profit"]["default"]
    _save_data("trading_settings", settings)
    # 변경 이력 기록
    history = load_setting("trading_settings_history", [])
    history.append({
        "changed_at": datetime.now(KST).isoformat(),
        "changed_by": "CEO",
        "action": "성향 변경",
        "detail": f"{ranges['label']} ({profile}) 으로 변경 → 설정값 기본값으로 리셋",
    })
    if len(history) > 100:
        history = history[-100:]
    save_setting("trading_settings_history", history)
    save_activity_log("system", f"🎯 투자 성향 변경: {ranges['label']} {ranges['emoji']}", "info")
    return {"success": True, "profile": profile, "settings": settings}


@router.post("/api/trading/settings/cio-update")
async def cio_update_trading_settings(request: Request):
    """CIO가 도구를 통해 자동매매 설정을 변경합니다 (안전 범위 내에서만).

    body: {changes: {key: value, ...}, reason: str}
    """
    body = await request.json()
    changes = body.get("changes", {})
    reason = body.get("reason", "CIO 자율 판단")
    if not changes:
        return {"success": False, "error": "변경할 항목이 없습니다"}

    profile = _get_risk_profile()
    settings = _load_data("trading_settings", _default_trading_settings())
    applied = {}
    rejected = {}

    _key_map = {
        "default_stop_loss": "default_stop_loss_pct",
        "default_take_profit": "default_take_profit_pct",
    }

    for key, value in changes.items():
        setting_key = _key_map.get(key, key)
        clamped = _clamp_setting(key, value, profile)
        if clamped != value:
            rejected[key] = f"{value} → {clamped} (안전 범위로 조정됨)"
        settings[setting_key] = clamped
        applied[key] = clamped

    _save_data("trading_settings", settings)

    # 변경 이력 기록
    history = load_setting("trading_settings_history", [])
    history.append({
        "changed_at": datetime.now(KST).isoformat(),
        "changed_by": "CIO",
        "action": "설정 자율 변경",
        "detail": reason,
        "applied": applied,
        "rejected": rejected,
    })
    if len(history) > 100:
        history = history[-100:]
    save_setting("trading_settings_history", history)
    save_activity_log("cio_manager", f"⚙️ CIO 설정 변경: {', '.join(f'{k}={v}' for k, v in applied.items())} | {reason}", "info")

    return {"success": True, "applied": applied, "rejected": rejected, "settings": settings}


@router.get("/api/trading/bot/status")
async def get_trading_bot_status():
    """자동매매 봇 상태."""
    us_h, us_m = _us_analysis_time_kst()
    dst_label = "EDT(서머타임)" if _is_us_dst() else "EST(겨울)"
    return {
        "active": app_state.trading_bot_active,
        "task_running": app_state.trading_bot_task is not None and not app_state.trading_bot_task.done() if app_state.trading_bot_task else False,
        "settings": _load_data("trading_settings", _default_trading_settings()),
        "schedule": {
            "kr_time": "09:10",
            "us_time": f"{us_h:02d}:{us_m:02d}",
            "us_tz": dst_label,
        },
    }


@router.get("/api/trading/calibration")
async def get_trading_calibration():
    """AI 자기보정 현황 조회 — 실제 승률 vs 예측 신뢰도 비교."""
    settings = _load_data("trading_settings", _default_trading_settings())
    return _compute_calibration_factor(settings.get("calibration_lookback", 20))


@router.get("/api/trading/kis/balance")
async def get_kis_balance():
    """KIS 실계좌 잔고 조회."""
    if not _KIS_AVAILABLE or not _kis_configured():
        return {"success": False, "message": "KIS API 미설정"}
    return await _kis_balance()


@router.get("/api/trading/kis/status")
async def get_kis_status():
    """KIS API 연결 상태 확인."""
    configured = _KIS_AVAILABLE and _kis_configured()
    account_display = "미설정"
    if configured:
        try:
            from kis_client import KIS_ACCOUNT_NO as _acct
            account_display = f"****{_acct[-4:]}" if len(_acct) >= 4 else "설정됨"
        except Exception:
            account_display = "설정됨"
    return {
        "available": configured,
        "is_mock": KIS_IS_MOCK,
        "mode": "모의투자" if KIS_IS_MOCK else "실거래",
        "account": account_display,
    }


@router.get("/api/trading/mock/balance")
async def get_mock_trading_balance():
    """모의투자 잔고 조회"""
    try:
        from kis_client import get_mock_balance
        result = await get_mock_balance()
        return result
    except Exception as e:
        return {"available": False, "error": str(e)}


@router.get("/api/trading/overseas/balance")
async def get_overseas_trading_balance():
    """해외주식 잔고 조회 (실거래) — KRW 환산 포함"""
    try:
        from kis_client import get_overseas_balance
        result = await get_overseas_balance()
        return _enrich_overseas_balance_with_krw(result)
    except Exception as e:
        return {"available": False, "error": str(e)}


@router.get("/api/trading/overseas/mock-balance")
async def get_overseas_mock_balance():
    """해외주식 모의투자 잔고 조회 — KRW 환산 포함"""
    try:
        from kis_client import get_mock_overseas_balance
        result = await get_mock_overseas_balance()
        return _enrich_overseas_balance_with_krw(result)
    except Exception as e:
        return {"available": False, "error": str(e), "is_mock": True}


@router.get("/api/trading/portfolio/history")
async def get_portfolio_history():
    """포트폴리오 일별 스냅샷 조회 (라인차트용)"""
    try:
        from db import load_portfolio_snapshots
        return {"snapshots": load_portfolio_snapshots()}
    except Exception as e:
        return {"snapshots": [], "error": str(e)}


@router.post("/api/trading/portfolio/set-initial")
async def set_portfolio_initial(request: Request):
    """초기 자금 수동 설정 — KRW + USD 분리 지원"""
    try:
        body = await request.json()
        result = {}
        # 한국장 초기자금 (원)
        kr_amount = body.get("amount") or body.get("amount_krw")
        if kr_amount and int(kr_amount) > 0:
            save_setting("portfolio_initial_capital", int(kr_amount))
            result["initial_capital_krw"] = int(kr_amount)
        # 미국장 초기자금 (달러)
        us_amount = body.get("amount_usd")
        if us_amount is not None and float(us_amount) >= 0:
            save_setting("portfolio_initial_capital_usd", float(us_amount))
            result["initial_capital_usd"] = float(us_amount)
        # 총 입금액 (원화, 환전과 무관한 전체 투자금)
        total_deposit = body.get("total_deposit")
        if total_deposit is not None and float(total_deposit) >= 0:
            save_setting("portfolio_total_deposit", float(total_deposit))
            result["total_deposit"] = float(total_deposit)
        # 환율 수동 설정
        fx_rate = body.get("fx_rate")
        if fx_rate and float(fx_rate) > 0:
            save_setting("fx_rate_usd_krw", float(fx_rate))
            result["fx_rate"] = float(fx_rate)
        if not result:
            return {"success": False, "error": "금액을 입력해주세요"}
        return {"success": True, **result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/trading/mock/holdings")
async def get_mock_trading_holdings():
    """모의투자 보유종목 조회"""
    try:
        from kis_client import get_mock_holdings
        result = await get_mock_holdings()
        return result
    except Exception as e:
        return {"available": False, "holdings": [], "error": str(e)}


@router.get("/api/trading/shadow/compare")
async def get_shadow_compare():
    """실거래 vs 모의투자 비교"""
    try:
        from kis_client import get_shadow_comparison
        result = await get_shadow_comparison()
        return result
    except Exception as e:
        return {"available": False, "error": str(e)}


@router.post("/api/trading/portfolio/reset")
async def reset_trading_portfolio(request: Request):
    """포트폴리오 초기화 (모의투자 리셋)."""
    body = await request.json()
    initial_cash = body.get("initial_cash", 50_000_000)
    portfolio = {
        "cash": initial_cash,
        "initial_cash": initial_cash,
        "holdings": [],
        "updated_at": datetime.now(KST).isoformat(),
    }
    _save_data("trading_portfolio", portfolio)
    _save_data("trading_history", [])
    _save_data("trading_signals", [])
    save_activity_log("system", f"🔄 모의투자 리셋: 초기 자금 {initial_cash:,.0f}원", "info")
    return {"success": True, "portfolio": portfolio}


# ── CIO 예측 히스토리 ──

@router.get("/api/cio/predictions")
async def get_cio_predictions(limit: int = 20, unverified_only: bool = False):
    """CIO 예측 히스토리 조회"""
    try:
        from db import load_cio_predictions
        predictions = load_cio_predictions(limit=limit, unverified_only=unverified_only)
        return {"predictions": predictions}
    except Exception as e:
        logger.error("[CIO] 예측 조회 실패: %s", e)
        return {"predictions": [], "error": str(e)}


@router.get("/api/cio/performance-summary")
async def get_cio_performance_summary():
    """CIO 예측 성과 요약"""
    try:
        from db import get_cio_performance_summary as _perf
        summary = _perf()
        return summary
    except Exception as e:
        logger.error("[CIO] 성과 조회 실패: %s", e)
        return {"total_predictions": 0, "accuracy_3d": 0, "accuracy_7d": 0, "pending_count": 0}
