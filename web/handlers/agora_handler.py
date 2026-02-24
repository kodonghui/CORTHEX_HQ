"""AGORA AI 법학 토론 시스템 API.

비유: 법정 — 찬반 양측이 쟁점별로 라운드를 나누어 토론하고,
      서기관이 논문을 실시간 갱신하며, 방청석에서 실시간 중계를 보는 곳.
"""
import asyncio
import json
import logging
import sys
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import (
    agora_create_session,
    agora_get_session,
    agora_update_session,
    agora_get_issues,
    agora_get_rounds,
    agora_get_paper_latest,
    agora_get_paper_diff,
    agora_get_paper_versions,
    agora_get_book,
    agora_save_paper_version,
)

logger = logging.getLogger("agora")

router = APIRouter(tags=["agora"])

# ── AGORA 전용 SSE 큐 관리 ──
_agora_sse_queues: list[asyncio.Queue] = []


def agora_broadcast(event: dict):
    """토론 이벤트를 연결된 모든 SSE 클라이언트에 전송."""
    for q in _agora_sse_queues:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


# ── 토론 시작 ──

@router.post("/api/agora/start")
async def start_debate(request: Request):
    """토론 시작 — 세션 생성 후 백그라운드에서 토론 엔진을 구동합니다.

    body: {title, paper_text}
    반환: {session_id}
    """
    try:
        from agora_engine import agora_engine

        body = await request.json()
        title = body.get("title", "")
        paper_text = body.get("paper_text", "")

        if not title or not paper_text:
            return JSONResponse(
                {"success": False, "error": "title과 paper_text는 필수입니다."},
                status_code=400,
            )

        # DB 세션 생성
        session_id = agora_create_session(title, paper_text)
        # 논문 v0 저장
        agora_save_paper_version(session_id, 0, paper_text)
        # 백그라운드로 토론 시작
        asyncio.create_task(agora_engine.start_debate(session_id))

        logger.info("AGORA 토론 시작: session=%s title=%s", session_id, title)
        agora_broadcast({"type": "session_started", "session_id": session_id, "title": title})

        return JSONResponse({"success": True, "session_id": session_id})
    except Exception as e:
        logger.error("AGORA 토론 시작 실패: %s", e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── 일시정지 ──

@router.post("/api/agora/pause")
async def pause_debate(request: Request):
    """토론 일시정지.

    body: {session_id}
    """
    try:
        from agora_engine import agora_engine

        body = await request.json()
        session_id = body.get("session_id", "")

        if not session_id:
            return JSONResponse(
                {"success": False, "error": "session_id는 필수입니다."},
                status_code=400,
            )

        agora_engine.pause(session_id)
        agora_update_session(session_id, status="paused")

        logger.info("AGORA 토론 일시정지: session=%s", session_id)
        agora_broadcast({"type": "session_paused", "session_id": session_id})

        return JSONResponse({"success": True, "session_id": session_id, "status": "paused"})
    except Exception as e:
        logger.error("AGORA 일시정지 실패: %s", e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── 재개 ──

@router.post("/api/agora/resume")
async def resume_debate(request: Request):
    """토론 재개.

    body: {session_id}
    """
    try:
        from agora_engine import agora_engine

        body = await request.json()
        session_id = body.get("session_id", "")

        if not session_id:
            return JSONResponse(
                {"success": False, "error": "session_id는 필수입니다."},
                status_code=400,
            )

        agora_engine.resume(session_id)
        agora_update_session(session_id, status="running")

        logger.info("AGORA 토론 재개: session=%s", session_id)
        agora_broadcast({"type": "session_resumed", "session_id": session_id})

        return JSONResponse({"success": True, "session_id": session_id, "status": "running"})
    except Exception as e:
        logger.error("AGORA 재개 실패: %s", e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── 상태 조회 ──

@router.get("/api/agora/status")
async def get_debate_status(session_id: str = ""):
    """현재 토론 세션 상태 + 비용 조회.

    query: ?session_id=xxx
    """
    try:
        if not session_id:
            return JSONResponse(
                {"success": False, "error": "session_id는 필수입니다."},
                status_code=400,
            )

        session = agora_get_session(session_id)
        if not session:
            return JSONResponse(
                {"success": False, "error": "세션을 찾을 수 없습니다."},
                status_code=404,
            )

        return JSONResponse({"success": True, "session": session})
    except Exception as e:
        logger.error("AGORA 상태 조회 실패: %s", e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── 쟁점 트리 ──

@router.get("/api/agora/issues")
async def get_issues(session_id: str = ""):
    """쟁점 트리 조회 — 토론에서 도출된 모든 쟁점과 하위 쟁점.

    query: ?session_id=xxx
    """
    try:
        if not session_id:
            return JSONResponse(
                {"success": False, "error": "session_id는 필수입니다."},
                status_code=400,
            )

        issues = agora_get_issues(session_id)
        return JSONResponse({"success": True, "issues": issues})
    except Exception as e:
        logger.error("AGORA 쟁점 조회 실패: %s", e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── 특정 쟁점의 라운드 목록 ──

@router.get("/api/agora/rounds/{issue_id}")
async def get_rounds(issue_id: str):
    """특정 쟁점의 토론 라운드 목록 — 찬반 발언 순서대로."""
    try:
        if not issue_id:
            return JSONResponse(
                {"success": False, "error": "issue_id는 필수입니다."},
                status_code=400,
            )

        rounds = agora_get_rounds(issue_id)
        return JSONResponse({"success": True, "rounds": rounds})
    except Exception as e:
        logger.error("AGORA 라운드 조회 실패: %s", e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── 최신 논문 전문 ──

@router.get("/api/agora/paper/latest")
async def get_paper_latest(session_id: str = ""):
    """최신 논문 전문 조회 — 토론 결과가 반영된 최종 버전.

    query: ?session_id=xxx
    """
    try:
        if not session_id:
            return JSONResponse(
                {"success": False, "error": "session_id는 필수입니다."},
                status_code=400,
            )

        paper = agora_get_paper_latest(session_id)
        if not paper:
            return JSONResponse(
                {"success": False, "error": "논문을 찾을 수 없습니다."},
                status_code=404,
            )

        return JSONResponse({"success": True, "paper": paper})
    except Exception as e:
        logger.error("AGORA 논문 조회 실패: %s", e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── 특정 버전 diff HTML ──

@router.get("/api/agora/paper/diff/{version_id}")
async def get_paper_diff(version_id: str):
    """특정 논문 버전의 diff HTML — 이전 버전 대비 변경사항 표시."""
    try:
        if not version_id:
            return JSONResponse(
                {"success": False, "error": "version_id는 필수입니다."},
                status_code=400,
            )

        diff = agora_get_paper_diff(version_id)
        if not diff:
            return JSONResponse(
                {"success": False, "error": "해당 버전의 diff를 찾을 수 없습니다."},
                status_code=404,
            )

        return JSONResponse({"success": True, "diff": diff})
    except Exception as e:
        logger.error("AGORA 논문 diff 조회 실패: %s", e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── 대화록 전체 ──

@router.get("/api/agora/book")
async def get_debate_book(session_id: str = ""):
    """대화록 전체 조회 — 토론의 전체 기록을 순서대로 반환.

    query: ?session_id=xxx
    """
    try:
        if not session_id:
            return JSONResponse(
                {"success": False, "error": "session_id는 필수입니다."},
                status_code=400,
            )

        book = agora_get_book(session_id)
        return JSONResponse({"success": True, "book": book})
    except Exception as e:
        logger.error("AGORA 대화록 조회 실패: %s", e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── SSE 실시간 토론 스트림 ──

@router.get("/api/agora/stream")
async def agora_stream():
    """SSE(Server-Sent Events) 실시간 토론 스트림.
    프론트엔드에서 EventSource('/api/agora/stream')로 연결.
    토론 진행 상황, 발언, 쟁점 갱신 등을 실시간으로 push.
    """
    queue: asyncio.Queue = asyncio.Queue()
    _agora_sse_queues.append(queue)

    async def event_generator():
        try:
            # 연결 확인 이벤트
            yield f"event: connected\ndata: {json.dumps({'status': 'ok'})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: agora\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # keepalive — 30초마다 ping
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in _agora_sse_queues:
                _agora_sse_queues.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
