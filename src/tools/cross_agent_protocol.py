"""에이전트 간 협업 프로토콜 도구 — 횡적 작업 요청·정보 공유·인계."""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.cross_agent_protocol")

# ── 실시간 에이전트 호출 콜백 (mini_server.py가 시작 시 등록) ──
_call_agent_callback: Any | None = None
# ── SSE broadcast 콜백 (내부통신 실시간 스트림) ──
_sse_broadcast_callback: Any | None = None
# ── 유효한 에이전트 ID 목록 (mini_server.py 시작 시 등록) ──
_valid_agent_ids: set[str] = set()

# AI가 흔히 지어내는 가짜 이름 → 실제 에이전트 ID 매핑
_AGENT_ALIAS: dict[str, str] = {
    # CIO 소속 전문가 — AI가 자주 줄여서 씀
    "risk_manager": "risk_management_specialist",
    "risk_analyst": "risk_management_specialist",
    "risk_specialist": "risk_management_specialist",
    "fundamental_analyst": "stock_analysis_specialist",
    "stock_analyst": "stock_analysis_specialist",
    "equity_analyst": "stock_analysis_specialist",
    "macro_analyst": "market_condition_specialist",
    "market_analyst": "market_condition_specialist",
    "market_specialist": "market_condition_specialist",
    "technical_analyst": "technical_analysis_specialist",
    "chart_analyst": "technical_analysis_specialist",
    # 기타 부서 — AI가 줄여 쓸 수 있는 패턴
    "frontend_developer": "frontend_specialist",
    "backend_developer": "backend_specialist",
    "patent_lawyer": "patent_specialist",
    "copyright_lawyer": "copyright_specialist",
    "market_researcher": "market_research_specialist",
    "content_creator": "content_specialist",
    "community_manager": "community_specialist",
}


def register_valid_agents(agent_ids: list[str]) -> None:
    """mini_server.py가 서버 시작 시 유효한 에이전트 ID 목록을 등록합니다."""
    global _valid_agent_ids
    _valid_agent_ids = set(agent_ids)
    logger.info("cross_agent_protocol: 유효 에이전트 %d개 등록", len(_valid_agent_ids))


def _resolve_agent_id(raw_id: str) -> str:
    """AI가 보낸 에이전트 ID를 실제 유효한 ID로 변환합니다.

    1) 이미 유효한 ID → 그대로 반환
    2) 별칭(alias) 테이블에 있음 → 매핑된 ID 반환
    3) 부분 문자열 매칭 — raw_id가 실제 ID의 일부를 포함하면 반환
    4) 어디에도 없으면 → 원본 반환 (caller가 에러 처리)
    """
    if not _valid_agent_ids:
        return raw_id  # 목록 미등록 시 검증 생략

    # 1) 정확 일치
    if raw_id in _valid_agent_ids:
        return raw_id

    # 2) 별칭 테이블
    alias_resolved = _AGENT_ALIAS.get(raw_id)
    if alias_resolved and alias_resolved in _valid_agent_ids:
        logger.info("에이전트 ID 별칭 매핑: %s → %s", raw_id, alias_resolved)
        return alias_resolved

    # 3) 부분 문자열 매칭 — raw_id의 핵심 단어가 실제 ID에 포함되는지
    raw_parts = raw_id.replace("_", " ").split()
    best_match = None
    best_score = 0
    for valid_id in _valid_agent_ids:
        score = sum(1 for part in raw_parts if part in valid_id)
        if score > best_score:
            best_score = score
            best_match = valid_id
    if best_match and best_score >= 1:
        logger.info("에이전트 ID 퍼지 매핑: %s → %s (score=%d)", raw_id, best_match, best_score)
        return best_match

    return raw_id


def register_call_agent(fn: Any) -> None:
    """mini_server.py가 서버 시작 시 _call_agent 함수를 등록합니다.

    등록된 콜백은 cross_agent_protocol의 request 액션에서
    실제 에이전트 AI를 실시간으로 호출하는 데 사용됩니다.
    """
    global _call_agent_callback
    _call_agent_callback = fn
    logger.info("cross_agent_protocol: _call_agent 콜백 등록 완료")


def register_sse_broadcast(fn: Any) -> None:
    """mini_server.py가 서버 시작 시 SSE broadcast 함수를 등록합니다.
    P2P 메시지 저장 시 내부통신 패널에 실시간 push됩니다.
    """
    global _sse_broadcast_callback
    _sse_broadcast_callback = fn
    logger.info("cross_agent_protocol: SSE broadcast 콜백 등록 완료")


