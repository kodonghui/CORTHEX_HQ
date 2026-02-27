"""
자동 뉴스레터 생성기 도구 (Newsletter Builder).

주간/월간 뉴스레터를 자동 생성합니다.
뉴스, 트렌드, 커뮤니티, 팁 등 다양한 섹션을 포함하며,
마크다운과 HTML(이메일용) 형식으로 저장합니다.

사용 방법:
  - action="build": 뉴스레터 생성 (period, topic, sections)
  - action="preview": 뉴스레터 미리보기 (newsletter_id)
  - action="templates": 사용 가능한 뉴스레터 템플릿 목록

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬 + LLM)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.newsletter_builder")

KST = timezone(timedelta(hours=9))

DATA_DIR = Path("data")
NEWSLETTERS_DIR = DATA_DIR / "newsletters"

# ── 뉴스레터 템플릿 ──

NEWSLETTER_TEMPLATE = """# 📰 CORTHEX 위클리 — {period_label}

> {intro_text}

---

{sections_content}

---

*이 뉴스레터는 CORTHEX AI가 자동 생성했습니다.*
"""

MONTHLY_TEMPLATE = """# 📰 CORTHEX 먼슬리 — {period_label}

> {intro_text}

---

{sections_content}

---

*이 뉴스레터는 CORTHEX AI가 자동 생성했습니다.*
"""

# ── 섹션별 이모지와 제목 ──

SECTION_CONFIG: dict[str, dict[str, str]] = {
    "news": {"emoji": "📋", "title": "주요 뉴스"},
    "trends": {"emoji": "📊", "title": "트렌드 & 데이터"},
    "community": {"emoji": "💬", "title": "커뮤니티 이야기"},
    "tips": {"emoji": "💡", "title": "이번 주의 팁"},
    "tech": {"emoji": "🔧", "title": "기술 업데이트"},
    "market": {"emoji": "📈", "title": "시장 동향"},
}

# HTML 이메일 인라인 스타일
EMAIL_STYLE = """
<style>
body { font-family: 'Noto Sans KR', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f5f5f5; }
.container { background-color: #ffffff; border-radius: 8px; padding: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
h1 { color: #1a1a2e; font-size: 24px; border-bottom: 3px solid #e94560; padding-bottom: 10px; }
h2 { color: #16213e; font-size: 18px; margin-top: 25px; }
h3 { color: #0f3460; font-size: 16px; }
hr { border: none; border-top: 1px solid #eee; margin: 25px 0; }
blockquote { border-left: 4px solid #e94560; padding-left: 15px; color: #666; font-style: italic; }
li { margin: 5px 0; line-height: 1.6; }
p { line-height: 1.8; color: #333; }
.footer { text-align: center; color: #999; font-size: 12px; margin-top: 30px; }
</style>
"""


class NewsletterBuilderTool(BaseTool):
    """자동 뉴스레터 생성기 — 주간/월간 뉴스레터를 자동 생성합니다."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "build")

        if action == "build":
            return await self._build(kwargs)
        elif action == "preview":
            return self._preview(kwargs)
        elif action == "templates":
            return self._list_templates()
        else:
            return (
                f"알 수 없는 action: {action}. "
                "build, preview, templates 중 하나를 사용하세요."
            )

    # ── 디렉토리 관리 ──

    def _ensure_newsletters_dir(self) -> None:
        NEWSLETTERS_DIR.mkdir(parents=True, exist_ok=True)

    # ── 마크다운 → HTML 변환 (이메일용) ──

    @staticmethod
    def _md_to_email_html(md: str) -> str:
        """마크다운을 이메일 호환 HTML로 변환합니다."""
        html = md
        # 제목
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.M)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.M)
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.M)
        # 인용
        html = re.sub(r"^> (.+)$", r"<blockquote>\1</blockquote>", html, flags=re.M)
        # 굵게, 기울임
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
        # 수평선
        html = re.sub(r"^---$", r"<hr>", html, flags=re.M)
        # 리스트
        html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.M)
        # 단락
        html = re.sub(r"\n\n", r"</p>\n<p>", html)

        return (
            f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"{EMAIL_STYLE}</head>"
            f"<body><div class='container'><p>{html}</p>"
            f"<div class='footer'>CORTHEX HQ Newsletter</div>"
            f"</div></body></html>"
        )

    # ── action 구현 ──

    async def _build(self, kwargs: dict[str, Any]) -> str:
        """뉴스레터를 생성합니다."""
        period = kwargs.get("period", "weekly")
        topic = kwargs.get("topic", "LEET/법학")
        sections_param = kwargs.get("sections", "news,trends,community,tips")

        now = datetime.now(KST)
        date_str = now.strftime("%Y-%m-%d")

        # 기간 라벨
        if period == "weekly":
            week_start = now - timedelta(days=now.weekday())
            week_end = week_start + timedelta(days=6)
            period_label = f"{week_start.strftime('%m/%d')} ~ {week_end.strftime('%m/%d')}"
        else:
            period_label = now.strftime("%Y년 %m월")

        # 섹션 목록 파싱
        section_list = [s.strip() for s in str(sections_param).split(",")]

        # 각 섹션 콘텐츠 생성
        sections_content_parts: list[str] = []
        for section_key in section_list:
            config = SECTION_CONFIG.get(section_key, {"emoji": "📌", "title": section_key})
            section_content = await self._generate_section(section_key, topic, period, period_label)
            sections_content_parts.append(
                f"## {config['emoji']} {config['title']}\n{section_content}"
            )

        sections_content = "\n\n".join(sections_content_parts)

        # 인트로 텍스트 생성
        intro_text = await self._llm_call(
            system_prompt=(
                "당신은 뉴스레터 편집자입니다.\n"
                "뉴스레터의 인트로(도입부) 한 문장을 작성하세요.\n"
                "톤: 친근하면서도 전문적. 독자의 관심을 끄는 문장.\n"
                "한국어로 작성하세요. 한 문장만 출력하세요."
            ),
            user_prompt=f"주제: {topic}, 기간: {period_label}",
        )

        # 템플릿 적용
        template = NEWSLETTER_TEMPLATE if period == "weekly" else MONTHLY_TEMPLATE
        newsletter_md = template.format(
            period_label=period_label,
            intro_text=intro_text.strip(),
            sections_content=sections_content,
        )

        # 품질 검토
        review = await self._llm_call(
            system_prompt=(
                "당신은 뉴스레터 품질 검토 전문가입니다.\n"
                "주어진 뉴스레터를 검토하고 다음만 출력하세요:\n"
                "1. 추천 제목 (이메일 제목으로 쓸 수 있는 매력적인 한 줄)\n"
                "2. 품질 점수 (1-10)\n"
                "3. 개선 포인트 1가지\n"
                "한국어로 작성하세요."
            ),
            user_prompt=newsletter_md,
        )

        # 파일 저장
        self._ensure_newsletters_dir()
        filename = f"newsletter_{period}_{date_str}"

        md_path = NEWSLETTERS_DIR / f"{filename}.md"
        md_path.write_text(newsletter_md, encoding="utf-8")

        html_content = self._md_to_email_html(newsletter_md)
        html_path = NEWSLETTERS_DIR / f"{filename}.html"
        html_path.write_text(html_content, encoding="utf-8")

        logger.info("뉴스레터 생성: %s", md_path)

        return (
            f"## 뉴스레터 생성 완료\n"
            f"- 마크다운: {md_path}\n"
            f"- HTML (이메일용): {html_path}\n"
            f"- ID: {filename}\n\n"
            f"### 품질 검토\n{review}\n\n"
            f"---\n\n{newsletter_md}"
        )

    async def _generate_section(self, section_key: str, topic: str, period: str, period_label: str) -> str:
        """섹션별 콘텐츠를 생성합니다."""
        # data/ 폴더에서 관련 데이터 파일 활용 시도
        data_context = self._get_section_data(section_key)

        prompts: dict[str, str] = {
            "news": f"'{topic}' 관련 이번 주({period_label}) 주요 뉴스/이슈 3-5개를 정리하세요. 각 항목은 제목과 1줄 요약으로 구성하세요.",
            "trends": f"'{topic}' 분야의 최근 트렌드와 데이터 포인트 3개를 정리하세요. 수치를 포함하세요.",
            "community": f"'{topic}' 커뮤니티에서 화제가 된 이야기 2-3개를 정리하세요. 독자의 관심을 끄는 톤으로.",
            "tips": f"'{topic}' 관련 실용적인 팁 2-3개를 정리하세요. 독자가 바로 적용할 수 있는 구체적인 것으로.",
            "tech": "이번 주 기술 업데이트와 개발 진행 상황을 정리하세요.",
            "market": f"'{topic}' 관련 시장 동향을 정리하세요. 수치와 데이터를 포함하세요.",
        }

        prompt = prompts.get(section_key, f"'{section_key}' 섹션 내용을 작성하세요.")

        if data_context:
            prompt += f"\n\n참고 데이터:\n{data_context}"

        return await self._llm_call(
            system_prompt=(
                "당신은 뉴스레터 콘텐츠 작성자입니다.\n"
                "주어진 주제에 대해 뉴스레터 섹션 콘텐츠를 작성하세요.\n"
                "규칙:\n"
                "- 마크다운 리스트 형식 사용\n"
                "- 각 항목은 간결하게 (2-3줄 이내)\n"
                "- 톤: 친근하면서도 정보 전달에 충실\n"
                "- 한국어로 작성\n"
                "- 섹션 제목은 쓰지 마세요 (이미 있음)"
            ),
            user_prompt=prompt,
        )

    @staticmethod
    def _get_section_data(section_key: str) -> str:
        """data/ 폴더에서 섹션과 관련된 데이터를 수집합니다."""
        data_files: dict[str, list[str]] = {
            "news": ["naver_news_*.json", "web_search_*.json"],
            "trends": ["naver_datalab_*.json", "public_data_*.json"],
            "community": ["daum_cafe_*.json", "leet_survey_*.json"],
            "market": ["kr_stock_*.json", "ecos_macro_*.json"],
        }

        patterns = data_files.get(section_key, [])
        summaries: list[str] = []

        for pattern in patterns:
            for f in sorted(DATA_DIR.glob(pattern)):
                try:
                    content = json.loads(f.read_text(encoding="utf-8"))
                    if isinstance(content, dict):
                        summaries.append(f"[{f.name}] {json.dumps(content, ensure_ascii=False)[:500]}")
                    elif isinstance(content, list):
                        summaries.append(f"[{f.name}] {len(content)}건 데이터")
                except Exception:
                    continue

        return "\n".join(summaries) if summaries else ""

    def _preview(self, kwargs: dict[str, Any]) -> str:
        """기존 뉴스레터를 미리보기합니다."""
        newsletter_id = kwargs.get("newsletter_id", "").strip()

        if not newsletter_id:
            # 가장 최근 뉴스레터 표시
            if not NEWSLETTERS_DIR.exists():
                return "생성된 뉴스레터가 없습니다. action='build'로 먼저 생성하세요."

            md_files = sorted(NEWSLETTERS_DIR.glob("*.md"))
            if not md_files:
                return "생성된 뉴스레터가 없습니다."

            latest = md_files[-1]
            return f"## 최근 뉴스레터: {latest.name}\n\n{latest.read_text(encoding='utf-8')}"

        # ID로 찾기
        md_path = NEWSLETTERS_DIR / f"{newsletter_id}.md"
        if not md_path.exists():
            return f"뉴스레터를 찾을 수 없습니다: {newsletter_id}"

        return md_path.read_text(encoding="utf-8")

    def _list_templates(self) -> str:
        """사용 가능한 뉴스레터 템플릿 목록."""
        lines = [
            "## 뉴스레터 템플릿",
            "",
            "### 기간 유형",
            "- **weekly**: 주간 뉴스레터 (기본)",
            "- **monthly**: 월간 뉴스레터",
            "",
            "### 사용 가능한 섹션",
        ]

        for key, config in SECTION_CONFIG.items():
            lines.append(f"- **{key}**: {config['emoji']} {config['title']}")

        lines.extend([
            "",
            "### 사용 예시",
            '```',
            'action="build", period="weekly", topic="LEET/법학"',
            'sections="news,trends,community,tips"',
            '```',
            "",
            "### 기존 뉴스레터 목록",
        ])

        if NEWSLETTERS_DIR.exists():
            md_files = sorted(NEWSLETTERS_DIR.glob("*.md"))
            if md_files:
                for f in md_files[-10:]:
                    lines.append(f"- {f.stem}")
            else:
                lines.append("- (없음)")
        else:
            lines.append("- (없음)")

        return "\n".join(lines)
