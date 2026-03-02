"""
CORTHEX HQ - ARM Server

Oracle Cloud ARM 서버 (4코어 24GB)에서 대시보드를 서비스합니다.
전체 백엔드의 핵심 API만 제공하여 대시보드 UI가 정상 작동하도록 함.
텔레그램 봇도 여기서 24시간 구동됩니다.
"""
import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid as _uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

# DB + WS 모듈을 같은 폴더에서 임포트
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ws_manager import wm  # WebSocket/SSE 브로드캐스트 매니저
from state import app_state  # 전역 상태 관리 (관리사무소)
from db import (
    init_db, get_connection, save_message, create_task, get_task as db_get_task,
    update_task, list_tasks, toggle_bookmark as db_toggle_bookmark,
    get_dashboard_stats, save_activity_log, list_activity_logs,
    save_archive, list_archives, get_archive as db_get_archive, delete_archive as db_delete_archive,
    save_setting, load_setting, get_today_cost,
    save_conversation_message, load_conversation_messages, clear_conversation_messages,
    load_conversation_messages_by_id,
    delete_task as db_delete_task, bulk_delete_tasks, bulk_archive_tasks,
    set_task_tags, mark_task_read, bulk_mark_read,
    save_quality_review, get_quality_stats,
    save_collaboration_log,
)

# ── 설정/유틸/에이전트 로딩 (config_loader.py에서 분리) ──
from config_loader import (
    _log, _diag, _extract_title_summary, logger,
    KST, BASE_DIR, TEMPLATE_DIR, CONFIG_DIR, DATA_DIR, KNOWLEDGE_DIR, ARCHIVE_DIR,
    get_build_number, _load_config, _load_agents, _load_tools,
    _AGENTS_DETAIL, _TOOLS_LIST,
    _load_data, _save_data, _save_config_file, _sync_agent_defaults_to_db,
    _AGENTS_FALLBACK, _build_agents_from_yaml, AGENTS,
    MODEL_REASONING_MAP, MODEL_MAX_TOKENS_MAP,
    _PROJECT_ROOT,
    load_workspace_profiles, get_workspace_profile,
)

try:
    from ai_handler import (
        init_ai_client, is_ai_ready, ask_ai, select_model,
        classify_task, get_available_providers,
        _load_tool_schemas,  # 도구 스키마 로딩 (function calling용)
        batch_submit, batch_check, batch_retrieve,  # Batch API
        batch_submit_grouped,  # 프로바이더별 그룹 배치 제출 (배치 체인용)
    )
except ImportError:
    def init_ai_client(): return False
    def is_ai_ready(): return False
    async def ask_ai(*a, **kw): return {"error": "ai_handler 미설치"}
    def select_model(t, override=None): return override or "claude-sonnet-4-6"
    async def classify_task(t): return {"agent_id": "chief_of_staff", "reason": "ai_handler 미설치", "cost_usd": 0}
    def get_available_providers(): return {"anthropic": False, "google": False, "openai": False}
    def _load_tool_schemas(allowed_tools=None): return {}
    async def batch_submit(*a, **kw): return {"error": "ai_handler 미설치"}
    async def batch_check(*a, **kw): return {"error": "ai_handler 미설치"}
    async def batch_retrieve(*a, **kw): return {"error": "ai_handler 미설치"}
    async def batch_submit_grouped(*a, **kw): return [{"error": "ai_handler 미설치"}]

# 품질검수 엔진
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
# 품질검수(QualityGate) → agent_router.py로 이관 (P8)

