"""
커뮤니케이션 최적화 도구 (Communication Optimizer) — 메시지의 명확성, 설득력, 청중 적합성을 분석합니다.

비서실 전용 도구로, CEO의 대내외 커뮤니케이션을 학술적 프레임워크 기반으로
분석·개선하여 메시지 전달력을 극대화합니다.

학술 근거:
  - Shannon & Weaver (1949) "A Mathematical Theory of Communication" — 정보 엔트로피, 노이즈 감소
  - Mehrabian (1971) "Silent Messages" — 7-38-55 법칙 (언어 7%, 톤 38%, 바디랭귀지 55%)
  - Aristotle's Rhetoric — Ethos(신뢰), Pathos(감정), Logos(논리)
  - Cialdini (2001) "Influence" — 6가지 설득 원칙
  - Gunning Fog Index (1952) — 텍스트 가독성 측정

사용 방법:
  - action="clarity"    : 메시지 명확성 분석 (문장 길이, 전문용어, 구조 점수)
  - action="persuasion" : 설득력 분석 (Aristotle 3요소 + Cialdini 6원칙)
  - action="channel"    : 최적 커뮤니케이션 채널 추천
  - action="noise"      : 커뮤니케이션 노이즈 분석 (Shannon-Weaver 기반)
  - action="audience"   : 청중 맞춤 메시지 변환
  - action="full"       : 위 5개 종합 분석

필요 환경변수: 없음
필요 라이브러리: 없음 (순수 Python)
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.communication_optimizer")


# ═══════════════════════════════════════════════════════
#  유틸리티 함수
# ═══════════════════════════════════════════════════════

def _mean(vals: list) -> float:
    """리스트 평균 (빈 리스트 방어)."""
    return sum(vals) / len(vals) if vals else 0.0


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """값을 범위 내로 고정."""
    return max(lo, min(hi, value))


def _split_sentences(text: str) -> list[str]:
    """한국어/영어 혼합 텍스트를 문장 단위로 분리."""
    parts = re.split(r'(?<=[.!?。\n])\s*', text.strip())
    return [s.strip() for s in parts if s.strip()]


def _count_chars(text: str) -> int:
    """공백 제외 글자 수."""
    return len(text.replace(" ", "").replace("\n", ""))


def _count_words(text: str) -> int:
    """단어 수 (한국어: 어절 기준)."""
    return len(text.split())


# ═══════════════════════════════════════════════════════
#  CommunicationOptimizerTool
# ═══════════════════════════════════════════════════════

class CommunicationOptimizerTool(BaseTool):
    """교수급 커뮤니케이션 최적화 도구 — 명확성·설득력·채널·노이즈·청중 맞춤 분석.

    Shannon-Weaver 정보 이론, Aristotle 수사학, Cialdini 설득 심리학 등
    5가지 학술 프레임워크를 종합하여 메시지 전달력을 정량 평가합니다.
    """

    # ── 청중별 전문용어 허용 수준 (0=금지, 1=자유) ──
    JARGON_TOLERANCE: dict[str, float] = {
        "executive": 0.25,    # 경영진: 핵심 비즈니스 용어만
        "manager": 0.50,      # 중간관리자: 업계 용어 허용
        "staff": 0.70,        # 실무자: 기술 용어 허용
        "external": 0.10,     # 외부 고객/파트너: 전문용어 최소화
    }

    # ── 채널 매트릭스 (message_type × channel 적합도, 1~10) ──
    CHANNEL_MATRIX: dict[str, dict[str, int]] = {
        "face_to_face": {"urgent": 9, "complex": 10, "routine": 4, "sensitive": 10, "announcement": 6},
        "video_call":   {"urgent": 8, "complex": 9,  "routine": 5, "sensitive": 8,  "announcement": 7},
        "phone":        {"urgent": 10,"complex": 6,  "routine": 4, "sensitive": 7,  "announcement": 3},
        "email":        {"urgent": 3, "complex": 7,  "routine": 9, "sensitive": 5,  "announcement": 8},
        "slack":        {"urgent": 7, "complex": 4,  "routine": 10,"sensitive": 3,  "announcement": 7},
        "document":     {"urgent": 2, "complex": 8,  "routine": 6, "sensitive": 6,  "announcement": 9},
        "presentation": {"urgent": 1, "complex": 7,  "routine": 3, "sensitive": 4,  "announcement": 10},
    }

    # ── 채널별 청중 규모 적합도 (1~10, 구간별) ──
    CHANNEL_AUDIENCE_FIT: dict[str, dict[str, int]] = {
        "face_to_face": {"small": 10, "medium": 5,  "large": 2},
        "video_call":   {"small": 9,  "medium": 8,  "large": 5},
        "phone":        {"small": 10, "medium": 3,  "large": 1},
        "email":        {"small": 8,  "medium": 9,  "large": 10},
        "slack":        {"small": 9,  "medium": 8,  "large": 7},
        "document":     {"small": 6,  "medium": 8,  "large": 10},
        "presentation": {"small": 5,  "medium": 9,  "large": 10},
    }

    # ── 채널별 격식 적합도 ──
    CHANNEL_FORMALITY_FIT: dict[str, dict[str, int]] = {
        "face_to_face": {"formal": 8,  "informal": 9,  "mixed": 9},
        "video_call":   {"formal": 8,  "informal": 7,  "mixed": 8},
        "phone":        {"formal": 6,  "informal": 8,  "mixed": 7},
        "email":        {"formal": 10, "informal": 5,  "mixed": 7},
        "slack":        {"formal": 4,  "informal": 10, "mixed": 7},
        "document":     {"formal": 10, "informal": 3,  "mixed": 6},
        "presentation": {"formal": 10, "informal": 4,  "mixed": 7},
    }

    # ── 채널 한국어 이름 ──
    CHANNEL_NAME_KO: dict[str, str] = {
        "face_to_face": "대면 회의",
        "video_call": "화상 회의",
        "phone": "전화",
        "email": "이메일",
        "slack": "메신저(슬랙/팀즈)",
        "document": "공식 문서",
        "presentation": "프레젠테이션",
    }

    # ── Cialdini 6원칙 정의 ──
    CIALDINI_PRINCIPLES: dict[str, str] = {
        "reciprocity": "상호성 — 먼저 베풀면 상대도 보답하려는 심리",
        "commitment": "일관성 — 한번 약속/동의하면 계속 유지하려는 심리",
        "social_proof": "사회적 증거 — 다수가 하면 따라가려는 심리",
        "authority": "권위 — 전문가/권위자의 말을 신뢰하는 심리",
        "liking": "호감 — 좋아하는 사람의 부탁에 응하는 심리",
        "scarcity": "희소성 — 한정된 것에 더 가치를 느끼는 심리",
    }

    # ── 한국어 전문용어 패턴 (일반인이 이해하기 어려운 단어) ──
    JARGON_PATTERNS: list[str] = [
        r"ROI|KPI|OKR|SLA|MVP|POC|GTM|CAC|LTV|ARR|MRR|NPS",
        r"레버리지|시너지|스케일|파이프라인|온보딩|오프보딩",
        r"애자일|스크럼|스프린트|백로그|리팩토링|디플로이",
        r"퍼널|리텐션|인게이지먼트|컨버전|어트리뷰션",
        r"디커플링|마이크로서비스|API|SDK|CI/CD|DevOps",
        r"밸류에이션|듀딜리전스|엑시트|벤치마크|포트폴리오",
        r"컨센서스|얼라인먼트|마일스톤|딜리버러블|워크스트림",
    ]

    # ── 메인 디스패처 ────────────────────────

    async def execute(self, **kwargs: Any) -> dict:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full,
            "clarity": self._clarity,
            "persuasion": self._persuasion,
            "channel": self._channel,
            "noise": self._noise,
            "audience": self._audience,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return {
            "status": "error",
            "message": (
                f"알 수 없는 action: {action}. "
                "clarity, persuasion, channel, noise, audience, full 중 하나를 사용하세요."
            ),
        }

    # ═══════════════════════════════════════════════════════
    #  1. clarity — 메시지 명확성 분석
    # ═══════════════════════════════════════════════════════

    async def _clarity(self, params: dict) -> dict:
        """Shannon-Weaver 기반 메시지 명확성 정량 평가.

        평가 지표 4가지:
          ① 평균 문장 길이 (이상적: 한국어 30~40자)
          ② 전문용어 비율 (청중별 허용 수준 대비)
          ③ 구조 점수 (서론→본론→결론 여부)
          ④ 핵심 메시지 식별 가능성 (LLM 분석)
        """
        message = params.get("message", "")
        audience = params.get("audience", "manager")
        if not message:
            return {"status": "error", "message": "message 파라미터가 필요합니다."}

        sentences = _split_sentences(message)
        num_sentences = max(len(sentences), 1)

        # ① 문장 길이 점수 (이상적 30~40자, 벗어날수록 감점)
        avg_sent_len = _mean([_count_chars(s) for s in sentences])
        ideal_min, ideal_max = 30, 40
        if ideal_min <= avg_sent_len <= ideal_max:
            sent_len_score = 100
        elif avg_sent_len < ideal_min:
            sent_len_score = _clamp(100 - (ideal_min - avg_sent_len) * 3)
        else:
            sent_len_score = _clamp(100 - (avg_sent_len - ideal_max) * 2)

        # ② 전문용어 비율 점수
        jargon_count = 0
        jargon_found = []
        combined_pattern = "|".join(self.JARGON_PATTERNS)
        for match in re.finditer(combined_pattern, message, re.IGNORECASE):
            jargon_count += 1
            if match.group() not in jargon_found:
                jargon_found.append(match.group())
        total_words = max(_count_words(message), 1)
        jargon_ratio = jargon_count / total_words
        tolerance = self.JARGON_TOLERANCE.get(audience, 0.3)
        if jargon_ratio <= tolerance:
            jargon_score = 100
        else:
            excess = (jargon_ratio - tolerance) / max(tolerance, 0.01)
            jargon_score = _clamp(100 - excess * 80)

        # ③ 구조 점수 (간단한 휴리스틱 + LLM 보완)
        has_intro = any(kw in message[:100] for kw in ["안녕", "배경", "목적", "건으로", "관련하여", "제안"])
        has_conclusion = any(kw in message[-150:] for kw in ["결론", "요약", "부탁", "감사", "따라서", "정리하면"])
        has_body = num_sentences >= 3
        structure_score = (30 if has_intro else 0) + (40 if has_body else 10) + (30 if has_conclusion else 0)

        # ④ 핵심 메시지 식별 (LLM)
        key_msg_prompt = (
            "아래 메시지를 읽고:\n"
            "1) 핵심 메시지 1문장으로 요약\n"
            "2) 핵심 메시지가 명확하게 드러나는지 1~10 점수 (10=매우 명확)\n"
            "3) 개선 제안 2~3가지\n"
            "JSON 형식으로 답변: {\"core_message\": \"...\", \"score\": N, \"suggestions\": [\"...\"]}"
        )
        llm_result = await self._llm_call(key_msg_prompt, f"[청중: {audience}]\n\n{message}")
        key_msg_score = 70  # LLM 점수 파싱 실패 시 기본값
        try:
            import json
            parsed = json.loads(llm_result)
            key_msg_score = _clamp(parsed.get("score", 7) * 10)
        except Exception:
            pass

        # 종합 Clarity Score
        clarity_score = round(
            sent_len_score * 0.25
            + jargon_score * 0.25
            + structure_score * 0.25
            + key_msg_score * 0.25, 1
        )

        return {
            "status": "success",
            "action": "clarity",
            "result": {
                "clarity_score": clarity_score,
                "grade": self._score_grade(clarity_score),
                "details": {
                    "sentence_length": {
                        "score": round(sent_len_score, 1),
                        "avg_chars": round(avg_sent_len, 1),
                        "ideal_range": "30~40자",
                        "sentence_count": num_sentences,
                    },
                    "jargon": {
                        "score": round(jargon_score, 1),
                        "ratio": round(jargon_ratio * 100, 1),
                        "tolerance_pct": round(tolerance * 100, 1),
                        "found": jargon_found[:15],
                    },
                    "structure": {
                        "score": structure_score,
                        "has_intro": has_intro,
                        "has_body": has_body,
                        "has_conclusion": has_conclusion,
                    },
                    "key_message": {
                        "score": round(key_msg_score, 1),
                    },
                },
                "audience": audience,
            },
            "llm_interpretation": llm_result,
        }

    # ═══════════════════════════════════════════════════════
    #  2. persuasion — 설득력 분석
    # ═══════════════════════════════════════════════════════

    # ── Cialdini 정량 탐지 패턴 (regex 기반, LLM 호출 전 사전 계산) ──
    CIALDINI_PATTERNS: dict[str, str] = {
        "reciprocity":   r"무료|공짜|선물|보너스|혜택|제공|드립니다|증정|사은품|무상",
        "scarcity":      r"한정|마감|선착순|오늘만|지금만|남은|마지막|품절 임박|잔여|곧 종료",
        "authority":     r"전문가|교수|박사|연구|논문|인증|수상|경력|석사|자격증|특허",
        "consistency":   r"약속|보장|확실|언제나|항상|변함없|일관|꾸준|지속|신뢰",
        "liking":        r"같이|함께|우리|공감|이해|비슷|친근|편안|소통|공유",
        "social_proof":  r"후기|리뷰|만족|고객|사용자|명이|인기|베스트셀러|화제|추천수",
    }

    async def _persuasion(self, params: dict) -> dict:
        """Aristotle 수사학 3요소 + Cialdini 6원칙 기반 설득력 정량 평가."""
        message = params.get("message", "")
        goal = params.get("goal", "상대를 설득하여 동의를 얻는 것")
        if not message:
            return {"status": "error", "message": "message 파라미터가 필요합니다."}

        # ── Cialdini 정량 사전 탐지 (regex, LLM 호출 전) ──
        cialdini_quantified: dict[str, dict] = {}
        for principle, pattern in self.CIALDINI_PATTERNS.items():
            matches = re.findall(pattern, message, re.IGNORECASE)
            count = len(matches)
            score = min(100, count * 20)  # 시그널 1개=20점, 5개 이상=100점
            cialdini_quantified[principle] = {
                "signal_count": count,
                "signals_found": list(set(matches))[:10],
                "quantified_score": score,
            }

        prompt_system = (
            "당신은 설득 커뮤니케이션 전문가입니다. Aristotle 수사학과 Cialdini 설득 심리학 프레임워크로 분석하세요.\n\n"
            "분석 프레임워크:\n"
            "1) Aristotle 3요소: Ethos(신뢰/전문성), Pathos(감정 호소), Logos(논리/근거) — 각 1~10점\n"
            "2) Cialdini 6원칙: reciprocity(상호성), commitment(일관성), social_proof(사회적 증거), "
            "authority(권위), liking(호감), scarcity(희소성) — 각 사용 여부(true/false)\n"
            "3) 추가 활용 가능한 원칙 추천\n\n"
            "JSON 형식으로 답변:\n"
            "{\n"
            "  \"ethos\": {\"score\": N, \"evidence\": \"근거\"},\n"
            "  \"pathos\": {\"score\": N, \"evidence\": \"근거\"},\n"
            "  \"logos\": {\"score\": N, \"evidence\": \"근거\"},\n"
            "  \"cialdini\": {\"reciprocity\": bool, \"commitment\": bool, \"social_proof\": bool, "
            "\"authority\": bool, \"liking\": bool, \"scarcity\": bool},\n"
            "  \"recommendations\": [\"추천1\", \"추천2\"],\n"
            "  \"overall_impression\": \"총평\"\n"
            "}"
        )
        prompt_user = f"[설득 목표: {goal}]\n\n{message}"
        llm_result = await self._llm_call(prompt_system, prompt_user)

        # LLM 결과 파싱 (실패 시 기본값)
        ethos, pathos, logos = 5, 5, 5
        cialdini_used = 0
        cialdini_details = {}
        try:
            import json
            parsed = json.loads(llm_result)
            ethos = parsed.get("ethos", {}).get("score", 5)
            pathos = parsed.get("pathos", {}).get("score", 5)
            logos = parsed.get("logos", {}).get("score", 5)
            cialdini_raw = parsed.get("cialdini", {})
            for principle in self.CIALDINI_PRINCIPLES:
                used = bool(cialdini_raw.get(principle, False))
                cialdini_details[principle] = used
                if used:
                    cialdini_used += 1
        except Exception:
            for principle in self.CIALDINI_PRINCIPLES:
                cialdini_details[principle] = False

        # ── Cialdini 정량 점수: regex 기반 + LLM 보정 (하이브리드) ──
        cialdini_final_scores: dict[str, float] = {}
        for principle in self.CIALDINI_PRINCIPLES:
            regex_score = cialdini_quantified[principle]["quantified_score"]
            llm_detected = cialdini_details.get(principle, False)
            # LLM이 감지했으면 최소 40점 보장, regex 점수와 병합
            llm_bonus = 40 if llm_detected else 0
            combined = min(100, max(regex_score, llm_bonus))
            cialdini_final_scores[principle] = combined

        cialdini_avg = _mean(list(cialdini_final_scores.values()))

        # ── Persuasion Score = Aristotle 60% + Cialdini 정량 40% ──
        aristotle_avg = _mean([ethos, pathos, logos])
        aristotle_score_100 = _clamp(aristotle_avg * 10)  # 1~10 → 0~100 스케일
        persuasion_score = _clamp(
            aristotle_score_100 * 0.6 + cialdini_avg * 0.4
        )

        return {
            "status": "success",
            "action": "persuasion",
            "result": {
                "persuasion_score": round(persuasion_score, 1),
                "grade": self._score_grade(persuasion_score),
                "aristotle": {
                    "ethos": ethos,
                    "pathos": pathos,
                    "logos": logos,
                    "average": round(aristotle_avg, 1),
                    "score_100": round(aristotle_score_100, 1),
                    "weight": "60%",
                },
                "cialdini": {
                    "principles_used": cialdini_used,
                    "details": cialdini_details,
                    "quantified_scores": {
                        k: {
                            "regex_signals": cialdini_quantified[k]["signal_count"],
                            "signals_found": cialdini_quantified[k]["signals_found"],
                            "regex_score": cialdini_quantified[k]["quantified_score"],
                            "llm_detected": cialdini_details.get(k, False),
                            "final_score": cialdini_final_scores[k],
                        }
                        for k in self.CIALDINI_PRINCIPLES
                    },
                    "average_score": round(cialdini_avg, 1),
                    "weight": "40%",
                    "descriptions": self.CIALDINI_PRINCIPLES,
                },
                "scoring_method": "Aristotle(60%) + Cialdini Quantified(40%) 가중 평균",
                "goal": goal,
            },
            "llm_interpretation": llm_result,
        }

    # ═══════════════════════════════════════════════════════
    #  3. channel — 최적 채널 추천
    # ═══════════════════════════════════════════════════════

    async def _channel(self, params: dict) -> dict:
        """미디어 리치니스 이론 + 실무 매트릭스 기반 최적 채널 추천."""
        msg_type = params.get("message_type", "routine")
        audience_size = int(params.get("audience_size", 5))
        formality = params.get("formality", "mixed")

        # 청중 규모 구간 결정
        if audience_size <= 5:
            size_key = "small"
        elif audience_size <= 20:
            size_key = "medium"
        else:
            size_key = "large"

        # 각 채널별 종합 점수 계산
        channel_scores = {}
        for channel in self.CHANNEL_MATRIX:
            type_score = self.CHANNEL_MATRIX[channel].get(msg_type, 5)
            size_score = self.CHANNEL_AUDIENCE_FIT[channel].get(size_key, 5)
            form_score = self.CHANNEL_FORMALITY_FIT[channel].get(formality, 5)

            # 가중 합산: 메시지 유형 40%, 청중 규모 30%, 격식 30%
            total = type_score * 0.4 + size_score * 0.3 + form_score * 0.3
            channel_scores[channel] = round(total, 2)

        # 상위 3개 추천
        ranked = sorted(channel_scores.items(), key=lambda x: x[1], reverse=True)
        top3 = ranked[:3]

        # LLM으로 추천 이유 생성
        top3_str = "\n".join(
            f"{i+1}. {self.CHANNEL_NAME_KO.get(ch, ch)} (점수: {sc})"
            for i, (ch, sc) in enumerate(top3)
        )
        prompt = (
            "커뮤니케이션 채널 추천 결과를 분석하세요.\n"
            f"메시지 유형: {msg_type}, 청중: {audience_size}명, 격식: {formality}\n"
            f"추천 순위:\n{top3_str}\n\n"
            "각 채널이 추천된 이유와 활용 팁을 간결하게 설명하세요."
        )
        llm_result = await self._llm_call(prompt, f"채널 추천 분석 요청")

        return {
            "status": "success",
            "action": "channel",
            "result": {
                "recommendations": [
                    {
                        "rank": i + 1,
                        "channel": ch,
                        "channel_ko": self.CHANNEL_NAME_KO.get(ch, ch),
                        "score": sc,
                        "max_score": 10.0,
                    }
                    for i, (ch, sc) in enumerate(top3)
                ],
                "all_scores": {
                    self.CHANNEL_NAME_KO.get(ch, ch): sc
                    for ch, sc in ranked
                },
                "parameters": {
                    "message_type": msg_type,
                    "audience_size": audience_size,
                    "size_category": size_key,
                    "formality": formality,
                },
            },
            "llm_interpretation": llm_result,
        }

    # ═══════════════════════════════════════════════════════
    #  4. noise — 커뮤니케이션 노이즈 분석
    # ═══════════════════════════════════════════════════════

    async def _noise(self, params: dict) -> dict:
        """Shannon-Weaver 모델 기반 커뮤니케이션 노이즈 탐지 및 제거."""
        message = params.get("message", "")
        context = params.get("context", "비즈니스 커뮤니케이션")
        if not message:
            return {"status": "error", "message": "message 파라미터가 필요합니다."}

        sentences = _split_sentences(message)
        num_sentences = max(len(sentences), 1)

        # 수학적 노이즈 지표 계산
        # ① 중복 표현 탐지 (같은 의미 반복)
        unique_words = set(message.split())
        total_words = max(_count_words(message), 1)
        lexical_diversity = len(unique_words) / total_words  # 낮을수록 반복 많음

        # ② 불필요한 수식어/필러 패턴
        filler_patterns = [
            r"기본적으로|사실상|실질적으로|일반적으로|보통|대체로",
            r"어떤 의미에서|말하자면|그러니까|뭐랄까|솔직히",
            r"매우|정말|진짜|완전|꽤|약간|다소|상당히",
            r"등등|기타|여러 가지|이런저런",
        ]
        filler_count = 0
        fillers_found = []
        for pattern in filler_patterns:
            for match in re.finditer(pattern, message):
                filler_count += 1
                if match.group() not in fillers_found:
                    fillers_found.append(match.group())

        filler_ratio = filler_count / total_words

        # ③ Signal-to-Noise Ratio (핵심 정보 문장 비율 추정)
        # 짧고 구체적인 문장 = 신호, 길고 모호한 문장 = 노이즈
        signal_sentences = 0
        for s in sentences:
            char_count = _count_chars(s)
            has_number = bool(re.search(r'\d', s))
            has_specific = bool(re.search(r'[%원건명개월일시]', s))
            if (15 <= char_count <= 60) or has_number or has_specific:
                signal_sentences += 1

        snr = signal_sentences / num_sentences  # 0~1, 높을수록 좋음
        snr_db = round(10 * math.log10(snr / (1 - snr + 0.001) + 0.001), 1) if snr > 0 else -20

        # LLM 노이즈 분석 + 개선 메시지 생성
        prompt_system = (
            "커뮤니케이션 노이즈 전문가로서 분석하세요.\n"
            "Shannon-Weaver 모델의 3가지 노이즈 유형으로 분류:\n"
            "1) semantic(의미적) — 모호한 표현, 이중 의미, 추상적 언어\n"
            "2) technical(기술적) — 전달 방식 문제, 포맷 부적절\n"
            "3) psychological(심리적) — 감정적 트리거, 방어 유발 표현\n\n"
            "JSON 형식:\n"
            "{\n"
            "  \"semantic_noise\": [{\"phrase\": \"문제 표현\", \"issue\": \"문제점\", \"fix\": \"개선안\"}],\n"
            "  \"technical_noise\": [{\"issue\": \"문제점\", \"fix\": \"개선안\"}],\n"
            "  \"psychological_noise\": [{\"trigger\": \"트리거 표현\", \"risk\": \"위험\", \"fix\": \"개선안\"}],\n"
            "  \"improved_message\": \"노이즈 제거 후 개선된 전체 메시지\"\n"
            "}"
        )
        llm_result = await self._llm_call(prompt_system, f"[맥락: {context}]\n\n{message}")

        # 노이즈 점수 종합 (낮을수록 노이즈 적음 = 좋음)
        noise_score = _clamp(
            (1 - lexical_diversity) * 30  # 반복 많으면 노이즈↑
            + filler_ratio * 200           # 필러 많으면 노이즈↑
            + (1 - snr) * 40               # 신호 적으면 노이즈↑
        )
        clarity_after_denoise = _clamp(100 - noise_score)

        return {
            "status": "success",
            "action": "noise",
            "result": {
                "noise_score": round(noise_score, 1),
                "clarity_after_denoise": round(clarity_after_denoise, 1),
                "signal_to_noise_ratio": {
                    "snr": round(snr * 100, 1),
                    "snr_db": snr_db,
                    "signal_sentences": signal_sentences,
                    "total_sentences": num_sentences,
                },
                "lexical_diversity": round(lexical_diversity * 100, 1),
                "fillers": {
                    "count": filler_count,
                    "ratio_pct": round(filler_ratio * 100, 1),
                    "found": fillers_found[:20],
                },
                "context": context,
            },
            "llm_interpretation": llm_result,
        }

    # ═══════════════════════════════════════════════════════
    #  5. audience — 청중 맞춤 변환
    # ═══════════════════════════════════════════════════════

    async def _audience(self, params: dict) -> dict:
        """같은 메시지를 다양한 청중에 맞게 변환 (Mehrabian + 실무 커뮤니케이션 이론)."""
        message = params.get("message", "")
        source_audience = params.get("source_audience", "staff")
        target_audiences = params.get("target_audiences", ["executive", "manager", "external"])
        if not message:
            return {"status": "error", "message": "message 파라미터가 필요합니다."}

        if isinstance(target_audiences, str):
            target_audiences = [a.strip() for a in target_audiences.split(",")]

        # 청중별 변환 기준
        audience_profiles = {
            "executive": {
                "name_ko": "경영진",
                "focus": "의사결정에 필요한 핵심 정보, 비용/수익 영향, 전략적 함의",
                "length": "원문의 30~50%로 압축",
                "tone": "격식 있고 간결, 숫자와 결론 위주",
                "avoid": "기술 세부사항, 과정 설명",
            },
            "manager": {
                "name_ko": "중간관리자",
                "focus": "실행 계획, 일정, 리소스, 팀 영향",
                "length": "원문과 비슷하거나 약간 압축",
                "tone": "업무적이되 협력적",
                "avoid": "지나친 기술 용어, 전략적 배경 장황하게",
            },
            "staff": {
                "name_ko": "실무자",
                "focus": "구체적 작업 내용, 기술 세부사항, 기한",
                "length": "원문보다 상세할 수 있음",
                "tone": "친근하고 구체적",
                "avoid": "추상적 전략 언어, 불필요한 격식",
            },
            "external": {
                "name_ko": "외부 파트너/고객",
                "focus": "가치 제안, 혜택, 신뢰 구축",
                "length": "원문의 50~70%",
                "tone": "정중하고 전문적, 전문용어 최소화",
                "avoid": "내부 용어, 사내 약어, 기술 구현 세부사항",
            },
        }

        # 각 청중별 변환 (LLM)
        conversions = {}
        for target in target_audiences:
            profile = audience_profiles.get(target, audience_profiles["manager"])
            prompt_system = (
                f"커뮤니케이션 전문가로서 메시지를 {profile['name_ko']}에게 맞게 변환하세요.\n\n"
                f"변환 기준:\n"
                f"- 초점: {profile['focus']}\n"
                f"- 분량: {profile['length']}\n"
                f"- 톤: {profile['tone']}\n"
                f"- 피할 것: {profile['avoid']}\n\n"
                "JSON 형식:\n"
                "{\"converted_message\": \"변환된 메시지\", \"changes_made\": [\"변경1\", \"변경2\"], "
                "\"word_count_change\": \"N% 감소/증가\"}"
            )
            result = await self._llm_call(prompt_system, f"[원래 청중: {source_audience}]\n\n{message}")
            conversions[target] = {
                "profile": profile,
                "llm_result": result,
            }

        return {
            "status": "success",
            "action": "audience",
            "result": {
                "source_audience": source_audience,
                "target_audiences": target_audiences,
                "conversions": conversions,
                "original_length": _count_chars(message),
            },
            "llm_interpretation": f"{len(target_audiences)}개 청중 대상 메시지 변환 완료",
        }

    # ═══════════════════════════════════════════════════════
    #  6. full — 종합 분석
    # ═══════════════════════════════════════════════════════

    async def _full(self, params: dict) -> dict:
        """5개 분석 모듈 종합 실행."""
        message = params.get("message", "")
        if not message:
            return {"status": "error", "message": "message 파라미터가 필요합니다."}

        results = {}
        action_list = ["clarity", "persuasion", "noise"]
        for act in action_list:
            handler = getattr(self, f"_{act}")
            results[act] = await handler({**params, "action": act})

        # channel은 별도 파라미터 필요 — 기본값으로 실행
        results["channel"] = await self._channel({
            "message_type": params.get("message_type", "routine"),
            "audience_size": params.get("audience_size", 5),
            "formality": params.get("formality", "mixed"),
        })

        # audience는 message가 있으면 자동 실행
        results["audience"] = await self._audience({
            "message": message,
            "source_audience": params.get("audience", "staff"),
            "target_audiences": params.get("target_audiences", ["executive", "external"]),
        })

        # 종합 요약 (LLM)
        scores_summary = []
        for act in ["clarity", "persuasion", "noise"]:
            r = results.get(act, {}).get("result", {})
            if act == "clarity":
                scores_summary.append(f"명확성: {r.get('clarity_score', 'N/A')}점")
            elif act == "persuasion":
                scores_summary.append(f"설득력: {r.get('persuasion_score', 'N/A')}점")
            elif act == "noise":
                scores_summary.append(f"노이즈: {r.get('noise_score', 'N/A')}점 (낮을수록 좋음)")

        prompt = (
            "커뮤니케이션 전문가로서 아래 분석 결과를 종합하여 핵심 인사이트와 개선 우선순위를 정리하세요.\n"
            f"분석 점수: {', '.join(scores_summary)}\n\n"
            "형식: 1) 강점 2~3개, 2) 개선 필요 2~3개, 3) 즉시 실행 가능한 팁 2개"
        )
        llm_summary = await self._llm_call(prompt, f"종합 분석 대상 메시지:\n{message[:500]}")

        return {
            "status": "success",
            "action": "full",
            "results": results,
            "llm_summary": llm_summary,
        }

    # ═══════════════════════════════════════════════════════
    #  유틸리티 메서드
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def _score_grade(score: float) -> str:
        """점수를 등급으로 변환."""
        if score >= 90:
            return "A+ (탁월)"
        elif score >= 80:
            return "A (우수)"
        elif score >= 70:
            return "B+ (양호)"
        elif score >= 60:
            return "B (보통)"
        elif score >= 50:
            return "C (개선 필요)"
        else:
            return "D (대폭 개선 필요)"
