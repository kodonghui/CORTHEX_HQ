"""이메일 마케팅 최적화기 — 마케팅 이메일의 효과를 예측하고 개선안을 제시하는 도구.

이메일 제목의 길이, 개인화, 긴급성, 구체성, 이모지, 질문형, 스팸 단어 등
7가지 이상의 규칙으로 100점 만점 점수를 산정하고, 개선된 대안을 생성합니다.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.email_optimizer")

# ─── 이메일 제목 점수 규칙 (100점 만점) ───
SUBJECT_RULES: dict[str, dict[str, Any]] = {
    # ── 길이 (20점) ──
    "length": {
        "optimal": (20, 50),
        "weight": 20,
        "description": "제목 길이 (20~50자 최적)",
    },
    # ── 개인화 (15점) ──
    "personalization": {
        "patterns": [r"\{이름\}", r"\{name\}", "님", "당신"],
        "weight": 15,
        "description": "개인화 요소 (이름, 님 등)",
    },
    # ── 긴급성 (15점) ──
    "urgency": {
        "words": ["마감", "오늘만", "한정", "지금", "놓치지", "서두르", "마지막",
                  "단 하루", "종료", "얼마 남지", "기한", "데드라인"],
        "weight": 15,
        "warning": "과도하면 스팸 느낌 → 1개만 권장",
        "description": "긴급성 키워드 (마감, 오늘만 등)",
    },
    # ── 숫자/구체성 (15점) ──
    "specificity": {
        "patterns": [r"\d+%", r"\d+가지", r"\d+일", r"\d+만원", r"\d+개",
                    r"\d+시간", r"\d+분", r"\d+명", r"\d+위", r"\d+배"],
        "weight": 15,
        "description": "구체적 숫자 사용 (%, 가지, 일 등)",
    },
    # ── 이모지 (10점) ──
    "emoji": {
        "weight": 10,
        "optimal_count": (0, 2),
        "description": "이모지 사용 (0~2개 적정)",
    },
    # ── 질문형 (10점) ──
    "question": {
        "patterns": [r"\?$", r"할까요", r"인가요", r"일까요", r"아세요",
                    r"아시나요", r"궁금하", r"어떻게"],
        "weight": 10,
        "description": "질문형 제목 (호기심 유발)",
    },
    # ── 혜택 제시 (15점) ──
    "benefit": {
        "words": ["비법", "비결", "노하우", "방법", "전략", "팁", "가이드",
                  "무료", "혜택", "할인", "쿠폰", "선물", "보너스", "특별"],
        "weight": 15,
        "description": "혜택/가치 제시 키워드",
    },
    # ── 스팸 단어 감점 (-15점) ──
    "spam_words": {
        "words": ["무료", "공짜", "100%", "클릭", "당첨", "대박", "보장",
                  "수익", "돈벌기", "재택", "알바", "부업", "광고"],
        "penalty": -15,
        "description": "스팸 의심 단어 (감점 요소)",
    },
}

# ─── 이메일 제목 스타일 ───
SUBJECT_STYLES = {
    "urgency": {
        "name": "긴급형",
        "prefix_examples": ["마지막 기회!", "오늘 마감:", "단 {n}시간 남았습니다:"],
        "description": "시간 제한을 강조하여 즉각적인 행동 유도",
    },
    "curiosity": {
        "name": "호기심형",
        "prefix_examples": ["아무도 모르는", "알고 계셨나요?", "{topic}의 숨겨진 비밀"],
        "description": "궁금증을 유발하여 열어보고 싶게 만들기",
    },
    "benefit": {
        "name": "혜택형",
        "prefix_examples": ["{topic} 완벽 가이드", "무료 {topic} 자료", "{n}가지 {topic} 팁"],
        "description": "실질적 가치와 혜택을 직접 제시",
    },
    "social_proof": {
        "name": "사회적 증거형",
        "prefix_examples": ["{n}명이 선택한", "합격생들의 {topic}", "전문가가 추천하는"],
        "description": "다른 사람들의 선택이나 전문가 권위를 활용",
    },
}


def _count_emoji(text: str) -> int:
    """텍스트에서 이모지 개수를 셉니다."""
    return sum(1 for ch in text if unicodedata.category(ch).startswith("So"))


def _score_subject(subject: str) -> dict[str, Any]:
    """이메일 제목의 점수를 산정합니다.

    Returns:
        {"total_score": int, "items": {규칙명: {score, max, detail}}, "grade": str}
    """
    items: dict[str, dict[str, Any]] = {}
    total_score = 0

    # 1. 길이 (20점)
    length = len(subject)
    opt_min, opt_max = SUBJECT_RULES["length"]["optimal"]
    if opt_min <= length <= opt_max:
        score = 20
        detail = f"{length}자 (최적 범위)"
    elif 10 <= length < opt_min or opt_max < length <= 70:
        score = 10
        detail = f"{length}자 (권장: {opt_min}~{opt_max}자)"
    else:
        score = 0
        detail = f"{length}자 (너무 {'짧음' if length < 10 else '김'})"
    items["length"] = {"score": score, "max": 20, "detail": detail}
    total_score += score

    # 2. 개인화 (15점)
    patterns = SUBJECT_RULES["personalization"]["patterns"]
    found = [p for p in patterns if re.search(p, subject)]
    if found:
        score = 15
        detail = f"개인화 요소 발견: {', '.join(found)}"
    else:
        score = 0
        detail = "개인화 요소 없음 (이름, 님 등 추가 권장)"
    items["personalization"] = {"score": score, "max": 15, "detail": detail}
    total_score += score

    # 3. 긴급성 (15점)
    urgency_words = SUBJECT_RULES["urgency"]["words"]
    found_urgency = [w for w in urgency_words if w in subject]
    if len(found_urgency) == 1:
        score = 15
        detail = f"적절한 긴급성: '{found_urgency[0]}'"
    elif len(found_urgency) > 1:
        score = 8
        detail = f"긴급성 단어 {len(found_urgency)}개 (1개만 권장): {', '.join(found_urgency)}"
    else:
        score = 0
        detail = "긴급성 없음 (상황에 따라 추가 고려)"
    items["urgency"] = {"score": score, "max": 15, "detail": detail}
    total_score += score

    # 4. 숫자/구체성 (15점)
    specificity_patterns = SUBJECT_RULES["specificity"]["patterns"]
    found_specificity = [p for p in specificity_patterns if re.search(p, subject)]
    if found_specificity:
        score = 15
        detail = f"구체적 숫자 사용: {len(found_specificity)}개 매칭"
    else:
        score = 0
        detail = "구체적 숫자 없음 (숫자 추가 권장)"
    items["specificity"] = {"score": score, "max": 15, "detail": detail}
    total_score += score

    # 5. 이모지 (10점)
    emoji_count = _count_emoji(subject)
    opt_min_e, opt_max_e = SUBJECT_RULES["emoji"]["optimal_count"]
    if opt_min_e <= emoji_count <= opt_max_e:
        score = 10
        detail = f"이모지 {emoji_count}개 (적정)"
    elif emoji_count > opt_max_e:
        score = 3
        detail = f"이모지 {emoji_count}개 (너무 많음, {opt_max_e}개 이하 권장)"
    else:
        score = 5
        detail = "이모지 없음 (1개 추가하면 개봉률 향상 가능)"
    items["emoji"] = {"score": score, "max": 10, "detail": detail}
    total_score += score

    # 6. 질문형 (10점)
    question_patterns = SUBJECT_RULES["question"]["patterns"]
    found_question = [p for p in question_patterns if re.search(p, subject)]
    if found_question:
        score = 10
        detail = "질문형 제목 (호기심 유발 효과)"
    else:
        score = 0
        detail = "서술형 제목 (질문형으로 바꾸면 개봉률 향상 가능)"
    items["question"] = {"score": score, "max": 10, "detail": detail}
    total_score += score

    # 7. 혜택 제시 (15점)
    benefit_words = SUBJECT_RULES["benefit"]["words"]
    found_benefit = [w for w in benefit_words if w in subject]
    if found_benefit:
        score = 15
        detail = f"혜택 키워드: {', '.join(found_benefit)}"
    else:
        score = 0
        detail = "혜택 키워드 없음 (가치 제시 추가 권장)"
    items["benefit"] = {"score": score, "max": 15, "detail": detail}
    total_score += score

    # 8. 스팸 감점 (-15점)
    spam_words = SUBJECT_RULES["spam_words"]["words"]
    found_spam = [w for w in spam_words if w in subject]
    if found_spam:
        penalty = SUBJECT_RULES["spam_words"]["penalty"]
        total_score += penalty
        items["spam_words"] = {
            "score": penalty,
            "max": 0,
            "detail": f"스팸 의심 단어 발견: {', '.join(found_spam)} ({penalty}점)",
        }
    else:
        items["spam_words"] = {"score": 0, "max": 0, "detail": "스팸 단어 없음 (양호)"}

    # 등급 산정
    total_score = max(0, min(100, total_score))
    if total_score >= 90:
        grade = "A+"
    elif total_score >= 80:
        grade = "A"
    elif total_score >= 70:
        grade = "B"
    elif total_score >= 60:
        grade = "C"
    elif total_score >= 50:
        grade = "D"
    else:
        grade = "F"

    return {"total_score": total_score, "items": items, "grade": grade}


class EmailOptimizerTool(BaseTool):
    """마케팅 이메일의 효과를 예측하고 개선안을 제시하는 도구."""

    async def execute(self, **kwargs: Any) -> str:
        """
        이메일 최적화 도구 실행.

        kwargs:
          - action: "analyze" | "suggest" | "ab_test"
          - subject: 이메일 제목
          - body: 이메일 본문 (선택)
          - audience: 대상 (기본: "일반")
          - count: 대안 개수 (기본: 5)
          - topic: A/B 테스트 주제
          - pairs: A/B 테스트 쌍 개수 (기본: 3)
        """
        action = kwargs.get("action", "analyze")

        if action == "analyze":
            return await self._analyze(kwargs)
        elif action == "suggest":
            return await self._suggest(kwargs)
        elif action == "ab_test":
            return await self._ab_test(kwargs)
        else:
            return f"알 수 없는 action: {action}\n사용 가능: analyze, suggest, ab_test"

    # ──────────────────────────────────────
    #  action: analyze
    # ──────────────────────────────────────

    async def _analyze(self, kwargs: dict[str, Any]) -> str:
        """이메일 제목(+ 본문)을 분석합니다."""
        subject = kwargs.get("subject", "")
        body = kwargs.get("body", "")
        audience = kwargs.get("audience", "일반")

        if not subject:
            return "subject(이메일 제목) 파라미터를 입력해주세요."

        logger.info("[email_optimizer] analyze: subject='%s', audience=%s", subject, audience)

        # 제목 점수
        result = _score_subject(subject)

        lines = [
            f"## 이메일 제목 분석",
            f"- 제목: \"{subject}\"",
            f"- 대상: {audience}",
            f"### 총점: {result['total_score']}/100 (등급: {result['grade']})",
            "",
            "### 항목별 점수",
            "",
            "| 항목 | 점수 | 상세 |",
            "|------|------|------|",
        ]

        for rule_name, item in result["items"].items():
            rule_desc = SUBJECT_RULES.get(rule_name, {}).get("description", rule_name)
            lines.append(f"| {rule_desc} | {item['score']}/{item['max']} | {item['detail']} |")

        # 본문 분석 (선택)
        if body:
            lines.extend(["", "### 본문 분석", ""])
            body_length = len(body)
            if 200 <= body_length <= 500:
                lines.append(f"- 본문 길이: {body_length}자 (적정)")
            elif body_length < 200:
                lines.append(f"- 본문 길이: {body_length}자 (너무 짧음, 200자 이상 권장)")
            else:
                lines.append(f"- 본문 길이: {body_length}자 (길 수 있음, 500자 이하 권장)")

            # CTA 존재 여부
            cta_patterns = [r"http[s]?://", r"바로가기", r"신청하기", r"구매하기",
                          r"확인하기", r"자세히", r"클릭", r"다운로드"]
            cta_found = [p for p in cta_patterns if re.search(p, body)]
            if cta_found:
                lines.append(f"- CTA(행동 유도): 있음 ({len(cta_found)}개)")
            else:
                lines.append("- CTA(행동 유도): 없음 (링크 또는 행동 유도 버튼 추가 권장)")

        result_text = "\n".join(lines)

        # LLM 개선 조언
        analysis = await self._llm_call(
            system_prompt=(
                f"당신은 이메일 마케팅 전문가입니다. 대상은 '{audience}'입니다.\n"
                "아래 분석 결과를 보고:\n"
                "1. 이 제목의 장점과 단점\n"
                "2. 가장 시급히 개선할 점 2가지\n"
                "3. 개선된 제목 예시 3개\n"
                "를 한국어로 작성하세요. 각 개선 제목은 왜 더 나은지 이유도 포함하세요."
            ),
            user_prompt=result_text,
        )

        return f"{result_text}\n\n---\n\n### AI 개선 조언\n\n{analysis}"

    # ──────────────────────────────────────
    #  action: suggest
    # ──────────────────────────────────────

    async def _suggest(self, kwargs: dict[str, Any]) -> str:
        """제목 개선안을 생성합니다."""
        subject = kwargs.get("subject", "")
        if not subject:
            return "subject(원래 제목) 파라미터를 입력해주세요."

        count = int(kwargs.get("count", 5))
        logger.info("[email_optimizer] suggest: subject='%s', count=%d", subject, count)

        # 현재 점수
        original_result = _score_subject(subject)

        lines = [
            f"## 이메일 제목 개선안",
            f"- 원래 제목: \"{subject}\"",
            f"- 현재 점수: {original_result['total_score']}/100 (등급: {original_result['grade']})",
            "",
        ]

        # LLM으로 개선안 생성
        suggestions = await self._llm_call(
            system_prompt=(
                "당신은 이메일 마케팅 카피라이터입니다.\n"
                f"아래 이메일 제목을 {count}가지 다른 버전으로 개선해주세요.\n\n"
                "개선 원칙:\n"
                "- 20~50자 길이 유지\n"
                "- 숫자/구체성 포함\n"
                "- 혜택이나 가치 제시\n"
                "- 호기심 유발 또는 긴급성 부여\n"
                "- 스팸 단어 사용 금지\n\n"
                f"각 제목을 '1. ', '2. ' 형식으로 작성하고, "
                f"각 제목 아래에 왜 이 제목이 효과적인지 한 줄로 설명하세요.\n"
                "한국어로 작성하세요."
            ),
            user_prompt=f"원래 제목: \"{subject}\"",
        )

        lines.extend([
            "### 개선 제안",
            "",
            suggestions,
        ])

        return "\n".join(lines)

    # ──────────────────────────────────────
    #  action: ab_test
    # ──────────────────────────────────────

    async def _ab_test(self, kwargs: dict[str, Any]) -> str:
        """A/B 테스트용 제목 쌍을 생성합니다."""
        topic = kwargs.get("topic", "")
        if not topic:
            return "topic(이메일 주제) 파라미터를 입력해주세요."

        pairs = int(kwargs.get("pairs", 3))
        logger.info("[email_optimizer] ab_test: topic='%s', pairs=%d", topic, pairs)

        # 스타일 정보 텍스트
        styles_info = "\n".join(
            f"- {style['name']}: {style['description']}"
            for style in SUBJECT_STYLES.values()
        )

        # LLM으로 A/B 테스트 쌍 생성
        ab_pairs = await self._llm_call(
            system_prompt=(
                "당신은 이메일 A/B 테스트 전문가입니다.\n"
                f"아래 주제로 {pairs}쌍의 A/B 테스트용 이메일 제목을 만들어주세요.\n\n"
                "각 쌍은 서로 다른 스타일을 비교합니다:\n"
                f"{styles_info}\n\n"
                "형식:\n"
                "## 쌍 1: [스타일A] vs [스타일B]\n"
                "- A: \"제목A\"\n"
                "- B: \"제목B\"\n"
                "- 테스트 포인트: 무엇을 비교하려는지\n\n"
                "모든 제목은 20~50자, 한국어로 작성하세요."
            ),
            user_prompt=f"주제: {topic}",
        )

        lines = [
            f"## A/B 테스트 제목 쌍: '{topic}'",
            f"- 생성 쌍 수: {pairs}",
            "",
            ab_pairs,
            "",
            "---",
            "",
            "### A/B 테스트 실행 가이드",
            "1. 각 쌍에서 A/B를 50:50으로 무작위 배분",
            "2. 최소 1,000명 이상에게 발송 (통계적 유의성 확보)",
            "3. 24시간 후 개봉률(open rate) 비교",
            "4. 개봉률 차이가 3% 이상이면 유의미한 결과",
            "5. 승리한 스타일을 향후 이메일에 적용",
        ]

        return "\n".join(lines)
