"""
CORTHEX HQ - SQLite Database Module

모든 데이터 영속화를 담당합니다.
- 서버 환경: /home/ubuntu/corthex.db
- 로컬 개발: ./corthex_dev.db
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

KST = timezone(timedelta(hours=9))


# ── DB 경로 결정 ──

def _get_db_path() -> str:
    """환경에 맞는 DB 경로를 반환합니다."""
    # 1순위: 환경변수로 직접 지정
    env_path = os.getenv("CORTHEX_DB_PATH")
    if env_path:
        return env_path
    # 2순위: 서버 환경 (/home/ubuntu/corthex.db)
    if os.path.isdir("/home/ubuntu"):
        return "/home/ubuntu/corthex.db"
    # 3순위: 로컬 개발 (프로젝트 루트)
    project_root = Path(__file__).parent.parent
    return str(project_root / "corthex_dev.db")


DB_PATH = _get_db_path()


# ── DB 연결 ──

def get_connection() -> sqlite3.Connection:
    """새 DB 연결을 생성합니다. WAL 모드 + Row 팩토리."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# ── 스키마 ──

_SCHEMA_SQL = """
-- 메시지 테이블: CEO가 보낸 원본 메시지 저장
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL DEFAULT 'telegram',
    chat_id         TEXT,
    text            TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    task_id         TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_task_id ON messages(task_id);

-- 작업 테이블: 모든 작업 기록
CREATE TABLE IF NOT EXISTS tasks (
    task_id         TEXT PRIMARY KEY,
    command         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    completed_at    TEXT,
    result_data     TEXT,
    result_summary  TEXT,
    success         INTEGER,
    cost_usd        REAL NOT NULL DEFAULT 0.0,
    tokens_used     INTEGER NOT NULL DEFAULT 0,
    time_seconds    REAL NOT NULL DEFAULT 0.0,
    bookmarked      INTEGER NOT NULL DEFAULT 0,
    correlation_id  TEXT,
    source          TEXT NOT NULL DEFAULT 'websocket',
    agent_id        TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_bookmarked ON tasks(bookmarked);

-- 활동 로그 테이블: 에이전트 활동 기록
CREATE TABLE IF NOT EXISTS activity_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        TEXT NOT NULL,
    message         TEXT NOT NULL,
    level           TEXT NOT NULL DEFAULT 'info',
    time            TEXT NOT NULL,
    timestamp       INTEGER NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp ON activity_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_activity_logs_agent_id ON activity_logs(agent_id);

-- 아카이브 테이블: 보고서 아카이브
CREATE TABLE IF NOT EXISTS archives (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    division        TEXT NOT NULL,
    filename        TEXT NOT NULL,
    content         TEXT NOT NULL,
    correlation_id  TEXT,
    agent_id        TEXT,
    created_at      TEXT NOT NULL,
    size            INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_archives_division ON archives(division);
CREATE INDEX IF NOT EXISTS idx_archives_created_at ON archives(created_at);

-- 설정 테이블: 키-값 저장소 (프리셋, 예약, 워크플로우, 예산 등 모든 웹 데이터)
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 대화 기록 테이블: 웹 채팅 메시지 저장
CREATE TABLE IF NOT EXISTS conversation_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    type            TEXT NOT NULL,
    text            TEXT,
    content         TEXT,
    sender_id       TEXT,
    handled_by      TEXT,
    delegation      TEXT,
    model           TEXT,
    time_seconds    REAL,
    cost            REAL,
    quality_score   REAL,
    task_id         TEXT,
    source          TEXT DEFAULT 'web',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversation_created_at ON conversation_messages(created_at);

-- 에이전트별 AI 호출 기록 테이블: 전력분석용
CREATE TABLE IF NOT EXISTS agent_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        TEXT NOT NULL,
    task_id         TEXT,
    model           TEXT,
    provider        TEXT,
    cost_usd        REAL NOT NULL DEFAULT 0.0,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    time_seconds    REAL NOT NULL DEFAULT 0.0,
    success         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_calls_agent_id ON agent_calls(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_calls_created_at ON agent_calls(created_at);

-- 비동기 작업 테이블: 장시간 실행 작업 추적 (토론, 배치 등)
CREATE TABLE IF NOT EXISTS async_tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',
    agent_id        TEXT,
    prompt          TEXT NOT NULL,
    result          TEXT,
    progress        INTEGER DEFAULT 0,
    progress_message TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at      DATETIME,
    completed_at    DATETIME,
    output_channels TEXT DEFAULT '["chat"]'
);

CREATE INDEX IF NOT EXISTS idx_async_tasks_status ON async_tasks(status);
CREATE INDEX IF NOT EXISTS idx_async_tasks_task_id ON async_tasks(task_id);
"""


