"""
CORTHEX HQ - Mini Server (경량 서버)

Oracle Cloud 무료 서버(1GB RAM)에서 대시보드를 서비스하기 위한 경량 서버.
전체 백엔드의 핵심 API만 제공하여 대시보드 UI가 정상 작동하도록 함.
"""
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

KST = timezone(timedelta(hours=9))

app = FastAPI(title="CORTHEX HQ Mini Server")

# ── HTML 서빙 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(TEMPLATE_DIR, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ── 에이전트 목록 ──
AGENTS = [
    {"agent_id": "chief_of_staff", "name_ko": "비서실장", "role": "manager", "division": "secretary", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "report_worker", "name_ko": "보고 요약 Worker", "role": "worker", "division": "secretary", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "schedule_worker", "name_ko": "일정/미결 추적 Worker", "role": "worker", "division": "secretary", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "relay_worker", "name_ko": "사업부 간 정보 중계 Worker", "role": "worker", "division": "secretary", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "cto_manager", "name_ko": "기술개발처장 (CTO)", "role": "manager", "division": "leet_master.tech", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "frontend_specialist", "name_ko": "프론트엔드 Specialist", "role": "specialist", "division": "leet_master.tech", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "backend_specialist", "name_ko": "백엔드/API Specialist", "role": "specialist", "division": "leet_master.tech", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "infra_specialist", "name_ko": "DB/인프라 Specialist", "role": "specialist", "division": "leet_master.tech", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "ai_model_specialist", "name_ko": "AI 모델 Specialist", "role": "specialist", "division": "leet_master.tech", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "cso_manager", "name_ko": "사업기획처장 (CSO)", "role": "manager", "division": "leet_master.strategy", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "market_research_specialist", "name_ko": "시장조사 Specialist", "role": "specialist", "division": "leet_master.strategy", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "business_plan_specialist", "name_ko": "사업계획서 Specialist", "role": "specialist", "division": "leet_master.strategy", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "financial_model_specialist", "name_ko": "재무모델링 Specialist", "role": "specialist", "division": "leet_master.strategy", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "clo_manager", "name_ko": "법무·IP처장 (CLO)", "role": "manager", "division": "leet_master.legal", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "copyright_specialist", "name_ko": "저작권 Specialist", "role": "specialist", "division": "leet_master.legal", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "patent_specialist", "name_ko": "특허/약관 Specialist", "role": "specialist", "division": "leet_master.legal", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "cmo_manager", "name_ko": "마케팅·고객처장 (CMO)", "role": "manager", "division": "leet_master.marketing", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "survey_specialist", "name_ko": "설문/리서치 Specialist", "role": "specialist", "division": "leet_master.marketing", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "content_specialist", "name_ko": "콘텐츠 Specialist", "role": "specialist", "division": "leet_master.marketing", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "community_specialist", "name_ko": "커뮤니티 Specialist", "role": "specialist", "division": "leet_master.marketing", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "cio_manager", "name_ko": "투자분석처장 (CIO)", "role": "manager", "division": "finance.investment", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "market_condition_specialist", "name_ko": "시황분석 Specialist", "role": "specialist", "division": "finance.investment", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "stock_analysis_specialist", "name_ko": "종목분석 Specialist", "role": "specialist", "division": "finance.investment", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "technical_analysis_specialist", "name_ko": "기술적분석 Specialist", "role": "specialist", "division": "finance.investment", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "risk_management_specialist", "name_ko": "리스크관리 Specialist", "role": "specialist", "division": "finance.investment", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "cpo_manager", "name_ko": "출판·기록처장 (CPO)", "role": "manager", "division": "publishing", "status": "idle", "model_name": "claude-sonnet-4-5-20250929"},
    {"agent_id": "chronicle_specialist", "name_ko": "회사연대기 Specialist", "role": "specialist", "division": "publishing", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "editor_specialist", "name_ko": "콘텐츠편집 Specialist", "role": "specialist", "division": "publishing", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
    {"agent_id": "archive_specialist", "name_ko": "아카이브 Specialist", "role": "specialist", "division": "publishing", "status": "idle", "model_name": "claude-haiku-4-5-20251001"},
]

# ── WebSocket 관리 ──
connected_clients: list[WebSocket] = []


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    try:
        # 연결 시 초기 상태 전송
        now = datetime.now(KST).strftime("%H:%M:%S")
        await ws.send_json({
            "event": "activity_log",
            "data": {
                "agent_id": "chief_of_staff",
                "message": "시스템 연결 완료. 대기 중입니다.",
                "level": "info",
                "time": now,
            }
        })
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            # 메시지를 받으면 간단한 응답
            if msg.get("type") == "command":
                await ws.send_json({
                    "event": "result",
                    "data": {
                        "content": "현재 경량 모드로 실행 중입니다. 전체 AI 에이전트 기능은 메인 서버에서 사용 가능합니다.",
                        "sender_id": "chief_of_staff",
                        "time_seconds": 0.1,
                        "cost": 0,
                    }
                })
    except WebSocketDisconnect:
        connected_clients.remove(ws)
    except Exception:
        if ws in connected_clients:
            connected_clients.remove(ws)


# ── API 엔드포인트 ──

@app.get("/api/auth/status")
async def auth_status():
    return {"bootstrap_mode": True, "role": "ceo", "authenticated": True}


@app.get("/api/agents")
async def get_agents():
    return AGENTS


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    for a in AGENTS:
        if a["agent_id"] == agent_id:
            return {**a, "system_prompt": "", "capabilities": [], "allowed_tools": []}
    return {"error": "not found"}


@app.get("/api/tools")
async def get_tools():
    """tools.yaml에서 도구 목록을 읽어 반환."""
    try:
        config_path = Path(BASE_DIR).parent / "config" / "tools.yaml"
        tools_cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        return tools_cfg.get("tools", [])
    except Exception:
        return []


@app.get("/api/dashboard")
async def get_dashboard():
    now = datetime.now(KST).isoformat()
    return {
        "total_agents": len(AGENTS),
        "active_agents": 0,
        "idle_agents": len(AGENTS),
        "total_tasks_today": 0,
        "system_status": "idle",
        "uptime": now,
        "agents": AGENTS,
    }


@app.get("/api/budget")
async def get_budget():
    return {
        "daily_limit": 10.0,
        "daily_used": 0.0,
        "monthly_limit": 300.0,
        "monthly_used": 0.0,
    }


@app.get("/api/quality")
async def get_quality():
    return {"average_score": 0, "total_evaluated": 0, "rules": []}


@app.get("/api/feedback")
async def get_feedback():
    return {"good": 0, "bad": 0, "total": 0}


@app.get("/api/presets")
async def get_presets():
    return []


@app.get("/api/performance")
async def get_performance():
    return {"agents": [], "summary": {}}


@app.get("/api/tasks")
async def get_tasks():
    return {"tasks": [], "total": 0}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    return {"error": "not found"}


@app.get("/api/replay/{correlation_id}")
async def get_replay(correlation_id: str):
    return {"steps": []}


@app.get("/api/replay/latest")
async def get_replay_latest():
    return {"steps": []}


@app.get("/api/schedules")
async def get_schedules():
    return []


@app.get("/api/workflows")
async def get_workflows():
    return []


@app.get("/api/knowledge")
async def get_knowledge():
    return {"entries": [], "total": 0}


@app.get("/api/knowledge/{entry_id}")
async def get_knowledge_entry(entry_id: str):
    return {"error": "not found"}


@app.get("/api/memory/{agent_id}")
async def get_memory(agent_id: str):
    return {"memories": []}


@app.get("/api/quality-rules")
async def get_quality_rules():
    return {"model": "", "rubrics": {}}


@app.get("/api/available-models")
async def get_available_models():
    return [
        {"id": "claude-sonnet-4-5-20250929", "name": "Claude Sonnet 4.5"},
        {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5"},
        {"id": "claude-opus-4-6", "name": "Claude Opus 4.6"},
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
