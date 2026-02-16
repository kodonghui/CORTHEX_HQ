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
import sys
import time
import uuid as _uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

# DB 모듈을 같은 폴더에서 임포트
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import (
    init_db, save_message, create_task, get_task as db_get_task,
    update_task, list_tasks, toggle_bookmark as db_toggle_bookmark,
    get_dashboard_stats, save_activity_log, list_activity_logs,
    save_archive, list_archives, get_archive as db_get_archive,
    save_setting, load_setting, get_today_cost,
    save_conversation_message, load_conversation_messages, clear_conversation_messages,
    delete_task as db_delete_task, bulk_delete_tasks, bulk_archive_tasks,
    set_task_tags, mark_task_read, bulk_mark_read,
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
    def select_model(t, override=None): return override or "claude-haiku-4-5-20251001"
    async def classify_task(t): return {"agent_id": "chief_of_staff", "reason": "ai_handler 미설치", "cost_usd": 0}
    def get_available_providers(): return {"anthropic": False, "google": False, "openai": False}
    def _load_tool_schemas(allowed_tools=None): return {}
    async def batch_submit(*a, **kw): return {"error": "ai_handler 미설치"}
    async def batch_check(*a, **kw): return {"error": "ai_handler 미설치"}
    async def batch_retrieve(*a, **kw): return {"error": "ai_handler 미설치"}
    async def batch_submit_grouped(*a, **kw): return [{"error": "ai_handler 미설치"}]

# Python 출력 버퍼링 비활성화 (systemd에서 로그가 바로 보이도록)
os.environ["PYTHONUNBUFFERED"] = "1"

# 진단 정보 수집용
_diag: dict = {"env_loaded": False, "env_file": "", "env_count": 0,
               "tg_import": False, "tg_import_error": "",
               "tg_token_found": False, "tg_started": False, "tg_error": ""}


def _log(msg: str) -> None:
    """디버그 로그 출력 (stdout + stderr 양쪽에 flush)."""
    print(msg, flush=True)
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def _load_env_file() -> None:
    """환경변수 파일을 직접 읽어서 os.environ에 설정."""
    env_paths = [
        Path("/home/ubuntu/corthex.env"),        # 서버 배포 환경
        Path(__file__).parent.parent / ".env.local",  # 로컬 개발 환경
        Path(__file__).parent.parent / ".env",        # 로컬 폴백
    ]
    for env_path in env_paths:
        _log(f"[ENV] 확인: {env_path} (존재: {env_path.exists()})")
        if env_path.exists():
            try:
                loaded = 0
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip()
                        if key:
                            os.environ[key] = value
                            loaded += 1
                _diag["env_loaded"] = True
                _diag["env_file"] = str(env_path)
                _diag["env_count"] = loaded
                tg = os.getenv("TELEGRAM_BOT_TOKEN", "")
                _diag["tg_token_found"] = bool(tg)
                _log(f"[ENV] ✅ {loaded}개 로드: {env_path}")
                _log(f"[ENV] TG_TOKEN: {bool(tg)} (길이:{len(tg)})")
            except Exception as e:
                _log(f"[ENV] ❌ 실패: {e}")
            break


_load_env_file()

# 프로젝트 루트를 sys.path에 추가 (src/ 모듈 임포트용)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    import yaml
except ImportError:
    yaml = None  # PyYAML 미설치 시 graceful fallback

# ── ToolPool 지연 로딩 ──
_tool_pool = None  # None=미초기화, False=실패, ToolPool인스턴스=성공

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

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
    _diag["tg_import"] = True
    _log("[TG] python-telegram-bot 임포트 성공 ✅")
except ImportError as e:
    _diag["tg_import_error"] = str(e)
    _log(f"[TG] python-telegram-bot 임포트 실패 ❌: {e}")

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

# ── 데이터 저장 디렉토리 (런타임 데이터) ──
DATA_DIR = Path(BASE_DIR).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
KNOWLEDGE_DIR = Path(BASE_DIR).parent / "knowledge"
ARCHIVE_DIR = Path(BASE_DIR).parent / "archive"


def _load_data(name: str, default=None):
    """DB에서 설정 데이터 로드. DB에 없으면 기존 JSON 파일 확인 후 자동 마이그레이션."""
    # 1순위: SQLite DB
    db_val = load_setting(name)
    if db_val is not None:
        return db_val
    # 2순위: 기존 JSON 파일 (자동 마이그레이션)
    path = DATA_DIR / f"{name}.json"
    if path.exists():
        try:
            val = json.loads(path.read_text(encoding="utf-8"))
            save_setting(name, val)  # DB로 마이그레이션
            return val
        except Exception:
            pass
    return default if default is not None else {}


def _save_data(name: str, data) -> None:
    """DB에 설정 데이터 저장."""
    save_setting(name, data)


def _save_config_file(name: str, data: dict) -> None:
    """설정 변경을 DB에 저장. (재배포해도 유지됨)"""
    save_setting(f"config_{name}", data)


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(TEMPLATE_DIR, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # BUILD_NUMBER_PLACEHOLDER를 실제 빌드 번호로 치환
    build_number = get_build_number()
    html_content = html_content.replace("BUILD_NUMBER_PLACEHOLDER", build_number)

    return HTMLResponse(content=html_content)


@app.get("/deploy-status.json")
async def deploy_status():
    """배포 상태 JSON (deploy.yml이 /var/www/html/에 생성한 파일 읽기)."""
    import json as _json
    for path in ["/var/www/html/deploy-status.json", os.path.join(BASE_DIR, "deploy-status.json")]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return _json.load(f)
            except Exception:
                pass
    return {"build": get_build_number(), "time": datetime.now(KST).isoformat(), "status": "success", "commit": ""}


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
            # 메시지를 받으면 DB에 저장 + 응답
            if msg.get("type") == "command":
                cmd_text = (msg.get("content") or msg.get("text", "")).strip()
                use_batch = msg.get("batch", False)
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
                    for c in connected_clients[:]:
                        try:
                            await c.send_json({"event": "task_accepted", "data": task})
                            await c.send_json({"event": "activity_log", "data": log_entry})
                        except Exception:
                            pass

                    # 배치 모드: 위임 체인 전체를 Batch API로 실행
                    if use_batch and is_ai_ready():
                        update_task(task["task_id"], status="pending",
                                    result_summary="📦 [배치 체인] 시작 중...")
                        # 배치 체인 시작 (분류 → 전문가 → 종합보고서 → CEO 전달)
                        chain_result = await _start_batch_chain(cmd_text, task["task_id"])
                        if "error" in chain_result:
                            await ws.send_json({
                                "event": "result",
                                "data": {
                                    "content": f"❌ 배치 체인 시작 실패: {chain_result['error']}",
                                    "sender_id": "chief_of_staff",
                                    "handled_by": "비서실장",
                                    "time_seconds": 0,
                                    "cost": 0,
                                }
                            })
                        else:
                            chain_id = chain_result.get("chain_id", "?")
                            step = chain_result.get("step", "?")
                            mode = chain_result.get("mode", "single")
                            mode_label = "브로드캐스트 (6개 부서)" if mode == "broadcast" else "단일 부서 위임"
                            await ws.send_json({
                                "event": "result",
                                "data": {
                                    "content": (
                                        f"📦 **배치 체인 시작됨**\n\n"
                                        f"- 모드: {mode_label}\n"
                                        f"- 현재 단계: {step}\n"
                                        f"- 체인 ID: `{chain_id[:30]}`\n\n"
                                        f"위임 체인 전체가 Batch API로 처리됩니다 (비용 ~50% 절감).\n"
                                        f"각 단계 완료 시 자동으로 다음 단계로 진행되며, "
                                        f"최종 보고서가 완성되면 알려드리겠습니다."
                                    ),
                                    "sender_id": "chief_of_staff",
                                    "handled_by": "비서실장",
                                    "time_seconds": 0,
                                    "cost": 0,
                                }
                            })
                        continue

                    # 실시간 모드: AI 즉시 처리
                    if is_ai_ready():
                        update_task(task["task_id"], status="running")
                        result = await _process_ai_command(cmd_text, task["task_id"])
                        if "error" in result:
                            await ws.send_json({
                                "event": "result",
                                "data": {"content": f"❌ {result['error']}", "sender_id": result.get("agent_id", "chief_of_staff"), "handled_by": result.get("handled_by", "비서실장"), "time_seconds": 0, "cost": 0}
                            })
                        else:
                            await ws.send_json({
                                "event": "result",
                                "data": {
                                    "content": result.get("content", ""),
                                    "sender_id": result.get("agent_id", "chief_of_staff"),
                                    "handled_by": result.get("handled_by", "비서실장"),
                                    "delegation": result.get("delegation", ""),
                                    "time_seconds": result.get("time_seconds", 0),
                                    "cost": result.get("total_cost_usd", result.get("cost_usd", 0)),
                                    "model": result.get("model", ""),
                                    "routing_method": result.get("routing_method", ""),
                                }
                            })
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
        connected_clients.remove(ws)
    except Exception:
        if ws in connected_clients:
            connected_clients.remove(ws)


# ── API 엔드포인트 ──

@app.get("/api/auth/status")
async def auth_status(request: Request):
    if _check_auth(request):
        return {"bootstrap_mode": False, "role": "ceo", "authenticated": True}
    # 비밀번호가 기본값이고 세션이 없으면 부트스트랩 모드
    stored_pw = load_setting("admin_password")
    if (not stored_pw or stored_pw == "corthex2026") and not _sessions:
        return {"bootstrap_mode": True, "role": "ceo", "authenticated": True}
    return {"bootstrap_mode": False, "role": "viewer", "authenticated": False}


@app.get("/api/agents")
async def get_agents():
    """에이전트 목록 반환 (오버라이드된 model_name, reasoning_effort 포함)."""
    result = []
    overrides = _load_data("agent_overrides", {})
    for a in AGENTS:
        agent = dict(a)
        aid = agent["agent_id"]
        detail = _AGENTS_DETAIL.get(aid, {})
        # 오버라이드된 모델명 반영
        if aid in overrides and "model_name" in overrides[aid]:
            agent["model_name"] = overrides[aid]["model_name"]
        elif detail.get("model_name"):
            agent["model_name"] = detail["model_name"]
        # 추론 레벨 반영
        agent["reasoning_effort"] = ""
        if aid in overrides and "reasoning_effort" in overrides[aid]:
            agent["reasoning_effort"] = overrides[aid]["reasoning_effort"]
        elif detail.get("reasoning_effort"):
            agent["reasoning_effort"] = detail["reasoning_effort"]
        result.append(agent)
    return result


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    for a in AGENTS:
        if a["agent_id"] == agent_id:
            # agents.yaml에서 상세 정보 보충 (allowed_tools, capabilities 등)
            detail = _AGENTS_DETAIL.get(agent_id, {})
            # 소울 로드 우선순위: 1) DB 오버라이드 → 2) souls/*.md 파일 → 3) agents.yaml
            soul_override = load_setting(f"soul_{agent_id}")
            if soul_override is not None:
                system_prompt = soul_override
            else:
                # souls/agents/{agent_id}.md 파일에서 소울 로드
                soul_md = Path(BASE_DIR).parent / "souls" / "agents" / f"{agent_id}.md"
                if soul_md.exists():
                    try:
                        system_prompt = soul_md.read_text(encoding="utf-8")
                    except Exception:
                        system_prompt = detail.get("system_prompt", "")
                else:
                    system_prompt = detail.get("system_prompt", "")
            return {
                **a,
                "system_prompt": system_prompt,
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
    stats = get_dashboard_stats()
    return {
        "total_agents": len(AGENTS),
        "active_agents": stats["running_count"],
        "idle_agents": len(AGENTS) - stats["running_count"],
        "total_tasks_today": stats["today_task_count"],
        "today_completed": stats["today_completed"],
        "today_failed": stats["today_failed"],
        "total_cost": stats["total_cost"],
        "total_tokens": stats["total_tokens"],
        "system_status": "busy" if stats["running_count"] > 0 else "idle",
        "uptime": now,
        "agents": AGENTS,
        "recent_completed": stats["recent_completed"],
        # API 키 연결 상태 — 프로바이더별 클라이언트 확인
        "api_keys": {
            "anthropic": get_available_providers().get("anthropic", False),
            "google": get_available_providers().get("google", False),
            "openai": get_available_providers().get("openai", False),
            "notion": bool(os.getenv("NOTION_API_KEY", "")),
            "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN", "")),
        },
    }


@app.get("/api/budget")
async def get_budget():
    limit = float(load_setting("daily_budget_usd") or 7.0)
    today = get_today_cost()
    return {
        "daily_limit": limit, "daily_used": today,
        "today_cost": today,
        "remaining": round(limit - today, 6),
        "exceeded": today >= limit,
        "monthly_limit": 300.0, "monthly_used": today,
    }


@app.get("/api/model-mode")
async def get_model_mode():
    """현재 모델 모드 조회 (auto/manual)."""
    mode = load_setting("model_mode") or "auto"
    override = load_setting("model_override") or "claude-sonnet-4-5-20250929"
    return {"mode": mode, "override": override}


@app.put("/api/model-mode")
async def set_model_mode(request: Request):
    """모델 모드 변경."""
    body = await request.json()
    mode = body.get("mode", "auto")
    save_setting("model_mode", mode)
    if mode == "manual" and "override" in body:
        save_setting("model_override", body["override"])
    return {"success": True, "mode": mode}


@app.get("/api/quality")
async def get_quality():
    return {"average_score": 0, "total_evaluated": 0, "rules": []}


# ── 프리셋 관리 ──

@app.get("/api/presets")
async def get_presets():
    return _load_data("presets", [])


@app.post("/api/presets")
async def save_preset(request: Request):
    """프리셋 저장."""
    body = await request.json()
    presets = _load_data("presets", [])
    name = body.get("name", "")
    # 같은 이름이 있으면 덮어쓰기
    presets = [p for p in presets if p.get("name") != name]
    presets.append(body)
    _save_data("presets", presets)
    return {"success": True}


@app.delete("/api/presets/{name}")
async def delete_preset(name: str):
    """프리셋 삭제."""
    presets = _load_data("presets", [])
    presets = [p for p in presets if p.get("name") != name]
    _save_data("presets", presets)
    return {"success": True}


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
        }
    finally:
        conn.close()


@app.get("/api/tasks")
async def get_tasks(keyword: str = "", status: str = "", bookmarked: bool = False,
                    limit: int = 50, archived: bool = False, tag: str = ""):
    tasks = list_tasks(keyword=keyword, status=status,
                       bookmarked=bookmarked, limit=limit,
                       archived=archived, tag=tag)
    return tasks


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    task = db_get_task(task_id)
    if not task:
        return {"error": "not found"}
    return task


@app.post("/api/tasks/{task_id}/bookmark")
async def bookmark_task(task_id: str):
    new_state = db_toggle_bookmark(task_id)
    return {"bookmarked": new_state}


@app.delete("/api/tasks/{task_id}")
async def delete_task_api(task_id: str):
    """작업 삭제."""
    db_delete_task(task_id)
    return {"success": True}


@app.put("/api/tasks/{task_id}/tags")
async def update_task_tags(task_id: str, request: Request):
    """작업 태그 업데이트."""
    body = await request.json()
    tags = body.get("tags", [])
    set_task_tags(task_id, tags)
    return {"success": True, "tags": tags}


@app.put("/api/tasks/{task_id}/read")
async def mark_task_read_api(task_id: str, request: Request):
    """작업 읽음/안읽음 표시."""
    body = await request.json()
    is_read = body.get("is_read", True)
    mark_task_read(task_id, is_read)
    return {"success": True, "is_read": is_read}


@app.post("/api/tasks/bulk")
async def bulk_task_action(request: Request):
    """작업 일괄 처리 (삭제/아카이브/읽음 등)."""
    body = await request.json()
    action = body.get("action", "")
    task_ids = body.get("task_ids", [])
    if not task_ids:
        return {"success": False, "error": "task_ids가 비어있습니다"}

    if action == "delete":
        count = bulk_delete_tasks(task_ids)
        return {"success": True, "action": "delete", "affected": count}
    elif action == "archive":
        count = bulk_archive_tasks(task_ids, archive=True)
        return {"success": True, "action": "archive", "affected": count}
    elif action == "unarchive":
        count = bulk_archive_tasks(task_ids, archive=False)
        return {"success": True, "action": "unarchive", "affected": count}
    elif action == "read":
        count = bulk_mark_read(task_ids, is_read=True)
        return {"success": True, "action": "read", "affected": count}
    elif action == "unread":
        count = bulk_mark_read(task_ids, is_read=False)
        return {"success": True, "action": "unread", "affected": count}
    else:
        return {"success": False, "error": f"알 수 없는 액션: {action}"}


# ── 배치 명령 (여러 명령 한번에 실행) ──

_batch_queue: list[dict] = []  # 배치 대기열 (로컬 순차/병렬 실행용)
_batch_running = False
_batch_api_queue: list[dict] = []  # Batch API 대기열 (프로바이더 배치 제출용)


@app.get("/api/batch/queue")
async def get_batch_queue():
    """배치 대기열 조회."""
    return {"queue": _batch_queue, "running": _batch_running}


@app.post("/api/batch")
async def submit_batch(request: Request):
    """배치 명령 제출 — 여러 명령을 한번에 접수합니다."""
    body = await request.json()
    commands = body.get("commands", [])
    mode = body.get("mode", "sequential")  # sequential 또는 parallel

    if not commands:
        return {"success": False, "error": "명령 목록이 비어있습니다"}

    batch_id = f"batch_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}"
    batch_items = []
    for i, cmd in enumerate(commands):
        item = {
            "batch_id": batch_id,
            "index": i,
            "command": cmd if isinstance(cmd, str) else cmd.get("command", ""),
            "status": "pending",
            "result": None,
            "task_id": None,
        }
        batch_items.append(item)
        _batch_queue.append(item)

    # 백그라운드에서 배치 실행
    asyncio.create_task(_run_batch(batch_id, batch_items, mode))

    return {"success": True, "batch_id": batch_id, "count": len(commands), "mode": mode}


async def _run_batch(batch_id: str, items: list, mode: str):
    """배치 명령을 실행합니다."""
    global _batch_running
    _batch_running = True

    try:
        if mode == "parallel":
            # 병렬 실행
            tasks = []
            for item in items:
                tasks.append(_run_batch_item(item))
            await asyncio.gather(*tasks)
        else:
            # 순차 실행
            for item in items:
                await _run_batch_item(item)
    finally:
        _batch_running = False
        # 완료된 배치 항목은 10분 후 정리
        await asyncio.sleep(600)
        for item in items:
            if item in _batch_queue:
                _batch_queue.remove(item)


async def _run_batch_item(item: dict):
    """배치 내 개별 명령을 실행합니다."""
    item["status"] = "running"
    try:
        task = create_task(item["command"], source="batch")
        item["task_id"] = task["task_id"]

        # AI 처리 (_process_ai_command과 동일한 로직)
        result = await _process_ai_command(item["command"], source="batch")

        item["status"] = "completed"
        item["result"] = result.get("content", "")[:200] if isinstance(result, dict) else str(result)[:200]
    except Exception as e:
        item["status"] = "failed"
        item["result"] = str(e)[:200]


@app.delete("/api/batch/queue")
async def clear_batch_queue():
    """배치 대기열을 비웁니다."""
    global _batch_queue
    _batch_queue = [item for item in _batch_queue if item.get("status") == "running"]
    return {"success": True}


