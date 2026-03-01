"""ARGOS API — DB 캐시 서빙 + 신뢰도 서버 계산 + 정보국 상태 + 진단.

비유: 정보국 창구 — ARGOS가 수집한 주가/뉴스/공시/매크로 데이터를
CEO에게 보여주는 읽기 전용 API. AI 호출 없이 서버에서 직접 계산.
"""
import asyncio
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from db import get_connection, load_setting
from config_loader import _load_data, KST
from argos_collector import (
    _argos_collect_prices_safe,
    _argos_collect_news_safe,
    _argos_collect_dart_safe,
    _argos_collect_macro_safe,
    _argos_collect_financial_safe,
    _argos_collect_sector_safe,
    _argos_collect_macro,
)

logger = logging.getLogger("corthex")

router = APIRouter(tags=["argos"])


# ── arm_server 참조 헬퍼 ──
def _ms():
    """arm_server 모듈 참조."""
    return sys.modules.get("arm_server") or sys.modules.get("web.arm_server")


def _compute_calibration_factor(lookback: int = 20) -> dict:
    ms = _ms()
    fn = getattr(ms, "_compute_calibration_factor", None) if ms else None
    return fn(lookback) if fn else {"factor": 1.0}


# ═══════════════════════════════════════════════════════════════
# ARGOS API — DB 캐시 서빙 (Phase 6-6) + 신뢰도 서버 계산 (Phase 6-7)
# + 정보국 상태 API (Phase 6-8)
# ═══════════════════════════════════════════════════════════════

@router.get("/api/argos/status")
async def argos_status():
    """ARGOS 수집 레이어 현황 — 수집 시각, 오류, 총 건수."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT data_type, last_collected, last_error, total_count, updated_at "
            "FROM argos_collection_status"
        ).fetchall()
        price_cnt     = conn.execute("SELECT COUNT(*) FROM argos_price_history").fetchone()[0]
        news_cnt      = conn.execute("SELECT COUNT(*) FROM argos_news_cache").fetchone()[0]
        dart_cnt      = conn.execute("SELECT COUNT(*) FROM argos_dart_filings").fetchone()[0]
        macro_cnt     = conn.execute("SELECT COUNT(*) FROM argos_macro_data").fetchone()[0]
        try:
            financial_cnt = conn.execute("SELECT COUNT(*) FROM argos_financial_data").fetchone()[0]
        except Exception:
            financial_cnt = 0
        try:
            sector_cnt = conn.execute("SELECT COUNT(*) FROM argos_sector_data").fetchone()[0]
        except Exception:
            sector_cnt = 0
        conn.close()

        status_map = {r[0]: {
            "last_collected": r[1], "last_error": r[2],
            "total_count": r[3], "updated_at": r[4]
        } for r in rows}

        return {"ok": True, "status": status_map, "db_counts": {
            "price": price_cnt, "news": news_cnt, "dart": dart_cnt,
            "macro": macro_cnt, "financial": financial_cnt, "sector": sector_cnt
        }}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/argos/price/{ticker}")
async def argos_price(ticker: str, days: int = 30):
    """ARGOS DB에서 주가 이력 서빙 — AI 도구 호출 불필요."""
    try:
        conn = get_connection()
        cutoff = (datetime.now(KST) - timedelta(days=min(days, 90))).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT trade_date, open_price, high_price, low_price, close_price, volume, change_pct
               FROM argos_price_history
               WHERE ticker=? AND trade_date >= ?
               ORDER BY trade_date DESC LIMIT 90""",
            (ticker.upper(), cutoff)
        ).fetchall()
        conn.close()
        data = [{"date": r[0], "open": r[1], "high": r[2], "low": r[3],
                 "close": r[4], "volume": r[5], "change_pct": r[6]} for r in rows]
        return {"ok": True, "ticker": ticker, "count": len(data), "prices": data,
                "source": "ARGOS DB (서버 캐시)"}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/argos/news/{keyword}")
