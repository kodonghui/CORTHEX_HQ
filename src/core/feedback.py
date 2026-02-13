"""
CEO Feedback System for CORTHEX HQ.

CEO can rate task results (good/bad) with optional comments.
Feedback is persisted to a JSON file and provides per-agent statistics.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
    """Manages CEO feedback on task results."""

    def __init__(self, data_path: Path) -> None:
        self._path = data_path
        self._entries: list[FeedbackEntry] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                for item in raw.get("feedback", []):
                    self._entries.append(FeedbackEntry(**item))
                logger.info("피드백 %d건 로드", len(self._entries))
            except Exception as e:
                logger.warning("피드백 로드 실패: %s", e)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"feedback": [asdict(e) for e in self._entries]}
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
