"""에이전트 간 협업 프로토콜 도구 — 횡적 작업 요청·정보 공유·인계."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.cross_agent_protocol")

MESSAGES_FILE = os.path.join(os.getcwd(), "data", "cross_agent_messages.json")

# ── 실시간 에이전트 호출 콜백 (mini_server.py가 시작 시 등록) ──
_call_agent_callback: Any | None = None


def register_call_agent(fn: Any) -> None:
    """mini_server.py가 서버 시작 시 _call_agent 함수를 등록합니다.

    등록된 콜백은 cross_agent_protocol의 request 액션에서
    실제 에이전트 AI를 실시간으로 호출하는 데 사용됩니다.
    """
    global _call_agent_callback
    _call_agent_callback = fn
    logger.info("cross_agent_protocol: _call_agent 콜백 등록 완료")


class CrossAgentProtocolTool(BaseTool):
    """에이전트 간 횡적 협업 프로토콜 — 작업 요청, 정보 공유, 작업 인계, 결과 수집."""

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

    def _load(self) -> list[dict]:
        if not os.path.isfile(MESSAGES_FILE):
            return []
        try:
            with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self, messages: list[dict]) -> None:
        os.makedirs(os.path.dirname(MESSAGES_FILE), exist_ok=True)
        with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

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

        messages = self._load()
        messages.append(msg)
        self._save(messages)

        logger.info("에이전트 간 요청: %s → %s (ID: %s)", from_agent, to_agent, msg["id"])

        # 실시간 에이전트 호출 (콜백이 등록된 경우)
        if _call_agent_callback is not None:
            try:
                full_task = f"{task}\n\n배경 정보: {context}" if context else task
                result = await _call_agent_callback(to_agent, full_task)
                response_text = result.get("content", "") if isinstance(result, dict) else str(result)
                # 응답을 메시지에 업데이트
                msg["response"] = response_text
                msg["status"] = "완료"
                msg["updated_at"] = datetime.now().isoformat()
                self._save(messages)
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
                self._save(messages)

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

        messages = self._load()
        messages.append(msg)
        self._save(messages)

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

        messages = self._load()
        messages.append(msg)
        self._save(messages)

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

        messages = self._load()
        if not messages:
            return "에이전트 간 메시지가 없습니다."

        if agent_id:
            messages = [m for m in messages if m.get("from") == agent_id or m.get("to") == agent_id]
        if msg_type:
            messages = [m for m in messages if m.get("type") == msg_type]

        recent = messages[-limit:]

        lines = [f"## 에이전트 간 메시지 현황 ({len(recent)}건)\n"]
        lines.append("| ID | 유형 | 발신 | 수신 | 상태 | 시간 |")
        lines.append("|-----|------|------|------|------|------|")

        for m in reversed(recent):
            ts = m.get("created_at", "")[:16]
            lines.append(
                f"| {m['id']} | {m.get('type', '')} | {m.get('from', '')} | "
                f"{m.get('to', '')} | {m.get('status', '')} | {ts} |"
            )

        # 통계
        total = len(self._load())
        pending = sum(1 for m in self._load() if m.get("status") == "대기")
        lines.append(f"\n- 총 메시지: {total}건")
        lines.append(f"- 대기 중: {pending}건")

        return "\n".join(lines)

    async def _collect(self, kwargs: dict) -> str:
        """여러 에이전트의 결과 수집·종합."""
        request_ids = kwargs.get("request_ids", [])

        if isinstance(request_ids, str):
            request_ids = [r.strip() for r in request_ids.split(",")]

        if not request_ids:
            return "수집할 요청 ID 목록(request_ids)을 입력해주세요."

        messages = self._load()
        collected: list[dict] = []

        for req_id in request_ids:
            msg = next((m for m in messages if m["id"] == req_id), None)
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
            # LLM으로 종합
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

        messages = self._load()
        msg = next((m for m in messages if m["id"] == request_id), None)
        if not msg:
            return f"요청 ID '{request_id}'를 찾을 수 없습니다."

        msg["response"] = response
        msg["status"] = "완료"
        msg["updated_at"] = datetime.now().isoformat()
        msg["responder"] = responder

        self._save(messages)

        return (
            f"## 응답 등록 완료\n\n"
            f"- 요청 ID: {request_id}\n"
            f"- 응답자: {responder}\n"
            f"- 상태: 완료"
        )
