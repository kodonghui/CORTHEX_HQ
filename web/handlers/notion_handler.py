"""노션(Notion) 로그 조회 API — 노션 저장 로그를 확인하는 곳.

비유: 우체국 수발신 기록 — 노션에 보낸 데이터가 잘 전달됐는지 확인하는 창구.
"""
import os

from fastapi import APIRouter

from state import app_state

router = APIRouter(tags=["notion"])


@router.get("/api/notion-log")
async def get_notion_log():
    """노션 저장 로그 조회 (최근 20건)."""
    _notion_log = app_state.notion_log
    _NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
    _NOTION_DB_SECRETARY = os.getenv("NOTION_DB_SECRETARY", "30a56b49-78dc-8153-bac1-dee5d04d6a74")
    _NOTION_DB_OUTPUT = os.getenv("NOTION_DB_OUTPUT", "30a56b49-78dc-81ce-aaca-ef3fc90a6fba")
    _NOTION_DB_ID = os.getenv("NOTION_DEFAULT_DB_ID", _NOTION_DB_OUTPUT)
    return {
        "logs": _notion_log,
        "total": len(_notion_log),
        "api_key_set": bool(_NOTION_API_KEY),
        "db_secretary": _NOTION_DB_SECRETARY[:8] + "..." if _NOTION_DB_SECRETARY else "(미설정)",
        # _NOTION_DB_ID는 NOTION_DEFAULT_DB_ID 환경변수 → 없으면 NOTION_DB_OUTPUT 폴백
        "db_output_active": _NOTION_DB_ID[:8] + "..." if _NOTION_DB_ID else "(미설정)",
        "db_output_fallback": _NOTION_DB_OUTPUT[:8] + "..." if _NOTION_DB_OUTPUT else "(미설정)",
        "db_id_source": "NOTION_DEFAULT_DB_ID" if os.getenv("NOTION_DEFAULT_DB_ID") else "NOTION_DB_OUTPUT(폴백)",
    }