try:
    from kis_client import (
        get_current_price as _kis_price,
        place_order as _kis_order,
        get_balance as _kis_balance,
        is_configured as _kis_configured,
        get_overseas_price as _kis_us_price,
        place_overseas_order as _kis_us_order,
        place_mock_order as _kis_mock_order,
        place_mock_overseas_order as _kis_mock_us_order,
        get_mock_balance as _kis_mock_balance,
        is_mock_configured as _kis_mock_configured,
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
    async def _kis_mock_order(ticker, action, qty, price=0): return {"success": False, "message": "kis_client 미설치", "order_no": ""}
    async def _kis_mock_us_order(symbol, action, qty, price=0, exchange=""): return {"success": False, "message": "kis_client 미설치", "order_no": ""}
    async def _kis_mock_balance(): return {"success": False, "cash": 0, "holdings": [], "total_eval": 0}
    def _kis_mock_configured(): return False
    _log("[KIS] kis_client 모듈 로드 실패 — 모의투자 모드")

# ── ToolPool → app_state.tool_pool 직접 사용 ──

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

# -- telegram bot -> telegram_bot.py (P9) --


app = FastAPI(title="CORTHEX HQ")

# ── 전체 활동 로깅 미들웨어 (CEO 요청: 웹에서 일어나는 일 전부 로그) ──
# 정적 파일, 헬스체크 등 노이즈를 제외한 모든 API 요청을 activity_log에 기록
_LOG_SKIP_PREFIXES = ("/static", "/favicon", "/deploy-status", "/ws", "/api/comms")
_LOG_SKIP_EXACT = {"/", "/api/health", "/api/agents/status", "/api/dashboard/stats",
                   "/api/activity-logs", "/api/batch/chain/status",
                   "/api/budget", "/api/trading/summary", "/api/trading/history",
                   "/api/trading/strategies", "/api/trading/signals",
                   "/api/trading/watchlist/prices"}
_LOG_DESCRIPTION: dict[str, str] = {
    # 채팅/AI
    "POST /api/chat": "💬 채팅 메시지 전송",
    "POST /api/chat/send": "💬 채팅 메시지 전송",
    # 에이전트
    "GET /api/agents": "📋 에이전트 목록 조회",
    "GET /api/agents/status": "🔵 에이전트 상태 조회",
    # 자동매매
    "POST /api/trading/bot/run-now": "🚀 즉시 매매 실행",
    "POST /api/trading/bot/toggle": "⚡ 자동매매 봇 ON/OFF",
    "GET /api/trading/portfolio": "💰 포트폴리오 조회",
    "GET /api/trading/signals": "📊 매매 시그널 조회",
    "GET /api/trading/watchlist": "👁️ 관심종목 조회",
    "POST /api/trading/watchlist": "👁️ 관심종목 추가",
    # KIS
    "GET /api/kis/balance": "💳 KIS 잔고 조회",
    "GET /api/kis/status": "🔌 KIS 연결 상태",
    # 배치
    "POST /api/batch/chain/start": "⛓️ 배치 체인 시작",
    "GET /api/batch/chain/status": "⛓️ 배치 체인 상태",
    # 콘텐츠 파이프라인
    "GET /api/content-pipeline": "📰 콘텐츠 파이프라인 현황",
    "POST /api/content-pipeline/run": "🚀 콘텐츠 파이프라인 실행",
    "POST /api/content-pipeline/approve": "✅ 콘텐츠 승인",
    "POST /api/content-pipeline/reject": "❌ 콘텐츠 거절",
    # 아카이브
    "GET /api/archives": "📁 아카이브 조회",
    # 작업
    "POST /api/tasks": "📝 작업 생성",
    "GET /api/tasks": "📝 작업 목록 조회",
    # 설정
    "GET /api/settings": "⚙️ 설정 조회",
    "POST /api/settings": "⚙️ 설정 저장",
    # 워크플로우
    "POST /api/workflows/run": "🔄 워크플로우 실행",
    # 디버그
    "GET /api/debug/kis-token": "🔍 KIS 토큰 디버그",
    "GET /api/debug/auto-trading-pipeline": "🔍 자동매매 파이프라인 디버그",
}

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

class ActivityLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        path = request.url.path
        method = request.method

        # 노이즈 제외
        if path in _LOG_SKIP_EXACT or any(path.startswith(p) for p in _LOG_SKIP_PREFIXES):
            return await call_next(request)

        start = time.time()
        response = await call_next(request)
        elapsed = time.time() - start

        # 로그 기록 (비동기 WebSocket broadcast는 startup 이후에만 가능)
        key = f"{method} {path}"
        desc = _LOG_DESCRIPTION.get(key, "")
        status = response.status_code
        level = "info" if status < 400 else ("warning" if status < 500 else "error")

        # 짧은 요약 생성
        if desc:
            action = f"{desc} ({elapsed:.1f}s)"
        else:
            action = f"🌐 {method} {path} → {status} ({elapsed:.1f}s)"

        try:
            log_entry = save_activity_log("system", action, level)
            # 시스템 HTTP 로그는 브로드캐스트하지 않음 (노이즈 감소)
            # 에이전트 활동로그만 실시간 전송
        except Exception as e:
            logger.debug("활동 로그 저장 실패: %s", e)

        return response

app.add_middleware(ActivityLogMiddleware)

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(TEMPLATE_DIR, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # BUILD_NUMBER_PLACEHOLDER를 실제 빌드 번호로 치환
    build_number = get_build_number()
    html_content = html_content.replace("BUILD_NUMBER_PLACEHOLDER", build_number)

    return HTMLResponse(
        content=html_content,
        headers={"Cache-Control": "no-cache, must-revalidate", "Vary": "Accept-Encoding"},
    )


@app.get("/sw.js")
async def service_worker():
    """PWA Service Worker — root scope 필요."""
    sw_path = os.path.join(os.path.dirname(__file__), "static", "sw.js")
    from starlette.responses import FileResponse
    return FileResponse(sw_path, media_type="application/javascript")


@app.get("/deploy-status.json")
async def deploy_status():
    """배포 상태 JSON (deploy.yml이 /var/www/html/에 생성한 파일 읽기)."""
    import json as _json
    for path in ["/var/www/html/deploy-status.json", os.path.join(BASE_DIR, "deploy-status.json")]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return _json.load(f)
            except Exception as e:
                logger.debug("배포 상태 파일 읽기 실패 (%s): %s", path, e)
    return {"build": get_build_number(), "time": datetime.now(KST).isoformat(), "status": "success", "commit": ""}

# ── WebSocket 관리 (wm 싱글턴 사용) ──
# 하위 호환: connected_clients는 wm 내부 리스트를 참조
connected_clients = wm._connections

# ── 백그라운드 에이전트 태스크 (새로고침해도 안 끊김) ──
# → app_state로 이동. 하위 호환 alias (dict/list는 공유 참조로 동작)
_bg_tasks = app_state.bg_tasks
_bg_results = app_state.bg_results
# app_state.bg_current_task_id는 primitive(재할당)이므로 app_state.bg_current_task_id 직접 사용


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    wm._connections.append(ws)
    # v5: WebSocket 연결 시 session_role 확인 (token 쿼리 파라미터로 전달)
    from handlers.auth_handler import _get_session
    _ws_token = ws.query_params.get("token", "")
    _ws_session = _get_session(_ws_token) if _ws_token else None
    ws_session_role: str = _ws_session.get("role", "ceo") if _ws_session else "ceo"
    try:
        # 연결 시 초기 상태 전송 (activity_log가 아닌 system_info 이벤트 사용 — 통신로그에 안 뜨게)
        now = datetime.now(KST).strftime("%H:%M:%S")
        await ws.send_json({
            "event": "system_info",
            "data": {
                "message": "시스템 연결 완료. 대기 중입니다.",
                "time": now,
            }
        })
        # 연결 직후 오늘 비용을 전송 → 우측 상단 $0.0000 문제 해결
        try:
            today_cost = get_today_cost()
            await ws.send_json({
                "event": "cost_update",
                "data": {"total_cost": today_cost, "total_tokens": 0},
            })
        except Exception as e:
            logger.debug("WS 비용 전송 실패: %s", e)
        # 새로고침 복구: 진행 중인 백그라운드 태스크가 있으면 상태 전송
        if app_state.bg_current_task_id and app_state.bg_current_task_id in _bg_tasks:
            try:
                await ws.send_json({
                    "event": "agent_status",
                    "data": {
                        "agent_id": "chief_of_staff",
                        "status": "working",
                        "progress": 0.5,
                        "detail": "에이전트 작업 진행중 (새로고침 복구)",
                        "task_id": app_state.bg_current_task_id,
                    },
                })
            except Exception as e:
                logger.debug("WS 상태 전송 실패: %s", e)
        while True:
            data = await ws.receive_text()
            # 메시지 크기 제한 (64KB) — 비정상적으로 큰 페이로드 차단
            if len(data) > 65536:
                await ws.send_json({"event": "error", "data": {"message": "메시지 크기 초과 (64KB 제한)"}})
                continue
            msg = json.loads(data)
            # 메시지를 받으면 DB에 저장 + 응답
            if msg.get("type") == "cancel":
                # 취소 요청: DB에서 running 태스크를 cancelled로 변경
                cancel_tid = msg.get("task_id")
                if cancel_tid:
                    update_task(cancel_tid, status="failed",
                                result_summary="CEO 취소", success=0)
                else:
                    # task_id 없으면 running 태스크 전부 취소
                    try:
                        running = list_tasks(status="running", limit=10)
                        for rt in running:
                            update_task(rt["task_id"], status="failed",
                                        result_summary="CEO 취소", success=0)
                    except Exception as e:
                        logger.debug("태스크 일괄 취소 실패: %s", e)
                continue
            if msg.get("type") == "command":
                cmd_text = (msg.get("content") or msg.get("text", "")).strip()
                use_batch = msg.get("batch", False)
                ws_target_agent_id = msg.get("target_agent_id", None)
                ws_conversation_id = msg.get("conversation_id", None)
                if cmd_text:
                    # DB에 메시지 + 작업 저장
                    task = create_task(cmd_text, source="websocket_batch" if use_batch else "websocket")
                    save_message(cmd_text, source="websocket",
                                 task_id=task["task_id"])
                    # 작업 접수 이벤트 브로드캐스트
                    mode_label = "📦 배치" if use_batch else "⚡ 실시간"
                    log_entry = save_activity_log(
                        "chief_of_staff",
                        f"[웹] {mode_label} 명령 접수: {cmd_text[:50]}{'...' if len(cmd_text) > 50 else ''} (#{task['task_id']})",
                    )
                    await wm.broadcast_multi([
                        ("task_accepted", task),
                        ("activity_log", log_entry),
                    ])

                    # 토론 명령: 백그라운드 실행 (채팅 차단 없음)
                    _stripped = cmd_text.strip()
                    is_debate_cmd = _stripped.startswith("/토론") or _stripped.startswith("/심층토론")
                    if is_ai_ready() and is_debate_cmd:
                        debate_rounds = 3 if _stripped.startswith("/심층토론") else 2
                        await ws.send_json({
                            "event": "result",
                            "data": {
                                "content": (
                                    f"🗣️ **임원 토론을 시작합니다** ({debate_rounds}라운드)\n\n"
                                    f"팀장 6명이 토론 중입니다. 2~5분 소요됩니다.\n"
                                    f"**토론이 완료되면 자동으로 결과를 전달해드립니다.**\n"
                                    f"💡 토론이 진행되는 동안 채팅을 계속 사용할 수 있습니다."
                                ),
                                "sender_id": "chief_of_staff",
                                "handled_by": f"임원 토론 시작 ({debate_rounds}라운드)",
                                "time_seconds": 0,
                                "cost": 0,
                            }
                        })

                        async def _run_debate_bg(text, task_id):
                            try:
                                update_task(task_id, status="running")
                                debate_result = await _process_ai_command(text, task_id)
                                if "error" in debate_result:
                                    update_task(task_id, status="failed",
                                                result_summary=str(debate_result.get("error", ""))[:200],
                                                success=0)
                                else:
                                    update_task(task_id, status="completed",
                                                result_summary=_extract_title_summary(debate_result.get("content", "") or ""),
                                                success=1,
                                                cost_usd=debate_result.get("total_cost_usd", debate_result.get("cost_usd", 0)))
                                if "error" in debate_result:
                                    await wm.broadcast("result", {
                                        "content": f"❌ 토론 실패: {debate_result['error']}",
                                        "sender_id": "chief_of_staff",
                                        "time_seconds": 0,
                                        "cost": 0,
                                    })
                                else:
                                    await wm.broadcast("result", {
                                        "content": debate_result.get("content", ""),
                                        "sender_id": debate_result.get("agent_id", "chief_of_staff"),
                                        "handled_by": debate_result.get("handled_by", "임원 토론"),
                                        "time_seconds": debate_result.get("time_seconds", 0),
                                        "cost": debate_result.get("total_cost_usd", debate_result.get("cost_usd", 0)),
                                    })
                                # 토론 결과도 텔레그램 CEO 전달
                                if "error" not in debate_result:
                                    await _forward_web_response_to_telegram(
                                        text,
                                        {
                                            "content": debate_result.get("content", ""),
                                            "handled_by": debate_result.get("handled_by", "임원 토론"),
                                            "cost": debate_result.get("total_cost_usd", debate_result.get("cost_usd", 0)),
                                        },
                                    )
                            except Exception as e:
                                _log(f"[DEBATE] 백그라운드 토론 오류: {e}")

                        asyncio.create_task(_run_debate_bg(cmd_text, task["task_id"]))
                        continue

                    # 실시간 모드: 백그라운드 태스크로 실행 (새로고침해도 안 끊김)
                    if is_ai_ready():
                        update_task(task["task_id"], status="running")
                        app_state.bg_current_task_id = task["task_id"]
                        asyncio.create_task(
                            _run_agent_bg(cmd_text, task["task_id"], ws_target_agent_id, ws_conversation_id,
                                          session_role=ws_session_role)
                        )
                    else:
                        update_task(task["task_id"], status="completed",
                                    result_summary="AI 미연결 — 접수만 완료",
                                    success=1, time_seconds=0.1)
                        await ws.send_json({
                            "event": "result",
                            "data": {
                                "content": "AI가 아직 연결되지 않았습니다. ANTHROPIC_API_KEY를 설정해주세요.",
                                "sender_id": "chief_of_staff",
                                "time_seconds": 0.1,
                                "cost": 0,
                            }
                        })
    except WebSocketDisconnect:
        wm.disconnect(ws)
    except Exception:
        wm.disconnect(ws)


# ── 백그라운드 에이전트 실행 (새로고침해도 안 끊김) ──

async def _run_agent_bg(cmd_text: str, task_id: str, target_agent_id: str | None = None,
                        conversation_id: str | None = None, session_role: str = "ceo"):
    """에이전트 작업을 백그라운드에서 실행. WebSocket 연결과 무관하게 동작."""

    _bg_tasks[task_id] = asyncio.current_task()
    try:
        result = await _process_ai_command(cmd_text, task_id, target_agent_id=target_agent_id,
                                           conversation_id=conversation_id, session_role=session_role)
        if "error" in result:
            update_task(task_id, status="failed",
                        result_summary=result.get("error", "")[:200],
                        success=0, time_seconds=0)
            _result_payload = {
                "content": f"❌ {result['error']}",
                "sender_id": result.get("agent_id", "chief_of_staff"),
                "handled_by": result.get("handled_by", "비서실장"),
                "time_seconds": 0, "cost": 0, "task_id": task_id,
            }
            try:
                save_conversation_message(
                    "result", content=_result_payload["content"],
                    sender_id=_result_payload["sender_id"],
                    handled_by=_result_payload["handled_by"],
                    time_seconds=0, cost=0, task_id=task_id, source="web",
                    conversation_id=conversation_id,
                )
            except Exception as e:
                logger.debug("에러 결과 대화 저장 실패: %s", e)
            _result_payload["_completed_at"] = time.time()
            _bg_results[task_id] = _result_payload
            await wm.broadcast("result", _result_payload)
        else:
            _result_data = {
                "content": result.get("content", ""),
                "sender_id": result.get("agent_id", "chief_of_staff"),
                "handled_by": result.get("handled_by", "비서실장"),
                "delegation": result.get("delegation", ""),
                "time_seconds": result.get("time_seconds", 0),
                "cost": result.get("total_cost_usd", result.get("cost_usd", 0)),
                "model": result.get("model", ""),
                "routing_method": result.get("routing_method", ""),
                "task_id": task_id,
            }
            try:
                save_conversation_message(
                    "result", content=_result_data["content"],
                    sender_id=_result_data["sender_id"],
                    handled_by=_result_data["handled_by"],
                    delegation=_result_data.get("delegation", ""),
                    model=_result_data.get("model", ""),
                    time_seconds=_result_data.get("time_seconds", 0),
                    cost=_result_data.get("cost", 0),
                    task_id=task_id, source="web",
                    conversation_id=conversation_id,
                )
            except Exception as e:
                logger.debug("결과 대화 저장 실패: %s", e)
            # 대화 세션 비용 누적
            if conversation_id and _result_data.get("cost"):
                try:
                    from db import get_conversation, update_conversation
                    _conv = get_conversation(conversation_id)
                    if _conv:
                        update_conversation(conversation_id,
                                            total_cost=_conv["total_cost"] + _result_data["cost"])
                except Exception:
                    pass
            _result_data["_completed_at"] = time.time()
            _bg_results[task_id] = _result_data
            await wm.broadcast("result", _result_data)
            update_task(task_id, status="completed",
                        result_summary=_extract_title_summary(result.get("content", "") or ""),
                        success=1,
                        time_seconds=result.get("time_seconds", 0),
                        cost_usd=result.get("total_cost_usd", result.get("cost_usd", 0)),
                        agent_id=result.get("agent_id", "chief_of_staff"))
            await _forward_web_response_to_telegram(cmd_text, _result_data)
    except Exception as e:
        _log(f"[BG-AGENT] 백그라운드 에이전트 오류: {e}")
        update_task(task_id, status="failed", result_summary=str(e)[:200], success=0, agent_id="chief_of_staff")
        _bg_results[task_id] = {"content": f"❌ 에이전트 오류: {e}", "sender_id": "chief_of_staff", "task_id": task_id, "_completed_at": time.time()}
        await wm.broadcast("result", _bg_results[task_id])
    finally:
        _bg_tasks.pop(task_id, None)
        app_state.bg_current_task_id = None


# ── 미디어 API → handlers/media_handler.py로 분리 ──
from handlers.media_handler import router as media_router
app.include_router(media_router)

# ── API 엔드포인트 ──

# ── 인증(Auth) API → handlers/auth_handler.py로 분리 ──
from handlers.auth_handler import router as auth_router, check_auth as _check_auth, get_auth_role, get_auth_org
app.include_router(auth_router)


# ── 워크스페이스 프로파일 API (v5.1 네이버 모델) ──
@app.get("/api/workspace-profile")
async def workspace_profile(request: Request):
    """로그인한 사용자의 워크스페이스 프로파일 반환."""
    role = get_auth_role(request)
    profile = get_workspace_profile(role)
    if not profile:
        # viewer 또는 미정의 role → 최소 권한 프로파일 반환 (404 금지)
        profile = get_workspace_profile("viewer") or {
            "label": "로그인 필요", "sidebarFilter": "", "mentionFilter": "",
            "orgScope": None, "showBulkModel": False, "showSatisfaction": False,
            "officeLayout": [], "showBuildNumber": False,
        }
    return profile


# ── 에이전트 관리 API → handlers/agent_handler.py로 분리 ──
from handlers.agent_handler import router as agent_router
app.include_router(agent_router)

# ── 도구(Tool) API → handlers/tools_handler.py로 분리 ──
from handlers.tools_handler import router as tools_router
app.include_router(tools_router)


@app.get("/api/dashboard")
async def get_dashboard(request: Request):
    now = datetime.now(KST).isoformat()
    _role = get_auth_role(request)
    _org = get_auth_org(request)

    # orgScope 기반 에이전트 필터 (누나는 자신의 에이전트 비용만)
    _scope_agents = None  # None = 전체
    if _org:
        _scope_agents = [a["agent_id"] for a in AGENTS if a.get("org") == _org or a.get("cli_owner") == _role]

    stats = get_dashboard_stats()
    today_cost = get_today_cost()

    # sister 계정: 자신의 에이전트 비용만 계산
    if _scope_agents is not None:
        try:
            _conn_cost = __import__("db").get_connection()
            _kst_midnight_c = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
            _today_start_c = _kst_midnight_c.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            _placeholders = ",".join("?" * len(_scope_agents))
            _row = _conn_cost.execute(
                f"SELECT COALESCE(SUM(cost_usd),0) FROM tasks WHERE agent_id IN ({_placeholders}) AND created_at >= ?",
                _scope_agents + [_today_start_c]
            ).fetchone()
            today_cost = float(_row[0]) if _row else 0.0
            _row_total = _conn_cost.execute(
                f"SELECT COALESCE(SUM(cost_usd),0) FROM tasks WHERE agent_id IN ({_placeholders})",
                _scope_agents
            ).fetchone()
            stats["total_cost"] = float(_row_total[0]) if _row_total else 0.0
            _conn_cost.close()
        except Exception as _e:
            logger.debug("orgScope 비용 계산 실패: %s", _e)

    daily_limit = float(load_setting("daily_budget_usd") or 7.0)

    # ── 프로바이더별 오늘 AI 호출 횟수 ──
    provider_calls = {"anthropic": 0, "openai": 0, "google": 0}
    try:
        conn = __import__("db").get_connection()
        # KST 자정을 UTC로 변환 (DB는 UTC ISO 형식으로 저장됨)
        _kst_midnight = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = _kst_midnight.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        rows = conn.execute(
            "SELECT provider, COUNT(*) FROM agent_calls "
            "WHERE created_at >= ? GROUP BY provider", (today_start,)
        ).fetchall()
        for row in rows:
            p = (row[0] or "").lower()
            if p in provider_calls:
                provider_calls[p] = row[1]
        conn.close()
    except Exception as e:
        logger.debug("프로바이더 호출 통계 조회 실패: %s", e)
    total_ai_calls = sum(provider_calls.values())

    # ── 배치 현황 ──
    chains = load_setting("batch_chains") or []
    batch_active = len([c for c in chains if c.get("status") in ("running", "pending")])
    batch_done = len([c for c in chains if c.get("status") == "completed"])

    # ── 도구 수 ──
    tool_count = 0
    try:
        pool = _init_tool_pool()
        if pool:
            tool_count = len(pool.registry)
    except Exception as e:
        logger.debug("도구 풀 카운트 실패: %s", e)
    if tool_count == 0:
        tool_count = len(_load_tool_schemas().get("anthropic", []))

    # ── API 키 상태 ──
    api_keys = {
        "anthropic": get_available_providers().get("anthropic", False),
        "google": get_available_providers().get("google", False),
        "openai": get_available_providers().get("openai", False),
        "notion": bool(os.getenv("NOTION_API_KEY", "")),
        "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN", "")),
    }
    api_connected = sum(1 for v in api_keys.values() if v)
    api_total = len(api_keys)

    # ── 시스템 상태 판단 (최근 1시간 실패 3건 이상 → 이상) ──
    recent_failed = 0
    try:
        one_hour_ago = (datetime.now(KST) - timedelta(hours=1)).isoformat()
        _conn_tmp = __import__("db").get_connection()
        recent_failed = _conn_tmp.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_at >= ? AND status = 'failed'",
            (one_hour_ago,),
        ).fetchone()[0]
        _conn_tmp.close()
    except Exception as e:
        logger.debug("최근 실패 건수 조회 실패: %s", e)
    if recent_failed >= 3:
        sys_status = "error"
    elif stats["running_count"] > 0:
        sys_status = "busy"
    else:
        sys_status = "ok"

    return {
        "total_agents": len(AGENTS),
        "active_agents": stats["running_count"],
        "idle_agents": len(AGENTS) - stats["running_count"],
        "total_tasks_today": stats["today_task_count"],
        "today_completed": stats["today_completed"],
        "today_failed": stats["today_failed"],
        "total_cost": stats["total_cost"],
        "today_cost": today_cost,
        "total_tokens": stats["total_tokens"],
        "notion_connected": bool(os.getenv("NOTION_API_KEY", "")),
        "system_status": sys_status,
        "uptime": now,
        "agents": AGENTS,
        "recent_completed": stats["recent_completed"],
        "api_keys": api_keys,
        # ── C안: 대시보드 확장 데이터 ──
        "provider_calls": provider_calls,
        "total_ai_calls": total_ai_calls,
        "daily_limit": daily_limit,
        "batch_active": batch_active,
        "batch_done": batch_done,
        "tool_count": tool_count,
        "api_connected": api_connected,
        "api_total": api_total,
    }