# ══════════════════════════════════════════════════════════════
# ── AI Batch API 시스템 (PENDING 추적 + 자동 결과 수집) ──
# ══════════════════════════════════════════════════════════════
#
# CEO가 여러 명령을 AI Batch API로 보내면:
#   1) 각 명령이 PENDING 상태로 DB에 저장됨
#   2) 프로바이더의 Batch API에 한꺼번에 제출 (실시간보다 ~50% 저렴)
#   3) 백그라운드 폴러가 60초마다 상태를 확인
#   4) 완료되면 자동으로 결과를 수집하고, 에이전트에게 위임하여 보고서 작성
#   5) WebSocket으로 CEO에게 실시간 알림

_batch_poller_task = None  # 배치 폴러 루프 태스크


@app.post("/api/batch/ai")
async def submit_ai_batch(request: Request):
    """AI Batch API로 여러 요청을 한꺼번에 제출합니다.

    요청 body:
    {
        "requests": [
            {"message": "삼성전자 분석해줘", "system_prompt": "...", "agent_id": "cio_manager"},
            {"message": "특허 검색해줘", "system_prompt": "...", "agent_id": "clo_manager"},
        ],
        "model": "claude-sonnet-4-5-20250929",  // 기본 모델 (선택)
        "auto_delegate": true  // 결과를 에이전트에게 자동 위임할지 (기본: true)
    }

    응답: {"batch_id": "...", "count": N, "status": "submitted"}
    """
    body = await request.json()
    requests_list = body.get("requests", [])
    model = body.get("model")
    auto_delegate = body.get("auto_delegate", True)

    if not requests_list:
        return {"success": False, "error": "요청 목록이 비어있습니다"}

    # 각 요청에 custom_id 자동 부여
    now_str = datetime.now(KST).strftime('%Y%m%d_%H%M%S')
    for i, req in enumerate(requests_list):
        if "custom_id" not in req:
            req["custom_id"] = f"batch_{now_str}_{i}"
        # 에이전트 소울(시스템 프롬프트)을 자동으로 로드
        agent_id = req.get("agent_id")
        if agent_id and not req.get("system_prompt"):
            req["system_prompt"] = _load_agent_prompt(agent_id)

    # Batch API 제출
    result = await batch_submit(requests_list, model=model)

    if "error" in result:
        return {"success": False, "error": result["error"]}

    batch_id = result["batch_id"]
    provider = result["provider"]

    # DB에 PENDING 상태로 저장
    pending_data = {
        "batch_id": batch_id,
        "provider": provider,
        "model": model,
        "status": "pending",
        "auto_delegate": auto_delegate,
        "submitted_at": datetime.now(KST).isoformat(),
        "requests": [
            {
                "custom_id": r.get("custom_id"),
                "message": r.get("message", "")[:200],
                "agent_id": r.get("agent_id", ""),
            }
            for r in requests_list
        ],
        "results": [],
    }

    # 기존 pending_batches 목록에 추가
    pending_batches = load_setting("pending_batches") or []
    pending_batches.append(pending_data)
    save_setting("pending_batches", pending_batches)

    # 각 요청을 task로도 생성 (PENDING 상태)
    for req in requests_list:
        task = create_task(
            req.get("message", "배치 요청"),
            source="batch_api",
            agent_id=req.get("agent_id", "chief_of_staff"),
        )
        update_task(task["task_id"], status="pending",
                    result_summary=f"[PENDING] 배치 처리 중 (batch_id: {batch_id[:20]}...)")

    # WebSocket 알림
    for c in connected_clients[:]:
        try:
            await c.send_json({
                "event": "batch_submitted",
                "data": {
                    "batch_id": batch_id,
                    "provider": provider,
                    "count": len(requests_list),
                },
            })
        except Exception:
            pass

    _log(f"[BATCH] AI 배치 제출 완료: {batch_id} ({len(requests_list)}개 요청, {provider})")

    # 폴러가 안 돌고 있으면 시작
    _ensure_batch_poller()

    return {
        "success": True,
        "batch_id": batch_id,
        "provider": provider,
        "count": len(requests_list),
        "status": "submitted",
    }


@app.get("/api/batch/pending")
async def get_pending_batches():
    """PENDING 상태인 배치 목록을 조회합니다."""
    pending_batches = load_setting("pending_batches") or []
    # pending과 processing만 반환
    active = [b for b in pending_batches if b.get("status") in ("pending", "processing")]
    return {"pending": active, "total": len(pending_batches)}


@app.post("/api/batch/check/{batch_id}")
async def check_batch_status(batch_id: str):
    """특정 배치의 상태를 수동으로 확인합니다."""
    pending_batches = load_setting("pending_batches") or []
    batch_info = next((b for b in pending_batches if b["batch_id"] == batch_id), None)

    if not batch_info:
        return {"error": f"배치 '{batch_id}'를 찾을 수 없습니다"}

    provider = batch_info["provider"]
    status_result = await batch_check(batch_id, provider)

    if "error" in status_result:
        return status_result

    # 상태 업데이트
    batch_info["status"] = status_result["status"]
    batch_info["progress"] = status_result.get("progress", {})
    save_setting("pending_batches", pending_batches)

    # 완료되었으면 결과 수집
    if status_result["status"] == "completed":
        await _collect_batch_results(batch_info, pending_batches)

    return status_result


@app.post("/api/batch/resume")
async def resume_all_pending():
    """모든 PENDING 배치의 상태를 확인하고, 완료된 것은 결과를 수집합니다."""
    pending_batches = load_setting("pending_batches") or []
    active = [b for b in pending_batches if b.get("status") in ("pending", "processing")]

    if not active:
        return {"message": "처리 중인 배치가 없습니다", "checked": 0}

    checked = 0
    collected = 0
    for batch_info in active:
        batch_id = batch_info["batch_id"]
        provider = batch_info["provider"]

        status_result = await batch_check(batch_id, provider)
        if "error" not in status_result:
            batch_info["status"] = status_result["status"]
            batch_info["progress"] = status_result.get("progress", {})
            checked += 1

            if status_result["status"] == "completed":
                await _collect_batch_results(batch_info, pending_batches)
                collected += 1

    save_setting("pending_batches", pending_batches)
    return {"checked": checked, "collected": collected, "remaining": len(active) - collected}


@app.get("/api/batch/history")
async def get_batch_history():
    """모든 배치의 히스토리를 조회합니다 (완료된 것 포함)."""
    all_batches = load_setting("pending_batches") or []
    return {"batches": all_batches[-50:], "total": len(all_batches)}  # 최근 50개만


async def _collect_batch_results(batch_info: dict, all_batches: list):
    """완료된 배치의 결과를 수집하고, 필요시 에이전트에게 위임합니다."""
    batch_id = batch_info["batch_id"]
    provider = batch_info["provider"]

    _log(f"[BATCH] 결과 수집 시작: {batch_id}")

    # 결과 가져오기
    result = await batch_retrieve(batch_id, provider)
    if "error" in result:
        _log(f"[BATCH] 결과 수집 실패: {result['error']}")
        return

    results = result.get("results", [])
    batch_info["results"] = results
    batch_info["status"] = "completed"
    batch_info["completed_at"] = datetime.now(KST).isoformat()

    # 총 비용 계산
    total_cost = sum(r.get("cost_usd", 0) for r in results if r.get("cost_usd"))
    batch_info["total_cost_usd"] = round(total_cost, 6)

    save_setting("pending_batches", all_batches)

    # 에이전트에게 자동 위임 (auto_delegate=true인 경우)
    if batch_info.get("auto_delegate"):
        req_map = {r["custom_id"]: r for r in batch_info.get("requests", [])}
        for res in results:
            if res.get("error"):
                continue
            custom_id = res.get("custom_id", "")
            req_info = req_map.get(custom_id, {})
            agent_id = req_info.get("agent_id")
            message = req_info.get("message", "")

            if agent_id and res.get("content"):
                # 결과를 활동 로그에 기록
                agent_name = _AGENT_NAMES.get(agent_id, agent_id)
                log_entry = save_activity_log(
                    agent_id,
                    f"[배치 완료] {agent_name}: {message[:40]}... → {res['content'][:60]}..."
                )
                for c in connected_clients[:]:
                    try:
                        await c.send_json({"event": "activity_log", "data": log_entry})
                    except Exception:
                        pass

                # 아카이브에 저장
                division = _AGENT_DIVISION.get(agent_id, "secretary")
                now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
                archive_content = f"# [배치] [{agent_name}] {message[:60]}\n\n{res['content']}"
                save_archive(
                    division=division,
                    filename=f"batch_{agent_id}_{now_str}.md",
                    content=archive_content,
                    agent_id=agent_id,
                )

    # WebSocket으로 완료 알림
    for c in connected_clients[:]:
        try:
            await c.send_json({
                "event": "batch_completed",
                "data": {
                    "batch_id": batch_id,
                    "provider": provider,
                    "count": len(results),
                    "total_cost_usd": total_cost,
                    "succeeded": sum(1 for r in results if not r.get("error")),
                    "failed": sum(1 for r in results if r.get("error")),
                },
            })
        except Exception:
            pass

    _log(f"[BATCH] 결과 수집 완료: {batch_id} ({len(results)}개, ${total_cost:.4f})")


async def _flush_batch_api_queue():
    """배치 대기열에 쌓인 요청을 Batch API에 제출합니다."""
    global _batch_api_queue
    if not _batch_api_queue:
        return {"message": "대기열이 비어있습니다"}

    queue_copy = list(_batch_api_queue)
    _batch_api_queue = []

    _log(f"[BATCH] 대기열 {len(queue_copy)}건 → Batch API 제출 중...")

    # 각 요청에 에이전트 라우팅 (시스템 프롬프트 결정)
    for req in queue_copy:
        if not req.get("system_prompt"):
            routing = await _route_task(req.get("message", ""))
            agent_id = routing.get("agent_id", "chief_of_staff")
            req["agent_id"] = agent_id
            req["system_prompt"] = _load_agent_prompt(agent_id)

    # Batch API 제출
    result = await batch_submit(queue_copy)

    if "error" in result:
        _log(f"[BATCH] 제출 실패: {result['error']}")
        # 실패하면 다시 대기열에 넣기
        _batch_api_queue.extend(queue_copy)
        return result

    batch_id = result["batch_id"]
    provider = result["provider"]

    # DB에 PENDING 상태로 저장
    pending_data = {
        "batch_id": batch_id,
        "provider": provider,
        "status": "pending",
        "auto_delegate": True,
        "submitted_at": datetime.now(KST).isoformat(),
        "requests": [
            {
                "custom_id": r.get("custom_id", r.get("task_id", "")),
                "message": r.get("message", "")[:200],
                "agent_id": r.get("agent_id", ""),
                "task_id": r.get("task_id", ""),
            }
            for r in queue_copy
        ],
        "results": [],
    }

    pending_batches = load_setting("pending_batches") or []
    pending_batches.append(pending_data)
    save_setting("pending_batches", pending_batches)

    # 각 task를 PENDING 상태로 업데이트
    for req in queue_copy:
        task_id = req.get("task_id")
        if task_id:
            update_task(task_id, status="pending",
                        result_summary=f"[PENDING] Batch API 제출됨 ({batch_id[:20]}...)")

    # WebSocket 알림
    for c in connected_clients[:]:
        try:
            await c.send_json({
                "event": "batch_submitted",
                "data": {"batch_id": batch_id, "provider": provider, "count": len(queue_copy)},
            })
        except Exception:
            pass

    _ensure_batch_poller()
    _log(f"[BATCH] Batch API 제출 완료: {batch_id} ({len(queue_copy)}건, {provider})")
    return result


@app.post("/api/batch/flush")
async def flush_batch_queue():
    """배치 대기열에 쌓인 요청을 즉시 Batch API에 제출합니다."""
    if not _batch_api_queue:
        return {"success": False, "message": "대기열이 비어있습니다"}
    result = await _flush_batch_api_queue()
    return {"success": "error" not in result, **result}


def _ensure_batch_poller():
    """배치 폴러가 돌고 있는지 확인하고, 안 돌면 시작합니다."""
    global _batch_poller_task
    if _batch_poller_task is None or _batch_poller_task.done():
        _batch_poller_task = asyncio.create_task(_batch_poller_loop())
        _log("[BATCH] 배치 폴러 시작됨 (60초 간격)")


async def _batch_poller_loop():
    """백그라운드에서 60초마다 PENDING 배치 + 배치 체인을 확인합니다."""
    while True:
        try:
            await asyncio.sleep(60)

            has_work = False

            # ── (A) 기존 단독 배치 확인 ──
            pending_batches = load_setting("pending_batches") or []
            active = [b for b in pending_batches if b.get("status") in ("pending", "processing")]

            if active:
                has_work = True
                for batch_info in active:
                    batch_id = batch_info["batch_id"]
                    provider = batch_info["provider"]

                    try:
                        status_result = await batch_check(batch_id, provider)
                        if "error" not in status_result:
                            batch_info["status"] = status_result["status"]
                            batch_info["progress"] = status_result.get("progress", {})

                            if status_result["status"] == "completed":
                                await _collect_batch_results(batch_info, pending_batches)
                            elif status_result["status"] in ("failed", "expired"):
                                batch_info["status"] = status_result["status"]
                                _log(f"[BATCH] 배치 실패/만료: {batch_id}")
                    except Exception as e:
                        _log(f"[BATCH] 배치 확인 실패 ({batch_id}): {e}")

                save_setting("pending_batches", pending_batches)

            # ── (B) 배치 체인 확인 + 자동 진행 ──
            chains = load_setting("batch_chains") or []
            active_chains = [c for c in chains if c.get("status") in ("running", "pending")]

            if active_chains:
                has_work = True
                for chain in active_chains:
                    try:
                        await _advance_batch_chain(chain["chain_id"])
                    except Exception as e:
                        _log(f"[CHAIN] 체인 진행 오류 ({chain['chain_id']}): {e}")

            if not has_work:
                _log("[BATCH] 처리 중인 배치/체인 없음 — 폴러 종료")
                break

        except asyncio.CancelledError:
            break
        except Exception as e:
            _log(f"[BATCH] 폴러 오류: {e}")
            await asyncio.sleep(30)  # 에러 시 30초 대기 후 재시도


# ══════════════════════════════════════════════════════════════
# ── 배치 체인 오케스트레이터 ──
# ══════════════════════════════════════════════════════════════
#
# CEO가 📦 배치 모드로 명령을 보내면 위임 체인 전체가 Batch API로 돌아감:
#
#   [1단계] 비서실장 분류 → Batch 제출 → PENDING → 결과: "CIO에게 위임"
#   [2단계] 전문가 N명 → 프로바이더별 묶어서 Batch 제출 → PENDING → 전부 대기
#   [3단계] 처장 종합보고서 → Batch 제출 → PENDING → 결과: 종합 보고서
#   [4단계] CEO에게 전달 + 아카이브 저장
#
# 매 단계마다 Batch API 사용 → 비용 ~50% 절감
# 프로바이더별 자동 그룹화 (Claude + GPT + Gemini 에이전트 혼합 가능)

# 분류용 시스템 프롬프트 (배치 체인에서 사용)
_BATCH_CLASSIFY_PROMPT = """당신은 업무 분류 전문가입니다.
CEO의 명령을 읽고 어느 부서가 처리해야 하는지 판단하세요.

## 부서 목록
- cto_manager: 기술개발 (코드, 웹사이트, API, 서버, 배포, 프론트엔드, 백엔드, 버그, UI, 디자인, 데이터베이스)
- cso_manager: 사업기획 (시장조사, 사업계획, 매출 예측, 비즈니스모델, 수익, 경쟁사)
- clo_manager: 법무IP (저작권, 특허, 상표, 약관, 계약, 법률, 소송)
- cmo_manager: 마케팅고객 (마케팅, 광고, SNS, 인스타그램, 유튜브, 콘텐츠, 브랜딩, 설문)
- cio_manager: 투자분석 (주식, 투자, 종목, 시황, 포트폴리오, 코스피, 나스닥, 차트, 금리)
- cpo_manager: 출판기록 (회사기록, 연대기, 블로그, 출판, 편집, 회고, 빌딩로그)
- chief_of_staff: 일반 질문, 요약, 일정 관리, 기타 (위 부서에 해당하지 않는 경우)

## 출력 형식
반드시 아래 JSON 형식으로만 답하세요. 다른 텍스트는 쓰지 마세요.
{"agent_id": "부서ID", "reason": "한줄 이유"}"""


def _save_chain(chain: dict):
    """배치 체인 상태를 DB에 저장합니다."""
    chains = load_setting("batch_chains") or []
    # 같은 chain_id가 있으면 업데이트, 없으면 추가
    found = False
    for i, c in enumerate(chains):
        if c["chain_id"] == chain["chain_id"]:
            chains[i] = chain
            found = True
            break
    if not found:
        chains.append(chain)
    # 최근 50개만 유지 (오래된 완료/실패 체인 정리)
    if len(chains) > 50:
        active = [c for c in chains if c.get("status") in ("running", "pending")]
        done = [c for c in chains if c.get("status") not in ("running", "pending")]
        chains = active + done[-20:]
    save_setting("batch_chains", chains)


def _load_chain(chain_id: str) -> dict | None:
    """DB에서 배치 체인 상태를 로드합니다."""
    chains = load_setting("batch_chains") or []
    for c in chains:
        if c["chain_id"] == chain_id:
            return c
    return None


async def _broadcast_chain_status(chain: dict, message: str):
    """배치 체인 진행 상황을 WebSocket으로 CEO에게 알립니다."""
    step_labels = {
        "classify": "1단계: 분류",
        "specialists": "2단계: 전문가 분석",
        "synthesis": "3단계: 종합 보고서",
        "completed": "완료",
        "failed": "실패",
        "direct": "비서실장 직접 처리",
    }
    step_label = step_labels.get(chain.get("step", ""), chain.get("step", ""))
    for c in connected_clients[:]:
        try:
            await c.send_json({
                "event": "batch_chain_progress",
                "data": {
                    "chain_id": chain["chain_id"],
                    "step": chain.get("step", ""),
                    "step_label": step_label,
                    "status": chain.get("status", ""),
                    "message": message,
                    "mode": chain.get("mode", "single"),
                    "target_id": chain.get("target_id"),
                },
            })
        except Exception:
            pass


