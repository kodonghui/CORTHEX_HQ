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
# 품질검수(QualityGate) 제거됨 (2026-02-27 CEO 지시)
_QUALITY_GATE_AVAILABLE = False

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
    _ensure_batch_poller,
)
app.include_router(batch_router)

# ── 트레이딩 엔진 → trading_engine.py로 분리 (P6 리팩토링) ──
from trading_engine import (
    trading_router,
    _run_trading_now_inner,
    _check_price_triggers,
    _auto_refresh_prices,
    _trading_bot_loop,
    _shadow_trading_alert,
    _cio_prediction_verifier,
    _cio_weekly_soul_update,
    _update_fx_rate,
    _get_fx_rate,
    _compute_calibration_factor,
    generate_trading_signals,
)
app.include_router(trading_router)


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


# ── 크론 실행 엔진 (asyncio 기반 스케줄러) ──

# app_state.cron_task → app_state.cron_task 직접 사용



def _parse_cron_preset(preset: str) -> dict:
    """크론 프리셋을 실행 조건으로 변환합니다."""
    presets = {
        "every_minute": {"interval_seconds": 60},
        "every_5min": {"interval_seconds": 300},
        "every_30min": {"interval_seconds": 1800},
        "hourly": {"interval_seconds": 3600},
        "daily_9am": {"hour": 9, "minute": 0},
        "daily_6pm": {"hour": 18, "minute": 0},
        "weekday_9am": {"hour": 9, "minute": 0, "weekday_only": True},
        "monday_9am": {"hour": 9, "minute": 0, "day_of_week": 0},
    }
    return presets.get(preset, {"interval_seconds": 3600})


def _match_cron_field(field: str, value: int, max_val: int) -> bool:
    """크론 필드 하나를 매칭합니다. (예: "1-5" → 월~금, "*/10" → 0,10,20,30,40,50)"""
    if field == "*":
        return True
    for part in field.split(","):
        part = part.strip()
        if "/" in part:
            base, step = part.split("/", 1)
            step = int(step)
            if base == "*":
                if value % step == 0:
                    return True
            else:
                start = int(base)
                if value >= start and (value - start) % step == 0:
                    return True
        elif "-" in part:
            lo, hi = part.split("-", 1)
            if int(lo) <= value <= int(hi):
                return True
        else:
            if int(part) == value:
                return True
    return False


def _match_cron_expr(cron: str, now: datetime) -> bool:
    """5필드 크론 표현식과 현재 시간을 매칭합니다.
    형식: 분 시 일 월 요일 (0=일, 1=월 ... 6=토 / 또는 0=월 ... 6=일 리눅스 표준)
    여기서는 리눅스 표준: 0=일, 1=월, ..., 6=토
    """
    fields = cron.strip().split()
    if len(fields) != 5:
        return False
    minute, hour, dom, month, dow = fields
    # Python weekday(): 0=월 → 크론 변환: (python_weekday + 1) % 7 → 0=일
    cron_dow = (now.weekday() + 1) % 7
    return (
        _match_cron_field(minute, now.minute, 59)
        and _match_cron_field(hour, now.hour, 23)
        and _match_cron_field(dom, now.day, 31)
        and _match_cron_field(month, now.month, 12)
        and _match_cron_field(dow, cron_dow, 6)
    )


def _should_run_schedule(schedule: dict, now: datetime) -> bool:
    """현재 시간에 이 예약을 실행해야 하는지 확인합니다."""
    if not schedule.get("enabled", False):
        return False

    # 마지막 실행 시간 확인
    last_run = schedule.get("last_run_ts", 0)
    elapsed = now.timestamp() - last_run

    # 1순위: 실제 크론 표현식이 있으면 그걸로 판단
    cron_expr = schedule.get("cron", "")
    if cron_expr and cron_expr.strip().count(" ") >= 3:
        if _match_cron_expr(cron_expr, now):
            return elapsed >= 55  # 중복 실행 방지
        return False

    # 2순위: 프리셋 기반 (하위호환)
    preset = schedule.get("cron_preset", "")
    cron_config = _parse_cron_preset(preset)

    if "interval_seconds" in cron_config:
        return elapsed >= cron_config["interval_seconds"]

    # 시/분 기반 스케줄
    if now.hour == cron_config.get("hour", -1) and now.minute == cron_config.get("minute", -1):
        if cron_config.get("weekday_only") and now.weekday() >= 5:
            return False
        if "day_of_week" in cron_config and now.weekday() != cron_config["day_of_week"]:
            return False
        # 같은 시각에 중복 실행 방지 (최소 55초 간격)
        return elapsed >= 55
    return False



# ── ARGOS 수집 → argos_collector.py로 분리 (P4 리팩토링) ──
from argos_collector import (
    _argos_sequential_collect,
    _argos_monthly_rl_analysis,
    _build_argos_context_section,
)


async def _cron_loop():
    """1분마다 예약된 작업을 확인하고 실행합니다."""
    logger = logging.getLogger("corthex.cron")
    logger.info("크론 실행 엔진 시작")

    # 서버 시작 시 환율 즉시 갱신
    await _update_fx_rate()

    while True:
        try:
            await asyncio.sleep(60)  # 1분마다 체크

            # 환율 주기적 갱신 (1시간마다)
            if time.time() - app_state.last_fx_update > _FX_UPDATE_INTERVAL:
                asyncio.create_task(_update_fx_rate())

            # Soul 자동 진화: 매주 일요일 03:00 KST
            _now_cron = datetime.now(KST)
            if _now_cron.weekday() == 6 and _now_cron.hour == 3 and _now_cron.minute == 0:
                logger.info("🧬 주간 Soul 진화 크론 실행")
                save_activity_log("system", "🧬 주간 Soul 진화 분석 시작 (크론)", "info")
                from handlers.soul_evolution_handler import run_soul_evolution_analysis
                asyncio.create_task(run_soul_evolution_analysis())

            # Soul Gym 24/7 상시 진화 — _soul_gym_loop()로 이관 (서버 시작 시 자동 실행)

            # ── ARGOS: 자동 데이터 수집 레이어 → argos_collector.py ──
            _now_ts = time.time()
            asyncio.create_task(_argos_sequential_collect(_now_ts))

            # 월간 강화학습 패턴 분석 (Phase 6-9)
            import argos_collector as _ac
            if _now_ts - _ac._ARGOS_LAST_MONTHLY_RL > _ac._ARGOS_MONTHLY_INTERVAL:
                _ac._ARGOS_LAST_MONTHLY_RL = _now_ts
                asyncio.create_task(_argos_monthly_rl_analysis())

            schedules = _load_data("schedules", [])
            now = datetime.now(KST)

            for schedule in schedules:
                if _should_run_schedule(schedule, now):
                    command = schedule.get("command", "")
                    if not command:
                        continue

                    logger.info("크론 실행: %s — %s", schedule.get("name", ""), command)
                    save_activity_log("system", f"⏰ 예약 실행: {schedule.get('name', '')} — {command[:50]}", "info")

                    # 실행 시간 기록
                    schedule["last_run"] = now.strftime("%Y-%m-%d %H:%M")
                    schedule["last_run_ts"] = now.timestamp()
                    _save_data("schedules", schedules)

                    # 백그라운드에서 명령 실행
                    asyncio.create_task(_run_scheduled_command(command, schedule.get("name", "")))

            # 가격 트리거 체크 (1분마다 — 손절/익절/목표매수 자동 실행)
            asyncio.create_task(_check_price_triggers())

        except Exception as e:
            logger.error("크론 루프 에러: %s", e)


