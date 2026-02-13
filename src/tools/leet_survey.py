"""
LEET 해설 부정의견 서베이 Tool.

leet-opinion-scraper를 에이전트가 호출하여 6개 커뮤니티에서
LEET 해설 관련 부정적 의견을 자동 수집·분석합니다.

사용 방법 (에이전트가 호출):
  - action="survey": 커뮤니티에서 의견 수집 + LLM 분석
    - keywords: 에이전트가 직접 검색 키워드를 지정 (쉼표 구분 문자열 또는 리스트)
    - topic: 키워드 대신 주제만 주면 LLM이 자동으로 키워드를 생성
    - (둘 다 없으면 config.py의 기본 키워드 사용)
  - action="status": 마지막 수집 결과 요약 조회
  - action="results": 기존 수집 결과 파일 기반 재분석

필요 환경변수 (플랫폼별):
  - KAKAO_ID / KAKAO_PW: 다음 카페 (카카오 로그인)
  - NAVER_ID / NAVER_PW: 네이버 카페 (네이버 로그인)
  - ORBI_ID / ORBI_PW: 오르비 (선택)
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from glob import glob
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.leet_survey")

# leet-opinion-scraper 프로젝트 루트
SCRAPER_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "leet-opinion-scraper",
)
OUTPUT_DIR = os.path.join(SCRAPER_DIR, "output")


class LeetSurveyTool(BaseTool):
    """LEET 해설 부정의견 멀티플랫폼 서베이 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "survey")

        if action == "survey":
            return await self._run_survey(kwargs)
        elif action == "status":
            return await self._get_status()
        elif action == "results":
            return await self._analyze_results(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능: survey(수집), status(현황), results(기존결과 분석)"
            )

    # ── 서베이 실행 ──

    async def _resolve_keywords(self, kwargs: dict[str, Any]) -> str | None:
        """에이전트가 준 keywords/topic으로부터 검색 키워드 문자열을 결정.

        - keywords가 있으면 그대로 사용
        - topic만 있으면 LLM이 키워드를 자동 생성
        - 둘 다 없으면 None (= config.py 기본값 사용)
        """
        # 1) 에이전트가 직접 키워드를 지정한 경우
        keywords = kwargs.get("keywords")
        if keywords:
            if isinstance(keywords, list):
                return ",".join(keywords)
            return str(keywords)

        # 2) 주제(topic)만 준 경우 → LLM이 키워드 생성
        topic = kwargs.get("topic")
        if topic:
            generated = await self._llm_call(
                system_prompt=(
                    "당신은 한국 온라인 커뮤니티 검색 전문가입니다.\n"
                    "주어진 조사 주제에 대해 한국 커뮤니티(다음카페, 네이버, 오르비, 디시인사이드 등)에서\n"
                    "실제로 사람들이 쓸 법한 검색 키워드를 생성하세요.\n\n"
                    "규칙:\n"
                    "- 15~25개 키워드를 생성\n"
                    "- 줄바꿈 없이 쉼표로 구분\n"
                    "- 구어체, 줄임말, 커뮤니티 은어도 포함\n"
                    "- 긍정/부정/질문형 다양하게\n"
                    "- LEET/리트/로스쿨 관련이면 해당 용어 포함\n"
                    "- 키워드만 출력하고 다른 설명은 하지 마세요"
                ),
                user_prompt=f"조사 주제: {topic}",
            )
            # LLM 응답을 정리
            cleaned = generated.strip().strip('"').strip("'")
            logger.info("[LeetSurvey] LLM 생성 키워드: %s", cleaned[:200])
            return cleaned

        # 3) 둘 다 없으면 기본값
        return None

    async def _run_survey(self, kwargs: dict[str, Any]) -> str:
        """leet-opinion-scraper를 subprocess로 실행하여 수집."""
        platforms = kwargs.get("platforms", "all")
        max_pages = kwargs.get("max_pages", 3)
        keywords_only = kwargs.get("keywords_only", True)

        # 스크래퍼 존재 확인
        main_py = os.path.join(SCRAPER_DIR, "main.py")
        if not os.path.exists(main_py):
            return (
                "leet-opinion-scraper가 설치되지 않았습니다.\n"
                f"경로: {main_py}"
            )

        # 키워드 결정 (에이전트 지정 > LLM 생성 > config 기본값)
        custom_keywords = await self._resolve_keywords(kwargs)

        # 명령어 구성
        cmd = [
            sys.executable, main_py,
            "--platforms", str(platforms),
            "--max-pages", str(max_pages),
            "--headless",
            "--output-dir", OUTPUT_DIR,
        ]
        if custom_keywords:
            cmd.extend(["--keywords", custom_keywords])
        if keywords_only:
            cmd.append("--keywords-only")

        platform_label = platforms if platforms != "all" else "6개 전체 플랫폼"
        keyword_label = f"커스텀 {len(custom_keywords.split(','))}개" if custom_keywords else "기본 키워드"
        logger.info("[LeetSurvey] 수집 시작: %s, 키워드: %s (max_pages=%d)",
                     platform_label, keyword_label, max_pages)

        try:
            result = subprocess.run(
                cmd,
                cwd=SCRAPER_DIR,
                capture_output=True,
                text=True,
                timeout=600,  # 10분 타임아웃
            )
        except subprocess.TimeoutExpired:
            return (
                "서베이 수집이 10분 시간제한을 초과했습니다.\n"
                "플랫폼 수를 줄이거나 max_pages를 낮춰서 재시도하세요.\n"
                f"예: action=survey, platforms=dcinside,orbi, max_pages=2"
            )
        except Exception as e:
            logger.error("[LeetSurvey] 실행 실패: %s", e)
            return f"스크래퍼 실행 실패: {e}"

        # 결과 파일 찾기
        json_files = sorted(
            glob(os.path.join(OUTPUT_DIR, "results_*.json")),
            key=os.path.getmtime,
            reverse=True,
        )

        if not json_files:
            # 중간결과 확인
            intermediate = sorted(
                glob(os.path.join(OUTPUT_DIR, "intermediate_*.json")),
                key=os.path.getmtime,
                reverse=True,
            )
            if intermediate:
                return await self._analyze_json_file(intermediate[0], platforms)

            stderr_tail = result.stderr[-1000:] if result.stderr else "(없음)"
            stdout_tail = result.stdout[-1000:] if result.stdout else "(없음)"
            return (
                "수집은 완료되었으나 결과 파일이 생성되지 않았습니다.\n\n"
                f"**stdout (마지막 1000자)**:\n```\n{stdout_tail}\n```\n\n"
                f"**stderr (마지막 1000자)**:\n```\n{stderr_tail}\n```"
            )

        return await self._analyze_json_file(json_files[0], platforms)

    # ── 결과 분석 ──

    async def _analyze_json_file(self, json_path: str, platforms: str) -> str:
        """JSON 결과 파일을 읽어 LLM으로 분석."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return f"결과 파일 읽기 실패: {e}"

        # 결과 파일이 리스트인 경우 (intermediate) vs 딕셔너리 (full results)
        if isinstance(data, list):
            posts = data
            summary_section = f"총 {len(posts)}건 수집"
        else:
            posts = data.get("posts", [])
            summary = data.get("summary", {})
            summary_section = (
                f"총 수집: {summary.get('total_collected', 0)}건\n"
                f"부정 의견: {summary.get('total_negative', 0)}건\n"
                f"플랫폼별: {json.dumps(summary.get('by_platform', {}), ensure_ascii=False)}\n"
                f"키워드별 상위: {json.dumps(dict(list(summary.get('by_keyword', {}).items())[:10]), ensure_ascii=False)}"
            )

        # 부정 의견 게시글만 추출
        negative_posts = [p for p in posts if p.get("is_negative")]
        if not negative_posts:
            negative_posts = posts[:20]

        # LLM 분석용 데이터 준비 (최대 30건)
        sample = negative_posts[:30]
        posts_text = "\n\n".join(
            f"[{i}] 제목: {p.get('title', '')}\n"
            f"    플랫폼: {p.get('platform', '')}\n"
            f"    날짜: {p.get('date', '')}\n"
            f"    조회: {p.get('view_count', 0)}\n"
            f"    매칭된 부정 표현: {', '.join(p.get('matched_negative', []))}\n"
            f"    본문 미리보기: {p.get('preview', '')[:200]}\n"
            f"    URL: {p.get('url', '')}"
            for i, p in enumerate(sample, 1)
        )

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 LEET(법학적성시험) 시장조사 분석가입니다.\n"
                "커뮤니티에서 수집된 LEET 해설서(해설집)에 대한 부정적 의견을 분석하세요.\n\n"
                "다음 항목을 정리하세요:\n"
                "1. **핵심 불만 유형 분류**: 해설 불일치, 해설 오류, 해설 부실, 납득 불가, 강사 비판, 공식해설 불만 등\n"
                "2. **주요 불만 트렌드**: 가장 많이 언급되는 불만과 그 빈도\n"
                "3. **플랫폼별 특성**: 각 커뮤니티별 의견 성향 차이\n"
                "4. **사업 기회 분석**: 이 불만들에서 도출할 수 있는 사업/제품 기회\n"
                "5. **경쟁사 언급 분석**: 메가, 피트, 진학사 등 어떤 출판사/학원이 언급되는지\n"
                "6. **실행 가능한 인사이트**: LEET Master 서비스 개선에 활용할 수 있는 구체적 제안\n\n"
                "수치와 구체적 게시글을 인용하여 근거를 제시하세요."
            ),
            user_prompt=(
                f"## 수집 요약\n{summary_section}\n\n"
                f"## 부정 의견 게시글 ({len(sample)}건 샘플)\n\n{posts_text}"
            ),
        )

        return (
            f"## LEET 해설 부정의견 서베이 결과\n\n"
            f"**수집 현황**: {summary_section}\n"
            f"**부정 의견 총 건수**: {len(negative_posts)}건\n"
            f"**결과 파일**: {json_path}\n\n"
            f"---\n\n"
            f"## 분석 리포트\n\n{analysis}"
        )

    # ── 기존 결과 분석 ──

    async def _analyze_results(self, kwargs: dict[str, Any]) -> str:
        """기존 수집 결과 파일 기반 재분석."""
        file_path = kwargs.get("file", "")

        if file_path and os.path.exists(file_path):
            return await self._analyze_json_file(file_path, "지정 파일")

        # 파일 미지정 시 최신 결과 사용
        json_files = sorted(
            glob(os.path.join(OUTPUT_DIR, "results_*.json")),
            key=os.path.getmtime,
            reverse=True,
        )
        if not json_files:
            return (
                "분석할 결과 파일이 없습니다.\n"
                "먼저 action=survey로 수집을 실행하세요."
            )

        return await self._analyze_json_file(json_files[0], "최신 결과")

    # ── 현황 조회 ──

    async def _get_status(self) -> str:
        """마지막 수집 결과 요약."""
        json_files = sorted(
            glob(os.path.join(OUTPUT_DIR, "results_*.json")),
            key=os.path.getmtime,
            reverse=True,
        )
        intermediate_files = sorted(
            glob(os.path.join(OUTPUT_DIR, "intermediate_*.json")),
            key=os.path.getmtime,
            reverse=True,
        )

        if not json_files and not intermediate_files:
            return (
                "아직 수집된 결과가 없습니다.\n\n"
                "**사용법**:\n"
                "- `action=survey`: 전체 플랫폼 수집\n"
                "- `action=survey, platforms=dcinside,orbi`: 특정 플랫폼만\n"
                "- `action=survey, max_pages=2, keywords_only=true`: 빠른 수집"
            )

        lines = ["## LEET 서베이 현황\n"]

        if json_files:
            latest = json_files[0]
            try:
                with open(latest, "r", encoding="utf-8") as f:
                    data = json.load(f)
                summary = data.get("summary", {})
                settings = data.get("settings", {})
                lines.append(f"**최신 결과**: {os.path.basename(latest)}")
                lines.append(f"- 수집 시각: {data.get('collection_datetime', '?')}")
                lines.append(f"- 플랫폼: {', '.join(settings.get('platforms', []))}")
                lines.append(f"- 총 수집: {summary.get('total_collected', 0)}건")
                lines.append(f"- 부정 의견: {summary.get('total_negative', 0)}건")
                by_plat = summary.get("by_platform", {})
                for plat, info in by_plat.items():
                    lines.append(f"  - {plat}: {info.get('collected', 0)}건 (부정 {info.get('negative', 0)}건)")
            except Exception:
                lines.append(f"**최신 결과**: {os.path.basename(latest)} (파싱 실패)")

        lines.append(f"\n**전체 결과 파일**: {len(json_files)}개")
        lines.append(f"**중간 결과 파일**: {len(intermediate_files)}개")

        return "\n".join(lines)
