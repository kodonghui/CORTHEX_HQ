"""도구(Tool) 실행 API — 도구 목록, 실행, 상태, 건강 점검.

비유: 도구 창고 — CORTHEX 에이전트들이 사용하는 도구를 관리하고 직접 실행하는 곳.
"""
import logging
import os
import sys

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from state import app_state

logger = logging.getLogger("corthex")

router = APIRouter(tags=["tools"])


# ── mini_server 참조 헬퍼 ──
def _ms():
    """mini_server 모듈 참조."""
    return sys.modules.get("mini_server") or sys.modules.get("web.mini_server")


def _get_tools_list():
    """_TOOLS_LIST 참조."""
    ms = _ms()
    return getattr(ms, "_TOOLS_LIST", []) if ms else []


def _init_tool_pool():
    """ToolPool 초기화."""
    ms = _ms()
    if ms and hasattr(ms, "_init_tool_pool"):
        return ms._init_tool_pool()
    return None


# ── 도구 목록 ──

@router.get("/api/tools")
async def get_tools():
    return _get_tools_list()


# ── 도구 실행 ──

@router.post("/api/tools/{tool_id}/execute")
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


# ── 도구 상태 ──

@router.get("/api/tools/status")
async def get_tools_status():
    """로드된 도구 목록과 ToolPool 상태를 반환합니다."""
    tools_list = _get_tools_list()
    pool = _init_tool_pool()
    if not pool:
        return {
            "pool_status": "unavailable",
            "loaded_tools": [],
            "total_defined": len(tools_list),
        }

    loaded = list(pool._tools.keys())
    return {
        "pool_status": "ready",
        "loaded_tools": loaded,
        "loaded_count": len(loaded),
        "total_defined": len(tools_list),
    }


# ── 도구 건강 점검 ──

@router.get("/api/tools/health")
async def get_tools_health():
    """모든 도구의 건강 상태를 점검합니다.

    각 도구별로:
    - loaded: ToolPool에 로드 성공 여부
    - api_key_required: API 키가 필요한 도구인지
    - api_key_set: 필요한 API 키가 설정되어 있는지
    - status: ready / missing_key / not_loaded / error
    """
    tools_list = _get_tools_list()
    pool = _init_tool_pool()
    loaded_tools = set(pool._tools.keys()) if pool else set()

    # API 키 환경변수 매핑
    _API_KEY_MAP = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "notion": "NOTION_API_KEY",
        "telegram": "TELEGRAM_BOT_TOKEN",
        "serpapi": "SERPAPI_KEY",
        "newsapi": "NEWSAPI_KEY",
        "alpha_vantage": "ALPHA_VANTAGE_KEY",
    }

    # 도구 → 필요한 서비스 매핑
    _TOOL_SERVICE_HINTS = {
        "notion": "notion", "real_web_search": "serpapi",
        "news": "newsapi", "stock": "alpha_vantage", "market": "alpha_vantage",
        "telegram": "telegram",
    }

    results = []
    for tool_def in tools_list:
        tid = tool_def.get("tool_id", "")
        tname = tool_def.get("name_ko", tool_def.get("name", tid))

        is_loaded = tid in loaded_tools

        # API 키 필요 여부 추정
        required_service = None
        for hint, service in _TOOL_SERVICE_HINTS.items():
            if hint in tid.lower():
                required_service = service
                break

        api_key_env = _API_KEY_MAP.get(required_service, "") if required_service else ""
        api_key_set = bool(os.getenv(api_key_env, "")) if api_key_env else True

        if is_loaded and api_key_set:
            status = "ready"
        elif is_loaded and not api_key_set:
            status = "missing_key"
        elif not is_loaded and required_service:
            status = "not_loaded"
        else:
            status = "not_loaded"

        results.append({
            "tool_id": tid,
            "name": tname,
            "loaded": is_loaded,
            "api_key_required": required_service or None,
            "api_key_env": api_key_env or None,
            "api_key_set": api_key_set,
            "status": status,
        })

    # 통계
    ready_count = sum(1 for r in results if r["status"] == "ready")
    missing_key = sum(1 for r in results if r["status"] == "missing_key")
    not_loaded = sum(1 for r in results if r["status"] == "not_loaded")

    return {
        "total": len(results),
        "ready": ready_count,
        "missing_key": missing_key,
        "not_loaded": not_loaded,
        "pool_status": "ready" if pool else "unavailable",
        "tools": results,
    }
