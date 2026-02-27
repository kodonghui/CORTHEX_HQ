"""
위기 소통 도구 (Risk Communicator) — 위기 상황에서 최적의 대응 메시지와 소통 전략을 생성합니다.

위기관리 커뮤니케이션 분야의 핵심 이론 5개를 기반으로,
위기 유형 평가 → 대응 메시지 작성 → 타임라인 계획 → 이해관계자별 소통 → 사후 분석까지
위기 대응의 전 과정을 체계적으로 지원합니다.

학술 근거:
  - Coombs (2007) "Situational Crisis Communication Theory (SCCT)"
    — 위기 유형(victim/accidental/preventable)별 최적 대응 전략 매칭
  - Benoit (1997) "Image Repair Theory"
    — 이미지 복구 5전략 14전술 체계
  - Fink (1986) Crisis Lifecycle
    — 4단계: Prodromal(전조) → Acute(급성) → Chronic(만성) → Resolution(해소)
  - Seeger, Sellnow & Ulmer (2003) "Best Practices in Crisis Communication"
    — 위기 소통 10대 원칙
  - Reynolds & Seeger (2005) "Crisis and Emergency Risk Communication (CERC)"
    — 위기 단계별 커뮤니케이션 전략

사용 방법:
  - action="assess"          : 위기 심각도 평가 (SCCT 기반)
  - action="response"        : 대응 메시지 생성 (Benoit Image Repair)
  - action="timeline"        : 위기 타임라인 계획 (Fink Lifecycle)
  - action="stakeholder_msg" : 이해관계자별 맞춤 메시지 생성
  - action="post_crisis"     : 위기 후 분석 (교훈 추출, AAR)
  - action="full"            : 위 5개 종합 분석

필요 환경변수: 없음
필요 라이브러리: 없음 (순수 Python)
"""
from __future__ import annotations

import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.risk_communicator")


# ═══════════════════════════════════════════════════════
#  유틸리티 함수
# ═══════════════════════════════════════════════════════

def _clamp(val: float, lo: float = 0.0, hi: float = 10.0) -> float:
    """값을 [lo, hi] 범위로 제한합니다."""
    return max(lo, min(hi, val))


def _mean(vals: list) -> float:
    """리스트 평균. 비어 있으면 0.0."""
    return sum(vals) / len(vals) if vals else 0.0


# ═══════════════════════════════════════════════════════
#  상수 데이터 (학술 이론 기반)
# ═══════════════════════════════════════════════════════

# Coombs (2007) SCCT — 위기 유형별 기본 심각도 & 권장 전략
SCCT_CRISIS_TYPES: dict[str, dict] = {
    "victim": {
        "base_severity": 3,
        "label": "피해자형 (자연재해, 루머, 악의적 공격)",
        "strategy": "bolstering",
        "strategy_ko": "보강 전략 — 과거 선행·공헌을 강조",
        "actions": ["감사 표현", "피해 사실 공유", "공동체 연대 호소"],
    },
    "accidental": {
        "base_severity": 5,
        "label": "우발형 (기술적 오류, 실수, 예상치 못한 사고)",
        "strategy": "diminishing",
        "strategy_ko": "감소 전략 — 위기의 의도성·심각성을 낮춤",
        "actions": ["사실 관계 설명", "의도 없음 강조", "재발 방지 약속"],
    },
    "preventable": {
        "base_severity": 8,
        "label": "예방가능형 (관리 소홀, 규정 위반, 조직적 비행)",
        "strategy": "rebuilding",
        "strategy_ko": "재건 전략 — 진심 어린 사과 + 보상 + 근본 개혁",
        "actions": ["즉시 공식 사과", "피해 보상 발표", "외부 감사 도입", "책임자 처분"],
    },
}

