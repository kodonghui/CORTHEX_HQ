"""해시태그 추천기 — SNS 게시물에 효과적인 해시태그를 자동 추천하는 도구.

게시물 주제, 플랫폼에 맞춰 대형/중형/소형 해시태그를 최적 조합하여
노출 효과를 극대화하는 해시태그 세트를 생성합니다.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.hashtag_recommender")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

# ─── 분야별 해시태그 데이터베이스 ───
HASHTAG_DB: dict[str, dict[str, list[str]]] = {
    "교육": {
        "대형": [
            "#공부", "#공부그램", "#공스타그램", "#합격", "#수험생",
            "#공부자극", "#열공", "#시험", "#자격증", "#대학",
        ],
        "중형": [
            "#법학", "#로스쿨", "#LEET", "#법대", "#사법시험",
            "#변호사시험", "#법학전문대학원", "#LEET준비", "#법학공부", "#로스쿨입시",
            "#법시", "#법조인", "#리트", "#법학과", "#법대생",
        ],
        "소형": [
            "#리트공부", "#LEET준비", "#로스쿨준비", "#법학적성시험",
            "#LEET공부법", "#리트기출", "#LEET독학", "#리트언어이해",
            "#리트추리논증", "#로스쿨면접",
        ],
    },
    "금융": {
        "대형": [
            "#주식", "#투자", "#재테크", "#부동산", "#경제",
            "#주식투자", "#금융", "#돈", "#부업", "#자산관리",
        ],
        "중형": [
            "#주식공부", "#ETF", "#배당주", "#미국주식", "#코인",
            "#부동산투자", "#아파트", "#경제공부", "#재무설계", "#펀드",
            "#주식초보", "#가치투자", "#종목추천", "#차트분석", "#금융투자",
        ],
        "소형": [
            "#주린이", "#주식일기", "#매매일지", "#배당금", "#적립식",
            "#ETF투자", "#S&P500", "#해외주식", "#퀀트투자", "#가계부",
        ],
    },
    "기술": {
        "대형": [
            "#IT", "#개발자", "#프로그래밍", "#코딩", "#AI",
            "#개발", "#기술", "#스타트업", "#앱", "#소프트웨어",
        ],
        "중형": [
            "#인공지능", "#머신러닝", "#파이썬", "#ChatGPT", "#딥러닝",
            "#웹개발", "#앱개발", "#데이터분석", "#클라우드", "#자동화",
            "#GPT", "#LLM", "#개발일지", "#사이드프로젝트", "#테크",
        ],
        "소형": [
            "#AI에이전트", "#RAG", "#벡터DB", "#프롬프트엔지니어링", "#LangChain",
            "#FastAPI", "#NextJS", "#리액트", "#타입스크립트", "#MLOps",
        ],
    },
    "라이프스타일": {
        "대형": [
            "#일상", "#데일리", "#소통", "#맞팔", "#좋아요",
            "#인스타그램", "#팔로우", "#일상그램", "#소통해요", "#선팔",
        ],
        "중형": [
            "#자기계발", "#독서", "#운동", "#다이어트", "#건강",
            "#미라클모닝", "#습관", "#목표", "#동기부여", "#성장",
            "#자기관리", "#루틴", "#생산성", "#독서그램", "#운동그램",
        ],
        "소형": [
            "#갓생살기", "#갓생", "#하루루틴", "#아침루틴", "#생산성도구",
            "#노션", "#플래너", "#타임블로킹", "#습관추적", "#감사일기",
        ],
    },
}

# ─── 플랫폼별 해시태그 권장 사항 ───
PLATFORM_RULES: dict[str, dict[str, Any]] = {
    "instagram": {
        "max_tags": 30,
        "optimal_tags": (20, 30),
        "대형_ratio": 0.1,
        "중형_ratio": 0.6,
        "소형_ratio": 0.3,
        "tip": "인스타그램은 최대 30개 해시태그 사용 가능. 중형 해시태그 위주가 최적.",
    },
    "youtube": {
        "max_tags": 15,
        "optimal_tags": (5, 15),
        "대형_ratio": 0.2,
        "중형_ratio": 0.5,
        "소형_ratio": 0.3,
        "tip": "유튜브는 태그보다 제목/설명의 키워드가 더 중요. 핵심 태그만 선별.",
    },
    "tiktok": {
        "max_tags": 10,
        "optimal_tags": (3, 8),
        "대형_ratio": 0.3,
        "중형_ratio": 0.5,
        "소형_ratio": 0.2,
        "tip": "틱톡은 3~5개의 핵심 해시태그가 가장 효과적. 트렌딩 태그 포함 권장.",
    },
}


class HashtagRecommenderTool(BaseTool):
    """SNS 게시물에 효과적인 해시태그를 자동 추천하는 도구."""

    async def execute(self, **kwargs: Any) -> str:
        """
        해시태그 추천 도구 실행.

        kwargs:
          - action: "recommend" | "analyze" | "trending"
          - topic: 게시물 주제
          - platform: "instagram" | "youtube" | "tiktok"
          - count: 추천 개수 (기본: 30)
          - hashtags: 분석할 해시태그 (쉼표 구분)
          - category: 인기 해시태그 카테고리
        """
        action = kwargs.get("action", "recommend")

        if action == "recommend":
            return await self._recommend(kwargs)
        elif action == "analyze":
            return await self._analyze(kwargs)
        elif action == "trending":
            return await self._trending(kwargs)
        else:
            return f"알 수 없는 action: {action}\n사용 가능: recommend, analyze, trending"

    # ──────────────────────────────────────
    #  내부: 카테고리 매칭
    # ──────────────────────────────────────

    def _find_category(self, topic: str) -> str:
        """주제에서 가장 적합한 카테고리를 찾습니다."""
        topic_lower = topic.lower()
        category_keywords = {
            "교육": ["LEET", "리트", "로스쿨", "법학", "공부", "시험", "수험", "대학", "학원",
                    "합격", "교육", "강의", "학습", "자격증", "입시"],
            "금융": ["주식", "투자", "재테크", "부동산", "코인", "펀드", "보험", "금융",
                    "경제", "은행", "대출", "배당"],
            "기술": ["AI", "개발", "코딩", "프로그래밍", "IT", "앱", "소프트웨어",
                    "인공지능", "스타트업", "기술", "데이터", "클라우드"],
            "라이프스타일": ["일상", "운동", "다이어트", "건강", "독서", "여행",
                         "음식", "카페", "취미", "라이프"],
        }

        best_match = "라이프스타일"  # 기본
        best_score = 0

        for category, keywords in category_keywords.items():
            score = sum(1 for kw in keywords if kw.lower() in topic_lower)
            if score > best_score:
                best_score = score
                best_match = category

        return best_match

    def _generate_topic_hashtags(self, topic: str) -> list[str]:
        """주제에서 커스텀 해시태그를 생성합니다."""
        # 주제 단어를 분리하여 해시태그 변형 생성
        words = re.split(r"[\s,./]+", topic)
        tags = []

        for word in words:
            if word:
                tags.append(f"#{word}")

        # 복합 해시태그 생성
        if len(words) >= 2:
            tags.append(f"#{''.join(words[:2])}")  # 첫 두 단어 합치기
            tags.append(f"#{words[0]}팁")
            tags.append(f"#{words[0]}공부")

        return tags

    # ──────────────────────────────────────
    #  내부: 인스타그램 게시물 수 조회
    # ──────────────────────────────────────

    async def _fetch_instagram_tag_count(self, tag: str) -> int | None:
        """인스타그램 해시태그의 게시물 수를 조회합니다.

        차단 방지를 위해 요청 간 딜레이를 둡니다.
        조회 실패 시 None을 반환합니다.
        """
        clean_tag = tag.lstrip("#")
        url = f"https://www.instagram.com/explore/tags/{clean_tag}/"

        try:
            await asyncio.sleep(2.5)  # 차단 방지 딜레이
            async with httpx.AsyncClient(
                headers=_HEADERS, follow_redirects=True, timeout=10.0
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
                # 게시물 수 추출 시도
                text = resp.text
                match = re.search(r'"edge_hashtag_to_media":\{"count":(\d+)', text)
                if match:
                    return int(match.group(1))
                # 대안 패턴
                match = re.search(r'"count":(\d+)', text)
                if match:
                    return int(match.group(1))
        except Exception as e:
            logger.debug("[hashtag_recommender] 인스타그램 조회 실패 (%s): %s", tag, e)
        return None

    # ──────────────────────────────────────
    #  action: recommend
    # ──────────────────────────────────────

    async def _recommend(self, kwargs: dict[str, Any]) -> str:
        """해시태그를 추천합니다."""
        topic = kwargs.get("topic", "")
        if not topic:
            return "topic 파라미터를 입력해주세요. 예: topic='LEET 공부법'"

        platform = kwargs.get("platform", "instagram")
        count = int(kwargs.get("count", 30))

        logger.info("[hashtag_recommender] recommend: topic=%s, platform=%s", topic, platform)

        # 플랫폼 규칙
        rules = PLATFORM_RULES.get(platform, PLATFORM_RULES["instagram"])
        max_tags = min(count, rules["max_tags"])

        # 1단계: 카테고리 매칭
        category = self._find_category(topic)

        # 2단계: 해시태그 풀 구성
        db_tags = HASHTAG_DB.get(category, HASHTAG_DB["라이프스타일"])
        topic_tags = self._generate_topic_hashtags(topic)

        # 3단계: 대형/중형/소형 비율에 따라 조합
        n_large = max(2, round(max_tags * rules["대형_ratio"]))
        n_medium = max(5, round(max_tags * rules["중형_ratio"]))
        n_small = max(3, round(max_tags * rules["소형_ratio"]))

        selected: list[str] = []

        # 대형 해시태그
        for tag in db_tags.get("대형", [])[:n_large]:
            if tag not in selected:
                selected.append(tag)

        # 중형 해시태그
        for tag in db_tags.get("중형", [])[:n_medium]:
            if tag not in selected:
                selected.append(tag)

        # 소형 해시태그
        for tag in db_tags.get("소형", [])[:n_small]:
            if tag not in selected:
                selected.append(tag)

        # 주제 기반 커스텀 해시태그 추가
        for tag in topic_tags:
            if tag not in selected and len(selected) < max_tags:
                selected.append(tag)

        selected = selected[:max_tags]

        # 포맷팅
        lines = [
            f"## 해시태그 추천: '{topic}'",
            f"- 플랫폼: {platform}",
            f"- 카테고리: {category}",
            f"- 추천 개수: {len(selected)}개",
            "",
            "### 추천 해시태그 세트",
            "",
            " ".join(selected),
            "",
            "### 카테고리별 분류",
            "",
        ]

        # 대형/중형/소형 분류
        large = [t for t in selected if t in db_tags.get("대형", [])]
        medium = [t for t in selected if t in db_tags.get("중형", [])]
        small = [t for t in selected if t in db_tags.get("소형", [])]
        custom = [t for t in selected if t not in large and t not in medium and t not in small]

        if large:
            lines.append(f"**대형** (노출 높음, 경쟁 치열): {' '.join(large)}")
        if medium:
            lines.append(f"**중형** (최적 노출 영역): {' '.join(medium)}")
        if small:
            lines.append(f"**소형** (타겟 정확): {' '.join(small)}")
        if custom:
            lines.append(f"**주제 맞춤**: {' '.join(custom)}")

        lines.extend([
            "",
            f"### 플랫폼 팁",
            f"{rules['tip']}",
        ])

        result_text = "\n".join(lines)

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 SNS 마케팅 전문가입니다. 아래 해시태그 추천 결과를 분석하여:\n"
                "1. 이 조합이 효과적인 이유\n"
                "2. 게시 시간 추천 (플랫폼별 최적 시간대)\n"
                "3. 추가로 고려할 해시태그 3~5개\n"
                "4. 주의할 점 (금지된 해시태그, 스팸 방지 등)\n"
                "를 한국어로 작성하세요."
            ),
            user_prompt=result_text,
        )

        return f"{result_text}\n\n---\n\n### AI 해시태그 전략\n\n{analysis}"

    # ──────────────────────────────────────
    #  action: analyze
    # ──────────────────────────────────────

    async def _analyze(self, kwargs: dict[str, Any]) -> str:
        """특정 해시태그의 인기도를 분석합니다."""
        hashtags_str = kwargs.get("hashtags", "")
        if not hashtags_str:
            return "hashtags 파라미터를 입력해주세요. 예: hashtags='#LEET,#로스쿨,#법학'"

        hashtags = [h.strip() for h in hashtags_str.split(",") if h.strip()]
        logger.info("[hashtag_recommender] analyze: %s", hashtags)

        lines = [
            "## 해시태그 인기도 분석",
            "",
            "| 해시태그 | 게시물 수 | 규모 | 경쟁도 |",
            "|----------|-----------|------|--------|",
        ]

        for tag in hashtags:
            count = await self._fetch_instagram_tag_count(tag)
            if count is not None:
                if count >= 1_000_000:
                    size = "대형"
                    competition = "높음"
                elif count >= 10_000:
                    size = "중형"
                    competition = "보통"
                else:
                    size = "소형"
                    competition = "낮음"
                lines.append(f"| {tag} | {count:,} | {size} | {competition} |")
            else:
                lines.append(f"| {tag} | 조회 불가 | - | - |")

        result_text = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 해시태그 분석 전문가입니다. 위 데이터를 기반으로:\n"
                "1. 각 해시태그의 효용성 평가\n"
                "2. 이 해시태그들을 함께 사용할 때의 전략\n"
                "3. 대체하면 좋을 해시태그 추천\n"
                "을 한국어로 작성하세요."
            ),
            user_prompt=result_text,
        )

        return f"{result_text}\n\n---\n\n### AI 분석\n\n{analysis}"

    # ──────────────────────────────────────
    #  action: trending
    # ──────────────────────────────────────

    async def _trending(self, kwargs: dict[str, Any]) -> str:
        """현재 인기 해시태그를 카테고리별로 보여줍니다."""
        category = kwargs.get("category", "")

        if category and category in HASHTAG_DB:
            categories = {category: HASHTAG_DB[category]}
        else:
            categories = HASHTAG_DB

        lines = ["## 인기 해시태그 목록", ""]

        for cat_name, tags in categories.items():
            lines.append(f"### {cat_name}")
            lines.append("")
            for size, tag_list in tags.items():
                lines.append(f"**{size}:**")
                lines.append(f"  {' '.join(tag_list)}")
            lines.append("")

        result_text = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 SNS 트렌드 전문가입니다. 위 해시태그 목록을 보고:\n"
                "1. 현재 가장 성장 중인 해시태그 트렌드 3가지\n"
                "2. 각 카테고리에서 가장 효과적인 조합\n"
                "3. 새로 떠오르고 있는 해시태그 추천\n"
                "을 한국어로 작성하세요."
            ),
            user_prompt=result_text,
        )

        return f"{result_text}\n---\n\n### AI 트렌드 분석\n\n{analysis}"
