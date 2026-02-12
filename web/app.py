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

from src.core.context import SharedContext
from src.core.knowledge import KnowledgeManager
from src.core.message import Message, MessageType
from src.core.task_store import TaskStore, StoredTask, TaskStatus
from src.core.orchestrator import Orchestrator
from src.core.registry import AgentRegistry
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.batch_collector import BatchCollector
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

# Output directory for saved results
OUTPUT_DIR = PROJECT_DIR / "output"

# FastAPI app
app = FastAPI(title="CORTHEX HQ", version="0.3.0")
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
telegram_bot: Any = None  # CorthexTelegramBot (optional)


@app.on_event("startup")
async def startup() -> None:
    """Initialize the agent system on server start."""
    global orchestrator, model_router, registry, context, knowledge_mgr, agents_cfg_raw

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

        # Build orchestrator
        orchestrator = Orchestrator(registry, model_router)

        logger.info("CORTHEX HQ 시스템 준비 완료 (에이전트 %d명)", registry.agent_count)

        # Telegram Bot (선택사항)
        tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        tg_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if tg_token and tg_chat_id:
            try:
                from src.integrations.telegram_bot import CorthexTelegramBot, HAS_TELEGRAM
                if HAS_TELEGRAM:
                    global telegram_bot
                    telegram_bot = CorthexTelegramBot(
                        token=tg_token,
                        allowed_chat_id=tg_chat_id,
                        command_callback=_execute_command_for_api,
                    )
                    async def _start_telegram():
                        try:
                            await telegram_bot.start()
                        except Exception as exc:
                            logger.error("텔레그램 봇 시작 실패: %s", exc, exc_info=True)
                    asyncio.create_task(_start_telegram())
                    logger.info("텔레그램 봇 활성화됨 (chat_id=%s)", tg_chat_id)
            except Exception as e:
                logger.warning("텔레그램 봇 초기화 실패: %s", e)

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
            msg = json.loads(data)

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
