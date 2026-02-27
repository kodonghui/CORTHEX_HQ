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
try:
    from src.core.quality_gate import QualityGate, HybridReviewResult
    from src.llm.base import LLMResponse
    _QUALITY_GATE_AVAILABLE = True
except ImportError:
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

# Python 출력 버퍼링 비활성화 (systemd에서 로그가 바로 보이도록)
os.environ["PYTHONUNBUFFERED"] = "1"

# 진단 정보 수집용 → app_state.diag 사용
_diag = app_state.diag
_diag.update({"env_file": "", "env_count": 0,
              "tg_import": False, "tg_import_error": "",
              "tg_token_found": False, "tg_started": False, "tg_error": ""})


def _log(msg: str) -> None:
    """디버그 로그 출력 (stdout + stderr 양쪽에 flush)."""
    print(msg, flush=True)
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


_RE_MD_HEADER = re.compile(r'^#{1,3}\s+(.+)', re.MULTILINE)
_RE_SENTENCE_END = re.compile(r'[.!?。]\s')

def _extract_title_summary(content: str) -> str:
    """AI 응답 content에서 작전일지 제목으로 쓸 1줄 요약을 추출한다.
    우선순위: ① 마크다운 헤더(#~###) ② 첫 문장(50자) ③ 앞 80자 잘라내기
    """
    if not content:
        return ""
    text = content.strip()
    # ① 마크다운 헤더 추출
    m = _RE_MD_HEADER.search(text)
    if m:
        title = m.group(1).strip().rstrip('#').strip()
        if len(title) > 80:
            title = title[:77] + "..."
        return title
    # ② 첫 문장 추출 (마침표/느낌표/물음표 기준)
    first_line = text.split('\n')[0].strip()
    # 이모지/특수문자로 시작하면 스킵하고 본문 찾기
    if first_line:
        m2 = _RE_SENTENCE_END.search(first_line)
        if m2 and m2.end() <= 80:
            return first_line[:m2.end()].strip()
        if len(first_line) <= 80:
            return first_line
    # ③ 앞 80자 잘라내기
    return text[:77].rstrip() + "..." if len(text) > 80 else text


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

# ── ToolPool → app_state.tool_pool 직접 사용 ──

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("corthex.arm_server")

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

KST = timezone(timedelta(hours=9))

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
            # 보험: YAML 읽은 후 JSON도 자동 생성 (다음 기동 시 1순위로 바로 로드)
            try:
                json_path.write_text(
                    json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                logger.info("%s.yaml → %s.json 자동 변환 완료", name, name)
            except Exception as e:
                logger.debug("YAML→JSON 변환 저장 실패: %s", e)
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
        except Exception as e:
            logger.debug("JSON→DB 마이그레이션 실패 (%s): %s", name, e)
    return default if default is not None else {}


def _save_data(name: str, data) -> None:
    """DB에 설정 데이터 저장."""
    save_setting(name, data)


def _save_config_file(name: str, data: dict) -> None:
    """설정 변경을 DB에 저장. (재배포해도 유지됨)"""
    save_setting(f"config_{name}", data)


def _sync_agent_defaults_to_db():
    """agents.yaml의 신규 에이전트만 agent_overrides DB에 추가.
    이미 DB에 존재하는 에이전트는 건드리지 않음 (사용자가 수동 변경한 모델 유지)."""
    try:
        agents_config = _load_config("agents")
        if not agents_config:
            return
        agents_list = agents_config.get("agents", [])

        overrides = _load_data("agent_overrides", {})
        changed = False

        for agent_data in agents_list:
            agent_id = agent_data.get("agent_id")
            if not agent_id:
                continue
            model_name = agent_data.get("model_name") or agent_data.get("model")
            reasoning = agent_data.get("reasoning_effort") or agent_data.get("reasoning")
            if not model_name:
                continue
            # DB에 없는 신규 에이전트만 yaml 기본값 적용 (기존 값은 보존)
            if agent_id not in overrides:
                overrides[agent_id] = {"model_name": model_name}
                if reasoning:
                    overrides[agent_id]["reasoning_effort"] = reasoning
                changed = True

        if changed:
            _save_data("agent_overrides", overrides)
            logger.info("agent_overrides DB 동기화: 신규 에이전트 %d건 추가", changed)
    except Exception as e:
        logger.warning("agent_overrides 동기화 실패: %s", e)


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


# 모델별 기본 추론 레벨 자동 매핑 (최신 2026년 기준)
MODEL_REASONING_MAP: dict[str, str] = {
    "claude-haiku-4-5-20251001": "low",
    "claude-sonnet-4-6":       "medium",
    "claude-opus-4-6":         "high",
    "gemini-3.1-pro-preview":    "high",
    "gemini-2.5-pro":          "high",
    "gpt-5.2":                 "high",
    "gpt-5.2-pro":             "xhigh",
    "gpt-5":                   "high",
    "gpt-5-mini":              "medium",
    "o3":                      "high",
    "o4-mini":                 "medium",
}

# 모델별 최대 출력 토큰 한도 (공식 API 기준, 2026년 2월)
MODEL_MAX_TOKENS_MAP: dict[str, int] = {
    "claude-haiku-4-5-20251001": 64000,
    "claude-sonnet-4-6":         64000,
    "claude-opus-4-6":           64000,
    "gemini-3.1-pro-preview":      64000,
    "gemini-2.5-pro":            65536,
    "gpt-5.2":                   128000,
    "gpt-5.2-pro":               128000,
    "gpt-5":                     128000,
    "gpt-5-mini":                32768,
    "o3":                        100000,
    "o4-mini":                   65536,
}


# ── 에이전트 목록 (agents.yaml에서 동적 로드) ──
_AGENTS_FALLBACK = [
    {"agent_id": "chief_of_staff", "name_ko": "비서실장", "role": "manager", "division": "secretary", "status": "idle", "model_name": "claude-sonnet-4-6"},
    {"agent_id": "cso_manager", "name_ko": "전략팀장", "role": "manager", "division": "leet_master.strategy", "status": "idle", "model_name": "claude-sonnet-4-6"},
    {"agent_id": "clo_manager", "name_ko": "법무팀장", "role": "manager", "division": "leet_master.legal", "status": "idle", "model_name": "claude-sonnet-4-6"},
    {"agent_id": "cmo_manager", "name_ko": "마케팅팀장", "role": "manager", "division": "leet_master.marketing", "status": "idle", "model_name": "claude-sonnet-4-6"},
    {"agent_id": "cio_manager", "name_ko": "금융분석팀장", "role": "manager", "division": "finance.investment", "status": "idle", "model_name": "claude-opus-4-6"},
    {"agent_id": "cpo_manager", "name_ko": "콘텐츠팀장", "role": "manager", "division": "publishing", "status": "idle", "model_name": "claude-sonnet-4-6"},
]


def _build_agents_from_yaml() -> list[dict]:
    """agents.yaml(또는 agents.json)에서 AGENTS 리스트를 동적 생성.
    로드 실패 시 _AGENTS_FALLBACK 사용."""
    try:
        agents_detail = _load_agents()  # _AGENTS_DETAIL과 동일 소스
        if not agents_detail:
            _log("[AGENTS] agents.yaml 로드 결과 비어있음 — 폴백 사용")
            return list(_AGENTS_FALLBACK)
        result = []
        for aid, detail in agents_detail.items():
            entry = {
                "agent_id": aid,
                "name_ko": detail.get("name_ko", aid),
                "role": detail.get("role", "specialist"),
                "division": detail.get("division", ""),
                "superior_id": detail.get("superior_id", ""),
                "dormant": detail.get("dormant", False),
                "status": "idle",
                "model_name": detail.get("model_name", "claude-sonnet-4-6"),
            }
            if detail.get("telegram_code"):
                entry["telegram_code"] = detail["telegram_code"]
            result.append(entry)
        _log(f"[AGENTS] agents.yaml에서 {len(result)}명 로드 완료")
        return result
    except Exception as e:
        _log(f"[AGENTS] agents.yaml 로드 실패 ({e}) — 폴백 사용")
        return list(_AGENTS_FALLBACK)


AGENTS = _build_agents_from_yaml()

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


# ── 배치 명령 (여러 명령 한번에 실행) ──

# → app_state로 이동. alias (list는 공유 참조)
_batch_queue = app_state.batch_queue
_batch_api_queue = app_state.batch_api_queue
# app_state.batch_running은 primitive → app_state.batch_running 직접 사용


@app.get("/api/batch/queue")
async def get_batch_queue():
    """배치 대기열 조회."""
    return {"queue": _batch_queue, "running": app_state.batch_running}


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

    app_state.batch_running = True

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
        app_state.batch_running = False
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

        # AI 처리
        result = await _process_ai_command(item["command"], task["task_id"])

        item["status"] = "completed"
        item["result"] = result.get("content", "")[:200] if isinstance(result, dict) else str(result)[:200]
        # R-3: 전력분석 데이터용 agent_id 기록
        agent_id = result.get("agent_id", "chief_of_staff") if isinstance(result, dict) else "chief_of_staff"
        update_task(task["task_id"], agent_id=agent_id)
    except Exception as e:
        item["status"] = "failed"
        item["result"] = str(e)[:200]


@app.delete("/api/batch/queue")
async def clear_batch_queue():
    """배치 대기열을 비웁니다."""
    _batch_queue[:] = [item for item in _batch_queue if item.get("status") == "running"]
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

# app_state.batch_poller_task → app_state.batch_poller_task 직접 사용


@app.post("/api/batch/ai")
async def submit_ai_batch(request: Request):
    """AI Batch API로 여러 요청을 한꺼번에 제출합니다.

    요청 body:
    {
        "requests": [
            {"message": "삼성전자 분석해줘", "system_prompt": "...", "agent_id": "cio_manager"},
            {"message": "특허 검색해줘", "system_prompt": "...", "agent_id": "clo_manager"},
        ],
        "model": "claude-sonnet-4-6",  // 기본 모델 (선택)
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
    await wm.broadcast("batch_submitted", {
        "batch_id": batch_id,
        "provider": provider,
        "count": len(requests_list),
    })

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
                await wm.send_activity_log(log_entry)

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
    await wm.broadcast("batch_completed", {
        "batch_id": batch_id,
        "provider": provider,
        "count": len(results),
        "total_cost_usd": total_cost,
        "succeeded": sum(1 for r in results if not r.get("error")),
        "failed": sum(1 for r in results if r.get("error")),
    })

    _log(f"[BATCH] 결과 수집 완료: {batch_id} ({len(results)}개, ${total_cost:.4f})")


async def _flush_batch_api_queue():
    """배치 대기열에 쌓인 요청을 Batch API에 제출합니다."""
    if not _batch_api_queue:
        return {"message": "대기열이 비어있습니다"}

    queue_copy = list(_batch_api_queue)
    _batch_api_queue.clear()

    _log(f"[BATCH] 대기열 {len(queue_copy)}건 → Batch API 제출 중...")

    # 각 요청에 에이전트 라우팅 (시스템 프롬프트 결정)
    for req in queue_copy:
        if not req.get("system_prompt"):
            routing = await _route_task(req.get("message", ""))
            agent_id = routing.get("agent_id", "chief_of_staff")
            req["agent_id"] = agent_id
            req["system_prompt"] = _load_agent_prompt(agent_id)

    # Batch API 제출 — 프로바이더별로 자동 그룹화 (Claude/GPT/Gemini 요청이 섞여도 각각 올바른 API로 전송)
    batch_results = await batch_submit_grouped(queue_copy)

    # 전부 실패한 경우 대기열에 복구
    all_failed = all("error" in br for br in batch_results)
    if all_failed:
        first_error = batch_results[0].get("error", "알 수 없는 오류") if batch_results else "결과 없음"
        _log(f"[BATCH] 제출 실패 (전체): {first_error}")
        _batch_api_queue.extend(queue_copy)
        return {"error": first_error}

    # 성공한 배치들을 DB에 PENDING 상태로 저장
    pending_batches = load_setting("pending_batches") or []
    submitted_ids = []
    for result in batch_results:
        if "error" in result:
            _log(f"[BATCH] 프로바이더 {result.get('provider','?')} 제출 실패: {result['error']}")
            continue

        batch_id = result["batch_id"]
        provider = result["provider"]
        custom_ids_in_batch = result.get("custom_ids", [])

        # 이 배치에 포함된 요청만 필터링
        reqs_in_batch = [r for r in queue_copy if r.get("custom_id", r.get("task_id", "")) in custom_ids_in_batch]

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
                for r in reqs_in_batch
            ],
            "results": [],
        }
        pending_batches.append(pending_data)
        submitted_ids.append(batch_id)

        # 각 task를 PENDING 상태로 업데이트
        for req in reqs_in_batch:
            task_id = req.get("task_id")
            if task_id:
                update_task(task_id, status="pending",
                            result_summary=f"[PENDING] Batch API 제출됨 ({batch_id[:20]}...)")

        # WebSocket 알림
        await wm.broadcast("batch_submitted", {"batch_id": batch_id, "provider": provider, "count": len(reqs_in_batch)})

        _log(f"[BATCH] Batch API 제출 완료: {batch_id} ({len(reqs_in_batch)}건, {provider})")

    save_setting("pending_batches", pending_batches)
    _ensure_batch_poller()

    # 첫 번째 성공 결과를 반환 (하위 호환성 유지)
    first_success = next((r for r in batch_results if "error" not in r), batch_results[0] if batch_results else {})
    return first_success


@app.post("/api/batch/flush")
async def flush_batch_queue():
    """배치 대기열에 쌓인 요청을 즉시 Batch API에 제출합니다."""
    if not _batch_api_queue:
        return {"success": False, "message": "대기열이 비어있습니다"}
    result = await _flush_batch_api_queue()
    return {"success": "error" not in result, **result}


def _ensure_batch_poller():
    """배치 폴러가 돌고 있는지 확인하고, 안 돌면 시작합니다."""

    if app_state.batch_poller_task is None or app_state.batch_poller_task.done():
        app_state.batch_poller_task = asyncio.create_task(_batch_poller_loop())
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
#   [3단계] 팀장 종합보고서 → Batch 제출 → PENDING → 결과: 종합 보고서
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
        "delegation": "2단계: 팀장 지시서",
        "specialists": "3단계: 전문가 분석",
        "synthesis": "4단계: 종합 보고서",
        "completed": "완료",
        "failed": "실패",
        "direct": "비서실장 직접 처리",
    }
    step_label = step_labels.get(chain.get("step", ""), chain.get("step", ""))
    await wm.broadcast("batch_chain_progress", {
        "chain_id": chain["chain_id"],
        "step": chain.get("step", ""),
        "step_label": step_label,
        "status": chain.get("status", ""),
        "message": message,
        "mode": chain.get("mode", "single"),
        "target_id": chain.get("target_id"),
    })

    # 텔레그램으로도 진행 상태 전달
    if app_state.telegram_app:
        ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
        if ceo_id:
            try:
                await app_state.telegram_app.bot.send_message(
                    chat_id=int(ceo_id),
                    text=f"📦 {message}",
                )
            except Exception as e:
                logger.debug("TG 배치 진행 전송 실패: %s", e)


async def _start_batch_chain(text: str, task_id: str) -> dict:
    """배치 체인을 시작합니다.

    CEO 명령을 받아서 위임 체인 전체를 Batch API로 처리합니다.
    키워드 매칭이 되면 분류 단계를 건너뛰고 바로 전문가 단계로 진행합니다.
    """
    chain_id = f"chain_{datetime.now(KST).strftime('%Y%m%d_%H%M%S')}_{task_id[:8]}"

    correlation_id = f"batch_{chain_id}"

    chain = {
        "chain_id": chain_id,
        "task_id": task_id,
        "correlation_id": correlation_id,
        "text": text,
        "mode": "broadcast" if _is_broadcast_command(text) else "single",
        "step": "classify",
        "status": "running",
        "target_id": None,
        "batches": {"classify": None, "specialists": [], "synthesis": []},
        "results": {"classify": None, "specialists": {}, "synthesis": {}},
        "custom_id_map": {},  # custom_id → {"agent_id", "step"} 역매핑
        "delegation_instructions": {},  # 팀장 지시서 (단일 부서)
        "broadcast_delegations": {},  # 팀장 지시서 (브로드캐스트)
        "total_cost_usd": 0.0,
        "created_at": datetime.now(KST).isoformat(),
        "completed_at": None,
    }

    # task에 correlation_id 연결
    update_task(task_id, correlation_id=correlation_id)

    # 예산 확인
    limit = float(load_setting("daily_budget_usd") or 7.0)
    today = get_today_cost()
    if today >= limit:
        update_task(task_id, status="failed",
                    result_summary=f"일일 예산 초과 (${today:.2f}/${limit:.0f})",
                    success=0)
        return {"error": f"일일 예산을 초과했습니다 (${today:.2f}/${limit:.0f})"}

    # ── 브로드캐스트 모드 → 분류 건너뛰고 팀장 지시서 → 전 부서 전문가 ──
    if chain["mode"] == "broadcast":
        chain["step"] = "delegation"
        chain["target_id"] = "broadcast"
        _save_chain(chain)

        await _broadcast_chain_status(chain, "📦 배치 체인 시작 (브로드캐스트: 6개 부서 → 팀장 지시서 생성 중)")
        await _chain_create_delegation_broadcast(chain)
        return {"chain_id": chain_id, "status": "started", "mode": "broadcast", "step": chain["step"]}

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
            # 팀장 부서로 위임 → 팀장 지시서 → 전문가 호출 단계
            chain["step"] = "delegation"
            _save_chain(chain)
            target_name = _AGENT_NAMES.get(keyword_match, keyword_match)
            await _broadcast_chain_status(chain, f"📦 키워드 분류 → {target_name} 지시서 생성 중")
            await _chain_create_delegation(chain)

        return {"chain_id": chain_id, "status": "started", "step": chain["step"]}

    # ── AI 분류가 필요 → Batch API로 분류 요청 제출 ──
    # 가장 저렴한 사용 가능 모델 선택 (Gemini Flash → GPT Mini → Claude)
    providers = get_available_providers()
    if providers.get("google"):
        classify_model = "gemini-2.5-flash"
    elif providers.get("openai"):
        classify_model = "gpt-5-mini"
    elif providers.get("anthropic"):
        classify_model = "claude-sonnet-4-6"
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
        "max_tokens": 1024,
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


# ── 팀장 지시서 생성 프롬프트 ──
_DELEGATION_PROMPT = """당신은 {mgr_name}입니다. CEO로부터 아래 업무 지시를 받았습니다.

소속 전문가들에게 각각 구체적인 작업 지시를 내려야 합니다.
각 전문가의 전문 분야에 맞게 CEO 명령을 세부 업무로 분해하세요.

## 소속 전문가
{spec_list}

## CEO 명령
{text}

## 출력 형식
반드시 아래 JSON 형식으로만 답하세요. 다른 텍스트는 쓰지 마세요.
각 전문가 ID를 키로, 구체적인 작업 지시(2~4문장)를 값으로 작성하세요.

{json_example}"""


async def _chain_create_delegation(chain: dict):
    """배치 체인 — 팀장이 전문가별 지시서를 작성합니다 (실시간 API 1회 호출).

    분류 완료 후, 전문가 배치 제출 전에 호출됩니다.
    팀장에게 CEO 명령을 전달하고, 각 전문가에게 내릴 구체적 지시서를 받습니다.
    """
    target_id = chain["target_id"]
    text = chain["text"]
    specialists = _MANAGER_SPECIALISTS.get(target_id, [])

    if not specialists:
        # 전문가 없음 → 지시서 생성 불필요
        await _chain_submit_specialists(chain)
        return

    mgr_name = _AGENT_NAMES.get(target_id, target_id)

    # 전문가 목록 텍스트 생성
    spec_list_parts = []
    json_example_parts = []
    for s_id in specialists:
        s_name = _SPECIALIST_NAMES.get(s_id, s_id)
        spec_list_parts.append(f"- {s_id}: {s_name}")
        json_example_parts.append(f'  "{s_id}": "구체적인 작업 지시 내용"')

    spec_list = "\n".join(spec_list_parts)
    json_example = "{\n" + ",\n".join(json_example_parts) + "\n}"

    delegation_prompt = _DELEGATION_PROMPT.format(
        mgr_name=mgr_name,
        spec_list=spec_list,
        text=text,
        json_example=json_example,
    )

    # 가장 저렴한 모델로 실시간 API 호출 (Gemini Flash → GPT Mini → Claude)
    providers = get_available_providers()
    if providers.get("google"):
        deleg_model = "gemini-2.5-flash"
    elif providers.get("openai"):
        deleg_model = "gpt-5-mini"
    elif providers.get("anthropic"):
        deleg_model = "claude-sonnet-4-6"
    else:
        deleg_model = None

    if deleg_model:
        # 팀장 초록불 켜기
        await _broadcast_status(target_id, "working", 0.2, f"{mgr_name} 지시서 작성 중...")
        try:
            result = await ask_ai(
                user_message=delegation_prompt,
                model=deleg_model,
                max_tokens=2048,
            )
            response_text = result.get("content", "") or result.get("text", "")

            # JSON 파싱 시도
            import json as _json
            # JSON 블록 추출 (```json ... ``` 또는 { ... })
            json_text = response_text.strip()
            if "```" in json_text:
                # 코드 블록에서 추출
                start = json_text.find("{")
                end = json_text.rfind("}") + 1
                if start >= 0 and end > start:
                    json_text = json_text[start:end]
            elif json_text.startswith("{"):
                pass  # 이미 JSON
            else:
                # { 찾기
                start = json_text.find("{")
                end = json_text.rfind("}") + 1
                if start >= 0 and end > start:
                    json_text = json_text[start:end]

            instructions = _json.loads(json_text)
            if isinstance(instructions, dict):
                chain["delegation_instructions"] = instructions
                chain["results"]["delegation"] = {
                    "agent_id": target_id,
                    "instructions": instructions,
                    "model": deleg_model,
                    "cost_usd": result.get("cost_usd", 0),
                }
                chain["total_cost_usd"] += result.get("cost_usd", 0)
                _log(f"[CHAIN] {chain['chain_id']} — {mgr_name} 지시서 생성 완료 ({len(instructions)}명)")
            else:
                _log(f"[CHAIN] {chain['chain_id']} — 지시서 파싱 실패 (dict 아님)")
        except Exception as e:
            _log(f"[CHAIN] {chain['chain_id']} — 지시서 생성 실패: {e}")
            # 실패해도 진행 (지시서 없이 원본 명령으로)

    # 지시서 상태 업데이트 + 팀장 초록불 끄기
    has_instructions = bool(chain.get("delegation_instructions"))
    deleg_status = f"✅ {mgr_name} 지시서 생성 완료" if has_instructions else f"⚠️ 지시서 없이 진행"
    await _broadcast_status(target_id, "done", 0.5, deleg_status)
    update_task(chain["task_id"], status="pending",
                result_summary=f"📦 [배치 체인] 2단계: {deleg_status}")
    await _broadcast_chain_status(chain, f"📦 2단계: {deleg_status}")

    _save_chain(chain)

    # 전문가 배치 제출로 진행
    await _chain_submit_specialists(chain)


async def _chain_create_delegation_broadcast(chain: dict):
    """배치 체인 — 브로드캐스트: 6개 팀장이 각각 지시서를 작성합니다."""
    text = chain["text"]
    all_managers = ["cto_manager", "cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]

    # 가장 저렴한 모델 선택 (Gemini Flash → GPT Mini → Claude)
    providers = get_available_providers()
    if providers.get("google"):
        deleg_model = "gemini-2.5-flash"
    elif providers.get("openai"):
        deleg_model = "gpt-5-mini"
    elif providers.get("anthropic"):
        deleg_model = "claude-sonnet-4-6"
    else:
        deleg_model = None

    broadcast_delegations = {}

    if deleg_model:
        import asyncio as _asyncio

        async def _get_delegation(mgr_id: str) -> tuple[str, dict]:
            specialists = _MANAGER_SPECIALISTS.get(mgr_id, [])
            if not specialists:
                return mgr_id, {}
            mgr_name = _AGENT_NAMES.get(mgr_id, mgr_id)
            spec_list_parts = []
            json_example_parts = []
            for s_id in specialists:
                s_name = _SPECIALIST_NAMES.get(s_id, s_id)
                spec_list_parts.append(f"- {s_id}: {s_name}")
                json_example_parts.append(f'  "{s_id}": "구체적인 작업 지시 내용"')

            prompt = _DELEGATION_PROMPT.format(
                mgr_name=mgr_name,
                spec_list="\n".join(spec_list_parts),
                text=text,
                json_example="{\n" + ",\n".join(json_example_parts) + "\n}",
            )
            try:
                result = await ask_ai(user_message=prompt, model=deleg_model)
                response_text = result.get("content", "") or result.get("text", "")
                import json as _json
                json_text = response_text.strip()
                start = json_text.find("{")
                end = json_text.rfind("}") + 1
                if start >= 0 and end > start:
                    json_text = json_text[start:end]
                instructions = _json.loads(json_text)
                chain["total_cost_usd"] += result.get("cost_usd", 0)
                return mgr_id, instructions if isinstance(instructions, dict) else {}
            except Exception as e:
                _log(f"[CHAIN] 브로드캐스트 지시서 실패 ({mgr_id}): {e}")
                return mgr_id, {}

        # 6개 팀장에게 동시에 지시서 요청
        tasks = [_get_delegation(m) for m in all_managers]
        results = await _asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, tuple):
                mgr_id, instructions = r
                if instructions:
                    broadcast_delegations[mgr_id] = instructions

    chain["broadcast_delegations"] = broadcast_delegations
    chain["results"]["delegation"] = {
        "mode": "broadcast",
        "delegations": broadcast_delegations,
    }

    deleg_count = sum(1 for d in broadcast_delegations.values() if d)
    _log(f"[CHAIN] {chain['chain_id']} — 브로드캐스트 지시서 {deleg_count}/6 완료")
    update_task(chain["task_id"], status="pending",
                result_summary=f"📦 [배치 체인] 2단계: 팀장 지시서 {deleg_count}/6 완료")
    await _broadcast_chain_status(chain, f"📦 2단계: 팀장 지시서 {deleg_count}/6 완료")
    _save_chain(chain)

    # 전문가 배치 제출로 진행
    await _chain_submit_specialists_broadcast(chain)


async def _chain_submit_specialists(chain: dict):
    """배치 체인 — 단일 부서의 전문가들에게 배치 제출합니다."""
    target_id = chain["target_id"]
    text = chain["text"]
    specialists = _MANAGER_SPECIALISTS.get(target_id, [])

    if not specialists:
        # 전문가 없음 → 바로 종합(팀장 직접 처리) 단계
        chain["step"] = "synthesis"
        _save_chain(chain)
        await _chain_submit_synthesis(chain)
        return

    # 팀장 지시서가 있으면 전문가에게 함께 전달
    delegation = chain.get("delegation_instructions", {})

    requests = []
    for spec_id in specialists:
        # 전문가 초록불 켜기
        spec_name = _SPECIALIST_NAMES.get(spec_id, spec_id)
        await _broadcast_status(spec_id, "working", 0.3, f"{spec_name} 배치 처리 중...")

        soul = _load_agent_prompt(spec_id, include_tools=False) + _BATCH_MODE_SUFFIX
        override = _get_model_override(spec_id)
        model = select_model(text, override=override)
        custom_id = f"{chain['chain_id']}_spec_{spec_id}"

        # 팀장 지시서가 있으면 전문가에게 함께 전달
        spec_instruction = delegation.get(spec_id, "")
        if spec_instruction:
            message = (
                f"## 팀장 지시\n{spec_instruction}\n\n"
                f"## CEO 원본 명령\n{text}"
            )
        else:
            message = text

        requests.append({
            "custom_id": custom_id,
            "message": message,
            "system_prompt": soul,
            "model": model,
            "max_tokens": min(MODEL_MAX_TOKENS_MAP.get(model, 8192), 16384),
            "reasoning_effort": _get_agent_reasoning_effort(spec_id),
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

    chain["step"] = "specialists"
    chain["status"] = "pending"
    _save_chain(chain)

    _ensure_batch_poller()
    spec_count = len(specialists)
    provider_count = len(batch_results)
    target_name = _AGENT_NAMES.get(target_id, target_id)
    update_task(chain["task_id"], status="pending",
                result_summary=f"📦 [배치 체인] 3단계: {target_name} 전문가 {spec_count}명 배치 제출 ({provider_count}개 프로바이더)")
    await _broadcast_chain_status(chain, f"📦 3단계: {target_name} 전문가 {spec_count}명 → {provider_count}개 프로바이더별 배치 제출")

    _log(f"[CHAIN] {chain['chain_id']} — 전문가 {spec_count}명 배치 제출 ({provider_count}개 프로바이더)")


async def _chain_submit_specialists_broadcast(chain: dict):
    """배치 체인 — 브로드캐스트: 6개 부서 전체 전문가에게 배치 제출합니다."""
    text = chain["text"]
    all_managers = ["cto_manager", "cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]

    # 브로드캐스트 모드의 팀장별 지시서
    broadcast_delegations = chain.get("broadcast_delegations", {})

    requests = []
    for mgr_id in all_managers:
        specialists = _MANAGER_SPECIALISTS.get(mgr_id, [])
        mgr_delegation = broadcast_delegations.get(mgr_id, {})
        for spec_id in specialists:
            soul = _load_agent_prompt(spec_id, include_tools=False) + _BATCH_MODE_SUFFIX
            override = _get_model_override(spec_id)
            model = select_model(text, override=override)
            custom_id = f"{chain['chain_id']}_spec_{spec_id}"

            # 팀장 지시서가 있으면 전문가에게 함께 전달
            spec_instruction = mgr_delegation.get(spec_id, "")
            if spec_instruction:
                message = (
                    f"## 팀장 지시\n{spec_instruction}\n\n"
                    f"## CEO 원본 명령\n{text}"
                )
            else:
                message = text

            requests.append({
                "custom_id": custom_id,
                "message": message,
                "system_prompt": soul,
                "model": model,
                "max_tokens": min(MODEL_MAX_TOKENS_MAP.get(model, 8192), 16384),
                "reasoning_effort": _get_agent_reasoning_effort(spec_id),
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

    chain["step"] = "specialists"
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
    """배치 체인 — 팀장(들)이 전문가 결과를 종합하는 배치를 제출합니다."""
    text = chain["text"]

    requests = []

    if chain["mode"] == "broadcast":
        # 브로드캐스트: 6개 팀장이 각각 자기 팀 결과를 종합
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

            soul = _load_agent_prompt(mgr_id, include_tools=False) + _BATCH_MODE_SUFFIX
            override = _get_model_override(mgr_id)
            model = select_model(synthesis_prompt, override=override)
            custom_id = f"{chain['chain_id']}_synth_{mgr_id}"

            requests.append({
                "custom_id": custom_id,
                "message": synthesis_prompt,
                "system_prompt": soul,
                "model": model,
                "max_tokens": min(MODEL_MAX_TOKENS_MAP.get(model, 8192), 16384),
                "reasoning_effort": _get_agent_reasoning_effort(mgr_id),
            })
            chain["custom_id_map"][custom_id] = {"agent_id": mgr_id, "step": "synthesis"}

    elif chain["target_id"] == "chief_of_staff":
        # 비서실장 직접 처리 (분류 결과가 chief_of_staff인 경우)
        soul = _load_agent_prompt("chief_of_staff", include_tools=False) + _BATCH_MODE_SUFFIX
        override = _get_model_override("chief_of_staff")
        model = select_model(text, override=override)
        custom_id = f"{chain['chain_id']}_synth_chief_of_staff"

        requests.append({
            "custom_id": custom_id,
            "message": text,
            "system_prompt": soul,
            "model": model,
            "max_tokens": min(MODEL_MAX_TOKENS_MAP.get(model, 8192), 16384),
            "reasoning_effort": _get_agent_reasoning_effort("chief_of_staff"),
        })
        chain["custom_id_map"][custom_id] = {"agent_id": "chief_of_staff", "step": "synthesis"}

    else:
        # 단일 부서: 팀장이 전문가 결과를 종합
        target_id = chain["target_id"]
        specialists = _MANAGER_SPECIALISTS.get(target_id, [])

        if not specialists or not chain["results"]["specialists"]:
            # 전문가 결과 없음 → 팀장이 직접 답변
            soul = _load_agent_prompt(target_id, include_tools=False) + _BATCH_MODE_SUFFIX
            override = _get_model_override(target_id)
            model = select_model(text, override=override)
            custom_id = f"{chain['chain_id']}_synth_{target_id}"

            requests.append({
                "custom_id": custom_id,
                "message": text,
                "system_prompt": soul,
                "model": model,
                "max_tokens": min(MODEL_MAX_TOKENS_MAP.get(model, 8192), 16384),
                "reasoning_effort": _get_agent_reasoning_effort(target_id),
            })
            chain["custom_id_map"][custom_id] = {"agent_id": target_id, "step": "synthesis"}
        else:
            # 전문가 결과 취합 → 팀장에게 종합 요청
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

            soul = _load_agent_prompt(target_id, include_tools=False) + _BATCH_MODE_SUFFIX
            override = _get_model_override(target_id)
            model = select_model(synthesis_prompt, override=override)
            custom_id = f"{chain['chain_id']}_synth_{target_id}"

            requests.append({
                "custom_id": custom_id,
                "message": synthesis_prompt,
                "system_prompt": soul,
                "model": model,
                "max_tokens": min(MODEL_MAX_TOKENS_MAP.get(model, 8192), 16384),
                "reasoning_effort": _get_agent_reasoning_effort(target_id),
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
                    result_summary="📦 [배치 체인] 4단계: 6개 팀장 종합보고서 배치 제출")
        await _broadcast_chain_status(chain, "📦 4단계: 6개 팀장이 종합보고서 작성 중 (배치)")
    else:
        target_name = _AGENT_NAMES.get(chain["target_id"], chain["target_id"])
        update_task(chain["task_id"], status="pending",
                    result_summary=f"📦 [배치 체인] 4단계: {target_name} 종합보고서 배치 제출")
        await _broadcast_chain_status(chain, f"📦 4단계: {target_name} 종합보고서 작성 중 (배치)")

    _log(f"[CHAIN] {chain['chain_id']} — 종합보고서 배치 제출 ({len(requests)}건)")


async def _send_batch_result_to_telegram(content: str, cost: float):
    """배치 체인 결과를 텔레그램 CEO에게 전달합니다."""
    if not app_state.telegram_app:
        return
    ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
    if not ceo_id:
        return
    try:
        # 텔레그램 코드명 변환
        content = _tg_convert_names(content)
        # 텔레그램 메시지 길이 제한 (4096자)
        if len(content) > 3800:
            content = content[:3800] + "\n\n... (전체 결과는 웹에서 확인)"
        await app_state.telegram_app.bot.send_message(
            chat_id=int(ceo_id),
            text=f"📦 배치 체인 완료\n\n{content}\n\n─────\n💰 ${cost:.4f}",
        )
    except Exception as e:
        _log(f"[TG] 배치 결과 전송 실패: {e}")


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


async def _synthesis_realtime_fallback(chain: dict):
    """종합 배치 실패 시 실시간 ask_ai()로 종합보고서를 대신 생성합니다."""
    text = chain["text"]
    _log(f"[CHAIN] {chain['chain_id']} — 실시간 폴백 시작")

    if chain["mode"] == "broadcast":
        all_managers = ["cto_manager", "cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]
        for mgr_id in all_managers:
            if mgr_id in chain["results"]["synthesis"]:
                continue  # 이미 있으면 skip
            specialists = _MANAGER_SPECIALISTS.get(mgr_id, [])
            spec_parts = []
            for s_id in specialists:
                s_res = chain["results"]["specialists"].get(s_id, {})
                name = _SPECIALIST_NAMES.get(s_id, s_id)
                content = s_res.get("content", "응답 없음")
                spec_parts.append(f"[{name}]\n{content}")

            mgr_name = _AGENT_NAMES.get(mgr_id, mgr_id)
            if spec_parts:
                synthesis_prompt = (
                    f"당신은 {mgr_name}입니다. 소속 전문가들의 분석 결과를 종합하여 CEO에게 보고하세요.\n\n"
                    f"## CEO 원본 명령\n{text}\n\n"
                    f"## 전문가 분석 결과\n" + "\n\n".join(spec_parts)
                )
            else:
                synthesis_prompt = text
            soul = _load_agent_prompt(mgr_id, include_tools=False)
            try:
                result = await ask_ai(user_message=synthesis_prompt, system_prompt=soul)
                chain["results"]["synthesis"][mgr_id] = {
                    "content": result.get("content", ""),
                    "model": result.get("model", ""),
                    "cost_usd": result.get("cost_usd", 0),
                    "error": result.get("error"),
                }
                chain["total_cost_usd"] += result.get("cost_usd", 0)
            except Exception as e:
                _log(f"[CHAIN] 실시간 폴백 실패 ({mgr_id}): {e}")
                chain["results"]["synthesis"][mgr_id] = {"content": "", "error": str(e)[:100]}
    else:
        target_id = chain.get("target_id", "chief_of_staff")
        if target_id not in chain["results"]["synthesis"]:
            soul = _load_agent_prompt(target_id, include_tools=False)
            try:
                result = await ask_ai(user_message=text, system_prompt=soul)
                chain["results"]["synthesis"][target_id] = {
                    "content": result.get("content", ""),
                    "model": result.get("model", ""),
                    "cost_usd": result.get("cost_usd", 0),
                    "error": result.get("error"),
                }
                chain["total_cost_usd"] += result.get("cost_usd", 0)
            except Exception as e:
                _log(f"[CHAIN] 실시간 폴백 실패 ({target_id}): {e}")
                chain["results"]["synthesis"][target_id] = {"content": "", "error": str(e)[:100]}

    target_id = chain.get("target_id", "chief_of_staff")
    await _broadcast_status(target_id, "done", 1.0, "보고 완료")
    _save_chain(chain)
    await _deliver_chain_result(chain)


async def _deliver_chain_result(chain: dict):
    """배치 체인 최종 결과를 CEO에게 전달합니다."""
    # ── 중복 전달 방지 ──
    if chain.get("delivered"):
        _log(f"[CHAIN] {chain.get('chain_id', '?')} — 이미 전달됨, 중복 방지")
        return
    chain["delivered"] = True
    # 즉시 completed 상태로 변경 → 폴러가 재진입 못하게 방지
    chain["step"] = "completed"
    chain["status"] = "completed"
    chain["completed_at"] = datetime.now(KST).isoformat()
    _save_chain(chain)

    task_id = chain["task_id"]
    text = chain["text"]
    total_cost = chain.get("total_cost_usd", 0)

    if chain["mode"] == "broadcast":
        # 브로드캐스트: 6개 팀장 종합 결과를 모아서 전달
        all_managers = ["cto_manager", "cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]
        parts = []
        total_specialists = 0
        for mgr_id in all_managers:
            synth = chain["results"]["synthesis"].get(mgr_id, {})
            mgr_name = _AGENT_NAMES.get(mgr_id, mgr_id)
            content = synth.get("content", "")
            # 종합보고서가 비었으면 전문가 원본 결과를 폴백으로 사용
            if not content or content == "응답 없음":
                specialists = _MANAGER_SPECIALISTS.get(mgr_id, [])
                fallback_parts = []
                for s_id in specialists:
                    s_res = chain["results"].get("specialists", {}).get(s_id, {})
                    s_content = s_res.get("content", "")
                    if s_content:
                        s_name = _SPECIALIST_NAMES.get(s_id, s_id)
                        fallback_parts.append(f"**{s_name}**: {s_content[:300]}")
                if fallback_parts:
                    content = "(종합 배치 실패 — 전문가 원본 결과)\n" + "\n".join(fallback_parts)
                else:
                    content = "응답 없음 (배치 처리 중 오류 발생)"
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
        await wm.broadcast("result", {
            "content": compiled,
            "sender_id": "chief_of_staff",
            "handled_by": "비서실장 → 6개 팀장",
            "delegation": "비서실장 → 팀장 → 전문가 (배치)",
            "time_seconds": 0,
            "cost": total_cost,
            "model": "multi-agent-batch",
            "routing_method": "배치 체인 (브로드캐스트)",
        })

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
        await wm.broadcast("result", {
            "content": final_content,
            "sender_id": target_id,
            "handled_by": handled_by,
            "delegation": delegation,
            "time_seconds": 0,
            "cost": total_cost,
            "model": synth.get("model", "batch"),
            "routing_method": "배치 체인",
        })

    # 텔레그램으로도 결과 전달
    tg_content = compiled if chain["mode"] == "broadcast" else final_content
    await _send_batch_result_to_telegram(tg_content, total_cost)

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
                # 팀장 지시서 → 전문가 단계로 진행
                chain["step"] = "delegation"
                _save_chain(chain)
                await _broadcast_chain_status(chain, f"📦 분류 완료: {target_name} 지시서 생성 중")
                await _chain_create_delegation(chain)

        elif status_result["status"] in ("failed", "expired"):
            # 분류 배치 실패 → 비서실장 폴백
            chain["target_id"] = "chief_of_staff"
            chain["step"] = "synthesis"
            chain["results"]["classify"] = {"agent_id": "chief_of_staff", "method": "폴백"}
            _save_chain(chain)
            await _chain_submit_synthesis(chain)

    # ── delegation 안전망 ──
    # delegation은 실시간 API로 즉시 처리되므로 폴러가 관여할 일이 없음.
    # 하지만 _chain_create_delegation() 중 에러로 step이 "delegation"에 멈춰있으면
    # 여기서 복구하여 전문가 단계를 재시도합니다.
    elif step == "delegation":
        # 이미 전문가 배치가 제출된 상태면 → specialists로 전환
        if chain["batches"].get("specialists"):
            chain["step"] = "specialists"
            _save_chain(chain)
            _log(f"[CHAIN] {chain_id} — delegation 안전망: specialists로 전환")
        else:
            # 전문가 배치가 아직 제출 안 됨 → 지시서 생성부터 재시도
            _log(f"[CHAIN] {chain_id} — delegation 안전망: 지시서 생성 재시도")
            try:
                await _chain_create_delegation(chain)
            except Exception as e:
                _log(f"[CHAIN] {chain_id} — delegation 재시도 실패: {e}")
                # 실패 시 지시서 없이 전문가에게 직접 전달
                chain["step"] = "specialists"
                _save_chain(chain)
                await _chain_submit_specialists(chain)
        return

    # ── 3단계: 전문가 ──
    elif step == "specialists":
        all_done = True
        batch_errors = []  # 오류 추적
        for batch_info in chain["batches"].get("specialists", []):
            if batch_info.get("status") in ("pending", "processing"):
                try:
                    status_result = await batch_check(batch_info["batch_id"], batch_info["provider"])
                    if "error" not in status_result:
                        batch_info["status"] = status_result["status"]
                    else:
                        err = status_result.get("error", "배치 상태 확인 실패")
                        _log(f"[CHAIN] 전문가 배치 확인 오류 ({batch_info['provider']}): {err}")
                        batch_errors.append(f"{batch_info['provider']}: {err[:80]}")
                except Exception as e:
                    _log(f"[CHAIN] 전문가 배치 확인 예외 ({batch_info.get('provider','?')}): {e}")
                    batch_errors.append(f"{batch_info.get('provider','?')}: {str(e)[:80]}")

            if batch_info.get("status") not in ("completed", "failed"):
                all_done = False

        _save_chain(chain)

        if not all_done:
            # ── 배치 처리 대기 중 → 초록불 유지 (맥박 효과) ──
            # Anthropic/OpenAI/Google 프로바이더 무관, 결과 없는 전문가에게 초록불
            target_id = chain.get("target_id", "")
            specialists = _MANAGER_SPECIALISTS.get(target_id, [])
            for spec_id in specialists:
                spec_res = chain["results"].get("specialists", {}).get(spec_id)
                if spec_res is None:
                    spec_name = _SPECIALIST_NAMES.get(spec_id, spec_id)
                    await _broadcast_status(spec_id, "working", 0.5, f"{spec_name} 배치 처리 중...")
            return

        if all_done:
            # 모든 전문가 배치 완료 → 결과 수집
            retrieve_errors = []
            for batch_info in chain["batches"]["specialists"]:
                if batch_info.get("status") != "completed":
                    if batch_info.get("status") == "failed":
                        err_detail = batch_info.get("error", "배치 실패")
                        retrieve_errors.append(f"{batch_info['provider']}: {err_detail[:80]}")
                    continue

                result = await batch_retrieve(batch_info["batch_id"], batch_info["provider"])
                if "error" in result:
                    retrieve_errors.append(f"{batch_info['provider']}: {result['error'][:80]}")
                    _log(f"[CHAIN] 전문가 결과 수집 실패 ({batch_info['provider']}): {result['error']}")
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
                    # 전문가 초록불 끄기
                    await _broadcast_status(agent_id, "done", 1.0, "완료")

            spec_count = len(chain["results"]["specialists"])
            _log(f"[CHAIN] {chain['chain_id']} — 전문가 {spec_count}명 결과 수집 완료")

            # 결과가 없으면 오류 원인을 텔레그램으로 전달
            if spec_count == 0:
                all_errors = batch_errors + retrieve_errors
                if all_errors:
                    error_summary = " | ".join(all_errors[:3])
                    await _broadcast_chain_status(chain, f"⚠️ 전문가 배치 실패 — 원인: {error_summary}")
                else:
                    await _broadcast_chain_status(chain, "⚠️ 전문가 배치 결과 없음 — 팀장 직접 처리로 전환")

            # ── 품질검수 HOOK: 전문가 결과 검수 ──
            if spec_count > 0 and app_state.quality_gate:
                target_id_qa = chain.get("target_id", "chief_of_staff")
                if target_id_qa not in _DORMANT_MANAGERS:
                    await _broadcast_chain_status(chain, "🔍 전문가 보고서 품질검수 시작...")
                    failed_specs = await _quality_review_specialists(chain)
                    if failed_specs:
                        _save_chain(chain)
                        await _handle_specialist_rework(chain, failed_specs)
                        _save_chain(chain)
                    qa_msg = f"✅ 품질검수 완료 (합격 {spec_count - len(failed_specs)}/{spec_count}명)"
                    await _broadcast_chain_status(chain, qa_msg)

            # 종합 단계로 진행 — 팀장 초록불 켜기
            target_id = chain.get("target_id", "chief_of_staff")
            target_name = _AGENT_NAMES.get(target_id, target_id)
            await _broadcast_status(target_id, "working", 0.7, f"{target_name} 종합보고서 작성 중...")

            chain["step"] = "synthesis"
            _save_chain(chain)
            await _broadcast_chain_status(chain, f"📦 전문가 {spec_count}명 완료 → 종합보고서 작성 시작")
            await _chain_submit_synthesis(chain)

    # ── 4단계: 종합보고서 ──
    elif step == "synthesis":
        all_done = True
        synth_errors = []  # 오류 추적
        for batch_info in chain["batches"].get("synthesis", []):
            if batch_info.get("status") in ("pending", "processing"):
                try:
                    status_result = await batch_check(batch_info["batch_id"], batch_info["provider"])
                    if "error" not in status_result:
                        batch_info["status"] = status_result["status"]
                    else:
                        err = status_result.get("error", "배치 상태 확인 실패")
                        _log(f"[CHAIN] 종합 배치 확인 오류 ({batch_info['provider']}): {err}")
                        synth_errors.append(f"{batch_info['provider']}: {err[:80]}")
                except Exception as e:
                    _log(f"[CHAIN] 종합 배치 확인 예외 ({batch_info.get('provider','?')}): {e}")
                    synth_errors.append(f"{batch_info.get('provider','?')}: {str(e)[:80]}")

            if batch_info.get("status") not in ("completed", "failed"):
                all_done = False

        _save_chain(chain)

        if not all_done:
            # ── 종합보고서 배치 대기 중 → 팀장 초록불 유지 ──
            target_id = chain.get("target_id", "chief_of_staff")
            target_name = _AGENT_NAMES.get(target_id, target_id)
            await _broadcast_status(target_id, "working", 0.8, f"{target_name} 종합보고서 작성 중...")
            return

        if all_done:
            # 종합보고서 결과 수집
            retrieve_errors = []
            for batch_info in chain["batches"]["synthesis"]:
                if batch_info.get("status") != "completed":
                    if batch_info.get("status") == "failed":
                        err_detail = batch_info.get("error", "배치 실패")
                        retrieve_errors.append(f"{batch_info['provider']}: {err_detail[:80]}")
                    continue

                result = await batch_retrieve(batch_info["batch_id"], batch_info["provider"])
                if "error" in result:
                    retrieve_errors.append(f"{batch_info['provider']}: {result['error'][:80]}")
                    _log(f"[CHAIN] 종합 결과 수집 실패 ({batch_info['provider']}): {result['error']}")
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

            synth_count = len(chain["results"]["synthesis"])
            _log(f"[CHAIN] {chain['chain_id']} — 종합보고서 {synth_count}개 완료")

            # 종합 결과가 없으면 오류 원인 알림 + 실시간 폴백
            if synth_count == 0:
                all_errors = synth_errors + retrieve_errors
                if all_errors:
                    error_summary = " | ".join(all_errors[:3])
                    await _broadcast_chain_status(chain, f"⚠️ 종합 배치 실패 — 실시간으로 재처리: {error_summary}")
                else:
                    await _broadcast_chain_status(chain, "⚠️ 종합 배치 결과 없음 — 실시간으로 재처리")

                # 실시간 폴백: ask_ai()로 직접 종합보고서 생성
                await _synthesis_realtime_fallback(chain)
                return

            # ── 품질검수 HOOK #2: 종합보고서 검수 (경고 뱃지만, 재작업 없음) ──
            if app_state.quality_gate and synth_count > 0:
                target_id_qa2 = chain.get("target_id", "chief_of_staff")
                if target_id_qa2 not in _DORMANT_MANAGERS:
                    division = _MANAGER_DIVISION.get(target_id_qa2, "default")
                    reviewer_model = _get_model_override(target_id_qa2) or "claude-sonnet-4-6"
                    task_desc = chain.get("original_command", "")[:500]
                    for agent_id, synth_data in chain["results"]["synthesis"].items():
                        try:
                            review = await app_state.quality_gate.hybrid_review(
                                result_data=synth_data.get("content", ""),
                                task_description=task_desc,
                                model_router=_qa_router,
                                reviewer_id=target_id_qa2,
                                reviewer_model=reviewer_model,
                                division=division,
                                target_agent_id=agent_id,
                            )
                            app_state.quality_gate.record_review(review, target_id_qa2, agent_id, task_desc)
                            if not review.passed:
                                synth_data["quality_warning"] = (
                                    " / ".join(review.rejection_reasons)[:200]
                                    if review.rejection_reasons else "품질 기준 미달"
                                )
                                _log(f"[QA] ⚠️ 종합보고서 불합격: {agent_id} (점수={review.weighted_average:.1f})")
                            else:
                                synth_data["quality_score"] = round(review.weighted_average, 1)
                                _log(f"[QA] ✅ 종합보고서 합격: {agent_id} (점수={review.weighted_average:.1f})")
                        except Exception as e:
                            _log(f"[QA] 종합보고서 검수 오류 ({agent_id}): {e}")
                    _save_chain(chain)

            # 팀장 초록불 끄기
            target_id = chain.get("target_id", "chief_of_staff")
            await _broadcast_status(target_id, "done", 1.0, "보고 완료")

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


# ────────────────────────────────────────────────────────────────
# 신뢰도 검증 파이프라인 — 학습 엔진
# ────────────────────────────────────────────────────────────────

_CIO_ANALYSTS = [
    "cio_manager", "market_condition_specialist", "stock_analysis_specialist",
    "technical_analysis_specialist", "risk_management_specialist",
]


def _run_confidence_learning_pipeline(verified_7d_ids: list[int]) -> None:
    """7일 검증 완료된 예측에 대해 학습 파이프라인 실행.
    ① ELO 업데이트 → ② 칼리브레이션 갱신 → ③ 도구 효과 → ④ 오답 패턴 탐지
    """
    _lp = logging.getLogger("corthex.confidence")
    try:
        for pred_id in verified_7d_ids:
            _update_analyst_elos_for_prediction(pred_id)
        _lp.info("[학습] ELO 업데이트 완료: %d건", len(verified_7d_ids))
    except Exception as e:
        _lp.warning("[학습] ELO 업데이트 실패: %s", e)

    try:
        _rebuild_calibration_buckets()
        _lp.info("[학습] 칼리브레이션 버킷 갱신 완료")
    except Exception as e:
        _lp.warning("[학습] 칼리브레이션 갱신 실패: %s", e)

    try:
        for pred_id in verified_7d_ids:
            _update_tool_effectiveness_for_prediction(pred_id)
        _lp.info("[학습] 도구 효과 업데이트 완료")
    except Exception as e:
        _lp.warning("[학습] 도구 효과 업데이트 실패: %s", e)

    try:
        _detect_error_patterns()
        _lp.info("[학습] 오답 패턴 탐지 완료")
    except Exception as e:
        _lp.warning("[학습] 오답 패턴 탐지 실패: %s", e)


def _update_analyst_elos_for_prediction(prediction_id: int) -> None:
    """단일 예측에 대해 5명 전문가 ELO를 업데이트합니다."""
    import math
    from db import (
        get_prediction_specialists, get_analyst_elo, upsert_analyst_elo,
        save_elo_history,
    )

    conn = get_connection()
    try:
        pred = conn.execute(
            "SELECT correct_7d, return_pct_7d, direction, confidence "
            "FROM cio_predictions WHERE id=?", (prediction_id,)
        ).fetchone()
    finally:
        conn.close()
    if not pred or pred[0] is None:
        return

    correct_7d = pred[0]
    return_pct = pred[1] or 0.0
    direction = pred[2]

    # 전문가 데이터
    spec_data = get_prediction_specialists(prediction_id)
    spec_map = {s["agent_id"]: s for s in spec_data}

    # 현재 ELO 조회 + 평균 ELO 계산
    elos = {aid: get_analyst_elo(aid) for aid in _CIO_ANALYSTS}
    avg_elo = sum(e["elo_rating"] for e in elos.values()) / len(elos)

    for agent_id in _CIO_ANALYSTS:
        current = elos[agent_id]
        agent_elo = current["elo_rating"]
        total = current["total_predictions"]

        # 전문가가 이 예측에 참여했는지 확인
        spec_info = spec_map.get(agent_id)
        if spec_info:
            # 개별 전문가의 추천이 실제 결과와 일치하는지
            rec = spec_info.get("recommendation", "HOLD")
            if rec in ("BUY", "SELL"):
                agent_correct = 1 if (
                    (rec == direction and correct_7d == 1) or
                    (rec != direction and correct_7d == 0)
                ) else 0
                outcome = 1.0 if agent_correct else 0.0
                # 부분적중: 방향 맞으나 수익 < 0.5%
                if agent_correct and abs(return_pct) < 0.5:
                    outcome = 0.5
            else:
                # HOLD 추천 → 관망은 약간의 보상/패널티
                outcome = 0.5
        else:
            # 전문가 데이터 없으면 전체 결과 사용
            outcome = 1.0 if correct_7d else 0.0

        # K-factor: 첫 30건은 K=48 (빠른 조정), 이후 K=32
        k = 48 if total < 30 else 32

        # ELO 변동 계산
        expected = 1.0 / (1.0 + math.pow(10, (avg_elo - agent_elo) / 400.0))
        elo_change = round(k * (outcome - expected), 2)
        new_elo = round(agent_elo + elo_change, 1)

        # DB 업데이트
        new_total = total + 1
        new_correct = current["correct_predictions"] + (1 if outcome >= 0.75 else 0)
        # 이동 평균 수익률
        old_avg_ret = current["avg_return_pct"]
        new_avg_ret = round(
            (old_avg_ret * total + return_pct) / new_total if new_total > 0 else 0, 2
        )

        upsert_analyst_elo(agent_id, new_elo, new_total, new_correct, new_avg_ret)
        save_elo_history(agent_id, prediction_id, agent_elo, new_elo, elo_change,
                         1 if outcome >= 0.75 else 0, return_pct)


def _rebuild_calibration_buckets() -> None:
    """cio_predictions 전체 데이터를 기반으로 칼리브레이션 버킷을 재계산합니다."""
    import math
    from db import upsert_calibration_bucket

    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT
                 CASE
                   WHEN confidence < 60 THEN '50-60'
                   WHEN confidence < 70 THEN '60-70'
                   WHEN confidence < 80 THEN '70-80'
                   WHEN confidence < 90 THEN '80-90'
                   ELSE '90-100'
                 END as bucket,
                 COUNT(*) as total,
                 SUM(CASE WHEN correct_7d=1 THEN 1 ELSE 0 END) as correct
               FROM cio_predictions
               WHERE correct_7d IS NOT NULL
               GROUP BY bucket"""
        ).fetchall()
    finally:
        conn.close()

    for r in rows:
        bucket, total, correct = r[0], r[1], r[2]
        # Beta 분포: 사전분포 Beta(1,1) + 데이터
        alpha = 1.0 + correct
        beta_val = 1.0 + (total - correct)
        actual_rate = round(alpha / (alpha + beta_val), 4)
        # 95% CI: 정규 근사 (scipy 불필요)
        ab = alpha + beta_val
        var = (alpha * beta_val) / (ab * ab * (ab + 1))
        std = math.sqrt(var) if var > 0 else 0
        ci_lower = round(max(0, actual_rate - 1.96 * std), 4)
        ci_upper = round(min(1, actual_rate + 1.96 * std), 4)

        upsert_calibration_bucket(
            bucket, total, correct, actual_rate, alpha, beta_val, ci_lower, ci_upper
        )


