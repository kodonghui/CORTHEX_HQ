"""작업(Task) CRUD API — 작업 목록 조회·북마크·삭제·태그·읽음 처리.

비유: 인사팀 — 에이전트에게 내려진 작업 지시를 관리하는 곳.
"""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from db import (
    list_tasks,
    get_task as db_get_task,
    update_task,
    toggle_bookmark as db_toggle_bookmark,
    delete_task as db_delete_task,
    bulk_delete_tasks,
    bulk_archive_tasks,
    set_task_tags,
    mark_task_read,
    bulk_mark_read,
)

logger = logging.getLogger("corthex")

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
async def get_tasks(keyword: str = "", status: str = "", bookmarked: bool = False,
                    limit: int = 50, archived: bool = False, tag: str = ""):
    tasks = list_tasks(keyword=keyword, status=status,
                       bookmarked=bookmarked, limit=limit,
                       archived=archived, tag=tag)
    return tasks


@router.get("/{task_id}")
async def get_task(task_id: str):
    task = db_get_task(task_id)
    if not task:
        return {"error": "not found"}
    return task


@router.post("/{task_id}/bookmark")
async def bookmark_task(task_id: str):
    new_state = db_toggle_bookmark(task_id)
    return {"bookmarked": new_state}


@router.post("/{task_id}/cancel")
async def cancel_task_api(task_id: str):
    """작업 취소 — running 상태를 failed(CEO 취소)로 변경."""
    task = db_get_task(task_id)
    if not task:
        return {"success": False, "error": "not found"}
    if task.get("status") == "running":
        update_task(task_id, status="failed",
                    result_summary="CEO 취소 (타임아웃)", success=0)
    return {"success": True}


@router.delete("/{task_id}")
async def delete_task_api(task_id: str):
    """작업 삭제."""
    db_delete_task(task_id)
    return {"success": True}


@router.put("/{task_id}/tags")
async def update_task_tags(task_id: str, request: Request):
    """작업 태그 업데이트."""
    body = await request.json()
    tags = body.get("tags", [])
    set_task_tags(task_id, tags)
    return {"success": True, "tags": tags}


@router.put("/{task_id}/read")
async def mark_task_read_api(task_id: str, request: Request):
    """작업 읽음/안읽음 표시."""
    body = await request.json()
    is_read = body.get("is_read", True)
    mark_task_read(task_id, is_read)
    return {"success": True, "is_read": is_read}


@router.post("/bulk")
async def bulk_task_action(request: Request):
    """작업 일괄 처리 (삭제/아카이브/읽음/북마크/태그 등)."""
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
    elif action == "bookmark":
        for tid in task_ids:
            db_toggle_bookmark(tid)
        return {"success": True, "action": "bookmark", "affected": len(task_ids)}
    elif action == "tag":
        tag = body.get("tag", "")
        if not tag:
            return {"success": False, "error": "태그를 입력해주세요"}
        for tid in task_ids:
            task = db_get_task(tid)
            if task:
                existing_tags = task.get("tags", [])
                if tag not in existing_tags:
                    existing_tags.append(tag)
                    set_task_tags(tid, existing_tags)
        return {"success": True, "action": "tag", "affected": len(task_ids)}
    else:
        return {"success": False, "error": f"알 수 없는 액션: {action}"}