def init_db() -> None:
    """테이블이 없으면 생성합니다. 서버 시작 시 1회 호출."""
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        # tasks 테이블에 신규 컬럼 추가 (기존 DB 호환 — 없으면 추가)
        _migrate_columns = [
            ("tags", "TEXT NOT NULL DEFAULT '[]'"),
            ("is_read", "INTEGER NOT NULL DEFAULT 0"),
            ("archived", "INTEGER NOT NULL DEFAULT 0"),
        ]
        for col_name, col_def in _migrate_columns:
            try:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_def}")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # 이미 존재하면 무시
        print(f"[DB] 초기화 완료: {DB_PATH}")
    except Exception as e:
        print(f"[DB] 초기화 실패: {e}")
    finally:
        conn.close()


# ── 유틸리티 ──

def _now_iso() -> str:
    """현재 시간을 ISO 8601 형식으로 반환 (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _now_kst() -> datetime:
    """현재 KST 시간 객체 반환."""
    return datetime.now(KST)


def _gen_task_id() -> str:
    """짧은 작업 ID 생성 (8자리)."""
    return str(uuid.uuid4())[:8]


def _row_to_task(row: sqlite3.Row) -> dict:
    """sqlite3.Row를 프론트엔드가 기대하는 task dict로 변환."""
    # 신규 컬럼이 없는 이전 DB와 호환
    tags_raw = ""
    is_read = 0
    archived = 0
    try:
        tags_raw = row["tags"]
        is_read = row["is_read"]
        archived = row["archived"]
    except (IndexError, KeyError):
        pass
    try:
        tags = json.loads(tags_raw) if tags_raw else []
    except (json.JSONDecodeError, TypeError):
        tags = []
    return {
        "task_id": row["task_id"],
        "command": row["command"],
        "status": row["status"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
        "summary": row["result_summary"] or "",
        "time_seconds": row["time_seconds"],
        "cost": row["cost_usd"],
        "bookmarked": bool(row["bookmarked"]),
        "correlation_id": row["correlation_id"],
        "source": row["source"],
        "agent_id": row["agent_id"],
        "tags": tags,
        "is_read": bool(is_read),
        "archived": bool(archived),
    }


def _row_to_task_detail(row: sqlite3.Row) -> dict:
    """sqlite3.Row를 상세 task dict로 변환 (result_data 포함)."""
    d = _row_to_task(row)
    d["result_data"] = row["result_data"] or ""
    d["success"] = bool(row["success"]) if row["success"] is not None else None
    d["tokens_used"] = row["tokens_used"]
    return d


# ── Messages CRUD ──

def save_message(text: str, source: str = "telegram",
                 chat_id: str = None, task_id: str = None) -> int:
    """메시지를 저장합니다. 반환: row id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO messages (source, chat_id, text, created_at, task_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (source, chat_id, text, _now_iso(), task_id),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# ── Tasks CRUD ──

def create_task(command: str, source: str = "websocket") -> dict:
    """새 작업을 생성합니다. 반환: task dict."""
    task_id = _gen_task_id()
    now = _now_iso()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO tasks (task_id, command, status, created_at, source) "
            "VALUES (?, ?, 'pending', ?, ?)",
            (task_id, command, now, source),
        )
        conn.commit()
        return {
            "task_id": task_id,
            "command": command,
            "status": "pending",
            "created_at": now,
            "source": source,
        }
    finally:
        conn.close()