def _update_tool_effectiveness_for_prediction(prediction_id: int) -> None:
    """단일 예측에 대해 도구별 효과를 업데이트합니다."""
    import json as _json_te
    from db import get_prediction_specialists, upsert_tool_effectiveness, get_tool_effectiveness_all

    conn = get_connection()
    try:
        pred = conn.execute(
            "SELECT correct_7d FROM cio_predictions WHERE id=?", (prediction_id,)
        ).fetchone()
    finally:
        conn.close()
    if not pred or pred[0] is None:
        return

    correct = pred[0] == 1
    spec_data = get_prediction_specialists(prediction_id)

    # 기존 도구 효과 캐시
    existing = {t["tool_name"]: t for t in get_tool_effectiveness_all()}

    tools_seen = set()
    for spec in spec_data:
        try:
            tools = _json_te.loads(spec.get("tools_used", "[]"))
        except (ValueError, TypeError):
            tools = []
        for tool in tools:
            if tool in tools_seen:
                continue
            tools_seen.add(tool)
            e = existing.get(tool, {"used_correct": 0, "used_incorrect": 0, "total_uses": 0})
            new_correct = e["used_correct"] + (1 if correct else 0)
            new_incorrect = e["used_incorrect"] + (0 if correct else 1)
            new_total = e["total_uses"] + 1
            eff = round(new_correct / new_total, 4) if new_total > 0 else 0.5
            upsert_tool_effectiveness(tool, new_correct, new_incorrect, new_total, eff)


def _detect_error_patterns() -> None:
    """검증된 예측에서 오답 패턴을 탐지합니다."""
    from db import upsert_error_pattern

    conn = get_connection()
    try:
        # 패턴 1: 신뢰도 구간별 과신 탐지
        overconf_rows = conn.execute(
            """SELECT
                 CASE WHEN confidence >= 80 THEN 'high_confidence_overfit'
                      WHEN confidence >= 70 THEN 'mid_confidence_overfit'
                      ELSE NULL END as ptype,
                 COUNT(*) as total,
                 SUM(CASE WHEN correct_7d=1 THEN 1 ELSE 0 END) as correct
               FROM cio_predictions
               WHERE correct_7d IS NOT NULL AND confidence >= 70
               GROUP BY ptype HAVING ptype IS NOT NULL"""
        ).fetchall()
        for r in overconf_rows:
            ptype, total, correct = r[0], r[1], r[2]
            miss = total - correct
            hit_rate = round(correct / total * 100, 1) if total > 0 else 0
            if total >= 5 and hit_rate < 60:
                conf_range = "80%+" if "high" in ptype else "70-80%"
                upsert_error_pattern(
                    ptype,
                    f"신뢰도 {conf_range} 시그널의 실제 적중률이 {hit_rate}%로 낮음 ({correct}/{total}건)",
                    correct, miss, hit_rate,
                )

        # 패턴 2: 같은 종목 연속 오답 (3회+)
        streak_rows = conn.execute(
            """SELECT ticker, ticker_name, COUNT(*) as miss_streak
               FROM cio_predictions
               WHERE correct_7d = 0
               GROUP BY ticker HAVING miss_streak >= 3
               ORDER BY miss_streak DESC LIMIT 5"""
        ).fetchall()
        for r in streak_rows:
            ticker, name, streak = r[0], r[1] or r[0], r[2]
            # 해당 종목의 전체 기록
            ticker_total = conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN correct_7d=1 THEN 1 ELSE 0 END) "
                "FROM cio_predictions WHERE ticker=? AND correct_7d IS NOT NULL",
                (ticker,),
            ).fetchone()
            t_total = ticker_total[0] or 0
            t_correct = ticker_total[1] or 0
            hit_rate = round(t_correct / t_total * 100, 1) if t_total > 0 else 0
            upsert_error_pattern(
                f"ticker_streak_{ticker}",
                f"{name}({ticker}) 연속 {streak}회 오답, 전체 적중률 {hit_rate}% ({t_correct}/{t_total})",
                t_correct, t_total - t_correct, hit_rate,
            )

        # 패턴 3: 매수/매도 편향
        dir_rows = conn.execute(
            """SELECT direction, COUNT(*) as total,
                      SUM(CASE WHEN correct_7d=1 THEN 1 ELSE 0 END) as correct
               FROM cio_predictions WHERE correct_7d IS NOT NULL
               GROUP BY direction"""
        ).fetchall()
        for r in dir_rows:
            direction, total, correct = r[0], r[1], r[2]
            miss = total - correct
            hit_rate = round(correct / total * 100, 1) if total > 0 else 0
            if total >= 5 and hit_rate < 45:
                upsert_error_pattern(
                    f"direction_bias_{direction.lower()}",
                    f"{direction} 시그널 적중률 {hit_rate}% ({correct}/{total}건) — 편향 주의",
                    correct, miss, hit_rate,
                )
    finally:
        conn.close()


def _capture_specialist_contributions_sync(
    parsed_signals: list[dict],
    spec_results: list[dict],
    cio_solo_content: str,
    sig_id: str,
) -> None:
    """전문가별 기여를 prediction_specialist_data 테이블에 기록합니다.

    parsed_signals에서 예측 ID를 찾고, spec_results에서 각 전문가의
    추천(BUY/SELL/HOLD)을 파싱하여 저장합니다.
    """
    import json as _json_cap
    import re as _re_cap
    from db import save_prediction_specialist, get_connection

    if not parsed_signals or not spec_results:
        return

    try:
        conn = get_connection()
        # sig_id(task_id)로 저장된 예측 ID들 조회
        pred_rows = conn.execute(
            "SELECT id, ticker, direction FROM cio_predictions WHERE task_id=? ORDER BY id DESC",
            (sig_id,),
        ).fetchall()
        conn.close()

        if not pred_rows:
            logger.debug("[신뢰도] 예측 ID 조회 실패 (sig_id=%s)", sig_id)
            return

        # 전문가별 추천 추출 패턴
        _buy_pat = _re_cap.compile(r"(?:매수|BUY|buy|강력\s*매수|적극\s*매수)", _re_cap.IGNORECASE)
        _sell_pat = _re_cap.compile(r"(?:매도|SELL|sell|강력\s*매도)", _re_cap.IGNORECASE)

        for pred_row in pred_rows:
            pred_id = pred_row[0]

            # CIO 팀장 독자분석 기여 저장
            if cio_solo_content:
                cio_rec = "HOLD"
                if _buy_pat.search(cio_solo_content[:500]):
                    cio_rec = "BUY"
                elif _sell_pat.search(cio_solo_content[:500]):
                    cio_rec = "SELL"
                save_prediction_specialist(
                    prediction_id=pred_id,
                    agent_id="cio_manager",
                    recommendation=cio_rec,
                    confidence=0.0,
                    tools_used="[]",
                    cost_usd=0.0,
                )

            # 각 전문가 기여 저장
            for r in spec_results:
                if not isinstance(r, dict) or "error" in r:
                    continue
                agent_id = r.get("agent_id", "unknown")
                content = r.get("content", "")
                tools = r.get("tools_used", [])
                cost = r.get("cost_usd", 0)

                # 추천 추출
                rec = "HOLD"
                snippet = content[:800] if content else ""
                if _buy_pat.search(snippet):
                    rec = "BUY"
                elif _sell_pat.search(snippet):
                    rec = "SELL"

                save_prediction_specialist(
                    prediction_id=pred_id,
                    agent_id=agent_id,
                    recommendation=rec,
                    confidence=0.0,
                    tools_used=_json_cap.dumps(tools[:20]) if tools else "[]",
                    cost_usd=cost or 0.0,
                )

        logger.info("[신뢰도] 전문가 기여 %d건 × %d예측 캡처 완료",
                     len(spec_results) + (1 if cio_solo_content else 0), len(pred_rows))
    except Exception as e:
        logger.warning("[신뢰도] 전문가 기여 캡처 실패: %s", e)


# ────────────────────────────────────────────────────────────────
# CIO 자기학습 크론 + Shadow Trading 알림
# ────────────────────────────────────────────────────────────────

async def _cio_prediction_verifier():
    """CIO 예측 사후검증: 3일·7일 경과한 예측의 실제 주가 조회 → 맞음/틀림 DB 저장 (매일 KST 03:00)."""
    import pytz as _pytz_v
    _KST_v = _pytz_v.timezone("Asia/Seoul")
    _logger_v = logging.getLogger("corthex.cio_verify")
    _logger_v.info("[CIO검증] 주가 사후검증 루프 시작")

    while True:
        try:
            now = datetime.now(_KST_v)
            # 매일 03:00 KST에 실행
            target = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= target:
                target = target + timedelta(days=1)
            wait_sec = (target - now).total_seconds()
            await asyncio.sleep(wait_sec)

            _logger_v.info("[CIO검증] 사후검증 시작")
            try:
                from db import get_pending_verifications, update_cio_prediction_result
                from kis_client import get_current_price

                verified_count = 0
                verified_results = []

                verified_7d_ids = []  # 7일 검증 완료된 prediction_id (학습 파이프라인용)

                for days in [3, 7]:
                    pending = get_pending_verifications(days_threshold=days)
                    for p in pending:
                        try:
                            price = await get_current_price(p["ticker"])
                            if days == 3:
                                result = update_cio_prediction_result(p["id"], actual_price_3d=price)
                                correct = bool(result.get("correct_3d"))
                                verified_results.append({
                                    "correct_3d": correct, "ticker": p["ticker"],
                                    "direction": p.get("direction", "BUY"),
                                })
                                verified_count += 1
                            else:
                                result = update_cio_prediction_result(p["id"], actual_price_7d=price)
                                if result:
                                    verified_7d_ids.append(p["id"])
                            _logger_v.info("[CIO검증] %s %d일 검증 완료: %d원", p["ticker"], days, price)
                        except Exception as e:
                            _logger_v.warning("[CIO검증] %s 주가 조회 실패: %s", p["ticker"], e)

                save_activity_log("system", f"✅ CIO 예측 사후검증 완료 (3일 {verified_count}건, 7일 {len(verified_7d_ids)}건)", "info")

                # ── 신뢰도 학습 파이프라인 (7일 검증 완료된 건에 대해) ──
                if verified_7d_ids:
                    try:
                        _run_confidence_learning_pipeline(verified_7d_ids)
                        _logger_v.info("[CIO학습] 신뢰도 학습 파이프라인 완료: %d건", len(verified_7d_ids))
                    except Exception as le:
                        _logger_v.warning("[CIO학습] 학습 파이프라인 실패: %s", le)

                # 검증 완료 후 텔레그램 알림 (수정: direction 버그 수정)
                if verified_count > 0:
                    try:
                        ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
                        if app_state.telegram_app and ceo_id:
                            correct_count = sum(1 for r in verified_results if r.get("correct_3d"))
                            accuracy = round(correct_count / verified_count * 100) if verified_count > 0 else 0
                            # ELO 요약 추가
                            from db import get_all_analyst_elos, get_cio_performance_summary
                            elo_data = get_all_analyst_elos()
                            perf = get_cio_performance_summary()
                            elo_section = "\n".join(
                                f"  {e['agent_id'].split('_')[0]}: {e['elo_rating']:.0f}"
                                for e in elo_data[:5]
                            ) if elo_data else "  (초기화 대기 중)"
                            brier_text = f"\nBrier Score: {perf.get('avg_brier_score', '-')}" if perf.get('avg_brier_score') else ""
                            msg = (
                                f"📊 CIO 자기학습 검증 완료\n"
                                f"오늘 검증: {verified_count}건\n"
                                f"3일 정확도: {accuracy}% ({correct_count}/{verified_count})\n"
                                f"전체 7일 정확도: {perf.get('overall_accuracy', '-')}%{brier_text}\n"
                                f"전문가 ELO:\n{elo_section}"
                            )
                            await app_state.telegram_app.bot.send_message(
                                chat_id=int(ceo_id),
                                text=msg,
                            )
                    except Exception as te:
                        _logger_v.warning("[CIO검증] 텔레그램 알림 실패: %s", te)

            except ImportError as e:
                _logger_v.warning("[CIO검증] 필요 함수 미구현 — 스킵: %s", e)
        except Exception as e:
            _logger_v.error("[CIO검증] 에러: %s", e)
            await asyncio.sleep(3600)  # 에러 시 1시간 후 재시도


