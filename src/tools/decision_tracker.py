"""의사결정 추적기 도구 — 의사결정 기록·추적·패턴 분석."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.decision_tracker")

DECISIONS_FILE = os.path.join(os.getcwd(), "data", "decisions.json")


class DecisionTrackerTool(BaseTool):
    """의사결정 기록·추적·패턴 분석 도구."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "list")
        if action == "record":
            return await self._record(kwargs)
        elif action == "list":
            return await self._list(kwargs)
        elif action == "detail":
            return await self._detail(kwargs)
        elif action == "update":
            return await self._update(kwargs)
        elif action == "analyze":
            return await self._analyze(kwargs)
        elif action == "timeline":
            return await self._timeline(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: record(기록), list(목록), detail(상세), "
                "update(결과 업데이트), analyze(패턴 분석), timeline(타임라인)"
            )

    def _load(self) -> list[dict]:
        if not os.path.isfile(DECISIONS_FILE):
            return []
        try:
            with open(DECISIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self, decisions: list[dict]) -> None:
        os.makedirs(os.path.dirname(DECISIONS_FILE), exist_ok=True)
        with open(DECISIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(decisions, f, ensure_ascii=False, indent=2)

    async def _record(self, kwargs: dict) -> str:
        """새 의사결정 기록."""
        title = kwargs.get("title", "")
        context = kwargs.get("context", "")
        options = kwargs.get("options", [])
        chosen = kwargs.get("chosen", "")
        reason = kwargs.get("reason", "")
        category = kwargs.get("category", "일반")
        impact = kwargs.get("impact", "중간")

        if not title:
            return (
                "의사결정 기록에 필요한 인자:\n"
                "- title: 결정 제목 (필수)\n"
                "- context: 배경/상황\n"
                "- options: 선택지 리스트\n"
                "- chosen: 선택한 것\n"
                "- reason: 선택 이유\n"
                "- category: 카테고리 (투자/기술/법률/마케팅/사업/일반)\n"
                "- impact: 영향도 (높음/중간/낮음)"
            )

        if isinstance(options, str):
            try:
                options = json.loads(options)
            except Exception:
                options = [o.strip() for o in options.split(",")]

        decision = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "context": context,
            "options": options,
            "chosen": chosen,
            "reason": reason,
            "category": category,
            "impact": impact,
            "status": "결정됨",
            "result": "",
            "created_at": datetime.now().isoformat(),
            "updated_at": "",
        }

        decisions = self._load()
        decisions.append(decision)
        self._save(decisions)

        logger.info("의사결정 기록: %s (ID: %s)", title, decision["id"])
        return (
            f"## 의사결정 기록 완료\n\n"
            f"| 항목 | 내용 |\n|------|------|\n"
            f"| ID | {decision['id']} |\n"
            f"| 제목 | {title} |\n"
            f"| 카테고리 | {category} |\n"
            f"| 영향도 | {impact} |\n"
            f"| 선택 | {chosen} |\n"
            f"| 이유 | {reason} |\n"
            f"| 상태 | 결정됨 |\n"
        )

    async def _list(self, kwargs: dict) -> str:
        """의사결정 목록."""
        category = kwargs.get("category", "")
        status = kwargs.get("status", "")
        limit = int(kwargs.get("limit", 20))

        decisions = self._load()
        if not decisions:
            return "기록된 의사결정이 없습니다."

        if category:
            decisions = [d for d in decisions if d.get("category") == category]
        if status:
            decisions = [d for d in decisions if d.get("status") == status]

        recent = decisions[-limit:]

        lines = [f"## 의사결정 목록 ({len(recent)}건)\n"]
        lines.append("| ID | 날짜 | 카테고리 | 제목 | 상태 |")
        lines.append("|-----|------|---------|------|------|")

        for d in reversed(recent):
            date = d.get("created_at", "")[:10]
            lines.append(
                f"| {d['id']} | {date} | {d.get('category', '')} | "
                f"{d.get('title', '')} | {d.get('status', '')} |"
            )

        return "\n".join(lines)

    async def _detail(self, kwargs: dict) -> str:
        """특정 의사결정 상세 조회."""
        decision_id = kwargs.get("id", "")
        if not decision_id:
            return "의사결정 ID를 입력해주세요."

        decisions = self._load()
        decision = next((d for d in decisions if d["id"] == decision_id), None)
        if not decision:
            return f"ID '{decision_id}'에 해당하는 의사결정을 찾을 수 없습니다."

        options_str = "\n".join(f"  - {o}" for o in decision.get("options", []))

        return (
            f"## 의사결정 상세\n\n"
            f"| 항목 | 내용 |\n|------|------|\n"
            f"| ID | {decision['id']} |\n"
            f"| 제목 | {decision['title']} |\n"
            f"| 카테고리 | {decision.get('category', '')} |\n"
            f"| 영향도 | {decision.get('impact', '')} |\n"
            f"| 상태 | {decision.get('status', '')} |\n"
            f"| 기록 일시 | {decision.get('created_at', '')} |\n"
            f"| 업데이트 | {decision.get('updated_at', '-')} |\n\n"
            f"### 배경\n{decision.get('context', '-')}\n\n"
            f"### 선택지\n{options_str or '-'}\n\n"
            f"### 선택\n{decision.get('chosen', '-')}\n\n"
            f"### 이유\n{decision.get('reason', '-')}\n\n"
            f"### 결과\n{decision.get('result', '아직 업데이트되지 않음')}"
        )

    async def _update(self, kwargs: dict) -> str:
        """의사결정 결과/상태 업데이트."""
        decision_id = kwargs.get("id", "")
        result = kwargs.get("result", "")
        status = kwargs.get("status", "")

        if not decision_id:
            return "의사결정 ID를 입력해주세요."

        decisions = self._load()
        decision = next((d for d in decisions if d["id"] == decision_id), None)
        if not decision:
            return f"ID '{decision_id}'에 해당하는 의사결정을 찾을 수 없습니다."

        if result:
            decision["result"] = result
        if status:
            decision["status"] = status
        decision["updated_at"] = datetime.now().isoformat()

        self._save(decisions)
        return (
            f"## 의사결정 업데이트 완료\n\n"
            f"- ID: {decision_id}\n"
            f"- 제목: {decision['title']}\n"
            f"- 상태: {decision.get('status', '')}\n"
            f"- 결과: {result or '변경 없음'}"
        )

    async def _analyze(self, kwargs: dict) -> str:
        """의사결정 패턴 분석."""
        decisions = self._load()
        if len(decisions) < 3:
            return "분석하기에 충분한 의사결정 기록이 없습니다 (최소 3건 필요)."

        # 통계 정리
        categories: dict[str, int] = {}
        statuses: dict[str, int] = {}
        impacts: dict[str, int] = {}

        for d in decisions:
            cat = d.get("category", "일반")
            categories[cat] = categories.get(cat, 0) + 1
            st = d.get("status", "결정됨")
            statuses[st] = statuses.get(st, 0) + 1
            imp = d.get("impact", "중간")
            impacts[imp] = impacts.get(imp, 0) + 1

        stats = (
            f"## 의사결정 통계\n\n"
            f"- 총 기록 수: {len(decisions)}건\n\n"
            f"### 카테고리별\n"
            + "\n".join(f"- {k}: {v}건" for k, v in sorted(categories.items(), key=lambda x: -x[1]))
            + f"\n\n### 상태별\n"
            + "\n".join(f"- {k}: {v}건" for k, v in statuses.items())
            + f"\n\n### 영향도별\n"
            + "\n".join(f"- {k}: {v}건" for k, v in impacts.items())
        )

        # LLM 패턴 분석
        summaries = "\n".join(
            f"- [{d['id']}] {d.get('created_at', '')[:10]} | {d.get('category', '')} | "
            f"{d['title']} → {d.get('chosen', '')} (이유: {d.get('reason', '')[:50]})"
            for d in decisions[-20:]
        )

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 의사결정 분석 전문가입니다. "
                "의사결정 기록을 분석하여 패턴, 경향, 개선점을 한국어로 제시하세요.\n"
                "1. 결정 패턴 (어떤 분야에서 자주 결정하는지)\n"
                "2. 의사결정 스타일 분석\n"
                "3. 개선 제안"
            ),
            user_prompt=f"{stats}\n\n### 최근 의사결정 요약\n{summaries}",
        )

        return f"{stats}\n\n---\n\n### 패턴 분석\n\n{analysis}"

    async def _timeline(self, kwargs: dict) -> str:
        """시간순 의사결정 타임라인."""
        limit = int(kwargs.get("limit", 30))
        decisions = self._load()

        if not decisions:
            return "기록된 의사결정이 없습니다."

        # 시간순 정렬
        sorted_decisions = sorted(decisions, key=lambda x: x.get("created_at", ""))
        recent = sorted_decisions[-limit:]

        lines = [f"## 의사결정 타임라인 (최근 {len(recent)}건)\n"]
        current_month = ""

        for d in recent:
            date = d.get("created_at", "")[:10]
            month = date[:7]
            if month != current_month:
                current_month = month
                lines.append(f"\n### {month}")

            impact_icon = {"높음": "🔴", "중간": "🟡", "낮음": "🟢"}.get(d.get("impact", ""), "⚪")
            status_icon = {"결정됨": "✅", "보류": "⏸️", "취소": "❌", "진행중": "🔄"}.get(d.get("status", ""), "")

            lines.append(
                f"- {impact_icon} **{date}** [{d.get('category', '')}] "
                f"{d['title']} → {d.get('chosen', '')} {status_icon}"
            )

        return "\n".join(lines)