# ── 예산(Budget) · 모델모드 → handlers/agent_handler.py로 분리 ──

# ── 품질검수 통계 + 프리셋 → handlers/quality_handler.py, handlers/preset_handler.py로 분리 ──
from handlers.preset_handler import router as preset_router
app.include_router(preset_router)


# ── 성능/작업 (읽기 전용 — 실제 데이터는 풀 서버에서 생성) ──

@app.get("/api/performance")
async def get_performance():
    """에이전트별 실제 성능 통계를 DB에서 계산하여 반환합니다."""
    from db import get_connection
    conn = get_connection()
    try:
        # DB에서 에이전트별 작업 통계 집계
        rows = conn.execute("""
            SELECT agent_id,
                   COUNT(*) as total_tasks,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as completed,
                   SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed,
                   COALESCE(SUM(cost_usd), 0) as total_cost,
                   COALESCE(AVG(time_seconds), 0) as avg_time,
                   COALESCE(SUM(tokens_used), 0) as total_tokens
            FROM tasks
            WHERE agent_id IS NOT NULL AND agent_id != ''
            GROUP BY agent_id
            ORDER BY total_tasks DESC
        """).fetchall()

        # 에이전트 이름/역할 맵 구축
        agent_map = {a["agent_id"]: a for a in AGENTS}

        agents_perf = []
        total_llm_calls = 0
        total_cost = 0.0

        for row in rows:
            aid = row["agent_id"]
            info = agent_map.get(aid, {})
            total = row["total_tasks"]
            completed = row["completed"] or 0
            rate = round(completed / total * 100, 1) if total > 0 else 0

            agents_perf.append({
                "agent_id": aid,
                "name_ko": info.get("name_ko", aid),
                "role": info.get("role", "unknown"),
                "division": info.get("division", ""),
                "llm_calls": total,
                "tasks_completed": completed,
                "tasks_failed": row["failed"] or 0,
                "success_rate": rate,
                "cost_usd": round(row["total_cost"], 6),
                "avg_execution_seconds": round(row["avg_time"], 2),
                "total_tokens": row["total_tokens"] or 0,
            })
            total_llm_calls += total
            total_cost += row["total_cost"]

        # DB에 작업이 아직 없으면 에이전트 목록만 빈 값으로 반환
        if not agents_perf:
            for a in AGENTS:
                agents_perf.append({
                    "agent_id": a["agent_id"],
                    "name_ko": a["name_ko"],
                    "role": a["role"],
                    "division": a.get("division", ""),
                    "llm_calls": 0,
                    "tasks_completed": 0,
                    "tasks_failed": 0,
                    "success_rate": 0,
                    "cost_usd": 0,
                    "avg_execution_seconds": 0,
                    "total_tokens": 0,
                })

        # agent_calls 테이블 데이터를 agents_perf에 병합
        # (스페셜리스트 등 tasks에 없는 에이전트도 포함시키기 위함)
        try:
            from db import get_agent_performance
            agent_perf = get_agent_performance()
        except Exception:
            agent_perf = []

        perf_map = {ap["agent_id"]: ap for ap in agents_perf}
        for ap in agent_perf:
            aid = ap["agent_id"]
            if aid in perf_map:
                # tasks에 이미 있는 에이전트 → agent_calls 수치 합산
                existing = perf_map[aid]
                existing["llm_calls"] += ap.get("call_count", 0)
                existing["cost_usd"] = round(
                    existing["cost_usd"] + ap.get("total_cost", 0), 6
                )
                existing["total_tokens"] += (
                    ap.get("total_input_tokens", 0) + ap.get("total_output_tokens", 0)
                )
                total_llm_calls += ap.get("call_count", 0)
                total_cost += ap.get("total_cost", 0)
            else:
                # tasks에 없는 에이전트 (스페셜리스트 등) → 새로 추가
                info = agent_map.get(aid, {})
                call_count = ap.get("call_count", 0)
                cost = ap.get("total_cost", 0)
                new_entry = {
                    "agent_id": aid,
                    "name_ko": info.get("name_ko", aid),
                    "role": info.get("role", "unknown"),
                    "division": info.get("division", ""),
                    "llm_calls": call_count,
                    "tasks_completed": 0,
                    "tasks_failed": 0,
                    "success_rate": ap.get("success_rate", 0),
                    "cost_usd": round(cost, 6),
                    "avg_execution_seconds": ap.get("avg_time", 0),
                    "total_tokens": (
                        ap.get("total_input_tokens", 0)
                        + ap.get("total_output_tokens", 0)
                    ),
                }
                agents_perf.append(new_entry)
                perf_map[aid] = new_entry
                total_llm_calls += call_count
                total_cost += cost

        return {
            "agents": agents_perf,
            "total_llm_calls": total_llm_calls,
            "total_cost_usd": round(total_cost, 6),
        }
    except Exception as e:
        logger.error("성능 통계 조회 실패: %s", e)
        # 에러 시에도 에이전트 목록은 보여주기
        return {
            "agents": [{"agent_id": a["agent_id"], "name_ko": a["name_ko"],
                        "role": a["role"], "llm_calls": 0, "tasks_completed": 0,
                        "success_rate": 0, "cost_usd": 0, "avg_execution_seconds": 0}
                       for a in AGENTS],
            "total_llm_calls": 0,
            "total_cost_usd": 0,
            "agent_calls": [],
        }
    finally:
        conn.close()