async def _cio_weekly_soul_update():
    """매주 일요일 KST 02:00: CLO가 CIO 오류 패턴 분석 → cio_manager.md 자동 업데이트."""
    import pytz as _pytz_s
    import re as _re_s
    _KST_s = _pytz_s.timezone("Asia/Seoul")
    _logger_s = logging.getLogger("corthex.cio_soul")
    _logger_s.info("[CIO소울] 주간 soul 업데이트 루프 시작")

    while True:
        try:
            now = datetime.now(_KST_s)
            # 다음 일요일 02:00 KST 계산 (weekday: 월=0, 일=6)
            days_until_sunday = (6 - now.weekday()) % 7
            if days_until_sunday == 0 and now.hour >= 2:
                days_until_sunday = 7
            target = (now + timedelta(days=days_until_sunday)).replace(
                hour=2, minute=0, second=0, microsecond=0
            )
            wait_sec = (target - now).total_seconds()
            await asyncio.sleep(wait_sec)

            try:
                from db import load_cio_predictions, get_cio_performance_summary
                summary = get_cio_performance_summary()
                recent = load_cio_predictions(limit=20)
            except ImportError as e:
                _logger_s.warning("[CIO소울] 필요 함수 미구현 — 스킵: %s", e)
                continue

            # 검증된 예측(7일 결과 있는 것)만 필터링
            verified = [p for p in recent if p.get("correct_7d") is not None]
            if len(verified) < 3:
                _logger_s.info(
                    "[CIO소울] 검증된 예측 %d건 — 업데이트 스킵 (최소 3건 필요)", len(verified)
                )
                continue

            predictions_text = "\n".join([
                f"- {p['ticker']}({p.get('ticker_name', '')}) {p['direction']}: "
                f"{'✅맞음' if p['correct_7d'] == 1 else '❌틀림'} "
                f"(예측가 {p.get('predicted_price', '-')}원 → 7일후 {p.get('actual_price_7d', '-')}원)"
                for p in verified
            ])

            analysis_prompt = (
                "당신은 CLO(준법감시인)입니다. CIO(투자팀장)의 최근 투자 예측 결과를 분석하여,\n"
                "반복되는 오류 패턴을 찾고 cio_manager.md에 추가할 규칙을 제안하세요.\n\n"
                f"## CIO 최근 예측 결과\n"
                f"전체 정확도: {summary.get('overall_accuracy', '-')}%\n"
                f"최근 20건 정확도: {summary.get('recent_20_accuracy', '-')}%\n"
                f"매수 정확도: {summary.get('buy_accuracy', '-')}%\n"
                f"매도 정확도: {summary.get('sell_accuracy', '-')}%\n\n"
                f"## 개별 예측 결과\n{predictions_text}\n\n"
                "## 요청\n"
                "1. 반복 오류 패턴 3가지 분석 (예: '반도체 섹터 과대평가 경향')\n"
                "2. 각 패턴에 대한 개선 규칙 제안 (cio_manager.md에 추가할 마크다운 형식)\n"
                "3. 답변은 반드시 아래 형식:\n"
                "---SOUL_UPDATE_START---\n"
                "[마크다운 형식의 규칙 내용]\n"
                "---SOUL_UPDATE_END---"
            )

            try:
                result_dict = await _call_agent("clo_manager", analysis_prompt)
                result = result_dict.get("content", "") if isinstance(result_dict, dict) else str(result_dict)
                if not result:
                    _logger_s.warning("[CIO소울] CLO 응답 없음")
                    continue

                match = _re_s.search(
                    r"---SOUL_UPDATE_START---\n(.*?)\n---SOUL_UPDATE_END---",
                    result,
                    _re_s.DOTALL,
                )
                if not match:
                    _logger_s.warning("[CIO소울] soul 업데이트 내용 추출 실패")
                    continue

                new_content = match.group(1).strip()
                soul_path = os.path.normpath(
                    os.path.join(os.path.dirname(__file__), "..", "souls", "agents", "cio_manager.md")
                )

                if os.path.exists(soul_path):
                    update_date = datetime.now(_KST_s).strftime("%Y-%m-%d")
                    update_section = (
                        f"\n\n## 자동 학습 업데이트 ({update_date})\n\n{new_content}"
                    )
                    with open(soul_path, "a", encoding="utf-8") as _f:
                        _f.write(update_section)
                    _logger_s.info("[CIO소울] soul 업데이트 완료 (%s)", update_date)
                    save_activity_log("system", f"CIO soul 주간 업데이트 완료 ({update_date})", "info")
                else:
                    _logger_s.warning("[CIO소울] soul 파일 없음: %s", soul_path)
            except Exception as e:
                _logger_s.error("[CIO소울] CLO 분석 실패: %s", e)

        except Exception as e:
            _logger_s.error("[CIO소울] 에러: %s", e)
            await asyncio.sleep(3600)


async def _shadow_trading_alert():
    """Shadow Trading 알림: 모의투자 2주 수익률 +5% 달성 시 텔레그램으로 실거래 전환 추천 (매일 KST 09:00)."""
    import pytz as _pytz_a
    _KST_a = _pytz_a.timezone("Asia/Seoul")
    _logger_a = logging.getLogger("corthex.shadow_alert")
    _logger_a.info("[Shadow알림] Shadow Trading 알림 루프 시작")

    while True:
        try:
            now = datetime.now(_KST_a)
            # 매일 09:00 KST에 실행
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= target:
                target = target + timedelta(days=1)
            wait_sec = (target - now).total_seconds()
            await asyncio.sleep(wait_sec)

            try:
                from kis_client import get_shadow_comparison
                shadow = await get_shadow_comparison()
            except (ImportError, Exception) as e:
                _logger_a.warning("[Shadow알림] shadow 데이터 조회 실패 — 스킵: %s", e)
                continue

            mock_data = shadow.get("mock", {})
            if not mock_data.get("available"):
                continue

            # 2주 수익률 히스토리 추적 (DB에 보관)
            mock_history = load_setting("shadow_mock_history") or []
            today_entry = {
                "date": now.strftime("%Y-%m-%d"),
                "total_eval": mock_data.get("total_eval", 0),
                "cash": mock_data.get("cash", 0),
            }
            mock_history.append(today_entry)
            mock_history = mock_history[-30:]  # 30일치만 보관
            save_setting("shadow_mock_history", mock_history)

            # 2주(14일) 전 데이터와 비교
            if len(mock_history) >= 14:
                old_entry = mock_history[-14]
                old_eval = old_entry.get("total_eval", 0)
                new_eval = today_entry.get("total_eval", 0)

                if old_eval > 0:
                    profit_rate = (new_eval - old_eval) / old_eval * 100

                    if profit_rate >= 5.0:  # B안: 2주 +5% 이상 기준
                        msg = (
                            f"[Shadow Trading 알림]\n\n"
                            f"모의투자 2주 수익률: +{profit_rate:.1f}% 달성!\n"
                            f"기준: 2주 +5% 이상 -> 실거래 전환 추천\n\n"
                            f"모의 현재 평가액: {new_eval:,}원\n"
                            f"2주 전 평가액: {old_eval:,}원\n\n"
                            f"전략실 -> '실거래/모의 비교' 탭에서 확인하세요."
                        )
                        if app_state.telegram_app:
                            ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
                            if ceo_id:
                                try:
                                    await app_state.telegram_app.bot.send_message(
                                        chat_id=int(ceo_id),
                                        text=msg,
                                    )
                                    _logger_a.info(
                                        "[Shadow알림] 실거래 전환 추천 알림 발송 (수익률 %.1f%%)", profit_rate
                                    )
                                    save_activity_log(
                                        "system",
                                        f"Shadow Trading 알림: +{profit_rate:.1f}%",
                                        "info",
                                    )
                                except Exception as e:
                                    _logger_a.error("[Shadow알림] 텔레그램 발송 실패: %s", e)

        except Exception as e:
            _logger_a.error("[Shadow알림] 에러: %s", e)
            await asyncio.sleep(3600)


# ── 실시간 환율 갱신 ──
_FX_UPDATE_INTERVAL = 3600  # 1시간마다 갱신
# app_state.last_fx_update → app_state.last_fx_update 직접 사용

async def _update_fx_rate():
    """yfinance로 USD/KRW 실시간 환율을 가져와 DB에 저장합니다."""

    try:
        import yfinance as yf
        ticker = yf.Ticker("USDKRW=X")
        hist = ticker.history(period="1d")
        if not hist.empty:
            rate = round(float(hist.iloc[-1]["Close"]), 2)
            if 1000 < rate < 2000:  # 비정상 값 필터
                old_rate = _get_fx_rate()
                save_setting("fx_rate_usd_krw", rate)
                app_state.last_fx_update = time.time()
                if abs(rate - old_rate) >= 1:
                    _log(f"[FX] 환율 갱신: ${1} = ₩{rate:,.2f} (이전: ₩{old_rate:,.2f})")
                    save_activity_log("system", f"💱 환율 갱신: ₩{rate:,.2f}/$ (이전 ₩{old_rate:,.2f})", "info")
                return rate
    except ImportError:
        _log("[FX] yfinance 미설치 — 환율 갱신 불가")
    except Exception as e:
        _log(f"[FX] 환율 갱신 실패: {e}")
    return None


def _get_fx_rate() -> float:
    """USD/KRW 환율 반환. DB 설정값 우선, 없으면 1450 폴백.

    모든 환율 참조에서 이 함수를 사용합니다 (하드코딩 방지).
    """
    try:
        rate = load_setting("fx_rate_usd_krw", 1450)
        if isinstance(rate, (int, float)) and 1000 < rate < 2000:
            return float(rate)
    except Exception as e:
        logger.debug("환율 조회 실패: %s", e)
    return 1450.0


# ══════════════════════════════════════════════════════════════════
# ARGOS — 자동 데이터 수집 레이어 (Phase 6-5)
# 서버가 심부름(데이터 수집), AI는 생각(판단)만
# ══════════════════════════════════════════════════════════════════

_ARGOS_LAST_PRICE     = 0.0    # 마지막 주가 수집 시각
_ARGOS_LAST_NEWS      = 0.0    # 마지막 뉴스 수집 시각 (30분)
_ARGOS_LAST_DART      = 0.0    # 마지막 DART 수집 시각 (1시간)
_ARGOS_LAST_MACRO     = 0.0    # 마지막 매크로 수집 시각 (1일)
_ARGOS_LAST_FINANCIAL = 0.0    # 마지막 재무지표 수집 시각 (1일)
_ARGOS_LAST_SECTOR    = 0.0    # 마지막 업종지수 수집 시각 (1일)
_ARGOS_LAST_MONTHLY_RL = 0.0   # 마지막 월간 RL 분석 시각

_ARGOS_NEWS_INTERVAL      = 1800    # 30분
_ARGOS_DART_INTERVAL      = 3600    # 1시간
_ARGOS_MACRO_INTERVAL     = 86400   # 1일
_ARGOS_FINANCIAL_INTERVAL = 86400   # 1일
_ARGOS_SECTOR_INTERVAL    = 86400   # 1일
_ARGOS_MONTHLY_INTERVAL   = 2592000 # 30일

_argos_logger = logging.getLogger("corthex.argos")


def _argos_update_status(data_type: str, error: str = "", count_delta: int = 0) -> None:
    """ARGOS 수집 상태를 DB에 기록합니다."""
    try:
        conn = get_connection()
        now = datetime.now(KST).isoformat()
        conn.execute(
            """INSERT INTO argos_collection_status(data_type, last_collected, last_error, total_count, updated_at)
               VALUES(?, ?, ?, ?, ?)
               ON CONFLICT(data_type) DO UPDATE SET
                 last_collected = CASE WHEN excluded.last_error='' THEN excluded.last_collected ELSE last_collected END,
                 last_error = excluded.last_error,
                 total_count = total_count + excluded.total_count,
                 updated_at = excluded.updated_at""",
            (data_type, now if not error else "", error, count_delta, now)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        _argos_logger.debug("상태 기록 실패: %s", e)


_argos_price_running = False  # 동시 실행 방지 플래그

async def _argos_collect_prices() -> int:
    """관심종목 주가를 pykrx/yfinance로 수집해 DB에 누적합니다 (90일 보존).
    타임아웃: 종목당 20초. 동시 실행 방지 플래그.
    Returns: 저장된 행 수
    """
    global _argos_price_running
    if _argos_price_running:
        _argos_logger.debug("ARGOS 주가 수집 이미 진행 중 — 스킵")
        return 0

    _argos_price_running = True
    try:
        watchlist = _load_data("trading_watchlist", [])
        if not watchlist:
            return 0

        conn = get_connection()
        saved = 0
        now_str = datetime.now(KST).isoformat()
        today = datetime.now(KST).strftime("%Y%m%d")
        # 첫 수집은 7일만 (빠르게), DB에 데이터 있으면 3일만 보충
        try:
            existing = conn.execute("SELECT COUNT(*) FROM argos_price_history").fetchone()[0]
        except Exception:
            existing = 0
        fetch_days = 7 if existing == 0 else 3
        start = (datetime.now(KST) - timedelta(days=fetch_days)).strftime("%Y%m%d")

        kr_tickers = [w for w in watchlist if w.get("market", "KR") == "KR"]
        us_tickers = [w for w in watchlist if w.get("market") == "US"]
        PER_TICKER_TIMEOUT = 20  # 초

        try:
            # ── 한국 주식 (pykrx) ──
            if kr_tickers:
                try:
                    from pykrx import stock as pykrx_stock
                    for w in kr_tickers:
                        ticker = w["ticker"]
                        try:
                            df = await asyncio.wait_for(
                                asyncio.to_thread(
                                    pykrx_stock.get_market_ohlcv_by_date, start, today, ticker
                                ),
                                timeout=PER_TICKER_TIMEOUT,
                            )
                            if df is None or df.empty:
                                _argos_logger.debug("PRICE KR %s: 데이터 없음", ticker)
                                continue
                            ticker_saved = 0
                            for dt_idx, row in df.iterrows():
                                trade_date = str(dt_idx)[:10]
                                close = float(row.get("종가", 0))
                                if close <= 0:
                                    continue
                                prev_rows = df[df.index < dt_idx]
                                prev_close = float(prev_rows.iloc[-1]["종가"]) if not prev_rows.empty else close
                                change_pct = round((close - prev_close) / prev_close * 100, 2) if prev_close else 0
                                conn.execute(
                                    """INSERT OR IGNORE INTO argos_price_history
                                       (ticker, market, trade_date, open_price, high_price, low_price,
                                        close_price, volume, change_pct, collected_at)
                                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                                    (ticker, "KR", trade_date,
                                     float(row.get("시가", close)), float(row.get("고가", close)),
                                     float(row.get("저가", close)), close,
                                     int(row.get("거래량", 0)), change_pct, now_str)
                                )
                                ticker_saved += 1
                            conn.commit()  # 종목별 즉시 커밋 → DB 잠금 최소화
                            saved += ticker_saved
                            _argos_logger.info("PRICE KR %s: %d행 저장 (%d일)", ticker, ticker_saved, fetch_days)
                        except asyncio.TimeoutError:
                            _argos_logger.warning("KR %s: %d초 타임아웃 — 스킵", ticker, PER_TICKER_TIMEOUT)
                        except Exception as e:
                            _argos_logger.debug("KR 주가 파싱 실패 (%s): %s", ticker, e)
                except ImportError:
                    _argos_logger.debug("pykrx 미설치 — 국내 주가 수집 불가")

            # ── 미국 주식 (yfinance) ──
            if us_tickers:
                try:
                    import yfinance as yf
                    period = "7d" if existing == 0 else "3d"
                    for w in us_tickers:
                        ticker = w["ticker"]
                        try:
                            t_obj = yf.Ticker(ticker)
                            hist = await asyncio.wait_for(
                                asyncio.to_thread(lambda t=t_obj, p=period: t.history(period=p)),
                                timeout=PER_TICKER_TIMEOUT,
                            )
                            if hist is None or hist.empty:
                                _argos_logger.debug("PRICE US %s: 데이터 없음", ticker)
                                continue
                            ticker_saved = 0
                            prev_close_val = None
                            for dt_idx, row in hist.iterrows():
                                trade_date = str(dt_idx)[:10]
                                close = round(float(row["Close"]), 4)
                                if close <= 0:
                                    continue
                                chg = round((close - prev_close_val) / prev_close_val * 100, 2) if prev_close_val else 0
                                conn.execute(
                                    """INSERT OR IGNORE INTO argos_price_history
                                       (ticker, market, trade_date, open_price, high_price, low_price,
                                        close_price, volume, change_pct, collected_at)
                                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                                    (ticker, "US", trade_date,
                                     round(float(row.get("Open", close)), 4),
                                     round(float(row.get("High", close)), 4),
                                     round(float(row.get("Low", close)), 4),
                                     close, int(row.get("Volume", 0)), chg, now_str)
                                )
                                ticker_saved += 1
                                prev_close_val = close
                            conn.commit()  # 종목별 즉시 커밋 → DB 잠금 최소화
                            saved += ticker_saved
                            _argos_logger.info("PRICE US %s: %d행 저장 (%s)", ticker, ticker_saved, period)
                        except asyncio.TimeoutError:
                            _argos_logger.warning("US %s: %d초 타임아웃 — 스킵", ticker, PER_TICKER_TIMEOUT)
                        except Exception as e:
                            _argos_logger.debug("US 주가 파싱 실패 (%s): %s", ticker, e)
                except ImportError:
                    _argos_logger.debug("yfinance 미설치 — 해외 주가 수집 불가")

            conn.commit()

            # 90일 초과 데이터 정리
            cutoff = (datetime.now(KST) - timedelta(days=90)).strftime("%Y-%m-%d")
            conn.execute("DELETE FROM argos_price_history WHERE trade_date < ?", (cutoff,))
            conn.commit()
        finally:
            conn.close()

        _argos_logger.info("ARGOS 주가 수집 완료: %d행 (fetch_days=%d)", saved, fetch_days)
        return saved
    finally:
        _argos_price_running = False


async def _argos_collect_news() -> int:
    """네이버 뉴스 API로 관심종목 뉴스를 수집해 DB에 저장합니다 (30일 보존).
    Returns: 저장된 행 수
    """
    naver_id = os.getenv("NAVER_CLIENT_ID", "")
    naver_secret = os.getenv("NAVER_CLIENT_SECRET", "")
    if not naver_id or not naver_secret:
        _argos_logger.debug("NAVER_CLIENT_ID/SECRET 미설정 — 뉴스 수집 불가")
        return 0

    watchlist = _load_data("trading_watchlist", [])
    if not watchlist:
        return 0

    import urllib.request
    import urllib.parse
    conn = get_connection()
    saved = 0
    now_str = datetime.now(KST).isoformat()

    try:
        for w in watchlist[:10]:  # 과부하 방지: 최대 10종목
            keyword = w.get("name") or w.get("ticker", "")
            if not keyword:
                continue
            try:
                encoded = urllib.parse.quote(keyword)
                url = f"https://openapi.naver.com/v1/search/news.json?query={encoded}&display=20&sort=date"
                req = urllib.request.Request(url, headers={
                    "X-Naver-Client-Id": naver_id,
                    "X-Naver-Client-Secret": naver_secret,
                })
                def _fetch(r=req):
                    with urllib.request.urlopen(r, timeout=5) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                data = await asyncio.to_thread(_fetch)
                for item in data.get("items", []):
                    title = re.sub(r"<[^>]+>", "", item.get("title", ""))
                    desc = re.sub(r"<[^>]+>", "", item.get("description", ""))
                    pub_date = item.get("pubDate", now_str)
                    link = item.get("link", "")
                    conn.execute(
                        """INSERT OR IGNORE INTO argos_news_cache
                           (keyword, title, description, link, pub_date, source, collected_at)
                           VALUES(?,?,?,?,?,?,?)""",
                        (keyword, title, desc, link, pub_date, "naver", now_str)
                    )
                    saved += 1
                conn.commit()  # 키워드별 즉시 커밋 → DB 잠금 최소화
            except Exception as e:
                _argos_logger.debug("뉴스 수집 실패 (%s): %s", keyword, e)

        cutoff = (datetime.now(KST) - timedelta(days=30)).isoformat()
        conn.execute("DELETE FROM argos_news_cache WHERE pub_date < ?", (cutoff,))
        conn.commit()
    finally:
        conn.close()

    return saved


async def _argos_collect_dart() -> int:
    """DART 공시를 수집해 DB에 저장합니다 (90일 보존).
    Returns: 저장된 행 수
    """
    dart_key = os.getenv("DART_API_KEY", "")
    if not dart_key:
        _argos_logger.debug("DART_API_KEY 미설정 — DART 수집 불가")
        return 0

    watchlist = _load_data("trading_watchlist", [])
    kr_tickers = [w for w in watchlist if w.get("market", "KR") == "KR"]
    if not kr_tickers:
        return 0

    import urllib.request
    import urllib.parse
    conn = get_connection()
    saved = 0
    now_str = datetime.now(KST).isoformat()
    bgn_de = (datetime.now(KST) - timedelta(days=90)).strftime("%Y%m%d")

    try:
        for w in kr_tickers[:10]:  # 과부하 방지
            ticker = w["ticker"]
            try:
                params = urllib.parse.urlencode({
                    "crtfc_key": dart_key,
                    "stock_code": ticker,
                    "bgn_de": bgn_de,
                    "sort": "date",
                    "sort_mth": "desc",
                    "page_count": 20,
                })
                url = f"https://opendart.fss.or.kr/api/list.json?{params}"
                def _fetch(u=url):
                    with urllib.request.urlopen(u, timeout=8) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                data = await asyncio.to_thread(_fetch)
                for item in data.get("list", []):
                    conn.execute(
                        """INSERT OR IGNORE INTO argos_dart_filings
                           (ticker, corp_name, report_nm, rcept_no, flr_nm, rcept_dt, collected_at)
                           VALUES(?,?,?,?,?,?,?)""",
                        (ticker, item.get("corp_name",""), item.get("report_nm",""),
                         item.get("rcept_no",""), item.get("flr_nm",""),
                         item.get("rcept_dt",""), now_str)
                    )
                    saved += 1
                conn.commit()  # 종목별 즉시 커밋 → DB 잠금 최소화
            except Exception as e:
                _argos_logger.debug("DART 수집 실패 (%s): %s", ticker, e)

        cutoff = (datetime.now(KST) - timedelta(days=90)).strftime("%Y%m%d")
        conn.execute("DELETE FROM argos_dart_filings WHERE rcept_dt < ?", (cutoff,))
        conn.commit()
    finally:
        conn.close()

    return saved


async def _argos_collect_macro() -> int:
    """KOSPI/KOSDAQ/환율 등 매크로 지표를 수집합니다.
    타임아웃: 항목당 15초.
    Returns: 저장된 행 수
    """
    MACRO_TIMEOUT = 15  # 초
    conn = get_connection()
    saved = 0
    now_str = datetime.now(KST).isoformat()
    today_iso = datetime.now(KST).strftime("%Y-%m-%d")

    try:
        # USD/KRW — yfinance
        try:
            import yfinance as yf
            def _fetch_fx():
                t = yf.Ticker("USDKRW=X")
                h = t.history(period="5d")
                return float(h.iloc[-1]["Close"]) if h is not None and not h.empty else None
            rate = await asyncio.wait_for(asyncio.to_thread(_fetch_fx), timeout=MACRO_TIMEOUT)
            if rate:
                conn.execute(
                    "INSERT OR IGNORE INTO argos_macro_data(indicator,trade_date,value,source,collected_at) VALUES(?,?,?,?,?)",
                    ("USD_KRW", today_iso, round(rate, 2), "yfinance", now_str)
                )
                saved += 1
                conn.commit()  # 즉시 커밋
                _argos_logger.info("MACRO USD/KRW: %.2f", rate)
        except asyncio.TimeoutError:
            _argos_logger.warning("USD/KRW: %d초 타임아웃", MACRO_TIMEOUT)
        except Exception as e:
            _argos_logger.debug("USD/KRW 수집 실패: %s", e)

        # KOSPI / KOSDAQ — pykrx
        try:
            from pykrx import stock as pykrx_stock
            today = datetime.now(KST).strftime("%Y%m%d")
            start = (datetime.now(KST) - timedelta(days=7)).strftime("%Y%m%d")
            for ticker, label in [("1001", "KOSPI"), ("2001", "KOSDAQ")]:
                try:
                    df = await asyncio.wait_for(
                        asyncio.to_thread(
                            pykrx_stock.get_index_ohlcv_by_date, start, today, ticker
                        ),
                        timeout=MACRO_TIMEOUT,
                    )
                    if df is not None and not df.empty:
                        close = float(df.iloc[-1]["종가"])
                        trade_date = str(df.index[-1])[:10]
                        conn.execute(
                            "INSERT OR IGNORE INTO argos_macro_data(indicator,trade_date,value,source,collected_at) VALUES(?,?,?,?,?)",
                            (label, trade_date, round(close, 2), "pykrx", now_str)
                        )
                        conn.commit()  # 즉시 커밋
                        saved += 1
                        _argos_logger.info("MACRO %s: %.2f", label, close)
                except asyncio.TimeoutError:
                    _argos_logger.warning("%s: %d초 타임아웃", label, MACRO_TIMEOUT)
                except Exception as e:
                    _argos_logger.debug("%s 수집 실패: %s", label, e)
        except ImportError:
            pass

        # VIX — yfinance
        try:
            import yfinance as yf
            def _fetch_vix():
                t = yf.Ticker("^VIX")
                h = t.history(period="5d")
                return float(h.iloc[-1]["Close"]) if h is not None and not h.empty else None
            vix = await asyncio.wait_for(asyncio.to_thread(_fetch_vix), timeout=MACRO_TIMEOUT)
            if vix:
                conn.execute(
                    "INSERT OR IGNORE INTO argos_macro_data(indicator,trade_date,value,source,collected_at) VALUES(?,?,?,?,?)",
                    ("VIX", today_iso, round(vix, 2), "yfinance", now_str)
                )
                conn.commit()  # 즉시 커밋
                saved += 1
                _argos_logger.info("MACRO VIX: %.2f", vix)
        except asyncio.TimeoutError:
            _argos_logger.warning("VIX: %d초 타임아웃", MACRO_TIMEOUT)
        except Exception as e:
            _argos_logger.debug("VIX 수집 실패: %s", e)


        # S&P500 / 나스닥 / 미국 10년 국채금리 — yfinance
        for yf_ticker, label in [("^GSPC", "SP500"), ("^IXIC", "NASDAQ"), ("^TNX", "US10Y")]:
            try:
                import yfinance as yf
                def _fetch_yf(sym=yf_ticker):
                    t = yf.Ticker(sym)
                    h = t.history(period="5d")
                    return float(h.iloc[-1]["Close"]) if h is not None and not h.empty else None
                val = await asyncio.wait_for(asyncio.to_thread(_fetch_yf), timeout=MACRO_TIMEOUT)
                if val:
                    conn.execute(
                        "INSERT OR IGNORE INTO argos_macro_data(indicator,trade_date,value,source,collected_at) VALUES(?,?,?,?,?)",
                        (label, today_iso, round(val, 4), "yfinance", now_str)
                    )
                    conn.commit()
                    saved += 1
                    _argos_logger.info("MACRO %s: %.4f", label, val)
            except asyncio.TimeoutError:
                _argos_logger.warning("%s: %d초 타임아웃", label, MACRO_TIMEOUT)
            except Exception as e:
                _argos_logger.debug("%s 수집 실패: %s", label, e)

        # 한국 기준금리 — ECOS API
        try:
            ecos_key = os.getenv("ECOS_API_KEY", "")
            if ecos_key:
                import urllib.request
                ecos_url = (
                    f"https://ecos.bok.or.kr/api/StatisticSearch/{ecos_key}/json/kr"
                    f"/1/5/722Y001/M/{today_iso[:4]}{today_iso[5:7]}/{today_iso[:4]}{today_iso[5:7]}"
                )
                def _fetch_ecos(url=ecos_url):
                    with urllib.request.urlopen(url, timeout=10) as r:
                        import json as _json
                        return _json.loads(r.read().decode("utf-8"))
                ecos_data = await asyncio.wait_for(asyncio.to_thread(_fetch_ecos), timeout=MACRO_TIMEOUT)
                rows_ecos = ecos_data.get("StatisticSearch", {}).get("row", [])
                if rows_ecos:
                    rate = float(rows_ecos[-1].get("DATA_VALUE", 0))
                    period = rows_ecos[-1].get("TIME", today_iso[:7])
                    trade_date_ecos = f"{period[:4]}-{period[4:6]}-01"
                    conn.execute(
                        "INSERT OR IGNORE INTO argos_macro_data(indicator,trade_date,value,source,collected_at) VALUES(?,?,?,?,?)",
                        ("KR_RATE", trade_date_ecos, rate, "ecos", now_str)
                    )
                    conn.commit()
                    saved += 1
                    _argos_logger.info("MACRO KR_RATE: %.2f%%", rate)
        except asyncio.TimeoutError:
            _argos_logger.warning("KR_RATE: %d초 타임아웃", MACRO_TIMEOUT)
        except Exception as e:
            _argos_logger.debug("KR_RATE 수집 실패: %s", e)

        cutoff = (datetime.now(KST) - timedelta(days=365)).strftime("%Y-%m-%d")
        conn.execute("DELETE FROM argos_macro_data WHERE trade_date < ?", (cutoff,))
        conn.commit()
    finally:
        conn.close()

    _argos_logger.info("ARGOS 매크로 수집 완료: %d건", saved)
    return saved


_argos_seq_lock = asyncio.Lock()  # 순차 수집 중복 실행 방지 (Lock 기반)

async def _argos_sequential_collect(now_ts: float):
    """ARGOS 수집을 순차 실행합니다 (DB lock 방지).
    동시에 여러 수집이 DB를 잡지 않도록 하나씩 순서대로.
    """
    global _ARGOS_LAST_NEWS, _ARGOS_LAST_DART, _ARGOS_LAST_MACRO, _ARGOS_LAST_FINANCIAL, _ARGOS_LAST_SECTOR
    if _argos_seq_lock.locked():
        return
    async with _argos_seq_lock:
        try:
            # 1) 주가 — 매 사이클
            await _argos_collect_prices_safe()

            # 2) 뉴스 — 30분마다
            if now_ts - _ARGOS_LAST_NEWS > _ARGOS_NEWS_INTERVAL:
                _ARGOS_LAST_NEWS = now_ts
                await _argos_collect_news_safe()

            # 3) DART — 1시간마다
            if now_ts - _ARGOS_LAST_DART > _ARGOS_DART_INTERVAL:
                _ARGOS_LAST_DART = now_ts
                await _argos_collect_dart_safe()

            # 4) 매크로 — 1일마다 (S&P500/나스닥/국채금리/기준금리 포함)
            if now_ts - _ARGOS_LAST_MACRO > _ARGOS_MACRO_INTERVAL:
                _ARGOS_LAST_MACRO = now_ts
                await _argos_collect_macro_safe()

            # 5) 재무지표 — 1일마다 (PER/PBR/EPS/BPS)
            if now_ts - _ARGOS_LAST_FINANCIAL > _ARGOS_FINANCIAL_INTERVAL:
                _ARGOS_LAST_FINANCIAL = now_ts
                await _argos_collect_financial_safe()

            # 6) 업종지수 — 1일마다 (전기전자/화학/금융 등 11개)
            if now_ts - _ARGOS_LAST_SECTOR > _ARGOS_SECTOR_INTERVAL:
                _ARGOS_LAST_SECTOR = now_ts
                await _argos_collect_sector_safe()
        except Exception as e:
            _argos_logger.error("ARGOS 순차 수집 오류: %s", e)


async def _argos_collect_prices_safe():
    """주가 수집 — 예외 안전 래퍼. 전체 3분 타임아웃."""
    try:
        n = await asyncio.wait_for(_argos_collect_prices(), timeout=180)
        if n > 0:
            _argos_update_status("price", count_delta=n)
    except asyncio.TimeoutError:
        _argos_update_status("price", error="전체 3분 타임아웃")
        _argos_logger.error("ARGOS 주가 수집: 전체 3분 타임아웃")
    except Exception as e:
        _argos_update_status("price", error=str(e)[:200])
        _argos_logger.error("ARGOS 주가 수집 실패: %s", e)


async def _argos_collect_news_safe():
    """뉴스 수집 — 예외 안전 래퍼. 전체 2분 타임아웃."""
    try:
        n = await asyncio.wait_for(_argos_collect_news(), timeout=120)
        _argos_update_status("news", count_delta=n)
        _argos_logger.info("ARGOS 뉴스 수집 완료: %d건", n)
    except asyncio.TimeoutError:
        _argos_update_status("news", error="전체 2분 타임아웃")
        _argos_logger.error("ARGOS 뉴스 수집: 전체 2분 타임아웃")
    except Exception as e:
        _argos_update_status("news", error=str(e)[:200])
        _argos_logger.error("ARGOS 뉴스 수집 실패: %s", e)


async def _argos_collect_dart_safe():
    """DART 수집 — 예외 안전 래퍼. 전체 2분 타임아웃."""
    try:
        n = await asyncio.wait_for(_argos_collect_dart(), timeout=120)
        _argos_update_status("dart", count_delta=n)
        _argos_logger.info("ARGOS DART 수집 완료: %d건", n)
    except asyncio.TimeoutError:
        _argos_update_status("dart", error="전체 2분 타임아웃")
        _argos_logger.error("ARGOS DART 수집: 전체 2분 타임아웃")
    except Exception as e:
        _argos_update_status("dart", error=str(e)[:200])
        _argos_logger.error("ARGOS DART 수집 실패: %s", e)


async def _argos_collect_macro_safe():
    """매크로 수집 — 예외 안전 래퍼. 전체 2분 타임아웃."""
    try:
        n = await asyncio.wait_for(_argos_collect_macro(), timeout=120)
        _argos_update_status("macro", count_delta=n)
        _argos_logger.info("ARGOS 매크로 수집 완료: %d건", n)
    except asyncio.TimeoutError:
        _argos_update_status("macro", error="전체 2분 타임아웃")
        _argos_logger.error("ARGOS 매크로 수집: 전체 2분 타임아웃")
    except Exception as e:
        _argos_update_status("macro", error=str(e)[:200])
        _argos_logger.error("ARGOS 매크로 수집 실패: %s", e)


async def _argos_collect_financial() -> int:
    """pykrx로 관심종목 재무지표(PER/PBR/EPS 등)를 수집해 DB에 저장 (1일 1회).
    Returns: 저장된 행 수
    """
    conn = get_connection()
    saved = 0
    now_str = datetime.now(KST).isoformat()
    today = datetime.now(KST).strftime("%Y%m%d")
    today_iso = datetime.now(KST).strftime("%Y-%m-%d")

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS argos_financial_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                per REAL, pbr REAL, eps REAL, dps REAL, bps REAL,
                source TEXT DEFAULT 'pykrx',
                collected_at TEXT,
                UNIQUE(ticker, trade_date)
            )
        """)
        conn.commit()

        from pykrx import stock as pykrx_stock
        watchlist = _load_data("trading_watchlist", [])
        kr_tickers = [w for w in watchlist if w.get("market", "KR") == "KR"]
        if not kr_tickers:
            return 0

        for w in kr_tickers:
            ticker = w["ticker"]
            try:
                df = await asyncio.wait_for(
                    asyncio.to_thread(pykrx_stock.get_market_fundamental, today, ticker=ticker),
                    timeout=20,
                )
                if df is not None and not df.empty:
                    row = df.iloc[-1]
                    conn.execute(
                        """INSERT OR IGNORE INTO argos_financial_data
                           (ticker, trade_date, per, pbr, eps, dps, bps, source, collected_at)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (ticker, today_iso,
                         float(row.get("PER", 0) or 0),
                         float(row.get("PBR", 0) or 0),
                         float(row.get("EPS", 0) or 0),
                         float(row.get("DPS", 0) or 0),
                         float(row.get("BPS", 0) or 0),
                         "pykrx", now_str)
                    )
                    conn.commit()
                    saved += 1
                    _argos_logger.info("FINANCIAL %s: PER=%.1f PBR=%.2f", ticker,
                                       row.get("PER", 0), row.get("PBR", 0))
            except asyncio.TimeoutError:
                _argos_logger.warning("FINANCIAL %s: 20초 타임아웃", ticker)
            except Exception as e:
                _argos_logger.debug("FINANCIAL %s 실패: %s", ticker, e)

        cutoff = (datetime.now(KST) - timedelta(days=90)).strftime("%Y-%m-%d")
        conn.execute("DELETE FROM argos_financial_data WHERE trade_date < ?", (cutoff,))
        conn.commit()
    except ImportError:
        _argos_logger.debug("pykrx 미설치 — 재무지표 수집 불가")
    finally:
        conn.close()

    _argos_logger.info("ARGOS 재무지표 수집 완료: %d건", saved)
    return saved


