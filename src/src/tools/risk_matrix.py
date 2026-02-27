"""
법적 리스크 매트릭스 Tool.

법적 리스크를 발생확률 x 영향도로 정량화하여
5x5 매트릭스를 생성하고 우선순위를 결정합니다.

사용 방법:
  - action="create"     (기본): 사업/프로젝트의 법적 리스크 매트릭스 생성
  - action="assess":    개별 리스크 항목 심층 평가
  - action="prioritize": 여러 리스크 우선순위 결정 (Pareto 원칙)
  - action="mitigate":  리스크 완화 전략 수립

학술 근거:
  - ISO 31000:2018 (Risk Management — 리스크 관리 국제표준)
  - COSO ERM Framework (Enterprise Risk Management — 전사적 리스크 관리)
  - Kaplan & Garrick (1981) "On the Quantitative Definition of Risk"
  - ISO 31010 (Risk Assessment Techniques — Risk = Probability x Impact)

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬)

주의: 이 리스크 분석은 참고용이며, 최종 법률 판단은 반드시 전문 변호사에게 의뢰하세요.
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.risk_matrix")

_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 리스크 분석은 AI 기반 참고 자료이며, "
    "법적 효력이 없습니다. 최종 법률 판단은 반드시 전문 변호사에게 의뢰하세요.\n"
    "학술 근거: ISO 31000:2018, COSO ERM Framework, "
    "Kaplan & Garrick (1981), ISO 31010"
)

# ══════════════════════════════════════════════════════════════════
#  5x5 리스크 매트릭스 정의 (ISO 31010 기반)
# ══════════════════════════════════════════════════════════════════

PROBABILITY_SCALE: dict[int, dict[str, str]] = {
    1: {"label": "매우 낮음", "desc": "거의 발생하지 않음 (1% 미만)"},
    2: {"label": "낮음",     "desc": "드물게 발생 가능 (1~10%)"},
    3: {"label": "보통",     "desc": "가끔 발생 가능 (10~30%)"},
    4: {"label": "높음",     "desc": "자주 발생 가능 (30~60%)"},
    5: {"label": "매우 높음", "desc": "거의 확실 (60% 이상)"},
}

IMPACT_SCALE: dict[int, dict[str, str]] = {
    1: {"label": "미미", "desc": "사업 영향 거의 없음, 경미한 행정 조치"},
    2: {"label": "경미", "desc": "일시적 업무 지장, 소액 과태료"},
    3: {"label": "보통", "desc": "수천만원 벌금/과징금, 일부 사업 중단"},
    4: {"label": "심각", "desc": "수억원 벌금, 인허가 정지, 대표이사 형사처벌 가능"},
    5: {"label": "치명적", "desc": "사업 존속 위기, 대규모 손해배상, 형사처벌"},
}


def _risk_grade(score: int) -> tuple[str, str]:
    """리스크 점수(1~25)를 등급과 색상 라벨로 변환."""
    if score <= 6:
        return "낮음", "녹색"
    elif score <= 12:
        return "중간", "노란색"
    elif score <= 18:
        return "높음", "주황색"
    else:
        return "매우높음", "빨간색"


# ══════════════════════════════════════════════════════════════════
#  리스크 카테고리별 기본 데이터
# ══════════════════════════════════════════════════════════════════

RISK_CATEGORIES: dict[str, list[dict[str, Any]]] = {
    "규제위반": [
        {"name": "인허가 미취득 운영", "probability": 3, "impact": 5,
         "desc": "필수 인허가 없이 사업 영위 시 형사처벌 및 사업 중단"},
        {"name": "금융규제 위반", "probability": 3, "impact": 5,
         "desc": "자본시장법/전자금융거래법 위반 시 영업정지 및 과징금"},
        {"name": "광고 규제 위반", "probability": 4, "impact": 3,
         "desc": "표시광고법 위반으로 과징금 및 시정명령"},
    ],
    "계약분쟁": [
        {"name": "계약 조건 불이행", "probability": 3, "impact": 4,
         "desc": "납기 지연, 품질 미달 등으로 손해배상 청구"},
        {"name": "계약 해석 분쟁", "probability": 3, "impact": 3,
         "desc": "모호한 계약 조항으로 인한 해석 다툼"},
        {"name": "하도급 분쟁", "probability": 3, "impact": 4,
         "desc": "하도급법 위반으로 과징금 및 형사처벌"},
    ],
    "IP침해": [
        {"name": "특허 침해 소송", "probability": 2, "impact": 5,
         "desc": "경쟁사 특허 침해 시 손해배상 및 제품 판매 금지"},
        {"name": "상표권 분쟁", "probability": 3, "impact": 3,
         "desc": "유사 상표 사용으로 인한 상표권 침해 분쟁"},
        {"name": "영업비밀 유출", "probability": 3, "impact": 5,
         "desc": "핵심 기술/정보 유출로 경쟁력 상실 및 형사처벌"},
        {"name": "저작권 침해", "probability": 3, "impact": 3,
         "desc": "소프트웨어/콘텐츠 무단 사용으로 손해배상"},
    ],
    "개인정보유출": [
        {"name": "대규모 개인정보 유출", "probability": 3, "impact": 5,
         "desc": "매출액 3% 과징금, 집단 소송, 기업 이미지 타격"},
        {"name": "개인정보 무단 수집/이용", "probability": 4, "impact": 4,
         "desc": "동의 없는 수집/이용으로 과징금 및 형사처벌"},
        {"name": "해외 이전 규정 위반", "probability": 2, "impact": 4,
         "desc": "GDPR/개인정보보호법 해외 이전 요건 미충족"},
    ],
    "노동법위반": [
        {"name": "부당해고", "probability": 3, "impact": 3,
         "desc": "근로기준법 위반으로 원직복직 및 임금 지급 명령"},
        {"name": "임금체불", "probability": 2, "impact": 4,
         "desc": "3년 이하 징역 또는 3천만원 이하 벌금"},
        {"name": "산업재해 발생", "probability": 2, "impact": 5,
         "desc": "중대재해처벌법 — 1년 이상 징역 또는 10억원 이하 벌금"},
        {"name": "직장 내 괴롭힘/성희롱", "probability": 3, "impact": 4,
         "desc": "손해배상, 과태료, 기업 이미지 훼손"},
    ],
    "소비자보호": [
        {"name": "제품 결함 클레임", "probability": 3, "impact": 4,
         "desc": "제조물책임법에 따른 손해배상 + 리콜 비용"},
        {"name": "허위/과장 광고", "probability": 4, "impact": 3,
         "desc": "매출액 2% 이하 과징금 + 시정명령"},
        {"name": "환불/취소 거부", "probability": 3, "impact": 3,
         "desc": "전자상거래법 위반으로 과태료"},
    ],
    "환경규제": [
        {"name": "환경오염 배출 기준 초과", "probability": 2, "impact": 5,
         "desc": "영업정지 + 원상복구 비용 + 형사처벌"},
        {"name": "폐기물 부적정 처리", "probability": 3, "impact": 4,
         "desc": "7년 이하 징역 또는 7천만원 이하 벌금"},
        {"name": "화학물질 관리 소홀", "probability": 2, "impact": 5,
         "desc": "화학물질관리법 위반 — 5년 이하 징역"},
    ],
    "세무": [
        {"name": "세금 과소 신고", "probability": 3, "impact": 4,
         "desc": "가산세 + 세무조사 리스크"},
        {"name": "이전가격 문제", "probability": 2, "impact": 4,
         "desc": "국제 거래 시 이전가격 과세 조정"},
        {"name": "세금계산서 부정 발행", "probability": 2, "impact": 5,
         "desc": "3년 이하 징역 또는 세액 2배 이하 벌금"},
    ],
}


class RiskMatrixTool(BaseTool):
    """법적 리스크 매트릭스 도구 (CLO 법무IP처 소속).

    ISO 31000:2018 및 COSO ERM 프레임워크에 기반하여
    법적 리스크를 발생확률 x 영향도로 정량화하고
    5x5 매트릭스를 생성합니다.
    """

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "create")

        if action == "create":
            return await self._create(kwargs)
        elif action == "assess":
            return await self._assess(kwargs)
        elif action == "prioritize":
            return await self._prioritize(kwargs)
        elif action == "mitigate":
            return await self._mitigate(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "create, assess, prioritize, mitigate 중 하나를 사용하세요."
            )

    # ══════════════════════════════════════════
    #  create: 리스크 매트릭스 생성
    # ══════════════════════════════════════════

    async def _create(self, kwargs: dict[str, Any]) -> str:
        """특정 사업/프로젝트의 법적 리스크 매트릭스 생성."""
        name = kwargs.get("name", "미지정 사업")
        risks_text = kwargs.get("risks", "")

        lines = [
            f"## 법적 리스크 매트릭스",
            f"- **대상**: {name}",
            f"- **분석 기준**: ISO 31000:2018, COSO ERM Framework",
            f"- **산출 공식**: 리스크 점수 = 발생확률(1~5) x 영향도(1~5)\n",
        ]

        # 5x5 매트릭스 시각화
        lines.append("### 5x5 리스크 매트릭스 (발생확률 x 영향도)")
        lines.append("")
        lines.append("```")
        lines.append("영향도 -->  1(미미)  2(경미)  3(보통)  4(심각)  5(치명)")
        lines.append("확률 |")
        for p in range(5, 0, -1):
            p_label = PROBABILITY_SCALE[p]["label"]
            cells = []
            for imp in range(1, 6):
                score = p * imp
                grade, _ = _risk_grade(score)
                grade_short = {"낮음": "낮", "중간": "중", "높음": "높", "매우높음": "극"}[grade]
                cells.append(f" {score:2d}({grade_short})")
            line = f"  {p}({p_label:4s}) |{'|'.join(cells)}|"
            lines.append(line)
        lines.append("```")
        lines.append("")
        lines.append("등급 기준: 녹색(1~6 낮음) | 노란색(7~12 중간) | 주황색(13~18 높음) | 빨간색(19~25 매우높음)")
        lines.append("")

        # 카테고리별 리스크 항목
        lines.append("### 카테고리별 리스크 항목")
        lines.append("")

        all_risks: list[dict[str, Any]] = []
        risk_summary_for_llm: list[str] = []

        for category, risks in RISK_CATEGORIES.items():
            lines.append(f"#### {category}")
            lines.append("| 리스크 | 발생확률 | 영향도 | 점수 | 등급 | 설명 |")
            lines.append("|--------|---------|--------|------|------|------|")

            for risk in risks:
                score = risk["probability"] * risk["impact"]
                grade, color = _risk_grade(score)
                grade_icon = {
                    "녹색": "[녹색]", "노란색": "[노란색]",
                    "주황색": "[주황색]", "빨간색": "[빨간색]",
                }[color]

                lines.append(
                    f"| {risk['name']} | {risk['probability']} "
                    f"({PROBABILITY_SCALE[risk['probability']]['label']}) | "
                    f"{risk['impact']} ({IMPACT_SCALE[risk['impact']]['label']}) | "
                    f"**{score}** | {grade_icon} {grade} | {risk['desc']} |"
                )
                all_risks.append({
                    **risk, "score": score, "grade": grade, "category": category,
                })
                risk_summary_for_llm.append(
                    f"[{category}] {risk['name']}: "
                    f"확률 {risk['probability']} x 영향 {risk['impact']} = {score}점 ({grade})"
                )
            lines.append("")

        # 위험도별 분포 통계
        grade_counts = {"낮음": 0, "중간": 0, "높음": 0, "매우높음": 0}
        for r in all_risks:
            grade_counts[r["grade"]] += 1

        lines.append("### 리스크 분포 요약")
        lines.append(f"- **총 리스크 항목**: {len(all_risks)}건")
        lines.append(f"- [빨간색] 매우높음 (19~25): **{grade_counts['매우높음']}건**")
        lines.append(f"- [주황색] 높음 (13~18): **{grade_counts['높음']}건**")
        lines.append(f"- [노란색] 중간 (7~12): **{grade_counts['중간']}건**")
        lines.append(f"- [녹색] 낮음 (1~6): **{grade_counts['낮음']}건**")
        lines.append("")

        # TOP 5 리스크
        sorted_risks = sorted(all_risks, key=lambda x: x["score"], reverse=True)
        lines.append("### TOP 5 최고위험 리스크")
        for i, risk in enumerate(sorted_risks[:5], 1):
            grade_icon = {
                "낮음": "[녹색]", "중간": "[노란색]",
                "높음": "[주황색]", "매우높음": "[빨간색]",
            }[risk["grade"]]
            lines.append(
                f"  {i}. **{risk['name']}** ({risk['category']}) — "
                f"점수 {risk['score']} {grade_icon} {risk['grade']}"
            )
            lines.append(f"     {risk['desc']}")
        lines.append("")

        formatted = "\n".join(lines)
        risk_summary = "\n".join(risk_summary_for_llm)

        # LLM 교수급 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 리스크 관리(Enterprise Risk Management) 전문 교수입니다.\n"
                "ISO 31000:2018, COSO ERM Framework, Kaplan & Garrick(1981)의 "
                "리스크 정량화 이론을 기반으로 분석합니다.\n\n"
                "아래 리스크 매트릭스를 분석하여 다음을 답변하세요:\n\n"
                "1. **전체 리스크 프로필 평가** — 이 사업의 전반적 리스크 수준\n"
                "2. **연쇄 리스크 분석** — 하나의 리스크가 다른 리스크를 촉발하는 시나리오\n"
                "3. **리스크 허용 수준(Risk Appetite) 권고** — 어디까지 감수하고 어디서 대응해야 하는지\n"
                "4. **즉시 대응 필요 항목** — 빨간색/주황색 등급 항목의 구체적 대응 방안\n"
                "5. **모니터링 체계 제안** — KRI(Key Risk Indicator) 설정 방안\n\n"
                "한국어로, 비개발자(CEO)도 이해할 수 있게 답변하세요.\n"
                "학술적 근거를 반드시 포함하세요."
            ),
            user_prompt=(
                f"사업명: {name}\n"
                f"{'추가 리스크 정보: ' + risks_text if risks_text else ''}\n\n"
                f"리스크 매트릭스 결과:\n{risk_summary}"
            ),
        )

        return f"{formatted}\n\n## 전문가 분석\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  assess: 개별 리스크 심층 평가
    # ══════════════════════════════════════════

    async def _assess(self, kwargs: dict[str, Any]) -> str:
        """개별 리스크 항목 심층 평가."""
        risk_description = kwargs.get("risk_description", "")

        if not risk_description:
            return (
                "평가할 리스크(risk_description)를 입력해주세요.\n"
                "예: '핀테크 서비스에서 전자금융거래법 미등록 운영'"
            )

        # 관련 카테고리 참고 데이터
        related_risks: list[str] = []
        for category, risks in RISK_CATEGORIES.items():
            for risk in risks:
                related_risks.append(
                    f"[{category}] {risk['name']} — "
                    f"확률 {risk['probability']} x 영향 {risk['impact']} = "
                    f"{risk['probability'] * risk['impact']}점: {risk['desc']}"
                )

        lines = [
            "## 개별 리스크 심층 평가",
            f"- **평가 대상 리스크**: {risk_description}",
            "- **분석 프레임워크**: ISO 31000:2018 + COSO ERM\n",
            "### 평가 기준표",
            "",
            "**발생확률 척도**",
            "| 등급 | 확률 범위 | 설명 |",
            "|------|---------|------|",
        ]
        for level, info in PROBABILITY_SCALE.items():
            lines.append(f"| {level} ({info['label']}) | {info['desc']} |  |")

        lines.append("")
        lines.append("**영향도 척도**")
        lines.append("| 등급 | 영향 수준 | 설명 |")
        lines.append("|------|---------|------|")
        for level, info in IMPACT_SCALE.items():
            lines.append(f"| {level} ({info['label']}) | {info['desc']} |  |")

        formatted = "\n".join(lines)
        related_text = "\n".join(related_risks)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 법적 리스크 평가 전문 교수이자 리스크 관리 컨설턴트입니다.\n"
                "ISO 31000:2018, COSO ERM, Kaplan & Garrick(1981) 이론을 적용합니다.\n\n"
                "아래 리스크를 심층 평가하여 다음을 답변하세요:\n\n"
                "1. **리스크 식별** — 이 리스크의 정확한 정의와 범위\n"
                "2. **발생확률 평가** (1~5 척도) — 근거와 함께 점수 부여\n"
                "3. **영향도 평가** (1~5 척도) — 재무적/법적/평판 영향 각각\n"
                "4. **리스크 점수 산출** — 확률 x 영향도 = 최종 점수\n"
                "5. **근본 원인 분석** (Root Cause Analysis) — 왜 이 리스크가 존재하는지\n"
                "6. **선행 지표** (Leading Indicator) — 리스크가 현실화되기 전 조기 경보 신호\n"
                "7. **후행 지표** (Lagging Indicator) — 이미 발생했을 때 확인하는 지표\n"
                "8. **대응 전략** — 회피/완화/전가/수용 중 최적 전략\n\n"
                "한국어로, 비개발자도 이해할 수 있게 구체적으로 답변하세요."
            ),
            user_prompt=(
                f"평가 대상 리스크: {risk_description}\n\n"
                f"참고 — 유사 리스크 데이터:\n{related_text}"
            ),
        )

        return f"{formatted}\n\n## 심층 평가 결과\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  prioritize: 우선순위 결정
    # ══════════════════════════════════════════

    async def _prioritize(self, kwargs: dict[str, Any]) -> str:
        """여러 리스크 우선순위 결정 (Pareto 원칙 적용)."""
        risks_text = kwargs.get("risks", "")

        if not risks_text:
            return (
                "우선순위를 매길 리스크 목록(risks)을 입력해주세요.\n"
                "예: '전자금융거래법 위반, 개인정보 유출, 상표권 분쟁, 임금 체불, 세금 과소신고'"
            )

        # 기본 카테고리 데이터를 참고 자료로 제공
        all_risks_text: list[str] = []
        for category, risks in RISK_CATEGORIES.items():
            for risk in risks:
                score = risk["probability"] * risk["impact"]
                grade, _ = _risk_grade(score)
                all_risks_text.append(
                    f"[{category}] {risk['name']}: {score}점 ({grade}) — {risk['desc']}"
                )

        lines = [
            "## 리스크 우선순위 분석",
            "- **분석 원칙**: Pareto 원칙 (80/20 법칙) — 상위 20% 리스크가 전체 손실의 80%를 차지",
            "- **분석 기준**: ISO 31000:2018 + COSO ERM Framework\n",
            f"### 입력된 리스크 목록",
            f"{risks_text}\n",
        ]

        formatted = "\n".join(lines)
        reference_data = "\n".join(all_risks_text)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 리스크 관리(ERM) 전문 교수입니다.\n"
                "ISO 31000:2018, COSO ERM, Pareto 원칙을 기반으로 분석합니다.\n\n"
                "아래 리스크 목록의 우선순위를 결정하여 다음을 답변하세요:\n\n"
                "1. **각 리스크별 점수 산출** — 발생확률(1~5) x 영향도(1~5) = 리스크 점수\n"
                "2. **우선순위 순위표** — 점수 높은 순으로 정렬\n"
                "   등급: [녹색](1~6 낮음), [노란색](7~12 중간), [주황색](13~18 높음), [빨간색](19~25 매우높음)\n"
                "3. **Pareto 분석** — 상위 20% 리스크 식별 + 이 리스크들이 전체에 미치는 비중\n"
                "4. **리소스 배분 권고** — 어떤 리스크에 얼마나 리소스를 투입해야 하는지\n"
                "5. **대응 순서 로드맵** — 1주일/1개월/3개월 단위 대응 순서\n\n"
                "반드시 표 형식으로 정리하세요.\n"
                "한국어로, 비개발자도 이해할 수 있게 답변하세요."
            ),
            user_prompt=(
                f"우선순위 분석 대상 리스크:\n{risks_text}\n\n"
                f"참고 — 법적 리스크 DB:\n{reference_data}"
            ),
        )

        return f"{formatted}\n\n## 우선순위 분석 결과\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  mitigate: 리스크 완화 전략
    # ══════════════════════════════════════════

    async def _mitigate(self, kwargs: dict[str, Any]) -> str:
        """리스크 완화 전략 수립."""
        risk_description = kwargs.get("risk_description", "")

        if not risk_description:
            return (
                "완화 전략을 수립할 리스크(risk_description)를 입력해주세요.\n"
                "예: '개인정보 대규모 유출 리스크'"
            )

        lines = [
            "## 리스크 완화 전략 보고서",
            f"- **대상 리스크**: {risk_description}",
            "- **전략 프레임워크**: ISO 31000:2018 4T 전략\n",
            "### 4T 리스크 대응 전략 (ISO 31000)",
            "| 전략 | 영문 | 설명 | 적용 시기 |",
            "|------|------|------|----------|",
            "| **회피** | Terminate | 리스크 원인 활동 자체를 중단 | 리스크가 허용 수준 초과 시 |",
            "| **완화** | Treat | 확률/영향 줄이는 조치 실행 | 대부분의 리스크에 적용 |",
            "| **전가** | Transfer | 보험/계약으로 제3자에게 이전 | 재무적 영향이 큰 리스크 |",
            "| **수용** | Tolerate | 모니터링하면서 감수 | 리스크가 허용 수준 이내 시 |",
            "",
        ]

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 리스크 관리 전문 교수이자 법률 자문위원입니다.\n"
                "ISO 31000:2018의 4T 전략(Terminate, Treat, Transfer, Tolerate), "
                "COSO ERM Framework를 기반으로 분석합니다.\n\n"
                "아래 리스크에 대한 완화 전략을 수립하여 다음을 답변하세요:\n\n"
                "1. **리스크 현재 수준 평가** — 확률/영향도 점수 + 등급\n"
                "2. **목표 수준 설정** — 완화 후 달성할 목표 점수\n"
                "3. **4T 전략 분석** — 각 전략별 적용 가능성 + 비용 대비 효과\n"
                "4. **최적 완화 전략 권고** — 구체적 실행 방안 5가지\n"
                "5. **잔여 리스크(Residual Risk) 평가** — 완화 후에도 남는 리스크\n"
                "6. **비용-효과 분석** — 완화 조치별 예상 비용 vs 리스크 감소 효과\n"
                "7. **모니터링 계획** — KRI(Key Risk Indicator)와 모니터링 주기\n"
                "8. **비상 계획(Contingency Plan)** — 리스크가 현실화됐을 때 대응 절차\n\n"
                "한국어로, 비개발자도 이해할 수 있게 구체적으로 답변하세요.\n"
                "표와 구조를 활용해 가독성을 높이세요."
            ),
            user_prompt=(
                f"완화 전략 대상 리스크: {risk_description}"
            ),
        )

        return f"{formatted}\n\n## 완화 전략 분석 결과\n\n{analysis}{_DISCLAIMER}"