def _register_default_schedules():
    """서버 시작 시 기본 스케줄이 없으면 자동 등록합니다.
    대표님이 삭제한 크론은 deleted_schedules에 기록 → 서버 재시작 시 복원하지 않음.
    """
    schedules = _load_data("schedules", [])
    deleted_ids: set = set(_load_data("deleted_schedules", []))  # 대표님이 삭제한 기본 크론 ID 목록
    existing_ids = {s.get("id") for s in schedules}

    # 마이그레이션: 기존 CSO 주식분석 크론 → CIO로 교체 (주식분석은 CIO 업무)
    _old_ids = {"default_cso_morning", "default_cso_weekly"}
    before_count = len(schedules)
    schedules = [s for s in schedules if s.get("id") not in _old_ids]
    _migrated = before_count - len(schedules)
    if _migrated:
        existing_ids = {s.get("id") for s in schedules}
        deleted_ids -= _old_ids  # 기존 CSO 삭제 기록 제거 (새 CIO ID로 대체)
        _log(f"[CRON] 기존 CSO 주식분석 크론 {_migrated}개 제거 → CIO로 교체 예정")

    defaults = [
        {
            "id": "default_cio_morning",
            "name": "CIO 일일 시장 분석",
            "command": "@금융분석팀장 오늘 한국 주식시장 주요 동향과 섹터별 분석을 보고해주세요. 주요 이슈와 투자 관점 포함.",
            "cron": "30 8 * * 1-5",  # 평일 08:30
            "enabled": True,
        },
        {
            "id": "default_cio_weekly",
            "name": "CIO 주간 시장 리뷰",
            "command": "@금융분석팀장 이번 주 시장 총평과 다음 주 전망을 종합 보고서로 작성해주세요.",
            "cron": "0 18 * * 5",  # 금요일 18:00
            "enabled": True,
        },
    ]

    added = 0
    for d in defaults:
        # 대표님이 삭제한 기본 크론은 다시 등록하지 않음
        if d["id"] in deleted_ids:
            continue
        if d["id"] not in existing_ids:
            d["last_run"] = ""
            d["last_run_ts"] = 0
            d["created_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
            schedules.append(d)
            added += 1

    if added or _migrated:
        _save_data("schedules", schedules)
        _log(f"[CRON] 기본 스케줄 {added}개 등록, {_migrated}개 마이그레이션 ✅")


async def _run_scheduled_command(command: str, schedule_name: str):
    """예약된 명령을 실행하고, 결과를 텔레그램 CEO에게 발송합니다."""
    try:
        # @멘션 파싱 — 텔레그램과 동일 로직 (크론 명령에서도 target_agent_id 지정)
        target_agent_id = None
        actual_command = command
        stripped = command.strip()
        if stripped.startswith("@"):
            parts = stripped.split(None, 1)
            if len(parts) >= 2:
                mention = parts[0][1:]
                mention_lower = mention.lower()
                for a in AGENTS:
                    aid = a.get("agent_id", "").lower()
                    aname = a.get("name_ko", "")
                    tcode = a.get("telegram_code", "").lstrip("@")
                    if (aid == mention_lower or aid.startswith(mention_lower)
                            or mention_lower in aname.lower() or mention == tcode):
                        target_agent_id = a["agent_id"]
                        actual_command = parts[1]  # @멘션 제거
                        break
                if not target_agent_id:
                    logger.warning("[CRON] @멘션 '%s' 매칭 실패, 스마트 라우팅으로 진행", mention)

        task = create_task(actual_command, source="cron")
        result = await _process_ai_command(actual_command, task["task_id"], target_agent_id=target_agent_id)
        # R-3: 전력분석 데이터용 agent_id 기록
        update_task(task["task_id"], agent_id=result.get("agent_id", target_agent_id or "chief_of_staff"))
        save_activity_log("system", f"✅ 예약 완료: {schedule_name}", "info")

        # 크론 결과를 텔레그램 CEO에게 발송
        content = result.get("content", "")
        if content and app_state.telegram_app:
            ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
            if ceo_id:
                try:
                    who = result.get("handled_by", "시스템")
                    msg = f"⏰ [{schedule_name}]\n\n{content}"
                    if len(msg) > 3900:
                        msg = msg[:3900] + "\n\n... (전체는 웹에서 확인)"
                    await app_state.telegram_app.bot.send_message(chat_id=int(ceo_id), text=msg)
                except Exception as tg_err:
                    logger.warning("크론 결과 텔레그램 발송 실패: %s", tg_err)
    except Exception as e:
        save_activity_log("system", f"❌ 예약 실패: {schedule_name} — {str(e)[:100]}", "error")




# ── 리플레이 API → handlers/replay_handler.py로 분리 ──
from handlers.replay_handler import router as replay_router
app.include_router(replay_router)


# ── Google Calendar OAuth → handlers/calendar_handler.py로 분리 ──
from handlers.calendar_handler import router as calendar_router
app.include_router(calendar_router)


# ── 예약(Schedule) · 워크플로우(Workflow) CRUD → handlers/schedule_handler.py로 분리 ──
from handlers.schedule_handler import router as schedule_router
app.include_router(schedule_router)


# ── 워크플로우 실행 (AI 의존 — arm_server.py에 유지) ──

@app.post("/api/workflows/{wf_id}/run")
async def run_workflow(wf_id: str):
    """워크플로우를 실행합니다 — 스텝을 순서대로 AI로 처리합니다."""
    workflows = _load_data("workflows", [])
    wf = None
    for w in workflows:
        if w.get("id") == wf_id:
            wf = w
            break
    if not wf:
        return {"success": False, "error": "워크플로우를 찾을 수 없습니다"}

    steps = wf.get("steps", [])
    if not steps:
        return {"success": False, "error": "워크플로우에 실행할 단계가 없습니다"}

    if not is_ai_ready():
        return {"success": False, "error": "AI가 연결되지 않아 워크플로우를 실행할 수 없습니다"}

    # 백그라운드에서 순차 실행
    asyncio.create_task(_run_workflow_steps(wf_id, wf.get("name", ""), steps))
    return {"success": True, "message": f"워크플로우 '{wf.get('name', '')}' 실행을 시작합니다 ({len(steps)}단계)"}


async def _run_workflow_steps(wf_id: str, wf_name: str, steps: list):
    """워크플로우 스텝을 순차 실행합니다."""
    save_activity_log("system", f"🔄 워크플로우 시작: {wf_name} ({len(steps)}단계)", "info")
    results = []
    prev_result = ""

    for i, step in enumerate(steps):
        step_name = step.get("name", f"단계 {i+1}")
        command = step.get("command", "")
        if not command:
            continue

        # 이전 단계 결과를 참조할 수 있도록 명령에 컨텍스트 추가
        if prev_result and i > 0:
            command = f"[이전 단계 결과 참고: {prev_result[:500]}]\n\n{command}"

        save_activity_log("system", f"▶ {wf_name} — {step_name} 실행 중", "info")
        # 웹소켓으로 단계 시작 알림
        await _broadcast_workflow_progress(i, len(steps), "running", step_name, "", workflow_id=wf_id)

        try:
            task = create_task(command, source="workflow")
            result = await _process_ai_command(command, task["task_id"])
            # R-3: 전력분석 데이터용 agent_id 기록
            wf_agent = result.get("agent_id", "chief_of_staff") if isinstance(result, dict) else "chief_of_staff"
            update_task(task["task_id"], agent_id=wf_agent)
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            prev_result = content[:500]
            results.append({"step": step_name, "status": "completed", "result": content[:200]})
            save_activity_log("system", f"✅ {wf_name} — {step_name} 완료", "info")
            # 웹소켓으로 단계 완료 알림
            await _broadcast_workflow_progress(i, len(steps), "completed", step_name, content[:300], workflow_id=wf_id)
        except Exception as e:
            results.append({"step": step_name, "status": "failed", "error": str(e)[:200]})
            save_activity_log("system", f"❌ {wf_name} — {step_name} 실패: {str(e)[:100]}", "error")
            await _broadcast_workflow_progress(i, len(steps), "failed", step_name, str(e)[:200], workflow_id=wf_id)
            break  # 실패 시 중단

    # 전체 완료 알림
    final_result = "\n\n".join([f"**{r['step']}**: {r.get('result', r.get('error', ''))}" for r in results])
    await _broadcast_workflow_progress(-1, len(steps), "done", "", final_result, workflow_done=True, workflow_id=wf_id)
    save_activity_log("system", f"🏁 워크플로우 완료: {wf_name} — {len(results)}/{len(steps)} 단계 처리", "info")


async def _broadcast_workflow_progress(step_index: int, total_steps: int, status: str,
                                        step_name: str, result: str, workflow_done: bool = False,
                                        workflow_id: str = ""):
    """워크플로우 진행 상태를 웹소켓으로 전송합니다."""
    msg = {
        "event": "workflow_progress",
        "data": {
            "workflow_id": workflow_id,
            "step_index": step_index,
            "total_steps": total_steps,
            "status": status,
            "step_name": step_name,
            "result": result,
            "workflow_done": workflow_done,
            "final_result": result if workflow_done else "",
        },
    }
    await wm.broadcast(msg["event"], msg["data"])


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


async def _broadcast_comms(msg_data: dict):
    """SSE 클라이언트들에게 내부통신 메시지 broadcast."""
    await wm.broadcast_sse(msg_data)


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


# ── AI 에이전트 위임 시스템 (Phase 5) ──

# 부서별 키워드 라우팅 테이블
_ROUTING_KEYWORDS: dict[str, list[str]] = {
    "cso_manager": [
        "시장", "경쟁사", "사업계획", "매출", "예측", "전략",
        "비즈니스", "BM", "수익", "사업", "기획", "성장",
    ],
    "clo_manager": [
        "저작권", "특허", "상표", "약관", "계약", "법률", "소송", "IP",
        "규제", "라이선스", "법적", "법무",
    ],
    "cmo_manager": [
        "마케팅", "광고", "SNS", "인스타", "유튜브", "고객",
        "설문", "브랜딩", "콘텐츠", "홍보", "프로모션", "캠페인",
    ],
    "cio_manager": [
        "삼성", "애플", "주식", "투자", "종목", "차트", "시황",
        "코스피", "나스닥", "포트폴리오", "금리", "환율", "채권",
        "ETF", "펀드", "배당", "테슬라", "엔비디아",
        "매수", "매도", "자동매매", "키움", "백테스트", "전략",
        "손절", "익절", "시가총액", "PER", "RSI", "MACD",
    ],
    "cpo_manager": [
        "기록", "빌딩로그", "연대기", "블로그", "출판", "편집", "회고",
        "아카이브", "문서화", "회의록",
    ],
}

# 에이전트 ID → 한국어 이름 매핑
_AGENT_NAMES: dict[str, str] = {
    "chief_of_staff": "비서실장",
    "cso_manager": "전략팀장",
    "clo_manager": "법무팀장",
    "cmo_manager": "마케팅팀장",
    "cio_manager": "금융분석팀장",
    "cpo_manager": "콘텐츠팀장",
}

# ── 노션 API 연동 (에이전트 산출물 자동 저장) ──


_TITLE_SKIP_WORDS = {"죄송", "오류", "에러", "실패", "sorry", "error", "안녕하세요", "네,", "네!"}
# CEO 명령문 패턴: 제목에서 걸러야 할 문장 끝 패턴
_TITLE_CMD_ENDINGS = ("해줘", "해주세요", "해봐", "하세요", "할까요", "알려줘", "알려주세요",
                      "보고해", "분석해", "조사해", "만들어줘", "작성해", "정리해")

def _extract_notion_title(content: str, fallback: str = "보고서",
                          user_query: str = "") -> str:
    """AI 응답 본문에서 깔끔한 제목을 추출합니다.
    금지어(사과/에러 문구), CEO 명령문 패턴, user_query 반복 줄은 건너뜁니다."""
    if not content:
        return fallback
    # user_query 유사도 체크용 (앞 20자 정규화)
    q_norm = user_query.strip().replace("**", "").replace("*", "")[:20] if user_query else ""
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        line = line.lstrip("#").strip()
        line = line.replace("**", "").replace("*", "")
        if len(line) < 3 or line.startswith("---") or line.startswith("```"):
            continue
        # 금지어 필터: "죄송합니다", "오류입니다" 등 제목으로 부적절한 문구
        low = line[:10].lower()
        if any(low.startswith(w) for w in _TITLE_SKIP_WORDS):
            continue
        # CEO 명령문 패턴 필터: "~해줘", "~분석해" 등 명령형 문장 건너뛰기
        if any(line.rstrip(".,!? ").endswith(e) for e in _TITLE_CMD_ENDINGS):
            continue
        # user_query 반복 필터: CEO 명령을 그대로 반복하는 줄 건너뛰기
        if q_norm and len(q_norm) > 5 and line[:20].startswith(q_norm[:15]):
            continue
        return line[:100]
    return fallback


_NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
# 비서실 DB (비서실장→CEO 보고서만)
_NOTION_DB_SECRETARY = os.getenv("NOTION_DB_SECRETARY", "30a56b49-78dc-8153-bac1-dee5d04d6a74")
# 에이전트 산출물 DB (팀장 6명 작업물)
_NOTION_DB_OUTPUT = os.getenv("NOTION_DB_OUTPUT", "30a56b49-78dc-81ce-aaca-ef3fc90a6fba")
# 아카이브 DB (v3 데이터 + 구버전 이관)
_NOTION_DB_ARCHIVE = os.getenv("NOTION_DB_ARCHIVE", "31256b49-78dc-81c9-9ad2-e31a076d0d97")
# 하위 호환
_NOTION_DB_ID = os.getenv("NOTION_DEFAULT_DB_ID", _NOTION_DB_OUTPUT)

# 노션 로그 → app_state 사용 (alias)
_notion_log = app_state.notion_log

def _add_notion_log(status: str, title: str, db: str = "", url: str = "", error: str = ""):
    """노션 작업 로그를 저장합니다 (최근 20개)."""
    _notion_log.append({
        "time": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "title": title[:60],
        "db": db,
        "url": url,
        "error": error[:200] if error else "",
    })
    # in-place 트리밍 (alias 깨지지 않게)
    if len(_notion_log) > 500:
        del _notion_log[:-500]

# 에이전트 ID → 부서명 매핑
_AGENT_DIVISION: dict[str, str] = {}
for _a in AGENTS:
    if _a.get("division"):
        _AGENT_DIVISION[_a["agent_id"]] = _a["division"]


async def _save_to_notion(agent_id: str, title: str, content: str,
                          report_type: str = "보고서",
                          db_target: str = "output") -> str | None:
    """에이전트 산출물을 노션 DB에 저장합니다.

    db_target: "output" = 에이전트 산출물 DB, "secretary" = 비서실 DB
    Python 기본 라이브러리(urllib)만 사용 — 추가 패키지 불필요.
    실패해도 에러만 로깅하고 None 반환 (서버 동작에 영향 없음).
    """
    if not _NOTION_API_KEY:
        _add_notion_log("SKIP", title, error="API 키 없음")
        return None

    db_id = _NOTION_DB_SECRETARY if db_target == "secretary" else _NOTION_DB_OUTPUT
    db_name = "비서실" if db_target == "secretary" else "산출물"

    division = _AGENT_DIVISION.get(agent_id, "")
    agent_name = _AGENT_NAMES.get(agent_id, _SPECIALIST_NAMES.get(agent_id, agent_id))
    now_str = datetime.now(KST).strftime("%Y-%m-%d")

    # 노션 페이지 프로퍼티 구성 — 두 DB 스키마가 다름
    # 비서실 DB: Name, 담당자(select), 카테고리(select), 상태(select), 날짜(date), 내용(rich_text)
    # 에이전트 산출물 DB: Name, 에이전트(select), 보고유형(select), 부서(select), 상태(select), 날짜(date)
    properties: dict = {
        "Name": {"title": [{"text": {"content": title[:100]}}]},
    }
    if db_target == "secretary":
        # 비서실 DB: 담당자 + 카테고리 + 내용
        if agent_name:
            properties["담당자"] = {"select": {"name": agent_name}}
        properties["카테고리"] = {"select": {"name": "보고서"}}
        if content:
            properties["내용"] = {"rich_text": [{"text": {"content": content[:2000]}}]}
    else:
        # 에이전트 산출물 DB: 에이전트 + 보고유형 + 부서
        if agent_name:
            properties["에이전트"] = {"select": {"name": agent_name}}
        if report_type:
            properties["보고유형"] = {"select": {"name": report_type}}
        # 부서 매핑: division → 노션 부서 select 옵션
        _div_map = {
            "secretary": "비서실",
            "leet_master.tech": "LEET MASTER",
            "leet_master.strategy": "LEET MASTER",
            "leet_master.legal": "LEET MASTER",
            "leet_master.marketing": "LEET MASTER",
            "finance.investment": "투자분석",
            "publishing": "출판기록",
        }
        notion_div = _div_map.get(division, "")
        if notion_div:
            properties["부서"] = {"select": {"name": notion_div}}
    properties["상태"] = {"select": {"name": "완료"}}
    properties["날짜"] = {"date": {"start": now_str}}

    # 본문 → 노션 블록 (최대 2000자, 노션 블록 크기 제한)
    children = []
    text_chunks = [content[i:i+1900] for i in range(0, min(len(content), 8000), 1900)]
    for chunk in text_chunks:
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": chunk}}]},
        })

    body = json.dumps({
        "parent": {"database_id": db_id},
        "properties": properties,
        "children": children,
    }).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {_NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    def _do_request():
        req = urllib.request.Request(
            "https://api.notion.com/v1/pages",
            data=body, headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:300]
            _log(f"[Notion] HTTP {e.code} 오류 ({db_name}): {err_body}")
            # 오류 원인 힌트: 400=속성명 불일치(Name vs 제목), 401=API키 오류, 404=DB ID 오류
            return {"_error": f"HTTP {e.code}: {err_body}"}
        except Exception as e:
            _log(f"[Notion] 요청 실패 ({db_name}): {e}")
            return {"_error": str(e)}

    try:
        result = await asyncio.to_thread(_do_request)
        # _error 키가 있으면 _do_request 내부에서 오류 발생 — 이미 _log에 기록됨
        if result and "_error" in result:
            _add_notion_log("FAIL", title, db=db_name, error=result["_error"])
            return None
        if result and result.get("url"):
            _log(f"[Notion] 저장 완료 ({db_name}): {title[:50]} → {result['url']}")
            _add_notion_log("OK", title, db=db_name, url=result["url"])
            return result["url"]
        elif result:
            # 응답은 왔지만 url 필드가 없는 경우 — 응답 내용 로깅해서 디버깅 가능하게
            resp_snippet = str(result)[:200]
            _log(f"[Notion] 응답에 URL 없음 ({db_name}): {resp_snippet}")
            _add_notion_log("FAIL", title, db=db_name, error=f"응답에 URL 없음: {resp_snippet}")
        else:
            # result가 None — _do_request가 예외 없이 None 반환 (이론상 발생 안 함)
            _add_notion_log("FAIL", title, db=db_name, error="응답 없음(None)")
    except Exception as e:
        _log(f"[Notion] 비동기 실행 실패: {e}")
        _add_notion_log("FAIL", title, db=db_name, error=str(e))

    return None


# ── 노션(Notion) 로그 API → handlers/notion_handler.py로 분리 ──
from handlers.notion_handler import router as notion_router
app.include_router(notion_router)


# ── ARGOS API → handlers/argos_handler.py로 분리 ──
from handlers.argos_handler import router as argos_api_router
app.include_router(argos_api_router)


# ══════════════════════════════════════════════════════════════════


# 브로드캐스트 키워드 (모든 부서에 동시 전달하는 명령)
_BROADCAST_KEYWORDS = [
    "전체", "모든 부서", "출석", "회의", "현황 보고",
    "총괄", "전원", "각 부서", "출석체크", "브리핑",
]

# 팀장/비서실장 → 소속 전문가 매핑
# 2026-02-25: 전문가 전원 동면 → 팀장 단독 분석 체제.
# 재도입 시점: 팀장 혼자 30분+ & 병렬이 의미 있을 때 (CLAUDE.md 규칙)
_MANAGER_SPECIALISTS: dict[str, list[str]] = {
    "chief_of_staff": [],
    "cso_manager": [],
    "clo_manager": [],
    "cmo_manager": [],
    "cio_manager": [],
    "cpo_manager": [],
}

# 매니저 → 부서 매핑 (품질검수 루브릭 조회용)
_MANAGER_DIVISION: dict[str, str] = {
    "chief_of_staff": "secretary",
    "cso_manager": "leet_master.strategy",
    "clo_manager": "leet_master.legal",
    "cmo_manager": "leet_master.marketing",
    "cio_manager": "finance.investment",
    "cpo_manager": "publishing",
}
# 동면 부서 (품질검수 제외)
_DORMANT_MANAGERS: set[str] = set()

# app_state.quality_gate → app_state.quality_gate 직접 사용

def _init_quality_gate():
    """품질검수 게이트 초기화."""

    if not _QUALITY_GATE_AVAILABLE:
        _log("[QA] QualityGate 모듈 미설치 — 품질검수 비활성")
        return
    config_path = Path(__file__).parent.parent / "config" / "quality_rules.yaml"
    app_state.quality_gate = QualityGate(config_path)
    _log("[QA] 품질검수 게이트 초기화 완료")


class _QAModelRouter:
    """ask_ai()를 ModelRouter.complete() 인터페이스로 감싸는 어댑터 (품질검수용)."""

    async def complete(self, model_name="", messages=None,
                       temperature=0.0, max_tokens=4096,
                       agent_id="", **kwargs):
        from src.llm.base import LLMResponse
        messages = messages or []
        system_prompt = ""
        user_message = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg["content"]
            elif msg.get("role") == "user":
                user_message = msg["content"]
        result = await ask_ai(user_message, system_prompt, model_name)
        if "error" in result:
            return LLMResponse(
                content=f"[QA 오류] {result['error']}",
                model=model_name,
                input_tokens=0, output_tokens=0,
                cost_usd=0.0, provider="unknown",
            )
        return LLMResponse(
            content=result["content"],
            model=result.get("model", model_name),
            input_tokens=result.get("input_tokens", 0),
            output_tokens=result.get("output_tokens", 0),
            cost_usd=result.get("cost_usd", 0.0),
            provider=result.get("provider", "unknown"),
        )

_qa_router = _QAModelRouter()


async def _quality_review_specialists(
    chain: dict,
    previous_reviews: dict | None = None,
) -> list[dict]:
    """전문가 결과를 매니저 모델로 개별 검수. 불합격 목록 반환.

    previous_reviews: {agent_id: HybridReviewResult} — 재작업 시 이전 검수 결과.
        제공되면 사유 특정 재검수 (반려 항목만 재평가, 나머지는 이전 점수 유지).

    Returns: [{"agent_id": ..., "review": HybridReviewResult, "content": ...}, ...]
    """
    if not app_state.quality_gate or not _QUALITY_GATE_AVAILABLE:
        return []

    target_id = chain.get("target_id", "chief_of_staff")
    if target_id in _DORMANT_MANAGERS:
        return []

    division = _MANAGER_DIVISION.get(target_id, "default")
    reviewer_model = _get_model_override(target_id) or "claude-sonnet-4-6"
    task_desc = chain.get("original_command", "")[:500]
    failed = []

    # #2: 검수 시작 로그 — 전 직원 작업 시작 시 로그 기록
    _spec_ids = list(chain.get("results", {}).get("specialists", {}).keys())
    if _spec_ids:
        _spec_names = ", ".join(_AGENT_NAMES.get(s, _SPECIALIST_NAMES.get(s, s)) for s in _spec_ids[:4])
        _qa_start_log = save_activity_log(
            target_id, f"🔍 검수 시작: {_spec_names} ({len(_spec_ids)}명)", level="qa_start"
        )
        await wm.send_activity_log(_qa_start_log)

    for agent_id, result_data in chain.get("results", {}).get("specialists", {}).items():
        content = result_data.get("content", "")

        # ★ 사유 특정 재검수 모드: 이전에 합격한 전문가는 건너뜀 (LLM 비용 절약)
        if previous_reviews and agent_id not in previous_reviews:
            continue  # 이 전문가는 이전 검수에서 합격 → 재검수 불필요

        if result_data.get("error"):
            # 에러 결과는 자동 불합격 처리
            failed.append({
                "agent_id": agent_id,
                "review": None,
                "content": content,
                "reason": f"에러 응답: {result_data.get('error', '')[:100]}",
            })
            continue

        # QA에 도구 사용 기록 포함 — D1 + Q1 판정을 위해 필수
        _qa_content = content
        _spec_tools = result_data.get("tools_used", [])
        if _spec_tools:
            _unique_tools = list(dict.fromkeys(_spec_tools))
            # 도구별 호출 횟수 집계
            from collections import Counter as _Counter
            _tool_counts = _Counter(_spec_tools)
            _tool_detail = ", ".join(f"{t}({c}회)" for t, c in _tool_counts.most_common())
            _qa_content += (
                f"\n\n---\n## 사용한 도구 (총 {len(_spec_tools)}회 호출, 고유 {len(_unique_tools)}종)\n"
                f"{_tool_detail}\n"
                f"※ 위 도구들은 실시간 API를 호출하여 분석 당일의 최신 데이터를 가져온 것입니다.\n"
                f"※ 도구가 반환한 수치(주가, 재무제표, 거시지표 등)는 정확한 실시간 데이터입니다."
            )

        try:
            # ★ 사유 특정 재검수: 이전 리뷰가 있으면 반려 항목만 재평가
            _prev_review = (previous_reviews or {}).get(agent_id)
            if _prev_review is not None:
                review = await app_state.quality_gate.targeted_hybrid_review(
                    result_data=_qa_content,
                    task_description=task_desc,
                    model_router=_qa_router,
                    previous_review=_prev_review,
                    reviewer_id=target_id,
                    reviewer_model=reviewer_model,
                    division=division,
                    target_agent_id=agent_id,
                )
            else:
                review = await app_state.quality_gate.hybrid_review(
                    result_data=_qa_content,
                    task_description=task_desc,
                    model_router=_qa_router,
                    reviewer_id=target_id,
                    reviewer_model=reviewer_model,
                    division=division,
                    target_agent_id=agent_id,
                )
            # 통계 기록 (메모리)
            app_state.quality_gate.record_review(review, target_id, agent_id, task_desc)
            chain["total_cost_usd"] += getattr(review, "_cost", 0)

            # ★ 품질검수 통합 로그 — 전문가당 1건 (Phase 4: #10/#10-2)
            _spec_name = _SPECIALIST_NAMES.get(agent_id, agent_id)
            _qa_parts = []
            for ci in review.checklist_results:
                _ico = "✅" if ci.passed else "❌"
                _req = "[필]" if ci.required else ""
                _qa_parts.append(f"{ci.id}{_ico}{_req}")
            for si in review.score_results:
                _crit = "⬇" if si.critical and si.score == 1 else ""
                _qa_parts.append(f"{si.id}:{si.score}{_crit}")
            _pass_icon = "✅" if review.passed else "❌"
            _pass_text = "합격" if review.passed else "부합격"
            _qa_summary = f"{_pass_icon} {_spec_name} {_pass_text}({review.weighted_average:.1f}) {' '.join(_qa_parts)}"
            _qa_unified_log = save_activity_log(
                agent_id, _qa_summary, level="qa_detail"
            )
            await wm.send_activity_log(_qa_unified_log)

            # DB에 검수 결과 저장
            import json as _json
            try:
                save_quality_review(
                    chain_id=chain.get("chain_id", ""),
                    reviewer_id=target_id,
                    target_id=agent_id,
                    division=division,
                    passed=review.passed,
                    weighted_score=review.weighted_average,
                    checklist_json=_json.dumps(
                        [{"id": c.id, "passed": c.passed, "required": c.required}
                         for c in review.checklist_results], ensure_ascii=False
                    ),
                    scores_json=_json.dumps(
                        [{"id": s.id, "score": s.score, "weight": s.weight}
                         for s in review.score_results], ensure_ascii=False
                    ),
                    feedback=review.feedback[:500],
                    rejection_reasons=" / ".join(review.rejection_reasons)[:500] if review.rejection_reasons else "",
                    review_model=review.review_model,
                )
            except Exception as e:
                logger.debug("검수 결과 DB 저장 실패: %s", e)

            # ★ 기밀문서용: 모든 리뷰 결과 수집 (합격/불합격 무관)
            chain.setdefault("qa_reviews", []).append({
                "agent_id": agent_id,
                "passed": review.passed,
                "weighted_average": review.weighted_average,
                "review_dict": review.to_dict(),
            })

            if not review.passed:
                reason = " / ".join(review.rejection_reasons) if review.rejection_reasons else "품질 기준 미달"
                failed.append({
                    "agent_id": agent_id,
                    "review": review,
                    "content": content,
                    "reason": reason,
                })
                _log(f"[QA] ❌ 불합격: {agent_id} (점수={review.weighted_average:.1f}, 사유={reason[:80]})")
                # QA 불합격 실시간 브로드캐스트 (검수로그 탭에 표시)
                qa_log = save_activity_log(
                    agent_id,
                    f"❌ [{agent_id}] 불합격 (점수 {review.weighted_average:.1f}) — {reason[:60]}",
                    level="qa_fail"
                )
                await wm.send_activity_log(qa_log)

                # ── Phase 3: 반려사유 교신로그 + 기밀문서 + 반려 학습 ──
                _spec_name_rej = _SPECIALIST_NAMES.get(agent_id, agent_id)
                # (A) 교신로그에 반려 메시지 broadcast
                _rej_comms = {
                    "id": f"rej_{chain.get('chain_id', '')[:6]}_{agent_id[:8]}",
                    "sender": target_id,
                    "receiver": agent_id,
                    "message": f"❌ {_spec_name_rej} 반려: {reason[:200]}",
                    "log_type": "delegation",
                    "source": "qa_rejection",
                    "status": "반려",
                    "created_at": datetime.now().isoformat(),
                }
                await _broadcast_comms(_rej_comms)

                # (B) 기밀문서에 반려사유 저장
                from datetime import datetime as _dt_rej
                _rej_date = _dt_rej.now().strftime("%Y%m%d_%H%M")
                _rej_filename = f"반려사유_{_spec_name_rej}_{_rej_date}.md"
                _rej_detail = []
                for ci in review.checklist_results:
                    if not ci.passed:
                        _rej_detail.append(f"- {ci.id} {ci.label}: ❌ 불통과{' [필수]' if ci.required else ''}")
                for si in review.score_results:
                    if si.score <= 3:
                        _fb = f" — {si.feedback}" if si.feedback else ""
                        _rej_detail.append(f"- {si.id} {si.label}: {si.score}점/5{_fb}")
                _rej_content = (
                    f"# 반려사유 — {_spec_name_rej}\n\n"
                    f"**점수**: {review.weighted_average:.1f}/5.0\n"
                    f"**사유**: {reason}\n\n"
                    f"## 항목별 문제점\n" + "\n".join(_rej_detail) + "\n\n"
                    f"## 피드백\n{review.feedback[:500]}\n"
                )
                try:
                    save_archive(division, _rej_filename, _rej_content,
                                 correlation_id=chain.get("chain_id", ""),
                                 agent_id=target_id)
                except Exception as _ae:
                    logger.debug("반려사유 기밀문서 저장 실패: %s", _ae)

                # (C) 반려 학습: warnings 카테고리에 교훈 저장
                try:
                    _mem_key = f"memory_categorized_{agent_id}"
                    _existing_mem = load_setting(_mem_key, {})
                    _warning_lesson = f"{_dt_rej.now().strftime('%m/%d')}: {reason[:100]}"
                    _prev_warnings = _existing_mem.get("warnings", "")
                    _existing_mem["warnings"] = (
                        (_prev_warnings + " | " + _warning_lesson).strip(" |")
                        if _prev_warnings else _warning_lesson
                    )
                    save_setting(_mem_key, _existing_mem)
                    _log(f"[QA] 반려 학습 저장: {agent_id} ← {_warning_lesson[:60]}")
                except Exception as _me:
                    logger.debug("반려 학습 저장 실패: %s", _me)
            else:
                _log(f"[QA] ✅ 합격: {agent_id} (점수={review.weighted_average:.1f})")
                # QA 합격 실시간 브로드캐스트 (검수로그 탭에 표시)
                qa_log = save_activity_log(
                    agent_id,
                    f"✅ [{agent_id}] 합격 (점수 {review.weighted_average:.1f})",
                    level="qa_pass"
                )
                await wm.send_activity_log(qa_log)

        except Exception as e:
            _log(f"[QA] 검수 오류 ({agent_id}): {e}")
            # 검수 실패 시 통과 처리 (업무 차단 방지)

    return failed


async def _handle_specialist_rework(chain: dict, failed_specs: list[dict], attempt: int = 1):
    """불합격 전문가에게 재작업 지시 → 재검수.

    attempt: 현재 재시도 횟수 (1 또는 2)
    max_retry: quality_rules.yaml에서 설정 (기본 2)
    """
    max_retry = app_state.quality_gate.max_retry if app_state.quality_gate else 2
    if attempt > max_retry:
        # 재시도 초과 → 경고 뱃지 부착 후 종합 단계로 진행
        for spec in failed_specs:
            agent_id = spec["agent_id"]
            _log(f"[QA] ⚠️ 재작업 {max_retry}회 초과 — {agent_id} 결과를 경고 포함 채 종합 진행")
            existing = chain["results"]["specialists"].get(agent_id, {})
            existing["quality_warning"] = spec.get("reason", "품질 기준 미달")[:200]
            chain["results"]["specialists"][agent_id] = existing
        return

    target_id = chain.get("target_id", "chief_of_staff")
    target_name = _AGENT_NAMES.get(target_id, target_id)
    task_desc = chain.get("original_command", "")[:500]

    await _broadcast_chain_status(
        chain,
        f"🔄 품질검수 불합격 {len(failed_specs)}건 → 재작업 지시 (시도 {attempt}/{max_retry})"
    )

    # ── 개별 전문가 재작업 코루틴 (병렬 실행용) ──
    async def _do_single_rework(spec: dict) -> None:
        agent_id = spec["agent_id"]
        reason = spec.get("reason", "품질 기준 미달")
        original_content = spec.get("content", "")  # 전문 첨부 (부분수정을 위해)

        # 전문가 초록불 다시 켜기
        agent_name = _AGENT_NAMES.get(agent_id, agent_id)
        await _broadcast_status(agent_id, "working", 0.5, f"{agent_name} 재작업 중...")

        # ★ QA 항목별 구체적 문제점 생성 (재작업 시 뭘 고쳐야 하는지 명확히)
        _review = spec.get("review")
        _detail_lines = []
        _failed_ids: list[str] = []  # ★ 반려 항목 ID 리스트 (사유 특정 재검수용)
        if _review:
            from src.core.quality_gate import QualityGate as _QG
            _failed_ids = _QG.get_failed_item_ids(_review)
            # 불합격 항목만 상세 표시 (통과 항목은 간략히)
            for ci in _review.checklist_results:
                if not ci.passed:
                    _rq = " [필수]" if ci.required else ""
                    _fb = f" — {ci.feedback}" if ci.feedback else ""
                    _detail_lines.append(f"- ❌ {ci.id} {ci.label}{_rq}{_fb}")
            for si in _review.score_results:
                if si.score <= 1:
                    _crit = " ⚠️치명적" if si.critical else ""
                    _fb = f" — {si.feedback}" if si.feedback else ""
                    _detail_lines.append(f"- ❌ {si.id} {si.label}: {si.score}점/5{_crit}{_fb}")
        _detail_block = "\n".join(_detail_lines) if _detail_lines else "(상세 항목 없음)"
        _failed_ids_str = ", ".join(_failed_ids) if _failed_ids else "(전체)"

        rework_prompt = (
            f"[재작업 요청 #{attempt}] 당신의 보고서가 품질검수에서 불합격되었습니다.\n\n"
            f"## 반려 항목 ID: {_failed_ids_str}\n"
            f"⚠️ 위 항목만 수정하세요. 통과한 항목은 수정하지 마세요.\n"
            f"⚠️ 재검수 시 위 항목만 재채점됩니다. 나머지는 이전 점수가 유지됩니다.\n\n"
            f"## 원래 업무 지시\n{task_desc}\n\n"
            f"## 불합격 사유\n{reason}\n\n"
            f"## 항목별 검수 결과\n{_detail_block}\n\n"
            f"## 당신의 이전 보고서 (전문)\n{original_content}\n\n"
            f"## 지시사항\n"
            f"⚠️ 반려된 항목만 수정하고 나머지는 그대로 유지하세요.\n"
            f"- 정확했던 수치(매출, PER, 주가 등)를 변경하지 마세요.\n"
            f"- 지적된 부분만 보완하세요 (도구 재호출하여 최신 데이터 확인).\n"
            f"- 보고서 전체를 다시 쓰지 말고, 문제 항목을 정확히 수정하세요."
        )

        try:
            # 전문가 모델로 재작업 실행 (★ 도구 포함! — 재작업에서도 API 호출 가능)
            spec_model = _get_model_override(agent_id) or "claude-sonnet-4-6"
            spec_soul = _load_agent_prompt(agent_id)
            rework_tool_schemas = None
            rework_tool_executor = None
            rework_tools_used: list[str] = []
            _rw_detail = _AGENTS_DETAIL.get(agent_id, {})
            _rw_allowed = _rw_detail.get("allowed_tools", [])
            if _rw_allowed:
                _rw_schemas = _load_tool_schemas(allowed_tools=_rw_allowed)
                if _rw_schemas.get("anthropic"):
                    rework_tool_schemas = _rw_schemas["anthropic"]
                    _rw_max = int(_rw_detail.get("max_tool_calls", 5))
                    # 클로저 캡처: 함수 인자로 바인딩하여 병렬 안전
                    _captured_id = agent_id
                    _captured_name = agent_name

                    async def _rework_executor(tool_name: str, tool_input: dict,
                                               _aid=_captured_id, _aname=_captured_name):
                        rework_tools_used.append(tool_name)
                        _cnt = len(rework_tools_used)
                        await _broadcast_status(
                            _aid, "working", 0.5 + min(_cnt / _rw_max, 1.0) * 0.3,
                            f"{tool_name} 실행 중... (재작업)",
                        )
                        _rw_log = save_activity_log(
                            _aid,
                            f"🔧 [{_aname}] {tool_name} 호출 ({_cnt}회) [재작업#{attempt}]",
                            level="tool",
                        )
                        await wm.send_activity_log(_rw_log)
                        pool = _init_tool_pool()
                        if pool:
                            return await pool.invoke(tool_name, caller_id=_aid, **tool_input)
                        return f"도구 '{tool_name}'을(를) 찾을 수 없습니다."

                    rework_tool_executor = _rework_executor

            result = await ask_ai(
                user_message=rework_prompt,
                system_prompt=spec_soul,
                model=spec_model,
                tools=rework_tool_schemas,
                tool_executor=rework_tool_executor,
                reasoning_effort=_get_agent_reasoning_effort(agent_id),
            )

            if "error" not in result:
                # 재작업 결과로 교체 (도구 사용 기록 포함)
                chain["results"]["specialists"][agent_id] = {
                    "content": result["content"],
                    "model": result.get("model", spec_model),
                    "cost_usd": result.get("cost_usd", 0),
                    "rework_attempt": attempt,
                    "tools_used": result.get("tools_used", []),
                }
                chain["total_cost_usd"] += result.get("cost_usd", 0)
                _log(f"[QA] 재작업 완료: {agent_id} (시도 {attempt})")

                # ── Phase 3: 재작업 보고서 기밀문서 저장 + 활동로그 ──
                from datetime import datetime as _dt_rw
                _rw_date = _dt_rw.now().strftime("%Y%m%d_%H%M")
                _rw_div = _AGENT_DIVISION.get(agent_id, "default")
                _rw_filename = f"{agent_name}_보고서_재작업v{attempt}_{_rw_date}.md"
                try:
                    save_archive(
                        _rw_div, _rw_filename, result["content"],
                        correlation_id=chain.get("chain_id", ""),
                        agent_id=agent_id,
                    )
                except Exception as _ae2:
                    logger.debug("재작업 기밀문서 저장 실패: %s", _ae2)
                _rw_log = save_activity_log(
                    agent_id,
                    f"🔄 [{agent_name}] 재작업 보고서 제출 (v{attempt})",
                    level="info",
                )
                await wm.send_activity_log(_rw_log)
            else:
                _log(f"[QA] 재작업 실패: {agent_id} — {result.get('error', '')[:100]}")

        except Exception as e:
            _log(f"[QA] 재작업 오류 ({agent_id}): {e}")

        # 전문가 초록불 끄기
        await _broadcast_status(agent_id, "done", 1.0, "재작업 완료")

    # ── 불합격 전문가 재작업 (전원 즉시 병렬) ──
    await asyncio.gather(*[_do_single_rework(spec) for spec in failed_specs])

    # ★ 사유 특정 재검수: 이전 검수 결과를 전달하여 반려 항목만 재평가
    _prev_reviews = {}
    for spec in failed_specs:
        _rv = spec.get("review")
        if _rv is not None:
            _prev_reviews[spec["agent_id"]] = _rv

    _save_chain(chain)
    still_failed = await _quality_review_specialists(chain, previous_reviews=_prev_reviews)

    if still_failed:
        # 아직 불합격인 건 → 다시 재작업 (attempt+1)
        await _handle_specialist_rework(chain, still_failed, attempt + 1)
    else:
        _log(f"[QA] 재작업 후 전원 합격 (시도 {attempt})")


# B안: 전문가별 역할 prefix — 팀장이 위임할 때 CEO 원문을 그대로 전달하지 않고,
# 각 전문가의 역할에 맞는 지시를 앞에 붙여서 보냄
# 전문가 전원 제거 (2026-02-26). 재도입 시 여기에 추가.
_SPECIALIST_ROLE_PREFIX: dict[str, str] = {}

# 전문가 ID → 한국어 이름 (AGENTS 리스트에서 자동 구축)
_SPECIALIST_NAMES: dict[str, str] = {}
for _a in AGENTS:
    if _a["role"] == "specialist":
        _SPECIALIST_NAMES[_a["agent_id"]] = _a["name_ko"]

# 텔레그램 직원코드 매핑 (agents.yaml의 telegram_code 필드에서 자동 구축)
_TELEGRAM_CODES: dict[str, str] = {}
for _a in AGENTS:
    if _a.get("telegram_code"):
        _TELEGRAM_CODES[_a["agent_id"]] = _a["telegram_code"]


def _tg_code(agent_id: str) -> str:
    """agent_id → 텔레그램 코드명 (없으면 name_ko 폴백)."""
    return _TELEGRAM_CODES.get(
        agent_id,
        _AGENT_NAMES.get(agent_id, _SPECIALIST_NAMES.get(agent_id, agent_id))
    )


def _tg_convert_names(text: str) -> str:
    """텍스트 내 에이전트 이름을 텔레그램 코드명으로 변환합니다."""
    for aid, code in _TELEGRAM_CODES.items():
        name = _AGENT_NAMES.get(aid, _SPECIALIST_NAMES.get(aid, ""))
        if name and name in text:
            text = text.replace(name, code)
    return text


def _is_broadcast_command(text: str) -> bool:
    """브로드캐스트 명령인지 확인합니다."""
    return any(kw in text for kw in _BROADCAST_KEYWORDS)


async def _broadcast_status(agent_id: str, status: str, progress: float, detail: str = ""):
    """에이전트 상태를 모든 WebSocket 클라이언트에게 전송합니다.

    프론트엔드의 상태 표시등(초록불 깜빡임)을 제어합니다.
    status: 'working' | 'done' | 'idle'
    """
    await wm.send_agent_status(agent_id, status, progress, detail)


async def _extract_and_save_memory(agent_id: str, task: str, response: str):
    """대화 후 기억할 정보 추출 → save_setting에 저장 (비동기 백그라운드)."""
    try:
        extraction_prompt = (
            "아래 대화에서 에이전트가 기억해야 할 정보가 있으면 JSON으로 추출해라. "
            "없으면 빈 dict {} 반환.\n\n"
            f"[대화]\n사용자: {task[:400]}\n에이전트: {response[:400]}\n\n"
            "[추출 항목]\n"
            "- ceo_preferences: CEO가 선호하거나 싫어하는 것 (있으면)\n"
            "- decisions: '~하기로 결정', '~로 확정' 등 중요 결정 (있으면)\n"
            "- warnings: 이 방법은 안 됨, CEO가 싫다고 함 등 주의사항 (있으면)\n"
            "- context: 프로젝트 상태, 거래처, 일정 등 중요 맥락 (있으면)\n\n"
            "JSON만 반환 (설명 없이):"
        )

        # 가장 저렴한 모델로 메모리 추출 (Gemini Flash → GPT Mini → Claude)
        _mem_providers = get_available_providers()
        if _mem_providers.get("google"):
            _mem_model = "gemini-2.5-flash"
        elif _mem_providers.get("openai"):
            _mem_model = "gpt-5-mini"
        else:
            _mem_model = "claude-sonnet-4-6"
        result = await ask_ai(
            user_message=extraction_prompt,
            model=_mem_model,
            max_tokens=400,
            system_prompt="JSON만 반환. 설명 없이."
        )

        text_resp = result.get("content", "") if isinstance(result, dict) else str(result)
        text_resp = text_resp.strip()
        # JSON 블록 추출
        if "```" in text_resp:
            text_resp = text_resp.split("```")[1].strip()
            if text_resp.startswith("json"):
                text_resp = text_resp[4:].strip()

        new_facts = json.loads(text_resp)
        if new_facts and isinstance(new_facts, dict):
            existing = load_setting(f"memory_categorized_{agent_id}", {})
            for key, val in new_facts.items():
                if val and val not in ("null", "없음", ""):
                    prev = existing.get(key, "")
                    existing[key] = (prev + " | " + str(val)).strip(" |") if prev else str(val)
            save_setting(f"memory_categorized_{agent_id}", existing)
    except Exception as e:
        logger.debug(f"기억 추출 건너뜀 ({agent_id}): {e}")


async def _call_agent(agent_id: str, text: str, conversation_id: str | None = None) -> dict:
    """단일 에이전트에게 AI 호출을 수행합니다 (상태 이벤트 + 활동 로그 + 도구 자동호출 포함)."""
    agent_name = _AGENT_NAMES.get(agent_id, _SPECIALIST_NAMES.get(agent_id, agent_id))
    await _broadcast_status(agent_id, "working", 0.1, f"{agent_name} 작업 준비 중...")

    # 활동 로그 — 누가 일하는지 기록
    log_entry = save_activity_log(agent_id, f"[{agent_name}] 작업 시작: {text[:40]}...")
    await wm.send_activity_log(log_entry)

    soul = _load_agent_prompt(agent_id)

    # ── 에이전트 기억 주입 (카테고리별 기억 → system_prompt 앞에 삽입) ──
    mem = load_setting(f"memory_categorized_{agent_id}", {})
    if mem:
        mem_lines = []
        if mem.get("ceo_preferences"):
            mem_lines.append(f"- CEO 취향/선호: {mem['ceo_preferences']}")
        if mem.get("decisions"):
            mem_lines.append(f"- 주요 결정: {mem['decisions']}")
        if mem.get("warnings"):
            mem_lines.append(f"- 주의사항: {mem['warnings']}")
        if mem.get("context"):
            mem_lines.append(f"- 중요 맥락: {mem['context']}")
        if mem_lines:
            memory_block = "[에이전트 기억]\n" + "\n".join(mem_lines) + "\n\n"
            soul = memory_block + soul

    override = _get_model_override(agent_id)
    model = select_model(text, override=override)

    # ── 도구 자동호출 (Function Calling) ──
    # 에이전트별 허용 도구 목록으로 스키마를 로드하고, 도구 실행 함수를 전달
    tool_schemas = None
    tool_executor_fn = None
    tools_used: list[str] = []  # 사용한 도구 이름 추적
    detail = _AGENTS_DETAIL.get(agent_id, {})
    allowed = detail.get("allowed_tools", [])
    if allowed:
        schemas = _load_tool_schemas(allowed_tools=allowed)
        if schemas.get("anthropic"):
            tool_schemas = schemas["anthropic"]  # ask_ai 내부에서 프로바이더별 변환

            _MAX_TOOL_CALLS = int(detail.get("max_tool_calls", 5))  # agents.yaml에서 에이전트별 설정, 기본값 5

            async def _tool_executor(tool_name: str, tool_input: dict):
                """ToolPool을 통해 도구를 실행합니다."""
                tools_used.append(tool_name)
                call_count = len(tools_used)
                # 도구 호출 횟수 기반 진행률 계산 (1회=20%, 2회=40%, ..., 5회=100%)
                tool_progress = 0.3 + min(call_count / _MAX_TOOL_CALLS, 1.0) * 0.35
                tool_progress_pct = int(tool_progress * 100)

                # 도구 호출 횟수 포함 agent_status 이벤트 발송
                await wm.send_agent_status(
                    agent_id, "working", round(tool_progress, 2),
                    f"{tool_name} 실행 중...",
                    tool_calls=call_count, max_calls=_MAX_TOOL_CALLS, tool_name=tool_name,
                )

                # 도구 사용 실시간 브로드캐스트 (도구로그 탭에 표시)
                tool_log = save_activity_log(
                    agent_id, f"🔧 [{agent_name}] {tool_name} 호출 ({call_count}회)",
                    level="tool"
                )
                await wm.send_activity_log(tool_log)

                pool = _init_tool_pool()
                if pool:
                    try:
                        # pool.invoke()로 호출 — _caller_model 자동 주입 (에이전트 모델 따라감)
                        return await pool.invoke(tool_name, caller_id=agent_id, **tool_input)
                    except Exception as e:
                        if "ToolNotFoundError" in type(e).__name__ or tool_name in str(e):
                            return f"도구 '{tool_name}'을(를) 찾을 수 없습니다."
                        raise
                # ToolPool 미초기화
                return f"도구 '{tool_name}'을(를) 찾을 수 없습니다."

            tool_executor_fn = _tool_executor

    # ── 최근 대화 기록 로드 (대화 맥락 유지) ──
    conv_history = _build_conv_history(conversation_id, text)

    await _broadcast_status(agent_id, "working", 0.3, "AI 응답 생성 중...")
    result = await ask_ai(text, system_prompt=soul, model=model,
                          tools=tool_schemas, tool_executor=tool_executor_fn,
                          reasoning_effort=_get_agent_reasoning_effort(agent_id),
                          conversation_history=conv_history)
    await _broadcast_status(agent_id, "working", 0.7, "응답 처리 중...")

    if "error" in result:
        # 에러 발생 시 (타임아웃 등) — 에러 내용과 함께 기록
        try:
            from db import save_agent_call
            save_agent_call(
                agent_id=agent_id, model=model or "error",
                provider="", cost_usd=0, input_tokens=0, output_tokens=0, time_seconds=0,
            )
        except Exception:
            pass
        await _broadcast_status(agent_id, "done", 1.0, "오류 발생")
        # 에러 활동 로그
        log_err = save_activity_log(agent_id, f"[{agent_name}] ❌ 오류: {result['error'][:80]}", "warning")
        await wm.send_activity_log(log_err)
        return {"agent_id": agent_id, "name": agent_name, "error": result["error"], "cost_usd": 0}

    # agent_calls 테이블에 AI 호출 기록 저장 (성공 시)
    try:
        from db import save_agent_call
        save_agent_call(
            agent_id=agent_id,
            model=result.get("model", model) if isinstance(result, dict) else model,
            provider=result.get("provider", "") if isinstance(result, dict) else "",
            cost_usd=result.get("cost_usd", 0) if isinstance(result, dict) else 0,
            input_tokens=result.get("input_tokens", 0) if isinstance(result, dict) else 0,
            output_tokens=result.get("output_tokens", 0) if isinstance(result, dict) else 0,
            time_seconds=result.get("time_seconds", 0) if isinstance(result, dict) else 0,
        )
    except Exception as e:
        _log(f"[AGENT_CALL] 기록 실패: {e}")

    await _broadcast_status(agent_id, "working", 0.9, "저장 완료...")
    await _broadcast_status(agent_id, "done", 1.0, "완료")

    # 완료 로그
    cost = result.get("cost_usd", 0)
    content = result.get("content", "")
    log_done = save_activity_log(agent_id, f"[{agent_name}] 작업 완료 (${cost:.4f})")
    await wm.send_activity_log(log_done)

    # ── 비용 업데이트 브로드캐스트 (프론트엔드 우측 상단 금액 실시간 반영) ──
    try:
        today_cost = get_today_cost()
    except Exception:
        today_cost = cost
    await wm.send_cost_update(today_cost)

    # ── 기억 자동 추출 (비동기 백그라운드 — 응답에서 중요 정보 저장) ──
    if content and len(content) > 30:
        asyncio.create_task(_extract_and_save_memory(agent_id, text, content))

    # 산출물 저장 (노션 + 아카이브 DB)
    if content and len(content) > 20:
        # 노션에 저장 (비동기, 실패해도 무시)
        asyncio.create_task(_save_to_notion(
            agent_id=agent_id,
            title=_extract_notion_title(content, f"[{agent_name}] 보고서", user_query=text),
            content=content,
            db_target="secretary" if _AGENT_DIVISION.get(agent_id) == "secretary" else "output",
        ))
        # 아카이브 DB에 저장 (영구 보관)
        division = _AGENT_DIVISION.get(agent_id, "secretary")
        now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        # 사용한 도구 메타데이터를 콘텐츠 맨 아래에 추가
        if tools_used:
            unique_tools = list(dict.fromkeys(tools_used))  # 중복 제거, 순서 유지
            content += f"\n\n---\n🔧 **사용한 도구**: {', '.join(unique_tools)}"

        # 제목 추출: AI 응답에서 의미 있는 제목을 뽑아서 파일명에 사용
        _title = _extract_notion_title(content, text[:40], user_query=text)
        _safe_title = re.sub(r'[\\/:*?"<>|\n\r]', '', _title)[:30].strip()
        archive_content = f"# [{agent_name}] {_safe_title}\n\n{content}"
        save_archive(
            division=division,
            filename=f"{agent_id}_{_safe_title}_{now_str}.md",
            content=archive_content,
            agent_id=agent_id,
        )

    return {
        "agent_id": agent_id,
        "name": agent_name,
        "content": content,
        "cost_usd": cost,
        "model": result.get("model", ""),
        "time_seconds": result.get("time_seconds", 0),
        "input_tokens": result.get("input_tokens", 0),
        "output_tokens": result.get("output_tokens", 0),
        "tools_used": tools_used,
    }


async def _chief_qa_review(report_content: str, team_leader_name: str) -> tuple[bool, str]:
    """비서실장이 팀장 보고서를 QA합니다. (승인/반려)

    비유: 비서실장이 팀장 보고서를 읽고 "이거 CEO한테 올려도 되나?" 검수.
    Returns: (passed: bool, reason: str)
    """
    if not report_content or len(report_content.strip()) < 50:
        return False, "보고서 내용이 너무 짧습니다 (50자 미만)"

    qa_prompt = f"""당신은 비서실장입니다. {team_leader_name}의 보고서를 검수하세요.

## 보고서
{report_content[:8000]}

## 검수 기준 (5항목, 각 통과/미달)
1. **결론 존재**: 매수/매도/관망 시그널이 명확한가?
2. **근거 제시**: 시그널에 데이터 기반 근거가 있는가? (숫자, 지표)
3. **리스크 언급**: 손절가/최대손실/주의사항이 있는가?
4. **형식 준수**: [시그널] 형식으로 종목별 결과가 있는가?
5. **논리 일관성**: 분석과 결론이 모순되지 않는가?

## 응답 형식 (반드시 첫 줄에 이 형식만)
판정: PASS 또는 FAIL
사유: [1줄 요약]"""

    try:
        soul = _load_agent_prompt("chief_of_staff")
        override = _get_model_override("chief_of_staff")
        model = select_model(qa_prompt, override=override)
        result = await ask_ai(
            qa_prompt,
            system_prompt=soul,
            model=model,
            reasoning_effort=_get_agent_reasoning_effort("chief_of_staff"),
        )
        qa_text = result.get("content", "")

        # 파싱: "판정: PASS" or "판정: FAIL" (영어 키워드로 오판 방지)
        qa_upper = qa_text.upper()
        if "PASS" in qa_upper and "FAIL" not in qa_upper:
            passed = True
        elif "FAIL" in qa_upper:
            passed = False
        else:
            # 폴백: 한국어 키워드
            passed = "승인" in qa_text and "반려" not in qa_text[:200]
        reason = ""
        for line in qa_text.split("\n"):
            if "사유" in line and ":" in line:
                reason = line.split(":", 1)[-1].strip()
                break
        if not reason:
            reason = "승인" if passed else "기준 미달"

        return passed, reason
    except Exception as e:
        logger.warning("비서실장 QA 실패 (기본 승인): %s", e)
        return True, f"QA 시스템 오류로 기본 승인: {str(e)[:60]}"


async def _delegate_to_specialists(manager_id: str, text: str) -> list[dict]:
    """팀장이 소속 전문가들에게 병렬로 위임합니다.

    asyncio.gather로 전문가들을 동시에 호출 → 상태 표시등 전부 깜빡임.
    위임 발생 시 delegation_log에 자동 기록합니다.
    """
    specialists = _MANAGER_SPECIALISTS.get(manager_id, [])
    if not specialists:
        return []

    # 위임 로그 자동 기록 + WebSocket + SSE broadcast
    try:
        from db import save_delegation_log
        import time as _time
        mgr_name = _AGENT_NAMES.get(manager_id, manager_id)
        # 위임 제목 추출 (CEO 원문에서 짧은 요약)
        _deleg_title = _extract_notion_title(text, text[:30])[:40]
        for spec_id in specialists:
            spec_name = _SPECIALIST_NAMES.get(spec_id, spec_id)
            row_id = save_delegation_log(
                sender=mgr_name,
                receiver=spec_name,
                message=text[:500],
                log_type="delegation",
            )
            _log_data = {
                "id": row_id,
                "sender": mgr_name,
                "receiver": spec_name,
                "title": _deleg_title,
                "message": text[:300],
                "log_type": "delegation",
                "created_at": _time.time(),
            }
            await wm.send_delegation_log(_log_data)
    except Exception as e:
        logger.debug("위임 로그 브로드캐스트 실패: %s", e)

    # 전문가 전원 즉시 병렬 출발 (시차 없음)
    # Google 키 4개 로테이션 + 속도 제한기가 429 방지 담당
    tasks = [_call_agent(spec_id, _SPECIALIST_ROLE_PREFIX.get(spec_id, "") + text) for spec_id in specialists]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed = []
    for i, r in enumerate(results):
        spec_id = specialists[i]
        if isinstance(r, Exception):
            processed.append({"agent_id": spec_id, "name": _SPECIALIST_NAMES.get(spec_id, spec_id), "error": str(r)[:100], "cost_usd": 0})
        else:
            # 전문가 결과 보고 로그 자동 기록 + WebSocket + SSE broadcast
            try:
                from db import save_delegation_log
                import time as _time
                spec_name = _SPECIALIST_NAMES.get(spec_id, spec_id)
                mgr_name = _AGENT_NAMES.get(manager_id, manager_id)
                content_preview = r.get("content", "")[:300] if isinstance(r, dict) else str(r)[:300]
                _tools = r.get("tools_used", []) if isinstance(r, dict) else []
                _tools_unique = list(dict.fromkeys(_tools))[:5]  # 중복 제거, 최대 5개
                _tools_str = ",".join(_tools_unique) if _tools_unique else ""
                # 보고 제목 추출 (응답 내용에서 짧은 요약)
                _rpt_title = _extract_notion_title(
                    r.get("content", "") if isinstance(r, dict) else str(r),
                    f"{spec_name} 보고", user_query=text
                )[:40]
                row_id = save_delegation_log(
                    sender=spec_name,
                    receiver=mgr_name,
                    message=content_preview,
                    log_type="report",
                    tools_used=_tools_str,
                )
                _log_data = {
                    "id": row_id,
                    "sender": spec_name,
                    "receiver": mgr_name,
                    "title": _rpt_title,
                    "message": content_preview,
                    "log_type": "report",
                    "tools_used": _tools_unique,
                    "created_at": _time.time(),
                }
                await wm.send_delegation_log(_log_data)
            except Exception as e:
                logger.debug("보고 로그 브로드캐스트 실패: %s", e)
            processed.append(r)
    return processed


async def _manager_with_delegation(manager_id: str, text: str, conversation_id: str | None = None) -> dict:
    """팀장이 전문가에게 위임 → 결과 종합(검수) → 보고서 작성.

    흐름: 팀장 분석 시작 → 전문가 병렬 호출 → 팀장이 결과 종합 + 검수 → 보고서 반환
    검수: 팀장이 전문가 결과를 읽고 종합하는 과정 자체가 품질 검수 역할을 합니다.
    """
    mgr_name = _AGENT_NAMES.get(manager_id, manager_id)
    specialists = _MANAGER_SPECIALISTS.get(manager_id, [])
    spec_names = [_SPECIALIST_NAMES.get(s, s) for s in specialists]

    # 전문가가 없으면 팀장이 직접 처리
    if not specialists:
        return await _call_agent(manager_id, text, conversation_id=conversation_id)

    # ── 팀장 독자 분석 함수 (CEO 아이디어: 팀장 = 5번째 분석가) ──
    # 전문가와 병렬로 팀장도 독자적으로 도구를 사용하여 분석 수행.
    # "종합 때 도구 써라"(프롬프트 의존) → "독자분석 따로 돌려"(구조적 강제)
    async def _manager_self_analysis():
        """팀장 독자 분석 — 전문가와 동일하게 도구 사용. 구조적 도구 사용 보장."""
        log_self = save_activity_log(manager_id,
            f"[{mgr_name}] 🔧 독자 분석 시작 (5번째 분석가)", "info")
        await wm.send_activity_log(log_self)
        self_prompt = (
            f"당신은 {mgr_name}입니다. 전문가들과 별개로 독자적 분석을 수행하세요.\n"
            f"반드시 도구(API)를 사용하여 실시간 데이터를 직접 조회하고 분석하세요.\n"
            f"전문가 결과는 무시하세요 — 당신만의 독립적 관점을 제시하세요.\n\n"
            f"## 분석 요청\n{text}\n"
        )
        self_result = await _call_agent(manager_id, self_prompt, conversation_id=conversation_id)
        log_done = save_activity_log(manager_id,
            f"[{mgr_name}] ✅ 독자 분석 완료", "info")
        await wm.send_activity_log(log_done)
        return self_result

    # 팀장 상태: 독자 분석 + 전문가 위임 시작
    await _broadcast_status(manager_id, "working", 0.1, "독자 분석 + 전문가 위임 중...")
    log_mgr = save_activity_log(manager_id,
        f"[{mgr_name}] 🔧 독자 분석 + 전문가 {len(specialists)}명 위임: {', '.join(spec_names)}")
    await wm.send_activity_log(log_mgr)

    # 팀장 독자분석 + 전문가 병렬 실행 (5번째 분석가 구조)
    _mgr_self_task = _manager_self_analysis()
    _spec_task = _delegate_to_specialists(manager_id, text)
    _parallel = await asyncio.gather(_mgr_self_task, _spec_task, return_exceptions=True)
    manager_self_result = _parallel[0] if not isinstance(_parallel[0], Exception) else {"error": str(_parallel[0])[:200]}
    spec_results = _parallel[1] if not isinstance(_parallel[1], Exception) else []
    if isinstance(_parallel[1], Exception):
        log_spec_err = save_activity_log(manager_id,
            f"[{mgr_name}] ⚠️ 전문가 위임 실패: {str(_parallel[1])[:100]}", "warning")
        await wm.send_activity_log(log_spec_err)

    # ── Phase 8: CIO 7단계 — (1) 선판단+독자분석 기밀문서 저장 ──
    _p8_div = _MANAGER_DIVISION.get(manager_id, "default")
    _p8_date = datetime.now(KST).strftime("%Y%m%d_%H%M")
    if isinstance(manager_self_result, dict) and "error" not in manager_self_result:
        try:
            save_archive(
                _p8_div,
                f"{mgr_name}_보고서1_독자분석_{_p8_date}.md",
                manager_self_result.get("content", ""),
                agent_id=manager_id,
            )
        except Exception as _ae_p8:
            logger.debug("Phase8 독자분석 기밀문서 저장 실패: %s", _ae_p8)

    # ── Phase 8: CIO 7단계 — (2) 전문가 보고서 각각 기밀문서 저장 ──
    for _p8r in (spec_results or []):
        if isinstance(_p8r, dict) and "error" not in _p8r:
            _p8_spec_id = _p8r.get("agent_id", "unknown")
            _p8_spec_name = _SPECIALIST_NAMES.get(_p8_spec_id, _p8_spec_id)
            try:
                save_archive(
                    _p8_div,
                    f"{_p8_spec_name}_보고서1_{_p8_date}.md",
                    _p8r.get("content", ""),
                    agent_id=_p8_spec_id,
                )
            except Exception as _ae_p8s:
                logger.debug("Phase8 전문가 기밀문서 저장 실패: %s", _ae_p8s)

    # ── 품질검수 제거됨 (2026-02-27) ──
    if False:  # 품질검수 비활성화
        await _broadcast_status(manager_id, "working", 0.45, "전문가 결과 품질검수 중...")

        # 품질검수용 pseudo-chain 구성
        _qa_chain = {
            "chain_id": f"trading_{manager_id}_{int(time.time())}",
            "target_id": manager_id,
            "original_command": text[:500],
            "total_cost_usd": 0,
            "results": {"specialists": {}},
        }
        for r in spec_results:
            if "error" not in r:
                _qa_chain["results"]["specialists"][r.get("agent_id", "unknown")] = {
                    "content": r.get("content", ""),
                    "model": r.get("model", ""),
                    "cost_usd": r.get("cost_usd", 0),
                    "tools_used": r.get("tools_used", []),
                }

        # ★ 버그#2 수정: 검수 대상 0명(전문가 전원 에러) → "합격"이 아니라 에러 경고!
        _qa_valid_count = len(_qa_chain["results"]["specialists"])
        _qa_error_count = len(spec_results) - _qa_valid_count

        if _qa_valid_count == 0:
            # 전문가 전원 에러 — QA 스킵, 에러 경고 로그
            log_err = save_activity_log(manager_id,
                f"[{mgr_name}] ⚠️ 전문가 {_qa_error_count}명 전원 에러 — 품질검수 불가 (유효 보고서 0건)", "warning")
            await wm.send_activity_log(log_err)
        else:
            _qa_note = f" (에러 {_qa_error_count}명 제외)" if _qa_error_count else ""
            log_qa = save_activity_log(manager_id,
                f"[{mgr_name}] 전문가 {_qa_valid_count}명 결과 품질검수 시작{_qa_note}", "info")
            await wm.send_activity_log(log_qa)

        failed_specs = await _quality_review_specialists(_qa_chain) if _qa_valid_count > 0 else []

        if failed_specs:
            # 불합격 전문가 활동로그
            for fs in failed_specs:
                _fs_name = _SPECIALIST_NAMES.get(fs["agent_id"], fs["agent_id"])
                log_reject = save_activity_log(manager_id,
                    f"[{mgr_name}] ❌ {_fs_name} 보고서 반려: {fs.get('reason', '품질 미달')[:80]}", "warning")
                await wm.send_activity_log(log_reject)

            # 반려 → 재작업 → 재검수
            await _handle_specialist_rework(_qa_chain, failed_specs)

            # 재작업 결과를 spec_results에 반영
            for r in spec_results:
                _aid = r.get("agent_id", "unknown")
                if _aid in _qa_chain["results"]["specialists"]:
                    updated = _qa_chain["results"]["specialists"][_aid]
                    r["content"] = updated.get("content", r.get("content", ""))
                    r["cost_usd"] = r.get("cost_usd", 0) + updated.get("cost_usd", 0)
                    if updated.get("rework_attempt"):
                        r["rework_attempt"] = updated["rework_attempt"]
                        log_rework = save_activity_log(_aid,
                            f"[{_SPECIALIST_NAMES.get(_aid, _aid)}] 재작업 완료 (시도 {updated['rework_attempt']}회)")
                        await wm.send_activity_log(log_rework)
                    if updated.get("quality_warning"):
                        r["quality_warning"] = updated["quality_warning"]
                    if updated.get("tools_used"):
                        r["tools_used"] = r.get("tools_used", []) + updated["tools_used"]
        elif _qa_valid_count > 0:
            # 불합격 0명 + 검수 대상 1명 이상 → 진짜 전원 합격
            log_pass = save_activity_log(manager_id,
                f"[{mgr_name}] ✅ 전문가 {_qa_valid_count}명 품질검수 합격", "info")
            await wm.send_activity_log(log_pass)

        # ★ 품질검수 결과를 기밀문서에 저장
        _qa_reviews = _qa_chain.get("qa_reviews", [])
        if _qa_reviews:
            try:
                _now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
                _qa_lines = [f"# 품질검수 보고서 — {mgr_name} ({_now_str})\n"]
                _qa_lines.append(f"검수 대상: {_qa_valid_count}명 | 불합격: {len(failed_specs)}명\n")
                for qr in _qa_reviews:
                    _qr_name = _SPECIALIST_NAMES.get(qr["agent_id"], qr["agent_id"])
                    _qr_pass = "✅ 합격" if qr["passed"] else "❌ 불합격"
                    _qa_lines.append(f"## {_qr_name} — {qr['weighted_average']:.1f}점 {_qr_pass}\n")
                    _rd = qr.get("review_dict", {})
                    # 체크리스트
                    for ci in _rd.get("checklist", []):
                        _st = "✅" if ci["passed"] else "❌"
                        _rq = " [필수]" if ci.get("required") else ""
                        _fb = f" — {ci['feedback']}" if ci.get("feedback") and not ci["passed"] else ""
                        _qa_lines.append(f"- 📋 {ci['id']} {ci.get('label','')}: {_st}{_rq}{_fb}")
                    # 점수
                    for si in _rd.get("scores", []):
                        _cr = " ⚠️치명적" if si.get("critical") and si["score"] == 1 else ""
                        _fb = f" — {si['feedback']}" if si.get("feedback") and si["score"] <= 3 else ""
                        _qa_lines.append(f"- 📊 {si['id']} {si.get('label','')}: {si['score']}점/5 (가중 {si.get('weight',0)}%){_cr}{_fb}")
                    # 반려 사유
                    _rej = _rd.get("rejection_reasons", [])
                    if _rej:
                        _qa_lines.append(f"\n**반려 사유**: {' / '.join(_rej)}")
                    _qa_lines.append("")
                _qa_content = "\n".join(_qa_lines)
                _qa_filename = f"QA_{mgr_name}_{datetime.now(KST).strftime('%Y%m%d_%H%M')}.md"
                _division = _MANAGER_DIVISION.get(manager_id, "default")
                save_archive(
                    division=_division,
                    filename=_qa_filename,
                    content=_qa_content,
                    correlation_id=_qa_chain.get("chain_id", ""),
                    agent_id=manager_id,
                )
                _log(f"[QA] 품질검수 보고서 기밀문서 저장: {_qa_filename}")
            except Exception as e:
                _log(f"[QA] 기밀문서 저장 실패: {e}")

    # 전문가 결과 취합
    spec_parts = []
    spec_cost = 0.0
    spec_time = 0.0
    for r in spec_results:
        name = r.get("name", r.get("agent_id", "?"))
        if "error" in r:
            spec_parts.append(f"[{name}] 오류: {r['error'][:80]}")
        else:
            spec_parts.append(f"[{name}]\n{r.get('content', '응답 없음')}")
            spec_cost += r.get("cost_usd", 0)
            spec_time = max(spec_time, r.get("time_seconds", 0))

    # 팀장 독자분석 결과 취합
    manager_self_content = ""
    mgr_self_tools: list[str] = []
    if isinstance(manager_self_result, dict) and "error" not in manager_self_result:
        manager_self_content = manager_self_result.get("content", "")
        mgr_self_tools = manager_self_result.get("tools_used", [])
        spec_cost += manager_self_result.get("cost_usd", 0)
        spec_time = max(spec_time, manager_self_result.get("time_seconds", 0))

    # 전문가 성공/실패 집계
    _spec_ok_count = len([r for r in spec_results if "error" not in r])
    _spec_err_count = len(spec_results) - _spec_ok_count

    # 팀장 종합 프롬프트 — 독자분석 + 전문가 결과 취합만 (도구 불필요)
    # CEO 아이디어: 팀장 독자분석에서 이미 도구 사용 완료 → 종합은 단순 취합
    synthesis_prompt = (
        f"당신은 {mgr_name}입니다.\n"
        f"아래 분석 결과(당신의 독자 분석 + 전문가)를 종합하여 최종 보고서를 작성하세요.\n"
        f"도구를 다시 사용할 필요 없습니다 — 결과를 취합만 하세요.\n\n"
        f"## CEO 원본 명령\n{text}\n\n"
        f"## 팀장 독자 분석\n{manager_self_content or '(분석 실패)'}\n\n"
        f"## 전문가 분석 결과\n" + "\n\n".join(spec_parts)
    )

    soul = _load_agent_prompt(manager_id)
    override = _get_model_override(manager_id)
    model = select_model(synthesis_prompt, override=override)

    await _broadcast_status(manager_id, "working", 0.7, "독자분석 + 전문가 결과 종합 중...")
    synthesis = await ask_ai(synthesis_prompt, system_prompt=soul, model=model,
                             tools=None, tool_executor=None,
                             reasoning_effort=_get_agent_reasoning_effort(manager_id))

    await _broadcast_status(manager_id, "done", 1.0, "보고 완료")

    if "error" in synthesis:
        # 종합 실패 시 독자분석 + 전문가 결과 반환
        _spec_ok = len([r for r in spec_results if "error" not in r])
        content = f"**{mgr_name} 독자 분석**\n\n{manager_self_content or '(분석 실패)'}\n\n---\n\n**전문가 분석 결과**\n\n" + "\n\n---\n\n".join(spec_parts)
        _all_spec_tools = [t for r in spec_results if isinstance(r, dict) and "error" not in r for t in r.get("tools_used", [])]
        return {"agent_id": manager_id, "name": mgr_name, "content": content, "cost_usd": spec_cost, "specialists_used": _spec_ok, "tools_used": mgr_self_tools + _all_spec_tools}

    total_cost = spec_cost + synthesis.get("cost_usd", 0)
    specialists_used = len([r for r in spec_results if "error" not in r])
    synth_content = synthesis.get("content", "")

    # 전문가 개별 산출물도 노션에 저장 (spawn된 전문가 결과 전부 기록)
    for r in spec_results:
        if "error" not in r and r.get("content") and len(r["content"]) > 20:
            _sid = r.get("agent_id", "unknown")
            _sname = r.get("name", _sid)
            asyncio.create_task(_save_to_notion(
                agent_id=_sid,
                title=_extract_notion_title(r["content"], f"[{_sname}] 분석보고", user_query=text),
                content=r["content"],
                report_type="전문가보고서",
                db_target="output",
            ))

    # 종합 보고서 저장 (노션 + 아카이브 DB)
    if synth_content and len(synth_content) > 20:
        asyncio.create_task(_save_to_notion(
            agent_id=manager_id,
            title=_extract_notion_title(synth_content, f"[{mgr_name}] 종합보고", user_query=text),
            content=synth_content,
            report_type="종합보고서",
            db_target="secretary" if _AGENT_DIVISION.get(manager_id) == "secretary" else "output",
        ))
        # 아카이브 DB에 저장 (제목 추출하여 파일명에 포함)
        division = _AGENT_DIVISION.get(manager_id, "secretary")
        now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        _synth_title = _extract_notion_title(synth_content, text[:40], user_query=text)
        _safe_synth = re.sub(r'[\\/:*?"<>|\n\r]', '', _synth_title)[:30].strip()
        archive_content = f"# [{mgr_name}] 종합보고: {_safe_synth}\n\n{synth_content}"
        save_archive(
            division=division,
            filename=f"{manager_id}_{_safe_synth}_{now_str}.md",
            content=archive_content,
            agent_id=manager_id,
        )

    # 팀장 독자분석 도구 사용 기록 로그
    if mgr_self_tools:
        _unique_self = list(dict.fromkeys(mgr_self_tools))
        log_tools = save_activity_log(manager_id,
            f"[{mgr_name}] 🔧 독자 분석 도구 {len(mgr_self_tools)}건 사용 (고유 {len(_unique_self)}개): {', '.join(_unique_self[:5])}", "tool")
        await wm.send_activity_log(log_tools)

    return {
        "agent_id": manager_id,
        "name": mgr_name,
        "content": synth_content,
        "cost_usd": total_cost,
        "model": synthesis.get("model", ""),
        "time_seconds": round(spec_time + synthesis.get("time_seconds", 0), 2),
        "specialists_used": specialists_used,
        "tools_used": mgr_self_tools,
    }


def _determine_routing_level(text: str) -> tuple[int, str | None]:
    """질문 복잡도에 따라 Level 1~4와 대상 팀장 ID 반환.

    Returns: (level, manager_id_or_None)
    - Level 1: 간단한 인사/단순 질문 → 비서실장 직접 처리 (팀장 호출 없음)
    - Level 2: 특정 부서 전문 질문 → 팀장 1명만 호출
    - Level 3: 특정 부서 심층 분석 → 팀장 1명 + spawn_agent 자율 전문가 선택
    - Level 4: 복합/전사 질문 → 전원 병렬 호출 (기존 브로드캐스트)
    """
    t = text.lower()

    # Level 1: 간단한 요청 — 비서실장 직접 처리
    SIMPLE_KEYWORDS = ["안녕", "안녕하세요", "고마워", "감사합니다", "일정", "뭐야",
                       "언제야", "뭔가요", "알려줘", "찾아줘", "확인해줘"]
    if len(text) < 50 and any(k in t for k in SIMPLE_KEYWORDS):
        return (1, None)

    # Level 2/3: 특정 부서 전문 질문
    MANAGER_KEYWORDS = {
        "cto_manager": ["기술", "개발", "코드", "api", "서버", "앱", "웹", "프론트", "백엔드", "인프라", "ai 모델", "데이터베이스"],
        "cso_manager": ["사업", "시장", "재무", "전략", "비즈니스", "계획", "수익", "매출", "투자 계획"],
        "clo_manager": ["법", "계약", "저작권", "특허", "약관", "법률", "ip"],
        "cmo_manager": ["마케팅", "고객", "콘텐츠", "sns", "광고", "커뮤니티", "브랜딩"],
        "cio_manager": ["투자", "주식", "코스피", "시황", "종목", "리스크", "포트폴리오", "etf", "채권"],
        "cpo_manager": ["기록", "출판", "블로그", "연대기", "회고", "편집", "아카이브"],
    }

    matched_manager = None
    for mgr_id, keywords in MANAGER_KEYWORDS.items():
        if any(k in t for k in keywords):
            matched_manager = mgr_id
            break

    if matched_manager:
        DEEP_KEYWORDS = ["분석", "보고서", "전략", "계획서", "검토", "평가", "비교", "예측", "전망"]
        if any(k in t for k in DEEP_KEYWORDS):
            return (3, matched_manager)
        return (2, matched_manager)

    return (4, None)


async def _manager_with_delegation_autonomous(manager_id: str, text: str, conversation_id: str | None = None) -> dict:
    """팀장이 spawn_agent 도구로 필요한 전문가만 자율 선택하여 호출 (Level 3용)."""
    agent_cfg = next((a for a in AGENTS if a.get("agent_id") == manager_id), None)
    if not agent_cfg:
        return {"content": f"에이전트 설정을 찾을 수 없습니다: {manager_id}", "error": True}

    soul = _load_agent_prompt(manager_id)
    specialists_pool = _MANAGER_SPECIALISTS.get(manager_id, [])

    # spawn_agent 도구 스키마
    spawn_tool = {
        "name": "spawn_agent",
        "description": (
            f"소속 전문가를 호출하여 특정 분석을 수행합니다. "
            f"사용 가능한 전문가 ID: {', '.join(specialists_pool)}"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "호출할 전문가 에이전트 ID",
                    "enum": specialists_pool,
                },
                "task": {
                    "type": "string",
                    "description": "전문가에게 지시할 구체적인 작업 내용",
                }
            },
            "required": ["agent_id", "task"]
        }
    }

    specialist_results: dict[str, str] = {}

    async def _spawn_executor(tool_name: str, tool_input: dict) -> str:
        if tool_name == "spawn_agent":
            sid = tool_input.get("agent_id", "")
            task = tool_input.get("task", "")
            if sid in specialists_pool:
                logger.info("spawn_agent: %s → %s", manager_id, sid)
                await _broadcast_status(manager_id, "working", 0.5, f"전문가 {_SPECIALIST_NAMES.get(sid, sid)} 호출 중...")
                result = await _call_agent(sid, task, conversation_id=conversation_id)
                content = result.get("content", "")
                specialist_results[sid] = content
                return content
        return "알 수 없는 도구입니다."

    mgr_name = _AGENT_NAMES.get(manager_id, manager_id)
    await _broadcast_status(manager_id, "working", 0.2, f"{mgr_name} 분석 중 (자율 전문가 선택)...")

    override = _get_model_override(manager_id)
    model = select_model(text, override=override)

    result = await ask_ai(
        text,
        system_prompt=soul,
        model=model,
        tools=[spawn_tool],
        tool_executor=_spawn_executor,
    )

    await _broadcast_status(manager_id, "done", 1.0, "보고 완료")

    return {
        "content": result.get("content", ""),
        "specialist_results": specialist_results,
        "manager_id": manager_id,
        "cost_usd": result.get("cost_usd", 0),
        "time_seconds": result.get("time_seconds", 0),
    }


