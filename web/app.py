"""
CORTHEX HQ - FastAPI Web Application.

CEO 관제실 웹 인터페이스를 제공합니다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
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

from src.core.budget import BudgetManager
from src.core.context import SharedContext
from src.core.feedback import FeedbackManager
from src.core.healthcheck import run_healthcheck
from src.core.knowledge import KnowledgeManager
from src.core.message import Message, MessageType
from src.core.task_store import TaskStore, StoredTask, TaskStatus
from src.core.orchestrator import Orchestrator
from src.core.performance import build_performance_report
from src.core.preset import PresetManager
from src.core.quality_gate import QualityGate
from src.core.quality_rules_manager import QualityRulesManager
from src.core.git_sync import git_auto_sync
from src.core.registry import AgentRegistry
from src.core.replay import build_replay, get_last_correlation_id
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.batch_collector import BatchCollector
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
# .env.local 우선 → .env 폴백 (AnySign4PC .env 잠금 방지)
_env_local = PROJECT_DIR / ".env.local"
if _env_local.exists():
    load_dotenv(_env_local)
else:
    load_dotenv(PROJECT_DIR / ".env")

# Output directory for saved results
OUTPUT_DIR = PROJECT_DIR / "output"

# FastAPI app
app = FastAPI(title="CORTHEX HQ", version="1.3.0")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
OUTPUT_DIR.mkdir(exist_ok=True)
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
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
task_store: TaskStore = TaskStore()
telegram_app: Any = None  # telegram.ext.Application (src.telegram)
budget_manager: BudgetManager | None = None
preset_manager: PresetManager | None = None
oauth_manager: OAuthManager | None = None
webhook_receiver: WebhookReceiver | None = None
tool_pool_ref: ToolPool | None = None
feedback_manager: FeedbackManager | None = None
quality_rules_manager: QualityRulesManager | None = None


@app.on_event("startup")
async def startup() -> None:
    """Initialize the agent system on server start."""
    global orchestrator, model_router, registry, context, knowledge_mgr, agents_cfg_raw, budget_manager, preset_manager, oauth_manager, webhook_receiver, tool_pool_ref, feedback_manager, quality_rules_manager

    logger.info("CORTHEX HQ 시스템 초기화 중...")

    try:
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

        # BatchCollector 초기화 (Batch API 50% 할인)
        openai_raw = openai_prov._client if openai_prov else None
        anthropic_raw = anthropic_prov._client if anthropic_prov else None
        if openai_raw or anthropic_raw:
            model_router.batch_collector = BatchCollector(
                openai_client=openai_raw,
                anthropic_client=anthropic_raw,
            )

        # Build tool pool
        tool_pool = ToolPool(model_router)
        tool_pool.build_from_config(tools_cfg)

        # Build agent registry (with knowledge injection)
        context = SharedContext()
        registry = AgentRegistry()
        knowledge_dir = PROJECT_DIR / "knowledge"
        knowledge_mgr = KnowledgeManager(knowledge_dir)
        knowledge_mgr.load_all()
        registry.build_from_config(
            agents_cfg_raw, model_router, tool_pool, context,
            knowledge_dir=knowledge_dir,
        )
        context.set_registry(registry)

        # Status callback: push real-time updates via WebSocket
        def on_message(msg: Message) -> None:
            asyncio.create_task(_handle_message_event(msg))

        context.set_status_callback(on_message)

        # Build quality gate with rules manager (CEO 웹 UI에서 설정 변경 가능)
        quality_rules_manager = QualityRulesManager(CONFIG_DIR / "quality_rules.yaml")
        quality_gate = QualityGate(CONFIG_DIR / "quality_rules.yaml")
        quality_gate.set_rules_manager(quality_rules_manager)
        context.set_quality_gate(quality_gate)

        # Build orchestrator
        orchestrator = Orchestrator(registry, model_router)

        # Build budget, preset & feedback managers
        budget_manager = BudgetManager(CONFIG_DIR / "budget.yaml")
        preset_manager = PresetManager(CONFIG_DIR / "presets.yaml")
        data_dir = PROJECT_DIR / "data"
        feedback_manager = FeedbackManager(data_dir / "feedback.json")

        # Initialize SNS subsystem
        oauth_manager = OAuthManager()
        webhook_receiver = WebhookReceiver()
        tool_pool_ref = tool_pool

        logger.info("CORTHEX HQ 시스템 준비 완료 (에이전트 %d명)", registry.agent_count)

        # 텔레그램 봇 초기화 (src.telegram 패키지 — 양방향 브릿지)
        if os.getenv("TELEGRAM_ENABLED", "0") == "1":
            try:
                from src.telegram.bot import create_bot
                global telegram_app
                telegram_app = await create_bot(
                    orchestrator=orchestrator,
                    ws_manager=ws_manager,
                    model_router=model_router,
                    registry=registry,
                    context=context,
                    task_store=task_store,
                )
                await telegram_app.initialize()
                await telegram_app.start()
                asyncio.create_task(telegram_app.updater.start_polling(drop_pending_updates=True))
                logger.info("텔레그램 봇 시작 완료 (src.telegram)")
            except Exception as e:
                logger.error("텔레그램 봇 시작 실패 (웹 서버는 계속 동작): %s", e)
                telegram_app = None
        else:
            logger.info("텔레그램 봇 비활성화 (TELEGRAM_ENABLED=0)")

    except Exception as e:
        logger.error("시스템 초기화 실패: %s", e, exc_info=True)
        # Knowledge manager at minimum — so file management works without LLM
        if knowledge_mgr is None:
            try:
                knowledge_dir = PROJECT_DIR / "knowledge"
                knowledge_mgr = KnowledgeManager(knowledge_dir)
                knowledge_mgr.load_all()
                logger.info("지식 관리자만 초기화됨 (LLM 없이 파일 관리 가능)")
            except Exception:
                pass


@app.on_event("shutdown")
async def shutdown() -> None:
    """Clean up resources on server shutdown."""
    if telegram_app:
        try:
            await telegram_app.updater.stop()
            await telegram_app.stop()
            await telegram_app.shutdown()
            logger.info("텔레그램 봇 종료 완료")
        except Exception as e:
            logger.warning("텔레그램 봇 종료 중 오류 (무시): %s", e)
    if model_router:
        await model_router.close()
    logger.info("CORTHEX HQ 시스템 종료")


async def _handle_message_event(msg: Message) -> None:
    """Push agent activity to WebSocket clients."""
    if msg.type == MessageType.TASK_REQUEST:
        await ws_manager.send_agent_status(msg.receiver_id, "working", 0.1)
        await ws_manager.send_activity_log(
            msg.sender_id, f"→ {msg.receiver_id} 에게 작업 배정"
        )
    elif msg.type == MessageType.STATUS_UPDATE:
        await ws_manager.send_agent_status(
            msg.sender_id, "working", msg.progress_pct, detail=msg.detail
        )
        await ws_manager.send_activity_log(
            msg.sender_id, f"단계 진행: {msg.current_step} - {msg.detail}"
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
        # 중간 보고서 아카이브 저장
        _archive_agent_report(msg)
        # SNS 발행 요청 텔레그램 알림 확인
        await _check_sns_notifications()

    # 텔레그램 브릿지에도 이벤트 전달
    try:
        from src.telegram.bot import get_bridge
        bridge = get_bridge()
        if bridge:
            await bridge.on_agent_event(msg)
    except ImportError:
        pass


# ─── SNS 텔레그램 알림 ───

_notified_sns_ids: set[str] = set()


async def _check_sns_notifications() -> None:
    """SNS 승인 큐에 새 요청이 있으면 텔레그램에 자동 알림."""
    if not tool_pool_ref:
        return
    try:
        from src.telegram.bot import get_notifier
        notifier = get_notifier()
        if not notifier:
            return
        result = await tool_pool_ref.invoke("sns_manager", action="queue")
        pending = result.get("pending", [])
        for item in pending:
            rid = item.get("request_id", "")
            if rid and rid not in _notified_sns_ids:
                _notified_sns_ids.add(rid)
                await notifier.notify_sns_approval(item)
    except Exception:
        pass


# ─── Archive ───

ARCHIVE_DIR = PROJECT_DIR / "archive"


def _archive_agent_report(msg: Message) -> None:
    """모든 에이전트의 보고서를 부서별 아카이브에 저장."""
    if not registry:
        return
    try:
        agent = registry.get_agent(msg.sender_id)
    except Exception:
        return

    division = agent.config.division or "general"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    archive_dir = ARCHIVE_DIR / division
    archive_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{timestamp}_{msg.sender_id}.md"

    # 보고서 본문 추출
    result_text = str(msg.result_data) if msg.result_data else "(결과 없음)"
    task_desc = getattr(msg, "task_description", "") or "(지시 내용 없음)"

    content = (
        f"# {agent.config.name_ko} 보고서\n\n"
        f"> **작성자**: {agent.config.name_ko} ({msg.sender_id})  \n"
        f"> **소속**: {division}  \n"
        f"> **보고 대상**: {msg.receiver_id}  \n"
        f"> **지시 내용**: {task_desc}  \n"
        f"> **작성 시각**: {timestamp}  \n"
        f"> **소요 시간**: {msg.execution_time_seconds}초  \n"
        f"> **상관 작업 ID**: {msg.correlation_id}  \n\n"
        f"---\n\n{result_text}\n"
    )
    (archive_dir / filename).write_text(content, encoding="utf-8")


# ─── Routes ───


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Main CEO dashboard page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health_check() -> dict:
    """서버 상태 진단 엔드포인트."""
    return {
        "status": "ok",
        "orchestrator": orchestrator is not None,
        "model_router": model_router is not None,
        "registry": registry is not None,
        "knowledge_mgr": knowledge_mgr is not None,
        "agent_count": registry.agent_count if registry else 0,
    }


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


@app.get("/api/budget")
async def get_budget() -> dict:
    """Return current budget status."""
    if not budget_manager or not model_router:
        return {"error": "시스템 미초기화"}
    status = budget_manager.get_status(model_router.cost_tracker)
    return status.to_dict()


@app.get("/api/presets")
async def get_presets() -> list[dict]:
    """Return all command presets."""
    if not preset_manager:
        return []
    return preset_manager.to_list()


@app.post("/api/presets")
async def add_preset(body: dict) -> dict:
    """Add a new command preset."""
    if not preset_manager:
        return {"error": "시스템 미초기화"}
    name = body.get("name", "").strip()
    command = body.get("command", "").strip()
    if not name or not command:
        return {"error": "name과 command가 필요합니다"}
    preset_manager.add(name, command)
    return {"success": True, "name": name, "command": command}


@app.delete("/api/presets/{name}")
async def delete_preset(name: str) -> dict:
    """Delete a command preset."""
    if not preset_manager:
        return {"error": "시스템 미초기화"}
    if preset_manager.remove(name):
        return {"success": True}
    return {"error": f"프리셋 '{name}'을 찾을 수 없습니다"}


@app.get("/api/conversation")
async def get_conversation() -> list[dict]:
    """Return conversation history."""
    if not orchestrator:
        return []
    return orchestrator.conversation_history


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


@app.get("/api/quality")
async def get_quality() -> dict:
    """Return quality gate statistics."""
    if not context or not context.quality_gate:
        return {"error": "시스템 미초기화"}
    return context.quality_gate.stats.to_dict()


@app.get("/api/quality-rules")
async def get_quality_rules() -> dict:
    """Return quality gate configuration (rules + rubrics)."""
    if not quality_rules_manager:
        return {"error": "시스템 미초기화"}
    return quality_rules_manager.to_dict()


@app.get("/api/available-models")
async def get_available_models() -> list[dict]:
    """Return list of all available models from models.yaml."""
    models_path = CONFIG_DIR / "models.yaml"
    if not models_path.exists():
        return []
    models_cfg = yaml.safe_load(models_path.read_text(encoding="utf-8"))
    models: list[dict] = []
    for provider_name, provider_data in models_cfg.get("providers", {}).items():
        for m in provider_data.get("models", []):
            models.append({
                "name": m["name"],
                "provider": provider_name,
                "tier": m.get("tier", ""),
                "cost_input": m.get("cost_per_1m_input", 0),
                "cost_output": m.get("cost_per_1m_output", 0),
            })
    return models


@app.put("/api/quality-rules/model")
async def update_review_model(body: dict) -> dict:
    """Update the review model used for quality checks."""
    if not quality_rules_manager:
        return {"error": "시스템 미초기화"}
    model_name = body.get("review_model", "").strip()
    if not model_name:
        return {"error": "review_model이 필요합니다"}
    quality_rules_manager.set_review_model(model_name)
    sync = await git_auto_sync(
        quality_rules_manager.path,
        f"[CORTHEX HQ] 검수 모델 변경: {model_name}",
    )
    return {"success": True, "review_model": model_name, "git_sync": sync}


@app.put("/api/quality-rules/rubric/{division}")
async def update_rubric(division: str, body: dict) -> dict:
    """Create or update a rubric for a specific division."""
    if not quality_rules_manager:
        return {"error": "시스템 미초기화"}
    name = body.get("name", "").strip()
    prompt = body.get("prompt", "").strip()
    if not name or not prompt:
        return {"error": "name과 prompt가 필요합니다"}
    quality_rules_manager.set_rubric(division, name, prompt)
    sync = await git_auto_sync(
        quality_rules_manager.path,
        f"[CORTHEX HQ] 검수 기준 변경: {division}",
    )
    return {"success": True, "division": division, "git_sync": sync}


@app.get("/api/replay/latest")
async def get_replay_latest() -> dict:
    """Get replay for the most recent command."""
    if not context:
        return {"error": "시스템 미초기화"}
    cid = get_last_correlation_id(context)
    if not cid:
        return {"error": "실행된 명령이 없습니다"}
    report = build_replay(cid, context)
    if not report:
        return {"error": "리플레이 데이터 없음"}
    return report.to_dict()


@app.get("/api/replay/{correlation_id}")
async def get_replay(correlation_id: str) -> dict:
    """Get replay for a specific correlation_id."""
    if not context:
        return {"error": "시스템 미초기화"}
    report = build_replay(correlation_id, context)
    if not report:
        return {"error": "리플레이 데이터 없음"}
    return report.to_dict()


@app.get("/api/feedback")
async def get_feedback() -> dict:
    """Return CEO feedback statistics."""
    if not feedback_manager:
        return {"error": "시스템 미초기화"}
    return feedback_manager.to_dict()


@app.post("/api/feedback")
async def add_feedback(body: dict) -> dict:
    """Record CEO feedback for a task result."""
    if not feedback_manager:
        return {"error": "시스템 미초기화"}
    correlation_id = body.get("correlation_id", "").strip()
    rating = body.get("rating", "").strip()
    if not correlation_id or rating not in ("good", "bad"):
        return {"error": "correlation_id와 rating(good/bad)이 필요합니다"}
    comment = body.get("comment", "")
    agent_id = body.get("agent_id", "")
    feedback_manager.add(
        correlation_id=correlation_id,
        rating=rating,
        comment=comment,
        agent_id=agent_id,
    )
    return {
        "success": True,
        "satisfaction_rate": feedback_manager.satisfaction_rate,
        "total": feedback_manager.total_count,
    }


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
        "reasoning_effort": cfg.reasoning_effort,
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


# ─── Model Management ───


@app.get("/api/models")
async def get_models() -> list[dict]:
    """Return available models from models.yaml."""
    try:
        models_cfg = yaml.safe_load(
            (CONFIG_DIR / "models.yaml").read_text(encoding="utf-8")
        )
    except Exception:
        return []
    result = []
    for provider_name, provider_cfg in models_cfg.get("providers", {}).items():
        for model in provider_cfg.get("models", []):
            result.append({
                "name": model["name"],
                "provider": provider_name,
                "tier": model.get("tier", ""),
                "cost_input": model.get("cost_per_1m_input", 0),
                "cost_output": model.get("cost_per_1m_output", 0),
                "reasoning_levels": model.get("reasoning_levels", []),
            })
    return result


class ModelUpdateRequest(BaseModel):
    model_name: str


@app.put("/api/agents/{agent_id}/model")
async def update_agent_model(agent_id: str, body: ModelUpdateRequest) -> dict:
    """Update an agent's model_name and persist to agents.yaml."""
    global agents_cfg_raw
    if not registry or not agents_cfg_raw:
        return {"error": "not initialized"}

    # Validate model_name exists in models.yaml
    try:
        models_cfg = yaml.safe_load(
            (CONFIG_DIR / "models.yaml").read_text(encoding="utf-8")
        )
        valid_names = []
        for prov_cfg in models_cfg.get("providers", {}).values():
            for m in prov_cfg.get("models", []):
                valid_names.append(m["name"])
        if body.model_name not in valid_names:
            return {"error": f"Unknown model: {body.model_name}"}
    except Exception:
        pass

    # Update in-memory YAML config
    found = False
    for a in agents_cfg_raw.get("agents", []):
        if a.get("agent_id") == agent_id:
            a["model_name"] = body.model_name
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

    # Hot-reload: update the running agent's model_name
    try:
        agent = registry.get_agent(agent_id)
        agent.config = agent.config.model_copy(update={"model_name": body.model_name})
    except Exception as e:
        logger.warning("모델 핫리로드 실패: %s", e)

    return {"success": True, "agent_id": agent_id, "model_name": body.model_name}