async def _start_batch_chain(text: str, task_id: str) -> dict:
    """배치 체인을 시작합니다.

    CEO 명령을 받아서 위임 체인 전체를 Batch API로 처리합니다.
    키워드 매칭이 되면 분류 단계를 건너뛰고 바로 전문가 단계로 진행합니다.
    """
    chain_id = f"chain_{datetime.now(KST).strftime('%Y%m%d_%H%M%S')}_{task_id[:8]}"

    chain = {
        "chain_id": chain_id,
        "task_id": task_id,
        "text": text,
        "mode": "broadcast" if _is_broadcast_command(text) else "single",
        "step": "classify",
        "status": "running",
        "target_id": None,
        "batches": {"classify": None, "specialists": [], "synthesis": []},
        "results": {"classify": None, "specialists": {}, "synthesis": {}},
        "custom_id_map": {},  # custom_id → {"agent_id", "step"} 역매핑
        "total_cost_usd": 0.0,
        "created_at": datetime.now(KST).isoformat(),
        "completed_at": None,
    }

    # 예산 확인
    limit = float(load_setting("daily_budget_usd") or 7.0)
    today = get_today_cost()
    if today >= limit:
        update_task(task_id, status="failed",
                    result_summary=f"일일 예산 초과 (${today:.2f}/${limit:.0f})",
                    success=0)
        return {"error": f"일일 예산을 초과했습니다 (${today:.2f}/${limit:.0f})"}

    # ── 브로드캐스트 모드 → 분류 건너뛰고 바로 전 부서 전문가 ──
    if chain["mode"] == "broadcast":
        chain["step"] = "specialists"
        chain["target_id"] = "broadcast"
        _save_chain(chain)

        await _broadcast_chain_status(chain, "📦 배치 체인 시작 (브로드캐스트: 6개 부서)")
        await _chain_submit_specialists_broadcast(chain)
        return {"chain_id": chain_id, "status": "started", "mode": "broadcast"}

    # ── 키워드 분류 시도 (무료, 즉시) ──
    keyword_match = _classify_by_keywords(text)
    if keyword_match:
        chain["target_id"] = keyword_match
        chain["results"]["classify"] = {
            "agent_id": keyword_match,
            "method": "키워드",
            "cost_usd": 0,
        }

        if keyword_match == "chief_of_staff":
            # 비서실장 직접 처리 → 바로 종합(=직접 답변) 단계
            chain["step"] = "synthesis"
            _save_chain(chain)
            await _broadcast_chain_status(chain, "📦 키워드 분류 → 비서실장 직접 처리")
            await _chain_submit_synthesis(chain)
        else:
            # 처장 부서로 위임 → 전문가 호출 단계
            chain["step"] = "specialists"
            _save_chain(chain)
            target_name = _AGENT_NAMES.get(keyword_match, keyword_match)
            await _broadcast_chain_status(chain, f"📦 키워드 분류 → {target_name}에게 위임")
            await _chain_submit_specialists(chain)

        return {"chain_id": chain_id, "status": "started", "step": chain["step"]}

    # ── AI 분류가 필요 → Batch API로 분류 요청 제출 ──
    # 가장 저렴한 사용 가능 모델 선택
    providers = get_available_providers()
    if providers.get("anthropic"):
        classify_model = "claude-haiku-4-5-20251001"
    elif providers.get("google"):
        classify_model = "gemini-2.5-flash"
    elif providers.get("openai"):
        classify_model = "gpt-5-mini"
    else:
        # AI 없음 → 비서실장 직접
        chain["target_id"] = "chief_of_staff"
        chain["step"] = "synthesis"
        chain["results"]["classify"] = {"agent_id": "chief_of_staff", "method": "폴백"}
        _save_chain(chain)
        await _chain_submit_synthesis(chain)
        return {"chain_id": chain_id, "status": "started", "step": "synthesis"}

    classify_custom_id = f"{chain_id}_classify"
    classify_req = {
        "custom_id": classify_custom_id,
        "message": text,
        "system_prompt": _BATCH_CLASSIFY_PROMPT,
        "model": classify_model,
    }

    result = await batch_submit([classify_req], model=classify_model)

    if "error" in result:
        # 배치 실패 → 폴백으로 비서실장 직접 처리
        _log(f"[CHAIN] 분류 배치 실패: {result['error']} → 비서실장 폴백")
        chain["target_id"] = "chief_of_staff"
        chain["step"] = "synthesis"
        chain["results"]["classify"] = {"agent_id": "chief_of_staff", "method": "폴백", "error": result["error"]}
        _save_chain(chain)
        await _chain_submit_synthesis(chain)
        return {"chain_id": chain_id, "status": "started", "step": "synthesis"}

    chain["batches"]["classify"] = {
        "batch_id": result["batch_id"],
        "provider": result["provider"],
        "status": "pending",
    }
    chain["status"] = "pending"
    chain["custom_id_map"][classify_custom_id] = {"agent_id": "classify", "step": "classify"}
    _save_chain(chain)

    _ensure_batch_poller()
    update_task(task_id, status="pending",
                result_summary="📦 [배치 체인] 1단계: 분류 요청 제출됨")
    await _broadcast_chain_status(chain, "📦 배치 체인 시작 — 1단계: 분류 요청 제출됨")

    _log(f"[CHAIN] 시작: {chain_id} — 분류 배치 제출 (batch_id: {result['batch_id']})")
    return {"chain_id": chain_id, "status": "pending", "step": "classify"}


async def _chain_submit_specialists(chain: dict):
    """배치 체인 — 단일 부서의 전문가들에게 배치 제출합니다."""
    target_id = chain["target_id"]
    text = chain["text"]
    specialists = _MANAGER_SPECIALISTS.get(target_id, [])

    if not specialists:
        # 전문가 없음 → 바로 종합(처장 직접 처리) 단계
        chain["step"] = "synthesis"
        _save_chain(chain)
        await _chain_submit_synthesis(chain)
        return

    requests = []
    for spec_id in specialists:
        soul = _load_agent_prompt(spec_id)
        override = _get_model_override(spec_id)
        model = select_model(text, override=override)
        custom_id = f"{chain['chain_id']}_spec_{spec_id}"

        requests.append({
            "custom_id": custom_id,
            "message": text,
            "system_prompt": soul,
            "model": model,
        })
        chain["custom_id_map"][custom_id] = {"agent_id": spec_id, "step": "specialists"}

    # 프로바이더별 그룹화하여 배치 제출
    batch_results = await batch_submit_grouped(requests)

    chain["batches"]["specialists"] = []
    for br in batch_results:
        chain["batches"]["specialists"].append({
            "batch_id": br.get("batch_id", ""),
            "provider": br.get("provider", ""),
            "status": "pending" if "error" not in br else "failed",
            "custom_ids": br.get("custom_ids", []),
            "error": br.get("error"),
        })

    chain["status"] = "pending"
    _save_chain(chain)

    _ensure_batch_poller()
    spec_count = len(specialists)
    provider_count = len(batch_results)
    target_name = _AGENT_NAMES.get(target_id, target_id)
    update_task(chain["task_id"], status="pending",
                result_summary=f"📦 [배치 체인] 2단계: {target_name} 전문가 {spec_count}명 배치 제출 ({provider_count}개 프로바이더)")
    await _broadcast_chain_status(chain, f"📦 2단계: {target_name} 전문가 {spec_count}명 → {provider_count}개 프로바이더별 배치 제출")

    _log(f"[CHAIN] {chain['chain_id']} — 전문가 {spec_count}명 배치 제출 ({provider_count}개 프로바이더)")


