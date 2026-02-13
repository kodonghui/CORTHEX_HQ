"""
보고서 자동 저장 모듈.

모든 에이전트의 산출물을 부서별/날짜별로 아카이브합니다.

디렉토리 구조:
  reports/
    2026-02-12/
      secretary/
        chief_of_staff_143025.md
      leet_master/
        tech/
          cto_manager_143027.md
          frontend_specialist_143028.md
      finance/
        investment/
          cio_manager_143032.md
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.agent import AgentConfig
    from src.core.message import TaskResult

logger = logging.getLogger("corthex.report_saver")

REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "reports"


def _slugify(text: str, max_len: int = 40) -> str:
    """한국어 포함 텍스트를 파일명에 안전한 문자열로 변환."""
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = text.replace(" ", "_")
    return text[:max_len].rstrip("_") or "report"


def _division_to_path(division: str) -> Path:
    """division 문자열을 디렉토리 경로로 변환.

    예: 'leet_master.tech' → Path('leet_master/tech')
    """
    return Path(*division.split("."))


def save_agent_report(
    config: AgentConfig,
    task_description: str,
    result: TaskResult,
) -> Path | None:
    """개별 에이전트의 산출물을 부서별/날짜별로 저장."""
    try:
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H%M%S")

        # reports/2026-02-12/leet_master/tech/
        division_path = _division_to_path(config.division)
        dir_path = REPORTS_DIR / date_str / division_path
        dir_path.mkdir(parents=True, exist_ok=True)

        # cto_manager_143027.md
        filename = f"{config.agent_id}_{time_str}.md"
        filepath = dir_path / filename

        content = _format_agent_report(config, task_description, result, now)
        filepath.write_text(content, encoding="utf-8")

        logger.info("[%s] 보고서 저장: %s", config.agent_id, filepath)
        return filepath
    except Exception as e:
        logger.error("[%s] 보고서 저장 실패: %s", config.agent_id, e)
        return None


def _format_agent_report(
    config: AgentConfig,
    task_description: str,
    result: TaskResult,
    timestamp: datetime,
) -> str:
    """에이전트 산출물을 마크다운 형식으로 포맷."""
    status = "SUCCESS" if result.success else "FAILED"
    body = str(result.result_data or result.summary)

    return (
        f"# {config.name_ko} ({config.agent_id}) 보고서\n\n"
        f"- **일시**: {timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"- **부서**: {config.division}\n"
        f"- **역할**: {config.role}\n"
        f"- **지시 내용**: {task_description}\n"
        f"- **상태**: {status}\n"
        f"- **처리 시간**: {result.execution_time_seconds}초\n\n"
        f"---\n\n"
        f"{body}\n"
    )
