"""에이전트 메모리(Memory) 관리 API — 에이전트별 기억 추가·삭제·조회.

비유: 비서 수첩 — 에이전트가 기억해야 할 사항을 기록하고 꺼내보는 곳.
"""
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from db import save_setting, load_setting

logger = logging.getLogger("corthex")

KST = timezone(timedelta(hours=9))

router = APIRouter(prefix="/api/memory", tags=["memory"])


def _load_data(name: str, default=None):
    """DB에서 설정 데이터 로드."""
    db_val = load_setting(name)
    if db_val is not None:
        return db_val
    return default if default is not None else {}


def _save_data(name: str, data) -> None:
    """DB에 설정 데이터 저장."""
    save_setting(name, data)


@router.get("/{agent_id}")
async def get_memory(agent_id: str):
    all_memories = _load_data("memories", {})
    # 수동 기억 + 자동 추출된 카테고리 기억 함께 반환
    categorized = load_setting(f"memory_categorized_{agent_id}", {})
    return {
        "memories": all_memories.get(agent_id, []),
        "categorized": categorized,
    }


@router.post("/{agent_id}")
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


@router.delete("/{agent_id}/categorized")
async def delete_categorized_memory(agent_id: str):
    """에이전트 자동 추출 카테고리 기억 초기화."""
    save_setting(f"memory_categorized_{agent_id}", {})
    return {"success": True}


@router.delete("/{agent_id}/{memory_id}")
async def delete_memory(agent_id: str, memory_id: str):
    """에이전트 메모리 삭제."""
    all_memories = _load_data("memories", {})
    if agent_id in all_memories:
        all_memories[agent_id] = [m for m in all_memories[agent_id] if m.get("id") != memory_id]
        _save_data("memories", all_memories)
    return {"success": True}
