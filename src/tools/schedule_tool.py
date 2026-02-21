"""스케줄(크론) 관리 도구 — 예약 작업 생성·수정·삭제·조회.

텔레그램에서 "뉴스브리핑 평일 아침 8시반으로 바꿔" 같은 자연어를
일정보좌관 AI가 파싱하여 이 도구를 호출합니다.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.schedule_tool")

# DB 접근을 위해 web/ 경로 추가
_WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "web")


def _get_db():
    """DB 모듈을 동적 로드합니다."""
    if _WEB_DIR not in sys.path:
        sys.path.insert(0, _WEB_DIR)
    from db import load_setting, save_setting
    return load_setting, save_setting


def _load_schedules() -> list[dict]:
    load_setting, _ = _get_db()
    return load_setting("schedules") or []


def _save_schedules(schedules: list[dict]):
    _, save_setting = _get_db()
    save_setting("schedules", schedules)


class ScheduleTool(BaseTool):
    """크론 예약 관리 — 생성·수정·삭제·조회·토글."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "list")
        if action == "list":
            return self._list()
        elif action == "create":
            return self._create(kwargs)
        elif action == "update":
            return self._update(kwargs)
        elif action == "delete":
            return self._delete(kwargs)
        elif action == "toggle":
            return self._toggle(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능: list(조회), create(생성), update(수정), "
                "delete(삭제), toggle(활성화/비활성화)"
            )

    def _list(self) -> str:
        schedules = _load_schedules()
        if not schedules:
            return "등록된 예약이 없습니다."
        lines = [f"📋 예약 목록 (총 {len(schedules)}개)\n"]
        for s in schedules:
            status = "✅" if s.get("enabled") else "⏸"
            cron = s.get("cron", s.get("cron_preset", ""))
            last = s.get("last_run", "없음")
            lines.append(
                f"{status} [{s.get('id', '?')}] {s.get('name', '이름없음')}\n"
                f"   크론: {cron} | 명령: {s.get('command', '')[:50]}\n"
                f"   마지막 실행: {last}"
            )
        return "\n".join(lines)

    def _create(self, params: dict) -> str:
        schedules = _load_schedules()
        try:
            import pytz
            KST = pytz.timezone("Asia/Seoul")
        except ImportError:
            from datetime import timezone, timedelta
            KST = timezone(timedelta(hours=9))
        now = datetime.now(KST)
        schedule_id = f"sch_{now.strftime('%Y%m%d%H%M%S')}_{len(schedules)}"

        name = params.get("name", "")
        command = params.get("command", "")
        cron = params.get("cron", "")

        if not name:
            return "❌ name(예약 이름)은 필수입니다."
        if not command:
            return "❌ command(실행할 명령)는 필수입니다."
        if not cron:
            return "❌ cron(크론 표현식)은 필수입니다. 예: '30 8 * * 1-5' (평일 08:30)"

        schedule = {
            "id": schedule_id,
            "name": name,
            "command": command,
            "cron": cron,
            "cron_preset": "",
            "description": params.get("description", ""),
            "enabled": True,
            "created_at": now.isoformat(),
        }
        schedules.append(schedule)
        _save_schedules(schedules)

        return (
            f"✅ 예약 생성 완료\n"
            f"ID: {schedule_id}\n"
            f"이름: {name}\n"
            f"크론: {cron}\n"
            f"명령: {command}"
        )

    def _update(self, params: dict) -> str:
        schedule_id = params.get("schedule_id", "")
        if not schedule_id:
            return "❌ schedule_id는 필수입니다. list로 ID를 확인하세요."

        schedules = _load_schedules()
        for s in schedules:
            if s.get("id") == schedule_id:
                if "name" in params and params["name"]:
                    s["name"] = params["name"]
                if "command" in params and params["command"]:
                    s["command"] = params["command"]
                if "cron" in params and params["cron"]:
                    s["cron"] = params["cron"]
                    s["cron_preset"] = ""  # 크론 직접 지정 시 프리셋 제거
                if "description" in params:
                    s["description"] = params["description"]
                _save_schedules(schedules)
                return (
                    f"✅ 예약 수정 완료\n"
                    f"ID: {schedule_id}\n"
                    f"이름: {s.get('name')}\n"
                    f"크론: {s.get('cron')}\n"
                    f"명령: {s.get('command', '')[:50]}"
                )
        return f"❌ ID '{schedule_id}'를 찾을 수 없습니다."

    def _delete(self, params: dict) -> str:
        schedule_id = params.get("schedule_id", "")
        if not schedule_id:
            return "❌ schedule_id는 필수입니다."

        schedules = _load_schedules()
        before = len(schedules)
        schedules = [s for s in schedules if s.get("id") != schedule_id]
        if len(schedules) == before:
            return f"❌ ID '{schedule_id}'를 찾을 수 없습니다."
        _save_schedules(schedules)
        return f"✅ 예약 '{schedule_id}' 삭제 완료"

    def _toggle(self, params: dict) -> str:
        schedule_id = params.get("schedule_id", "")
        if not schedule_id:
            return "❌ schedule_id는 필수입니다."

        schedules = _load_schedules()
        for s in schedules:
            if s.get("id") == schedule_id:
                s["enabled"] = not s.get("enabled", True)
                _save_schedules(schedules)
                state = "활성화 ✅" if s["enabled"] else "비활성화 ⏸"
                return f"예약 '{s.get('name')}' → {state}"
        return f"❌ ID '{schedule_id}'를 찾을 수 없습니다."
