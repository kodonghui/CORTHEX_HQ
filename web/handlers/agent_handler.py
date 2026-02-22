"""에이전트 관리 API — 에이전트 목록, 모델 변경, 예산 관리.

비유: 인사부 — 에이전트 인력 정보 조회, 모델(장비) 배정, 예산 관리를 담당.
"""
import logging
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from db import load_setting, save_setting, get_today_cost
from state import app_state

logger = logging.getLogger("corthex")

router = APIRouter(tags=["agents"])


# ── mini_server 참조 헬퍼 ──
def _ms():
    """mini_server 모듈 참조 (lazy import로 순환 참조 방지)."""
    return sys.modules.get("mini_server") or sys.modules.get("web.mini_server")


def _load_data(name: str, default=None):
    """DB에서 설정 로드 (mini_server._load_data 위임)."""
    ms = _ms()
    if ms and hasattr(ms, "_load_data"):
        return ms._load_data(name, default)
    val = load_setting(name)
    return val if val is not None else (default if default is not None else {})


def _save_data(name: str, data) -> None:
    """DB에 설정 저장 (mini_server._save_data 위임)."""
    ms = _ms()
    if ms and hasattr(ms, "_save_data"):
        ms._save_data(name, data)
    else:
        save_setting(name, data)


def _load_config(name: str) -> dict:
    """설정 파일 로드 (mini_server._load_config 위임)."""
    ms = _ms()
    if ms and hasattr(ms, "_load_config"):
        return ms._load_config(name)
    return {}


def _get_agents():
    """AGENTS 리스트 참조."""
    ms = _ms()
    return getattr(ms, "AGENTS", []) if ms else []


def _get_agents_detail():
    """_AGENTS_DETAIL dict 참조."""
    ms = _ms()
    return getattr(ms, "_AGENTS_DETAIL", {}) if ms else {}


def _get_model_reasoning_map():
    """MODEL_REASONING_MAP 참조."""
    ms = _ms()
    return getattr(ms, "MODEL_REASONING_MAP", {}) if ms else {}


def _init_tool_pool():
    """ToolPool 초기화 (mini_server._init_tool_pool 위임)."""
    ms = _ms()
    if ms and hasattr(ms, "_init_tool_pool"):
        return ms._init_tool_pool()
    return None


# ── 에이전트 목록 ──

@router.get("/api/agents")
async def get_agents():
    """에이전트 목록 반환 (오버라이드된 model_name, reasoning_effort 포함)."""
    AGENTS = _get_agents()
    agents_detail = _get_agents_detail()
    result = []
    overrides = _load_data("agent_overrides", {})
    for a in AGENTS:
        agent = dict(a)
        aid = agent["agent_id"]
        detail = agents_detail.get(aid, {})
        # 오버라이드된 모델명 반영
        if aid in overrides and "model_name" in overrides[aid]:
            agent["model_name"] = overrides[aid]["model_name"]
        elif detail.get("model_name"):
            agent["model_name"] = detail["model_name"]
        # 추론 레벨 반영
        agent["reasoning_effort"] = ""
        if aid in overrides and "reasoning_effort" in overrides[aid]:
            agent["reasoning_effort"] = overrides[aid]["reasoning_effort"]
        elif detail.get("reasoning_effort"):
            agent["reasoning_effort"] = detail["reasoning_effort"]
        result.append(agent)
    return result


@router.get("/api/agents/recommended-models")
async def get_recommended_models():
    """agents.yaml 원본의 권장 모델 목록 반환 (메모리 변경에 영향받지 않음)."""
    yaml_data = _load_config("agents")
    result = {}
    for agent in yaml_data.get("agents", []):
        aid = agent.get("agent_id")
        if aid:
            result[aid] = {
                "model_name": agent.get("model_name", "claude-sonnet-4-6"),
                "reasoning_effort": agent.get("reasoning_effort", "medium"),
            }
    return result