# ── 작업(Task) API → handlers/task_handler.py로 분리 ──
from handlers.task_handler import router as task_router
app.include_router(task_router)

# ── 트레이딩 엔진 → trading_engine.py로 분리 (P6 리팩토링) ──
from trading_engine import (
    trading_router,
    _run_trading_now_inner,
    _check_price_triggers,
    _update_fx_rate,
    _get_fx_rate,
    _compute_calibration_factor,
    generate_trading_signals,
)
app.include_router(trading_router)

# ── 스케줄러 → scheduler.py로 분리 (P7 리팩토링) ──
from scheduler import (
    scheduler_router,
    start_background_tasks,
    _cron_loop,
    _register_default_schedules,
    _soul_gym_loop,
)
app.include_router(scheduler_router)

# ── 에이전트 라우팅 → agent_router.py로 분리 (P8 리팩토링) ──
from agent_router import (
    _process_ai_command,
    _call_agent,
    _broadcast_comms,
    _init_tool_pool,
    _load_chief_prompt,
    _tg_convert_names,
    _AGENT_NAMES,
)


# -- telegram bot -> telegram_bot.py (P9) --
from telegram_bot import _start_telegram_bot, _stop_telegram_bot, _forward_web_response_to_telegram



# ── 리플레이 API → handlers/replay_handler.py로 분리 ──
from handlers.replay_handler import router as replay_router
app.include_router(replay_router)