async def _argos_collect_financial_safe():
    """재무지표 수집 — 예외 안전 래퍼. 전체 3분 타임아웃."""
    try:
        n = await asyncio.wait_for(_argos_collect_financial(), timeout=180)
        _argos_update_status("financial", count_delta=n)
        _argos_logger.info("ARGOS 재무지표 수집 완료: %d건", n)
    except asyncio.TimeoutError:
        _argos_update_status("financial", error="전체 3분 타임아웃")
        _argos_logger.error("ARGOS 재무지표 수집: 전체 3분 타임아웃")
    except Exception as e:
        _argos_update_status("financial", error=str(e)[:200])
        _argos_logger.error("ARGOS 재무지표 수집 실패: %s", e)


async def _argos_collect_sector() -> int:
    """pykrx로 주요 업종지수를 수집해 DB에 저장 (1일 1회).
    Returns: 저장된 행 수
    """
    SECTOR_CODES = [
        ("1028", "전기전자"), ("1003", "화학"), ("1004", "의약품"),
        ("1006", "철강금속"), ("1008", "기계"), ("1022", "유통업"),
        ("1024", "건설업"), ("1027", "통신업"), ("1029", "금융업"),
        ("1032", "서비스업"), ("1005", "비금속광물"),
    ]
    conn = get_connection()
    saved = 0
    now_str = datetime.now(KST).isoformat()

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS argos_sector_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sector_name TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close_val REAL,
                change_pct REAL,
                source TEXT DEFAULT 'pykrx',
                collected_at TEXT,
                UNIQUE(sector_name, trade_date)
            )
        """)
        conn.commit()

        from pykrx import stock as pykrx_stock
        today = datetime.now(KST).strftime("%Y%m%d")
        start = (datetime.now(KST) - timedelta(days=7)).strftime("%Y%m%d")

        for code, name in SECTOR_CODES:
            try:
                df = await asyncio.wait_for(
                    asyncio.to_thread(pykrx_stock.get_index_ohlcv_by_date, start, today, code),
                    timeout=15,
                )
                if df is not None and not df.empty:
                    close = float(df.iloc[-1]["종가"])
                    trade_date = str(df.index[-1])[:10]
                    # 전일 대비 등락률
                    change_pct = 0.0
                    if len(df) >= 2:
                        prev = float(df.iloc[-2]["종가"])
                        change_pct = (close - prev) / prev * 100 if prev != 0 else 0.0
                    conn.execute(
                        """INSERT OR IGNORE INTO argos_sector_data
                           (sector_name, trade_date, close_val, change_pct, source, collected_at)
                           VALUES(?,?,?,?,?,?)""",
                        (name, trade_date, round(close, 2), round(change_pct, 2), "pykrx", now_str)
                    )
                    conn.commit()
                    saved += 1
                    _argos_logger.info("SECTOR %s: %.2f (%+.2f%%)", name, close, change_pct)
            except asyncio.TimeoutError:
                _argos_logger.warning("SECTOR %s: 15초 타임아웃", name)
            except Exception as e:
                _argos_logger.debug("SECTOR %s 실패: %s", name, e)

        cutoff = (datetime.now(KST) - timedelta(days=90)).strftime("%Y-%m-%d")
        conn.execute("DELETE FROM argos_sector_data WHERE trade_date < ?", (cutoff,))
        conn.commit()
    except ImportError:
        _argos_logger.debug("pykrx 미설치 — 업종지수 수집 불가")
    finally:
        conn.close()

    _argos_logger.info("ARGOS 업종지수 수집 완료: %d건", saved)
    return saved


async def _argos_collect_sector_safe():
    """업종지수 수집 — 예외 안전 래퍼. 전체 3분 타임아웃."""
    try:
        n = await asyncio.wait_for(_argos_collect_sector(), timeout=180)
        _argos_update_status("sector", count_delta=n)
        _argos_logger.info("ARGOS 업종지수 수집 완료: %d건", n)
    except asyncio.TimeoutError:
        _argos_update_status("sector", error="전체 3분 타임아웃")
        _argos_logger.error("ARGOS 업종지수 수집: 전체 3분 타임아웃")
    except Exception as e:
        _argos_update_status("sector", error=str(e)[:200])
        _argos_logger.error("ARGOS 업종지수 수집 실패: %s", e)


async def _argos_monthly_rl_analysis():
    """월 1회: AI에게 최근 오답 패턴 분석 요청 → error_patterns 테이블 업데이트.
    Phase 6-9 강화학습 파이프라인.
    """
    _argos_logger.info("📊 월간 강화학습 패턴 분석 시작")
    save_activity_log("system", "📊 월간 강화학습 패턴 분석 시작 (크론)", "info")
    try:
        conn = get_connection()
        # 최근 30일 내 틀린 예측 집계
        rows = conn.execute(
            """SELECT ticker, direction, confidence, return_pct_7d, analyzed_at
               FROM cio_predictions
               WHERE correct_7d = 0
                 AND analyzed_at >= datetime('now', '-30 days')
               ORDER BY analyzed_at DESC
               LIMIT 30"""
        ).fetchall()
        conn.close()

        if not rows:
            _argos_logger.info("최근 30일 오답 없음 — 패턴 분석 스킵")
            return

        wrong_list = [
            f"- {r[0]} ({r[1]}, 신뢰도 {r[2]}%) → 실제수익 {r[3]}% ({r[4][:10]})"
            for r in rows
        ]
        prompt = (
            "다음은 최근 30일간 틀린 매매 예측 목록입니다:\n"
            + "\n".join(wrong_list)
            + "\n\n공통 패턴을 분석해주세요: "
            "① 어떤 종목/방향에서 많이 틀렸나? "
            "② 높은 신뢰도인데 틀린 케이스 원인? "
            "③ 다음 분석 시 주의사항 3가지를 간결하게 요약하세요."
        )

        from ai_handler import ask_ai
        result = await ask_ai(
            agent_id="secretary",
            messages=[{"role": "user", "content": prompt}],
            model=None,  # config/models.yaml에서 자동 선택
            task_id=f"rl_monthly_{datetime.now(KST).strftime('%Y%m')}",
        )

        analysis_text = result.get("content", "")
        if analysis_text:
            conn = get_connection()
            conn.execute(
                """INSERT INTO error_patterns
                   (pattern_type, description, ticker_filter, direction_filter,
                    confidence_threshold, active, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                ("monthly_rl", analysis_text[:2000], "", "", 0.0, 1,
                 datetime.now(KST).isoformat(), datetime.now(KST).isoformat())
            )
            conn.commit()
            conn.close()
            save_activity_log("system", f"📊 월간 RL 패턴 분석 완료 ({len(rows)}건 분석)", "success")
            _argos_logger.info("월간 RL 패턴 분석 완료: %d건", len(rows))
    except Exception as e:
        _argos_logger.error("월간 RL 패턴 분석 실패: %s", e)


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

            # ── ARGOS: 자동 데이터 수집 레이어 (Phase 6-5) ──
            # DB lock 방지: 순차 실행 (하나 끝나면 다음 실행)
            _now_ts = time.time()
            global _ARGOS_LAST_PRICE, _ARGOS_LAST_NEWS, _ARGOS_LAST_DART, _ARGOS_LAST_MACRO, _ARGOS_LAST_MONTHLY_RL
            asyncio.create_task(_argos_sequential_collect(_now_ts))

            # 월간 강화학습 패턴 분석 (Phase 6-9)
            if _now_ts - _ARGOS_LAST_MONTHLY_RL > _ARGOS_MONTHLY_INTERVAL:
                _ARGOS_LAST_MONTHLY_RL = _now_ts
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

# ── 자동매매 시스템 (KIS 한국투자증권 프레임워크) ──

# app_state.trading_bot_active, app_state.trading_bot_task → app_state 직접 사용

# ── 시세 캐시 → app_state 사용 ──
_price_cache = app_state.price_cache
_price_cache_lock = app_state.price_cache_lock


async def _auto_refresh_prices():
    """관심종목 시세를 1분마다 자동 갱신."""
    while True:
        try:
            await asyncio.sleep(60)
            watchlist = _load_data("trading_watchlist", [])
            if not watchlist:
                continue

            new_cache = {}
            kr_tickers = [w for w in watchlist if w.get("market", "KR") == "KR"]
            us_tickers = [w for w in watchlist if w.get("market") == "US"]

            # 한국 주식 (pykrx)
            if kr_tickers:
                try:
                    from pykrx import stock as pykrx_stock
                    today = datetime.now(KST).strftime("%Y%m%d")
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
                                new_cache[w["ticker"]] = {
                                    "price": close,
                                    "change_pct": change_pct,
                                    "updated_at": datetime.now(KST).isoformat(),
                                }
                        except Exception as e:
                            logger.debug("국내 종목 시세 파싱 실패 (%s): %s", w.get("ticker"), e)
                except Exception as e:
                    logger.debug("pykrx 시세 조회 실패: %s", e)

            # 미국 주식 (yfinance)
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
                                new_cache[w["ticker"]] = {
                                    "price": close,
                                    "change_pct": change_pct,
                                    "updated_at": datetime.now(KST).isoformat(),
                                }
                        except Exception as e:
                            logger.debug("해외 종목 시세 파싱 실패 (%s): %s", w.get("ticker"), e)
                except Exception as e:
                    logger.debug("yfinance 시세 조회 실패: %s", e)

            if new_cache:
                async with _price_cache_lock:
                    _price_cache.update(new_cache)
                _log(f"[PRICE] 시세 자동 갱신 완료 — {len(new_cache)}종목")
        except Exception as e:
            _log(f"[PRICE] 시세 자동 갱신 오류: {e}")
            await asyncio.sleep(60)


def _default_portfolio() -> dict:
    """기본 포트폴리오 데이터."""
    return {
        "cash": 50_000_000,    # 초기 현금 (5천만원)
        "initial_cash": 50_000_000,
        "holdings": [],        # [{ticker, name, qty, avg_price, current_price}]
        "updated_at": datetime.now(KST).isoformat(),
    }


# ── 투자 성향 시스템 (CEO B안 승인: 성향 + CIO 자율) ──

# 성향별 안전 범위 — CIO가 이 범위 안에서만 자유롭게 변경 가능
RISK_PROFILES = {
    "aggressive": {
        "label": "공격적", "emoji": "🔥",
        "cash_reserve":       {"min": 5,  "max": 20,  "default": 10},
        "max_position_pct":   {"min": 15, "max": 35,  "default": 30},
        "min_confidence":     {"min": 50, "max": 75,  "default": 55},
        "default_stop_loss":  {"min": -12,"max": -3,  "default": -8},
        "default_take_profit":{"min": 5,  "max": 40,  "default": 15},
        "max_daily_trades":   {"min": 5,  "max": 20,  "default": 15},
        "max_daily_loss_pct": {"min": 2,  "max": 8,   "default": 5},
        "order_size":         {"min": 0,  "max": 10_000_000, "default": 0},
    },
    "balanced": {
        "label": "균형", "emoji": "⚖️",
        "cash_reserve":       {"min": 15, "max": 35,  "default": 20},
        "max_position_pct":   {"min": 10, "max": 25,  "default": 20},
        "min_confidence":     {"min": 55, "max": 80,  "default": 65},
        "default_stop_loss":  {"min": -8, "max": -2,  "default": -5},
        "default_take_profit":{"min": 5,  "max": 25,  "default": 10},
        "max_daily_trades":   {"min": 3,  "max": 15,  "default": 10},
        "max_daily_loss_pct": {"min": 1,  "max": 5,   "default": 3},
        "order_size":         {"min": 0,  "max": 5_000_000, "default": 0},
    },
    "conservative": {
        "label": "보수적", "emoji": "🐢",
        "cash_reserve":       {"min": 30, "max": 60,  "default": 40},
        "max_position_pct":   {"min": 5,  "max": 15,  "default": 10},
        "min_confidence":     {"min": 65, "max": 90,  "default": 75},
        "default_stop_loss":  {"min": -5, "max": -1,  "default": -3},
        "default_take_profit":{"min": 3,  "max": 15,  "default": 8},
        "max_daily_trades":   {"min": 1,  "max": 8,   "default": 5},
        "max_daily_loss_pct": {"min": 1,  "max": 3,   "default": 2},
        "order_size":         {"min": 0,  "max": 2_000_000, "default": 0},
    },
}


def _get_risk_profile() -> str:
    """현재 투자 성향 조회 (DB에서)."""
    return load_setting("trading_risk_profile", "aggressive")


def _clamp_setting(key: str, value, profile: str = None) -> float | int:
    """설정값을 현재 투자 성향의 안전 범위 내로 클램핑합니다."""
    if profile is None:
        profile = _get_risk_profile()
    ranges = RISK_PROFILES.get(profile, RISK_PROFILES["balanced"])
    r = ranges.get(key)
    if r is None:
        return value
    return max(r["min"], min(r["max"], value))


def _default_trading_settings() -> dict:
    """기본 자동매매 설정."""
    return {
        "max_position_pct": 20,       # 종목당 최대 비중 (%)
        "max_daily_trades": 10,       # 일일 최대 거래 횟수
        "max_daily_loss_pct": 3,      # 일일 최대 손실 (%)
        "default_stop_loss_pct": -5,  # 기본 손절 (%)
        "default_take_profit_pct": 10, # 기본 익절 (%)
        "order_size": 0,              # 0 = CIO 비중 자율
        "trading_hours_kr": {"start": "09:00", "end": "15:20"},   # 한국 장 시간
        "trading_hours_us": {"start": "22:30", "end": "05:00"},   # 미국 장 시간 (KST 기준, 서머타임 시 23:30)
        "trading_hours": {"start": "09:00", "end": "15:20"},      # 하위호환
        "auto_stop_loss": True,       # 자동 손절 활성화
        "auto_take_profit": True,     # 자동 익절 활성화
        "auto_execute": False,        # CIO 시그널 기반 자동 주문 실행 (안전장치: 기본 OFF)
        # --- 신뢰도 임계값 (연구 기반 조정) ---
        # 근거: LLM은 실제 정확도보다 10~20% 과신 (FinGPT 2023, GPT-4 Trading 2024 논문)
        # 한국장 손익비 1:2 (손절 -5%, 익절 +10%) → 손익분기 승률 ≒ 33%
        # LLM 실제 방향성 예측 정확도 55~65% → 임계값 65% = 과신 할인 적용 후 최소 수익선
        "min_confidence": 65,         # 자동매매 최소 신뢰도 (%, 연구 기반: 기존 70→65)
        "kis_connected": False,       # KIS(한국투자증권) API 연결 여부
        "paper_trading": True,        # 모의투자 모드 (실거래 전)
        "enable_real": True,          # 실거래 계좌에 주문
        "enable_mock": False,         # 모의투자 계좌에 주문
        # --- AI 자기보정(Self-Calibration) ---
        # 원리: Platt Scaling 단순화 — 실제 승률/예측 신뢰도 비율로 보정 계수 계산
        # factor < 1.0: AI 과신 → 유효 신뢰도 하향 보정 / factor > 1.0: AI 겸손 → 상향
        "calibration_enabled": True,  # AI 자기보정 활성화
        "calibration_lookback": 20,   # 보정 계산에 사용할 최근 거래 수
    }


def _compute_calibration_factor(lookback: int = 20) -> dict:
    """실제 승률 vs 예측 신뢰도 비율로 AI 자기보정 계수를 계산합니다.

    방법론: Platt Scaling 단순화 버전
    - LLM은 예측 신뢰도를 실제 정확도보다 과대 보고하는 경향이 있음
      (FinGPT 2023 / GPT-4 Trading 2024 논문에서 10~20% 과신 확인)
    - 보정 계수(factor) = 실제 승률 / 예측 평균 신뢰도
    - factor < 1: AI 과신 → 유효 신뢰도 하향 / factor > 1: AI 겸손 → 상향
    - 안전 범위: 0.5 ~ 1.5 (극단적 보정 방지)
    """
    import re as _re
    history = _load_data("trading_history", [])
    bot_trades = [
        h for h in history
        if h.get("auto_bot", False) or "신뢰도" in h.get("strategy", "")
    ]
    recent = bot_trades[:lookback]

    if len(recent) < 5:
        return {
            "factor": 1.0, "win_rate": None, "avg_confidence": None,
            "n": len(recent), "note": f"데이터 부족 ({len(recent)}건, 최소 5건 필요) — 보정 미적용",
        }

    closed = [h for h in recent if h.get("action") == "sell" and "pnl" in h]
    if not closed:
        return {
            "factor": 1.0, "win_rate": None, "avg_confidence": None,
            "n": 0, "note": "평가 가능한 매도 기록 없음 — 보정 미적용",
        }

    wins = sum(1 for t in closed if t.get("pnl", 0) > 0)
    actual_win_rate = wins / len(closed)

    confidences = []
    for t in closed:
        m = _re.search(r"신뢰도\s*(\d+)", t.get("strategy", ""))
        if m:
            confidences.append(int(m.group(1)) / 100.0)

    if not confidences:
        return {
            "factor": 1.0, "win_rate": round(actual_win_rate * 100, 1),
            "avg_confidence": None, "n": len(closed),
            "note": "신뢰도 기록 없음 — 보정 미적용",
        }

    avg_confidence = sum(confidences) / len(confidences)
    raw_factor = actual_win_rate / avg_confidence if avg_confidence > 0 else 1.0
    factor = round(max(0.5, min(1.5, raw_factor)), 3)

    diff = actual_win_rate * 100 - avg_confidence * 100
    if diff < -5:
        note = f"AI 과신 (예측 {avg_confidence*100:.0f}% → 실제 {actual_win_rate*100:.0f}%) → 신뢰도 {factor:.2f}배 하향 보정"
    elif diff > 5:
        note = f"AI 겸손 (예측 {avg_confidence*100:.0f}% → 실제 {actual_win_rate*100:.0f}%) → 신뢰도 {factor:.2f}배 상향 보정"
    else:
        note = f"AI 보정 미미 (예측≒실제, factor={factor:.2f})"

    return {
        "factor": factor,
        "win_rate": round(actual_win_rate * 100, 1),
        "avg_confidence": round(avg_confidence * 100, 1),
        "n": len(closed),
        "note": note,
    }


def _build_calibration_prompt_section(settings: dict | None = None) -> str:
    """CIO 분석 프롬프트에 삽입할 자기학습 보정 섹션을 구축합니다.

    포함 항목:
    1. 기존 Platt Scaling 보정 (호환성)
    2. 베이지안 구간별 보정 데이터
    3. 전문가 ELO 가중치
    4. 오답 패턴 경고
    5. 도구 추천/경고
    """
    from db import (
        get_all_calibration_buckets, get_all_analyst_elos,
        get_active_error_patterns, get_tool_effectiveness_all,
    )

    if settings is None:
        settings = {}

    parts = []

    # ─ 1. 베이지안 구간별 보정 ─
    try:
        buckets = get_all_calibration_buckets()
        if buckets:
            rows = []
            for b in buckets:
                total = b.get("total_count", 0)
                if total < 3:
                    continue
                actual = b.get("actual_rate", 0)
                ci_lo = b.get("ci_lower", 0)
                ci_hi = b.get("ci_upper", 1)
                actual_pct = round(actual * 100, 1)
                ci_lo_pct = round(ci_lo * 100)
                ci_hi_pct = round(ci_hi * 100)
                # 보정 방향 판단
                bucket_label = b["bucket"]
                mid = 0.5  # 기본
                try:
                    lo, hi = bucket_label.split("-")
                    mid = (int(lo) + int(hi)) / 200.0
                except Exception:
                    pass
                if actual < mid - 0.05:
                    direction = "↓ 하향 보정 필요"
                elif actual > mid + 0.05:
                    direction = "↑ 상향 가능"
                else:
                    direction = "≈ 적정"
                rows.append(f"| {bucket_label}% | {total}건 | {actual_pct}% | [{ci_lo_pct}-{ci_hi_pct}%] | {direction} |")

            if rows:
                parts.append(
                    "\n## 📊 신뢰도 보정 데이터 (Bayesian Calibration)\n"
                    "| 구간 | 예측 횟수 | 실제 적중률 | 95% CI | 보정 방향 |\n"
                    "|------|----------|-----------|--------|----------|\n"
                    + "\n".join(rows)
                    + "\n→ 위 데이터를 참고하여 신뢰도 수치를 보정하세요."
                )
    except Exception:
        pass

    # ─ 2. 전문가 ELO 가중치 ─
    try:
        elos = get_all_analyst_elos()
        if elos and len(elos) >= 2:
            elo_rows = []
            for e in sorted(elos, key=lambda x: x.get("elo_rating", 1500), reverse=True):
                agent = e["agent_id"].replace("_specialist", "").replace("_", " ").title()
                rating = round(e.get("elo_rating", 1500))
                total = e.get("total_predictions", 0)
                correct = e.get("correct_predictions", 0)
                hit = round(correct / total * 100) if total > 0 else 0
                weight = "★★★" if rating >= 1560 else ("★★" if rating >= 1520 else "★")
                elo_rows.append(f"| {agent} | {rating} | {hit}% ({correct}/{total}) | {weight} |")

            if elo_rows:
                parts.append(
                    "\n## 🏆 전문가 신뢰 가중치 (ELO 기반)\n"
                    "| 전문가 | ELO | 적중률 | 가중치 |\n"
                    "|--------|-----|--------|--------|\n"
                    + "\n".join(elo_rows)
                    + "\n→ ELO 높은 전문가의 의견에 더 높은 가중치를 부여하세요."
                )
    except Exception:
        pass

    # ─ 3. 오답 패턴 경고 ─
    try:
        patterns = get_active_error_patterns()
        if patterns:
            warns = []
            for p in patterns[:5]:
                warns.append(f"- {p['description']}")
            parts.append(
                "\n## ⚠️ 주의 패턴 (최근 오류에서 학습)\n"
                + "\n".join(warns)
            )
    except Exception:
        pass

    # ─ 4. 도구 추천/경고 ─
    try:
        tools = get_tool_effectiveness_all()
        if tools and len(tools) >= 3:
            good = [t for t in tools if t.get("total_uses", 0) >= 3 and t.get("eff_score", 0.5) >= 0.6]
            bad = [t for t in tools if t.get("total_uses", 0) >= 3 and t.get("eff_score", 0.5) < 0.45]
            tool_lines = []
            if good:
                good_s = sorted(good, key=lambda x: x["eff_score"], reverse=True)[:4]
                names = ", ".join(f"{t['tool_name']}({round(t['eff_score']*100)}%)" for t in good_s)
                tool_lines.append(f"- 우수: {names}")
            if bad:
                bad_s = sorted(bad, key=lambda x: x["eff_score"])[:3]
                names = ", ".join(f"{t['tool_name']}({round(t['eff_score']*100)}%)" for t in bad_s)
                tool_lines.append(f"- 부진: {names} — 분석 참고만, 결정 기반 금지")
            if tool_lines:
                parts.append(
                    "\n## 🔧 도구 추천 (성과 기반)\n"
                    + "\n".join(tool_lines)
                )
    except Exception:
        pass

    # ─ 5. 기존 Platt Scaling 보정 (하위 호환) ─
    if settings.get("calibration_enabled", True):
        calibration = _compute_calibration_factor(settings.get("calibration_lookback", 20))
        if calibration.get("win_rate") is not None:
            diff = calibration["win_rate"] - (calibration.get("avg_confidence") or calibration["win_rate"])
            direction = "보수적으로" if diff < -5 else ("적극적으로" if diff > 5 else "현재 수준으로")
            parts.append(
                f"\n## 📈 매매 성과 보정 (Platt Scaling)\n"
                f"- 최근 {calibration['n']}건 실제 승률: {calibration['win_rate']}%\n"
                f"- 평균 예측 신뢰도: {calibration.get('avg_confidence', 'N/A')}%\n"
                f"- {calibration['note']}\n"
                f"→ 이번 신뢰도를 {direction} 설정하세요."
            )

    return "\n".join(parts) if parts else ""


# ── [QUANT SCORE] 정량 신뢰도 계산 (RSI/MACD/볼린저밴드/거래량/이동평균) ──

