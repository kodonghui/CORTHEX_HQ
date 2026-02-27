"""디버그 API — KIS/CIO/AI/매매/환율/서버 진단 엔드포인트.

비유: 정비소 — 시스템 각 부품의 상태를 하나씩 꺼내 확인하는 곳.
CEO에게 URL 제공 → 브라우저에서 바로 JSON 확인 가능.
"""
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from db import load_setting
from state import app_state
from config_loader import _AGENTS_DETAIL, _load_data, KST

logger = logging.getLogger("corthex")

router = APIRouter(tags=["debug"])


# ── arm_server 참조 헬퍼 ──
def _ms():
    """arm_server 모듈 참조."""
    return sys.modules.get("arm_server") or sys.modules.get("web.arm_server")


def _kis_available():
    ms = _ms()
    return getattr(ms, "_KIS_AVAILABLE", False) if ms else False


def _kis_configured():
    ms = _ms()
    fn = getattr(ms, "_kis_configured", None) if ms else None
    return fn() if fn else False


def _kis_is_mock():
    ms = _ms()
    return getattr(ms, "KIS_IS_MOCK", True) if ms else True


def _get_fx_rate():
    ms = _ms()
    fn = getattr(ms, "_get_fx_rate", None) if ms else None
    return fn() if fn else 1350.0


def _fx_update_interval():
    ms = _ms()
    return getattr(ms, "_FX_UPDATE_INTERVAL", 3600) if ms else 3600


async def _update_fx_rate():
    ms = _ms()
    fn = getattr(ms, "_update_fx_rate", None) if ms else None
    return await fn() if fn else None


def _default_trading_settings():
    ms = _ms()
    fn = getattr(ms, "_default_trading_settings", None) if ms else None
    return fn() if fn else {}


def _default_portfolio():
    ms = _ms()
    fn = getattr(ms, "_default_portfolio", None) if ms else None
    return fn() if fn else {}


async def _kis_balance():
    ms = _ms()
    fn = getattr(ms, "_kis_balance", None) if ms else None
    return await fn() if fn else {"success": False}


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


# ═══════════════════════════════════════════════════════════════
# KIS 디버그
# ═══════════════════════════════════════════════════════════════

