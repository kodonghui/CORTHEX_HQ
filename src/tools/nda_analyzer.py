"""
NDA(비밀유지계약) 분석 Tool.

비밀유지계약(NDA/기밀유지계약) 조항별 리스크 분석,
불리 조항 탐지, 비교분석, 초안 가이드라인 제공.

사용 방법:
  - action="analyze" (기본): NDA 텍스트 입력 → 조항별 리스크 분석
  - action="compare":       두 NDA 비교 (우리 측 vs 상대 측)
  - action="checklist":     NDA 유형별 필수/권장 조항 체크리스트
  - action="draft_guide":   NDA 초안 작성 가이드라인

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬 + re 모듈)

학술 기반:
  - Pooley (2013) "Trade Secrets" — 영업비밀 보호의 NDA 역할
  - Halligan & Weyand (2016) "Trade Secret Asset Management"
  - Decker (2012) "Drafting Effective Nondisclosure Agreements"
  - WIPO Model NDA Template — 국제 기준 NDA 구조
  - 한국 부정경쟁방지법 §2(2) — 영업비밀 3요소(비공지성, 경제적유용성, 비밀관리성)

주의: 이 분석은 참고용이며, 중요한 NDA는 반드시 변호사 검토를 받으세요.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.nda_analyzer")

_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 NDA 분석은 참고용이며, "
    "중요한 계약은 반드시 변호사 검토를 받으세요. "
    "(Pooley 2013, WIPO Model NDA 기반 분석)"
)

# ══════════════════════════════════════════
#  NDA 필수 조항 (WIPO Model + Decker 2012)
# ══════════════════════════════════════════

NDA_ESSENTIAL_CLAUSES: dict[str, dict[str, Any]] = {
    "정의조항": {
        "keywords": ["비밀정보", "기밀정보", "confidential information", "비밀유지", "기밀"],
        "importance": "필수",
        "desc": "비밀정보의 범위와 정의 — NDA의 핵심. 범위가 너무 넓으면 실효성 저하",
        "risk_if_missing": "비밀정보 범위 불명확 → 분쟁 시 보호 불가능",
    },
    "의무범위": {
        "keywords": ["사용 금지", "제3자", "비밀유지 의무", "누설", "공개하지"],
        "importance": "필수",
        "desc": "수신자의 비밀유지 의무 범위 (사용제한, 제3자 공개금지 등)",
        "risk_if_missing": "의무 범위 불분명 → 수신자가 자유롭게 사용 가능",
    },
    "예외사항": {
        "keywords": ["공지", "공개된", "독자적", "법원", "정부기관", "예외"],
        "importance": "필수",
        "desc": "비밀유지 의무 예외 (이미 공개된 정보, 독자 개발, 법적 의무 등)",
        "risk_if_missing": "합리적 예외 없이 모든 정보 비밀 취급 → 비현실적 의무",
    },
    "유효기간": {
        "keywords": ["유효기간", "계약기간", "존속", "효력", "개월", "년간"],
        "importance": "필수",
        "desc": "NDA 유효기간 + 비밀유지 의무 존속기간 (보통 2~5년)",
        "risk_if_missing": "기간 불명확 → 영구적 의무 해석 가능 (과도)",
    },
    "반환·파기": {
        "keywords": ["반환", "파기", "삭제", "반납", "폐기"],
        "importance": "필수",
        "desc": "계약 종료 시 비밀정보 반환/파기 의무",
        "risk_if_missing": "정보 반환 의무 없음 → 종료 후에도 정보 보유 가능",
    },
    "손해배상": {
        "keywords": ["손해배상", "위약금", "배상", "손해", "위반 시"],
        "importance": "권장",
        "desc": "위반 시 손해배상 조항 (금지청구 포함 여부 확인)",
        "risk_if_missing": "위반 시 제재 수단 약함",
    },
    "관할·준거법": {
        "keywords": ["관할", "법원", "중재", "준거법", "분쟁해결"],
        "importance": "권장",
        "desc": "분쟁 발생 시 관할 법원/중재 + 준거법",
        "risk_if_missing": "관할 불명확 → 분쟁 시 불리한 관할에서 소송 가능",
    },
    "잔존조항": {
        "keywords": ["잔존", "존속", "효력 유지", "종료 후에도"],
        "importance": "권장",
        "desc": "계약 종료 후에도 효력이 유지되는 조항 명시",
        "risk_if_missing": "계약 종료 = 모든 의무 소멸로 해석 가능",
    },
}

# ══════════════════════════════════════════
#  NDA 위험 패턴 (Halligan & Weyand 2016 기반)
# ══════════════════════════════════════════

NDA_RISK_PATTERNS: dict[str, list[dict[str, str]]] = {
    "높음": [
        {"pattern": r"(?:모든|일체의)\s*정보.{0,20}비밀", "desc": "비밀정보 정의가 지나치게 광범위 (모든 정보=비밀)"},
        {"pattern": r"영구(?:적)?(?:으로|인)?\s*(?:비밀|기밀|의무)", "desc": "비밀유지 의무 영구 조항 — 비현실적"},
        {"pattern": r"(?:무한|무제한).{0,10}(?:배상|손해|책임)", "desc": "무제한 손해배상 조항"},
        {"pattern": r"일방적[으로]?\s*(?:해지|해제|종료)", "desc": "일방적 해지권 — 상대방만 가능한지 확인"},
        {"pattern": r"(?:경업금지|경쟁금지|동종업계).{0,20}\d+년", "desc": "NDA에 경업금지(비경쟁) 조항 포함 — NDA 범위 초과 가능"},
        {"pattern": r"(?:발명|특허|저작권|지식재산).{0,30}(?:양도|이전|귀속)", "desc": "NDA에 IP 귀속 조항 — 별도 계약이 필요한 사항"},
    ],
    "중간": [
        {"pattern": r"비밀정보.{0,30}(?:구두|구두로)", "desc": "구두 전달 정보도 비밀정보 포함 — 입증 어려움"},
        {"pattern": r"(?:5|6|7|8|9|10)년.{0,10}(?:비밀|기밀|의무)", "desc": "5년 이상 장기 비밀유지 — 산업 표준 초과 가능"},
        {"pattern": r"위약금.{0,20}\d{3,}", "desc": "고액 위약금 설정 — 적정성 검토 필요"},
        {"pattern": r"(?:사전\s*서면\s*동의|사전\s*승인).{0,20}(?:없이|없이는)", "desc": "사전 서면 동의 없이 행동 제한 — 과도할 수 있음"},
        {"pattern": r"제3자.{0,20}(?:하도급|위탁|외주)", "desc": "제3자 위탁 시 비밀정보 처리 방법 확인 필요"},
    ],
    "낮음": [
        {"pattern": r"(?:서면|문서).{0,10}(?:표시|기재|명시)", "desc": "비밀표시 의무 — 합리적이나 실행 부담 확인"},
        {"pattern": r"(?:통지|통보|알려).{0,20}(?:즉시|지체 없이)", "desc": "즉시 통지 의무 — '즉시'의 기준 확인 필요"},
        {"pattern": r"(?:합의|협의).{0,10}(?:해결|해결한다)", "desc": "분쟁 시 합의 우선 해결 — 긍정적이나 실효성 검토"},
    ],
}

# ══════════════════════════════════════════
#  NDA 유형별 체크리스트
# ══════════════════════════════════════════

NDA_TYPES: dict[str, dict[str, Any]] = {
    "단방향": {
        "desc": "한쪽만 비밀정보를 제공 (예: 투자 유치 시 스타트업→투자자)",
        "key_points": [
            "정보 제공자(공개자)의 권리 보호 중심",
            "수신자의 사용 범위 명확히 제한",
            "수신자의 직원·대리인 관리 의무 포함",
        ],
        "common_risk": "수신자에게 지나치게 유리한 예외 조항",
    },
    "양방향": {
        "desc": "양측 모두 비밀정보를 교환 (예: 합작투자, 기술 협력)",
        "key_points": [
            "양측 의무의 대칭성(균형) 확인",
            "각 측의 비밀정보 범위 명확히 구분",
            "공동 개발 결과물의 IP 귀속 별도 합의 필요",
        ],
        "common_risk": "한쪽에만 과도한 의무 부과 (비대칭)",
    },
    "다자간": {
        "desc": "3자 이상 참여 (예: 컨소시엄, 다자간 프로젝트)",
        "key_points": [
            "각 당사자의 역할·의무 명확 구분",
            "정보 흐름 경로 명시 (누가 누구에게)",
            "탈퇴 시 비밀정보 처리 방법",
        ],
        "common_risk": "정보 유출 경로 추적 어려움",
    },
}

# ══════════════════════════════════════════
#  NDA 초안 가이드라인
# ══════════════════════════════════════════

DRAFT_GUIDELINES: list[dict[str, str]] = [
    {
        "section": "1. 당사자 정보",
        "guide": "정확한 법인명, 대표자, 주소 기재. 개인인 경우 주민등록번호 대신 생년월일",
    },
    {
        "section": "2. 비밀정보 정의",
        "guide": (
            "구체적으로 열거(기술자료, 사업계획, 고객목록 등) + 포괄 조항 병행. "
            "Pooley(2013): '모든 정보'는 법원에서 인정 안 될 수 있음"
        ),
    },
    {
        "section": "3. 비밀유지 의무",
        "guide": "선량한 관리자의 주의의무 기준. 자기 비밀정보와 동일한 수준 이상으로 보호",
    },
    {
        "section": "4. 사용 범위 제한",
        "guide": "비밀정보 사용 목적을 명시 (예: '본 프로젝트 검토 목적에 한정')",
    },
    {
        "section": "5. 예외 사항",
        "guide": (
            "5가지 표준 예외: ① 이미 공개된 정보 ② 수신 전 이미 알고 있던 정보 "
            "③ 독자적으로 개발한 정보 ④ 제3자로부터 적법하게 입수 ⑤ 법적 의무에 의한 공개"
        ),
    },
    {
        "section": "6. 유효기간",
        "guide": (
            "계약기간 + 비밀유지 의무 존속기간을 분리 명시. "
            "산업 표준: 기술 NDA 3~5년, 영업비밀 NDA 5~10년"
        ),
    },
    {
        "section": "7. 반환·파기",
        "guide": "계약 종료/해지 시 30일 이내 반환 또는 파기 + 파기증명서 제출",
    },
    {
        "section": "8. 손해배상·금지청구",
        "guide": "위반 시 손해배상 + 금지청구(injunction) 가능 명시. 위약금 설정 시 적정성 검토",
    },
    {
        "section": "9. 관할·준거법",
        "guide": "한국법 준거 + 관할 법원 명시 (보통 당사자 본점 소재지 관할)",
    },
    {
        "section": "10. 잔존·일반 조항",
        "guide": "잔존조항, 양도금지, 완전합의, 수정절차(서면 합의) 등",
    },
]


class NdaAnalyzerTool(BaseTool):
    """NDA(비밀유지계약) 분석 도구."""

    name = "nda_analyzer"
    description = (
        "비밀유지계약(NDA) 조항별 리스크 분석, 불리 조항 탐지, "
        "비교분석, 초안 가이드라인 제공"
    )
    version = "1.0.0"

    # ── action 라우터 ──────────────────────
    async def execute(self, **kwargs) -> dict[str, Any]:
        action = (kwargs.get("action") or "analyze").strip().lower()
        dispatch = {
            "analyze": self._analyze,
            "compare": self._compare,
            "checklist": self._checklist,
            "draft_guide": self._draft_guide,
        }
        handler = dispatch.get(action)
        if handler is None:
            return {
                "error": f"지원하지 않는 action: {action}",
                "available": list(dispatch.keys()),
            }
        return await handler(kwargs)

    # ── analyze: NDA 조항별 리스크 분석 ──────
    async def _analyze(self, args: dict[str, Any]) -> dict[str, Any]:
        text = (args.get("text") or args.get("nda_text") or "").strip()
        if not text:
            return {"error": "text 파라미터에 NDA 텍스트를 입력해주세요"}

        # 1) 필수 조항 존재 여부 체크
        clause_results: list[dict] = []
        found_count = 0
        essential_count = 0
        for clause_name, info in NDA_ESSENTIAL_CLAUSES.items():
            is_essential = info["importance"] == "필수"
            if is_essential:
                essential_count += 1
            found = any(kw in text for kw in info["keywords"])
            if found:
                found_count += 1
            clause_results.append({
                "조항": clause_name,
                "중요도": info["importance"],
                "포함여부": "포함" if found else "누락",
                "설명": info["desc"],
                "누락위험": info["risk_if_missing"] if not found else None,
            })

        # 2) 위험 패턴 탐지
        risks_found: list[dict] = []
        for level, patterns in NDA_RISK_PATTERNS.items():
            for p in patterns:
                matches = re.findall(p["pattern"], text)
                if matches:
                    risks_found.append({
                        "위험도": level,
                        "설명": p["desc"],
                        "발견횟수": len(matches),
                        "발견문구": matches[0][:80],
                    })

        # 3) NDA 유형 추정
        is_mutual = any(kw in text for kw in ["양측", "쌍방", "상호", "mutual"])
        nda_type = "양방향" if is_mutual else "단방향"

        # 4) 종합 점수 (100점 만점)
        score = 100
        missing_essential = sum(
            1 for c in clause_results
            if c["중요도"] == "필수" and c["포함여부"] == "누락"
        )
        score -= missing_essential * 15
        score -= sum(5 for r in risks_found if r["위험도"] == "높음")
        score -= sum(3 for r in risks_found if r["위험도"] == "중간")
        score -= sum(1 for r in risks_found if r["위험도"] == "낮음")
        score = max(0, min(100, score))

        grade = (
            "A (양호)" if score >= 85
            else "B (보통)" if score >= 70
            else "C (주의)" if score >= 50
            else "D (위험)"
        )

        md_parts = [
            f"# NDA 분석 결과\n",
            f"**종합 점수**: {score}/100 ({grade})",
            f"**NDA 유형 추정**: {nda_type}",
            f"**필수 조항**: {found_count}개 포함 / {essential_count}개 중\n",
            "## 조항별 분석\n",
            "| 조항 | 중요도 | 포함여부 | 누락 시 위험 |",
            "|------|--------|---------|------------|",
        ]
        for c in clause_results:
            risk_text = c["누락위험"] or "-"
            status = c["포함여부"]
            mark = "포함" if status == "포함" else "**누락**"
            md_parts.append(
                f"| {c['조항']} | {c['중요도']} | {mark} | {risk_text} |"
            )

        if risks_found:
            md_parts.append("\n## 위험 패턴 탐지\n")
            md_parts.append("| 위험도 | 설명 | 발견 문구 |")
            md_parts.append("|--------|------|----------|")
            for r in risks_found:
                md_parts.append(
                    f"| **{r['위험도']}** | {r['설명']} | `{r['발견문구']}` |"
                )

        md_parts.append(_DISCLAIMER)
        return {
            "score": score,
            "grade": grade,
            "nda_type": nda_type,
            "clauses": clause_results,
            "risks": risks_found,
            "summary": "\n".join(md_parts),
        }

    # ── compare: 두 NDA 비교 ───────────────
    async def _compare(self, args: dict[str, Any]) -> dict[str, Any]:
        text_a = (args.get("text_a") or args.get("our_nda") or "").strip()
        text_b = (args.get("text_b") or args.get("their_nda") or "").strip()
        if not text_a or not text_b:
            return {
                "error": "text_a (우리 측 NDA)와 text_b (상대 측 NDA)를 모두 입력해주세요"
            }

        result_a = await self._analyze({"text": text_a})
        result_b = await self._analyze({"text": text_b})

        comparisons: list[dict] = []
        clauses_a = {c["조항"]: c for c in result_a.get("clauses", [])}
        clauses_b = {c["조항"]: c for c in result_b.get("clauses", [])}

        for clause_name in NDA_ESSENTIAL_CLAUSES:
            ca = clauses_a.get(clause_name, {})
            cb = clauses_b.get(clause_name, {})
            comparisons.append({
                "조항": clause_name,
                "우리측": ca.get("포함여부", "?"),
                "상대측": cb.get("포함여부", "?"),
                "차이": "동일" if ca.get("포함여부") == cb.get("포함여부") else "차이 있음",
            })

        md_parts = [
            "# NDA 비교 분석\n",
            f"**우리 측 점수**: {result_a.get('score', '?')}/100",
            f"**상대 측 점수**: {result_b.get('score', '?')}/100\n",
            "## 조항별 비교\n",
            "| 조항 | 우리 측 | 상대 측 | 차이 |",
            "|------|--------|--------|------|",
        ]
        for c in comparisons:
            md_parts.append(
                f"| {c['조항']} | {c['우리측']} | {c['상대측']} | {c['차이']} |"
            )

        risk_diff_a = len(result_a.get("risks", []))
        risk_diff_b = len(result_b.get("risks", []))
        md_parts.append(f"\n**위험 패턴**: 우리 측 {risk_diff_a}건, 상대 측 {risk_diff_b}건")

        if result_b.get("score", 0) < result_a.get("score", 0):
            md_parts.append(
                "\n> **주의**: 상대 측 NDA가 우리 측보다 점수가 낮습니다. "
                "상대 측 NDA 기준으로 서명 시 불리할 수 있습니다."
            )

        md_parts.append(_DISCLAIMER)
        return {
            "our_score": result_a.get("score"),
            "their_score": result_b.get("score"),
            "comparisons": comparisons,
            "summary": "\n".join(md_parts),
        }

    # ── checklist: NDA 유형별 체크리스트 ───────
    async def _checklist(self, args: dict[str, Any]) -> dict[str, Any]:
        nda_type = (args.get("nda_type") or "양방향").strip()

        md_parts = ["# NDA 유형별 체크리스트\n"]

        if nda_type in NDA_TYPES:
            info = NDA_TYPES[nda_type]
            md_parts.append(f"## {nda_type} NDA\n")
            md_parts.append(f"**설명**: {info['desc']}\n")
            md_parts.append("**핵심 포인트**:")
            for pt in info["key_points"]:
                md_parts.append(f"- {pt}")
            md_parts.append(f"\n**주요 위험**: {info['common_risk']}\n")
        else:
            md_parts.append(f"요청 유형: {nda_type}\n")

        md_parts.append("## 필수/권장 조항 체크리스트\n")
        md_parts.append("| 조항 | 중요도 | 설명 |")
        md_parts.append("|------|--------|------|")
        for name, info in NDA_ESSENTIAL_CLAUSES.items():
            md_parts.append(f"| {name} | {info['importance']} | {info['desc']} |")

        md_parts.append("\n## NDA 유형 비교\n")
        md_parts.append("| 유형 | 설명 | 주요 위험 |")
        md_parts.append("|------|------|----------|")
        for t_name, t_info in NDA_TYPES.items():
            md_parts.append(f"| {t_name} | {t_info['desc']} | {t_info['common_risk']} |")

        md_parts.append(_DISCLAIMER)
        return {
            "nda_type": nda_type,
            "clauses": list(NDA_ESSENTIAL_CLAUSES.keys()),
            "types": list(NDA_TYPES.keys()),
            "summary": "\n".join(md_parts),
        }

    # ── draft_guide: NDA 초안 가이드라인 ────────
    async def _draft_guide(self, args: dict[str, Any]) -> dict[str, Any]:
        purpose = (args.get("purpose") or "일반").strip()

        md_parts = [
            "# NDA 초안 작성 가이드라인\n",
            f"**작성 목적**: {purpose}\n",
            "> Decker(2012), Pooley(2013), WIPO Model NDA 기반 가이드\n",
        ]

        for item in DRAFT_GUIDELINES:
            md_parts.append(f"### {item['section']}")
            md_parts.append(f"{item['guide']}\n")

        md_parts.append("## 한국법 특수 고려사항\n")
        md_parts.append(
            "- **부정경쟁방지법 §2(2)**: 영업비밀 3요소 — "
            "비공지성, 경제적 유용성, 비밀관리성\n"
            "- **NDA만으로 부족**: 영업비밀로 인정받으려면 "
            "NDA 체결 + 접근 제한 + 비밀 표시 등 관리 조치 필요\n"
            "- **근로자 NDA**: 퇴직 후 비밀유지 기간은 합리적 범위 "
            "(통상 1~2년) — 과도하면 무효 가능"
        )

        md_parts.append(_DISCLAIMER)
        return {
            "purpose": purpose,
            "sections": [g["section"] for g in DRAFT_GUIDELINES],
            "summary": "\n".join(md_parts),
        }
