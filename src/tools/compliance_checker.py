"""
컴플라이언스(법규 준수) 자동 검증 Tool.

사업/서비스가 관련 법규를 준수하는지 체크리스트 기반 자동 검증합니다.

사용 방법:
  - action="check"  (기본): 사업 유형별 법규 준수 체크리스트 생성 + 검증
  - action="audit":  전반적 컴플라이언스 감사 종합 보고
  - action="gap":    현행 준수 현황 vs 법적 요구사항 갭분석
  - action="checklist": 업종별 필수 법규 체크리스트 생성

학술 근거:
  - SOX Act Section 404 (내부통제 — 미국 상장회사의 재무보고 내부통제 의무)
  - OECD Guidelines on Corporate Governance (기업지배구조 가이드라인)
  - ISO 19600:2014 (Compliance Management Systems — 컴플라이언스 관리 체계 국제표준)
  - Basel III (금융기관 컴플라이언스 프레임워크)

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬)

주의: 이 검증은 참고용이며, 최종 법률 판단은 반드시 전문 변호사에게 의뢰하세요.
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.compliance_checker")

_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 컴플라이언스 검증은 AI 기반 참고 자료이며, "
    "법적 효력이 없습니다. 최종 법률 판단은 반드시 전문 변호사에게 의뢰하세요.\n"
    "학술 근거: SOX Act Section 404, OECD Corporate Governance Guidelines, "
    "ISO 19600:2014, Basel III Framework"
)

# ══════════════════════════════════════════════════════════════════
#  업종별 주요 규제 법령 데이터베이스
# ══════════════════════════════════════════════════════════════════

INDUSTRY_REGULATIONS: dict[str, dict[str, Any]] = {
    "핀테크": {
        "display": "핀테크 (금융기술)",
        "regulations": [
            {
                "law": "전자금융거래법",
                "items": [
                    {"check": "전자금융업 등록/허가 완료", "risk": "상", "penalty": "5년 이하 징역 또는 5천만원 이하 벌금"},
                    {"check": "이용자 자금 보호 조치(별도 관리)", "risk": "상", "penalty": "등록 취소 가능"},
                    {"check": "전자금융거래 안전성 확보 의무 이행", "risk": "상", "penalty": "5천만원 이하 과태료"},
                    {"check": "접근매체 관리 기준 준수", "risk": "중", "penalty": "3천만원 이하 과태료"},
                    {"check": "거래내역 보존(5년)", "risk": "중", "penalty": "3천만원 이하 과태료"},
                ],
            },
            {
                "law": "신용정보법",
                "items": [
                    {"check": "본인신용정보관리업 허가/등록", "risk": "상", "penalty": "5년 이하 징역 또는 5천만원 이하 벌금"},
                    {"check": "신용정보 수집/이용 동의 절차", "risk": "상", "penalty": "5천만원 이하 과태료"},
                    {"check": "개인신용평점 산출 시 차별금지 조치", "risk": "중", "penalty": "시정명령"},
                ],
            },
            {
                "law": "자본시장법",
                "items": [
                    {"check": "투자중개업/투자자문업 인가", "risk": "상", "penalty": "5년 이하 징역 또는 2억원 이하 벌금"},
                    {"check": "투자자 적합성 확인 절차", "risk": "중", "penalty": "과징금"},
                    {"check": "설명의무 이행", "risk": "중", "penalty": "손해배상 책임"},
                ],
            },
            {
                "law": "개인정보보호법",
                "items": [
                    {"check": "개인정보 수집/이용 동의", "risk": "상", "penalty": "매출액 3% 이하 과징금"},
                    {"check": "개인정보 처리방침 공개", "risk": "중", "penalty": "1천만원 이하 과태료"},
                    {"check": "개인정보 보호책임자 지정", "risk": "중", "penalty": "1천만원 이하 과태료"},
                ],
            },
        ],
    },
    "이커머스": {
        "display": "이커머스 (전자상거래)",
        "regulations": [
            {
                "law": "전자상거래법",
                "items": [
                    {"check": "통신판매업 신고 완료", "risk": "상", "penalty": "1년 이하 징역 또는 1억원 이하 벌금"},
                    {"check": "청약철회(환불) 규정 고지", "risk": "상", "penalty": "1억원 이하 과태료"},
                    {"check": "재화 등 정보 표시(가격, 배송비 등)", "risk": "중", "penalty": "5천만원 이하 과태료"},
                    {"check": "소비자 피해보상보험 가입", "risk": "중", "penalty": "시정명령 + 과태료"},
                    {"check": "미성년자 거래 시 법정대리인 동의", "risk": "중", "penalty": "거래 취소 리스크"},
                ],
            },
            {
                "law": "소비자기본법",
                "items": [
                    {"check": "소비자 피해 구제 절차 마련", "risk": "중", "penalty": "시정명령"},
                    {"check": "결함 상품 리콜 체계 구축", "risk": "상", "penalty": "3년 이하 징역 또는 5천만원 이하 벌금"},
                    {"check": "표시/광고 적정성 확보", "risk": "중", "penalty": "시정명령 + 과징금"},
                ],
            },
            {
                "law": "개인정보보호법",
                "items": [
                    {"check": "개인정보 수집/이용 동의", "risk": "상", "penalty": "매출액 3% 이하 과징금"},
                    {"check": "결제정보 암호화 저장", "risk": "상", "penalty": "5년 이하 징역 또는 5천만원 이하 벌금"},
                    {"check": "개인정보 파기 절차", "risk": "중", "penalty": "3천만원 이하 과태료"},
                ],
            },
            {
                "law": "표시광고법",
                "items": [
                    {"check": "허위/과장 광고 금지 준수", "risk": "상", "penalty": "매출액 2% 이하 과징금"},
                    {"check": "추천/후기 광고 시 경제적 이해관계 표시", "risk": "중", "penalty": "시정명령"},
                    {"check": "비교 광고 시 객관적 근거 확보", "risk": "중", "penalty": "과징금"},
                ],
            },
        ],
    },
    "AI서비스": {
        "display": "AI 서비스 (인공지능)",
        "regulations": [
            {
                "law": "개인정보보호법 (AI 관련)",
                "items": [
                    {"check": "AI 학습 데이터의 개인정보 동의 확보", "risk": "상", "penalty": "매출액 3% 이하 과징금"},
                    {"check": "자동화된 의사결정에 대한 설명 의무", "risk": "상", "penalty": "EU GDPR 위반 시 최대 매출 4%"},
                    {"check": "프로파일링 동의 및 거부권 보장", "risk": "중", "penalty": "시정명령 + 과태료"},
                    {"check": "AI 생성 결과물의 개인정보 포함 여부 검토", "risk": "중", "penalty": "과태료"},
                ],
            },
            {
                "law": "저작권법 (AI 관련)",
                "items": [
                    {"check": "AI 학습 데이터 저작권 적법성 확보", "risk": "상", "penalty": "손해배상 + 형사처벌 가능"},
                    {"check": "AI 생성물 저작권 귀속 관계 정리", "risk": "중", "penalty": "권리 분쟁 리스크"},
                    {"check": "오픈소스 라이선스 준수", "risk": "중", "penalty": "저작권 침해 + 손해배상"},
                ],
            },
            {
                "law": "정보통신망법",
                "items": [
                    {"check": "AI 서비스 이용약관 게시", "risk": "중", "penalty": "3천만원 이하 과태료"},
                    {"check": "AI 챗봇 등 자동응답 시 AI임을 고지", "risk": "중", "penalty": "이용자 기만 리스크"},
                    {"check": "딥페이크 등 합성 콘텐츠 표시", "risk": "상", "penalty": "5년 이하 징역 또는 5천만원 이하 벌금"},
                ],
            },
            {
                "law": "EU AI Act (참고)",
                "items": [
                    {"check": "AI 시스템 위험 등급 분류", "risk": "중", "penalty": "최대 3,500만 유로 또는 전세계 매출 7%"},
                    {"check": "고위험 AI 시스템 적합성 평가", "risk": "상", "penalty": "최대 1,500만 유로"},
                    {"check": "AI 투명성 의무(모델카드 등) 이행", "risk": "중", "penalty": "최대 750만 유로"},
                ],
            },
        ],
    },
    "개인정보": {
        "display": "개인정보 처리 사업",
        "regulations": [
            {
                "law": "개인정보보호법",
                "items": [
                    {"check": "개인정보 수집/이용 목적 명시 및 동의", "risk": "상", "penalty": "매출액 3% 이하 과징금"},
                    {"check": "개인정보 처리방침 수립/공개", "risk": "상", "penalty": "1천만원 이하 과태료"},
                    {"check": "개인정보 보호책임자(CPO) 지정", "risk": "중", "penalty": "1천만원 이하 과태료"},
                    {"check": "개인정보 영향평가 실시(공공기관)", "risk": "중", "penalty": "시정명령"},
                    {"check": "개인정보 유출 통지 절차 마련", "risk": "상", "penalty": "5억원 이하 과징금"},
                    {"check": "개인정보 파기 절차 수립", "risk": "중", "penalty": "3천만원 이하 과태료"},
                    {"check": "CCTV 운영 시 안내판 설치", "risk": "하", "penalty": "1천만원 이하 과태료"},
                ],
            },
            {
                "law": "정보통신망법",
                "items": [
                    {"check": "접근권한 최소화 및 접근기록 보관", "risk": "상", "penalty": "3천만원 이하 과태료"},
                    {"check": "개인정보 암호화 저장/전송", "risk": "상", "penalty": "3천만원 이하 과태료"},
                    {"check": "개인정보 처리 위탁 시 공개", "risk": "중", "penalty": "3천만원 이하 과태료"},
                ],
            },
        ],
    },
    "노동법": {
        "display": "노동/인사 관련",
        "regulations": [
            {
                "law": "근로기준법",
                "items": [
                    {"check": "근로계약서 서면 교부", "risk": "상", "penalty": "500만원 이하 벌금"},
                    {"check": "최저임금 이상 지급", "risk": "상", "penalty": "3년 이하 징역 또는 2천만원 이하 벌금"},
                    {"check": "주 52시간 근무 준수", "risk": "상", "penalty": "2년 이하 징역 또는 2천만원 이하 벌금"},
                    {"check": "연차휴가 부여 및 사용 촉진", "risk": "중", "penalty": "2년 이하 징역 또는 2천만원 이하 벌금"},
                    {"check": "퇴직급여 지급 준비", "risk": "상", "penalty": "3년 이하 징역 또는 3천만원 이하 벌금"},
                    {"check": "직장 내 괴롭힘 예방 교육", "risk": "중", "penalty": "500만원 이하 과태료"},
                ],
            },
            {
                "law": "산업안전보건법",
                "items": [
                    {"check": "안전보건관리체계 구축", "risk": "상", "penalty": "1년 이하 징역 또는 1천만원 이하 벌금"},
                    {"check": "안전보건교육 실시", "risk": "중", "penalty": "500만원 이하 과태료"},
                    {"check": "작업환경측정 실시", "risk": "중", "penalty": "1천만원 이하 과태료"},
                ],
            },
            {
                "law": "남녀고용평등법",
                "items": [
                    {"check": "성희롱 예방 교육 실시", "risk": "상", "penalty": "500만원 이하 과태료"},
                    {"check": "육아휴직 보장", "risk": "상", "penalty": "500만원 이하 벌금"},
                    {"check": "동일가치 동일임금 준수", "risk": "중", "penalty": "3년 이하 징역 또는 3천만원 이하 벌금"},
                ],
            },
        ],
    },
    "헬스케어": {
        "display": "헬스케어/의료",
        "regulations": [
            {
                "law": "의료법",
                "items": [
                    {"check": "의료기관 개설 허가/신고", "risk": "상", "penalty": "5년 이하 징역 또는 5천만원 이하 벌금"},
                    {"check": "비대면 진료 요건 충족", "risk": "상", "penalty": "면허 정지/취소"},
                    {"check": "의료광고 심의 통과", "risk": "중", "penalty": "1년 이하 징역 또는 1천만원 이하 벌금"},
                ],
            },
            {
                "law": "의료기기법",
                "items": [
                    {"check": "의료기기 허가/인증/신고 완료", "risk": "상", "penalty": "5년 이하 징역 또는 5천만원 이하 벌금"},
                    {"check": "GMP(제조품질관리) 기준 충족", "risk": "상", "penalty": "허가 취소"},
                    {"check": "임상시험 승인(필요 시)", "risk": "상", "penalty": "허가 불가"},
                ],
            },
            {
                "law": "개인정보보호법 (민감정보)",
                "items": [
                    {"check": "건강정보 등 민감정보 별도 동의", "risk": "상", "penalty": "매출액 3% 이하 과징금"},
                    {"check": "의료기록 보존 기간 준수", "risk": "중", "penalty": "과태료"},
                ],
            },
        ],
    },
    "플랫폼": {
        "display": "플랫폼 (중개 서비스)",
        "regulations": [
            {
                "law": "전자상거래법",
                "items": [
                    {"check": "통신판매중개자 의무 이행", "risk": "상", "penalty": "1억원 이하 과태료"},
                    {"check": "판매자 신원정보 제공", "risk": "중", "penalty": "5천만원 이하 과태료"},
                    {"check": "소비자 피해 방지 조치", "risk": "중", "penalty": "시정명령"},
                ],
            },
            {
                "law": "온라인 플랫폼 공정화법",
                "items": [
                    {"check": "이용사업자와 서면계약 체결", "risk": "상", "penalty": "시정명령 + 과징금"},
                    {"check": "중요 정보(수수료, 정산주기 등) 사전 고지", "risk": "중", "penalty": "과태료"},
                    {"check": "검색순위 결정 기준 공개", "risk": "중", "penalty": "과태료"},
                    {"check": "데이터 이동권 보장", "risk": "중", "penalty": "시정명령"},
                ],
            },
            {
                "law": "개인정보보호법",
                "items": [
                    {"check": "개인정보 수집/이용 동의", "risk": "상", "penalty": "매출액 3% 이하 과징금"},
                    {"check": "제3자 제공 동의", "risk": "상", "penalty": "5년 이하 징역 또는 5천만원 이하 벌금"},
                ],
            },
        ],
    },
    "콘텐츠": {
        "display": "콘텐츠/미디어",
        "regulations": [
            {
                "law": "저작권법",
                "items": [
                    {"check": "저작물 이용 허락/라이선스 확보", "risk": "상", "penalty": "5년 이하 징역 또는 5천만원 이하 벌금"},
                    {"check": "저작인격권 존중 (성명표시 등)", "risk": "중", "penalty": "손해배상"},
                    {"check": "2차적저작물 작성 허락", "risk": "중", "penalty": "저작권 침해"},
                ],
            },
            {
                "law": "게임산업진흥법",
                "items": [
                    {"check": "게임물 등급분류 취득", "risk": "상", "penalty": "5년 이하 징역 또는 5천만원 이하 벌금"},
                    {"check": "확률형 아이템 확률 공개", "risk": "상", "penalty": "과태료 + 등급 취소"},
                    {"check": "게임 과몰입 방지 조치", "risk": "중", "penalty": "시정명령"},
                ],
            },
            {
                "law": "영상물등급위원회 관련법",
                "items": [
                    {"check": "영상물 등급분류 취득(해당 시)", "risk": "중", "penalty": "과태료"},
                    {"check": "청소년 유해 콘텐츠 접근 제한", "risk": "상", "penalty": "3년 이하 징역 또는 3천만원 이하 벌금"},
                ],
            },
        ],
    },
}

# ══════════════════════════════════════════════════════════════════
#  컴플라이언스 영역별 감사 항목 (audit 액션용)
# ══════════════════════════════════════════════════════════════════

AUDIT_DOMAINS: dict[str, list[str]] = {
    "개인정보보호": [
        "개인정보 수집/이용 동의 절차",
        "개인정보 처리방침 게시 여부",
        "개인정보 보호책임자(CPO) 지정",
        "개인정보 유출 대응 계획",
        "개인정보 제3자 제공/위탁 관리",
        "개인정보 파기 절차",
        "해외 이전 시 적정성 평가",
    ],
    "금융규제": [
        "금융업 인허가/등록 현황",
        "자금세탁방지(AML) 체계",
        "고객확인(KYC) 절차",
        "내부통제 시스템 (SOX 404 기준)",
        "이해충돌 방지 정책",
        "금융소비자 보호 체계",
    ],
    "노동법": [
        "근로계약서 교부 여부",
        "최저임금/근로시간 준수",
        "4대보험 가입",
        "퇴직급여 제도",
        "성희롱 예방 교육",
        "직장 내 괴롭힘 방지",
    ],
    "세무": [
        "법인세 신고 적정성",
        "부가세 신고/납부 현황",
        "원천징수 이행 여부",
        "세금계산서 발행 의무",
        "이전가격(Transfer Pricing) 적정성",
    ],
    "지식재산": [
        "특허/상표 출원 현황",
        "영업비밀 관리 체계",
        "오픈소스 라이선스 준수",
        "직무발명 보상 규정",
        "IP 계약 관리 현황",
    ],
    "기업지배구조": [
        "이사회 구성 및 운영 (OECD 가이드라인)",
        "감사위원회/감사 기능",
        "내부고발(공익신고) 시스템",
        "윤리경영 규정",
        "이해관계자 소통 체계",
    ],
    "환경/ESG": [
        "환경영향평가 이행",
        "폐기물 처리 규정 준수",
        "탄소배출 관리 체계",
        "ESG 보고서 작성",
        "공급망 실사(Due Diligence)",
    ],
}


class ComplianceCheckerTool(BaseTool):
    """컴플라이언스(법규 준수) 자동 검증 도구 (CLO 법무IP처 소속).

    ISO 19600 기반 컴플라이언스 관리 체계에 따라 사업/서비스의
    법규 준수 여부를 체크리스트 방식으로 자동 검증합니다.
    """

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "check")

        if action == "check":
            return await self._check(kwargs)
        elif action == "audit":
            return await self._audit(kwargs)
        elif action == "gap":
            return await self._gap(kwargs)
        elif action == "checklist":
            return await self._checklist(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "check, audit, gap, checklist 중 하나를 사용하세요."
            )

    # ══════════════════════════════════════════
    #  check: 사업 유형별 법규 준수 검증
    # ══════════════════════════════════════════

    async def _check(self, kwargs: dict[str, Any]) -> str:
        """특정 사업 유형에 대한 법규 준수 체크리스트 생성 + 검증."""
        business_type = kwargs.get("business_type", "")
        name = kwargs.get("name", "미지정 사업")

        if not business_type:
            available = ", ".join(INDUSTRY_REGULATIONS.keys())
            return (
                f"사업 유형(business_type)을 입력해주세요.\n"
                f"지원 유형: {available}"
            )

        reg_data = INDUSTRY_REGULATIONS.get(business_type)
        if reg_data is None:
            available = ", ".join(INDUSTRY_REGULATIONS.keys())
            return (
                f"'{business_type}'은(는) 지원하지 않는 유형입니다.\n"
                f"지원 유형: {available}"
            )

        display_name = reg_data["display"]
        regulations = reg_data["regulations"]

        # 체크리스트 생성
        lines = [
            f"## 컴플라이언스 검증 보고서",
            f"- **사업명**: {name}",
            f"- **사업 유형**: {display_name}",
            f"- **검증 기준**: ISO 19600 (컴플라이언스 관리 체계)\n",
        ]

        total_items = 0
        high_risk_items: list[str] = []
        all_items_text: list[str] = []

        for reg_group in regulations:
            law_name = reg_group["law"]
            items = reg_group["items"]
            lines.append(f"### [{law_name}]")
            lines.append("| 순번 | 체크 항목 | 위험도 | 위반 시 벌칙 | 상태 |")
            lines.append("|------|----------|--------|------------|------|")

            for i, item in enumerate(items, 1):
                total_items += 1
                risk_icon = {"상": "[위험]", "중": "[주의]", "하": "[참고]"}.get(item["risk"], "")
                lines.append(
                    f"| {i} | {item['check']} | {risk_icon} {item['risk']} | "
                    f"{item['penalty']} | 확인필요 |"
                )
                all_items_text.append(f"- [{law_name}] {item['check']} (위험도: {item['risk']})")
                if item["risk"] == "상":
                    high_risk_items.append(f"[{law_name}] {item['check']} — 벌칙: {item['penalty']}")

            lines.append("")

        # 요약 통계
        lines.append("---")
        lines.append(f"### 검증 요약")
        lines.append(f"- **총 검사 항목**: {total_items}건")
        lines.append(f"- **상 위험 항목**: {len(high_risk_items)}건 (우선 확인 필요)")
        lines.append(f"- **관련 법령 수**: {len(regulations)}개\n")

        if high_risk_items:
            lines.append("### [긴급] 상 위험 항목 (우선 확인 필요)")
            for idx, item in enumerate(high_risk_items, 1):
                lines.append(f"  {idx}. {item}")
            lines.append("")

        formatted = "\n".join(lines)
        items_summary = "\n".join(all_items_text)

        # LLM 교수급 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 기업 컴플라이언스(법규 준수) 전문 교수이자 법률 자문위원입니다.\n"
                "SOX Act Section 404, OECD 기업지배구조 가이드라인, ISO 19600, "
                "Basel III 프레임워크를 기반으로 분석합니다.\n\n"
                "아래 컴플라이언스 체크리스트를 분석하여 다음을 답변하세요:\n\n"
                "1. **종합 컴플라이언스 위험도 평가** (상/중/하 + 근거)\n"
                "2. **가장 시급한 준수 항목 TOP 5** — 미준수 시 사업 존속 위험인 항목\n"
                "3. **업종별 규제 트렌드** — 최근 강화되고 있는 규제 방향\n"
                "4. **실무 대응 로드맵** — 단계별(즉시/1개월/3개월/6개월) 대응 계획\n"
                "5. **비용 최적화 팁** — 컴플라이언스 비용을 줄이면서 준수하는 방법\n\n"
                "한국어로, 비개발자(CEO)도 이해할 수 있게 쉽게 답변하세요.\n"
                "각 항목에 학술적/법적 근거를 반드시 포함하세요."
            ),
            user_prompt=(
                f"사업명: {name}\n"
                f"사업 유형: {display_name}\n\n"
                f"체크리스트 항목:\n{items_summary}"
            ),
        )

        return f"{formatted}\n\n## 전문가 분석\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  audit: 전반적 컴플라이언스 감사
    # ══════════════════════════════════════════

    async def _audit(self, kwargs: dict[str, Any]) -> str:
        """전반적 컴플라이언스 감사 — 주요 법규 영역별 준수 현황 종합 보고."""
        name = kwargs.get("name", "미지정 사업")
        business_type = kwargs.get("business_type", "")

        lines = [
            f"## 컴플라이언스 종합 감사 보고서",
            f"- **대상**: {name}",
            f"- **감사 기준**: SOX Act Section 404, OECD Corporate Governance, ISO 19600\n",
        ]

        total_domains = 0
        total_items = 0
        all_items_for_llm: list[str] = []

        for domain, checks in AUDIT_DOMAINS.items():
            total_domains += 1
            lines.append(f"### {total_domains}. {domain} 영역")
            lines.append("| 순번 | 감사 항목 | 현황 |")
            lines.append("|------|----------|------|")
            for i, check_item in enumerate(checks, 1):
                total_items += 1
                lines.append(f"| {i} | {check_item} | 확인필요 |")
                all_items_for_llm.append(f"[{domain}] {check_item}")
            lines.append("")

        lines.append("---")
        lines.append("### 감사 요약 통계")
        lines.append(f"- **감사 영역**: {total_domains}개")
        lines.append(f"- **총 감사 항목**: {total_items}건")
        lines.append("")

        formatted = "\n".join(lines)
        items_summary = "\n".join(all_items_for_llm)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 기업 컴플라이언스 감사 전문가이자 법학 교수입니다.\n"
                "SOX Act Section 404(내부통제), OECD 기업지배구조 가이드라인, "
                "ISO 19600(컴플라이언스 관리), Basel III를 기반으로 분석합니다.\n\n"
                "아래 감사 항목을 종합적으로 분석하여 다음을 답변하세요:\n\n"
                "1. **영역별 컴플라이언스 성숙도 평가** (5단계: 초기-반복-정의-관리-최적화)\n"
                "2. **크로스 영역 리스크** — 여러 영역에 걸쳐 발생할 수 있는 복합 리스크\n"
                "3. **최우선 개선 영역 3가지** — 근거와 함께\n"
                "4. **컴플라이언스 프로그램 구축 권고안** — ISO 19600 기반 단계별 계획\n"
                "5. **경영진 보고 요약** — CEO에게 보고할 핵심 사항 3줄 요약\n\n"
                "한국어로, 비개발자도 이해할 수 있게 답변하세요."
            ),
            user_prompt=(
                f"감사 대상: {name}\n"
                f"사업 유형: {business_type or '미지정'}\n\n"
                f"감사 항목 목록:\n{items_summary}"
            ),
        )

        return f"{formatted}\n\n## 감사 전문가 분석\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  gap: 갭분석 (현행 vs 요구사항)
    # ══════════════════════════════════════════

    async def _gap(self, kwargs: dict[str, Any]) -> str:
        """현행 준수 현황 vs 법적 요구사항 갭분석."""
        current_status = kwargs.get("current_status", "")
        name = kwargs.get("name", "미지정 사업")
        business_type = kwargs.get("business_type", "")

        if not current_status:
            return (
                "현재 상황(current_status)을 텍스트로 입력해주세요.\n"
                "예: '개인정보 처리방침은 있으나 CPO 미지정, 직원 교육 미실시'"
            )

        # 관련 감사 영역 요구사항 모음
        requirements: list[str] = []
        for domain, checks in AUDIT_DOMAINS.items():
            for check_item in checks:
                requirements.append(f"[{domain}] {check_item}")

        if business_type and business_type in INDUSTRY_REGULATIONS:
            reg_data = INDUSTRY_REGULATIONS[business_type]
            for reg_group in reg_data["regulations"]:
                for item in reg_group["items"]:
                    requirements.append(
                        f"[{reg_group['law']}] {item['check']} (위험도: {item['risk']})"
                    )

        requirements_text = "\n".join(requirements)

        lines = [
            f"## 컴플라이언스 갭분석 보고서",
            f"- **대상**: {name}",
            f"- **사업 유형**: {business_type or '미지정'}",
            f"- **분석 기준**: ISO 19600 + SOX Act Section 404\n",
            f"### 현재 상황 (입력된 정보)",
            f"{current_status}\n",
            f"### 법적 요구사항 (대조 기준) — 총 {len(requirements)}건",
        ]

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 기업 컴플라이언스 갭분석 전문가이자 법학 교수입니다.\n"
                "ISO 19600, SOX Act Section 404, OECD 가이드라인 기반으로 분석합니다.\n\n"
                "아래 '현재 상황'과 '법적 요구사항'을 대조하여 갭분석을 수행하세요:\n\n"
                "1. **준수 현황 매트릭스** — 각 요구사항별 (준수/부분준수/미준수/확인불가) 분류\n"
                "2. **핵심 갭(Gap) 항목** — 미준수 중 가장 위험한 항목 순서로\n"
                "3. **갭 해소 로드맵** — 즉시/단기(1개월)/중기(3개월)/장기(6개월) 단계별\n"
                "4. **필요 리소스 추정** — 인력, 비용, 시간 개략 추정\n"
                "5. **Quick Win 항목** — 적은 노력으로 빠르게 해소 가능한 갭 3가지\n\n"
                "한국어로, 비개발자도 이해할 수 있게 구체적으로 답변하세요.\n"
                "표와 구조를 활용해 가독성을 높이세요."
            ),
            user_prompt=(
                f"대상: {name}\n"
                f"사업 유형: {business_type or '미지정'}\n\n"
                f"■ 현재 상황:\n{current_status}\n\n"
                f"■ 법적 요구사항 목록:\n{requirements_text}"
            ),
        )

        return f"{formatted}\n\n## 갭분석 결과\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  checklist: 업종별 필수 법규 체크리스트
    # ══════════════════════════════════════════

    async def _checklist(self, kwargs: dict[str, Any]) -> str:
        """업종별 필수 법규 체크리스트 생성."""
        industry = kwargs.get("industry", "")

        if not industry:
            available = ", ".join(INDUSTRY_REGULATIONS.keys())
            return (
                f"업종(industry)을 입력해주세요.\n"
                f"기본 제공 업종: {available}\n"
                "위 목록에 없는 업종도 입력 가능합니다 (AI가 분석합니다)."
            )

        # 기본 데이터가 있는 업종인지 확인
        reg_data = INDUSTRY_REGULATIONS.get(industry)

        if reg_data:
            display_name = reg_data["display"]
            regulations = reg_data["regulations"]

            lines = [
                f"## {display_name} 필수 법규 체크리스트\n",
            ]

            total_items = 0
            items_for_llm: list[str] = []
            for reg_group in regulations:
                law_name = reg_group["law"]
                items = reg_group["items"]
                lines.append(f"### {law_name}")
                for i, item in enumerate(items, 1):
                    total_items += 1
                    risk_icon = {"상": "[위험]", "중": "[주의]", "하": "[참고]"}.get(item["risk"], "")
                    lines.append(f"  {i}. [ ] {item['check']} — {risk_icon} 위험도 {item['risk']}")
                    items_for_llm.append(f"[{law_name}] {item['check']}")
                lines.append("")

            lines.append(f"**총 {total_items}개 필수 체크 항목**")
            formatted = "\n".join(lines)
            items_summary = "\n".join(items_for_llm)
        else:
            formatted = f"## {industry} 필수 법규 체크리스트\n\n(기본 데이터 없음 — AI가 분석합니다)"
            items_summary = f"업종: {industry} (기본 데이터 없음)"

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 기업 법규 준수(컴플라이언스) 전문 교수입니다.\n"
                "ISO 19600, SOX Act Section 404, OECD 가이드라인을 기반으로 분석합니다.\n\n"
                "해당 업종의 필수 법규 체크리스트에 대해 다음을 답변하세요:\n\n"
                "1. **각 항목의 중요도 설명** — 왜 이 항목을 반드시 확인해야 하는지\n"
                "2. **놓치기 쉬운 규제 3가지** — 체크리스트에 없지만 주의해야 할 것\n"
                "3. **업종별 규제 특수성** — 이 업종만의 특별한 규제 이슈\n"
                "4. **준수 우선순위** — 어떤 항목부터 확인해야 하는지 순서\n"
                "5. **자주 발생하는 위반 사례** — 실무에서 흔히 놓치는 부분\n\n"
                "한국어로, 비개발자(CEO)도 이해할 수 있게 답변하세요."
            ),
            user_prompt=(
                f"업종: {industry}\n\n"
                f"체크리스트 항목:\n{items_summary}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 전문가 분석\n\n{analysis}{_DISCLAIMER}"
