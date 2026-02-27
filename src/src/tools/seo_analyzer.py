"""SEO 분석기 — 웹사이트의 검색엔진 최적화(SEO) 상태를 자동 점검하는 도구.

웹페이지의 HTML을 분석하여 메타 태그, 콘텐츠 품질, 기술 요소, 성능 등
14개 항목을 100점 만점으로 점수를 매기고, 개선 방법을 제시합니다.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.seo_analyzer")

# ─── 브라우저처럼 보이기 위한 헤더 ───
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

# ─── SEO 점검 항목 (총 100점) ───
SEO_CHECKS: dict[str, dict[str, Any]] = {
    # ── 기본 메타 (30점) ──
    "title_tag": {
        "weight": 10,
        "check": "title 태그 존재 여부 + 길이(30~60자 적정)",
        "deduction": "없으면 -10, 너무 짧거나 길면 -5",
    },
    "meta_description": {
        "weight": 10,
        "check": "meta description 존재 여부 + 길이(120~160자 적정)",
    },
    "h1_tag": {
        "weight": 5,
        "check": "h1 태그 존재 여부 + 유일성(1개만 있어야 함)",
    },
    "heading_structure": {
        "weight": 5,
        "check": "h1→h2→h3 순서 올바른지 (건너뛰기 없는지)",
    },
    # ── 콘텐츠 (25점) ──
    "content_length": {
        "weight": 10,
        "check": "본문 텍스트 길이 (최소 300단어 권장)",
    },
    "keyword_density": {
        "weight": 10,
        "check": "목표 키워드 밀도 (1~3% 적정, 5% 이상은 과다)",
    },
    "image_alt": {
        "weight": 5,
        "check": "img 태그에 alt 속성 있는지 (접근성 + SEO)",
    },
    # ── 기술 (25점) ──
    "mobile_viewport": {
        "weight": 10,
        "check": "viewport 메타 태그 존재 (모바일 대응)",
    },
    "canonical_tag": {
        "weight": 5,
        "check": "canonical URL 설정 여부",
    },
    "robots_txt": {
        "weight": 5,
        "check": "/robots.txt 존재 여부",
    },
    "sitemap": {
        "weight": 5,
        "check": "/sitemap.xml 존재 여부",
    },
    # ── 성능 (20점) ──
    "page_load_time": {
        "weight": 10,
        "check": "페이지 응답 시간 (1초 미만 우수, 3초 이상 나쁨)",
    },
    "html_size": {
        "weight": 5,
        "check": "HTML 파일 크기 (100KB 이하 적정)",
    },
    "external_links": {
        "weight": 5,
        "check": "외부 링크 수 + nofollow 여부",
    },
}


class SeoAnalyzerTool(BaseTool):
    """웹사이트 SEO(검색엔진 최적화) 상태를 자동 점검하고 개선안을 제시하는 도구."""

    async def execute(self, **kwargs: Any) -> str:
        """
        SEO 분석 도구 실행.

        kwargs:
          - action: "audit" | "keywords" | "compare"
          - url / url1 / url2: 분석할 웹페이지 주소
          - target_keywords: 확인할 키워드 (쉼표 구분)
        """
        action = kwargs.get("action", "audit")

        if action == "audit":
            return await self._audit(kwargs)
        elif action == "keywords":
            return await self._keywords(kwargs)
        elif action == "compare":
            return await self._compare(kwargs)
        else:
            return f"알 수 없는 action: {action}\n사용 가능: audit, keywords, compare"

    # ──────────────────────────────────────
    #  내부: 페이지 가져오기
    # ──────────────────────────────────────

    async def _fetch_page(self, url: str) -> tuple[str, float, int]:
        """URL의 HTML을 가져오고, 응답 시간과 크기를 함께 반환합니다.

        Returns:
            (html_text, elapsed_seconds, content_length_bytes)
        """
        async with httpx.AsyncClient(
            headers=_HEADERS, follow_redirects=True, timeout=15.0
        ) as client:
            start = time.time()
            resp = await client.get(url)
            elapsed = time.time() - start
            resp.raise_for_status()
            html = resp.text
            return html, elapsed, len(resp.content)

    async def _check_url_exists(self, url: str) -> bool:
        """URL이 존재하는지(200 응답) 확인합니다."""
        try:
            async with httpx.AsyncClient(
                headers=_HEADERS, follow_redirects=True, timeout=10.0
            ) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except Exception:
            return False

    # ──────────────────────────────────────
    #  내부: 점수 산정 로직
    # ──────────────────────────────────────

    async def _run_audit(self, url: str) -> dict[str, Any]:
        """SEO 감사를 실행하고 항목별 점수 딕셔너리를 반환합니다."""
        try:
            html, elapsed, content_size = await self._fetch_page(url)
        except Exception as e:
            return {"error": f"페이지를 불러올 수 없습니다: {e}"}

        soup = BeautifulSoup(html, "html.parser")
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        results: dict[str, dict[str, Any]] = {}
        total_score = 0

        # 1. title_tag (10점)
        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else ""
        if not title_text:
            results["title_tag"] = {"score": 0, "max": 10, "detail": "title 태그가 없습니다."}
        elif len(title_text) < 30 or len(title_text) > 60:
            results["title_tag"] = {
                "score": 5,
                "max": 10,
                "detail": f"title 길이 {len(title_text)}자 (권장: 30~60자): '{title_text}'",
            }
        else:
            results["title_tag"] = {
                "score": 10,
                "max": 10,
                "detail": f"title 적정 ({len(title_text)}자): '{title_text}'",
            }
        total_score += results["title_tag"]["score"]

        # 2. meta_description (10점)
        meta_desc = soup.find("meta", attrs={"name": "description"})
        desc_content = meta_desc["content"].strip() if meta_desc and meta_desc.get("content") else ""
        if not desc_content:
            results["meta_description"] = {"score": 0, "max": 10, "detail": "meta description이 없습니다."}
        elif len(desc_content) < 120 or len(desc_content) > 160:
            results["meta_description"] = {
                "score": 5,
                "max": 10,
                "detail": f"meta description 길이 {len(desc_content)}자 (권장: 120~160자)",
            }
        else:
            results["meta_description"] = {
                "score": 10,
                "max": 10,
                "detail": f"meta description 적정 ({len(desc_content)}자)",
            }
        total_score += results["meta_description"]["score"]

        # 3. h1_tag (5점)
        h1_tags = soup.find_all("h1")
        if len(h1_tags) == 0:
            results["h1_tag"] = {"score": 0, "max": 5, "detail": "h1 태그가 없습니다."}
        elif len(h1_tags) == 1:
            results["h1_tag"] = {
                "score": 5,
                "max": 5,
                "detail": f"h1 태그 1개 (정상): '{h1_tags[0].get_text(strip=True)[:50]}'",
            }
        else:
            results["h1_tag"] = {
                "score": 2,
                "max": 5,
                "detail": f"h1 태그 {len(h1_tags)}개 (1개만 권장)",
            }
        total_score += results["h1_tag"]["score"]

        # 4. heading_structure (5점)
        headings = soup.find_all(re.compile(r"^h[1-6]$"))
        heading_levels = [int(h.name[1]) for h in headings]
        skip_found = False
        for i in range(1, len(heading_levels)):
            if heading_levels[i] > heading_levels[i - 1] + 1:
                skip_found = True
                break
        if not heading_levels:
            results["heading_structure"] = {"score": 0, "max": 5, "detail": "heading 태그가 없습니다."}
        elif skip_found:
            results["heading_structure"] = {
                "score": 2,
                "max": 5,
                "detail": f"heading 순서 건너뛰기 발견 (예: h1→h3). 순서: {heading_levels[:10]}",
            }
        else:
            results["heading_structure"] = {
                "score": 5,
                "max": 5,
                "detail": f"heading 순서 정상. 순서: {heading_levels[:10]}",
            }
        total_score += results["heading_structure"]["score"]

        # 5. content_length (10점)
        body = soup.find("body")
        body_text = body.get_text(separator=" ", strip=True) if body else ""
        word_count = len(body_text.split())
        if word_count >= 300:
            results["content_length"] = {
                "score": 10,
                "max": 10,
                "detail": f"본문 {word_count}단어 (충분)",
            }
        elif word_count >= 100:
            results["content_length"] = {
                "score": 5,
                "max": 10,
                "detail": f"본문 {word_count}단어 (권장: 300단어 이상)",
            }
        else:
            results["content_length"] = {
                "score": 2,
                "max": 10,
                "detail": f"본문 {word_count}단어 (너무 적음, 권장: 300단어 이상)",
            }
        total_score += results["content_length"]["score"]

        # 6. keyword_density (10점) — 키워드 없으면 title 기준
        kw_text = title_text or ""
        if kw_text and body_text and word_count > 0:
            kw_count = body_text.lower().count(kw_text.lower().split()[0]) if kw_text.split() else 0
            density = (kw_count / word_count) * 100 if word_count > 0 else 0
            if 1.0 <= density <= 3.0:
                results["keyword_density"] = {
                    "score": 10,
                    "max": 10,
                    "detail": f"키워드 밀도 {density:.1f}% (적정 범위)",
                }
            elif density > 5.0:
                results["keyword_density"] = {
                    "score": 3,
                    "max": 10,
                    "detail": f"키워드 밀도 {density:.1f}% (과다 — 스팸으로 인식될 수 있음)",
                }
            elif density > 0:
                results["keyword_density"] = {
                    "score": 7,
                    "max": 10,
                    "detail": f"키워드 밀도 {density:.1f}%",
                }
            else:
                results["keyword_density"] = {
                    "score": 5,
                    "max": 10,
                    "detail": "키워드 밀도 측정 불가 (title 키워드가 본문에 없음)",
                }
        else:
            results["keyword_density"] = {
                "score": 5,
                "max": 10,
                "detail": "키워드 밀도 측정 불가 (title 또는 본문 부족)",
            }
        total_score += results["keyword_density"]["score"]

        # 7. image_alt (5점)
        images = soup.find_all("img")
        if not images:
            results["image_alt"] = {"score": 5, "max": 5, "detail": "이미지 없음 (감점 없음)"}
        else:
            no_alt = [img for img in images if not img.get("alt")]
            alt_ratio = 1 - (len(no_alt) / len(images)) if images else 1
            score = round(5 * alt_ratio)
            results["image_alt"] = {
                "score": score,
                "max": 5,
                "detail": f"이미지 {len(images)}개 중 alt 없는 것 {len(no_alt)}개",
            }
        total_score += results["image_alt"]["score"]

        # 8. mobile_viewport (10점)
        viewport = soup.find("meta", attrs={"name": "viewport"})
        if viewport:
            results["mobile_viewport"] = {"score": 10, "max": 10, "detail": "viewport 메타 태그 있음"}
        else:
            results["mobile_viewport"] = {"score": 0, "max": 10, "detail": "viewport 메타 태그 없음 (모바일 미대응)"}
        total_score += results["mobile_viewport"]["score"]

        # 9. canonical_tag (5점)
        canonical = soup.find("link", attrs={"rel": "canonical"})
        if canonical:
            results["canonical_tag"] = {
                "score": 5,
                "max": 5,
                "detail": f"canonical URL 설정됨: {canonical.get('href', '')}",
            }
        else:
            results["canonical_tag"] = {"score": 0, "max": 5, "detail": "canonical URL 없음"}
        total_score += results["canonical_tag"]["score"]

        # 10. robots.txt (5점)
        robots_url = urljoin(base_url, "/robots.txt")
        robots_exists = await self._check_url_exists(robots_url)
        results["robots_txt"] = {
            "score": 5 if robots_exists else 0,
            "max": 5,
            "detail": f"robots.txt {'있음' if robots_exists else '없음'} ({robots_url})",
        }
        total_score += results["robots_txt"]["score"]

        # 11. sitemap (5점)
        sitemap_url = urljoin(base_url, "/sitemap.xml")
        sitemap_exists = await self._check_url_exists(sitemap_url)
        results["sitemap"] = {
            "score": 5 if sitemap_exists else 0,
            "max": 5,
            "detail": f"sitemap.xml {'있음' if sitemap_exists else '없음'} ({sitemap_url})",
        }
        total_score += results["sitemap"]["score"]

        # 12. page_load_time (10점)
        if elapsed < 1.0:
            load_score = 10
            load_label = "우수"
        elif elapsed < 2.0:
            load_score = 7
            load_label = "양호"
        elif elapsed < 3.0:
            load_score = 4
            load_label = "보통"
        else:
            load_score = 0
            load_label = "느림"
        results["page_load_time"] = {
            "score": load_score,
            "max": 10,
            "detail": f"응답 시간 {elapsed:.2f}초 ({load_label})",
        }
        total_score += load_score

        # 13. html_size (5점)
        size_kb = content_size / 1024
        if size_kb <= 100:
            results["html_size"] = {"score": 5, "max": 5, "detail": f"HTML 크기 {size_kb:.0f}KB (적정)"}
        elif size_kb <= 200:
            results["html_size"] = {"score": 3, "max": 5, "detail": f"HTML 크기 {size_kb:.0f}KB (약간 큼)"}
        else:
            results["html_size"] = {"score": 0, "max": 5, "detail": f"HTML 크기 {size_kb:.0f}KB (너무 큼)"}
        total_score += results["html_size"]["score"]

        # 14. external_links (5점)
        all_links = soup.find_all("a", href=True)
        external = [a for a in all_links if urlparse(a["href"]).netloc and urlparse(a["href"]).netloc != parsed.netloc]
        nofollow_count = sum(1 for a in external if "nofollow" in (a.get("rel") or []))
        if len(external) <= 20:
            results["external_links"] = {
                "score": 5,
                "max": 5,
                "detail": f"외부 링크 {len(external)}개 (적정), nofollow {nofollow_count}개",
            }
        elif len(external) <= 50:
            results["external_links"] = {
                "score": 3,
                "max": 5,
                "detail": f"외부 링크 {len(external)}개 (약간 많음), nofollow {nofollow_count}개",
            }
        else:
            results["external_links"] = {
                "score": 0,
                "max": 5,
                "detail": f"외부 링크 {len(external)}개 (과다), nofollow {nofollow_count}개",
            }
        total_score += results["external_links"]["score"]

        return {
            "url": url,
            "total_score": total_score,
            "items": results,
            "word_count": word_count,
        }

    # ──────────────────────────────────────
    #  action: audit
    # ──────────────────────────────────────

    async def _audit(self, kwargs: dict[str, Any]) -> str:
        """SEO 종합 감사를 실행합니다."""
        url = kwargs.get("url", "")
        if not url:
            return "url 파라미터를 입력해주세요. 예: url='https://example.com'"

        logger.info("[seo_analyzer] audit 시작: %s", url)

        audit = await self._run_audit(url)
        if "error" in audit:
            return f"SEO 감사 실패: {audit['error']}"

        # 결과 포맷팅
        total = audit["total_score"]
        grade = "A+" if total >= 90 else "A" if total >= 80 else "B" if total >= 70 else "C" if total >= 60 else "D" if total >= 50 else "F"

        lines = [
            f"## SEO 감사 결과: {audit['url']}",
            f"### 총점: {total}/100 (등급: {grade})",
            "",
        ]

        # 카테고리별 정리
        categories = {
            "기본 메타 (30점)": ["title_tag", "meta_description", "h1_tag", "heading_structure"],
            "콘텐츠 (25점)": ["content_length", "keyword_density", "image_alt"],
            "기술 (25점)": ["mobile_viewport", "canonical_tag", "robots_txt", "sitemap"],
            "성능 (20점)": ["page_load_time", "html_size", "external_links"],
        }

        for cat_name, keys in categories.items():
            cat_score = sum(audit["items"][k]["score"] for k in keys)
            cat_max = sum(audit["items"][k]["max"] for k in keys)
            lines.append(f"#### {cat_name} — {cat_score}/{cat_max}")
            for k in keys:
                item = audit["items"][k]
                icon = "pass" if item["score"] == item["max"] else ("warn" if item["score"] > 0 else "fail")
                lines.append(f"- [{icon}] **{k}** ({item['score']}/{item['max']}): {item['detail']}")
            lines.append("")

        result_text = "\n".join(lines)

        # LLM 분석 추가
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 SEO 전문가입니다. 아래 SEO 감사 결과를 분석하여:\n"
                "1. 가장 시급히 개선해야 할 항목 3가지\n"
                "2. 각 항목별 구체적인 수정 방법 (코드 예시 포함)\n"
                "3. 개선 시 예상되는 효과\n"
                "를 한국어로 작성하세요."
            ),
            user_prompt=result_text,
        )

        return f"{result_text}\n---\n\n### AI 개선 가이드\n\n{analysis}"

    # ──────────────────────────────────────
    #  action: keywords
    # ──────────────────────────────────────

    async def _keywords(self, kwargs: dict[str, Any]) -> str:
        """페이지의 키워드 밀도를 분석합니다."""
        url = kwargs.get("url", "")
        target_keywords = kwargs.get("target_keywords", "")
        if not url:
            return "url 파라미터를 입력해주세요."
        if not target_keywords:
            return "target_keywords 파라미터를 입력해주세요. 예: target_keywords='LEET,로스쿨,법학'"

        logger.info("[seo_analyzer] keywords 분석: %s, 키워드=%s", url, target_keywords)

        try:
            html, _, _ = await self._fetch_page(url)
        except Exception as e:
            return f"페이지를 불러올 수 없습니다: {e}"

        soup = BeautifulSoup(html, "html.parser")
        body = soup.find("body")
        body_text = body.get_text(separator=" ", strip=True) if body else ""
        total_words = len(body_text.split())

        if total_words == 0:
            return "본문 텍스트가 없어 키워드 밀도를 측정할 수 없습니다."

        keywords = [kw.strip() for kw in target_keywords.split(",") if kw.strip()]
        lines = [
            f"## 키워드 밀도 분석: {url}",
            f"- 총 단어 수: {total_words}",
            "",
            "| 키워드 | 출현 횟수 | 밀도(%) | 평가 |",
            "|--------|-----------|---------|------|",
        ]

        for kw in keywords:
            count = body_text.lower().count(kw.lower())
            density = (count / total_words) * 100
            if 1.0 <= density <= 3.0:
                evaluation = "적정"
            elif density > 5.0:
                evaluation = "과다 (스팸 위험)"
            elif density > 3.0:
                evaluation = "약간 높음"
            elif density > 0:
                evaluation = "낮음"
            else:
                evaluation = "없음"
            lines.append(f"| {kw} | {count} | {density:.2f}% | {evaluation} |")

        result_text = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 SEO 키워드 전문가입니다. 아래 키워드 밀도 분석 결과를 보고:\n"
                "1. 각 키워드의 밀도가 적절한지 평가\n"
                "2. 밀도를 높이거나 낮추는 구체적 방법\n"
                "3. 추가로 사용하면 좋을 관련 키워드 5개 추천\n"
                "을 한국어로 작성하세요."
            ),
            user_prompt=result_text,
        )

        return f"{result_text}\n\n---\n\n### AI 키워드 전략\n\n{analysis}"

    # ──────────────────────────────────────
    #  action: compare
    # ──────────────────────────────────────

    async def _compare(self, kwargs: dict[str, Any]) -> str:
        """두 URL의 SEO 점수를 비교합니다."""
        url1 = kwargs.get("url1", "")
        url2 = kwargs.get("url2", "")
        if not url1 or not url2:
            return "url1과 url2 파라미터를 모두 입력해주세요."

        logger.info("[seo_analyzer] compare: %s vs %s", url1, url2)

        audit1 = await self._run_audit(url1)
        audit2 = await self._run_audit(url2)

        if "error" in audit1:
            return f"URL1 분석 실패: {audit1['error']}"
        if "error" in audit2:
            return f"URL2 분석 실패: {audit2['error']}"

        lines = [
            "## SEO 점수 비교",
            "",
            f"| 항목 | {url1} | {url2} | 차이 |",
            "|------|--------|--------|------|",
            f"| **총점** | **{audit1['total_score']}** | **{audit2['total_score']}** | **{audit1['total_score'] - audit2['total_score']:+d}** |",
        ]

        for key in SEO_CHECKS:
            s1 = audit1["items"][key]["score"]
            s2 = audit2["items"][key]["score"]
            diff = s1 - s2
            lines.append(f"| {key} | {s1} | {s2} | {diff:+d} |")

        result_text = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 SEO 전문가입니다. 두 웹사이트의 SEO 점수 비교 결과를 분석하여:\n"
                "1. 어떤 사이트가 SEO에 더 유리한지 (이유 포함)\n"
                "2. 각 사이트가 서로에게서 배울 수 있는 점\n"
                "3. 양쪽 모두에게 해당되는 공통 개선 사항\n"
                "을 한국어로 작성하세요."
            ),
            user_prompt=result_text,
        )

        return f"{result_text}\n\n---\n\n### AI 비교 분석\n\n{analysis}"
