"""아키텍처 맵 대시보드 API — 조직도·비용·실시간 상태.

비유: 회사 건물 안내도 — 누가 어디에 있는지, 누가 일하고 있는지, 비용은 얼마인지.
"""
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query

from db import get_today_cost, get_monthly_cost, get_cost_by_agent, get_cost_by_agent_raw

logger = logging.getLogger("corthex")

router = APIRouter(prefix="/api/architecture", tags=["architecture"])

KST = timezone(timedelta(hours=9))


# ── 조직도 (계층 구조) ──

@router.get("/hierarchy")
async def get_hierarchy():
    """에이전트 계층 구조를 반환합니다 (Mermaid 렌더링용)."""
    from mini_server import AGENTS, _AGENTS_DETAIL

    nodes = []
    edges = []

    for agent in AGENTS:
        aid = agent["agent_id"]
        detail = _AGENTS_DETAIL.get(aid, {})
        nodes.append({
            "id": aid,
            "name_ko": agent.get("name_ko", aid),
            "role": detail.get("role", "specialist"),
            "division": detail.get("division", ""),
            "model_name": agent.get("model_name", ""),
        })

        subs = detail.get("subordinate_ids") or []
        for sub_id in subs:
            edges.append({"from": aid, "to": sub_id})

    return {"nodes": nodes, "edges": edges, "total_agents": len(nodes)}


# ── 비용 요약 ──

@router.get("/cost-summary")
async def get_cost_summary():
    """이번 달·오늘·일평균 비용 요약을 반환합니다."""
    today_cost = get_today_cost()
    monthly_cost = get_monthly_cost()

    now_kst = datetime.now(KST)
    day_of_month = now_kst.day
    daily_avg = round(monthly_cost / day_of_month, 6) if day_of_month > 0 else 0.0

    return {
        "today_cost_usd": today_cost,
        "monthly_cost_usd": monthly_cost,
        "daily_avg_usd": daily_avg,
        "day_of_month": day_of_month,
        "month_label": now_kst.strftime("%Y년 %m월"),
    }


# ── 에이전트별 비용 ──

@router.get("/cost-by-agent")
async def get_cost_by_agent_api(period: str = Query("month")):
    """에이전트별 비용을 집계합니다."""
    return get_cost_by_agent(period)


# ── 부서별 비용 ──

@router.get("/cost-by-division")
async def get_cost_by_division_api(period: str = Query("month")):
    """부서별 비용을 집계합니다."""
    from mini_server import AGENTS

    raw = get_cost_by_agent_raw(period)
    agent_costs = raw.get("agent_costs", {})

    # AGENTS에서 division 매핑
    agent_div_map = {}
    for a in AGENTS:
        div = a.get("division", "")
        # agents.yaml의 긴 키를 짧은 키로 변환 (프론트엔드 agentDivision과 일치)
        short = div
        if div.startswith("leet_master."):
            short = div.replace("leet_master.", "")
        elif div.startswith("finance."):
            short = "finance"
        agent_div_map[a["agent_id"]] = short

    div_labels = {
        "secretary": "비서실",
        "tech": "기술개발처 (CTO)",
        "strategy": "사업기획처 (CSO)",
        "legal": "법무처 (CLO)",
        "marketing": "마케팅처 (CMO)",
        "finance": "투자분석처 (CIO)",
        "publishing": "출판기록처 (CPO)",
    }

    division_agg = {}
    total = 0.0
    for aid, cost_data in agent_costs.items():
        div = agent_div_map.get(aid, "unknown")
        if div not in division_agg:
            division_agg[div] = {"cost_usd": 0.0, "call_count": 0, "agents": set()}
        division_agg[div]["cost_usd"] += cost_data["cost_usd"]
        division_agg[div]["call_count"] += cost_data["call_count"]
        division_agg[div]["agents"].add(aid)
        total += cost_data["cost_usd"]

    divisions = []
    for div, data in sorted(division_agg.items(), key=lambda x: -x[1]["cost_usd"]):
        divisions.append({
            "division": div,
            "label": div_labels.get(div, div),
            "cost_usd": round(data["cost_usd"], 6),
            "call_count": data["call_count"],
            "agent_count": len(data["agents"]),
        })

    return {"divisions": divisions, "total_cost_usd": round(total, 6)}