async def argos_news(keyword: str, days: int = 7):
    """ARGOS DB에서 뉴스 캐시 서빙."""
    try:
        conn = get_connection()
        cutoff = (datetime.now(KST) - timedelta(days=min(days, 30))).isoformat()
        rows = conn.execute(
            """SELECT title, description, link, pub_date, source
               FROM argos_news_cache
               WHERE keyword=? AND pub_date >= ?
               ORDER BY pub_date DESC LIMIT 50""",
            (keyword, cutoff)
        ).fetchall()
        conn.close()
        data = [{"title": r[0], "desc": r[1], "link": r[2],
                 "pub_date": r[3], "source": r[4]} for r in rows]
        return {"ok": True, "keyword": keyword, "count": len(data), "news": data,
                "source": "ARGOS DB (서버 캐시)"}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/argos/dart/{ticker}")
async def argos_dart(ticker: str, days: int = 90):
    """ARGOS DB에서 DART 공시 서빙."""
    try:
        conn = get_connection()
        cutoff = (datetime.now(KST) - timedelta(days=min(days, 90))).strftime("%Y%m%d")
        rows = conn.execute(
            """SELECT corp_name, report_nm, rcept_no, flr_nm, rcept_dt
               FROM argos_dart_filings
               WHERE ticker=? AND rcept_dt >= ?
               ORDER BY rcept_dt DESC LIMIT 50""",
            (ticker.upper(), cutoff)
        ).fetchall()
        conn.close()
        data = [{"corp_name": r[0], "report_nm": r[1], "rcept_no": r[2],
                 "flr_nm": r[3], "rcept_dt": r[4]} for r in rows]
        return {"ok": True, "ticker": ticker, "count": len(data), "filings": data,
                "source": "ARGOS DB (서버 캐시)"}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/argos/macro")