@router.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    AGENTS = _get_agents()
    agents_detail = _get_agents_detail()
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for a in AGENTS:
        if a["agent_id"] == agent_id:
            detail = agents_detail.get(agent_id, {})
            overrides = _load_data("agent_overrides", {})
            override = overrides.get(agent_id, {})
            model_name = override.get("model_name") or detail.get("model_name") or a.get("model_name", "")
            reasoning_effort = override.get("reasoning_effort") or detail.get("reasoning_effort", "")
            # 소울 로드 우선순위: 1) agents.yaml → 2) souls/*.md 파일
            system_prompt = detail.get("system_prompt", "")
            if not system_prompt:
                soul_md = Path(BASE_DIR) / "souls" / "agents" / f"{agent_id}.md"
                if soul_md.exists():
                    try:
                        system_prompt = soul_md.read_text(encoding="utf-8")
                    except Exception:
                        system_prompt = ""
            return {
                **a,
                "model_name": model_name,
                "system_prompt": system_prompt,
                "capabilities": detail.get("capabilities", []),
                "allowed_tools": detail.get("allowed_tools", []),
                "subordinate_ids": detail.get("subordinate_ids", []),
                "superior_id": detail.get("superior_id", ""),
                "temperature": detail.get("temperature", 0.3),
                "reasoning_effort": reasoning_effort,
            }
    return JSONResponse({"error": "not found", "agent_id": agent_id}, status_code=404)


# ── 에이전트 기본값 관리 ──

@router.post("/api/agents/save-defaults")
async def save_agent_defaults():
    """현재 agent_overrides를 기본값 스냅샷으로 저장."""
    overrides = _load_data("agent_overrides", {})
    _save_data("agent_model_defaults", overrides)
    return {"success": True, "saved_count": len(overrides)}


@router.post("/api/agents/apply-recommended")
async def apply_recommended_models():
    """agents.yaml 원본의 권장 모델을 모든 에이전트에 즉시 적용."""
    AGENTS = _get_agents()
    agents_detail = _get_agents_detail()
    yaml_data = _load_config("agents")
    yaml_defaults = {}
    for agent in yaml_data.get("agents", []):
        aid = agent.get("agent_id")
        if aid:
            yaml_defaults[aid] = {
                "model_name": agent.get("model_name", "claude-sonnet-4-6"),
                "reasoning_effort": agent.get("reasoning_effort", "medium"),
            }
    if not yaml_defaults:
        return {"error": "agents.yaml에서 권장 모델을 읽을 수 없습니다."}
    _save_data("agent_overrides", yaml_defaults)
    for a in AGENTS:
        aid = a["agent_id"]
        if aid in yaml_defaults:
            a["model_name"] = yaml_defaults[aid]["model_name"]
    for aid, vals in yaml_defaults.items():
        if aid in agents_detail:
            agents_detail[aid]["model_name"] = vals["model_name"]
            agents_detail[aid]["reasoning_effort"] = vals["reasoning_effort"]
    pool = _init_tool_pool()
    if pool and hasattr(pool, "set_agent_model"):
        for aid, vals in yaml_defaults.items():
            _temp = agents_detail.get(aid, {}).get("temperature", 0.7)
            pool.set_agent_model(aid, vals["model_name"], temperature=_temp)
    return {"success": True, "applied_count": len(yaml_defaults)}


@router.post("/api/agents/restore-defaults")
async def restore_agent_defaults():
    """저장된 기본값 스냅샷으로 전체 에이전트 모델/추론 복원."""
    AGENTS = _get_agents()
    agents_detail = _get_agents_detail()
    # 1순위: 사용자가 저장한 스냅샷 (agent_model_defaults)
    saved_defaults = _load_data("agent_model_defaults", {})
    if saved_defaults:
        defaults = saved_defaults
        source = "snapshot"
    else:
        # 2순위: agents.yaml 하드코딩 기본값
        yaml_data = _load_config("agents")
        defaults = {}
        for agent in yaml_data.get("agents", []):
            aid = agent.get("agent_id")
            if aid:
                defaults[aid] = {
                    "model_name": agent.get("model_name", "claude-sonnet-4-6"),
                    "reasoning_effort": agent.get("reasoning_effort", "medium"),
                }
        source = "yaml"
    if not defaults:
        return {"error": "복원할 기본값이 없습니다. 먼저 '현재를 기본값으로 저장'을 눌러주세요."}
    _save_data("agent_overrides", defaults)
    for agent_id, vals in defaults.items():
        for a in AGENTS:
            if a["agent_id"] == agent_id:
                a["model_name"] = vals["model_name"]
                break
        if agent_id in agents_detail:
            agents_detail[agent_id].update(vals)
    pool = _init_tool_pool()
    if pool and hasattr(pool, "set_agent_model"):
        for agent_id, vals in defaults.items():
            if "model_name" in vals:
                _temp = agents_detail.get(agent_id, {}).get("temperature", 0.7)
                pool.set_agent_model(agent_id, vals["model_name"], temperature=_temp)
    return {"success": True, "restored_count": len(defaults), "source": source}