@router.get("/api/trading/kis/debug")
async def kis_debug():
    """KIS API 원본 응답 확인 (디버그용)."""
    if not _kis_available() or not _kis_configured():
        return {"error": "KIS 미설정", "available": False}
    try:
        from kis_client import (
            _get_token, KIS_BASE, KIS_APP_KEY, KIS_APP_SECRET,
            KIS_ACCOUNT_NO, KIS_ACCOUNT_CODE, _TR, KIS_IS_MOCK as _mock,
        )
        import httpx as _hx

        token = await _get_token()
        async with _hx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{KIS_BASE}/uapi/domestic-stock/v1/trading/inquire-balance",
                headers={
                    "authorization": f"Bearer {token}",
                    "appkey": KIS_APP_KEY,
                    "appsecret": KIS_APP_SECRET,
                    "tr_id": _TR["balance"],
                },
                params={
                    "CANO": KIS_ACCOUNT_NO,
                    "ACNT_PRDT_CD": KIS_ACCOUNT_CODE,
                    "AFHR_FLPR_YN": "N", "OFL_YN": "",
                    "INQR_DVSN": "02", "UNPR_DVSN": "01",
                    "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
                    "PRCS_DVSN": "01", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
                },
            )
            data = resp.json()
        return {
            "mode": "모의투자" if _mock else "실거래",
            "base_url": KIS_BASE,
            "account": f"****{KIS_ACCOUNT_NO[-4:]}",
            "tr_id": _TR["balance"],
            "http_status": resp.status_code,
            "rt_cd": data.get("rt_cd"),
            "msg_cd": data.get("msg_cd"),
            "msg1": data.get("msg1"),
            "output1_count": len(data.get("output1", [])),
            "output2_sample": data.get("output2", [{}])[:1],
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/trading/kis/debug-us")
async def kis_debug_us():
    """해외주식 KIS API 원본 응답 확인 (디버그용)."""
    if not _kis_available() or not _kis_configured():
        return {"error": "KIS 미설정", "available": False}
    try:
        from kis_client import (
            get_overseas_balance, KIS_IS_MOCK as _mock, KIS_BASE,
        )
        result = await get_overseas_balance()
        result = _enrich_overseas_balance_with_krw(result)
        return {
            "mode": "모의투자" if _mock else "실거래",
            "base_url": KIS_BASE,
            "result": result,
        }
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════
# CIO 디버그
# ═══════════════════════════════════════════════════════════════

@router.get("/api/trading/cio/debug")
async def cio_debug():
    """CIO 전문가 도구 스키마 + 테스트 호출 (디버그용)."""
    try:
        from ai_handler import _load_tool_schemas, ask_ai
        detail = _AGENTS_DETAIL.get("market_analyst", {})
        allowed = detail.get("allowed_tools", [])
        schemas = _load_tool_schemas(allowed_tools=allowed)
        openai_tools = schemas.get("openai", [])
        tool_names = [t["function"]["name"] for t in openai_tools]
        tool_count = len(openai_tools)
        test_result = await ask_ai("안녕하세요, 테스트입니다. 한 줄로 응답해주세요.",
                                   system_prompt="간단히 응답", model="gpt-5.2")
        return {
            "specialist": "market_analyst (시황분석)",
            "allowed_tools": allowed,
            "openai_tool_count": tool_count,
            "openai_tool_names": tool_names,
            "openai_first_tool_schema": openai_tools[0] if openai_tools else None,
            "test_call_result": test_result.get("content", "")[:200] if "error" not in test_result else test_result["error"],
            "test_call_error": test_result.get("error"),
        }
    except Exception as e:
        return {"error": str(e)[:500]}


@router.get("/api/trading/cio/debug-tools")
async def cio_debug_tools():
    """CIO 전문가에게 도구 포함 테스트 호출 (실제 400 에러 재현)."""
    try:
        from ai_handler import _load_tool_schemas, ask_ai
        detail = _AGENTS_DETAIL.get("market_analyst", {})
        allowed = detail.get("allowed_tools", [])
        schemas = _load_tool_schemas(allowed_tools=allowed)
        anthropic_tools = schemas.get("anthropic", [])

        async def _dummy_executor(name, args):
            return f"[테스트] {name} 호출됨: {args}"
        result = await ask_ai(
            "테스트입니다. global_market_tool action=index 로 현재 시장 지수를 알려주세요.",
            system_prompt="간단히 도구를 사용해 응답하세요.",
            model="gpt-5.2",
            tools=anthropic_tools,
            tool_executor=_dummy_executor,
        )
        return {
            "success": "error" not in result,
            "content": result.get("content", "")[:300],
            "error": result.get("error"),
            "tools_count": len(anthropic_tools),
        }
    except Exception as e:
        return {"error": str(e)[:500], "type": type(e).__name__}


# ═══════════════════════════════════════════════════════════════
# 범용 디버그 엔드포인트 — 버그 발생 시 CEO에게 URL 제공용
# ═══════════════════════════════════════════════════════════════

@router.get("/api/debug/ai-providers")
async def debug_ai_providers():
    """AI 프로바이더 연결 상태 진단 — GPT/Claude/Gemini 중 뭐가 켜져있는지 확인."""
    import ai_handler as _ah
    providers = _ah.get_available_providers()
    env_keys = {
        "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY", "")),
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY", "")),
        "GOOGLE_API_KEY": bool(os.getenv("GOOGLE_API_KEY", "")),
    }
    client_info = {
        "anthropic": type(_ah._anthropic_client).__name__ if _ah._anthropic_client else None,
        "openai": type(_ah._openai_client).__name__ if _ah._openai_client else None,
        "google": type(_ah._google_client).__name__ if _ah._google_client else None,
    }
    env_key_map = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GOOGLE_API_KEY"}
    exhausted = list(_ah._exhausted_providers)
    return {
        "providers_available": providers,
        "env_keys_present": env_keys,
        "client_types": client_info,
        "exhausted_providers": exhausted,
        "diagnosis": {
            k: ("🔴 크레딧 소진" if k in _ah._exhausted_providers else
                "정상" if providers.get(k) else
                ("API 키 없음" if not env_keys.get(env_key_map[k]) else
                 "키 있으나 클라이언트 초기화 실패"))
            for k in ["anthropic", "openai", "google"]
        },
    }


