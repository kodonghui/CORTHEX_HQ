"""
계약서 자동 검토 Tool.

계약서 텍스트에서 위험/불리 조항을 자동 탐지하고,
필수 조항 누락 여부를 체크합니다.

사용 방법:
  - action="review": 계약서 검토 (위험 조항 탐지)
  - action="checklist": 계약서 유형별 필수 조항 체크리스트
  - action="compare": 두 계약서 비교

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬 + re 모듈)

주의: 이 검토는 참고용이며, 중요한 계약은 반드시 변호사 검토를 받으세요.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.contract_reviewer")

_DISCLAIMER = (
    "\n\n---\n**면책 안내**: 이 검토는 참고용이며, "
    "중요한 계약은 반드시 변호사 검토를 받으세요."
)

# ══════════════════════════════════════════
#  위험 조항 패턴 데이터베이스 (총 26개)
# ══════════════════════════════════════════

RISK_PATTERNS: dict[str, list[dict[str, str]]] = {
    "높음": [
        {"pattern": r"일방적[으로]?\s*해지", "desc": "상대방만 일방적으로 해지 가능"},
        {"pattern": r"손해배상.{0,20}무제한", "desc": "손해배상 한도 없음"},
        {"pattern": r"위약금.{0,10}\d{2,}%", "desc": "과도한 위약금 비율"},
        {"pattern": r"지적재산권.{0,30}양도", "desc": "IP(지식재산) 권리 양도 조항"},
        {"pattern": r"경업금지.{0,20}\d+년", "desc": "경업금지 기간 확인 필요"},
        {"pattern": r"자동\s*갱신", "desc": "자동 갱신 조항 -- 해지 절차 확인 필요"},
        {"pattern": r"모든\s*(?:권리|권한).{0,20}(?:포기|이전|양도)", "desc": "모든 권리 포기/이전 조항"},
        {"pattern": r"책임.{0,10}(?:면제|면책).{0,20}(?:갑|상대방|회사)", "desc": "상대방의 책임 면제 조항"},
        {"pattern": r"손해배상.{0,20}(?:3|4|5|6|7|8|9|10)배", "desc": "과도한 손해배상 배수"},
        {"pattern": r"위약벌.{0,20}(?:전액|계약금액)", "desc": "위약벌이 계약금액 전액인 조항"},
    ],
    "중간": [
        {"pattern": r"재판관할.{0,20}(?:서울|수원|부산|대구|광주|대전)", "desc": "재판관할 지역 확인 필요"},
        {"pattern": r"준거법.{0,20}(?:외국|미국|중국|일본|영국)", "desc": "외국법 준거 -- 분쟁 시 불리할 수 있음"},
        {"pattern": r"비밀유지.{0,20}\d+년", "desc": "비밀유지 기간 확인 필요"},
        {"pattern": r"해지\s*(?:통지|통보).{0,10}(?:\d+일|\d+개월)", "desc": "해지 통지 기간 확인"},
        {"pattern": r"(?:중재|조정).{0,20}(?:기관|센터|원)", "desc": "분쟁 해결 기관 확인 필요"},
        {"pattern": r"연체.{0,10}(?:이자|이율).{0,10}\d+%", "desc": "연체 이자율 확인 필요"},
        {"pattern": r"보증.{0,20}(?:연대|무한)", "desc": "연대보증/무한보증 조항"},
        {"pattern": r"수정.{0,20}(?:일방|자유|임의)", "desc": "일방적 계약 수정 가능 조항"},
    ],
    "참고": [
        {"pattern": r"제\d+조", "desc": "조문 번호 확인"},
        {"pattern": r"갑.{0,5}을", "desc": "갑을 관계 확인"},
        {"pattern": r"(?:본|이)\s*계약.{0,10}(?:기간|유효)", "desc": "계약 기간/유효 조항"},
        {"pattern": r"(?:대금|대가|보수).{0,20}(?:지급|지불)", "desc": "대금 지급 조건 확인"},
        {"pattern": r"(?:불가항력|천재지변)", "desc": "불가항력 조항 존재"},
        {"pattern": r"(?:양도|이전).{0,10}(?:금지|불가)", "desc": "권리 양도 제한 조항"},
        {"pattern": r"(?:통지|통보).{0,20}(?:서면|이메일|내용증명)", "desc": "통지 방법 확인"},
        {"pattern": r"(?:개인정보|정보보호).{0,20}(?:처리|관리)", "desc": "개인정보 처리 관련 조항"},
    ],
}

# ══════════════════════════════════════════
#  유형별 필수 조항 체크리스트
# ══════════════════════════════════════════

REQUIRED_CLAUSES: dict[str, list[str]] = {
    "서비스이용약관": [
        "개인정보처리", "환불규정", "면책조항", "분쟁해결",
        "서비스변경", "서비스중단", "이용제한", "저작권",
        "약관변경", "회원탈퇴",
    ],
    "업무위탁": [
        "업무범위", "대가지급", "비밀유지", "지적재산권",
        "손해배상", "계약해지", "재위탁", "검수기준",
    ],
    "투자계약": [
        "투자금액", "지분비율", "의결권", "배당",
        "희석방지", "동반매도", "우선매수", "경영참여",
        "투자금반환", "손해배상",
    ],
    "고용계약": [
        "업무내용", "근무시간", "급여", "퇴직금",
        "비밀유지", "경업금지", "지적재산권", "해고사유",
        "수습기간", "복리후생",
    ],
    "NDA": [
        "비밀정보정의", "비밀유지의무", "사용범위",
        "유효기간", "반환의무", "손해배상", "예외사항",
    ],
}


class ContractReviewerTool(BaseTool):
    """계약서 자동 검토 도구 (CLO 법무IP처 소속)."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "review")

        if action == "review":
            return await self._review(kwargs)
        elif action == "checklist":
            return await self._checklist(kwargs)
        elif action == "compare":
            return await self._compare(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "review, checklist, compare 중 하나를 사용하세요."
            )

    # ── 계약서 검토 ──

    async def _review(self, kwargs: dict[str, Any]) -> str:
        """계약서 텍스트에서 위험/불리 조항 탐지."""
        text = kwargs.get("text", "")
        file_path = kwargs.get("file_path", "")

        if not text and file_path:
            text = self._read_file(file_path)
        if not text:
            return "계약서 텍스트(text) 또는 파일 경로(file_path)를 입력해주세요."

        # 위험 조항 패턴 매칭
        findings: dict[str, list[dict]] = {"높음": [], "중간": [], "참고": []}

        for level, patterns in RISK_PATTERNS.items():
            for pat_info in patterns:
                matches = list(re.finditer(pat_info["pattern"], text))
                if matches:
                    for m in matches:
                        # 매칭 주변 텍스트 (앞뒤 30자)
                        start = max(0, m.start() - 30)
                        end = min(len(text), m.end() + 30)
                        context = text[start:end].replace("\n", " ").strip()

                        findings[level].append({
                            "desc": pat_info["desc"],
                            "matched": m.group(),
                            "context": f"...{context}...",
                        })

        # 결과 포맷
        total_high = len(findings["높음"])
        total_mid = len(findings["중간"])
        total_ref = len(findings["참고"])

        lines = ["## 계약서 자동 검토 결과\n"]
        lines.append(f"계약서 길이: {len(text):,}자\n")
        lines.append(f"### 탐지 요약")
        lines.append(f"- 높은 위험: **{total_high}건**")
        lines.append(f"- 중간 위험: **{total_mid}건**")
        lines.append(f"- 참고 사항: **{total_ref}건**\n")

        for level in ["높음", "중간", "참고"]:
            if findings[level]:
                emoji_map = {"높음": "[위험]", "중간": "[주의]", "참고": "[참고]"}
                lines.append(f"### {emoji_map[level]} {level} 위험 ({len(findings[level])}건)")
                for i, f in enumerate(findings[level], 1):
                    lines.append(f"  {i}. **{f['desc']}**")
                    lines.append(f"     매칭: `{f['matched']}`")
                    lines.append(f"     문맥: {f['context']}")
                lines.append("")

        # 필수 조항 누락 체크 (자동 유형 추정)
        contract_type = self._guess_contract_type(text)
        if contract_type:
            lines.append(f"\n### 필수 조항 누락 체크 (추정 유형: {contract_type})")
            required = REQUIRED_CLAUSES.get(contract_type, [])
            missing = []
            present = []
            for clause in required:
                if clause in text or any(
                    kw in text for kw in self._clause_keywords(clause)
                ):
                    present.append(clause)
                else:
                    missing.append(clause)

            if missing:
                lines.append(f"**누락 의심 조항 ({len(missing)}건):**")
                for m in missing:
                    lines.append(f"  - {m}")
            if present:
                lines.append(f"\n포함 확인 조항 ({len(present)}건):")
                for p in present:
                    lines.append(f"  - {p}")

        formatted = "\n".join(lines)

        # LLM 종합 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 계약법 전문 변호사입니다.\n"
                "계약서 자동 검토 결과를 분석하여 다음을 답변하세요:\n\n"
                "1. **종합 리스크 평가**: 이 계약서의 전체적인 위험도 (상/중/하)\n"
                "2. **가장 위험한 조항 TOP 3**: 어떤 조항이 왜 위험한지\n"
                "3. **수정 권고사항**: 구체적으로 어떻게 수정해야 하는지\n"
                "4. **누락 조항 보완**: 반드시 추가해야 할 조항\n"
                "5. **협상 포인트**: 상대방과 협상 시 집중해야 할 사항\n\n"
                "한국어로 구체적으로 답변하세요.\n"
                "주의: 이 검토는 참고용이며, 중요한 계약은 변호사 검토를 받으세요."
            ),
            user_prompt=f"계약서 자동 검토 결과:\n\n{formatted}\n\n계약서 원문 (앞부분):\n{text[:2000]}",
        )

        return f"{formatted}\n\n---\n\n## 전문가 분석\n\n{analysis}{_DISCLAIMER}"

    # ── 필수 조항 체크리스트 ──

    async def _checklist(self, kwargs: dict[str, Any]) -> str:
        """계약서 유형별 필수 조항 체크리스트 제공."""
        contract_type = kwargs.get("contract_type", "")
        if not contract_type:
            available = ", ".join(REQUIRED_CLAUSES.keys())
            return (
                f"계약서 유형(contract_type)을 입력해주세요.\n"
                f"사용 가능한 유형: {available}"
            )

        clauses = REQUIRED_CLAUSES.get(contract_type)
        if clauses is None:
            available = ", ".join(REQUIRED_CLAUSES.keys())
            return (
                f"'{contract_type}'은(는) 지원하지 않는 유형입니다.\n"
                f"사용 가능한 유형: {available}"
            )

        lines = [f"## {contract_type} 필수 조항 체크리스트\n"]
        lines.append(f"총 {len(clauses)}개 필수 조항:\n")
        for i, clause in enumerate(clauses, 1):
            lines.append(f"  {i}. [ ] {clause}")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 계약법 전문 변호사입니다.\n"
                "계약서 유형별 필수 조항 체크리스트에 대해\n"
                "각 조항이 왜 필요한지, 빠졌을 때 어떤 문제가 생기는지\n"
                "비개발자(CEO)도 이해할 수 있게 쉽게 설명하세요.\n"
                "한국어로 답변하세요."
            ),
            user_prompt=f"계약서 유형: {contract_type}\n\n{formatted}",
        )

        return f"{formatted}\n\n---\n\n## 조항별 설명\n\n{analysis}{_DISCLAIMER}"

    # ── 두 계약서 비교 ──

    async def _compare(self, kwargs: dict[str, Any]) -> str:
        """두 계약서 비교 분석."""
        text1 = kwargs.get("text1", "")
        text2 = kwargs.get("text2", "")

        if not text1 or not text2:
            return "비교할 두 계약서 텍스트(text1, text2)를 모두 입력해주세요."

        # 각각 위험 패턴 탐지
        findings1 = self._detect_risks(text1)
        findings2 = self._detect_risks(text2)

        count1 = sum(len(v) for v in findings1.values())
        count2 = sum(len(v) for v in findings2.values())

        lines = ["## 계약서 비교 분석\n"]
        lines.append("| 항목 | 계약서 1 | 계약서 2 |")
        lines.append("|------|---------|---------|")
        lines.append(f"| 전체 길이 | {len(text1):,}자 | {len(text2):,}자 |")
        lines.append(f"| 높은 위험 | {len(findings1['높음'])}건 | {len(findings2['높음'])}건 |")
        lines.append(f"| 중간 위험 | {len(findings1['중간'])}건 | {len(findings2['중간'])}건 |")
        lines.append(f"| 참고 사항 | {len(findings1['참고'])}건 | {len(findings2['참고'])}건 |")
        lines.append(f"| **총 탐지** | **{count1}건** | **{count2}건** |")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 계약법 전문 변호사입니다.\n"
                "두 계약서를 비교 분석하여 다음을 답변하세요:\n\n"
                "1. **핵심 차이점**: 가장 중요한 차이 3~5가지\n"
                "2. **유리/불리 비교**: 어느 계약서가 우리에게 유리한지\n"
                "3. **통합 권고사항**: 두 계약서의 장점을 합친 최적안 제안\n\n"
                "한국어로 답변하세요."
            ),
            user_prompt=(
                f"비교 결과:\n{formatted}\n\n"
                f"계약서 1 (앞부분):\n{text1[:1500]}\n\n"
                f"계약서 2 (앞부분):\n{text2[:1500]}"
            ),
        )

        return f"{formatted}\n\n---\n\n## 비교 분석\n\n{analysis}{_DISCLAIMER}"

    # ══════════════════════════════════════════
    #  내부 유틸
    # ══════════════════════════════════════════

    def _detect_risks(self, text: str) -> dict[str, list[dict]]:
        """텍스트에서 위험 패턴 탐지 (내부 유틸)."""
        findings: dict[str, list[dict]] = {"높음": [], "중간": [], "참고": []}
        for level, patterns in RISK_PATTERNS.items():
            for pat_info in patterns:
                if re.search(pat_info["pattern"], text):
                    findings[level].append(pat_info)
        return findings

    @staticmethod
    def _guess_contract_type(text: str) -> str:
        """계약서 텍스트에서 유형 자동 추정."""
        type_keywords = {
            "서비스이용약관": ["이용약관", "서비스 약관", "이용 약관", "서비스이용"],
            "업무위탁": ["업무위탁", "위탁계약", "외주", "용역계약"],
            "투자계약": ["투자계약", "투자 계약", "지분", "출자"],
            "고용계약": ["고용계약", "근로계약", "근로 계약", "채용"],
            "NDA": ["비밀유지", "기밀유지", "NDA", "비밀 유지"],
        }
        for ctype, keywords in type_keywords.items():
            if any(kw in text for kw in keywords):
                return ctype
        return ""

    @staticmethod
    def _clause_keywords(clause: str) -> list[str]:
        """필수 조항명을 검색 키워드로 변환."""
        keyword_map: dict[str, list[str]] = {
            "개인정보처리": ["개인정보", "정보처리", "개인 정보"],
            "환불규정": ["환불", "반환", "취소"],
            "면책조항": ["면책", "책임제한", "책임 제한"],
            "분쟁해결": ["분쟁", "중재", "재판관할"],
            "서비스변경": ["서비스 변경", "변경 사항"],
            "서비스중단": ["서비스 중단", "중단", "중지"],
            "이용제한": ["이용 제한", "이용제한", "제한"],
            "저작권": ["저작권", "저작물", "지적재산"],
            "약관변경": ["약관 변경", "약관변경"],
            "회원탈퇴": ["탈퇴", "회원 탈퇴"],
            "업무범위": ["업무 범위", "업무범위", "위탁 업무"],
            "대가지급": ["대가", "대금", "보수", "수수료"],
            "비밀유지": ["비밀", "기밀", "비밀유지"],
            "지적재산권": ["지적재산", "특허", "저작권", "IP"],
            "손해배상": ["손해배상", "배상"],
            "계약해지": ["해지", "해제", "종료"],
            "재위탁": ["재위탁", "하도급", "제3자 위탁"],
            "검수기준": ["검수", "인수", "인도"],
            "투자금액": ["투자금", "투자 금액", "출자금"],
            "지분비율": ["지분", "주식", "주주"],
            "의결권": ["의결", "의결권"],
            "배당": ["배당", "이익 분배"],
            "희석방지": ["희석", "안티딜루션"],
            "동반매도": ["동반매도", "태그얼롱"],
            "우선매수": ["우선매수", "선매"],
            "경영참여": ["이사회", "경영", "임원 선임"],
            "투자금반환": ["투자금 반환", "투자 회수"],
            "업무내용": ["업무", "직무", "담당"],
            "근무시간": ["근무시간", "근로시간", "근무 시간"],
            "급여": ["급여", "임금", "보수", "연봉"],
            "퇴직금": ["퇴직금", "퇴직"],
            "경업금지": ["경업금지", "경쟁금지", "경업 금지"],
            "해고사유": ["해고", "해임"],
            "수습기간": ["수습", "시용"],
            "복리후생": ["복리후생", "복지", "4대보험"],
            "비밀정보정의": ["비밀정보", "기밀정보", "비밀 정보"],
            "비밀유지의무": ["비밀유지", "비밀 유지"],
            "사용범위": ["사용 범위", "사용범위", "이용 범위"],
            "유효기간": ["유효기간", "계약기간", "기간"],
            "반환의무": ["반환", "폐기"],
            "예외사항": ["예외", "제외"],
        }
        return keyword_map.get(clause, [clause])

    @staticmethod
    def _read_file(file_path: str) -> str:
        """파일에서 텍스트 읽기 (.txt, .md 지원)."""
        path = Path(file_path)
        if not path.exists():
            return ""
        if path.suffix not in (".txt", ".md"):
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""