async def _compute_quant_score(ticker: str, market: str = "KR", lookback: int = 60) -> dict:
    """RSI(14)/MACD(12,26,9)/볼린저밴드(20,2σ)/거래량/이동평균으로 정량 신뢰도 계산.

    LLM이 신뢰도를 직접 찍는 대신, 이 함수 계산값을 기준으로 ±20%p 조정만 허용.
    반환: {ticker, direction, quant_confidence(0-99), components, summary, error}
    """
    _err = {
        "ticker": ticker, "direction": "neutral", "quant_confidence": 50,
        "components": {}, "summary": "정량 데이터 없음 — AI 판단 사용", "error": None,
    }
    try:
        closes: list = []
        volumes: list = []

        if market == "KR":
            try:
                from pykrx import stock as _pykrx
                _today = datetime.now(KST).strftime("%Y%m%d")
                _start = (datetime.now(KST) - timedelta(days=lookback + 30)).strftime("%Y%m%d")
                df = await asyncio.to_thread(_pykrx.get_market_ohlcv_by_date, _start, _today, ticker)
                if df is None or df.empty or len(df) < 20:
                    return {**_err, "error": f"pykrx 데이터 부족 ({0 if df is None else len(df)}일)"}
                closes = df["종가"].astype(float).tolist()
                volumes = df["거래량"].astype(float).tolist()
            except Exception as e:
                return {**_err, "error": f"pykrx: {str(e)[:60]}"}
        else:
            try:
                import yfinance as yf
                _t = yf.Ticker(ticker)
                hist = await asyncio.to_thread(lambda: _t.history(period="3mo"))
                if hist is None or hist.empty or len(hist) < 20:
                    return {**_err, "error": "yfinance 데이터 부족"}
                closes = hist["Close"].astype(float).tolist()
                volumes = hist["Volume"].astype(float).tolist()
            except Exception as e:
                return {**_err, "error": f"yfinance: {str(e)[:60]}"}

        n = len(closes)

        # ── RSI(14) ──
        def _rsi(prices, p=14):
            if len(prices) < p + 1:
                return 50.0
            d = [prices[i] - prices[i-1] for i in range(1, len(prices))]
            g = [max(x, 0.0) for x in d[-p:]]
            l = [abs(min(x, 0.0)) for x in d[-p:]]
            ag, al = sum(g)/p, sum(l)/p
            return 100.0 if al == 0 else 100 - 100/(1 + ag/al)

        rsi = _rsi(closes)

        # ── RSI → 방향 투표 (방향과 신뢰도 분리) ──
        if   rsi < 30: rsi_dir, rsi_str, rsi_sig = "buy",  0.8, f"과매도({rsi:.1f})"
        elif rsi < 40: rsi_dir, rsi_str, rsi_sig = "buy",  0.5, f"매수우호({rsi:.1f})"
        elif rsi < 45: rsi_dir, rsi_str, rsi_sig = "neutral", 0.2, f"중립({rsi:.1f})"
        elif rsi < 55: rsi_dir, rsi_str, rsi_sig = "neutral", 0.1, f"중립({rsi:.1f})"
        elif rsi < 60: rsi_dir, rsi_str, rsi_sig = "neutral", 0.2, f"중립({rsi:.1f})"
        elif rsi < 70: rsi_dir, rsi_str, rsi_sig = "sell", 0.5, f"매도우호({rsi:.1f})"
        else:          rsi_dir, rsi_str, rsi_sig = "sell", 0.8, f"과매수({rsi:.1f})"

        # ── MACD(12, 26, 9) → 방향 투표 ──
        def _ema(prices, p):
            if len(prices) < p:
                return [prices[-1]]
            k = 2 / (p + 1)
            vals = [sum(prices[:p]) / p]
            for x in prices[p:]:
                vals.append(x * k + vals[-1] * (1 - k))
            return vals

        macd_dir, macd_str, macd_sig = "neutral", 0.1, "데이터부족"
        if n >= 27:
            e12 = _ema(closes, 12)
            e26 = _ema(closes, 26)
            ml = min(len(e12), len(e26))
            macd_line = [e12[i] - e26[i] for i in range(-ml, 0)]
            if len(macd_line) >= 9:
                sig_line = _ema(macd_line, 9)
                if sig_line:
                    mv, sv = macd_line[-1], sig_line[-1]
                    mv2 = macd_line[-2] if len(macd_line) >= 2 else mv
                    sv2 = sig_line[-2] if len(sig_line) >= 2 else sv
                    if   mv2 < sv2 and mv > sv:           macd_dir, macd_str, macd_sig = "buy",  0.9, "골든크로스↑"
                    elif mv2 > sv2 and mv < sv:           macd_dir, macd_str, macd_sig = "sell", 0.9, "데드크로스↓"
                    elif mv > sv and (mv-sv) > (mv2-sv2): macd_dir, macd_str, macd_sig = "buy",  0.6, "MACD>시그널상승"
                    elif mv > sv:                         macd_dir, macd_str, macd_sig = "buy",  0.3, "MACD>시그널"
                    elif mv < sv and (mv-sv) < (mv2-sv2): macd_dir, macd_str, macd_sig = "sell", 0.6, "MACD<시그널하락"
                    else:                                 macd_dir, macd_str, macd_sig = "sell", 0.3, "MACD<시그널"

        # ── 볼린저밴드(20, 2σ) → 방향 투표 ──
        bb_dir, bb_str, bb_sig, pct_b = "neutral", 0.1, "데이터부족", 0.5
        if n >= 20:
            sma = sum(closes[-20:]) / 20
            std = (sum((c - sma)**2 for c in closes[-20:]) / 20) ** 0.5
            bw = 4 * std
            if bw > 0:
                pct_b = (closes[-1] - (sma - 2*std)) / bw
                if   pct_b <= 0.10: bb_dir, bb_str, bb_sig = "buy",  0.9, f"하단돌파(%B={pct_b:.2f})"
                elif pct_b <= 0.25: bb_dir, bb_str, bb_sig = "buy",  0.6, f"하단근접(%B={pct_b:.2f})"
                elif pct_b <= 0.40: bb_dir, bb_str, bb_sig = "buy",  0.2, f"중하단(%B={pct_b:.2f})"
                elif pct_b <= 0.60: bb_dir, bb_str, bb_sig = "neutral", 0.1, f"중간(%B={pct_b:.2f})"
                elif pct_b <= 0.75: bb_dir, bb_str, bb_sig = "sell", 0.2, f"중상단(%B={pct_b:.2f})"
                elif pct_b <= 0.90: bb_dir, bb_str, bb_sig = "sell", 0.6, f"상단근접(%B={pct_b:.2f})"
                else:               bb_dir, bb_str, bb_sig = "sell", 0.9, f"상단돌파(%B={pct_b:.2f})"

        # ── 거래량 (방향 아닌 확신 보정용) ──
        vol_adj, vol_sig = 0, "보통"
        vol_ratio = 1.0
        if n >= 20 and len(volumes) >= 20:
            avg_v = sum(volumes[-20:-1]) / 19
            if avg_v > 0:
                vol_ratio = volumes[-1] / avg_v
                if   vol_ratio >= 2.0: vol_adj, vol_sig = 8,  f"급증({vol_ratio:.1f}x)"
                elif vol_ratio >= 1.5: vol_adj, vol_sig = 5,  f"증가({vol_ratio:.1f}x)"
                elif vol_ratio < 0.8:  vol_adj, vol_sig = -5, f"감소({vol_ratio:.1f}x)"
                else:                  vol_sig = f"보통({vol_ratio:.1f}x)"

        # ── 이동평균 추세 → 방향 투표 ──
        ma5  = round(sum(closes[-5:]) /5)  if n >= 5  else 0
        ma20 = round(sum(closes[-20:])/20) if n >= 20 else 0
        ma60 = round(sum(closes[-60:])/60) if n >= 60 else 0
        if ma5 and ma20 and ma60:
            if   ma5 > ma20 > ma60: tr_dir, tr_str, tr_sig = "buy",  0.8, "상승정렬(5>20>60)"
            elif ma5 > ma20:        tr_dir, tr_str, tr_sig = "buy",  0.4, "단기반등"
            elif ma5 < ma20 < ma60: tr_dir, tr_str, tr_sig = "sell", 0.8, "하락정렬(5<20<60)"
            else:                   tr_dir, tr_str, tr_sig = "neutral", 0.2, "혼조세"
        elif ma5 and ma20:
            if ma5 > ma20: tr_dir, tr_str, tr_sig = "buy",  0.4, "단기상승"
            else:          tr_dir, tr_str, tr_sig = "sell", 0.4, "단기하락"
        else:
            tr_dir, tr_str, tr_sig = "neutral", 0.1, "데이터부족"

        # ── 종합: 방향 = 다수결, 신뢰도 = 합의율 ──
        votes = [
            ("RSI",  rsi_dir,  rsi_str),
            ("MACD", macd_dir, macd_str),
            ("BB",   bb_dir,   bb_str),
            ("MA",   tr_dir,   tr_str),
        ]
        buy_votes  = [(nm, st) for nm, d, st in votes if d == "buy"]
        sell_votes = [(nm, st) for nm, d, st in votes if d == "sell"]
        n_votes = len(votes)

        if len(buy_votes) > len(sell_votes):
            direction = "buy"
            winner_count = len(buy_votes)
            winner_avg_str = sum(s for _, s in buy_votes) / len(buy_votes)
        elif len(sell_votes) > len(buy_votes):
            direction = "sell"
            winner_count = len(sell_votes)
            winner_avg_str = sum(s for _, s in sell_votes) / len(sell_votes)
        else:
            direction = "neutral"
            winner_count = 0
            winner_avg_str = 0.3

        # 합의율 → 기본 신뢰도 (30~90% 범위)
        if direction == "neutral":
            base_conf = 50
        else:
            consensus = winner_count / n_votes  # 0.25~1.0
            base_conf = 35 + consensus * 55     # 1/4→49, 2/4→63, 3/4→76, 4/4→90
            # 강도 보정: 같은 3/4라도 신호 강도가 다름
            strength_adj = (winner_avg_str - 0.5) * 10  # -5 ~ +4
            base_conf += strength_adj

        qconf = int(max(30, min(95, base_conf + vol_adj)))
        dir_kr = {"buy": "매수", "sell": "매도", "neutral": "관망"}[direction]
        vote_detail = " / ".join(
            f"{nm}→{'매수' if d == 'buy' else '매도' if d == 'sell' else '중립'}"
            for nm, d, _ in votes
        )
        summary = (
            f"RSI {rsi:.0f} / MACD {macd_sig} / BB {bb_sig} / 거래량 {vol_sig}"
            f" → 투표 [{vote_detail}] = {winner_count}/{n_votes} 합의"
            f" → 정량신뢰도 {qconf}%({dir_kr})"
        )
        return {
            "ticker": ticker, "direction": direction, "quant_confidence": qconf,
            "components": {
                "rsi":       {"value": round(rsi, 1), "direction": rsi_dir, "strength": rsi_str, "signal": rsi_sig},
                "macd":      {"direction": macd_dir, "strength": macd_str, "signal": macd_sig},
                "bollinger": {"pct_b": round(pct_b, 2), "direction": bb_dir, "strength": bb_str, "signal": bb_sig},
                "volume":    {"ratio": round(vol_ratio, 1), "adj": vol_adj, "signal": vol_sig},
                "trend":     {"ma5": ma5, "ma20": ma20, "ma60": ma60, "direction": tr_dir, "strength": tr_str, "signal": tr_sig},
            },
            "votes": {"buy": len(buy_votes), "sell": len(sell_votes), "neutral": n_votes - len(buy_votes) - len(sell_votes)},
            "summary": summary, "error": None,
        }
    except Exception as e:
        return {**_err, "error": f"계산오류: {str(e)[:80]}"}


async def _build_quant_prompt_section(market_watchlist: list, market: str = "KR") -> str:
    """관심종목 전체 정량지표를 병렬 계산 → 프롬프트 삽입용 테이블 반환."""
    if not market_watchlist:
        return ""
    try:
        tasks = [_compute_quant_score(w["ticker"], market) for w in market_watchlist]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        rows = []
        for w, r in zip(market_watchlist, results):
            if isinstance(r, Exception) or (isinstance(r, dict) and r.get("error")):
                rows.append(
                    f"| {w['name']}({w['ticker']}) | 조회실패 | — | — | — | — | — | **50% 판단불가** |"
                )
                continue
            c = r["components"]
            d_kr = {"buy": "매수", "sell": "매도", "neutral": "관망"}[r["direction"]]
            v = r.get("votes", {})
            vote_str = f"매수{v.get('buy',0)}:매도{v.get('sell',0)}:중립{v.get('neutral',0)}"
            rows.append(
                f"| {w['name']}({w['ticker']}) "
                f"| {c['rsi']['signal']} "
                f"| {c['macd']['signal']} "
                f"| {c['bollinger']['signal']} "
                f"| {c['volume']['signal']} "
                f"| {c['trend']['signal']} "
                f"| {vote_str} "
                f"| **{r['quant_confidence']}% {d_kr}** |"
            )
        return (
            "\n\n## 📐 정량지표 사전분석 (서버 자동계산 — 지표 합의 방식)\n"
            "| 종목 | RSI(14) | MACD | 볼린저밴드 | 거래량 | 추세(MA) | 지표투표 | 합의신뢰도 |\n"
            "|------|---------|------|-----------|--------|---------|---------|------------|\n"
            + "\n".join(rows)
            + "\n\n⚠️ 위 합의신뢰도는 4개 기술지표의 방향 합의율입니다."
            " 뉴스/실적/수급/매크로 등 정성분석을 반영하여 **±20%p 범위 내**에서 조정하세요."
            " 근거를 반드시 명시하세요."
        )
    except Exception as e:
        return f"\n\n## 📐 정량지표 (계산 실패: {str(e)[:60]})\n"


async def _build_argos_context_section(market_watchlist: list, market: str = "KR") -> str:
    """ARGOS DB에서 수집된 데이터를 꺼내 팀장 프롬프트에 직접 주입.

    서버가 심부름(데이터 수집)을 완료 → 팀장은 해석만.
    DB에 데이터 없으면 해당 섹션 생략 (팀장이 판단하도록).
    """
    conn = get_connection()
    sections = []

    # ① 종목별 최근 주가 (최근 10거래일)
    price_rows_all = []
    for w in market_watchlist:
        ticker = w["ticker"]
        try:
            rows = conn.execute(
                """SELECT trade_date, close_price, change_pct, volume
                   FROM argos_price_history
                   WHERE ticker=?
                   ORDER BY trade_date DESC LIMIT 10""",
                (ticker,)
            ).fetchall()
            if rows:
                price_rows_all.append((w["name"], ticker, rows))
        except Exception:
            pass

    if price_rows_all:
        lines = ["\n\n## 📈 최근 주가 (ARGOS 수집 — 서버 제공)"]
        for name, ticker, rows in price_rows_all:
            latest = rows[0]
            unit = "원" if market == "KR" else "USD"
            lines.append(f"\n### {name} ({ticker})")
            lines.append(f"  현재가: {latest[1]:,.0f}{unit}  전일대비: {(latest[2] or 0):+.2f}%")
            lines.append("  | 날짜 | 종가 | 등락률 | 거래량 |")
            lines.append("  |------|------|--------|--------|")
            for r in rows:
                lines.append(f"  | {r[0]} | {r[1]:,.0f} | {(r[2] or 0):+.2f}% | {(r[3] or 0):,.0f} |")
        sections.append("\n".join(lines))

    # ② 매크로 지표 (KOSPI, USD_KRW 등)
    try:
        macro_rows = conn.execute(
            """SELECT indicator, trade_date, value
               FROM argos_macro_data
               ORDER BY indicator, trade_date DESC"""
        ).fetchall()
        if macro_rows:
            macro_dict: dict = {}
            for r in macro_rows:
                if r[0] not in macro_dict:
                    macro_dict[r[0]] = (r[1], r[2])
            lines = ["\n\n## 🌐 매크로 지표 (ARGOS 수집 — 서버 제공)"]
            for indicator, (dt, val) in macro_dict.items():
                lines.append(f"  {indicator}: {val:,.2f} ({dt})")
            sections.append("\n".join(lines))
    except Exception:
        pass

    # ③ 최신 공시 (DART — ticker 기준)
    dart_found = []
    for w in market_watchlist:
        ticker = w["ticker"]
        try:
            rows = conn.execute(
                """SELECT corp_name, report_nm, rcept_dt
                   FROM argos_dart_filings
                   WHERE ticker=?
                   ORDER BY rcept_dt DESC LIMIT 5""",
                (ticker,)
            ).fetchall()
            if rows:
                dart_found.append((w["name"], ticker, rows))
        except Exception:
            pass

    if dart_found:
        lines = ["\n\n## 📋 최신 공시 (ARGOS 수집 — 서버 제공)"]
        for name, ticker, rows in dart_found:
            lines.append(f"\n### {name} ({ticker})")
            for r in rows:
                lines.append(f"  [{r[2]}] {r[1]}")
        sections.append("\n".join(lines))

    # ④ 뉴스 캐시 (종목명 키워드)
    news_found = []
    for w in market_watchlist:
        keyword = w["name"]
        try:
            rows = conn.execute(
                """SELECT title, description, pub_date
                   FROM argos_news_cache
                   WHERE keyword=?
                   ORDER BY pub_date DESC LIMIT 5""",
                (keyword,)
            ).fetchall()
            if rows:
                news_found.append((keyword, rows))
        except Exception:
            pass

    if news_found:
        lines = ["\n\n## 📰 최신 뉴스 (ARGOS 수집 — 서버 제공)"]
        for keyword, rows in news_found:
            lines.append(f"\n### {keyword}")
            for r in rows:
                title = (r[0] or "")[:60]
                desc = (r[1] or "")[:80]
                lines.append(f"  [{r[2][:10] if r[2] else ''}] {title}")
                if desc:
                    lines.append(f"    → {desc}")
        sections.append("\n".join(lines))

    # ⑤ 재무지표 (PER/PBR/EPS — pykrx 1일 수집)
    try:
        conn2 = get_connection()
        fin_found = []
        for w in market_watchlist:
            ticker = w["ticker"]
            try:
                row = conn2.execute(
                    """SELECT trade_date, per, pbr, eps, bps
                       FROM argos_financial_data
                       WHERE ticker=?
                       ORDER BY trade_date DESC LIMIT 1""",
                    (ticker,)
                ).fetchone()
                if row:
                    fin_found.append((w["name"], ticker, row))
            except Exception:
                pass
        conn2.close()
        if fin_found:
            lines = ["\n\n## 💹 재무지표 (ARGOS 수집 — 서버 제공)"]
            lines.append("  | 종목 | PER | PBR | EPS | BPS | 기준일 |")
            lines.append("  |------|-----|-----|-----|-----|--------|")
            for name, ticker, r in fin_found:
                lines.append(f"  | {name}({ticker}) | {r[1]:.1f} | {r[2]:.2f} | {r[3]:,.0f} | {r[4]:,.0f} | {r[0]} |")
            sections.append("\n".join(lines))
    except Exception:
        pass

    # ⑥ 업종지수 (pykrx 11개 업종 — 1일 수집)
    try:
        conn3 = get_connection()
        sector_rows = conn3.execute(
            """SELECT s1.sector_name, s1.close_val, s1.change_pct, s1.trade_date
               FROM argos_sector_data s1
               INNER JOIN (
                   SELECT sector_name, MAX(trade_date) AS max_date
                   FROM argos_sector_data GROUP BY sector_name
               ) s2 ON s1.sector_name=s2.sector_name AND s1.trade_date=s2.max_date
               ORDER BY s1.change_pct DESC"""
        ).fetchall()
        conn3.close()
        if sector_rows:
            lines = ["\n\n## 🏭 업종지수 (ARGOS 수집 — 서버 제공)"]
            lines.append("  | 업종 | 지수 | 등락률 | 기준일 |")
            lines.append("  |------|------|--------|--------|")
            for r in sector_rows:
                arrow = "▲" if r[2] > 0 else ("▼" if r[2] < 0 else "─")
                lines.append(f"  | {r[0]} | {r[1]:,.2f} | {arrow}{abs(r[2]):.2f}% | {r[3]} |")
            sections.append("\n".join(lines))
    except Exception:
        pass

    if not sections:
        return "\n\n## 📡 ARGOS 수집 데이터 없음 (수집 중이거나 관심종목 미등록)"

    return "".join(sections)


# ── [PRICE TRIGGERS] 목표가/손절/익절 자동 주문 ──

def _register_position_triggers(
    ticker: str, name: str, buy_price: float, qty: int,
    market: str, settings: dict, source_id: str = "",
) -> None:
    """매수 체결 후 자동 손절/익절 트리거 등록."""
    if buy_price <= 0 or qty <= 0:
        return
    sl_pct = settings.get("default_stop_loss_pct", -5)
    tp_pct = settings.get("default_take_profit_pct", 10)
    stop_price = round(buy_price * (1 + sl_pct / 100))
    take_price = round(buy_price * (1 + tp_pct / 100))
    now_str = datetime.now(KST).isoformat()
    base_id = f"{ticker}_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}"
    new_triggers = [
        {
            "id": f"sl_{base_id}", "ticker": ticker, "name": name,
            "type": "stop_loss", "trigger_price": stop_price, "qty": qty,
            "market": market, "active": True, "created_at": now_str,
            "source": "auto_buy", "source_id": source_id,
            "note": f"매수가 {buy_price:,.0f} × {1+sl_pct/100:.2f} = {stop_price:,.0f} 손절",
        },
        {
            "id": f"tp_{base_id}", "ticker": ticker, "name": name,
            "type": "take_profit", "trigger_price": take_price, "qty": qty,
            "market": market, "active": True, "created_at": now_str,
            "source": "auto_buy", "source_id": source_id,
            "note": f"매수가 {buy_price:,.0f} × {1+tp_pct/100:.2f} = {take_price:,.0f} 익절",
        },
    ]
    triggers = _load_data("price_triggers", [])
    triggers = new_triggers + triggers
    if len(triggers) > 500:
        triggers = triggers[:500]
    _save_data("price_triggers", triggers)
    save_activity_log(
        "cio_manager",
        f"🎯 트리거 등록: {name} 손절 {stop_price:,.0f} / 익절 {take_price:,.0f} ({sl_pct}%/{tp_pct}%)",
        "info",
    )


async def _check_price_triggers() -> None:
    """1분마다 가격 모니터링 → 목표가 도달 시 자동 주문 실행."""
    triggers = _load_data("price_triggers", [])
    active = [t for t in triggers if t.get("active", True)]
    if not active:
        return

    settings = _load_data("trading_settings", _default_trading_settings())
    enable_mock = settings.get("enable_mock", False)
    use_kis = _KIS_AVAILABLE and _kis_configured()
    use_mock_kis = (not use_kis) and enable_mock and _KIS_AVAILABLE and _kis_mock_configured()

    async with _price_cache_lock:
        prices_snapshot = dict(_price_cache)

    triggered_ids: set = set()
    for t in active:
        ticker = t["ticker"]
        if ticker not in prices_snapshot:
            continue
        current_price = prices_snapshot[ticker]["price"]
        tp_val = t["trigger_price"]
        ttype  = t["type"]

        if   ttype == "stop_loss"   and current_price <= tp_val: pass
        elif ttype == "take_profit" and current_price >= tp_val: pass
        elif ttype == "buy_limit"   and current_price <= tp_val: pass
        else: continue

        action    = "buy" if ttype == "buy_limit" else "sell"
        action_kr = "매수" if action == "buy" else "매도"
        type_kr   = {"stop_loss": "🔴 손절", "take_profit": "✅ 익절", "buy_limit": "🎯 목표매수"}[ttype]
        name      = t.get("name", ticker)
        qty       = t.get("qty", 1)
        market    = t.get("market", "KR")
        is_us     = market == "US"

        save_activity_log(
            "cio_manager",
            f"{type_kr} 발동: {name}({ticker}) 현재가 {current_price:,.0f} / 목표 {tp_val:,.0f} → {action_kr} {qty}주",
            "info",
        )
        try:
            order_result = {"success": False, "message": "미실행", "order_no": ""}
            if use_kis:
                order_result = await (
                    _kis_us_order(ticker, action, qty, price=current_price) if is_us
                    else _kis_order(ticker, action, qty, price=0)
                )
            elif use_mock_kis:
                order_result = await (
                    _kis_mock_us_order(ticker, action, qty, price=current_price) if is_us
                    else _kis_mock_order(ticker, action, qty, price=0)
                )
            else:
                portfolio = _load_data("trading_portfolio", _default_portfolio())
                if action == "sell":
                    holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
                    if holding and holding["qty"] >= qty:
                        sell_qty = min(qty, holding["qty"])
                        holding["qty"] -= sell_qty
                        if holding["qty"] == 0:
                            portfolio["holdings"] = [h for h in portfolio["holdings"] if h["ticker"] != ticker]
                        portfolio["cash"] += sell_qty * current_price
                        portfolio["updated_at"] = datetime.now(KST).isoformat()
                        _save_data("trading_portfolio", portfolio)
                        order_result = {"success": True, "order_no": "virtual"}
                elif action == "buy" and portfolio.get("cash", 0) >= current_price * qty:
                    holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
                    if holding:
                        old_total = holding["avg_price"] * holding["qty"]
                        holding["qty"] += qty
                        holding["avg_price"] = int((old_total + current_price * qty) / holding["qty"])
                        holding["current_price"] = int(current_price)
                    else:
                        portfolio["holdings"].append({
                            "ticker": ticker, "name": name, "qty": qty,
                            "avg_price": int(current_price), "current_price": int(current_price),
                            "market": market,
                        })
                    portfolio["cash"] -= current_price * qty
                    portfolio["updated_at"] = datetime.now(KST).isoformat()
                    _save_data("trading_portfolio", portfolio)
                    order_result = {"success": True, "order_no": "virtual"}

            if order_result["success"]:
                triggered_ids.add(t["id"])
                mode = "실거래" if use_kis else ("모의투자" if use_mock_kis else "가상")
                history = _load_data("trading_history", [])
                history.insert(0, {
                    "id": f"trigger_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}",
                    "date": datetime.now(KST).isoformat(),
                    "ticker": ticker, "name": name, "action": action,
                    "qty": qty, "price": current_price, "total": qty * current_price, "pnl": 0,
                    "strategy": f"{type_kr} 자동실행 ({mode})",
                    "status": "executed", "market": market,
                    "order_no": order_result.get("order_no", ""),
                })
                _save_data("trading_history", history)
                save_activity_log(
                    "cio_manager",
                    f"✅ {type_kr} 자동{action_kr} 완료: {name} {qty}주 @ {current_price:,.0f} ({mode})",
                    "info",
                )
                if action == "buy":
                    _register_position_triggers(ticker, name, current_price, qty, market, settings,
                                                source_id=t["id"])
                # 반대쪽 트리거 비활성화 (손절 발동 → 익절 제거, 익절 발동 → 손절 제거)
                pair_prefix = "tp_" if ttype == "stop_loss" else ("sl_" if ttype == "take_profit" else "")
                base_key = t["id"].split("_", 1)[1] if "_" in t["id"] else ""
                if pair_prefix and base_key:
                    for other in triggers:
                        if other.get("active") and other["id"] == f"{pair_prefix}{base_key}":
                            other["active"] = False
            else:
                save_activity_log(
                    "cio_manager",
                    f"❌ {type_kr} 주문 실패: {name} — {order_result.get('message','원인 불명')[:80]}",
                    "error",
                )
        except Exception as ex:
            save_activity_log(
                "cio_manager",
                f"❌ {type_kr} 트리거 오류: {name} — {str(ex)[:80]}",
                "error",
            )

    if triggered_ids:
        for t in triggers:
            if t["id"] in triggered_ids:
                t["active"] = False
                t["triggered_at"] = datetime.now(KST).isoformat()
        _save_data("price_triggers", triggers)


# ── 트레이딩 CRUD 엔드포인트 → handlers/trading_handler.py로 분리 ──
# summary, portfolio, strategies, watchlist, prices, chart, order,
# history, signals, decisions (CRUD) 등은 trading_handler.py에서 제공


@app.post("/api/trading/signals/generate")
async def generate_trading_signals():
    """투자팀장이 관심종목을 분석 → 매매 시그널 생성.

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
    tickers_info = ", ".join([f"{w['name']}({w['ticker']})" for w in watchlist])
    strats_info = ", ".join([s["name"] for s in active_strategies[:5]])

    # 투자 성향 정보
    _profile = _get_risk_profile()
    _profile_info = RISK_PROFILES.get(_profile, RISK_PROFILES["balanced"])
    _profile_label = f"{_profile_info['label']} ({_profile})"
    _max_pos = _profile_info["max_position_pct"]["max"]
    _cash_reserve = _profile_info["cash_reserve"]["default"]

    # 정량지표 사전분석 (병렬 계산)
    _auto_market = "US" if (len(us_tickers) > len(kr_tickers)) else "KR"
    save_activity_log("cio_manager", "📐 정량지표 사전계산 시작 (자동매매)...", "info")
    quant_section_auto = await _build_quant_prompt_section(watchlist, _auto_market)

    # ARGOS DB 수집 데이터 주입 (자동매매)
    save_activity_log("cio_manager", "📡 ARGOS 수집 데이터 로딩 (자동매매)...", "info")
    argos_section_auto = await _build_argos_context_section(watchlist, _auto_market)

    # CIO에게 보내는 분석 명령
    prompt = f"""[자동매매 시스템] 관심종목 종합 분석을 요청합니다.

## CEO 투자 성향: {_profile_label} {_profile_info['emoji']}
- 종목당 최대 비중: {_max_pos}%
- 현금 유보: {_cash_reserve}%
- 전 종목 비중 합계 ≤ {100 - _cash_reserve}% (현금 유보분 제외)
- Kelly Criterion, 현대 포트폴리오 이론, 분산투자 원칙을 기반으로 비중을 산출하세요

## 관심종목 ({len(watchlist)}개)
{tickers_info or '없음'}
{f'- 한국 주식: {len(kr_tickers)}개' if kr_tickers else ''}
{f'- 미국 주식: {len(us_tickers)}개' if us_tickers else ''}

## 활성 매매 전략
{strats_info or '기본 전략 (RSI/MACD 기반)'}{quant_section_auto}{argos_section_auto}

## 분석 요청사항 (추가 데이터 수집 불필요 — 위 서버 제공 데이터만 활용)
아래 분석을 수행하세요:
- **시황분석**: 위 매크로 지표/뉴스를 기반으로 시장 분위기, 금리/환율 동향, 업종별 흐름 해석
- **종목분석**: 위 공시/뉴스/주가 데이터를 기반으로 재무 건전성, PER/PBR, 실적 전망 해석
- **기술적분석**: 위 정량지표(RSI/MACD 등)와 최근 주가 흐름을 종합하여 방향성 판단
- **리스크관리**: 포지션 크기 적정성, 손절가, 전체 포트폴리오 리스크

## 최종 산출물 (반드시 아래 형식 그대로 — 예시처럼 정확히)
[시그널] 삼성전자 (005930) | 매수 | 신뢰도 72% | 비중 15% | 목표가 85000 | 반도체 수요 회복 + RSI 과매도 구간
[시그널] 카카오 (035720) | 매도 | 신뢰도 61% | 비중 0% | 목표가 42000 | PER 과대평가, 금리 민감 섹터 약세
[시그널] LG에너지솔루션 (373220) | 관망 | 신뢰도 45% | 비중 5% | 목표가 0 | 혼조세, 방향성 불명확