@router.put("/api/agents/bulk-model")
async def bulk_change_model(request: Request):
    """모든 에이전트의 모델을 한번에 변경."""
    AGENTS = _get_agents()
    agents_detail = _get_agents_detail()
    model_reasoning_map = _get_model_reasoning_map()
    body = await request.json()
    new_model = body.get("model_name", "")
    reasoning = body.get("reasoning_effort", "")
    if not reasoning:
        reasoning = model_reasoning_map.get(new_model, "medium")
    if not new_model:
        return {"error": "model_name 필수"}
    overrides = _load_data("agent_overrides", {})
    changed = 0
    for a in AGENTS:
        aid = a["agent_id"]
        a["model_name"] = new_model
        if aid in agents_detail:
            agents_detail[aid]["model_name"] = new_model
            agents_detail[aid]["reasoning_effort"] = reasoning
        if aid not in overrides:
            overrides[aid] = {}
        overrides[aid]["model_name"] = new_model
        overrides[aid]["reasoning_effort"] = reasoning
        changed += 1
    _save_data("agent_overrides", overrides)
    pool = _init_tool_pool()
    if pool and hasattr(pool, "set_agent_model"):
        for a in AGENTS:
            _temp = agents_detail.get(a["agent_id"], {}).get("temperature", 0.7)
            pool.set_agent_model(a["agent_id"], new_model, temperature=_temp)
    return {"success": True, "changed": changed, "model_name": new_model, "reasoning_effort": reasoning}


@router.put("/api/agents/{agent_id}/soul")
async def save_agent_soul(agent_id: str, request: Request):
    """에이전트 소울은 코드(agents.yaml)에서만 수정 가능. 웹 수정 차단."""
    return {"success": False, "error": "소울은 설정 파일(agents.yaml)에서만 수정 가능합니다. 웹 수정이 비활성화되었습니다."}


@router.put("/api/agents/{agent_id}/model")
async def save_agent_model(agent_id: str, request: Request):
    """에이전트에 배정된 AI 모델 변경."""
    AGENTS = _get_agents()
    agents_detail = _get_agents_detail()
    model_reasoning_map = _get_model_reasoning_map()
    body = await request.json()
    new_model = body.get("model_name") or body.get("model", "")
    for a in AGENTS:
        if a["agent_id"] == agent_id:
            a["model_name"] = new_model
            break
    if agent_id in agents_detail:
        agents_detail[agent_id]["model_name"] = new_model
    overrides = _load_data("agent_overrides", {})
    if agent_id not in overrides:
        overrides[agent_id] = {}
    overrides[agent_id]["model_name"] = new_model
    auto_reasoning = model_reasoning_map.get(new_model, "")
    if auto_reasoning:
        overrides[agent_id]["reasoning_effort"] = auto_reasoning
        if agent_id in agents_detail:
            agents_detail[agent_id]["reasoning_effort"] = auto_reasoning
    _save_data("agent_overrides", overrides)
    pool = _init_tool_pool()
    if pool and hasattr(pool, "set_agent_model"):
        _temp = agents_detail.get(agent_id, {}).get("temperature", 0.7)
        pool.set_agent_model(agent_id, new_model, temperature=_temp)
    return {"success": True, "agent_id": agent_id, "model": new_model}


@router.put("/api/agents/{agent_id}/reasoning")
async def save_agent_reasoning(agent_id: str, request: Request):
    """에이전트 추론 방식(reasoning effort) 변경."""
    agents_detail = _get_agents_detail()
    body = await request.json()
    effort = body.get("reasoning_effort", "")
    if agent_id in agents_detail:
        agents_detail[agent_id]["reasoning_effort"] = effort
    overrides = _load_data("agent_overrides", {})
    if agent_id not in overrides:
        overrides[agent_id] = {}
    overrides[agent_id]["reasoning_effort"] = effort
    _save_data("agent_overrides", overrides)
    return {"success": True, "agent_id": agent_id, "reasoning_effort": effort}


