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
from pydantic import BaseModel
from starlette.requests import Request

from src.core.context import SharedContext
from src.core.knowledge import KnowledgeManager
from src.core.message import Message, MessageType
from src.core.orchestrator import Orchestrator
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
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# WebSocket manager
ws_manager = ConnectionManager()

# Global state (initialized on startup)
orchestrator: Orchestrator | None = None
model_router: ModelRouter | None = None
registry: AgentRegistry | None = None
context: SharedContext | None = None
knowledge_mgr: KnowledgeManager | None = None
agents_cfg_raw: dict | None = None  # raw YAML config for soul editing


@app.on_event("startup")
async def startup() -> None:
    """Initialize the agent system on server start."""
    global orchestrator, model_router, registry, context, knowledge_mgr, agents_cfg_raw

    logger.info("CORTHEX HQ 시스템 초기화 중...")

    # Load configs
    agents_cfg_raw = yaml.safe_load(
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
    knowledge_mgr = KnowledgeManager(knowledge_dir)
    registry.build_from_config(
        agents_cfg_raw, model_router, tool_pool, context,
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


# ─── Agent Detail & Soul Editing ───


@app.get("/api/agents/{agent_id}")
async def get_agent_detail(agent_id: str) -> dict:
    """Return full agent info including system_prompt (soul)."""
    if not registry:
        return {"error": "not initialized"}
    try:
        agent = registry.get_agent(agent_id)
    except Exception:
        return {"error": "agent not found"}
    cfg = agent.config
    # Get the original (un-knowledge-injected) prompt from YAML
    original_prompt = ""
    if agents_cfg_raw:
        for a in agents_cfg_raw.get("agents", []):
            if a.get("agent_id") == agent_id:
                original_prompt = a.get("system_prompt", "")
                break
    return {
        "agent_id": cfg.agent_id,
        "name": cfg.name,
        "name_ko": cfg.name_ko,
        "role": cfg.role,
        "division": cfg.division,
        "model_name": cfg.model_name,
        "capabilities": cfg.capabilities,
        "subordinate_ids": cfg.subordinate_ids,
        "superior_id": cfg.superior_id,
        "system_prompt": original_prompt,
        "allowed_tools": cfg.allowed_tools,
        "temperature": cfg.temperature,
    }


class SoulUpdateRequest(BaseModel):
    system_prompt: str


@app.put("/api/agents/{agent_id}/soul")
async def update_agent_soul(agent_id: str, body: SoulUpdateRequest) -> dict:
    """Update an agent's system_prompt (soul) and persist to agents.yaml."""
    global agents_cfg_raw
    if not registry or not agents_cfg_raw:
        return {"error": "not initialized"}

    # Update in-memory YAML config
    found = False
    for a in agents_cfg_raw.get("agents", []):
        if a.get("agent_id") == agent_id:
            a["system_prompt"] = body.system_prompt
            found = True
            break
    if not found:
        return {"error": "agent not found"}

    # Persist to YAML file
    yaml_path = CONFIG_DIR / "agents.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write("# =============================================================\n")
        f.write("# CORTHEX HQ - Agent Configuration (에이전트 설정)\n")
        f.write("# =============================================================\n\n")
        yaml.dump(
            agents_cfg_raw, f,
            allow_unicode=True, default_flow_style=False, sort_keys=False,
        )

    # Hot-reload: update the running agent's system_prompt
    try:
        agent = registry.get_agent(agent_id)
        new_prompt = body.system_prompt
        if knowledge_mgr:
            extra = knowledge_mgr.get_knowledge_for_agent(agent.config.division)
            if extra:
                new_prompt += extra
        agent.config = agent.config.model_copy(update={"system_prompt": new_prompt})
    except Exception as e:
        logger.warning("Soul 핫리로드 실패: %s", e)

    return {"success": True, "agent_id": agent_id}


# ─── Knowledge Management ───


@app.get("/api/knowledge")
async def list_knowledge() -> list[dict]:
    """List all knowledge files."""
    if not knowledge_mgr:
        return []
    return knowledge_mgr.list_files()


@app.get("/api/knowledge/{folder}/{filename}")
async def read_knowledge(folder: str, filename: str) -> dict:
    """Read a knowledge file."""
    if not knowledge_mgr:
        return {"error": "not initialized"}
    content = knowledge_mgr.read_file(f"{folder}/{filename}")
    if content is None:
        return {"error": "file not found"}
    return {"folder": folder, "filename": filename, "content": content}


class KnowledgeSaveRequest(BaseModel):
    folder: str
    filename: str
    content: str


@app.post("/api/knowledge")
async def save_knowledge(body: KnowledgeSaveRequest) -> dict:
    """Create or update a knowledge file."""
    if not knowledge_mgr:
        return {"error": "not initialized"}
    rel = knowledge_mgr.save_file(body.folder, body.filename, body.content)
    return {"success": True, "path": rel}


@app.delete("/api/knowledge/{folder}/{filename}")
async def delete_knowledge(folder: str, filename: str) -> dict:
    """Delete a knowledge file."""
    if not knowledge_mgr:
        return {"error": "not initialized"}
    ok = knowledge_mgr.delete_file(f"{folder}/{filename}")
    return {"success": ok}


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
