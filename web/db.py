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
"""


def init_db() -> None:
    """테이블이 없으면 생성합니다. 서버 시작 시 1회 호출."""
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
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
               bookmarked: bool = False, limit: int = 50) -> list:
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
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [_row_to_task(r) for r in rows]
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
        query = "SELECT division, filename, created_at, size FROM archives"
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


# ── Settings (키-값 저장소) ──

def get_today_cost() -> float:
    """오늘(KST 기준) 사용한 총 AI 비용을 반환합니다 (USD)."""
    conn = get_connection()
    try:
        today = _now_kst().strftime("%Y-%m-%d")
        today_start = f"{today}T00:00:00"
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM tasks WHERE created_at >= ?",
            (today_start,),
        ).fetchone()
        return round(row[0], 6)
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