※ 신뢰도는 정량기준값 ±20%p 범위 내에서 결정. 반드시 0~100 숫자 + % 기호.
※ 비중: 포트폴리오 내 해당 종목 비중(%). 매도 종목은 0%. 전 종목 비중 합계 ≤ {100 - _cash_reserve}%.
※ 목표가: 매수 종목은 목표 매도가, 매도 종목은 목표 재진입가, 관망은 0. 반드시 숫자만 (쉼표 없이)."""

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

    # 1단계: 투자팀장 독자 분석 + 도구 활용 (P2-4: 병렬화)
    cio_solo_prompt = (
        f"CEO 투자 성향: {_profile_label}. 관심종목 독자 분석을 작성하세요:\n{tickers_info or '없음'}\n\n"
        f"활성 전략: {strats_info or '기본 전략'}\n\n"
        f"각 종목에 대해 현재 시장 환경, 섹터 동향, 밸류에이션 관점에서 독립적으로 판단하고 "
        f"매수/매도/관망 + 포트폴리오 비중(%) + 목표가를 제시하세요. 최종 산출물은 반드시 아래 형식으로:\n"
        f"[시그널] 삼성전자 (005930) | 매수 | 신뢰도 72% | 비중 15% | 목표가 85000 | 반도체 수요 회복 신호\n"
        f"[시그널] 카카오 (035720) | 관망 | 신뢰도 48% | 비중 5% | 목표가 0 | 방향성 불명확\n"
        f"※ 신뢰도는 종목별로 독립적으로 0~100 숫자 + % 기호. 비중은 전 종목 합계 ≤ {100 - _cash_reserve}%. 목표가는 숫자만."
    )
    cio_soul = _load_agent_prompt("cio_manager")
    cio_solo_model = select_model(cio_solo_prompt, override=_get_model_override("cio_manager"))
    save_activity_log("cio_manager", "📊 CIO 독자 분석 + 전문가 위임 병렬 시작", "info")
    # CIO 독자 분석 시작 교신 로그
    try:
        from db import save_delegation_log as _sdl
        _sdl(sender="투자팀장", receiver="CIO 독자 분석", message="전문가 위임과 병렬로 독립 판단 시작", log_type="delegation")
    except Exception as e:
        logger.debug("CIO 위임 로그 저장 실패: %s", e)

    # CIO 독자 분석용 도구 로드
    cio_detail = _AGENTS_DETAIL.get("cio_manager", {})
    cio_allowed = cio_detail.get("allowed_tools", [])
    cio_solo_tools = None
    cio_solo_executor = None
    cio_solo_tools_used: list[str] = []
    if cio_allowed:
        cio_schemas = _load_tool_schemas(allowed_tools=cio_allowed)
        if cio_schemas.get("anthropic"):
            cio_solo_tools = cio_schemas["anthropic"]
            async def cio_solo_executor(tool_name: str, tool_input: dict):
                cio_solo_tools_used.append(tool_name)
                pool = _init_tool_pool()
                if pool:
                    return await pool.execute(tool_name, tool_input)
                return {"error": f"도구 풀 미초기화: {tool_name}"}

    # CIO 독자 분석과 전문가 위임을 동시에 실행 (asyncio.gather)
    async def _cio_solo_analysis():
        result = await ask_ai(cio_solo_prompt, system_prompt=cio_soul, model=cio_solo_model,
                              tools=cio_solo_tools, tool_executor=cio_solo_executor)
        content = result.get("content", "") if isinstance(result, dict) else ""
        cost = result.get("cost_usd", 0) if isinstance(result, dict) else 0
        # 교신 로그 기록
        try:
            preview = content[:300] if content else "분석 결과 없음"
            _sdl(sender="CIO 독자 분석", receiver="투자팀장", message=preview, log_type="report")
            await _broadcast_comms({"id": f"cio_solo_{datetime.now(KST).strftime('%H%M%S')}", "sender": "CIO 독자 분석", "receiver": "투자팀장", "message": preview, "log_type": "report", "source": "delegation", "created_at": datetime.now(KST).isoformat()})
        except Exception as e:
            logger.debug("CIO 독자 분석 교신 로그 실패: %s", e)
        return {"content": content, "cost_usd": cost}

    # 병렬 실행: CIO 독자 분석 + 전문가 위임
    await _broadcast_status("cio_manager", "working", 0.1, "투자팀장 분석 진행 중...")
    cio_solo_task = _cio_solo_analysis()
    spec_task = _delegate_to_specialists("cio_manager", prompt)
    cio_solo_result, spec_results = await asyncio.gather(cio_solo_task, spec_task)

    cio_solo_content = cio_solo_result.get("content", "")
    cio_solo_cost = cio_solo_result.get("cost_usd", 0)

    # 2단계: CIO가 독자 분석 + 전문가 결과를 종합
    spec_parts = []
    spec_cost = 0.0
    for r in (spec_results or []):
        name = r.get("name", r.get("agent_id", "?"))
        if "error" in r:
            spec_parts.append(f"[{name}] 오류: {r['error'][:80]}")
        else:
            spec_parts.append(f"[{name}]\n{r.get('content', '응답 없음')}")
            spec_cost += r.get("cost_usd", 0)

    mgr_name = _AGENT_NAMES.get("cio_manager", "CIO")
    synthesis_prompt = (
        f"당신은 {mgr_name}입니다. 아래 두 가지 분석을 종합하여 최종 시그널을 결정하세요.\n\n"
        f"## CEO 원본 명령\n{prompt}\n\n"
        f"## CIO 독자 사전 분석 (전문가 보고서 참고 전 작성한 독립 판단)\n"
        f"{cio_solo_content[:1000] if cio_solo_content else '분석 없음'}\n\n"
        f"## 전문가 분석 결과\n" + "\n\n".join(spec_parts) + "\n\n"
        f"위 독자 분석과 전문가 보고서를 모두 반영하여 최종 시그널을 결정하세요."
    )
    override = _get_model_override("cio_manager")
    synth_model = select_model(synthesis_prompt, override=override)
    await _broadcast_status("cio_manager", "working", 0.7, "독자 분석 + 전문가 결과 종합 중...")
    synthesis = await ask_ai(synthesis_prompt, system_prompt=cio_soul, model=synth_model)
    await _broadcast_status("cio_manager", "done", 1.0, "보고 완료")

    specialists_used = len([r for r in (spec_results or []) if "error" not in r])
    if "error" in synthesis:
        content = f"**{mgr_name} 전문가 분석 결과**\n\n" + "\n\n---\n\n".join(spec_parts)
    else:
        content = synthesis.get("content", "")
    cost = spec_cost + cio_solo_cost + synthesis.get("cost_usd", 0)

    # CIO 분석 결과에서 시그널 파싱
    parsed_signals = _parse_cio_signals(content, watchlist)

    signals = _load_data("trading_signals", [])
    new_signal = {
        "id": f"sig_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}",
        "date": datetime.now(KST).isoformat(),
        "analysis": content,
        "tickers": [w["ticker"] for w in watchlist],
        "parsed_signals": parsed_signals,
        "strategy": "cio_analysis",
        "analyzed_by": f"CIO 포함 {specialists_used + 1}명",
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

    # CIO 성과 추적: 예측을 cio_predictions 테이블에 저장
    try:
        from db import save_cio_prediction
        sig_id = new_signal["id"]
        for sig in parsed_signals:
            action_raw = sig.get("action", "hold")
            if action_raw in ("buy", "sell"):
                direction = "BUY" if action_raw == "buy" else "SELL"
                # 현재가 조회 (검증 기준가 — 3일/7일 후 비교용)
                current_price = 0
                try:
                    from kis_client import get_overseas_price as _gop
                    _pd = await _gop(sig["ticker"])
                    current_price = int(float(_pd.get("price", 0) or 0))
                except Exception as e:
                    logger.debug("현재가 조회 실패 (%s): %s", sig.get("ticker"), e)
                save_cio_prediction(
                    ticker=sig.get("ticker", ""),
                    direction=direction,
                    ticker_name=sig.get("name", ""),
                    confidence=sig.get("confidence", 0),
                    predicted_price=current_price or None,
                    target_price=sig.get("target_price"),
                    analysis_summary=sig.get("reason", ""),
                    task_id=sig_id,
                )
        logger.info("[CIO성과] %d건 예측 저장 완료 (sig_id=%s)", len([s for s in parsed_signals if s.get("action") in ("buy", "sell")]), sig_id)
    except Exception as e:
        logger.warning("[CIO성과] 예측 저장 실패: %s", e)

    # 신뢰도 파이프라인: 전문가 기여 캡처
    _capture_specialist_contributions_sync(
        parsed_signals, spec_results or [], cio_solo_content or "", sig_id if 'sig_id' in dir() else ""
    )

    # P2-7: CIO 목표가 → 관심종목 자동 반영
    try:
        _wl = _load_data("trading_watchlist", [])
        _updated = 0
        for sig in parsed_signals:
            tp = sig.get("target_price", 0)
            if not tp or tp <= 0:
                continue
            for w in _wl:
                if w.get("ticker") == sig.get("ticker"):
                    w["target_price"] = tp
                    _updated += 1
                    break
        if _updated > 0:
            _save_data("trading_watchlist", _wl)
            logger.info("[P2-7] 관심종목 목표가 %d건 자동 갱신", _updated)
    except Exception as e:
        logger.warning("[P2-7] 관심종목 목표가 반영 실패: %s", e)

    # 기밀문서 자동 저장 (CIO 독자분석 + 전체 분석 포함)
    try:
        now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        archive_lines = [f"# CIO 매매 시그널 분석 — {now_str}\n"]
        # CIO 독자 분석 내용 포함
        if cio_solo_content:
            archive_lines.append("## CIO 독자 사전 분석 (전문가 보고 전 독립 판단)\n")
            archive_lines.append(cio_solo_content[:2000])
            archive_lines.append("\n---\n")
        # CIO 최종 종합 분석 전문
        archive_lines.append("## CIO 최종 종합 분석\n")
        archive_lines.append(content[:3000] if content else "분석 내용 없음")
        archive_lines.append("\n---\n")
        # 종목별 시그널 요약
        archive_lines.append("## 종목별 시그널 요약\n")
        for sig in parsed_signals:
            ticker = sig.get("ticker", "")
            name = sig.get("name", ticker)
            action_raw = sig.get("action", "hold")
            action_label = "매수" if action_raw == "buy" else ("매도" if action_raw == "sell" else "관망")
            conf = sig.get("confidence", 0)
            reason = sig.get("reason", "")
            archive_lines.append(f"### {name} ({ticker}) — {action_label}")
            archive_lines.append(f"- 신뢰도: {conf}%")
            archive_lines.append(f"- 분석: {reason}\n")
        if len(parsed_signals) == 0:
            archive_lines.append("### 종목별 시그널 파싱 결과 없음\n")
            archive_lines.append(content[:2000] if content else "")
        archive_content = "\n".join(archive_lines)
        filename = f"CIO_시그널_{datetime.now(KST).strftime('%Y%m%d_%H%M')}.md"
        save_archive(
            division="finance",
            filename=filename,
            content=archive_content,
            agent_id="cio_manager",
        )
    except Exception as e:
        logger.debug("CIO 아카이브 저장 실패: %s", e)

    # 매매 결정 일지 저장
    _save_decisions(parsed_signals)

    return {"success": True, "signal": new_signal, "parsed_signals": parsed_signals}


def _save_decisions(parsed_signals: list) -> None:
    """시그널을 매매 결정 일지(trading_decisions)에 저장합니다.

    P2-1 수정: 수동 분석(run_trading_now), 자동봇(_trading_bot_loop),
    스케줄 분석(generate_trading_signals) 모두에서 호출.
    """
    try:
        decisions = load_setting("trading_decisions", [])
        for sig in parsed_signals:
            action_raw = sig.get("action", "hold")
            action_label = "매수" if action_raw == "buy" else ("매도" if action_raw == "sell" else "관망")
            decision = {
                "id": str(_uuid.uuid4()),
                "created_at": datetime.now(KST).isoformat(),
                "ticker": sig.get("ticker", ""),
                "ticker_name": sig.get("name", sig.get("ticker", "")),
                "action": action_label,
                "confidence": sig.get("confidence", 0),
                "reason": sig.get("reason", ""),
                "expert_opinions": sig.get("expert_opinions", []),
                "executed": False,
            }
            decisions.append(decision)
        if len(decisions) > 50:
            decisions = decisions[-50:]
        save_setting("trading_decisions", decisions)
    except Exception as e:
        logger.debug("매매 결정 저장 실패: %s", e)


def _cio_confidence_weight(confidence: float) -> float:
    """CIO 신뢰도 기반 포트폴리오 비중 폴백 (CIO가 비중을 산출하지 않은 경우).
    75%+ → 20%, 65%+ → 15%, 55%+ → 10%, 기타 → 5%
    """
    if confidence >= 75:
        return 0.20
    elif confidence >= 65:
        return 0.15
    elif confidence >= 55:
        return 0.10
    return 0.05


def _get_signal_weight(sig: dict, fallback_conf: float = 50) -> float:
    """시그널에서 비중(0~1 비율)을 가져옵니다. CIO 비중 우선, 없으면 신뢰도 기반 폴백."""
    w = sig.get("weight", 0)
    if w and w > 0:
        return w / 100.0
    return _cio_confidence_weight(fallback_conf)


def _parse_cio_signals(content: str, watchlist: list) -> list:
    """CIO 분석 결과에서 종목별 매수/매도/관망 시그널을 추출합니다."""
    import re
    parsed = []
    seen_tickers = set()

    # [시그널] 패턴 — 비중 + 목표가 포함 (최신 형식)
    # 예: [시그널] 삼성전자 (005930) | 매수 | 신뢰도 72% | 비중 15% | 목표가 85000 | 이유
    pattern = r'\[시그널\]\s*(.+?)\s*[\(（]([A-Za-z0-9]+)[\)）]\s*\|\s*[^\|]*?(매수|매도|관망|buy|sell|hold)\b[^\|]*\|\s*(?:신뢰도[:\s]*)?\s*(\d+)\s*%?\s*\|\s*(?:비중\s*(\d+)\s*%?\s*\|\s*)?(?:목표가\s*(\d+)\s*\|\s*)?(.*)'
    matches = re.findall(pattern, content, re.IGNORECASE)

    # 기존 형식 (비중/목표가 없는 것) 호환용 폴백
    if not matches:
        pattern_legacy = r'\[시그널\]\s*(.+?)\s*[\(（]([A-Za-z0-9]+)[\)）]\s*\|\s*[^\|]*?(매수|매도|관망|buy|sell|hold)\b[^\|]*\|\s*(?:신뢰도[:\s]*)?\s*(\d+)\s*%?\s*\|?\s*()()(.*)'
        matches = re.findall(pattern_legacy, content, re.IGNORECASE)

    for name, ticker, action, confidence, weight_str, target_price_str, reason in matches:
        ticker = ticker.strip()
        if ticker in seen_tickers:
            continue  # 같은 종목 중복 시그널 방지 (요약 섹션 중복)
        seen_tickers.add(ticker)
        action_map = {"매수": "buy", "매도": "sell", "관망": "hold", "buy": "buy", "sell": "sell", "hold": "hold"}
        market = "US" if any(c.isalpha() and c.isupper() for c in ticker) and not ticker.isdigit() else "KR"
        # 이유가 빈 줄이면 시그널 다음 줄에서 추출
        reason_text = reason.strip()
        if not reason_text:
            sig_pos = content.find(f"[시그널] {name.strip()}")
            if sig_pos >= 0:
                after = content[sig_pos:sig_pos + 500]
                lines = after.split("\n")
                for line in lines[1:4]:  # 다음 1~3줄에서 이유 찾기
                    line = line.strip()
                    if line and not line.startswith("[시그널]") and not line.startswith("━"):
                        reason_text = line
                        break
        parsed.append({
            "ticker": ticker,
            "name": name.strip(),
            "market": market,
            "action": action_map.get(action.lower(), "hold"),
            "confidence": int(confidence),
            "weight": int(weight_str) if weight_str and weight_str.isdigit() else 0,
            "target_price": int(target_price_str) if target_price_str and target_price_str.isdigit() else 0,
            "reason": reason_text or "CIO 종합 분석 참조",
        })

    # 비중 안전장치: 종목당 최대 비중 + 총합 제한 (투자 성향 기반)
    if parsed:
        _profile = _get_risk_profile()
        _ranges = RISK_PROFILES.get(_profile, RISK_PROFILES["balanced"])
        _max_pos = _ranges["max_position_pct"]["max"]
        _cash_reserve = _ranges["cash_reserve"]["default"]
        _max_total = 100 - _cash_reserve
        # 종목당 클램핑
        for sig in parsed:
            if sig["weight"] > _max_pos:
                sig["weight"] = _max_pos
        # 총합 제한
        total_weight = sum(s["weight"] for s in parsed)
        if total_weight > _max_total and total_weight > 0:
            ratio = _max_total / total_weight
            for sig in parsed:
                sig["weight"] = max(1, int(sig["weight"] * ratio))

    # [시그널] 패턴이 없으면 관심종목 기반으로 키워드 파싱 (종목별 개별 컨텍스트 기준)
    if not parsed:
        for w in watchlist:
            action = "hold"
            confidence = 50
            reason = ""
            name = w.get("name", w["ticker"])
            ticker = w["ticker"]
            # 이 종목이 보고서에 언급됐는지 확인
            name_idx = content.find(name)
            ticker_idx = content.find(ticker)
            ref_idx = name_idx if name_idx >= 0 else ticker_idx
            if ref_idx < 0:
                continue  # 언급 안 된 종목은 제외
            # 해당 종목 주변 300자만 컨텍스트로 사용 (전체 보고서 X)
            ctx = content[ref_idx:ref_idx + 300]
            if any(k in ctx for k in ["매수", "적극 매수", "buy", "진입"]):
                action = "buy"
            elif any(k in ctx for k in ["매도", "sell", "청산", "익절"]):
                action = "sell"
            # 컨텍스트에서 신뢰도 숫자 추출 (예: "신뢰도 72%" / "72%")
            conf_match = re.search(r'신뢰도[:\s]*(\d+)\s*%?', ctx)
            if conf_match:
                confidence = int(conf_match.group(1))
            else:
                pct_match = re.search(r'(\d{2,3})\s*%', ctx)
                if pct_match:
                    confidence = int(pct_match.group(1))
            # 근거 추출
            reason = ctx.split("\n")[0].strip()
            parsed.append({
                "ticker": ticker,
                "name": name,
                "market": w.get("market", "KR"),
                "action": action,
                "confidence": confidence,
                "reason": reason or "CIO 종합 분석 참조",
            })

    return parsed


# ── settings, risk-profile, cio-update → handlers/trading_handler.py로 분리 ──

@app.post("/api/trading/bot/toggle")
async def toggle_trading_bot():
    """자동매매 봇 ON/OFF 토글."""


    app_state.trading_bot_active = not app_state.trading_bot_active
    # DB에 상태 저장 → 배포/재시작 후에도 유지
    save_setting("trading_bot_active", app_state.trading_bot_active)

    if app_state.trading_bot_active:
        if app_state.trading_bot_task is None or app_state.trading_bot_task.done():
            app_state.trading_bot_task = asyncio.create_task(_trading_bot_loop())
        save_activity_log("system", "🤖 자동매매 봇 가동 시작!", "info")
        _log("[TRADING] 자동매매 봇 시작 ✅")
    else:
        save_activity_log("system", "⏹️ 자동매매 봇 중지", "info")
        _log("[TRADING] 자동매매 봇 중지")

    return {"success": True, "bot_active": app_state.trading_bot_active}


# ── bot/status, calibration → handlers/trading_handler.py로 분리 ──

@app.post("/api/trading/watchlist/analyze-selected")
async def analyze_selected_watchlist(request: Request):
    """관심종목 중 선택한 종목만 즉시 분석 + 자동매매."""
    body = await request.json()
    tickers = body.get("tickers", [])
    if not tickers:
        return {"success": False, "message": "분석할 종목을 선택하세요."}

    existing = app_state.bg_tasks.get("trading_run_now")
    if existing and not existing.done():
        return {"success": True, "message": "CIO 분석이 이미 진행 중입니다.", "already_running": True}

    async def _bg():
        try:
            result = await _run_trading_now_inner(selected_tickers=tickers)
            app_state.bg_results["trading_run_now"] = {**result, "_completed_at": __import__("time").time()}
        except Exception as e:
            logger.error("[선택 분석] 백그라운드 오류: %s", e, exc_info=True)
            app_state.bg_results["trading_run_now"] = {
                "success": False, "message": f"분석 중 오류: {str(e)[:200]}",
                "signals": [], "signals_count": 0, "orders_triggered": 0,
                "_completed_at": __import__("time").time(),
            }
        finally:
            result = app_state.bg_results.get("trading_run_now", {})
            await wm.broadcast({"type": "trading_run_complete",
                "success": result.get("success", False),
                "signals_count": result.get("signals_count", 0),
                "orders_triggered": result.get("orders_triggered", 0)})

    app_state.bg_tasks["trading_run_now"] = asyncio.create_task(_bg())
    return {"success": True, "message": f"{len(tickers)}개 종목 분석 시작됨.", "background": True}


@app.post("/api/trading/bot/run-now")
async def run_trading_now():
    """지금 즉시 CIO 분석 + 매매 판단 실행 (장 시간 무관, 수동 트리거).

    봇 ON/OFF 상태와 무관하게 즉시 1회 분석을 실행합니다.
    수동 실행이므로 auto_execute 설정 무관하게 항상 매매까지 진행합니다.

    Cloudflare 100초 타임아웃 대응: 즉시 응답 + 백그라운드 실행.
    프론트엔드는 CIO SSE + 폴링으로 실시간 추적.
    """
    # 이미 실행 중이면 중복 방지
    existing = app_state.bg_tasks.get("trading_run_now")
    if existing and not existing.done():
        return {"success": True, "message": "CIO 분석이 이미 진행 중입니다. 잠시 기다려주세요.", "already_running": True}

    async def _bg_run_trading():
        try:
            result = await _run_trading_now_inner()
            app_state.bg_results["trading_run_now"] = {
                **result, "_completed_at": __import__("time").time()
            }
        except Exception as e:
            logger.error("[수동 분석] 백그라운드 오류: %s", e, exc_info=True)
            signals = _load_data("trading_signals", [])
            latest = signals[0] if signals else {}
            app_state.bg_results["trading_run_now"] = {
                "success": False,
                "message": f"분석 중 오류: {str(e)[:200]}",
                "signals": latest.get("parsed_signals", []),
                "signals_count": len(latest.get("parsed_signals", [])),
                "orders_triggered": 0,
                "error": str(e)[:200],
                "_completed_at": __import__("time").time(),
            }
        finally:
            # 완료 알림 브로드캐스트
            result = app_state.bg_results.get("trading_run_now", {})
            await wm.broadcast({
                "type": "trading_run_complete",
                "success": result.get("success", False),
                "signals_count": result.get("signals_count", 0),
                "orders_triggered": result.get("orders_triggered", 0),
            })

    app_state.bg_tasks["trading_run_now"] = asyncio.create_task(_bg_run_trading())
    return {"success": True, "message": "CIO 분석 시작됨. 실시간 진행 상황은 화면에서 확인하세요.", "background": True}


@app.get("/api/trading/bot/run-status")
async def get_trading_run_status():
    """백그라운드 CIO 분석 진행 상태 확인."""
    task = app_state.bg_tasks.get("trading_run_now")
    result = app_state.bg_results.get("trading_run_now")

    if task and not task.done():
        return {"status": "running", "message": "CIO 분석 진행 중..."}
    elif result:
        return {"status": "completed", **result}
    else:
        return {"status": "idle", "message": "실행 대기 중"}


@app.post("/api/trading/bot/stop")
async def stop_trading_now():
    """진행 중인 CIO 분석을 즉시 중지합니다."""
    task = app_state.bg_tasks.get("trading_run_now")
    if task and not task.done():
        task.cancel()
        save_activity_log("cio_manager", "🛑 CEO가 수동으로 분석을 중지했습니다.", "info")
        await wm.broadcast({"type": "trading_run_complete", "success": False, "stopped": True, "signals_count": 0, "orders_triggered": 0})
        return {"success": True, "message": "분석이 중지되었습니다."}
    return {"success": False, "message": "진행 중인 분석이 없습니다."}


async def _run_trading_now_inner(selected_tickers: list[str] | None = None):
    """run_trading_now의 실제 로직 (에러 핸들링은 호출자가 담당).

    selected_tickers: 지정 시 해당 종목만 분석. None이면 전체 관심종목.
    """
    settings = _load_data("trading_settings", _default_trading_settings())
    watchlist = _load_data("trading_watchlist", [])

    if not watchlist:
        return {"success": False, "message": "관심종목이 없습니다. 먼저 종목을 추가하세요."}

    # 장 시간 확인 (수동 실행은 강제 실행 — 장 마감이어도 진행)
    is_open, market = _is_market_open(settings)
    if not is_open:
        market = "KR"  # 장 마감 시 한국장 기준으로 분석
    market_watchlist = [w for w in watchlist if w.get("market", "KR") == market] or watchlist

    # 선택 종목 필터링 (selected_tickers 지정 시)
    if selected_tickers:
        upper_sel = [t.upper() for t in selected_tickers]
        market_watchlist = [w for w in watchlist if w.get("ticker", "").upper() in upper_sel]
        if not market_watchlist:
            return {"success": False, "message": f"선택한 종목({', '.join(selected_tickers)})이 관심종목에 없습니다."}
        # 선택 종목의 마켓 자동 결정
        markets = set(w.get("market", "KR") for w in market_watchlist)
        market = "US" if "US" in markets else "KR"

    # 자기학습 보정 섹션 (베이지안 + ELO + 오답패턴 + Platt Scaling 통합)
    cal_section = _build_calibration_prompt_section(settings)

    # 정량지표 사전분석 (RSI/MACD/볼린저/거래량/추세 — 병렬 계산)
    save_activity_log("cio_manager", "📐 정량지표 사전계산 시작...", "info")
    quant_section = await _build_quant_prompt_section(market_watchlist, market)

    # ARGOS DB 수집 데이터 주입 (주가/매크로/공시/뉴스 — 서버가 직접 제공)
    save_activity_log("cio_manager", "📡 ARGOS 수집 데이터 로딩...", "info")
    argos_section = await _build_argos_context_section(market_watchlist, market)

    tickers_info = ", ".join([f"{w['name']}({w['ticker']})" for w in market_watchlist])
    strategies = _load_data("trading_strategies", [])
    active_strats = [s for s in strategies if s.get("active")]
    strats_info = ", ".join([s["name"] for s in active_strats[:5]]) or "기본 전략"

    market_label = "한국" if market == "KR" else "미국"
    prompt = f"""[수동 즉시 분석 요청 — {market_label}장]

## 분석 대상 ({len(market_watchlist)}개 종목)
{tickers_info}

## 활성 전략: {strats_info}{cal_section}{quant_section}{argos_section}

## 분석 요청 (추가 데이터 수집 불필요 — 위 서버 제공 데이터만 활용)
아래 분석을 수행하세요:
- **시황분석**: 위 매크로 지표/뉴스를 기반으로 {'코스피/코스닥 흐름, 외국인/기관 동향, 금리/환율' if market == 'KR' else 'S&P500/나스닥, 미국 금리/고용지표, 달러 강세'} 해석
- **종목분석**: 위 공시/뉴스/주가 데이터를 기반으로 재무 건전성, PER/PBR, 실적 방향 해석
- **기술적분석**: 위 정량지표(RSI/MACD 등)와 주가 흐름을 종합하여 방향성 판단
- **리스크관리**: 손절가, 적정 포지션 크기, 전체 포트폴리오 리스크

## 최종 산출물 (반드시 아래 형식 그대로 — 예시처럼 정확히)
[시그널] 삼성전자 (005930) | 매수 | 신뢰도 72% | 비중 15% | 목표가 78000 | 반도체 수요 회복 + RSI 과매도 구간
[시그널] 카카오 (035720) | 매도 | 신뢰도 61% | 비중 10% | 목표가 0 | PER 과대평가, 금리 민감 섹터 약세
[시그널] LG에너지솔루션 (373220) | 관망 | 신뢰도 45% | 비중 0% | 목표가 390000 | 혼조세, 이 가격 도달 시 진입 검토

※ 주의:
- 신뢰도는 위 정량기준값 ±20%p 범위 내에서 결정. 종목별로 독립적으로, 0~100 숫자 + % 기호로 표기
- 목표가(권장 매수 진입가): 매수/관망 종목은 반드시 입력. 현재가보다 낮은 목표 진입가 설정. 미국 주식은 USD 단위. 매도 종목은 0
- 목표가 도달 시 서버가 자동으로 매수 실행 — 신중하게 설정할 것"""

    save_activity_log("cio_manager", f"🔍 수동 즉시 분석 시작: {market_label}장 {len(market_watchlist)}개 종목", "info")
    cio_result = await _call_agent("cio_manager", prompt)
    content = cio_result.get("content", "")
    cost = cio_result.get("cost_usd", 0)

    # ── 비서실장 QA: 팀장 보고서 검수 ──
    qa_passed, qa_reason = await _chief_qa_review(content, "금융분석팀장")
    save_activity_log("chief_of_staff",
        f"📋 금융분석팀장 보고서 QA: {'✅ 승인' if qa_passed else '❌ 반려'} — {qa_reason[:80]}",
        "info" if qa_passed else "warning")
    await _broadcast_comms({
        "type": "comms",
        "agent_id": "chief_of_staff",
        "agent_name": "비서실장",
        "message": f"금융분석팀장 보고서 QA {'✅ 승인' if qa_passed else '❌ 반려'}: {qa_reason[:100]}",
        "timestamp": datetime.now(KST).isoformat(),
        "channel": "cio",
    })

    parsed_signals = _parse_cio_signals(content, market_watchlist)

    # 신호 저장 (QA 결과 포함)
    signals = _load_data("trading_signals", [])
    new_signal = {
        "id": f"sig_manual_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}",
        "date": datetime.now(KST).isoformat(),
        "market": market,
        "analysis": content,
        "tickers": [w["ticker"] for w in market_watchlist[:10]],
        "parsed_signals": parsed_signals,
        "strategy": "cio_manual_analysis",
        "analyzed_by": "금융분석팀장 단독 분석 (수동 실행)",
        "cost_usd": cost,
        "auto_bot": False,
        "manual_run": True,
        "qa_passed": qa_passed,
        "qa_reason": qa_reason[:200],
    }
    signals.insert(0, new_signal)
    if len(signals) > 200:
        signals = signals[:200]
    _save_data("trading_signals", signals)

    # 매매 결정 일지 저장 (P2-1: 수동 분석에서도 decisions 저장)
    _save_decisions(parsed_signals)

    # QA 반려 시 1회 재분석
    if not qa_passed:
        save_activity_log("chief_of_staff",
            f"🔄 QA 반려 → 재분석 요청: {qa_reason[:100]}", "warning")
        retry_prompt = (
            f"{prompt}\n\n"
            f"## ⚠️ 비서실장 재검토 요청\n"
            f"이전 보고서가 반려되었습니다. 반려 사유: {qa_reason[:200]}\n"
            f"위 사유를 반드시 해결하여 다시 분석하세요. 신뢰도 근거를 구체적 수치로 보완하세요."
        )
        content2, cost2 = await ask_ai(
            agent_id="cio_manager", prompt=retry_prompt,
            use_tools=True, tools=cio_tools,
        )
        cost += cost2
        qa_passed2, qa_reason2 = await _qa_check_cio_report(content2, market_watchlist)
        save_activity_log("chief_of_staff",
            f"📋 재분석 QA: {'✅ 승인' if qa_passed2 else '❌ 최종 반려'} — {qa_reason2[:100]}", "info" if qa_passed2 else "warning")
        if qa_passed2:
            content = content2
            parsed_signals = _parse_cio_signals(content, market_watchlist)
            _save_decisions(parsed_signals)
        else:
            return {
                "signals": parsed_signals,
                "analysis": content2[:500],
                "cost_usd": cost,
                "qa_passed": False,
                "qa_reason": qa_reason2,
                "orders": [],
                "message": f"비서실장 QA 최종 반려 (재분석 후): {qa_reason2[:100]}"
            }

    # 수동 즉시 실행 → auto_execute 설정 무관하게 항상 주문 진행
    # (CEO가 버튼을 직접 누른 것 = 매매 의사 표시)
    min_confidence = settings.get("min_confidence", 65)
    order_size = settings.get("order_size", 0)  # 0 = CIO 비중 자율, >0 = 고정 금액
    orders_triggered = 0

    # 자기보정 계수 계산 (Platt Scaling) — 미정의 시 NameError 방지
    calibration = _compute_calibration_factor(settings.get("calibration_lookback", 20))
    calibration_factor = calibration.get("factor", 1.0)
    if calibration.get("win_rate") is not None:
        save_activity_log("cio_manager",
            f"📊 자기보정 적용: factor={calibration_factor} ({calibration.get('note', '')})", "info")
    if True:  # 수동 실행은 항상 매매 진행 (auto_execute 체크 제거)
        # 수동 실행: KIS가 연결되어 있으면 실제 주문 (paper_trading 설정 무시)
        # CEO가 "즉시 분석·매매결정" 버튼을 누른 것 = 매매 의사 명시적 표시
        enable_mock = settings.get("enable_mock", False)
        use_kis = _KIS_AVAILABLE and _kis_configured()
        use_mock_kis = (not use_kis) and enable_mock and _KIS_AVAILABLE and _kis_mock_configured()
        paper_mode = not use_kis and not use_mock_kis  # 둘 다 불가할 때만 가상 모드

        # CIO 비중 기반 매수(B안): order_size=0이면 잔고×비중으로 자동 산출
        account_balance = 0
        if order_size == 0:
            try:
                if use_kis:
                    _bal = await _kis_balance()
                    account_balance = _bal.get("cash", 0) if _bal.get("success") else 0
                elif use_mock_kis:
                    _bal = await _kis_mock_balance()
                    account_balance = _bal.get("cash", 0) if _bal.get("success") else 0
                else:
                    _port = _load_data("trading_portfolio", _default_portfolio())
                    account_balance = _port.get("cash", 0)
            except Exception as e:
                logger.debug("잔고 조회 실패: %s", e)
            if account_balance <= 0:
                account_balance = 1_000_000
                save_activity_log("cio_manager", "CIO 비중 모드: 잔고 조회 실패, 기본 100만원 사용", "warning")
            save_activity_log("cio_manager",
                f"CIO 비중 모드: 계좌잔고 {account_balance:,.0f}원 기준 자동 주수 산출", "info")

        mode_label = ("실거래" if not KIS_IS_MOCK else "모의투자") if use_kis else ("모의투자" if use_mock_kis else "가상")
        save_activity_log("cio_manager",
            f"📋 매매 실행 시작: 시그널 {len(parsed_signals)}건, 최소신뢰도 {min_confidence}%, order_size={order_size}, KIS={use_kis}, MOCK={use_mock_kis}, 모드={mode_label}", "info")

        for sig in parsed_signals:
            if sig["action"] not in ("buy", "sell"):
                continue
            effective_conf = sig.get("confidence", 0) * calibration_factor
            if effective_conf < min_confidence:
                save_activity_log("cio_manager",
                    f"[수동] {sig.get('name', sig['ticker'])} 신뢰도 부족 ({effective_conf:.0f}% < {min_confidence}%) — 건너뜀",
                    "info")
                continue

            ticker = sig["ticker"]
            sig_market = sig.get("market", market)
            is_us = sig_market.upper() in ("US", "USA", "OVERSEAS") or (ticker.isalpha() and len(ticker) <= 5)
            action_kr = "매수" if sig["action"] == "buy" else "매도"
            save_activity_log("cio_manager",
                f"🎯 {action_kr} 시도: {sig.get('name', ticker)} ({ticker}) 신뢰도 {effective_conf:.0f}% 비중 {sig.get('weight', 0)}%", "info")

            try:
                # 현재가 조회
                if is_us:
                    if _KIS_AVAILABLE and _kis_configured():
                        us_price_data = await _kis_us_price(ticker)
                        price = us_price_data.get("price", 0) if us_price_data.get("success") else 0
                        save_activity_log("cio_manager", f"  💵 {ticker} 현재가: ${price:.2f} (KIS 조회)", "info")
                    else:
                        target_w = next((w for w in market_watchlist if w.get("ticker", "").upper() == ticker.upper()), None)
                        price = float(target_w.get("target_price", 0)) if target_w else 0
                    if price <= 0:
                        save_activity_log("cio_manager", f"[수동/US] {ticker} 현재가 조회 실패 (price={price}) — 건너뜀", "warning")
                        continue
                    _fx = _get_fx_rate()
                    _sig_weight = _get_signal_weight(sig, effective_conf)
                    _order_amt = order_size if order_size > 0 else int(account_balance * _sig_weight)
                    qty = max(1, int(_order_amt / (price * _fx)))
                    save_activity_log("cio_manager",
                        f"  📐 주문 계산: 잔고 {account_balance:,.0f}원 × 비중 {_sig_weight:.1%} = {_order_amt:,.0f}원 → ${price:.2f} × ₩{_fx:.0f} = {qty}주", "info")
                else:
                    if _KIS_AVAILABLE and _kis_configured():
                        price = await _kis_price(ticker)
                    else:
                        target_w = next((w for w in market_watchlist if w["ticker"] == ticker), None)
                        price = target_w.get("target_price", 0) if target_w else 0
                    if price <= 0:
                        price = 50000
                    _order_amt = order_size if order_size > 0 else int(account_balance * _get_signal_weight(sig, effective_conf))
                    qty = max(1, int(_order_amt / price))

                if use_kis:
                    mode_str = "실거래" if not KIS_IS_MOCK else "모의투자(KIS)"
                    save_activity_log("cio_manager",
                        f"  🚀 KIS 주문 전송: {action_kr} {ticker} {qty}주 @ {'$'+str(round(price,2)) if is_us else str(price)+'원'} ({mode_str})", "info")
                    if is_us:
                        order_result = await _kis_us_order(ticker, sig["action"], qty, price=price)
                    else:
                        order_result = await _kis_order(ticker, sig["action"], qty, price=0)
                    save_activity_log("cio_manager",
                        f"  📨 KIS 응답: success={order_result.get('success')}, msg={order_result.get('message', '')[:100]}", "info")
                    if order_result["success"]:
                        orders_triggered += 1
                        save_activity_log("cio_manager",
                            f"✅ [수동/{mode_str}] {action_kr} 성공: {sig.get('name', ticker)} {qty}주 (신뢰도 {effective_conf:.0f}%)",
                            "info")
                        history = _load_data("trading_history", [])
                        _h_id = f"manual_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}"
                        history.insert(0, {
                            "id": _h_id,
                            "date": datetime.now(KST).isoformat(),
                            "ticker": ticker, "name": sig.get("name", ticker),
                            "action": sig["action"], "qty": qty, "price": price,
                            "total": qty * price, "pnl": 0,
                            "strategy": f"CIO 수동분석 ({mode_str}, 신뢰도 {sig['confidence']}%)",
                            "status": "executed", "market": "US" if is_us else "KR",
                            "order_no": order_result.get("order_no", ""),
                        })
                        _save_data("trading_history", history)
                        if sig["action"] == "buy":
                            _register_position_triggers(ticker, sig.get("name", ticker), price, qty,
                                                        "US" if is_us else "KR", settings, source_id=_h_id)
                    else:
                        save_activity_log("cio_manager",
                            f"❌ [수동/{mode_str}] 주문 실패: {sig.get('name', ticker)} — {order_result.get('message', '원인 불명')}", "error")
                elif use_mock_kis:
                    # ── KIS 모의투자 계좌로 실제 주문 ──
                    save_activity_log("cio_manager",
                        f"  🚀 KIS 모의투자 주문 전송: {action_kr} {ticker} {qty}주 @ {'$'+str(round(price,2)) if is_us else str(price)+'원'}", "info")
                    if is_us:
                        order_result = await _kis_mock_us_order(ticker, sig["action"], qty, price=price)
                    else:
                        order_result = await _kis_mock_order(ticker, sig["action"], qty, price=0)
                    save_activity_log("cio_manager",
                        f"  📨 KIS 모의투자 응답: success={order_result.get('success')}, msg={order_result.get('message', '')[:100]}", "info")
                    if order_result["success"]:
                        orders_triggered += 1
                        save_activity_log("cio_manager",
                            f"✅ [수동/모의투자] {action_kr} 성공: {sig.get('name', ticker)} {qty}주 (신뢰도 {effective_conf:.0f}%)", "info")
                        history = _load_data("trading_history", [])
                        _h_id2 = f"mock_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}"
                        history.insert(0, {
                            "id": _h_id2,
                            "date": datetime.now(KST).isoformat(),
                            "ticker": ticker, "name": sig.get("name", ticker),
                            "action": sig["action"], "qty": qty, "price": price,
                            "total": qty * price, "pnl": 0,
                            "strategy": f"CIO 수동분석 (모의투자, 신뢰도 {sig['confidence']}%)",
                            "status": "mock_executed", "market": "US" if is_us else "KR",
                            "order_no": order_result.get("order_no", ""),
                        })
                        _save_data("trading_history", history)
                        if sig["action"] == "buy":
                            _register_position_triggers(ticker, sig.get("name", ticker), price, qty,
                                                        "US" if is_us else "KR", settings, source_id=_h_id2)
                    else:
                        save_activity_log("cio_manager",
                            f"❌ [수동/모의투자] 주문 실패: {sig.get('name', ticker)} — {order_result.get('message', '원인 불명')}", "error")
                else:
                    # 가상 포트폴리오 (paper trading)
                    portfolio = _load_data("trading_portfolio", _default_portfolio())
                    if sig["action"] == "buy" and portfolio["cash"] >= price * qty:
                        holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
                        total_amount = qty * price
                        if holding:
                            old_total = holding["avg_price"] * holding["qty"]
                            holding["qty"] += qty
                            holding["avg_price"] = int((old_total + total_amount) / holding["qty"])
                            holding["current_price"] = price
                        else:
                            portfolio["holdings"].append({
                                "ticker": ticker, "name": sig.get("name", ticker),
                                "qty": qty, "avg_price": price, "current_price": price,
                                "market": sig.get("market", market),
                            })
                        portfolio["cash"] -= total_amount
                        portfolio["updated_at"] = datetime.now(KST).isoformat()
                        _save_data("trading_portfolio", portfolio)
                        orders_triggered += 1
                        history = _load_data("trading_history", [])
                        _h_id3 = f"manual_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}"
                        history.insert(0, {
                            "id": _h_id3,
                            "date": datetime.now(KST).isoformat(),
                            "ticker": ticker, "name": sig.get("name", ticker),
                            "action": "buy", "qty": qty, "price": price,
                            "total": total_amount, "pnl": 0,
                            "strategy": f"CIO 수동분석 (가상, 신뢰도 {sig['confidence']}%)",
                            "status": "executed", "market": sig.get("market", market),
                        })
                        _save_data("trading_history", history)
                        save_activity_log("cio_manager",
                            f"[수동/가상] 매수: {sig.get('name', ticker)} {qty}주 x {price:,.0f}원 (신뢰도 {effective_conf:.0f}%)", "info")
                        _register_position_triggers(ticker, sig.get("name", ticker), price, qty,
                                                    sig.get("market", market), settings, source_id=_h_id3)
                    elif sig["action"] == "sell":
                        holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
                        if holding and holding["qty"] > 0:
                            sell_qty = min(qty, holding["qty"])
                            total_amount = sell_qty * price
                            pnl = (price - holding["avg_price"]) * sell_qty
                            holding["qty"] -= sell_qty
                            if holding["qty"] == 0:
                                portfolio["holdings"] = [h for h in portfolio["holdings"] if h["ticker"] != ticker]
                            portfolio["cash"] += total_amount
                            portfolio["updated_at"] = datetime.now(KST).isoformat()
                            _save_data("trading_portfolio", portfolio)
                            orders_triggered += 1
                            history = _load_data("trading_history", [])
                            history.insert(0, {
                                "id": f"manual_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}",
                                "date": datetime.now(KST).isoformat(),
                                "ticker": ticker, "name": sig.get("name", ticker),
                                "action": "sell", "qty": sell_qty, "price": price,
                                "total": total_amount, "pnl": pnl,
                                "strategy": f"CIO 수동분석 (가상, 신뢰도 {sig['confidence']}%)",
                                "status": "executed", "market": sig.get("market", market),
                            })
                            _save_data("trading_history", history)
                            pnl_str = f"{'+'if pnl>=0 else ''}{pnl:,.0f}원"
                            save_activity_log("cio_manager",
                                f"[수동/가상] 매도: {sig.get('name', ticker)} {sell_qty}주 x {price:,.0f}원 (손익 {pnl_str})", "info")
            except Exception as order_err:
                import traceback
                _tb = traceback.format_exc()
                logger.error("[수동 분석] 자동주문 오류 (%s): %s\n%s", ticker, order_err, _tb)
                save_activity_log("cio_manager", f"❌ [수동] 주문 오류: {ticker} — {order_err}", "error")

    # ── CIO 목표가 기반 buy_limit 트리거 자동 등록 (수동 즉시분석) ──
    _today_str2 = datetime.now(KST).strftime("%Y%m%d")
    for sig in parsed_signals:
        _tp = sig.get("target_price", 0)
        if _tp <= 0 or sig["action"] not in ("buy", "hold"):
            continue
        _bl2_ticker = sig["ticker"]
        _bl2_name = sig.get("name", _bl2_ticker)
        _bl2_market = sig.get("market", market)
        _bl2_is_us = _bl2_market.upper() in ("US", "USA", "OVERSEAS") or (
            _bl2_ticker.isalpha() and len(_bl2_ticker) <= 5
        )
        _all2 = _load_data("price_triggers", [])
        _all2 = [
            t for t in _all2
            if not (
                t.get("type") == "buy_limit"
                and t.get("ticker") == _bl2_ticker
                and t.get("created_at", "").startswith(_today_str2)
            )
        ]
        _w2 = _get_signal_weight(sig, sig.get("confidence", 50))
        _amt2 = int(account_balance * _w2) if account_balance > 0 else 500_000
        _fx2 = _get_fx_rate()
        _qty2 = max(1, int(_amt2 / (_tp * _fx2))) if _bl2_is_us else max(1, int(_amt2 / _tp))
        _all2.insert(0, {
            "id": f"bl_{_bl2_ticker}_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}",
            "ticker": _bl2_ticker, "name": _bl2_name,
            "type": "buy_limit", "trigger_price": _tp, "qty": _qty2,
            "market": _bl2_market, "active": True,
            "created_at": datetime.now(KST).isoformat(),
            "source": "cio_manual", "source_id": new_signal["id"],
            "note": f"CIO 목표매수: {_tp:,.0f} ({sig.get('confidence', 0)}% 신뢰도) — {sig.get('reason', '')[:60]}",
        })
        if len(_all2) > 500:
            _all2 = _all2[:500]
        _save_data("price_triggers", _all2)
        save_activity_log(
            "cio_manager",
            f"🎯 목표매수 자동등록: {_bl2_name}({_bl2_ticker}) 목표가 {_tp:,.0f} × {_qty2}주",
            "info",
        )

    save_activity_log("cio_manager",
        f"✅ 수동 분석 완료: {len(parsed_signals)}개 시그널 (주문 {orders_triggered}건, 비용 ${cost:.4f})", "info")

    return {
        "success": True,
        "market": market_label,
        "signals_count": len(parsed_signals),
        "signals": parsed_signals,
        "orders_triggered": orders_triggered,
        "calibration": calibration,
        "calibration_factor": calibration_factor,
        "cost_usd": cost,
        "analysis_preview": content[:500] + "..." if len(content) > 500 else content,
    }


def _is_us_dst() -> bool:
    """미국 서머타임(EDT) 여부 판정 — 3월 둘째 일요일 02:00 ~ 11월 첫째 일요일 02:00 (ET).
    한국은 서머타임이 없으므로 날짜 기준 근사 판정."""
    now = datetime.now(KST)
    y = now.year
    # 3월 둘째 일요일 (weekday: 0=Mon, 6=Sun)
    mar1_wd = datetime(y, 3, 1).weekday()
    second_sun_mar = 1 + (6 - mar1_wd) % 7 + 7
    # 11월 첫째 일요일
    nov1_wd = datetime(y, 11, 1).weekday()
    first_sun_nov = 1 + (6 - nov1_wd) % 7
    mar_date = datetime(y, 3, second_sun_mar, tzinfo=KST)
    nov_date = datetime(y, 11, first_sun_nov, tzinfo=KST)
    return mar_date <= now < nov_date


def _us_market_hours_kst() -> tuple[str, str]:
    """미국 정규장 KST 시작/종료 시각 (서머타임 자동 반영).
    EST(겨울): 23:30~06:00 KST | EDT(여름): 22:30~05:00 KST"""
    if _is_us_dst():
        return "22:30", "05:00"
    return "23:30", "06:00"


def _is_market_open(settings: dict) -> tuple[bool, str]:
    """한국/미국 장 시간인지 확인합니다. (둘 중 하나라도 열려있으면 True)
    주말(토/일)에는 무조건 False. 미국 장 시간은 서머타임(DST) 자동 반영."""
    now = datetime.now(KST)

    # 주말 체크 (월=0 ~ 금=4 평일, 토=5 일=6 주말)
    if now.weekday() >= 5:
        return False, ""

    now_min = now.hour * 60 + now.minute

    # 한국 장 (09:00 ~ 15:20 KST, 평일만)
    kr = settings.get("trading_hours_kr", settings.get("trading_hours", {}))
    kr_start = sum(int(x) * m for x, m in zip(kr.get("start", "09:00").split(":"), [60, 1]))
    kr_end = sum(int(x) * m for x, m in zip(kr.get("end", "15:20").split(":"), [60, 1]))
    if kr_start <= now_min < kr_end:
        return True, "KR"

    # 미국 장 (서머타임 자동 반영, 평일만)
    # 금요일 밤~토요일 새벽은 미국장 오픈이지만, 토요일 새벽(weekday=5)은 위에서 이미 차단됨
    us_default_start, us_default_end = _us_market_hours_kst()
    us = settings.get("trading_hours_us", {})
    us_start = sum(int(x) * m for x, m in zip(us.get("start", us_default_start).split(":"), [60, 1]))
    us_end = sum(int(x) * m for x, m in zip(us.get("end", us_default_end).split(":"), [60, 1]))
    if us_start <= now_min or now_min < us_end:  # 자정 넘김 처리
        return True, "US"

    return False, ""


def _us_analysis_time_kst() -> tuple[int, int]:
    """미국장 분석 실행 시각 (KST, 장 오픈 10분 후).
    EST(겨울): 23:40 KST | EDT(여름): 22:40 KST"""
    return (22, 40) if _is_us_dst() else (23, 40)


def _next_trading_run_time():
    """다음 실행 시각 계산 (09:10 KST 한국장 / 23:40 또는 22:40 KST 미국장).

    미국장 시간은 서머타임(DST) 자동 반영.
    주말(토/일)은 건너뛰고 다음 평일(월요일)로 이동.
    """
    now = datetime.now(KST)
    us_h, us_m = _us_analysis_time_kst()

    # 오늘부터 최대 7일 탐색 (주말 건너뛰기)
    for offset in range(7):
        day = now.date() + timedelta(days=offset)
        # 주말 건너뛰기 (토=5, 일=6)
        if day.weekday() >= 5:
            continue
        run_times = [
            datetime(day.year, day.month, day.day, 9, 10, tzinfo=KST),
            datetime(day.year, day.month, day.day, us_h, us_m, tzinfo=KST),
        ]
        for t in run_times:
            if t > now:
                return t

    # 폴백 (도달하면 안 되지만 안전장치)
    tomorrow = now.date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, 9, 10, tzinfo=KST)


async def _trading_bot_loop():
    """자동매매 봇 루프 — 투자팀장이 분석 → 자동 매매.

    흐름:
    1. 하루 2회 정해진 시각에 실행 (09:10 KST, 14:50 KST)
    2. 관심종목이 있으면 CIO 팀에게 분석 위임
    3. CIO가 4명 전문가 결과를 취합하여 매수/매도/관망 판단
    4. 신뢰도 70% 이상 시그널만 자동 주문 실행 (auto_execute=True일 때만)
    5. 모의투자 모드(paper_trading=True)에서는 가상 포트폴리오만 업데이트
    """
    logger = logging.getLogger("corthex.trading")
    us_h, us_m = _us_analysis_time_kst()
    logger.info("자동매매 봇 루프 시작 (CIO 연동 — 하루 2회: 09:10 한국장 + %02d:%02d 미국장 KST)", us_h, us_m)

    while app_state.trading_bot_active:
        try:
            next_run = _next_trading_run_time()
            now = datetime.now(KST)
            sleep_seconds = (next_run - now).total_seconds()
            logger.info("[TRADING BOT] 다음 실행 예약: %s (약 %.0f초 후)",
                        next_run.strftime("%Y-%m-%d %H:%M KST"), sleep_seconds)
            if sleep_seconds > 0:
                await asyncio.sleep(sleep_seconds)
            if not app_state.trading_bot_active:
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
            tickers_info = ", ".join([f"{w['name']}({w['ticker']})" for w in market_watchlist])
            strategies = _load_data("trading_strategies", [])
            active = [s for s in strategies if s.get("active")]
            strats_info = ", ".join([s["name"] for s in active[:5]]) or "기본 전략"

            # 자기학습 보정 섹션 (베이지안 + ELO + 오답패턴 + Platt Scaling 통합)
            cal_section = _build_calibration_prompt_section(settings)

            prompt = f"""[자동매매 봇 — {market_name}장 정기 분석]

