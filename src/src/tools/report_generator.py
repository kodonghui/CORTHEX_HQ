"""
보고서 자동 생성기 도구 (Report Generator).

분석 결과를 전문적인 마크다운 또는 HTML 보고서로
자동 생성합니다. 투자보고서, 시장분석, 주간보고 등
다양한 템플릿을 지원합니다.

사용 방법:
  - action="generate": 보고서 생성 (title, sections, format, template)
  - action="weekly": 주간 종합 보고서 자동 생성 (week_start)
  - action="templates": 사용 가능한 보고서 템플릿 목록

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.report_generator")

KST = timezone(timedelta(hours=9))

DATA_DIR = Path("data")  # 레거시 — 주간 보고서 수집용 (읽기 전용)
REPORTS_DIR = DATA_DIR / "reports"  # 레거시 — DB 아카이브로 대체

# ── 보고서 템플릿 ──

TEMPLATES: dict[str, str] = {
    "investment": """# {title}
**작성일**: {date} | **작성자**: CORTHEX 투자분석처

---

## 1. 시장 현황
{market_overview}

## 2. 종목 분석
{stock_analysis}

## 3. 기술적 분석
{technical_analysis}

## 4. 리스크 평가
{risk_assessment}

## 5. 투자 의견
{investment_opinion}

---
*본 보고서는 AI 분석 기반이며, 투자 결정의 최종 책임은 투자자에게 있습니다.*
""",

    "market": """# {title}
**작성일**: {date} | **작성자**: CORTHEX 사업기획처

---

## 1. 시장 개요
{market_overview}

## 2. 경쟁 환경
{competition}

## 3. 시장 규모 (TAM/SAM/SOM)
{market_size}

## 4. 트렌드 분석
{trends}

## 5. 기회 및 위협
{opportunities_threats}

## 6. 전략적 시사점
{strategic_implications}

---
*본 보고서는 AI 분석 기반이며, 실제 의사결정 시 추가 검증이 필요합니다.*
""",

    "weekly": """# {title}
**기간**: {period} | **작성일**: {date} | **작성자**: CORTHEX HQ

---

## 📋 이번 주 요약
{summary}

## 📊 주요 성과
{achievements}

## 🔧 기술 업데이트
{tech_updates}

## 📈 데이터 & 지표
{metrics}

## ⚠️ 이슈 & 리스크
{issues}

## 📝 다음 주 계획
{next_plans}