# ── Google Calendar OAuth → handlers/calendar_handler.py로 분리 ──
from handlers.calendar_handler import router as calendar_router
app.include_router(calendar_router)


# ── 예약(Schedule) · 워크플로우(Workflow) CRUD → handlers/schedule_handler.py로 분리 ──
from handlers.schedule_handler import router as schedule_router
app.include_router(schedule_router)



# ── 콘텐츠 파이프라인 — 제거됨 (2026-02-21, CEO 지시) ──



# ── 디버그 API → handlers/debug_handler.py로 분리 ──
from handlers.debug_handler import router as debug_router
app.include_router(debug_router)


# ── mock/balance, overseas/balance, overseas/mock-balance, portfolio/history,
#    portfolio/set-initial, portfolio/reset, mock/holdings, shadow/compare,
#    cio/predictions, cio/performance-summary → handlers/trading_handler.py로 분리 ──


# ── 지식파일 API → handlers/knowledge_handler.py로 분리 ──
from handlers.knowledge_handler import router as knowledge_router
app.include_router(knowledge_router)


# ── 에이전트 메모리 API → handlers/memory_handler.py로 분리 ──
from handlers.memory_handler import router as memory_router
app.include_router(memory_router)


# ── 피드백 API → handlers/feedback_handler.py로 분리 ──
from handlers.feedback_handler import router as feedback_router
app.include_router(feedback_router)


