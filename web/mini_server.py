"""
CORTHEX HQ - Mini Server (경량 서버)

Oracle Cloud 무료 서버(1GB RAM)에서 대시보드를 서비스하기 위한 경량 서버.
전체 백엔드의 핵심 API만 제공하여 대시보드 UI가 정상 작동하도록 함.
텔레그램 봇도 여기서 24시간 구동됩니다.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # PyYAML 미설치 시 graceful fallback

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

logger = logging.getLogger("corthex.mini_server")

# ── 텔레그램 봇 (선택적 로드) ──
_telegram_available = False
try:
    from telegram import Update, BotCommand
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        ContextTypes,
        filters,
    )
    _telegram_available = True
except ImportError:
    logger.info("python-telegram-bot 미설치 — 텔레그램 봇 비활성화")

KST = timezone(timedelta(hours=9))

app = FastAPI(title="CORTHEX HQ Mini Server")

# ── HTML 서빙 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

def get_build_number() -> str:
    """빌드 번호 반환.
    실제 빌드 번호는 GitHub Actions 배포 시 deploy.yml이 HTML에 직접 주입함.
    이 함수는 로컬 개발 환경(배포 전)에서만 사용되는 폴백 값을 반환."""
    return "dev"

# ── 설정 파일에서 에이전트/도구 정보 로드 ──
CONFIG_DIR = Path(BASE_DIR).parent / "config"

def _load_config(name: str) -> dict:
    """설정 파일 로드. JSON을 먼저 시도하고, 없으면 YAML로 시도."""
    # 1순위: JSON 파일 (deploy.yml이 배포 시 YAML → JSON으로 변환해둠)
    json_path = CONFIG_DIR / f"{name}.json"
    if json_path.exists():
        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            logger.info("%s.json 로드 성공", name)
            return raw
        except Exception as e:
            logger.warning("%s.json 로드 실패: %s", name, e)

    # 2순위: YAML 파일 (PyYAML 필요)
    yaml_path = CONFIG_DIR / f"{name}.yaml"
    if yaml is not None and yaml_path.exists():
        try:
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            logger.info("%s.yaml 로드 성공", name)
            return raw
        except Exception as e:
            logger.warning("%s.yaml 로드 실패: %s", name, e)

    logger.warning("%s 설정 파일 로드 실패 (빈 설정 사용)", name)
    return {}


def _load_agents() -> dict:
    """에이전트별 상세 정보(allowed_tools, capabilities 등)를 로드."""
    raw = _load_config("agents")
    lookup: dict[str, dict] = {}
    for a in raw.get("agents", []):
        lookup[a["agent_id"]] = a
    return lookup


def _load_tools() -> list[dict]:
    """도구 목록을 로드."""
    raw = _load_config("tools")
    return raw.get("tools", [])

# 서버 시작 시 1회 로드 (메모리 절약: 필요한 정보만 캐시)
_AGENTS_DETAIL: dict[str, dict] = _load_agents()
_TOOLS_LIST: list[dict] = _load_tools()


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(TEMPLATE_DIR, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # BUILD_NUMBER_PLACEHOLDER를 실제 빌드 번호로 치환
    build_number = get_build_number()
    html_content = html_content.replace("BUILD_NUMBER_PLACEHOLDER", build_number)

    return HTMLResponse(content=html_content)


# ── 에이전트 목록 ──
AGENTS = [
    {"agent_id": "chief_of_staff", "name_ko": "비서실장", "role": "manager", "division": "secretary", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "report_specialist", "name_ko": "총괄 보좌관", "role": "specialist", "division": "secretary", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "schedule_specialist", "name_ko": "전략 보좌관", "role": "specialist", "division": "secretary", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "relay_specialist", "name_ko": "소통 보좌관", "role": "specialist", "division": "secretary", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "cto_manager", "name_ko": "기술개발처장 (CTO)", "role": "manager", "division": "leet_master.tech", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "frontend_specialist", "name_ko": "프론트엔드 Specialist", "role": "specialist", "division": "leet_master.tech", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "backend_specialist", "name_ko": "백엔드/API Specialist", "role": "specialist", "division": "leet_master.tech", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "infra_specialist", "name_ko": "DB/인프라 Specialist", "role": "specialist", "division": "leet_master.tech", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "ai_model_specialist", "name_ko": "AI 모델 Specialist", "role": "specialist", "division": "leet_master.tech", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "cso_manager", "name_ko": "사업기획처장 (CSO)", "role": "manager", "division": "leet_master.strategy", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "market_research_specialist", "name_ko": "시장조사 Specialist", "role": "specialist", "division": "leet_master.strategy", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "business_plan_specialist", "name_ko": "사업계획서 Specialist", "role": "specialist", "division": "leet_master.strategy", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "financial_model_specialist", "name_ko": "재무모델링 Specialist", "role": "specialist", "division": "leet_master.strategy", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "clo_manager", "name_ko": "법무·IP처장 (CLO)", "role": "manager", "division": "leet_master.legal", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "copyright_specialist", "name_ko": "저작권 Specialist", "role": "specialist", "division": "leet_master.legal", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "patent_specialist", "name_ko": "특허/약관 Specialist", "role": "specialist", "division": "leet_master.legal", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "cmo_manager", "name_ko": "마케팅·고객처장 (CMO)", "role": "manager", "division": "leet_master.marketing", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "survey_specialist", "name_ko": "설문/리서치 Specialist", "role": "specialist", "division": "leet_master.marketing", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "content_specialist", "name_ko": "콘텐츠 Specialist", "role": "specialist", "division": "leet_master.marketing", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "community_specialist", "name_ko": "커뮤니티 Specialist", "role": "specialist", "division": "leet_master.marketing", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "cio_manager", "name_ko": "투자분석처장 (CIO)", "role": "manager", "division": "finance.investment", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "market_condition_specialist", "name_ko": "시황분석 Specialist", "role": "specialist", "division": "finance.investment", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "stock_analysis_specialist", "name_ko": "종목분석 Specialist", "role": "specialist", "division": "finance.investment", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "technical_analysis_specialist", "name_ko": "기술적분석 Specialist", "role": "specialist", "division": "finance.investment", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "risk_management_specialist", "name_ko": "리스크관리 Specialist", "role": "specialist", "division": "finance.investment", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "cpo_manager", "name_ko": "출판·기록처장 (CPO)", "role": "manager", "division": "publishing", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "chronicle_specialist", "name_ko": "회사연대기 Specialist", "role": "specialist", "division": "publishing", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "editor_specialist", "name_ko": "콘텐츠편집 Specialist", "role": "specialist", "division": "publishing", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "archive_specialist", "name_ko": "아카이브 Specialist", "role": "specialist", "division": "publishing", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
]

# ── WebSocket 관리 ──
connected_clients: list[WebSocket] = []


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    try:
        # 연결 시 초기 상태 전송
        now = datetime.now(KST).strftime("%H:%M:%S")
        await ws.send_json({
            "event": "activity_log",
            "data": {
                "agent_id": "chief_of_staff",
                "message": "시스템 연결 완료. 대기 중입니다.",
                "level": "info",
                "time": now,
            }
        })
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            # 메시지를 받으면 간단한 응답
            if msg.get("type") == "command":
                await ws.send_json({
                    "event": "result",
                    "data": {
                        "content": "현재 경량 모드로 실행 중입니다. 전체 AI 에이전트 기능은 메인 서버에서 사용 가능합니다.",
                        "sender_id": "chief_of_staff",
                        "time_seconds": 0.1,
                        "cost": 0,
                    }
                })
    except WebSocketDisconnect:
        connected_clients.remove(ws)
    except Exception:
        if ws in connected_clients:
            connected_clients.remove(ws)


# ── API 엔드포인트 ──

@app.get("/api/auth/status")
async def auth_status():
    return {"bootstrap_mode": True, "role": "ceo", "authenticated": True}


@app.get("/api/agents")
async def get_agents():
    return AGENTS


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    for a in AGENTS:
        if a["agent_id"] == agent_id:
            # agents.yaml에서 상세 정보 보충 (allowed_tools, capabilities 등)
            detail = _AGENTS_DETAIL.get(agent_id, {})
            return {
                **a,
                "system_prompt": detail.get("system_prompt", ""),
                "capabilities": detail.get("capabilities", []),
                "allowed_tools": detail.get("allowed_tools", []),
                "subordinate_ids": detail.get("subordinate_ids", []),
                "superior_id": detail.get("superior_id", ""),
                "temperature": detail.get("temperature", 0.3),
                "reasoning_effort": detail.get("reasoning_effort", ""),
            }
    return {"error": "not found"}


@app.get("/api/tools")
async def get_tools():
    return _TOOLS_LIST


@app.get("/api/dashboard")
async def get_dashboard():
    now = datetime.now(KST).isoformat()
    return {
        "total_agents": len(AGENTS),
        "active_agents": 0,
        "idle_agents": len(AGENTS),
        "total_tasks_today": 0,
        "system_status": "idle",
        "uptime": now,
        "agents": AGENTS,
    }


@app.get("/api/budget")
async def get_budget():
    return {
        "daily_limit": 10.0,
        "daily_used": 0.0,
        "monthly_limit": 300.0,
        "monthly_used": 0.0,
    }


@app.get("/api/quality")
async def get_quality():
    return {"average_score": 0, "total_evaluated": 0, "rules": []}


@app.get("/api/feedback")
async def get_feedback():
    return {"good": 0, "bad": 0, "total": 0}


@app.get("/api/presets")
async def get_presets():
    return []


@app.get("/api/performance")
async def get_performance():
    return {"agents": [], "summary": {}}


@app.get("/api/tasks")
async def get_tasks():
    return {"tasks": [], "total": 0}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    return {"error": "not found"}


@app.get("/api/replay/{correlation_id}")
async def get_replay(correlation_id: str):
    return {"steps": []}


@app.get("/api/replay/latest")
async def get_replay_latest():
    return {"steps": []}


@app.get("/api/schedules")
async def get_schedules():
    return []


@app.get("/api/workflows")
async def get_workflows():
    return []


@app.get("/api/knowledge")
async def get_knowledge():
    return {"entries": [], "total": 0}


@app.get("/api/knowledge/{entry_id}")
async def get_knowledge_entry(entry_id: str):
    return {"error": "not found"}


@app.get("/api/memory/{agent_id}")
async def get_memory(agent_id: str):
    return {"memories": []}


_QUALITY_RULES: dict = _load_config("quality_rules")

# 부서 ID → 한국어 이름 매핑
_DIVISION_LABELS: dict[str, str] = {
    "default": "기본 (전체 공통)",
    "secretary": "비서실",
    "leet_master.tech": "기술개발팀 (CTO)",
    "leet_master.strategy": "전략기획팀 (CSO)",
    "leet_master.legal": "법무팀 (CLO)",
    "leet_master.marketing": "마케팅팀 (CMO)",
    "finance.investment": "금융분석팀 (CIO)",
    "publishing": "콘텐츠팀 (CPO)",
}

# 부서 목록 (default 제외)
_KNOWN_DIVISIONS: list[str] = [
    "secretary",
    "leet_master.tech",
    "leet_master.strategy",
    "leet_master.legal",
    "leet_master.marketing",
    "finance.investment",
    "publishing",
]


@app.get("/api/quality-rules")
async def get_quality_rules():
    rules = _QUALITY_RULES.get("rules", {})
    rubrics = _QUALITY_RULES.get("rubrics", {})
    return {
        "rules": rules,
        "rubrics": rubrics,
        "known_divisions": _KNOWN_DIVISIONS,
        "division_labels": _DIVISION_LABELS,
    }


@app.get("/api/available-models")
async def get_available_models():
    return [
        # Anthropic (Claude) 모델들 - 임원급/매니저급
        {
            "name": "claude-opus-4-6",
            "provider": "anthropic",
            "tier": "executive",
            "cost_input": 15.0,
            "cost_output": 75.0,
        },
        {
            "name": "claude-sonnet-4-5-20250929",
            "provider": "anthropic",
            "tier": "manager",
            "cost_input": 3.0,
            "cost_output": 15.0,
        },
        {
            "name": "claude-haiku-4-5-20251001",
            "provider": "anthropic",
            "tier": "specialist",
            "cost_input": 0.25,
            "cost_output": 1.25,
        },
        # OpenAI (GPT) 모델들 - 임원급/매니저급/전문가급
        {
            "name": "gpt-5.2-pro",
            "provider": "openai",
            "tier": "executive",
            "cost_input": 18.0,
            "cost_output": 90.0,
        },
        {
            "name": "gpt-5.2",
            "provider": "openai",
            "tier": "manager",
            "cost_input": 5.0,
            "cost_output": 25.0,
        },
        {
            "name": "gpt-5.1",
            "provider": "openai",
            "tier": "manager",
            "cost_input": 4.0,
            "cost_output": 20.0,
        },
        {
            "name": "gpt-5",
            "provider": "openai",
            "tier": "specialist",
            "cost_input": 2.5,
            "cost_output": 10.0,
        },
        {
            "name": "gpt-5-mini",
            "provider": "openai",
            "tier": "specialist",
            "cost_input": 0.5,
            "cost_output": 2.0,
        },
    ]


# ── 텔레그램 봇 ──

_telegram_app = None  # telegram.ext.Application 인스턴스


async def _tg_cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — 봇 연결 확인."""
    chat_id = update.effective_chat.id
    ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")

    if not ceo_id:
        # CEO chat_id 미설정 → 안내 메시지
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


