"""
워크플로우 엔진.

여러 단계(Step)를 순차적으로 실행하는 자동화 파이프라인입니다.
각 단계의 결과가 다음 단계의 {prev_result} 플레이스홀더에 자동 주입됩니다.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from src.core.orchestrator import Orchestrator
    from src.core.task_store import TaskStore
    from src.llm.router import ModelRouter
    from web.ws_manager import ConnectionManager

logger = logging.getLogger("corthex.workflow")


class WorkflowStep:
    """워크플로우의 단일 단계."""

    def __init__(self, name: str, command: str) -> None:
        self.name = name
        self.command = command

    def to_dict(self) -> dict:
        return {"name": self.name, "command": self.command}

    @classmethod
    def from_dict(cls, d: dict) -> WorkflowStep:
        return cls(name=d.get("name", ""), command=d.get("command", ""))


class WorkflowDefinition:
    """워크플로우 정의."""

    def __init__(
        self,
        workflow_id: str,
        name: str,
        description: str = "",
        steps: list[WorkflowStep] | None = None,
    ) -> None:
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.steps = steps or []

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorkflowDefinition:
        return cls(
            workflow_id=d.get("workflow_id", str(uuid.uuid4())[:8]),
            name=d.get("name", ""),
            description=d.get("description", ""),
            steps=[WorkflowStep.from_dict(s) for s in d.get("steps", [])],
        )


class WorkflowEngine:
    """워크플로우 관리 + 실행 엔진."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._workflows: list[WorkflowDefinition] = []
        self._load()

    def _load(self) -> None:
        if not self._config_path.exists():
            self._workflows = []
            return
        try:
            raw = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))
            items = raw.get("workflows", []) if raw else []
            self._workflows = [WorkflowDefinition.from_dict(d) for d in items]
        except Exception as e:
            logger.warning("워크플로우 설정 로드 실패: %s", e)
            self._workflows = []

    def _save(self) -> None:
        data = {"workflows": [w.to_dict() for w in self._workflows]}
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    def list_all(self) -> list[dict]:
        return [w.to_dict() for w in self._workflows]

    def get(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        for w in self._workflows:
            if w.workflow_id == workflow_id:
                return w
        return None

    def create(self, name: str, description: str, steps: list[dict]) -> dict:
        wf = WorkflowDefinition(
            workflow_id=str(uuid.uuid4())[:8],
            name=name,
            description=description,
            steps=[WorkflowStep.from_dict(s) for s in steps],
        )
        self._workflows.append(wf)
        self._save()
        logger.info("워크플로우 생성: %s (%d단계)", name, len(wf.steps))
        return wf.to_dict()

    def update(self, workflow_id: str, data: dict) -> Optional[dict]:
        for w in self._workflows:
            if w.workflow_id == workflow_id:
                if "name" in data:
                    w.name = data["name"]
                if "description" in data:
                    w.description = data["description"]
                if "steps" in data:
                    w.steps = [WorkflowStep.from_dict(s) for s in data["steps"]]
                self._save()
                return w.to_dict()
        return None

    def delete(self, workflow_id: str) -> bool:
        before = len(self._workflows)
        self._workflows = [w for w in self._workflows if w.workflow_id != workflow_id]
        if len(self._workflows) < before:
            self._save()
            return True
        return False

    async def run(
        self,
        workflow_id: str,
        orchestrator: Orchestrator,
        ws_manager: ConnectionManager,
        task_store: TaskStore,
        model_router: ModelRouter,
    ) -> dict:
        """워크플로우를 순차 실행합니다."""
        wf = self.get(workflow_id)
        if not wf:
            return {"error": "워크플로우를 찾을 수 없습니다"}

        from src.core.task_store import TaskStatus

        results = []
        prev_result = ""

        for i, step in enumerate(wf.steps):
            # {prev_result} 플레이스홀더 치환
            command = step.command.replace("{prev_result}", prev_result)

            # 진행 상황 브로드캐스트
            await ws_manager.broadcast("workflow_progress", {
                "workflow_id": workflow_id,
                "step": i + 1,
                "total_steps": len(wf.steps),
                "step_name": step.name,
                "status": "running",
            })

            # 작업 생성 + 실행
            stored = task_store.create(f"[WF:{wf.name}] {step.name}: {command}")
            stored.status = TaskStatus.RUNNING
            stored.started_at = datetime.now(timezone.utc)
            start_cost = model_router.cost_tracker.total_cost
            start_tokens = model_router.cost_tracker.total_tokens
            start_time = time.monotonic()

            try:
                result = await orchestrator.process_command(command)
                stored.success = result.success
                stored.result_data = str(result.result_data or result.summary)
                stored.result_summary = result.summary
                stored.correlation_id = result.correlation_id
                stored.status = TaskStatus.COMPLETED
                prev_result = stored.result_summary or stored.result_data or ""
            except Exception as e:
                stored.success = False
                stored.result_data = str(e)
                stored.result_summary = f"오류: {e}"
                stored.status = TaskStatus.FAILED
                prev_result = ""
                await ws_manager.send_error_alert(
                    "workflow_error",
                    f"워크플로우 '{wf.name}' 단계 {i+1} 실패: {e}",
                    "error",
                )
            finally:
                stored.completed_at = datetime.now(timezone.utc)
                stored.execution_time_seconds = round(time.monotonic() - start_time, 2)
                stored.cost_usd = round(model_router.cost_tracker.total_cost - start_cost, 6)
                stored.tokens_used = model_router.cost_tracker.total_tokens - start_tokens

            results.append({
                "step": i + 1,
                "name": step.name,
                "success": stored.success,
                "summary": stored.result_summary,
                "time_seconds": stored.execution_time_seconds,
                "cost": stored.cost_usd,
            })

            await ws_manager.broadcast("workflow_progress", {
                "workflow_id": workflow_id,
                "step": i + 1,
                "total_steps": len(wf.steps),
                "step_name": step.name,
                "status": "completed" if stored.success else "failed",
            })

            # 실패 시 중단
            if not stored.success:
                break

        total_success = all(r["success"] for r in results)
        return {
            "workflow_id": workflow_id,
            "name": wf.name,
            "success": total_success,
            "steps_completed": len(results),
            "total_steps": len(wf.steps),
            "results": results,
        }
