"""
회의록 자동 정리기 도구 (Meeting Formatter).

회의 내용 텍스트에서 결정사항, 할일(Action Items),
담당자를 자동 추출하고 구조화된 회의록을 생성합니다.

사용 방법:
  - action="format": 회의록 정리 (text, meeting_type)
  - action="action_items": 할일 목록만 추출 (text)
  - action="template": 회의록 양식 제공 (meeting_type)

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬 + LLM)
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.meeting_formatter")

KST = timezone(timedelta(hours=9))

# 할일 관련 패턴 (정규식)
ACTION_PATTERNS = [
    re.compile(r"해야\s*(합니다|함|할\s*것)"),
    re.compile(r"까지\s*(완료|제출|보고)"),
    re.compile(r"담당[:\s]*([\w]+)"),
    re.compile(r"기한[:\s]*([\d/\-]+)"),
    re.compile(r"TODO[:\s]*(.*)", re.I),
    re.compile(r"\[\s*\]\s*(.*)"),  # 체크박스 형식
    re.compile(r"진행해\s*(주세요|야|보겠)"),
    re.compile(r"확인\s*(해|부탁|필요)"),
    re.compile(r"준비\s*(해|부탁|필요)"),
]

# ── 회의록 양식 템플릿 ──

MEETING_TEMPLATES: dict[str, str] = {
    "일반": """# 회의록

## 기본 정보
- **날짜**: YYYY-MM-DD
- **시간**: HH:MM ~ HH:MM
- **장소/방식**: (대면/온라인)
- **참석자**:
- **작성자**:

## 안건
1.

## 논의 사항


## 결정 사항
1.

## Action Items (할 일)
- [ ] 할일 내용 | 담당: OO | 기한: YYYY-MM-DD

## 다음 회의
- **일정**:
- **안건**:

---
*작성일: {date}*
""",

    "투자검토": """# 투자 검토 회의록

## 기본 정보
- **날짜**: YYYY-MM-DD
- **참석자**:
- **검토 목적**:

## 검토 종목
| 종목명 | 현재가 | 목표가 | 의견 |
|--------|--------|--------|------|
|        |        |        |      |

## 시장 환경 분석


## 투자 논거 (Bull Case)
1.

## 리스크 요인 (Bear Case)
1.

## 결정 사항
- 투자 여부: (매수/매도/관망)
- 투자 금액:
- 손절 기준:

## 후속 조치
- [ ] 할일 | 담당: OO | 기한: YYYY-MM-DD

---
*작성일: {date}*
""",

    "기획회의": """# 기획 회의록

## 기본 정보
- **날짜**: YYYY-MM-DD
- **참석자**:
- **프로젝트**:

## 안건
1.

## 현황 보고


## 기획 내용
### 목표

### 범위

### 일정

### 리소스

## 결정 사항
1.

## Action Items
- [ ] 할일 | 담당: OO | 기한: YYYY-MM-DD

## 다음 마일스톤
-

---
*작성일: {date}*
""",

    "기술회의": """# 기술 회의록

## 기본 정보
- **날짜**: YYYY-MM-DD
- **참석자**:
- **주제**:

## 기술 안건
1.

## 아키텍처 논의


## 기술 결정
| 항목 | 선택 | 사유 |
|------|------|------|
|      |      |      |

## 코드 리뷰 사항


## Action Items
- [ ] 할일 | 담당: OO | 기한: YYYY-MM-DD

## 기술 부채 (Tech Debt)
-

