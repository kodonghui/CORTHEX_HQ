"""
AI 거버넌스 검사 Tool.

AI 시스템의 거버넌스, 윤리, 규제 준수를 체계적으로 검증합니다.

사용 방법:
  - action="check": AI 시스템 거버넌스 종합 체크
  - action="risk_classify": EU AI Act 기준 리스크 등급 분류
  - action="ethics": AI 윤리 검토 (공정성, 투명성, 책임성, 안전성)
  - action="audit_trail": AI 의사결정 감사추적 체크리스트

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬)

학술 근거:
  - EU AI Act (2024 발효) -- Risk-based Classification
  - ISO/IEC 42001:2023 (AI Management System)
  - OECD AI Principles (2019)
  - UNESCO Recommendation on Ethics of AI (2021)
  - NIST AI Risk Management Framework (AI RMF 1.0, 2023)
  - 한국 AI 기본법 (2025)

주의: 이 검사는 참고용이며, 실제 규제 준수 여부는 전문 법률가와 상담하세요.
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.ai_governance_checker")

_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 검사는 참고용이며, "
    "실제 규제 준수 여부는 전문 법률가와 상담하세요."
)

# ══════════════════════════════════════════
#  EU AI Act 4단계 리스크 분류
# ══════════════════════════════════════════

EU_AI_ACT_RISK_LEVELS: dict[str, dict[str, Any]] = {
    "금지 (Unacceptable Risk)": {
        "article": "Article 5",
        "description": "EU 내에서 사용이 완전히 금지되는 AI 시스템",
        "examples": [
            "소셜 스코어링 (사회적 점수 부여)",
            "잠재의식 조작 (subliminal manipulation)",
            "취약 계층 착취 (vulnerable groups exploitation)",
            "법 집행 목적 실시간 원격 생체인식 (예외적 허용)",
            "감정 추론 기반 채용/교육/법 집행",
            "인터넷/CCTV 이미지 무차별 스크래핑한 얼굴인식 DB 구축",
        ],
        "obligation": "사용 및 시장 출시 전면 금지",
        "penalty": "최대 3,500만 유로 또는 전 세계 매출 7%",
    },
    "고위험 (High Risk)": {
        "article": "Annex III, Article 6",
        "description": "기본권에 중대한 영향을 미치는 AI 시스템 -- 엄격한 요건 적용",
        "examples": [
            "채용 및 근로자 관리 (이력서 선별, 성과 평가)",
            "교육 및 직업훈련 (입학, 시험 채점)",
            "신용평가 및 보험 (대출 승인, 보험료 산정)",
            "의료기기 및 진단 보조",
            "법 집행 (범죄 예측, 증거 평가)",
            "출입국 관리 (비자 심사, 국경 통제)",
            "사법 (재판 지원, 판결 예측)",
            "민주적 절차 (투표 시스템 관련 AI)",
        ],
        "obligation": (
            "리스크 관리 시스템 구축, 데이터 거버넌스, 기술 문서화, "
            "기록 보존, 투명성, 인간 감독, 정확성/견고성/사이버보안"
        ),
        "penalty": "최대 1,500만 유로 또는 전 세계 매출 3%",
    },
    "제한적 (Limited Risk)": {
        "article": "Article 50",
        "description": "투명성 의무가 적용되는 AI 시스템",
        "examples": [
            "챗봇 (AI와 대화 중임을 고지)",
            "감정 인식 시스템 (사용 사실 고지)",
            "딥페이크 생성 (AI 생성물임을 표시)",
            "AI 생성 텍스트 (뉴스 등 공공 이익 콘텐츠)",
        ],
        "obligation": "AI 시스템임을 사용자에게 명확히 고지 (투명성 의무)",
        "penalty": "최대 750만 유로 또는 전 세계 매출 1.5%",
    },
    "최소 (Minimal Risk)": {
        "article": "Article 95 (자율 규범 권장)",
        "description": "추가 규제 의무 없음 -- 자율적 행동강령 권장",
        "examples": [
            "스팸 필터",
            "게임 AI",
            "추천 시스템 (개인 맞춤형 콘텐츠)",
            "제조 공정 최적화",
            "농업 AI (작물 관리)",
        ],
        "obligation": "법적 의무 없음, 자율적 행동강령 및 베스트 프랙티스 권장",
        "penalty": "없음",
    },
}

# ══════════════════════════════════════════
#  OECD AI 5대 원칙 (2019)
# ══════════════════════════════════════════

OECD_AI_PRINCIPLES: dict[str, dict[str, str]] = {
    "포괄적 성장 (Inclusive Growth)": {
        "description": "AI가 모든 사람에게 혜택을 주고, 불평등을 줄여야 함",
        "check_items": (
            "다양한 사용자 그룹 접근성 보장, 경제적 포용성, "
            "디지털 격차 해소, 취약 계층 고려"
        ),
    },
    "인간 중심 가치 (Human-centred Values)": {
        "description": "인권, 민주주의 가치, 다양성을 존중해야 함",
        "check_items": (
            "개인정보 보호, 차별 금지, 자기결정권, "
            "인간 존엄성, 다양성 존중"
        ),
    },
    "투명성 (Transparency)": {
        "description": "AI 시스템의 작동 방식을 이해할 수 있어야 함",
        "check_items": (
            "설명 가능성(Explainability), 해석 가능성(Interpretability), "
            "AI 사용 사실 공개, 의사결정 근거 제공"
        ),
    },
    "견고성과 안전성 (Robustness & Safety)": {
        "description": "AI 시스템이 안전하고, 오류에 강건해야 함",
        "check_items": (
            "적대적 공격 방어, 데이터 품질 관리, "
            "시스템 장애 대응, 보안 취약점 점검"
        ),
    },
    "책임성 (Accountability)": {
        "description": "AI 시스템의 결과에 대해 책임을 져야 함",
        "check_items": (
            "책임 주체 명확화, 감사 추적(Audit Trail), "
            "이의 제기 메커니즘, 피해 구제 절차"
        ),
    },
}

# ══════════════════════════════════════════
#  ISO/IEC 42001:2023 거버넌스 체크
# ══════════════════════════════════════════

ISO_42001_DOMAINS: dict[str, dict[str, str]] = {
    "리더십 (Leadership)": {
        "clause": "Clause 5",
        "check_items": (
            "AI 정책 수립, 경영진 책임, 역할/책임/권한 배정, "
            "AI 윤리위원회 설치"
        ),
    },
    "계획 (Planning)": {
        "clause": "Clause 6",
        "check_items": (
            "AI 리스크 식별 및 평가, 목표 설정, "
            "리스크 대응 계획, 변경 관리 계획"
        ),
    },
    "지원 (Support)": {
        "clause": "Clause 7",
        "check_items": (
            "자원 확보(인력/기술/예산), 역량 교육, "
            "인식 제고, 커뮤니케이션, 문서 관리"
        ),
    },
    "운영 (Operation)": {
        "clause": "Clause 8",
        "check_items": (
            "운영 계획 및 통제, AI 리스크 평가 실행, "
            "AI 리스크 처리, 데이터 관리"
        ),
    },
    "성과 평가 (Performance Evaluation)": {
        "clause": "Clause 9",
        "check_items": (
            "모니터링/측정/분석, 내부 심사, "
            "경영 검토, KPI 추적"
        ),
    },
    "개선 (Improvement)": {
        "clause": "Clause 10",
        "check_items": (
            "부적합 및 시정 조치, 지속적 개선, "
            "교훈 반영, 피드백 루프"
        ),
    },
}

# ══════════════════════════════════════════
#  NIST AI RMF 4개 기능
# ══════════════════════════════════════════

NIST_AI_RMF_FUNCTIONS: dict[str, dict[str, str]] = {
    "Govern (거버넌스)": {
        "description": "AI 리스크 관리를 위한 조직 문화, 구조, 정책 수립",
        "subcategories": (
            "정책/절차/프로세스, 책임 구조, "
            "다양한 이해관계자 참여, 조직 맥락 이해"
        ),
    },
    "Map (맵핑)": {
        "description": "AI 시스템의 맥락과 리스크 요인을 식별하고 맵핑",
        "subcategories": (
            "사용 목적/맥락 정의, 이해관계자 식별, "
            "기술적/사회적 리스크 요인 분석, 혜택/비용 분석"
        ),
    },
    "Measure (측정)": {
        "description": "AI 리스크를 정량적/정성적으로 측정하고 평가",
        "subcategories": (
            "성능 지표 정의, 편향/공정성 측정, "
            "신뢰도/견고성 테스트, 설명 가능성 평가"
        ),
    },
    "Manage (관리)": {
        "description": "식별된 리스크에 대한 대응 조치를 계획하고 실행",
        "subcategories": (
            "리스크 완화 조치, 모니터링/대응 체계, "
            "인시던트 관리, 지속적 개선"
        ),
    },
}

# ══════════════════════════════════════════
#  편향/공정성 체크 항목
# ══════════════════════════════════════════

BIAS_FAIRNESS_CHECKLIST: dict[str, dict[str, str]] = {
    "데이터 편향 (Data Bias)": {
        "description": "학습 데이터에 내재된 편향",
        "check_items": (
            "표본 편향(특정 집단 과대/과소 대표), "
            "역사적 편향(과거 차별이 데이터에 반영), "
            "측정 편향(부정확한 레이블/피처), "
            "집계 편향(하위 그룹 차이 무시)"
        ),
        "mitigation": "데이터 감사, 리샘플링, 합성 데이터 보강, 다양성 확보",
    },
    "알고리즘 편향 (Algorithmic Bias)": {
        "description": "모델 설계 및 학습 과정에서 발생하는 편향",
        "check_items": (
            "모델 아키텍처 편향, 최적화 목표 편향, "
            "특성 선택 편향, 프록시 변수 사용"
        ),
        "mitigation": "공정성 제약 추가, 편향 인식 정규화, 다중 목표 최적화",
    },
    "결과 편향 (Outcome Bias)": {
        "description": "AI 의사결정 결과에서 나타나는 차별적 영향",
        "check_items": (
            "그룹 간 결과 격차, 개인 공정성 위반, "
            "교차 차별(intersectional discrimination), "
            "피드백 루프(차별 강화)"
        ),
        "mitigation": "결과 모니터링, 영향 평가, 이의 제기 메커니즘, 인간 검토",
    },
}


class AIGovernanceCheckerTool(BaseTool):
    """AI 거버넌스 검사 도구 (CLO 법무IP처 소속).

    학술 근거:
      - EU AI Act (2024) -- Risk-based Classification
      - ISO/IEC 42001:2023 (AI Management System)
      - OECD AI Principles (2019)
      - UNESCO Recommendation on Ethics of AI (2021)
      - NIST AI Risk Management Framework (AI RMF 1.0, 2023)
      - 한국 AI 기본법 (2025)
    """

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "check")

        if action == "check":
            return await self._check(kwargs)
        elif action == "risk_classify":
            return await self._risk_classify(kwargs)
        elif action == "ethics":
            return await self._ethics(kwargs)
        elif action == "audit_trail":
            return await self._audit_trail(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "check, risk_classify, ethics, audit_trail 중 하나를 사용하세요."
            )

    # ══════════════════════════════════════════
    #  Action 1: AI 거버넌스 종합 체크
    # ══════════════════════════════════════════

    async def _check(self, kwargs: dict[str, Any]) -> str:
        """AI 시스템의 거버넌스를 종합적으로 검사합니다."""
        ai_description = kwargs.get("ai_description", "")
        name = kwargs.get("name", "")

        if not ai_description:
            return (
                "AI 시스템 설명(ai_description)을 입력해주세요.\n"
                "예: ai_description='고객 상담 자동 응답 챗봇', name='CORTHEX 에이전트'"
            )

        target = name or "대상 AI 시스템"

        lines = [f"## AI 거버넌스 종합 검사: {target}\n"]
        lines.append(f"AI 시스템 설명: {ai_description}\n")

        # 1. EU AI Act 리스크 등급
        lines.append("### 1. EU AI Act 리스크 분류 (2024 발효)\n")
        lines.append("| 리스크 등급 | 조항 | 의무 | 과태료 |")
        lines.append("|-----------|------|------|--------|")
        for level_name, info in EU_AI_ACT_RISK_LEVELS.items():
            lines.append(
                f"| **{level_name}** | {info['article']} | "
                f"{info['obligation'][:30]}... | {info['penalty']} |"
            )

        # 2. OECD AI 5대 원칙
        lines.append("\n### 2. OECD AI 5대 원칙 (2019)\n")
        lines.append("| 원칙 | 설명 | 체크 항목 |")
        lines.append("|------|------|----------|")
        for principle_name, info in OECD_AI_PRINCIPLES.items():
            lines.append(
                f"| **{principle_name}** | {info['description'][:25]}... | "
                f"{info['check_items'][:35]}... |"
            )

        # 3. ISO 42001 거버넌스
        lines.append("\n### 3. ISO/IEC 42001:2023 거버넌스 체크\n")
        lines.append("| 도메인 | 조항 | 확인 항목 |")
        lines.append("|--------|------|----------|")
        for domain_name, info in ISO_42001_DOMAINS.items():
            lines.append(
                f"| **{domain_name}** | {info['clause']} | "
                f"{info['check_items'][:40]}... |"
            )

        # 4. NIST AI RMF
        lines.append("\n### 4. NIST AI RMF 1.0 (2023)\n")
        lines.append("| 기능 | 설명 | 하위 범주 |")
        lines.append("|------|------|----------|")
        for func_name, info in NIST_AI_RMF_FUNCTIONS.items():
            lines.append(
                f"| **{func_name}** | {info['description'][:30]}... | "
                f"{info['subcategories'][:35]}... |"
            )

        # 5. 한국 AI 기본법 (2025)
        lines.append("\n### 5. 한국 AI 기본법 (2025) 주요 의무\n")
        lines.append("- 고위험 AI: 사전 영향 평가 의무")
        lines.append("- AI 투명성: AI 사용 사실 고지 의무")
        lines.append("- 데이터 품질: 학습 데이터 품질 관리 의무")
        lines.append("- 이용자 보호: 이의 제기 및 설명 요구권")
        lines.append("- 인간 감독: 고위험 AI의 인간 통제 보장")

        formatted = "\n".join(lines)

        # LLM 종합 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 AI 거버넌스 및 규제 준수 전문가입니다.\n"
                "EU AI Act(2024), ISO 42001(2023), OECD AI Principles(2019),\n"
                "NIST AI RMF(2023), 한국 AI 기본법(2025)을 기반으로\n"
                "AI 시스템의 거버넌스를 종합 검사하세요.\n\n"
                "반드시 다음을 포함하세요:\n"
                "1. **EU AI Act 리스크 등급 판정**: 이 AI 시스템의 리스크 등급\n"
                "2. **OECD 5대 원칙 준수도**: 각 원칙별 준수/미준수 판단\n"
                "3. **ISO 42001 갭 분석**: 현재 갖춰진 것과 부족한 것\n"
                "4. **NIST AI RMF 적용**: 4개 기능별 현재 수준 평가\n"
                "5. **한국 AI 기본법 준수**: 한국 법률 기준 준수 사항\n"
                "6. **종합 권고사항**: 우선순위별 개선 과제 (즉시/단기/중기)\n\n"
                "학술 근거를 명시하고, 한국어로 답변하세요.\n"
                "주의: 이 검사는 참고용이며, 실제 규제 준수는 전문가와 상담하세요."
            ),
            user_prompt=(
                f"AI 시스템명: {target}\n"
                f"AI 시스템 설명: {ai_description}\n\n"
                f"거버넌스 검사 프레임워크:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 전문가 종합 검사 결과\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  Action 2: EU AI Act 리스크 등급 분류
    # ══════════════════════════════════════════

    async def _risk_classify(self, kwargs: dict[str, Any]) -> str:
        """EU AI Act 기준으로 AI 시스템의 리스크 등급을 분류합니다."""
        ai_description = kwargs.get("ai_description", "")
        use_case = kwargs.get("use_case", "")

        if not ai_description:
            return (
                "AI 시스템 설명(ai_description)을 입력해주세요.\n"
                "예: ai_description='이력서 자동 심사 AI', "
                "use_case='채용 프로세스에서 이력서 1차 선별'"
            )

        lines = ["## EU AI Act 리스크 등급 분류\n"]
        lines.append(f"- **AI 시스템**: {ai_description}")
        lines.append(f"- **사용 사례**: {use_case or '미제공'}\n")

        # 4단계 리스크 분류 상세
        for level_name, info in EU_AI_ACT_RISK_LEVELS.items():
            lines.append(f"### {level_name}")
            lines.append(f"**조항**: {info['article']}")
            lines.append(f"**설명**: {info['description']}")
            lines.append(f"**의무**: {info['obligation']}")
            lines.append(f"**과태료**: {info['penalty']}")
            lines.append("**해당 사례**:")
            for example in info["examples"]:
                lines.append(f"  - {example}")
            lines.append("")

        # 리스크 판별 체크리스트
        lines.append("### 리스크 등급 판별 체크리스트\n")
        lines.append("다음 질문에 '예'가 하나라도 해당하면 해당 등급 적용:\n")
        lines.append("**금지 등급 체크 (Article 5)**:")
        lines.append("- [ ] 사회적 점수를 부여하는가?")
        lines.append("- [ ] 잠재의식을 조작하는 기법을 사용하는가?")
        lines.append("- [ ] 취약 계층의 취약점을 악용하는가?")
        lines.append("- [ ] 공공장소에서 실시간 생체인식을 수행하는가?\n")

        lines.append("**고위험 등급 체크 (Annex III)**:")
        lines.append("- [ ] 채용/근로자 관리에 사용되는가?")
        lines.append("- [ ] 교육/직업훈련 평가에 사용되는가?")
        lines.append("- [ ] 신용평가/보험 결정에 사용되는가?")
        lines.append("- [ ] 의료 진단/기기에 사용되는가?")
        lines.append("- [ ] 법 집행/사법 절차에 사용되는가?")
        lines.append("- [ ] 출입국 관리에 사용되는가?\n")

        lines.append("**제한적 등급 체크 (Article 50)**:")
        lines.append("- [ ] 사용자가 AI와 상호작용하는가? (챗봇 등)")
        lines.append("- [ ] 감정/생체 정보를 인식하는가?")
        lines.append("- [ ] 딥페이크/AI 생성 콘텐츠를 만드는가?")

        formatted = "\n".join(lines)

        # LLM 전문가 분류
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 EU AI Act 전문 법률가입니다.\n"
                "EU AI Act(2024)의 리스크 기반 분류 체계를 기반으로\n"
                "주어진 AI 시스템의 리스크 등급을 정확히 분류하세요.\n\n"
                "반드시 다음을 포함하세요:\n"
                "1. **리스크 등급 판정**: 금지/고위험/제한적/최소 중 어디에 해당하는지\n"
                "2. **판정 근거**: Article/Annex 구체적 조항 인용\n"
                "3. **준수 의무 목록**: 해당 등급에서 반드시 이행해야 할 의무\n"
                "4. **이행 일정**: EU AI Act 시행 일정에 따른 준수 기한\n"
                "5. **실무 조치**: 지금 당장 해야 할 구체적 행동 3~5가지\n"
                "6. **한국 적용**: 한국 AI 기본법 기준으로도 어떤 의무가 있는지\n\n"
                "학술 근거를 명시하고, 한국어로 답변하세요."
            ),
            user_prompt=(
                f"AI 시스템 설명: {ai_description}\n"
                f"사용 사례: {use_case or '미제공'}\n\n"
                f"리스크 분류 프레임워크:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 전문가 리스크 분류 결과\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  Action 3: AI 윤리 검토
    # ══════════════════════════════════════════

    async def _ethics(self, kwargs: dict[str, Any]) -> str:
        """AI 시스템의 윤리적 측면을 검토합니다."""
        ai_description = kwargs.get("ai_description", "")

        if not ai_description:
            return (
                "AI 시스템 설명(ai_description)을 입력해주세요.\n"
                "예: ai_description='고객 행동 패턴 분석 및 맞춤 추천 AI'"
            )

        lines = ["## AI 윤리 검토\n"]
        lines.append(f"AI 시스템: {ai_description}\n")

        # OECD 5대 원칙 상세
        lines.append("### 1. OECD AI 5대 원칙 (2019) 검토\n")
        for principle_name, info in OECD_AI_PRINCIPLES.items():
            lines.append(f"#### {principle_name}")
            lines.append(f"- **원칙**: {info['description']}")
            lines.append(f"- **체크 항목**: {info['check_items']}\n")

        # UNESCO AI 윤리 권고 (2021)
        lines.append("### 2. UNESCO AI 윤리 권고 (2021) 핵심 가치\n")
        lines.append("| 가치 | 설명 |")
        lines.append("|------|------|")
        lines.append("| **인간 존엄성** | AI가 인간의 존엄성, 인권, 기본적 자유를 존중 |")
        lines.append("| **평화** | AI가 평화적 목적으로만 사용되어야 함 |")
        lines.append("| **다양성/포용** | AI가 문화적 다양성과 포용성을 증진 |")
        lines.append("| **환경/생태** | AI가 환경적 영향을 최소화하고 지속가능성 추구 |")

        # 편향/공정성 체크
        lines.append("\n### 3. 편향(Bias) 및 공정성(Fairness) 검토\n")
        for bias_type, info in BIAS_FAIRNESS_CHECKLIST.items():
            lines.append(f"#### {bias_type}")
            lines.append(f"- **설명**: {info['description']}")
            lines.append(f"- **체크 항목**: {info['check_items']}")
            lines.append(f"- **완화 조치**: {info['mitigation']}\n")

        # 윤리적 AI 설계 원칙
        lines.append("### 4. 윤리적 AI 설계 원칙 (실무 체크리스트)\n")
        lines.append("- [ ] **투명성**: AI 의사결정 과정을 사용자가 이해할 수 있는가?")
        lines.append("- [ ] **공정성**: 특정 집단에 불리한 결과를 초래하지 않는가?")
        lines.append("- [ ] **책임성**: AI 오류 시 책임 주체가 명확한가?")
        lines.append("- [ ] **안전성**: AI 시스템 장애 시 안전장치가 있는가?")
        lines.append("- [ ] **프라이버시**: 개인정보를 최소한으로 수집하고 보호하는가?")
        lines.append("- [ ] **인간 통제**: 인간이 AI 결정을 번복할 수 있는가?")
        lines.append("- [ ] **설명 요구권**: 사용자가 AI 결정에 대한 설명을 요구할 수 있는가?")
        lines.append("- [ ] **이의 제기**: AI 결정에 대한 이의 제기 절차가 있는가?")

        formatted = "\n".join(lines)

        # LLM 윤리 전문가 검토
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 AI 윤리 전문가입니다.\n"
                "OECD AI Principles(2019), UNESCO AI Ethics(2021),\n"
                "그리고 편향/공정성(Bias/Fairness) 연구를 기반으로\n"
                "AI 시스템의 윤리적 측면을 검토하세요.\n\n"
                "반드시 다음을 포함하세요:\n"
                "1. **OECD 5대 원칙 준수도**: 각 원칙별 등급 (준수/부분/미준수)\n"
                "2. **편향 위험 분석**: 데이터/알고리즘/결과 편향 가능성\n"
                "3. **공정성 지표 제안**: 이 AI에 적합한 공정성 측정 지표\n"
                "4. **윤리적 리스크**: 가장 우려되는 윤리적 문제 TOP 3\n"
                "5. **개선 로드맵**: 우선순위별 윤리 개선 과제\n"
                "6. **이해관계자 영향**: 이 AI가 영향을 미치는 이해관계자 분석\n\n"
                "학술 근거를 명시하고, 한국어로 답변하세요.\n"
                "주의: 이 검토는 참고용이며, 윤리적 판단의 최종 책임은 운영 주체에 있습니다."
            ),
            user_prompt=(
                f"AI 시스템 설명: {ai_description}\n\n"
                f"윤리 검토 프레임워크:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 전문가 윤리 검토 결과\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  Action 4: AI 감사추적 체크리스트
    # ══════════════════════════════════════════

    async def _audit_trail(self, kwargs: dict[str, Any]) -> str:
        """AI 의사결정의 감사추적(Audit Trail) 체크리스트를 제공합니다."""
        ai_description = kwargs.get("ai_description", "")

        if not ai_description:
            return (
                "AI 시스템 설명(ai_description)을 입력해주세요.\n"
                "예: ai_description='AI 기반 투자 자문 시스템'"
            )

        lines = ["## AI 의사결정 감사추적(Audit Trail) 체크리스트\n"]
        lines.append(f"AI 시스템: {ai_description}\n")

        # 감사추적 필수 기록 항목
        lines.append("### 1. 필수 기록 항목 (EU AI Act + ISO 42001)\n")
        lines.append("| 구분 | 기록 항목 | 보존 기간 |")
        lines.append("|------|----------|----------|")
        lines.append("| **입력** | 입력 데이터, 요청자 정보, 요청 시간 | 최소 5년 |")
        lines.append("| **처리** | 사용 모델, 모델 버전, 파라미터, 처리 시간 | 최소 5년 |")
        lines.append("| **출력** | AI 결과물, 신뢰도 점수, 대안 결과 | 최소 5년 |")
        lines.append("| **검토** | 인간 검토자, 검토 결과(승인/수정/거부) | 최소 5년 |")
        lines.append("| **피드백** | 사용자 피드백, 이의 제기, 수정 요청 | 최소 3년 |")
        lines.append("| **사고** | 오류/사고 발생, 원인 분석, 시정 조치 | 최소 10년 |")

        # NIST AI RMF 기반 감사 체크리스트
        lines.append("\n### 2. NIST AI RMF 기반 감사 체크리스트\n")
        for func_name, info in NIST_AI_RMF_FUNCTIONS.items():
            lines.append(f"#### {func_name}")
            lines.append(f"- 목적: {info['description']}")
            lines.append(f"- 확인 항목: {info['subcategories']}\n")

        # ISO 42001 감사 포인트
        lines.append("### 3. ISO 42001 내부 감사 포인트\n")
        for domain_name, info in ISO_42001_DOMAINS.items():
            lines.append(f"- **{domain_name}** ({info['clause']}): {info['check_items']}")

        # 실무 감사추적 구현 가이드
        lines.append("\n### 4. 실무 감사추적 구현 가이드\n")
        lines.append("#### 로깅 아키텍처")
        lines.append("- [ ] 모든 AI 호출에 고유 요청 ID(request_id) 부여")
        lines.append("- [ ] 입력 -> 처리 -> 출력 전 과정 타임스탬프 기록")
        lines.append("- [ ] 사용 모델명, 버전, 파라미터 기록")
        lines.append("- [ ] 토큰 사용량, 비용, 응답 시간 기록")
        lines.append("- [ ] 에러/예외 발생 시 전체 컨텍스트 로깅\n")

        lines.append("#### 인간 감독 체계")
        lines.append("- [ ] 고위험 결정에 대한 인간 검토 프로세스 수립")
        lines.append("- [ ] 검토자의 승인/거부/수정 기록 보존")
        lines.append("- [ ] 이의 제기 접수 및 처리 절차 마련")
        lines.append("- [ ] 정기적 AI 의사결정 품질 감사 실시\n")

        lines.append("#### 데이터 보존 정책")
        lines.append("- [ ] 기록 보존 기간 정의 (법령 기준 최소 기간 충족)")
        lines.append("- [ ] 보존 기간 경과 후 안전한 삭제 절차")
        lines.append("- [ ] 백업 및 복구 계획 수립")
        lines.append("- [ ] 접근 권한 관리 (최소 권한 원칙)")

        formatted = "\n".join(lines)

        # LLM 감사추적 전문가 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 AI 감사(Audit) 및 거버넌스 전문가입니다.\n"
                "ISO 42001(2023), NIST AI RMF(2023), EU AI Act(2024)를\n"
                "기반으로 AI 의사결정 감사추적 체계를 분석하세요.\n\n"
                "반드시 다음을 포함하세요:\n"
                "1. **맞춤형 감사추적 설계**: 이 AI 시스템에 맞는 로깅 항목\n"
                "2. **법적 요구사항**: EU AI Act, 한국 AI 기본법 기준 필수 기록\n"
                "3. **기술 구현 권고**: 감사추적 시스템 아키텍처 제안\n"
                "4. **인간 감독 프로세스**: 적합한 인간 검토 체계 설계\n"
                "5. **감사 빈도**: 정기 감사 일정 및 항목 권고\n"
                "6. **사고 대응**: AI 오류/사고 시 감사추적 활용 절차\n\n"
                "학술 근거를 명시하고, 한국어로 답변하세요.\n"
                "주의: 이 체크리스트는 참고용이며, 실제 감사 체계 구축은 전문가와 상담하세요."
            ),
            user_prompt=(
                f"AI 시스템 설명: {ai_description}\n\n"
                f"감사추적 체크리스트:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 전문가 감사추적 분석\n\n{analysis}{_DISCLAIMER}"
