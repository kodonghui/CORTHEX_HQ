"""
위임 분석 도구 (Delegation Analyzer) — CEO의 업무 위임을 체계적으로 분석하고 최적 위임 전략을 추천합니다.

경영학 위임 이론 5개를 기반으로,
수행자 준비도 진단 → 위임 수준 결정 → 역위임 탐지 → 시간 용량 분석 → 실행 계획 수립까지
업무 위임의 전 과정을 과학적으로 지원합니다.

학술 근거:
  - Hersey & Blanchard (1977) "Situational Leadership"
    — 부하의 능력(Competence) x 의지(Commitment)에 따른 4단계 리더십 스타일
  - Tannenbaum & Schmidt (1958) "Leadership Continuum"
    — Tell → Sell → Consult → Join → Advise → Inquire → Delegate 7단계
  - Oncken & Wass (1974) "Who's Got the Monkey?"
    — 업무 원숭이 비유: 위임한 업무가 다시 상사에게 돌아오는 역위임 문제
  - Drucker (1967) "The Effective Executive"
    — 경영자의 시간은 조직의 것. 위임 가능 업무에 시간 낭비 금지
  - Eisenhower Matrix (위임 응용)
    — Q3(긴급+비중요)는 반드시 위임, Q1(긴급+중요)만 직접 수행

사용 방법:
  - action="readiness"       : 수행자 준비도 분석 (Hersey-Blanchard)
  - action="spectrum"        : 위임 수준 결정 (Tannenbaum-Schmidt 7단계)
  - action="monkey"          : 역위임(Monkey) 탐지 (Oncken & Wass)
  - action="capacity"        : 위임 용량 분석 (Drucker + Eisenhower)
  - action="plan"            : 위임 실행 계획 생성 (RACI + 대화 스크립트)
  - action="full"            : 위 5개 종합 분석

필요 환경변수: 없음
필요 라이브러리: 없음 (순수 Python)
"""
from __future__ import annotations

import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.delegation_analyzer")


# ═══════════════════════════════════════════════════════
#  유틸리티 함수
# ═══════════════════════════════════════════════════════

def _clamp(val: float, lo: float, hi: float) -> float:
    """값을 [lo, hi] 범위로 제한합니다."""
    return max(lo, min(hi, val))


def _mean(vals: list) -> float:
    """리스트 평균. 비어 있으면 0.0."""
    return sum(vals) / len(vals) if vals else 0.0


# ═══════════════════════════════════════════════════════
#  상수 데이터 (학술 이론 기반)
# ═══════════════════════════════════════════════════════

# Hersey & Blanchard (1977) — 4단계 준비도 + 리더십 스타일
READINESS_LEVELS: dict[str, dict] = {
    "D1": {
        "label": "D1 — 낮은 능력, 높은 의지",
        "style": "Directing (지시형)",
        "description": "열정은 있지만 경험이 부족한 단계. 구체적 지시와 밀착 감독이 필요.",
        "leader_behavior": "높은 과업 행동 + 낮은 관계 행동",
        "actions": [
            "구체적인 단계별 지시서 작성",
            "체크포인트를 자주 설정 (매일 or 이틀에 한 번)",
            "실수를 비난하지 않되, 즉시 교정 피드백",
            "작은 성공 경험을 만들어 자신감 형성",
        ],
    },
    "D2": {
        "label": "D2 — 약간의 능력, 낮은 의지",
        "style": "Coaching (코칭형)",
        "description": "경험은 쌓였지만 좌절이나 회의감이 있는 단계. 설명과 격려가 필요.",
        "leader_behavior": "높은 과업 행동 + 높은 관계 행동",
        "actions": [
            "왜 이 업무가 중요한지 의미를 설명",
            "의견을 묻고 존중 (일방적 지시 X)",
            "어려움을 공감하되, 해결책은 함께 찾기",
            "성장 가능성을 구체적으로 피드백",
        ],
    },
    "D3": {
        "label": "D3 — 높은 능력, 변동하는 의지",
        "style": "Supporting (지원형)",
        "description": "능력은 충분하지만 자신감이나 동기가 불안정한 단계. 함께 결정하고 자율을 확대.",
        "leader_behavior": "낮은 과업 행동 + 높은 관계 행동",
        "actions": [
            "결정을 함께 내리되 수행자가 주도",
            "'어떻게 하면 좋겠어?'로 의견 먼저 구하기",
            "실패해도 괜찮다는 심리적 안전감 제공",
            "성과를 공개적으로 인정",
        ],
    },
    "D4": {
        "label": "D4 — 높은 능력, 높은 의지",
        "style": "Delegating (위임형)",
        "description": "능력과 의지 모두 충분. 완전히 위임하고 결과만 확인.",
        "leader_behavior": "낮은 과업 행동 + 낮은 관계 행동",
        "actions": [
            "목표와 기한만 전달, 방법은 자율",
            "체크포인트는 마일스톤 기준 (매일 X)",
            "문제가 생기면 알려달라고만 전달",
            "결과 보고 후 칭찬 + 다음 도전 기회 제공",
        ],
    },
}