# Benoit (1997) Image Repair — 5전략 14전술
BENOIT_STRATEGIES: dict[str, dict] = {
    "denial": {
        "label": "부인 (Denial)",
        "tactics": [
            {"name": "단순 부인", "desc": "행위 자체를 부인"},
            {"name": "책임 전가", "desc": "제3자에게 원인 귀속"},
        ],
        "severity_range": (1, 3),
    },
    "evasion": {
        "label": "회피 (Evasion of Responsibility)",
        "tactics": [
            {"name": "도발", "desc": "타인의 행동에 대한 반응이었음"},
            {"name": "결함", "desc": "정보 부족으로 잘못된 판단"},
            {"name": "사고", "desc": "예측 불가능한 상황이었음"},
            {"name": "선의", "desc": "좋은 의도에서 비롯된 실수"},
        ],
        "severity_range": (2, 5),
    },
    "reducing": {
        "label": "공격성 감소 (Reducing Offensiveness)",
        "tactics": [
            {"name": "보강", "desc": "과거 긍정적 이미지 환기"},
            {"name": "최소화", "desc": "피해 규모를 축소 설명"},
            {"name": "차별화", "desc": "더 나쁜 사례와 비교"},
            {"name": "초월", "desc": "더 큰 가치·맥락으로 전환"},
            {"name": "반격", "desc": "비판자의 신뢰성 공격"},
            {"name": "보상", "desc": "피해에 대한 물질적 보상"},
        ],
        "severity_range": (3, 7),
    },
    "corrective": {
        "label": "시정 조치 (Corrective Action)",
        "tactics": [
            {"name": "문제 해결", "desc": "현재 문제를 즉시 해결"},
            {"name": "재발 방지", "desc": "시스템·프로세스 개선 약속"},
        ],
        "severity_range": (4, 9),
    },
    "mortification": {
        "label": "사죄 (Mortification)",
        "tactics": [
            {"name": "공식 사과", "desc": "진심 어린 사과 + 책임 인정"},
        ],
        "severity_range": (7, 10),
    },
}

# Fink (1986) Crisis Lifecycle — 4단계
FINK_LIFECYCLE: list[dict] = [
    {
        "phase": "prodromal",
        "label": "전조기 (Prodromal)",
        "description": "위기 징후가 감지되는 단계. 아직 외부에 알려지지 않음.",
        "default_hours": "0~2시간",
        "key_actions": ["대응팀 소집", "사실 확인 착수", "내부 모니터링 강화", "초기 성명 초안 준비"],
        "channel": "내부 (경영진 + 위기대응팀)",
    },
    {
        "phase": "acute",
        "label": "급성기 (Acute)",
        "description": "위기가 공개·확산되는 단계. 미디어 관심 최고조.",
        "default_hours": "2~24시간",
        "key_actions": ["초기 공식 성명 발표", "미디어 대응 (기자회견/보도자료)", "이해관계자 직접 통보", "SNS 모니터링 + 대응"],
        "channel": "외부 (미디어, 고객, 투자자, 규제기관)",
    },
    {
        "phase": "chronic",
        "label": "만성기 (Chronic)",
        "description": "위기의 여파가 지속되는 단계. 복구 작업 진행 중.",
        "default_hours": "1일~수주",
        "key_actions": ["후속 조치 실행 + 진행 보고", "피해 보상 프로그램 운영", "내부 직원 사기 관리", "조직 개선안 실행"],
        "channel": "내부+외부 (정기 업데이트)",
    },
    {
        "phase": "resolution",
        "label": "해소기 (Resolution)",
        "description": "위기가 마무리되고 일상으로 복귀하는 단계.",
        "default_hours": "수주~수개월",
        "key_actions": ["최종 보고서 작성", "재발 방지 체계 구축", "교훈 문서화 (AAR)", "이해관계자 감사 소통"],
        "channel": "내부 (전직원 공유) + 외부 (최종 성명)",
    },
]