async def _chief_finalize(original_text: str, manager_results: dict) -> dict:
    """Level 2/3 완료 후 비서실장이 최종 보고서 1개 작성."""
    chief_cfg = next((a for a in AGENTS if a.get("agent_id") == "chief_of_staff"), None)
    if not chief_cfg:
        # fallback: 팀장 결과 그대로 반환
        combined = "\n\n".join(r.get("content", "") for r in manager_results.values())
        return {"content": combined}

    results_text = "\n\n".join(
        f"[{mgr_id} 보고]\n{res.get('content', '')}"
        for mgr_id, res in manager_results.items()
    )

    synthesis_prompt = (
        f"CEO 질문: {original_text}\n\n"
        f"팀장 보고 내용:\n{results_text}\n\n"
        "위 내용을 바탕으로 CEO에게 드릴 최종 보고서를 작성하세요. "
        "핵심 결론을 먼저, 세부 내용을 뒤에 정리하세요."
    )

    soul = _load_agent_prompt("chief_of_staff")
    override = _get_model_override("chief_of_staff")
    model = select_model(synthesis_prompt, override=override)

    result = await ask_ai(
        synthesis_prompt,
        system_prompt=soul,
        model=model,
    )

    return {"content": result.get("content", ""), "routing_level": "finalized", "cost_usd": result.get("cost_usd", 0)}


