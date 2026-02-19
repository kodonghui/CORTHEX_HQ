"""
IP 포트폴리오 관리 Tool.

기업의 지식재산권(특허, 상표, 디자인, 저작권) 포트폴리오를
분석하고 전략적으로 관리합니다.

사용 방법:
  - action="overview": IP 포트폴리오 현황 종합 분석
  - action="landscape": 기술 분야 IP 지형도(Landscape) 분석
  - action="valuation": IP 자산 가치 평가
  - action="strategy": IP 전략 수립

필요 환경변수: 없음 (KIPRIS API 연동은 kipris 도구에 위임)
의존 라이브러리: 없음 (순수 파이썬)

학술 근거:
  - IPR Landscaping (WIPO Guidelines)
  - Patent Analytics (Griliches 1990, Hall et al. 2005)
  - IP Valuation: Income Approach, Market Approach, Cost Approach (Razgaitis 2003)
  - Technology S-Curve (Foster 1986)

주의: 이 분석은 참고용이며, 실제 IP 전략 수립은 변리사/IP 전문가와 상담하세요.
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.ip_portfolio_manager")

_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 분석은 참고용이며, "
    "실제 IP 전략 수립은 변리사 또는 IP 전문가와 상담하세요."
)

# ══════════════════════════════════════════
#  IP 유형 분류 체계
# ══════════════════════════════════════════

IP_TYPES: dict[str, dict[str, Any]] = {
    "특허": {
        "subtypes": ["발명특허", "실용신안", "디자인특허"],
        "lifecycle": ["아이디어", "선행기술조사", "출원", "심사", "등록", "유지", "소멸"],
        "max_duration": "20년 (발명특허 기준, 출원일로부터)",
        "cost_stages": {
            "출원": "50~200만원",
            "심사": "심사청구료 14~46만원",
            "등록": "등록료 연차별 상이",
            "유지": "연차별 등록유지료",
        },
        "protection_scope": "기술적 사상의 창작 (물건, 방법, 제조방법)",
    },
    "상표": {
        "subtypes": ["문자상표", "도형상표", "입체상표", "색채상표", "소리상표"],
        "lifecycle": ["조사", "출원", "심사", "등록", "갱신", "소멸"],
        "max_duration": "10년 (갱신으로 무한 연장 가능)",
        "cost_stages": {
            "출원": "1류당 6.2만원",
            "심사": "1류당 17.8만원",
            "등록": "1류당 21.1만원",
            "갱신": "1류당 31만원 (10년마다)",
        },
        "protection_scope": "자기 상품과 타인 상품을 구별하는 식별력 있는 표장",
    },
    "저작권": {
        "subtypes": ["어문저작물", "음악저작물", "미술저작물", "프로그램저작물", "데이터베이스"],
        "lifecycle": ["창작", "등록(선택)", "보호", "소멸"],
        "max_duration": "저작자 사후 70년 (업무상저작물: 공표 후 70년)",
        "cost_stages": {
            "등록": "1건당 2~5만원 (한국저작권위원회)",
        },
        "protection_scope": "인간의 사상 또는 감정을 표현한 창작물 (아이디어는 비보호)",
    },
    "영업비밀": {
        "subtypes": ["기술정보", "경영정보", "고객정보"],
        "lifecycle": ["식별", "분류", "보호조치", "관리", "폐기"],
        "max_duration": "비밀 유지되는 한 무기한",
        "cost_stages": {
            "관리": "비밀관리체계 구축 비용 (NDA, 보안시스템 등)",
        },
        "protection_scope": "비공지성 + 경제적유용성 + 비밀관리성 3요건 충족 정보",
    },
}

# ══════════════════════════════════════════
#  IP 성숙도 평가 프레임
# ══════════════════════════════════════════

IP_MATURITY_LEVELS: dict[str, dict[str, str]] = {
    "Level 1 - 초기": {
        "description": "IP 인식 부재, 체계적 관리 없음",
        "characteristics": "IP 목록 없음, 발명신고 제도 없음, 직원 IP 교육 없음",
        "risk": "높음 -- 핵심 기술 유출 및 타사 IP 침해 가능성",
    },
    "Level 2 - 인식": {
        "description": "IP 중요성 인식, 기본 출원 시작",
        "characteristics": "간헐적 특허 출원, 기본 NDA 사용, 상표 등록 시작",
        "risk": "중간 -- 체계적 관리 부재로 기회 손실",
    },
    "Level 3 - 관리": {
        "description": "IP 포트폴리오 체계적 관리",
        "characteristics": "IP 목록 관리, 정기 검토, 발명신고 제도 운영, 연차료 관리",
        "risk": "낮음 -- 기본 보호 체계 갖춤",
    },
    "Level 4 - 전략": {
        "description": "IP를 사업 전략과 연계",
        "characteristics": "사업 목표 연계 출원 전략, 경쟁사 IP 모니터링, 라이선싱 수익화",
        "risk": "매우 낮음 -- 전략적 IP 활용",
    },
    "Level 5 - 혁신": {
        "description": "IP가 사업 가치의 핵심 동력",
        "characteristics": "IP 가치 평가 정례화, M&A/투자 시 IP 실사, 오픈 이노베이션",
        "risk": "최소 -- IP가 경쟁 우위의 원천",
    },
}

# ══════════════════════════════════════════
#  IP 가치 평가 3대 접근법
# ══════════════════════════════════════════

VALUATION_APPROACHES: dict[str, dict[str, str]] = {
    "수익접근법 (Income Approach)": {
        "method": "해당 IP가 미래에 창출할 경제적 이익을 현재 가치로 할인",
        "formula": "IP 가치 = SUM(순현금흐름 / (1 + 할인율)^t), t=1..n",
        "when_to_use": "IP가 수익을 직접 창출하거나, 로열티 수입이 있을 때",
        "variants": "직접현금흐름법(DCF), 로열티면제법(Relief from Royalty), 초과수익법(Excess Earnings)",
        "reference": "Razgaitis (2003), Smith & Parr (2005)",
    },
    "시장접근법 (Market Approach)": {
        "method": "유사한 IP의 실제 거래 사례와 비교하여 가치 산정",
        "formula": "IP 가치 = 유사 거래 가격 x 조정 계수",
        "when_to_use": "비교 가능한 IP 거래 사례가 존재할 때",
        "variants": "비교거래법(Comparable Transactions), 산업 로열티율 벤치마크",
        "reference": "Hall et al. (2005), Griliches (1990)",
    },
    "비용접근법 (Cost Approach)": {
        "method": "해당 IP를 처음부터 다시 만들거나 대체하는 데 드는 비용 산정",
        "formula": "IP 가치 = 재생산 비용 - 감가상각(기능적/경제적 진부화)",
        "when_to_use": "수익이나 거래 사례 데이터가 부족할 때, 초기 단계 IP",
        "variants": "재생산비용법(Reproduction Cost), 대체비용법(Replacement Cost)",
        "reference": "Reilly & Schweihs (1998)",
    },
}


class IPPortfolioManagerTool(BaseTool):
    """IP 포트폴리오 관리 도구 (CLO 법무IP처 소속).

    학술 근거:
      - IPR Landscaping (WIPO Guidelines)
      - Patent Analytics (Griliches 1990, Hall et al. 2005)
      - IP Valuation: Income/Market/Cost Approach (Razgaitis 2003)
      - Technology S-Curve (Foster 1986)
    """

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "overview")

        if action == "overview":
            return await self._overview(kwargs)
        elif action == "landscape":
            return await self._landscape(kwargs)
        elif action == "valuation":
            return await self._valuation(kwargs)
        elif action == "strategy":
            return await self._strategy(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "overview, landscape, valuation, strategy 중 하나를 사용하세요."
            )

    # ══════════════════════════════════════════
    #  Action 1: IP 포트폴리오 현황 종합 분석
    # ══════════════════════════════════════════

    async def _overview(self, kwargs: dict[str, Any]) -> str:
        """IP 포트폴리오 현황 종합 분석."""
        company_name = kwargs.get("company_name", "")
        name = kwargs.get("name", "")

        if not company_name and not name:
            return (
                "기업명(company_name) 또는 프로젝트명(name)을 입력해주세요.\n"
                "예: company_name='CORTHEX', name='AI 에이전트 플랫폼'"
            )

        target = company_name or name

        # IP 유형별 분류 체계 표
        lines = [f"## IP 포트폴리오 현황 분석: {target}\n"]

        lines.append("### 1. IP 유형별 분류 체계\n")
        lines.append("| IP 유형 | 하위 유형 | 보호 기간 | 보호 범위 |")
        lines.append("|---------|----------|----------|----------|")
        for ip_type, info in IP_TYPES.items():
            subtypes = ", ".join(info["subtypes"][:3])
            lines.append(
                f"| **{ip_type}** | {subtypes} | "
                f"{info['max_duration']} | {info['protection_scope'][:30]}... |"
            )

        # IP 생명주기
        lines.append("\n### 2. IP 생명주기 (Lifecycle)\n")
        for ip_type, info in IP_TYPES.items():
            stages = " -> ".join(info["lifecycle"])
            lines.append(f"- **{ip_type}**: {stages}")

        # 비용 구조
        lines.append("\n### 3. 주요 비용 구조\n")
        lines.append("| IP 유형 | 출원/등록 | 유지/갱신 |")
        lines.append("|---------|----------|----------|")
        for ip_type, info in IP_TYPES.items():
            costs = info["cost_stages"]
            filing = costs.get("출원", "-")
            maintenance = costs.get("유지", costs.get("갱신", costs.get("관리", "-")))
            lines.append(f"| {ip_type} | {filing} | {maintenance} |")

        # IP 성숙도 평가
        lines.append("\n### 4. IP 성숙도 평가 프레임워크\n")
        lines.append("| 단계 | 설명 | 리스크 수준 |")
        lines.append("|------|------|-----------|")
        for level, info in IP_MATURITY_LEVELS.items():
            lines.append(f"| {level} | {info['description']} | {info['risk']} |")

        # KIPRIS 연동 안내
        lines.append("\n### 5. 특허/상표 데이터 연동")
        lines.append(
            "- 실제 특허/상표 검색은 **kipris** 도구를 통해 KIPRIS Plus API 호출 가능"
        )
        lines.append(
            "- 상표 유사도 검사는 **trademark_similarity** 도구 사용"
        )

        formatted = "\n".join(lines)

        # LLM 종합 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 IP 전략 컨설턴트입니다.\n"
                "WIPO Guidelines와 Patent Analytics(Griliches 1990, Hall et al. 2005) 기반으로\n"
                "기업의 IP 포트폴리오 현황을 종합 분석하세요.\n\n"
                "반드시 다음 항목을 포함하세요:\n"
                "1. **IP 포트폴리오 진단**: 해당 기업/프로젝트에 필요한 IP 유형 추천\n"
                "2. **우선순위 권고**: 어떤 IP부터 확보해야 하는지 순서\n"
                "3. **예상 비용**: IP 확보에 필요한 대략적 비용 범위\n"
                "4. **리스크 분석**: IP 미확보 시 발생할 수 있는 위험\n"
                "5. **경쟁사 대응**: 경쟁사 IP에 대한 FTO(실시자유) 확인 필요성\n\n"
                "학술 근거를 반드시 명시하고, 한국어로 답변하세요.\n"
                "주의: 이 분석은 참고용이며, 실제 IP 전략은 변리사와 상담하세요."
            ),
            user_prompt=(
                f"대상: {target}\n\n"
                f"IP 포트폴리오 현황 자료:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 전문가 종합 분석\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  Action 2: IP 지형도(Landscape) 분석
    # ══════════════════════════════════════════

    async def _landscape(self, kwargs: dict[str, Any]) -> str:
        """특정 기술 분야의 IP 지형도 분석."""
        technology = kwargs.get("technology", "")
        name = kwargs.get("name", "")

        if not technology:
            return (
                "기술 분야(technology)를 입력해주세요.\n"
                "예: technology='자연어 처리 AI', name='CORTHEX 에이전트'"
            )

        target = name or technology

        lines = [f"## IP 지형도(Landscape) 분석: {target}\n"]
        lines.append(f"기술 분야: **{technology}**\n")

        # IPR Landscaping 3단계 프레임워크
        lines.append("### IPR Landscaping 3단계 (WIPO Guidelines 기반)\n")

        lines.append("#### 1단계: Patent Map (특허 지도)")
        lines.append("- 해당 기술 분야의 전체 특허 분포 파악")
        lines.append("- 주요 출원인(기업/연구기관) 식별")
        lines.append("- 기술 분류(IPC/CPC) 기준 핵심 영역 매핑")
        lines.append("- **KIPRIS 도구**로 한국 특허 검색, USPTO/EPO로 해외 특허 검색 가능\n")

        lines.append("#### 2단계: White Space Analysis (공백 분석)")
        lines.append("- 아직 특허가 출원되지 않은 기술 영역 발견")
        lines.append("- 출원 기회가 있는 신규 영역 식별")
        lines.append("- Technology S-Curve(Foster 1986) 기반 기술 성숙도 판단\n")

        lines.append("#### 3단계: Freedom to Operate (FTO, 실시자유 분석)")
        lines.append("- 우리 제품/서비스가 타사 특허를 침해하는지 확인")
        lines.append("- 회피 설계(Design Around) 가능 여부 검토")
        lines.append("- 라이선스 확보 필요 여부 판단\n")

        # Technology S-Curve
        lines.append("### Technology S-Curve 분석 (Foster 1986)\n")
        lines.append("| 단계 | 특성 | IP 전략 |")
        lines.append("|------|------|---------|")
        lines.append("| **도입기** | 기초 연구, 소수 선두 기업 | 핵심 기술 특허 확보 (방어용) |")
        lines.append("| **성장기** | 경쟁 심화, 출원 급증 | 포트폴리오 확대, 경쟁사 모니터링 |")
        lines.append("| **성숙기** | 기술 표준화, 출원 둔화 | 라이선싱 수익화, 방어 전략 |")
        lines.append("| **쇠퇴기** | 차세대 기술 등장 | IP 매각/포기, 차세대 기술 전환 |")

        # 경쟁사 IP 비교 분석 프레임
        lines.append("\n### 경쟁사 IP 비교 분석 프레임\n")
        lines.append("| 분석 항목 | 확인 내용 | 데이터 소스 |")
        lines.append("|----------|----------|-----------|")
        lines.append("| 특허 출원 수 | 연도별 출원 추이, 기술 분야별 분포 | KIPRIS, USPTO |")
        lines.append("| 핵심 발명자 | 주요 연구자, 연구팀 규모 추정 | 특허 발명자 정보 |")
        lines.append("| 기술 집중도 | IPC 분류별 특허 비중 | 특허 분류 분석 |")
        lines.append("| 상표 포트폴리오 | 등록 상표 수, 니스분류 커버리지 | KIPRIS 상표 검색 |")
        lines.append("| IP 분쟁 이력 | 소송/무효심판 이력 | 판례 DB |")

        formatted = "\n".join(lines)

        # LLM 전문가 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 IP 지형도(Patent Landscape) 분석 전문가입니다.\n"
                "WIPO IPR Landscaping Guidelines와 Technology S-Curve(Foster 1986)를\n"
                "기반으로 해당 기술 분야의 IP 지형을 분석하세요.\n\n"
                "반드시 다음을 포함하세요:\n"
                "1. **기술 분야 IP 현황**: 전 세계 및 한국의 특허 출원 동향 추정\n"
                "2. **주요 IP 보유자**: 해당 기술의 주요 특허권자 추정\n"
                "3. **기술 S-Curve 위치**: 현재 이 기술이 어느 단계인지 판단\n"
                "4. **White Space 기회**: 아직 특허가 적은 하위 기술 영역\n"
                "5. **FTO 리스크**: 실시자유 확보 시 주의해야 할 핵심 특허\n"
                "6. **전략 권고**: 이 기술 분야에서의 IP 전략 방향\n\n"
                "학술 근거를 명시하고, 한국어로 답변하세요."
            ),
            user_prompt=(
                f"기술 분야: {technology}\n"
                f"프로젝트/기업: {target}\n\n"
                f"IP 지형도 분석 프레임워크:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 전문가 IP 지형 분석\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  Action 3: IP 가치 평가
    # ══════════════════════════════════════════

    async def _valuation(self, kwargs: dict[str, Any]) -> str:
        """IP 자산의 가치를 평가합니다."""
        ip_description = kwargs.get("ip_description", "")
        ip_type = kwargs.get("ip_type", "특허")

        if not ip_description:
            return (
                "IP 설명(ip_description)을 입력해주세요.\n"
                "예: ip_description='AI 기반 자연어 처리 에이전트 시스템 특허', "
                "ip_type='특허'"
            )

        lines = [f"## IP 가치 평가: {ip_description[:50]}...\n"]
        lines.append(f"IP 유형: **{ip_type}**\n")

        # IP 유형 정보
        type_info = IP_TYPES.get(ip_type, IP_TYPES.get("특허", {}))
        if type_info:
            lines.append(f"- 보호 기간: {type_info.get('max_duration', 'N/A')}")
            lines.append(f"- 보호 범위: {type_info.get('protection_scope', 'N/A')}\n")

        # 3대 가치 평가 접근법
        lines.append("### IP 가치 평가 3대 접근법 (Razgaitis 2003)\n")
        for approach_name, details in VALUATION_APPROACHES.items():
            lines.append(f"#### {approach_name}")
            lines.append(f"- **방법**: {details['method']}")
            lines.append(f"- **산식**: `{details['formula']}`")
            lines.append(f"- **적용 시점**: {details['when_to_use']}")
            lines.append(f"- **세부 기법**: {details['variants']}")
            lines.append(f"- **참고 문헌**: {details['reference']}\n")

        # 가치 평가 체크리스트
        lines.append("### 가치 평가 시 확인 사항\n")
        lines.append("| 항목 | 확인 내용 | 가치 영향 |")
        lines.append("|------|----------|----------|")
        lines.append("| 법적 상태 | 등록/출원/심사 중 | 등록 완료 시 가치 높음 |")
        lines.append("| 잔여 보호 기간 | 남은 보호 기간 | 기간 길수록 가치 높음 |")
        lines.append("| 청구항 범위 | 독립항 수, 종속항 수 | 넓은 청구항일수록 가치 높음 |")
        lines.append("| 인용 횟수 | 후속 특허에서의 인용 수 | 많을수록 기술적 가치 높음 |")
        lines.append("| 시장 규모 | 해당 기술의 시장 크기 | 큰 시장일수록 가치 높음 |")
        lines.append("| 대체 기술 | 회피 설계 가능성 | 대체 어려울수록 가치 높음 |")
        lines.append("| 실시 현황 | 실제 제품/서비스에 적용 여부 | 실시 중이면 가치 입증 |")
        lines.append("| 분쟁 이력 | 무효심판, 침해소송 이력 | 분쟁 없으면 안정적 |")

        formatted = "\n".join(lines)

        # LLM 전문가 평가
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 IP 가치 평가(IP Valuation) 전문가입니다.\n"
                "Razgaitis(2003), Smith & Parr(2005), Hall et al.(2005)의\n"
                "IP 가치 평가 방법론을 기반으로 분석하세요.\n\n"
                "반드시 다음을 포함하세요:\n"
                "1. **추천 평가 접근법**: 3대 접근법 중 이 IP에 가장 적합한 방법과 이유\n"
                "2. **가치 영향 요인 분석**: 이 IP의 가치를 높이는/낮추는 핵심 요인\n"
                "3. **업종별 로열티율 벤치마크**: 해당 기술 분야의 일반적 로열티율 범위\n"
                "4. **가치 극대화 전략**: IP 가치를 높이기 위한 구체적 방법\n"
                "5. **주의사항**: 가치 평가 시 흔히 하는 실수와 주의점\n\n"
                "학술 근거를 명시하고, 한국어로 구체적 수치를 포함해 답변하세요.\n"
                "주의: 이 평가는 참고용이며, 공식 가치 평가는 전문 감정기관에 의뢰하세요."
            ),
            user_prompt=(
                f"IP 설명: {ip_description}\n"
                f"IP 유형: {ip_type}\n\n"
                f"평가 프레임워크:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 전문가 가치 평가 분석\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  Action 4: IP 전략 수립
    # ══════════════════════════════════════════

    async def _strategy(self, kwargs: dict[str, Any]) -> str:
        """사업 목표에 맞는 IP 전략을 수립합니다."""
        business_goal = kwargs.get("business_goal", "")
        current_ip = kwargs.get("current_ip", "")

        if not business_goal:
            return (
                "사업 목표(business_goal)를 입력해주세요.\n"
                "예: business_goal='AI SaaS 서비스 글로벌 런칭', "
                "current_ip='특허 2건, 상표 1건 보유'"
            )

        lines = ["## IP 전략 수립\n"]
        lines.append(f"- **사업 목표**: {business_goal}")
        lines.append(f"- **현재 IP 현황**: {current_ip or '미제공'}\n")

        # IP 전략 유형
        lines.append("### IP 전략 유형\n")
        lines.append("| 전략 | 설명 | 적합한 상황 |")
        lines.append("|------|------|-----------|")
        lines.append("| **공격형** | 적극적 IP 확보 + 경쟁사 견제 | 시장 선점이 중요할 때 |")
        lines.append("| **방어형** | 핵심 기술 보호 + FTO 확보 | 기존 사업 보호가 우선일 때 |")
        lines.append("| **수익형** | 라이선싱, IP 매각으로 직접 수익 | IP 포트폴리오가 충분할 때 |")
        lines.append("| **협력형** | 크로스 라이선싱, 특허 풀 참여 | 기술 표준화 시장일 때 |")
        lines.append("| **하이브리드** | 위 전략의 조합 | 복합적 상황 (대부분의 기업) |")

        # 사업 단계별 IP 전략
        lines.append("\n### 사업 단계별 IP 전략 로드맵\n")
        lines.append("| 단계 | IP 전략 | 우선 과제 |")
        lines.append("|------|---------|---------|")
        lines.append(
            "| **시드/초기** | 핵심 기술 특허 1~2건 + 브랜드 상표 등록 | "
            "FTO 확인, 창업자 IP 양도 계약 |"
        )
        lines.append(
            "| **시리즈 A** | 특허 포트폴리오 확대 (5~10건) + 해외 출원 | "
            "경쟁사 IP 모니터링, 투자 유치 시 IP 실사 대비 |"
        )
        lines.append(
            "| **시리즈 B+** | IP 전략 팀 구성 + 라이선싱 시작 | "
            "IP 가치 평가, M&A 시 IP 실사 |"
        )
        lines.append(
            "| **상장/글로벌** | IP 수익화 본격화 + 글로벌 IP 관리 | "
            "다국적 IP 포트폴리오, 분쟁 대응 체계 |"
        )

        # IP 확보 우선순위 매트릭스
        lines.append("\n### IP 확보 우선순위 매트릭스\n")
        lines.append("| | 영향도 높음 | 영향도 낮음 |")
        lines.append("|---|----------|----------|")
        lines.append("| **확보 용이** | 즉시 확보 (상표, 저작권) | 선택적 확보 |")
        lines.append("| **확보 어려움** | 전략적 투자 (핵심 특허) | 보류/모니터링 |")

        formatted = "\n".join(lines)

        # LLM 전문가 전략 수립
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 IP 전략 컨설턴트입니다.\n"
                "IPR Landscaping(WIPO), Patent Analytics(Griliches 1990),\n"
                "Technology S-Curve(Foster 1986)를 기반으로\n"
                "사업 목표에 맞는 맞춤형 IP 전략을 수립하세요.\n\n"
                "반드시 다음을 포함하세요:\n"
                "1. **추천 전략 유형**: 5가지 전략 중 어떤 조합이 적합한지\n"
                "2. **90일 실행 계획**: 즉시 실행할 수 있는 구체적 행동 3~5가지\n"
                "3. **예상 비용**: IP 확보에 필요한 대략적 비용과 기간\n"
                "4. **리스크 대응**: IP 관련 잠재 리스크와 대응 방안\n"
                "5. **KPI**: IP 전략의 성과를 측정할 핵심 지표\n"
                "6. **벤치마크**: 유사 기업/산업의 IP 전략 사례\n\n"
                "학술 근거를 명시하고, 한국어로 구체적 수치를 포함해 답변하세요.\n"
                "주의: 이 전략은 참고용이며, 실제 IP 전략은 변리사와 상담하세요."
            ),
            user_prompt=(
                f"사업 목표: {business_goal}\n"
                f"현재 IP 현황: {current_ip or '정보 미제공'}\n\n"
                f"전략 수립 프레임워크:\n{formatted}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 전문가 IP 전략 권고\n\n{analysis}{_DISCLAIMER}"