# Tannenbaum & Schmidt (1958) — 7단계 위임 스펙트럼
DELEGATION_SPECTRUM: list[dict] = [
    {"level": 1, "name": "Tell (명령)", "desc": "결정을 내리고 통보. 의견 불필요.", "autonomy": "최소"},
    {"level": 2, "name": "Sell (설득)", "desc": "결정을 내리고 이유를 설명. 수용 유도.", "autonomy": "낮음"},
    {"level": 3, "name": "Consult (상담)", "desc": "의견을 먼저 듣고 최종 결정은 리더.", "autonomy": "약간"},
    {"level": 4, "name": "Join (합의)", "desc": "함께 논의하여 합의로 결정.", "autonomy": "중간"},
    {"level": 5, "name": "Advise (조언)", "desc": "수행자가 결정, 리더는 조언만.", "autonomy": "높음"},
    {"level": 6, "name": "Inquire (확인)", "desc": "수행자가 결정 + 실행, 결과만 보고.", "autonomy": "매우 높음"},
    {"level": 7, "name": "Delegate (완전위임)", "desc": "수행자가 전적 판단. 보고 불필요.", "autonomy": "최대"},
]

# Oncken & Wass (1974) — 역위임(Monkey) 패턴
MONKEY_PATTERNS: dict[str, dict] = {
    "confirm": {
        "label": "확인 요청 패턴",
        "signal": "'확인해주세요', '검토 부탁드립니다'",
        "severity": "정상",
        "description": "완성된 결과물에 대한 최종 승인 요청. 이것은 역위임이 아니라 정상 프로세스.",
    },
    "how_to": {
        "label": "방법 질문 패턴",
        "signal": "'어떻게 할까요?', '이걸 어떻게 처리하죠?'",
        "severity": "역위임 주의",
        "description": "의사결정 원숭이가 CEO에게 되돌아옴. 수행자가 선택지를 가져와야 함.",
    },
    "problem_only": {
        "label": "문제만 보고 패턴",
        "signal": "'문제가 있어요', '이게 안 돼요'",
        "severity": "역위임 심각",
        "description": "해결책 없이 문제만 전달. 원숭이가 완전히 CEO 어깨 위로 올라옴.",
    },
    "passive_wait": {
        "label": "수동 대기 패턴",
        "signal": "'지시해주시면 하겠습니다', '시키시는 대로'",
        "severity": "역위임 만성",
        "description": "자발적 판단 포기. CEO가 모든 결정을 내려야 함. 가장 심각한 역위임 유형.",
    },
}

# 역위임 탈출 5단계 (Oncken & Wass)
MONKEY_ESCAPE_STEPS: list[dict] = [
    {"step": 1, "name": "문제를 질문으로", "action": "'이 문제에 대해 어떤 선택지가 있을까요?' 되묻기"},
    {"step": 2, "name": "선택지 요청", "action": "'2~3가지 해결 방안을 가져와 주세요' 요청"},
    {"step": 3, "name": "추천안 요청", "action": "'가장 좋다고 생각하는 방안과 이유를 알려주세요' 요청"},
    {"step": 4, "name": "실행 후 보고", "action": "'본인 판단대로 실행하고 결과를 알려주세요' 지시"},
    {"step": 5, "name": "자율 실행", "action": "'이 영역은 전적으로 맡기겠습니다. 이슈 있을 때만 보고' 선언"},
]

