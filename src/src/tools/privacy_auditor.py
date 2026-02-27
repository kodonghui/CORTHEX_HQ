"""
개인정보 감사 및 영향평가(PIA) Tool.

개인정보 처리의 적법성을 감사하고,
개인정보영향평가(PIA)를 수행합니다.

사용 방법:
  - action="audit": 개인정보 처리 전반 감사
  - action="pia": 개인정보영향평가(Privacy Impact Assessment) 수행
  - action="consent": 동의서/개인정보 처리방침 적정성 검토
  - action="cross_border": 국외 이전 적법성 검토

학술 근거:
  - GDPR (General Data Protection Regulation) — Article 35 DPIA
  - 개인정보보호법 2024 개정 (자동화 의사결정 거부권 신설)
  - OECD Privacy Guidelines (1980/2013 개정)
  - ISO 27701 (Privacy Information Management)
  - Privacy by Design (Ann Cavoukian, 7 Foundational Principles)

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬)

주의: 이 감사 결과는 참고용이며, 실제 개인정보 보호 이슈는
      반드시 전문 변호사/개인정보 보호 책임자(DPO)와 상담하세요.
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.privacy_auditor")

_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 감사 결과는 참고용이며, "
    "실제 개인정보 보호 이슈는 반드시 전문 변호사 또는 "
    "개인정보 보호 책임자(DPO)와 상담하세요."
)

# ══════════════════════════════════════════
#  개인정보 유형별 민감도 분류
# ══════════════════════════════════════════

DATA_SENSITIVITY: dict[str, dict[str, Any]] = {
    "고유식별정보": {
        "examples": ["주민등록번호", "여권번호", "운전면허번호", "외국인등록번호"],
        "level": "최고",
        "legal_basis": "개인정보보호법 제24조의2 (원칙적 처리 금지, 별도 동의/법령 근거 필요)",
        "penalty": "위반 시 5년 이하 징역 또는 5천만원 이하 벌금",
    },
    "민감정보": {
        "examples": [
            "사상/신념", "노동조합/정당 가입", "건강/의료기록",
            "성생활", "유전자/생체정보", "범죄경력", "인종/민족",
        ],
        "level": "매우 높음",
        "legal_basis": "개인정보보호법 제23조 (별도 동의 필요, 목적 외 이용 금지)",
        "penalty": "위반 시 5년 이하 징역 또는 5천만원 이하 벌금",
    },
    "일반정보": {
        "examples": ["이름", "이메일", "전화번호", "주소", "생년월일"],
        "level": "보통",
        "legal_basis": "개인정보보호법 제15조 (동의 또는 법적 근거 필요)",
        "penalty": "위반 시 2년 이하 징역 또는 2천만원 이하 벌금",
    },
}

# ══════════════════════════════════════════
#  GDPR 6가지 적법 처리 근거
# ══════════════════════════════════════════

GDPR_LAWFUL_BASES: list[dict[str, str]] = [
    {
        "basis": "동의 (Consent)",
        "article": "Article 6(1)(a)",
        "description": "정보주체가 자신의 개인정보 처리에 명확히 동의한 경우",
        "requirements": "자유롭고, 구체적이며, 고지에 의한, 명확한 동의여야 함",
    },
    {
        "basis": "계약 이행 (Contract)",
        "article": "Article 6(1)(b)",
        "description": "정보주체와의 계약 이행 또는 계약 체결 전 요청 처리에 필요한 경우",
        "requirements": "계약 이행에 객관적으로 필요한 범위로 제한",
    },
    {
        "basis": "법적 의무 (Legal Obligation)",
        "article": "Article 6(1)(c)",
        "description": "법적 의무를 준수하기 위해 필요한 경우",
        "requirements": "EU 또는 회원국 법률에 근거해야 함",
    },
    {
        "basis": "중대 이익 (Vital Interests)",
        "article": "Article 6(1)(d)",
        "description": "정보주체 또는 타인의 생명 등 중대한 이익을 보호하기 위해 필요한 경우",
        "requirements": "다른 적법 근거가 없을 때만 사용 (최후 수단)",
    },
    {
        "basis": "공적 업무 (Public Task)",
        "article": "Article 6(1)(e)",
        "description": "공공의 이익을 위한 업무 수행 또는 공적 권한 행사에 필요한 경우",
        "requirements": "EU 또는 회원국 법률에 근거한 공적 업무에 한정",
    },
    {
        "basis": "정당한 이익 (Legitimate Interests)",
        "article": "Article 6(1)(f)",
        "description": "컨트롤러 또는 제3자의 정당한 이익을 위해 필요한 경우",
        "requirements": "정보주체의 이익/권리보다 컨트롤러의 이익이 우선해야 함 (이익형량 테스트 필수)",
    },
]

# ══════════════════════════════════════════
#  개인정보보호법 8대 원칙
# ══════════════════════════════════════════

PRIVACY_PRINCIPLES: list[dict[str, str]] = [
    {
        "principle": "목적 제한의 원칙",
        "article": "제3조 제1항",
        "description": "개인정보의 처리 목적을 명확하게 하여야 하고, "
                       "그 목적에 필요한 범위에서 최소한의 개인정보만 적법하게 수집하여야 한다.",
        "check": "수집 목적이 명확하고 구체적으로 기재되어 있는가?",
    },
    {
        "principle": "최소 수집의 원칙",
        "article": "제16조 제1항",
        "description": "목적에 필요한 최소한의 개인정보를 수집하여야 한다.",
        "check": "불필요한 정보를 과도하게 수집하고 있지 않은가?",
    },
    {
        "principle": "목적 외 이용/제공 금지",
        "article": "제18조",
        "description": "수집 목적 범위를 초과하여 이용하거나 제3자에게 제공해서는 안 된다.",
        "check": "수집 목적 외 마케팅, 프로파일링 등에 활용하고 있지 않은가?",
    },
    {
        "principle": "정확성 보장",
        "article": "제3조 제3항",
        "description": "개인정보의 정확성, 완전성, 최신성이 보장되도록 하여야 한다.",
        "check": "정보주체가 정보를 정정/삭제할 수 있는 절차가 있는가?",
    },
    {
        "principle": "안전성 확보",
        "article": "제29조",
        "description": "개인정보가 분실/도난/유출/위조/변조/훼손되지 않도록 "
                       "안전성 확보에 필요한 기술적/관리적/물리적 조치를 하여야 한다.",
        "check": "암호화, 접근통제, 로그관리 등 기술적 보호조치가 되어 있는가?",
    },
    {
        "principle": "투명성의 원칙",
        "article": "제3조 제5항",
        "description": "개인정보 처리방침 등 처리에 관한 사항을 공개하여야 하며, "
                       "열람청구권 등 정보주체의 권리를 보장하여야 한다.",
        "check": "개인정보 처리방침이 공개되어 있고 쉽게 접근 가능한가?",
    },
    {
        "principle": "정보주체 권리 보장",
        "article": "제4조",
        "description": "정보주체는 자신의 개인정보에 대한 열람, 정정/삭제, "
                       "처리정지, 동의철회 등의 권리를 가진다.",
        "check": "열람/정정/삭제/처리정지 요청 절차가 마련되어 있는가?",
    },
    {
        "principle": "책임의 원칙",
        "article": "제3조 제8항",
        "description": "개인정보처리자는 개인정보의 처리에 관한 책임을 진다.",
        "check": "개인정보 보호 책임자(DPO)가 지정되어 있는가?",
    },
]

# ══════════════════════════════════════════
#  Privacy by Design 7원칙 (Ann Cavoukian)
# ══════════════════════════════════════════

PBD_PRINCIPLES: list[dict[str, str]] = [
    {
        "principle": "사전 예방적 (Proactive not Reactive)",
        "description": "사후 대응이 아닌, 사전에 개인정보 위험을 예방하는 설계",
        "check": "서비스 기획 단계부터 개인정보 보호를 고려했는가?",
    },
    {
        "principle": "기본값으로 보호 (Privacy as the Default)",
        "description": "사용자가 아무 조치를 하지 않아도 개인정보가 보호되는 기본 설정",
        "check": "기본 설정이 최대 보호 상태인가? (옵트인 방식)",
    },
    {
        "principle": "설계에 내장 (Privacy Embedded into Design)",
        "description": "개인정보 보호가 시스템의 핵심 기능으로 내장",
        "check": "개인정보 보호가 부가 기능이 아닌 핵심 설계에 포함되어 있는가?",
    },
    {
        "principle": "양립 가능 (Full Functionality — Positive-Sum)",
        "description": "개인정보 보호와 서비스 기능이 양립 가능 (제로섬이 아님)",
        "check": "보호를 강화하면서도 서비스 품질을 유지하고 있는가?",
    },
    {
        "principle": "전 생애주기 보호 (End-to-End Security)",
        "description": "수집부터 파기까지 전 과정에서 보호",
        "check": "데이터 수집-저장-이용-제공-파기 전 단계에서 보호 조치가 있는가?",
    },
    {
        "principle": "가시성과 투명성 (Visibility and Transparency)",
        "description": "처리 과정이 투명하게 공개되고 검증 가능",
        "check": "개인정보 처리 현황을 정보주체가 확인할 수 있는가?",
    },
    {
        "principle": "사용자 중심 (Respect for User Privacy)",
        "description": "정보주체의 이익을 최우선으로 설계",
        "check": "정보주체가 자신의 정보를 통제할 수 있는 권한이 있는가?",
    },
]

# ══════════════════════════════════════════
#  과태료/과징금 정보
# ══════════════════════════════════════════

PENALTY_INFO: dict[str, dict[str, str]] = {
    "GDPR": {
        "최대 과징금": "2천만 유로(약 290억원) 또는 전세계 연 매출의 4% 중 큰 금액",
        "일반 위반": "1천만 유로(약 145억원) 또는 전세계 연 매출의 2% 중 큰 금액",
        "사례": "Meta 12억 유로(2023), Amazon 7.46억 유로(2021)",
    },
    "개인정보보호법": {
        "과징금": "위반 관련 매출의 3% 이내 (2024 개정으로 상향)",
        "과태료": "최대 5천만원 (유형에 따라 상이)",
        "형사벌": "5년 이하 징역 또는 5천만원 이하 벌금 (고유식별정보/민감정보 위반)",
        "손해배상": "법정손해배상 300만원 이하 청구 가능 (입증 부담 완화)",
    },
}


class PrivacyAuditorTool(BaseTool):
    """개인정보 감사 및 영향평가(PIA) 도구 (CLO 법무IP처 소속).

    학술 근거:
      - GDPR Article 35 (Data Protection Impact Assessment)
      - 개인정보보호법 2024 개정 (자동화 의사결정 거부권 신설)
      - OECD Privacy Guidelines (1980, 2013 개정)
      - ISO 27701 (Privacy Information Management System)
      - Privacy by Design (Ann Cavoukian, 7 Foundational Principles)
    """

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "audit")

        if action == "audit":
            return await self._audit(kwargs)
        elif action == "pia":
            return await self._pia(kwargs)
        elif action == "consent":
            return await self._consent_review(kwargs)
        elif action == "cross_border":
            return await self._cross_border(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "audit, pia, consent, cross_border 중 하나를 사용하세요."
            )

    # ── 개인정보 처리 전반 감사 ──

    async def _audit(self, kwargs: dict[str, Any]) -> str:
        """서비스의 개인정보 처리 전반에 대한 적법성 감사."""
        service_description = kwargs.get("service_description", "")
        name = kwargs.get("name", "대상 서비스")

        if not service_description:
            return (
                "서비스 설명(service_description)을 입력해주세요.\n"
                "예: service_description='회원가입 시 이름, 이메일, 전화번호를 수집하여 "
                "마케팅 이메일 발송 및 주문 처리에 사용하는 쇼핑몰 서비스'"
            )

        # 1) 개인정보보호법 8대 원칙 체크리스트 구성
        principles_section = self._format_principles_checklist()

        # 2) Privacy by Design 7원칙 체크리스트
        pbd_section = self._format_pbd_checklist()

        # 3) 데이터 민감도 분류 가이드
        sensitivity_section = self._format_sensitivity_guide()

        # 4) 과태료/과징금 정보
        penalty_section = self._format_penalty_info()

        formatted = (
            f"## 개인정보 처리 감사 보고서: {name}\n\n"
            f"### 감사 대상 서비스\n{service_description}\n\n"
            f"{principles_section}\n\n"
            f"{pbd_section}\n\n"
            f"{sensitivity_section}\n\n"
            f"{penalty_section}"
        )

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 개인정보 보호 전문 감사관(DPO)입니다.\n\n"
                "아래 학술 근거를 반드시 참조하여 감사를 수행하세요:\n"
                "- GDPR Article 35 (DPIA 의무)\n"
                "- 개인정보보호법 2024 개정 (자동화 의사결정 거부권 제37조의2)\n"
                "- OECD Privacy Guidelines (8대 원칙)\n"
                "- ISO 27701 (PIMS 국제 표준)\n"
                "- Privacy by Design (Ann Cavoukian)\n\n"
                "주어진 서비스 설명을 분석하여 다음을 구체적으로 답변하세요:\n\n"
                "1. **수집 정보 분류**: 서비스가 수집하는 것으로 추정되는 개인정보를 "
                "고유식별정보/민감정보/일반정보로 분류\n"
                "2. **적법 처리 근거 평가**: GDPR 6가지 적법 근거 중 어떤 근거에 해당하는지\n"
                "3. **8대 원칙 준수 평가**: 각 원칙별 준수 여부와 개선 사항\n"
                "4. **Privacy by Design 적용 평가**: 7원칙 중 미흡한 부분\n"
                "5. **위반 위험 사항**: 현재 구조에서 법 위반 가능성이 있는 부분\n"
                "6. **과태료/과징금 위험**: 위반 시 예상되는 제재 수준\n"
                "7. **개선 권고사항**: 우선순위별 개선 조치 (시급/중요/권장)\n"
                "8. **자동화 의사결정 해당 여부**: 2024 개정법상 자동화 의사결정 "
                "거부권 적용 대상인지\n\n"
                "한국어로 구체적이고 실무적으로 답변하세요.\n"
                "주의: 이 감사 결과는 참고용이며, 실제 이슈는 전문 DPO와 상담하세요."
            ),
            user_prompt=(
                f"서비스명: {name}\n"
                f"서비스 설명:\n{service_description}\n\n"
                f"참조 체크리스트:\n{formatted}"
            ),
            caller_model=kwargs.get("_caller_model"),
            caller_temperature=kwargs.get("_caller_temperature"),
        )

        return f"{formatted}\n\n---\n\n## 전문가 감사 의견\n\n{analysis}{_DISCLAIMER}"

    # ── 개인정보영향평가(PIA) ──

    async def _pia(self, kwargs: dict[str, Any]) -> str:
        """개인정보영향평가(Privacy Impact Assessment) 수행."""
        data_types = kwargs.get("data_types", "")
        processing_purpose = kwargs.get("processing_purpose", "")

        if not data_types or not processing_purpose:
            return (
                "다음 파라미터를 모두 입력해주세요:\n"
                "- data_types: 처리하는 개인정보 유형 (예: '이름, 이메일, 위치정보, 구매이력')\n"
                "- processing_purpose: 처리 목적 (예: '맞춤형 광고 제공 및 추천 시스템 운영')"
            )

        # 민감도 자동 분류
        classification = self._classify_data_types(data_types)

        # GDPR DPIA 필수 여부 판정
        dpia_required = self._check_dpia_required(data_types, processing_purpose)

        lines = [
            "## 개인정보영향평가(PIA) 보고서\n",
            f"### 1. 평가 개요",
            f"- **처리 개인정보**: {data_types}",
            f"- **처리 목적**: {processing_purpose}\n",
            f"### 2. 데이터 민감도 분류",
        ]

        for level, items in classification.items():
            if items:
                lines.append(f"- **{level}**: {', '.join(items)}")

        lines.append(f"\n### 3. GDPR DPIA 의무 해당 여부")
        lines.append(f"- **판정**: {'필수' if dpia_required else '권고 (의무 아님)'}")
        if dpia_required:
            lines.append(
                "- **근거**: GDPR Article 35 — 대규모 민감정보 처리, "
                "체계적 모니터링, 자동화 의사결정 중 하나 이상 해당"
            )

        # 위험도 매트릭스
        lines.append("\n### 4. 위험도 평가 매트릭스")
        lines.append("| 위험 요소 | 발생 가능성 | 영향도 | 위험 등급 |")
        lines.append("|----------|-----------|-------|---------|")

        risk_factors = [
            ("데이터 유출", "중", "높음", "높음"),
            ("목적 외 이용", "중", "중", "중"),
            ("동의 없는 제3자 제공", "낮음", "높음", "중"),
            ("부정확한 정보 활용", "중", "중", "중"),
            ("과도한 정보 수집", "높음", "중", "높음"),
            ("파기 미이행", "중", "중", "중"),
        ]

        for factor, likelihood, impact, risk in risk_factors:
            lines.append(f"| {factor} | {likelihood} | {impact} | **{risk}** |")

        formatted = "\n".join(lines)

        # LLM 심층 평가
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 개인정보영향평가(PIA/DPIA) 전문가입니다.\n\n"
                "아래 학술 근거를 반드시 참조하세요:\n"
                "- GDPR Article 35 (DPIA 수행 의무, 감독기관 사전 협의)\n"
                "- 개인정보보호법 제33조 (개인정보 영향평가)\n"
                "- ISO 29134 (PIA 가이드라인)\n"
                "- NIST Privacy Framework\n\n"
                "주어진 데이터 유형과 처리 목적을 분석하여 다음을 수행하세요:\n\n"
                "1. **위험 식별**: 개인정보 처리 과정에서 발생 가능한 위험 상세 분석\n"
                "2. **영향 평가**: 정보주체에게 미치는 부정적 영향 평가\n"
                "3. **위험 완화 조치**: 각 위험에 대한 구체적 보호 조치 제안\n"
                "4. **잔여 위험 평가**: 조치 후에도 남는 위험 분석\n"
                "5. **기술적 보호조치**: 암호화, 익명화, 가명처리 등 기술적 방안\n"
                "6. **관리적 보호조치**: 내부 정책, 교육, 감사 등 관리적 방안\n"
                "7. **DPO 의견**: 개인정보 보호 책임자로서의 종합 의견\n\n"
                "한국어로 구체적이고 실무적으로 답변하세요."
            ),
            user_prompt=(
                f"처리 개인정보: {data_types}\n"
                f"처리 목적: {processing_purpose}\n\n"
                f"자동 분류 결과:\n{formatted}"
            ),
            caller_model=kwargs.get("_caller_model"),
            caller_temperature=kwargs.get("_caller_temperature"),
        )

        return f"{formatted}\n\n---\n\n## PIA 심층 평가\n\n{analysis}{_DISCLAIMER}"

    # ── 동의서/처리방침 적정성 검토 ──

    async def _consent_review(self, kwargs: dict[str, Any]) -> str:
        """동의서 또는 개인정보 처리방침 텍스트의 적정성 검토."""
        consent_text = kwargs.get("consent_text", "")

        if not consent_text:
            return (
                "검토할 동의서 텍스트(consent_text)를 입력해주세요.\n"
                "예: consent_text='본 서비스는 회원가입 시 이름, 이메일 주소를 수집하며...'"
            )

        # 필수 기재 항목 체크리스트 (개인정보보호법 제15조, 제17조, 제30조)
        required_items = [
            ("수집 항목", ["수집", "항목", "정보"]),
            ("수집 목적", ["목적", "위하여", "위해"]),
            ("보유 기간", ["보유", "기간", "파기", "보관"]),
            ("제3자 제공", ["제3자", "제공", "공유", "위탁"]),
            ("파기 절차", ["파기", "폐기", "삭제"]),
            ("정보주체 권리", ["열람", "정정", "삭제", "처리정지", "권리"]),
            ("DPO/책임자 정보", ["책임자", "보호책임자", "DPO", "담당자"]),
            ("동의 거부 권리", ["거부", "동의하지", "거절"]),
            ("동의 거부 시 불이익", ["불이익", "제한", "이용 불가"]),
            ("자동 수집 장치", ["쿠키", "자동 수집", "로그", "접속기록"]),
        ]

        check_results: list[dict[str, Any]] = []
        for item_name, keywords in required_items:
            found = any(kw in consent_text for kw in keywords)
            check_results.append({
                "item": item_name,
                "found": found,
                "status": "포함" if found else "누락 의심",
            })

        missing_count = sum(1 for r in check_results if not r["found"])
        total_count = len(check_results)

        lines = [
            "## 동의서/처리방침 적정성 검토\n",
            f"### 문서 기본 정보",
            f"- 문서 길이: {len(consent_text):,}자",
            f"- 필수 항목 포함율: {total_count - missing_count}/{total_count} "
            f"({(total_count - missing_count) / total_count * 100:.0f}%)\n",
            "### 필수 기재 항목 체크",
            "| 항목 | 포함 여부 | 근거 법조문 |",
            "|------|---------|-----------|",
        ]

        article_map = {
            "수집 항목": "제15조 제2항 제1호",
            "수집 목적": "제15조 제2항 제1호",
            "보유 기간": "제15조 제2항 제2호",
            "제3자 제공": "제17조 제2항",
            "파기 절차": "제21조, 제30조 제1항 제4호",
            "정보주체 권리": "제4조, 제30조 제1항 제5호",
            "DPO/책임자 정보": "제30조 제1항 제7호",
            "동의 거부 권리": "제16조 제2항",
            "동의 거부 시 불이익": "제16조 제3항",
            "자동 수집 장치": "제30조 제1항 제8호",
        }

        for r in check_results:
            status_mark = "[O] 포함" if r["found"] else "[X] 누락"
            article = article_map.get(r["item"], "")
            lines.append(f"| {r['item']} | {status_mark} | {article} |")

        formatted = "\n".join(lines)

        # LLM 상세 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 개인정보 보호 전문 변호사입니다.\n\n"
                "아래 학술 근거를 반드시 참조하세요:\n"
                "- 개인정보보호법 제15조 (개인정보의 수집·이용)\n"
                "- 개인정보보호법 제22조 (동의를 받는 방법)\n"
                "- 개인정보보호법 제30조 (개인정보 처리방침의 수립 및 공개)\n"
                "- GDPR Article 7 (Conditions for consent)\n"
                "- GDPR Article 12~14 (투명한 정보 제공 의무)\n\n"
                "주어진 동의서/처리방침 텍스트를 분석하여 다음을 답변하세요:\n\n"
                "1. **적법성 평가**: 법적 필수 요건 충족 여부\n"
                "2. **투명성 평가**: 정보주체가 이해하기 쉬운 언어로 작성되었는지\n"
                "3. **동의 방식 적정성**: 포괄 동의 vs 개별 동의, 옵트인/옵트아웃\n"
                "4. **누락 항목 보완 제안**: 구체적으로 어떤 내용을 추가해야 하는지\n"
                "5. **불공정 조항 여부**: 정보주체에게 불리한 조항이 있는지\n"
                "6. **GDPR 준수 여부**: 해외 서비스 시 GDPR 추가 요건\n"
                "7. **수정 문안 제시**: 문제 조항의 수정 초안\n\n"
                "한국어로 구체적이고 실무적으로 답변하세요."
            ),
            user_prompt=(
                f"자동 검토 결과:\n{formatted}\n\n"
                f"동의서/처리방침 원문:\n{consent_text[:3000]}"
            ),
            caller_model=kwargs.get("_caller_model"),
            caller_temperature=kwargs.get("_caller_temperature"),
        )

        return f"{formatted}\n\n---\n\n## 전문가 검토 의견\n\n{analysis}{_DISCLAIMER}"

    # ── 국외 이전 적법성 검토 ──

    async def _cross_border(self, kwargs: dict[str, Any]) -> str:
        """개인정보 국외 이전의 적법성을 검토."""
        destination_country = kwargs.get("destination_country", "")
        data_types = kwargs.get("data_types", "")

        if not destination_country or not data_types:
            return (
                "다음 파라미터를 모두 입력해주세요:\n"
                "- destination_country: 이전 대상국 (예: '미국', 'EU', '일본')\n"
                "- data_types: 이전 데이터 유형 (예: '고객 이름, 이메일, 구매이력')"
            )

        # 적정성 결정(Adequacy Decision) 현황
        adequacy_countries = {
            "EU": "적정성 결정 보유 (2024)",
            "영국": "적정성 결정 보유 (2022)",
            "일본": "적정성 결정 보유 (2022)",
            "이스라엘": "적정성 결정 보유",
            "캐나다": "적정성 결정 보유 (PIPEDA 적용 기관)",
            "뉴질랜드": "적정성 결정 보유",
            "스위스": "적정성 결정 보유",
            "우루과이": "적정성 결정 보유",
            "아르헨티나": "적정성 결정 보유",
            "미국": "적정성 결정 없음 — EU-US Data Privacy Framework(2023) 활용 가능",
            "중국": "적정성 결정 없음 — PIPL(개인정보보호법) 적용, 국외이전 규제 엄격",
            "인도": "적정성 결정 없음 — DPDPA(2023) 적용",
        }

        country_status = adequacy_countries.get(
            destination_country,
            "적정성 결정 정보 없음 — 별도 보호조치 필요"
        )

        # 민감도 분류
        classification = self._classify_data_types(data_types)

        lines = [
            f"## 개인정보 국외 이전 적법성 검토\n",
            f"### 이전 개요",
            f"- **이전 대상국**: {destination_country}",
            f"- **이전 데이터**: {data_types}",
            f"- **적정성 결정 현황**: {country_status}\n",
            "### 데이터 민감도 분류",
        ]

        for level, items in classification.items():
            if items:
                lines.append(f"- **{level}**: {', '.join(items)}")

        lines.append("\n### 국외 이전 적법 근거 (개인정보보호법 제28조의8)")
        lines.append("| 근거 | 설명 | 비고 |")
        lines.append("|------|------|------|")
        transfer_bases = [
            ("정보주체 동의", "이전 대상국, 이전 항목, 수령자 고지 후 별도 동의", "가장 일반적"),
            ("적정성 결정", "개인정보보호위원회가 보호수준이 적정하다고 인정한 국가", country_status),
            ("표준 계약 조항", "개인정보보호위원회가 고시한 표준계약조항 체결", "SCC 활용"),
            ("인증 취득", "개인정보 보호 인증(CBPR 등) 취득", "APEC CBPR"),
            ("법령상 의무", "법률 또는 조약에 따른 이전 의무", "제한적 적용"),
        ]
        for basis, desc, note in transfer_bases:
            lines.append(f"| {basis} | {desc} | {note} |")

        formatted = "\n".join(lines)

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 국제 개인정보 이전 전문 변호사입니다.\n\n"
                "아래 학술 근거를 반드시 참조하세요:\n"
                "- GDPR Chapter V (Transfers to third countries, Articles 44-49)\n"
                "- 개인정보보호법 제28조의8 (국외 이전)\n"
                "- Schrems II 판결 (2020, EU 사법재판소)\n"
                "- EU-US Data Privacy Framework (2023)\n"
                "- APEC CBPR (Cross-Border Privacy Rules)\n\n"
                "주어진 국외 이전 건에 대해 다음을 분석하세요:\n\n"
                "1. **적법성 평가**: 현재 이전이 합법적인지, 어떤 근거가 적용되는지\n"
                "2. **이전 대상국 위험 평가**: 해당 국가의 개인정보 보호 수준\n"
                "3. **추가 보호조치**: 적정성 결정이 없는 경우 필요한 보완 조치\n"
                "4. **계약 조건**: 수령자와 체결해야 할 계약 조항\n"
                "5. **기술적 보호조치**: 암호화, 가명처리 등 기술적 방안\n"
                "6. **GDPR 추가 요건**: EU 거주자 데이터 포함 시 추가 의무\n"
                "7. **실무 체크리스트**: 이전 전 확인해야 할 사항 목록\n\n"
                "한국어로 구체적이고 실무적으로 답변하세요."
            ),
            user_prompt=(
                f"이전 대상국: {destination_country}\n"
                f"이전 데이터: {data_types}\n\n"
                f"검토 결과:\n{formatted}"
            ),
            caller_model=kwargs.get("_caller_model"),
            caller_temperature=kwargs.get("_caller_temperature"),
        )

        return f"{formatted}\n\n---\n\n## 전문가 검토 의견\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  내부 유틸리티
    # ══════════════════════════════════════════

    @staticmethod
    def _format_principles_checklist() -> str:
        """개인정보보호법 8대 원칙 체크리스트를 포맷팅."""
        lines = ["### 개인정보보호법 8대 원칙 체크리스트"]
        lines.append("| 원칙 | 조문 | 점검 사항 |")
        lines.append("|------|------|---------|")
        for p in PRIVACY_PRINCIPLES:
            lines.append(f"| {p['principle']} | {p['article']} | {p['check']} |")
        return "\n".join(lines)

    @staticmethod
    def _format_pbd_checklist() -> str:
        """Privacy by Design 7원칙 체크리스트를 포맷팅."""
        lines = ["### Privacy by Design 7원칙 (Ann Cavoukian)"]
        lines.append("| 원칙 | 점검 사항 |")
        lines.append("|------|---------|")
        for p in PBD_PRINCIPLES:
            lines.append(f"| {p['principle']} | {p['check']} |")
        return "\n".join(lines)

    @staticmethod
    def _format_sensitivity_guide() -> str:
        """개인정보 유형별 민감도 분류 가이드를 포맷팅."""
        lines = ["### 개인정보 유형별 민감도 분류"]
        lines.append("| 분류 | 민감도 | 예시 | 법적 근거 |")
        lines.append("|------|-------|------|---------|")
        for category, info in DATA_SENSITIVITY.items():
            examples = ", ".join(info["examples"][:4])
            lines.append(
                f"| {category} | {info['level']} | {examples} | {info['legal_basis'][:30]}... |"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_penalty_info() -> str:
        """과태료/과징금 정보를 포맷팅."""
        lines = ["### 위반 시 제재 정보"]
        for law, penalties in PENALTY_INFO.items():
            lines.append(f"\n**{law}**:")
            for key, value in penalties.items():
                lines.append(f"- {key}: {value}")
        return "\n".join(lines)

    @staticmethod
    def _classify_data_types(data_types_str: str) -> dict[str, list[str]]:
        """주어진 데이터 유형 문자열을 민감도별로 자동 분류."""
        result: dict[str, list[str]] = {
            "고유식별정보": [],
            "민감정보": [],
            "일반정보": [],
        }

        high_keywords = [
            "주민등록", "여권", "운전면허", "외국인등록", "주민번호",
        ]
        sensitive_keywords = [
            "건강", "의료", "병력", "진료", "질병", "유전", "생체",
            "지문", "홍채", "DNA", "사상", "신념", "종교", "노동조합",
            "정당", "성생활", "범죄", "전과",
        ]
        general_keywords = [
            "이름", "이메일", "전화", "주소", "생년월일", "성별", "연령",
            "직업", "학력", "구매", "결제", "위치", "IP", "쿠키", "접속",
            "로그", "기기", "브라우저",
        ]

        text_lower = data_types_str.lower()

        for kw in high_keywords:
            if kw in text_lower:
                result["고유식별정보"].append(kw)

        for kw in sensitive_keywords:
            if kw in text_lower:
                result["민감정보"].append(kw)

        for kw in general_keywords:
            if kw in text_lower:
                result["일반정보"].append(kw)

        return result

    @staticmethod
    def _check_dpia_required(data_types: str, purpose: str) -> bool:
        """GDPR Article 35 기준 DPIA 의무 해당 여부 판정."""
        text = (data_types + " " + purpose).lower()

        triggers = [
            # 대규모 민감정보/고유식별정보 처리
            any(kw in text for kw in [
                "주민등록", "건강", "의료", "생체", "유전", "범죄",
            ]),
            # 체계적 모니터링 / 프로파일링
            any(kw in text for kw in [
                "모니터링", "추적", "프로파일링", "행동분석", "위치추적",
                "CCTV", "감시",
            ]),
            # 자동화 의사결정
            any(kw in text for kw in [
                "자동화", "AI", "알고리즘", "자동 결정", "자동 판단",
                "신용평가", "채용심사",
            ]),
            # 대규모 처리
            any(kw in text for kw in [
                "대규모", "대량", "전국민", "전체 고객", "빅데이터",
            ]),
            # 아동 정보
            any(kw in text for kw in [
                "아동", "미성년", "어린이",
            ]),
        ]

        # 2개 이상 해당 시 DPIA 의무
        return sum(triggers) >= 2