def get_task(task_id: str) -> Optional[dict]:
    """작업 상세 조회."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if not row:
            return None
        return _row_to_task_detail(row)
    finally:
        conn.close()


def update_task(task_id: str, **kwargs) -> None:
    """작업 상태/결과를 업데이트합니다."""
    if not kwargs:
        return
    # status가 completed/failed이면 completed_at 자동 설정
    if kwargs.get("status") in ("completed", "failed") and "completed_at" not in kwargs:
        kwargs["completed_at"] = _now_iso()
    if kwargs.get("status") == "running" and "started_at" not in kwargs:
        kwargs["started_at"] = _now_iso()

    allowed = {
        "status", "started_at", "completed_at", "result_data",
        "result_summary", "success", "cost_usd", "tokens_used",
        "time_seconds", "bookmarked", "correlation_id", "agent_id",
    }
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    if not filtered:
        return

    set_clause = ", ".join(f"{k} = ?" for k in filtered)
    values = list(filtered.values()) + [task_id]

    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE task_id = ?", values
        )
        conn.commit()
    finally:
        conn.close()


def list_tasks(keyword: str = "", status: str = "",
               bookmarked: bool = False, limit: int = 50,
               archived: bool = False, tag: str = "") -> list:
    """작업 목록 조회 (검색/필터/페이징)."""
    conn = get_connection()
    try:
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if keyword:
            query += " AND (command LIKE ? OR result_summary LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if status and status != "all":
            query += " AND status = ?"
            params.append(status)
        if bookmarked:
            query += " AND bookmarked = 1"
        # 아카이브 필터: 기본적으로 아카이브 안 된 것만 보여줌
        try:
            if archived:
                query += " AND archived = 1"
            else:
                query += " AND (archived = 0 OR archived IS NULL)"
        except Exception:
            pass  # archived 컬럼이 없는 이전 DB 호환
        if tag:
            query += " AND tags LIKE ?"
            params.append(f'%"{tag}"%')
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [_row_to_task(r) for r in rows]
    finally:
        conn.close()


def delete_task(task_id: str) -> bool:
    """작업을 삭제합니다."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def bulk_delete_tasks(task_ids: list) -> int:
    """여러 작업을 한번에 삭제합니다. 반환: 삭제된 수."""
    if not task_ids:
        return 0
    conn = get_connection()
    try:
        placeholders = ",".join(["?"] * len(task_ids))
        cur = conn.execute(f"DELETE FROM tasks WHERE task_id IN ({placeholders})", task_ids)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def bulk_archive_tasks(task_ids: list, archive: bool = True) -> int:
    """여러 작업을 아카이브(보관)합니다. 반환: 변경된 수."""
    if not task_ids:
        return 0
    conn = get_connection()
    try:
        placeholders = ",".join(["?"] * len(task_ids))
        val = 1 if archive else 0
        cur = conn.execute(
            f"UPDATE tasks SET archived = ? WHERE task_id IN ({placeholders})",
            [val] + task_ids,
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def set_task_tags(task_id: str, tags: list) -> bool:
    """작업에 태그를 설정합니다."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE tasks SET tags = ? WHERE task_id = ?",
            (json.dumps(tags, ensure_ascii=False), task_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def mark_task_read(task_id: str, is_read: bool = True) -> bool:
    """작업을 읽음/안읽음으로 표시합니다."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE tasks SET is_read = ? WHERE task_id = ?",
            (1 if is_read else 0, task_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def bulk_mark_read(task_ids: list, is_read: bool = True) -> int:
    """여러 작업을 읽음/안읽음으로 표시합니다."""
    if not task_ids:
        return 0
    conn = get_connection()
    try:
        placeholders = ",".join(["?"] * len(task_ids))
        val = 1 if is_read else 0
        cur = conn.execute(
            f"UPDATE tasks SET is_read = ? WHERE task_id IN ({placeholders})",
            [val] + task_ids,
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def toggle_bookmark(task_id: str) -> bool:
    """북마크를 토글합니다. 반환: 새 상태."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT bookmarked FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if not row:
            return False
        new_val = 0 if row["bookmarked"] else 1
        conn.execute(
            "UPDATE tasks SET bookmarked = ? WHERE task_id = ?",
            (new_val, task_id),
        )
        conn.commit()
        return bool(new_val)
    finally:
        conn.close()


# ── Dashboard Stats ──

def get_dashboard_stats() -> dict:
    """대시보드 통계를 반환합니다."""
    conn = get_connection()
    try:
        today = _now_kst().strftime("%Y-%m-%d")
        today_start = f"{today}T00:00:00"

        today_total = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_at >= ?", (today_start,)
        ).fetchone()[0]
        today_completed = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_at >= ? AND status = 'completed'",
            (today_start,),
        ).fetchone()[0]
        today_failed = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_at >= ? AND status = 'failed'",
            (today_start,),
        ).fetchone()[0]
        running = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'running'"
        ).fetchone()[0]
        cost_row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM tasks"
        ).fetchone()
        tokens_row = conn.execute(
            "SELECT COALESCE(SUM(tokens_used), 0) FROM tasks"
        ).fetchone()
        recent_rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 'completed' "
            "ORDER BY completed_at DESC LIMIT 5"
        ).fetchall()

        return {
            "today_task_count": today_total,
            "today_completed": today_completed,
            "today_failed": today_failed,
            "running_count": running,
            "total_cost": round(cost_row[0], 6),
            "total_tokens": tokens_row[0],
            "recent_completed": [_row_to_task(r) for r in recent_rows],
        }
    finally:
        conn.close()


# ── Activity Logs CRUD ──

def save_activity_log(agent_id: str, message: str,
                      level: str = "info", time_str: str = None) -> dict:
    """활동 로그를 DB에 저장합니다."""
    now = _now_kst()
    if not time_str:
        time_str = now.strftime("%H:%M:%S")
    ts = int(now.timestamp() * 1000)
    created = _now_iso()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO activity_logs (agent_id, message, level, time, timestamp, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (agent_id, message, level, time_str, ts, created),
        )
        conn.commit()
        # 자동 정리: 1000건 초과 시 오래된 것 삭제
        count = conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0]
        if count > 1000:
            conn.execute(
                "DELETE FROM activity_logs WHERE id NOT IN "
                "(SELECT id FROM activity_logs ORDER BY timestamp DESC LIMIT 1000)"
            )
            conn.commit()
        return {
            "agent_id": agent_id,
            "message": message,
            "level": level,
            "time": time_str,
            "timestamp": ts,
        }
    finally:
        conn.close()


def list_activity_logs(limit: int = 50, agent_id: str = None) -> list:
    """활동 로그를 조회합니다."""
    conn = get_connection()
    try:
        query = "SELECT agent_id, message, level, time, timestamp FROM activity_logs"
        params = []
        if agent_id:
            query += " WHERE agent_id = ?"
            params.append(agent_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Archives CRUD ──

def save_archive(division: str, filename: str, content: str,
                 correlation_id: str = None, agent_id: str = None) -> int:
    """아카이브 보고서를 저장합니다. 반환: row id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO archives (division, filename, content, correlation_id, "
            "agent_id, created_at, size) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (division, filename, content, correlation_id, agent_id,
             _now_iso(), len(content)),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_archives(division: str = None, limit: int = 100) -> list:
    """아카이브 목록을 조회합니다."""
    conn = get_connection()
    try:
        query = "SELECT division, filename, agent_id, created_at, size FROM archives"
        params = []
        if division and division != "all":
            query += " WHERE division = ?"
            params.append(division)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_archive(division: str, filename: str) -> Optional[dict]:
    """아카이브 보고서를 조회합니다."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM archives WHERE division = ? AND filename = ?",
            (division, filename),
        ).fetchone()
        if not row:
            return None
        return {
            "division": row["division"],
            "filename": row["filename"],
            "content": row["content"],
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


def delete_archive(division: str, filename: str) -> bool:
    """아카이브 보고서를 삭제합니다. 반환: 삭제 성공 여부."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM archives WHERE division = ? AND filename = ?",
            (division, filename),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ── Settings (키-값 저장소) ──

def get_today_cost() -> float:
    """오늘(KST 기준) 사용한 총 AI 비용을 반환합니다 (USD).

    tasks 테이블과 agent_calls 테이블 양쪽의 비용을 합산합니다.
    """
    conn = get_connection()
    try:
        today = _now_kst().strftime("%Y-%m-%d")
        today_start = f"{today}T00:00:00"
        # tasks 테이블 비용
        task_row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM tasks WHERE created_at >= ?",
            (today_start,),
        ).fetchone()
        task_cost = task_row[0]
        # agent_calls 테이블 비용
        try:
            ac_row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM agent_calls WHERE created_at >= ?",
                (today_start,),
            ).fetchone()
            agent_cost = ac_row[0]
        except Exception:
            agent_cost = 0.0
        return round(task_cost + agent_cost, 6)
    except Exception:
        return 0.0
    finally:
        conn.close()


def save_setting(key: str, value) -> None:
    """설정값을 DB에 저장합니다. value는 JSON 직렬화됩니다."""
    conn = get_connection()
    try:
        json_value = json.dumps(value, ensure_ascii=False)
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) "
            "VALUES (?, ?, ?)",
            (key, json_value, _now_iso()),
        )
        conn.commit()
    except sqlite3.OperationalError:
        # settings 테이블이 아직 생성되지 않은 경우 — init_db() 후 재시도됨
        pass
    finally:
        conn.close()


