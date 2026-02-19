"""
법적 분쟁 시뮬레이터 Tool (CLO 법무IP처 소속).

법적 분쟁 시나리오 시뮬레이션 및 결과 예측, 최적 대응 전략 수립.
게임이론(Nash), 의사결정트리(Raiffa), 소송위험모델(Priest & Klein),
ADR 이론, Mnookin & Kornhauser 협상 모델 기반.

사용 방법:
  - action="simulate": 분쟁 시나리오 시뮬레이션
  - action="outcome": 분쟁 결과 예측
  - action="strategy": 최적 대응 전략 수립
  - action="cost": 분쟁 비용 추정

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬)

주의: 이 분석은 참고용이며, 실제 법적 분쟁 대응은 반드시 변호사 자문을 받으세요.
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.dispute_simulator")

_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 분석은 참고용이며, "
    "실제 법적 분쟁 대응은 반드시 변호사 자문을 받으세요."
)

# ══════════════════════════════════════════
#  분쟁 유형 데이터베이스 (6대 분류)
# ══════════════════════════════════════════

DISPUTE_TYPES: dict[str, dict[str, Any]] = {
    "민사": {
        "name": "민사 분쟁",
        "court": "지방법원 민사부",
        "typical_duration": "6개월~2년",
        "appeal_stages": "1심 -> 항소심(고등법원) -> 상고심(대법원)",
        "key_laws": ["민법", "민사소송법", "민사집행법"],
        "common_cases": [
            "계약 위반", "손해배상", "부당이득", "소유권 분쟁",
            "채권 추심", "임대차 분쟁",
        ],
    },
    "형사": {
        "name": "형사 분쟁",
        "court": "지방법원 형사부",
        "typical_duration": "3개월~1년 (수사 별도)",
        "appeal_stages": "1심 -> 항소심(고등법원) -> 상고심(대법원)",
        "key_laws": ["형법", "형사소송법", "특별형법"],
        "common_cases": [
            "사기", "횡령/배임", "명예훼손", "업무상과실",
            "저작권 침해", "영업비밀 침해",
        ],
    },
    "행정": {
        "name": "행정 분쟁",
        "court": "행정법원",
        "typical_duration": "6개월~1.5년",
        "appeal_stages": "행정심판(선택) -> 행정소송 1심 -> 항소 -> 상고",
        "key_laws": ["행정소송법", "행정심판법", "행정절차법"],
        "common_cases": [
            "인허가 취소", "과징금/과태료 부과", "행정처분 취소",
            "규제 위반 제재", "입찰 분쟁",
        ],
    },
    "중재": {
        "name": "중재 분쟁",
        "court": "대한상사중재원 (KCAB) / ICC",
        "typical_duration": "3~12개월",
        "appeal_stages": "단심 (중재판정 확정, 제한적 취소소송만 가능)",
        "key_laws": ["중재법", "뉴욕협약", "UNCITRAL 모델법"],
        "common_cases": [
            "국제 상사 분쟁", "M&A 분쟁", "건설 분쟁",
            "투자 분쟁", "기술 라이선스 분쟁",
        ],
    },
    "노동": {
        "name": "노동 분쟁",
        "court": "노동위원회 -> 법원",
        "typical_duration": "2~6개월 (노동위) + 소송 별도",
        "appeal_stages": "지방노동위 -> 중앙노동위 -> 행정소송",
        "key_laws": ["근로기준법", "노동조합법", "근로자참여법"],
        "common_cases": [
            "부당해고", "임금체불", "부당노동행위",
            "산업재해 보상", "차별 구제",
        ],
    },
    "IP": {
        "name": "지식재산 분쟁",
        "court": "특허법원 / 지방법원",
        "typical_duration": "1~3년",
        "appeal_stages": "특허심판원 -> 특허법원 -> 대법원 / 법원 1심 -> 항소 -> 상고",
        "key_laws": ["특허법", "상표법", "저작권법", "부정경쟁방지법"],
        "common_cases": [
            "특허 침해", "상표권 침해", "저작권 침해",
            "영업비밀 침해", "디자인권 침해",
        ],
    },
}

# ══════════════════════════════════════════
#  ADR(대체적 분쟁해결) 방법 비교
# ══════════════════════════════════════════

ADR_COMPARISON: list[dict[str, Any]] = [
    {
        "method": "소송",
        "duration": "6개월~3년",
        "cost": "높음 (변호사 비용 + 인지대)",
        "binding": "법적 구속력 (강제집행 가능)",
        "confidentiality": "공개 (판결문 공개)",
        "relationship": "대립적 (관계 악화 가능)",
        "suitable_for": "명확한 법적 판단 필요, 강제집행 필요",
    },
    {
        "method": "중재",
        "duration": "3~12개월",
        "cost": "중~높음 (중재비용 + 변호사 비용)",
        "binding": "법적 구속력 (뉴욕협약으로 국제 집행 가능)",
        "confidentiality": "비공개 (기밀 유지)",
        "relationship": "비교적 대립적",
        "suitable_for": "국제 분쟁, 기밀 필요, 전문성 필요",
    },
    {
        "method": "조정",
        "duration": "1~3개월",
        "cost": "낮음 (조정 수수료)",
        "binding": "당사자 합의 시 효력 (조정조서는 강제집행 가능)",
        "confidentiality": "비공개",
        "relationship": "협력적 (관계 유지 가능)",
        "suitable_for": "관계 유지 필요, 유연한 해결 원함",
    },
    {
        "method": "협상",
        "duration": "수일~수개월",
        "cost": "최저 (직접 협상 시 무료)",
        "binding": "합의서 작성 시 계약 효력",
        "confidentiality": "완전 비공개",
        "relationship": "가장 협력적",
        "suitable_for": "비용 최소화, 신속 해결, 관계 유지",
    },
]

# ══════════════════════════════════════════
#  한국 법원 통계 데이터
# ══════════════════════════════════════════

COURT_STATISTICS: dict[str, dict[str, Any]] = {
    "민사_일반": {
        "avg_duration_months": 9.2,
        "plaintiff_win_rate": 0.62,
        "settlement_rate": 0.28,
        "appeal_rate": 0.18,
        "overturn_rate": 0.12,
    },
    "특허_침해": {
        "avg_duration_months": 18.5,
        "plaintiff_win_rate": 0.35,
        "settlement_rate": 0.40,
        "appeal_rate": 0.45,
        "overturn_rate": 0.22,
    },
    "노동_부당해고": {
        "avg_duration_months": 4.5,
        "plaintiff_win_rate": 0.48,
        "settlement_rate": 0.35,
        "appeal_rate": 0.25,
        "overturn_rate": 0.15,
    },
    "행정_과징금": {
        "avg_duration_months": 12.0,
        "plaintiff_win_rate": 0.30,
        "settlement_rate": 0.10,
        "appeal_rate": 0.55,
        "overturn_rate": 0.18,
    },
    "저작권_침해": {
        "avg_duration_months": 14.0,
        "plaintiff_win_rate": 0.55,
        "settlement_rate": 0.32,
        "appeal_rate": 0.30,
        "overturn_rate": 0.15,
    },
}

# ══════════════════════════════════════════
#  비용 모델 (한국 기준 추정)
# ══════════════════════════════════════════

COST_MODEL: dict[str, dict[str, Any]] = {
    "변호사_비용": {
        "착수금_범위": "500만~5,000만원",
        "성공보수_범위": "경제적이익의 5~30%",
        "시간당_범위": "30~100만원/시간",
        "note": "사건 복잡도, 변호사 경력에 따라 차이",
    },
    "소송_비용": {
        "인지대": "소가의 0.5~1.0%",
        "송달료": "5만~50만원",
        "감정비": "50만~500만원 (필요시)",
        "증인_일당": "법정 일당 기준",
        "note": "소가(소송에서 다투는 금액)에 비례",
    },
    "전문가_비용": {
        "감정인": "200만~2,000만원",
        "회계_감정": "500만~5,000만원",
        "기술_감정": "300만~3,000만원",
        "note": "사건 복잡도에 따라 차이",
    },
}

INDIRECT_COSTS: dict[str, str] = {
    "경영진_시간": "소송 관련 회의, 서류 준비, 증언 등에 소요되는 시간 (기회비용)",
    "평판_리스크": "언론 보도, 투자자/고객 신뢰 하락 (특히 상장사)",
    "사업_기회비용": "분쟁 기간 동안 해당 사업 진행 지연/중단",
    "내부_혼란": "직원 사기 저하, 핵심 인력 이탈 리스크",
    "관계_비용": "거래처, 파트너사와의 관계 악화",
}

# ══════════════════════════════════════════
#  분쟁 유형 자동 탐지 키워드
# ══════════════════════════════════════════

_DISPUTE_TYPE_KEYWORDS: dict[str, list[str]] = {
    "민사": ["계약", "위반", "손해배상", "채무", "부당이득", "임대", "매매"],
    "형사": ["사기", "횡령", "배임", "명예훼손", "고소", "고발", "수사"],
    "행정": ["인허가", "과징금", "과태료", "행정처분", "허가취소", "규제위반"],
    "중재": ["중재", "KCAB", "ICC", "국제", "M&A", "투자분쟁"],
    "노동": ["해고", "임금", "퇴직금", "노동위원회", "부당해고", "산재"],
    "IP": ["특허", "상표", "저작권", "디자인", "영업비밀", "침해"],
}


def _detect_dispute_type(description: str) -> str:
    """분쟁 설명에서 유형 자동 탐지."""
    scores: dict[str, int] = {}
    for dtype, keywords in _DISPUTE_TYPE_KEYWORDS.items():
        scores[dtype] = sum(1 for kw in keywords if kw in description)
    if not any(scores.values()):
        return "민사"  # 기본값
    return max(scores, key=lambda k: scores[k])


class DisputeSimulatorTool(BaseTool):
    """법적 분쟁 시뮬레이터 (CLO 법무IP처 소속).

    게임이론(Nash) + 의사결정트리(Raiffa) + Priest & Klein 소송위험모델 기반.
    """

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "simulate")

        if action == "simulate":
            return await self._simulate(kwargs)
        elif action == "outcome":
            return await self._outcome(kwargs)
        elif action == "strategy":
            return await self._strategy(kwargs)
        elif action == "cost":
            return await self._cost(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "simulate, outcome, strategy, cost 중 하나를 사용하세요."
            )

    # ── simulate: 분쟁 시나리오 시뮬레이션 ──

    async def _simulate(self, kwargs: dict[str, Any]) -> str:
        """분쟁 시나리오 시뮬레이션 (게임이론 기반)."""
        description = kwargs.get("dispute_description", "")
        name = kwargs.get("name", "분쟁 사건")

        if not description:
            return "분쟁 상황 설명(dispute_description)을 입력해주세요."

        # 분쟁 유형 자동 탐지
        detected_type = _detect_dispute_type(description)
        dtype = DISPUTE_TYPES.get(detected_type, DISPUTE_TYPES["민사"])

        lines = [f"## 분쟁 시나리오 시뮬레이션: {name}\n"]
        lines.append(f"- 탐지된 분쟁 유형: **{dtype['name']}**")
        lines.append(f"- 관할: {dtype['court']}")
        lines.append(f"- 예상 기간: {dtype['typical_duration']}")
        lines.append(f"- 심급 구조: {dtype['appeal_stages']}")
        lines.append(f"- 관련 법률: {', '.join(dtype['key_laws'])}\n")

        # ADR 비교표
        lines.append("### 분쟁 해결 방법 비교 (ADR)\n")
        lines.append("| 방법 | 기간 | 비용 | 구속력 | 비밀유지 |")
        lines.append("|------|------|------|--------|---------|")
        for adr in ADR_COMPARISON:
            lines.append(
                f"| {adr['method']} | {adr['duration']} | {adr['cost']} "
                f"| {adr['binding'][:15]}... | {adr['confidentiality']} |"
            )

        formatted = "\n".join(lines)

        adr_detail = "\n".join(
            f"- {a['method']}: 기간={a['duration']}, 비용={a['cost']}, "
            f"구속력={a['binding']}, 적합={a['suitable_for']}"
            for a in ADR_COMPARISON
        )

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 법적 분쟁 시뮬레이션 전문가입니다.\n"
                "게임이론(Nash Equilibrium)을 적용하여 분쟁 시나리오를 시뮬레이션하세요.\n\n"
                "반드시 포함할 내용:\n"
                "1. **당사자별 전략 분석** (Nash Game Theory):\n"
                "   - 우리 측 가용 전략 3가지 이상\n"
                "   - 상대방 예상 전략 3가지 이상\n"
                "   - 각 전략 조합의 보수(payoff) 매트릭스\n"
                "2. **내쉬 균형**: 양측의 최적 전략 조합\n"
                "3. **시나리오 시뮬레이션** (3가지):\n"
                "   - 최선 시나리오: 우리에게 가장 유리한 경우\n"
                "   - 기본 시나리오: 가장 가능성 높은 경우\n"
                "   - 최악 시나리오: 우리에게 가장 불리한 경우\n"
                "4. **분쟁 해결 방법 추천**: 소송/중재/조정/협상 중 최적 선택\n\n"
                "참고 학술 근거:\n"
                "- Nash (1950), 'The Bargaining Problem'\n"
                "- Raiffa (1982), 'The Art and Science of Negotiation'\n"
                "- ADR(Alternative Dispute Resolution) Theory\n\n"
                "한국어로, 비개발자도 이해할 수 있게 구체적으로 답변하세요."
            ),
            user_prompt=(
                f"사건명: {name}\n"
                f"분쟁 상황: {description}\n"
                f"분쟁 유형: {dtype['name']}\n"
                f"관련 법률: {', '.join(dtype['key_laws'])}\n\n"
                f"ADR 방법 비교:\n{adr_detail}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 시뮬레이션 분석\n\n{analysis}{_DISCLAIMER}"

    # ── outcome: 분쟁 결과 예측 ──

    async def _outcome(self, kwargs: dict[str, Any]) -> str:
        """분쟁 결과 예측 (Priest & Klein 소송위험모델)."""
        description = kwargs.get("dispute_description", "")
        evidence = kwargs.get("evidence", "")

        if not description:
            return "분쟁 상황 설명(dispute_description)을 입력해주세요."

        detected_type = _detect_dispute_type(description)

        # 관련 법원 통계 찾기
        stat_key_map: dict[str, str] = {
            "민사": "민사_일반",
            "IP": "특허_침해",
            "노동": "노동_부당해고",
            "행정": "행정_과징금",
        }
        stat_key = stat_key_map.get(detected_type, "민사_일반")
        stats = COURT_STATISTICS.get(stat_key, COURT_STATISTICS["민사_일반"])

        lines = [f"## 분쟁 결과 예측\n"]
        lines.append(f"- 분쟁 유형: **{detected_type}**")
        lines.append(f"- 참조 통계: {stat_key.replace('_', ' ')}\n")

        lines.append("### 한국 법원 통계 (참조)\n")
        lines.append("| 지표 | 값 |")
        lines.append("|------|-----|")
        lines.append(f"| 평균 소요 기간 | {stats['avg_duration_months']}개월 |")
        lines.append(f"| 원고 승소율 | {stats['plaintiff_win_rate']*100:.0f}% |")
        lines.append(f"| 화해/조정 비율 | {stats['settlement_rate']*100:.0f}% |")
        lines.append(f"| 항소율 | {stats['appeal_rate']*100:.0f}% |")
        lines.append(f"| 항소심 파기율 | {stats['overturn_rate']*100:.0f}% |")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 소송 결과 예측 전문가입니다.\n"
                "Priest & Klein (1984)의 소송위험모델을 적용하여\n"
                "분쟁 결과를 예측하세요.\n\n"
                "Priest & Klein 모델 핵심:\n"
                "- 소송까지 가는 사건은 양측의 기대가 크게 엇갈리는 경우\n"
                "- 확실한 사건은 대부분 소송 전에 합의됨\n"
                "- 따라서 실제 소송의 승소율은 50%에 수렴하는 경향\n\n"
                "반드시 포함할 내용:\n"
                "1. **승소 확률 추정**: 원고/피고 각각의 승소 확률 (백분율)\n"
                "2. **의사결정트리** (Raiffa Decision Tree):\n"
                "   - 소송 진행 시 기대값\n"
                "   - 합의 시 기대값\n"
                "   - 최적 의사결정 경로\n"
                "3. **핵심 변수**: 결과에 가장 큰 영향을 미치는 요소 3가지\n"
                "4. **증거 평가**: 제출된 증거의 강도 평가 (강/중/약)\n"
                "5. **합의 vs 소송 비교**: 어느 쪽이 기대값이 높은지\n\n"
                "참고 학술 근거:\n"
                "- Priest & Klein (1984), 'The Selection of Disputes for Litigation'\n"
                "- Raiffa (1982), 'The Art and Science of Negotiation'\n"
                "- Shavell (1996), 'Any Frequency of Plaintiff Victory at Trial is Possible'\n\n"
                "한국어로, 비개발자도 이해할 수 있게 구체적으로 답변하세요."
            ),
            user_prompt=(
                f"분쟁 상황: {description}\n"
                f"증거/근거: {evidence or '별도 제출 없음'}\n"
                f"분쟁 유형: {detected_type}\n"
                f"법원 통계: 승소율 {stats['plaintiff_win_rate']*100:.0f}%, "
                f"화해율 {stats['settlement_rate']*100:.0f}%, "
                f"평균 기간 {stats['avg_duration_months']}개월"
            ),
        )

        return f"{formatted}\n\n---\n\n## 결과 예측 분석\n\n{analysis}{_DISCLAIMER}"

    # ── strategy: 최적 대응 전략 수립 ──

    async def _strategy(self, kwargs: dict[str, Any]) -> str:
        """최적 대응 전략 수립 (Mnookin & Kornhauser 모델)."""
        description = kwargs.get("dispute_description", "")
        goal = kwargs.get("goal", "승소")

        if not description:
            return "분쟁 상황 설명(dispute_description)을 입력해주세요."

        detected_type = _detect_dispute_type(description)
        dtype = DISPUTE_TYPES.get(detected_type, DISPUTE_TYPES["민사"])

        lines = [f"## 최적 대응 전략\n"]
        lines.append(f"- 분쟁 유형: **{dtype['name']}**")
        lines.append(f"- 전략 목표: **{goal}**\n")

        # 전략 목표별 프레임워크
        goal_frameworks: dict[str, str] = {
            "승소": "공격적 전략 — 승소에 필요한 증거 확보 + 법적 논거 강화",
            "합의": "협상 전략 — Mnookin & Kornhauser BATNA 기반 합의 최적화",
            "비용최소화": "방어적 전략 — 조기 종결 + 비용 통제",
        }
        lines.append(f"### 전략 프레임워크: {goal_frameworks.get(goal, goal_frameworks['승소'])}\n")

        # ADR 추천
        lines.append("### ADR 방법별 적합도\n")
        lines.append("| 방법 | 적합한 경우 |")
        lines.append("|------|-----------|")
        for adr in ADR_COMPARISON:
            lines.append(f"| {adr['method']} | {adr['suitable_for']} |")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 법적 분쟁 전략 전문가입니다.\n"
                "Mnookin & Kornhauser의 'Bargaining in the Shadow of the Law' 모델을 적용하여\n"
                "최적 대응 전략을 수립하세요.\n\n"
                "핵심 개념:\n"
                "- BATNA (Best Alternative To Negotiated Agreement): 합의 실패 시 최선의 대안\n"
                "- ZOPA (Zone of Possible Agreement): 양측이 합의 가능한 범위\n"
                "- 법의 그늘(Shadow of the Law): 소송 결과 예측이 협상에 미치는 영향\n\n"
                "반드시 포함할 내용:\n"
                "1. **BATNA 분석**: 우리 측과 상대방의 BATNA\n"
                "2. **ZOPA 식별**: 합의 가능 범위\n"
                "3. **단계별 전략** (4단계):\n"
                "   - 즉시 (1주 이내): 긴급 대응\n"
                "   - 단기 (1개월 이내): 증거 확보, 법적 검토\n"
                "   - 중기 (3개월 이내): 본격 대응\n"
                "   - 장기 (6개월~): 최종 해결\n"
                "4. **위험 관리**: 각 단계별 리스크와 대비책\n"
                "5. **소통 전략**: 상대방, 언론, 이해관계자 소통 방법\n"
                "6. **탈출 전략(Exit Strategy)**: 불리해질 경우 손실 최소화 방안\n\n"
                "참고 학술 근거:\n"
                "- Mnookin & Kornhauser (1979), 'Bargaining in the Shadow of the Law'\n"
                "- Fisher & Ury (1981), 'Getting to Yes'\n"
                "- Raiffa (1982), 'The Art and Science of Negotiation'\n\n"
                "한국어로, 비개발자도 이해할 수 있게 구체적으로 답변하세요."
            ),
            user_prompt=(
                f"분쟁 상황: {description}\n"
                f"전략 목표: {goal}\n"
                f"분쟁 유형: {dtype['name']}\n"
                f"관련 법률: {', '.join(dtype['key_laws'])}\n"
                f"예상 기간: {dtype['typical_duration']}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 전략 분석\n\n{analysis}{_DISCLAIMER}"

    # ── cost: 분쟁 비용 추정 ──

    async def _cost(self, kwargs: dict[str, Any]) -> str:
        """분쟁 비용 추정 (직접비용 + 간접비용)."""
        description = kwargs.get("dispute_description", "")
        dispute_type = kwargs.get("dispute_type", "")

        if not description:
            return "분쟁 상황 설명(dispute_description)을 입력해주세요."

        if not dispute_type:
            dispute_type = _detect_dispute_type(description)

        lines = ["## 분쟁 비용 추정\n"]
        lines.append(f"- 분쟁 유형: **{dispute_type}**\n")

        # 직접 비용 표
        lines.append("### 직접 비용 (한국 기준 추정)\n")
        for cost_cat, details in COST_MODEL.items():
            cat_name = cost_cat.replace("_", " ")
            lines.append(f"#### {cat_name}")
            for key, val in details.items():
                if key != "note":
                    lines.append(f"- {key.replace('_', ' ')}: {val}")
            lines.append(f"- 참고: {details['note']}\n")

        # 간접 비용
        lines.append("### 간접 비용 (정량화 어려운 비용)\n")
        lines.append("| 비용 항목 | 설명 |")
        lines.append("|---------|------|")
        for cost_name, cost_desc in INDIRECT_COSTS.items():
            lines.append(f"| {cost_name.replace('_', ' ')} | {cost_desc} |")

        formatted = "\n".join(lines)

        # 관련 통계
        stat_key_map: dict[str, str] = {
            "민사": "민사_일반",
            "IP": "특허_침해",
            "노동": "노동_부당해고",
            "행정": "행정_과징금",
        }
        stat_key = stat_key_map.get(dispute_type, "민사_일반")
        stats = COURT_STATISTICS.get(stat_key, COURT_STATISTICS["민사_일반"])

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 소송 비용 분석 전문가입니다.\n"
                "주어진 분쟁 상황의 예상 비용을 구체적으로 추정하세요.\n\n"
                "반드시 포함할 내용:\n"
                "1. **총 비용 추정**: 최소/예상/최대 시나리오별 (만원 단위)\n"
                "2. **비용 시간 분포**: 단계별 비용 발생 예측\n"
                "   - 초기 (착수금, 서류 준비)\n"
                "   - 진행 중 (변호사 비용, 감정, 증거)\n"
                "   - 종결 (성공보수, 집행비용)\n"
                "3. **비용-편익 분석**:\n"
                "   - 승소 시 기대 회수액\n"
                "   - 패소 시 추가 부담액\n"
                "   - 손익분기점(BEP)\n"
                "4. **비용 절감 방안**: 어떻게 하면 비용을 줄일 수 있는지\n"
                "5. **숨겨진 비용 경고**: 놓치기 쉬운 간접 비용\n\n"
                "참고 학술 근거:\n"
                "- Posner (2014), 'Economic Analysis of Law' (비용편익분석)\n"
                "- 대한변호사협회 변호사보수기준\n\n"
                "한국어로, 구체적인 금액 범위를 포함하여 답변하세요."
            ),
            user_prompt=(
                f"분쟁 상황: {description}\n"
                f"분쟁 유형: {dispute_type}\n"
                f"평균 소요 기간: {stats['avg_duration_months']}개월\n"
                f"화해 비율: {stats['settlement_rate']*100:.0f}%\n"
                f"항소 비율: {stats['appeal_rate']*100:.0f}%"
            ),
        )

        return f"{formatted}\n\n---\n\n## 비용 분석\n\n{analysis}{_DISCLAIMER}"