def _get_conn() -> sqlite3.Connection:
    """DB 연결 — cross_agent_messages 테이블 자동 생성."""
    try:
        from db import get_connection  # 서버 환경 (web/ 기준)
    except ImportError:
        from web.db import get_connection  # 로컬 환경
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cross_agent_messages (
            id TEXT PRIMARY KEY,
            msg_type TEXT NOT NULL,
            from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL,
            data TEXT NOT NULL,
            status TEXT DEFAULT '대기',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


class CrossAgentProtocolTool(BaseTool):
    """에이전트 간 횡적 협업 프로토콜 — 작업 요청, 정보 공유, 작업 인계, 결과 수집."""

    def _save_msg(self, msg: dict) -> None:
        """새 메시지를 DB에 저장 + SSE broadcast."""
        try:
            conn = _get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO cross_agent_messages "
                "(id, msg_type, from_agent, to_agent, data, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    msg["id"],
                    msg.get("type", "request"),
                    msg.get("from", "unknown"),
                    msg.get("to", ""),
                    json.dumps(msg, ensure_ascii=False),
                    msg.get("status", "대기"),
                    msg.get("created_at", datetime.now().isoformat()),
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("cross_agent_protocol DB 저장 실패: %s", e)

        # SSE broadcast — 내부통신 패널에 실시간 push
        if _sse_broadcast_callback is not None:
            try:
                import asyncio
                sse_data = {
                    "id": f"ca_{msg['id']}",
                    "sender": msg.get("from", "unknown"),
                    "receiver": msg.get("to", ""),
                    "message": msg.get("task", msg.get("message", msg.get("next_task", ""))),
                    "log_type": msg.get("type", "p2p"),
                    "source": "cross_agent",
                    "status": msg.get("status", "대기"),
                    "created_at": msg.get("created_at", datetime.now().isoformat()),
                }
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(_sse_broadcast_callback(sse_data))
                else:
                    loop.run_until_complete(_sse_broadcast_callback(sse_data))
            except Exception as e:
                logger.debug("SSE broadcast 실패 (무시 가능): %s", e)

    def _update_msg(self, msg: dict) -> None:
        """기존 메시지 상태/내용 업데이트."""
        try:
            conn = _get_conn()
            conn.execute(
                "UPDATE cross_agent_messages SET data=?, status=? WHERE id=?",
                (json.dumps(msg, ensure_ascii=False), msg.get("status", ""), msg["id"]),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("cross_agent_protocol DB 업데이트 실패: %s", e)

    def _load(self, limit: int = 200, agent_id: str = "", msg_type: str = "") -> list[dict]:
        """DB에서 메시지 목록 조회."""
        try:
            conn = _get_conn()
            params: list = []
            where_clauses: list[str] = []
            if agent_id:
                where_clauses.append("(from_agent=? OR to_agent=?)")
                params.extend([agent_id, agent_id])
            if msg_type:
                where_clauses.append("msg_type=?")
                params.append(msg_type)
            where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            params.append(limit)
            rows = conn.execute(
                f"SELECT data FROM cross_agent_messages {where} "
                f"ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
            conn.close()
            return [json.loads(r[0]) for r in rows]
        except Exception:
            return []

    def _find_by_id(self, msg_id: str) -> dict | None:
        """ID로 메시지 1건 조회."""
        try:
            conn = _get_conn()
            row = conn.execute(
                "SELECT data FROM cross_agent_messages WHERE id=?", (msg_id,)
            ).fetchone()
            conn.close()
            return json.loads(row[0]) if row else None
        except Exception:
            return None

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "request")
        if action == "request":
            return await self._request(kwargs)
        elif action == "broadcast":
            return await self._broadcast(kwargs)
        elif action == "handoff":
            return await self._handoff(kwargs)
        elif action == "status":
            return await self._status(kwargs)
        elif action == "collect":
            return await self._collect(kwargs)
        elif action == "respond":
            return await self._respond(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: request(작업 요청), broadcast(전체 공유), "
                "handoff(작업 인계), status(현황), collect(결과 수집), respond(응답)"
            )

    async def _request(self, kwargs: dict) -> str:
        """다른 에이전트에게 작업 요청."""
        from_agent = kwargs.get("from_agent", kwargs.get("caller_id", "unknown"))
        to_agent = kwargs.get("to_agent", "")
        task = kwargs.get("task", "")
        context = kwargs.get("context", "")
        priority = kwargs.get("priority", "보통")

        if not to_agent or not task:
            return (
                "작업 요청에 필요한 인자:\n"
                "- to_agent: 요청할 에이전트 ID\n"
                "- task: 작업 내용\n"
                "- context: 배경 정보 (선택)\n"
                "- priority: 우선순위 (긴급/높음/보통/낮음)"
            )

        msg = {
            "id": str(uuid.uuid4())[:8],
            "type": "request",
            "from": from_agent,
            "to": to_agent,
            "task": task,
            "context": context,
            "priority": priority,
            "status": "대기",
            "response": "",
            "created_at": datetime.now().isoformat(),
            "updated_at": "",
        }

        self._save_msg(msg)
        logger.info("에이전트 간 요청: %s → %s (ID: %s)", from_agent, to_agent, msg["id"])

        # 에이전트 ID 검증 + 자동 매핑 (AI가 가짜 이름 보내는 문제 방지)
        resolved_id = _resolve_agent_id(to_agent)
        if resolved_id != to_agent:
            logger.info("cross_agent_protocol: AI가 보낸 '%s' → 실제 ID '%s'로 변환", to_agent, resolved_id)
            msg["to"] = resolved_id  # DB 기록도 실제 ID로
            msg["original_to"] = to_agent  # 원본 보존
            to_agent = resolved_id

        # 실시간 에이전트 호출 (콜백이 등록된 경우)
        if _call_agent_callback is not None:
            try:
                full_task = f"{task}\n\n배경 정보: {context}" if context else task
                result = await _call_agent_callback(to_agent, full_task)
                response_text = result.get("content", "") if isinstance(result, dict) else str(result)
                msg["response"] = response_text
                msg["status"] = "완료"
                msg["updated_at"] = datetime.now().isoformat()
                self._update_msg(msg)
                logger.info("실시간 요청 완료: %s → %s", from_agent, to_agent)
                return (
                    f"## 에이전트 간 실시간 요청 완료\n\n"
                    f"**{from_agent} → {to_agent}**\n\n"
                    f"**{to_agent}의 응답:**\n\n{response_text}"
                )
            except Exception as e:
                logger.error("실시간 에이전트 호출 실패: %s", e)
                msg["status"] = "실패"
                msg["updated_at"] = datetime.now().isoformat()
                self._update_msg(msg)

        return (
            f"## 작업 요청 전송 완료\n\n"
            f"| 항목 | 내용 |\n|------|------|\n"
            f"| 요청 ID | {msg['id']} |\n"
            f"| 발신 | {from_agent} |\n"
            f"| 수신 | {to_agent} |\n"
            f"| 우선순위 | {priority} |\n"
            f"| 작업 | {task} |\n"
            f"| 상태 | 대기 |\n"
        )

    async def _broadcast(self, kwargs: dict) -> str:
        """전체 에이전트에게 정보 공유."""
        from_agent = kwargs.get("from_agent", kwargs.get("caller_id", "unknown"))
        message = kwargs.get("message", "")
        tags = kwargs.get("tags", [])

        if not message:
            return "공유할 메시지(message)를 입력해주세요."

        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]

        msg = {
            "id": str(uuid.uuid4())[:8],
            "type": "broadcast",
            "from": from_agent,
            "to": "all",
            "message": message,
            "tags": tags,
            "status": "전달됨",
            "created_at": datetime.now().isoformat(),
        }

        self._save_msg(msg)

        tags_str = ", ".join(tags) if tags else "없음"
        return (
            f"## 전체 공유 완료\n\n"
            f"- 발신: {from_agent}\n"
            f"- 메시지 ID: {msg['id']}\n"
            f"- 태그: {tags_str}\n"
            f"- 내용: {message[:200]}"
        )

    async def _handoff(self, kwargs: dict) -> str:
        """현재 작업을 다른 에이전트에게 인계."""
        from_agent = kwargs.get("from_agent", kwargs.get("caller_id", "unknown"))
        to_agent = kwargs.get("to_agent", "")
        current_result = kwargs.get("current_result", "")
        next_task = kwargs.get("next_task", "")

        if not to_agent or not next_task:
            return (
                "작업 인계에 필요한 인자:\n"
                "- to_agent: 인계할 에이전트 ID\n"
                "- current_result: 현재까지의 작업 결과\n"
                "- next_task: 다음에 해야 할 작업"
            )

        msg = {
            "id": str(uuid.uuid4())[:8],
            "type": "handoff",
            "from": from_agent,
            "to": to_agent,
            "current_result": current_result,
            "next_task": next_task,
            "status": "인계됨",
            "response": "",
            "created_at": datetime.now().isoformat(),
        }

        self._save_msg(msg)

        return (
            f"## 작업 인계 완료\n\n"
            f"| 항목 | 내용 |\n|------|------|\n"
            f"| 인계 ID | {msg['id']} |\n"
            f"| 인계자 | {from_agent} |\n"
            f"| 수신자 | {to_agent} |\n"
            f"| 다음 작업 | {next_task} |\n"
        )

    async def _status(self, kwargs: dict) -> str:
        """에이전트 간 메시지 현황."""
        agent_id = kwargs.get("agent_id", "")
        msg_type = kwargs.get("type", "")
        limit = int(kwargs.get("limit", 20))

        messages = self._load(limit=limit, agent_id=agent_id, msg_type=msg_type)
        if not messages:
            return "에이전트 간 메시지가 없습니다."

        lines = [f"## 에이전트 간 메시지 현황 ({len(messages)}건)\n"]
        lines.append("| ID | 유형 | 발신 | 수신 | 상태 | 시간 |")
        lines.append("|-----|------|------|------|------|------|")

        for m in messages:
            ts = m.get("created_at", "")[:16]
            lines.append(
                f"| {m['id']} | {m.get('type', '')} | {m.get('from', '')} | "
                f"{m.get('to', '')} | {m.get('status', '')} | {ts} |"
            )

        try:
            conn = _get_conn()
            total = conn.execute("SELECT COUNT(*) FROM cross_agent_messages").fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM cross_agent_messages WHERE status='대기'"
            ).fetchone()[0]
            conn.close()
            lines.append(f"\n- 총 메시지: {total}건")
            lines.append(f"- 대기 중: {pending}건")
        except Exception:
            pass

        return "\n".join(lines)

    async def _collect(self, kwargs: dict) -> str:
        """여러 에이전트의 결과 수집·종합."""
        request_ids = kwargs.get("request_ids", [])

        if isinstance(request_ids, str):
            request_ids = [r.strip() for r in request_ids.split(",")]

        if not request_ids:
            return "수집할 요청 ID 목록(request_ids)을 입력해주세요."

        collected: list[dict] = []
        for req_id in request_ids:
            msg = self._find_by_id(req_id)
            if msg:
                collected.append(msg)

        if not collected:
            return "해당 ID의 메시지를 찾을 수 없습니다."

        lines = ["## 결과 수집\n"]
        context_parts: list[str] = []
        for m in collected:
            status = m.get("status", "")
            response = m.get("response", "응답 없음")
            lines.append(f"### [{m['id']}] {m.get('from', '')} → {m.get('to', '')} ({status})")
            lines.append(f"- 작업: {m.get('task', m.get('next_task', ''))}")
            lines.append(f"- 응답: {response[:300]}\n")
            if response:
                context_parts.append(response)

        if context_parts:
            synthesis = await self._llm_call(
                system_prompt=(
                    "당신은 다양한 부서의 보고를 종합하는 전문가입니다. "
                    "각 에이전트의 결과를 종합하여 핵심 인사이트를 한국어로 정리하세요."
                ),
                user_prompt="\n\n---\n\n".join(context_parts),
            )
            lines.append(f"\n---\n\n### 종합 분석\n\n{synthesis}")

        return "\n".join(lines)

    async def _respond(self, kwargs: dict) -> str:
        """요청에 대한 응답 등록."""
        request_id = kwargs.get("request_id", "")
        response = kwargs.get("response", "")
        responder = kwargs.get("responder", kwargs.get("caller_id", "unknown"))

        if not request_id or not response:
            return "요청 ID(request_id)와 응답 내용(response)을 입력해주세요."

        msg = self._find_by_id(request_id)
        if not msg:
            return f"요청 ID '{request_id}'를 찾을 수 없습니다."

        msg["response"] = response
        msg["status"] = "완료"
        msg["updated_at"] = datetime.now().isoformat()
        msg["responder"] = responder

        self._update_msg(msg)

        return (
            f"## 응답 등록 완료\n\n"
            f"- 요청 ID: {request_id}\n"
            f"- 응답자: {responder}\n"
            f"- 상태: 완료"
        )