# 이해관계자 유형별 특성
STAKEHOLDER_PROFILES: dict[str, dict] = {
    "employee": {
        "label": "직원",
        "concern": "고용 안정, 업무 영향, 회사 미래",
        "tone": "투명하고 안심시키는 톤 — 사실 기반 + 공감",
        "channel": "내부 이메일, 전체 미팅, 인트라넷",
        "timing": "외부 발표 전 또는 동시에 (내부가 뉴스로 알면 안 됨)",
    },
    "customer": {
        "label": "고객",
        "concern": "서비스 지속성, 개인정보 보호, 보상",
        "tone": "공감 + 해결 중심 — '불편을 드려 죄송합니다' + 구체적 조치",
        "channel": "공식 공지, 앱 푸시, SNS, 고객센터 강화",
        "timing": "사실 확인 직후 최대한 빠르게 (1차: 사과 + 현황, 2차: 원인 + 보상)",
    },
    "investor": {
        "label": "투자자",
        "concern": "재무 영향, 주가, 장기 전략, 법적 리스크",
        "tone": "사실 + 수치 기반 — 감정 배제, 리스크 평가 + 대응 계획",
        "channel": "IR 공시, 이사회 보고, 기관투자자 직접 소통",
        "timing": "규정 준수 시한 내 (금감원 공시 의무 등)",
    },
    "media": {
        "label": "미디어",
        "concern": "뉴스 가치, 사실 확인, 인용 가능한 코멘트",
        "tone": "간결 + 핵심 — 해석의 여지 최소화, 인용문 준비",
        "channel": "보도자료, 기자회견, 공식 대변인 지정",
        "timing": "첫 보도 전 선제 발표가 이상적 (불가능 시 즉시 반응)",
    },
    "regulator": {
        "label": "규제기관",
        "concern": "법규 준수, 책임 소재, 시정 조치, 재발 방지",
        "tone": "공식 + 협조적 — 법률 용어, 규정 인용, 자발적 협조 강조",
        "channel": "공문, 규제당국 직접 보고, 법무팀 경유",
        "timing": "법정 보고 기한 엄수 (초과 시 가중 제재)",
    },
    "partner": {
        "label": "파트너/협력사",
        "concern": "사업 연속성, 계약 이행, 평판 연대 리스크",
        "tone": "파트너십 강조 — 투명하게 공유 + 영향 최소화 약속",
        "channel": "직접 전화/이메일 (담당자 1:1), 공동 성명 검토",
        "timing": "외부 발표 직전 사전 통보 (파트너가 뉴스로 알면 신뢰 훼손)",
    },
}


# ═══════════════════════════════════════════════════════
#  RiskCommunicatorTool
# ═══════════════════════════════════════════════════════

