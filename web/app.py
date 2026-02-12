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
from src.core.healthcheck import run_healthcheck
from src.core.message import Message, MessageType
from src.core.orchestrator import Orchestrator
from src.core.performance import build_performance_report
from src.core.registry import AgentRegistry
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.openai_provider import OpenAIProvider
from src.llm.router import ModelRouter
from src.tools.pool import ToolPool
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


@app.on_event("startup")
async def startup() -> None:
    """Initialize the agent system on server start."""
    global orchestrator, model_router, registry, context

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


@app.get("/api/health")
async def get_health() -> dict:
    """Run system health check and return results."""
    if not registry or not model_router:
        return {"overall": "error", "checks": [], "message": "시스템 미초기화"}
    report = await run_healthcheck(registry, model_router)
    return report.to_dict()


@app.get("/api/performance")
async def get_performance() -> dict:
    """Return agent performance statistics."""
    if not model_router or not context:
        return {"total_llm_calls": 0, "total_cost_usd": 0, "total_tasks": 0, "agents": []}
    report = build_performance_report(model_router.cost_tracker, context)
    return report.to_dict()


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
