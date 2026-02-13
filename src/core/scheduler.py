"""
작업 예약 엔진.

asyncio 기반으로 30초마다 체크하여 예약된 작업을 자동 실행합니다.
설정은 config/schedules.yaml에 저장됩니다.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from src.core.orchestrator import Orchestrator
    from src.core.task_store import TaskStore
    from src.llm.router import ModelRouter
    from web.ws_manager import ConnectionManager

logger = logging.getLogger("corthex.scheduler")

# 한국어 cron 프리셋 → (hour, minute, weekday | None)
CRON_PRESETS = {
    "매일 오전 9시": {"hour": 9, "minute": 0, "weekday": None, "interval_type": "daily"},
    "매일 오후 6시": {"hour": 18, "minute": 0, "weekday": None, "interval_type": "daily"},
    "매주 월요일 오전 10시": {"hour": 10, "minute": 0, "weekday": 0, "interval_type": "weekly"},
    "매주 금요일 오후 5시": {"hour": 17, "minute": 0, "weekday": 4, "interval_type": "weekly"},
    "매시간": {"hour": None, "minute": 0, "weekday": None, "interval_type": "hourly"},
    "30분마다": {"hour": None, "minute": None, "weekday": None, "interval_type": "every_30min"},
}


class ScheduleEntry:
    """하나의 예약 작업."""

    def __init__(
        self,
        schedule_id: str,
        name: str,
        command: str,
        cron_preset: str,
        enabled: bool = True,
        last_run: str | None = None,
        next_run: str | None = None,
        run_count: int = 0,
    ) -> None:
        self.schedule_id = schedule_id
        self.name = name
        self.command = command
        self.cron_preset = cron_preset
        self.enabled = enabled
        self.last_run = last_run
        self.next_run = next_run
        self.run_count = run_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "name": self.name,
            "command": self.command,
            "cron_preset": self.cron_preset,
            "enabled": self.enabled,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScheduleEntry:
        return cls(
            schedule_id=d.get("schedule_id", str(uuid.uuid4())[:8]),
            name=d.get("name", ""),
            command=d.get("command", ""),
            cron_preset=d.get("cron_preset", ""),
            enabled=d.get("enabled", True),
            last_run=d.get("last_run"),
            next_run=d.get("next_run"),
            run_count=d.get("run_count", 0),
        )

    def compute_next_run(self) -> Optional[str]:
        """다음 실행 시간을 계산합니다 (KST 기준)."""
        import zoneinfo
        try:
            kst = zoneinfo.ZoneInfo("Asia/Seoul")
        except Exception:
            # fallback: UTC+9
            kst = timezone(timedelta(hours=9))

        now = datetime.now(kst)
        preset = CRON_PRESETS.get(self.cron_preset)
        if not preset:
            return None

        interval_type = preset["interval_type"]

        if interval_type == "every_30min":
            # 다음 30분 경계
            if now.minute < 30:
                nxt = now.replace(minute=30, second=0, microsecond=0)
            else:
                nxt = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        elif interval_type == "hourly":
            minute = preset["minute"] or 0
            nxt = now.replace(minute=minute, second=0, microsecond=0)
            if nxt <= now:
                nxt += timedelta(hours=1)
        elif interval_type == "daily":
            hour = preset["hour"] or 0
            minute = preset["minute"] or 0
            nxt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if nxt <= now:
                nxt += timedelta(days=1)
        elif interval_type == "weekly":
            hour = preset["hour"] or 0
            minute = preset["minute"] or 0
            weekday = preset["weekday"] or 0
            days_ahead = weekday - now.weekday()
            if days_ahead < 0:
                days_ahead += 7
            nxt = (now + timedelta(days=days_ahead)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            if nxt <= now:
                nxt += timedelta(weeks=1)
        else:
            return None

        self.next_run = nxt.isoformat()
        return self.next_run

    def should_run_now(self) -> bool:
        """현재 시간에 실행해야 하는지 확인합니다."""
        if not self.enabled or not self.next_run:
            return False
        try:
            import zoneinfo
            try:
                kst = zoneinfo.ZoneInfo("Asia/Seoul")
            except Exception:
                kst = timezone(timedelta(hours=9))
            now = datetime.now(kst)
            next_dt = datetime.fromisoformat(self.next_run)
            # next_run 시각이 현재보다 과거이면 실행
            return now >= next_dt
        except Exception:
            return False


class Scheduler:
    """asyncio 기반 작업 예약 엔진."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._schedules: list[ScheduleEntry] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._load()

    def _load(self) -> None:
        """YAML에서 예약 목록을 로드합니다."""
        if not self._config_path.exists():
            self._schedules = []
            return
        try:
            raw = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))
            items = raw.get("schedules", []) if raw else []
            self._schedules = [ScheduleEntry.from_dict(d) for d in items]
            # 다음 실행 시간 계산
            for s in self._schedules:
                if s.enabled and not s.next_run:
                    s.compute_next_run()
        except Exception as e:
            logger.warning("예약 설정 로드 실패: %s", e)
            self._schedules = []

    def _save(self) -> None:
        """예약 목록을 YAML에 저장합니다."""
        data = {"schedules": [s.to_dict() for s in self._schedules]}
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    def list_all(self) -> list[dict]:
        return [s.to_dict() for s in self._schedules]

    def add(self, name: str, command: str, cron_preset: str) -> dict:
        """새 예약을 추가합니다."""
        entry = ScheduleEntry(
            schedule_id=str(uuid.uuid4())[:8],
            name=name,
            command=command,
            cron_preset=cron_preset,
        )
        entry.compute_next_run()
        self._schedules.append(entry)
        self._save()
        logger.info("예약 추가: %s (%s)", name, cron_preset)
        return entry.to_dict()

    def update(self, schedule_id: str, data: dict) -> Optional[dict]:
        """예약을 수정합니다."""
        for s in self._schedules:
            if s.schedule_id == schedule_id:
                if "name" in data:
                    s.name = data["name"]
                if "command" in data:
                    s.command = data["command"]
                if "cron_preset" in data:
                    s.cron_preset = data["cron_preset"]
                if "enabled" in data:
                    s.enabled = data["enabled"]
                s.compute_next_run()
                self._save()
                return s.to_dict()
        return None

    def delete(self, schedule_id: str) -> bool:
        """예약을 삭제합니다."""
        before = len(self._schedules)
        self._schedules = [s for s in self._schedules if s.schedule_id != schedule_id]
        if len(self._schedules) < before:
            self._save()
            return True
        return False

    def toggle(self, schedule_id: str) -> Optional[dict]:
        """예약 활성화/비활성화를 토글합니다."""
        for s in self._schedules:
            if s.schedule_id == schedule_id:
                s.enabled = not s.enabled
                if s.enabled:
                    s.compute_next_run()
                self._save()
                return s.to_dict()
        return None

    def start(
        self,
        orchestrator: Orchestrator,
        ws_manager: ConnectionManager,
        task_store: TaskStore,
        model_router: ModelRouter,
    ) -> None:
        """백그라운드 체크 루프를 시작합니다."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._check_loop(orchestrator, ws_manager, task_store, model_router)
        )
        logger.info("스케줄러 시작 (예약 %d개)", len(self._schedules))

    def stop(self) -> None:
        """백그라운드 루프를 중지합니다."""
        self._running = False
        if self._task:
            self._task.cancel()

    async def _check_loop(
        self,
        orchestrator: Orchestrator,
        ws_manager: ConnectionManager,
        task_store: TaskStore,
        model_router: ModelRouter,
    ) -> None:
        """30초마다 예약을 확인하고 실행합니다."""
        while self._running:
            try:
                await self._check_and_run(orchestrator, ws_manager, task_store, model_router)
            except Exception as e:
                logger.error("스케줄러 체크 오류: %s", e)
            await asyncio.sleep(30)

    async def _check_and_run(
        self,
        orchestrator: Orchestrator,
        ws_manager: ConnectionManager,
        task_store: TaskStore,
        model_router: ModelRouter,
    ) -> None:
        """실행할 예약이 있는지 확인하고 실행합니다."""
        for schedule in self._schedules:
            if not schedule.should_run_now():
                continue

            logger.info("예약 실행: %s (%s)", schedule.name, schedule.command)

            # 작업 생성
            stored = task_store.create(f"[예약] {schedule.command}")
            stored.status = __import__("src.core.task_store", fromlist=["TaskStatus"]).TaskStatus.RUNNING
            stored.started_at = datetime.now(timezone.utc)

            start_cost = model_router.cost_tracker.total_cost
            start_tokens = model_router.cost_tracker.total_tokens
            import time
            start_time = time.monotonic()

            try:
                result = await orchestrator.process_command(schedule.command)
                stored.success = result.success
                stored.result_data = str(result.result_data or result.summary)
                stored.result_summary = result.summary
                stored.correlation_id = result.correlation_id
                stored.status = __import__("src.core.task_store", fromlist=["TaskStatus"]).TaskStatus.COMPLETED
            except Exception as e:
                stored.success = False
                stored.result_data = str(e)
                stored.result_summary = f"예약 실행 오류: {e}"
                stored.status = __import__("src.core.task_store", fromlist=["TaskStatus"]).TaskStatus.FAILED
                # 에러 알림
                await ws_manager.send_error_alert(
                    "schedule_error",
                    f"예약 '{schedule.name}' 실행 실패: {e}",
                    "warning",
                )
            finally:
                stored.completed_at = datetime.now(timezone.utc)
                stored.execution_time_seconds = round(time.monotonic() - start_time, 2)
                stored.cost_usd = round(model_router.cost_tracker.total_cost - start_cost, 6)
                stored.tokens_used = model_router.cost_tracker.total_tokens - start_tokens

                # WebSocket 알림
                await ws_manager.broadcast("task_completed", {
                    "task_id": stored.task_id,
                    "success": stored.success,
                    "summary": stored.result_summary,
                    "scheduled": True,
                    "schedule_name": schedule.name,
                })

            # 실행 기록 업데이트
            schedule.last_run = datetime.now(timezone.utc).isoformat()
            schedule.run_count += 1
            schedule.compute_next_run()
            self._save()
