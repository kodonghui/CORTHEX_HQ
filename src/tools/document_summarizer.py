"""
문서 요약 도구 (Document Summarizer) — 장문 문서를 핵심 요약하고, 실행 항목을 추출합니다.

긴 문서를 체계적으로 분석하여 "이 문서에서 뭘 해야 하는지"를
추출적·생성적 방법으로 정리합니다.

학술 근거:
  - TextRank (Mihalcea & Tarau, 2004) "TextRank: Bringing Order into Texts"
    → 그래프 기반 추출적 요약, PageRank 알고리즘의 NLP 적용
  - ROUGE Metric (Lin, 2004) "ROUGE: A Package for Automatic Evaluation of Summaries"
    → 요약 품질 평가 표준 지표 (Recall-Oriented Understudy for Gisting Evaluation)
  - Luhn (1958) "The Automatic Creation of Literature Abstracts"
    → TF 기반 문장 중요도 산정, NLP 원전
  - Barbara Minto (1987) "The Pyramid Principle"
    → 구조적 사고와 커뮤니케이션 프레임워크 (핵심 → 근거 → 상세)
  - Bloom's Taxonomy (1956, Anderson & Krathwohl 2001 개정판)
    → 지식 수준별 요약 깊이 조절

사용 방법:
  - action="extract"       : 핵심 문장 추출 (TextRank 간소화)
  - action="pyramid"       : Minto 피라미드 요약 (3층 구조)
  - action="action_items"  : 실행 항목 추출 (우선순위 정렬)
  - action="compare"       : 다중 문서 비교 요약
  - action="readability"   : 가독성 분석 (Flesch 변형 + 한국어 적합)
  - action="full"          : 위 5개 종합 분석

필요 환경변수: 없음
필요 라이브러리: 없음 (순수 Python)
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.document_summarizer")


# ═══════════════════════════════════════════════════════
#  유틸리티 함수
# ═══════════════════════════════════════════════════════

def _mean(vals: list) -> float:
    """리스트의 평균을 반환합니다. 빈 리스트이면 0.0."""
    return sum(vals) / len(vals) if vals else 0.0


def _split_sentences(text: str) -> list[str]:
    """텍스트를 문장 단위로 분리합니다.
    한국어(다/요/까 등) + 영어(. ! ?) + 줄바꿈 기준으로 분리합니다.
    """
    # 한국어 문장 종결 + 영어 문장 부호 + 줄바꿈 기반 분리
    raw = re.split(r'(?<=[.!?。\n])\s+|(?<=[다요까죠음됨임함])\.\s*|(?<=[다요까죠음됨임함])\s+(?=[A-Z가-힣])', text)
    sentences = []
    for s in raw:
        s = s.strip()
        if len(s) > 5:  # 너무 짧은 조각 제외
            sentences.append(s)
    return sentences


def _tokenize_words(sentence: str) -> list[str]:
    """문장에서 단어를 추출합니다 (한국어 + 영어 모두 지원)."""
    # 한국어: 음절 2개 이상, 영어: 알파벳 2개 이상
    words = re.findall(r'[가-힣]{2,}|[a-zA-Z]{2,}', sentence.lower())
    return words


def _count_syllables_ko(text: str) -> int:
    """한국어 텍스트의 음절 수를 반환합니다 (글자 수 기반 근사)."""
    return len(re.findall(r'[가-힣]', text))


def _count_syllables_en(word: str) -> int:
    """영어 단어의 음절 수를 추정합니다 (Flesch 방식 근사)."""
    word = word.lower().strip()
    if len(word) <= 3:
        return 1
    # 모음 그룹 카운트
    count = len(re.findall(r'[aeiouy]+', word))
    # 끝 e 제거 보정
    if word.endswith('e') and count > 1:
        count -= 1
    return max(1, count)


# ═══════════════════════════════════════════════════════
#  상수 데이터
# ═══════════════════════════════════════════════════════

# 가독성 등급 기준 (avg_sentence_length 기반 — 한국어 적합 조정)
READABILITY_GRADES = [
    (10, "매우 쉬움", "초등학생도 이해 가능 — 대중 홍보물에 적합"),
    (20, "쉬움",     "일반인 이해 가능 — 뉴스, 공지사항에 적합"),
    (30, "보통",     "대학생 수준 — 보고서, 제안서에 적합"),
    (40, "어려움",   "전문가 수준 — 학술 논문, 법률 문서 수준"),
    (999, "매우 어려움", "극도로 복잡 — 가독성 개선 강력 권장"),
]

# 한국어 불용어 (TextRank 유사도 계산 시 제외)
STOPWORDS_KO = {
    "이", "그", "저", "것", "수", "등", "및", "또는", "그리고", "하지만",
    "이것", "그것", "때문", "위해", "통해", "대한", "에서", "으로", "에게",
    "까지", "부터", "보다", "처럼", "만큼", "같은", "있는", "하는", "되는",
    "있다", "하다", "되다", "없다", "않다", "이다", "아니다",
}


# ═══════════════════════════════════════════════════════
#  DocumentSummarizerTool
# ═══════════════════════════════════════════════════════

class DocumentSummarizerTool(BaseTool):
    """교수급 문서 요약 도구 — TextRank 추출 + Minto 피라미드 + 실행 항목 + 비교 + 가독성."""

    # ── 메인 디스패처 ────────────────────────

    async def execute(self, **kwargs: Any) -> dict:
        action = kwargs.get("action", "full")

        actions = {
            "full":         self._full_analysis,
            "extract":      self._textrank_extract,
            "pyramid":      self._pyramid_summary,
            "action_items": self._action_items,
            "compare":      self._compare_documents,
            "readability":  self._readability_analysis,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)

        return {
            "status": "error",
            "message": (
                f"알 수 없는 action: {action}. "
                "extract, pyramid, action_items, compare, readability, full 중 하나를 사용하세요."
            ),
        }

    # ═══════════════════════════════════════════════════
    #  1) TextRank 핵심 문장 추출
    # ═══════════════════════════════════════════════════

    async def _textrank_extract(self, params: dict) -> dict:
        """Mihalcea & Tarau (2004) TextRank 간소화 — 핵심 문장을 추출합니다."""
        text = params.get("text", "")
        if not text or len(text.strip()) < 20:
            return {"status": "error", "message": "text가 필요합니다 (최소 20자 이상)."}

        num_sentences = int(params.get("num_sentences", 5))
        sentences = _split_sentences(text)

        if len(sentences) <= num_sentences:
            return {"status": "success", "analysis": "extract",
                    "extracted_sentences": sentences,
                    "note": "원문 문장 수가 요청 수 이하로, 전체를 반환합니다."}

        # 문장별 단어 집합 (불용어 제거)
        sent_words = []
        for s in sentences:
            words = set(_tokenize_words(s)) - STOPWORDS_KO
            sent_words.append(words)

        # ─── TF-IDF 가중치 계산 (Luhn, 1958 기반 확장) ───
        n = len(sentences)

        # 각 문장별 단어 빈도 (TF 계산용, 불용어 제거 후)
        sent_word_lists = []
        for s in sentences:
            wl = [w for w in _tokenize_words(s) if w not in STOPWORDS_KO]
            sent_word_lists.append(wl)

        # DF: 각 단어가 등장하는 문장 수
        doc_freq: dict[str, int] = {}
        for words_set in sent_words:
            for w in words_set:
                doc_freq[w] = doc_freq.get(w, 0) + 1

        # 문장별 TF-IDF 벡터 (word → tfidf score)
        sent_tfidf: list[dict[str, float]] = []
        for wl in sent_word_lists:
            tfidf_vec: dict[str, float] = {}
            total_w = len(wl) if wl else 1
            # 단어 빈도 계산
            wf: dict[str, int] = {}
            for w in wl:
                wf[w] = wf.get(w, 0) + 1
            for w, cnt in wf.items():
                tf = cnt / total_w
                idf = math.log(n / (1 + doc_freq.get(w, 0)))
                tfidf_vec[w] = tf * idf
            sent_tfidf.append(tfidf_vec)

        # 문장 간 TF-IDF 가중 유사도 행렬 (Mihalcea 확장)
        similarity_matrix = [[0.0] * n for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                if not sent_words[i] or not sent_words[j]:
                    continue
                # TF-IDF 가중 Jaccard: Σ(tfidf of common words) / (log|s_i| + log|s_j|)
                common = sent_words[i] & sent_words[j]
                if not common:
                    continue
                # 공통 단어의 TF-IDF 합산 (양쪽 문장의 평균)
                tfidf_sum = sum(
                    (sent_tfidf[i].get(w, 0) + sent_tfidf[j].get(w, 0)) / 2
                    for w in common
                )
                len_i = len(sent_words[i])
                len_j = len(sent_words[j])
                denominator = math.log(max(len_i, 1) + 1) + math.log(max(len_j, 1) + 1)
                if denominator > 0:
                    sim = tfidf_sum / denominator
                else:
                    sim = 0.0
                similarity_matrix[i][j] = sim
                similarity_matrix[j][i] = sim

        # PageRank 스타일 점수 계산 (반복 수렴)
        damping = 0.85
        scores = [1.0 / n] * n
        max_iterations = 50
        convergence_threshold = 1e-6

        for iteration in range(max_iterations):
            new_scores = [0.0] * n
            for i in range(n):
                rank_sum = 0.0
                for j in range(n):
                    if i == j:
                        continue
                    # j에서 나가는 총 유사도
                    out_sum = sum(similarity_matrix[j])
                    if out_sum > 0:
                        rank_sum += (similarity_matrix[j][i] / out_sum) * scores[j]
                new_scores[i] = (1 - damping) / n + damping * rank_sum

            # 수렴 체크
            delta = sum(abs(new_scores[i] - scores[i]) for i in range(n))
            scores = new_scores
            if delta < convergence_threshold:
                logger.debug("TextRank converged at iteration %d", iteration + 1)
                break

        # 상위 N문장 추출 (원문 순서 유지)
        indexed_scores = sorted(enumerate(scores), key=lambda x: -x[1])
        top_indices = sorted([idx for idx, _ in indexed_scores[:num_sentences]])
        extracted = [{"index": idx, "sentence": sentences[idx],
                      "score": round(scores[idx], 6)} for idx in top_indices]

        return {"status": "success", "analysis": "extract",
                "total_sentences": n, "extracted_count": len(extracted),
                "extracted_sentences": extracted,
                "convergence_iterations": min(iteration + 1, max_iterations)}

    # ═══════════════════════════════════════════════════
    #  2) Minto 피라미드 요약
    # ═══════════════════════════════════════════════════

    async def _pyramid_summary(self, params: dict) -> dict:
        """Barbara Minto (1987) Pyramid Principle — 3층 구조로 요약합니다."""
        text = params.get("text", "")
        context = params.get("context", "")

        if not text or len(text.strip()) < 20:
            return {"status": "error", "message": "text가 필요합니다 (최소 20자 이상)."}

        context_instruction = f"\n문서 맥락: {context}" if context else ""

        # 임원용 브리핑
        executive_llm = await self._llm_call(
            "당신은 Barbara Minto의 피라미드 원칙(Pyramid Principle) 전문가입니다.\n"
            "문서를 3층 피라미드 구조로 요약합니다.\n"
            "반드시 한국어로 작성하세요.",
            f"아래 문서를 Minto 피라미드 구조로 요약해주세요.{context_instruction}\n\n"
            f"문서 내용:\n{text[:4000]}\n\n"
            f"다음 3층 구조로 정리해주세요:\n"
            f"[Level 1 - 핵심 메시지] 이 문서가 말하고 싶은 것 1문장\n"
            f"[Level 2 - 핵심 근거] 핵심 메시지를 뒷받침하는 3~5개 포인트\n"
            f"[Level 3 - 상세 데이터] 각 포인트를 뒷받침하는 구체적 사실/수치\n\n"
            f"이 버전은 '임원 브리핑용'입니다. 간결하고 결론 중심으로 작성하세요."
        )

        # 실무자용 상세 요약
        detailed_llm = await self._llm_call(
            "당신은 Barbara Minto의 피라미드 원칙(Pyramid Principle) 전문가입니다.\n"
            "문서를 실무자가 즉시 활용할 수 있도록 상세히 요약합니다.\n"
            "반드시 한국어로 작성하세요.",
            f"아래 문서를 실무자용으로 상세 요약해주세요.{context_instruction}\n\n"
            f"문서 내용:\n{text[:4000]}\n\n"
            f"다음을 포함해주세요:\n"
            f"1. 핵심 메시지 (1문장)\n"
            f"2. 주요 논점별 상세 설명 (각 200자 이내)\n"
            f"3. 배경 정보 및 전제 조건\n"
            f"4. 관련 데이터/수치 정리\n"
            f"5. 추가 조사/확인이 필요한 사항"
        )

        word_count = len(_tokenize_words(text))
        sentence_count = len(_split_sentences(text))

        return {"status": "success", "analysis": "pyramid",
                "document_stats": {"word_count": word_count, "sentence_count": sentence_count,
                                   "char_count": len(text)},
                "executive_summary": executive_llm,
                "detailed_summary": detailed_llm}

    # ═══════════════════════════════════════════════════
    #  3) 실행 항목 추출
    # ═══════════════════════════════════════════════════

    async def _action_items(self, params: dict) -> dict:
        """문서에서 실행 항목(Action Items)을 추출합니다."""
        text = params.get("text", "")
        if not text or len(text.strip()) < 20:
            return {"status": "error", "message": "text가 필요합니다 (최소 20자 이상)."}

        llm = await self._llm_call(
            "당신은 프로젝트 관리 전문가입니다. 문서에서 실행 항목을 추출합니다.\n"
            "반드시 한국어로 작성하세요.\n"
            "반드시 아래 JSON 배열 형식으로만 응답하세요 (다른 텍스트 없이):\n"
            '[{"action": "할 일", "responsible": "담당자 또는 미정", '
            '"deadline": "추정 기한 또는 미정", "priority": "high/medium/low"}]',
            f"아래 문서에서 실행 항목(Action Items)을 모두 추출해주세요.\n"
            f"각 항목에는 구체적인 행동, 담당자(추정), 기한(추정), 우선순위를 포함하세요.\n"
            f"우선순위 기준:\n"
            f"- high: 즉시 실행 필요, 지연 시 리스크\n"
            f"- medium: 이번 주/스프린트 내 실행\n"
            f"- low: 시간 여유 있음, 개선 사항\n\n"
            f"문서:\n{text[:4000]}"
        )

        # LLM 응답에서 JSON 파싱 시도
        import json
        action_items = []
        try:
            # JSON 배열 추출 (응답에 다른 텍스트가 있을 수 있음)
            json_match = re.search(r'\[.*\]', llm, re.DOTALL)
            if json_match:
                action_items = json.loads(json_match.group())
        except (json.JSONDecodeError, AttributeError):
            logger.warning("Action items JSON 파싱 실패, 원문 반환")

        # 우선순위순 정렬
        priority_order = {"high": 0, "medium": 1, "low": 2}
        if action_items:
            action_items.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 3))

        return {"status": "success", "analysis": "action_items",
                "action_items": action_items,
                "total_items": len(action_items),
                "priority_breakdown": {
                    "high": len([a for a in action_items if a.get("priority") == "high"]),
                    "medium": len([a for a in action_items if a.get("priority") == "medium"]),
                    "low": len([a for a in action_items if a.get("priority") == "low"]),
                },
                "llm_raw": llm}

    # ═══════════════════════════════════════════════════
    #  4) 다중 문서 비교 요약
    # ═══════════════════════════════════════════════════

    async def _compare_documents(self, params: dict) -> dict:
        """다중 문서의 핵심을 비교·요약하고, 공통점/차이점/충돌을 식별합니다."""
        documents = params.get("documents", [])
        if not documents or len(documents) < 2:
            return {"status": "error", "message": "documents 리스트가 필요합니다 (최소 2개). "
                    "형식: [{title, text}, {title, text}]"}

        # 각 문서 기본 통계
        doc_stats = []
        doc_summaries_text = []
        for i, doc in enumerate(documents):
            title = doc.get("title", f"문서 {i+1}")
            text = doc.get("text", "")
            sentences = _split_sentences(text)
            words = _tokenize_words(text)
            doc_stats.append({
                "title": title,
                "char_count": len(text),
                "word_count": len(words),
                "sentence_count": len(sentences),
            })
            # 비교용 요약 텍스트 구성 (각 문서 앞 2000자)
            doc_summaries_text.append(f"[{title}]\n{text[:2000]}")

        combined_text = "\n\n---\n\n".join(doc_summaries_text)

        llm = await self._llm_call(
            "당신은 문서 비교 분석 전문가입니다.\n"
            "여러 문서를 비교하여 공통점, 차이점, 충돌 내용을 식별합니다.\n"
            "반드시 한국어로 작성하세요.",
            f"아래 {len(documents)}개 문서를 비교 분석해주세요.\n\n"
            f"{combined_text}\n\n"
            f"다음 구조로 정리해주세요:\n"
            f"1. 각 문서 핵심 요약 (문서당 2~3문장)\n"
            f"2. 공통점 (모든 문서가 동의하는 내용)\n"
            f"3. 차이점 (문서 간 다른 관점/결론)\n"
            f"4. 충돌 내용 (서로 모순되는 주장 — 없으면 '없음')\n"
            f"5. 종합 판단 (어떤 문서가 더 신뢰할 수 있는지, 추가 확인 필요 사항)"
        )

        return {"status": "success", "analysis": "compare",
                "document_count": len(documents),
                "document_stats": doc_stats,
                "llm_comparison": llm}

    # ═══════════════════════════════════════════════════
    #  5) 가독성 분석
    # ═══════════════════════════════════════════════════

    async def _readability_analysis(self, params: dict) -> dict:
        """Flesch 변형 + 한국어 적합 가독성 분석 — 등급과 개선점을 제시합니다."""
        text = params.get("text", "")
        if not text or len(text.strip()) < 20:
            return {"status": "error", "message": "text가 필요합니다 (최소 20자 이상)."}

        sentences = _split_sentences(text)
        words = _tokenize_words(text)
        total_chars = len(text)
        total_sentences = len(sentences) or 1
        total_words = len(words) or 1

        # 기본 통계
        avg_sentence_length = round(total_words / total_sentences, 2)
        avg_word_length = round(total_chars / total_words, 2)

        # 한국어 음절 수
        ko_syllables = _count_syllables_ko(text)
        # 영어 음절 수 (영어 단어만)
        en_words = re.findall(r'[a-zA-Z]+', text)
        en_syllables = sum(_count_syllables_en(w) for w in en_words) if en_words else 0
        total_syllables = ko_syllables + en_syllables
        avg_syllables_per_word = round(total_syllables / total_words, 2) if total_words else 0

        # 복잡도 점수 (문장 길이 기반 — 한국어 적합)
        complexity_score = round(avg_sentence_length, 1)

        # 등급 판정
        grade = "매우 어려움"
        grade_desc = ""
        for threshold, g, desc in READABILITY_GRADES:
            if complexity_score <= threshold:
                grade = g
                grade_desc = desc
                break

        # 긴 문장 식별 (30단어 초과)
        long_sentences = []
        for i, s in enumerate(sentences):
            wc = len(_tokenize_words(s))
            if wc > 30:
                long_sentences.append({
                    "index": i,
                    "word_count": wc,
                    "preview": s[:80] + ("..." if len(s) > 80 else ""),
                })

        # 전문용어 밀도 추정 (4음절 이상 한자어/외래어 비율)
        complex_words = [w for w in words if len(w) >= 4]
        jargon_density = round(len(complex_words) / total_words * 100, 1) if total_words else 0

        # LLM으로 개선 추천
        llm = await self._llm_call(
            "당신은 문서 가독성 개선 전문 에디터입니다.\n"
            "한국어 문서의 가독성을 분석하고 구체적인 개선 방안을 제시합니다.\n"
            "반드시 한국어로 작성하세요.",
            f"아래 문서의 가독성 분석 결과입니다. 개선 방안을 구체적으로 제시해주세요.\n\n"
            f"통계:\n"
            f"- 총 문장: {total_sentences}개, 총 단어: {total_words}개\n"
            f"- 평균 문장 길이: {avg_sentence_length} 단어/문장\n"
            f"- 복잡도 등급: {grade} ({grade_desc})\n"
            f"- 전문용어 밀도: {jargon_density}%\n"
            f"- 30단어 초과 긴 문장: {len(long_sentences)}개\n\n"
            f"문서 앞부분 (1000자):\n{text[:1000]}\n\n"
            f"다음을 포함해주세요:\n"
            f"1. 긴 문장 분리 방안 (구체적 예시)\n"
            f"2. 전문용어 대체어 제안\n"
            f"3. 문단 구조 개선\n"
            f"4. 전체 가독성 향상을 위한 3가지 핵심 권고"
        )

        return {
            "status": "success",
            "analysis": "readability",
            "statistics": {
                "total_chars": total_chars,
                "total_words": total_words,
                "total_sentences": total_sentences,
                "avg_sentence_length": avg_sentence_length,
                "avg_word_length": avg_word_length,
                "avg_syllables_per_word": avg_syllables_per_word,
                "jargon_density_percent": jargon_density,
            },
            "complexity_score": complexity_score,
            "grade": grade,
            "grade_description": grade_desc,
            "long_sentences": long_sentences,
            "long_sentence_count": len(long_sentences),
            "llm_improvement_suggestions": llm,
        }

    # ═══════════════════════════════════════════════════
    #  6) 종합 분석 (Full)
    # ═══════════════════════════════════════════════════

    async def _full_analysis(self, params: dict) -> dict:
        """5가지 분석을 모두 수행하고 종합 보고서를 생성합니다."""
        text = params.get("text", "")
        documents = params.get("documents", [])

        if not text and not documents:
            return {"status": "error", "message": "text 또는 documents가 필요합니다."}

        # text가 없으면 첫 문서 사용
        if not text and documents:
            text = documents[0].get("text", "")
            params = {**params, "text": text}

        results = {}

        # 1) TextRank 추출
        try:
            results["extract"] = await self._textrank_extract({**params, "action": "extract"})
        except Exception as e:
            logger.warning("Full analysis — extract 실패: %s", e)
            results["extract"] = {"status": "skipped", "reason": str(e)}

        # 2) Minto 피라미드
        try:
            results["pyramid"] = await self._pyramid_summary({**params, "action": "pyramid"})
        except Exception as e:
            logger.warning("Full analysis — pyramid 실패: %s", e)
            results["pyramid"] = {"status": "skipped", "reason": str(e)}

        # 3) 실행 항목
        try:
            results["action_items"] = await self._action_items({**params, "action": "action_items"})
        except Exception as e:
            logger.warning("Full analysis — action_items 실패: %s", e)
            results["action_items"] = {"status": "skipped", "reason": str(e)}

        # 4) 문서 비교 (documents가 2개 이상일 때만)
        if documents and len(documents) >= 2:
            try:
                results["compare"] = await self._compare_documents({**params, "action": "compare"})
            except Exception as e:
                logger.warning("Full analysis — compare 실패: %s", e)
                results["compare"] = {"status": "skipped", "reason": str(e)}
        else:
            results["compare"] = {"status": "skipped", "reason": "비교할 문서가 2개 미만"}

        # 5) 가독성
        try:
            results["readability"] = await self._readability_analysis({**params, "action": "readability"})
        except Exception as e:
            logger.warning("Full analysis — readability 실패: %s", e)
            results["readability"] = {"status": "skipped", "reason": str(e)}

        # 종합 요약 LLM
        summary_parts = []
        if results.get("pyramid", {}).get("status") == "success":
            summary_parts.append(f"[피라미드 요약]\n{results['pyramid'].get('executive_summary', '')[:500]}")
        if results.get("action_items", {}).get("status") == "success":
            items = results["action_items"].get("action_items", [])
            high_items = [a for a in items if a.get("priority") == "high"]
            summary_parts.append(f"[실행 항목] 총 {len(items)}건 (긴급 {len(high_items)}건)")
        if results.get("readability", {}).get("status") == "success":
            grade = results["readability"].get("grade", "")
            summary_parts.append(f"[가독성] 등급: {grade}")

        llm = await self._llm_call(
            "당신은 문서 분석 전문 컨설턴트입니다.\n"
            "여러 분석 결과를 종합하여 경영진 브리핑용 1페이지 요약을 작성합니다.\n"
            "한국어로, 구조적으로 정리하세요.",
            f"아래 문서 분석 결과를 종합하여 1페이지 브리핑을 작성해주세요.\n\n"
            + "\n\n".join(summary_parts) + "\n\n"
            f"포함 사항:\n"
            f"1. 핵심 메시지 (3줄 이내)\n"
            f"2. 즉시 실행 사항\n"
            f"3. 문서 품질 평가\n"
            f"4. 추가 필요 사항"
        )

        return {"status": "success", "analysis": "full",
                "results": results, "llm_summary": llm}