def load_setting(key: str, default=None):
    """DB에서 설정값을 조회합니다. 없으면 default 반환."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row:
            return json.loads(row[0])
        return default
    except sqlite3.OperationalError:
        # settings 테이블이 아직 생성되지 않은 경우 (init_db 호출 전)
        return default
    finally:
        conn.close()


# ── Conversation Messages CRUD ──

def save_conversation_message(message_type: str, **kwargs) -> int:
    """대화 메시지를 DB에 저장합니다. 반환: row id."""
    conn = get_connection()
    try:
        # 허용된 필드만 필터링
        allowed = {
            "text", "content", "sender_id", "handled_by", "delegation",
            "model", "time_seconds", "cost", "quality_score", "task_id", "source"
        }
        filtered = {k: v for k, v in kwargs.items() if k in allowed}

        # 컬럼과 값 준비
        columns = ["type", "created_at"] + list(filtered.keys())
        values = [message_type, _now_iso()] + list(filtered.values())
        placeholders = ", ".join(["?"] * len(columns))

        cur = conn.execute(
            f"INSERT INTO conversation_messages ({', '.join(columns)}) VALUES ({placeholders})",
            values
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.OperationalError:
        # conversation_messages 테이블이 아직 없는 경우 (init_db 전)
        return 0
    finally:
        conn.close()


def load_conversation_messages(limit: int = 100) -> list:
    """DB에서 대화 기록을 조회합니다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM conversation_messages ORDER BY created_at ASC LIMIT ?",
            (limit,)
        ).fetchall()

        messages = []
        for row in rows:
            msg = {"type": row["type"], "timestamp": row["created_at"]}
            # type에 따라 필요한 필드만 추가
            if row["type"] == "user":
                msg["text"] = row["text"]
                if row["source"]:
                    msg["source"] = row["source"]
            elif row["type"] == "result":
                msg.update({
                    "content": row["content"],
                    "sender_id": row["sender_id"],
                    "handled_by": row["handled_by"],
                    "delegation": row["delegation"] or "",
                    "model": row["model"] or "",
                    "time_seconds": row["time_seconds"],
                    "cost": row["cost"],
                    "quality_score": row["quality_score"],
                    "task_id": row["task_id"] or "",
                    "collapsed": False,
                    "feedbackSent": False,
                    "feedbackRating": None,
                    "source": row["source"] or "web",
                })
            messages.append(msg)
        return messages
    except sqlite3.OperationalError:
        # conversation_messages 테이블이 아직 없는 경우
        return []
    finally:
        conn.close()


