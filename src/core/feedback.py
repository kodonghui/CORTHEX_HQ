"""
CEO Feedback System for CORTHEX HQ.

CEO can rate task results (good/bad) with optional comments.
Feedback is persisted to SQLite DB (settings 테이블) and provides per-agent statistics.
기존 JSON 파일(data/feedback.json)이 있으면 자동 마이그레이션.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("corthex.feedback")


@dataclass
class FeedbackEntry:
    correlation_id: str
    rating: str  # "good" or "bad"
    comment: str = ""
    agent_id: str = ""  # primary responding agent
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class FeedbackManager:
    """Manages CEO feedback on task results.

    SQLite DB (save_setting/load_setting)에 저장.
    기존 JSON 파일이 있으면 최초 1회 자동 마이그레이션.
    """

    _SETTING_KEY = "feedback_entries"

    def __init__(self, data_path: Path) -> None:
        # data_path는 기존 JSON 마이그레이션용으로 보존 (호출부 호환)
        self._legacy_path = data_path
        self._entries: list[FeedbackEntry] = []
        self._load()

    def _load(self) -> None:
        """DB에서 피드백 로드. 없으면 JSON 파일에서 마이그레이션."""
        try:
            from web.db import load_setting
            raw = load_setting(self._SETTING_KEY, None)
            if raw is not None:
                for item in raw:
                    self._entries.append(FeedbackEntry(**item))
                logger.info("피드백 %d건 로드 (DB)", len(self._entries))
                return
        except Exception as e:
            logger.warning("피드백 DB 로드 실패: %s", e)

        # DB에 없으면 기존 JSON 파일에서 마이그레이션
        if self._legacy_path and self._legacy_path.exists():
            try:
                raw_json = json.loads(self._legacy_path.read_text(encoding="utf-8"))
                for item in raw_json.get("feedback", []):
                    self._entries.append(FeedbackEntry(**item))
                logger.info("피드백 JSON→DB 마이그레이션: %d건", len(self._entries))
                self._save()  # DB에 저장
            except Exception as e:
                logger.warning("피드백 JSON 마이그레이션 실패: %s", e)

    def _save(self) -> None:
        """피드백을 DB에 저장."""
        try:
            from web.db import save_setting
            save_setting(self._SETTING_KEY, [asdict(e) for e in self._entries])
        except Exception as e:
            logger.warning("피드백 DB 저장 실패: %s", e)

    def add(
        self,
        correlation_id: str,
        rating: str,
        comment: str = "",
        agent_id: str = "",
    ) -> None:
        """Record a feedback entry."""
        entry = FeedbackEntry(
            correlation_id=correlation_id,
            rating=rating,
            comment=comment,
            agent_id=agent_id,
        )
        self._entries.append(entry)
        self._save()

    @property
    def total_count(self) -> int:
        return len(self._entries)

    @property
    def good_count(self) -> int:
        return sum(1 for e in self._entries if e.rating == "good")

    @property
    def bad_count(self) -> int:
        return sum(1 for e in self._entries if e.rating == "bad")

    @property
    def satisfaction_rate(self) -> float:
        if not self._entries:
            return 0.0
        return self.good_count / len(self._entries) * 100

    def stats_by_agent(self) -> dict[str, dict]:
        """Per-agent feedback statistics."""
        stats: dict[str, dict] = {}
        for e in self._entries:
            aid = e.agent_id or "unknown"
            if aid not in stats:
                stats[aid] = {"good": 0, "bad": 0, "total": 0}
            stats[aid]["total"] += 1
            if e.rating == "good":
                stats[aid]["good"] += 1
            else:
                stats[aid]["bad"] += 1

        # Add satisfaction rate
        for aid, s in stats.items():
            s["satisfaction_pct"] = (
                round(s["good"] / s["total"] * 100, 1) if s["total"] > 0 else 0.0
            )

        return stats

    def recent(self, limit: int = 10) -> list[FeedbackEntry]:
        return self._entries[-limit:]

    def to_dict(self) -> dict:
        return {
            "total": self.total_count,
            "good": self.good_count,
            "bad": self.bad_count,
            "satisfaction_rate": round(self.satisfaction_rate, 1),
            "by_agent": self.stats_by_agent(),
            "recent": [asdict(e) for e in self.recent()],
        }