async def argos_macro(days: int = 30):
    """ARGOS DB에서 매크로 지표 서빙."""
    try:
        conn = get_connection()
        cutoff = (datetime.now(KST) - timedelta(days=min(days, 365))).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT indicator, trade_date, value, source
               FROM argos_macro_data
               WHERE trade_date >= ?
               ORDER BY indicator, trade_date DESC""",
            (cutoff,)
        ).fetchall()
        conn.close()
        grouped = defaultdict(list)
        for r in rows:
            grouped[r[0]].append({"date": r[1], "value": r[2], "source": r[3]})
        return {"ok": True, "macro": dict(grouped), "source": "ARGOS DB (서버 캐시)"}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/argos/confidence/{ticker}")
async def argos_confidence(ticker: str):
    """Phase 6-7: 서버 계산 신뢰도 — Quant + Calibration + Bayesian + ELO.
    AI는 이 값을 받아 뉴스 맥락으로 ±20%p 조정만 하면 됨.
    """
    try:
        conn = get_connection()

        # ① 최근 주가 데이터 (90일)
        price_rows = conn.execute(
            """SELECT close_price, volume, change_pct FROM argos_price_history
               WHERE ticker=? ORDER BY trade_date DESC LIMIT 90""",
            (ticker.upper(),)
        ).fetchall()

        quant_score = None
        if len(price_rows) >= 14:
            closes = [r[0] for r in reversed(price_rows)]
            volumes = [r[1] for r in reversed(price_rows)]

            # RSI(14)
            gains, losses = [], []
            for i in range(1, len(closes)):
                d = closes[i] - closes[i-1]
                (gains if d > 0 else losses).append(abs(d))
            avg_gain = sum(gains[-14:]) / 14 if gains else 0.001
            avg_loss = sum(losses[-14:]) / 14 if losses else 0.001
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            # 20일 MA
            ma20 = sum(closes[-20:]) / min(20, len(closes))
            cur = closes[-1]
            above_ma = cur > ma20

            # 볼린저밴드
            if len(closes) >= 20:
                std20 = (sum((x - ma20)**2 for x in closes[-20:]) / 20) ** 0.5
                bb_upper = ma20 + 2 * std20
                bb_lower = ma20 - 2 * std20
                bb_pos = (cur - bb_lower) / (bb_upper - bb_lower) * 100 if bb_upper != bb_lower else 50
            else:
                bb_pos = 50

            # 거래량 비율 (최근 5일 / 이전 20일 평균)
            if len(volumes) >= 25:
                vol_ratio = sum(volumes[-5:]) / 5 / (sum(volumes[-25:-5]) / 20 + 0.001)
            else:
                vol_ratio = 1.0

            # Quant Score 계산 (0~99)
            rsi_score = max(0, min(100, (rsi - 30) / 40 * 100)) if rsi < 70 else max(0, (90 - rsi) * 3)
            ma_score = 60 if above_ma else 30
            bb_score = max(0, min(100, 100 - abs(bb_pos - 50) * 2))
            vol_score = min(100, vol_ratio * 50)
            trend_score = max(0, min(100, 50 + (cur - closes[-10]) / closes[-10] * 100)) if len(closes) >= 10 else 50
            quant_score = round((rsi_score * 0.25 + ma_score * 0.25 + bb_score * 0.2 + vol_score * 0.15 + trend_score * 0.15))

        # ② Calibration Factor
        calibration = _compute_calibration_factor(20)
        cal_factor = calibration.get("factor", 1.0)

        # ③ Bayesian 버킷 보정
        bayesian_adj = 0
        try:
            buckets = conn.execute(
                """SELECT bucket_label, actual_win_rate, sample_count
                   FROM confidence_calibration ORDER BY created_at DESC LIMIT 10"""
            ).fetchall()
            if buckets and quant_score is not None:
                qs_norm = quant_score  # 0~99
                best = min(buckets, key=lambda b: abs(float(b[0].split("_")[0] if "_" in str(b[0]) else b[0]) - qs_norm), default=None)
                if best and best[2] >= 5:
                    actual_wr = float(best[1]) * 100  # 실제 승률(%)
                    bayesian_adj = round(actual_wr - 50, 1)  # 50% 기준 편차
        except Exception:
            pass

        # ④ ELO 가중치 (금융분석팀장 평균 ELO → 신뢰도 가중)
        elo_adj = 0
        try:
            from db import get_analyst_elo
            elos = [get_analyst_elo(aid)["elo_rating"] for aid in ["fin_analyst"]]
            avg_elo = sum(elos) / len(elos)
            # ELO 1500 기준: 100점 차이 = ±3%p
            elo_adj = round((avg_elo - 1500) / 100 * 3, 1)
        except Exception:
            pass

        conn.close()

        # 최종 서버 신뢰도
        base_conf = quant_score if quant_score is not None else 50
        server_conf = round(base_conf * cal_factor + bayesian_adj + elo_adj)
        server_conf = max(10, min(95, server_conf))

        return {
            "ok": True,
            "ticker": ticker,
            "server_confidence": server_conf,
            "components": {
                "quant_score": quant_score,
                "calibration_factor": round(cal_factor, 3),
                "bayesian_adj": bayesian_adj,
                "elo_adj": elo_adj,
            },
            "ai_instruction": f"서버 계산 신뢰도 {server_conf}%. 뉴스/맥락 분석 후 ±20%p 범위 내에서 조정 (이탈 시 이유 명시).",
            "price_bars_used": len(price_rows),
            "source": "ARGOS 서버 계산 (AI 호출 없음)"
        }
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/intelligence/status")
async def intelligence_status():
    """정보국 통합 상태 — 상단 상태바 + 정보국 탭 데이터 소스 (Phase 6-8)."""
    try:
        conn = get_connection()
        now_kst = datetime.now(KST)

        # ARGOS 수집 상태
        argos_rows = conn.execute(
            "SELECT data_type, last_collected, last_error FROM argos_collection_status"
        ).fetchall()
        argos_map = {r[0]: {"last": r[1], "error": r[2]} for r in argos_rows}

        # 활성 가격 트리거
        triggers = _load_data("price_triggers", [])
        active_triggers = [t for t in triggers if t.get("active", True)]

        # 오늘 AI 비용
        today_str = now_kst.strftime("%Y-%m-%d")
        cost_rows = conn.execute(
            """SELECT COALESCE(SUM(cost_usd), 0) FROM agent_calls
               WHERE created_at >= ?""",
            (today_str,)
        ).fetchone()
        today_cost = round(float(cost_rows[0] or 0), 4)

        week_ago = (now_kst - timedelta(days=7)).strftime("%Y-%m-%d")
        week_rows = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM agent_calls WHERE created_at >= ?",
            (week_ago,)
        ).fetchone()
        week_cost = round(float(week_rows[0] or 0), 4)

        # 최근 AI 활동 (교신로그 통합)
        recent_logs = conn.execute(
            """SELECT agent_id, message, level, timestamp FROM activity_logs
               ORDER BY timestamp DESC LIMIT 20"""
        ).fetchall()
        activity = [{"agent": r[0], "msg": r[1][:100], "level": r[2], "ts": r[3]} for r in recent_logs]

        # 최근 에러 (24시간)
        yesterday = (now_kst - timedelta(hours=24)).isoformat()
        error_logs = conn.execute(
            """SELECT agent_id, message, timestamp FROM activity_logs
               WHERE level='error' AND timestamp >= ?
               ORDER BY timestamp DESC LIMIT 10""",
            (yesterday,)
        ).fetchall()
        errors = [{"agent": r[0], "msg": r[1][:150], "ts": r[2]} for r in error_logs]

        # 팀장별 비용 (오늘)
        agent_costs = conn.execute(
            """SELECT agent_id, COALESCE(SUM(cost_usd), 0) as cost
               FROM agent_calls WHERE created_at >= ?
               GROUP BY agent_id ORDER BY cost DESC""",
            (today_str,)
        ).fetchall()
        per_agent = [{"agent": r[0], "cost": round(float(r[1]), 4)} for r in agent_costs]

        conn.close()

        # 데이터 수집 상태 판정
        price_ok = bool(argos_map.get("price", {}).get("last"))
        news_ok  = bool(argos_map.get("news", {}).get("last"))
        has_error = bool(errors)

        return {
            "ok": True,
            "timestamp": now_kst.isoformat(),
            "status_bar": {
                "data_ok": price_ok,
                "data_last": argos_map.get("price", {}).get("last", ""),
                "ai_ok": len(activity) > 0,
                "ai_last": activity[0]["ts"] if activity else "",
                "trigger_count": len(active_triggers),
                "today_cost_usd": today_cost,
                "has_error": has_error,
            },
            "argos": argos_map,
            "triggers": active_triggers[:20],
            "activity": activity,
            "errors": errors,
            "costs": {
                "today_usd": today_cost,
                "week_usd": week_cost,
                "per_agent": per_agent,
            },
        }
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/argos/collect/now")
async def argos_collect_now(req: Request):
    """수동으로 ARGOS 수집을 즉시 트리거합니다."""
    body = await req.json() if req.headers.get("content-type", "").startswith("application/json") else {}
    data_type = body.get("type", "all")
    results = {}
    if data_type in ("all", "price"):
        results["price"] = await _argos_collect_prices_safe() or "실행됨"
    if data_type in ("all", "news"):
        results["news"] = await _argos_collect_news_safe() or "실행됨"
    if data_type in ("all", "dart"):
        results["dart"] = await _argos_collect_dart_safe() or "실행됨"
    if data_type in ("all", "macro"):
        results["macro"] = await _argos_collect_macro_safe() or "실행됨"
    if data_type in ("all", "financial"):
        results["financial"] = await _argos_collect_financial_safe() or "실행됨"
    if data_type in ("all", "sector"):
        results["sector"] = await _argos_collect_sector_safe() or "실행됨"
    return {"ok": True, "triggered": results}


@router.get("/api/debug/argos-diag")
async def argos_diagnostic():
    """ARGOS 수집 문제 진단 — 각 단계별 성공/실패 리포트. 항목당 15초 타임아웃."""
    DIAG_TIMEOUT = 15
    diag = {}
    # 1) DB 연결
    try:
        conn = get_connection()
        diag["db"] = "OK"
        conn.close()
    except Exception as e:
        diag["db"] = f"FAIL: {e}"
        return {"ok": False, "diag": diag}

    # 2) watchlist
    wl = _load_data("trading_watchlist", [])
    diag["watchlist"] = f"{len(wl)}종목"
    kr = [w for w in wl if w.get("market", "KR") == "KR"]
    us = [w for w in wl if w.get("market") == "US"]
    diag["kr_tickers"] = [w["ticker"] for w in kr]
    diag["us_tickers"] = [w["ticker"] for w in us]

    # 3) pykrx 테스트 (삼성전자 3일)
    try:
        from pykrx import stock as _pk
        today = datetime.now(KST).strftime("%Y%m%d")
        start = (datetime.now(KST) - timedelta(days=3)).strftime("%Y%m%d")
        df = await asyncio.wait_for(
            asyncio.to_thread(_pk.get_market_ohlcv_by_date, start, today, "005930"),
            timeout=DIAG_TIMEOUT,
        )
        diag["pykrx"] = f"OK ({len(df)}행)" if df is not None and not df.empty else "EMPTY"
    except asyncio.TimeoutError:
        diag["pykrx"] = f"TIMEOUT ({DIAG_TIMEOUT}s)"
    except Exception as e:
        diag["pykrx"] = f"FAIL: {e}"

    # 4) yfinance 테스트 (NVDA)
    try:
        import yfinance as yf
        t = yf.Ticker("NVDA")
        h = await asyncio.wait_for(
            asyncio.to_thread(lambda: t.history(period="3d")),
            timeout=DIAG_TIMEOUT,
        )
        diag["yfinance"] = f"OK ({len(h)}행)" if h is not None and not h.empty else "EMPTY"
    except asyncio.TimeoutError:
        diag["yfinance"] = f"TIMEOUT ({DIAG_TIMEOUT}s)"
    except Exception as e:
        diag["yfinance"] = f"FAIL: {e}"

    # 5) ARGOS 테이블 레코드 수
    try:
        conn = get_connection()
        diag["price_rows"] = conn.execute("SELECT COUNT(*) FROM argos_price_history").fetchone()[0]
        diag["news_rows"] = conn.execute("SELECT COUNT(*) FROM argos_news_cache").fetchone()[0]
        diag["dart_rows"] = conn.execute("SELECT COUNT(*) FROM argos_dart_filings").fetchone()[0]
        diag["macro_rows"] = conn.execute("SELECT COUNT(*) FROM argos_macro_data").fetchone()[0]
        diag["status_rows"] = conn.execute("SELECT COUNT(*) FROM argos_collection_status").fetchone()[0]
        conn.close()
    except Exception as e:
        diag["db_check"] = f"FAIL: {e}"

    # 6) 매크로 수동 테스트 (타임아웃 있음)
    try:
        n = await asyncio.wait_for(_argos_collect_macro(), timeout=60)
        diag["macro_test"] = f"OK ({n}건 수집)"
    except asyncio.TimeoutError:
        diag["macro_test"] = "TIMEOUT (60s)"
    except Exception as e:
        diag["macro_test"] = f"FAIL: {e}"

    return {"ok": True, "diag": diag}