# Drucker/Eisenhower — 시간 배분 기준
DRUCKER_THRESHOLDS: dict[str, Any] = {
    "delegation_warning": 0.25,  # CEO 시간의 25% 이상이 위임 가능이면 경고
    "strategic_minimum": 0.40,   # CEO 시간의 최소 40%는 전략적 업무에 써야 함
    "labels": {
        "under_delegating": "위임 부족 — CEO가 위임 가능한 업무를 직접 하고 있음",
        "balanced": "균형 — 위임과 직접 수행이 적절히 분배됨",
        "effective": "효과적 — 전략적 업무에 집중할 수 있는 시간이 확보됨",
    },
}


# ═══════════════════════════════════════════════════════
#  DelegationAnalyzerTool
# ═══════════════════════════════════════════════════════

class DelegationAnalyzerTool(BaseTool):
    """위임 분석 도구 — Hersey-Blanchard 상황리더십 + Tannenbaum-Schmidt 위임 스펙트럼 +
    Oncken & Wass 역위임 탐지 + Drucker 시간관리 기반으로 최적의 업무 위임 전략을 수립합니다."""

    # ── 메인 디스패처 ────────────────────────

    async def execute(self, **kwargs: Any) -> dict:
        action = kwargs.get("action", "full")
        dispatch = {
            "readiness": self._readiness,
            "spectrum": self._spectrum,
            "monkey": self._monkey,
            "capacity": self._capacity,
            "plan": self._plan,
            "full": self._full,
        }
        handler = dispatch.get(action, self._full)
        return await handler(kwargs)

    # ── 1) 수행자 준비도 분석 (Hersey-Blanchard) ────────

    async def _readiness(self, params: dict) -> dict:
        tasks = params.get("tasks", [])
        if not tasks:
            tasks = [{"task_name": "예시 업무", "assignee": "미지정", "competence": 5, "commitment": 5}]

        analysis = []
        for t in tasks:
            comp = _clamp(float(t.get("competence", 5)), 1.0, 10.0)
            commit = _clamp(float(t.get("commitment", 5)), 1.0, 10.0)

            # D1~D4 판정
            if comp <= 5 and commit > 5:
                level_key = "D1"
            elif comp <= 5 and commit <= 5:
                level_key = "D2"
            elif comp > 5 and commit <= 5:
                level_key = "D3"
            else:
                level_key = "D4"

            level_info = READINESS_LEVELS[level_key]
            analysis.append({
                "task_name": t.get("task_name", "미명시"),
                "assignee": t.get("assignee", "미지정"),
                "competence": comp,
                "commitment": commit,
                "readiness_level": level_key,
                "readiness_label": level_info["label"],
                "leadership_style": level_info["style"],
                "description": level_info["description"],
                "leader_behavior": level_info["leader_behavior"],
                "recommended_actions": level_info["actions"],
            })

        result = {
            "task_count": len(analysis),
            "analysis": analysis,
            "summary": {
                "D1_count": sum(1 for a in analysis if a["readiness_level"] == "D1"),
                "D2_count": sum(1 for a in analysis if a["readiness_level"] == "D2"),
                "D3_count": sum(1 for a in analysis if a["readiness_level"] == "D3"),
                "D4_count": sum(1 for a in analysis if a["readiness_level"] == "D4"),
            },
        }

        analysis_text = "\n".join(
            f"- {a['task_name']} ({a['assignee']}): 능력 {a['competence']}/10, "
            f"의지 {a['commitment']}/10 → {a['readiness_level']} {a['leadership_style']}"
            for a in analysis
        )

        sys_prompt = (
            "당신은 Hersey & Blanchard의 상황리더십(Situational Leadership) 전문가입니다. "
            "수행자의 능력과 의지 수준에 따라 최적의 리더십 스타일을 추천하고, "
            "CEO가 각 팀원에게 어떻게 접근해야 하는지 구체적으로 안내합니다."
        )
        user_prompt = (
            f"수행자 준비도 분석 결과:\n{analysis_text}\n\n"
            "각 업무-수행자 조합에 대해:\n"
            "1. 현재 준비도 진단 근거\n"
            "2. CEO가 취해야 할 구체적 행동 3가지\n"
            "3. 이 수행자를 D4(완전위임)로 성장시키기 위한 로드맵\n"
            "을 실무적으로 작성해 주세요."
        )
        llm = await self._llm_call(sys_prompt, user_prompt)

        return {"status": "success", "result": result, "llm_interpretation": llm}

    # ── 2) 위임 수준 결정 (Tannenbaum-Schmidt 7단계) ──

    async def _spectrum(self, params: dict) -> dict:
        tasks = params.get("tasks", [])
        if not tasks:
            tasks = [{"task_name": "예시 업무", "risk_level": 5, "reversibility": 5, "assignee_experience": 5}]

        analysis = []
        for t in tasks:
            risk = _clamp(float(t.get("risk_level", 5)), 1.0, 10.0)
            reversibility = _clamp(float(t.get("reversibility", 5)), 1.0, 10.0)
            experience = _clamp(float(t.get("assignee_experience", 5)), 1.0, 10.0)

            # 위임 수준 점수 계산
            # reversibility 높을수록 + experience 높을수록 → 위임 수준 UP
            # risk 높을수록 → 위임 수준 DOWN
            raw_score = reversibility * 0.3 + experience * 0.4 - risk * 0.3
            # raw_score 범위: -3.0(최악) ~ +7.0(최고) → 1~7 스케일로 매핑
            normalized = (raw_score + 3.0) / 10.0  # 0.0 ~ 1.0
            level_idx = int(_clamp(math.floor(normalized * 7), 0, 6))
            level_info = DELEGATION_SPECTRUM[level_idx]

            analysis.append({
                "task_name": t.get("task_name", "미명시"),
                "risk_level": risk,
                "reversibility": reversibility,
                "assignee_experience": experience,
                "raw_score": round(raw_score, 2),
                "delegation_level": level_info["level"],
                "delegation_name": level_info["name"],
                "delegation_desc": level_info["desc"],
                "autonomy": level_info["autonomy"],
            })

        result = {
            "task_count": len(analysis),
            "analysis": analysis,
            "spectrum_reference": DELEGATION_SPECTRUM,
        }

        analysis_text = "\n".join(
            f"- {a['task_name']}: 리스크 {a['risk_level']}, 되돌림 가능성 {a['reversibility']}, "
            f"경험 {a['assignee_experience']} → Lv.{a['delegation_level']} {a['delegation_name']}"
            for a in analysis
        )

        sys_prompt = (
            "당신은 Tannenbaum & Schmidt의 리더십 연속체(Leadership Continuum) 전문가입니다. "
            "업무의 리스크, 되돌림 가능성, 수행자 경험을 종합하여 "
            "7단계 중 최적의 위임 수준을 추천합니다."
        )
        user_prompt = (
            f"위임 수준 분석 결과:\n{analysis_text}\n\n"
            "각 업무에 대해:\n"
            "1. 이 위임 수준이 적절한 이유\n"
            "2. CEO가 실제로 할 말 (예시 대화문)\n"
            "3. 위임 수준을 한 단계 올리려면 필요한 조건\n"
            "을 실무적으로 작성해 주세요."
        )
        llm = await self._llm_call(sys_prompt, user_prompt)

        return {"status": "success", "result": result, "llm_interpretation": llm}

    # ── 3) 역위임(Monkey) 탐지 ────────────────────

    async def _monkey(self, params: dict) -> dict:
        tasks = params.get("tasks", [])
        if not tasks:
            tasks = [{
                "task_name": "예시 업무", "original_owner": "팀원A",
                "current_owner": "CEO", "reason_returned": "어떻게 할까요?",
                "times_returned": 2,
            }]

        analysis = []
        total_monkeys = 0
        severe_count = 0

        for t in tasks:
            reason = t.get("reason_returned", "")
            times = int(t.get("times_returned", 0))
            original = t.get("original_owner", "미지정")
            current = t.get("current_owner", "CEO")

            # 패턴 감지
            detected_pattern = "confirm"  # 기본: 정상
            reason_lower = reason.lower() if reason else ""

            if any(kw in reason_lower for kw in ["어떻게", "방법", "how", "뭘 해야"]):
                detected_pattern = "how_to"
            elif any(kw in reason_lower for kw in ["문제", "안 돼", "에러", "오류", "막혀"]):
                detected_pattern = "problem_only"
            elif any(kw in reason_lower for kw in ["시키시면", "지시", "말씀해주시면", "대로"]):
                detected_pattern = "passive_wait"
            elif any(kw in reason_lower for kw in ["확인", "검토", "승인", "리뷰"]):
                detected_pattern = "confirm"

            pattern_info = MONKEY_PATTERNS[detected_pattern]
            is_monkey = detected_pattern != "confirm"
            is_severe = times >= 3 or detected_pattern == "passive_wait"

            if is_monkey:
                total_monkeys += 1
            if is_severe:
                severe_count += 1

            # 탈출 전략: 현재 패턴에 따라 시작 단계 결정
            escape_start = {"confirm": 5, "how_to": 2, "problem_only": 1, "passive_wait": 1}
            recommended_steps = [s for s in MONKEY_ESCAPE_STEPS if s["step"] >= escape_start[detected_pattern]]

            analysis.append({
                "task_name": t.get("task_name", "미명시"),
                "original_owner": original,
                "current_owner": current,
                "reason_returned": reason,
                "times_returned": times,
                "detected_pattern": pattern_info["label"],
                "pattern_severity": pattern_info["severity"],
                "pattern_description": pattern_info["description"],
                "is_reverse_delegation": is_monkey,
                "is_severe": is_severe,
                "escape_steps": recommended_steps,
            })

        result = {
            "task_count": len(analysis),
            "total_monkeys": total_monkeys,
            "severe_count": severe_count,
            "monkey_rate": round(total_monkeys / len(analysis) * 100, 1) if analysis else 0,
            "analysis": analysis,
            "escape_framework": MONKEY_ESCAPE_STEPS,
        }

        analysis_text = "\n".join(
            f"- {a['task_name']} ({a['original_owner']}→{a['current_owner']}): "
            f"사유: '{a['reason_returned']}' | 반환 {a['times_returned']}회 | "
            f"{a['detected_pattern']} [{a['pattern_severity']}]"
            for a in analysis
        )

        sys_prompt = (
            "당신은 Oncken & Wass의 'Who's Got the Monkey?' 이론 전문가입니다. "
            "CEO에게 되돌아온 업무(역위임)를 탐지하고, "
            "원숭이를 원래 주인에게 돌려보내는 구체적 전략을 제시합니다. "
            "목표: CEO의 어깨 위 원숭이를 0마리로 만드는 것."
        )
        user_prompt = (
            f"역위임 분석 결과:\n{analysis_text}\n"
            f"역위임 비율: {result['monkey_rate']}% ({total_monkeys}/{len(analysis)}건)\n"
            f"심각 건수: {severe_count}건\n\n"
            "분석해 주세요:\n"
            "1. 가장 시급히 해결해야 할 역위임 건 (우선순위)\n"
            "2. 각 건에 대한 구체적 탈출 대화 예시\n"
            "3. 역위임을 근본적으로 방지하기 위한 조직 문화 개선 방안 2가지"
        )
        llm = await self._llm_call(sys_prompt, user_prompt)

        return {"status": "success", "result": result, "llm_interpretation": llm}

    # ── 4) 위임 용량 분석 (Drucker + Eisenhower) ────

    async def _capacity(self, params: dict) -> dict:
        ceo_tasks = params.get("ceo_tasks", [])
        if not ceo_tasks:
            ceo_tasks = [
                {"task_name": "전략 기획", "hours_per_week": 10, "delegatable": False},
                {"task_name": "보고서 검토", "hours_per_week": 8, "delegatable": True, "delegate_to": "비서실장"},
                {"task_name": "미팅 일정 관리", "hours_per_week": 5, "delegatable": True, "delegate_to": "비서"},
            ]

        total_hours = 0.0
        delegatable_hours = 0.0
        non_delegatable_hours = 0.0
        delegation_candidates = []

        for t in ceo_tasks:
            hours = float(t.get("hours_per_week", 0))
            is_delegatable = t.get("delegatable", False)
            total_hours += hours

            if is_delegatable:
                delegatable_hours += hours
                delegation_candidates.append({
                    "task_name": t.get("task_name", "미명시"),
                    "hours_per_week": hours,
                    "delegate_to": t.get("delegate_to", "미지정"),
                    "priority": hours,  # 시간이 많이 드는 것부터 위임 우선
                })
            else:
                non_delegatable_hours += hours

        # 위임 비율
        delegation_ratio = delegatable_hours / total_hours if total_hours > 0 else 0
        saved_hours = delegatable_hours
        strategic_ratio = non_delegatable_hours / total_hours if total_hours > 0 else 0

        # Drucker 기준 진단
        threshold = DRUCKER_THRESHOLDS["delegation_warning"]
        strategic_min = DRUCKER_THRESHOLDS["strategic_minimum"]

        if delegation_ratio >= threshold:
            diagnosis = DRUCKER_THRESHOLDS["labels"]["under_delegating"]
            health = "unhealthy"
        elif strategic_ratio >= strategic_min:
            diagnosis = DRUCKER_THRESHOLDS["labels"]["effective"]
            health = "healthy"
        else:
            diagnosis = DRUCKER_THRESHOLDS["labels"]["balanced"]
            health = "moderate"

        # 위임 후보 우선순위 정렬 (시간 많이 드는 순)
        delegation_candidates.sort(key=lambda x: x["priority"], reverse=True)

        result = {
            "total_hours_per_week": round(total_hours, 1),
            "delegatable_hours": round(delegatable_hours, 1),
            "non_delegatable_hours": round(non_delegatable_hours, 1),
            "delegation_ratio": round(delegation_ratio * 100, 1),
            "strategic_ratio": round(strategic_ratio * 100, 1),
            "potential_saved_hours": round(saved_hours, 1),
            "diagnosis": diagnosis,
            "health": health,
            "delegation_candidates": delegation_candidates,
            "drucker_thresholds": DRUCKER_THRESHOLDS,
        }

        tasks_text = "\n".join(
            f"- {t.get('task_name', '?')}: 주 {t.get('hours_per_week', 0)}시간 "
            f"({'위임 가능 → ' + t.get('delegate_to', '?') if t.get('delegatable') else '직접 수행'})"
            for t in ceo_tasks
        )

        sys_prompt = (
            "당신은 Drucker의 시간관리 이론과 Eisenhower Matrix 전문가입니다. "
            "CEO의 시간 배분을 분석하여, 위임해야 할 업무를 식별하고 "
            "전략적 업무에 집중할 수 있는 시간을 확보하는 방안을 제시합니다."
        )
        user_prompt = (
            f"CEO 주간 업무:\n{tasks_text}\n\n"
            f"총 {total_hours}시간 중 위임 가능: {delegatable_hours}시간 ({delegation_ratio*100:.1f}%)\n"
            f"진단: {diagnosis}\n\n"
            "분석해 주세요:\n"
            "1. 현재 시간 배분의 문제점\n"
            "2. 즉시 위임해야 할 업무 TOP 3 (시간 절약 효과순)\n"
            "3. 위임 후 확보된 시간으로 CEO가 집중해야 할 전략적 업무\n"
            "4. 주간 이상적 시간 배분 비율 제안"
        )
        llm = await self._llm_call(sys_prompt, user_prompt)

        return {"status": "success", "result": result, "llm_interpretation": llm}

    # ── 5) 위임 실행 계획 생성 (RACI + 대화 스크립트) ──

    async def _plan(self, params: dict) -> dict:
        tasks = params.get("tasks", [])
        if not tasks:
            tasks = [{"task_name": "예시 업무", "assignee": "팀원A", "competence": 7, "commitment": 8}]

        # 각 태스크별 RACI 생성
        raci_matrix = []
        for t in tasks:
            comp = _clamp(float(t.get("competence", 5)), 1.0, 10.0)
            commit = _clamp(float(t.get("commitment", 5)), 1.0, 10.0)

            # 준비도 기반 RACI 역할 배분
            if comp > 5 and commit > 5:
                # D4: 수행자가 R+A, CEO는 I만
                raci = {"R": t.get("assignee", "수행자"), "A": t.get("assignee", "수행자"), "C": "-", "I": "CEO"}
            elif comp > 5:
                # D3: 수행자 R, CEO와 공동 A
                raci = {"R": t.get("assignee", "수행자"), "A": "CEO + 수행자", "C": "CEO", "I": "팀"}
            elif commit > 5:
                # D1: 수행자 R, CEO A+C
                raci = {"R": t.get("assignee", "수행자"), "A": "CEO", "C": "CEO", "I": "팀"}
            else:
                # D2: CEO 깊이 관여
                raci = {"R": t.get("assignee", "수행자"), "A": "CEO", "C": "CEO + 멘토", "I": "팀"}

            raci_matrix.append({
                "task_name": t.get("task_name", "미명시"),
                "assignee": t.get("assignee", "미지정"),
                "competence": comp,
                "commitment": commit,
                "raci": raci,
            })

        result = {
            "task_count": len(raci_matrix),
            "raci_matrix": raci_matrix,
            "raci_legend": {
                "R": "Responsible (실행 책임) — 실제로 업무를 수행하는 사람",
                "A": "Accountable (최종 책임) — 결과에 대한 최종 승인권자",
                "C": "Consulted (자문) — 의견을 구하는 대상 (양방향 소통)",
                "I": "Informed (통보) — 결과를 통보받는 대상 (단방향)",
            },
        }

        raci_text = "\n".join(
            f"- {r['task_name']} → {r['assignee']} (능력 {r['competence']}, 의지 {r['commitment']})\n"
            f"  RACI: R={r['raci']['R']}, A={r['raci']['A']}, C={r['raci']['C']}, I={r['raci']['I']}"
            for r in raci_matrix
        )

        sys_prompt = (
            "당신은 업무 위임 실행 전문 코치입니다. "
            "RACI 매트릭스 기반의 역할 배분과 함께, "
            "CEO가 수행자에게 업무를 위임할 때 실제로 할 수 있는 대화 스크립트를 작성합니다. "
            "Hersey-Blanchard 상황리더십과 Tannenbaum-Schmidt 위임 스펙트럼을 적용합니다."
        )
        user_prompt = (
            f"위임 실행 계획:\n{raci_text}\n\n"
            "각 업무에 대해:\n"
            "1. 위임 대화 스크립트 (CEO↔수행자 실제 대화 예시, 3~4턴)\n"
            "2. 체크포인트 일정 (언제, 무엇을, 어떻게 확인할지)\n"
            "3. 위임 성공/실패 판단 기준\n"
            "4. 문제 발생 시 에스컬레이션 규칙\n"
            "을 실무적으로 작성해 주세요."
        )
        llm = await self._llm_call(sys_prompt, user_prompt)

        return {"status": "success", "result": result, "llm_plan": llm}

    # ── 6) 종합 분석 ────────────────────────────

    async def _full(self, params: dict) -> dict:
        results = {}

        # 1단계: 수행자 준비도
        results["readiness"] = await self._readiness(params)

        # 2단계: 위임 수준 결정
        results["spectrum"] = await self._spectrum(params)

        # 3단계: 역위임 탐지
        results["monkey"] = await self._monkey(params)

        # 4단계: 위임 용량 분석
        results["capacity"] = await self._capacity(params)

        # 5단계: 실행 계획
        results["plan"] = await self._plan(params)

        # 종합 요약 LLM
        monkey_rate = results["monkey"]["result"]["monkey_rate"]
        delegation_ratio = results["capacity"]["result"]["delegation_ratio"]
        health = results["capacity"]["result"]["health"]

        sys_prompt = (
            "당신은 CEO 업무 위임 총괄 컨설턴트입니다. "
            "5가지 분석(준비도/위임수준/역위임/용량/실행계획)을 종합하여 "
            "CEO가 즉시 실행할 수 있는 위임 전략을 1페이지로 요약합니다."
        )
        user_prompt = (
            f"분석 결과 요약:\n"
            f"- 역위임 비율: {monkey_rate}%\n"
            f"- 위임 가능 비율: {delegation_ratio}%\n"
            f"- 시간 건강도: {health}\n\n"
            "CEO를 위한 1페이지 위임 전략을 작성해 주세요:\n"
            "1. [현황] CEO 위임 상태 한 줄 진단\n"
            "2. [즉시 실행] 이번 주에 바로 위임할 업무 TOP 3\n"
            "3. [역위임 대응] 원숭이를 돌려보내기 위한 이번 주 행동 1가지\n"
            "4. [성장 로드맵] 1개월 후 목표 위임 비율\n"
            "5. [주의사항] 위임 시 절대 해서는 안 되는 실수 1가지"
        )
        llm_summary = await self._llm_call(sys_prompt, user_prompt)

        return {"status": "success", "results": results, "llm_summary": llm_summary}
