"""
Agent Health Check System for CORTHEX HQ.

Provides system-wide diagnostics:
- LLM provider connectivity (API key presence + lightweight ping)
- Agent configuration validity
- Organizational hierarchy integrity
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.registry import AgentRegistry
    from src.llm.router import ModelRouter

logger = logging.getLogger("corthex.healthcheck")


class HealthStatus(str, Enum):
    OK = "ok"
    WARN = "warn"
    ERROR = "error"


@dataclass
class CheckResult:
    name: str
    status: HealthStatus
    message: str
    latency_ms: Optional[float] = None


@dataclass
class HealthReport:
    overall: HealthStatus
    checks: list[CheckResult] = field(default_factory=list)
    agent_count: int = 0
    provider_count: int = 0

    def to_dict(self) -> dict:
        return {
            "overall": self.overall.value,
            "agent_count": self.agent_count,
            "provider_count": self.provider_count,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "latency_ms": c.latency_ms,
                }
                for c in self.checks
            ],
        }


async def run_healthcheck(
    registry: AgentRegistry,
    model_router: ModelRouter,
) -> HealthReport:
    """Run all health checks and return a consolidated report."""
    checks: list[CheckResult] = []

    # Run provider checks and agent checks concurrently
    provider_checks, agent_checks, hierarchy_checks = await asyncio.gather(
        _check_providers(model_router),
        _check_agents(registry),
        _check_hierarchy(registry),
    )
    checks.extend(provider_checks)
    checks.extend(agent_checks)
    checks.extend(hierarchy_checks)

    # Determine overall status
    statuses = [c.status for c in checks]
    if HealthStatus.ERROR in statuses:
        overall = HealthStatus.ERROR
    elif HealthStatus.WARN in statuses:
        overall = HealthStatus.WARN
    else:
        overall = HealthStatus.OK

    provider_count = sum(
        1 for name in ("openai", "anthropic")
        if model_router._providers.get(name) is not None
    )

    return HealthReport(
        overall=overall,
        checks=checks,
        agent_count=registry.agent_count,
        provider_count=provider_count,
    )


async def _check_providers(router: ModelRouter) -> list[CheckResult]:
    """Check LLM provider availability by sending a minimal request."""
    results: list[CheckResult] = []

    provider_models = {
        "openai": "gpt-5-mini",
        "anthropic": "claude-haiku-4-5-20251001",
    }

    for provider_name, test_model in provider_models.items():
        provider = router._providers.get(provider_name)
        if provider is None:
            results.append(CheckResult(
                name=f"LLM:{provider_name}",
                status=HealthStatus.WARN,
                message=f"{provider_name} API 키 미설정 - 해당 프로바이더 사용 불가",
            ))
            continue

        # Lightweight ping: minimal completion request
        start = time.monotonic()
        try:
            resp = await provider.complete(
                model=test_model,
                messages=[{"role": "user", "content": "ping"}],
                temperature=0.0,
                max_tokens=1,
            )
            latency = (time.monotonic() - start) * 1000
            results.append(CheckResult(
                name=f"LLM:{provider_name}",
                status=HealthStatus.OK,
                message=f"{provider_name} 연결 정상 ({test_model})",
                latency_ms=round(latency, 1),
            ))
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            results.append(CheckResult(
                name=f"LLM:{provider_name}",
                status=HealthStatus.ERROR,
                message=f"{provider_name} 연결 실패: {e}",
                latency_ms=round(latency, 1),
            ))

    return results


async def _check_agents(registry: AgentRegistry) -> list[CheckResult]:
    """Validate agent configurations."""
    results: list[CheckResult] = []
    agents = registry.list_all()

    if not agents:
        results.append(CheckResult(
            name="에이전트",
            status=HealthStatus.ERROR,
            message="등록된 에이전트가 없습니다",
        ))
        return results

    # Check each agent has required config fields
    misconfigured = []
    for agent in agents:
        cfg = agent.config
        issues = []
        if not cfg.system_prompt.strip():
            issues.append("시스템 프롬프트 없음")
        if not cfg.model_name:
            issues.append("모델명 미지정")
        if cfg.role == "manager" and not cfg.subordinate_ids:
            issues.append("매니저인데 부하 에이전트 없음")
        if issues:
            misconfigured.append(f"{cfg.agent_id}: {', '.join(issues)}")

    if misconfigured:
        results.append(CheckResult(
            name="에이전트 설정",
            status=HealthStatus.WARN,
            message=f"설정 이상 {len(misconfigured)}건 - {'; '.join(misconfigured)}",
        ))
    else:
        results.append(CheckResult(
            name="에이전트 설정",
            status=HealthStatus.OK,
            message=f"전체 {len(agents)}개 에이전트 설정 정상",
        ))

    return results


async def _check_hierarchy(registry: AgentRegistry) -> list[CheckResult]:
    """Verify organizational hierarchy integrity."""
    results: list[CheckResult] = []
    agents = registry.list_all()
    agent_ids = {a.agent_id for a in agents}
    issues = []

    for agent in agents:
        cfg = agent.config
        # Check superior exists
        if cfg.superior_id and cfg.superior_id not in agent_ids:
            issues.append(f"{cfg.agent_id}: 상관 '{cfg.superior_id}' 미등록")

        # Check subordinates exist
        for sub_id in cfg.subordinate_ids:
            if sub_id not in agent_ids:
                issues.append(f"{cfg.agent_id}: 부하 '{sub_id}' 미등록")

    if issues:
        results.append(CheckResult(
            name="조직도 무결성",
            status=HealthStatus.ERROR,
            message=f"계층 구조 오류 {len(issues)}건 - {'; '.join(issues)}",
        ))
    else:
        results.append(CheckResult(
            name="조직도 무결성",
            status=HealthStatus.OK,
            message="상하 관계 정상",
        ))

    return results
