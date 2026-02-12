"""
CORTHEX HQ - FastAPI Web Application.

CEO 관제실 웹 인터페이스를 제공합니다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from src.core.context import SharedContext
from src.core.message import Message, MessageType
from src.core.orchestrator import Orchestrator
from src.core.registry import AgentRegistry
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.openai_provider import OpenAIProvider
from src.llm.router import ModelRouter
from src.tools.pool import ToolPool
from src.tools.sns.oauth_manager import OAuthManager
from src.tools.sns.webhook_receiver import WebhookReceiver
from web.ws_manager import ConnectionManager

logger = logging.getLogger("corthex.web")

# Paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
CONFIG_DIR = PROJECT_DIR / "config"
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Load environment
load_dotenv(PROJECT_DIR / ".env")

# FastAPI app
app = FastAPI(title="CORTHEX HQ", version="0.3.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# WebSocket manager
ws_manager = ConnectionManager()

# Global state (initialized on startup)
orchestrator: Orchestrator | None = None
model_router: ModelRouter | None = None
registry: AgentRegistry | None = None
context: SharedContext | None = None
oauth_manager: OAuthManager | None = None
webhook_receiver: WebhookReceiver | None = None
tool_pool_ref: ToolPool | None = None


@app.on_event("startup")
async def startup() -> None:
    """Initialize the agent system on server start."""
    global orchestrator, model_router, registry, context, oauth_manager, webhook_receiver, tool_pool_ref

    logger.info("CORTHEX HQ 시스템 초기화 중...")

    # Load configs
    agents_cfg = yaml.safe_load(
        (CONFIG_DIR / "agents.yaml").read_text(encoding="utf-8")
    )
    tools_cfg = yaml.safe_load(
        (CONFIG_DIR / "tools.yaml").read_text(encoding="utf-8")
    )

    # Build LLM providers
    openai_key = os.getenv("OPENAI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    openai_prov = OpenAIProvider(api_key=openai_key) if openai_key else None
    anthropic_prov = AnthropicProvider(api_key=anthropic_key) if anthropic_key else None

    model_router = ModelRouter(
        openai_provider=openai_prov,
        anthropic_provider=anthropic_prov,
    )

    # Build tool pool
    tool_pool = ToolPool(model_router)
    tool_pool.build_from_config(tools_cfg)

    # Build agent registry (with knowledge injection)
    context = SharedContext()
    registry = AgentRegistry()
    knowledge_dir = PROJECT_DIR / "knowledge"
    registry.build_from_config(
        agents_cfg, model_router, tool_pool, context,
        knowledge_dir=knowledge_dir,
    )
    context.set_registry(registry)

    # Status callback: push real-time updates via WebSocket
    def on_message(msg: Message) -> None:
        asyncio.create_task(_handle_message_event(msg))

    context.set_status_callback(on_message)

    # Build orchestrator
    orchestrator = Orchestrator(registry, model_router)

    # Initialize SNS subsystem
    oauth_manager = OAuthManager()
    webhook_receiver = WebhookReceiver()
    tool_pool_ref = tool_pool

    logger.info("CORTHEX HQ 시스템 준비 완료 (에이전트 %d명)", registry.agent_count)


async def _handle_message_event(msg: Message) -> None:
    """Push agent activity to WebSocket clients."""
    if msg.type == MessageType.TASK_REQUEST:
        await ws_manager.send_agent_status(msg.receiver_id, "working", 0.1)
        await ws_manager.send_activity_log(
            msg.sender_id, f"→ {msg.receiver_id} 에게 작업 배정"
        )
    elif msg.type == MessageType.TASK_RESULT:
        await ws_manager.send_agent_status(msg.sender_id, "done", 1.0)
        await ws_manager.send_activity_log(msg.sender_id, "작업 완료")
        # Update cost
        if model_router:
            await ws_manager.send_cost_update(
                model_router.cost_tracker.total_cost,
                model_router.cost_tracker.total_tokens,
            )


# ─── Routes ───


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Main CEO dashboard page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/agents")
async def get_agents() -> list[dict]:
    """Return all agents with their hierarchy info."""
    if not registry:
        return []
    agents = []
    for agent in registry.list_all():
        agents.append({
            "agent_id": agent.config.agent_id,
            "name_ko": agent.config.name_ko,
            "role": agent.config.role,
            "division": agent.config.division,
            "model_name": agent.config.model_name,
            "capabilities": agent.config.capabilities,
            "subordinate_ids": agent.config.subordinate_ids,
            "superior_id": agent.config.superior_id,
        })
    return agents


@app.get("/api/cost")
async def get_cost() -> dict:
    """Return cost tracking data."""
    if not model_router:
        return {"total_cost": 0, "total_tokens": 0, "by_model": {}}
    tracker = model_router.cost_tracker
    return {
        "total_cost": tracker.total_cost,
        "total_tokens": tracker.total_tokens,
        "total_calls": tracker.total_calls,
        "by_model": tracker.summary_by_model(),
        "by_agent": tracker.summary_by_agent(),
        "by_provider": tracker.summary_by_provider(),
    }


@app.get("/api/tools")
async def get_tools() -> list[dict]:
    """Return available tools."""
    if not orchestrator:
        return []
    # Access tool pool through any agent... or rebuild from config
    tools_cfg = yaml.safe_load(
        (CONFIG_DIR / "tools.yaml").read_text(encoding="utf-8")
    )
    return tools_cfg.get("tools", [])


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """WebSocket for real-time updates and CEO commands."""
    await ws_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "command":
                user_input = msg.get("text", "").strip()
                if not user_input or not orchestrator:
                    continue

                # Notify: processing started
                await ws.send_text(json.dumps({
                    "event": "processing_start",
                    "data": {"command": user_input},
                }, ensure_ascii=False))

                # Reset all agent statuses
                if registry:
                    for agent in registry.list_all():
                        await ws_manager.send_agent_status(
                            agent.config.agent_id, "idle"
                        )

                # Process the command
                try:
                    result = await orchestrator.process_command(user_input)

                    await ws.send_text(json.dumps({
                        "event": "result",
                        "data": {
                            "success": result.success,
                            "content": str(result.result_data or result.summary),
                            "sender_id": result.sender_id,
                            "time_seconds": result.execution_time_seconds,
                            "cost": model_router.cost_tracker.total_cost if model_router else 0,
                        },
                    }, ensure_ascii=False))

                except Exception as e:
                    await ws.send_text(json.dumps({
                        "event": "error",
                        "data": {"message": str(e)},
                    }, ensure_ascii=False))

                # Reset all statuses to idle
                if registry:
                    for agent in registry.list_all():
                        await ws_manager.send_agent_status(
                            agent.config.agent_id, "idle"
                        )

    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ─── SNS 연동 API ───


@app.get("/api/sns/status")
async def sns_status() -> dict:
    """SNS 플랫폼 연결 상태 조회."""
    if not oauth_manager:
        return {"platforms": []}
    return {"platforms": oauth_manager.status()}


@app.get("/api/sns/queue")
async def sns_queue() -> dict:
    """SNS 발행 승인 큐 조회."""
    if not tool_pool_ref:
        return {"error": "시스템 미초기화"}
    try:
        result = await tool_pool_ref.invoke("sns_manager", action="queue")
        return result
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/sns/approve/{request_id}")
async def sns_approve(request_id: str) -> dict:
    """CEO가 SNS 발행 요청을 승인."""
    if not tool_pool_ref:
        return {"error": "시스템 미초기화"}
    try:
        result = await tool_pool_ref.invoke(
            "sns_manager", action="approve", request_id=request_id,
        )
        return result
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/sns/reject/{request_id}")
async def sns_reject(request_id: str, request: Request) -> dict:
    """CEO가 SNS 발행 요청을 거절."""
    if not tool_pool_ref:
        return {"error": "시스템 미초기화"}
    try:
        body = await request.json()
        result = await tool_pool_ref.invoke(
            "sns_manager", action="reject",
            request_id=request_id,
            reason=body.get("reason", ""),
        )
        return result
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/sns/auth/{platform}")
async def sns_auth_url(platform: str) -> dict:
    """OAuth 인증 URL 생성."""
    if not oauth_manager:
        return {"error": "시스템 미초기화"}
    try:
        url = oauth_manager.get_auth_url(platform)
        return {"platform": platform, "auth_url": url}
    except ValueError as e:
        return {"error": str(e)}


@app.get("/oauth/callback/{platform}")
async def oauth_callback(platform: str, code: str = "") -> HTMLResponse:
    """OAuth 인증 콜백 (각 플랫폼에서 리다이렉트)."""
    if not oauth_manager or not code:
        return HTMLResponse("<h1>인증 실패</h1><p>코드가 없습니다.</p>")
    try:
        await oauth_manager.exchange_code(platform, code)
        return HTMLResponse(
            f"<h1>{platform} 연결 완료!</h1>"
            f"<p>이 창을 닫고 CORTHEX HQ 대시보드로 돌아가세요.</p>"
            f"<script>setTimeout(()=>window.close(), 2000)</script>"
        )
    except Exception as e:
        return HTMLResponse(f"<h1>인증 실패</h1><p>{e}</p>")


# ─── Webhook 수신 엔드포인트 ───


@app.post("/webhook/{platform}")
async def webhook_endpoint(platform: str, request: Request) -> dict:
    """SNS 플랫폼으로부터 Webhook 이벤트 수신."""
    if not webhook_receiver:
        return {"error": "시스템 미초기화"}

    body = await request.body()
    headers = dict(request.headers)

    handler_map = {
        "youtube": webhook_receiver.handle_youtube,
        "instagram": webhook_receiver.handle_instagram,
        "linkedin": webhook_receiver.handle_linkedin,
        "tistory": webhook_receiver.handle_tistory,
    }

    handler = handler_map.get(platform)
    if not handler:
        return {"error": f"미지원 플랫폼: {platform}"}

    return await handler(body, headers)


@app.get("/webhook/{platform}")
async def webhook_verify(platform: str, request: Request) -> Any:
    """Webhook 구독 검증 (Instagram/YouTube 용)."""
    params = dict(request.query_params)

    # Instagram/Facebook Webhook 검증
    if "hub.challenge" in params:
        verify_token = os.getenv("WEBHOOK_VERIFY_TOKEN", "corthex-webhook")
        if params.get("hub.verify_token") == verify_token:
            return int(params["hub.challenge"])
        return {"error": "검증 실패"}

    # YouTube PubSubHubbub 검증
    if "hub.challenge" in params:
        return params["hub.challenge"]

    return {"status": "ok"}


@app.get("/api/sns/events")
async def sns_events(limit: int = 20) -> dict:
    """최근 Webhook 이벤트 조회."""
    if not webhook_receiver:
        return {"events": []}
    return {"events": webhook_receiver.recent_events(limit)}
