"""
에러 로그 분석기 도구 (Log Analyzer).

로그 파일을 분석하여 에러 유형, 빈도, 패턴을 자동으로
통계 내고, 시간대별 분포를 텍스트 그래프로 시각화합니다.

사용 방법:
  - action="analyze": 로그 파일 전체 분석 (log_file, level, hours)
  - action="top_errors": 가장 많이 발생하는 에러 Top N (top_n)
  - action="timeline": 시간대별 에러 발생 빈도 (log_file, hours)

필요 환경변수: 없음
의존 라이브러리: 없음 (순수 파이썬)
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.log_analyzer")

KST = timezone(timedelta(hours=9))

DEFAULT_LOG_FILE = "logs/corthex.log"

# 표준 파이썬 로그 형식 파싱
LOG_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}),?\d*\s*[-–]\s*"
    r"([\w.]+)\s*[-–]\s*(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*[-–]\s*(.*)"
)

# 메시지 정규화용 패턴 (변수 부분을 치환하여 그룹핑)
NORMALIZE_PATTERNS = [
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*"), "{TIMESTAMP}"),
    (re.compile(r"https?://\S+"), "{URL}"),
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "{IP}"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "{UUID}"),
    (re.compile(r"\b\d+\b"), "{N}"),
]


@dataclass
class LogEntry:
    """파싱된 로그 한 줄."""
    timestamp: datetime
    logger_name: str
    level: str
    message: str


class LogAnalyzerTool(BaseTool):
    """에러 로그 분석기 — 로그 파일에서 에러 패턴과 빈도를 자동 분석합니다."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "analyze")

        if action == "analyze":
            return await self._analyze(kwargs)
        elif action == "top_errors":
            return await self._top_errors(kwargs)
        elif action == "timeline":
            return self._timeline(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "analyze, top_errors, timeline 중 하나를 사용하세요."
            )

    # ── 로그 파싱 ──

    @staticmethod
    def _parse_log_file(log_file: str, level: str = "ALL", hours: int = 24) -> list[LogEntry]:
        """로그 파일을 파싱하여 LogEntry 리스트로 변환합니다."""
        path = Path(log_file)
        if not path.exists():
            return []

        cutoff = datetime.now(KST) - timedelta(hours=hours)
        entries: list[LogEntry] = []

        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = LOG_PATTERN.match(line.strip())
            if not m:
                continue

            ts_str, logger_name, log_level, message = m.groups()
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
            except ValueError:
                continue

            if ts < cutoff:
                continue

            if level != "ALL" and log_level != level:
                continue

            entries.append(LogEntry(
                timestamp=ts,
                logger_name=logger_name,
                level=log_level,
                message=message.strip(),
            ))

        return entries

    @staticmethod
    def _normalize_message(message: str) -> str:
        """에러 메시지에서 변수 부분을 제거하여 패턴화합니다."""
        result = message
        for pattern, replacement in NORMALIZE_PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    # ── action 구현 ──

    async def _analyze(self, kwargs: dict[str, Any]) -> str:
        """로그 파일 전체 분석."""
        log_file = kwargs.get("log_file", DEFAULT_LOG_FILE)
        level = kwargs.get("level", "ERROR").upper()
        hours = int(kwargs.get("hours", 24))

        # 전체 레벨 카운트를 위해 ALL로 먼저 파싱
        all_entries = self._parse_log_file(log_file, "ALL", hours)

        if not all_entries:
            path = Path(log_file)
            if not path.exists():
                return f"로그 파일이 없습니다: {log_file}"
            return f"최근 {hours}시간 내 로그가 없습니다."

        # 레벨별 건수
        level_counts = Counter(e.level for e in all_entries)

        # 요청된 레벨만 필터
        if level != "ALL":
            filtered = [e for e in all_entries if e.level == level]
        else:
            filtered = all_entries

        # 모듈별 분포
        module_counts = Counter(e.logger_name for e in filtered)

        # 에러 메시지 그룹핑
        msg_patterns = Counter(self._normalize_message(e.message) for e in filtered)

        lines = [
            f"## 로그 분석 결과",
            f"파일: {log_file} | 기간: 최근 {hours}시간 | 필터: {level}",
            "",
            "### 레벨별 건수",
        ]
        for lvl in ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]:
            cnt = level_counts.get(lvl, 0)
            if cnt > 0:
                lines.append(f"  {lvl}: {cnt:,}건")

        lines.append(f"\n### 필터된 로그 건수: {len(filtered):,}건")

        if module_counts:
            lines.append("\n### 모듈별 분포")
            for mod, cnt in module_counts.most_common(10):
                lines.append(f"  {mod}: {cnt:,}건")

        if msg_patterns:
            lines.append("\n### 에러 메시지 패턴 (상위 10개)")
            for pattern, cnt in msg_patterns.most_common(10):
                lines.append(f"  [{cnt:,}건] {pattern[:100]}")

        result = "\n".join(lines)

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 시스템 운영 전문가입니다.\n"
                "로그 분석 결과를 보고 다음을 정리하세요:\n"
                "1. 에러 근본 원인 추정 (가능한 원인 3가지)\n"
                "2. 수정 우선순위 (가장 시급한 것부터)\n"
                "3. 구체적인 해결 방법 제안\n"
                "한국어로, 비개발자도 이해할 수 있게 작성하세요."
            ),
            user_prompt=result,
        )

        return f"{result}\n\n---\n\n## 원인 분석\n\n{analysis}"

    async def _top_errors(self, kwargs: dict[str, Any]) -> str:
        """가장 많이 발생하는 에러 Top N."""
        log_file = kwargs.get("log_file", DEFAULT_LOG_FILE)
        top_n = int(kwargs.get("top_n", 10))
        hours = int(kwargs.get("hours", 24))

        entries = self._parse_log_file(log_file, "ERROR", hours)
        if not entries:
            return f"최근 {hours}시간 내 ERROR 로그가 없습니다."

        msg_patterns = Counter(self._normalize_message(e.message) for e in entries)

        lines = [f"## 에러 빈도 Top {top_n} (최근 {hours}시간)", ""]
        for rank, (pattern, cnt) in enumerate(msg_patterns.most_common(top_n), 1):
            lines.append(f"{rank}. **[{cnt:,}건]** {pattern[:150]}")

        result = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 시스템 운영 전문가입니다.\n"
                "자주 발생하는 에러 목록을 보고 다음을 정리하세요:\n"
                "1. 각 에러의 가능한 원인\n"
                "2. 해결 우선순위 (빈도와 심각도 고려)\n"
                "3. 구체적인 해결 방법\n"
                "한국어로 답변하세요."
            ),
            user_prompt=result,
        )

        return f"{result}\n\n---\n\n## 분석\n\n{analysis}"

    def _timeline(self, kwargs: dict[str, Any]) -> str:
        """시간대별 에러 발생 빈도를 텍스트 막대 그래프로 표현합니다."""
        log_file = kwargs.get("log_file", DEFAULT_LOG_FILE)
        hours = int(kwargs.get("hours", 24))

        entries = self._parse_log_file(log_file, "ERROR", hours)
        if not entries:
            return f"최근 {hours}시간 내 ERROR 로그가 없습니다."

        # 시간대별 집계
        hour_counts: dict[int, int] = defaultdict(int)
        for e in entries:
            hour_counts[e.timestamp.hour] += 1

        max_count = max(hour_counts.values()) if hour_counts else 1
        bar_max = 30  # 최대 막대 길이

        lines = [
            f"## 시간대별 에러 빈도 (최근 {hours}시간)",
            f"총 에러: {len(entries):,}건",
            "",
        ]

        for h in range(24):
            cnt = hour_counts.get(h, 0)
            bar_len = int((cnt / max_count) * bar_max) if max_count > 0 else 0
            bar = "█" * bar_len
            lines.append(f"{h:02d}시: {bar} ({cnt}건)")

        # 피크 시간대
        if hour_counts:
            peak_hour = max(hour_counts, key=hour_counts.get)  # type: ignore[arg-type]
            lines.append(f"\n⚠️ 피크 시간대: {peak_hour:02d}시 ({hour_counts[peak_hour]}건)")

        return "\n".join(lines)
