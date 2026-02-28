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

# ── 텔레그램 봇 (선택적 로드) ──
_telegram_available = False
try:
    from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        CallbackQueryHandler,
        ContextTypes,
        filters,
    )
    _telegram_available = True
    _diag["tg_import"] = True
    _log("[TG] python-telegram-bot 임포트 성공 ✅")
except ImportError as e:
    _diag["tg_import_error"] = str(e)
    _log(f"[TG] python-telegram-bot 임포트 실패 ❌: {e}")

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

    return HTMLResponse(content=html_content)


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

                    # 배치 모드: 위임 체인 전체를 Batch API로 실행
                    if use_batch and is_ai_ready():
                        update_task(task["task_id"], status="pending",
                                    result_summary="📦 [배치 체인] 시작 중...")
                        # 즉시 접수 응답 → 대화창 바로 풀림 (배치는 백그라운드에서 실행)
                        await ws.send_json({
                            "event": "result",
                            "data": {
                                "content": (
                                    f"📦 **배치 접수 완료** (#{task['task_id']})\n\n"
                                    f"배치 체인이 백그라운드에서 실행됩니다.\n"
                                    f"각 단계 완료 시 자동으로 진행되며, "
                                    f"최종 보고서가 완성되면 알려드리겠습니다.\n\n"
                                    f"💡 대화를 계속하실 수 있습니다."
                                ),
                                "sender_id": "chief_of_staff",
                                "handled_by": "비서실장",
                                "time_seconds": 0,
                                "cost": 0,
                            }
                        })

                        # 배치 체인을 백그라운드 태스크로 실행 (대화 차단 없음)
                        async def _run_batch_chain(text, task_id, ws_ref):
                            try:
                                chain_result = await _start_batch_chain(text, task_id)
                                if "error" in chain_result:
                                    await wm.broadcast("batch_chain_progress", {"message": f"❌ 배치 시작 실패: {chain_result['error']}"})
                            except Exception as e:
                                _log(f"[CHAIN] 백그라운드 배치 체인 오류: {e}")

                        asyncio.create_task(_run_batch_chain(cmd_text, task["task_id"], ws))
                        continue

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
                            _run_agent_bg(cmd_text, task["task_id"], ws_target_agent_id, ws_conversation_id)
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
                        conversation_id: str | None = None):
    """에이전트 작업을 백그라운드에서 실행. WebSocket 연결과 무관하게 동작."""

    _bg_tasks[task_id] = asyncio.current_task()
    try:
        result = await _process_ai_command(cmd_text, task_id, target_agent_id=target_agent_id,
                                           conversation_id=conversation_id)
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
from handlers.auth_handler import router as auth_router, check_auth as _check_auth
app.include_router(auth_router)


# ── 에이전트 관리 API → handlers/agent_handler.py로 분리 ──
from handlers.agent_handler import router as agent_router
app.include_router(agent_router)

# ── 도구(Tool) API → handlers/tools_handler.py로 분리 ──
from handlers.tools_handler import router as tools_router
app.include_router(tools_router)


@app.get("/api/dashboard")
async def get_dashboard():
    now = datetime.now(KST).isoformat()
    stats = get_dashboard_stats()
    today_cost = get_today_cost()
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
        "notion_connected": bool(_NOTION_API_KEY),
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

# ── 배치 시스템 → batch_system.py로 분리 (P5 리팩토링) ──
from batch_system import (
    batch_router,
    _start_batch_chain,
)
app.include_router(batch_router)

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


async def _forward_web_response_to_telegram(
    user_command: str, result_data: dict
) -> None:
    """웹 채팅 에이전트 응답을 텔레그램 CEO에게 자동 전달합니다."""
    if not app_state.telegram_app:
        return
    ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
    if not ceo_id:
        return
    content = result_data.get("content", "")
    if not content:
        return
    handled_by = result_data.get("handled_by", "")
    # 텔레그램 코드명 변환
    tg_who = _tg_convert_names(handled_by) if handled_by else ""
    cost = result_data.get("cost", 0)
    try:
        # 텔레그램 메시지 길이 제한 (4096자)
        cmd_preview = user_command[:60] + ("..." if len(user_command) > 60 else "")
        header = f"💬 [{tg_who}] 웹 응답\n📝 \"{cmd_preview}\"\n─────\n"
        footer = f"\n─────\n💰 ${cost:.4f}" if cost else ""
        max_content = 4096 - len(header) - len(footer) - 50
        if len(content) > max_content:
            content = content[:max_content] + "\n\n... (전체는 웹에서 확인)"
        msg = f"{header}{content}{footer}"
        await app_state.telegram_app.bot.send_message(
            chat_id=int(ceo_id), text=msg,
        )
    except Exception as e:
        _log(f"[TG] 웹 응답 전송 실패: {e}")


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


