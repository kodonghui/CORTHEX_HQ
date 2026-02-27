"""
규제 동향 레이더 Tool (CLO 법무IP처 소속).

국내외 규제 동향 실시간 모니터링 및 사업 영향 분석.
OECD RIA(규제영향분석) 방법론, Zweigert & Koetz 비교법,
Regulatory Sandbox Framework 기반.

사용 방법:
  - action="scan": 산업별 규제 동향 스캔
  - action="impact": 특정 규제의 사업 영향 분석
  - action="timeline": 규제 시행 일정표 생성
  - action="compare": 국가별 규제 비교

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬)

주의: 이 분석은 참고용이며, 실제 규제 준수 판단은 법률 전문가의 검토를 받으세요.
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.regulation_radar")

_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 분석은 참고용이며, "
    "실제 규제 준수 판단은 반드시 법률 전문가의 검토를 받으세요."
)

# ══════════════════════════════════════════
#  규제 카테고리 체계 (6대 분류)
# ══════════════════════════════════════════

REGULATION_CATEGORIES: dict[str, dict[str, Any]] = {
    "AI_데이터": {
        "name": "AI/데이터 규제",
        "scope": "인공지능, 자동화 의사결정, 개인정보, 데이터 거버넌스",
        "key_laws": [
            "EU AI Act (2024)", "개인정보보호법 (한국)",
            "GDPR (EU)", "CCPA/CPRA (미국 캘리포니아)",
            "디지털 플랫폼 규제법 (한국, 2025 시행)",
        ],
        "watchpoints": [
            "고위험 AI 분류 기준", "알고리즘 투명성 의무",
            "설명가능 AI(XAI) 요구사항", "데이터 국외이전 제한",
            "AI 영향평가 의무화", "생성형 AI 표시 의무",
        ],
    },
    "금융": {
        "name": "금융 규제",
        "scope": "금융, 핀테크, 가상자산, 투자, 보험",
        "key_laws": [
            "자본시장법 (한국)", "가상자산이용자보호법 (한국)",
            "MiCA (EU 암호자산 규제)", "Dodd-Frank Act (미국)",
            "전자금융거래법 (한국)",
        ],
        "watchpoints": [
            "스테이블코인 발행 요건", "DeFi 규제 프레임워크",
            "오픈뱅킹 규제", "암호자산 거래소 인허가",
            "금융 AI 활용 가이드라인", "마이데이터 사업 규제",
        ],
    },
    "환경_ESG": {
        "name": "환경/ESG 규제",
        "scope": "환경, 탄소, ESG, 지속가능성, 공급망",
        "key_laws": [
            "EU CSRD (기업지속가능성보고지침)", "EU CBAM (탄소국경조정메커니즘)",
            "녹색분류체계 (한국 K-Taxonomy)", "공급망실사법 (EU CSDDD)",
            "탄소중립기본법 (한국)",
        ],
        "watchpoints": [
            "ESG 공시 의무 확대", "탄소배출권 거래 규제",
            "그린워싱 규제 강화", "공급망 인권 실사 의무",
            "전과정 평가(LCA) 의무화", "생물다양성 보고 의무",
        ],
    },
    "소비자": {
        "name": "소비자 보호 규제",
        "scope": "소비자보호, 전자상거래, 광고, 구독경제",
        "key_laws": [
            "전자상거래법 (한국)", "표시광고법 (한국)",
            "디지털서비스법 DSA (EU)", "FTC Act (미국)",
            "소비자기본법 (한국)",
        ],
        "watchpoints": [
            "다크패턴 규제", "구독 해지 간소화 의무",
            "리뷰/추천 투명성", "아동 온라인 보호 강화",
            "AI 기반 가격 차별 규제", "인플루언서 마케팅 규제",
        ],
    },
    "노동": {
        "name": "노동/플랫폼 규제",
        "scope": "노동, 플랫폼 노동, 원격근무, 근로조건",
        "key_laws": [
            "근로기준법 (한국)", "플랫폼종사자보호법 (한국, 추진중)",
            "EU Platform Work Directive", "산업안전보건법 (한국)",
            "기간제/파견근로자보호법 (한국)",
        ],
        "watchpoints": [
            "플랫폼 노동자 근로자성 판단", "알고리즘 경영 투명성",
            "원격근무 법적 프레임워크", "AI 채용 차별 금지",
            "주 52시간 예외 업종", "MZ세대 노동법 이슈",
        ],
    },
    "보안_인프라": {
        "name": "보안/인프라 규제",
        "scope": "사이버보안, 클라우드, 통신, 핵심인프라",
        "key_laws": [
            "정보통신망법 (한국)", "EU NIS2 Directive",
            "클라우드보안인증 (CSAP)", "전자서명법 (한국)",
            "사이버보안기본법 (한국, 추진중)",
        ],
        "watchpoints": [
            "제로트러스트 보안 의무화", "클라우드 데이터 주권",
            "공급망 보안 요구사항", "IoT 기기 보안 인증",
            "양자내성암호 전환 일정", "랜섬웨어 신고 의무",
        ],
    },
}

# ══════════════════════════════════════════
#  규제 성숙도 단계 (5단계)
# ══════════════════════════════════════════

MATURITY_STAGES: list[dict[str, str]] = [
    {
        "stage": "논의",
        "description": "학계/업계에서 규제 필요성이 논의되는 단계",
        "action": "동향 모니터링, 업계 의견 수렴 참여",
    },
    {
        "stage": "입법예고",
        "description": "정부가 법안 초안을 공개하고 의견을 받는 단계",
        "action": "법안 분석, 의견서 제출, 로비 전략 수립",
    },
    {
        "stage": "국회통과",
        "description": "법안이 국회를 통과한 단계 (유예기간 시작)",
        "action": "준수 계획 수립, 시스템 변경 착수",
    },
    {
        "stage": "공포",
        "description": "관보에 게재되어 법적 효력이 확정된 단계",
        "action": "세부 시행령/시행규칙 확인, 내부 교육",
    },
    {
        "stage": "시행",
        "description": "법률이 실제 시행되어 위반 시 제재가 가능한 단계",
        "action": "준수 감사, 위반 리스크 점검, 정기 업데이트",
    },
]

# ══════════════════════════════════════════
#  산업별 규제 매핑
# ══════════════════════════════════════════

INDUSTRY_REGULATION_MAP: dict[str, list[str]] = {
    "AI": ["AI_데이터", "소비자", "노동", "보안_인프라"],
    "핀테크": ["금융", "AI_데이터", "소비자", "보안_인프라"],
    "이커머스": ["소비자", "AI_데이터", "노동", "환경_ESG"],
    "플랫폼": ["소비자", "노동", "AI_데이터", "금융"],
    "제조": ["환경_ESG", "노동", "보안_인프라", "소비자"],
    "SaaS": ["AI_데이터", "보안_인프라", "소비자", "금융"],
    "헬스케어": ["AI_데이터", "소비자", "보안_인프라", "환경_ESG"],
    "에너지": ["환경_ESG", "보안_인프라", "금융", "노동"],
    "미디어": ["AI_데이터", "소비자", "노동", "보안_인프라"],
    "부동산": ["금융", "소비자", "환경_ESG", "AI_데이터"],
}

# ══════════════════════════════════════════
#  OECD RIA 영향 분석 프레임워크
# ══════════════════════════════════════════

RIA_DIMENSIONS: list[dict[str, str]] = [
    {"dimension": "경제적 영향", "description": "매출, 비용, 시장구조 변화"},
    {"dimension": "사회적 영향", "description": "고용, 소비자 후생, 형평성"},
    {"dimension": "환경적 영향", "description": "탄소배출, 자원 사용, 생태계"},
    {"dimension": "행정 부담", "description": "신고/인허가/보고 의무, 준수 비용"},
    {"dimension": "경쟁 영향", "description": "진입장벽, 시장 집중도, 혁신 저해 여부"},
    {"dimension": "국제 비교", "description": "주요국 대비 규제 수준, 글로벌 정합성"},
]


class RegulationRadarTool(BaseTool):
    """국내외 규제 동향 레이더 (CLO 법무IP처 소속).

    OECD RIA 방법론 + Zweigert & Koetz 비교법 기반.
    """

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "scan")

        if action == "scan":
            return await self._scan(kwargs)
        elif action == "impact":
            return await self._impact(kwargs)
        elif action == "timeline":
            return await self._timeline(kwargs)
        elif action == "compare":
            return await self._compare(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "scan, impact, timeline, compare 중 하나를 사용하세요."
            )

    # ── scan: 산업별 규제 동향 스캔 ──

    async def _scan(self, kwargs: dict[str, Any]) -> str:
        """산업별 규제 동향 스캔."""
        industry = kwargs.get("industry", "AI")
        name = kwargs.get("name", "")

        # 해당 산업의 관련 규제 카테고리 식별
        related_cats = INDUSTRY_REGULATION_MAP.get(
            industry, ["AI_데이터", "소비자"]
        )

        lines = [f"## 규제 동향 스캔: {industry} 산업\n"]
        if name:
            lines.append(f"관심 분야: **{name}**\n")

        lines.append(f"### 관련 규제 카테고리 ({len(related_cats)}개)\n")

        scan_data_parts: list[str] = []
        for cat_key in related_cats:
            cat = REGULATION_CATEGORIES.get(cat_key)
            if not cat:
                continue
            lines.append(f"#### {cat['name']}")
            lines.append(f"- 범위: {cat['scope']}")
            lines.append(f"- 주요 법령: {', '.join(cat['key_laws'][:3])}")
            lines.append("- 주요 감시 포인트:")
            for wp in cat["watchpoints"][:3]:
                lines.append(f"  - {wp}")
            lines.append("")
            scan_data_parts.append(
                f"카테고리: {cat['name']}\n"
                f"범위: {cat['scope']}\n"
                f"주요 법령: {', '.join(cat['key_laws'])}\n"
                f"감시 포인트: {', '.join(cat['watchpoints'])}"
            )

        # 성숙도 단계 안내
        lines.append("\n### 규제 성숙도 단계 (Regulatory Maturity Stages)\n")
        for stage in MATURITY_STAGES:
            lines.append(
                f"- **{stage['stage']}**: {stage['description']} "
                f"-> 권장 대응: {stage['action']}"
            )

        formatted = "\n".join(lines)
        scan_data = "\n\n".join(scan_data_parts)

        # LLM 심층 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 규제 동향 분석 전문가입니다.\n"
                "OECD RIA(Regulatory Impact Analysis) 방법론에 기반하여,\n"
                "주어진 산업의 규제 동향을 분석하세요.\n\n"
                "반드시 포함할 내용:\n"
                "1. **긴급도 TOP 3**: 가장 빨리 대응해야 할 규제 3가지\n"
                "2. **기회 요인**: 규제가 오히려 사업 기회가 되는 경우\n"
                "3. **리스크 요인**: 준수하지 않으면 생기는 구체적 리스크\n"
                "4. **권장 대응 로드맵**: 시간순으로 해야 할 일\n\n"
                "참고 학술 근거:\n"
                "- OECD (2020), 'Regulatory Impact Assessment Best Practices'\n"
                "- Zweigert & Koetz, 'Introduction to Comparative Law'\n\n"
                "한국어로, 비개발자도 이해할 수 있게 구체적으로 답변하세요."
            ),
            user_prompt=(
                f"산업: {industry}\n"
                f"관심 분야: {name or '전체'}\n\n"
                f"관련 규제 데이터:\n{scan_data}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 전문가 분석\n\n{analysis}{_DISCLAIMER}"

    # ── impact: 규제 사업 영향 분석 ──

    async def _impact(self, kwargs: dict[str, Any]) -> str:
        """특정 규제의 사업 영향 분석 (OECD RIA 6차원)."""
        regulation = kwargs.get("regulation", "")
        business = kwargs.get("business_description", "")

        if not regulation:
            return "규제명(regulation)을 입력해주세요. 예: 'EU AI Act', '개인정보보호법 개정안'"
        if not business:
            return "사업 설명(business_description)을 입력해주세요."

        # RIA 6차원 프레임워크 표
        lines = [f"## 규제 사업 영향 분석\n"]
        lines.append(f"- 대상 규제: **{regulation}**")
        lines.append(f"- 사업 설명: {business[:200]}\n")

        lines.append("### OECD RIA 6차원 분석 프레임워크\n")
        lines.append("| 차원 | 분석 범위 |")
        lines.append("|------|---------|")
        for dim in RIA_DIMENSIONS:
            lines.append(f"| {dim['dimension']} | {dim['description']} |")

        formatted = "\n".join(lines)

        ria_text = "\n".join(
            f"- {d['dimension']}: {d['description']}" for d in RIA_DIMENSIONS
        )

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 규제영향분석(RIA) 전문가입니다.\n"
                "OECD RIA 방법론의 6가지 차원으로 규제의 사업 영향을 분석하세요.\n\n"
                "반드시 포함할 내용:\n"
                "1. **차원별 영향 평가**: 6가지 차원 각각에 대해 영향도(상/중/하) + 구체적 영향\n"
                "2. **비용-편익 분석**: 준수 비용 vs 비준수 리스크(과태료, 사업중단 등)\n"
                "3. **시나리오 분석**: 최선/최악/예상 시나리오\n"
                "4. **대응 전략**: 단기(3개월), 중기(6개월), 장기(1년) 로드맵\n"
                "5. **필요 리소스**: 인력, 시스템, 예산 추정\n\n"
                "참고 학술 근거:\n"
                "- OECD (2020), 'Regulatory Impact Assessment Best Practices'\n"
                "- Kirkpatrick & Parker (2007), 'Regulatory Impact Assessment'\n"
                "- Radaelli (2009), 'Measuring Regulatory Quality'\n\n"
                "한국어로, 비개발자도 이해할 수 있게 구체적으로 답변하세요."
            ),
            user_prompt=(
                f"대상 규제: {regulation}\n"
                f"사업 설명: {business}\n\n"
                f"RIA 6차원 프레임워크:\n{ria_text}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 영향 분석 결과\n\n{analysis}{_DISCLAIMER}"

    # ── timeline: 규제 시행 일정표 ──

    async def _timeline(self, kwargs: dict[str, Any]) -> str:
        """규제 시행 일정표 생성."""
        industry = kwargs.get("industry", "AI")

        related_cats = INDUSTRY_REGULATION_MAP.get(
            industry, ["AI_데이터", "소비자"]
        )

        lines = [f"## 규제 시행 일정표: {industry} 산업\n"]

        # 성숙도 단계별 표
        lines.append("### 규제 성숙도 단계\n")
        lines.append("| 단계 | 설명 | 권장 대응 |")
        lines.append("|------|------|---------|")
        for stage in MATURITY_STAGES:
            lines.append(
                f"| {stage['stage']} | {stage['description']} | {stage['action']} |"
            )

        # 관련 법령 목록
        lines.append(f"\n### 관련 주요 법령 ({industry})\n")
        all_laws: list[str] = []
        for cat_key in related_cats:
            cat = REGULATION_CATEGORIES.get(cat_key)
            if cat:
                all_laws.extend(cat["key_laws"])
        for i, law in enumerate(all_laws, 1):
            lines.append(f"  {i}. {law}")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 규제 일정 분석 전문가입니다.\n"
                "주어진 산업과 관련 법령 목록을 바탕으로\n"
                "향후 1~2년간의 규제 시행 일정표를 구체적으로 작성하세요.\n\n"
                "반드시 포함할 내용:\n"
                "1. **시행 임박 규제 (3개월 이내)**: 즉시 대응 필요\n"
                "2. **시행 예정 규제 (6개월 이내)**: 준비 착수 필요\n"
                "3. **입법 추진 중 규제 (1년 이내)**: 모니터링 필요\n"
                "4. **논의 단계 규제 (1~2년)**: 장기 대비 필요\n"
                "5. **월별 대응 체크리스트**: 각 규제별 구체적 할 일\n\n"
                "참고:\n"
                "- Regulatory Sandbox Framework (금융위원회)\n"
                "- 규제정보포털 (규제개혁위원회)\n\n"
                "한국어로, 시간순으로 정리하여 답변하세요."
            ),
            user_prompt=(
                f"산업: {industry}\n"
                f"관련 규제 카테고리: {', '.join(related_cats)}\n"
                f"관련 주요 법령:\n"
                + "\n".join(f"- {law}" for law in all_laws)
            ),
        )

        return f"{formatted}\n\n---\n\n## 상세 일정표\n\n{analysis}{_DISCLAIMER}"

    # ── compare: 국가별 규제 비교 ──

    async def _compare(self, kwargs: dict[str, Any]) -> str:
        """국가별 규제 비교 (비교법학 기반)."""
        topic = kwargs.get("regulation_topic", "")
        countries_str = kwargs.get("countries", "한국,미국,EU")

        if not topic:
            return (
                "규제 주제(regulation_topic)를 입력해주세요. "
                "예: 'AI 규제', '개인정보보호', '가상자산 규제'"
            )

        countries = [c.strip() for c in countries_str.split(",") if c.strip()]
        if not countries:
            countries = ["한국", "미국", "EU"]

        lines = [f"## 국가별 규제 비교: {topic}\n"]
        lines.append(f"비교 대상국: {', '.join(countries)}\n")

        # 비교 프레임워크 표
        lines.append("### 비교 분석 프레임워크 (Zweigert & Koetz)\n")
        lines.append("| 비교 차원 | 분석 내용 |")
        lines.append("|---------|---------|")
        lines.append("| 법적 전통 | 대륙법/영미법/혼합 체계 |")
        lines.append("| 규제 수준 | 강규제/중규제/약규제/자율규제 |")
        lines.append("| 시행 시기 | 시행중/시행예정/논의중 |")
        lines.append("| 제재 수준 | 과태료, 형사벌, 영업정지 등 |")
        lines.append("| 적용 범위 | 업종, 기업 규모, 데이터 유형 등 |")
        lines.append("| 규제 기관 | 주무부처, 독립기관, 자율규제 기구 |")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 비교법학(Comparative Law) 전문가입니다.\n"
                "Zweigert & Koetz의 비교법 방법론에 기반하여\n"
                "국가별 규제를 체계적으로 비교 분석하세요.\n\n"
                "반드시 포함할 내용:\n"
                "1. **국가별 규제 현황 비교표**: 각 나라의 법명, 시행일, 핵심 내용\n"
                "2. **규제 수준 비교**: 어느 나라가 가장 강력한지, 왜 그런지\n"
                "3. **제재 수준 비교**: 위반 시 과태료/벌금 수준\n"
                "4. **한국 기업 시사점**: 글로벌 사업 시 어느 나라 기준에 맞춰야 하는지\n"
                "5. **규제 차익(Regulatory Arbitrage) 가능성**: 규제 차이를 활용할 수 있는 전략\n"
                "6. **향후 수렴 전망**: 국제적으로 규제가 어느 방향으로 수렴할 것인지\n\n"
                "참고 학술 근거:\n"
                "- Zweigert & Koetz, 'Introduction to Comparative Law' (3rd ed.)\n"
                "- Mattei (1997), 'Three Patterns of Law'\n"
                "- OECD, 'International Regulatory Co-operation'\n\n"
                "한국어로, 비개발자도 이해할 수 있게 답변하세요."
            ),
            user_prompt=(
                f"규제 주제: {topic}\n"
                f"비교 대상국: {', '.join(countries)}\n"
            ),
        )

        return f"{formatted}\n\n---\n\n## 비교 분석 결과\n\n{analysis}{_DISCLAIMER}"
