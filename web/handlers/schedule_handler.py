"""예약(Schedule) · 워크플로우(Workflow) CRUD API.

비유: 달력/플래너 — 예약 작업과 워크플로우를 만들고 관리하는 곳.
워크플로우 실행(/run)은 AI 의존성이 있어 arm_server.py에 남아 있습니다.
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request

from db import load_setting, save_setting

KST = timezone(timedelta(hours=9))

router = APIRouter(tags=["schedules", "workflows"])


def _load_data(name: str, default=None):
    """DB에서 설정 데이터 로드."""
    val = load_setting(name)
    if val is not None:
        return val
    return default if default is not None else {}


def _save_data(name: str, data) -> None:
    """DB에 설정 데이터 저장."""
    save_setting(name, data)


# ── 예약 (스케줄) 관리 ──

@router.get("/api/schedules")
async def get_schedules():
    return _load_data("schedules", [])


@router.post("/api/schedules")
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


@router.post("/api/schedules/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str):
    """예약 활성화/비활성화."""
    schedules = _load_data("schedules", [])
    for s in schedules:
        if s.get("id") == schedule_id:
            s["enabled"] = not s.get("enabled", True)
            _save_data("schedules", schedules)
            return {"success": True, "enabled": s["enabled"]}
    return {"success": False, "error": "not found"}


@router.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """예약 삭제. 기본 크론(default_*) 삭제 시 서버 재시작 후 복원 방지."""
    schedules = _load_data("schedules", [])
    schedules = [s for s in schedules if s.get("id") != schedule_id]
    _save_data("schedules", schedules)

    # 기본 크론 삭제 시 deleted_schedules에 기록 → 서버 재시작 시 복원하지 않음
    if schedule_id.startswith("default_"):
        deleted = _load_data("deleted_schedules", [])
        if schedule_id not in deleted:
            deleted.append(schedule_id)
            _save_data("deleted_schedules", deleted)

    return {"success": True}


# ── 워크플로우 CRUD (실행 제외) ──

@router.get("/api/workflows")
async def get_workflows():
    return _load_data("workflows", [])


@router.post("/api/workflows")
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


@router.put("/api/workflows/{wf_id}")
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


@router.delete("/api/workflows/{wf_id}")
async def delete_workflow(wf_id: str):
    """워크플로우 삭제."""
    workflows = _load_data("workflows", [])
    workflows = [w for w in workflows if w.get("id") != wf_id]
    _save_data("workflows", workflows)
    return {"success": True}