async def _broadcast_to_managers_all(text: str, task_id: str, conversation_id: str | None = None) -> dict:
    """Level 4: 기존 방식 — 활성 팀장 병렬 호출 (브로드캐스트)."""
    # dormant 제외한 활성 팀장만
    managers = [m for m in ["cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]
                if m not in _DORMANT_MANAGERS]
    staff_specialists = []  # 비서실 보좌관도 동면 (전문가 전원 동면 체제)

    # 비서실장 상태: 전달 중
    await _broadcast_status("chief_of_staff", "working", 0.1, f"{len(managers)}개 부서 팀장에게 명령 하달 중...")

    # 활동 로그
    log_entry = save_activity_log("chief_of_staff", f"[비서실장] {len(managers)}개 팀장에게 명령 전달: {text[:40]}...")
    await wm.send_activity_log(log_entry)

    # ── 1단계: 6개 팀장 + 비서실 보좌관 3명 동시 호출 ──
    mgr_tasks = [_manager_with_delegation(mgr_id, text, conversation_id=conversation_id) for mgr_id in managers]
    staff_tasks = [_call_agent(spec_id, text, conversation_id=conversation_id) for spec_id in staff_specialists]
    all_results = await asyncio.gather(*(mgr_tasks + staff_tasks), return_exceptions=True)

    mgr_results = all_results[:6]
    staff_results = all_results[6:]

    # ── 2단계: 팀장 결과 정리 (기밀문서에는 이미 _manager_with_delegation에서 저장됨) ──
    mgr_summaries = []  # 비서실장에게 전달할 요약
    total_cost = 0.0
    total_time = 0.0
    success_count = 0
    total_specialists = 0

    for i, result in enumerate(mgr_results):
        mgr_id = managers[i]
        mgr_name = _AGENT_NAMES.get(mgr_id, mgr_id)

        if isinstance(result, Exception):
            mgr_summaries.append(f"[{mgr_name}] 오류: {str(result)[:100]}")
        elif "error" in result:
            mgr_summaries.append(f"[{mgr_name}] 오류: {result['error'][:200]}")
        else:
            specs = result.get("specialists_used", 0)
            total_specialists += specs
            mgr_summaries.append(f"[{mgr_name}] (전문가 {specs}명)\n{result.get('content', '응답 없음')}")
            total_cost += result.get("cost_usd", 0)
            total_time = max(total_time, result.get("time_seconds", 0))
            success_count += 1

    # 보좌관 결과 정리
    staff_summaries = []
    for i, result in enumerate(staff_results):
        spec_id = staff_specialists[i]
        spec_name = _SPECIALIST_NAMES.get(spec_id, spec_id)

        if isinstance(result, Exception):
            staff_summaries.append(f"[{spec_name}] 오류: {str(result)[:100]}")
        elif "error" in result:
            staff_summaries.append(f"[{spec_name}] 오류: {result['error'][:200]}")
        else:
            staff_summaries.append(f"[{spec_name}]\n{result.get('content', '응답 없음')}")
            total_cost += result.get("cost_usd", 0)
            total_time = max(total_time, result.get("time_seconds", 0))

    # ── 3단계: 비서실장이 AI로 종합 보고서 작성 ──
    await _broadcast_status("chief_of_staff", "working", 0.8, "종합 보고서 작성 중...")

    synthesis_input = (
        f"CEO 원본 명령: {text}\n\n"
        f"## 6개 부서 팀장 보고서\n\n"
        + "\n\n---\n\n".join(mgr_summaries)
        + f"\n\n## 비서실 보좌관 보고\n\n"
        + "\n\n".join(staff_summaries)
    )

    synthesis_system = (
        "당신은 비서실장입니다. 6개 부서 팀장과 비서실 보좌관 3명의 보고를 검토하고, "
        "CEO에게 종합 보고서를 작성하세요.\n\n"
        "## 반드시 아래 구조를 따를 것\n\n"
        "### 핵심 요약\n"
        "(전체 상황을 1~2문장으로 요약)\n\n"
        "### 부서별 한줄 요약\n"
        "| 부서 | 핵심 내용 | 상태 |\n"
        "|------|----------|------|\n"
        "| CTO (기술개발) | ... | 정상/주의/위험 |\n"
        "(6개 부서 전부)\n\n"
        "### CEO 결재/결정 필요 사항\n"
        "(각 팀장 보고서에서 CEO가 결정해야 할 것만 추출. 체크리스트 형태)\n"
        "- [ ] 부서명: 결정 사항 — 배경 설명\n"
        "(결재할 것이 없으면 '현재 결재 대기 사항 없음')\n\n"
        "### 특이사항 / 리스크\n"
        "(각 보고서에서 리스크 요소만 추출. 없으면 '특이사항 없음')\n\n"
        "### 비서실 보좌관 보고\n"
        "- 기록 보좌관: (1줄 요약)\n"
        "- 일정 보좌관: (1줄 요약)\n"
        "- 소통 보좌관: (1줄 요약)\n\n"
        "## 규칙\n"
        "- 한국어로 작성\n"
        "- 간결하게. CEO가 30초 안에 핵심을 파악할 수 있게\n"
        "- 중요한 숫자/데이터는 반드시 포함\n"
        "- 팀장 보고서를 그대로 복사하지 말고, 핵심만 추출하여 재구성\n"
    )

    soul = _load_agent_prompt("chief_of_staff")
    override = _get_model_override("chief_of_staff")
    model = select_model(synthesis_input, override=override)

    chief_synthesis = await ask_ai(
        synthesis_input,
        system_prompt=synthesis_system + "\n\n" + soul,
        model=model,
    )

    await _broadcast_status("chief_of_staff", "done", 1.0, "종합 보고 완료")

    # 종합 보고서 비용 추가
    if "error" not in chief_synthesis:
        total_cost += chief_synthesis.get("cost_usd", 0)

    # ── 4단계: 최종 출력 = 비서실장 종합 보고서만 ──
    if "error" in chief_synthesis:
        # 종합 실패 시 팀장 요약만 간단히 표시
        chief_content = "⚠️ 비서실장 종합 보고서 작성 실패\n\n" + "\n\n---\n\n".join(
            f"**{_AGENT_NAMES.get(managers[i], managers[i])}**: "
            + (mgr_results[i].get("content", "")[:100] + "..." if not isinstance(mgr_results[i], Exception) else "오류")
            for i in range(6)
        )
    else:
        chief_content = chief_synthesis.get("content", "")

    # 맨 아래 안내 추가
    final_content = (
        f"📋 **비서실장 종합 보고** "
        f"(6개 팀장 + 전문가 {total_specialists}명 + 보좌관 3명 동원)\n\n"
        f"{chief_content}\n\n"
        f"---\n\n"
        f"📂 **상세 보고서 {success_count}건이 기밀문서에 저장되었습니다.** "
        f"기밀문서 탭에서 부서별 필터로 각 팀장의 전체 보고서를 확인할 수 있습니다."
    )

    # 비서실장 종합 보고서도 아카이브에 저장
    now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    save_archive(
        division="secretary",
        filename=f"chief_of_staff_broadcast_{now_str}.md",
        content=f"# [비서실장] 종합 보고: {text[:50]}\n\n{chief_content}",
        agent_id="chief_of_staff",
    )

    # DB 업데이트
    update_task(task_id, status="completed",
                result_summary=f"브로드캐스트 완료 ({success_count}/6 부서, 전문가 {total_specialists}명, 보좌관 3명)",
                result_data=final_content,
                success=1,
                cost_usd=total_cost,
                time_seconds=round(total_time, 2),
                agent_id="chief_of_staff")

    return {
        "content": final_content,
        "agent_id": "chief_of_staff",
        "handled_by": "비서실장 → 6개 팀장 + 보좌관 3명",
        "delegation": "비서실장 → 팀장 → 전문가",
        "total_cost_usd": round(total_cost, 6),
        "time_seconds": round(total_time, 2),
        "model": "multi-agent",
        "routing_method": "브로드캐스트",
    }


# ── 토론 시스템 (임원 회의 방식 다라운드 토론) ──

DEBATE_ROTATION = [
    ["cio_manager", "cto_manager", "cso_manager", "cmo_manager", "clo_manager", "cpo_manager"],
    ["cto_manager", "cso_manager", "cio_manager", "clo_manager", "cmo_manager", "cpo_manager"],
    ["cso_manager", "cmo_manager", "cto_manager", "cio_manager", "cpo_manager", "clo_manager"],
]

# 팀장별 토론 관점 — 1라운드에서 각자 무엇을 분석해야 하는지 구체적으로 지시
_DEBATE_LENSES: dict[str, str] = {
    "cio_manager": (
        "투자/재무 관점에서 분석하세요:\n"
        "- 이 주제가 회사 재무에 미치는 영향 (매출, 비용, ROI 수치 추정)\n"
        "- 실행 시 재무 리스크와 기회비용\n"
        "- 시장/경쟁 환경에서 타이밍이 적절한지 근거 제시"
    ),
    "cto_manager": (
        "기술 실현 가능성 관점에서 분석하세요:\n"
        "- 현재 기술 스택으로 구현 가능한지, 추가 필요한 기술은 무엇인지\n"
        "- 개발 리소스 (인력, 시간, 비용) 현실적 추정\n"
        "- 기술적 리스크 (확장성, 유지보수, 보안) 구체적으로"
    ),
    "cso_manager": (
        "사업 전략 관점에서 분석하세요:\n"
        "- 시장 규모와 경쟁 구도 (구체적 수치나 사례 인용)\n"
        "- 우리의 차별화 포인트가 무엇이고 경쟁 우위가 지속 가능한지\n"
        "- 실행 전략의 단계와 우선순위"
    ),
    "cmo_manager": (
        "마케팅/고객 관점에서 분석하세요:\n"
        "- 타겟 고객이 이것을 정말 원하는지, 어떤 근거가 있는지\n"
        "- 고객 획득 비용(CAC)과 채널 전략의 현실성\n"
        "- 브랜드/포지셔닝에 미치는 영향"
    ),
    "clo_manager": (
        "법무/리스크 관점에서 분석하세요:\n"
        "- 법적 리스크와 규제 이슈 (구체적 법령이나 판례 인용)\n"
        "- 지식재산권 보호 방안 또는 침해 위험\n"
        "- 계약/약관/개인정보 관련 주의사항"
    ),
    "cpo_manager": (
        "제품/콘텐츠 관점에서 분석하세요:\n"
        "- 사용자 경험과 제품 완성도에 미치는 영향\n"
        "- 콘텐츠 전략 및 지식 자산으로서의 가치\n"
        "- 실행 시 품질 기준과 기록/문서화 방안"
    ),
}


async def _call_agent_debate(agent_id: str, topic: str, history: str, extra_instruction: str) -> str:
    """토론용 에이전트 호출 — 주제 + 이전 발언 + 추가 지시를 결합하여 호출."""
    prompt = (
        f"[임원 토론 모드]\n"
        f"지금은 CEO가 소집한 임원 토론입니다. 보고서가 아니라 \"토론 발언\"으로 답하세요.\n"
        f"형식적인 보고서 틀(## 팀장 의견, ## 팀원 보고서 요약 등)은 사용하지 마세요.\n"
        f"대신 당신의 핵심 주장을 명확히 밝히고, 근거를 들어 설득하세요.\n\n"
        f"[토론 주제]\n{topic}\n\n"
        f"[이전 발언들]\n{history if history else '(첫 발언입니다. 다른 팀장의 의견 없이 독립적으로 발언하세요.)'}\n\n"
        f"{extra_instruction}"
    )
    result = await _call_agent(agent_id, prompt)
    return result.get("content", str(result)) if isinstance(result, dict) else str(result)


async def _broadcast_with_debate(ceo_message: str, rounds: int = 2) -> dict:
    """임원 회의 방식 토론 — CEO 메시지를 팀장들이 다단계 토론 후 비서실장이 종합."""
    debate_history = ""

    # 참가 팀장 목록 (설정에 존재하는 팀장만)
    all_managers = ["cio_manager", "cto_manager", "cso_manager", "cmo_manager", "clo_manager", "cpo_manager"]
    manager_ids = [m for m in all_managers if m in _AGENTS_DETAIL]

    for round_num in range(1, rounds + 1):
        rotation_idx = (round_num - 1) % len(DEBATE_ROTATION)
        ordered_managers = [m for m in DEBATE_ROTATION[rotation_idx] if m in manager_ids]

        if round_num == 1:
            # 라운드 1: 병렬 — 서로 모르고 독립 의견 제시 (팀장별 맞춤 분석 관점)
            tasks = []
            for mid in ordered_managers:
                lens = _DEBATE_LENSES.get(mid, "당신의 전문 분야 관점에서 구체적으로 분석하세요.")
                r1_instruction = (
                    f"\n\n[1라운드 — 독립 의견 제시]\n"
                    f"{lens}\n\n"
                    f"[발언 규칙]\n"
                    f"- 결론을 먼저 한 문장으로 제시한 뒤 근거를 대세요\n"
                    f"- \"~할 수 있다\", \"~이 좋을 것이다\" 같은 모호한 표현 금지. 구체적 수치, 사례, 기한을 넣으세요\n"
                    f"- CEO가 의사결정할 수 있는 정보를 주세요. 교과서 내용 복붙이 아니라 이 상황에 맞는 판단을 하세요\n"
                    f"- 300자 이상 800자 이하로 핵심만"
                )
                tasks.append(_call_agent_debate(mid, ceo_message, "", r1_instruction))
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for mid, resp in zip(ordered_managers, responses):
                if not isinstance(resp, Exception):
                    mgr_name = _AGENT_NAMES.get(mid, mid)
                    debate_history += f"\n[{mgr_name}의 1라운드 의견]\n{resp}\n"
        else:
            # 라운드 2+: 순차 — 이전 라운드 전체를 읽고 반박/보강
            rebuttal_instruction = (
                f"\n\n[{round_num}라운드 — 반박 및 보강]\n"
                "위 발언들을 읽고 아래 3가지를 반드시 수행하세요:\n\n"
                "1. **반박**: 다른 팀장 의견 중 가장 취약한 논리나 빠진 관점을 구체적으로 지적하세요.\n"
                "   - 누구의 어떤 주장이 왜 틀렸거나 부족한지 이름을 거론하여 명확히 밝히세요.\n"
                "   - \"일리 있지만\"으로 시작하는 빈 양보 표현 금지.\n\n"
                "2. **새로운 정보 추가**: 1라운드에서 아무도 언급하지 않은 새로운 관점, 데이터, 리스크를 하나 이상 제시하세요.\n\n"
                "3. **입장 표명**: 이 주제에 대한 당신의 최종 입장을 한 문장으로 명확히 밝히세요.\n"
                "   찬성/반대/조건부 찬성 중 하나를 선택하고 그 이유를 대세요.\n\n"
                "- '동의합니다', '좋은 의견입니다', '각 팀장의 의견을 존중합니다' 같은 빈 동의/예의 표현은 절대 금지\n"
                "- 300자 이상 800자 이하로 핵심만"
            )
            for mid in ordered_managers:
                mgr_name = _AGENT_NAMES.get(mid, mid)
                resp = await _call_agent_debate(mid, ceo_message, debate_history, rebuttal_instruction)
                debate_history += f"\n[{mgr_name}의 {round_num}라운드 발언]\n{resp}\n"

    # 비서실장이 토론 결과 종합
    synthesis_prompt = (
        f"[임원 토론 종합 보고]\n\n"
        f"[토론 주제]\n{ceo_message}\n\n"
        f"[팀장들의 토론 내용]\n{debate_history}\n\n"
        "위 토론을 바탕으로 CEO에게 보고하세요. 아래 형식을 따르세요:\n\n"
        "## 한줄 결론\n"
        "(이 토론의 결론을 CEO가 즉시 이해할 수 있는 한 문장으로)\n\n"
        "## 핵심 쟁점 (팀장 간 실제로 대립한 것만)\n"
        "| 쟁점 | 찬성 측 | 반대 측 | 판정 |\n"
        "(형식적으로 이견이 없는 항목은 제외. 실제 의견 충돌만 기록)\n\n"
        "## 전원 합의 사항\n"
        "(팀장들이 실제로 공통 동의한 핵심 포인트만. 없으면 '없음')\n\n"
        "## CEO 결정 필요 사항\n"
        "(CEO가 결정해야 할 구체적 선택지를 A/B 형태로 제시. 각 선택지의 장단점 1줄씩)\n\n"
        "## 비서실장 권고\n"
        "(당신의 판단으로 어떤 방향이 나은지, 그 이유와 함께)"
    )

    final_result = await _call_agent("chief_of_staff", synthesis_prompt)
    final_content = final_result.get("content", str(final_result)) if isinstance(final_result, dict) else str(final_result)

    return {
        "content": (
            f"## 임원 토론 결과 ({rounds}라운드)\n\n"
            f"{final_content}\n\n"
            f"---\n\n"
            f"<details><summary>전체 토론 내역 보기</summary>\n\n{debate_history}\n</details>"
        ),
        "debate_rounds": rounds,
        "participants": manager_ids,
        "agent_id": "chief_of_staff",
        "handled_by": f"임원 토론 ({rounds}라운드, {len(manager_ids)}명 참여)",
    }


async def _broadcast_to_managers(text: str, task_id: str, target_agent_id: str | None = None, conversation_id: str | None = None) -> dict:
    """스마트 라우팅: Level에 따라 적절한 에이전트만 호출.

    Level 1: 비서실장 직접 처리 (팀장 호출 없음)
    Level 2: 팀장 1명만 호출 (전문가 위임 없음)
    Level 3: 팀장 1명 + spawn_agent 자율 전문가 선택
    Level 4: 전원 병렬 호출 (기존 브로드캐스트)
    """
    # CEO 직접 개입: 특정 에이전트에게 직접 전달
    if target_agent_id:
        logger.info("CEO 직접 개입: → %s", target_agent_id)
        return await _call_agent(target_agent_id, text, conversation_id=conversation_id)

    level, manager_id = _determine_routing_level(text)
    logger.info("스마트 라우팅 Level %d, 팀장: %s", level, manager_id)

    if level == 1:
        # 비서실장 직접 처리
        return await _call_agent("chief_of_staff", text, conversation_id=conversation_id)

    elif level == 2:
        # 팀장 1명만 호출 (전문가 위임 없음)
        mgr_result = await _call_agent(manager_id, text, conversation_id=conversation_id)
        return await _chief_finalize(text, {manager_id: mgr_result})

    elif level == 3:
        # 팀장 + spawn_agent 자율 전문가 선택
        mgr_result = await _manager_with_delegation_autonomous(manager_id, text, conversation_id=conversation_id)
        return await _chief_finalize(text, {manager_id: mgr_result})

    else:  # level == 4
        return await _broadcast_to_managers_all(text, task_id, conversation_id=conversation_id)


async def _sequential_collaboration(text: str, task_id: str, agent_order: list[str] | None = None) -> dict:
    """에이전트 간 순차 협업 — 비서실장이 허브로 부서 간 순차 작업을 오케스트레이션합니다.

    흐름:
    1) 비서실장이 AI로 작업 순서 결정 (또는 CEO가 직접 지정)
    2) 첫 번째 에이전트에게 원본 명령 전달
    3) 이전 에이전트의 결과를 다음 에이전트에게 컨텍스트로 전달
    4) 모든 에이전트 완료 후 비서실장이 종합 보고

    예: "CPO가 데이터 수집 → CMO가 마케팅 콘텐츠 작성" 같은 순차 작업
    """
    await _broadcast_status("chief_of_staff", "working", 0.1, "순차 협업 계획 수립 중...")

    # 에이전트 순서가 지정되지 않았으면 AI가 결정
    if not agent_order:
        order_prompt = (
            f"CEO 명령: {text}\n\n"
            "이 작업을 처리하기 위해 어떤 부서가 어떤 순서로 작업해야 하는지 결정하세요.\n"
            "가능한 부서: cto_manager(기술), cso_manager(사업), clo_manager(법무), "
            "cmo_manager(마케팅), cio_manager(투자), cpo_manager(기획)\n\n"
            "JSON 형식으로 답변:\n"
            '{"order": ["첫번째_agent_id", "두번째_agent_id"], "reason": "이유"}\n'
            "최소 2개, 최대 4개 부서만 선택하세요. 관련 없는 부서는 제외."
        )
        soul = _load_agent_prompt("chief_of_staff")
        override = _get_model_override("chief_of_staff")
        model = select_model(order_prompt, override=override)
        plan_result = await ask_ai(order_prompt, system_prompt=soul, model=model)

        if "error" not in plan_result:
            try:
                raw = plan_result.get("content", "")
                if "```" in raw:
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                parsed = json.loads(raw)
                agent_order = parsed.get("order", [])
            except (json.JSONDecodeError, IndexError):
                pass

        if not agent_order:
            agent_order = ["cto_manager", "cso_manager"]

    # 유효한 에이전트만 필터링
    valid_agents = set(_AGENT_NAMES.keys())
    agent_order = [a for a in agent_order if a in valid_agents]
    if not agent_order:
        agent_order = ["chief_of_staff"]

    # 순차 실행
    chain_context = f"CEO 원본 명령: {text}"
    results = []
    total_cost = 0.0
    total_time = 0.0

    for i, agent_id in enumerate(agent_order):
        agent_name = _AGENT_NAMES.get(agent_id, agent_id)
        step_label = f"[{i+1}/{len(agent_order)}]"

        await _broadcast_status("chief_of_staff", "working", (i + 0.5) / len(agent_order),
                                f"순차 협업 {step_label} {agent_name} 작업 중...")

        # 이전 결과를 컨텍스트로 포함하여 호출
        if i == 0:
            agent_input = text
        else:
            prev_results = "\n\n".join(
                f"[{r['name']}의 작업 결과]\n{r['content'][:500]}"
                for r in results
            )
            agent_input = (
                f"{text}\n\n"
                f"## 이전 단계 작업 결과 (참고하여 작업하세요)\n{prev_results}"
            )

        result = await _manager_with_delegation(agent_id, agent_input)

        if isinstance(result, Exception):
            results.append({"agent_id": agent_id, "name": agent_name, "content": f"오류: {result}", "cost_usd": 0})
        elif "error" in result:
            results.append({"agent_id": agent_id, "name": agent_name, "content": f"오류: {result['error']}", "cost_usd": 0})
        else:
            results.append(result)
            total_cost += result.get("cost_usd", 0)
            total_time += result.get("time_seconds", 0)

    # 비서실장 종합
    await _broadcast_status("chief_of_staff", "working", 0.9, "순차 협업 종합 보고서 작성 중...")

    chain_summary = "\n\n---\n\n".join(
        f"### {i+1}단계: {r.get('name', r.get('agent_id', '?'))}\n{r.get('content', '결과 없음')}"
        for i, r in enumerate(results)
    )

    synthesis_prompt = (
        f"CEO 명령: {text}\n\n"
        f"아래는 {len(results)}개 부서가 순차적으로 작업한 결과입니다.\n"
        f"이전 단계의 결과를 다음 단계가 참고하여 작업했습니다.\n\n"
        f"{chain_summary}\n\n"
        f"위 순차 협업 결과를 종합하여 CEO에게 간결한 최종 보고서를 작성하세요."
    )

    soul = _load_agent_prompt("chief_of_staff")
    override = _get_model_override("chief_of_staff")
    model = select_model(synthesis_prompt, override=override)
    synthesis = await ask_ai(synthesis_prompt, system_prompt=soul, model=model)

    await _broadcast_status("chief_of_staff", "done", 1.0, "순차 협업 완료")

    if "error" in synthesis:
        chief_content = f"⚠️ 종합 보고서 작성 실패\n\n{chain_summary}"
    else:
        chief_content = synthesis.get("content", "")
        total_cost += synthesis.get("cost_usd", 0)

    order_names = " → ".join(_AGENT_NAMES.get(a, a) for a in agent_order)
    final_content = (
        f"🔗 **순차 협업 보고** ({order_names})\n\n"
        f"{chief_content}\n\n---\n\n"
        f"📂 상세 보고서 {len(results)}건이 기밀문서에 저장되었습니다."
    )

    # 아카이브 저장
    now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    save_archive(
        division="secretary",
        filename=f"sequential_collab_{now_str}.md",
        content=f"# [순차 협업] {text[:50]}\n\n작업 순서: {order_names}\n\n{chain_summary}",
        agent_id="chief_of_staff",
    )

    update_task(task_id, status="completed",
                result_summary=f"순차 협업 완료 ({order_names})",
                result_data=final_content,
                success=1, cost_usd=total_cost,
                time_seconds=round(total_time, 2),
                agent_id="chief_of_staff")

    return {
        "content": final_content,
        "agent_id": "chief_of_staff",
        "handled_by": f"비서실장 → {order_names}",
        "delegation": f"순차 협업: {order_names}",
        "total_cost_usd": round(total_cost, 6),
        "time_seconds": round(total_time, 2),
        "model": "multi-agent-sequential",
        "routing_method": "순차 협업",
    }


# 순차 협업 트리거 키워드
_SEQUENTIAL_KEYWORDS = ["순차", "협업", "순서대로", "단계별", "릴레이", "연계"]


def _is_sequential_command(text: str) -> bool:
    """순차 협업 명령인지 확인합니다."""
    return any(kw in text for kw in _SEQUENTIAL_KEYWORDS)


def _classify_by_keywords(text: str) -> str | None:
    """키워드 기반 빠른 분류. 매칭 실패 시 None 반환."""
    for agent_id, keywords in _ROUTING_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return agent_id
    return None


async def _route_task(text: str) -> dict:
    """CEO 명령을 적합한 에이전트에게 라우팅합니다.

    1단계: 키워드 매칭 (무료, 즉시)
    2단계: AI 분류 (Haiku, ~$0.001)
    3단계: 폴백 → 비서실장
    """
    # 1단계: 키워드 분류
    agent_id = _classify_by_keywords(text)
    if agent_id:
        return {
            "agent_id": agent_id,
            "method": "키워드",
            "cost_usd": 0.0,
            "reason": "키워드 매칭",
        }

    # 2단계: AI 분류 (키워드 실패 시)
    result = await classify_task(text)
    if result.get("agent_id") and result["agent_id"] != "chief_of_staff":
        return {
            "agent_id": result["agent_id"],
            "method": "AI분류",
            "cost_usd": result.get("cost_usd", 0),
            "reason": result.get("reason", "AI 분류"),
        }

    # 3단계: 폴백 — 비서실장 직접 처리
    return {
        "agent_id": "chief_of_staff",
        "method": "직접",
        "cost_usd": result.get("cost_usd", 0),
        "reason": result.get("reason", "비서실장 직접 처리"),
    }


def _get_tool_descriptions(agent_id: str) -> str:
    """에이전트에 할당된 도구 설명을 생성합니다."""
    detail = _AGENTS_DETAIL.get(agent_id, {})
    allowed = detail.get("allowed_tools", [])
    if not allowed:
        return ""

    # 도구 ID → 설명 매핑
    tool_map = {t.get("tool_id"): t for t in _TOOLS_LIST}
    descs = []
    for tid in allowed:
        t = tool_map.get(tid)
        if t:
            name = t.get("name_ko") or t.get("name", tid)
            desc = t.get("description", "")[:150]
            descs.append(f"- **{name}**: {desc}")

    if not descs:
        return ""

    return (
        "\n\n## 사용 가능한 전문 도구\n"
        "아래 도구의 기능을 활용하여 더 정확하고 전문적인 답변을 제공하세요.\n"
        + "\n".join(descs)
    )


def _load_agent_prompt(agent_id: str, *, include_tools: bool = True) -> str:
    """에이전트의 시스템 프롬프트(소울) + 도구 정보를 로드합니다.

    우선순위: DB 오버라이드 > souls/*.md 파일 > agents.yaml system_prompt > 기본값
    include_tools=True이면 마지막에 할당된 도구 설명을 추가합니다.
    배치 모드에서는 include_tools=False로 호출하여 도구 설명을 제외합니다.
    """
    prompt = ""

    # 1순위: DB 오버라이드
    soul = load_setting(f"soul_{agent_id}")
    if soul:
        prompt = soul
    else:
        # 2순위: souls 파일
        soul_path = Path(BASE_DIR).parent / "souls" / "agents" / f"{agent_id}.md"
        if soul_path.exists():
            try:
                prompt = soul_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.debug("소울 파일 읽기 실패 (%s): %s", agent_id, e)

    if not prompt:
        # 3순위: agents.yaml의 system_prompt
        detail = _AGENTS_DETAIL.get(agent_id, {})
        if detail.get("system_prompt"):
            prompt = detail["system_prompt"]

    if not prompt:
        # 4순위: 기본 프롬프트
        name = _AGENT_NAMES.get(agent_id, _SPECIALIST_NAMES.get(agent_id, agent_id))
        prompt = (
            f"당신은 CORTHEX HQ의 {name}입니다. "
            "CEO의 업무 지시를 받아 처리하고, 명확하고 간결하게 한국어로 답변합니다. "
            "항상 존댓말을 사용하고, 구체적이고 실행 가능한 답변을 제공합니다."
        )

    if include_tools:
        # 도구 설명 추가 (에이전트가 자신의 도구를 인지하고 활용할 수 있게)
        tools_desc = _get_tool_descriptions(agent_id)
        if tools_desc:
            prompt += tools_desc

    return prompt




# app_state.chief_prompt → app_state.chief_prompt 직접 사용


def _load_chief_prompt() -> None:
    """비서실장 시스템 프롬프트를 로드합니다 (서버 시작 시 캐시)."""

    app_state.chief_prompt = _load_agent_prompt("chief_of_staff")
    _log("[AI] 비서실장 프롬프트 로드 완료")


def _get_model_override(agent_id: str) -> str | None:
    """에이전트에 지정된 모델을 반환합니다.

    우선순위:
    1. agent_overrides DB (CEO 수동 설정 / 권장 버튼 / 일괄 변경)
    2. _AGENTS_DETAIL (agents.yaml 기본값)
    3. AGENTS 리스트 폴백
    4. 글로벌 오버라이드
    """
    # 1. DB 오버라이드 (CEO 수동 설정 — 가장 우선!)
    overrides = _load_data("agent_overrides", {})
    if agent_id in overrides and "model_name" in overrides[agent_id]:
        return overrides[agent_id]["model_name"]
    # 2. 에이전트별 개별 지정 모델 (agents.yaml 기본값)
    detail = _AGENTS_DETAIL.get(agent_id, {})
    agent_model = detail.get("model_name")
    if agent_model:
        return agent_model
    # 3. AGENTS 리스트 폴백
    for a in AGENTS:
        if a["agent_id"] == agent_id and a.get("model_name"):
            return a["model_name"]
    # 4. 글로벌 오버라이드 (텔레그램 /models 또는 웹 대시보드에서 설정한 전체 모델)
    global_override = load_setting("model_override")
    if global_override:
        return global_override
    return None


def _get_agent_reasoning_effort(agent_id: str) -> str:
    """에이전트의 reasoning_effort를 agent_overrides DB → AGENTS 목록 순서로 조회."""
    overrides = _load_data("agent_overrides", {})
    if agent_id in overrides and "reasoning_effort" in overrides[agent_id]:
        return overrides[agent_id]["reasoning_effort"]
    for a in AGENTS:
        if a["agent_id"] == agent_id:
            return a.get("reasoning_effort", "")
    return ""


def _build_conv_history(conversation_id: str | None, current_text: str) -> list | None:
    """대화 세션에서 AI conversation_history를 구성합니다.

    conversation_id가 있으면 해당 세션만, 없으면 전체(레거시) 메시지를 사용합니다.
    """
    try:
        if conversation_id:
            recent = load_conversation_messages_by_id(conversation_id, limit=200)
        else:
            recent = load_conversation_messages(limit=100)

        # 최근 20개 메시지 (약 10턴)
        tail = recent[-20:] if len(recent) > 20 else recent
        if not tail:
            return None

        conv_history = []
        for m in tail:
            if m["type"] == "user" and m.get("text"):
                conv_history.append({"role": "user", "content": m["text"][:2000]})
            elif m["type"] == "result" and m.get("content"):
                conv_history.append({"role": "assistant", "content": m["content"][:2000]})

        # 현재 메시지와 동일한 마지막 user 메시지는 제거 (중복 방지)
        if (conv_history and conv_history[-1].get("role") == "user"
                and conv_history[-1].get("content", "").strip() == current_text[:2000].strip()):
            conv_history.pop()

        return conv_history if conv_history else None
    except Exception as e:
        logger.debug("대화 기록 로드 실패 (무시): %s", e)
        return None


async def _process_ai_command(text: str, task_id: str, target_agent_id: str | None = None,
                              conversation_id: str | None = None) -> dict:
    """CEO 명령을 적합한 에이전트에게 위임하고 AI 결과를 반환합니다.

    흐름:
      예산 확인 → 브로드캐스트 확인 → 라우팅(분류) → 상태 전송
      → 팀장+전문가 풀 체인 위임 → 검수 → DB 저장

    브로드캐스트 모드: "전체", "출석체크" 등 → 스마트 라우팅 (Level 1~4)
    단일 위임 모드: 키워드/AI 분류 → 팀장+전문가 체인 호출
    직접 처리: 비서실장이 직접 답변 (단순 질문)
    target_agent_id: CEO가 특정 에이전트를 직접 지정한 경우
    """
    # 1) 예산 확인
    limit = float(load_setting("daily_budget_usd") or 7.0)
    today = get_today_cost()
    if today >= limit:
        update_task(task_id, status="failed",
                    result_summary=f"일일 예산 초과 (${today:.2f}/${limit:.0f})",
                    success=0)
        return {"error": f"일일 예산을 초과했습니다 (${today:.2f}/${limit:.0f})"}

    # ── 슬래시 명령어 시스템 ──
    text_lower = text.strip().lower()
    text_stripped = text.strip()

    # /명령어 또는 /도움말 — 사용 가능한 명령어 목록
    if text_lower in ("/명령어", "/도움말", "/help", "/commands"):
        content = (
            "📋 **사용 가능한 명령어**\n\n"
            "| 명령어 | 설명 |\n"
            "|--------|------|\n"
            "| `/토론 [주제]` | 임원 토론 (2라운드: 독립 의견 → 재반박) |\n"
            "| `/심층토론 [주제]` | 심층 임원 토론 (3라운드: 더 깊은 반박) |\n"
            "| `/전체 [메시지]` | 29명 에이전트 동시 가동 (브로드캐스트) |\n"
            "| `/순차 [메시지]` | 에이전트 릴레이 (순서대로 작업) |\n"
            f"| `/도구점검` | {len(_TOOLS_LIST)}개 도구 상태 점검 |\n"
            "| `/배치실행` | 대기 중인 배치 작업 실행 |\n"
            "| `/배치상태` | 배치 처리 현황 |\n"
            "| `/명령어` | 이 도움말 |\n\n"
            "**일반 메시지**는 비서실장이 자동으로 적합한 부서에 위임합니다."
        )
        update_task(task_id, status="completed", result_summary=content[:500], success=1)
        return {"content": content, "handled_by": "비서실장", "agent_id": "chief_of_staff"}

    # /토론 [주제] — 임원 토론 (2라운드: 독립 의견 + 재반박)
    if text_stripped.startswith("/토론"):
        topic = text_stripped[len("/토론"):].strip() or "CORTHEX 전략 방향"
        result = await _broadcast_with_debate(topic, rounds=2)
        update_task(task_id, status="completed", result_summary=f"임원 토론 완료 (2라운드)", success=1)
        result["handled_by"] = result.get("handled_by", "임원 토론")
        return result

    # /심층토론 [주제] — 심층 임원 토론 (3라운드: 더 깊은 반박)
    if text_stripped.startswith("/심층토론"):
        topic = text_stripped[len("/심층토론"):].strip() or "CORTHEX 전략 방향"
        result = await _broadcast_with_debate(topic, rounds=3)
        update_task(task_id, status="completed", result_summary=f"심층 임원 토론 완료 (3라운드)", success=1)
        result["handled_by"] = result.get("handled_by", "심층 임원 토론")
        return result

    # /전체 [메시지] — 브로드캐스트 (29명 동시 가동) — 항상 Level 4 전원 호출
    if text_stripped.startswith("/전체"):
        broadcast_text = text_stripped[len("/전체"):].strip()
        if not broadcast_text:
            broadcast_text = "전체 출석 보고"
        return await _broadcast_to_managers_all(broadcast_text, task_id)

    # /순차 [메시지] — 순차 협업 (에이전트 릴레이)
    if text_stripped.startswith("/순차"):
        seq_text = text_stripped[len("/순차"):].strip()
        if not seq_text:
            content = "⚠️ `/순차` 뒤에 작업 내용을 입력해주세요.\n\n예: `/순차 CORTHEX 웹사이트 기술→보안→사업성 분석`"
            update_task(task_id, status="completed", result_summary=content[:500], success=1)
            return {"content": content, "handled_by": "비서실장", "agent_id": "chief_of_staff"}
        return await _sequential_collaboration(seq_text, task_id)

    # /도구점검 — 도구 건강 점검
    if text_lower in ("/도구점검", "/도구상태", "/tools_health", "전체 도구 점검", "도구 점검", "도구 상태"):
        import urllib.request as _ur
        try:
            req = _ur.Request("http://127.0.0.1:8000/api/tools/health")
            with _ur.urlopen(req, timeout=10) as resp:
                health = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            health = {"total": 0, "ready": 0, "missing_key": 0, "not_loaded": 0, "tools": [], "error": str(e)}

        content = f"🔧 **전체 도구 점검 결과**\n\n"
        content += f"| 항목 | 수량 |\n|------|------|\n"
        content += f"| 전체 도구 | {health.get('total', 0)}개 |\n"
        content += f"| 정상 (ready) | {health.get('ready', 0)}개 |\n"
        content += f"| API 키 미설정 | {health.get('missing_key', 0)}개 |\n"
        content += f"| 미로드 | {health.get('not_loaded', 0)}개 |\n"
        content += f"| ToolPool | {health.get('pool_status', 'unknown')} |\n\n"

        missing = [t for t in health.get("tools", []) if t.get("status") == "missing_key"]
        if missing:
            content += "### ⚠️ API 키 필요한 도구\n"
            for t in missing[:10]:
                content += f"- **{t['name']}** (`{t['tool_id']}`) — 환경변수: `{t.get('api_key_env', '?')}`\n"

        ready = [t for t in health.get("tools", []) if t.get("status") == "ready"]
        if ready:
            content += f"\n### ✅ 정상 작동 도구 ({len(ready)}개 중 상위 10개)\n"
            for t in ready[:10]:
                content += f"- {t['name']} (`{t['tool_id']}`)\n"

        update_task(task_id, status="completed", result_summary=content[:500], success=1)
        return {"content": content, "handled_by": "비서실장", "agent_id": "chief_of_staff"}

    # /배치실행 — 배치 작업 실행
    if text_lower in ("/배치실행", "/batch_flush", "배치실행", "배치 실행"):
        result = await _flush_batch_api_queue()
        content = f"📦 **배치 실행 결과**\n\n"
        if "error" in result:
            content += f"❌ 실패: {result['error']}"
        elif result.get("batch_id"):
            content += f"✅ Batch API 제출 완료\n- batch_id: `{result['batch_id']}`\n- 건수: {result.get('count', 0)}건\n- 프로바이더: {result.get('provider', '?')}"
        else:
            content += result.get("message", "처리 완료")
        update_task(task_id, status="completed", result_summary=content[:500], success=1)
        return {"content": content, "handled_by": "비서실장", "agent_id": "chief_of_staff"}

    # /배치상태 — 배치 현황
    if text_lower in ("/배치상태", "/batch_status", "배치상태", "배치 상태"):
        pending_batches = load_setting("pending_batches") or []
        active = [b for b in pending_batches if b.get("status") in ("pending", "processing")]
        queue_count = len(_batch_api_queue)
        content = f"📦 **배치 상태**\n\n"
        content += f"- 대기열: {queue_count}건\n"
        content += f"- 처리 중인 배치: {len(active)}건\n"
        for b in active:
            prog = b.get("progress", {})
            content += f"  - `{b['batch_id'][:20]}...` ({b['provider']}) — {prog.get('completed', '?')}/{prog.get('total', '?')} 완료\n"
        update_task(task_id, status="completed", result_summary=content[:500], success=1)
        return {"content": content, "handled_by": "비서실장", "agent_id": "chief_of_staff"}

    # ── 슬래시 명령어 이외: 키워드 기반 브로드캐스트 (기존 호환) ──
    # "전체", "출석체크" 등의 키워드는 스마트 라우팅 적용 (Level 1~4)
    if _is_broadcast_command(text):
        return await _broadcast_to_managers(text, task_id, target_agent_id=target_agent_id, conversation_id=conversation_id)

    # 3) CEO가 @에이전트로 직접 지정한 경우 → 자동 라우팅 건너뜀
    if target_agent_id:
        logger.info("CEO 직접 지정: → %s", target_agent_id)
        target_id = target_agent_id
        routing = {"agent_id": target_id, "method": "ceo_direct", "cost_usd": 0}
        routing_cost = 0

        # 팀장이든 전문가든 — 비서실장 위임 없이 직접 호출
        is_specialist = target_id in _SPECIALIST_NAMES
        if is_specialist or target_id not in _AGENT_NAMES:
            # 전문가이거나 팀장도 아닌 에이전트 → 바로 _call_agent()
            direct_result = await _call_agent(target_id, text, conversation_id=conversation_id)
            direct_name = _SPECIALIST_NAMES.get(target_id, _AGENT_NAMES.get(target_id, target_id))
            if "error" in direct_result:
                update_task(task_id, status="failed",
                            result_summary=f"오류: {direct_result['error'][:100]}",
                            success=0, agent_id=target_id)
                direct_result["handled_by"] = direct_name
                return direct_result
            total_cost = routing_cost + direct_result.get("cost_usd", 0)
            update_task(task_id, status="completed",
                        result_summary=direct_result.get("content", "")[:500],
                        result_data=direct_result.get("content", ""),
                        success=1, cost_usd=total_cost,
                        tokens_used=direct_result.get("input_tokens", 0) + direct_result.get("output_tokens", 0),
                        time_seconds=direct_result.get("time_seconds", 0),
                        agent_id=target_id)
            direct_result["handled_by"] = direct_name
            direct_result["delegation"] = ""
            direct_result["agent_id"] = target_id
            direct_result["routing_method"] = "ceo_direct"
            direct_result["total_cost_usd"] = total_cost
            return direct_result
        # 팀장이면 아래 기존 위임 로직으로 진행
    else:
        # 라우팅 — 적합한 에이전트 결정
        routing = await _route_task(text)
        target_id = routing["agent_id"]
        routing_cost = routing.get("cost_usd", 0)

    # 4) 비서실장 직접 처리 (일반 질문, 인사 등)
    if target_id == "chief_of_staff":
        await _broadcast_status("chief_of_staff", "working", 0.2, "직접 처리 중...")
        soul = app_state.chief_prompt if app_state.chief_prompt else _load_agent_prompt("chief_of_staff")
        override = _get_model_override("chief_of_staff")
        model = select_model(text, override=override)
        # 대화 맥락 로드
        _chief_history = _build_conv_history(conversation_id, text)
        result = await ask_ai(text, system_prompt=soul, model=model,
                              conversation_history=_chief_history)

        await _broadcast_status("chief_of_staff", "done", 1.0, "완료")

        if "error" in result:
            update_task(task_id, status="failed",
                        result_summary=f"AI 오류: {result['error'][:100]}",
                        success=0, agent_id="chief_of_staff")
            result["handled_by"] = "비서실장"
            return result

        total_cost = routing_cost + result.get("cost_usd", 0)
        update_task(task_id, status="completed",
                    result_summary=result["content"][:500],
                    result_data=result["content"],
                    success=1, cost_usd=total_cost,
                    tokens_used=result.get("input_tokens", 0) + result.get("output_tokens", 0),
                    time_seconds=result.get("time_seconds", 0),
                    agent_id="chief_of_staff")
        result["handled_by"] = "비서실장"
        result["delegation"] = ""
        result["agent_id"] = "chief_of_staff"
        result["routing_method"] = routing["method"]
        result["total_cost_usd"] = total_cost
        return result

    # 5) 부서 위임 — 비서실장이 적합한 팀장에게 전달
    target_name = _AGENT_NAMES.get(target_id, target_id)
    await _broadcast_status("chief_of_staff", "working", 0.1, f"{target_name}에게 위임 중...")

    # 팀장이 자기 전문가를 호출 → 결과 검수 → 종합 보고서
    delegation_result = await _manager_with_delegation(target_id, text, conversation_id=conversation_id)
    await _broadcast_status("chief_of_staff", "done", 1.0, "위임 완료")

    if "error" in delegation_result:
        update_task(task_id, status="failed",
                    result_summary=f"위임 오류: {delegation_result['error'][:100]}",
                    success=0, agent_id=target_id)
        delegation_result["handled_by"] = target_name
        return delegation_result

    # 6) 결과 정리
    total_cost = routing_cost + delegation_result.get("cost_usd", 0)
    specs_used = delegation_result.get("specialists_used", 0)
    delegation_label = f"비서실장 → {target_name}"
    if specs_used:
        delegation_label += f" → 전문가 {specs_used}명"

    content = delegation_result.get("content", "")
    header = f"📋 **{target_name}** 보고"
    if specs_used:
        header += f" (소속 전문가 {specs_used}명 동원)"
    content = f"{header}\n\n---\n\n{content}"

    update_task(task_id, status="completed",
                result_summary=content[:500],
                result_data=content,
                success=1, cost_usd=total_cost,
                time_seconds=delegation_result.get("time_seconds", 0),
                agent_id=target_id)

    return {
        "content": content,
        "agent_id": target_id,
        "handled_by": target_name,
        "delegation": delegation_label,
        "total_cost_usd": round(total_cost, 6),
        "time_seconds": delegation_result.get("time_seconds", 0),
        "model": delegation_result.get("model", ""),
        "routing_method": routing["method"],
    }


# ── 도구 실행 파이프라인 ──

def _init_tool_pool():
    """ToolPool 초기화 — src/tools/ 모듈을 동적으로 로드합니다.

    ask_ai()를 ModelRouter 인터페이스로 감싸는 어댑터를 만들어,
    기존 도구 코드를 수정 없이 사용할 수 있게 합니다.
    """

    if app_state.tool_pool is not None:
        return app_state.tool_pool if app_state.tool_pool else None

    try:
        from src.tools.pool import ToolPool
        from src.llm.base import LLMResponse

        class _MiniModelRouter:
            """ask_ai()를 ModelRouter.complete() 인터페이스로 감싸는 어댑터."""

            class cost_tracker:
                """더미 비용 추적기 (arm_server는 자체 비용 추적 사용)."""
                @staticmethod
                def record(*args, **kwargs):
                    pass

            async def complete(self, model_name="", messages=None,
                             temperature=0.3, max_tokens=32768,
                             agent_id="", reasoning_effort=None,
                             use_batch=False):
                messages = messages or []
                system_prompt = ""
                user_message = ""
                for msg in messages:
                    if msg.get("role") == "system":
                        system_prompt = msg["content"]
                    elif msg.get("role") == "user":
                        user_message = msg["content"]

                result = await ask_ai(user_message, system_prompt, model_name)

                if "error" in result:
                    return LLMResponse(
                        content=f"[도구 LLM 오류] {result['error']}",
                        model=model_name,
                        input_tokens=0, output_tokens=0,
                        cost_usd=0.0, provider="unknown",
                    )
                return LLMResponse(
                    content=result["content"],
                    model=result.get("model", model_name),
                    input_tokens=result.get("input_tokens", 0),
                    output_tokens=result.get("output_tokens", 0),
                    cost_usd=result.get("cost_usd", 0.0),
                    provider=result.get("provider", "unknown"),
                )

            async def close(self):
                pass

        router = _MiniModelRouter()
        pool = ToolPool(router)

        tools_config = _load_config("tools")
        pool.build_from_config(tools_config)

        loaded = len(pool._tools)
        app_state.tool_pool = pool
        # AGENTS 초기 모델을 풀에 등록 (Skill 도구가 caller 에이전트 모델을 따라가도록)
        for a in AGENTS:
            _temp = _AGENTS_DETAIL.get(a["agent_id"], {}).get("temperature", 0.7)
            pool.set_agent_model(a["agent_id"], a.get("model_name", "claude-sonnet-4-6"), temperature=_temp)
        # DB에 저장된 에이전트 모델 덮어씌우기 (사용자가 UI에서 변경한 값 우선)
        try:
            overrides = _load_data("agent_overrides", {})
            for agent_id, vals in overrides.items():
                if "model_name" in vals:
                    _temp = _AGENTS_DETAIL.get(agent_id, {}).get("temperature", 0.7)
                    pool.set_agent_model(agent_id, vals["model_name"], temperature=_temp)
        except Exception as e:
            logger.debug("에이전트 모델 오버라이드 실패: %s", e)
        _log(f"[TOOLS] ToolPool 초기화 완료: {loaded}개 도구 로드 ✅")
        return pool

    except Exception as e:
        _log(f"[TOOLS] ToolPool 초기화 실패 (도구 목록만 표시): {e}")
        app_state.tool_pool = False
        return None


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


# ── Soul Gym 24/7 상시 루프 ──

_soul_gym_lock = asyncio.Lock()  # 중복 실행 방지 Lock

async def _soul_gym_loop():
    """Soul Gym 상시 진화 루프 — 한 라운드 끝나면 5분 쉬고 다음 라운드.

    비유: 24시간 운영 헬스장. 선수가 운동 끝나면 5분 쉬고 다시 시작.
    """
    if _soul_gym_lock.locked():
        logger.warning("[SOUL GYM] 이미 루프 실행 중 — 중복 방지")
        return
    async with _soul_gym_lock:
        INTERVAL_SECONDS = 1800  # 라운드 간 대기 (30분, 6팀장 순차 실행 고려)

        try:
            from soul_gym_engine import evolve_all as _evolve_all
        except ImportError:
            logger.error("[SOUL GYM] soul_gym_engine 임포트 실패")
            return

        round_num = 0
        while True:
            try:
                round_num += 1
                _evo_msg = f"🧬 Soul Gym 라운드 #{round_num} 시작"
                logger.info(_evo_msg)
                save_activity_log("system", _evo_msg, "info")
                await _broadcast_evolution_log(_evo_msg, "info")
                result = await _evolve_all()
                _evo_msg = f"🧬 Soul Gym 라운드 #{round_num} 완료 — {result.get('status', '')}"
                logger.info("🧬 Soul Gym 라운드 #%d 완료: %s", round_num, result.get("status", "unknown"))
                save_activity_log("system", _evo_msg, "info")
                await _broadcast_evolution_log(_evo_msg, "info")
            except Exception as e:
                _evo_msg = f"🧬 Soul Gym 라운드 #{round_num} 에러: {e}"
                logger.error(_evo_msg)
                save_activity_log("system", _evo_msg, "error")
                await _broadcast_evolution_log(_evo_msg, "error")

            await asyncio.sleep(INTERVAL_SECONDS)


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
    # 크론 실행 엔진 시작

    app_state.cron_task = asyncio.create_task(_cron_loop())
    _log("[CRON] 크론 실행 엔진 시작 ✅")
    # 기본 스케줄 자동 등록 (없으면 생성)
    _register_default_schedules()
    # 품질검수 제거됨 (2026-02-27)
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
    # PENDING 배치 또는 진행 중인 체인이 있으면 폴러 시작
    pending_batches = load_setting("pending_batches") or []
    active_batches = [b for b in pending_batches if b.get("status") in ("pending", "processing")]
    chains = load_setting("batch_chains") or []
    active_chains = [c for c in chains if c.get("status") in ("running", "pending")]
    if active_batches or active_chains:
        _ensure_batch_poller()
        _log(f"[BATCH] 미완료 배치 {len(active_batches)}개 + 체인 {len(active_chains)}개 감지 — 폴러 자동 시작")
    # 자동매매 봇 상태 DB에서 복원 (배포/재시작 후에도 유지)

    app_state.trading_bot_active = bool(load_setting("trading_bot_active", False))
    if app_state.trading_bot_active:
        app_state.trading_bot_task = asyncio.create_task(_trading_bot_loop())
        _log("[TRADING] 자동매매 봇 DB 상태 복원 → 자동 재시작 ✅")
    # 관심종목 시세 1분 자동 갱신 태스크 시작
    asyncio.create_task(_auto_refresh_prices())
    _log("[PRICE] 시세 자동 갱신 태스크 시작 ✅ (1분 간격)")
    # KIS 토큰 매일 오전 7시 자동 갱신 스케줄러 시작
    from kis_client import start_daily_token_renewal
    asyncio.create_task(start_daily_token_renewal())
    _log("[KIS] 토큰 자동 갱신 스케줄러 시작 ✅ (매일 KST 07:00)")
    asyncio.create_task(_cio_prediction_verifier())
    _log("[CIO] 예측 사후검증 스케줄러 시작 ✅ (매일 KST 03:00)")
    asyncio.create_task(_cio_weekly_soul_update())
    _log("[CIO] 주간 soul 자동 업데이트 스케줄러 시작 ✅ (매주 일요일 KST 02:00)")
    asyncio.create_task(_shadow_trading_alert())
    _log("[Shadow] Shadow Trading 알림 스케줄러 시작 ✅ (매일 KST 09:00, +5% 기준)")
    # 메모리 정리 태스크 (10분마다 bg_results, notion_log 정리)
    app_state._cleanup_task = asyncio.create_task(app_state.periodic_cleanup())
    _log("[CLEANUP] 메모리 자동 정리 태스크 시작 ✅ (10분 간격)")
    # Soul Gym 24/7 상시 루프 (대표님 지시 2026-02-25: "24시간 7일 내내")
    asyncio.create_task(_soul_gym_loop())
    _log("[SOUL GYM] 24/7 상시 진화 루프 시작 ✅ (라운드당 ~$0.012)")


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