# ── 대화 API → handlers/conversation_handler.py로 분리 ──
from handlers.conversation_handler import router as conversation_router
app.include_router(conversation_router)


# ── 아키텍처 맵 → handlers/architecture_handler.py로 분리 ──
from handlers.architecture_handler import router as architecture_router
app.include_router(architecture_router)

# ── SNS 연동 → handlers/sns_handler.py로 분리 ──
from handlers.sns_handler import router as sns_router
app.include_router(sns_router)


# ── 인증 → handlers/auth_handler.py에서 분리됨 (위쪽에서 include_router 완료) ──

# ── 헬스체크 → handlers/health_handler.py로 분리 ──
from handlers.health_handler import router as health_router
app.include_router(health_router)


# ── 품질검수(Quality) API → handlers/quality_handler.py로 분리 ──
from handlers.quality_handler import router as quality_router
app.include_router(quality_router)


# ── 트레이딩 CRUD API → handlers/trading_handler.py로 분리 ──
from handlers.trading_handler import router as trading_router
app.include_router(trading_router)


# ── 에이전트 설정(소울/모델/추론), 예산, 모델목록 → handlers/agent_handler.py로 분리 ──

# ── 활동 로그 · 위임 로그 · 내부통신(Comms) API → handlers/activity_handler.py로 분리 ──
from handlers.activity_handler import router as activity_router
app.include_router(activity_router)