async def _tg_cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help — 사용법 안내."""
    if not _is_tg_ceo(update):
        return
    await update.message.reply_text(
        "*CORTHEX HQ 사용법*\n\n"
        "/agents — 에이전트 목록 (29명)\n"
        "/health — 서버 상태 확인\n"
        "/help — 이 사용법\n\n"
        "일반 메시지를 보내면 접수됩니다.",
        parse_mode="Markdown",
    )


async def _tg_cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/agents — 에이전트 목록."""
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
            role_icon = "👔" if a["role"] == "manager" else "👤"
            lines.append(f"  {role_icon} {a['name_ko']}")

    lines.append(f"\n총 {len(AGENTS)}명")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _tg_cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/health — 서버 상태."""
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


async def _tg_handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """일반 텍스트 메시지 처리."""
    if not _is_tg_ceo(update):
        return

    text = update.message.text.strip()
    if not text:
        return

    now = datetime.now(KST).strftime("%H:%M")
    await update.message.reply_text(
        f"접수했습니다. ({now})\n\n"
        f"현재 경량 서버 모드로, AI 에이전트 실행은 메인 서버에서 가능합니다.\n"
        f"메인 서버 구축 후 이 봇에서 직접 업무 지시가 가능해집니다.",
    )

    # 웹 대시보드에 알림 (WebSocket 연결된 클라이언트들에게)
    for ws in connected_clients[:]:
        try:
            await ws.send_json({
                "event": "activity_log",
                "data": {
                    "agent_id": "chief_of_staff",
                    "message": f"[텔레그램] CEO 지시: {text[:50]}{'...' if len(text) > 50 else ''}",
                    "level": "info",
                    "time": now,
                }
            })
        except Exception:
            pass


def _is_tg_ceo(update: Update) -> bool:
    """CEO 인증 확인."""
    if not update.effective_chat or not update.message:
        return False
    ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
    if not ceo_id:
        return False
    if str(update.effective_chat.id) != ceo_id:
        asyncio.create_task(update.message.reply_text("권한이 없습니다."))
        return False
    return True


async def _start_telegram_bot() -> None:
    """텔레그램 봇을 시작합니다 (FastAPI 이벤트 루프 안에서 실행)."""
    global _telegram_app

    if not _telegram_available:
        logger.info("python-telegram-bot 미설치 — 텔레그램 봇 건너뜀")
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.info("TELEGRAM_BOT_TOKEN 미설정 — 텔레그램 봇 건너뜀")
        return

    try:
        _telegram_app = Application.builder().token(token).build()

        # 핸들러 등록
        _telegram_app.add_handler(CommandHandler("start", _tg_cmd_start))
        _telegram_app.add_handler(CommandHandler("help", _tg_cmd_help))
        _telegram_app.add_handler(CommandHandler("agents", _tg_cmd_agents))
        _telegram_app.add_handler(CommandHandler("health", _tg_cmd_health))
        _telegram_app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, _tg_handle_message)
        )

        # 봇 명령어 메뉴 설정
        await _telegram_app.bot.set_my_commands([
            BotCommand("start", "봇 시작"),
            BotCommand("help", "사용법"),
            BotCommand("agents", "에이전트 목록"),
            BotCommand("health", "서버 상태"),
        ])

        await _telegram_app.initialize()
        await _telegram_app.start()
        await _telegram_app.updater.start_polling(drop_pending_updates=True)

        ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
        logger.info("텔레그램 봇 시작 완료 (CEO chat_id: %s)", ceo_id or "미설정")
    except Exception as e:
        logger.error("텔레그램 봇 시작 실패: %s", e)
        _telegram_app = None


async def _stop_telegram_bot() -> None:
    """텔레그램 봇을 종료합니다."""
    global _telegram_app
    if _telegram_app:
        try:
            await _telegram_app.updater.stop()
            await _telegram_app.stop()
            await _telegram_app.shutdown()
            logger.info("텔레그램 봇 종료 완료")
        except Exception as e:
            logger.warning("텔레그램 봇 종료 중 오류: %s", e)
        _telegram_app = None


@app.on_event("startup")
async def on_startup():
    """서버 시작 시 텔레그램 봇도 함께 시작."""
    await _start_telegram_bot()


@app.on_event("shutdown")
async def on_shutdown():
    """서버 종료 시 텔레그램 봇도 함께 종료."""
    await _stop_telegram_bot()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