class RiskCommunicatorTool(BaseTool):
    """위기 소통 도구 — Coombs SCCT + Benoit Image Repair + Fink Lifecycle 기반으로
    위기 평가, 대응 메시지 작성, 타임라인 계획, 이해관계자 소통, 사후 분석을 수행합니다."""

    # ── 메인 디스패처 ────────────────────────

    async def execute(self, **kwargs: Any) -> dict:
        action = kwargs.get("action", "full")
        dispatch = {
            "assess": self._assess,
            "response": self._response,
            "timeline": self._timeline,
            "stakeholder_msg": self._stakeholder_msg,
            "post_crisis": self._post_crisis,
            "full": self._full,
        }
        handler = dispatch.get(action, self._full)
        return await handler(kwargs)

    # ── 1) 위기 심각도 평가 (SCCT) ────────────────────

    async def _assess(self, params: dict) -> dict:
        crisis_desc = params.get("crisis_description", "위기 상황 미입력")
        crisis_type = params.get("crisis_type", "accidental")
        has_history = params.get("history", False)
        reputation = params.get("reputation", "neutral")

        # SCCT 기반 위기 프로필
        profile = SCCT_CRISIS_TYPES.get(crisis_type, SCCT_CRISIS_TYPES["accidental"])
        base = profile["base_severity"]

        # 수정자 계산
        history_mod = 2.0 if has_history else 0.0
        rep_map = {"positive": -1.0, "neutral": 0.0, "negative": 1.0}
        rep_mod = rep_map.get(reputation, 0.0)

        severity = _clamp(base + history_mod + rep_mod, 1.0, 10.0)

        # 대응 수준 결정
        if severity <= 3:
            level = "모니터링"
            level_desc = "내부 모니터링 강화. 외부 성명 불필요. 징후 추적에 집중."
        elif severity <= 6:
            level = "공식 입장"
            level_desc = "공식 입장문 발표 필요. 대변인 지정 + 미디어 대응 준비."
        elif severity <= 8:
            level = "긴급 대응"
            level_desc = "위기대응팀 즉시 소집. CEO 직접 소통. 24시간 모니터링 체제."
        else:
            level = "전면 위기관리"
            level_desc = "전사적 위기관리 돌입. 외부 전문가 투입. 이사회 보고. 법무팀 즉시 가동."

        # 권장 Benoit 전략 매핑
        recommended_strategies = []
        for key, strat in BENOIT_STRATEGIES.items():
            lo, hi = strat["severity_range"]
            if lo <= severity <= hi:
                recommended_strategies.append({
                    "strategy": strat["label"],
                    "tactics": [t["name"] for t in strat["tactics"]],
                })

        result = {
            "crisis_type": crisis_type,
            "crisis_type_label": profile["label"],
            "base_severity": base,
            "history_modifier": history_mod,
            "reputation_modifier": rep_mod,
            "final_severity": round(severity, 1),
            "response_level": level,
            "response_level_description": level_desc,
            "scct_strategy": profile["strategy_ko"],
            "recommended_actions": profile["actions"],
            "benoit_strategies": recommended_strategies,
        }

        sys_prompt = (
            "당신은 위기관리 커뮤니케이션 전문가입니다. "
            "Coombs의 SCCT 이론과 Benoit의 Image Repair Theory를 기반으로 "
            "위기 상황을 분석하고 구체적인 대응 방향을 제시합니다."
        )
        user_prompt = (
            f"위기 상황: {crisis_desc}\n"
            f"위기 유형: {profile['label']}\n"
            f"심각도: {severity}/10 → 대응 수준: {level}\n"
            f"SCCT 권장 전략: {profile['strategy_ko']}\n"
            f"유사 위기 전력: {'있음' if has_history else '없음'}\n"
            f"기존 평판: {reputation}\n\n"
            "위 분석 결과를 바탕으로:\n"
            "1. 이 위기의 핵심 위험 요소 3가지\n"
            "2. 즉시 취해야 할 조치 3가지 (우선순위순)\n"
            "3. 절대 해서는 안 되는 실수 2가지\n"
            "를 구체적으로 제시해 주세요."
        )
        llm = await self._llm_call(sys_prompt, user_prompt)

        return {"status": "success", "result": result, "llm_interpretation": llm}

    # ── 2) 대응 메시지 생성 (Benoit Image Repair) ────────

    async def _response(self, params: dict) -> dict:
        crisis_type = params.get("crisis_type", "accidental")
        severity = _clamp(float(params.get("severity", 5)), 1.0, 10.0)
        key_facts = params.get("key_facts", [])
        spokesperson = params.get("spokesperson", "CEO")

        # 심각도 기반 전략 선택
        if severity <= 3:
            primary = "denial"
            secondary = "evasion"
        elif severity <= 6:
            primary = "reducing"
            secondary = "corrective"
        else:
            primary = "mortification"
            secondary = "corrective"

        p_strat = BENOIT_STRATEGIES[primary]
        s_strat = BENOIT_STRATEGIES[secondary]

        # 성명서 구조: 공감 → 사실 → 조치 → 약속 (Seeger et al. 2003)
        statement_structure = {
            "opening": "공감 표현 — 피해자·이해관계자의 감정 인정",
            "facts": "사실 전달 — 확인된 사실만 간결하게 (추측·변명 금지)",
            "action": "조치 발표 — 현재 하고 있는 구체적 조치",
            "commitment": "약속 — 재발 방지 + 투명한 후속 보고 약속",
        }

        result = {
            "severity": severity,
            "primary_strategy": {
                "name": p_strat["label"],
                "tactics": [t["name"] + ": " + t["desc"] for t in p_strat["tactics"]],
            },
            "secondary_strategy": {
                "name": s_strat["label"],
                "tactics": [t["name"] + ": " + t["desc"] for t in s_strat["tactics"]],
            },
            "statement_structure": statement_structure,
            "spokesperson": spokesperson,
            "key_facts_provided": key_facts,
        }

        facts_text = "\n".join(f"  - {f}" for f in key_facts) if key_facts else "  (제공된 사실 없음)"

        sys_prompt = (
            "당신은 위기관리 커뮤니케이션 전문 카피라이터입니다. "
            "Benoit의 Image Repair Theory와 Seeger의 Best Practices를 기반으로 "
            "위기 대응 성명서를 작성합니다. "
            "구조: 공감 → 사실 → 조치 → 약속. "
            "톤: 진정성 있고, 구체적이며, 책임감 있는 어조."
        )
        user_prompt = (
            f"위기 유형: {crisis_type} | 심각도: {severity}/10\n"
            f"주요 전략: {p_strat['label']} + {s_strat['label']}\n"
            f"대변인: {spokesperson}\n"
            f"확인된 사실:\n{facts_text}\n\n"
            "위 정보를 바탕으로 공식 대응 성명서 초안을 작성해 주세요.\n"
            "형식: 제목 + 본문(4단락: 공감/사실/조치/약속) + 맺음말.\n"
            "분량: 400~600자 내외. 한국어로 작성."
        )
        llm = await self._llm_call(sys_prompt, user_prompt)

        return {"status": "success", "result": result, "llm_statement_draft": llm}

    # ── 3) 위기 타임라인 계획 (Fink Lifecycle) ────────

    async def _timeline(self, params: dict) -> dict:
        crisis_desc = params.get("crisis_description", "위기 상황 미입력")
        detection_time = params.get("detection_time", "방금")
        severity = _clamp(float(params.get("severity", 5)), 1.0, 10.0)

        # 심각도에 따라 타임라인 압축/확장
        urgency_factor = severity / 5.0  # severity 5 = 1.0배, 10 = 2.0배(더 빠르게)

        timeline_plan = []
        for phase in FINK_LIFECYCLE:
            phase_entry = {
                "phase": phase["phase"],
                "label": phase["label"],
                "description": phase["description"],
                "default_duration": phase["default_hours"],
                "key_actions": phase["key_actions"],
                "channel": phase["channel"],
                "urgency_note": (
                    "심각도가 높아 시간 단축 필요 — 평소보다 빠르게 진행"
                    if urgency_factor > 1.2 else
                    "표준 속도로 진행 가능"
                ),
            }
            timeline_plan.append(phase_entry)

        result = {
            "crisis_description": crisis_desc,
            "detection_time": detection_time,
            "severity": severity,
            "urgency_factor": round(urgency_factor, 2),
            "lifecycle_phases": timeline_plan,
        }

        sys_prompt = (
            "당신은 위기관리 타임라인 전문가입니다. "
            "Fink의 Crisis Lifecycle (전조→급성→만성→해소) 모델과 "
            "Reynolds & Seeger의 CERC 프레임워크를 기반으로 "
            "구체적인 시간별 행동 계획을 작성합니다."
        )
        user_prompt = (
            f"위기 상황: {crisis_desc}\n"
            f"감지 시점: {detection_time}\n"
            f"심각도: {severity}/10 (긴급도 배율: {urgency_factor:.1f}x)\n\n"
            "4단계(전조/급성/만성/해소) 각각에 대해:\n"
            "1. 시작 시점 ~ 종료 시점 (구체적 시간)\n"
            "2. 담당자 (CEO, 대변인, 법무팀, PR팀 등)\n"
            "3. 핵심 메시지 키워드 3개\n"
            "4. 사용할 소통 채널\n"
            "을 시간순 표 형태로 작성해 주세요."
        )
        llm = await self._llm_call(sys_prompt, user_prompt)

        return {"status": "success", "result": result, "llm_timeline": llm}

    # ── 4) 이해관계자별 맞춤 메시지 ──────────────

    async def _stakeholder_msg(self, params: dict) -> dict:
        crisis_summary = params.get("crisis_summary", "위기 상황 요약 미입력")
        stakeholders = params.get("stakeholders", [
            {"type": "employee"}, {"type": "customer"}, {"type": "investor"},
        ])

        # 각 이해관계자 유형별 프로필 매칭
        stakeholder_analysis = []
        for sh in stakeholders:
            sh_type = sh.get("type", "customer")
            profile = STAKEHOLDER_PROFILES.get(sh_type, STAKEHOLDER_PROFILES["customer"])
            stakeholder_analysis.append({
                "type": sh_type,
                "label": profile["label"],
                "concern": profile["concern"],
                "tone": profile["tone"],
                "channel": profile["channel"],
                "timing": profile["timing"],
            })

        result = {
            "crisis_summary": crisis_summary,
            "stakeholder_count": len(stakeholder_analysis),
            "stakeholder_profiles": stakeholder_analysis,
        }

        # 이해관계자 목록 텍스트
        sh_text_parts = []
        for sa in stakeholder_analysis:
            sh_text_parts.append(
                f"[{sa['label']}] 관심사: {sa['concern']} | 톤: {sa['tone']} | "
                f"채널: {sa['channel']} | 시점: {sa['timing']}"
            )
        sh_text = "\n".join(sh_text_parts)

        sys_prompt = (
            "당신은 이해관계자 커뮤니케이션 전문가입니다. "
            "같은 위기 상황이라도 이해관계자마다 관심사, 톤, 채널이 다르므로 "
            "각 유형에 맞는 맞춤 메시지를 작성합니다. "
            "Seeger, Sellnow & Ulmer의 위기 소통 Best Practices를 준수합니다."
        )
        user_prompt = (
            f"위기 요약: {crisis_summary}\n\n"
            f"이해관계자 프로필:\n{sh_text}\n\n"
            "각 이해관계자 유형별로 맞춤 메시지를 작성해 주세요.\n"
            "형식: [유형명] → 메시지 (200~300자, 해당 톤 준수)\n"
            "주의: 같은 사실이라도 강조점과 표현이 달라야 합니다."
        )
        llm = await self._llm_call(sys_prompt, user_prompt)

        return {"status": "success", "result": result, "llm_messages": llm}

    # ── 5) 위기 후 분석 (AAR) ────────────────────

    async def _post_crisis(self, params: dict) -> dict:
        crisis_desc = params.get("crisis_description", "위기 상황 미입력")
        actions_taken = params.get("actions_taken", [])
        outcome = params.get("outcome", "결과 미입력")
        damages = params.get("damages", {})

        # After Action Review (AAR) 구조
        aar_framework = {
            "planned": "계획 — 원래 위기 대응 계획은 무엇이었는가?",
            "actual": "실제 — 실제로 어떻게 대응했는가?",
            "gap": "차이 — 계획과 실제 사이 차이의 원인은?",
            "lesson": "교훈 — 다음에 같은 상황이 오면 어떻게 할 것인가?",
        }

        # 대응 속도 평가 기준
        speed_criteria = {
            "excellent": "1시간 이내 초기 대응",
            "good": "1~6시간 이내 대응",
            "fair": "6~24시간 이내 대응",
            "poor": "24시간 초과 대응",
        }

        # 커뮤니케이션 효과성 체크리스트
        comm_checklist = [
            {"item": "초기 성명 발표 속도", "question": "위기 인지 후 몇 시간 내 첫 성명을 냈는가?"},
            {"item": "사실 정확성", "question": "발표한 내용 중 나중에 정정한 것이 있는가?"},
            {"item": "이해관계자 커버리지", "question": "모든 주요 이해관계자에게 소통했는가?"},
            {"item": "톤 일관성", "question": "모든 채널에서 메시지 톤이 일관되었는가?"},
            {"item": "후속 보고", "question": "진행 상황을 정기적으로 업데이트했는가?"},
            {"item": "내부 소통", "question": "직원들이 외부 뉴스보다 먼저 정보를 받았는가?"},
        ]

        # 재발 방지 체크리스트
        prevention_checklist = [
            "위기 대응 매뉴얼 업데이트",
            "위기 시뮬레이션 훈련 일정 수립",
            "조기 경보 시스템 점검/개선",
            "이해관계자 연락망 갱신",
            "대변인 미디어 트레이닝",
            "위기 유형별 성명서 템플릿 준비",
        ]

        result = {
            "crisis_description": crisis_desc,
            "actions_taken": actions_taken,
            "outcome": outcome,
            "damages": damages,
            "aar_framework": aar_framework,
            "speed_criteria": speed_criteria,
            "communication_checklist": comm_checklist,
            "prevention_checklist": prevention_checklist,
        }

        actions_text = "\n".join(f"  - {a}" for a in actions_taken) if actions_taken else "  (기록 없음)"
        damages_text = ", ".join(f"{k}: {v}" for k, v in damages.items()) if damages else "(미산정)"

        sys_prompt = (
            "당신은 위기 사후 분석 전문가입니다. "
            "AAR(After Action Review) 방법론을 사용하여 "
            "위기 대응의 성과와 개선점을 체계적으로 분석합니다. "
            "감정적 평가가 아닌, 프로세스 기반의 객관적 분석을 제공합니다."
        )
        user_prompt = (
            f"위기 상황: {crisis_desc}\n"
            f"취한 조치:\n{actions_text}\n"
            f"결과: {outcome}\n"
            f"피해: {damages_text}\n\n"
            "AAR 형식으로 분석해 주세요:\n"
            "1. [계획 vs 실제] 대응 계획과 실제 대응의 차이점\n"
            "2. [잘한 점] 효과적이었던 대응 3가지\n"
            "3. [개선점] 부족했던 대응 3가지 + 구체적 개선 방안\n"
            "4. [교훈] 조직이 반드시 기억해야 할 핵심 교훈 2가지\n"
            "5. [재발 방지] 향후 6개월 내 실행할 예방 조치 로드맵"
        )
        llm = await self._llm_call(sys_prompt, user_prompt)

        return {"status": "success", "result": result, "llm_analysis": llm}

    # ── 6) 종합 분석 ────────────────────────────

    async def _full(self, params: dict) -> dict:
        results = {}

        # 1단계: 위기 평가
        results["assess"] = await self._assess(params)

        # 평가 결과에서 심각도 추출하여 후속 분석에 반영
        severity = results["assess"]["result"]["final_severity"]
        params_with_severity = {**params, "severity": severity}

        # 2~4단계: 대응 메시지, 타임라인, 이해관계자 소통
        results["response"] = await self._response(params_with_severity)
        results["timeline"] = await self._timeline(params_with_severity)
        results["stakeholder_msg"] = await self._stakeholder_msg(params)

        # 5단계: 사후 분석 (아직 위기 중이면 사전 계획으로 활용)
        results["post_crisis"] = await self._post_crisis(params)

        # 종합 요약 LLM
        sys_prompt = (
            "당신은 위기관리 총괄 컨설턴트입니다. "
            "5가지 분석 결과(위기 평가/대응 메시지/타임라인/이해관계자 소통/사후 분석)를 "
            "종합하여 CEO가 즉시 행동할 수 있는 1페이지 요약을 작성합니다."
        )
        user_prompt = (
            f"위기 상황: {params.get('crisis_description', '미입력')}\n"
            f"심각도: {severity}/10\n"
            f"대응 수준: {results['assess']['result']['response_level']}\n"
            f"SCCT 전략: {results['assess']['result']['scct_strategy']}\n\n"
            "CEO를 위한 1페이지 요약을 작성해 주세요:\n"
            "1. [현황] 지금 상황 한 줄 요약\n"
            "2. [즉시 행동] 지금 당장 해야 할 것 3가지 (시간순)\n"
            "3. [대응 핵심] 외부에 전달할 핵심 메시지 1문장\n"
            "4. [타임라인] 향후 48시간 핵심 일정\n"
            "5. [위험 요소] 가장 주의해야 할 것 1가지"
        )
        llm_summary = await self._llm_call(sys_prompt, user_prompt)

        return {"status": "success", "results": results, "llm_summary": llm_summary}