# _broadcast_comms → agent_router.py로 이관 (P8)

# ── 팀장 간 협의(Consult) API → handlers/consult_handler.py로 분리 ──
from handlers.consult_handler import router as consult_router
app.include_router(consult_router)

# ── 아카이브 API → handlers/archive_handler.py로 분리 ──
from handlers.archive_handler import router as archive_router
app.include_router(archive_router)

# ── 텔레그램 상태/테스트 API → handlers/telegram_handler.py로 분리 ──
from handlers.telegram_handler import router as telegram_router
app.include_router(telegram_router)

# ── Soul 자동 진화 API → handlers/soul_evolution_handler.py로 분리 ──
from handlers.soul_evolution_handler import router as soul_evolution_router
app.include_router(soul_evolution_router)

# ── Soul Gym 경쟁 진화 API → handlers/soul_gym_handler.py ──
from handlers.soul_gym_handler import router as soul_gym_router
app.include_router(soul_gym_router)

# ── AGORA: AI 법학 토론 시스템 → handlers/agora_handler.py로 분리 ──
from handlers.agora_handler import router as agora_router
app.include_router(agora_router)




# ── 에이전트 위임 시스템 → agent_router.py로 분리 (P8 리팩토링) ──
# 2,684줄 → agent_router.py로 이관 (상수/노션/QA/에이전트코어/라우팅/도구풀)