class ReasoningUpdateRequest(BaseModel):
    reasoning_effort: str  # "", "low", "medium", "high"


@app.put("/api/agents/{agent_id}/reasoning")
async def update_reasoning_effort(agent_id: str, body: ReasoningUpdateRequest) -> dict:
    """Update an agent's reasoning_effort and persist to agents.yaml."""
    global agents_cfg_raw
    if not registry or not agents_cfg_raw:
        return {"error": "not initialized"}

    valid = {"", "low", "medium", "high"}
    if body.reasoning_effort not in valid:
        return {"error": f"Invalid reasoning_effort: {body.reasoning_effort}"}

    # Update in-memory YAML config
    found = False
    for a in agents_cfg_raw.get("agents", []):
        if a.get("agent_id") == agent_id:
            a["reasoning_effort"] = body.reasoning_effort
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

    # Hot-reload
    try:
        agent = registry.get_agent(agent_id)
        agent.config = agent.config.model_copy(update={"reasoning_effort": body.reasoning_effort})
    except Exception as e:
        logger.warning("추론 수준 핫리로드 실패: %s", e)

    return {"success": True, "agent_id": agent_id, "reasoning_effort": body.reasoning_effort}


# ─── Task Management ───


def _save_result_file(task: StoredTask) -> str | None:
    """Save task result as a markdown file. Returns relative path."""
    if not task.result_data or not task.success:
        return None
    try:
        OUTPUT_DIR.mkdir(exist_ok=True)
        timestamp = task.created_at.strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(
            c if c.isalnum() or c in "._- " else "_"
            for c in task.command[:30]
        ).strip()
        filename = f"{timestamp}_{safe_name}.md"
        filepath = OUTPUT_DIR / filename
        content = (
            f"# {task.command}\n\n"
            f"> **작업 ID**: {task.task_id}  \n"
            f"> **생성**: {task.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC  \n"
            f"> **소요 시간**: {task.execution_time_seconds}초  \n"
            f"> **비용**: ${task.cost_usd:.4f}  \n"
            f"> **토큰**: {task.tokens_used:,}\n\n---\n\n"
            f"{task.result_data}\n"
        )
        filepath.write_text(content, encoding="utf-8")
        return f"output/{filename}"
    except Exception:
        return None