## 분석 대상 ({len(market_watchlist)}개 종목)
{tickers_info}

## 활성 전략: {strats_info}{cal_section}

## 분석 요청
도구(API)를 사용하여 직접 아래 분석을 수행하세요:
- **시황분석**: {'코스피/코스닥 지수 흐름, 외국인/기관 동향, 금리/환율' if market == 'KR' else 'S&P500/나스닥 지수, 미국 금리/고용지표, 달러 강세'}
- **종목분석**: 각 종목 재무 건전성, PER/PBR, 최근 실적
- **기술적분석**: RSI, MACD, 이동평균선, 볼린저밴드
- **리스크관리**: 손절가, 적정 포지션 크기, 전체 포트폴리오 리스크

## 최종 산출물 (반드시 아래 형식 그대로 — 예시처럼 정확히)
[시그널] 삼성전자 (005930) | 매수 | 신뢰도 72% | 비중 15% | 목표가 78000 | 반도체 수요 회복 + RSI 과매도 구간
[시그널] 카카오 (035720) | 매도 | 신뢰도 61% | 비중 10% | 목표가 0 | PER 과대평가, 금리 민감 섹터 약세
[시그널] LG에너지솔루션 (373220) | 관망 | 신뢰도 45% | 비중 0% | 목표가 390000 | 혼조세, 이 가격 도달 시 진입 검토

※ 주의:
- 신뢰도는 종목별로 독립적으로 계산, 0~100 숫자 + % 기호로 표기
- 목표가(권장 매수 진입가): 매수/관망 종목은 반드시 입력. 현재가보다 낮은 목표 진입가 설정. 미국 주식은 USD 단위. 매도 종목은 0
- 목표가 도달 시 서버가 자동으로 매수 실행 — 신중하게 설정할 것"""

            cio_result = await _call_agent("cio_manager", prompt)
            content = cio_result.get("content", "")
            cost = cio_result.get("cost_usd", 0)

            # ── 비서실장 QA: 팀장 보고서 검수 ──
            qa_passed, qa_reason = await _chief_qa_review(content, "금융분석팀장")
            save_activity_log("chief_of_staff",
                f"📋 자동분석 QA: {'✅ 승인' if qa_passed else '❌ 반려'} — {qa_reason[:80]}",
                "info" if qa_passed else "warning")

            # 시그널 파싱
            parsed_signals = _parse_cio_signals(content, market_watchlist)

            # 시그널 저장 (QA 결과 포함)
            signals = _load_data("trading_signals", [])
            new_signal = {
                "id": f"sig_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}",
                "date": datetime.now(KST).isoformat(),
                "market": market,
                "analysis": content,
                "tickers": [w["ticker"] for w in market_watchlist[:10]],
                "parsed_signals": parsed_signals,
                "strategy": "cio_bot_analysis",
                "analyzed_by": "금융분석팀장 단독 분석",
                "cost_usd": cost,
                "auto_bot": True,
                "qa_passed": qa_passed,
                "qa_reason": qa_reason[:200],
            }
            signals.insert(0, new_signal)
            if len(signals) > 200:
                signals = signals[:200]
            _save_data("trading_signals", signals)

            # QA 반려 시 매매 안 함
            if not qa_passed:
                save_activity_log("chief_of_staff",
                    f"🚫 자동분석 QA 반려 — 매매 중단: {qa_reason[:100]}", "warning")
                continue

            # 매매 결정 일지 저장 (P2-1: 자동봇에서도 decisions 저장)
            _save_decisions(parsed_signals)

            # 자동 주문 실행 (auto_execute=True + 신뢰도 충족 시)
            auto_execute = settings.get("auto_execute", False)
            min_confidence = settings.get("min_confidence", 70)
            order_size = settings.get("order_size", 0)  # 0 = CIO 비중 자율

            if auto_execute:
                enable_real = settings.get("enable_real", True)
                enable_mock = settings.get("enable_mock", False)
                paper_mode = settings.get("paper_trading", True)
                use_kis = enable_real and _KIS_AVAILABLE and not paper_mode and _kis_configured()
                use_mock_kis = (not use_kis) and enable_mock and _KIS_AVAILABLE and _kis_mock_configured()

                # CIO 비중 기반 매수(B안): order_size=0이면 잔고×비중으로 자동 산출
                account_balance = 0
                if order_size == 0:
                    try:
                        if use_kis:
                            _bal = await _kis_balance()
                            account_balance = _bal.get("cash", 0) if _bal.get("success") else 0
                        elif use_mock_kis:
                            _bal = await _kis_mock_balance()
                            account_balance = _bal.get("cash", 0) if _bal.get("success") else 0
                        else:
                            _port = _load_data("trading_portfolio", _default_portfolio())
                            account_balance = _port.get("cash", 0)
                    except Exception as e:
                        logger.debug("봇 잔고 조회 실패: %s", e)
                    if account_balance <= 0:
                        account_balance = 1_000_000
                        save_activity_log("cio_manager", "CIO 비중 모드: 잔고 조회 실패, 기본 100만원 사용", "warning")

                for sig in parsed_signals:
                    if sig["action"] not in ("buy", "sell"):
                        continue
                    # 자기보정 적용: 유효 신뢰도 = raw × calibration_factor
                    # factor < 1 (AI 과신) → 유효 신뢰도 하락 → 더 엄격한 필터
                    effective_conf = sig.get("confidence", 0) * calibration_factor
                    if effective_conf < min_confidence:
                        continue

                    ticker = sig["ticker"]
                    # 한국/미국 시장 자동 판별: ticker가 영문이면 US, 숫자면 KR
                    sig_market = sig.get("market", market)
                    is_us = sig_market.upper() in ("US", "USA", "OVERSEAS") or (ticker.isalpha() and len(ticker) <= 5)

                    try:
                        if is_us:
                            # ── 미국주식 현재가 조회 + 지정가 주문 ──
                            if _KIS_AVAILABLE and _kis_configured():
                                us_price_data = await _kis_us_price(ticker)
                                price = us_price_data.get("price", 0) if us_price_data.get("success") else 0
                            else:
                                target_w = next((w for w in market_watchlist if w.get("ticker", "").upper() == ticker.upper()), None)
                                price = float(target_w.get("target_price", 0)) if target_w else 0
                            if price <= 0:
                                save_activity_log("cio_manager", f"[US] {ticker} 현재가 조회 실패 — 주문 건너뜀", "warning")
                                continue
                            # 미국주식: order_size(원) ÷ (가격×환율) = 주수
                            _fx = _get_fx_rate()
                            _order_amt = order_size if order_size > 0 else int(account_balance * _get_signal_weight(sig, effective_conf))
                            qty = max(1, int(_order_amt / (price * _fx)))
                        else:
                            # ── 한국주식 현재가 조회 ──
                            if _KIS_AVAILABLE and _kis_configured():
                                price = await _kis_price(ticker)
                            else:
                                target_w = next((w for w in market_watchlist if w["ticker"] == ticker), None)
                                price = target_w.get("target_price", 0) if target_w else 0
                            if price <= 0:
                                price = 50000  # 가격 미설정 시 기본값
                            _order_amt = order_size if order_size > 0 else int(account_balance * _get_signal_weight(sig, effective_conf))
                            qty = max(1, int(_order_amt / price))

                        if use_kis:
                            mode_str = "실거래" if not KIS_IS_MOCK else "모의투자(KIS)"
                            action_kr = "매수" if sig["action"] == "buy" else "매도"

                            if is_us:
                                order_result = await _kis_us_order(ticker, sig["action"], qty, price=price)
                                order_total = qty * price
                            else:
                                order_result = await _kis_order(ticker, sig["action"], qty, price=0)
                                order_total = qty * price

                            if order_result["success"]:
                                order_msg = f"[{mode_str}] {action_kr} 주문 완료: {sig.get('name', ticker)} {qty}주 ${price:.2f}" if is_us else \
                                            f"[{mode_str}] {action_kr} 주문 완료: {sig.get('name', ticker)} {qty}주 (주문번호: {order_result['order_no']})"
                                save_activity_log("cio_manager", order_msg, "info")
                                history = _load_data("trading_history", [])
                                _auto_h_id = f"kis_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}"
                                history.insert(0, {
                                    "id": _auto_h_id,
                                    "date": datetime.now(KST).isoformat(),
                                    "ticker": ticker, "name": sig.get("name", ticker),
                                    "action": sig["action"], "qty": qty, "price": price,
                                    "total": order_total, "pnl": 0,
                                    "strategy": f"CIO 자동매매 ({mode_str}, 신뢰도 {sig['confidence']}%)",
                                    "status": "executed", "market": "US" if is_us else "KR",
                                    "order_no": order_result["order_no"],
                                    "currency": "USD" if is_us else "KRW",
                                })
                                _save_data("trading_history", history)
                                if sig["action"] == "buy":
                                    _register_position_triggers(ticker, sig.get("name", ticker), price, qty,
                                                                "US" if is_us else "KR", settings, source_id=_auto_h_id)
                            else:
                                order_msg = f"[{mode_str}] 주문 실패: {sig.get('name', ticker)} — {order_result['message']}"
                                save_activity_log("cio_manager", order_msg, "warning")

                        elif use_mock_kis:
                            # ── KIS 모의투자 계좌로 실제 주문 ──
                            action_kr = "매수" if sig["action"] == "buy" else "매도"

                            if is_us:
                                order_result = await _kis_mock_us_order(ticker, sig["action"], qty, price=price)
                                order_total = qty * price
                            else:
                                order_result = await _kis_mock_order(ticker, sig["action"], qty, price=0)
                                order_total = qty * price

                            if order_result["success"]:
                                order_msg = f"[모의투자] {action_kr} 주문 완료: {sig.get('name', ticker)} {qty}주" + \
                                            (f" ${price:.2f}" if is_us else f" (주문번호: {order_result['order_no']})")
                                save_activity_log("cio_manager", order_msg, "info")
                                history = _load_data("trading_history", [])
                                _auto_mock_id = f"mock_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}"
                                history.insert(0, {
                                    "id": _auto_mock_id,
                                    "date": datetime.now(KST).isoformat(),
                                    "ticker": ticker, "name": sig.get("name", ticker),
                                    "action": sig["action"], "qty": qty, "price": price,
                                    "total": order_total, "pnl": 0,
                                    "strategy": f"CIO 자동매매 (모의투자, 신뢰도 {sig['confidence']}%)",
                                    "status": "mock_executed", "market": "US" if is_us else "KR",
                                    "order_no": order_result["order_no"],
                                    "currency": "USD" if is_us else "KRW",
                                })
                                _save_data("trading_history", history)
                                if sig["action"] == "buy":
                                    _register_position_triggers(ticker, sig.get("name", ticker), price, qty,
                                                                "US" if is_us else "KR", settings, source_id=_auto_mock_id)
                            else:
                                order_msg = f"[모의투자] 주문 실패: {sig.get('name', ticker)} — {order_result['message']}"
                                save_activity_log("cio_manager", order_msg, "warning")

                        else:
                            # 가상 포트폴리오 업데이트 (paper_trading 모드)
                            portfolio = _load_data("trading_portfolio", _default_portfolio())
                            if sig["action"] == "buy" and portfolio["cash"] >= price * qty:
                                holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
                                total_amount = qty * price
                                if holding:
                                    old_total = holding["avg_price"] * holding["qty"]
                                    new_total = old_total + total_amount
                                    holding["qty"] += qty
                                    holding["avg_price"] = int(new_total / holding["qty"])
                                    holding["current_price"] = price
                                else:
                                    portfolio["holdings"].append({
                                        "ticker": ticker, "name": sig.get("name", ticker),
                                        "qty": qty, "avg_price": price, "current_price": price,
                                        "market": sig.get("market", market),
                                    })
                                portfolio["cash"] -= total_amount
                                portfolio["updated_at"] = datetime.now(KST).isoformat()
                                _save_data("trading_portfolio", portfolio)

                                history = _load_data("trading_history", [])
                                history.insert(0, {
                                    "id": f"auto_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}",
                                    "date": datetime.now(KST).isoformat(),
                                    "ticker": ticker, "name": sig.get("name", ticker),
                                    "action": "buy", "qty": qty, "price": price,
                                    "total": total_amount, "pnl": 0,
                                    "strategy": f"CIO 자동매매 (가상, 신뢰도 {sig['confidence']}%)",
                                    "status": "executed", "market": sig.get("market", market),
                                })
                                _save_data("trading_history", history)

                                save_activity_log("cio_manager",
                                    f"[가상] 매수: {sig.get('name', ticker)} {qty}주 x {price:,.0f}원 (신뢰도 {sig['confidence']}%)",
                                    "info")

                            elif sig["action"] == "sell":
                                holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
                                if holding and holding["qty"] > 0:
                                    sell_qty = min(qty, holding["qty"])
                                    total_amount = sell_qty * price
                                    pnl = (price - holding["avg_price"]) * sell_qty
                                    holding["qty"] -= sell_qty
                                    if holding["qty"] == 0:
                                        portfolio["holdings"] = [h for h in portfolio["holdings"] if h["ticker"] != ticker]
                                    portfolio["cash"] += total_amount
                                    portfolio["updated_at"] = datetime.now(KST).isoformat()
                                    _save_data("trading_portfolio", portfolio)

                                    history = _load_data("trading_history", [])
                                    history.insert(0, {
                                        "id": f"auto_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}",
                                        "date": datetime.now(KST).isoformat(),
                                        "ticker": ticker, "name": sig.get("name", ticker),
                                        "action": "sell", "qty": sell_qty, "price": price,
                                        "total": total_amount, "pnl": pnl,
                                        "strategy": f"CIO 자동매매 (가상, 신뢰도 {sig['confidence']}%)",
                                        "status": "executed", "market": sig.get("market", market),
                                    })
                                    _save_data("trading_history", history)

                                    pnl_str = f"{'+'if pnl>=0 else ''}{pnl:,.0f}원"
                                    save_activity_log("cio_manager",
                                        f"[가상] 매도: {sig.get('name', ticker)} {sell_qty}주 x {price:,.0f}원 (손익 {pnl_str})",
                                        "info")
                    except Exception as order_err:
                        logger.error("[TRADING BOT] 자동주문 오류 (%s): %s", ticker, order_err)

                # ── CIO 목표가 기반 buy_limit 트리거 자동 등록 ──
                # 매수/관망 시그널에 목표가가 있으면, 가격 도달 시 서버가 자동 매수 실행
                _today_str = datetime.now(KST).strftime("%Y%m%d")
                for sig in parsed_signals:
                    target_price = sig.get("target_price", 0)
                    if target_price <= 0:
                        continue
                    if sig["action"] not in ("buy", "hold"):
                        continue
                    _bl_ticker = sig["ticker"]
                    _bl_name = sig.get("name", _bl_ticker)
                    _bl_market = sig.get("market", market)
                    _bl_is_us = _bl_market.upper() in ("US", "USA", "OVERSEAS") or (
                        _bl_ticker.isalpha() and len(_bl_ticker) <= 5
                    )
                    # 오늘 이미 등록된 같은 종목의 buy_limit은 갱신(제거 후 재등록)
                    _all_triggers = _load_data("price_triggers", [])
                    _all_triggers = [
                        t for t in _all_triggers
                        if not (
                            t.get("type") == "buy_limit"
                            and t.get("ticker") == _bl_ticker
                            and t.get("created_at", "").startswith(_today_str)
                        )
                    ]
                    # 수량: 비중 기반 계산
                    _bl_weight = _get_signal_weight(sig, sig.get("confidence", 50))
                    _bl_amt = int(account_balance * _bl_weight) if account_balance > 0 else 500_000
                    _bl_fx = _get_fx_rate()
                    _bl_qty = max(1, int(_bl_amt / (target_price * _bl_fx))) if _bl_is_us else max(1, int(_bl_amt / target_price))
                    _bl_trigger = {
                        "id": f"bl_{_bl_ticker}_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}",
                        "ticker": _bl_ticker, "name": _bl_name,
                        "type": "buy_limit", "trigger_price": target_price, "qty": _bl_qty,
                        "market": _bl_market, "active": True,
                        "created_at": datetime.now(KST).isoformat(),
                        "source": "cio_auto", "source_id": new_signal["id"],
                        "note": f"CIO 목표매수: {target_price:,.0f} ({sig.get('confidence', 0)}% 신뢰도) — {sig.get('reason', '')[:60]}",
                    }
                    _all_triggers.insert(0, _bl_trigger)
                    if len(_all_triggers) > 500:
                        _all_triggers = _all_triggers[:500]
                    _save_data("price_triggers", _all_triggers)
                    save_activity_log(
                        "cio_manager",
                        f"🎯 목표매수 자동등록: {_bl_name}({_bl_ticker}) 목표가 {target_price:,.0f} × {_bl_qty}주",
                        "info",
                    )

            buy_count = len([s for s in parsed_signals if s.get("action") == "buy"])
            sell_count = len([s for s in parsed_signals if s.get("action") == "sell"])
            logger.info("[TRADING BOT] CIO 분석 완료: 매수 %d, 매도 %d (비용 $%.4f)", buy_count, sell_count, cost)

        except Exception as e:
            logger.error("[TRADING BOT] 에러: %s", e)

    logger.info("자동매매 봇 루프 종료")


# ── kis/balance, kis/status → handlers/trading_handler.py로 분리 ──

@app.get("/api/trading/kis/debug")
async def kis_debug():
    """KIS API 원본 응답 확인 (디버그용)."""
    if not _KIS_AVAILABLE or not _kis_configured():
        return {"error": "KIS 미설정", "available": False}
    try:
        from kis_client import (
            _get_token, KIS_BASE, KIS_APP_KEY, KIS_APP_SECRET,
            KIS_ACCOUNT_NO, KIS_ACCOUNT_CODE, _TR, KIS_IS_MOCK as _mock,
        )
        import httpx as _hx

        token = await _get_token()
        async with _hx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{KIS_BASE}/uapi/domestic-stock/v1/trading/inquire-balance",
                headers={
                    "authorization": f"Bearer {token}",
                    "appkey": KIS_APP_KEY,
                    "appsecret": KIS_APP_SECRET,
                    "tr_id": _TR["balance"],
                },
                params={
                    "CANO": KIS_ACCOUNT_NO,
                    "ACNT_PRDT_CD": KIS_ACCOUNT_CODE,
                    "AFHR_FLPR_YN": "N", "OFL_YN": "",
                    "INQR_DVSN": "02", "UNPR_DVSN": "01",
                    "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
                    "PRCS_DVSN": "01", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
                },
            )
            data = resp.json()
        return {
            "mode": "모의투자" if _mock else "실거래",
            "base_url": KIS_BASE,
            "account": f"****{KIS_ACCOUNT_NO[-4:]}",
            "tr_id": _TR["balance"],
            "http_status": resp.status_code,
            "rt_cd": data.get("rt_cd"),
            "msg_cd": data.get("msg_cd"),
            "msg1": data.get("msg1"),
            "output1_count": len(data.get("output1", [])),
            "output2_sample": data.get("output2", [{}])[:1],
        }
    except Exception as e:
        return {"error": str(e)}


def _enrich_overseas_balance_with_krw(result: dict) -> dict:
    """해외 잔고 결과에 KRW 환산 필드를 추가합니다."""
    if not result.get("success"):
        return result
    fx = _get_fx_rate()
    result["fx_rate"] = fx
    for h in result.get("holdings", []):
        eval_usd = h.get("eval_amt", h.get("qty", 0) * h.get("current_price", 0))
        h["eval_amt_krw"] = round(eval_usd * fx)
        h["eval_profit_krw"] = round(h.get("eval_profit", 0) * fx)
    total_usd = result.get("total_eval_usd", 0)
    result["total_eval_krw"] = round(total_usd * fx)
    cash_usd = result.get("cash_usd", 0)
    result["cash_krw"] = round(cash_usd * fx)
    return result


@app.get("/api/trading/kis/debug-us")
async def kis_debug_us():
    """해외주식 KIS API 원본 응답 확인 (디버그용)."""
    if not _KIS_AVAILABLE or not _kis_configured():
        return {"error": "KIS 미설정", "available": False}
    try:
        from kis_client import (
            get_overseas_balance, KIS_IS_MOCK as _mock, KIS_BASE,
        )
        result = await get_overseas_balance()
        result = _enrich_overseas_balance_with_krw(result)
        return {
            "mode": "모의투자" if _mock else "실거래",
            "base_url": KIS_BASE,
            "result": result,
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/trading/cio/debug")
async def cio_debug():
    """CIO 전문가 도구 스키마 + 테스트 호출 (디버그용)."""
    try:
        from ai_handler import _load_tool_schemas, ask_ai
        # CIO 전문가(시황분석) 허용 도구
        detail = _AGENTS_DETAIL.get("market_analyst", {})
        allowed = detail.get("allowed_tools", [])
        schemas = _load_tool_schemas(allowed_tools=allowed)
        openai_tools = schemas.get("openai", [])
        # 스키마 요약 + 테스트 호출
        tool_names = [t["function"]["name"] for t in openai_tools]
        tool_count = len(openai_tools)
        # 간단한 테스트 호출 (도구 없이)
        test_result = await ask_ai("안녕하세요, 테스트입니다. 한 줄로 응답해주세요.",
                                   system_prompt="간단히 응답", model="gpt-5.2")
        return {
            "specialist": "market_analyst (시황분석)",
            "allowed_tools": allowed,
            "openai_tool_count": tool_count,
            "openai_tool_names": tool_names,
            "openai_first_tool_schema": openai_tools[0] if openai_tools else None,
            "test_call_result": test_result.get("content", "")[:200] if "error" not in test_result else test_result["error"],
            "test_call_error": test_result.get("error"),
        }
    except Exception as e:
        return {"error": str(e)[:500]}


@app.get("/api/trading/cio/debug-tools")
async def cio_debug_tools():
    """CIO 전문가에게 도구 포함 테스트 호출 (실제 400 에러 재현)."""
    try:
        from ai_handler import _load_tool_schemas, ask_ai
        detail = _AGENTS_DETAIL.get("market_analyst", {})
        allowed = detail.get("allowed_tools", [])
        schemas = _load_tool_schemas(allowed_tools=allowed)
        anthropic_tools = schemas.get("anthropic", [])
        # 도구 포함 테스트 — 실제 _call_agent와 동일 경로
        async def _dummy_executor(name, args):
            return f"[테스트] {name} 호출됨: {args}"
        result = await ask_ai(
            "테스트입니다. global_market_tool action=index 로 현재 시장 지수를 알려주세요.",
            system_prompt="간단히 도구를 사용해 응답하세요.",
            model="gpt-5.2",
            tools=anthropic_tools,
            tool_executor=_dummy_executor,
        )
        return {
            "success": "error" not in result,
            "content": result.get("content", "")[:300],
            "error": result.get("error"),
            "tools_count": len(anthropic_tools),
        }
    except Exception as e:
        return {"error": str(e)[:500], "type": type(e).__name__}


# ═══════════════════════════════════════════════════════════════
# 범용 디버그 엔드포인트 — 버그 발생 시 CEO에게 URL 제공용
# ═══════════════════════════════════════════════════════════════

@app.get("/api/debug/ai-providers")
async def debug_ai_providers():
    """AI 프로바이더 연결 상태 진단 — GPT/Claude/Gemini 중 뭐가 켜져있는지 확인."""
    import ai_handler as _ah
    providers = _ah.get_available_providers()
    env_keys = {
        "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY", "")),
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY", "")),
        "GOOGLE_API_KEY": bool(os.getenv("GOOGLE_API_KEY", "")),
    }
    client_info = {
        "anthropic": type(_ah._anthropic_client).__name__ if _ah._anthropic_client else None,
        "openai": type(_ah._openai_client).__name__ if _ah._openai_client else None,
        "google": type(_ah._google_client).__name__ if _ah._google_client else None,
    }
    env_key_map = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GOOGLE_API_KEY"}
    exhausted = list(_ah._exhausted_providers)
    return {
        "providers_available": providers,
        "env_keys_present": env_keys,
        "client_types": client_info,
        "exhausted_providers": exhausted,
        "diagnosis": {
            k: ("🔴 크레딧 소진" if k in _ah._exhausted_providers else
                "정상" if providers.get(k) else
                ("API 키 없음" if not env_keys.get(env_key_map[k]) else
                 "키 있으나 클라이언트 초기화 실패"))
            for k in ["anthropic", "openai", "google"]
        },
    }


@app.post("/api/debug/reset-exhausted-providers")
async def reset_exhausted_providers():
    """크레딧 충전 후 소진 상태를 초기화합니다."""
    import ai_handler as _ah
    prev = list(_ah._exhausted_providers)
    _ah.reset_exhausted_providers()
    return {"reset": prev, "message": f"{len(prev)}개 프로바이더 소진 상태 초기화 완료"}


@app.get("/api/debug/agent-calls")
async def debug_agent_calls():
    """최근 AI 호출 기록 10건 — 어떤 모델/프로바이더로 호출됐는지 확인."""
    try:
        conn = __import__("db").get_connection()
        rows = conn.execute(
            "SELECT agent_id, model, provider, cost_usd, input_tokens, output_tokens, "
            "time_seconds, success, created_at FROM agent_calls "
            "ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        conn.close()
        return {
            "recent_calls": [
                {
                    "agent_id": r[0], "model": r[1], "provider": r[2],
                    "cost_usd": round(r[3], 4) if r[3] else 0,
                    "tokens": f"{r[4] or 0}+{r[5] or 0}",
                    "time_sec": round(r[6], 1) if r[6] else 0,
                    "success": bool(r[7]), "created_at": r[8],
                }
                for r in rows
            ],
            "total_count": len(rows),
        }
    except Exception as e:
        return {"error": str(e)[:300]}


@app.get("/api/debug/cio-signals")
async def debug_cio_signals():
    """CIO 시그널 파싱 상태 — 시그널이 왜 안 뜨는지 확인."""
    signals_data = load_setting("trading_signals") or {}
    decisions = load_setting("trading_decisions") or []
    return {
        "saved_signals": signals_data,
        "saved_decisions_count": len(decisions),
        "latest_decisions": decisions[-3:] if decisions else [],
        "watchlist": load_setting("watchlist") or [],
    }


@app.get("/api/debug/trading-execution")
async def debug_trading_execution():
    """매매 실행 디버그 — auto_execute, 설정, 최근 시그널, 주문 상태 확인."""
    settings = _load_data("trading_settings", _default_trading_settings())
    signals = _load_data("trading_signals", [])
    history = _load_data("trading_history", [])
    latest_signal = signals[0] if signals else {}
    recent_history = history[:5]

    return {
        "settings": {
            "auto_execute": settings.get("auto_execute", False),
            "paper_trading": settings.get("paper_trading", True),
            "min_confidence": settings.get("min_confidence", 65),
            "order_size": settings.get("order_size", 0),
        },
        "kis_status": {
            "available": _KIS_AVAILABLE,
            "configured": _kis_configured() if _KIS_AVAILABLE else False,
            "is_mock": KIS_IS_MOCK,
        },
        "latest_signal": {
            "id": latest_signal.get("id", ""),
            "date": latest_signal.get("date", ""),
            "parsed_count": len(latest_signal.get("parsed_signals", [])),
            "parsed_signals": latest_signal.get("parsed_signals", []),
            "manual_run": latest_signal.get("manual_run", False),
        },
        "recent_orders": [{
            "id": h.get("id"), "date": h.get("date"),
            "ticker": h.get("ticker"), "action": h.get("action"),
            "qty": h.get("qty"), "status": h.get("status"),
        } for h in recent_history],
        "note": "수동 즉시 실행은 auto_execute 무관하게 항상 매매 진행 (2026-02-21 수정)",
    }


@app.get("/api/debug/trading-holdings")
async def debug_trading_holdings():
    """매매 보유종목 디버그 — KIS 잔고 vs 내부 포트폴리오 vs 거래내역 비교."""
    portfolio = _load_data("trading_portfolio", _default_portfolio())
    history = _load_data("trading_history", [])
    settings = _load_data("trading_settings", _default_trading_settings())

    # KIS 실거래 잔고
    kis_bal = None
    if _KIS_AVAILABLE and _kis_configured():
        try:
            kis_bal = await _kis_balance()
        except Exception as e:
            kis_bal = {"error": str(e)}

    # KIS 모의 잔고
    kis_mock = None
    try:
        from kis_client import get_mock_balance
        kis_mock = await get_mock_balance()
    except Exception as e:
        kis_mock = {"error": str(e)}

    # 최근 매수 기록
    recent_buys = [t for t in history[:30] if t.get("action") == "buy"]

    return {
        "kis_available": _KIS_AVAILABLE,
        "kis_configured": _kis_configured() if _KIS_AVAILABLE else False,
        "kis_is_mock": KIS_IS_MOCK,
        "paper_trading": settings.get("paper_trading", True),
        "kis_real_balance": kis_bal,
        "kis_mock_balance": kis_mock,
        "internal_portfolio": {
            "cash": portfolio.get("cash", 0),
            "holdings": portfolio.get("holdings", []),
            "updated_at": portfolio.get("updated_at"),
        },
        "recent_buys": recent_buys[:10],
    }


@app.get("/api/debug/kis-token")
async def debug_kis_token():
    """KIS 토큰 상태 디버그 — 토큰 유효성, 만료시간, 캐시 상태, 쿨다운."""
    info = {"kis_available": _KIS_AVAILABLE, "configured": False}
    if not _KIS_AVAILABLE:
        info["error"] = "kis_client 모듈 로드 실패"
        return info
    try:
        from kis_client import (
            is_configured, KIS_IS_MOCK, KIS_BASE,
            _token_cache, _last_token_request, _TOKEN_COOLDOWN_SEC,
            _last_token_request_domestic, _last_token_request_overseas,
            _last_balance_cache, _last_mock_balance_cache,
            KIS_ACCOUNT_NO, KIS_ACCOUNT_CODE,
        )
        info["configured"] = is_configured()
        info["is_mock"] = KIS_IS_MOCK
        info["base_url"] = KIS_BASE
        info["account"] = f"{KIS_ACCOUNT_NO[:4]}****-{KIS_ACCOUNT_CODE}" if KIS_ACCOUNT_NO else "미설정"

        # 토큰 상태
        now = datetime.now()
        token = _token_cache.get("token")
        expires = _token_cache.get("expires")
        if token and expires:
            remaining = (expires - now).total_seconds()
            info["token"] = {
                "status": "유효" if remaining > 0 else "만료됨",
                "masked": f"{token[:8]}...{token[-4:]}" if token else None,
                "expires": expires.isoformat() if expires else None,
                "remaining_seconds": max(0, int(remaining)),
                "remaining_human": f"{int(remaining // 3600)}시간 {int((remaining % 3600) // 60)}분" if remaining > 0 else "만료됨",
            }
        else:
            info["token"] = {"status": "토큰 없음 (아직 발급되지 않았거나 서버 재시작됨)"}

        # 쿨다운 상태 — 국내/해외 분리
        def _cooldown_info(last_req, label):
            if last_req:
                elapsed = (now - last_req).total_seconds()
                cooldown_remaining = max(0, _TOKEN_COOLDOWN_SEC - elapsed)
                return {
                    "market": label,
                    "last_request": last_req.isoformat(),
                    "elapsed_seconds": int(elapsed),
                    "remaining_seconds": int(cooldown_remaining),
                    "can_request": cooldown_remaining <= 0,
                }
            return {"market": label, "last_request": None, "can_request": True}

        info["cooldown"] = {
            "domestic": _cooldown_info(_last_token_request_domestic, "국내"),
            "overseas": _cooldown_info(_last_token_request_overseas, "해외"),
            "last_any": _last_token_request.isoformat() if _last_token_request else None,
        }

        # 잔고 캐시 상태
        info["balance_cache"] = {
            "real_cached": bool(_last_balance_cache),
            "mock_cached": bool(_last_mock_balance_cache),
            "real_total_krw": _last_balance_cache.get("total_krw") if _last_balance_cache else None,
            "mock_total_krw": _last_mock_balance_cache.get("total_krw") if _last_mock_balance_cache else None,
        }
    except Exception as e:
        info["error"] = str(e)
    return info


@app.get("/api/debug/auto-trading-pipeline")
async def debug_auto_trading_pipeline():
    """자동매매 전체 파이프라인 디버그 — KIS 연결부터 주문 실행까지 전 단계."""
    settings = _load_data("trading_settings", _default_trading_settings())
    signals = _load_data("trading_signals", [])
    watchlist = _load_data("trading_watchlist", [])
    history = _load_data("trading_history", [])

    # KIS 연결 상태
    kis_ok = _KIS_AVAILABLE and _kis_configured()

    # AI 연결 상태
    providers = get_available_providers()

    # 최근 시그널
    latest = signals[0] if signals else {}
    parsed = latest.get("parsed_signals", [])
    buy_signals = [s for s in parsed if s.get("action") == "buy"]
    sell_signals = [s for s in parsed if s.get("action") == "sell"]

    # 파이프라인 단계별 상태
    pipeline = {
        "1_ai_connection": {
            "status": "OK" if any(providers.values()) else "FAIL",
            "providers": {k: "연결됨" if v else "미연결" for k, v in providers.items()},
        },
        "2_watchlist": {
            "status": "OK" if watchlist else "FAIL",
            "count": len(watchlist),
            "tickers": [f"{w['name']}({w['ticker']})" for w in watchlist[:5]],
        },
        "3_signal_generation": {
            "status": "OK" if signals else "FAIL",
            "latest_date": latest.get("date", "없음"),
            "analyzed_by": latest.get("analyzed_by", "없음"),
            "buy_count": len(buy_signals),
            "sell_count": len(sell_signals),
            "hold_count": len([s for s in parsed if s.get("action") == "hold"]),
        },
        "4_kis_connection": {
            "status": "OK" if kis_ok else "FAIL",
            "kis_available": _KIS_AVAILABLE,
            "kis_configured": _kis_configured() if _KIS_AVAILABLE else False,
            "is_mock": KIS_IS_MOCK,
        },
        "5_order_execution": {
            "status": "OK" if kis_ok else "BLOCKED",
            "paper_trading": settings.get("paper_trading", True),
            "auto_execute": settings.get("auto_execute", False),
            "note": "수동 즉시실행(버튼)은 paper_trading 무시하고 KIS 실주문 (2026-02-21 수정)",
            "min_confidence": settings.get("min_confidence", 65),
            "order_size": settings.get("order_size", 0),
        },
        "6_recent_orders": {
            "count": len(history),
            "last_5": [{
                "date": h.get("date", ""),
                "ticker": h.get("ticker", ""),
                "action": h.get("action", ""),
                "status": h.get("status", ""),
            } for h in history[:5]],
        },
    }

    # 전체 판정
    all_ok = all(
        pipeline[k]["status"] == "OK"
        for k in ["1_ai_connection", "2_watchlist", "4_kis_connection"]
    )

    return {
        "overall": "READY" if all_ok else "NOT READY",
        "pipeline": pipeline,
        "quick_diagnosis": (
            "모든 단계 정상 — 즉시분석 버튼으로 매매 가능"
            if all_ok else
            " / ".join([
                f"[{k}] {pipeline[k]['status']}"
                for k in pipeline
                if pipeline[k]["status"] != "OK"
            ])
        ),
    }


@app.get("/api/debug/fx-rate")
async def debug_fx_rate():
    """환율 상태 디버그 — 현재 환율, 마지막 갱신 시간, 수동 갱신."""
    current_rate = _get_fx_rate()
    last_update = app_state.last_fx_update
    since_update = time.time() - last_update if last_update > 0 else -1
    return {
        "current_rate": current_rate,
        "last_updated": datetime.fromtimestamp(last_update, tz=KST).isoformat() if last_update > 0 else "갱신 안됨 (기본값 사용 중)",
        "seconds_since_update": round(since_update) if since_update >= 0 else None,
        "next_update_in": max(0, round(_FX_UPDATE_INTERVAL - since_update)) if since_update >= 0 else "미정",
        "source": "yfinance (USDKRW=X)",
    }


@app.post("/api/debug/fx-rate/refresh")
async def refresh_fx_rate():
    """환율 즉시 갱신."""
    new_rate = await _update_fx_rate()
    if new_rate:
        return {"success": True, "rate": new_rate}
    return {"success": False, "rate": _get_fx_rate(), "message": "갱신 실패 — 기존 값 유지"}


@app.get("/api/debug/server-logs")
async def debug_server_logs(lines: int = 50, service: str = "corthex"):
    """서버 로그 디버그 — SSH 터널 또는 localhost에서만 접근 가능.
    Cloudflare를 우회하여 서버 로그를 확인할 수 있습니다.
    service: corthex(앱 로그), nginx-error, nginx-access
    """
    import subprocess
    # localhost 요청만 허용 (보안)
    log_commands = {
        "corthex": f"journalctl -u corthex --no-pager -n {min(lines, 200)} --output=short-iso",
        "nginx-error": f"tail -n {min(lines, 200)} /var/log/nginx/error.log",
        "nginx-access": f"tail -n {min(lines, 200)} /var/log/nginx/access.log",
    }
    cmd = log_commands.get(service)
    if not cmd:
        return {"error": f"unknown service: {service}", "available": list(log_commands.keys())}
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        log_lines = result.stdout.strip().split("\n") if result.stdout else []
        return {
            "service": service,
            "lines": len(log_lines),
            "logs": log_lines[-min(lines, 200):],
            "stderr": result.stderr[:500] if result.stderr else None,
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout (10s)", "service": service}
    except Exception as e:
        return {"error": str(e), "service": service}


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


# ══════════════════════════════════════════════════════════════════
# ARGOS API — DB 캐시 서빙 (Phase 6-6) + 신뢰도 서버 계산 (Phase 6-7)
# + 정보국 상태 API (Phase 6-8)
# ══════════════════════════════════════════════════════════════════

@app.get("/api/argos/status")
async def argos_status():
    """ARGOS 수집 레이어 현황 — 수집 시각, 오류, 총 건수."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT data_type, last_collected, last_error, total_count, updated_at "
            "FROM argos_collection_status"
        ).fetchall()
        # 주가 레코드 수
        price_cnt     = conn.execute("SELECT COUNT(*) FROM argos_price_history").fetchone()[0]
        news_cnt      = conn.execute("SELECT COUNT(*) FROM argos_news_cache").fetchone()[0]
        dart_cnt      = conn.execute("SELECT COUNT(*) FROM argos_dart_filings").fetchone()[0]
        macro_cnt     = conn.execute("SELECT COUNT(*) FROM argos_macro_data").fetchone()[0]
        try:
            financial_cnt = conn.execute("SELECT COUNT(*) FROM argos_financial_data").fetchone()[0]
        except Exception:
            financial_cnt = 0
        try:
            sector_cnt = conn.execute("SELECT COUNT(*) FROM argos_sector_data").fetchone()[0]
        except Exception:
            sector_cnt = 0
        conn.close()

        status_map = {r[0]: {
            "last_collected": r[1], "last_error": r[2],
            "total_count": r[3], "updated_at": r[4]
        } for r in rows}

        return {"ok": True, "status": status_map, "db_counts": {
            "price": price_cnt, "news": news_cnt, "dart": dart_cnt,
            "macro": macro_cnt, "financial": financial_cnt, "sector": sector_cnt
        }}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/argos/price/{ticker}")
