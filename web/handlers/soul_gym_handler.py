"""Soul Gym API 핸들러 — 에이전트 소울 경쟁 진화 엔드포인트.

비유: 패스트푸드 카운터. 웹 UI에서 버튼을 누르면 이 파일이 받아서 엔진에 전달.

엔드포인트:
- POST /api/soul-gym/evolve/{agent_id}  — 특정 에이전트 진화
- POST /api/soul-gym/evolve-all          — 전체 팀장 진화
- GET  /api/soul-gym/history             — 진화 기록 조회
- GET  /api/soul-gym/status              — 현재 진화 중 상태
- GET  /api/soul-gym/config              — Gym 설정 확인
"""

import asyncio
import logging
from fastapi import APIRouter, Request

logger = logging.getLogger("corthex.soul_gym_api")
router = APIRouter(tags=["soul-gym"])

# 진화 진행 상태 (in-memory)
_running: dict[str, bool] = {}
_running_all: bool = False
_single_results: dict[str, dict] = {}  # 개별 진화 결과 저장


@router.post("/api/soul-gym/evolve/{agent_id}")
async def evolve_single(agent_id: str, request: Request):
    """특정 에이전트 1명의 소울 진화를 백그라운드로 실행합니다."""
    global _running
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    dry_run = body.get("dry_run", False)

    if _running.get(agent_id):
        return {"success": False, "message": f"{agent_id} 이미 진화 중입니다."}

    async def _bg():
        try:
            from soul_gym_engine import evolve_agent
            result = await evolve_agent(agent_id, dry_run=dry_run)
            _single_results[agent_id] = {"success": True, **result}
            logger.info("Soul Gym %s 진화 완료: %s", agent_id, result.get("status"))
        except Exception as e:
            logger.error("Soul Gym 진화 실패 (%s): %s", agent_id, e, exc_info=True)
            _single_results[agent_id] = {"success": False, "message": str(e)[:200]}
        finally:
            _running[agent_id] = False

    _running[agent_id] = True
    _single_results.pop(agent_id, None)
    asyncio.create_task(_bg())
    return {"success": True, "message": f"{agent_id} 진화를 시작합니다. /api/soul-gym/status에서 진행 상태를 확인하세요."}


@router.post("/api/soul-gym/evolve-all")
async def evolve_all_agents(request: Request):
    """전체 팀장 6명 순차 진화를 백그라운드로 실행합니다."""
    global _running_all
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    dry_run = body.get("dry_run", False)

    if _running_all:
        return {"success": False, "message": "이미 전체 진화가 진행 중입니다."}

    async def _bg():
        global _running_all
        try:
            from soul_gym_engine import evolve_all
            result = await evolve_all(dry_run=dry_run)
            logger.info("Soul Gym 전체 진화 완료: %s", result.get("status"))
        except Exception as e:
            logger.error("Soul Gym 전체 진화 실패: %s", e, exc_info=True)
        finally:
            _running_all = False

    _running_all = True
    asyncio.create_task(_bg())
    return {"success": True, "message": "전체 팀장 진화를 시작합니다. 완료 시 텔레그램으로 알림됩니다."}


@router.get("/api/soul-gym/history")
async def get_history(agent_id: str = "", limit: int = 50):
    """Soul Gym 진화 기록을 조회합니다."""
    from db import get_soul_gym_history
    history = get_soul_gym_history(agent_id=agent_id, limit=limit)
    return {"history": history, "count": len(history)}


@router.get("/api/soul-gym/status")
async def get_status():
    """현재 진화 진행 상태를 반환합니다."""
    running_agents = [aid for aid, running in _running.items() if running]
    return {
        "running_all": _running_all,
        "running_agents": running_agents,
        "idle": not _running_all and not running_agents,
        "results": _single_results,
    }


@router.get("/api/soul-gym/config")
async def get_config():
    """Soul Gym 설정 정보를 반환합니다."""
    from soul_gym_engine import GYM_MODEL, JUDGE_MODEL, VARIANT_MODEL, MIN_IMPROVEMENT, COST_CAP_USD
    return {
        "gym_model": GYM_MODEL,
        "judge_model": JUDGE_MODEL,
        "variant_model": VARIANT_MODEL,
        "min_improvement": MIN_IMPROVEMENT,
        "cost_cap_usd": COST_CAP_USD,
    }
