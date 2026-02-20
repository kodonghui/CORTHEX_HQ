"""
에러 로그 분석기 도구 (Log Analyzer).

로그 파일을 분석하여 에러 유형, 빈도, 패턴을 자동으로
통계 내고, 시간대별 분포를 텍스트 그래프로 시각화합니다.

사용 방법:
  - action="analyze": 로그 파일 전체 분석 (log_file, level, hours)
  - action="top_errors": 가장 많이 발생하는 에러 Top N (top_n)
  - action="timeline": 시간대별 에러 발생 빈도 (log_file, hours)
  - action="activity": DB 활동 로그 조회 (agent_id, level, keyword, limit)
  - action="trading": 자동매매 관련 활동 로그만 필터 분석 (hours, limit)

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
        elif action == "activity":
            return await self._activity_logs(kwargs)
        elif action == "trading":
            return await self._trading_logs(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "analyze, top_errors, timeline, activity, trading 중 하나를 사용하세요."
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

    @staticmethod
    def _ensure_log_file(log_file: str) -> None:
        """로그 파일이 없으면 디렉토리와 빈 파일을 생성합니다."""
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
            logger.info("[LogAnalyzer] 로그 파일 생성: %s", log_file)

    async def _analyze(self, kwargs: dict[str, Any]) -> str:
        """로그 파일 전체 분석."""
        log_file = kwargs.get("log_file", DEFAULT_LOG_FILE)
        level = kwargs.get("level", "ERROR").upper()
        hours = int(kwargs.get("hours", 24))

        # 로그 파일/디렉토리가 없으면 자동 생성
        self._ensure_log_file(log_file)

        # 전체 레벨 카운트를 위해 ALL로 먼저 파싱
        all_entries = self._parse_log_file(log_file, "ALL", hours)

        if not all_entries:
            return f"최근 {hours}시간 내 로그가 없습니다. (파일: {log_file})"

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

        # 로그 파일/디렉토리가 없으면 자동 생성
        self._ensure_log_file(log_file)

        entries = self._parse_log_file(log_file, "ERROR", hours)
        if not entries:
            return f"최근 {hours}시간 내 ERROR 로그가 없습니다. (파일: {log_file})"

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

        # 로그 파일/디렉토리가 없으면 자동 생성
        self._ensure_log_file(log_file)

        entries = self._parse_log_file(log_file, "ERROR", hours)
        if not entries:
            return f"최근 {hours}시간 내 ERROR 로그가 없습니다. (파일: {log_file})"

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

    # ── DB 활동 로그 분석 ──

    @staticmethod
    def _get_activity_logs(
        agent_id: str | None = None,
        level: str | None = None,
        keyword: str | None = None,
        limit: int = 200,
        hours: int | None = None,
    ) -> list[dict]:
        """DB activity_logs 테이블에서 로그를 조회합니다."""
        try:
            from web.db import get_connection
        except ImportError:
            try:
                import sys
                from pathlib import Path as _P
                sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
                from web.db import get_connection
            except ImportError:
                return []

        conn = get_connection()
        try:
            query = (
                "SELECT agent_id, message, level, time, timestamp, created_at "
                "FROM activity_logs"
            )
            conditions: list[str] = []
            params: list[Any] = []

            if agent_id:
                conditions.append("agent_id = ?")
                params.append(agent_id)
            if level:
                conditions.append("level = ?")
                params.append(level.lower())
            if hours:
                cutoff_ms = int(
                    (datetime.now(KST) - timedelta(hours=hours)).timestamp() * 1000
                )
                conditions.append("timestamp >= ?")
                params.append(cutoff_ms)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            results = [dict(r) for r in rows]

            # 키워드 필터 (SQL LIKE보다 유연한 Python 필터)
            if keyword:
                kw_lower = keyword.lower()
                results = [r for r in results if kw_lower in r.get("message", "").lower()]

            return results
        finally:
            conn.close()

    async def _activity_logs(self, kwargs: dict[str, Any]) -> str:
        """DB 활동 로그를 조회하고 분석합니다."""
        agent_id = kwargs.get("agent_id")
        level = kwargs.get("level")
        keyword = kwargs.get("keyword")
        limit = int(kwargs.get("limit", 100))
        hours = int(kwargs.get("hours", 24)) if kwargs.get("hours") else None

        logs = self._get_activity_logs(
            agent_id=agent_id, level=level, keyword=keyword,
            limit=limit, hours=hours,
        )

        if not logs:
            filter_desc = []
            if agent_id:
                filter_desc.append(f"에이전트={agent_id}")
            if level:
                filter_desc.append(f"레벨={level}")
            if keyword:
                filter_desc.append(f"키워드={keyword}")
            if hours:
                filter_desc.append(f"최근 {hours}시간")
            return f"활동 로그가 없습니다. (필터: {', '.join(filter_desc) or '없음'})"

        # 레벨별 건수
        level_counts = Counter(log.get("level", "info") for log in logs)

        # 에이전트별 건수
        agent_counts = Counter(log.get("agent_id", "unknown") for log in logs)

        lines = [
            "## 활동 로그 분석",
            f"조회 건수: {len(logs):,}건",
        ]
        if agent_id:
            lines.append(f"에이전트 필터: {agent_id}")
        if keyword:
            lines.append(f"키워드 필터: {keyword}")
        if hours:
            lines.append(f"기간: 최근 {hours}시간")

        lines.append("\n### 레벨별 건수")
        for lvl in ["error", "warning", "info"]:
            cnt = level_counts.get(lvl, 0)
            if cnt > 0:
                emoji = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(lvl, "⚪")
                lines.append(f"  {emoji} {lvl}: {cnt:,}건")

        if len(agent_counts) > 1:
            lines.append("\n### 에이전트별 건수")
            for aid, cnt in agent_counts.most_common(10):
                lines.append(f"  {aid}: {cnt:,}건")

        # 최근 로그 목록 (최대 30건)
        lines.append(f"\n### 최근 로그 (최대 30건)")
        for log in logs[:30]:
            lvl_icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(
                log.get("level", ""), "⚪"
            )
            lines.append(
                f"  {lvl_icon} [{log.get('time', '')}] "
                f"({log.get('agent_id', '')}) {log.get('message', '')[:120]}"
            )

        result = "\n".join(lines)

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 CORTHEX HQ 시스템 운영 전문가입니다.\n"
                "활동 로그를 분석하여 다음을 정리하세요:\n"
                "1. 전체 흐름 요약 (무슨 일이 있었는지)\n"
                "2. 에러나 경고가 있다면 원인 추정\n"
                "3. 개선 제안\n"
                "한국어로, CEO(비개발자)도 이해할 수 있게 작성하세요."
            ),
            user_prompt=result,
        )

        return f"{result}\n\n---\n\n## AI 분석\n\n{analysis}"

    async def _trading_logs(self, kwargs: dict[str, Any]) -> str:
        """자동매매 관련 활동 로그만 필터하여 상세 분석합니다."""
        hours = int(kwargs.get("hours", 24))
        limit = int(kwargs.get("limit", 200))

        # CIO 에이전트 + 시스템의 매매 관련 로그 수집
        cio_logs = self._get_activity_logs(
            agent_id="cio_manager", limit=limit, hours=hours,
        )
        system_trading_logs = self._get_activity_logs(
            agent_id="system", keyword="매매", limit=limit, hours=hours,
        )
        system_trading_logs += self._get_activity_logs(
            agent_id="system", keyword="trading", limit=limit, hours=hours,
        )

        # 중복 제거 (timestamp 기준)
        seen_ts = set()
        all_logs = []
        for log in cio_logs + system_trading_logs:
            ts = log.get("timestamp", 0)
            if ts not in seen_ts:
                seen_ts.add(ts)
                all_logs.append(log)

        # 시간순 정렬 (오래된 순 → 흐름 파악 용이)
        all_logs.sort(key=lambda x: x.get("timestamp", 0))

        if not all_logs:
            return f"최근 {hours}시간 내 자동매매 관련 로그가 없습니다."

        # 분류
        errors = [l for l in all_logs if l.get("level") == "error"]
        warnings = [l for l in all_logs if l.get("level") == "warning"]
        orders = [l for l in all_logs if any(
            kw in l.get("message", "") for kw in ["KIS 주문", "매수 성공", "매도 성공", "주문 실패", "주문 전송"]
        )]
        skipped = [l for l in all_logs if "건너뜀" in l.get("message", "") or "부족" in l.get("message", "")]
        analysis_starts = [l for l in all_logs if "분석 시작" in l.get("message", "")]

        lines = [
            f"## 자동매매 로그 분석 (최근 {hours}시간)",
            f"전체 로그: {len(all_logs):,}건",
            f"  - 🔴 에러: {len(errors)}건",
            f"  - 🟡 경고: {len(warnings)}건",
            f"  - 📊 분석 시작: {len(analysis_starts)}건",
            f"  - 🎯 주문 시도: {len(orders)}건",
            f"  - ⏭️ 건너뜀: {len(skipped)}건",
        ]

        if errors:
            lines.append("\n### 🔴 에러 목록 (매매 실패 원인)")
            for log in errors:
                lines.append(
                    f"  [{log.get('time', '')}] {log.get('message', '')[:150]}"
                )

        if warnings:
            lines.append("\n### 🟡 경고 목록")
            for log in warnings[:10]:
                lines.append(
                    f"  [{log.get('time', '')}] {log.get('message', '')[:150]}"
                )

        if skipped:
            lines.append("\n### ⏭️ 건너뛴 시그널 (왜 매매가 안 됐는지)")
            for log in skipped:
                lines.append(
                    f"  [{log.get('time', '')}] {log.get('message', '')[:150]}"
                )

        if orders:
            lines.append("\n### 🎯 실제 주문 내역")
            for log in orders:
                lines.append(
                    f"  [{log.get('time', '')}] {log.get('message', '')[:150]}"
                )

        # 전체 시간순 흐름 (최대 50건)
        lines.append(f"\n### 📋 전체 흐름 (시간순, 최대 50건)")
        for log in all_logs[:50]:
            lvl_icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(
                log.get("level", ""), "⚪"
            )
            lines.append(
                f"  {lvl_icon} [{log.get('time', '')}] {log.get('message', '')[:120]}"
            )

        result = "\n".join(lines)

        # LLM 분석 — 매매 실패 원인 특화
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 CORTHEX HQ 자동매매 시스템 전문가입니다.\n"
                "아래 매매 로그를 분석하여 다음을 정리하세요:\n"
                "1. **매매가 실행됐는지 여부** — 실제 주문이 나갔는지\n"
                "2. **실패 원인** — 왜 매매가 안 됐는지 (에러, 신뢰도 부족, KIS 미연결 등)\n"
                "3. **흐름 재구성** — 버튼 클릭 → 분석 → 시그널 → 주문까지 어디서 끊겼는지\n"
                "4. **해결 방법** — 구체적 조치 사항\n"
                "한국어로, CEO(비개발자)도 이해할 수 있게 쉽게 작성하세요.\n"
                "기술 용어는 괄호 안에 설명을 넣으세요."
            ),
            user_prompt=result,
        )

        return f"{result}\n\n---\n\n## AI 진단\n\n{analysis}"
