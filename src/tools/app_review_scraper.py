"""
앱스토어 리뷰 수집기 Tool.

구글 플레이스토어에서 앱 리뷰를 대량 수집하고,
별점 분포, 키워드 빈도, 시간별 추이 등을 분석합니다.

사용 방법:
  - action="reviews": 앱 리뷰 수집
  - action="analyze": 수집된 리뷰 분석
  - action="compare": 두 앱 리뷰 비교

필요 환경변수: 없음
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.app_review_scraper")


def _import_google_play_scraper():
    """google-play-scraper 라이브러리 임포트."""
    try:
        from google_play_scraper import reviews as gp_reviews, Sort
        return gp_reviews, Sort
    except ImportError:
        return None, None


class AppReviewScraperTool(BaseTool):
    """구글 플레이스토어 앱 리뷰 수집 및 분석 도구."""

    _INSTALL_MSG = (
        "google-play-scraper 라이브러리가 설치되지 않았습니다.\n"
        "다음 명령어로 설치하세요:\n"
        "```\npip install google-play-scraper\n```"
    )

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "reviews")

        if action == "reviews":
            return await self._get_reviews(kwargs)
        elif action == "analyze":
            return await self._analyze_reviews(kwargs)
        elif action == "compare":
            return await self._compare_apps(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "reviews, analyze, compare 중 하나를 사용하세요."
            )

    # ── 리뷰 수집 ──

    async def _get_reviews(self, kwargs: dict[str, Any]) -> str:
        gp_reviews, Sort = _import_google_play_scraper()
        if gp_reviews is None:
            return self._INSTALL_MSG

        app_id = kwargs.get("app_id", "").strip()
        if not app_id:
            return "앱 ID(app_id)를 입력해주세요. 예: app_id='com.megastudy.leet'"

        count = min(int(kwargs.get("count", 100)), 500)
        lang = kwargs.get("lang", "ko")
        sort_type = kwargs.get("sort", "newest")

        sort_map = {
            "newest": Sort.NEWEST,
            "rating": Sort.MOST_RELEVANT,
            "relevance": Sort.MOST_RELEVANT,
        }
        sort_val = sort_map.get(sort_type, Sort.NEWEST)

        try:
            result, _ = gp_reviews(
                app_id,
                lang=lang,
                country="kr",
                sort=sort_val,
                count=count,
            )
        except Exception as e:
            logger.error("리뷰 수집 실패: %s — %s", app_id, e)
            return f"리뷰 수집 실패: {e}\n앱 ID가 올바른지 확인해주세요."

        if not result:
            return f"'{app_id}' 앱의 리뷰를 찾을 수 없습니다."

        # 리뷰 데이터 정리
        reviews_data = []
        for r in result:
            reviews_data.append({
                "score": r.get("score", 0),
                "content": r.get("content", "")[:300],
                "date": str(r.get("at", ""))[:10],
                "thumbs_up": r.get("thumbsUpCount", 0),
                "version": r.get("reviewCreatedVersion", ""),
            })

        # 별점 분포
        scores = [r["score"] for r in reviews_data]
        dist = Counter(scores)
        total = len(scores)
        avg_score = sum(scores) / total if total else 0

        dist_text = "\n".join(
            f"  {star}점: {dist.get(star, 0)}건 ({dist.get(star, 0) / total * 100:.1f}%)"
            for star in range(5, 0, -1)
        )

        # 상위 리뷰 표시
        top_reviews = sorted(reviews_data, key=lambda x: x["thumbs_up"], reverse=True)[:10]
        review_lines = []
        for i, r in enumerate(top_reviews, 1):
            review_lines.append(
                f"[{i}] ★{r['score']} | 좋아요 {r['thumbs_up']}개 | {r['date']}\n"
                f"    {r['content']}"
            )

        report = (
            f"## 앱 리뷰 수집 결과\n\n"
            f"- **앱 ID**: {app_id}\n"
            f"- **수집 건수**: {total}건\n"
            f"- **평균 별점**: {avg_score:.1f}점\n\n"
            f"### 별점 분포\n{dist_text}\n\n"
            f"### 인기 리뷰 (좋아요순 상위 10개)\n\n"
            + "\n\n".join(review_lines)
        )

        return report

    # ── 리뷰 분석 ──

    async def _analyze_reviews(self, kwargs: dict[str, Any]) -> str:
        gp_reviews, Sort = _import_google_play_scraper()
        if gp_reviews is None:
            return self._INSTALL_MSG

        app_id = kwargs.get("app_id", "").strip()
        if not app_id:
            return "앱 ID(app_id)를 입력해주세요."

        count = min(int(kwargs.get("count", 200)), 500)

        try:
            result, _ = gp_reviews(
                app_id,
                lang="ko",
                country="kr",
                sort=Sort.NEWEST,
                count=count,
            )
        except Exception as e:
            return f"리뷰 수집 실패: {e}"

        if not result:
            return f"'{app_id}' 앱의 리뷰를 찾을 수 없습니다."

        # 별점 분포
        scores = [r.get("score", 0) for r in result]
        total = len(scores)
        avg = sum(scores) / total if total else 0
        dist = Counter(scores)

        # 긍정/부정 분류
        positive = [r for r in result if r.get("score", 0) >= 4]
        negative = [r for r in result if r.get("score", 0) <= 2]

        # 텍스트 합치기 (분석용)
        all_text = "\n---\n".join(
            f"★{r.get('score', 0)}: {r.get('content', '')[:200]}"
            for r in result[:100]
        )

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 앱 리뷰 분석 전문가입니다.\n"
                "구글 플레이 앱 리뷰를 분석하여 다음을 정리하세요:\n"
                "1. 핵심 불만 사항 TOP 5 (구체적으로)\n"
                "2. 칭찬 포인트 TOP 3\n"
                "3. 개선 우선순위 (시급한 순서대로)\n"
                "4. 경쟁사 대비 차별화 포인트 (리뷰에서 추출)\n"
                "5. 사업 관점에서의 시사점\n"
                "한국어로 간결하게 보고하세요."
            ),
            user_prompt=(
                f"앱 ID: {app_id}\n"
                f"총 리뷰: {total}건, 평균 별점: {avg:.1f}\n"
                f"긍정(4~5점): {len(positive)}건, 부정(1~2점): {len(negative)}건\n\n"
                f"리뷰 샘플:\n{all_text}"
            ),
        )

        dist_text = "\n".join(
            f"  {star}점: {dist.get(star, 0)}건 ({dist.get(star, 0) / total * 100:.1f}%)"
            for star in range(5, 0, -1)
        )

        return (
            f"## 앱 리뷰 분석 보고서\n\n"
            f"- **앱 ID**: {app_id}\n"
            f"- **분석 대상**: {total}건\n"
            f"- **평균 별점**: {avg:.1f}점\n"
            f"- **긍정 리뷰** (4~5점): {len(positive)}건\n"
            f"- **부정 리뷰** (1~2점): {len(negative)}건\n\n"
            f"### 별점 분포\n{dist_text}\n\n"
            f"---\n\n### 분석\n\n{analysis}"
        )

    # ── 두 앱 비교 ──

    async def _compare_apps(self, kwargs: dict[str, Any]) -> str:
        gp_reviews, Sort = _import_google_play_scraper()
        if gp_reviews is None:
            return self._INSTALL_MSG

        app_ids_raw = kwargs.get("app_ids", "").strip()
        if not app_ids_raw:
            return "비교할 앱 ID를 쉼표로 구분해 입력하세요. 예: app_ids='com.app1,com.app2'"

        app_ids = [aid.strip() for aid in app_ids_raw.split(",") if aid.strip()]
        if len(app_ids) < 2:
            return "비교하려면 최소 2개 앱 ID가 필요합니다."

        comparisons = []
        for app_id in app_ids[:3]:  # 최대 3개
            try:
                result, _ = gp_reviews(
                    app_id,
                    lang="ko",
                    country="kr",
                    sort=Sort.NEWEST,
                    count=100,
                )
                scores = [r.get("score", 0) for r in result]
                avg = sum(scores) / len(scores) if scores else 0
                dist = Counter(scores)
                sample = "\n".join(
                    f"★{r.get('score', 0)}: {r.get('content', '')[:150]}"
                    for r in result[:20]
                )
                comparisons.append(
                    f"**{app_id}** — 평균 {avg:.1f}점, {len(scores)}건\n"
                    f"  5점: {dist.get(5, 0)}건 | 4점: {dist.get(4, 0)}건 | "
                    f"3점: {dist.get(3, 0)}건 | 2점: {dist.get(2, 0)}건 | 1점: {dist.get(1, 0)}건\n\n"
                    f"리뷰 샘플:\n{sample}"
                )
            except Exception as e:
                comparisons.append(f"**{app_id}** — 수집 실패: {e}")

        compare_text = "\n\n---\n\n".join(comparisons)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 앱 비교 분석 전문가입니다.\n"
                "여러 앱의 리뷰를 비교 분석하여 다음을 정리하세요:\n"
                "1. 각 앱의 강점/약점 비교 표\n"
                "2. 사용자가 선호하는 앱과 그 이유\n"
                "3. 각 앱의 개선 기회\n"
                "4. 사업 전략 시사점\n"
                "한국어로 보고하세요."
            ),
            user_prompt=compare_text,
        )

        return (
            f"## 앱 리뷰 비교 분석\n\n{compare_text}\n\n"
            f"---\n\n### 비교 분석\n\n{analysis}"
        )