async def argos_price(ticker: str, days: int = 30):
    """ARGOS DB에서 주가 이력 서빙 — AI 도구 호출 불필요."""
    try:
        conn = get_connection()
        cutoff = (datetime.now(KST) - timedelta(days=min(days, 90))).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT trade_date, open_price, high_price, low_price, close_price, volume, change_pct
               FROM argos_price_history
               WHERE ticker=? AND trade_date >= ?
               ORDER BY trade_date DESC LIMIT 90""",
            (ticker.upper(), cutoff)
        ).fetchall()
        conn.close()
        data = [{"date": r[0], "open": r[1], "high": r[2], "low": r[3],
                 "close": r[4], "volume": r[5], "change_pct": r[6]} for r in rows]
        return {"ok": True, "ticker": ticker, "count": len(data), "prices": data,
                "source": "ARGOS DB (서버 캐시)"}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/argos/news/{keyword}")
async def argos_news(keyword: str, days: int = 7):
    """ARGOS DB에서 뉴스 캐시 서빙."""
    try:
        conn = get_connection()
        cutoff = (datetime.now(KST) - timedelta(days=min(days, 30))).isoformat()
        rows = conn.execute(
            """SELECT title, description, link, pub_date, source
               FROM argos_news_cache
               WHERE keyword=? AND pub_date >= ?
               ORDER BY pub_date DESC LIMIT 50""",
            (keyword, cutoff)
        ).fetchall()
        conn.close()
        data = [{"title": r[0], "desc": r[1], "link": r[2],
                 "pub_date": r[3], "source": r[4]} for r in rows]
        return {"ok": True, "keyword": keyword, "count": len(data), "news": data,
                "source": "ARGOS DB (서버 캐시)"}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/argos/dart/{ticker}")
async def argos_dart(ticker: str, days: int = 90):
    """ARGOS DB에서 DART 공시 서빙."""
    try:
        conn = get_connection()
        cutoff = (datetime.now(KST) - timedelta(days=min(days, 90))).strftime("%Y%m%d")
        rows = conn.execute(
            """SELECT corp_name, report_nm, rcept_no, flr_nm, rcept_dt
               FROM argos_dart_filings
               WHERE ticker=? AND rcept_dt >= ?
               ORDER BY rcept_dt DESC LIMIT 50""",
            (ticker.upper(), cutoff)
        ).fetchall()
        conn.close()
        data = [{"corp_name": r[0], "report_nm": r[1], "rcept_no": r[2],
                 "flr_nm": r[3], "rcept_dt": r[4]} for r in rows]
        return {"ok": True, "ticker": ticker, "count": len(data), "filings": data,
                "source": "ARGOS DB (서버 캐시)"}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/argos/macro")
async def argos_macro(days: int = 30):
    """ARGOS DB에서 매크로 지표 서빙."""
    try:
        conn = get_connection()
        cutoff = (datetime.now(KST) - timedelta(days=min(days, 365))).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT indicator, trade_date, value, source
               FROM argos_macro_data
               WHERE trade_date >= ?
               ORDER BY indicator, trade_date DESC""",
            (cutoff,)
        ).fetchall()
        conn.close()
        # indicator별 그룹핑
        from collections import defaultdict
        grouped = defaultdict(list)
        for r in rows:
            grouped[r[0]].append({"date": r[1], "value": r[2], "source": r[3]})
        return {"ok": True, "macro": dict(grouped), "source": "ARGOS DB (서버 캐시)"}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/argos/confidence/{ticker}")
async def argos_confidence(ticker: str):
    """Phase 6-7: 서버 계산 신뢰도 — Quant + Calibration + Bayesian + ELO.
    AI는 이 값을 받아 뉴스 맥락으로 ±20%p 조정만 하면 됨.
    """
    try:
        conn = get_connection()

        # ① 최근 주가 데이터 (90일)
        price_rows = conn.execute(
            """SELECT close_price, volume, change_pct FROM argos_price_history
               WHERE ticker=? ORDER BY trade_date DESC LIMIT 90""",
            (ticker.upper(),)
        ).fetchall()

        quant_score = None
        if len(price_rows) >= 14:
            closes = [r[0] for r in reversed(price_rows)]
            volumes = [r[1] for r in reversed(price_rows)]

            # RSI(14)
            gains, losses = [], []
            for i in range(1, len(closes)):
                d = closes[i] - closes[i-1]
                (gains if d > 0 else losses).append(abs(d))
            avg_gain = sum(gains[-14:]) / 14 if gains else 0.001
            avg_loss = sum(losses[-14:]) / 14 if losses else 0.001
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            # 20일 MA
            ma20 = sum(closes[-20:]) / min(20, len(closes))
            cur = closes[-1]
            above_ma = cur > ma20

            # 볼린저밴드
            if len(closes) >= 20:
                std20 = (sum((x - ma20)**2 for x in closes[-20:]) / 20) ** 0.5
                bb_upper = ma20 + 2 * std20
                bb_lower = ma20 - 2 * std20
                bb_pos = (cur - bb_lower) / (bb_upper - bb_lower) * 100 if bb_upper != bb_lower else 50
            else:
                bb_pos = 50

            # 거래량 비율 (최근 5일 / 이전 20일 평균)
            if len(volumes) >= 25:
                vol_ratio = sum(volumes[-5:]) / 5 / (sum(volumes[-25:-5]) / 20 + 0.001)
            else:
                vol_ratio = 1.0

            # Quant Score 계산 (0~99)
            rsi_score = max(0, min(100, (rsi - 30) / 40 * 100)) if rsi < 70 else max(0, (90 - rsi) * 3)
            ma_score = 60 if above_ma else 30
            bb_score = max(0, min(100, 100 - abs(bb_pos - 50) * 2))
            vol_score = min(100, vol_ratio * 50)
            trend_score = max(0, min(100, 50 + (cur - closes[-10]) / closes[-10] * 100)) if len(closes) >= 10 else 50
            quant_score = round((rsi_score * 0.25 + ma_score * 0.25 + bb_score * 0.2 + vol_score * 0.15 + trend_score * 0.15))

        # ② Calibration Factor
        calibration = _compute_calibration_factor(20)
        cal_factor = calibration.get("factor", 1.0)

        # ③ Bayesian 버킷 보정
        bayesian_adj = 0
        try:
            buckets = conn.execute(
                """SELECT bucket_label, actual_win_rate, sample_count
                   FROM confidence_calibration ORDER BY created_at DESC LIMIT 10"""
            ).fetchall()
            if buckets and quant_score is not None:
                qs_norm = quant_score  # 0~99
                best = min(buckets, key=lambda b: abs(float(b[0].split("_")[0] if "_" in str(b[0]) else b[0]) - qs_norm), default=None)
                if best and best[2] >= 5:
                    actual_wr = float(best[1]) * 100  # 실제 승률(%)
                    bayesian_adj = round(actual_wr - 50, 1)  # 50% 기준 편차
        except Exception:
            pass

        # ④ ELO 가중치 (금융분석팀장 평균 ELO → 신뢰도 가중)
        elo_adj = 0
        try:
            from db import get_analyst_elo
            elos = [get_analyst_elo(aid)["elo_rating"] for aid in ["cio_manager"]]
            avg_elo = sum(elos) / len(elos)
            # ELO 1500 기준: 100점 차이 = ±3%p
            elo_adj = round((avg_elo - 1500) / 100 * 3, 1)
        except Exception:
            pass

        conn.close()

        # 최종 서버 신뢰도
        base_conf = quant_score if quant_score is not None else 50
        server_conf = round(base_conf * cal_factor + bayesian_adj + elo_adj)
        server_conf = max(10, min(95, server_conf))

        return {
            "ok": True,
            "ticker": ticker,
            "server_confidence": server_conf,
            "components": {
                "quant_score": quant_score,
                "calibration_factor": round(cal_factor, 3),
                "bayesian_adj": bayesian_adj,
                "elo_adj": elo_adj,
            },
            "ai_instruction": f"서버 계산 신뢰도 {server_conf}%. 뉴스/맥락 분석 후 ±20%p 범위 내에서 조정 (이탈 시 이유 명시).",
            "price_bars_used": len(price_rows),
            "source": "ARGOS 서버 계산 (AI 호출 없음)"
        }
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/intelligence/status")
async def intelligence_status():
    """정보국 통합 상태 — 상단 상태바 + 정보국 탭 데이터 소스 (Phase 6-8)."""
    try:
        conn = get_connection()
        now_kst = datetime.now(KST)

        # ARGOS 수집 상태
        argos_rows = conn.execute(
            "SELECT data_type, last_collected, last_error FROM argos_collection_status"
        ).fetchall()
        argos_map = {r[0]: {"last": r[1], "error": r[2]} for r in argos_rows}

        # 활성 가격 트리거
        triggers = _load_data("price_triggers", [])
        active_triggers = [t for t in triggers if t.get("active", True)]

        # 오늘 AI 비용
        today_str = now_kst.strftime("%Y-%m-%d")
        cost_rows = conn.execute(
            """SELECT COALESCE(SUM(cost_usd), 0) FROM agent_calls
               WHERE created_at >= ?""",
            (today_str,)
        ).fetchone()
        today_cost = round(float(cost_rows[0] or 0), 4)

        week_ago = (now_kst - timedelta(days=7)).strftime("%Y-%m-%d")
        week_rows = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM agent_calls WHERE created_at >= ?",
            (week_ago,)
        ).fetchone()
        week_cost = round(float(week_rows[0] or 0), 4)

        # 최근 AI 활동 (교신로그 통합)
        recent_logs = conn.execute(
            """SELECT agent_id, message, level, timestamp FROM activity_logs
               ORDER BY timestamp DESC LIMIT 20"""
        ).fetchall()
        activity = [{"agent": r[0], "msg": r[1][:100], "level": r[2], "ts": r[3]} for r in recent_logs]

        # 최근 에러 (24시간)
        yesterday = (now_kst - timedelta(hours=24)).isoformat()
        error_logs = conn.execute(
            """SELECT agent_id, message, timestamp FROM activity_logs
               WHERE level='error' AND timestamp >= ?
               ORDER BY timestamp DESC LIMIT 10""",
            (yesterday,)
        ).fetchall()
        errors = [{"agent": r[0], "msg": r[1][:150], "ts": r[2]} for r in error_logs]

        # 팀장별 비용 (오늘)
        agent_costs = conn.execute(
            """SELECT agent_id, COALESCE(SUM(cost_usd), 0) as cost
               FROM agent_calls WHERE created_at >= ?
               GROUP BY agent_id ORDER BY cost DESC""",
            (today_str,)
        ).fetchall()
        per_agent = [{"agent": r[0], "cost": round(float(r[1]), 4)} for r in agent_costs]

        conn.close()

        # 데이터 수집 상태 판정
        price_ok = bool(argos_map.get("price", {}).get("last"))
        news_ok  = bool(argos_map.get("news", {}).get("last"))
        has_error = bool(errors)

        return {
            "ok": True,
            "timestamp": now_kst.isoformat(),
            "status_bar": {
                "data_ok": price_ok,
                "data_last": argos_map.get("price", {}).get("last", ""),
                "ai_ok": len(activity) > 0,
                "ai_last": activity[0]["ts"] if activity else "",
                "trigger_count": len(active_triggers),
                "today_cost_usd": today_cost,
                "has_error": has_error,
            },
            "argos": argos_map,
            "triggers": active_triggers[:20],
            "activity": activity,
            "errors": errors,
            "costs": {
                "today_usd": today_cost,
                "week_usd": week_cost,
                "per_agent": per_agent,
            },
        }
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/argos/collect/now")
async def argos_collect_now(req: Request):
    """수동으로 ARGOS 수집을 즉시 트리거합니다."""
    body = await req.json() if req.headers.get("content-type", "").startswith("application/json") else {}
    data_type = body.get("type", "all")
    results = {}
    if data_type in ("all", "price"):
        results["price"] = await _argos_collect_prices_safe() or "실행됨"
    if data_type in ("all", "news"):
        results["news"] = await _argos_collect_news_safe() or "실행됨"
    if data_type in ("all", "dart"):
        results["dart"] = await _argos_collect_dart_safe() or "실행됨"
    if data_type in ("all", "macro"):
        results["macro"] = await _argos_collect_macro_safe() or "실행됨"
    if data_type in ("all", "financial"):
        results["financial"] = await _argos_collect_financial_safe() or "실행됨"
    if data_type in ("all", "sector"):
        results["sector"] = await _argos_collect_sector_safe() or "실행됨"
    return {"ok": True, "triggered": results}


@app.get("/api/debug/argos-diag")
async def argos_diagnostic():
    """ARGOS 수집 문제 진단 — 각 단계별 성공/실패 리포트. 항목당 15초 타임아웃."""
    DIAG_TIMEOUT = 15
    diag = {}
    # 1) DB 연결
    try:
        conn = get_connection()
        diag["db"] = "OK"
        conn.close()
    except Exception as e:
        diag["db"] = f"FAIL: {e}"
        return {"ok": False, "diag": diag}

    # 2) watchlist
    wl = _load_data("trading_watchlist", [])
    diag["watchlist"] = f"{len(wl)}종목"
    kr = [w for w in wl if w.get("market", "KR") == "KR"]
    us = [w for w in wl if w.get("market") == "US"]
    diag["kr_tickers"] = [w["ticker"] for w in kr]
    diag["us_tickers"] = [w["ticker"] for w in us]

    # 3) pykrx 테스트 (삼성전자 3일)
    try:
        from pykrx import stock as _pk
        today = datetime.now(KST).strftime("%Y%m%d")
        start = (datetime.now(KST) - timedelta(days=3)).strftime("%Y%m%d")
        df = await asyncio.wait_for(
            asyncio.to_thread(_pk.get_market_ohlcv_by_date, start, today, "005930"),
            timeout=DIAG_TIMEOUT,
        )
        diag["pykrx"] = f"OK ({len(df)}행)" if df is not None and not df.empty else "EMPTY"
    except asyncio.TimeoutError:
        diag["pykrx"] = f"TIMEOUT ({DIAG_TIMEOUT}s)"
    except Exception as e:
        diag["pykrx"] = f"FAIL: {e}"

    # 4) yfinance 테스트 (NVDA)
    try:
        import yfinance as yf
        t = yf.Ticker("NVDA")
        h = await asyncio.wait_for(
            asyncio.to_thread(lambda: t.history(period="3d")),
            timeout=DIAG_TIMEOUT,
        )
        diag["yfinance"] = f"OK ({len(h)}행)" if h is not None and not h.empty else "EMPTY"
    except asyncio.TimeoutError:
        diag["yfinance"] = f"TIMEOUT ({DIAG_TIMEOUT}s)"
    except Exception as e:
        diag["yfinance"] = f"FAIL: {e}"

    # 5) ARGOS 테이블 레코드 수
    try:
        conn = get_connection()
        diag["price_rows"] = conn.execute("SELECT COUNT(*) FROM argos_price_history").fetchone()[0]
        diag["news_rows"] = conn.execute("SELECT COUNT(*) FROM argos_news_cache").fetchone()[0]
        diag["dart_rows"] = conn.execute("SELECT COUNT(*) FROM argos_dart_filings").fetchone()[0]
        diag["macro_rows"] = conn.execute("SELECT COUNT(*) FROM argos_macro_data").fetchone()[0]
        diag["status_rows"] = conn.execute("SELECT COUNT(*) FROM argos_collection_status").fetchone()[0]
        conn.close()
    except Exception as e:
        diag["db_check"] = f"FAIL: {e}"

    # 6) 매크로 수동 테스트 (타임아웃 있음)
    try:
        n = await asyncio.wait_for(_argos_collect_macro(), timeout=60)
        diag["macro_test"] = f"OK ({n}건 수집)"
    except asyncio.TimeoutError:
        diag["macro_test"] = "TIMEOUT (60s)"
    except Exception as e:
        diag["macro_test"] = f"FAIL: {e}"

    return {"ok": True, "diag": diag}


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

    # ── 품질검수 (Quality Gate) ── 전문가 결과를 팀장이 종합하기 전에 검수
    if app_state.quality_gate and _QUALITY_GATE_AVAILABLE and spec_results:
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
            quality_note = ""
            if r.get("rework_attempt"):
                quality_note = f"\n⚠️ 재작업 {r['rework_attempt']}회 후 결과"
            if r.get("quality_warning"):
                quality_note = f"\n⚠️ 품질 경고: {r['quality_warning'][:60]}"
            spec_parts.append(f"[{name}]{quality_note}\n{r.get('content', '응답 없음')}")
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


# 배치 모드 전용 시스템 프롬프트 접미사 (도구 호출 방지)
_BATCH_MODE_SUFFIX = (
    "\n\n[배치 모드 안내] 이 요청은 배치 처리입니다. "
    "도구(함수)를 직접 호출할 수 없습니다. "
    "보유한 지식과 분석 능력만으로 텍스트 기반 답변을 작성하세요. "
    "코드 블록이나 함수 호출 형태(예: await, function() 등)로 답변하지 마세요."
)


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
    # 품질검수 게이트 초기화
    _init_quality_gate()
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