# ── 노션(Notion) 로그 API → handlers/notion_handler.py로 분리 ──
from handlers.notion_handler import router as notion_router
app.include_router(notion_router)

# ── ARGOS API → handlers/argos_handler.py로 분리 ──
from handlers.argos_handler import router as argos_api_router
app.include_router(argos_api_router)

# ── SketchVibe (스케치→다이어그램 변환) ──
from handlers.sketchvibe_handler import router as sketchvibe_router
app.include_router(sketchvibe_router)

# ── 내부 도구 실행 API (MCP 프록시 → CLI 에이전트 도구 호출용) ──
@app.post("/api/internal/tool-invoke")
async def internal_tool_invoke(request: Request):
    """MCP 프록시 서버가 호출하는 내부 도구 실행 엔드포인트.

    CLI 에이전트가 MCP를 통해 도구를 사용할 때,
    MCP 서버가 이 엔드포인트로 도구 실행을 위임합니다.
    localhost에서만 접근 가능 (nginx가 외부 차단).
    """
    from agent_router import _init_tool_pool
    try:
        body = await request.json()
        tool_name = body.get("tool_name", "")
        arguments = body.get("arguments", {})
        caller_id = body.get("caller_id", "cli_agent")

        if not tool_name:
            return JSONResponse({"error": "tool_name 필수"}, status_code=400)

        pool = _init_tool_pool()
        if not pool:
            return JSONResponse({"error": "ToolPool 초기화 실패"}, status_code=500)

        result = await pool.invoke(tool_name, caller_id=caller_id, **arguments)
        return {"result": result}
    except Exception as e:
        logger.error("[InternalTool] %s 실행 오류: %s", body.get("tool_name", "?"), e)
        return JSONResponse({"error": str(e)}, status_code=500)

# ── 도구 실행/상태/건강 → handlers/tools_handler.py로 분리 ──


# ── 진화 로그 실시간 브로드캐스트 + REST API ──

async def _broadcast_evolution_log(message: str, level: str = "info"):
    """진화 시스템 로그를 WebSocket으로 실시간 브로드캐스트."""
    from datetime import datetime, timezone, timedelta
    _KST = timezone(timedelta(hours=9))
    now = datetime.now(_KST)
    await wm.broadcast("evolution_log", {
        "message": message,
        "level": level,
        "time": now.strftime("%H:%M:%S"),
        "timestamp": now.isoformat(),
    })


@app.get("/api/evolution/logs")
async def api_evolution_logs(limit: int = 50):
    """최근 진화 시스템 로그 조회 (activity_logs에서 Soul Gym / Soul Evolution 필터)."""
    try:
        conn = get_connection()
        rows = conn.execute(
            """SELECT agent_id, message, level, timestamp
               FROM activity_logs
               WHERE (message LIKE '%Soul Gym%' OR message LIKE '%Soul Evolution%' OR message LIKE '%진화%')
               ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        logs = [{"agent_id": r[0], "message": r[1], "level": r[2], "timestamp": r[3]} for r in rows]
        return {"logs": logs}
    except Exception as e:
        return {"logs": [], "error": str(e)}



@app.on_event("startup")
async def on_startup():
    """서버 시작 시 DB 초기화 + AI 클라이언트 + 텔레그램 봇 + 크론 엔진 + 도구 풀 시작."""
    init_db()
    _sync_agent_defaults_to_db()
    _load_chief_prompt()
    ai_ok = init_ai_client()
    _log(f"[AI] 클라이언트 초기화: {'성공 ✅' if ai_ok else '실패 ❌ (ANTHROPIC_API_KEY 미설정?)'}")
    try:
        await _start_telegram_bot()
    except Exception as tg_err:
        _log(f"[TG] ❌ 봇 시작 중 미처리 예외: {tg_err}")
        _diag["tg_error"] = f"startup 예외: {tg_err}"
    # 도구 실행 엔진 초기화 (비동기 아닌 동기 — 첫 요청 시 lazy 로드도 지원)
    _init_tool_pool()
    # cross_agent_protocol 실시간 콜백 등록
    try:
        from src.tools.cross_agent_protocol import register_call_agent, register_sse_broadcast, register_valid_agents, register_collaboration_log_callback
        register_call_agent(_call_agent)
        register_sse_broadcast(_broadcast_comms)
        register_valid_agents([{
            "agent_id": a["agent_id"],
            "division": a.get("division", ""),
            "superior_id": a.get("superior_id", ""),
            "dormant": a.get("dormant", False),
        } for a in AGENTS])
        # Phase 12: 부서 간 협업 로그 콜백
        register_collaboration_log_callback(
            lambda **kw: save_collaboration_log(**kw)
        )
        _log("[P2P] cross_agent_protocol 콜백 등록 완료 ✅ (에이전트 호출 + SSE + 협업로그)")
    except Exception as e:
        _log(f"[P2P] cross_agent_protocol 콜백 등록 실패: {e}")
    # 모든 백그라운드 스케줄러 시작 (scheduler.py)
    await start_background_tasks()


@app.on_event("shutdown")
async def on_shutdown():
    """서버 종료 시 백그라운드 태스크 정리 + 텔레그램 봇 종료."""
    cancelled = await app_state.cancel_all_bg_tasks()
    _log(f"[SHUTDOWN] 백그라운드 태스크 {cancelled}개 취소")
    await _stop_telegram_bot()
    _log("[SHUTDOWN] 서버 종료 완료")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