---
*본 보고서는 CORTHEX AI가 자동 생성했습니다.*
""",
}


class ReportGeneratorTool(BaseTool):
    """보고서 자동 생성기 — 분석 결과를 전문적인 보고서로 변환합니다."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "generate")

        if action == "generate":
            return await self._generate(kwargs)
        elif action == "weekly":
            return await self._weekly(kwargs)
        elif action == "templates":
            return self._list_templates()
        else:
            return (
                f"알 수 없는 action: {action}. "
                "generate, weekly, templates 중 하나를 사용하세요."
            )

    # ── 보고서 저장 (SQLite DB 아카이브) ──

    def _save_report_to_db(self, filename: str, content: str) -> None:
        """보고서를 DB 아카이브에 저장합니다."""
        try:
            from web.db import save_archive
            save_archive(
                division="reports",
                filename=filename,
                content=content,
            )
        except Exception as e:
            logger.warning("보고서 DB 저장 실패: %s", e)

    # ── 마크다운 → HTML 변환 ──

    @staticmethod
    def _md_to_html(md: str) -> str:
        """간단한 마크다운을 HTML로 변환합니다."""
        html = md
        # 제목
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.M)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.M)
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.M)
        # 굵게, 기울임
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
        # 수평선
        html = re.sub(r"^---$", r"<hr>", html, flags=re.M)
        # 리스트
        html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.M)
        # 단락
        html = re.sub(r"\n\n", r"</p>\n<p>", html)

        style = (
            "<style>"
            "body{font-family:'Noto Sans KR',sans-serif;max-width:800px;"
            "margin:0 auto;padding:20px;line-height:1.8;color:#333}"
            "h1{color:#1a1a2e;border-bottom:2px solid #16213e;padding-bottom:10px}"
            "h2{color:#16213e;margin-top:30px}"
            "h3{color:#0f3460}"
            "hr{border:none;border-top:1px solid #ddd;margin:30px 0}"
            "li{margin:5px 0}"
            "strong{color:#e94560}"
            "</style>"
        )
        return f"<!DOCTYPE html><html><head><meta charset='utf-8'>{style}</head><body><p>{html}</p></body></html>"

    # ── action 구현 ──

    async def _generate(self, kwargs: dict[str, Any]) -> str:
        """보고서 생성."""
        title = kwargs.get("title", "CORTHEX 보고서")
        sections = kwargs.get("sections", {})
        fmt = kwargs.get("format", "markdown")
        template_name = kwargs.get("template", "custom")

        now = datetime.now(KST)
        date_str = now.strftime("%Y-%m-%d")

        # sections이 JSON 문자열이면 파싱
        if isinstance(sections, str):
            try:
                sections = json.loads(sections)
            except json.JSONDecodeError:
                sections = {"content": sections}

        # 템플릿 기반 생성
        if template_name in TEMPLATES:
            template = TEMPLATES[template_name]
            # 템플릿 변수 채우기
            fill = {"title": title, "date": date_str}
            fill.update(sections)
            # 템플릿에서 사용하는 모든 변수에 기본값 설정
            placeholders = re.findall(r"\{(\w+)\}", template)
            for ph in placeholders:
                if ph not in fill:
                    fill[ph] = "(데이터 없음)"
            try:
                report_md = template.format(**fill)
            except KeyError as e:
                report_md = f"템플릿 변수 오류: {e}"
        else:
            # 커스텀 보고서
            report_md = f"# {title}\n**작성일**: {date_str}\n\n---\n\n"
            if isinstance(sections, dict):
                for sec_title, sec_content in sections.items():
                    report_md += f"## {sec_title}\n{sec_content}\n\n"
            else:
                report_md += str(sections)

        # LLM으로 보고서 보강
        enhanced = await self._llm_call(
            system_prompt=(
                "당신은 전문 보고서 편집자입니다.\n"
                "주어진 보고서 초안을 검토하고 다음을 추가하세요:\n"
                "1. 각 섹션에 대한 핵심 인사이트 1줄 추가 (💡로 시작)\n"
                "2. 보고서 맨 끝에 '핵심 요약' 섹션 (3줄 이내)\n"
                "원본 구조와 내용은 유지하되, 가독성을 높이세요.\n"
                "한국어로 작성하세요."
            ),
            user_prompt=report_md,
        )

        # DB 아카이브에 저장
        filename = f"report_{date_str}_{template_name}"
        self._save_report_to_db(f"{filename}.md", enhanced)
        logger.info("보고서 생성 (DB 저장): %s", filename)

        if fmt == "html":
            html_content = self._md_to_html(enhanced)
            self._save_report_to_db(f"{filename}.html", html_content)
            return f"보고서 생성 완료 (HTML+마크다운, DB 저장): {filename}\n\n{enhanced}"

        return f"보고서 생성 완료 (DB 저장): {filename}\n\n{enhanced}"

    async def _weekly(self, kwargs: dict[str, Any]) -> str:
        """주간 종합 보고서 자동 생성."""
        now = datetime.now(KST)
        week_start_str = kwargs.get("week_start", "")

        if week_start_str:
            try:
                week_start = datetime.strptime(week_start_str, "%Y-%m-%d").replace(tzinfo=KST)
            except ValueError:
                return f"날짜 형식이 잘못되었습니다: {week_start_str} (예: 2026-02-10)"
        else:
            # 이번 주 월요일
            week_start = now - timedelta(days=now.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        week_end = week_start + timedelta(days=6)
        period = f"{week_start.strftime('%Y-%m-%d')} ~ {week_end.strftime('%Y-%m-%d')}"

        # data/ 폴더에서 최근 데이터 파일 수집
        data_summary = self._collect_recent_data(week_start, week_end)

        # LLM으로 주간 보고서 내용 생성
        report_content = await self._llm_call(
            system_prompt=(
                "당신은 CORTHEX HQ의 주간 보고서 작성 전문가입니다.\n"
                "주어진 데이터를 바탕으로 주간 보고서의 각 섹션을 작성하세요.\n"
                "데이터가 없는 섹션은 '이번 주 해당 사항 없음'으로 표시하세요.\n\n"
                "반드시 다음 형식으로 작성하세요:\n"
                "SUMMARY: (요약 내용)\n"
                "ACHIEVEMENTS: (성과 내용)\n"
                "TECH_UPDATES: (기술 업데이트)\n"
                "METRICS: (데이터/지표)\n"
                "ISSUES: (이슈/리스크)\n"
                "NEXT_PLANS: (다음 주 계획)\n\n"
                "한국어로 작성하세요."
            ),
            user_prompt=f"기간: {period}\n\n수집된 데이터:\n{data_summary}",
        )

        # 섹션 파싱
        section_map = {
            "summary": "이번 주 활동 요약",
            "achievements": "해당 사항 없음",
            "tech_updates": "해당 사항 없음",
            "metrics": "해당 사항 없음",
            "issues": "해당 사항 없음",
            "next_plans": "해당 사항 없음",
        }
        for key in section_map:
            pattern = re.compile(rf"{key.upper()}:\s*(.+?)(?=\n[A-Z_]+:|$)", re.DOTALL)
            match = pattern.search(report_content)
            if match:
                section_map[key] = match.group(1).strip()

        return await self._generate({
            "title": f"CORTHEX 주간 보고서",
            "template": "weekly",
            "format": kwargs.get("format", "markdown"),
            "sections": {
                "period": period,
                "summary": section_map["summary"],
                "achievements": section_map["achievements"],
                "tech_updates": section_map["tech_updates"],
                "metrics": section_map["metrics"],
                "issues": section_map["issues"],
                "next_plans": section_map["next_plans"],
            },
        })

    def _list_templates(self) -> str:
        """사용 가능한 보고서 템플릿 목록."""
        lines = ["## 사용 가능한 보고서 템플릿", ""]
        template_info = {
            "investment": "투자 보고서 — 시장현황, 종목분석, 기술적분석, 리스크평가, 투자의견",
            "market": "시장 분석 보고서 — 시장개요, 경쟁환경, 시장규모, 트렌드, 기회/위협",
            "weekly": "주간 보고서 — 주간요약, 성과, 기술업데이트, 지표, 이슈, 다음주계획",
            "custom": "커스텀 보고서 — 자유 형식 (sections에 딕셔너리로 전달)",
        }
        for name, desc in template_info.items():
            lines.append(f"- **{name}**: {desc}")

        lines.extend([
            "",
            "### 사용 예시",
            '```',
            'action="generate", template="investment", title="삼성전자 투자보고서"',
            'sections={"market_overview": "...", "stock_analysis": "..."}',
            '```',
        ])
        return "\n".join(lines)

    @staticmethod
    def _collect_recent_data(start: datetime, end: datetime) -> str:
        """data/ 폴더에서 최근 데이터 파일들을 수집합니다."""
        summaries: list[str] = []

        if not DATA_DIR.exists():
            return "data/ 폴더에 수집된 데이터가 없습니다."

        for json_file in sorted(DATA_DIR.glob("*.json")):
            try:
                content = json.loads(json_file.read_text(encoding="utf-8"))
                summaries.append(f"- {json_file.name}: {type(content).__name__} 데이터")
            except Exception:
                continue

        if not summaries:
            return "수집된 데이터 파일이 없습니다."

        return "\n".join(summaries)
