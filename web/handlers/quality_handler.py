"""품질검수(Quality) API — 품질 통계 조회 + 검수 규칙 관리.

비유: 품질관리실 — 에이전트 산출물의 품질을 검수하고 기준을 설정하는 곳.
"""
import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Request

from db import load_setting, save_setting, get_quality_stats, get_quality_scores_timeline, get_top_rejection_reasons
from state import app_state

logger = logging.getLogger("corthex")

router = APIRouter(tags=["quality"])

# ── 설정 파일 로드 유틸 (mini_server.py의 _load_config 경량 복제) ──
_CONFIG_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent / "config"

try:
    import yaml as _yaml
except ImportError:
    _yaml = None


def _load_config(name: str) -> dict:
    """설정 파일 로드. JSON 우선, YAML 폴백."""
    json_path = _CONFIG_DIR / f"{name}.json"
    if json_path.exists():
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    yaml_path = _CONFIG_DIR / f"{name}.yaml"
    if _yaml is not None and yaml_path.exists():
        try:
            return _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_config_file(name: str, data: dict) -> None:
    """설정 변경을 DB에 저장. (재배포해도 유지됨)"""
    save_setting(f"config_{name}", data)


# 품질검수 규칙: DB 오버라이드 우선, 없으면 파일에서 로드
_QUALITY_RULES: dict = load_setting("config_quality_rules") or _load_config("quality_rules")

# 부서 ID → 한국어 이름 매핑
_DIVISION_LABELS: dict[str, str] = {
    "default": "기본 (전체 공통)",
    "secretary": "비서실",
    "leet_master.tech": "기술개발팀 (CTO)",
    "leet_master.strategy": "전략기획팀 (CSO)",
    "leet_master.legal": "법무팀 (CLO)",
    "leet_master.marketing": "마케팅팀 (CMO)",
    "finance.investment": "금융분석팀 (CIO)",
    "publishing": "콘텐츠팀 (CPO)",
}

# 부서 목록 (default 제외)
_KNOWN_DIVISIONS: list[str] = [
    "secretary",
    "leet_master.tech",
    "leet_master.strategy",
    "leet_master.legal",
    "leet_master.marketing",
    "finance.investment",
    "publishing",
]


@router.get("/api/quality")
async def get_quality():
    """품질검수 통계 반환 (DB 영구 통계 + 메모리 세션 통계 병합)."""
    db_stats = get_quality_stats()
    if app_state.quality_gate:
        mem = app_state.quality_gate.stats
        db_stats["session_retried"] = mem.total_retried
        db_stats["session_retry_success_rate"] = mem.retry_success_rate
        db_stats["rejections_by_agent"] = mem.rejections_by_agent
    return db_stats


@router.get("/api/quality-rules")
async def get_quality_rules():
    rules = _QUALITY_RULES.get("rules", {})
    rubrics = _QUALITY_RULES.get("rubrics", {})
    common_checklist = _QUALITY_RULES.get("common_checklist", {"required": [], "optional": []})
    pass_criteria = _QUALITY_RULES.get("pass_criteria", {"all_required_pass": True, "min_average_score": 3.0})
    return {
        "rules": rules,
        "rubrics": rubrics,
        "common_checklist": common_checklist,
        "pass_criteria": pass_criteria,
        "known_divisions": _KNOWN_DIVISIONS,
        "division_labels": _DIVISION_LABELS,
    }


# ── 품질검수: 루브릭 저장/삭제 + 규칙 저장 ──

@router.put("/api/quality-rules/rubric/{division}")
async def save_rubric(division: str, request: Request):
    """부서별 루브릭(검수 기준) 저장 — 하이브리드 구조 지원."""
    body = await request.json()
    rubric = {
        "name": body.get("name", ""),
        "department_checklist": body.get("department_checklist", {"required": [], "optional": []}),
        "scoring": body.get("scoring", []),
    }
    # 레거시 호환: prompt 필드가 있으면 유지
    if body.get("prompt"):
        rubric["prompt"] = body["prompt"]
    if "rubrics" not in _QUALITY_RULES:
        _QUALITY_RULES["rubrics"] = {}
    _QUALITY_RULES["rubrics"][division] = rubric
    _save_config_file("quality_rules", _QUALITY_RULES)
    # 품질검수 게이트에 변경 반영
    if app_state.quality_gate:
        app_state.quality_gate.reload_config()
    return {"success": True, "division": division}


@router.delete("/api/quality-rules/rubric/{division}")
async def delete_rubric(division: str):
    """부서별 루브릭 삭제 (default는 삭제 불가)."""
    if division == "default":
        return {"success": False, "error": "기본 루브릭은 삭제할 수 없습니다"}
    rubrics = _QUALITY_RULES.get("rubrics", {})
    if division in rubrics:
        del rubrics[division]
        _save_config_file("quality_rules", _QUALITY_RULES)
    return {"success": True}


@router.put("/api/quality-rules/model")
async def save_review_model(request: Request):
    """검수 모델 설정 (비활성화 — 각 매니저가 자기 모델 사용)."""
    return {
        "success": True,
        "info": "각 매니저가 자기 모델로 검수합니다. 별도 검수 모델 설정 불필요.",
    }


@router.put("/api/quality-rules/rules")
async def save_quality_rules(request: Request):
    """품질검수 규칙 저장 (최소 길이, 재시도 횟수 등)."""
    body = await request.json()
    if "rules" not in _QUALITY_RULES:
        _QUALITY_RULES["rules"] = {}
    for key in ("min_length", "max_retry", "check_hallucination", "check_relevance"):
        if key in body:
            _QUALITY_RULES["rules"][key] = body[key]
    _save_config_file("quality_rules", _QUALITY_RULES)
    if app_state.quality_gate:
        app_state.quality_gate.reload_config()
    return {"success": True}


# ── 품질 점수 타임라인 (대시보드용) ──

@router.get("/api/quality/scores")
async def get_quality_scores(request: Request):
    """에이전트별 품질 점수 타임라인 조회 (Chart.js 대시보드용).

    Query params:
      - days: 최근 N일 (기본 30)
      - agent_id: 특정 에이전트 필터 (옵션)
    """
    days = int(request.query_params.get("days", "30"))
    agent_id = request.query_params.get("agent_id", "")
    timeline = get_quality_scores_timeline(days=days, agent_id=agent_id)

    # 에이전트별 그룹화 (Chart.js datasets용)
    by_agent: dict[str, list] = {}
    for row in timeline:
        aid = row["target_id"]
        if aid not in by_agent:
            by_agent[aid] = []
        by_agent[aid].append({
            "score": row["weighted_score"],
            "passed": row["passed"],
            "date": row["created_at"],
        })

    return {
        "timeline": timeline,
        "by_agent": by_agent,
        "agent_ids": list(by_agent.keys()),
        "total_reviews": len(timeline),
    }


@router.get("/api/quality/top-rejections")
async def get_top_rejections():
    """가장 많이 반려된 항목 Top 5 조회."""
    return {"rejections": get_top_rejection_reasons(limit=5)}
