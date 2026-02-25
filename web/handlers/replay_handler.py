"""리플레이(Replay) API — 배치 체인의 단계별 결과를 트리 형태로 조회.

비유: 블랙박스 — 배치 체인이 어떻게 진행되었는지 단계별로 되돌아보는 곳.
"""
import logging
import sys

from fastapi import APIRouter

from db import load_setting

logger = logging.getLogger("corthex")

router = APIRouter(tags=["replay"])


# ── arm_server 참조 헬퍼 ──
def _ms():
    """arm_server 모듈 참조."""
    return sys.modules.get("arm_server") or sys.modules.get("web.arm_server")


def _agent_names() -> dict:
    ms = _ms()
    return getattr(ms, "_AGENT_NAMES", {}) if ms else {}


def _specialist_names() -> dict:
    ms = _ms()
    return getattr(ms, "_SPECIALIST_NAMES", {}) if ms else {}


@router.get("/api/replay/{correlation_id}")
async def get_replay(correlation_id: str):
    """배치 체인의 단계별 결과를 트리 형태로 반환합니다."""
    agent_names = _agent_names()
    specialist_names = _specialist_names()
    chains = load_setting("batch_chains") or []

    # correlation_id 또는 chain_id로 검색
    chain = None
    for c in chains:
        if c.get("correlation_id") == correlation_id:
            chain = c
            break
        if c.get("chain_id") == correlation_id.replace("batch_", ""):
            chain = c
            break

    if not chain:
        return {"steps": [], "error": "체인을 찾을 수 없습니다"}

    steps = []

    # 1단계: 분류
    classify = chain.get("results", {}).get("classify")
    if classify:
        agent_name = agent_names.get(classify.get("agent_id", ""), classify.get("agent_id", ""))
        steps.append({
            "step": "classify",
            "step_label": "1단계: 분류",
            "agent": classify.get("method", "AI 분류"),
            "agent_name": agent_name,
            "result": classify.get("reason", f"→ {agent_name}"),
            "cost_usd": classify.get("cost_usd", 0),
        })

    # 2단계: 처장 지시서
    delegation = chain.get("results", {}).get("delegation")
    if delegation:
        if delegation.get("mode") == "broadcast":
            for mgr_id, instructions in delegation.get("delegations", {}).items():
                mgr_name = agent_names.get(mgr_id, mgr_id)
                spec_instructions = []
                for s_id, instruction in instructions.items():
                    s_name = specialist_names.get(s_id, s_id)
                    spec_instructions.append(f"**{s_name}**: {instruction}")
                steps.append({
                    "step": "delegation",
                    "step_label": "2단계: 처장 지시서",
                    "agent": mgr_id,
                    "agent_name": mgr_name,
                    "result": "\n".join(spec_instructions) if spec_instructions else "지시서 없음",
                })
        else:
            deleg_agent = delegation.get("agent_id", "")
            deleg_name = agent_names.get(deleg_agent, deleg_agent)
            instructions = delegation.get("instructions", {})
            spec_instructions = []
            for s_id, instruction in instructions.items():
                s_name = specialist_names.get(s_id, s_id)
                spec_instructions.append(f"**{s_name}**: {instruction}")
            steps.append({
                "step": "delegation",
                "step_label": "2단계: 처장 지시서",
                "agent": deleg_agent,
                "agent_name": deleg_name,
                "result": "\n".join(spec_instructions) if spec_instructions else "지시서 없음",
                "cost_usd": delegation.get("cost_usd", 0),
            })

    # 3단계: 전문가 결과
    specialists = chain.get("results", {}).get("specialists", {})
    for s_id, s_res in specialists.items():
        s_name = specialist_names.get(s_id, s_id)
        steps.append({
            "step": "specialist",
            "step_label": "3단계: 전문가 분석",
            "agent": s_id,
            "agent_name": s_name,
            "result": s_res.get("content", "")[:2000],
            "model": s_res.get("model", ""),
            "cost_usd": s_res.get("cost_usd", 0),
            "error": s_res.get("error"),
        })

    # 4단계: 종합보고서
    synthesis = chain.get("results", {}).get("synthesis", {})
    for mgr_id, synth_res in synthesis.items():
        mgr_name = agent_names.get(mgr_id, mgr_id)
        steps.append({
            "step": "synthesis",
            "step_label": "4단계: 종합보고서",
            "agent": mgr_id,
            "agent_name": mgr_name,
            "result": synth_res.get("content", "")[:2000],
            "model": synth_res.get("model", ""),
            "cost_usd": synth_res.get("cost_usd", 0),
        })

    return {
        "steps": steps,
        "chain_id": chain.get("chain_id", ""),
        "mode": chain.get("mode", ""),
        "status": chain.get("status", ""),
        "total_cost_usd": chain.get("total_cost_usd", 0),
    }


@router.get("/api/replay/latest")
async def get_replay_latest():
    """가장 최근 완료된 배치 체인의 replay를 반환합니다."""
    chains = load_setting("batch_chains") or []
    completed = [c for c in chains if c.get("status") == "completed"]
    if not completed:
        return {"steps": []}
    latest = max(completed, key=lambda c: c.get("completed_at", ""))
    corr_id = latest.get("correlation_id", "")
    if corr_id:
        return await get_replay(corr_id)
    return {"steps": []}
