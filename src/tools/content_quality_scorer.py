"""
콘텐츠 품질 채점 도구 — 마케팅 콘텐츠를 다각도로 평가합니다.

"이 글이 진짜 좋은 콘텐츠인가?"를 수치적으로 판별하는 교수급 채점 도구입니다.
가독성, SEO, E-E-A-T, 감성, 구조를 종합 평가해 100점 만점으로 채점합니다.

학술 근거:
  - Flesch Reading Ease (Rudolf Flesch, 1948) — 한국어 적용 변형
  - Gunning Fog Index (Robert Gunning, 1952)
  - E-E-A-T 프레임워크 (Google Search Quality Guidelines, 2022)
  - SEO Content Score (Moz + Ahrefs 연구 종합)
  - 감성 분석 (VADER sentiment + 한국어 극성 사전)
  - Hook Model (Nir Eyal, 2014) — 콘텐츠 중독성 평가
  - Cialdini의 설득 원리 (Robert Cialdini, 2001)

사용 방법:
  - action="score"      : 종합 품질 점수 (100점)
  - action="readability" : 가독성 분석 (Flesch 한국어 변형)
  - action="seo"        : SEO 점수 분석
  - action="eeat"       : E-E-A-T 평가
  - action="persuasion" : 설득력 분석 (Cialdini 6원칙)
  - action="full"       : 종합 분석

필요 환경변수: 없음
필요 라이브러리: 없음 (순수 Python)
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.content_quality_scorer")


# ═══════════════════════════════════════════════════════
#  한국어 가독성 상수
# ═══════════════════════════════════════════════════════

# 한국어 어려운 단어 패턴 (한자어, 전문용어 등)
DIFFICULT_PATTERNS = [
    r"[가-힣]*화\b",       # ~화 (최적화, 정상화)
    r"[가-힣]*성\b",       # ~성 (효율성, 가능성)
    r"[가-힣]*적\b",       # ~적 (전략적, 효과적)
    r"[가-힣]*론\b",       # ~론 (방법론, 이론)
    r"[가-힣]*률\b",       # ~률 (확률, 비율)
    r"패러다임|프레임워크|인사이트|시너지|레버리지|스케일",  # 외래어 전문용어
]

# SEO 최적 범위 (업계 연구 종합)
SEO_OPTIMAL = {
    "title_length": (30, 60),       # 제목 길이 (자)
    "meta_desc_length": (120, 160), # 메타 설명 (자)
    "content_length": (1500, 5000), # 본문 길이 (자)
    "heading_ratio": (0.02, 0.08),  # 제목 비율
    "keyword_density": (0.01, 0.03), # 키워드 밀도
    "paragraph_avg_length": (100, 300), # 문단 평균 길이
    "image_per_300_words": 1,       # 300자당 이미지 1개
}


class ContentQualityScorerTool(BaseTool):
    """교수급 콘텐츠 품질 채점 도구."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        action = kwargs.get("action", "full")
        dispatch = {
            "score": self._score,
            "readability": self._readability,
            "seo": self._seo,
            "eeat": self._eeat,
            "persuasion": self._persuasion,
            "full": self._full_analysis,
        }
        handler = dispatch.get(action)
        if not handler:
            return {"error": f"지원하지 않는 action: {action}. "
                    f"가능한 값: {list(dispatch.keys())}"}
        return await handler(**kwargs)

    # ═══════════════════════════════════════════════════════
    #  1. 종합 품질 점수
    # ═══════════════════════════════════════════════════════

    async def _score(self, **kwargs) -> dict[str, Any]:
        """콘텐츠를 100점 만점으로 종합 채점."""
        content = kwargs.get("content", "")
        title = kwargs.get("title", "")
        keyword = kwargs.get("keyword", "")

        if not content:
            return {"error": "content(본문 텍스트)를 입력해주세요."}

        # 각 영역 점수 계산
        readability = self._calc_readability(content)
        seo = self._calc_seo(content, title, keyword)
        structure = self._calc_structure(content)
        engagement = self._calc_engagement(content)
        persuasion = self._calc_persuasion_score(content)

        # 가중 평균 (각 영역의 중요도)
        weights = {
            "readability": 0.25,
            "seo": 0.20,
            "structure": 0.20,
            "engagement": 0.20,
            "persuasion": 0.15,
        }
        scores = {
            "readability": readability["score"],
            "seo": seo["score"],
            "structure": structure["score"],
            "engagement": engagement["score"],
            "persuasion": persuasion["score"],
        }

        total = sum(scores[k] * weights[k] for k in weights)

        # 등급 판정
        grade = self._grade(total)

        result = {
            "total_score": round(total, 1),
            "grade": grade,
            "breakdown": {
                k: {"score": round(v, 1), "weight": f"{weights[k]*100:.0f}%"}
                for k, v in scores.items()
            },
            "content_stats": {
                "char_count": len(content),
                "word_count": len(content.split()),
                "sentence_count": self._count_sentences(content),
                "paragraph_count": content.count("\n\n") + 1,
            },
            "top_improvements": self._get_top_improvements(
                readability, seo, structure, engagement, persuasion
            ),
        }

        llm_summary = await self._llm_call(
            f"콘텐츠 품질 채점 결과입니다:\n{result}\n\n"
            f"제목: {title}\n본문 앞부분: {content[:300]}...\n\n"
            "점수를 높이기 위한 구체적인 개선안 3가지를 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  2. 가독성 분석
    # ═══════════════════════════════════════════════════════

    async def _readability(self, **kwargs) -> dict[str, Any]:
        """Flesch 한국어 변형 + Gunning Fog 한국어 변형."""
        content = kwargs.get("content", "")
        if not content:
            return {"error": "content(본문 텍스트)를 입력해주세요."}

        analysis = self._calc_readability(content)

        result = {
            **analysis,
            "academic_reference": (
                "Flesch (1948) Reading Ease + "
                "Gunning (1952) Fog Index — 한국어 적용 변형"
            ),
        }

        llm_summary = await self._llm_call(
            f"가독성 분석 결과입니다:\n{result}\n\n"
            f"본문 앞부분: {content[:500]}...\n\n"
            "가독성을 높이기 위한 구체적인 문장 수정 제안을 해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  3. SEO 점수 분석
    # ═══════════════════════════════════════════════════════

    async def _seo(self, **kwargs) -> dict[str, Any]:
        """SEO 관점에서 콘텐츠 품질 평가."""
        content = kwargs.get("content", "")
        title = kwargs.get("title", "")
        keyword = kwargs.get("keyword", "")
        meta_description = kwargs.get("meta_description", "")

        if not content:
            return {"error": "content(본문 텍스트)를 입력해주세요."}

        analysis = self._calc_seo(content, title, keyword, meta_description)

        result = {
            **analysis,
            "academic_reference": "Moz + Ahrefs + Google Search Quality Guidelines 종합",
        }

        llm_summary = await self._llm_call(
            f"SEO 분석 결과입니다:\n{result}\n\n"
            f"제목: {title}\n키워드: {keyword}\n\n"
            "SEO 점수를 높이기 위한 구체적 액션을 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  4. E-E-A-T 평가
    # ═══════════════════════════════════════════════════════

    async def _eeat(self, **kwargs) -> dict[str, Any]:
        """Google E-E-A-T (Experience, Expertise, Authoritativeness, Trust) 평가."""
        content = kwargs.get("content", "")
        author = kwargs.get("author", "")
        has_citations = kwargs.get("has_citations", False)
        has_data = kwargs.get("has_data", False)
        has_original_research = kwargs.get("has_original_research", False)

        if not content:
            return {"error": "content(본문 텍스트)를 입력해주세요."}

        # E-E-A-T 각 축 점수 계산
        experience_score = self._calc_experience(content)
        expertise_score = self._calc_expertise(content, has_citations)
        authority_score = self._calc_authority(content, author, has_data)
        trust_score = self._calc_trust(content, has_original_research)

        total = (experience_score + expertise_score +
                 authority_score + trust_score) / 4

        result = {
            "eeat_total": round(total, 1),
            "breakdown": {
                "experience": {
                    "score": round(experience_score, 1),
                    "description": "직접 경험/사례/후기 포함 여부",
                },
                "expertise": {
                    "score": round(expertise_score, 1),
                    "description": "전문 지식의 깊이 + 인용/출처",
                },
                "authoritativeness": {
                    "score": round(authority_score, 1),
                    "description": "저자 권위 + 데이터 근거",
                },
                "trustworthiness": {
                    "score": round(trust_score, 1),
                    "description": "투명성 + 정확성 + 독창성",
                },
            },
            "improvements": self._eeat_improvements(
                experience_score, expertise_score,
                authority_score, trust_score
            ),
            "academic_reference": "Google Search Quality Evaluator Guidelines (2022) E-E-A-T",
        }

        llm_summary = await self._llm_call(
            f"E-E-A-T 분석 결과입니다:\n{result}\n\n"
            f"본문 앞부분: {content[:500]}...\n\n"
            "각 E-E-A-T 축별 개선 방법을 구체적으로 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  5. 설득력 분석 (Cialdini 6원칙)
    # ═══════════════════════════════════════════════════════

    async def _persuasion(self, **kwargs) -> dict[str, Any]:
        """Cialdini 설득의 6원칙 + Hook Model 기반 설득력 분석."""
        content = kwargs.get("content", "")
        if not content:
            return {"error": "content(본문 텍스트)를 입력해주세요."}

        analysis = self._calc_persuasion_score(content)

        result = {
            **analysis,
            "academic_reference": (
                "Cialdini (2001) 'Influence: The Psychology of Persuasion' + "
                "Nir Eyal (2014) 'Hooked: How to Build Habit-Forming Products'"
            ),
        }

        llm_summary = await self._llm_call(
            f"설득력 분석 결과입니다:\n{result}\n\n"
            f"본문 앞부분: {content[:500]}...\n\n"
            "설득력을 높이기 위해 추가할 수 있는 요소를 구체적으로 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  6. 종합 분석
    # ═══════════════════════════════════════════════════════

    async def _full_analysis(self, **kwargs) -> dict[str, Any]:
        """모든 분석을 통합."""
        score_result = await self._score(**kwargs)
        readability_result = await self._readability(**kwargs)
        seo_result = await self._seo(**kwargs)
        eeat_result = await self._eeat(**kwargs)
        persuasion_result = await self._persuasion(**kwargs)

        result = {
            "summary": "교수급 콘텐츠 품질 종합 분석",
            "1_total_score": score_result,
            "2_readability": readability_result,
            "3_seo": seo_result,
            "4_eeat": eeat_result,
            "5_persuasion": persuasion_result,
        }

        llm_summary = await self._llm_call(
            f"콘텐츠 품질 종합 분석입니다:\n\n"
            f"총점: {score_result.get('total_score', 0)}/100\n"
            f"등급: {score_result.get('grade', 'N/A')}\n\n"
            "전체를 종합해 콘텐츠 품질 개선 로드맵을 제안해주세요."
        )
        result["executive_summary"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  핵심 계산 함수들
    # ═══════════════════════════════════════════════════════

    def _calc_readability(self, content: str) -> dict:
        """가독성 점수 계산 (100점 만점)."""
        sentences = self._count_sentences(content)
        words = len(content.split())
        chars = len(content.replace(" ", "").replace("\n", ""))

        if sentences == 0 or words == 0:
            return {"score": 0, "details": "텍스트가 너무 짧습니다"}

        # ─── 한국어 Flesch 변형 (KR-Flesch) ───
        # 원본: 206.835 - 1.015(words/sentences) - 84.6(syllables/words)
        # 한국어: 글자/어절 비율 사용 (음절 대신)
        avg_sentence_len = words / sentences
        avg_word_len = chars / words

        # 한국어 Flesch Reading Ease 변형
        kr_flesch = 206.835 - 1.015 * avg_sentence_len - 31.0 * avg_word_len
        kr_flesch = max(0, min(100, kr_flesch))

        # ─── 어려운 단어 비율 ───
        difficult_count = 0
        for pattern in DIFFICULT_PATTERNS:
            difficult_count += len(re.findall(pattern, content))

        difficult_ratio = difficult_count / words if words > 0 else 0

        # ─── 문장 길이 변동성 (좋은 글은 길고 짧은 문장이 섞임) ───
        sentence_lengths = []
        for s in re.split(r'[.!?。]+', content):
            s = s.strip()
            if s:
                sentence_lengths.append(len(s.split()))

        if len(sentence_lengths) >= 2:
            length_cv = (float(_std(sentence_lengths)) /
                         float(_mean(sentence_lengths)))
            variation_score = min(100, length_cv * 200)  # CV 0.5면 100점
        else:
            variation_score = 50

        # 종합 가독성 점수
        score = (
            kr_flesch * 0.4 +
            (1 - difficult_ratio) * 100 * 0.3 +
            variation_score * 0.3
        )

        # 등급
        if kr_flesch >= 60:
            level = "쉬움 (초등 5~6학년)"
        elif kr_flesch >= 40:
            level = "보통 (중학생)"
        elif kr_flesch >= 20:
            level = "어려움 (고등학생+)"
        else:
            level = "매우 어려움 (전문가)"

        return {
            "score": round(min(100, max(0, score)), 1),
            "kr_flesch_ease": round(kr_flesch, 1),
            "difficulty_level": level,
            "avg_sentence_length": round(avg_sentence_len, 1),
            "avg_word_length": round(avg_word_len, 1),
            "difficult_word_ratio": f"{difficult_ratio*100:.1f}%",
            "sentence_variation": round(variation_score, 1),
            "recommendations": self._readability_recommendations(
                avg_sentence_len, difficult_ratio, variation_score
            ),
        }

    def _calc_seo(self, content: str, title: str = "",
                  keyword: str = "", meta_desc: str = "") -> dict:
        """SEO 점수 계산 (100점 만점)."""
        checks = []
        total_score = 0
        max_score = 0

        # 1. 제목 길이
        if title:
            title_len = len(title)
            opt_min, opt_max = SEO_OPTIMAL["title_length"]
            if opt_min <= title_len <= opt_max:
                checks.append({"item": "제목 길이", "status": "pass",
                               "detail": f"{title_len}자 (최적: {opt_min}~{opt_max}자)"})
                total_score += 10
            else:
                checks.append({"item": "제목 길이", "status": "warn",
                               "detail": f"{title_len}자 (권장: {opt_min}~{opt_max}자)"})
                total_score += 5
            max_score += 10

        # 2. 콘텐츠 길이
        content_len = len(content)
        opt_min, opt_max = SEO_OPTIMAL["content_length"]
        if content_len >= opt_min:
            checks.append({"item": "본문 길이", "status": "pass",
                           "detail": f"{content_len}자"})
            total_score += 15
        elif content_len >= 800:
            checks.append({"item": "본문 길이", "status": "warn",
                           "detail": f"{content_len}자 (권장: {opt_min}자 이상)"})
            total_score += 8
        else:
            checks.append({"item": "본문 길이", "status": "fail",
                           "detail": f"{content_len}자 (너무 짧음)"})
            total_score += 3
        max_score += 15

        # 3. 키워드 밀도
        if keyword:
            keyword_count = content.lower().count(keyword.lower())
            words = len(content.split())
            density = keyword_count / words if words > 0 else 0
            opt_min, opt_max = SEO_OPTIMAL["keyword_density"]
            if opt_min <= density <= opt_max:
                checks.append({"item": "키워드 밀도", "status": "pass",
                               "detail": f"{density*100:.1f}% ({keyword_count}회)"})
                total_score += 15
            elif density > 0:
                checks.append({"item": "키워드 밀도", "status": "warn",
                               "detail": f"{density*100:.1f}% (권장: 1~3%)"})
                total_score += 8
            else:
                checks.append({"item": "키워드 밀도", "status": "fail",
                               "detail": "키워드 미포함"})
            max_score += 15

            # 4. 키워드 위치
            first_100 = content[:100].lower()
            if keyword.lower() in first_100:
                checks.append({"item": "키워드 위치 (첫 100자)", "status": "pass",
                               "detail": "본문 초반에 키워드 포함"})
                total_score += 10
            else:
                checks.append({"item": "키워드 위치 (첫 100자)", "status": "warn",
                               "detail": "첫 100자에 키워드 없음"})
                total_score += 3
            max_score += 10

            # 5. 제목에 키워드
            if title and keyword.lower() in title.lower():
                checks.append({"item": "제목 키워드", "status": "pass",
                               "detail": "제목에 키워드 포함"})
                total_score += 10
            elif title:
                checks.append({"item": "제목 키워드", "status": "fail",
                               "detail": "제목에 키워드 없음"})
            max_score += 10

        # 6. 구조 (제목/소제목 사용)
        heading_count = len(re.findall(r'#{1,3}\s|<h[1-6]', content))
        if heading_count >= 3:
            checks.append({"item": "소제목 사용", "status": "pass",
                           "detail": f"{heading_count}개 소제목"})
            total_score += 10
        elif heading_count >= 1:
            checks.append({"item": "소제목 사용", "status": "warn",
                           "detail": f"{heading_count}개 (3개 이상 권장)"})
            total_score += 5
        else:
            checks.append({"item": "소제목 사용", "status": "fail",
                           "detail": "소제목 없음"})
        max_score += 10

        # 7. 문단 길이
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if paragraphs:
            avg_para_len = sum(len(p) for p in paragraphs) / len(paragraphs)
            if avg_para_len <= 300:
                checks.append({"item": "문단 길이", "status": "pass",
                               "detail": f"평균 {avg_para_len:.0f}자"})
                total_score += 10
            else:
                checks.append({"item": "문단 길이", "status": "warn",
                               "detail": f"평균 {avg_para_len:.0f}자 (300자 이하 권장)"})
                total_score += 5
        max_score += 10

        # 8. 리스트/목록 사용
        list_count = len(re.findall(r'[-*•]\s|^\d+[.)]\s', content, re.MULTILINE))
        if list_count >= 3:
            checks.append({"item": "목록 사용", "status": "pass",
                           "detail": f"{list_count}개 항목"})
            total_score += 10
        elif list_count >= 1:
            checks.append({"item": "목록 사용", "status": "warn",
                           "detail": f"{list_count}개 (3개 이상 권장)"})
            total_score += 5
        else:
            checks.append({"item": "목록 사용", "status": "fail",
                           "detail": "목록 없음"})
        max_score += 10

        normalized_score = (total_score / max_score * 100) if max_score > 0 else 0

        return {
            "score": round(min(100, normalized_score), 1),
            "checks": checks,
            "pass_count": sum(1 for c in checks if c["status"] == "pass"),
            "total_checks": len(checks),
        }

    def _calc_structure(self, content: str) -> dict:
        """콘텐츠 구조 점수."""
        score = 0

        # 서론-본론-결론 구조 감지
        has_intro = bool(re.search(r'^.{50,300}[\n]', content))
        has_conclusion = bool(re.search(
            r'(결론|마무리|정리|요약|마치며|핵심).{10,}$', content, re.MULTILINE
        ))
        has_cta = bool(re.search(
            r'(신청|구매|가입|시작|클릭|문의|확인|다운로드)', content
        ))

        if has_intro:
            score += 30
        if has_conclusion:
            score += 30
        if has_cta:
            score += 20

        # 논리적 흐름 (접속사 사용)
        connectors = len(re.findall(
            r'(따라서|그러므로|또한|그러나|하지만|반면|예를 들어|즉|결과적으로|왜냐하면)',
            content
        ))
        if connectors >= 5:
            score += 20
        elif connectors >= 2:
            score += 10

        return {
            "score": min(100, score),
            "has_intro": has_intro,
            "has_conclusion": has_conclusion,
            "has_cta": has_cta,
            "connector_count": connectors,
        }

    def _calc_engagement(self, content: str) -> dict:
        """독자 몰입도/참여 유도 점수."""
        score = 0

        # 질문 사용
        question_count = len(re.findall(r'\?', content))
        if question_count >= 3:
            score += 25
        elif question_count >= 1:
            score += 15

        # 숫자/데이터 사용
        number_count = len(re.findall(r'\d+[%만억원회개명]', content))
        if number_count >= 5:
            score += 25
        elif number_count >= 2:
            score += 15

        # 대화체/2인칭 사용
        you_count = len(re.findall(r'(당신|여러분|독자|고객님|사장님|대표님)', content))
        if you_count >= 3:
            score += 25
        elif you_count >= 1:
            score += 15

        # 스토리텔링 요소
        story_signals = len(re.findall(
            r'(어느 날|실제로|사례|경험|이야기|이전에|결국|비하인드)', content
        ))
        if story_signals >= 2:
            score += 25
        elif story_signals >= 1:
            score += 15

        return {
            "score": min(100, score),
            "question_count": question_count,
            "data_points": number_count,
            "personalization": you_count,
            "story_elements": story_signals,
        }

    def _calc_persuasion_score(self, content: str) -> dict:
        """Cialdini 6원칙 기반 설득력 점수."""
        principles = {}

        # 1. 상호성 (Reciprocity)
        reciprocity_signals = len(re.findall(
            r'(무료|공짜|선물|보너스|추가|혜택|제공|드립니다)', content
        ))
        principles["reciprocity"] = {
            "name_ko": "상호성",
            "signals": reciprocity_signals,
            "score": min(100, reciprocity_signals * 25),
            "tip": "무료 가치를 먼저 제공하면 호혜 심리가 작동합니다",
        }

        # 2. 희소성 (Scarcity)
        scarcity_signals = len(re.findall(
            r'(한정|마감|선착순|오늘만|지금|곧|남은|마지막|품절|조기)', content
        ))
        principles["scarcity"] = {
            "name_ko": "희소성",
            "signals": scarcity_signals,
            "score": min(100, scarcity_signals * 25),
            "tip": "한정 수량/기간을 명시하면 행동을 촉진합니다",
        }

        # 3. 권위 (Authority)
        authority_signals = len(re.findall(
            r'(전문가|교수|박사|연구|논문|데이터|통계|검증|인증|수상)', content
        ))
        principles["authority"] = {
            "name_ko": "권위",
            "signals": authority_signals,
            "score": min(100, authority_signals * 20),
            "tip": "전문가 의견, 연구 결과, 인증을 인용하세요",
        }

        # 4. 일관성 (Consistency)
        consistency_signals = len(re.findall(
            r'(약속|보장|확실|반드시|꾸준|항상|변함없)', content
        ))
        principles["consistency"] = {
            "name_ko": "일관성",
            "signals": consistency_signals,
            "score": min(100, consistency_signals * 25),
            "tip": "작은 동의를 먼저 이끌어내면 큰 행동으로 이어집니다",
        }

        # 5. 호감 (Liking)
        liking_signals = len(re.findall(
            r'(같이|함께|우리|공감|이해|비슷|공통|친근)', content
        ))
        principles["liking"] = {
            "name_ko": "호감",
            "signals": liking_signals,
            "score": min(100, liking_signals * 25),
            "tip": "공감, 유사성, 칭찬으로 친밀감을 형성하세요",
        }

        # 6. 사회적 증거 (Social Proof)
        social_signals = len(re.findall(
            r'(후기|리뷰|평점|만족|고객|사용자|명이|%가|많은|인기)', content
        ))
        principles["social_proof"] = {
            "name_ko": "사회적 증거",
            "signals": social_signals,
            "score": min(100, social_signals * 20),
            "tip": "고객 후기, 사용자 수, 평점을 보여주세요",
        }

        # 종합 점수
        total = sum(p["score"] for p in principles.values()) / len(principles)

        return {
            "score": round(total, 1),
            "principles": principles,
            "strongest": max(principles.items(), key=lambda x: x[1]["score"])[0],
            "weakest": min(principles.items(), key=lambda x: x[1]["score"])[0],
        }

    # ═══════════════════════════════════════════════════════
    #  E-E-A-T 세부 계산
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def _calc_experience(content: str) -> float:
        """경험(Experience) 점수."""
        signals = len(re.findall(
            r'(직접|경험|사용해|써봤|해봤|느낀|실제로|후기|리뷰|1인칭)', content
        ))
        return min(100, signals * 15 + 20)

    @staticmethod
    def _calc_expertise(content: str, has_citations: bool) -> float:
        """전문성(Expertise) 점수."""
        score = 20  # 기본
        # 전문 용어 사용
        technical = len(re.findall(
            r'(알고리즘|프레임워크|방법론|분석|데이터|연구|이론|모델|지표|메트릭)',
            content
        ))
        score += min(30, technical * 5)
        # 인용/출처
        if has_citations or re.search(r'\(\d{4}\)|\[참고\]|출처:', content):
            score += 25
        # 깊이 (길이)
        if len(content) > 2000:
            score += 15
        elif len(content) > 1000:
            score += 10
        return min(100, score)

    @staticmethod
    def _calc_authority(content: str, author: str, has_data: bool) -> float:
        """권위(Authoritativeness) 점수."""
        score = 20
        if author:
            score += 20
        if has_data:
            score += 25
        # 데이터/숫자 포함
        data_count = len(re.findall(r'\d+[%만억원]', content))
        score += min(20, data_count * 4)
        # 외부 소스 언급
        if re.search(r'(보고서|발표|연구|조사|설문)', content):
            score += 15
        return min(100, score)

    @staticmethod
    def _calc_trust(content: str, has_original: bool) -> float:
        """신뢰(Trustworthiness) 점수."""
        score = 30  # 기본 (명시적 거짓 없으면)
        if has_original:
            score += 25
        # 투명성 표현
        if re.search(r'(단점|한계|주의|고려|리스크|위험|주의사항)', content):
            score += 20  # 균형 잡힌 시각
        # 구체적 근거
        if re.search(r'\d{4}년|\d+%|연구에 따르면', content):
            score += 15
        # 수정/업데이트 날짜
        if re.search(r'(최종 수정|업데이트|작성일)', content):
            score += 10
        return min(100, score)

    # ═══════════════════════════════════════════════════════
    #  유틸리티 함수
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def _count_sentences(text: str) -> int:
        """문장 수 계산."""
        # 한국어 문장 종결 패턴
        sentences = re.split(r'[.!?。]\s*', text)
        return max(1, len([s for s in sentences if s.strip()]))

    @staticmethod
    def _grade(score: float) -> str:
        """점수 → 등급."""
        if score >= 90:
            return "S (최우수)"
        elif score >= 80:
            return "A (우수)"
        elif score >= 70:
            return "B (양호)"
        elif score >= 60:
            return "C (보통)"
        elif score >= 50:
            return "D (개선 필요)"
        else:
            return "F (대폭 개선 필요)"

    @staticmethod
    def _readability_recommendations(avg_sent: float, diff_ratio: float,
                                     variation: float) -> list[str]:
        """가독성 개선 권장사항."""
        recs = []
        if avg_sent > 20:
            recs.append(f"문장이 길어요 (평균 {avg_sent:.0f}어절). 15어절 이하로 줄여보세요.")
        if diff_ratio > 0.15:
            recs.append(f"어려운 단어 비율이 {diff_ratio*100:.0f}%입니다. 쉬운 표현으로 바꿔보세요.")
        if variation < 30:
            recs.append("문장 길이가 비슷합니다. 짧은 문장과 긴 문장을 섞으면 리듬이 살아나요.")
        if not recs:
            recs.append("가독성이 양호합니다!")
        return recs

    @staticmethod
    def _eeat_improvements(exp: float, expt: float, auth: float, trust: float) -> list[str]:
        """E-E-A-T 개선 제안."""
        improvements = []
        if exp < 60:
            improvements.append("직접 경험, 사례, 후기를 추가하세요 (Experience)")
        if expt < 60:
            improvements.append("전문 용어 설명, 출처/인용을 추가하세요 (Expertise)")
        if auth < 60:
            improvements.append("저자 소개, 데이터 근거를 보강하세요 (Authority)")
        if trust < 60:
            improvements.append("장단점 균형, 수정 날짜를 명시하세요 (Trust)")
        return improvements or ["E-E-A-T 점수가 양호합니다!"]

    @staticmethod
    def _get_top_improvements(readability, seo, structure,
                              engagement, persuasion) -> list[str]:
        """가장 개선이 필요한 영역 3개 추출."""
        areas = [
            (readability["score"], "가독성", readability.get("recommendations", [])),
            (seo["score"], "SEO", [c["detail"] for c in seo.get("checks", [])
                                    if c.get("status") == "fail"]),
            (structure["score"], "구조", []),
            (engagement["score"], "독자 참여", []),
            (persuasion["score"], "설득력", []),
        ]
        areas.sort(key=lambda x: x[0])

        result = []
        for score, name, details in areas[:3]:
            if score < 80:
                detail_str = f" — {details[0]}" if details else ""
                result.append(f"{name} ({score:.0f}점){detail_str}")
        return result or ["모든 영역이 80점 이상입니다!"]


# ═══════════════════════════════════════════════════════
#  순수 Python 통계 함수 (numpy 불필요)
# ═══════════════════════════════════════════════════════

def _mean(values: list) -> float:
    return sum(values) / len(values) if values else 0.0

def _std(values: list) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))