---
*작성일: {date}*
""",
}


class MeetingFormatterTool(BaseTool):
    """회의록 자동 정리기 — 회의 내용에서 결정사항/할일/담당자를 자동 추출합니다."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "format")

        if action == "format":
            return await self._format_meeting(kwargs)
        elif action == "action_items":
            return await self._extract_action_items(kwargs)
        elif action == "template":
            return self._get_template(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "format, action_items, template 중 하나를 사용하세요."
            )

    # ── 정규식 기반 할일 추출 ──

    @staticmethod
    def _extract_actions_by_regex(text: str) -> list[str]:
        """정규식으로 할일 관련 문장을 추출합니다."""
        actions: list[str] = []
        sentences = re.split(r"[.。\n]", text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            for pattern in ACTION_PATTERNS:
                if pattern.search(sentence):
                    actions.append(sentence)
                    break

        return list(dict.fromkeys(actions))  # 중복 제거 (순서 유지)

    # ── action 구현 ──

    async def _format_meeting(self, kwargs: dict[str, Any]) -> str:
        """회의 내용을 구조화된 회의록으로 정리합니다."""
        text = kwargs.get("text", "").strip()
        meeting_type = kwargs.get("meeting_type", "일반")

        if not text:
            return "text 파라미터가 필요합니다. 회의 내용을 입력하세요."

        now = datetime.now(KST)

        # 회의 유형별 시스템 프롬프트 보강
        type_guidance = {
            "일반": "일반적인 비즈니스 회의입니다.",
            "투자검토": "투자 종목 검토 회의입니다. 종목명, 가격, 투자 의견을 특히 잘 정리하세요.",
            "기획회의": "프로젝트 기획 회의입니다. 목표, 범위, 일정, 리소스를 특히 잘 정리하세요.",
            "기술회의": "기술 관련 회의입니다. 아키텍처 결정, 기술 선택 사유를 특히 잘 정리하세요.",
        }
        guidance = type_guidance.get(meeting_type, type_guidance["일반"])

        result = await self._llm_call(
            system_prompt=(
                f"당신은 회의록 정리 전문가입니다. {guidance}\n"
                "회의 내용을 다음 구조로 정리하세요:\n\n"
                f"# {meeting_type} 회의록\n\n"
                "## 회의 개요\n"
                f"- 정리일: {now.strftime('%Y-%m-%d %H:%M')}\n"
                "- 참석자: (내용에서 추출)\n"
                "- 안건: (내용에서 추출)\n\n"
                "## 논의 사항\n"
                "(주요 논의 내용을 번호로 정리)\n\n"
                "## 결정 사항\n"
                "(확정된 결정을 번호로 정리)\n\n"
                "## Action Items (할 일)\n"
                "- [ ] 할일 내용 | 담당: OO | 기한: YYYY-MM-DD\n\n"
                "## 다음 회의\n"
                "- 일정: (있으면)\n"
                "- 안건: (있으면)\n\n"
                "비전문가도 이해할 수 있게 쉽게 작성하세요.\n"
                "내용에 없는 정보는 만들지 마세요."
            ),
            user_prompt=text,
        )

        return result

    async def _extract_action_items(self, kwargs: dict[str, Any]) -> str:
        """회의 내용에서 할일 목록만 추출합니다."""
        text = kwargs.get("text", "").strip()

        if not text:
            return "text 파라미터가 필요합니다."

        # 1단계: 정규식으로 추출
        regex_actions = self._extract_actions_by_regex(text)

        # 2단계: LLM으로 추가 추출
        llm_result = await self._llm_call(
            system_prompt=(
                "당신은 할일(Action Item) 추출 전문가입니다.\n"
                "회의 내용에서 해야 할 일을 모두 추출하세요.\n\n"
                "각 할일은 다음 형식으로 작성하세요:\n"
                "- [ ] 할일 내용 | 담당: (이름 또는 '미정') | 기한: (날짜 또는 '미정')\n\n"
                "규칙:\n"
                "- 명시적으로 언급된 작업만 추출 (추측하지 말 것)\n"
                "- 담당자와 기한이 명시되어 있으면 반드시 포함\n"
                "- 우선순위가 높은 것부터 나열\n"
                "- 한국어로 작성"
            ),
            user_prompt=text,
        )

        lines = ["## Action Items (할 일) 추출 결과", ""]

        if regex_actions:
            lines.append("### 패턴 감지된 항목")
            for i, action in enumerate(regex_actions, 1):
                lines.append(f"{i}. {action}")
            lines.append("")

        lines.append("### 전체 할일 목록")
        lines.append(llm_result)

        return "\n".join(lines)

    def _get_template(self, kwargs: dict[str, Any]) -> str:
        """회의 유형별 빈 양식을 제공합니다."""
        meeting_type = kwargs.get("meeting_type", "일반")
        now = datetime.now(KST)

        if meeting_type not in MEETING_TEMPLATES:
            available = ", ".join(MEETING_TEMPLATES.keys())
            return f"'{meeting_type}' 양식이 없습니다. 사용 가능: {available}"

        template = MEETING_TEMPLATES[meeting_type].format(date=now.strftime("%Y-%m-%d"))
        return f"## {meeting_type} 회의록 양식\n\n아래 양식을 복사하여 사용하세요:\n\n{template}"