@router.post("/api/debug/reset-exhausted-providers")
async def reset_exhausted_providers():
    """크레딧 충전 후 소진 상태를 초기화합니다."""
    import ai_handler as _ah
    prev = list(_ah._exhausted_providers)
    _ah.reset_exhausted_providers()
    return {"reset": prev, "message": f"{len(prev)}개 프로바이더 소진 상태 초기화 완료"}


@router.get("/api/debug/agent-calls")
async def debug_agent_calls():
    """최근 AI 호출 기록 10건 — 어떤 모델/프로바이더로 호출됐는지 확인."""
    try:
        conn = __import__("db").get_connection()
        rows = conn.execute(
            "SELECT agent_id, model, provider, cost_usd, input_tokens, output_tokens, "
            "time_seconds, success, created_at FROM agent_calls "
            "ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        conn.close()
        return {
            "recent_calls": [
                {
                    "agent_id": r[0], "model": r[1], "provider": r[2],
                    "cost_usd": round(r[3], 4) if r[3] else 0,
                    "tokens": f"{r[4] or 0}+{r[5] or 0}",
                    "time_sec": round(r[6], 1) if r[6] else 0,
                    "success": bool(r[7]), "created_at": r[8],
                }
                for r in rows
            ],
            "total_count": len(rows),
        }
    except Exception as e:
        return {"error": str(e)[:300]}


@router.get("/api/debug/cio-signals")
async def debug_cio_signals():
    """CIO 시그널 파싱 상태 — 시그널이 왜 안 뜨는지 확인."""
    signals_data = load_setting("trading_signals") or {}
    decisions = load_setting("trading_decisions") or []
    return {
        "saved_signals": signals_data,
        "saved_decisions_count": len(decisions),
        "latest_decisions": decisions[-3:] if decisions else [],
        "watchlist": load_setting("watchlist") or [],
    }


@router.get("/api/debug/trading-execution")
async def debug_trading_execution():
    """매매 실행 디버그 — auto_execute, 설정, 최근 시그널, 주문 상태 확인."""
    settings = _load_data("trading_settings", _default_trading_settings())
    signals = _load_data("trading_signals", [])
    history = _load_data("trading_history", [])
    latest_signal = signals[0] if signals else {}
    recent_history = history[:5]

    return {
        "settings": {
            "auto_execute": settings.get("auto_execute", False),
            "paper_trading": settings.get("paper_trading", True),
            "min_confidence": settings.get("min_confidence", 65),
            "order_size": settings.get("order_size", 0),
        },
        "kis_status": {
            "available": _kis_available(),
            "configured": _kis_configured(),
            "is_mock": _kis_is_mock(),
        },
        "latest_signal": {
            "id": latest_signal.get("id", ""),
            "date": latest_signal.get("date", ""),
            "parsed_count": len(latest_signal.get("parsed_signals", [])),
            "parsed_signals": latest_signal.get("parsed_signals", []),
            "manual_run": latest_signal.get("manual_run", False),
        },
        "recent_orders": [{
            "id": h.get("id"), "date": h.get("date"),
            "ticker": h.get("ticker"), "action": h.get("action"),
            "qty": h.get("qty"), "status": h.get("status"),
        } for h in recent_history],
        "note": "수동 즉시 실행은 auto_execute 무관하게 항상 매매 진행 (2026-02-21 수정)",
    }


@router.get("/api/debug/trading-holdings")
async def debug_trading_holdings():
    """매매 보유종목 디버그 — KIS 잔고 vs 내부 포트폴리오 vs 거래내역 비교."""
    portfolio = _load_data("trading_portfolio", _default_portfolio())
    history = _load_data("trading_history", [])
    settings = _load_data("trading_settings", _default_trading_settings())

    kis_bal = None
    if _kis_available() and _kis_configured():
        try:
            kis_bal = await _kis_balance()
        except Exception as e:
            kis_bal = {"error": str(e)}

    kis_mock = None
    try:
        from kis_client import get_mock_balance
        kis_mock = await get_mock_balance()
    except Exception as e:
        kis_mock = {"error": str(e)}

    recent_buys = [t for t in history[:30] if t.get("action") == "buy"]

    return {
        "kis_available": _kis_available(),
        "kis_configured": _kis_configured(),
        "kis_is_mock": _kis_is_mock(),
        "paper_trading": settings.get("paper_trading", True),
        "kis_real_balance": kis_bal,
        "kis_mock_balance": kis_mock,
        "internal_portfolio": {
            "cash": portfolio.get("cash", 0),
            "holdings": portfolio.get("holdings", []),
            "updated_at": portfolio.get("updated_at"),
        },
        "recent_buys": recent_buys[:10],
    }


@router.get("/api/debug/kis-token")
async def debug_kis_token():
    """KIS 토큰 상태 디버그 — 토큰 유효성, 만료시간, 캐시 상태, 쿨다운."""
    info = {"kis_available": _kis_available(), "configured": False}
    if not _kis_available():
        info["error"] = "kis_client 모듈 로드 실패"
        return info
    try:
        from kis_client import (
            is_configured, KIS_IS_MOCK, KIS_BASE,
            _token_cache, _last_token_request, _TOKEN_COOLDOWN_SEC,
            _last_token_request_domestic, _last_token_request_overseas,
            _last_balance_cache, _last_mock_balance_cache,
            KIS_ACCOUNT_NO, KIS_ACCOUNT_CODE,
        )
        info["configured"] = is_configured()
        info["is_mock"] = KIS_IS_MOCK
        info["base_url"] = KIS_BASE
        info["account"] = f"{KIS_ACCOUNT_NO[:4]}****-{KIS_ACCOUNT_CODE}" if KIS_ACCOUNT_NO else "미설정"

        now = datetime.now()
        token = _token_cache.get("token")
        expires = _token_cache.get("expires")
        if token and expires:
            remaining = (expires - now).total_seconds()
            info["token"] = {
                "status": "유효" if remaining > 0 else "만료됨",
                "masked": f"{token[:8]}...{token[-4:]}" if token else None,
                "expires": expires.isoformat() if expires else None,
                "remaining_seconds": max(0, int(remaining)),
                "remaining_human": f"{int(remaining // 3600)}시간 {int((remaining % 3600) // 60)}분" if remaining > 0 else "만료됨",
            }
        else:
            info["token"] = {"status": "토큰 없음 (아직 발급되지 않았거나 서버 재시작됨)"}

        def _cooldown_info(last_req, label):
            if last_req:
                elapsed = (now - last_req).total_seconds()
                cooldown_remaining = max(0, _TOKEN_COOLDOWN_SEC - elapsed)
                return {
                    "market": label,
                    "last_request": last_req.isoformat(),
                    "elapsed_seconds": int(elapsed),
                    "remaining_seconds": int(cooldown_remaining),
                    "can_request": cooldown_remaining <= 0,
                }
            return {"market": label, "last_request": None, "can_request": True}

        info["cooldown"] = {
            "domestic": _cooldown_info(_last_token_request_domestic, "국내"),
            "overseas": _cooldown_info(_last_token_request_overseas, "해외"),
            "last_any": _last_token_request.isoformat() if _last_token_request else None,
        }

        info["balance_cache"] = {
            "real_cached": bool(_last_balance_cache),
            "mock_cached": bool(_last_mock_balance_cache),
            "real_total_krw": _last_balance_cache.get("total_krw") if _last_balance_cache else None,
            "mock_total_krw": _last_mock_balance_cache.get("total_krw") if _last_mock_balance_cache else None,
        }
    except Exception as e:
        info["error"] = str(e)
    return info


@router.get("/api/debug/auto-trading-pipeline")
async def debug_auto_trading_pipeline():
    """자동매매 전체 파이프라인 디버그 — KIS 연결부터 주문 실행까지 전 단계."""
    settings = _load_data("trading_settings", _default_trading_settings())
    signals = _load_data("trading_signals", [])
    watchlist = _load_data("trading_watchlist", [])
    history = _load_data("trading_history", [])

    kis_ok = _kis_available() and _kis_configured()

    import ai_handler as _ah
    providers = _ah.get_available_providers()

    latest = signals[0] if signals else {}
    parsed = latest.get("parsed_signals", [])
    buy_signals = [s for s in parsed if s.get("action") == "buy"]
    sell_signals = [s for s in parsed if s.get("action") == "sell"]

    pipeline = {
        "1_ai_connection": {
            "status": "OK" if any(providers.values()) else "FAIL",
            "providers": {k: "연결됨" if v else "미연결" for k, v in providers.items()},
        },
        "2_watchlist": {
            "status": "OK" if watchlist else "FAIL",
            "count": len(watchlist),
            "tickers": [f"{w['name']}({w['ticker']})" for w in watchlist[:5]],
        },
        "3_signal_generation": {
            "status": "OK" if signals else "FAIL",
            "latest_date": latest.get("date", "없음"),
            "analyzed_by": latest.get("analyzed_by", "없음"),
            "buy_count": len(buy_signals),
            "sell_count": len(sell_signals),
            "hold_count": len([s for s in parsed if s.get("action") == "hold"]),
        },
        "4_kis_connection": {
            "status": "OK" if kis_ok else "FAIL",
            "kis_available": _kis_available(),
            "kis_configured": _kis_configured(),
            "is_mock": _kis_is_mock(),
        },
        "5_order_execution": {
            "status": "OK" if kis_ok else "BLOCKED",
            "paper_trading": settings.get("paper_trading", True),
            "auto_execute": settings.get("auto_execute", False),
            "note": "수동 즉시실행(버튼)은 paper_trading 무시하고 KIS 실주문 (2026-02-21 수정)",
            "min_confidence": settings.get("min_confidence", 65),
            "order_size": settings.get("order_size", 0),
        },
        "6_recent_orders": {
            "count": len(history),
            "last_5": [{
                "date": h.get("date", ""),
                "ticker": h.get("ticker", ""),
                "action": h.get("action", ""),
                "status": h.get("status", ""),
            } for h in history[:5]],
        },
    }

    all_ok = all(
        pipeline[k]["status"] == "OK"
        for k in ["1_ai_connection", "2_watchlist", "4_kis_connection"]
    )

    return {
        "overall": "READY" if all_ok else "NOT READY",
        "pipeline": pipeline,
        "quick_diagnosis": (
            "모든 단계 정상 — 즉시분석 버튼으로 매매 가능"
            if all_ok else
            " / ".join([
                f"[{k}] {pipeline[k]['status']}"
                for k in pipeline
                if pipeline[k]["status"] != "OK"
            ])
        ),
    }


@router.get("/api/debug/fx-rate")
async def debug_fx_rate():
    """환율 상태 디버그 — 현재 환율, 마지막 갱신 시간, 수동 갱신."""
    current_rate = _get_fx_rate()
    last_update = app_state.last_fx_update
    since_update = time.time() - last_update if last_update > 0 else -1
    interval = _fx_update_interval()
    return {
        "current_rate": current_rate,
        "last_updated": datetime.fromtimestamp(last_update, tz=KST).isoformat() if last_update > 0 else "갱신 안됨 (기본값 사용 중)",
        "seconds_since_update": round(since_update) if since_update >= 0 else None,
        "next_update_in": max(0, round(interval - since_update)) if since_update >= 0 else "미정",
        "source": "yfinance (USDKRW=X)",
    }


@router.post("/api/debug/fx-rate/refresh")
async def refresh_fx_rate():
    """환율 즉시 갱신."""
    new_rate = await _update_fx_rate()
    if new_rate:
        return {"success": True, "rate": new_rate}
    return {"success": False, "rate": _get_fx_rate(), "message": "갱신 실패 — 기존 값 유지"}


@router.get("/api/debug/server-logs")
async def debug_server_logs(lines: int = 50, service: str = "corthex"):
    """서버 로그 디버그 — SSH 터널 또는 localhost에서만 접근 가능.
    Cloudflare를 우회하여 서버 로그를 확인할 수 있습니다.
    service: corthex(앱 로그), nginx-error, nginx-access
    """
    log_commands = {
        "corthex": f"journalctl -u corthex --no-pager -n {min(lines, 200)} --output=short-iso",
        "nginx-error": f"tail -n {min(lines, 200)} /var/log/nginx/error.log",
        "nginx-access": f"tail -n {min(lines, 200)} /var/log/nginx/access.log",
    }
    cmd = log_commands.get(service)
    if not cmd:
        return {"error": f"unknown service: {service}", "available": list(log_commands.keys())}
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        log_lines = result.stdout.strip().split("\n") if result.stdout else []
        return {
            "service": service,
            "lines": len(log_lines),
            "logs": log_lines[-min(lines, 200):],
            "stderr": result.stderr[:500] if result.stderr else None,
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout (10s)", "service": service}
    except Exception as e:
        return {"error": str(e), "service": service}