async def _chain_submit_specialists_broadcast(chain: dict):
    """배치 체인 — 브로드캐스트: 6개 부서 전체 전문가에게 배치 제출합니다."""
    text = chain["text"]
    all_managers = ["cto_manager", "cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]

    requests = []
    for mgr_id in all_managers:
        specialists = _MANAGER_SPECIALISTS.get(mgr_id, [])
        for spec_id in specialists:
            soul = _load_agent_prompt(spec_id)
            override = _get_model_override(spec_id)
            model = select_model(text, override=override)
            custom_id = f"{chain['chain_id']}_spec_{spec_id}"

            requests.append({
                "custom_id": custom_id,
                "message": text,
                "system_prompt": soul,
                "model": model,
            })
            chain["custom_id_map"][custom_id] = {"agent_id": spec_id, "step": "specialists"}

    if not requests:
        chain["step"] = "synthesis"
        _save_chain(chain)
        await _chain_submit_synthesis(chain)
        return

    # 프로바이더별 그룹화하여 배치 제출
    batch_results = await batch_submit_grouped(requests)

    chain["batches"]["specialists"] = []
    for br in batch_results:
        chain["batches"]["specialists"].append({
            "batch_id": br.get("batch_id", ""),
            "provider": br.get("provider", ""),
            "status": "pending" if "error" not in br else "failed",
            "custom_ids": br.get("custom_ids", []),
            "error": br.get("error"),
        })

    chain["status"] = "pending"
    _save_chain(chain)

    _ensure_batch_poller()
    spec_count = len(requests)
    provider_count = len(batch_results)
    update_task(chain["task_id"], status="pending",
                result_summary=f"📦 [배치 체인] 2단계: 전체 {spec_count}명 전문가 배치 제출 ({provider_count}개 프로바이더)")
    await _broadcast_chain_status(chain, f"📦 2단계: 6개 부서 전문가 {spec_count}명 → {provider_count}개 프로바이더별 배치 제출")

    _log(f"[CHAIN] {chain['chain_id']} — 브로드캐스트 전문가 {spec_count}명 배치 제출")


async def _chain_submit_synthesis(chain: dict):
    """배치 체인 — 처장(들)이 전문가 결과를 종합하는 배치를 제출합니다."""
    text = chain["text"]

    requests = []

    if chain["mode"] == "broadcast":
        # 브로드캐스트: 6개 처장이 각각 자기 팀 결과를 종합
        all_managers = ["cto_manager", "cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]
        for mgr_id in all_managers:
            specialists = _MANAGER_SPECIALISTS.get(mgr_id, [])
            spec_parts = []
            for s_id in specialists:
                s_res = chain["results"]["specialists"].get(s_id, {})
                name = _SPECIALIST_NAMES.get(s_id, s_id)
                content = s_res.get("content", "응답 없음")
                if s_res.get("error"):
                    content = f"오류: {s_res['error'][:100]}"
                spec_parts.append(f"[{name}]\n{content}")

            mgr_name = _AGENT_NAMES.get(mgr_id, mgr_id)
            synthesis_prompt = (
                f"당신은 {mgr_name}입니다. 소속 전문가들이 아래 분석 결과를 제출했습니다.\n"
                f"이를 검수하고 종합하여 CEO에게 보고할 간결한 보고서를 작성하세요.\n"
                f"전문가 의견 중 부족하거나 잘못된 부분이 있으면 지적하고 보완하세요.\n\n"
                f"## CEO 원본 명령\n{text}\n\n"
                f"## 전문가 분석 결과\n" + "\n\n".join(spec_parts)
            )

            soul = _load_agent_prompt(mgr_id)
            override = _get_model_override(mgr_id)
            model = select_model(synthesis_prompt, override=override)
            custom_id = f"{chain['chain_id']}_synth_{mgr_id}"

            requests.append({
                "custom_id": custom_id,
                "message": synthesis_prompt,
                "system_prompt": soul,
                "model": model,
            })
            chain["custom_id_map"][custom_id] = {"agent_id": mgr_id, "step": "synthesis"}

    elif chain["target_id"] == "chief_of_staff":
        # 비서실장 직접 처리 (분류 결과가 chief_of_staff인 경우)
        soul = _load_agent_prompt("chief_of_staff")
        override = _get_model_override("chief_of_staff")
        model = select_model(text, override=override)
        custom_id = f"{chain['chain_id']}_synth_chief_of_staff"

        requests.append({
            "custom_id": custom_id,
            "message": text,
            "system_prompt": soul,
            "model": model,
        })
        chain["custom_id_map"][custom_id] = {"agent_id": "chief_of_staff", "step": "synthesis"}

    else:
        # 단일 부서: 처장이 전문가 결과를 종합
        target_id = chain["target_id"]
        specialists = _MANAGER_SPECIALISTS.get(target_id, [])

        if not specialists or not chain["results"]["specialists"]:
            # 전문가 결과 없음 → 처장이 직접 답변
            soul = _load_agent_prompt(target_id)
            override = _get_model_override(target_id)
            model = select_model(text, override=override)
            custom_id = f"{chain['chain_id']}_synth_{target_id}"

            requests.append({
                "custom_id": custom_id,
                "message": text,
                "system_prompt": soul,
                "model": model,
            })
            chain["custom_id_map"][custom_id] = {"agent_id": target_id, "step": "synthesis"}
        else:
            # 전문가 결과 취합 → 처장에게 종합 요청
            spec_parts = []
            for s_id in specialists:
                s_res = chain["results"]["specialists"].get(s_id, {})
                name = _SPECIALIST_NAMES.get(s_id, s_id)
                content = s_res.get("content", "응답 없음")
                if s_res.get("error"):
                    content = f"오류: {s_res['error'][:100]}"
                spec_parts.append(f"[{name}]\n{content}")

            mgr_name = _AGENT_NAMES.get(target_id, target_id)
            synthesis_prompt = (
                f"당신은 {mgr_name}입니다. 소속 전문가들이 아래 분석 결과를 제출했습니다.\n"
                f"이를 검수하고 종합하여 CEO에게 보고할 간결한 보고서를 작성하세요.\n"
                f"전문가 의견 중 부족하거나 잘못된 부분이 있으면 지적하고 보완하세요.\n\n"
                f"## CEO 원본 명령\n{text}\n\n"
                f"## 전문가 분석 결과\n" + "\n\n".join(spec_parts)
            )

            soul = _load_agent_prompt(target_id)
            override = _get_model_override(target_id)
            model = select_model(synthesis_prompt, override=override)
            custom_id = f"{chain['chain_id']}_synth_{target_id}"

            requests.append({
                "custom_id": custom_id,
                "message": synthesis_prompt,
                "system_prompt": soul,
                "model": model,
            })
            chain["custom_id_map"][custom_id] = {"agent_id": target_id, "step": "synthesis"}

    if not requests:
        # 요청 없음 → 바로 완료
        await _deliver_chain_result(chain)
        return

    # 프로바이더별 그룹화하여 배치 제출
    batch_results = await batch_submit_grouped(requests)

    chain["batches"]["synthesis"] = []
    for br in batch_results:
        chain["batches"]["synthesis"].append({
            "batch_id": br.get("batch_id", ""),
            "provider": br.get("provider", ""),
            "status": "pending" if "error" not in br else "failed",
            "custom_ids": br.get("custom_ids", []),
            "error": br.get("error"),
        })

    chain["step"] = "synthesis"
    chain["status"] = "pending"
    _save_chain(chain)

    _ensure_batch_poller()

    if chain["mode"] == "broadcast":
        update_task(chain["task_id"], status="pending",
                    result_summary="📦 [배치 체인] 3단계: 6개 처장 종합보고서 배치 제출")
        await _broadcast_chain_status(chain, "📦 3단계: 6개 처장이 종합보고서 작성 중 (배치)")
    else:
        target_name = _AGENT_NAMES.get(chain["target_id"], chain["target_id"])
        update_task(chain["task_id"], status="pending",
                    result_summary=f"📦 [배치 체인] 3단계: {target_name} 종합보고서 배치 제출")
        await _broadcast_chain_status(chain, f"📦 3단계: {target_name} 종합보고서 작성 중 (배치)")

    _log(f"[CHAIN] {chain['chain_id']} — 종합보고서 배치 제출 ({len(requests)}건)")


async def _deliver_chain_result(chain: dict):
    """배치 체인 최종 결과를 CEO에게 전달합니다."""
    task_id = chain["task_id"]
    text = chain["text"]
    total_cost = chain.get("total_cost_usd", 0)

    if chain["mode"] == "broadcast":
        # 브로드캐스트: 6개 처장 종합 결과를 모아서 전달
        all_managers = ["cto_manager", "cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]
        parts = []
        total_specialists = 0
        for mgr_id in all_managers:
            synth = chain["results"]["synthesis"].get(mgr_id, {})
            mgr_name = _AGENT_NAMES.get(mgr_id, mgr_id)
            content = synth.get("content", "응답 없음")
            specs = len(_MANAGER_SPECIALISTS.get(mgr_id, []))
            total_specialists += specs
            spec_label = f" (전문가 {specs}명 동원)" if specs else ""
            parts.append(f"### 📋 {mgr_name}{spec_label}\n{content}")

        compiled = (
            f"📢 **배치 체인 결과** (6개 부서 + 전문가 {total_specialists}명 동원)\n"
            f"💰 총 비용: ${total_cost:.4f} (배치 할인 ~50% 적용)\n\n---\n\n"
            + "\n\n---\n\n".join(parts)
        )

        update_task(task_id, status="completed",
                    result_summary=compiled[:500],
                    result_data=compiled,
                    success=1, cost_usd=total_cost,
                    agent_id="chief_of_staff")

        # WebSocket으로 최종 결과 전달
        for c in connected_clients[:]:
            try:
                await c.send_json({
                    "event": "result",
                    "data": {
                        "content": compiled,
                        "sender_id": "chief_of_staff",
                        "handled_by": "비서실장 → 6개 처장",
                        "delegation": "비서실장 → 처장 → 전문가 (배치)",
                        "time_seconds": 0,
                        "cost": total_cost,
                        "model": "multi-agent-batch",
                        "routing_method": "배치 체인 (브로드캐스트)",
                    }
                })
            except Exception:
                pass

    else:
        # 단일 부서 결과
        target_id = chain.get("target_id", "chief_of_staff")
        synth = chain["results"]["synthesis"].get(
            target_id,
            chain["results"]["synthesis"].get("chief_of_staff", {})
        )
        content = synth.get("content", "")
        target_name = _AGENT_NAMES.get(target_id, target_id)

        # 위임 정보 구성
        specs_count = len(_MANAGER_SPECIALISTS.get(target_id, []))
        if target_id == "chief_of_staff":
            delegation = ""
            handled_by = "비서실장"
            header = "📋 **비서실장** (배치 처리)"
        else:
            delegation = f"비서실장 → {target_name}"
            if specs_count:
                delegation += f" → 전문가 {specs_count}명"
            handled_by = target_name
            header = f"📋 **{target_name}** 보고 (배치 체인)"
            if specs_count:
                header += f" (소속 전문가 {specs_count}명 동원)"

        final_content = f"{header}\n💰 비용: ${total_cost:.4f} (배치 할인 ~50% 적용)\n\n---\n\n{content}"

        update_task(task_id, status="completed",
                    result_summary=final_content[:500],
                    result_data=final_content,
                    success=1, cost_usd=total_cost,
                    agent_id=target_id)

        # WebSocket으로 최종 결과 전달
        for c in connected_clients[:]:
            try:
                await c.send_json({
                    "event": "result",
                    "data": {
                        "content": final_content,
                        "sender_id": target_id,
                        "handled_by": handled_by,
                        "delegation": delegation,
                        "time_seconds": 0,
                        "cost": total_cost,
                        "model": synth.get("model", "batch"),
                        "routing_method": "배치 체인",
                    }
                })
            except Exception:
                pass

    # 아카이브에 저장
    synth_content = ""
    if chain["mode"] == "broadcast":
        synth_content = compiled
    else:
        synth_content = content

    if synth_content and len(synth_content) > 20:
        division = _AGENT_DIVISION.get(chain.get("target_id", "chief_of_staff"), "secretary")
        now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        save_archive(
            division=division,
            filename=f"batch_chain_{now_str}.md",
            content=f"# [배치 체인] {text[:60]}\n\n{synth_content}",
            agent_id=chain.get("target_id", "chief_of_staff"),
        )

    chain["step"] = "completed"
    chain["status"] = "completed"
    chain["completed_at"] = datetime.now(KST).isoformat()
    _save_chain(chain)

    await _broadcast_chain_status(chain, "✅ 배치 체인 완료 — 최종 보고서 전달됨")
    _log(f"[CHAIN] {chain['chain_id']} — 완료! 비용: ${total_cost:.4f}")


async def _advance_batch_chain(chain_id: str):
    """배치 체인의 현재 단계를 확인하고, 완료되었으면 다음 단계로 진행합니다.

    배치 폴러(_batch_poller_loop)에서 60초마다 호출됩니다.
    """
    chain = _load_chain(chain_id)
    if not chain or chain.get("status") not in ("running", "pending"):
        return

    step = chain.get("step", "")

    # ── 1단계: 분류 ──
    if step == "classify":
        batch_info = chain["batches"].get("classify")
        if not batch_info:
            return

        status_result = await batch_check(batch_info["batch_id"], batch_info["provider"])
        if "error" in status_result:
            return

        batch_info["status"] = status_result["status"]

        if status_result["status"] == "completed":
            # 분류 결과 가져오기
            result = await batch_retrieve(batch_info["batch_id"], batch_info["provider"])
            if "error" in result:
                chain["status"] = "failed"
                _save_chain(chain)
                return

            # JSON 파싱 — {"agent_id": "cio_manager", "reason": "..."}
            results_list = result.get("results", [])
            if results_list:
                raw_content = results_list[0].get("content", "").strip()
                cost = results_list[0].get("cost_usd", 0)
                chain["total_cost_usd"] += cost

                try:
                    if "```" in raw_content:
                        raw_content = raw_content.split("```")[1]
                        if raw_content.startswith("json"):
                            raw_content = raw_content[4:]
                    parsed = json.loads(raw_content)
                    target_id = parsed.get("agent_id", "chief_of_staff")
                    reason = parsed.get("reason", "")
                except (json.JSONDecodeError, IndexError):
                    _log(f"[CHAIN] 분류 JSON 파싱 실패: {raw_content[:100]}")
                    target_id = "chief_of_staff"
                    reason = "분류 결과 파싱 실패"
            else:
                target_id = "chief_of_staff"
                reason = "분류 결과 없음"

            chain["target_id"] = target_id
            chain["results"]["classify"] = {
                "agent_id": target_id,
                "reason": reason,
                "method": "AI분류 (배치)",
                "cost_usd": cost if results_list else 0,
            }

            target_name = _AGENT_NAMES.get(target_id, target_id)
            _log(f"[CHAIN] {chain['chain_id']} — 분류 완료: {target_name} ({reason})")

            if target_id == "chief_of_staff":
                # 비서실장 직접 → 종합 단계
                chain["step"] = "synthesis"
                _save_chain(chain)
                await _broadcast_chain_status(chain, f"📦 분류 완료: 비서실장 직접 처리")
                await _chain_submit_synthesis(chain)
            else:
                # 전문가 단계로 진행
                chain["step"] = "specialists"
                _save_chain(chain)
                await _broadcast_chain_status(chain, f"📦 분류 완료: {target_name}에게 위임 → 전문가 호출")
                await _chain_submit_specialists(chain)

        elif status_result["status"] in ("failed", "expired"):
            # 분류 배치 실패 → 비서실장 폴백
            chain["target_id"] = "chief_of_staff"
            chain["step"] = "synthesis"
            chain["results"]["classify"] = {"agent_id": "chief_of_staff", "method": "폴백"}
            _save_chain(chain)
            await _chain_submit_synthesis(chain)

    # ── 2단계: 전문가 ──
    elif step == "specialists":
        all_done = True
        for batch_info in chain["batches"].get("specialists", []):
            if batch_info.get("status") in ("pending", "processing"):
                try:
                    status_result = await batch_check(batch_info["batch_id"], batch_info["provider"])
                    if "error" not in status_result:
                        batch_info["status"] = status_result["status"]
                except Exception as e:
                    _log(f"[CHAIN] 전문가 배치 확인 오류: {e}")

            if batch_info.get("status") not in ("completed", "failed"):
                all_done = False

        _save_chain(chain)

        if all_done:
            # 모든 전문가 배치 완료 → 결과 수집
            for batch_info in chain["batches"]["specialists"]:
                if batch_info.get("status") != "completed":
                    continue

                result = await batch_retrieve(batch_info["batch_id"], batch_info["provider"])
                if "error" in result:
                    continue

                for r in result.get("results", []):
                    custom_id = r.get("custom_id", "")
                    mapping = chain["custom_id_map"].get(custom_id, {})
                    agent_id = mapping.get("agent_id", custom_id)

                    chain["results"]["specialists"][agent_id] = {
                        "content": r.get("content", ""),
                        "model": r.get("model", ""),
                        "cost_usd": r.get("cost_usd", 0),
                        "error": r.get("error"),
                    }
                    chain["total_cost_usd"] += r.get("cost_usd", 0)

            spec_count = len(chain["results"]["specialists"])
            _log(f"[CHAIN] {chain['chain_id']} — 전문가 {spec_count}명 결과 수집 완료")

            # 종합 단계로 진행
            chain["step"] = "synthesis"
            _save_chain(chain)
            await _broadcast_chain_status(chain, f"📦 전문가 {spec_count}명 완료 → 종합보고서 작성 시작")
            await _chain_submit_synthesis(chain)

    # ── 3단계: 종합보고서 ──
    elif step == "synthesis":
        all_done = True
        for batch_info in chain["batches"].get("synthesis", []):
            if batch_info.get("status") in ("pending", "processing"):
                try:
                    status_result = await batch_check(batch_info["batch_id"], batch_info["provider"])
                    if "error" not in status_result:
                        batch_info["status"] = status_result["status"]
                except Exception as e:
                    _log(f"[CHAIN] 종합 배치 확인 오류: {e}")

            if batch_info.get("status") not in ("completed", "failed"):
                all_done = False

        _save_chain(chain)

        if all_done:
            # 종합보고서 결과 수집
            for batch_info in chain["batches"]["synthesis"]:
                if batch_info.get("status") != "completed":
                    continue

                result = await batch_retrieve(batch_info["batch_id"], batch_info["provider"])
                if "error" in result:
                    continue

                for r in result.get("results", []):
                    custom_id = r.get("custom_id", "")
                    mapping = chain["custom_id_map"].get(custom_id, {})
                    agent_id = mapping.get("agent_id", custom_id)

                    chain["results"]["synthesis"][agent_id] = {
                        "content": r.get("content", ""),
                        "model": r.get("model", ""),
                        "cost_usd": r.get("cost_usd", 0),
                        "error": r.get("error"),
                    }
                    chain["total_cost_usd"] += r.get("cost_usd", 0)

            _log(f"[CHAIN] {chain['chain_id']} — 종합보고서 완료")

            # 최종 전달
            await _deliver_chain_result(chain)


@app.get("/api/batch/chains")
async def get_batch_chains():
    """진행 중인 배치 체인 목록을 조회합니다."""
    chains = load_setting("batch_chains") or []
    active = [c for c in chains if c.get("status") in ("running", "pending")]
    recent_done = [c for c in chains if c.get("status") in ("completed", "failed")][-10:]
    return {"active": active, "recent": recent_done}


# ── 크론 실행 엔진 (asyncio 기반 스케줄러) ──

_cron_task = None  # 크론 루프 태스크


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


def _should_run_schedule(schedule: dict, now: datetime) -> bool:
    """현재 시간에 이 예약을 실행해야 하는지 확인합니다."""
    if not schedule.get("enabled", False):
        return False

    preset = schedule.get("cron_preset", "")
    cron_config = _parse_cron_preset(preset)

    # 마지막 실행 시간 확인
    last_run = schedule.get("last_run_ts", 0)
    elapsed = now.timestamp() - last_run

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


async def _cron_loop():
    """1분마다 예약된 작업을 확인하고 실행합니다."""
    logger = logging.getLogger("corthex.cron")
    logger.info("크론 실행 엔진 시작")

    while True:
        try:
            await asyncio.sleep(60)  # 1분마다 체크
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

        except Exception as e:
            logger.error("크론 루프 에러: %s", e)


async def _run_scheduled_command(command: str, schedule_name: str):
    """예약된 명령을 실행합니다."""
    try:
        result = await _process_ai_command(command, source="cron")
        save_activity_log("system", f"✅ 예약 완료: {schedule_name}", "info")
    except Exception as e:
        save_activity_log("system", f"❌ 예약 실패: {schedule_name} — {str(e)[:100]}", "error")


@app.get("/api/replay/{correlation_id}")
async def get_replay(correlation_id: str):
    return {"steps": []}


@app.get("/api/replay/latest")
async def get_replay_latest():
    return {"steps": []}


# ── 예약 (스케줄) 관리 ──

@app.get("/api/schedules")
async def get_schedules():
    return _load_data("schedules", [])


@app.post("/api/schedules")
async def add_schedule(request: Request):
    """새 예약 추가."""
    body = await request.json()
    schedules = _load_data("schedules", [])
    schedule_id = f"sch_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{len(schedules)}"
    schedule = {
        "id": schedule_id,
        "name": body.get("name", ""),
        "command": body.get("command", ""),
        "cron": body.get("cron", ""),
        "cron_preset": body.get("cron_preset", ""),
        "description": body.get("description", ""),
        "enabled": True,
        "created_at": datetime.now(KST).isoformat(),
    }
    schedules.append(schedule)
    _save_data("schedules", schedules)
    return {"success": True, "schedule": schedule}


@app.post("/api/schedules/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str):
    """예약 활성화/비활성화."""
    schedules = _load_data("schedules", [])
    for s in schedules:
        if s.get("id") == schedule_id:
            s["enabled"] = not s.get("enabled", True)
            _save_data("schedules", schedules)
            return {"success": True, "enabled": s["enabled"]}
    return {"success": False, "error": "not found"}


@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """예약 삭제."""
    schedules = _load_data("schedules", [])
    schedules = [s for s in schedules if s.get("id") != schedule_id]
    _save_data("schedules", schedules)
    return {"success": True}


# ── 워크플로우 관리 ──

@app.get("/api/workflows")
async def get_workflows():
    return _load_data("workflows", [])


@app.post("/api/workflows")
async def create_workflow(request: Request):
    """새 워크플로우 생성."""
    body = await request.json()
    workflows = _load_data("workflows", [])
    wf_id = f"wf_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{len(workflows)}"
    workflow = {
        "id": wf_id,
        "name": body.get("name", "새 워크플로우"),
        "description": body.get("description", ""),
        "steps": body.get("steps", []),
        "created_at": datetime.now(KST).isoformat(),
    }
    workflows.append(workflow)
    _save_data("workflows", workflows)
    return {"success": True, "workflow": workflow}


@app.put("/api/workflows/{wf_id}")
async def save_workflow(wf_id: str, request: Request):
    """워크플로우 수정."""
    body = await request.json()
    workflows = _load_data("workflows", [])
    for wf in workflows:
        if wf.get("id") == wf_id:
            wf["name"] = body.get("name", wf.get("name", ""))
            wf["description"] = body.get("description", wf.get("description", ""))
            wf["steps"] = body.get("steps", wf.get("steps", []))
            _save_data("workflows", workflows)
            return {"success": True, "workflow": wf}
    return {"success": False, "error": "not found"}


@app.delete("/api/workflows/{wf_id}")
async def delete_workflow(wf_id: str):
    """워크플로우 삭제."""
    workflows = _load_data("workflows", [])
    workflows = [w for w in workflows if w.get("id") != wf_id]
    _save_data("workflows", workflows)
    return {"success": True}


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

        try:
            result = await _process_ai_command(command, source="workflow")
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            prev_result = content[:500]
            results.append({"step": step_name, "status": "completed", "result": content[:200]})
            save_activity_log("system", f"✅ {wf_name} — {step_name} 완료", "info")
        except Exception as e:
            results.append({"step": step_name, "status": "failed", "error": str(e)[:200]})
            save_activity_log("system", f"❌ {wf_name} — {step_name} 실패: {str(e)[:100]}", "error")
            break  # 실패 시 중단

    save_activity_log("system", f"🏁 워크플로우 완료: {wf_name} — {len(results)}/{len(steps)} 단계 처리", "info")


# ── 자동매매 시스템 (키움증권 프레임워크) ──

_trading_bot_active = False  # 자동매매 봇 ON/OFF
_trading_bot_task = None     # 자동매매 봇 asyncio Task


def _default_portfolio() -> dict:
    """기본 포트폴리오 데이터."""
    return {
        "cash": 50_000_000,    # 초기 현금 (5천만원)
        "initial_cash": 50_000_000,
        "holdings": [],        # [{ticker, name, qty, avg_price, current_price}]
        "updated_at": datetime.now(KST).isoformat(),
    }


def _default_trading_settings() -> dict:
    """기본 자동매매 설정."""
    return {
        "max_position_pct": 20,       # 종목당 최대 비중 (%)
        "max_daily_trades": 10,       # 일일 최대 거래 횟수
        "max_daily_loss_pct": 3,      # 일일 최대 손실 (%)
        "default_stop_loss_pct": -5,  # 기본 손절 (%)
        "default_take_profit_pct": 10, # 기본 익절 (%)
        "order_size": 1_000_000,      # 기본 주문 금액 (원)
        "trading_hours_kr": {"start": "09:00", "end": "15:20"},   # 한국 장 시간
        "trading_hours_us": {"start": "22:30", "end": "05:00"},   # 미국 장 시간 (KST 기준, 서머타임 시 23:30)
        "trading_hours": {"start": "09:00", "end": "15:20"},      # 하위호환
        "auto_stop_loss": True,       # 자동 손절 활성화
        "auto_take_profit": True,     # 자동 익절 활성화
        "auto_execute": False,        # CIO 시그널 기반 자동 주문 실행 (안전장치: 기본 OFF)
        "min_confidence": 70,         # 자동매매 최소 신뢰도 (%)
        "kiwoom_connected": False,    # 키움증권 API 연결 여부
        "paper_trading": True,        # 모의투자 모드 (실거래 전)
    }


@app.get("/api/trading/summary")
async def get_trading_summary():
    """트레이딩 대시보드 요약 데이터."""
    portfolio = _load_data("trading_portfolio", _default_portfolio())
    strategies = _load_data("trading_strategies", [])
    watchlist = _load_data("trading_watchlist", [])
    history = _load_data("trading_history", [])
    signals = _load_data("trading_signals", [])
    settings = _load_data("trading_settings", _default_trading_settings())

    # 포트폴리오 평가 계산
    holdings = portfolio.get("holdings", [])
    total_eval = sum(h.get("current_price", 0) * h.get("qty", 0) for h in holdings)
    total_buy_cost = sum(h.get("avg_price", 0) * h.get("qty", 0) for h in holdings)
    cash = portfolio.get("cash", 0)
    total_asset = cash + total_eval
    total_pnl = total_eval - total_buy_cost
    pnl_pct = (total_pnl / total_buy_cost * 100) if total_buy_cost > 0 else 0

    # 오늘 거래 집계
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    today_trades = [t for t in history if t.get("date", "").startswith(today_str)]
    today_pnl = sum(t.get("pnl", 0) for t in today_trades)

    active_strategies = [s for s in strategies if s.get("active")]

    return {
        "portfolio": {
            "cash": cash,
            "total_eval": total_eval,
            "total_asset": total_asset,
            "total_pnl": total_pnl,
            "pnl_pct": round(pnl_pct, 2),
            "holdings_count": len(holdings),
            "initial_cash": portfolio.get("initial_cash", 50_000_000),
        },
        "strategies": {
            "total": len(strategies),
            "active": len(active_strategies),
        },
        "watchlist_count": len(watchlist),
        "today": {
            "trades": len(today_trades),
            "pnl": today_pnl,
        },
        "signals_count": len(signals),
        "settings": settings,
        "bot_active": _trading_bot_active,
    }


@app.get("/api/trading/portfolio")
async def get_trading_portfolio():
    """포트폴리오 전체 데이터."""
    portfolio = _load_data("trading_portfolio", _default_portfolio())
    return portfolio


@app.post("/api/trading/portfolio")
async def update_trading_portfolio(request: Request):
    """포트폴리오 업데이트 (초기 자금 설정 등)."""
    body = await request.json()
    portfolio = _load_data("trading_portfolio", _default_portfolio())

    if "cash" in body:
        portfolio["cash"] = body["cash"]
    if "initial_cash" in body:
        portfolio["initial_cash"] = body["initial_cash"]
        portfolio["cash"] = body["initial_cash"]
        portfolio["holdings"] = []
    portfolio["updated_at"] = datetime.now(KST).isoformat()

    _save_data("trading_portfolio", portfolio)
    save_activity_log("system", f"💰 포트폴리오 업데이트: 현금 {portfolio['cash']:,.0f}원", "info")
    return {"success": True, "portfolio": portfolio}


@app.get("/api/trading/strategies")
async def get_trading_strategies():
    """매매 전략 목록."""
    return _load_data("trading_strategies", [])


@app.post("/api/trading/strategies")
async def save_trading_strategy(request: Request):
    """매매 전략 추가/수정."""
    body = await request.json()
    strategies = _load_data("trading_strategies", [])

    strategy_id = body.get("id") or f"strat_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{len(strategies)}"

    existing = next((s for s in strategies if s.get("id") == strategy_id), None)
    if existing:
        existing.update({
            "name": body.get("name", existing.get("name", "")),
            "type": body.get("type", existing.get("type", "manual")),
            "indicator": body.get("indicator", existing.get("indicator", "")),
            "buy_condition": body.get("buy_condition", existing.get("buy_condition", "")),
            "sell_condition": body.get("sell_condition", existing.get("sell_condition", "")),
            "target_tickers": body.get("target_tickers", existing.get("target_tickers", [])),
            "stop_loss_pct": body.get("stop_loss_pct", existing.get("stop_loss_pct", -5)),
            "take_profit_pct": body.get("take_profit_pct", existing.get("take_profit_pct", 10)),
            "order_size": body.get("order_size", existing.get("order_size", 1_000_000)),
            "active": body.get("active", existing.get("active", True)),
            "updated_at": datetime.now(KST).isoformat(),
        })
    else:
        strategy = {
            "id": strategy_id,
            "name": body.get("name", "새 전략"),
            "type": body.get("type", "manual"),
            "indicator": body.get("indicator", ""),
            "buy_condition": body.get("buy_condition", ""),
            "sell_condition": body.get("sell_condition", ""),
            "target_tickers": body.get("target_tickers", []),
            "stop_loss_pct": body.get("stop_loss_pct", -5),
            "take_profit_pct": body.get("take_profit_pct", 10),
            "order_size": body.get("order_size", 1_000_000),
            "active": body.get("active", True),
            "created_at": datetime.now(KST).isoformat(),
            "updated_at": datetime.now(KST).isoformat(),
        }
        strategies.append(strategy)

    _save_data("trading_strategies", strategies)
    save_activity_log("system", f"📊 매매 전략 저장: {body.get('name', strategy_id)}", "info")
    return {"success": True, "strategies": strategies}


@app.delete("/api/trading/strategies/{strategy_id}")
async def delete_trading_strategy(strategy_id: str):
    """매매 전략 삭제."""
    strategies = _load_data("trading_strategies", [])
    strategies = [s for s in strategies if s.get("id") != strategy_id]
    _save_data("trading_strategies", strategies)
    return {"success": True}


@app.put("/api/trading/strategies/{strategy_id}/toggle")
async def toggle_trading_strategy(strategy_id: str):
    """매매 전략 활성/비활성 토글."""
    strategies = _load_data("trading_strategies", [])
    for s in strategies:
        if s.get("id") == strategy_id:
            s["active"] = not s.get("active", True)
            _save_data("trading_strategies", strategies)
            return {"success": True, "active": s["active"]}
    return {"success": False, "error": "전략을 찾을 수 없습니다"}


@app.get("/api/trading/watchlist")
async def get_trading_watchlist():
    """관심 종목 목록."""
    return _load_data("trading_watchlist", [])


@app.post("/api/trading/watchlist")
async def add_trading_watchlist(request: Request):
    """관심 종목 추가."""
    body = await request.json()
    watchlist = _load_data("trading_watchlist", [])

    ticker = body.get("ticker", "")
    if not ticker:
        return {"success": False, "error": "종목코드 필수"}

    # 중복 체크
    if any(w.get("ticker") == ticker for w in watchlist):
        return {"success": False, "error": "이미 등록된 종목"}

    item = {
        "ticker": ticker,
        "name": body.get("name", ticker),
        "market": body.get("market", "KR"),
        "target_price": body.get("target_price", 0),
        "alert_type": body.get("alert_type", "above"),
        "notes": body.get("notes", ""),
        "added_at": datetime.now(KST).isoformat(),
    }
    watchlist.append(item)
    _save_data("trading_watchlist", watchlist)
    save_activity_log("system", f"👁️ 관심종목 추가: {item['name']} ({ticker})", "info")
    return {"success": True, "watchlist": watchlist}


@app.delete("/api/trading/watchlist/{ticker}")
async def remove_trading_watchlist(ticker: str):
    """관심 종목 삭제."""
    watchlist = _load_data("trading_watchlist", [])
    watchlist = [w for w in watchlist if w.get("ticker") != ticker]
    _save_data("trading_watchlist", watchlist)
    return {"success": True}


@app.get("/api/trading/watchlist/prices")
async def get_watchlist_prices():
    """관심종목의 실시간 현재가를 조회.

    한국 주식: pykrx 라이브러리 (한국거래소 무료 데이터)
    미국 주식: yfinance 라이브러리 (Yahoo Finance 무료 데이터)
    """
    watchlist = _load_data("trading_watchlist", [])
    if not watchlist:
        return {"prices": {}, "updated_at": datetime.now(KST).isoformat()}

    prices = {}

    # --- 한국 주식 (pykrx) ---
    kr_tickers = [w for w in watchlist if w.get("market", "KR") == "KR"]
    if kr_tickers:
        try:
            from pykrx import stock as pykrx_stock
            today = datetime.now(KST).strftime("%Y%m%d")
            # 최근 5영업일 범위로 조회 (주말/공휴일 대비)
            start = (datetime.now(KST) - timedelta(days=7)).strftime("%Y%m%d")
            for w in kr_tickers:
                try:
                    df = await asyncio.to_thread(
                        pykrx_stock.get_market_ohlcv_by_date, start, today, w["ticker"]
                    )
                    if df is not None and not df.empty:
                        latest = df.iloc[-1]
                        prev = df.iloc[-2] if len(df) >= 2 else latest
                        close = int(latest["종가"])
                        prev_close = int(prev["종가"])
                        change = close - prev_close
                        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
                        prices[w["ticker"]] = {
                            "current_price": close,
                            "prev_close": prev_close,
                            "change": change,
                            "change_pct": change_pct,
                            "volume": int(latest.get("거래량", 0)),
                            "high": int(latest.get("고가", 0)),
                            "low": int(latest.get("저가", 0)),
                            "currency": "KRW",
                        }
                except Exception as e:
                    logger.warning("한국 주가 조회 실패 %s: %s", w["ticker"], e)
                    prices[w["ticker"]] = {"error": str(e)}
        except ImportError:
            for w in kr_tickers:
                prices[w["ticker"]] = {"error": "pykrx 미설치"}

    # --- 미국 주식 (yfinance) ---
    us_tickers = [w for w in watchlist if w.get("market") == "US"]
    if us_tickers:
        try:
            import yfinance as yf
            for w in us_tickers:
                try:
                    ticker_obj = yf.Ticker(w["ticker"])
                    hist = await asyncio.to_thread(
                        lambda t=ticker_obj: t.history(period="5d")
                    )
                    if hist is not None and not hist.empty:
                        latest = hist.iloc[-1]
                        prev = hist.iloc[-2] if len(hist) >= 2 else latest
                        close = round(float(latest["Close"]), 2)
                        prev_close = round(float(prev["Close"]), 2)
                        change = round(close - prev_close, 2)
                        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
                        prices[w["ticker"]] = {
                            "current_price": close,
                            "prev_close": prev_close,
                            "change": change,
                            "change_pct": change_pct,
                            "volume": int(latest.get("Volume", 0)),
                            "high": round(float(latest.get("High", 0)), 2),
                            "low": round(float(latest.get("Low", 0)), 2),
                            "currency": "USD",
                        }
                except Exception as e:
                    logger.warning("미국 주가 조회 실패 %s: %s", w["ticker"], e)
                    prices[w["ticker"]] = {"error": str(e)}
        except ImportError:
            for w in us_tickers:
                prices[w["ticker"]] = {"error": "yfinance 미설치"}

    return {"prices": prices, "updated_at": datetime.now(KST).isoformat()}


@app.get("/api/trading/watchlist/chart/{ticker}")
async def get_watchlist_chart(ticker: str, market: str = "KR", days: int = 30):
    """관심종목의 일별 가격 데이터 (차트용).

    간단한 일별 종가 데이터를 반환하여 프론트엔드에서 선 그래프를 그릴 수 있게 합니다.
    """
    chart_data = []

    if market == "KR":
        try:
            from pykrx import stock as pykrx_stock
            end = datetime.now(KST).strftime("%Y%m%d")
            start = (datetime.now(KST) - timedelta(days=days + 10)).strftime("%Y%m%d")
            df = await asyncio.to_thread(
                pykrx_stock.get_market_ohlcv_by_date, start, end, ticker
            )
            if df is not None and not df.empty:
                for date, row in df.tail(days).iterrows():
                    chart_data.append({
                        "date": date.strftime("%m/%d"),
                        "close": int(row["종가"]),
                        "volume": int(row.get("거래량", 0)),
                    })
        except ImportError:
            return {"ticker": ticker, "chart": [], "error": "pykrx 미설치"}
        except Exception as e:
            return {"ticker": ticker, "chart": [], "error": str(e)}
    else:
        try:
            import yfinance as yf
            ticker_obj = yf.Ticker(ticker)
            period = "1mo" if days <= 30 else "3mo"
            hist = await asyncio.to_thread(
                lambda t=ticker_obj, p=period: t.history(period=p)
            )
            if hist is not None and not hist.empty:
                for date, row in hist.tail(days).iterrows():
                    chart_data.append({
                        "date": date.strftime("%m/%d"),
                        "close": round(float(row["Close"]), 2),
                        "volume": int(row.get("Volume", 0)),
                    })
        except ImportError:
            return {"ticker": ticker, "chart": [], "error": "yfinance 미설치"}
        except Exception as e:
            return {"ticker": ticker, "chart": [], "error": str(e)}

    return {"ticker": ticker, "chart": chart_data}


@app.post("/api/trading/order")
async def execute_trading_order(request: Request):
    """모의 주문 실행 (매수/매도).

    실제 키움증권 API 연결 전까지는 포트폴리오 데이터만 업데이트합니다.
    """
    body = await request.json()
    action = body.get("action", "")  # "buy" or "sell"
    ticker = body.get("ticker", "")
    name = body.get("name", ticker)
    qty = int(body.get("qty", 0))
    price = int(body.get("price", 0))

    if not all([action in ("buy", "sell"), ticker, qty > 0, price > 0]):
        return {"success": False, "error": "매수/매도, 종목코드, 수량, 가격 필수"}

    portfolio = _load_data("trading_portfolio", _default_portfolio())
    total_amount = qty * price

    if action == "buy":
        if portfolio["cash"] < total_amount:
            return {"success": False, "error": f"현금 부족: 필요 {total_amount:,.0f}원, 보유 {portfolio['cash']:,.0f}원"}

        # 기존 보유 종목 확인 (평단 계산)
        holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
        if holding:
            old_total = holding["avg_price"] * holding["qty"]
            new_total = old_total + total_amount
            holding["qty"] += qty
            holding["avg_price"] = int(new_total / holding["qty"])
            holding["current_price"] = price
        else:
            portfolio["holdings"].append({
                "ticker": ticker,
                "name": name,
                "qty": qty,
                "avg_price": price,
                "current_price": price,
            })

        portfolio["cash"] -= total_amount

    elif action == "sell":
        holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
        if not holding:
            return {"success": False, "error": f"{name} 보유하지 않음"}
        if holding["qty"] < qty:
            return {"success": False, "error": f"보유 수량 부족: 보유 {holding['qty']}주, 매도 {qty}주"}

        pnl = (price - holding["avg_price"]) * qty
        holding["qty"] -= qty
        holding["current_price"] = price

        if holding["qty"] == 0:
            portfolio["holdings"] = [h for h in portfolio["holdings"] if h["ticker"] != ticker]

        portfolio["cash"] += total_amount

    portfolio["updated_at"] = datetime.now(KST).isoformat()
    _save_data("trading_portfolio", portfolio)

    # 거래 내역 저장
    history = _load_data("trading_history", [])
    trade = {
        "id": f"trade_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{len(history)}",
        "date": datetime.now(KST).isoformat(),
        "ticker": ticker,
        "name": name,
        "action": action,
        "qty": qty,
        "price": price,
        "total": total_amount,
        "pnl": pnl if action == "sell" else 0,
        "strategy": body.get("strategy", "manual"),
        "status": "executed",
    }
    history.insert(0, trade)
    if len(history) > 500:
        history = history[:500]
    _save_data("trading_history", history)

    action_ko = "매수" if action == "buy" else "매도"
    pnl_str = f" (손익: {pnl:+,.0f}원)" if action == "sell" else ""
    save_activity_log("system",
        f"{'📈' if action == 'buy' else '📉'} {action_ko}: {name} {qty}주 × {price:,.0f}원 = {total_amount:,.0f}원{pnl_str}",
        "info")

    return {"success": True, "trade": trade, "portfolio": portfolio}


@app.get("/api/trading/history")
async def get_trading_history():
    """거래 내역."""
    return _load_data("trading_history", [])


@app.get("/api/trading/signals")
async def get_trading_signals():
    """매매 시그널 목록."""
    return _load_data("trading_signals", [])


@app.post("/api/trading/signals/generate")
async def generate_trading_signals():
    """CIO(투자분석처장) + 4명 전문가가 관심종목을 분석 → 매매 시그널 생성.

    흐름:
    1. 시황분석 Specialist → 거시경제/시장 분위기 분석
    2. 종목분석 Specialist → 재무제표/실적/밸류에이션 분석
    3. 기술적분석 Specialist → RSI/MACD/볼린저밴드/이평선 분석
    4. 리스크관리 Specialist → 손절/포지션/리스크 평가
    5. CIO가 4명 결과 취합 → 종목별 매수/매도/관망 판단
    """
    watchlist = _load_data("trading_watchlist", [])
    strategies = _load_data("trading_strategies", [])
    active_strategies = [s for s in strategies if s.get("active")]

    if not watchlist and not active_strategies:
        return {"success": False, "error": "관심종목이나 활성 전략이 없습니다"}

    # 종목 정보 정리 (한국/미국 구분)
    kr_tickers = [w for w in watchlist if w.get("market", "KR") == "KR"]
    us_tickers = [w for w in watchlist if w.get("market") == "US"]
    tickers_info = ", ".join([f"{w['name']}({w['ticker']})" for w in watchlist[:10]])
    strats_info = ", ".join([s["name"] for s in active_strategies[:5]])

    # CIO에게 보내는 분석 명령
    prompt = f"""[자동매매 시스템] 관심종목 종합 분석을 요청합니다.

## 관심종목 ({len(watchlist)}개)
{tickers_info or '없음'}
{f'- 한국 주식: {len(kr_tickers)}개' if kr_tickers else ''}
{f'- 미국 주식: {len(us_tickers)}개' if us_tickers else ''}

## 활성 매매 전략
{strats_info or '기본 전략 (RSI/MACD 기반)'}

## 분석 요청사항
각 전문가에게 아래 분석을 지시하세요:
- **시황분석**: 현재 시장 분위기, 금리/환율 동향, 업종별 흐름
- **종목분석**: 각 관심종목의 재무 건전성, PER/PBR, 실적 전망
- **기술적분석**: 각 관심종목의 RSI, MACD, 이동평균선, 볼린저밴드 지표 확인
- **리스크관리**: 포지션 크기 적정성, 손절가, 전체 포트폴리오 리스크

## 최종 산출물 (반드시 이 형식으로)
각 종목에 대해 다음 형식의 결론을 포함해주세요:
[시그널] 종목명 (종목코드) | 매수/매도/관망 | 신뢰도 0~100% | 근거 한줄
[시그널] 종목명 (종목코드) | 매수/매도/관망 | 신뢰도 0~100% | 근거 한줄"""

    if not is_ai_ready():
        # AI 미연결 시 더미 시그널
        signals = _load_data("trading_signals", [])
        for w in watchlist[:5]:
            signal = {
                "id": f"sig_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{w['ticker']}",
                "date": datetime.now(KST).isoformat(),
                "ticker": w["ticker"],
                "name": w["name"],
                "market": w.get("market", "KR"),
                "action": "hold",
                "confidence": 50,
                "reason": "AI 미연결 — 분석 불가 (API 키 등록 필요)",
                "strategy": "auto",
                "analyzed_by": "system",
            }
            signals.insert(0, signal)
        if len(signals) > 200:
            signals = signals[:200]
        _save_data("trading_signals", signals)
        return {"success": True, "signals": signals[:20]}

    # CIO + 4명 전문가에게 위임 (실제 도구 사용 + 병렬 분석)
    save_activity_log("cio_manager", f"📊 자동매매 시그널 생성 — {len(watchlist)}개 종목 분석 시작", "info")
    cio_result = await _manager_with_delegation("cio_manager", prompt)

    content = cio_result.get("content", "")
    cost = cio_result.get("cost_usd", 0)
    specialists_used = cio_result.get("specialists_used", 0)

    # CIO 분석 결과에서 시그널 파싱
    parsed_signals = _parse_cio_signals(content, watchlist)

    signals = _load_data("trading_signals", [])
    new_signal = {
        "id": f"sig_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}",
        "date": datetime.now(KST).isoformat(),
        "analysis": content,
        "tickers": [w["ticker"] for w in watchlist[:10]],
        "parsed_signals": parsed_signals,
        "strategy": "cio_analysis",
        "analyzed_by": f"CIO + 전문가 {specialists_used}명",
        "cost_usd": cost,
    }
    signals.insert(0, new_signal)
    if len(signals) > 200:
        signals = signals[:200]
    _save_data("trading_signals", signals)

    buy_count = len([s for s in parsed_signals if s.get("action") == "buy"])
    sell_count = len([s for s in parsed_signals if s.get("action") == "sell"])
    save_activity_log("cio_manager",
        f"📊 CIO 시그널 완료: {len(watchlist)}개 종목 (매수 {buy_count}, 매도 {sell_count}, 비용 ${cost:.4f})",
        "info")

    return {"success": True, "signal": new_signal, "parsed_signals": parsed_signals}


def _parse_cio_signals(content: str, watchlist: list) -> list:
    """CIO 분석 결과에서 종목별 매수/매도/관망 시그널을 추출합니다."""
    import re
    parsed = []

    # [시그널] 패턴 매칭
    pattern = r'\[시그널\]\s*(.+?)\s*\((.+?)\)\s*\|\s*(매수|매도|관망|buy|sell|hold)\s*\|\s*(\d+)%?\s*\|\s*(.+)'
    matches = re.findall(pattern, content, re.IGNORECASE)

    for name, ticker, action, confidence, reason in matches:
        action_map = {"매수": "buy", "매도": "sell", "관망": "hold", "buy": "buy", "sell": "sell", "hold": "hold"}
        market = "US" if any(c.isalpha() and c.isupper() for c in ticker) and not ticker.isdigit() else "KR"
        parsed.append({
            "ticker": ticker.strip(),
            "name": name.strip(),
            "market": market,
            "action": action_map.get(action.lower(), "hold"),
            "confidence": int(confidence),
            "reason": reason.strip(),
        })

    # [시그널] 패턴이 없으면 관심종목 기반으로 키워드 파싱
    if not parsed:
        for w in watchlist:
            action = "hold"
            confidence = 50
            reason = ""
            name = w.get("name", w["ticker"])
            if name in content or w["ticker"] in content:
                lower_content = content.lower()
                if any(k in content for k in ["매수", "적극 매수", "buy", "진입"]):
                    action = "buy"
                    confidence = 65
                elif any(k in content for k in ["매도", "sell", "청산", "익절"]):
                    action = "sell"
                    confidence = 65
                # 근거 추출 (종목명 주변 문장)
                idx = content.find(name)
                if idx >= 0:
                    reason = content[idx:idx+100].split("\n")[0]
            parsed.append({
                "ticker": w["ticker"],
                "name": name,
                "market": w.get("market", "KR"),
                "action": action,
                "confidence": confidence,
                "reason": reason or "CIO 종합 분석 참조",
            })

    return parsed


@app.get("/api/trading/settings")
async def get_trading_settings():
    """자동매매 설정."""
    return _load_data("trading_settings", _default_trading_settings())


@app.post("/api/trading/settings")
async def save_trading_settings(request: Request):
    """자동매매 설정 저장."""
    body = await request.json()
    settings = _load_data("trading_settings", _default_trading_settings())
    settings.update(body)
    _save_data("trading_settings", settings)
    save_activity_log("system", "⚙️ 자동매매 설정 업데이트", "info")
    return {"success": True, "settings": settings}


@app.post("/api/trading/bot/toggle")
async def toggle_trading_bot():
    """자동매매 봇 ON/OFF 토글."""
    global _trading_bot_active, _trading_bot_task

    _trading_bot_active = not _trading_bot_active

    if _trading_bot_active:
        if _trading_bot_task is None or _trading_bot_task.done():
            _trading_bot_task = asyncio.create_task(_trading_bot_loop())
        save_activity_log("system", "🤖 자동매매 봇 가동 시작!", "info")
        _log("[TRADING] 자동매매 봇 시작 ✅")
    else:
        save_activity_log("system", "⏹️ 자동매매 봇 중지", "info")
        _log("[TRADING] 자동매매 봇 중지")

    return {"success": True, "bot_active": _trading_bot_active}


@app.get("/api/trading/bot/status")
async def get_trading_bot_status():
    """자동매매 봇 상태."""
    return {
        "active": _trading_bot_active,
        "task_running": _trading_bot_task is not None and not _trading_bot_task.done() if _trading_bot_task else False,
        "settings": _load_data("trading_settings", _default_trading_settings()),
    }


def _is_market_open(settings: dict) -> tuple[bool, str]:
    """한국/미국 장 시간인지 확인합니다. (둘 중 하나라도 열려있으면 True)"""
    now = datetime.now(KST)
    now_min = now.hour * 60 + now.minute

    # 한국 장 (09:00 ~ 15:20 KST)
    kr = settings.get("trading_hours_kr", settings.get("trading_hours", {}))
    kr_start = sum(int(x) * m for x, m in zip(kr.get("start", "09:00").split(":"), [60, 1]))
    kr_end = sum(int(x) * m for x, m in zip(kr.get("end", "15:20").split(":"), [60, 1]))
    if kr_start <= now_min < kr_end:
        return True, "KR"

    # 미국 장 (22:30 ~ 05:00 KST, 다음날로 넘어감)
    us = settings.get("trading_hours_us", {})
    us_start = sum(int(x) * m for x, m in zip(us.get("start", "22:30").split(":"), [60, 1]))
    us_end = sum(int(x) * m for x, m in zip(us.get("end", "05:00").split(":"), [60, 1]))
    if us_start <= now_min or now_min < us_end:  # 자정 넘김 처리
        return True, "US"

    return False, ""


async def _trading_bot_loop():
    """자동매매 봇 루프 — CIO(투자분석처장) + 4명 전문가가 분석 → 자동 매매.

    흐름:
    1. 5분마다 장 시간 체크 (한국 09:00~15:20, 미국 22:30~05:00 KST)
    2. 관심종목이 있으면 CIO 팀에게 분석 위임
    3. CIO가 4명 전문가 결과를 취합하여 매수/매도/관망 판단
    4. 신뢰도 70% 이상 시그널만 자동 주문 실행 (auto_execute=True일 때만)
    5. 모의투자 모드(paper_trading=True)에서는 가상 포트폴리오만 업데이트
    """
    logger = logging.getLogger("corthex.trading")
    logger.info("자동매매 봇 루프 시작 (CIO 연동)")

    while _trading_bot_active:
        try:
            await asyncio.sleep(300)  # 5분마다 체크
            if not _trading_bot_active:
                break

            settings = _load_data("trading_settings", _default_trading_settings())
            is_open, market = _is_market_open(settings)

            if not is_open:
                continue

            # 관심종목 확인
            watchlist = _load_data("trading_watchlist", [])
            if not watchlist:
                continue

            # 해당 시장의 관심종목만 필터 (한국 장이면 한국 종목, 미국 장이면 미국 종목)
            market_watchlist = [w for w in watchlist if w.get("market", "KR") == market]
            if not market_watchlist:
                continue

            market_name = "한국" if market == "KR" else "미국"
            logger.info("[TRADING BOT] %s장 오픈 — %d개 종목 CIO 분석 시작", market_name, len(market_watchlist))
            save_activity_log("cio_manager",
                f"🤖 자동매매 봇: {market_name}장 {len(market_watchlist)}개 종목 CIO 분석 시작",
                "info")

            # CIO + 전문가 팀에게 분석 위임
            tickers_info = ", ".join([f"{w['name']}({w['ticker']})" for w in market_watchlist[:10]])
            strategies = _load_data("trading_strategies", [])
            active = [s for s in strategies if s.get("active")]
            strats_info = ", ".join([s["name"] for s in active[:5]]) or "기본 전략"

            prompt = f"""[자동매매 봇 — {market_name}장 정기 분석]

## 분석 대상 ({len(market_watchlist)}개 종목)
{tickers_info}

## 활성 전략: {strats_info}

## 분석 요청
각 전문가에게 아래 분석을 지시하세요:
- **시황분석**: {'코스피/코스닥 지수 흐름, 외국인/기관 동향, 금리/환율' if market == 'KR' else 'S&P500/나스닥 지수, 미국 금리/고용지표, 달러 강세'}
- **종목분석**: 각 종목 재무 건전성, PER/PBR, 최근 실적
- **기술적분석**: RSI, MACD, 이동평균선, 볼린저밴드
- **리스크관리**: 손절가, 적정 포지션 크기, 전체 포트폴리오 리스크

## 최종 산출물 (반드시 이 형식으로)
[시그널] 종목명 (종목코드) | 매수/매도/관망 | 신뢰도 0~100% | 근거 한줄"""

            cio_result = await _manager_with_delegation("cio_manager", prompt)
            content = cio_result.get("content", "")
            cost = cio_result.get("cost_usd", 0)

            # 시그널 파싱
            parsed_signals = _parse_cio_signals(content, market_watchlist)

            # 시그널 저장
            signals = _load_data("trading_signals", [])
            new_signal = {
                "id": f"sig_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}",
                "date": datetime.now(KST).isoformat(),
                "market": market,
                "analysis": content,
                "tickers": [w["ticker"] for w in market_watchlist[:10]],
                "parsed_signals": parsed_signals,
                "strategy": "cio_bot_analysis",
                "analyzed_by": f"CIO + 전문가 {cio_result.get('specialists_used', 0)}명",
                "cost_usd": cost,
                "auto_bot": True,
            }
            signals.insert(0, new_signal)
            if len(signals) > 200:
                signals = signals[:200]
            _save_data("trading_signals", signals)

            # 자동 주문 실행 (auto_execute=True + 신뢰도 충족 시)
            auto_execute = settings.get("auto_execute", False)
            min_confidence = settings.get("min_confidence", 70)
            order_size = settings.get("order_size", 1_000_000)

            if auto_execute:
                for sig in parsed_signals:
                    if sig["action"] in ("buy", "sell") and sig.get("confidence", 0) >= min_confidence:
                        # 주문 가격은 현재가 기준 (모의투자이므로 목표가 또는 기본가 사용)
                        target_w = next((w for w in market_watchlist if w["ticker"] == sig["ticker"]), None)
                        price = target_w.get("target_price", 0) if target_w else 0
                        if price <= 0:
                            price = 50000  # 가격 미설정 시 기본값

                        qty = max(1, int(order_size / price))

                        # 내부적으로 주문 실행 (모의투자)
                        from starlette.testclient import TestClient  # noqa
                        try:
                            portfolio = _load_data("trading_portfolio", _default_portfolio())
                            if sig["action"] == "buy" and portfolio["cash"] >= price * qty:
                                # 매수 로직 (execute_trading_order와 동일)
                                holding = next((h for h in portfolio["holdings"] if h["ticker"] == sig["ticker"]), None)
                                total_amount = qty * price
                                if holding:
                                    old_total = holding["avg_price"] * holding["qty"]
                                    new_total = old_total + total_amount
                                    holding["qty"] += qty
                                    holding["avg_price"] = int(new_total / holding["qty"])
                                    holding["current_price"] = price
                                else:
                                    portfolio["holdings"].append({
                                        "ticker": sig["ticker"], "name": sig["name"],
                                        "qty": qty, "avg_price": price, "current_price": price,
                                        "market": sig.get("market", market),
                                    })
                                portfolio["cash"] -= total_amount
                                portfolio["updated_at"] = datetime.now(KST).isoformat()
                                _save_data("trading_portfolio", portfolio)

                                # 거래 내역 저장
                                history = _load_data("trading_history", [])
                                history.insert(0, {
                                    "id": f"auto_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{sig['ticker']}",
                                    "date": datetime.now(KST).isoformat(),
                                    "ticker": sig["ticker"], "name": sig["name"],
                                    "action": "buy", "qty": qty, "price": price,
                                    "total": total_amount, "pnl": 0,
                                    "strategy": f"CIO 자동매매 (신뢰도 {sig['confidence']}%)",
                                    "status": "executed", "market": sig.get("market", market),
                                })
                                _save_data("trading_history", history)

                                save_activity_log("cio_manager",
                                    f"📈 자동매수: {sig['name']} {qty}주 × {price:,.0f}원 (신뢰도 {sig['confidence']}%)",
                                    "info")

                            elif sig["action"] == "sell":
                                holding = next((h for h in portfolio["holdings"] if h["ticker"] == sig["ticker"]), None)
                                if holding and holding["qty"] > 0:
                                    sell_qty = min(qty, holding["qty"])
                                    total_amount = sell_qty * price
                                    pnl = (price - holding["avg_price"]) * sell_qty
                                    holding["qty"] -= sell_qty
                                    if holding["qty"] == 0:
                                        portfolio["holdings"] = [h for h in portfolio["holdings"] if h["ticker"] != sig["ticker"]]
                                    portfolio["cash"] += total_amount
                                    portfolio["updated_at"] = datetime.now(KST).isoformat()
                                    _save_data("trading_portfolio", portfolio)

                                    history = _load_data("trading_history", [])
                                    history.insert(0, {
                                        "id": f"auto_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{sig['ticker']}",
                                        "date": datetime.now(KST).isoformat(),
                                        "ticker": sig["ticker"], "name": sig["name"],
                                        "action": "sell", "qty": sell_qty, "price": price,
                                        "total": total_amount, "pnl": pnl,
                                        "strategy": f"CIO 자동매매 (신뢰도 {sig['confidence']}%)",
                                        "status": "executed", "market": sig.get("market", market),
                                    })
                                    _save_data("trading_history", history)

                                    pnl_str = f"{'+'if pnl>=0 else ''}{pnl:,.0f}원"
                                    save_activity_log("cio_manager",
                                        f"📉 자동매도: {sig['name']} {sell_qty}주 × {price:,.0f}원 (손익 {pnl_str})",
                                        "info")
                        except Exception as order_err:
                            logger.error("[TRADING BOT] 자동주문 오류: %s", order_err)

            buy_count = len([s for s in parsed_signals if s.get("action") == "buy"])
            sell_count = len([s for s in parsed_signals if s.get("action") == "sell"])
            logger.info("[TRADING BOT] CIO 분석 완료: 매수 %d, 매도 %d (비용 $%.4f)", buy_count, sell_count, cost)

        except Exception as e:
            logger.error("[TRADING BOT] 에러: %s", e)

    logger.info("자동매매 봇 루프 종료")


@app.post("/api/trading/portfolio/reset")
async def reset_trading_portfolio(request: Request):
    """포트폴리오 초기화 (모의투자 리셋)."""
    body = await request.json()
    initial_cash = body.get("initial_cash", 50_000_000)
    portfolio = {
        "cash": initial_cash,
        "initial_cash": initial_cash,
        "holdings": [],
        "updated_at": datetime.now(KST).isoformat(),
    }
    _save_data("trading_portfolio", portfolio)
    _save_data("trading_history", [])
    _save_data("trading_signals", [])
    save_activity_log("system", f"🔄 모의투자 리셋: 초기 자금 {initial_cash:,.0f}원", "info")
    return {"success": True, "portfolio": portfolio}


# ── 지식파일 관리 ──

@app.get("/api/knowledge")
async def get_knowledge():
    entries = []
    if KNOWLEDGE_DIR.exists():
        for folder in sorted(KNOWLEDGE_DIR.iterdir()):
            if folder.is_dir() and not folder.name.startswith("."):
                for f in sorted(folder.iterdir()):
                    if f.is_file() and f.suffix == ".md":
                        entries.append({
                            "folder": folder.name,
                            "filename": f.name,
                            "size": f.stat().st_size,
                            "modified": datetime.fromtimestamp(f.stat().st_mtime, KST).isoformat(),
                        })
    return {"entries": entries, "total": len(entries)}


@app.get("/api/knowledge/{folder}/{filename}")
async def get_knowledge_file(folder: str, filename: str):
    """지식 파일 내용 읽기."""
    file_path = KNOWLEDGE_DIR / folder / filename
    if file_path.exists() and file_path.is_file():
        content = file_path.read_text(encoding="utf-8")
        return {"folder": folder, "filename": filename, "content": content}
    return {"error": "not found"}


@app.post("/api/knowledge")
async def save_knowledge(request: Request):
    """지식 파일 저장/업로드."""
    body = await request.json()
    folder = body.get("folder", "shared")
    filename = body.get("filename", "untitled.md")
    content = body.get("content", "")
    folder_path = KNOWLEDGE_DIR / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    file_path = folder_path / filename
    file_path.write_text(content, encoding="utf-8")
    return {"success": True, "folder": folder, "filename": filename}


@app.delete("/api/knowledge/{folder}/{filename}")
async def delete_knowledge(folder: str, filename: str):
    """지식 파일 삭제."""
    file_path = KNOWLEDGE_DIR / folder / filename
    if file_path.exists() and file_path.is_file():
        file_path.unlink()
        return {"success": True}
    return {"success": False, "error": "not found"}


# ── 에이전트 메모리 관리 ──

@app.get("/api/memory/{agent_id}")
async def get_memory(agent_id: str):
    all_memories = _load_data("memories", {})
    return {"memories": all_memories.get(agent_id, [])}


@app.post("/api/memory/{agent_id}")
async def add_memory(agent_id: str, request: Request):
    """에이전트 메모리 추가."""
    body = await request.json()
    all_memories = _load_data("memories", {})
    if agent_id not in all_memories:
        all_memories[agent_id] = []
    memory_id = f"mem_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{len(all_memories[agent_id])}"
    memory = {
        "id": memory_id,
        "content": body.get("content", ""),
        "created_at": datetime.now(KST).isoformat(),
    }
    all_memories[agent_id].append(memory)
    _save_data("memories", all_memories)
    return {"success": True, "memory": memory}


@app.delete("/api/memory/{agent_id}/{memory_id}")
async def delete_memory(agent_id: str, memory_id: str):
    """에이전트 메모리 삭제."""
    all_memories = _load_data("memories", {})
    if agent_id in all_memories:
        all_memories[agent_id] = [m for m in all_memories[agent_id] if m.get("id") != memory_id]
        _save_data("memories", all_memories)
    return {"success": True}


# ── 피드백 ──

@app.get("/api/feedback")
async def get_feedback():
    return _load_data("feedback", {"good": 0, "bad": 0, "total": 0})


@app.post("/api/feedback")
async def send_feedback(request: Request):
    """피드백 전송/취소/변경.

    action 파라미터:
      - "send" (기본): 새 피드백 추가 (카운트 +1)
      - "cancel": 기존 피드백 취소 (카운트 -1)
      - "change": 기존 피드백 변경 (이전 카운트 -1 + 새 카운트 +1)
    """
    body = await request.json()
    feedback = _load_data("feedback", {"good": 0, "bad": 0, "total": 0})
    rating = body.get("rating", "")
    action = body.get("action", "send")  # "send", "cancel", "change"
    previous_rating = body.get("previous_rating")  # 변경 시 이전 값

    if not rating:
        return {"success": False, "error": "rating is required"}

    if action == "cancel":
        # 피드백 취소: 해당 카운트 1 감소 (0 이하로 내려가지 않음)
        if rating == "good":
            feedback["good"] = max(0, feedback.get("good", 0) - 1)
        elif rating == "bad":
            feedback["bad"] = max(0, feedback.get("bad", 0) - 1)
    elif action == "change":
        # 피드백 변경: 이전 피드백 카운트 1 감소 + 새 피드백 카운트 1 증가
        if previous_rating == "good":
            feedback["good"] = max(0, feedback.get("good", 0) - 1)
        elif previous_rating == "bad":
            feedback["bad"] = max(0, feedback.get("bad", 0) - 1)
        if rating == "good":
            feedback["good"] = feedback.get("good", 0) + 1
        elif rating == "bad":
            feedback["bad"] = feedback.get("bad", 0) + 1
    else:  # action == "send" (기본값)
        if rating == "good":
            feedback["good"] = feedback.get("good", 0) + 1
        elif rating == "bad":
            feedback["bad"] = feedback.get("bad", 0) + 1

    feedback["total"] = feedback.get("good", 0) + feedback.get("bad", 0)
    _save_data("feedback", feedback)
    return {"success": True, **feedback}


# ── 대화 ──

@app.get("/api/conversation")
async def get_conversation():
    """대화 기록을 DB에서 조회합니다."""
    messages = load_conversation_messages(limit=100)
    return messages


@app.post("/api/conversation/save")
async def save_conversation(data: dict = Body(...)):
    """대화 메시지를 DB에 저장합니다.

    요청 본문:
    - type: "user" 또는 "result"
    - user 타입: text 필드 필수
    - result 타입: content, sender_id 등 필드 전달
    """
    try:
        message_type = data.get("type")
        if not message_type:
            return {"success": False, "error": "type 필드가 필요합니다"}

        # type 제외한 나머지 필드들을 kwargs로 전달
        kwargs = {k: v for k, v in data.items() if k != "type"}

        row_id = save_conversation_message(message_type, **kwargs)
        return {"success": True, "id": row_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.delete("/api/conversation")
async def delete_conversation():
    """대화 기록을 모두 삭제합니다."""
    try:
        clear_conversation_messages()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 아카이브 (DB 기반 — 하단 activity-logs/archive API 섹션에서 정의됨) ──


# ── SNS 연동 (플레이스홀더 — 실제 연동은 외부 API 키 필요) ──

_SNS_PLATFORMS = ["instagram", "x", "youtube", "threads", "tiktok", "facebook"]


@app.get("/api/sns/status")
async def get_sns_status():
    """SNS 플랫폼 연결 상태."""
    return {p: {"connected": False, "username": ""} for p in _SNS_PLATFORMS}


@app.get("/api/sns/oauth/status")
async def get_sns_oauth_status():
    """SNS OAuth 인증 상태."""
    return {p: {"authenticated": False} for p in _SNS_PLATFORMS}


@app.get("/api/sns/auth/{platform}")
async def sns_auth(platform: str):
    """SNS 플랫폼 인증 (미구현 — OAuth 설정 필요)."""
    return {"success": False, "error": f"{platform} OAuth 연동이 아직 설정되지 않았습니다. API 키를 등록해주세요."}


@app.post("/api/sns/instagram/photo")
async def post_instagram_photo(request: Request):
    return {"success": False, "error": "인스타그램 API가 아직 연동되지 않았습니다."}


@app.post("/api/sns/instagram/reel")
async def post_instagram_reel(request: Request):
    return {"success": False, "error": "인스타그램 API가 아직 연동되지 않았습니다."}


@app.post("/api/sns/youtube/upload")
async def post_youtube_video(request: Request):
    return {"success": False, "error": "유튜브 API가 아직 연동되지 않았습니다."}


@app.get("/api/sns/queue")
async def get_sns_queue():
    """SNS 게시 대기열."""
    return _load_data("sns_queue", [])


@app.post("/api/sns/approve/{item_id}")
async def approve_sns(item_id: str):
    return {"success": False, "error": "SNS API가 아직 연동되지 않았습니다."}


@app.post("/api/sns/reject/{item_id}")
async def reject_sns(item_id: str):
    queue = _load_data("sns_queue", [])
    queue = [q for q in queue if q.get("id") != item_id]
    _save_data("sns_queue", queue)
    return {"success": True}


@app.get("/api/sns/events")
async def get_sns_events(limit: int = 50):
    """SNS 이벤트 로그."""
    return _load_data("sns_events", [])[:limit]


# ── 인증 (Phase 3: 비밀번호 로그인) ──

_sessions: dict[str, float] = {}  # token → 만료 시간
_SESSION_TTL = 86400 * 7  # 7일


def _check_auth(request: Request) -> bool:
    """요청의 인증 상태를 확인합니다."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.query_params.get("token", "")
    if token and token in _sessions:
        if _sessions[token] > time.time():
            return True
        del _sessions[token]
    return False


@app.post("/api/auth/login")
async def login(request: Request):
    """비밀번호 로그인."""
    body = await request.json()
    pw = body.get("password", "")
    stored_pw = load_setting("admin_password") or "corthex2026"
    if pw != stored_pw:
        return JSONResponse({"success": False, "error": "비밀번호가 틀립니다"}, status_code=401)
    token = str(_uuid.uuid4())
    _sessions[token] = time.time() + _SESSION_TTL
    return {"success": True, "token": token, "user": {"role": "ceo", "name": "CEO"}}


@app.post("/api/auth/logout")
async def logout(request: Request):
    """로그아웃."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token in _sessions:
        del _sessions[token]
    return {"success": True}


@app.get("/api/auth/check")
async def auth_check(request: Request):
    """토큰 유효성 확인."""
    if _check_auth(request):
        return {"authenticated": True, "role": "ceo"}
    return JSONResponse({"authenticated": False}, status_code=401)


@app.post("/api/auth/change-password")
async def change_password(request: Request):
    """비밀번호 변경."""
    if not _check_auth(request):
        return JSONResponse({"success": False, "error": "인증 필요"}, status_code=401)
    body = await request.json()
    current = body.get("current", "")
    new_pw = body.get("new_password", "")
    stored_pw = load_setting("admin_password") or "corthex2026"
    if current != stored_pw:
        return JSONResponse({"success": False, "error": "현재 비밀번호가 틀립니다"}, status_code=401)
    if len(new_pw) < 4:
        return {"success": False, "error": "비밀번호는 4자 이상이어야 합니다"}
    save_setting("admin_password", new_pw)
    return {"success": True}


# ── 헬스체크 ──

@app.get("/api/health")
async def health_check():
    """서버 상태 확인."""
    return {
        "status": "ok",
        "mode": "mini_server",
        "agents": len(AGENTS),
        "telegram": _telegram_available and _telegram_app is not None,
        "timestamp": datetime.now(KST).isoformat(),
    }


# 품질검수 규칙: DB 오버라이드 우선, 없으면 파일에서 로드
_QUALITY_RULES: dict = load_setting("config_quality_rules") or _load_config("quality_rules")

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


# ── 품질검수: 루브릭 저장/삭제 + 규칙 저장 ──

@app.put("/api/quality-rules/rubric/{division}")
async def save_rubric(division: str, request: Request):
    """부서별 루브릭(검수 기준) 저장."""
    body = await request.json()
    rubric = {
        "name": body.get("name", ""),
        "prompt": body.get("prompt", ""),
        "model": body.get("model", ""),
        "reasoning_effort": body.get("reasoning_effort", ""),
    }
    if "rubrics" not in _QUALITY_RULES:
        _QUALITY_RULES["rubrics"] = {}
    _QUALITY_RULES["rubrics"][division] = rubric
    _save_config_file("quality_rules", _QUALITY_RULES)
    return {"success": True, "division": division}


@app.delete("/api/quality-rules/rubric/{division}")
async def delete_rubric(division: str):
    """부서별 루브릭 삭제 (default는 삭제 불가)."""
    if division == "default":
        return {"success": False, "error": "기본 루브릭은 삭제할 수 없습니다"}
    rubrics = _QUALITY_RULES.get("rubrics", {})
    if division in rubrics:
        del rubrics[division]
        _save_config_file("quality_rules", _QUALITY_RULES)
    return {"success": True}


@app.put("/api/quality-rules/model")
async def save_review_model(request: Request):
    """품질검수에 사용할 AI 모델 변경."""
    body = await request.json()
    if "rules" not in _QUALITY_RULES:
        _QUALITY_RULES["rules"] = {}
    _QUALITY_RULES["rules"]["review_model"] = body.get("model", "gpt-4o-mini")
    _save_config_file("quality_rules", _QUALITY_RULES)
    return {"success": True}


@app.put("/api/quality-rules/rules")
async def save_quality_rules(request: Request):
    """품질검수 규칙 저장 (최소 길이, 재시도 횟수 등)."""
    body = await request.json()
    if "rules" not in _QUALITY_RULES:
        _QUALITY_RULES["rules"] = {}
    for key in ("min_length", "max_retry", "check_hallucination", "check_relevance", "review_model"):
        if key in body:
            _QUALITY_RULES["rules"][key] = body[key]
    _save_config_file("quality_rules", _QUALITY_RULES)
    return {"success": True}


# ── 에이전트 설정: 소울/모델/추론 저장 ──

@app.put("/api/agents/bulk-model")
async def bulk_change_model(request: Request):
    """모든 에이전트의 모델을 한번에 변경."""
    body = await request.json()
    new_model = body.get("model_name", "")
    reasoning = body.get("reasoning_effort", "")
    if not new_model:
        return {"error": "model_name 필수"}
    overrides = _load_data("agent_overrides", {})
    changed = 0
    for a in AGENTS:
        aid = a["agent_id"]
        a["model_name"] = new_model
        if aid in _AGENTS_DETAIL:
            _AGENTS_DETAIL[aid]["model_name"] = new_model
            _AGENTS_DETAIL[aid]["reasoning_effort"] = reasoning
        if aid not in overrides:
            overrides[aid] = {}
        overrides[aid]["model_name"] = new_model
        overrides[aid]["reasoning_effort"] = reasoning
        changed += 1
    _save_data("agent_overrides", overrides)
    return {"success": True, "changed": changed, "model_name": new_model, "reasoning_effort": reasoning}


@app.put("/api/agents/{agent_id}/soul")
async def save_agent_soul(agent_id: str, request: Request):
    """에이전트 소울(성격) 저장. DB에 영구 저장됨."""
    body = await request.json()
    soul_text = body.get("soul") or body.get("system_prompt", "")
    # DB에 저장 (재배포해도 유지)
    save_setting(f"soul_{agent_id}", soul_text)
    return {"success": True, "agent_id": agent_id}


@app.put("/api/agents/{agent_id}/model")
async def save_agent_model(agent_id: str, request: Request):
    """에이전트에 배정된 AI 모델 변경."""
    body = await request.json()
    new_model = body.get("model_name") or body.get("model", "")
    # 메모리 내 AGENTS 리스트 업데이트
    for a in AGENTS:
        if a["agent_id"] == agent_id:
            a["model_name"] = new_model
            break
    # agents.yaml 상세 정보도 업데이트
    if agent_id in _AGENTS_DETAIL:
        _AGENTS_DETAIL[agent_id]["model_name"] = new_model
    # 데이터 파일에 변경사항 저장 (서버 재시작 시 복원용)
    overrides = _load_data("agent_overrides", {})
    if agent_id not in overrides:
        overrides[agent_id] = {}
    overrides[agent_id]["model_name"] = new_model
    _save_data("agent_overrides", overrides)
    return {"success": True, "agent_id": agent_id, "model": new_model}


@app.put("/api/agents/{agent_id}/reasoning")
async def save_agent_reasoning(agent_id: str, request: Request):
    """에이전트 추론 방식(reasoning effort) 변경."""
    body = await request.json()
    effort = body.get("reasoning_effort", "")
    if agent_id in _AGENTS_DETAIL:
        _AGENTS_DETAIL[agent_id]["reasoning_effort"] = effort
    overrides = _load_data("agent_overrides", {})
    if agent_id not in overrides:
        overrides[agent_id] = {}
    overrides[agent_id]["reasoning_effort"] = effort
    _save_data("agent_overrides", overrides)
    return {"success": True, "agent_id": agent_id, "reasoning_effort": effort}


# ── 예산 설정 저장 ──

@app.put("/api/budget")
async def save_budget(request: Request):
    """일일 예산 한도 변경."""
    body = await request.json()
    if "daily_limit" in body:
        save_setting("daily_budget_usd", float(body["daily_limit"]))
    return {"success": True}


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
            "reasoning_levels": ["low", "medium", "high"],
        },
        {
            "name": "claude-sonnet-4-5-20250929",
            "provider": "anthropic",
            "tier": "manager",
            "cost_input": 3.0,
            "cost_output": 15.0,
            "reasoning_levels": ["low", "medium", "high"],
        },
        {
            "name": "claude-haiku-4-5-20251001",
            "provider": "anthropic",
            "tier": "specialist",
            "cost_input": 0.25,
            "cost_output": 1.25,
            "reasoning_levels": [],
        },
        # OpenAI (GPT) 모델들 - 임원급/매니저급/전문가급
        {
            "name": "gpt-5.2-pro",
            "provider": "openai",
            "tier": "executive",
            "cost_input": 18.0,
            "cost_output": 90.0,
            "reasoning_levels": ["medium", "high", "xhigh"],
        },
        {
            "name": "gpt-5.2",
            "provider": "openai",
            "tier": "manager",
            "cost_input": 5.0,
            "cost_output": 25.0,
            "reasoning_levels": ["none", "low", "medium", "high", "xhigh"],
        },
        {
            "name": "gpt-5.1",
            "provider": "openai",
            "tier": "manager",
            "cost_input": 4.0,
            "cost_output": 20.0,
            "reasoning_levels": ["none", "low", "medium", "high"],
        },
        {
            "name": "gpt-5",
            "provider": "openai",
            "tier": "specialist",
            "cost_input": 2.5,
            "cost_output": 10.0,
            "reasoning_levels": ["none", "low", "medium", "high"],
        },
        {
            "name": "gpt-5-mini",
            "provider": "openai",
            "tier": "specialist",
            "cost_input": 0.5,
            "cost_output": 2.0,
            "reasoning_levels": ["low", "medium", "high"],
        },
        # Google (Gemini) 모델들
        # Gemini 3: thinking_level 파라미터 (low/high만 지원)
        {
            "name": "gemini-3-pro-preview",
            "provider": "google",
            "tier": "executive",
            "cost_input": 2.5,
            "cost_output": 15.0,
            "reasoning_levels": ["low", "high"],
        },
        # Gemini 2.5: thinking_budget 파라미터 (토큰 수 조절)
        # 2.5 Pro: 최소 128 토큰, 끌 수 없음
        {
            "name": "gemini-2.5-pro",
            "provider": "google",
            "tier": "manager",
            "cost_input": 1.25,
            "cost_output": 10.0,
            "reasoning_levels": ["low", "medium", "high"],
        },
        # 2.5 Flash: 0~24576 토큰, 끌 수 있음 (budget=0)
        {
            "name": "gemini-2.5-flash",
            "provider": "google",
            "tier": "specialist",
            "cost_input": 0.15,
            "cost_output": 0.60,
            "reasoning_levels": ["none", "low", "medium", "high"],
        },
    ]


# ── 활동 로그 API ──
@app.get("/api/activity-logs")
async def get_activity_logs(limit: int = 50, agent_id: str = None):
    logs = list_activity_logs(limit=limit, agent_id=agent_id)
    return logs


# ── 아카이브 API ──
@app.get("/api/archive")
async def get_archive_list(division: str = None, limit: int = 100):
    return list_archives(division=division, limit=limit)


@app.get("/api/archive/{division}/{filename}")
async def get_archive_file(division: str, filename: str):
    doc = db_get_archive(division, filename)
    if not doc:
        return {"error": "not found"}
    return doc


# ── 진단 API (텔레그램 봇 디버깅용) ──
@app.get("/api/telegram-status")
async def telegram_status():
    """텔레그램 봇 진단 정보 반환."""
    return {
        **_diag,
        "tg_app_exists": _telegram_app is not None,
        "tg_available": _telegram_available,
        "env_token_set": bool(os.getenv("TELEGRAM_BOT_TOKEN", "")),
        "env_ceo_id": os.getenv("TELEGRAM_CEO_CHAT_ID", ""),
    }


# ── 텔레그램 봇 ──
# 주의: python-telegram-bot 미설치 시에도 서버가 정상 작동해야 함
# 모든 텔레그램 관련 코드는 _telegram_available 체크 후에만 실행

_telegram_app = None  # telegram.ext.Application 인스턴스


async def _start_telegram_bot() -> None:
    """텔레그램 봇을 시작합니다 (FastAPI 이벤트 루프 안에서 실행)."""
    global _telegram_app

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
        _telegram_app = Application.builder().token(token).build()

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
                "/agents — 에이전트 목록 (29명)\n"
                "/health — 서버 상태 확인\n"
                "/help — 이 사용법\n\n"
                "*모드 전환*\n"
                "/rt — 실시간 모드 (AI 즉시 답변)\n"
                "/batch — 배치 모드 (접수만)\n\n"
                "일반 메시지를 보내면 AI가 답변합니다.",
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
                    lines.append(f"  {icon} {a['name_ko']}")
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

        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not _is_tg_ceo(update):
                return
            text = update.message.text.strip()
            if not text:
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

            chat_id = str(update.effective_chat.id)
            # DB에 메시지 + 작업 저장
            task = create_task(text, source="telegram")
            save_message(text, source="telegram", chat_id=chat_id,
                         task_id=task["task_id"])

            # 모드 확인
            mode = load_setting("tg_mode") or "realtime"
            now = datetime.now(KST).strftime("%H:%M")
            result = {}  # 웹소켓 브로드캐스트용

            if mode == "realtime" and is_ai_ready():
                # 실시간 모드: AI가 답변
                update_task(task["task_id"], status="running")
                await update.message.reply_text(f"⏳ 처리 중... (#{task['task_id']})")

                result = await _process_ai_command(text, task["task_id"])

                if "error" in result:
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
                    # 비서실장 위임 표시: "비서실장 → CTO" 또는 "비서실장"
                    footer_who = delegation if delegation else "비서실장"
                    await update.message.reply_text(
                        f"{content}\n\n"
                        f"─────\n"
                        f"👤 {footer_who} | 💰 ${cost:.4f} | 🤖 {model_short}",
                        parse_mode=None,
                    )
            else:
                # 배치 모드 또는 AI 미준비
                update_task(task["task_id"], status="completed",
                            result_summary="배치 모드 — 접수만 완료" if mode == "batch" else "AI 미연결 — 접수만 완료",
                            success=1, time_seconds=0.1)
                reason = "배치 모드" if mode == "batch" else "AI 미연결"
                await update.message.reply_text(
                    f"📋 접수했습니다. ({now})\n"
                    f"작업 ID: `{task['task_id']}`\n"
                    f"상태: {reason}",
                    parse_mode="Markdown",
                )

            # 활동 로그 저장 + 웹소켓 브로드캐스트 (웹 채팅에도 대화 표시)
            log_entry = save_activity_log(
                "chief_of_staff",
                f"[텔레그램] CEO 지시: {text[:50]}{'...' if len(text) > 50 else ''} (#{task['task_id']})",
            )
            for ws in connected_clients[:]:
                try:
                    await ws.send_json({"event": "task_accepted", "data": task})
                    await ws.send_json({"event": "activity_log", "data": log_entry})
                    # 텔레그램 대화를 웹 채팅에도 표시
                    await ws.send_json({
                        "event": "telegram_message",
                        "data": {"type": "user", "text": text, "source": "telegram"}
                    })
                    if "error" not in result:
                        await ws.send_json({
                            "event": "result",
                            "data": {
                                "content": result.get("content", ""),
                                "sender_id": result.get("agent_id", "chief_of_staff"),
                                "handled_by": result.get("handled_by", "비서실장"),
                                "delegation": result.get("delegation", ""),
                                "time_seconds": result.get("time_seconds", 0),
                                "cost": result.get("total_cost_usd", result.get("cost_usd", 0)),
                                "model": result.get("model", ""),
                                "routing_method": result.get("routing_method", ""),
                                "source": "telegram",
                            }
                        })
                    else:
                        await ws.send_json({
                            "event": "result",
                            "data": {
                                "content": f"❌ {result['error']}",
                                "sender_id": "chief_of_staff",
                                "handled_by": "비서실장",
                                "time_seconds": 0, "cost": 0,
                                "source": "telegram",
                            }
                        })
                except Exception:
                    pass

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

        # 핸들러 등록
        _telegram_app.add_handler(CommandHandler("start", cmd_start))
        _telegram_app.add_handler(CommandHandler("help", cmd_help))
        _telegram_app.add_handler(CommandHandler("agents", cmd_agents))
        _telegram_app.add_handler(CommandHandler("health", cmd_health))
        _telegram_app.add_handler(CommandHandler("rt", cmd_rt))
        _telegram_app.add_handler(CommandHandler("batch", cmd_batch))
        _telegram_app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )

        # 봇 명령어 메뉴 설정
        await _telegram_app.bot.set_my_commands([
            BotCommand("start", "봇 시작"),
            BotCommand("help", "사용법"),
            BotCommand("agents", "에이전트 목록"),
            BotCommand("health", "서버 상태"),
            BotCommand("rt", "실시간 모드 (AI 즉시 답변)"),
            BotCommand("batch", "배치 모드 (접수만)"),
        ])

        _log("[TG] 핸들러 등록 완료, initialize()...")
        await _telegram_app.initialize()
        _log("[TG] start()...")
        await _telegram_app.start()
        _log("[TG] polling 시작...")
        await _telegram_app.updater.start_polling(drop_pending_updates=True)

        ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
        _diag["tg_started"] = True
        _log(f"[TG] ✅ 봇 시작 완료! (CEO: {ceo_id or '미설정'})")
    except Exception as e:
        _diag["tg_error"] = str(e)
        _log(f"[TG] ❌ 봇 시작 실패: {e}")
        import traceback
        traceback.print_exc()
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


# ── AI 에이전트 위임 시스템 (Phase 5) ──

# 부서별 키워드 라우팅 테이블
_ROUTING_KEYWORDS: dict[str, list[str]] = {
    "cto_manager": [
        "코드", "버그", "프론트", "백엔드", "API", "서버", "배포",
        "웹사이트", "홈페이지", "디자인", "UI", "UX", "데이터베이스",
        "개발", "프로그래밍", "깃허브", "github", "리팩토링",
    ],
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
    "cto_manager": "CTO (기술개발처장)",
    "cso_manager": "CSO (사업기획처장)",
    "clo_manager": "CLO (법무IP처장)",
    "cmo_manager": "CMO (마케팅고객처장)",
    "cio_manager": "CIO (투자분석처장)",
    "cpo_manager": "CPO (출판기록처장)",
}

# ── 노션 API 연동 (에이전트 산출물 자동 저장) ──

_NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
_NOTION_DB_ID = os.getenv("NOTION_DEFAULT_DB_ID", "ee0527e4-697b-4cb6-8df0-6dca3f59ad4e")

# 에이전트 ID → 부서명 매핑
_AGENT_DIVISION: dict[str, str] = {}
for _a in AGENTS:
    if _a.get("division"):
        _AGENT_DIVISION[_a["agent_id"]] = _a["division"]


async def _save_to_notion(agent_id: str, title: str, content: str,
                          report_type: str = "보고서") -> str | None:
    """에이전트 산출물을 노션 DB에 저장합니다.

    Python 기본 라이브러리(urllib)만 사용 — 추가 패키지 불필요.
    실패해도 에러만 로깅하고 None 반환 (서버 동작에 영향 없음).
    """
    if not _NOTION_API_KEY:
        return None

    division = _AGENT_DIVISION.get(agent_id, "")
    agent_name = _AGENT_NAMES.get(agent_id, _SPECIALIST_NAMES.get(agent_id, agent_id))
    now_str = datetime.now(KST).strftime("%Y-%m-%d")

    # 노션 페이지 프로퍼티 구성
    properties: dict = {
        "Name": {"title": [{"text": {"content": title[:100]}}]},
    }
    # 선택 속성들 (DB에 해당 컬럼이 없으면 노션이 무시함)
    if agent_name:
        properties["Agent"] = {"rich_text": [{"text": {"content": agent_name}}]}
    if division:
        properties["Division"] = {"rich_text": [{"text": {"content": division}}]}
    if report_type:
        properties["Type"] = {"rich_text": [{"text": {"content": report_type}}]}
    properties["Status"] = {"rich_text": [{"text": {"content": "완료"}}]}

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
        "parent": {"database_id": _NOTION_DB_ID},
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
            err_body = e.read().decode("utf-8", errors="replace")[:200]
            _log(f"[Notion] HTTP {e.code} 오류: {err_body}")
            return None
        except Exception as e:
            _log(f"[Notion] 요청 실패: {e}")
            return None

    try:
        result = await asyncio.to_thread(_do_request)
        if result and result.get("url"):
            _log(f"[Notion] 저장 완료: {title[:50]} → {result['url']}")
            return result["url"]
    except Exception as e:
        _log(f"[Notion] 비동기 실행 실패: {e}")

    return None


# 브로드캐스트 키워드 (모든 부서에 동시 전달하는 명령)
_BROADCAST_KEYWORDS = [
    "전체", "모든 부서", "출석", "회의", "현황 보고",
    "총괄", "전원", "각 부서", "출석체크", "브리핑",
]

# 처장 → 소속 전문가 매핑
_MANAGER_SPECIALISTS: dict[str, list[str]] = {
    "cto_manager": ["frontend_specialist", "backend_specialist", "infra_specialist", "ai_model_specialist"],
    "cso_manager": ["market_research_specialist", "business_plan_specialist", "financial_model_specialist"],
    "clo_manager": ["copyright_specialist", "patent_specialist"],
    "cmo_manager": ["survey_specialist", "content_specialist", "community_specialist"],
    "cio_manager": ["market_condition_specialist", "stock_analysis_specialist", "technical_analysis_specialist", "risk_management_specialist"],
    "cpo_manager": ["chronicle_specialist", "editor_specialist", "archive_specialist"],
}

# 전문가 ID → 한국어 이름 (AGENTS 리스트에서 자동 구축)
_SPECIALIST_NAMES: dict[str, str] = {}
for _a in AGENTS:
    if _a["role"] == "specialist":
        _SPECIALIST_NAMES[_a["agent_id"]] = _a["name_ko"]


def _is_broadcast_command(text: str) -> bool:
    """브로드캐스트 명령인지 확인합니다."""
    return any(kw in text for kw in _BROADCAST_KEYWORDS)


async def _broadcast_status(agent_id: str, status: str, progress: float, detail: str = ""):
    """에이전트 상태를 모든 WebSocket 클라이언트에게 전송합니다.

    프론트엔드의 상태 표시등(초록불 깜빡임)을 제어합니다.
    status: 'working' | 'done' | 'idle'
    """
    for c in connected_clients[:]:
        try:
            await c.send_json({
                "event": "agent_status",
                "data": {
                    "agent_id": agent_id,
                    "status": status,
                    "progress": progress,
                    "detail": detail,
                }
            })
        except Exception:
            pass


async def _call_agent(agent_id: str, text: str) -> dict:
    """단일 에이전트에게 AI 호출을 수행합니다 (상태 이벤트 + 활동 로그 + 도구 자동호출 포함)."""
    agent_name = _AGENT_NAMES.get(agent_id, _SPECIALIST_NAMES.get(agent_id, agent_id))
    await _broadcast_status(agent_id, "working", 0.2, f"{agent_name} 분석 중...")

    # 활동 로그 — 누가 일하는지 기록
    log_entry = save_activity_log(agent_id, f"[{agent_name}] 작업 시작: {text[:40]}...")
    for c in connected_clients[:]:
        try:
            await c.send_json({"event": "activity_log", "data": log_entry})
        except Exception:
            pass

    soul = _load_agent_prompt(agent_id)
    override = _get_model_override(agent_id)
    model = select_model(text, override=override)

    # ── 도구 자동호출 (Function Calling) ──
    # 에이전트별 허용 도구 목록으로 스키마를 로드하고, 도구 실행 함수를 전달
    tool_schemas = None
    tool_executor_fn = None
    detail = _AGENTS_DETAIL.get(agent_id, {})
    allowed = detail.get("allowed_tools", [])
    if allowed:
        schemas = _load_tool_schemas(allowed_tools=allowed)
        if schemas.get("anthropic"):
            tool_schemas = schemas["anthropic"]  # ask_ai 내부에서 프로바이더별 변환

            async def _tool_executor(tool_name: str, tool_input: dict):
                """ToolPool을 통해 도구를 실행합니다."""
                pool = _init_tool_pool()
                if pool and hasattr(pool, '_tools') and tool_name in pool._tools:
                    await _broadcast_status(agent_id, "working", 0.5, f"🔧 {tool_name} 도구 실행 중...")
                    tool_obj = pool._tools[tool_name]
                    # 도구의 execute 메서드 호출
                    if asyncio.iscoroutinefunction(getattr(tool_obj, 'execute', None)):
                        return await tool_obj.execute(**tool_input)
                    elif hasattr(tool_obj, 'execute'):
                        return await asyncio.to_thread(tool_obj.execute, **tool_input)
                # ToolPool에 없으면 단순 설명 반환
                return f"도구 '{tool_name}'을(를) 찾을 수 없습니다."

            tool_executor_fn = _tool_executor

    result = await ask_ai(text, system_prompt=soul, model=model,
                          tools=tool_schemas, tool_executor=tool_executor_fn)

    if "error" in result:
        await _broadcast_status(agent_id, "done", 1.0, "오류 발생")
        return {"agent_id": agent_id, "name": agent_name, "error": result["error"], "cost_usd": 0}

    await _broadcast_status(agent_id, "done", 1.0, "완료")

    # 완료 로그
    cost = result.get("cost_usd", 0)
    content = result.get("content", "")
    log_done = save_activity_log(agent_id, f"[{agent_name}] 작업 완료 (${cost:.4f})")
    for c in connected_clients[:]:
        try:
            await c.send_json({"event": "activity_log", "data": log_done})
        except Exception:
            pass

    # 산출물 저장 (노션 + 아카이브 DB)
    if content and len(content) > 20:
        # 노션에 저장 (비동기, 실패해도 무시)
        asyncio.create_task(_save_to_notion(
            agent_id=agent_id,
            title=f"[{agent_name}] {text[:50]}",
            content=content,
        ))
        # 아카이브 DB에 저장 (영구 보관)
        division = _AGENT_DIVISION.get(agent_id, "secretary")
        now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        archive_content = f"# [{agent_name}] {text[:60]}\n\n{content}"
        save_archive(
            division=division,
            filename=f"{agent_id}_{now_str}.md",
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
    }


async def _delegate_to_specialists(manager_id: str, text: str) -> list[dict]:
    """처장이 소속 전문가들에게 병렬로 위임합니다.

    asyncio.gather로 전문가들을 동시에 호출 → 상태 표시등 전부 깜빡임.
    """
    specialists = _MANAGER_SPECIALISTS.get(manager_id, [])
    if not specialists:
        return []

    tasks = [_call_agent(spec_id, text) for spec_id in specialists]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed = []
    for i, r in enumerate(results):
        spec_id = specialists[i]
        if isinstance(r, Exception):
            processed.append({"agent_id": spec_id, "name": _SPECIALIST_NAMES.get(spec_id, spec_id), "error": str(r)[:100], "cost_usd": 0})
        else:
            processed.append(r)
    return processed


async def _manager_with_delegation(manager_id: str, text: str) -> dict:
    """처장이 전문가에게 위임 → 결과 종합(검수) → 보고서 작성.

    흐름: 처장 분석 시작 → 전문가 병렬 호출 → 처장이 결과 종합 + 검수 → 보고서 반환
    검수: 처장이 전문가 결과를 읽고 종합하는 과정 자체가 품질 검수 역할을 합니다.
    """
    mgr_name = _AGENT_NAMES.get(manager_id, manager_id)
    specialists = _MANAGER_SPECIALISTS.get(manager_id, [])
    spec_names = [_SPECIALIST_NAMES.get(s, s) for s in specialists]

    # 처장 상태: 명령 분석 중
    await _broadcast_status(manager_id, "working", 0.1, "명령 분석 → 전문가 위임 중...")

    # 처장 활동 로그 — 전문가에게 위임
    if specialists:
        log_mgr = save_activity_log(manager_id, f"[{mgr_name}] 전문가 {len(specialists)}명에게 위임: {', '.join(spec_names)}")
        for c in connected_clients[:]:
            try:
                await c.send_json({"event": "activity_log", "data": log_mgr})
            except Exception:
                pass

    # 전문가들에게 병렬 위임
    spec_results = await _delegate_to_specialists(manager_id, text)

    if not spec_results:
        # 전문가가 없으면 처장이 직접 처리
        return await _call_agent(manager_id, text)

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

    # 처장이 종합 + 검수 (전문가 결과를 읽고 CEO에게 보고서 작성)
    synthesis_prompt = (
        f"당신은 {mgr_name}입니다. 소속 전문가들이 아래 분석 결과를 제출했습니다.\n"
        f"이를 검수하고 종합하여 CEO에게 보고할 간결한 보고서를 작성하세요.\n"
        f"전문가 의견 중 부족하거나 잘못된 부분이 있으면 지적하고 보완하세요.\n\n"
        f"## CEO 원본 명령\n{text}\n\n"
        f"## 전문가 분석 결과\n" + "\n\n".join(spec_parts)
    )

    soul = _load_agent_prompt(manager_id)
    override = _get_model_override(manager_id)
    model = select_model(synthesis_prompt, override=override)

    await _broadcast_status(manager_id, "working", 0.7, "전문가 결과 검수 + 종합 중...")
    synthesis = await ask_ai(synthesis_prompt, system_prompt=soul, model=model)

    await _broadcast_status(manager_id, "done", 1.0, "보고 완료")

    if "error" in synthesis:
        # 종합 실패 시 전문가 결과만 반환
        content = f"**{mgr_name} 전문가 분석 결과**\n\n" + "\n\n---\n\n".join(spec_parts)
        return {"agent_id": manager_id, "name": mgr_name, "content": content, "cost_usd": spec_cost}

    total_cost = spec_cost + synthesis.get("cost_usd", 0)
    specialists_used = len([r for r in spec_results if "error" not in r])
    synth_content = synthesis.get("content", "")

    # 종합 보고서 저장 (노션 + 아카이브 DB)
    if synth_content and len(synth_content) > 20:
        asyncio.create_task(_save_to_notion(
            agent_id=manager_id,
            title=f"[{mgr_name}] 종합보고: {text[:40]}",
            content=synth_content,
            report_type="종합보고서",
        ))
        # 아카이브 DB에 저장
        division = _AGENT_DIVISION.get(manager_id, "secretary")
        now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        archive_content = f"# [{mgr_name}] 종합보고: {text[:50]}\n\n{synth_content}"
        save_archive(
            division=division,
            filename=f"{manager_id}_synthesis_{now_str}.md",
            content=archive_content,
            agent_id=manager_id,
        )

    return {
        "agent_id": manager_id,
        "name": mgr_name,
        "content": synth_content,
        "cost_usd": total_cost,
        "model": synthesis.get("model", ""),
        "time_seconds": round(spec_time + synthesis.get("time_seconds", 0), 2),
        "specialists_used": specialists_used,
    }


async def _broadcast_to_managers(text: str, task_id: str) -> dict:
    """전체 부서 브로드캐스트.

    비서실장 → 6개 처장에게 명령 전달.
    각 처장은 자기 소속 전문가들에게 위임 → 결과 검수 → 종합 보고서 작성.
    비서실장은 처장만 호출하고, 전문가는 처장이 알아서 호출합니다.
    """
    managers = ["cto_manager", "cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]

    # 비서실장 상태: 전달 중
    await _broadcast_status("chief_of_staff", "working", 0.1, "6개 부서 처장에게 명령 하달 중...")

    # 활동 로그 — 비서실장이 처장들에게 전달
    log_entry = save_activity_log("chief_of_staff", f"[비서실장] 6개 처장에게 명령 전달: {text[:40]}...")
    for c in connected_clients[:]:
        try:
            await c.send_json({"event": "activity_log", "data": log_entry})
        except Exception:
            pass

    # 6개 처장 동시 호출 (각 처장이 자기 전문가를 알아서 호출 + 검수)
    tasks = [_manager_with_delegation(mgr_id, text) for mgr_id in managers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 결과 종합
    compiled_parts = []
    total_cost = 0.0
    total_time = 0.0
    success_count = 0
    total_specialists = 0

    for i, result in enumerate(results):
        mgr_id = managers[i]
        mgr_name = _AGENT_NAMES.get(mgr_id, mgr_id)

        if isinstance(result, Exception):
            compiled_parts.append(f"### ❌ {mgr_name}\n오류: {str(result)[:100]}")
        elif "error" in result:
            compiled_parts.append(f"### ❌ {mgr_name}\n{result['error'][:200]}")
        else:
            specs = result.get("specialists_used", 0)
            total_specialists += specs
            spec_label = f" (전문가 {specs}명 동원)" if specs else ""
            compiled_parts.append(f"### 📋 {mgr_name}{spec_label}\n{result.get('content', '응답 없음')}")
            total_cost += result.get("cost_usd", 0)
            total_time = max(total_time, result.get("time_seconds", 0))
            success_count += 1

    # 비서실장 완료
    await _broadcast_status("chief_of_staff", "done", 1.0, "종합 완료")

    compiled_content = (
        f"📢 **전체 부서 브로드캐스트 결과** (6개 처장 + 전문가 {total_specialists}명 동원)\n\n"
        f"비서실장 → 6개 처장에게 명령 전달 → 각 처장이 소속 전문가를 호출하여 결과를 종합했습니다.\n\n---\n\n"
        + "\n\n---\n\n".join(compiled_parts)
    )

    # DB 업데이트
    update_task(task_id, status="completed",
                result_summary=f"브로드캐스트 완료 ({success_count}/6 부서 보고, 전문가 {total_specialists}명)",
                result_data=compiled_content,
                success=1,
                cost_usd=total_cost,
                time_seconds=round(total_time, 2),
                agent_id="chief_of_staff")

    return {
        "content": compiled_content,
        "agent_id": "chief_of_staff",
        "handled_by": "비서실장 → 6개 처장",
        "delegation": "비서실장 → 처장 → 전문가",
        "total_cost_usd": round(total_cost, 6),
        "time_seconds": round(total_time, 2),
        "model": "multi-agent",
        "routing_method": "브로드캐스트",
    }


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


def _load_agent_prompt(agent_id: str) -> str:
    """에이전트의 시스템 프롬프트(소울) + 도구 정보를 로드합니다.

    우선순위: DB 오버라이드 > souls/*.md 파일 > agents.yaml system_prompt > 기본값
    마지막에 할당된 도구 설명을 자동으로 추가합니다.
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
            except Exception:
                pass

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

    # 도구 설명 추가 (에이전트가 자신의 도구를 인지하고 활용할 수 있게)
    tools_desc = _get_tool_descriptions(agent_id)
    if tools_desc:
        prompt += tools_desc

    return prompt


_chief_prompt: str = ""


def _load_chief_prompt() -> None:
    """비서실장 시스템 프롬프트를 로드합니다 (서버 시작 시 캐시)."""
    global _chief_prompt
    _chief_prompt = _load_agent_prompt("chief_of_staff")
    _log("[AI] 비서실장 프롬프트 로드 완료")


def _get_model_override(agent_id: str) -> str | None:
    """모델 모드에 따라 에이전트의 모델을 결정합니다.

    - 자동 모드: None 반환 → select_model()이 질문 내용에 따라 자동 선택
    - 수동 모드: 해당 에이전트에 개별 지정된 모델을 반환
      (에이전트 상세에서 CEO가 직접 설정한 모델)
    """
    mode = load_setting("model_mode") or "auto"
    if mode != "manual":
        return None
    # 수동 모드 → 에이전트별 개별 지정 모델 사용
    detail = _AGENTS_DETAIL.get(agent_id, {})
    agent_model = detail.get("model_name")
    if agent_model:
        return agent_model
    # AGENTS 리스트에서도 확인
    for a in AGENTS:
        if a["agent_id"] == agent_id and a.get("model_name"):
            return a["model_name"]
    return None


async def _process_ai_command(text: str, task_id: str) -> dict:
    """CEO 명령을 적합한 에이전트에게 위임하고 AI 결과를 반환합니다.

    흐름:
      예산 확인 → 브로드캐스트 확인 → 라우팅(분류) → 상태 전송
      → 처장+전문가 풀 체인 위임 → 검수 → DB 저장

    브로드캐스트 모드: "전체", "출석체크" 등 → 29명 동시 가동
    단일 위임 모드: 키워드/AI 분류 → 처장+전문가 체인 호출
    직접 처리: 비서실장이 직접 답변 (단순 질문)
    """
    # 1) 예산 확인
    limit = float(load_setting("daily_budget_usd") or 7.0)
    today = get_today_cost()
    if today >= limit:
        update_task(task_id, status="failed",
                    result_summary=f"일일 예산 초과 (${today:.2f}/${limit:.0f})",
                    success=0)
        return {"error": f"일일 예산을 초과했습니다 (${today:.2f}/${limit:.0f})"}

    # 1.5) 배치 특수 명령 처리
    text_lower = text.strip().lower()
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

    # 2) 브로드캐스트 명령 확인 → 29명 동시 가동
    if _is_broadcast_command(text):
        return await _broadcast_to_managers(text, task_id)

    # 3) 라우팅 — 적합한 에이전트 결정
    routing = await _route_task(text)
    target_id = routing["agent_id"]
    routing_cost = routing.get("cost_usd", 0)

    # 4) 비서실장 직접 처리 (일반 질문, 인사 등)
    if target_id == "chief_of_staff":
        await _broadcast_status("chief_of_staff", "working", 0.2, "직접 처리 중...")
        soul = _chief_prompt if _chief_prompt else _load_agent_prompt("chief_of_staff")
        override = _get_model_override("chief_of_staff")
        model = select_model(text, override=override)
        result = await ask_ai(text, system_prompt=soul, model=model)

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

    # 5) 부서 위임 — 비서실장 → 처장 → 전문가
    target_name = _AGENT_NAMES.get(target_id, target_id)
    await _broadcast_status("chief_of_staff", "working", 0.1, f"{target_name}에게 위임 중...")

    # 처장이 자기 전문가를 호출 → 결과 검수 → 종합 보고서
    delegation_result = await _manager_with_delegation(target_id, text)

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
    global _tool_pool
    if _tool_pool is not None:
        return _tool_pool if _tool_pool else None

    try:
        from src.tools.pool import ToolPool
        from src.llm.base import LLMResponse

        class _MiniModelRouter:
            """ask_ai()를 ModelRouter.complete() 인터페이스로 감싸는 어댑터."""

            class cost_tracker:
                """더미 비용 추적기 (mini_server는 자체 비용 추적 사용)."""
                @staticmethod
                def record(*args, **kwargs):
                    pass

            async def complete(self, model_name="", messages=None,
                             temperature=0.3, max_tokens=4096,
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
        _tool_pool = pool
        _log(f"[TOOLS] ToolPool 초기화 완료: {loaded}개 도구 로드 ✅")
        return pool

    except Exception as e:
        _log(f"[TOOLS] ToolPool 초기화 실패 (도구 목록만 표시): {e}")
        _tool_pool = False
        return None


@app.post("/api/tools/{tool_id}/execute")
async def execute_tool(tool_id: str, request: Request):
    """도구를 직접 실행합니다.

    요청 body: {"action": "...", "query": "...", ...} (도구별 상이)
    응답: {"result": "...", "tool_id": "...", "cost_usd": 0.0}
    """
    pool = _init_tool_pool()
    if not pool:
        return JSONResponse(
            {"error": "도구 실행 엔진 미초기화 (ToolPool 로드 실패)"},
            status_code=503,
        )

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        result = await pool.invoke(tool_id, caller_id="ceo_direct", **body)
        return {"result": result, "tool_id": tool_id, "status": "ok"}
    except Exception as e:
        return JSONResponse(
            {"error": f"도구 실행 오류: {str(e)[:300]}", "tool_id": tool_id},
            status_code=400,
        )


@app.get("/api/tools/status")
async def get_tools_status():
    """로드된 도구 목록과 ToolPool 상태를 반환합니다."""
    pool = _init_tool_pool()
    if not pool:
        return {
            "pool_status": "unavailable",
            "loaded_tools": [],
            "total_defined": len(_TOOLS_LIST),
        }

    loaded = list(pool._tools.keys())
    return {
        "pool_status": "ready",
        "loaded_tools": loaded,
        "loaded_count": len(loaded),
        "total_defined": len(_TOOLS_LIST),
    }


@app.on_event("startup")
async def on_startup():
    """서버 시작 시 DB 초기화 + AI 클라이언트 + 텔레그램 봇 + 크론 엔진 + 도구 풀 시작."""
    init_db()
    _load_chief_prompt()
    ai_ok = init_ai_client()
    _log(f"[AI] 클라이언트 초기화: {'성공 ✅' if ai_ok else '실패 ❌ (ANTHROPIC_API_KEY 미설정?)'}")
    await _start_telegram_bot()
    # 크론 실행 엔진 시작
    global _cron_task
    _cron_task = asyncio.create_task(_cron_loop())
    _log("[CRON] 크론 실행 엔진 시작 ✅")
    # 도구 실행 엔진 초기화 (비동기 아닌 동기 — 첫 요청 시 lazy 로드도 지원)
    _init_tool_pool()
    # PENDING 배치 또는 진행 중인 체인이 있으면 폴러 시작
    pending_batches = load_setting("pending_batches") or []
    active_batches = [b for b in pending_batches if b.get("status") in ("pending", "processing")]
    chains = load_setting("batch_chains") or []
    active_chains = [c for c in chains if c.get("status") in ("running", "pending")]
    if active_batches or active_chains:
        _ensure_batch_poller()
        _log(f"[BATCH] 미완료 배치 {len(active_batches)}개 + 체인 {len(active_chains)}개 감지 — 폴러 자동 시작")


@app.on_event("shutdown")
async def on_shutdown():
    """서버 종료 시 텔레그램 봇도 함께 종료."""
    await _stop_telegram_bot()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
