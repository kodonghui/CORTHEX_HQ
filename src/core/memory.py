"""
에이전트 장기 기억 저장소.

SQLite DB (corthex.db)에 저장 — 배포 시 데이터 유지됨.
기존 JSON 파일(data/memory/{agent_id}.json)이 있으면 자동 마이그레이션.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("corthex.memory")


def _get_db_path() -> str:
    """환경에 맞는 DB 경로를 반환합니다 (web/db.py와 동일한 로직)."""
    env_path = os.getenv("CORTHEX_DB_PATH")
    if env_path:
        return env_path
    if os.path.isdir("/home/ubuntu"):
        return "/home/ubuntu/corthex.db"
    # src/core/memory.py → 두 단계 위로 = 프로젝트 루트
    project_root = Path(__file__).parent.parent.parent
    return str(project_root / "corthex_dev.db")


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

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> MemoryEntry:
        return cls(
            memory_id=row["memory_id"],
            key=row["key"],
            value=row["value"],
            created_at=row["created_at"],
            source=row["source"],
        )


class MemoryManager:
    """에이전트별 장기 기억 관리자 — SQLite 기반.

    기존 JSON 방식에서 SQLite로 교체됨 (2026-02-18).
    공개 API는 동일 — app.py / agent.py 수정 불필요.
    """

    def __init__(self, data_dir: Path) -> None:
        # data_dir은 JSON 마이그레이션용으로 보존 (기존 호출부 호환)
        self._data_dir = data_dir
        self._db_path = _get_db_path()
        self._ensure_table()
        self._migrate_json_if_needed(data_dir)

    # ── 내부 헬퍼 ──────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _ensure_table(self) -> None:
        """memories 테이블이 없으면 생성합니다."""
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id    TEXT NOT NULL,
                    memory_id   TEXT NOT NULL,
                    key         TEXT NOT NULL,
                    value       TEXT NOT NULL,
                    source      TEXT NOT NULL DEFAULT 'manual',
                    created_at  TEXT NOT NULL,
                    UNIQUE(agent_id, memory_id)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id)"
            )
            conn.commit()
        except Exception as e:
            logger.warning("memories 테이블 생성 실패: %s", e)
        finally:
            conn.close()

    def _migrate_json_if_needed(self, data_dir: Path) -> None:
        """기존 JSON 파일을 DB로 일회성 마이그레이션합니다.

        agent_id별로 DB에 이미 데이터가 있으면 스킵하므로 중복 없음.
        """
        if not data_dir or not data_dir.exists():
            return
        for fp in data_dir.glob("*.json"):
            agent_id = fp.stem
            conn = self._get_conn()
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE agent_id = ?", (agent_id,)
                ).fetchone()[0]
                if count > 0:
                    continue  # 이미 마이그레이션됨
                raw = json.loads(fp.read_text(encoding="utf-8"))
                for d in raw:
                    entry = MemoryEntry.from_dict(d)
                    conn.execute(
                        "INSERT OR IGNORE INTO memories "
                        "(agent_id, memory_id, key, value, source, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (agent_id, entry.memory_id, entry.key, entry.value,
                         entry.source, entry.created_at),
                    )
                conn.commit()
                logger.info("기억 JSON→DB 마이그레이션: %s (%d건)", agent_id, len(raw))
            except Exception as e:
                logger.warning("기억 마이그레이션 실패 (%s): %s", agent_id, e)
            finally:
                conn.close()

    # ── 공개 API ───────────────────────────────────────────────────────────

    def load(self, agent_id: str) -> list[MemoryEntry]:
        """에이전트의 모든 기억을 로드합니다."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM memories WHERE agent_id = ? ORDER BY created_at",
                (agent_id,),
            ).fetchall()
            return [MemoryEntry.from_row(row) for row in rows]
        except Exception as e:
            logger.warning("기억 로드 실패 (%s): %s", agent_id, e)
            return []
        finally:
            conn.close()

    def add(
        self,
        agent_id: str,
        key: str,
        value: str,
        source: str = "manual",
    ) -> MemoryEntry:
        """새 기억을 추가합니다."""
        entry = MemoryEntry(
            memory_id=str(uuid.uuid4())[:8],
            key=key,
            value=value,
            source=source,
        )
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO memories "
                "(agent_id, memory_id, key, value, source, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (agent_id, entry.memory_id, entry.key, entry.value,
                 entry.source, entry.created_at),
            )
            conn.commit()
        except Exception as e:
            logger.warning("기억 추가 실패 (%s): %s", agent_id, e)
        finally:
            conn.close()
        logger.info("기억 추가: %s / %s = %s", agent_id, key, value[:50])
        return entry

    def delete(self, agent_id: str, memory_id: str) -> bool:
        """기억을 삭제합니다."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM memories WHERE agent_id = ? AND memory_id = ?",
                (agent_id, memory_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.warning("기억 삭제 실패 (%s): %s", agent_id, e)
            return False
        finally:
            conn.close()

    def get_all(self, agent_id: str) -> list[dict]:
        """에이전트의 모든 기억을 dict 리스트로 반환합니다."""
        return [e.to_dict() for e in self.load(agent_id)]

    def get_context_string(self, agent_id: str) -> str:
        """시스템 프롬프트에 주입할 기억 문자열을 반환합니다."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT key, value FROM memories "
                "WHERE agent_id = ? ORDER BY created_at DESC LIMIT 20",
                (agent_id,),
            ).fetchall()
        except Exception:
            return ""
        finally:
            conn.close()

        if not rows:
            return ""

        lines = [f"- {row['key']}: {row['value']}" for row in reversed(rows)]
        return (
            "\n\n---\n"
            "## 장기 기억 (이전 작업에서 학습한 내용)\n"
            + "\n".join(lines)
            + "\n---\n"
        )
