"""
에이전트 장기 기억 저장소.

각 에이전트별로 data/memory/{agent_id}.json에 key-value 기억을 저장합니다.
think() 호출 시 관련 기억을 시스템 프롬프트에 자동 주입합니다.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("corthex.memory")


class MemoryEntry:
    """하나의 기억 항목."""

    def __init__(
        self,
        memory_id: str,
        key: str,
        value: str,
        created_at: str | None = None,
        source: str = "manual",
    ) -> None:
        self.memory_id = memory_id
        self.key = key
        self.value = value
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.source = source  # "manual" | "auto"

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MemoryEntry:
        return cls(
            memory_id=d["memory_id"],
            key=d["key"],
            value=d["value"],
            created_at=d.get("created_at"),
            source=d.get("source", "manual"),
        )


class MemoryManager:
    """에이전트별 장기 기억 관리자."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, list[MemoryEntry]] = {}

    def _file_path(self, agent_id: str) -> Path:
        return self._data_dir / f"{agent_id}.json"

    def load(self, agent_id: str) -> list[MemoryEntry]:
        """에이전트의 모든 기억을 로드합니다."""
        if agent_id in self._cache:
            return self._cache[agent_id]

        fp = self._file_path(agent_id)
        if not fp.exists():
            self._cache[agent_id] = []
            return []

        try:
            raw = json.loads(fp.read_text(encoding="utf-8"))
            entries = [MemoryEntry.from_dict(d) for d in raw]
            self._cache[agent_id] = entries
            return entries
        except Exception as e:
            logger.warning("기억 로드 실패 (%s): %s", agent_id, e)
            self._cache[agent_id] = []
            return []

    def _save(self, agent_id: str) -> None:
        """에이전트의 기억을 파일에 저장합니다."""
        entries = self._cache.get(agent_id, [])
        fp = self._file_path(agent_id)
        fp.write_text(
            json.dumps([e.to_dict() for e in entries], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add(
        self,
        agent_id: str,
        key: str,
        value: str,
        source: str = "manual",
    ) -> MemoryEntry:
        """새 기억을 추가합니다."""
        self.load(agent_id)  # ensure cache populated
        entry = MemoryEntry(
            memory_id=str(uuid.uuid4())[:8],
            key=key,
            value=value,
            source=source,
        )
        self._cache[agent_id].append(entry)
        self._save(agent_id)
        logger.info("기억 추가: %s / %s = %s", agent_id, key, value[:50])
        return entry

    def delete(self, agent_id: str, memory_id: str) -> bool:
        """기억을 삭제합니다."""
        self.load(agent_id)
        entries = self._cache.get(agent_id, [])
        before = len(entries)
        self._cache[agent_id] = [e for e in entries if e.memory_id != memory_id]
        if len(self._cache[agent_id]) < before:
            self._save(agent_id)
            return True
        return False

    def get_all(self, agent_id: str) -> list[dict]:
        """에이전트의 모든 기억을 dict 리스트로 반환합니다."""
        return [e.to_dict() for e in self.load(agent_id)]

    def get_context_string(self, agent_id: str) -> str:
        """시스템 프롬프트에 주입할 기억 문자열을 반환합니다."""
        entries = self.load(agent_id)
        if not entries:
            return ""

        lines = []
        for e in entries[-20:]:  # 최근 20개만
            lines.append(f"- {e.key}: {e.value}")

        return (
            "\n\n---\n"
            "## 장기 기억 (이전 작업에서 학습한 내용)\n"
            + "\n".join(lines)
            + "\n---\n"
        )
