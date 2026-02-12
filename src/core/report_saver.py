"""
보고서 자동 저장 모듈.

Orchestrator가 처리한 결과를 reports/ 디렉토리에
마크다운 파일로 저장합니다.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.message import TaskResult

logger = logging.getLogger("corthex.report_saver")

REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "reports"


def _slugify(text: str, max_len: int = 40) -> str:
    """한국어 포함 텍스트를 파일명에 안전한 문자열로 변환."""
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = text.replace(" ", "_")
    return text[:max_len].rstrip("_") or "report"


def save_report(command: str, result: TaskResult) -> Path | None:
    """TaskResult를 마크다운 파일로 저장하고 경로를 반환."""
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        slug = _slugify(command)
        filename = f"{timestamp}_{slug}.md"
        filepath = REPORTS_DIR / filename

        content = _format_report(command, result, now)
        filepath.write_text(content, encoding="utf-8")

        logger.info("보고서 저장: %s", filepath)
        return filepath
    except Exception as e:
        logger.error("보고서 저장 실패: %s", e)
        return None


def _format_report(command: str, result: TaskResult, timestamp: datetime) -> str:
    """TaskResult를 마크다운 형식으로 포맷."""
    status = "SUCCESS" if result.success else "FAILED"
    body = str(result.result_data or result.summary)

    return (
        f"# CORTHEX HQ 보고서\n\n"
        f"- **일시**: {timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"- **CEO 명령**: {command}\n"
        f"- **처리 에이전트**: {result.sender_id}\n"
        f"- **상태**: {status}\n"
        f"- **처리 시간**: {result.execution_time_seconds}초\n\n"
        f"---\n\n"
        f"{body}\n"
    )