def _task_to_dict(t: StoredTask, include_result: bool = False) -> dict:
    d = {
        "task_id": t.task_id,
        "command": t.command,
        "status": t.status.value,
        "created_at": t.created_at.isoformat(),
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "success": t.success,
        "summary": t.result_summary,
        "time_seconds": t.execution_time_seconds,
        "cost": t.cost_usd,
        "output_file": t.output_file,
    }
    if include_result:
        d["result_data"] = t.result_data
        d["tokens_used"] = t.tokens_used
    return d


@app.get("/api/tasks")
async def list_tasks() -> list[dict]:
    """List all tasks with status."""
    return [_task_to_dict(t) for t in task_store.list_all()]


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    """Get full task details including result content."""
    t = task_store.get(task_id)
    if not t:
        return {"error": "task not found"}
    return _task_to_dict(t, include_result=True)


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


# ─── Archive API ───


@app.get("/api/archive")
async def list_archive() -> list[dict]:
    """부서별 아카이브 파일 목록 반환."""
    if not ARCHIVE_DIR.exists():
        return []
    result = []
    for division_dir in sorted(ARCHIVE_DIR.iterdir()):
        if not division_dir.is_dir() or division_dir.name.startswith("."):
            continue
        for f in sorted(division_dir.iterdir(), reverse=True):
            if f.suffix == ".md":
                result.append({
                    "division": division_dir.name,
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(
                        f.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                })
    return result


@app.get("/api/archive/{division}/{filename}")
async def read_archive(division: str, filename: str) -> dict:
    """개별 아카이브 보고서 조회."""
    filepath = ARCHIVE_DIR / division / filename
    if not filepath.exists() or not filepath.is_file():
        return {"error": "file not found"}
    content = filepath.read_text(encoding="utf-8")
    return {"division": division, "filename": filename, "content": content}


@app.get("/api/archive/by-correlation/{correlation_id}")
async def list_archive_by_correlation(correlation_id: str) -> list[dict]:
    """특정 작업의 모든 중간 보고서 조회 (correlation_id 기준)."""
    if not ARCHIVE_DIR.exists():
        return []
    results = []
    for division_dir in ARCHIVE_DIR.iterdir():
        if not division_dir.is_dir():
            continue
        for f in sorted(division_dir.iterdir()):
            if not f.suffix == ".md":
                continue
            content = f.read_text(encoding="utf-8")
            if correlation_id in content:
                results.append({
                    "division": division_dir.name,
                    "filename": f.name,
                    "content": content,
                })
    return results


# ─── SNS 발행 API ───

from src.integrations.sns_publisher import SNSPublisher

_sns = SNSPublisher()


@app.get("/api/sns/status")
async def sns_status() -> dict:
    """SNS 플랫폼 연동 상태 확인."""
    return _sns.get_status()


class InstagramPhotoRequest(BaseModel):
    image_url: str
    caption: str = ""


class InstagramReelRequest(BaseModel):
    video_url: str
    caption: str = ""


class YouTubeUploadRequest(BaseModel):
    file_path: str
    title: str
    description: str = ""
    tags: list[str] = []
    privacy: str = "private"


@app.post("/api/sns/instagram/photo")
async def publish_ig_photo(body: InstagramPhotoRequest) -> dict:
    """Instagram 사진 게시."""
    r = await _sns.publish_instagram_photo(body.image_url, body.caption)
    return {"success": r.success, "post_id": r.post_id, "url": r.url, "error": r.error}


@app.post("/api/sns/instagram/reel")
async def publish_ig_reel(body: InstagramReelRequest) -> dict:
    """Instagram 릴스 발행."""
    r = await _sns.publish_instagram_reel(body.video_url, body.caption)
    return {"success": r.success, "post_id": r.post_id, "url": r.url, "error": r.error}


@app.post("/api/sns/youtube/upload")
async def publish_yt_video(body: YouTubeUploadRequest) -> dict:
    """YouTube 동영상 업로드."""
    r = await _sns.publish_youtube_video(
        body.file_path, body.title, body.description, body.tags, body.privacy,
    )
    return {"success": r.success, "post_id": r.post_id, "url": r.url, "error": r.error}


# ─── REST Command API (외부 연동용) ───


class CommandRequest(BaseModel):
    text: str
    depth: int = 3
    batch: bool = False


@app.post("/api/command")
async def submit_command(body: CommandRequest) -> dict:
    """외부에서 명령 제출 (Telegram, OpenClaw, 기타 클라이언트)."""
    if not orchestrator:
        return {"error": "시스템 미초기화"}
    stored = task_store.create(body.text)
    asyncio.create_task(
        _run_background_task(stored, body.text, body.depth, body.batch)
    )
    return {"task_id": stored.task_id, "status": "accepted"}


async def _execute_command_for_api(
    text: str, depth: int = 3, use_batch: bool = False
) -> dict:
    """Telegram/REST 등 외부 클라이언트를 위한 동기적 명령 실행."""
    if not orchestrator:
        return {"error": "시스템 미초기화"}
    stored = task_store.create(text)
    stored.status = TaskStatus.RUNNING
    stored.started_at = datetime.now(timezone.utc)
    start_cost = model_router.cost_tracker.total_cost if model_router else 0
    start_tokens = model_router.cost_tracker.total_tokens if model_router else 0
    start_time = time.monotonic()

    try:
        result = await orchestrator.process_command(
            text, context={"max_steps": depth, "use_batch": use_batch}
        )
        stored.success = result.success
        stored.result_data = str(result.result_data or result.summary)
        stored.result_summary = result.summary
        stored.status = TaskStatus.COMPLETED
    except Exception as e:
        stored.success = False
        stored.result_data = str(e)
        stored.result_summary = f"오류: {e}"
        stored.status = TaskStatus.FAILED
    finally:
        stored.completed_at = datetime.now(timezone.utc)
        stored.execution_time_seconds = round(time.monotonic() - start_time, 2)
        stored.cost_usd = round(
            (model_router.cost_tracker.total_cost - start_cost) if model_router else 0, 6
        )
        stored.tokens_used = (
            (model_router.cost_tracker.total_tokens - start_tokens) if model_router else 0
        )
        stored.output_file = _save_result_file(stored)

    return {
        "task_id": stored.task_id,
        "success": stored.success,
        "result_data": stored.result_data,
        "summary": stored.result_summary,
        "time_seconds": stored.execution_time_seconds,
        "cost": stored.cost_usd,
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """WebSocket for real-time updates and CEO commands."""
    await ws_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("WebSocket 잘못된 JSON 수신: %s", data[:200])
                await ws.send_text(json.dumps({
                    "event": "error",
                    "data": {"message": "잘못된 JSON 형식입니다."},
                }, ensure_ascii=False))
                continue

            if msg.get("type") == "command":
                user_input = msg.get("text", "").strip()
                depth = msg.get("depth", 3)
                use_batch = msg.get("batch", False)
                if not user_input or not orchestrator:
                    continue

                # Create a stored task
                stored = task_store.create(user_input)

                # Notify all clients: task accepted
                await ws_manager.broadcast("task_accepted", {
                    "task_id": stored.task_id,
                    "command": user_input,
                    "batch": use_batch,
                })

                # Reset all agent statuses
                if registry:
                    for agent in registry.list_all():
                        await ws_manager.send_agent_status(
                            agent.config.agent_id, "idle"
                        )

                # Launch background task
                asyncio.create_task(
                    _run_background_task(stored, user_input, depth, use_batch)
                )

    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception as e:
        logger.error("WebSocket 오류: %s", e)
        ws_manager.disconnect(ws)


async def _run_background_task(
    stored: StoredTask, user_input: str, depth: int, use_batch: bool = False
) -> None:
    """Execute orchestrator command in the background."""
    stored.status = TaskStatus.RUNNING
    stored.started_at = datetime.now(timezone.utc)
    start_cost = model_router.cost_tracker.total_cost if model_router else 0
    start_tokens = model_router.cost_tracker.total_tokens if model_router else 0
    start_time = time.monotonic()

    try:
        result = await orchestrator.process_command(
            user_input, context={"max_steps": depth, "use_batch": use_batch}
        )
        stored.success = result.success
        stored.result_data = str(result.result_data or result.summary)
        stored.result_summary = result.summary
        stored.status = TaskStatus.COMPLETED
    except Exception as e:
        stored.success = False
        stored.result_data = str(e)
        stored.result_summary = f"오류: {e}"
        stored.status = TaskStatus.FAILED
    finally:
        stored.completed_at = datetime.now(timezone.utc)
        stored.execution_time_seconds = round(time.monotonic() - start_time, 2)
        stored.cost_usd = round(
            (model_router.cost_tracker.total_cost - start_cost) if model_router else 0, 6
        )
        stored.tokens_used = (
            (model_router.cost_tracker.total_tokens - start_tokens) if model_router else 0
        )

        # Save result to file
        stored.output_file = _save_result_file(stored)

        # Broadcast completion to ALL connected clients
        await ws_manager.broadcast("task_completed", {
            "task_id": stored.task_id,
            "success": stored.success,
            "content": stored.result_data,
            "summary": stored.result_summary,
            "time_seconds": stored.execution_time_seconds,
            "cost": stored.cost_usd,
            "output_file": stored.output_file,
        })

        # Reset all agent statuses
        if registry:
            for agent in registry.list_all():
                await ws_manager.send_agent_status(
                    agent.config.agent_id, "idle"
                )

        # GitHub 자동 동기화 (비동기, UI 안 멈춤)
        asyncio.create_task(_auto_sync_to_github())


async def _auto_sync_to_github() -> None:
    """archive/와 output/ 폴더를 GitHub에 자동 동기화."""
    try:
        # git pull --rebase (충돌 방지)
        proc = await asyncio.create_subprocess_exec(
            "git", "pull", "--rebase", "--autostash",
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

        # git add archive/ output/
        proc = await asyncio.create_subprocess_exec(
            "git", "add", "archive/", "output/",
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

        # 변경사항 확인
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--cached", "--quiet",
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        ret = await proc.wait()
        if ret == 0:
            # 변경사항 없음
            return

        # git commit
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", f"auto: 보고서 동기화 ({timestamp})",
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

        # git push
        proc = await asyncio.create_subprocess_exec(
            "git", "push",
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        ret = await proc.wait()
        if ret == 0:
            logger.info("GitHub 자동 동기화 완료")
        else:
            stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
            logger.warning("GitHub push 실패: %s", stderr)

    except Exception as e:
        logger.warning("GitHub 자동 동기화 오류: %s", e)


# ─── SNS 연동 API ───


@app.get("/api/sns/oauth/status")
async def sns_oauth_status() -> dict:
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