# ── 텔레그램 봇 ──
# 주의: python-telegram-bot 미설치 시에도 서버가 정상 작동해야 함
# 모든 텔레그램 관련 코드는 _telegram_available 체크 후에만 실행

# app_state.telegram_app → app_state.telegram_app 직접 사용


async def _start_telegram_bot() -> None:
    """텔레그램 봇을 시작합니다 (FastAPI 이벤트 루프 안에서 실행)."""


    _log(f"[TG] 봇 시작 시도 (_telegram_available={_telegram_available})")

    if not _telegram_available:
        _log("[TG] ❌ 라이브러리 없음 — 건너뜀")
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    _log(f"[TG] 토큰 존재: {bool(token)} (길이: {len(token)})")
    if not token:
        _log("[TG] ❌ 토큰 미설정 — 건너뜀")
        _diag["tg_error"] = "TELEGRAM_BOT_TOKEN 환경변수 없음"
        return

    try:
        _log("[TG] Application 빌드 중...")
        app_state.telegram_app = Application.builder().token(token).build()

        # ── 핸들러 함수들 (라이브러리 설치된 경우에만 정의) ──

        async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            chat_id = update.effective_chat.id
            ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
            if not ceo_id:
                logger.info("텔레그램 chat_id 감지: %s", chat_id)
                await update.message.reply_text(
                    f"CORTHEX HQ 텔레그램 봇입니다.\n\n"
                    f"당신의 chat_id: `{chat_id}`\n\n"
                    f"서버 환경변수에 TELEGRAM_CEO_CHAT_ID={chat_id} 를 추가하세요.",
                    parse_mode="Markdown",
                )
                return
            if str(chat_id) != ceo_id:
                await update.message.reply_text("권한이 없습니다.")
                return
            await update.message.reply_text(
                "*CORTHEX HQ 텔레그램 봇*\n\n"
                "CEO 인증 완료.\n"
                "24시간 서버에서 작동 중입니다.\n\n"
                "/help 로 사용법을 확인하세요.",
                parse_mode="Markdown",
            )

        async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            await update.message.reply_text(
                "*CORTHEX HQ 사용법*\n\n"
                "*정보*\n"
                "/agents — 에이전트 목록\n"
                "/health — 서버 상태\n"
                "/status — 배치 진행 현황\n"
                "/budget — 오늘 비용 / 한도 변경\n\n"
                "*AI 명령*\n"
                "/토론 \\[주제\\] — 임원 토론 (2라운드)\n"
                "/심층토론 \\[주제\\] — 심층 임원 토론 (3라운드)\n"
                "/전체 \\[메시지\\] — 29명 동시 지시\n"
                "/순차 \\[작업\\] — 에이전트 릴레이 순차 협업\n"
                "@에이전트명 \\[지시\\] — 특정 에이전트 직접 지시\n\n"
                "*모드 전환*\n"
                "/rt — 실시간 모드 (AI 즉시 답변)\n"
                "/batch — 배치 모드\n\n"
                "*설정*\n"
                "/models — 전원 모델 변경 (3단계 버튼)\n"
                "/pause — AI 처리 중단\n"
                "/resume — AI 처리 재개\n\n"
                "일반 메시지를 보내면 AI가 자동 라우팅합니다.",
                parse_mode="Markdown",
            )

        async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            divisions = {}
            for a in AGENTS:
                div = a.get("division", "기타")
                divisions.setdefault(div, []).append(a)
            lines = ["*CORTHEX HQ 에이전트 목록*\n"]
            div_labels = {
                "secretary": "비서실",
                "leet_master.tech": "기술개발처 (CTO)",
                "leet_master.strategy": "사업기획처 (CSO)",
                "leet_master.legal": "법무·IP처 (CLO)",
                "leet_master.marketing": "마케팅·고객처 (CMO)",
                "finance.investment": "투자분석처 (CIO)",
                "publishing": "출판·기록처 (CPO)",
            }
            for div, agents_list in divisions.items():
                label = div_labels.get(div, div)
                lines.append(f"\n*{label}* ({len(agents_list)}명)")
                for a in agents_list:
                    icon = "👔" if a["role"] == "manager" else "👤"
                    display = a.get("telegram_code", a["name_ko"])
                    lines.append(f"  {icon} {display}")
            lines.append(f"\n총 {len(AGENTS)}명")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            await update.message.reply_text(
                f"*서버 상태*\n\n"
                f"상태: 정상 운영 중\n"
                f"서버: Oracle Cloud (춘천)\n"
                f"에이전트: {len(AGENTS)}명 대기 중\n"
                f"시간: {now} KST",
                parse_mode="Markdown",
            )

        async def cmd_rt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            """실시간 모드 전환 (/rt)."""
            if not _is_tg_ceo(update):
                return
            save_setting("tg_mode", "realtime")
            await update.message.reply_text(
                "🔴 *실시간 모드*로 전환했습니다.\n\n"
                "이제 보내시는 메시지에 AI가 즉시 답변합니다.",
                parse_mode="Markdown",
            )

        async def cmd_batch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            """배치 모드 전환 (/batch)."""
            if not _is_tg_ceo(update):
                return
            save_setting("tg_mode", "batch")
            await update.message.reply_text(
                "📦 *배치 모드*로 전환했습니다.\n\n"
                "메시지를 접수만 하고, AI 처리는 하지 않습니다.",
                parse_mode="Markdown",
            )

        # ── /status — 배치 진행 목록 ──
        async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            chains = load_setting("batch_chains") or []
            active = [c for c in chains if c.get("status") in ("running", "pending")]
            if not active:
                await update.message.reply_text("현재 진행 중인 배치가 없습니다.")
                return
            lines = [f"*진행 중인 배치 ({len(active)}건)*\n"]
            for c in active[:10]:
                step = c.get("step", "?")
                text_preview = c.get("text", "")[:40]
                chain_id = c.get("chain_id", "?")[:8]
                lines.append(f"• `{chain_id}` | {step} | {text_preview}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        # ── /budget — 오늘 지출 확인/변경 ──
        async def cmd_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            args = (update.message.text or "").split()
            today_cost = get_today_cost()
            daily_limit = load_setting("daily_budget_usd") or 10
            if len(args) >= 2:
                try:
                    new_limit = float(args[1])
                    save_setting("daily_budget_usd", new_limit)
                    await update.message.reply_text(
                        f"💰 일일 예산을 *${new_limit:.2f}*로 변경했습니다.\n오늘 사용: ${today_cost:.4f}",
                        parse_mode="Markdown",
                    )
                    return
                except ValueError:
                    pass
            pct = (today_cost / daily_limit * 100) if daily_limit > 0 else 0
            await update.message.reply_text(
                f"💰 *오늘 비용 현황*\n\n"
                f"사용: ${today_cost:.4f}\n"
                f"한도: ${daily_limit:.2f}\n"
                f"사용률: {pct:.1f}%\n\n"
                f"한도 변경: `/budget 15` (15달러로 변경)",
                parse_mode="Markdown",
            )

        # ── /pause, /resume — AI 처리 중단/재개 ──
        async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            save_setting("ai_paused", True)
            await update.message.reply_text("⏸ *AI 처리를 일시 중단*했습니다.\n\n`/resume`으로 재개하세요.", parse_mode="Markdown")

        async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            save_setting("ai_paused", False)
            await update.message.reply_text("▶️ *AI 처리를 재개*했습니다.", parse_mode="Markdown")

        # ── /models — 3단계 인라인 버튼으로 모델 변경 ──
        # 프로바이더별 모델 목록 (코드 내 _MODEL_CATALOG과 동기화)
        _TG_MODELS = {
            "Anthropic": [
                ("claude-opus-4-6", "Opus 4.6", ["xhigh", "high", "low", "없음"]),
                ("claude-sonnet-4-6", "Sonnet 4.6", ["high", "medium", "low", "없음"]),
                ("claude-haiku-4-5-20251001", "Claude Haiku 4.5", []),
            ],
            "OpenAI": [
                ("gpt-5.2-pro", "GPT-5.2 Pro", ["xhigh", "high", "medium", "없음"]),
                ("gpt-5.2", "GPT-5.2", ["xhigh", "high", "medium", "low", "없음"]),
                ("gpt-5", "GPT-5", ["xhigh", "high", "low", "없음"]),
                ("gpt-5-mini", "GPT-5 Mini", []),
            ],
            "Google": [
                ("gemini-3.1-pro-preview", "Gemini 3.1 Pro Preview", ["high", "low", "없음"]),
                ("gemini-2.5-pro", "Gemini 2.5 Pro", ["high", "low", "없음"]),
                ("gemini-2.5-flash", "Gemini 2.5 Flash", []),
            ],
        }

        async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            current = load_setting("global_model_override") or {}
            cur_model = current.get("model", "없음")
            cur_reason = current.get("reasoning", "없음")
            buttons = [
                [InlineKeyboardButton("🟣 Anthropic", callback_data="mdl_p_Anthropic")],
                [InlineKeyboardButton("🟢 OpenAI", callback_data="mdl_p_OpenAI")],
                [InlineKeyboardButton("🔵 Google", callback_data="mdl_p_Google")],
            ]
            await update.message.reply_text(
                f"*전원 모델 변경*\n\n현재: `{cur_model}` (추론: {cur_reason})\n\n프로바이더를 선택하세요:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons),
            )

        async def models_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            query = update.callback_query
            await query.answer()
            data = query.data

            # 1단계: 프로바이더 선택 → 모델 목록 표시
            if data.startswith("mdl_p_"):
                provider = data[6:]
                models_list = _TG_MODELS.get(provider, [])
                buttons = []
                for model_id, label, _ in models_list:
                    buttons.append([InlineKeyboardButton(label, callback_data=f"mdl_m_{model_id}")])
                buttons.append([InlineKeyboardButton("« 뒤로", callback_data="mdl_back")])
                await query.edit_message_text(
                    f"*{provider}* 모델을 선택하세요:",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )

            # 2단계: 모델 선택 → 추론 강도 표시 (또는 바로 저장)
            elif data.startswith("mdl_m_"):
                model_id = data[6:]
                # 모델의 추론 레벨 찾기
                reasoning_levels = []
                for provider, models_list in _TG_MODELS.items():
                    for mid, label, levels in models_list:
                        if mid == model_id:
                            reasoning_levels = levels
                            break

                if not reasoning_levels:
                    # 추론 없음 → 바로 저장 (웹과 동일한 키 사용 → 동기화)
                    save_setting("model_mode", "manual")
                    save_setting("model_override", model_id)
                    save_setting("global_model_override", {"model": model_id, "reasoning": "없음"})
                    await query.edit_message_text(f"✅ 전원 모델을 `{model_id}` 으로 변경했습니다.\n(추론: 없음)", parse_mode="Markdown")
                else:
                    # 추론 레벨 선택 버튼
                    context.user_data["pending_model"] = model_id
                    buttons = []
                    for level in reasoning_levels:
                        buttons.append([InlineKeyboardButton(level, callback_data=f"mdl_r_{level}")])
                    buttons.append([InlineKeyboardButton("« 뒤로", callback_data="mdl_back")])
                    await query.edit_message_text(
                        f"*{model_id}*\n추론 강도를 선택하세요:",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(buttons),
                    )

            # 3단계: 추론 강도 선택 → 저장
            elif data.startswith("mdl_r_"):
                level = data[6:]
                model_id = context.user_data.get("pending_model", "")
                if model_id:
                    # 웹과 동일한 키 사용 → 동기화
                    save_setting("model_mode", "manual")
                    save_setting("model_override", model_id)
                    save_setting("global_model_override", {"model": model_id, "reasoning": level})
                    await query.edit_message_text(
                        f"✅ 전원 모델을 `{model_id}` 으로 변경했습니다.\n(추론: {level})",
                        parse_mode="Markdown",
                    )
                else:
                    await query.edit_message_text("❌ 모델 정보가 없습니다. /models를 다시 시도하세요.")

            # 뒤로가기
            elif data == "mdl_back":
                current = load_setting("global_model_override") or {}
                cur_model = current.get("model", "없음")
                cur_reason = current.get("reasoning", "없음")
                buttons = [
                    [InlineKeyboardButton("🟣 Anthropic", callback_data="mdl_p_Anthropic")],
                    [InlineKeyboardButton("🟢 OpenAI", callback_data="mdl_p_OpenAI")],
                    [InlineKeyboardButton("🔵 Google", callback_data="mdl_p_Google")],
                ]
                await query.edit_message_text(
                    f"*전원 모델 변경*\n\n현재: `{cur_model}` (추론: {cur_reason})\n\n프로바이더를 선택하세요:",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )

        # ── 장기 실행 명령 공통 헬퍼 (토론/전체/순차 등 2~10분 소요 명령) ──
        async def _tg_long_command(update_obj, task_text, target_agent_id=None):
            """백그라운드로 실행하고 완료 시 텔레그램으로 결과 전송."""
            chat_id = str(update_obj.effective_chat.id)
            task = create_task(task_text, source="telegram")
            cmd_name = task_text.split()[0]
            await update_obj.message.reply_text(
                f"⏳ *{cmd_name}* 시작 (#{task['task_id']})\n"
                f"완료 시 결과를 보내드립니다. (2~10분 소요)",
                parse_mode="Markdown",
            )

            async def _bg(t, tid, cid):
                try:
                    update_task(tid, status="running")
                    result = await _process_ai_command(t, tid, target_agent_id=target_agent_id)
                    content = result.get("content", result.get("error", "결과 없음"))
                    cost = result.get("cost_usd", result.get("total_cost_usd", 0))
                    tg_agent_id = result.get("agent_id", "chief_of_staff")
                    if "error" in result:
                        update_task(tid, status="failed",
                                    result_summary=str(result.get("error", ""))[:200],
                                    success=0, agent_id=tg_agent_id)
                    else:
                        update_task(tid, status="completed",
                                    result_summary=_extract_title_summary(content or ""),
                                    success=1, cost_usd=cost, agent_id=tg_agent_id)
                    if len(content) > 3900:
                        content = content[:3900] + "\n\n... (결과가 잘렸습니다. 웹에서 전체 확인)"
                    await app_state.telegram_app.bot.send_message(
                        chat_id=int(cid),
                        text=f"{content}\n\n─────\n💰 ${cost:.4f}",
                    )
                except Exception as e:
                    update_task(tid, status="failed",
                                result_summary=str(e)[:200], success=0)
                    try:
                        await app_state.telegram_app.bot.send_message(chat_id=int(cid), text=f"❌ 오류: {e}")
                    except Exception as e2:
                        logger.debug("TG 오류 메시지 전송 실패: %s", e2)

            asyncio.create_task(_bg(task_text, task["task_id"], chat_id))

        # ── /토론 [주제] — 임원 토론 (2라운드) ──
        async def cmd_debate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            topic = " ".join(context.args) if context.args else ""
            if not topic:
                await update.message.reply_text(
                    "사용법: `/토론 [주제]`\n예: `/토론 AI가 인간의 일자리를 대체할까?`",
                    parse_mode="Markdown",
                )
                return
            await _tg_long_command(update, f"/토론 {topic}")

        # ── /심층토론 [주제] — 심층 임원 토론 (3라운드) ──
        async def cmd_deep_debate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            topic = " ".join(context.args) if context.args else ""
            if not topic:
                await update.message.reply_text(
                    "사용법: `/심층토론 [주제]`\n예: `/심층토론 CORTHEX 2026 전략 방향`",
                    parse_mode="Markdown",
                )
                return
            await _tg_long_command(update, f"/심층토론 {topic}")

        # ── /전체 [메시지] — 29명 동시 브로드캐스트 ──
        async def cmd_broadcast_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            message = " ".join(context.args) if context.args else "전체 출석 보고"
            await _tg_long_command(update, f"/전체 {message}")

        # ── /순차 [메시지] — 에이전트 릴레이 순차 협업 ──
        async def cmd_sequential(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            message = " ".join(context.args) if context.args else ""
            if not message:
                await update.message.reply_text(
                    "사용법: `/순차 [작업]`\n예: `/순차 CORTHEX 웹사이트 기술→보안→사업성 분석`",
                    parse_mode="Markdown",
                )
                return
            await _tg_long_command(update, f"/순차 {message}")

        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            text = update.message.text.strip()
            if not text:
                return

            # @에이전트명 직접 지시 파싱 (예: "@cto_manager 기술 분석해줘")
            tg_target_agent_id = None
            if text.startswith("@"):
                parts = text.split(None, 1)
                if len(parts) >= 2:
                    mention = parts[0][1:]
                    mention_lower = mention.lower()
                    for a in AGENTS:
                        aid = a.get("agent_id", "").lower()
                        aname = a.get("name_ko", "")
                        tcode = a.get("telegram_code", "").lstrip("@")
                        if aid == mention_lower or aid.startswith(mention_lower) or mention_lower in aname.lower() or mention == tcode:
                            tg_target_agent_id = a["agent_id"]
                            text = parts[1]
                            break
                    if not tg_target_agent_id:
                        await update.message.reply_text(
                            f"❌ `@{parts[0][1:]}` 에이전트를 찾을 수 없습니다.\n"
                            f"/agents 로 에이전트 목록을 확인하세요.",
                            parse_mode="Markdown",
                        )
                        return

            # 한국어 명령어 처리 (텔레그램 CommandHandler는 영어만 지원하므로 텍스트로 처리)
            if text in ("실시간", "/실시간"):
                save_setting("tg_mode", "realtime")
                await update.message.reply_text(
                    "🔴 *실시간 모드*로 전환했습니다.\n\n"
                    "이제 보내시는 메시지에 AI가 즉시 답변합니다.",
                    parse_mode="Markdown",
                )
                return
            if text in ("배치", "/배치"):
                save_setting("tg_mode", "batch")
                await update.message.reply_text(
                    "📦 *배치 모드*로 전환했습니다.\n\n"
                    "메시지를 접수만 하고, AI 처리는 하지 않습니다.",
                    parse_mode="Markdown",
                )
                return

            # 한국어 AI 명령어 (/토론, /심층토론, /전체, /순차)
            if text.startswith("/토론 ") or text == "/토론":
                topic = text[len("/토론"):].strip()
                if not topic:
                    await update.message.reply_text(
                        "사용법: /토론 [주제]\n예: /토론 AI가 인간의 일자리를 대체할까?")
                    return
                await _tg_long_command(update, f"/토론 {topic}")
                return
            if text.startswith("/심층토론 ") or text == "/심층토론":
                topic = text[len("/심층토론"):].strip()
                if not topic:
                    await update.message.reply_text(
                        "사용법: /심층토론 [주제]\n예: /심층토론 CORTHEX 2026 전략 방향")
                    return
                await _tg_long_command(update, f"/심층토론 {topic}")
                return
            if text.startswith("/전체 ") or text == "/전체":
                message_text = text[len("/전체"):].strip() or "전체 출석 보고"
                await _tg_long_command(update, f"/전체 {message_text}")
                return
            if text.startswith("/순차 ") or text == "/순차":
                message_text = text[len("/순차"):].strip()
                if not message_text:
                    await update.message.reply_text(
                        "사용법: /순차 [작업]\n예: /순차 CORTHEX 웹사이트 기술→보안→사업성 분석")
                    return
                await _tg_long_command(update, f"/순차 {message_text}")
                return

            chat_id = str(update.effective_chat.id)
            # DB에 메시지 + 작업 저장
            task = create_task(text, source="telegram")
            save_message(text, source="telegram", chat_id=chat_id,
                         task_id=task["task_id"])

            # AI 일시 중단 체크
            if load_setting("ai_paused"):
                await update.message.reply_text("⏸ AI 처리가 일시 중단된 상태입니다.\n`/resume`으로 재개하세요.", parse_mode="Markdown")
                return

            # 모드 확인
            mode = load_setting("tg_mode") or "realtime"
            now = datetime.now(KST).strftime("%H:%M")
            result = {}  # 웹소켓 브로드캐스트용

            if mode == "realtime" and is_ai_ready():
                # 실시간 모드: AI가 답변
                update_task(task["task_id"], status="running")
                await update.message.reply_text(f"⏳ 처리 중... (#{task['task_id']})")

                result = await _process_ai_command(text, task["task_id"], target_agent_id=tg_target_agent_id)

                tg_rt_agent_id = result.get("agent_id", "chief_of_staff")
                if "error" in result:
                    update_task(task["task_id"], status="failed",
                                result_summary=str(result.get("error", ""))[:200],
                                success=0, agent_id=tg_rt_agent_id)
                    await update.message.reply_text(f"❌ {result['error']}")
                else:
                    content = result.get("content", "")
                    cost = result.get("cost_usd", 0)
                    model = result.get("model", "")
                    # 텔레그램 메시지 길이 제한 (4096자)
                    if len(content) > 3900:
                        content = content[:3900] + "\n\n... (결과가 잘렸습니다. 웹에서 전체 확인)"
                    delegation = result.get("delegation", "")
                    model_short = model.split("-")[1] if "-" in model else model
                    # 담당자 표시: 팀장 이름 또는 비서실장
                    footer_who = delegation if delegation else "비서실장"
                    update_task(task["task_id"], status="completed",
                                result_summary=_extract_title_summary(content or ""),
                                success=1, cost_usd=cost,
                                time_seconds=result.get("time_seconds", 0),
                                agent_id=tg_rt_agent_id)
                    await update.message.reply_text(
                        f"{content}\n\n"
                        f"─────\n"
                        f"👤 {footer_who} | 💰 ${cost:.4f} | 🤖 {model_short}",
                        parse_mode=None,
                    )
            elif mode == "batch" and is_ai_ready():
                # 배치 모드 + AI 연결됨 → 실제 배치 체인 실행
                update_task(task["task_id"], status="pending",
                            result_summary="📦 [배치 체인] 시작 중...")
                await update.message.reply_text(
                    f"📦 배치 접수 완료 (#{task['task_id']})\n"
                    f"배치 체인이 백그라운드에서 실행됩니다.\n"
                    f"완료 시 결과를 여기로 보내드리겠습니다.",
                    parse_mode=None,
                )

                # 배치 체인을 백그라운드로 실행
                async def _tg_run_batch(text_arg, task_id_arg, chat_id_arg):
                    try:
                        chain_result = await _start_batch_chain(text_arg, task_id_arg)
                        if "error" in chain_result and app_state.telegram_app:
                            try:
                                await app_state.telegram_app.bot.send_message(
                                    chat_id=int(chat_id_arg),
                                    text=f"❌ 배치 시작 실패: {chain_result['error']}",
                                )
                            except Exception as e2:
                                logger.debug("TG 배치 실패 전송 실패: %s", e2)
                    except Exception as e:
                        _log(f"[TG] 배치 체인 오류: {e}")

                asyncio.create_task(_tg_run_batch(text, task["task_id"], chat_id))
            else:
                # AI 미연결 → 접수만
                update_task(task["task_id"], status="completed",
                            result_summary="AI 미연결 — 접수만 완료",
                            success=1, time_seconds=0.1)
                await update.message.reply_text(
                    f"📋 접수했습니다. ({now})\n"
                    f"작업 ID: `{task['task_id']}`\n"
                    f"상태: AI 미연결",
                    parse_mode="Markdown",
                )

            # 활동 로그 저장 + 웹소켓 브로드캐스트 (웹 채팅에도 대화 표시)
            log_entry = save_activity_log(
                "chief_of_staff",
                f"[텔레그램] CEO 지시: {text[:50]}{'...' if len(text) > 50 else ''} (#{task['task_id']})",
            )
            await wm.broadcast_multi([
                ("task_accepted", task),
                ("activity_log", log_entry),
                ("telegram_message", {"type": "user", "text": text, "source": "telegram"}),
            ])
            if "error" not in result:
                await wm.broadcast("result", {
                    "content": result.get("content", ""),
                    "sender_id": result.get("agent_id", "chief_of_staff"),
                    "handled_by": result.get("handled_by", "비서실장"),
                    "delegation": result.get("delegation", ""),
                    "time_seconds": result.get("time_seconds", 0),
                    "cost": result.get("total_cost_usd", result.get("cost_usd", 0)),
                    "model": result.get("model", ""),
                    "routing_method": result.get("routing_method", ""),
                    "source": "telegram",
                })
            else:
                await wm.broadcast("result", {
                    "content": f"❌ {result['error']}",
                    "sender_id": "chief_of_staff",
                    "handled_by": "비서실장",
                    "time_seconds": 0, "cost": 0,
                    "source": "telegram",
                })

        def _is_tg_ceo(update: Update) -> bool:
            if not update.effective_chat or not update.message:
                return False
            ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
            if not ceo_id:
                return False
            if str(update.effective_chat.id) != ceo_id:
                asyncio.create_task(update.message.reply_text("권한이 없습니다."))
                return False
            return True

        # ── 글로벌 에러 핸들러 (핸들러 예외 로깅) ──
        async def _tg_error_handler(update, context):
            _log(f"[TG] ❌ 핸들러 오류: {context.error}")
            import traceback
            _diag["tg_last_error"] = str(context.error)
            _diag["tg_error_time"] = datetime.now(KST).isoformat()
            traceback.print_exc()
        app_state.telegram_app.add_error_handler(_tg_error_handler)

        # 핸들러 등록
        app_state.telegram_app.add_handler(CommandHandler("start", cmd_start))
        app_state.telegram_app.add_handler(CommandHandler("help", cmd_help))
        app_state.telegram_app.add_handler(CommandHandler("agents", cmd_agents))
        app_state.telegram_app.add_handler(CommandHandler("health", cmd_health))
        app_state.telegram_app.add_handler(CommandHandler("rt", cmd_rt))
        app_state.telegram_app.add_handler(CommandHandler("batch", cmd_batch))
        app_state.telegram_app.add_handler(CommandHandler("status", cmd_status))
        app_state.telegram_app.add_handler(CommandHandler("budget", cmd_budget))
        app_state.telegram_app.add_handler(CommandHandler("pause", cmd_pause))
        app_state.telegram_app.add_handler(CommandHandler("resume", cmd_resume))
        app_state.telegram_app.add_handler(CommandHandler("models", cmd_models))
        app_state.telegram_app.add_handler(CallbackQueryHandler(models_callback, pattern=r"^mdl_"))
        # 한국어 명령(/토론, /심층토론, /전체, /순차)은 handle_message에서 텍스트로 처리
        # (Telegram CommandHandler는 라틴 소문자+숫자+밑줄만 허용)
        app_state.telegram_app.add_handler(
            MessageHandler(filters.TEXT, handle_message)
        )

        _log("[TG] 핸들러 등록 완료, initialize()...")
        await app_state.telegram_app.initialize()

        # 토큰 유효성 사전 확인 (getMe)
        try:
            me = await app_state.telegram_app.bot.get_me()
            _diag["tg_bot_username"] = me.username
            _diag["tg_bot_id"] = me.id
            _log(f"[TG] ✅ 봇 인증 성공: @{me.username} (ID: {me.id})")
        except Exception as me_err:
            _log(f"[TG] ❌ 봇 토큰 무효 또는 네트워크 오류: {me_err}")
            _diag["tg_error"] = f"getMe 실패: {me_err}"
            app_state.telegram_app = None
            return

        # webhook 충돌 방지: polling 시작 전 webhook 강제 삭제
        for attempt in range(3):
            try:
                await app_state.telegram_app.bot.delete_webhook(drop_pending_updates=False)
                _log("[TG] webhook 삭제 완료 (polling 충돌 방지)")
                break
            except Exception as we:
                _log(f"[TG] webhook 삭제 시도 {attempt+1}/3 실패: {we}")
                if attempt < 2:
                    await asyncio.sleep(1)

        # 봇 명령어 메뉴 설정 (initialize 이후에 API 호출 가능)
        # NOTE: Telegram BotCommand는 라틴 소문자+숫자+밑줄만 허용 (한국어 불가)
        # 한국어 명령(/토론, /심층토론, /전체, /순차)은 CommandHandler로만 동작
        try:
            await app_state.telegram_app.bot.set_my_commands([
                BotCommand("start", "봇 시작"),
                BotCommand("help", "사용법 (한국어 명령 포함)"),
                BotCommand("agents", "에이전트 목록"),
                BotCommand("health", "서버 상태"),
                BotCommand("rt", "실시간 모드"),
                BotCommand("batch", "배치 모드"),
                BotCommand("models", "전원 모델 변경"),
                BotCommand("status", "배치 진행 상태"),
                BotCommand("budget", "오늘 비용 / 한도 변경"),
                BotCommand("pause", "AI 처리 중단"),
                BotCommand("resume", "AI 처리 재개"),
            ])
        except Exception as cmd_err:
            _log(f"[TG] 명령어 메뉴 설정 건너뜀 (봇은 정상 동작): {cmd_err}")

        _log("[TG] start()...")
        await app_state.telegram_app.start()
        _log("[TG] polling 시작...")
        # drop_pending_updates=True: 이전 쌓인 메시지 무시하고 새 메시지만 처리
        await app_state.telegram_app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )

        ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
        _diag["tg_started"] = True
        _log(f"[TG] ✅ 봇 시작 완료! (CEO: {ceo_id or '미설정'})")
    except Exception as e:
        _diag["tg_error"] = str(e)
        _log(f"[TG] ❌ 봇 시작 실패: {e}")
        import traceback
        traceback.print_exc()
        app_state.telegram_app = None


async def _stop_telegram_bot() -> None:
    """텔레그램 봇을 종료합니다."""

    if app_state.telegram_app:
        try:
            await app_state.telegram_app.updater.stop()
            await app_state.telegram_app.stop()
            await app_state.telegram_app.shutdown()
            logger.info("텔레그램 봇 종료 완료")
        except Exception as e:
            logger.warning("텔레그램 봇 종료 중 오류: %s", e)
        app_state.telegram_app = None



# ── 에이전트 위임 시스템 → agent_router.py로 분리 (P8 리팩토링) ──
# 2,684줄 → agent_router.py로 이관 (상수/노션/QA/에이전트코어/라우팅/도구풀)

# ── 노션(Notion) 로그 API → handlers/notion_handler.py로 분리 ──
from handlers.notion_handler import router as notion_router
app.include_router(notion_router)

# ── ARGOS API → handlers/argos_handler.py로 분리 ──
from handlers.argos_handler import router as argos_api_router
app.include_router(argos_api_router)

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
