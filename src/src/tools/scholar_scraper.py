"""
학술 논문 검색기 Tool.

Google Scholar에서 논문을 검색하고 트렌드를 분석하여
사업에 활용할 수 있는 학술 근거를 제공합니다.

사용 방법:
  - action="search": 논문 검색
  - action="cite": 특정 논문의 인용 정보
  - action="trend": 분야별 논문 발표 추이

필요 환경변수: 없음
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.scholar_scraper")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _import_scholarly():
    """scholarly 라이브러리 임포트."""
    try:
        from scholarly import scholarly
        return scholarly
    except ImportError:
        return None


class ScholarScraperTool(BaseTool):
    """Google Scholar 논문 검색 및 트렌드 분석 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "search")

        if action == "search":
            return await self._search_papers(kwargs)
        elif action == "cite":
            return await self._get_citation(kwargs)
        elif action == "trend":
            return await self._analyze_trend(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "search, cite, trend 중 하나를 사용하세요."
            )

    # ── 논문 검색 ──

    async def _search_papers(self, kwargs: dict[str, Any]) -> str:
        query = kwargs.get("query", "").strip()
        if not query:
            return "검색 키워드(query)를 입력해주세요. 예: query='법학적성시험 예측타당도'"

        count = min(int(kwargs.get("count", 20)), 50)
        year_from = kwargs.get("year_from", "")
        sort_by = kwargs.get("sort_by", "relevance")

        # scholarly 라이브러리 시도
        scholarly = _import_scholarly()
        if scholarly is not None:
            return await self._search_with_scholarly(scholarly, query, count, year_from, sort_by)

        # fallback: httpx로 Google Scholar 직접 크롤링
        return await self._search_with_httpx(query, count, year_from, sort_by)

    async def _search_with_scholarly(self, scholarly, query: str, count: int,
                                      year_from: str, sort_by: str) -> str:
        try:
            if year_from:
                search_query = scholarly.search_pubs(
                    query, year_low=int(year_from),
                    sort_by="date" if sort_by == "date" else "relevance",
                )
            else:
                search_query = scholarly.search_pubs(query)

            results = []
            for i in range(count):
                await asyncio.sleep(1)  # 요청 간 딜레이 (차단 방지)
                try:
                    paper = next(search_query)
                    bib = paper.get("bib", {})
                    results.append({
                        "title": bib.get("title", ""),
                        "author": ", ".join(bib.get("author", []))[:100],
                        "year": bib.get("pub_year", ""),
                        "abstract": bib.get("abstract", "")[:300],
                        "citations": paper.get("num_citations", 0),
                        "url": paper.get("pub_url", paper.get("eprint_url", "")),
                    })
                except StopIteration:
                    break

            if not results:
                return f"'{query}' 관련 논문을 찾을 수 없습니다."

            return self._format_search_results(query, results)

        except Exception as e:
            logger.warning("scholarly 검색 실패, fallback 사용: %s", e)
            return await self._search_with_httpx(query, count, year_from, sort_by)

    async def _search_with_httpx(self, query: str, count: int,
                                  year_from: str, sort_by: str) -> str:
        """Google Scholar를 직접 크롤링하여 논문 검색 (fallback)."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return (
                "scholarly 또는 beautifulsoup4 라이브러리가 필요합니다.\n"
                "다음 중 하나를 설치하세요:\n"
                "```\npip install scholarly\n```\n"
                "또는\n"
                "```\npip install beautifulsoup4\n```"
            )

        params = {"q": query, "hl": "ko", "num": str(min(count, 20))}
        if year_from:
            params["as_ylo"] = str(year_from)
        if sort_by == "date":
            params["scisbd"] = "1"

        results = []
        page = 0

        while len(results) < count and page < 3:
            if page > 0:
                params["start"] = str(page * 10)
                await asyncio.sleep(2)  # 차단 방지 딜레이

            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp = await client.get(
                        "https://scholar.google.com/scholar",
                        params=params,
                        headers={"User-Agent": USER_AGENT},
                        timeout=15,
                    )
            except httpx.HTTPError as e:
                logger.error("Google Scholar 접근 실패: %s", e)
                break

            if resp.status_code == 429:
                logger.warning("Google Scholar 요청 제한 (429)")
                break

            if resp.status_code != 200:
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            entries = soup.select(".gs_r.gs_or.gs_scl")

            if not entries:
                break

            for entry in entries:
                title_el = entry.select_one(".gs_rt a")
                if not title_el:
                    title_el = entry.select_one(".gs_rt")

                title = title_el.get_text(strip=True) if title_el else ""
                url = title_el.get("href", "") if title_el and title_el.name == "a" else ""

                # 저자/연도/저널
                meta_el = entry.select_one(".gs_a")
                meta_text = meta_el.get_text(strip=True) if meta_el else ""

                # 초록
                abstract_el = entry.select_one(".gs_rs")
                abstract = abstract_el.get_text(strip=True) if abstract_el else ""

                # 인용 수
                cite_el = entry.select_one(".gs_fl a")
                citations = 0
                if cite_el:
                    cite_match = re.search(r"(\d+)", cite_el.get_text())
                    if cite_match:
                        citations = int(cite_match.group(1))

                # 연도 추출
                year_match = re.search(r"(\d{4})", meta_text)
                year = year_match.group(1) if year_match else ""

                results.append({
                    "title": title,
                    "author": meta_text[:100],
                    "year": year,
                    "abstract": abstract[:300],
                    "citations": citations,
                    "url": url,
                })

            page += 1

        if not results:
            return (
                f"'{query}' 관련 논문을 찾을 수 없습니다.\n"
                "Google Scholar의 요청 제한일 수 있습니다. 잠시 후 다시 시도하세요."
            )

        return self._format_search_results(query, results[:count])

    def _format_search_results(self, query: str, results: list[dict]) -> str:
        """검색 결과를 보고서 형태로 포맷팅."""
        lines = []
        for i, r in enumerate(results, 1):
            cite_str = f"인용 {r['citations']}회" if r["citations"] else "인용 정보 없음"
            lines.append(
                f"**{i}. {r['title']}**\n"
                f"   저자: {r['author']}\n"
                f"   연도: {r['year']} | {cite_str}\n"
                f"   초록: {r['abstract']}\n"
                f"   링크: {r['url']}"
            )

        report = (
            f"## 학술 논문 검색 결과: '{query}'\n\n"
            f"총 {len(results)}건\n\n"
            + "\n\n".join(lines)
        )

        return report

    # ── 인용 정보 ──

    async def _get_citation(self, kwargs: dict[str, Any]) -> str:
        title = kwargs.get("title", "").strip()
        if not title:
            return "논문 제목(title)을 입력해주세요."

        # 논문 검색 후 인용 정보 추출
        scholarly = _import_scholarly()
        if scholarly is not None:
            try:
                await asyncio.sleep(1)
                search = scholarly.search_pubs(title)
                paper = next(search)
                bib = paper.get("bib", {})

                return (
                    f"## 논문 인용 정보\n\n"
                    f"- **제목**: {bib.get('title', '')}\n"
                    f"- **저자**: {', '.join(bib.get('author', []))}\n"
                    f"- **연도**: {bib.get('pub_year', '')}\n"
                    f"- **저널**: {bib.get('venue', bib.get('journal', ''))}\n"
                    f"- **인용 횟수**: {paper.get('num_citations', 0)}회\n"
                    f"- **초록**: {bib.get('abstract', '')[:500]}\n"
                    f"- **URL**: {paper.get('pub_url', '')}"
                )
            except StopIteration:
                return f"'{title}' 논문을 찾을 수 없습니다."
            except Exception as e:
                logger.warning("scholarly 인용 조회 실패: %s", e)

        # fallback: 검색으로 대체
        return await self._search_papers({"query": title, "count": 5})

    # ── 트렌드 분석 ──

    async def _analyze_trend(self, kwargs: dict[str, Any]) -> str:
        query = kwargs.get("query", "").strip()
        if not query:
            return "키워드(query)를 입력해주세요. 예: query='LEET 법학적성시험'"

        years = int(kwargs.get("years", 10))

        from datetime import datetime
        current_year = datetime.now().year
        start_year = current_year - years

        # 연도별 검색
        yearly_counts = {}
        scholarly = _import_scholarly()

        if scholarly is not None:
            for year in range(start_year, current_year + 1):
                await asyncio.sleep(1.5)  # 차단 방지
                try:
                    search = scholarly.search_pubs(query, year_low=year, year_high=year)
                    count = 0
                    for _ in range(100):  # 최대 100건까지 카운트
                        try:
                            next(search)
                            count += 1
                        except StopIteration:
                            break
                    yearly_counts[year] = count
                except Exception:
                    yearly_counts[year] = 0
        else:
            # fallback: httpx 크롤링
            try:
                from bs4 import BeautifulSoup
            except ImportError:
                return (
                    "scholarly 또는 beautifulsoup4 라이브러리가 필요합니다.\n"
                    "```\npip install scholarly\n```"
                )

            for year in range(start_year, current_year + 1):
                await asyncio.sleep(2)  # 차단 방지
                try:
                    async with httpx.AsyncClient(follow_redirects=True) as client:
                        resp = await client.get(
                            "https://scholar.google.com/scholar",
                            params={
                                "q": query,
                                "as_ylo": str(year),
                                "as_yhi": str(year),
                                "hl": "ko",
                            },
                            headers={"User-Agent": USER_AGENT},
                            timeout=15,
                        )
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        result_stats = soup.select_one("#gs_ab_md")
                        if result_stats:
                            num_match = re.search(r"약 ([\d,]+)개", result_stats.get_text())
                            if not num_match:
                                num_match = re.search(r"([\d,]+)", result_stats.get_text())
                            yearly_counts[year] = int(num_match.group(1).replace(",", "")) if num_match else 0
                        else:
                            entries = soup.select(".gs_r.gs_or.gs_scl")
                            yearly_counts[year] = len(entries)
                    elif resp.status_code == 429:
                        logger.warning("Google Scholar 요청 제한, 트렌드 분석 중단")
                        break
                except Exception:
                    yearly_counts[year] = 0

        if not yearly_counts:
            return "트렌드 데이터를 수집할 수 없습니다. 잠시 후 다시 시도하세요."

        # 트렌드 차트 (텍스트 기반)
        max_count = max(yearly_counts.values()) if yearly_counts.values() else 1
        chart_lines = []
        for year in sorted(yearly_counts.keys()):
            cnt = yearly_counts[year]
            bar_len = int(cnt / max(max_count, 1) * 30) if max_count > 0 else 0
            bar = "█" * bar_len
            chart_lines.append(f"  {year}: {bar} ({cnt}건)")

        chart = "\n".join(chart_lines)

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 학술 트렌드 분석 전문가입니다.\n"
                "연도별 논문 발표 추이 데이터를 분석하여 다음을 정리하세요:\n"
                "1. 전체 추세 (증가/감소/유지)\n"
                "2. 특이 시점 (급증/급감 구간)과 가능한 원인\n"
                "3. 현재 연구 활성도 평가\n"
                "4. 사업에 활용 가능한 학술 근거 및 시사점\n"
                "한국어로 보고하세요."
            ),
            user_prompt=(
                f"키워드: '{query}'\n"
                f"기간: {start_year}~{current_year}\n\n"
                f"연도별 논문 수:\n{chart}"
            ),
        )

        return (
            f"## 학술 논문 트렌드 분석: '{query}'\n\n"
            f"기간: {start_year}~{current_year} ({years}년간)\n\n"
            f"### 연도별 논문 발표 추이\n```\n{chart}\n```\n\n"
            f"---\n\n### 분석\n\n{analysis}"
        )
