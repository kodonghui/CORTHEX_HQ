"""
법률 문서 초안 생성 Tool.

이용약관, 개인정보처리방침, 환불정책, 쿠키정책 등
법률 문서 초안을 자동 생성하고 검토합니다.

사용 방법:
  - action="generate": 약관/정책 문서 초안 생성
  - action="review": 기존 약관 적정성 검토
  - action="simplify": 약관을 쉬운 한국어로 재작성 (Plain Language)
  - action="compare": 두 약관 비교분석

학술 근거:
  - Legal Design Thinking (Stanford Legal Design Lab)
  - Plain Language Movement (SEC Plain English Rule)
  - 전자상거래법 (표준약관)
  - 약관규제법 (불공정 약관 조항 무효)
  - Layered/Tiered Disclosure (다층적 공시)

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬)

주의: 이 문서는 초안이며, 실제 사용 전 반드시 변호사 검토를 받으세요.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.terms_generator")

_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 문서는 AI가 생성한 초안이며, "
    "실제 사용 전 반드시 변호사 검토를 받으세요. "
    "법적 효력을 보장하지 않습니다."
)

# ══════════════════════════════════════════
#  문서 유형별 필수 포함 조항 체크리스트
# ══════════════════════════════════════════

REQUIRED_CLAUSES: dict[str, list[dict[str, str]]] = {
    "이용약관": [
        {"clause": "목적", "description": "약관의 적용 범위와 목적을 명시"},
        {"clause": "용어 정의", "description": "서비스, 회원, 콘텐츠 등 주요 용어 정의"},
        {"clause": "서비스 내용", "description": "제공하는 서비스의 구체적 내용"},
        {"clause": "회원가입/탈퇴", "description": "가입 조건, 절차, 탈퇴 방법"},
        {"clause": "이용 조건", "description": "서비스 이용에 필요한 조건과 제한"},
        {"clause": "금지 행위", "description": "회원이 해서는 안 되는 행위 목록"},
        {"clause": "지적재산권", "description": "서비스 내 콘텐츠의 저작권 귀속"},
        {"clause": "면책 조항", "description": "회사의 책임 범위와 한계"},
        {"clause": "손해배상", "description": "손해 발생 시 배상 책임과 절차"},
        {"clause": "약관 변경", "description": "약관 변경 시 고지 방법과 절차"},
        {"clause": "분쟁 해결", "description": "분쟁 발생 시 해결 방법 (관할 법원 등)"},
        {"clause": "준거법", "description": "적용되는 법률 명시"},
    ],
    "개인정보처리방침": [
        {"clause": "수집 항목", "description": "수집하는 개인정보의 구체적 항목"},
        {"clause": "수집 방법", "description": "개인정보를 수집하는 방법 (직접 입력, 자동 수집 등)"},
        {"clause": "처리 목적", "description": "개인정보를 어떤 목적으로 사용하는지"},
        {"clause": "보유 기간", "description": "개인정보를 얼마나 보관하는지"},
        {"clause": "제3자 제공", "description": "다른 회사에 정보를 제공하는 경우의 내용"},
        {"clause": "처리 위탁", "description": "개인정보 처리를 외부에 맡기는 경우"},
        {"clause": "파기 절차", "description": "보유 기간 종료 후 정보 삭제 방법"},
        {"clause": "정보주체 권리", "description": "열람/정정/삭제/처리정지 요청 방법"},
        {"clause": "안전성 확보 조치", "description": "개인정보 보호를 위한 기술적/관리적 조치"},
        {"clause": "책임자 정보", "description": "개인정보 보호 책임자(DPO) 연락처"},
        {"clause": "자동 수집 장치", "description": "쿠키, 로그 등 자동 수집 장치 운영 현황"},
        {"clause": "고지 의무", "description": "방침 변경 시 고지 방법"},
    ],
    "환불정책": [
        {"clause": "환불 대상", "description": "환불 가능한 상품/서비스 범위"},
        {"clause": "환불 조건", "description": "환불이 가능한 조건 (기간, 사유 등)"},
        {"clause": "환불 불가 사유", "description": "환불이 불가능한 경우"},
        {"clause": "환불 절차", "description": "환불 신청 방법과 처리 절차"},
        {"clause": "환불 기간", "description": "환불 처리에 소요되는 기간"},
        {"clause": "환불 방법", "description": "환불금 반환 방법 (원래 결제수단 등)"},
        {"clause": "부분 환불", "description": "부분 이용 시 환불 계산 방법"},
        {"clause": "교환/반품", "description": "교환 또는 반품 가능 여부와 조건"},
        {"clause": "청약 철회", "description": "전자상거래법상 청약 철회 권리 (7일)"},
        {"clause": "분쟁 해결", "description": "환불 관련 분쟁 해결 방법"},
    ],
    "쿠키정책": [
        {"clause": "쿠키 정의", "description": "쿠키가 무엇인지 쉬운 설명"},
        {"clause": "사용 목적", "description": "쿠키를 왜 사용하는지"},
        {"clause": "쿠키 유형", "description": "필수/기능/분석/마케팅 쿠키 분류"},
        {"clause": "제3자 쿠키", "description": "외부 서비스(Google Analytics 등)의 쿠키"},
        {"clause": "쿠키 관리 방법", "description": "사용자가 쿠키를 차단/삭제하는 방법"},
        {"clause": "동의 방법", "description": "쿠키 동의를 받는 방법 (배너 등)"},
        {"clause": "변경 고지", "description": "쿠키정책 변경 시 고지 방법"},
    ],
}

# ══════════════════════════════════════════
#  약관규제법 불공정 약관 8가지 유형
# ══════════════════════════════════════════

UNFAIR_TERMS_TYPES: list[dict[str, str]] = [
    {
        "type": "면책 조항 (제7조)",
        "description": "사업자의 고의/과실로 인한 법률상 책임을 배제하는 조항",
        "example": "'회사는 어떠한 경우에도 책임을 지지 않습니다'",
        "risk": "무효 — 고의/중과실 면책은 약관규제법상 무효",
    },
    {
        "type": "손해배상 제한 (제8조)",
        "description": "부당하게 손해배상 범위를 제한하거나 과다한 손해배상 의무를 부과",
        "example": "'손해배상은 월 이용료를 초과할 수 없습니다' (과도한 제한)",
        "risk": "무효 가능 — 현저히 불합리한 제한은 무효",
    },
    {
        "type": "계약 해제/해지 제한 (제9조)",
        "description": "고객의 해제/해지권을 부당하게 제한하는 조항",
        "example": "'1년 약정 기간 내 해지 시 잔여 기간 요금 전액 위약금'",
        "risk": "무효 가능 — 해지 시 과도한 위약금은 불공정",
    },
    {
        "type": "채무 이행 (제10조)",
        "description": "사업자의 급부 내용을 부당하게 제한하는 조항",
        "example": "'회사는 사전 통보 없이 서비스 내용을 변경할 수 있습니다'",
        "risk": "무효 가능 — 일방적 서비스 변경권은 불공정",
    },
    {
        "type": "고객 의무 가중 (제11조)",
        "description": "고객에게 부당하게 불리한 의무를 부과하는 조항",
        "example": "'회원은 회사의 모든 마케팅 활동에 동의한 것으로 간주합니다'",
        "risk": "무효 — 포괄적 동의 간주 조항은 불공정",
    },
    {
        "type": "의사표시 의제 (제12조)",
        "description": "고객의 의사표시가 있거나 없는 것으로 부당하게 의제하는 조항",
        "example": "'30일 내 이의가 없으면 약관 변경에 동의한 것으로 봅니다'",
        "risk": "무효 가능 — 묵시적 동의 의제는 제한적으로만 허용",
    },
    {
        "type": "대리인 책임 가중 (제13조)",
        "description": "고객의 대리인에게 부당한 책임을 지우는 조항",
        "example": "'법정 대리인은 미성년자의 모든 행위에 무한 책임을 집니다'",
        "risk": "무효 가능 — 과도한 대리인 책임은 불공정",
    },
    {
        "type": "소제기 금지/제한 (제14조)",
        "description": "고객의 소송 제기를 부당하게 제한하는 조항",
        "example": "'모든 분쟁은 서울중앙지방법원에서만 해결합니다' (소비자 불리)",
        "risk": "무효 가능 — 소비자의 재판청구권을 부당하게 제한",
    },
]

# ══════════════════════════════════════════
#  한국어 가독성 측정 기준
# ══════════════════════════════════════════

READABILITY_CRITERIA: dict[str, dict[str, Any]] = {
    "문장 길이": {
        "good": 40,
        "warning": 60,
        "bad": 80,
        "unit": "자",
    },
    "전문용어 비율": {
        "good": 5,
        "warning": 10,
        "bad": 15,
        "unit": "%",
    },
}

# 법률 전문 용어 목록 (가독성 체크용)
_LEGAL_JARGON: list[str] = [
    "갑", "을", "병", "정", "준거법", "관할", "재판관할",
    "불가항력", "면책", "위약금", "위약벌", "채무불이행",
    "손해배상", "지체상금", "해제", "해지", "항변",
    "선관주의", "연대보증", "이행보증", "하자담보",
    "양도", "전대", "상계", "경합", "소멸시효",
    "기판력", "집행력", "형성권", "청구권", "항변권",
    "공시송달", "즉시항고", "가처분", "가압류",
    "중재", "조정", "화해", "내용증명",
]


class TermsGeneratorTool(BaseTool):
    """법률 문서 초안 생성 도구 (CLO 법무IP처 소속).

    학술 근거:
      - Legal Design Thinking (Stanford Legal Design Lab)
      - Plain Language Movement (SEC Plain English Rule)
      - 전자상거래법 (표준약관)
      - 약관규제법 (불공정 약관 조항 무효)
      - Layered/Tiered Disclosure (다층적 공시)
    """

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "generate")

        if action == "generate":
            return await self._generate(kwargs)
        elif action == "review":
            return await self._review(kwargs)
        elif action == "simplify":
            return await self._simplify(kwargs)
        elif action == "compare":
            return await self._compare(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "generate, review, simplify, compare 중 하나를 사용하세요."
            )

    # ── 약관/정책 문서 초안 생성 ──

    async def _generate(self, kwargs: dict[str, Any]) -> str:
        """약관/정책 문서 초안을 자동 생성."""
        doc_type = kwargs.get("doc_type", "이용약관")
        service_description = kwargs.get("service_description", "")
        name = kwargs.get("name", "서비스")

        if not service_description:
            return (
                "서비스 설명(service_description)을 입력해주세요.\n"
                "예: service_description='월 구독형 온라인 교육 플랫폼. "
                "동영상 강의와 실시간 질의응답 제공'"
            )

        valid_types = list(REQUIRED_CLAUSES.keys())
        if doc_type not in valid_types:
            return (
                f"'{doc_type}'은(는) 지원하지 않는 문서 유형입니다.\n"
                f"사용 가능한 유형: {', '.join(valid_types)}"
            )

        # 필수 포함 조항 목록
        clauses = REQUIRED_CLAUSES[doc_type]
        clause_list = "\n".join(
            f"  {i}. **{c['clause']}**: {c['description']}"
            for i, c in enumerate(clauses, 1)
        )

        # 불공정 약관 주의사항
        unfair_warnings = self._format_unfair_terms_warnings()

        lines = [
            f"## {name} {doc_type} 생성\n",
            f"### 서비스 설명\n{service_description}\n",
            f"### 필수 포함 조항 ({len(clauses)}개)",
            clause_list,
        ]

        formatted = "\n".join(lines)

        # LLM으로 초안 생성
        draft = await self._llm_call(
            system_prompt=(
                f"당신은 법률 문서 전문가이자 Legal Design Thinking 실천가입니다.\n\n"
                f"아래 학술 근거를 반드시 참조하여 '{doc_type}'을 작성하세요:\n"
                f"- Legal Design Thinking (Stanford Legal Design Lab)\n"
                f"- Plain Language Movement (SEC Plain English Rule)\n"
                f"- 전자상거래법 제10조~제17조 (전자상거래 소비자 보호)\n"
                f"- 약관규제법 제6조~제14조 (불공정 약관 규제)\n"
                f"- Layered/Tiered Disclosure (다층적 공시, 핵심 → 상세 구조)\n\n"
                f"### 작성 원칙\n"
                f"1. **한국어로 작성**: 모든 내용을 한국어로\n"
                f"2. **쉬운 언어**: 법률 전문 용어는 최소화하고, 사용 시 괄호 안에 쉬운 설명 추가\n"
                f"3. **구조적 작성**: 조(Article) → 항(Paragraph) → 호(Item) 구조\n"
                f"4. **필수 조항 전부 포함**: 아래 체크리스트의 모든 조항을 빠짐없이 포함\n"
                f"5. **불공정 조항 배제**: 약관규제법상 무효가 되는 조항은 포함하지 않을 것\n"
                f"6. **서비스 특성 반영**: 서비스 설명에 맞게 구체적으로 작성\n"
                f"7. **Layered Disclosure**: 핵심 요약을 앞에, 상세 내용을 뒤에\n"
                f"8. **시행일 포함**: 마지막에 시행일 명시\n\n"
                f"### 불공정 약관 주의사항\n{unfair_warnings}\n\n"
                f"최종 문서 맨 앞에 '핵심 요약' 섹션을 만들어 5줄 이내로 핵심 내용을 정리하세요.\n"
                f"주의: 이 문서는 AI가 생성한 초안이며, 실제 사용 전 변호사 검토를 받으세요."
            ),
            user_prompt=(
                f"서비스명: {name}\n"
                f"문서 유형: {doc_type}\n"
                f"서비스 설명:\n{service_description}\n\n"
                f"필수 포함 조항:\n{clause_list}"
            ),
            caller_model=kwargs.get("_caller_model"),
            caller_temperature=kwargs.get("_caller_temperature"),
        )

        return f"{formatted}\n\n---\n\n## {doc_type} 초안\n\n{draft}{_DISCLAIMER}"

    # ── 기존 약관 적정성 검토 ──

    async def _review(self, kwargs: dict[str, Any]) -> str:
        """기존 약관 텍스트의 적정성을 검토."""
        terms_text = kwargs.get("terms_text", "")

        if not terms_text:
            return "검토할 약관 텍스트(terms_text)를 입력해주세요."

        # 1) 가독성 분석
        readability = self._analyze_readability(terms_text)

        # 2) 불공정 약관 패턴 검사
        unfair_findings = self._detect_unfair_terms(terms_text)

        # 3) 필수 조항 누락 검사 (유형 자동 추정)
        doc_type = self._guess_doc_type(terms_text)
        missing_clauses: list[str] = []
        if doc_type:
            clauses = REQUIRED_CLAUSES.get(doc_type, [])
            for c in clauses:
                keywords = self._clause_search_keywords(c["clause"])
                if not any(kw in terms_text for kw in keywords):
                    missing_clauses.append(c["clause"])

        lines = [
            "## 약관 적정성 검토 결과\n",
            f"### 기본 정보",
            f"- 문서 길이: {len(terms_text):,}자",
            f"- 추정 유형: {doc_type or '판별 불가'}",
        ]

        # 가독성 결과
        lines.append(f"\n### 가독성 분석")
        lines.append(f"- 총 문장 수: {readability['sentence_count']}개")
        lines.append(f"- 평균 문장 길이: {readability['avg_sentence_length']:.1f}자")
        lines.append(f"- 긴 문장 비율 (60자 이상): {readability['long_sentence_ratio']:.1f}%")
        lines.append(f"- 전문용어 비율: {readability['jargon_ratio']:.1f}%")
        lines.append(f"- **가독성 등급**: {readability['grade']}")

        # 불공정 약관 탐지
        if unfair_findings:
            lines.append(f"\n### 불공정 약관 의심 조항 ({len(unfair_findings)}건)")
            for i, finding in enumerate(unfair_findings, 1):
                lines.append(f"  {i}. **{finding['type']}**")
                lines.append(f"     매칭: `{finding['matched']}`")
                lines.append(f"     위험: {finding['risk']}")
        else:
            lines.append("\n### 불공정 약관 의심 조항: 탐지되지 않음")

        # 필수 조항 누락
        if doc_type and missing_clauses:
            lines.append(f"\n### 필수 조항 누락 의심 ({len(missing_clauses)}건)")
            for mc in missing_clauses:
                lines.append(f"  - {mc}")

        formatted = "\n".join(lines)

        # LLM 심층 검토
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 약관 검토 전문 변호사입니다.\n\n"
                "아래 학술 근거를 반드시 참조하여 검토하세요:\n"
                "- 약관규제법 제6조~제14조 (불공정 약관 8유형)\n"
                "- 전자상거래법 (소비자 보호 관련 조항)\n"
                "- 공정거래위원회 표준약관 가이드라인\n"
                "- Legal Design Thinking (Stanford Legal Design Lab)\n"
                "- Plain Language Movement (SEC Plain English Rule)\n\n"
                "주어진 약관 자동 검토 결과와 원문을 분석하여 다음을 답변하세요:\n\n"
                "1. **적법성 평가**: 약관규제법 위반 여부 (조항별)\n"
                "2. **소비자 보호 평가**: 소비자에게 불리한 조항 분석\n"
                "3. **가독성 개선**: 어려운 표현을 쉽게 바꾸는 제안\n"
                "4. **누락 조항 보완**: 반드시 추가해야 할 내용\n"
                "5. **불공정 조항 수정안**: 문제 조항의 수정 초안 제시\n"
                "6. **우수 사례 비교**: 동종 업계 표준약관과의 비교\n"
                "7. **종합 등급**: A(우수)/B(양호)/C(보통)/D(미흡)/F(심각) 평가\n\n"
                "한국어로 구체적이고 실무적으로 답변하세요."
            ),
            user_prompt=(
                f"자동 검토 결과:\n{formatted}\n\n"
                f"약관 원문:\n{terms_text[:3000]}"
            ),
            caller_model=kwargs.get("_caller_model"),
            caller_temperature=kwargs.get("_caller_temperature"),
        )

        return f"{formatted}\n\n---\n\n## 전문가 검토 의견\n\n{analysis}{_DISCLAIMER}"

    # ── 약관 쉬운 한국어로 재작성 (Plain Language) ──

    async def _simplify(self, kwargs: dict[str, Any]) -> str:
        """약관을 쉬운 한국어로 재작성합니다."""
        terms_text = kwargs.get("terms_text", "")

        if not terms_text:
            return "간소화할 약관 텍스트(terms_text)를 입력해주세요."

        # 현재 가독성 분석
        readability_before = self._analyze_readability(terms_text)

        lines = [
            "## 약관 쉬운 한국어 변환 (Plain Language)\n",
            "### 변환 전 가독성",
            f"- 평균 문장 길이: {readability_before['avg_sentence_length']:.1f}자",
            f"- 전문용어 비율: {readability_before['jargon_ratio']:.1f}%",
            f"- 가독성 등급: {readability_before['grade']}",
        ]

        formatted = "\n".join(lines)

        # LLM으로 쉬운 한국어 변환
        simplified = await self._llm_call(
            system_prompt=(
                "당신은 법률 문서 Plain Language 전문가입니다.\n\n"
                "아래 학술 근거를 반드시 참조하세요:\n"
                "- Plain Language Movement (SEC Plain English Rule, 1998)\n"
                "- Legal Design Thinking (Stanford Legal Design Lab)\n"
                "- Flesch Reading Ease 한국어 적용 연구\n"
                "- 다층적 공시(Layered Disclosure) 기법\n\n"
                "### 변환 규칙 (반드시 지킬 것)\n"
                "1. **짧은 문장**: 한 문장은 40자 이내로 끊을 것\n"
                "2. **쉬운 단어**: 법률 전문 용어를 일상 언어로 바꿀 것\n"
                "   - '면책' → '책임 면제'\n"
                "   - '준거법' → '적용되는 법률'\n"
                "   - '불가항력' → '예측할 수 없는 사건 (자연재해, 전쟁 등)'\n"
                "   - '해지' → '계약 종료'\n"
                "   - '위약금' → '계약 위반 시 내야 하는 돈'\n"
                "3. **능동태 사용**: '처리됩니다' → '회사가 처리합니다'\n"
                "4. **구조 명확화**: 제목, 번호, 들여쓰기로 구조화\n"
                "5. **핵심 요약 추가**: 각 조항 앞에 '한 줄 요약'을 굵은 글씨로\n"
                "6. **법적 효력 유지**: 쉽게 바꾸되, 법적 의미는 동일하게 유지\n"
                "7. **비유/예시 활용**: 어려운 개념은 비유나 예시를 추가\n\n"
                "변환 결과의 형식:\n"
                "```\n"
                "제1조 (목적)\n"
                "**한 줄 요약: 이 약관은 ~ 서비스 이용 규칙입니다.**\n"
                "쉬운 설명 본문...\n"
                "```\n\n"
                "주의: 법적 의미를 바꾸면 안 됩니다. 표현만 쉽게."
            ),
            user_prompt=f"변환할 약관 원문:\n\n{terms_text[:4000]}",
            caller_model=kwargs.get("_caller_model"),
            caller_temperature=kwargs.get("_caller_temperature"),
        )

        return (
            f"{formatted}\n\n---\n\n"
            f"## 쉬운 한국어 변환 결과\n\n{simplified}{_DISCLAIMER}"
        )

    # ── 두 약관 비교분석 ──

    async def _compare(self, kwargs: dict[str, Any]) -> str:
        """두 약관 텍스트를 비교 분석."""
        terms_a = kwargs.get("terms_a", "")
        terms_b = kwargs.get("terms_b", "")

        if not terms_a or not terms_b:
            return "비교할 두 약관 텍스트(terms_a, terms_b)를 모두 입력해주세요."

        # 각각 가독성 분석
        read_a = self._analyze_readability(terms_a)
        read_b = self._analyze_readability(terms_b)

        # 각각 불공정 약관 탐지
        unfair_a = self._detect_unfair_terms(terms_a)
        unfair_b = self._detect_unfair_terms(terms_b)

        lines = [
            "## 약관 비교 분석\n",
            "### 기본 비교",
            "| 항목 | 약관 A | 약관 B |",
            "|------|-------|-------|",
            f"| 문서 길이 | {len(terms_a):,}자 | {len(terms_b):,}자 |",
            f"| 문장 수 | {read_a['sentence_count']}개 | {read_b['sentence_count']}개 |",
            f"| 평균 문장 길이 | {read_a['avg_sentence_length']:.1f}자 | "
            f"{read_b['avg_sentence_length']:.1f}자 |",
            f"| 전문용어 비율 | {read_a['jargon_ratio']:.1f}% | "
            f"{read_b['jargon_ratio']:.1f}% |",
            f"| 가독성 등급 | {read_a['grade']} | {read_b['grade']} |",
            f"| 불공정 조항 의심 | {len(unfair_a)}건 | {len(unfair_b)}건 |",
        ]

        formatted = "\n".join(lines)

        # LLM 비교 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 약관 비교 분석 전문 변호사입니다.\n\n"
                "아래 학술 근거를 참조하세요:\n"
                "- 약관규제법 (불공정 약관 규제)\n"
                "- 전자상거래법 (소비자 보호)\n"
                "- Legal Design Thinking (Stanford Legal Design Lab)\n\n"
                "두 약관을 비교하여 다음을 분석하세요:\n\n"
                "1. **핵심 차이점 TOP 5**: 가장 중요한 차이를 먼저\n"
                "2. **소비자 보호 수준 비교**: 어느 약관이 소비자에게 유리한지\n"
                "3. **법적 완성도 비교**: 필수 조항 포함 여부, 법적 표현 정확성\n"
                "4. **가독성 비교**: 어느 약관이 더 읽기 쉬운지\n"
                "5. **불공정 조항 비교**: 각 약관의 문제 조항\n"
                "6. **통합 권고**: 두 약관의 장점을 합친 최적안 제안\n"
                "7. **종합 판정**: 어느 약관이 더 우수한지, 그 이유\n\n"
                "한국어로 구체적이고 실무적으로 답변하세요."
            ),
            user_prompt=(
                f"비교 결과:\n{formatted}\n\n"
                f"약관 A (앞부분):\n{terms_a[:2000]}\n\n"
                f"약관 B (앞부분):\n{terms_b[:2000]}"
            ),
            caller_model=kwargs.get("_caller_model"),
            caller_temperature=kwargs.get("_caller_temperature"),
        )

        return f"{formatted}\n\n---\n\n## 비교 분석 의견\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  내부 유틸리티
    # ══════════════════════════════════════════

    @staticmethod
    def _analyze_readability(text: str) -> dict[str, Any]:
        """한국어 약관 가독성을 분석합니다.

        Flesch-Kincaid 유사 방식으로 문장 길이와 전문용어 비율을 측정합니다.
        """
        # 문장 분리 (마침표, 물음표, 느낌표 기준)
        sentences = re.split(r'[.?!]\s*', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        sentence_count = len(sentences) or 1

        # 평균 문장 길이
        total_chars = sum(len(s) for s in sentences)
        avg_length = total_chars / sentence_count

        # 긴 문장 비율 (60자 이상)
        long_sentences = sum(1 for s in sentences if len(s) >= 60)
        long_ratio = (long_sentences / sentence_count) * 100

        # 전문용어 비율
        jargon_count = sum(1 for j in _LEGAL_JARGON if j in text)
        # 전체 2글자+ 한글 단어 수
        all_words = re.findall(r'[가-힣]{2,}', text)
        total_words = len(all_words) or 1
        jargon_ratio = (jargon_count / total_words) * 100

        # 가독성 등급 판정
        score = 0
        if avg_length <= 40:
            score += 2
        elif avg_length <= 60:
            score += 1

        if jargon_ratio <= 5:
            score += 2
        elif jargon_ratio <= 10:
            score += 1

        if long_ratio <= 20:
            score += 1

        grade_map = {5: "A (매우 좋음)", 4: "B (좋음)", 3: "C (보통)", 2: "D (어려움)"}
        grade = grade_map.get(score, "F (매우 어려움)")

        return {
            "sentence_count": sentence_count,
            "avg_sentence_length": avg_length,
            "long_sentence_ratio": long_ratio,
            "jargon_ratio": jargon_ratio,
            "jargon_count": jargon_count,
            "grade": grade,
        }

    @staticmethod
    def _detect_unfair_terms(text: str) -> list[dict[str, str]]:
        """약관규제법상 불공정 약관 패턴을 탐지합니다."""
        patterns: list[dict[str, Any]] = [
            {
                "type": "면책 조항 (제7조)",
                "pattern": r"(?:어떠한\s*경우에도|일체의?)\s*(?:책임|배상).{0,20}(?:지지\s*않|면제|없)",
                "risk": "사업자의 고의/과실 면책은 무효 가능",
            },
            {
                "type": "손해배상 제한 (제8조)",
                "pattern": r"손해배상.{0,30}(?:초과할?\s*수\s*없|한도|제한|상한)",
                "risk": "현저히 불합리한 배상 제한은 무효 가능",
            },
            {
                "type": "계약 해제/해지 제한 (제9조)",
                "pattern": r"(?:해지|해제|취소).{0,20}(?:불가|금지|제한|할\s*수\s*없)",
                "risk": "소비자의 해지권을 부당하게 제한",
            },
            {
                "type": "일방적 변경 (제10조)",
                "pattern": r"(?:사전\s*(?:통보|동의)\s*없이|일방적[으로]?).{0,20}(?:변경|수정|개정)",
                "risk": "일방적 서비스 변경권은 불공정",
            },
            {
                "type": "고객 의무 가중 (제11조)",
                "pattern": r"(?:동의한\s*것으로|간주|의제).{0,20}(?:합니다|됩니다|본다)",
                "risk": "포괄적 동의 간주 조항은 불공정",
            },
            {
                "type": "의사표시 의제 (제12조)",
                "pattern": r"(?:이의|의견|반대).{0,20}(?:없으면|없는\s*경우).{0,20}(?:동의|승인|수락)",
                "risk": "묵시적 동의 의제는 제한적으로만 허용",
            },
            {
                "type": "과도한 위약금 (제9조)",
                "pattern": r"위약금.{0,20}(?:전액|100%|\d{2,}%|계약금액)",
                "risk": "과도한 위약금은 감액 또는 무효 가능",
            },
            {
                "type": "소 제기 제한 (제14조)",
                "pattern": r"(?:소송|소\s*제기|재판).{0,20}(?:포기|금지|제한|할\s*수\s*없)",
                "risk": "재판청구권 제한은 무효",
            },
        ]

        findings: list[dict[str, str]] = []
        for pat_info in patterns:
            matches = re.finditer(pat_info["pattern"], text)
            for m in matches:
                start = max(0, m.start() - 20)
                end = min(len(text), m.end() + 20)
                context = text[start:end].replace("\n", " ").strip()
                findings.append({
                    "type": pat_info["type"],
                    "matched": f"...{context}...",
                    "risk": pat_info["risk"],
                })

        return findings

    @staticmethod
    def _guess_doc_type(text: str) -> str:
        """약관 텍스트에서 문서 유형을 자동 추정."""
        type_keywords = {
            "이용약관": ["이용약관", "서비스 약관", "이용 약관", "서비스이용"],
            "개인정보처리방침": [
                "개인정보처리방침", "개인정보 처리방침", "개인정보 보호정책",
                "개인정보 수집", "Privacy Policy",
            ],
            "환불정책": ["환불", "반품", "교환", "청약철회", "환불정책"],
            "쿠키정책": ["쿠키", "Cookie", "쿠키정책"],
        }
        for doc_type, keywords in type_keywords.items():
            if any(kw in text for kw in keywords):
                return doc_type
        return ""

    @staticmethod
    def _clause_search_keywords(clause_name: str) -> list[str]:
        """조항명에 대한 검색 키워드 목록을 반환."""
        keyword_map: dict[str, list[str]] = {
            "목적": ["목적", "적용범위", "적용 범위"],
            "용어 정의": ["용어", "정의", "의미"],
            "서비스 내용": ["서비스 내용", "서비스 제공", "제공 서비스"],
            "회원가입/탈퇴": ["회원가입", "회원 가입", "탈퇴", "회원 탈퇴"],
            "이용 조건": ["이용 조건", "이용조건", "이용 자격"],
            "금지 행위": ["금지", "해서는 안", "하여서는 안"],
            "지적재산권": ["지적재산", "저작권", "지식재산", "특허"],
            "면책 조항": ["면책", "책임제한", "책임 제한", "보증"],
            "손해배상": ["손해배상", "배상", "보상"],
            "약관 변경": ["약관 변경", "약관변경", "개정"],
            "분쟁 해결": ["분쟁", "관할", "중재", "소송"],
            "준거법": ["준거법", "적용 법률", "적용법률"],
            "수집 항목": ["수집 항목", "수집하는", "수집 정보"],
            "수집 방법": ["수집 방법", "수집방법", "자동 수집"],
            "처리 목적": ["처리 목적", "이용 목적", "목적"],
            "보유 기간": ["보유 기간", "보유기간", "보관 기간"],
            "제3자 제공": ["제3자", "제삼자", "제공"],
            "처리 위탁": ["위탁", "수탁자", "수탁"],
            "파기 절차": ["파기", "삭제", "폐기"],
            "정보주체 권리": ["열람", "정정", "삭제", "처리정지", "권리"],
            "안전성 확보 조치": ["안전성", "보안", "암호화", "접근통제"],
            "책임자 정보": ["책임자", "보호책임자", "DPO", "담당자"],
            "자동 수집 장치": ["쿠키", "자동 수집", "로그", "접속기록"],
            "고지 의무": ["고지", "공지", "통지", "변경 시"],
            "환불 대상": ["환불 대상", "환불가능", "환불 가능"],
            "환불 조건": ["환불 조건", "환불조건"],
            "환불 불가 사유": ["환불 불가", "환불불가", "환불 제외"],
            "환불 절차": ["환불 절차", "환불절차", "환불 신청"],
            "환불 기간": ["환불 기간", "환불기간", "처리 기간"],
            "환불 방법": ["환불 방법", "환불방법", "반환 방법"],
            "부분 환불": ["부분 환불", "부분환불", "일할 계산"],
            "교환/반품": ["교환", "반품"],
            "청약 철회": ["청약 철회", "청약철회", "7일"],
            "쿠키 정의": ["쿠키란", "쿠키 정의", "Cookie"],
            "사용 목적": ["사용 목적", "사용목적", "이용 목적"],
            "쿠키 유형": ["쿠키 유형", "필수 쿠키", "기능 쿠키", "분석 쿠키"],
            "제3자 쿠키": ["제3자 쿠키", "Google Analytics", "타사 쿠키"],
            "쿠키 관리 방법": ["쿠키 관리", "쿠키 차단", "쿠키 삭제"],
            "동의 방법": ["동의 방법", "동의방법", "배너"],
            "변경 고지": ["변경 고지", "변경고지", "변경 시"],
        }
        return keyword_map.get(clause_name, [clause_name])

    @staticmethod
    def _format_unfair_terms_warnings() -> str:
        """불공정 약관 8유형 경고 목록을 포맷팅."""
        lines = []
        for i, ut in enumerate(UNFAIR_TERMS_TYPES, 1):
            lines.append(
                f"{i}. **{ut['type']}**: {ut['description']}\n"
                f"   예: {ut['example']}\n"
                f"   위험: {ut['risk']}"
            )
        return "\n".join(lines)