def clear_conversation_messages() -> None:
    """대화 기록을 모두 삭제합니다."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM conversation_messages")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


# ── Agent Calls CRUD ──

def save_agent_call(agent_id: str, task_id: str | None = None,
                    model: str | None = None, provider: str | None = None,
                    cost_usd: float = 0.0, input_tokens: int = 0,
                    output_tokens: int = 0, time_seconds: float = 0.0,
                    success: int = 1) -> int:
    """에이전트 AI 호출 1건을 기록합니다."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO agent_calls
               (agent_id, task_id, model, provider, cost_usd,
                input_tokens, output_tokens, time_seconds, success, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (agent_id, task_id, model, provider, cost_usd,
             input_tokens, output_tokens, time_seconds, success,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_agent_performance() -> list[dict]:
    """agent_calls 테이블에서 에이전트별 통계를 집계합니다."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT agent_id,
                   COUNT(*) as call_count,
                   COALESCE(SUM(cost_usd), 0) as total_cost,
                   COALESCE(AVG(time_seconds), 0) as avg_time,
                   COALESCE(SUM(input_tokens), 0) as total_input,
                   COALESCE(SUM(output_tokens), 0) as total_output,
                   ROUND(AVG(success) * 100, 1) as success_rate
            FROM agent_calls
            GROUP BY agent_id
            ORDER BY total_cost DESC
        """).fetchall()
        return [
            {
                "agent_id": r[0],
                "call_count": r[1],
                "total_cost": round(r[2], 6),
                "avg_time": round(r[3], 2),
                "total_input_tokens": r[4],
                "total_output_tokens": r[5],
                "success_rate": r[6],
            }
            for r in rows
        ]
    finally:
        conn.close()