# ── 사용 가능 모델 목록 ──

@router.get("/api/available-models")
async def get_available_models():
    return [
        # Anthropic (Claude)
        {"name": "claude-opus-4-6", "provider": "anthropic", "tier": "executive",
         "cost_input": 15.0, "cost_output": 75.0, "reasoning_levels": ["low", "medium", "high"]},
        {"name": "claude-sonnet-4-6", "provider": "anthropic", "tier": "manager",
         "cost_input": 3.0, "cost_output": 15.0, "reasoning_levels": ["low", "medium", "high"]},
        {"name": "claude-haiku-4-5-20251001", "provider": "anthropic", "tier": "specialist",
         "cost_input": 0.25, "cost_output": 1.25, "reasoning_levels": []},
        # OpenAI (GPT)
        {"name": "gpt-5.2-pro", "provider": "openai", "tier": "executive",
         "cost_input": 18.0, "cost_output": 90.0, "reasoning_levels": ["medium", "high", "xhigh"]},
        {"name": "gpt-5.2", "provider": "openai", "tier": "manager",
         "cost_input": 5.0, "cost_output": 25.0, "reasoning_levels": ["none", "low", "medium", "high", "xhigh"]},
        {"name": "gpt-5", "provider": "openai", "tier": "specialist",
         "cost_input": 2.5, "cost_output": 10.0, "reasoning_levels": ["none", "low", "medium", "high"]},
        {"name": "gpt-5-mini", "provider": "openai", "tier": "specialist",
         "cost_input": 0.5, "cost_output": 2.0, "reasoning_levels": ["low", "medium", "high"]},
        # Google (Gemini)
        {"name": "gemini-3.1-pro-preview", "provider": "google", "tier": "executive",
         "cost_input": 2.0, "cost_output": 12.0, "reasoning_levels": ["low", "high"]},
        {"name": "gemini-2.5-pro", "provider": "google", "tier": "manager",
         "cost_input": 1.25, "cost_output": 10.0, "reasoning_levels": ["low", "medium", "high"]},
        {"name": "gemini-2.5-flash", "provider": "google", "tier": "specialist",
         "cost_input": 0.15, "cost_output": 0.60, "reasoning_levels": ["none", "low", "medium", "high"]},
    ]


# ── 예산 관리 ──

@router.get("/api/budget")
async def get_budget():
    limit = float(load_setting("daily_budget_usd") or 7.0)
    today = get_today_cost()
    try:
        from db import get_monthly_cost
        monthly = get_monthly_cost()
    except (ImportError, Exception):
        monthly = today
    monthly_limit = float(load_setting("monthly_budget_usd") or 300.0)
    return {
        "daily_limit": limit, "daily_used": today,
        "today_spent": today, "today_cost": today,
        "remaining": round(limit - today, 6),
        "exceeded": today >= limit,
        "monthly_limit": monthly_limit, "monthly_used": monthly,
    }


@router.put("/api/budget")
async def save_budget(request: Request):
    """일일/월간 예산 한도 변경."""
    body = await request.json()
    if "daily_limit" in body:
        save_setting("daily_budget_usd", float(body["daily_limit"]))
    if "monthly_limit" in body:
        save_setting("monthly_budget_usd", float(body["monthly_limit"]))
    daily = float(load_setting("daily_budget_usd") or 7.0)
    monthly = float(load_setting("monthly_budget_usd") or 300.0)
    return {"success": True, "daily_limit": daily, "monthly_limit": monthly}


# ── 모델 모드 ──

@router.get("/api/model-mode")
async def get_model_mode():
    """현재 모델 모드 조회 (auto/manual)."""
    mode = load_setting("model_mode") or "auto"
    override = load_setting("model_override") or "claude-sonnet-4-6"
    return {"mode": mode, "override": override}


@router.put("/api/model-mode")
async def set_model_mode(request: Request):
    """모델 모드 변경."""
    body = await request.json()
    mode = body.get("mode", "auto")
    save_setting("model_mode", mode)
    if mode == "manual" and "override" in body:
        save_setting("model_override", body["override"])
    return {"success": True, "mode": mode}
