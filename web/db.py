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
CREATE INDEX IF NOT EXISTS idx_conversation_task_id ON conversation_messages(task_id);

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

-- 위임 로그 테이블: 에이전트 간 협업/위임 기록
CREATE TABLE IF NOT EXISTS delegation_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sender      TEXT NOT NULL,
    receiver    TEXT NOT NULL,
    message     TEXT NOT NULL,
    task_id     TEXT,
    log_type    TEXT DEFAULT 'delegation',
    tools_used  TEXT DEFAULT '',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_delegation_log_sender ON delegation_log(sender);
CREATE INDEX IF NOT EXISTS idx_delegation_log_receiver ON delegation_log(receiver);
CREATE INDEX IF NOT EXISTS idx_delegation_log_task_id ON delegation_log(task_id);
CREATE INDEX IF NOT EXISTS idx_delegation_log_created_at ON delegation_log(created_at);

-- CIO 예측 추적 테이블: CIO의 종목 예측 및 사후 검증 결과 저장
CREATE TABLE IF NOT EXISTS cio_predictions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    ticker_name         TEXT,
    direction           TEXT NOT NULL,
    confidence          REAL DEFAULT 0.0,
    predicted_price     INTEGER,
    target_price        INTEGER,
    stop_loss           INTEGER,
    analysis_summary    TEXT,
    task_id             TEXT,
    analyzed_at         TEXT NOT NULL,
    verify_at_3d        TEXT,
    verify_at_7d        TEXT,
    actual_price_3d     INTEGER,
    actual_price_7d     INTEGER,
    correct_3d          INTEGER,
    correct_7d          INTEGER,
    verified_at         TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cio_predictions_ticker ON cio_predictions(ticker);
CREATE INDEX IF NOT EXISTS idx_cio_predictions_analyzed_at ON cio_predictions(analyzed_at);
CREATE INDEX IF NOT EXISTS idx_cio_predictions_direction ON cio_predictions(direction);
CREATE INDEX IF NOT EXISTS idx_cio_predictions_task_id ON cio_predictions(task_id);

CREATE TABLE IF NOT EXISTS quality_reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id        TEXT,
    reviewer_id     TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    division        TEXT DEFAULT '',
    passed          INTEGER NOT NULL DEFAULT 0,
    weighted_score  REAL DEFAULT 0.0,
    checklist_json  TEXT DEFAULT '{}',
    scores_json     TEXT DEFAULT '{}',
    feedback        TEXT DEFAULT '',
    rejection_reasons TEXT DEFAULT '',
    rework_attempt  INTEGER DEFAULT 0,
    review_model    TEXT DEFAULT '',
    review_cost_usd REAL DEFAULT 0.0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_quality_reviews_chain ON quality_reviews(chain_id);
CREATE INDEX IF NOT EXISTS idx_quality_reviews_reviewer ON quality_reviews(reviewer_id);
CREATE INDEX IF NOT EXISTS idx_quality_reviews_target ON quality_reviews(target_id);
CREATE INDEX IF NOT EXISTS idx_quality_reviews_created ON quality_reviews(created_at);

-- 대화 세션 메타데이터: 멀티턴 대화 세션 관리
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    title           TEXT NOT NULL DEFAULT '새 대화',
    agent_id        TEXT,
    turn_count      INTEGER NOT NULL DEFAULT 0,
    summary         TEXT,
    total_cost      REAL NOT NULL DEFAULT 0.0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversations_active ON conversations(is_active);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at);

-- ═══════════════════════════════════════════════════════════════
-- 신뢰도 검증 파이프라인 (Confidence Validation Pipeline)
-- ═══════════════════════════════════════════════════════════════

-- 전문가별 예측 기여 기록
CREATE TABLE IF NOT EXISTS prediction_specialist_data (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id   INTEGER NOT NULL,
    agent_id        TEXT NOT NULL,
    recommendation  TEXT DEFAULT 'hold',
    confidence      REAL DEFAULT 0.0,
    tools_used      TEXT DEFAULT '[]',
    cost_usd        REAL DEFAULT 0.0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_psd_pred ON prediction_specialist_data(prediction_id);
CREATE INDEX IF NOT EXISTS idx_psd_agent ON prediction_specialist_data(agent_id);

-- 전문가 ELO 레이팅
CREATE TABLE IF NOT EXISTS analyst_elo_ratings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        TEXT NOT NULL UNIQUE,
    elo_rating      REAL NOT NULL DEFAULT 1500.0,
    total_predictions INTEGER DEFAULT 0,
    correct_predictions INTEGER DEFAULT 0,
    avg_return_pct  REAL DEFAULT 0.0,
    last_updated    TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ELO 변동 히스토리
CREATE TABLE IF NOT EXISTS analyst_elo_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        TEXT NOT NULL,
    prediction_id   INTEGER NOT NULL,
    elo_before      REAL NOT NULL,
    elo_after       REAL NOT NULL,
    elo_change      REAL NOT NULL,
    correct         INTEGER,
    return_pct      REAL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_elo_hist_agent ON analyst_elo_history(agent_id);
CREATE INDEX IF NOT EXISTS idx_elo_hist_pred ON analyst_elo_history(prediction_id);

-- 베이지안 신뢰도 칼리브레이션 (구간별)
CREATE TABLE IF NOT EXISTS confidence_calibration (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket          TEXT NOT NULL UNIQUE,
    total_count     INTEGER DEFAULT 0,
    correct_count   INTEGER DEFAULT 0,
    actual_rate     REAL DEFAULT 0.5,
    bayesian_alpha  REAL DEFAULT 1.0,
    bayesian_beta   REAL DEFAULT 1.0,
    ci_lower        REAL DEFAULT 0.0,
    ci_upper        REAL DEFAULT 1.0,
    last_updated    TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 도구별 예측 성공 상관관계
CREATE TABLE IF NOT EXISTS tool_effectiveness (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name       TEXT NOT NULL UNIQUE,
    used_correct    INTEGER DEFAULT 0,
    used_incorrect  INTEGER DEFAULT 0,
    total_uses      INTEGER DEFAULT 0,
    eff_score       REAL DEFAULT 0.5,
    last_updated    TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 탐지된 오답 패턴
CREATE TABLE IF NOT EXISTS error_patterns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type    TEXT NOT NULL,
    description     TEXT NOT NULL,
    hit_count       INTEGER DEFAULT 0,
    miss_count      INTEGER DEFAULT 0,
    hit_rate        REAL DEFAULT 0.0,
    active          INTEGER DEFAULT 1,
    detected_at     TEXT,
    last_triggered  TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_err_pattern_active ON error_patterns(active);

-- 부서 간 협업 로그 (Phase 12)
CREATE TABLE IF NOT EXISTS collaboration_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    from_division   TEXT NOT NULL,
    to_division     TEXT NOT NULL,
    from_agent      TEXT NOT NULL,
    to_agent        TEXT NOT NULL,
    redirected_to   TEXT DEFAULT '',
    task_summary    TEXT DEFAULT '',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_collab_from ON collaboration_logs(from_division);
CREATE INDEX IF NOT EXISTS idx_collab_to ON collaboration_logs(to_division);
CREATE INDEX IF NOT EXISTS idx_collab_created ON collaboration_logs(created_at);

-- ============================================================
-- AGORA: AI 법학 토론 시스템
-- ============================================================

-- 토론 세션
CREATE TABLE IF NOT EXISTS agora_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    paper_text      TEXT NOT NULL,
    status          TEXT DEFAULT 'active',
    total_cost_usd  REAL DEFAULT 0,
    total_rounds    INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 쟁점 (트리 구조 — parent_id로 파생 쟁점 무한 확장)
CREATE TABLE IF NOT EXISTS agora_issues (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL,
    parent_id       INTEGER,
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    status          TEXT DEFAULT 'pending',
    resolution      TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES agora_sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_agora_issues_session ON agora_issues(session_id);
CREATE INDEX IF NOT EXISTS idx_agora_issues_parent ON agora_issues(parent_id);

-- 토론 라운드 (각 발언)
CREATE TABLE IF NOT EXISTS agora_rounds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id        INTEGER NOT NULL,
    round_num       INTEGER NOT NULL,
    speaker         TEXT NOT NULL,
    speaker_model   TEXT NOT NULL,
    content         TEXT NOT NULL,
    citations       TEXT DEFAULT '[]',
    cost_usd        REAL DEFAULT 0,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (issue_id) REFERENCES agora_issues(id)
);
CREATE INDEX IF NOT EXISTS idx_agora_rounds_issue ON agora_rounds(issue_id);

-- 논문 버전 (diff 추적)
CREATE TABLE IF NOT EXISTS agora_paper_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL,
    issue_id        INTEGER,
    version_num     INTEGER NOT NULL,
    full_text       TEXT NOT NULL,
    diff_html       TEXT DEFAULT '',
    change_summary  TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES agora_sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_agora_paper_session ON agora_paper_versions(session_id);

-- 플라톤 대화록 (챕터별)
CREATE TABLE IF NOT EXISTS agora_book_chapters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL,
    issue_id        INTEGER NOT NULL,
    chapter_num     INTEGER NOT NULL,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES agora_sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_agora_book_session ON agora_book_chapters(session_id);

-- ============================================================
-- SOUL GYM: 에이전트 소울 경쟁 진화 시스템
-- ============================================================

CREATE TABLE IF NOT EXISTS soul_gym_rounds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        TEXT NOT NULL,
    agent_name      TEXT DEFAULT '',
    round_num       INTEGER DEFAULT 1,
    soul_before     TEXT DEFAULT '',
    soul_after      TEXT DEFAULT '',
    winner          TEXT DEFAULT 'original',
    score_before    REAL DEFAULT 0,
    score_after     REAL DEFAULT 0,
    improvement     REAL DEFAULT 0,
    cost_usd        REAL DEFAULT 0,
    variants_json   TEXT DEFAULT '{}',
    benchmark_json  TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_soul_gym_agent ON soul_gym_rounds(agent_id);
CREATE INDEX IF NOT EXISTS idx_soul_gym_created ON soul_gym_rounds(created_at);

-- ============================================================
-- ARGOS: 자동 데이터 수집 레이어 (6-5)
-- 분석 시점 API 호출 0회 — 미리 쌓아놓은 DB에서 꺼냄
-- ============================================================

CREATE TABLE IF NOT EXISTS argos_price_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    market          TEXT NOT NULL DEFAULT 'KR',  -- KR | US
    trade_date      TEXT NOT NULL,               -- YYYY-MM-DD
    open_price      REAL,
    high_price      REAL,
    low_price       REAL,
    close_price     REAL NOT NULL,
    volume          INTEGER,
    change_pct      REAL,                        -- 전일 대비 변동률(%)
    collected_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_argos_price_uq ON argos_price_history(ticker, trade_date);
CREATE INDEX IF NOT EXISTS idx_argos_price_ticker ON argos_price_history(ticker);
CREATE INDEX IF NOT EXISTS idx_argos_price_date ON argos_price_history(trade_date);

CREATE TABLE IF NOT EXISTS argos_news_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword         TEXT NOT NULL,               -- 종목코드 or 검색어
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    link            TEXT DEFAULT '',
    pub_date        TEXT NOT NULL,               -- ISO8601
    source          TEXT DEFAULT 'naver',
    sentiment       TEXT DEFAULT '',             -- positive | negative | neutral
    collected_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_argos_news_keyword ON argos_news_cache(keyword);
CREATE INDEX IF NOT EXISTS idx_argos_news_pub ON argos_news_cache(pub_date);

CREATE TABLE IF NOT EXISTS argos_dart_filings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    corp_name       TEXT DEFAULT '',
    report_nm       TEXT NOT NULL,               -- 공시 제목
    rcept_no        TEXT UNIQUE,                 -- 접수번호
    flr_nm          TEXT DEFAULT '',             -- 공시인
    rcept_dt        TEXT NOT NULL,               -- 접수일 YYYYMMDD
    remark          TEXT DEFAULT '',
    collected_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_argos_dart_ticker ON argos_dart_filings(ticker);
CREATE INDEX IF NOT EXISTS idx_argos_dart_dt ON argos_dart_filings(rcept_dt);

CREATE TABLE IF NOT EXISTS argos_macro_data (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator       TEXT NOT NULL,               -- USD_KRW | KOSPI | KOSDAQ | VIX | ...
    trade_date      TEXT NOT NULL,               -- YYYY-MM-DD
    value           REAL NOT NULL,
    source          TEXT DEFAULT '',
    collected_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_argos_macro_uq ON argos_macro_data(indicator, trade_date);
CREATE INDEX IF NOT EXISTS idx_argos_macro_indicator ON argos_macro_data(indicator);

CREATE TABLE IF NOT EXISTS argos_collection_status (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    data_type       TEXT NOT NULL UNIQUE,        -- price | news | dart | macro
    last_collected  TEXT DEFAULT '',             -- ISO8601
    last_error      TEXT DEFAULT '',
    total_count     INTEGER DEFAULT 0,
    updated_at      TEXT NOT NULL
);
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
        # delegation_log 테이블에 tools_used 컬럼 추가 (P2-3: 도구 사용 표시)
        try:
            conn.execute("ALTER TABLE delegation_log ADD COLUMN tools_used TEXT DEFAULT ''")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # 이미 존재하면 무시
        # conversation_messages에 conversation_id 컬럼 추가 (Step 13: 멀티턴 대화)
        try:
            conn.execute("ALTER TABLE conversation_messages ADD COLUMN conversation_id TEXT DEFAULT NULL")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversation_conv_id ON conversation_messages(conversation_id)")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        # cio_predictions에 신뢰도 파이프라인 컬럼 추가
        _cio_migrate = [
            ("return_pct_3d", "REAL DEFAULT NULL"),
            ("return_pct_7d", "REAL DEFAULT NULL"),
            ("brier_score", "REAL DEFAULT NULL"),
            ("market_context", "TEXT DEFAULT ''"),
            ("specialists_json", "TEXT DEFAULT '{}'"),
        ]
        for col_name, col_def in _cio_migrate:
            try:
                conn.execute(f"ALTER TABLE cio_predictions ADD COLUMN {col_name} {col_def}")
                conn.commit()
            except sqlite3.OperationalError:
                pass
        # N-9: tasks 테이블에 보고서 재작성 관련 컬럼 추가
        _task_rewrite_migrate = [
            ("version", "INTEGER NOT NULL DEFAULT 1"),
            ("parent_task_id", "TEXT DEFAULT NULL"),
            ("rejected_sections", "TEXT DEFAULT NULL"),
        ]
        for col_name, col_def in _task_rewrite_migrate:
            try:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_def}")
                conn.commit()
            except sqlite3.OperationalError:
                pass
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
    version = 1
    parent_task_id = None
    rejected_sections = None
    try:
        tags_raw = row["tags"]
        is_read = row["is_read"]
        archived = row["archived"]
    except (IndexError, KeyError):
        pass
    try:
        version = row["version"] or 1
        parent_task_id = row["parent_task_id"]
        rejected_sections = row["rejected_sections"]
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
        "version": version,
        "parent_task_id": parent_task_id,
        "rejected_sections": json.loads(rejected_sections) if rejected_sections else None,
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

def create_task(command: str, source: str = "websocket", agent_id: str = None) -> dict:
    """새 작업을 생성합니다. 반환: task dict."""
    task_id = _gen_task_id()
    now = _now_iso()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO tasks (task_id, command, status, created_at, source, agent_id) "
            "VALUES (?, ?, 'pending', ?, ?, ?)",
            (task_id, command, now, source, agent_id),
        )
        conn.commit()
        return {
            "task_id": task_id,
            "command": command,
            "status": "pending",
            "created_at": now,
            "source": source,
            "agent_id": agent_id,
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
        "version", "parent_task_id", "rejected_sections",
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

def _today_start_utc_iso() -> str:
    """오늘 KST 자정을 UTC ISO 형식으로 반환합니다.

    DB에 UTC ISO 형식(Z 접미사)으로 저장되는 값과 올바르게 비교하기 위해
    KST 자정(00:00:00 KST)을 UTC로 변환합니다.
    예: KST 2026-02-19 00:00:00 → UTC 2026-02-18 15:00:00 → "2026-02-18T15:00:00"
    """
    kst_midnight = _now_kst().replace(hour=0, minute=0, second=0, microsecond=0)
    utc_midnight = kst_midnight.astimezone(timezone.utc)
    return utc_midnight.strftime("%Y-%m-%dT%H:%M:%S")


def get_dashboard_stats() -> dict:
    """대시보드 통계를 반환합니다."""
    conn = get_connection()
    try:
        # KST 자정을 UTC로 변환하여 DB의 UTC ISO 타임스탬프와 올바르게 비교
        today_start = _today_start_utc_iso()

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
        # tasks + agent_calls 양쪽 비용 합산
        task_cost = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM tasks"
        ).fetchone()[0]
        try:
            ac_cost = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM agent_calls"
            ).fetchone()[0]
        except Exception:
            ac_cost = 0.0
        cost_row = (task_cost + ac_cost,)
        # tasks + agent_calls 토큰 합산
        task_tokens = conn.execute(
            "SELECT COALESCE(SUM(tokens_used), 0) FROM tasks"
        ).fetchone()[0]
        try:
            ac_tokens = conn.execute(
                "SELECT COALESCE(SUM(input_tokens) + SUM(output_tokens), 0) FROM agent_calls"
            ).fetchone()[0]
        except Exception:
            ac_tokens = 0
        tokens_row = (task_tokens + ac_tokens,)
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
        # 자동 정리: 5000건 초과 시 오래된 것 삭제
        count = conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0]
        if count > 5000:
            conn.execute(
                "DELETE FROM activity_logs WHERE id NOT IN "
                "(SELECT id FROM activity_logs ORDER BY timestamp DESC LIMIT 5000)"
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
        query = "SELECT agent_id, message, level, time, timestamp, created_at FROM activity_logs"
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


def delete_all_archives() -> int:
    """모든 아카이브(기밀문서)를 삭제합니다. 반환: 삭제된 건수."""
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM archives")
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


# ── Settings (키-값 저장소) ──

def get_today_cost() -> float:
    """오늘(KST 기준) 사용한 총 AI 비용을 반환합니다 (USD).

    tasks 테이블과 agent_calls 테이블 양쪽의 비용을 합산합니다.
    KST 자정을 UTC로 변환하여 DB의 UTC ISO 타임스탬프와 올바르게 비교합니다.
    """
    conn = get_connection()
    try:
        today_start = _today_start_utc_iso()
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


def get_monthly_cost() -> float:
    """이번 달 총 AI 비용을 반환합니다 (USD).

    tasks 테이블과 agent_calls 테이블 양쪽의 비용을 합산합니다.
    """
    conn = get_connection()
    try:
        # KST 월 시작을 UTC ISO 형식으로 변환 (DB 저장 형식과 일치)
        kst_month_start = _now_kst().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        utc_month_start = kst_month_start.astimezone(timezone.utc)
        month_start = utc_month_start.strftime("%Y-%m-%dT%H:%M:%S")

        # tasks 테이블 비용
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM tasks WHERE created_at >= ?",
            (month_start,)
        ).fetchone()
        total = row[0] if row else 0.0

        # agent_calls 테이블 비용
        try:
            row2 = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM agent_calls WHERE created_at >= ?",
                (month_start,)
            ).fetchone()
            total += row2[0] if row2 else 0.0
        except Exception:
            pass

        return round(total, 6)
    except Exception:
        return 0.0
    finally:
        conn.close()


def get_cost_by_agent(period: str = "month") -> dict:
    """에이전트별 AI 비용을 집계합니다.

    period: 'today' | 'month' | 'all'
    반환: { agents: [{agent_id, cost_usd, call_count, input_tokens, output_tokens}], total_cost_usd }
    """
    conn = get_connection()
    try:
        if period == "today":
            time_filter = _today_start_utc_iso()
        elif period == "month":
            kst_month_start = _now_kst().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            utc_month_start = kst_month_start.astimezone(timezone.utc)
            time_filter = utc_month_start.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            time_filter = None

        where = "WHERE created_at >= ?" if time_filter else ""
        params = (time_filter,) if time_filter else ()

        rows = conn.execute(
            f"SELECT agent_id, COALESCE(SUM(cost_usd),0), COUNT(*),"
            f" COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0)"
            f" FROM agent_calls {where} GROUP BY agent_id ORDER BY 2 DESC",
            params,
        ).fetchall()

        agents = []
        total = 0.0
        for r in rows:
            cost = round(r[1], 6)
            agents.append({
                "agent_id": r[0],
                "cost_usd": cost,
                "call_count": r[2],
                "input_tokens": r[3],
                "output_tokens": r[4],
            })
            total += cost

        return {"agents": agents, "total_cost_usd": round(total, 6)}
    except Exception:
        return {"agents": [], "total_cost_usd": 0.0}
    finally:
        conn.close()


def get_cost_by_agent_raw(period: str = "month") -> dict:
    """에이전트별 비용 raw 데이터 (division 매핑은 호출자가 수행).

    반환: { agent_costs: { agent_id: {cost_usd, call_count} } }
    """
    conn = get_connection()
    try:
        if period == "today":
            time_filter = _today_start_utc_iso()
        elif period == "month":
            kst_month_start = _now_kst().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            utc_month_start = kst_month_start.astimezone(timezone.utc)
            time_filter = utc_month_start.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            time_filter = None

        where = "WHERE created_at >= ?" if time_filter else ""
        params = (time_filter,) if time_filter else ()

        rows = conn.execute(
            f"SELECT agent_id, COALESCE(SUM(cost_usd),0), COUNT(*)"
            f" FROM agent_calls {where} GROUP BY agent_id",
            params,
        ).fetchall()

        agent_costs = {}
        for r in rows:
            agent_costs[r[0]] = {"cost_usd": round(r[1], 6), "call_count": r[2]}
        return {"agent_costs": agent_costs}
    except Exception:
        return {"agent_costs": {}}
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
    """대화 메시지를 DB에 저장합니다. 반환: row id.
    result 타입이고 task_id가 있으면 중복 저장을 방지합니다 (서버+클라이언트 양쪽 저장 대비).
    """
    conn = get_connection()
    try:
        # 허용된 필드만 필터링
        allowed = {
            "text", "content", "sender_id", "handled_by", "delegation",
            "model", "time_seconds", "cost", "quality_score", "task_id", "source",
            "conversation_id",
        }
        filtered = {k: v for k, v in kwargs.items() if k in allowed}

        # result 타입 + task_id가 있으면 중복 체크
        task_id = filtered.get("task_id")
        if message_type == "result" and task_id:
            existing = conn.execute(
                "SELECT id FROM conversation_messages WHERE type='result' AND task_id=?",
                (task_id,)
            ).fetchone()
            if existing:
                return existing["id"]  # 이미 있으면 기존 id 반환 (중복 저장 생략)

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


# ── Conversations (멀티턴 대화 세션) CRUD ──

def create_conversation(agent_id: str | None = None, title: str = "새 대화") -> dict:
    """새 대화 세션을 생성합니다."""
    conv_id = _gen_task_id()
    now = _now_iso()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO conversations (conversation_id, title, agent_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conv_id, title, agent_id, now, now),
        )
        conn.commit()
        return {"conversation_id": conv_id, "title": title, "agent_id": agent_id,
                "turn_count": 0, "total_cost": 0.0, "is_active": 1,
                "created_at": now, "updated_at": now}
    except sqlite3.OperationalError:
        return {"conversation_id": conv_id, "title": title}
    finally:
        conn.close()


def list_conversations(limit: int = 50) -> list:
    """활성 대화 세션 목록을 반환합니다 (최신순)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE is_active = 1 ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def get_conversation(conversation_id: str) -> dict | None:
    """단일 대화 세션 정보를 반환합니다."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def update_conversation(conversation_id: str, **kwargs) -> None:
    """대화 세션 메타데이터를 업데이트합니다."""
    allowed = {"title", "agent_id", "turn_count", "summary", "total_cost", "is_active"}
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    if not filtered:
        return
    filtered["updated_at"] = _now_iso()
    set_clause = ", ".join(f"{k} = ?" for k in filtered)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE conversations SET {set_clause} WHERE conversation_id = ?",
            (*filtered.values(), conversation_id),
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def load_conversation_messages_by_id(conversation_id: str, limit: int = 200) -> list:
    """특정 대화 세션의 메시지를 조회합니다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM conversation_messages WHERE conversation_id = ? "
            "ORDER BY created_at ASC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
        messages = []
        for row in rows:
            msg = {"type": row["type"], "timestamp": row["created_at"]}
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
        return []
    finally:
        conn.close()


def delete_conversation(conversation_id: str) -> None:
    """대화 세션과 관련 메시지를 삭제합니다."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM conversation_messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
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


# ── Delegation Log CRUD ──

def save_delegation_log(sender: str, receiver: str, message: str,
                        task_id: str = None,
                        log_type: str = "delegation",
                        tools_used: str = "") -> int:
    """에이전트 간 위임/협업 로그를 저장합니다. 반환: row id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO delegation_log (sender, receiver, message, task_id, log_type, tools_used) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (sender, receiver, message, task_id, log_type, tools_used),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.OperationalError:
        # delegation_log 테이블이 아직 없는 경우 (init_db 전)
        return 0
    finally:
        conn.close()


def list_delegation_logs(agent: str = None, limit: int = 100) -> list:
    """위임 로그를 최근순으로 조회합니다.

    agent 파라미터 지정 시 해당 에이전트가 sender 또는 receiver인 로그만 반환합니다.
    """
    conn = get_connection()
    try:
        if agent:
            rows = conn.execute(
                "SELECT id, sender, receiver, message, task_id, log_type, tools_used, created_at "
                "FROM delegation_log "
                "WHERE sender = ? OR receiver = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (agent, agent, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, sender, receiver, message, task_id, log_type, tools_used, created_at "
                "FROM delegation_log "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


# ── CIO Predictions CRUD ──

def save_cio_prediction(
    ticker: str,
    direction: str,
    analyzed_at: str = None,
    ticker_name: str = None,
    confidence: float = 0.0,
    predicted_price: int = None,
    target_price: int = None,
    stop_loss: int = None,
    analysis_summary: str = None,
    task_id: str = None,
) -> int:
    """CIO의 종목 예측을 저장합니다. 반환값: 예측 ID."""
    now_str = analyzed_at or datetime.now(KST).isoformat()
    try:
        now_dt = (
            datetime.fromisoformat(now_str.replace("Z", "+00:00"))
            if analyzed_at
            else datetime.now(KST)
        )
    except ValueError:
        now_dt = datetime.now(KST)
    verify_3d = (now_dt + timedelta(days=3)).isoformat()
    verify_7d = (now_dt + timedelta(days=7)).isoformat()

    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO cio_predictions
               (ticker, ticker_name, direction, confidence, predicted_price, target_price, stop_loss,
                analysis_summary, task_id, analyzed_at, verify_at_3d, verify_at_7d)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticker,
                ticker_name,
                direction.upper(),
                confidence,
                predicted_price,
                target_price,
                stop_loss,
                analysis_summary[:500] if analysis_summary else None,
                task_id,
                now_str,
                verify_3d,
                verify_7d,
            ),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def update_cio_prediction_result(
    prediction_id: int,
    actual_price_3d: int = None,
    actual_price_7d: int = None,
) -> dict:
    """3일/7일 후 실제 주가를 기록하고 예측 정확도·수익률·Brier Score를 계산합니다."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT direction, predicted_price, confidence FROM cio_predictions WHERE id=?",
            (prediction_id,),
        ).fetchone()
        if not row:
            return {}
        direction = row["direction"]
        predicted_price = row["predicted_price"]
        confidence = row["confidence"] or 0.0

        correct_3d = None
        correct_7d = None
        return_pct_3d = None
        return_pct_7d = None
        brier_score = None

        if actual_price_3d is not None and predicted_price and predicted_price > 0:
            went_up = actual_price_3d > predicted_price
            correct_3d = 1 if (direction == "BUY" and went_up) or (direction == "SELL" and not went_up) else 0
            # 수익률 (방향 고려): 매수면 그대로, 매도면 반대
            raw_pct = (actual_price_3d - predicted_price) / predicted_price * 100
            return_pct_3d = round(raw_pct if direction == "BUY" else -raw_pct, 2)

        if actual_price_7d is not None and predicted_price and predicted_price > 0:
            went_up = actual_price_7d > predicted_price
            correct_7d = 1 if (direction == "BUY" and went_up) or (direction == "SELL" and not went_up) else 0
            raw_pct = (actual_price_7d - predicted_price) / predicted_price * 100
            return_pct_7d = round(raw_pct if direction == "BUY" else -raw_pct, 2)
            # Brier Score: (p - o)² where p=stated confidence, o=actual outcome
            outcome = 1.0 if correct_7d else 0.0
            brier_score = round((confidence / 100.0 - outcome) ** 2, 4)

        conn.execute(
            """UPDATE cio_predictions SET
               actual_price_3d=?, actual_price_7d=?, correct_3d=?, correct_7d=?,
               return_pct_3d=?, return_pct_7d=?, brier_score=?,
               verified_at=?
               WHERE id=?""",
            (
                actual_price_3d,
                actual_price_7d,
                correct_3d,
                correct_7d,
                return_pct_3d,
                return_pct_7d,
                brier_score,
                datetime.now(KST).isoformat(),
                prediction_id,
            ),
        )
        conn.commit()
        return {
            "correct_3d": correct_3d, "correct_7d": correct_7d,
            "return_pct_3d": return_pct_3d, "return_pct_7d": return_pct_7d,
            "brier_score": brier_score, "direction": direction,
            "confidence": confidence,
        }
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def load_cio_predictions(limit: int = 50, unverified_only: bool = False) -> list:
    """CIO 예측 목록 조회. unverified_only=True이면 검증 미완료만 반환."""
    cols = [
        "id", "ticker", "ticker_name", "direction", "confidence", "predicted_price",
        "analysis_summary", "task_id", "analyzed_at", "verify_at_3d", "verify_at_7d",
        "actual_price_3d", "actual_price_7d", "correct_3d", "correct_7d", "verified_at",
    ]
    col_sql = ", ".join(cols)
    conn = get_connection()
    try:
        if unverified_only:
            rows = conn.execute(
                f"SELECT {col_sql} FROM cio_predictions "
                "WHERE correct_7d IS NULL ORDER BY analyzed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {col_sql} FROM cio_predictions "
                "ORDER BY analyzed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(zip(cols, tuple(r))) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def get_cio_performance_summary() -> dict:
    """CIO 예측 성과 요약. 전체/최근 20건/방향별 정확도 포함."""
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM cio_predictions").fetchone()[0]
        verified = conn.execute(
            "SELECT COUNT(*) FROM cio_predictions WHERE correct_7d IS NOT NULL"
        ).fetchone()[0]
        correct_7d = conn.execute(
            "SELECT COUNT(*) FROM cio_predictions WHERE correct_7d=1"
        ).fetchone()[0]

        recent = conn.execute(
            "SELECT direction, correct_7d FROM cio_predictions "
            "WHERE correct_7d IS NOT NULL ORDER BY analyzed_at DESC LIMIT 20"
        ).fetchall()
        recent_correct = sum(1 for r in recent if r[1] == 1)
        recent_total = len(recent)

        buy_total = conn.execute(
            "SELECT COUNT(*) FROM cio_predictions WHERE direction='BUY' AND correct_7d IS NOT NULL"
        ).fetchone()[0]
        buy_correct = conn.execute(
            "SELECT COUNT(*) FROM cio_predictions WHERE direction='BUY' AND correct_7d=1"
        ).fetchone()[0]
        sell_total = conn.execute(
            "SELECT COUNT(*) FROM cio_predictions WHERE direction='SELL' AND correct_7d IS NOT NULL"
        ).fetchone()[0]
        sell_correct = conn.execute(
            "SELECT COUNT(*) FROM cio_predictions WHERE direction='SELL' AND correct_7d=1"
        ).fetchone()[0]

        # Brier Score 평균
        brier_row = conn.execute(
            "SELECT AVG(brier_score) FROM cio_predictions WHERE brier_score IS NOT NULL"
        ).fetchone()
        avg_brier = round(brier_row[0], 4) if brier_row and brier_row[0] is not None else None

        # 평균 수익률
        ret_row = conn.execute(
            "SELECT AVG(return_pct_7d) FROM cio_predictions WHERE return_pct_7d IS NOT NULL"
        ).fetchone()
        avg_return = round(ret_row[0], 2) if ret_row and ret_row[0] is not None else None

        # 구간별 적중률
        bucket_rows = conn.execute(
            """SELECT
                 CASE
                   WHEN confidence < 60 THEN '50-60'
                   WHEN confidence < 70 THEN '60-70'
                   WHEN confidence < 80 THEN '70-80'
                   WHEN confidence < 90 THEN '80-90'
                   ELSE '90-100'
                 END as bucket,
                 COUNT(*) as cnt,
                 SUM(CASE WHEN correct_7d=1 THEN 1 ELSE 0 END) as correct_cnt
               FROM cio_predictions
               WHERE correct_7d IS NOT NULL
               GROUP BY bucket ORDER BY bucket"""
        ).fetchall()
        bucket_accuracy = {
            r[0]: {"total": r[1], "correct": r[2],
                   "accuracy": round(r[2] / r[1] * 100, 1) if r[1] > 0 else None}
            for r in bucket_rows
        }

        return {
            "total": total,
            "verified": verified,
            "overall_accuracy": round(correct_7d / verified * 100, 1) if verified > 0 else None,
            "recent_20_accuracy": round(recent_correct / recent_total * 100, 1) if recent_total > 0 else None,
            "recent_correct": recent_correct,
            "recent_total": recent_total,
            "buy_accuracy": round(buy_correct / buy_total * 100, 1) if buy_total > 0 else None,
            "sell_accuracy": round(sell_correct / sell_total * 100, 1) if sell_total > 0 else None,
            "avg_brier_score": avg_brier,
            "avg_return_pct_7d": avg_return,
            "bucket_accuracy": bucket_accuracy,
        }
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def get_pending_verifications(days_threshold: int = 3) -> list:
    """검증이 필요한 예측 목록 반환 (3일 또는 7일이 지났지만 아직 검증 안 된 것)."""
    now = datetime.now(KST).isoformat()
    conn = get_connection()
    try:
        if days_threshold == 3:
            rows = conn.execute(
                "SELECT id, ticker, ticker_name, direction, confidence, verify_at_3d, predicted_price "
                "FROM cio_predictions "
                "WHERE correct_3d IS NULL AND verify_at_3d <= ? "
                "ORDER BY verify_at_3d ASC LIMIT 20",
                (now,),
            ).fetchall()
            return [
                {"id": r[0], "ticker": r[1], "ticker_name": r[2], "direction": r[3],
                 "confidence": r[4], "verify_at": r[5], "predicted_price": r[6], "days": 3}
                for r in rows
            ]
        else:
            rows = conn.execute(
                "SELECT id, ticker, ticker_name, direction, confidence, verify_at_7d, predicted_price "
                "FROM cio_predictions "
                "WHERE correct_7d IS NULL AND verify_at_7d <= ? "
                "ORDER BY verify_at_7d ASC LIMIT 20",
                (now,),
            ).fetchall()
            return [
                {"id": r[0], "ticker": r[1], "ticker_name": r[2], "direction": r[3],
                 "confidence": r[4], "verify_at": r[5], "predicted_price": r[6], "days": 7}
                for r in rows
            ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


# ── Portfolio Snapshots ──

def save_portfolio_snapshot(total_cash: int, total_eval: int, total_pnl: int, pnl_pct: float) -> None:
    """일별 포트폴리오 스냅샷 저장 (날짜별 1개, 덮어씀)"""
    from datetime import date
    today = date.today().isoformat()
    snapshots = load_setting("portfolio_snapshots", [])
    # 오늘 것 있으면 업데이트, 없으면 추가
    updated = False
    for s in snapshots:
        if s.get("date") == today:
            s.update({"cash": total_cash, "eval": total_eval, "pnl": total_pnl, "pnl_pct": pnl_pct})
            updated = True
            break
    if not updated:
        snapshots.append({"date": today, "cash": total_cash, "eval": total_eval, "pnl": total_pnl, "pnl_pct": pnl_pct})
    # 최근 90일만 보관
    snapshots = sorted(snapshots, key=lambda x: x["date"])[-90:]
    save_setting("portfolio_snapshots", snapshots)

def load_portfolio_snapshots() -> list:
    """포트폴리오 스냅샷 목록 조회 (최근 90일)"""
    return load_setting("portfolio_snapshots", [])


# ── 품질검수 기록 ──

def save_quality_review(
    chain_id: str,
    reviewer_id: str,
    target_id: str,
    division: str,
    passed: bool,
    weighted_score: float,
    checklist_json: str = "{}",
    scores_json: str = "{}",
    feedback: str = "",
    rejection_reasons: str = "",
    rework_attempt: int = 0,
    review_model: str = "",
    review_cost_usd: float = 0.0,
) -> int:
    """품질검수 결과를 DB에 저장. 반환: row id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO quality_reviews
               (chain_id, reviewer_id, target_id, division, passed,
                weighted_score, checklist_json, scores_json, feedback,
                rejection_reasons, rework_attempt, review_model, review_cost_usd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (chain_id, reviewer_id, target_id, division, int(passed),
             weighted_score, checklist_json, scores_json, feedback,
             rejection_reasons, rework_attempt, review_model, review_cost_usd),
        )
        conn.commit()
        return cur.lastrowid or 0
    except Exception as e:
        print(f"[DB] quality_review 저장 실패: {e}")
        return 0
    finally:
        conn.close()


def get_quality_stats() -> dict:
    """품질검수 전체 통계 반환."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT
                 COUNT(*) as total,
                 SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) as passed,
                 SUM(CASE WHEN passed = 0 THEN 1 ELSE 0 END) as failed,
                 AVG(weighted_score) as avg_score
               FROM quality_reviews"""
        ).fetchone()
        total = row[0] or 0
        passed = row[1] or 0
        failed = row[2] or 0
        avg_score = round(row[3] or 0, 2)
        pass_rate = round(passed / total * 100, 1) if total > 0 else 100.0

        # 최근 10건
        recent = conn.execute(
            """SELECT reviewer_id, target_id, division, passed,
                      weighted_score, feedback, rejection_reasons, created_at
               FROM quality_reviews ORDER BY id DESC LIMIT 10"""
        ).fetchall()
        recent_list = [
            {
                "reviewer": r[0], "target": r[1], "division": r[2],
                "passed": bool(r[3]), "score": r[4], "feedback": r[5],
                "rejection_reasons": r[6], "created_at": r[7],
            }
            for r in recent
        ]

        return {
            "total_reviews": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate,
            "average_score": avg_score,
            "recent_reviews": recent_list,
        }
    except Exception as e:
        print(f"[DB] quality stats 조회 실패: {e}")
        return {"total_reviews": 0, "passed": 0, "failed": 0, "pass_rate": 100.0, "average_score": 0}
    finally:
        conn.close()


def get_quality_scores_timeline(days: int = 30, agent_id: str = "") -> list[dict]:
    """에이전트별 품질 점수 타임라인 조회 (대시보드 차트용).

    반환: [{target_id, weighted_score, passed, created_at, scores_json}, ...]
    """
    conn = get_connection()
    try:
        query = """SELECT target_id, weighted_score, passed, created_at, scores_json
                   FROM quality_reviews
                   WHERE created_at >= datetime('now', ?)"""
        params: list = [f"-{days} days"]
        if agent_id:
            query += " AND target_id = ?"
            params.append(agent_id)
        query += " ORDER BY created_at ASC"
        rows = conn.execute(query, params).fetchall()
        return [
            {
                "target_id": r[0],
                "weighted_score": r[1],
                "passed": bool(r[2]),
                "created_at": r[3],
                "scores_json": r[4],
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[DB] quality scores timeline 조회 실패: {e}")
        return []
    finally:
        conn.close()


def get_top_rejection_reasons(limit: int = 5) -> list[dict]:
    """가장 많이 반려된 항목 Top N 조회."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT target_id, rejection_reasons, COUNT(*) as cnt
               FROM quality_reviews
               WHERE passed = 0 AND rejection_reasons != ''
               GROUP BY target_id, rejection_reasons
               ORDER BY cnt DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [{"target_id": r[0], "reason": r[1], "count": r[2]} for r in rows]
    except Exception as e:
        print(f"[DB] top rejection reasons 조회 실패: {e}")
        return []
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# SOUL GYM — 에이전트 소울 경쟁 진화
# ═══════════════════════════════════════════════════════════════

def save_soul_gym_round(data: dict) -> int:
    """Soul Gym 진화 라운드 결과를 저장합니다. 반환: row id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO soul_gym_rounds
               (agent_id, agent_name, round_num, soul_before, soul_after,
                winner, score_before, score_after, improvement,
                cost_usd, variants_json, benchmark_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("agent_id", ""),
                data.get("agent_name", ""),
                data.get("round_num", 1),
                data.get("soul_before", "")[:500],
                data.get("soul_after", "")[:500],
                data.get("winner", "original"),
                data.get("score_before", 0),
                data.get("score_after", 0),
                data.get("improvement", 0),
                data.get("cost_usd", 0),
                data.get("variants_json", "{}"),
                data.get("benchmark_json", "{}"),
                _now_iso(),
            ),
        )
        conn.commit()
        return cur.lastrowid or 0
    except Exception as e:
        print(f"[DB] soul_gym_round 저장 실패: {e}")
        return 0
    finally:
        conn.close()


def get_soul_gym_history(agent_id: str = "", limit: int = 50) -> list[dict]:
    """Soul Gym 진화 히스토리를 조회합니다."""
    conn = get_connection()
    try:
        query = "SELECT * FROM soul_gym_rounds"
        params: list = []
        if agent_id:
            query += " WHERE agent_id = ?"
            params.append(agent_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        cols = [d[0] for d in conn.execute("PRAGMA table_info(soul_gym_rounds)").fetchall()]
        col_names = [c[1] for c in conn.execute("PRAGMA table_info(soul_gym_rounds)").fetchall()]
        # 직접 컬럼명 매핑
        return [
            {
                "id": r[0], "agent_id": r[1], "agent_name": r[2],
                "round_num": r[3], "soul_before": r[4], "soul_after": r[5],
                "winner": r[6], "score_before": r[7], "score_after": r[8],
                "improvement": r[9], "cost_usd": r[10],
                "variants_json": r[11], "benchmark_json": r[12],
                "created_at": r[13],
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[DB] soul_gym_history 조회 실패: {e}")
        return []
    finally:
        conn.close()


def get_soul_gym_next_round(agent_id: str) -> int:
    """해당 에이전트의 다음 라운드 번호를 반환합니다."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(round_num) FROM soul_gym_rounds WHERE agent_id = ?",
            (agent_id,),
        ).fetchone()
        return (row[0] or 0) + 1
    except Exception:
        return 1
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# 신뢰도 검증 파이프라인 — CRUD 함수
# ═══════════════════════════════════════════════════════════════

# ── 전문가별 예측 기여 ──

def save_prediction_specialist(
    prediction_id: int, agent_id: str, recommendation: str = "hold",
    confidence: float = 0.0, tools_used: str = "[]", cost_usd: float = 0.0,
) -> int:
    """전문가의 개별 예측 기여를 저장합니다."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO prediction_specialist_data
               (prediction_id, agent_id, recommendation, confidence, tools_used, cost_usd)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (prediction_id, agent_id, recommendation.upper(), confidence, tools_used, cost_usd),
        )
        conn.commit()
        return cur.lastrowid or 0
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def get_prediction_specialists(prediction_id: int) -> list:
    """특정 예측의 전문가 기여 목록을 조회합니다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT agent_id, recommendation, confidence, tools_used, cost_usd "
            "FROM prediction_specialist_data WHERE prediction_id=?",
            (prediction_id,),
        ).fetchall()
        return [
            {"agent_id": r[0], "recommendation": r[1], "confidence": r[2],
             "tools_used": r[3], "cost_usd": r[4]}
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


# ── ELO 레이팅 ──

def get_analyst_elo(agent_id: str) -> dict:
    """특정 전문가의 ELO 레이팅을 조회합니다."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT agent_id, elo_rating, total_predictions, correct_predictions, "
            "avg_return_pct, last_updated FROM analyst_elo_ratings WHERE agent_id=?",
            (agent_id,),
        ).fetchone()
        if not row:
            return {"agent_id": agent_id, "elo_rating": 1500.0, "total_predictions": 0,
                    "correct_predictions": 0, "avg_return_pct": 0.0, "last_updated": None}
        return {"agent_id": row[0], "elo_rating": row[1], "total_predictions": row[2],
                "correct_predictions": row[3], "avg_return_pct": row[4], "last_updated": row[5]}
    except sqlite3.OperationalError:
        return {"agent_id": agent_id, "elo_rating": 1500.0, "total_predictions": 0,
                "correct_predictions": 0, "avg_return_pct": 0.0, "last_updated": None}
    finally:
        conn.close()


def get_all_analyst_elos() -> list:
    """모든 전문가의 ELO 레이팅을 조회합니다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT agent_id, elo_rating, total_predictions, correct_predictions, "
            "avg_return_pct, last_updated FROM analyst_elo_ratings ORDER BY elo_rating DESC"
        ).fetchall()
        return [
            {"agent_id": r[0], "elo_rating": r[1], "total_predictions": r[2],
             "correct_predictions": r[3], "avg_return_pct": r[4], "last_updated": r[5]}
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def upsert_analyst_elo(
    agent_id: str, elo_rating: float, total_predictions: int,
    correct_predictions: int, avg_return_pct: float,
) -> None:
    """전문가 ELO 레이팅을 생성 또는 갱신합니다."""
    now = datetime.now(KST).isoformat()
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM analyst_elo_ratings WHERE agent_id=?", (agent_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE analyst_elo_ratings SET elo_rating=?, total_predictions=?,
                   correct_predictions=?, avg_return_pct=?, last_updated=? WHERE agent_id=?""",
                (elo_rating, total_predictions, correct_predictions, avg_return_pct, now, agent_id),
            )
        else:
            conn.execute(
                """INSERT INTO analyst_elo_ratings
                   (agent_id, elo_rating, total_predictions, correct_predictions, avg_return_pct, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (agent_id, elo_rating, total_predictions, correct_predictions, avg_return_pct, now),
            )
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def save_elo_history(
    agent_id: str, prediction_id: int, elo_before: float,
    elo_after: float, elo_change: float, correct: int, return_pct: float,
) -> None:
    """ELO 변동 히스토리를 저장합니다."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO analyst_elo_history
               (agent_id, prediction_id, elo_before, elo_after, elo_change, correct, return_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (agent_id, prediction_id, elo_before, elo_after, elo_change, correct, return_pct),
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def get_elo_history(agent_id: str, limit: int = 30) -> list:
    """특정 전문가의 ELO 변동 히스토리를 조회합니다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT prediction_id, elo_before, elo_after, elo_change, correct, return_pct, created_at "
            "FROM analyst_elo_history WHERE agent_id=? ORDER BY id DESC LIMIT ?",
            (agent_id, limit),
        ).fetchall()
        return [
            {"prediction_id": r[0], "elo_before": r[1], "elo_after": r[2],
             "elo_change": r[3], "correct": r[4], "return_pct": r[5], "created_at": r[6]}
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


# ── 베이지안 칼리브레이션 ──

def get_all_calibration_buckets() -> list:
    """모든 신뢰도 구간의 칼리브레이션 데이터를 조회합니다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT bucket, total_count, correct_count, actual_rate, "
            "bayesian_alpha, bayesian_beta, ci_lower, ci_upper, last_updated "
            "FROM confidence_calibration ORDER BY bucket"
        ).fetchall()
        return [
            {"bucket": r[0], "total_count": r[1], "correct_count": r[2],
             "actual_rate": r[3], "bayesian_alpha": r[4], "bayesian_beta": r[5],
             "ci_lower": r[6], "ci_upper": r[7], "last_updated": r[8]}
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def upsert_calibration_bucket(
    bucket: str, total_count: int, correct_count: int,
    actual_rate: float, alpha: float, beta_val: float,
    ci_lower: float, ci_upper: float,
) -> None:
    """신뢰도 구간 칼리브레이션 데이터를 생성 또는 갱신합니다."""
    now = datetime.now(KST).isoformat()
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM confidence_calibration WHERE bucket=?", (bucket,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE confidence_calibration SET total_count=?, correct_count=?,
                   actual_rate=?, bayesian_alpha=?, bayesian_beta=?, ci_lower=?, ci_upper=?,
                   last_updated=? WHERE bucket=?""",
                (total_count, correct_count, actual_rate, alpha, beta_val,
                 ci_lower, ci_upper, now, bucket),
            )
        else:
            conn.execute(
                """INSERT INTO confidence_calibration
                   (bucket, total_count, correct_count, actual_rate,
                    bayesian_alpha, bayesian_beta, ci_lower, ci_upper, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (bucket, total_count, correct_count, actual_rate,
                 alpha, beta_val, ci_lower, ci_upper, now),
            )
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


# ── 도구 효과 ──

def upsert_tool_effectiveness(
    tool_name: str, used_correct: int, used_incorrect: int,
    total_uses: int, eff_score: float,
) -> None:
    """도구별 예측 성공 상관관계 데이터를 생성 또는 갱신합니다."""
    now = datetime.now(KST).isoformat()
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM tool_effectiveness WHERE tool_name=?", (tool_name,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE tool_effectiveness SET used_correct=?, used_incorrect=?,
                   total_uses=?, eff_score=?, last_updated=? WHERE tool_name=?""",
                (used_correct, used_incorrect, total_uses, eff_score, now, tool_name),
            )
        else:
            conn.execute(
                """INSERT INTO tool_effectiveness
                   (tool_name, used_correct, used_incorrect, total_uses, eff_score, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tool_name, used_correct, used_incorrect, total_uses, eff_score, now),
            )
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def get_tool_effectiveness_all() -> list:
    """모든 도구의 효과 데이터를 조회합니다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT tool_name, used_correct, used_incorrect, total_uses, eff_score, last_updated "
            "FROM tool_effectiveness ORDER BY eff_score DESC"
        ).fetchall()
        return [
            {"tool_name": r[0], "used_correct": r[1], "used_incorrect": r[2],
             "total_uses": r[3], "eff_score": r[4], "last_updated": r[5]}
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


# ── 오답 패턴 ──

def upsert_error_pattern(
    pattern_type: str, description: str, hit_count: int, miss_count: int, hit_rate: float,
) -> None:
    """오답 패턴을 생성 또는 갱신합니다."""
    now = datetime.now(KST).isoformat()
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM error_patterns WHERE pattern_type=?", (pattern_type,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE error_patterns SET description=?, hit_count=?, miss_count=?,
                   hit_rate=?, last_triggered=? WHERE pattern_type=?""",
                (description, hit_count, miss_count, hit_rate, now, pattern_type),
            )
        else:
            conn.execute(
                """INSERT INTO error_patterns
                   (pattern_type, description, hit_count, miss_count, hit_rate, detected_at, last_triggered)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (pattern_type, description, hit_count, miss_count, hit_rate, now, now),
            )
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def get_active_error_patterns() -> list:
    """활성화된 오답 패턴 목록을 조회합니다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT pattern_type, description, hit_count, miss_count, hit_rate, "
            "detected_at, last_triggered FROM error_patterns WHERE active=1 "
            "ORDER BY miss_count DESC LIMIT 20"
        ).fetchall()
        return [
            {"pattern_type": r[0], "description": r[1], "hit_count": r[2],
             "miss_count": r[3], "hit_rate": r[4], "detected_at": r[5], "last_triggered": r[6]}
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# 부서 간 협업 로그 (Phase 12)
# ═══════════════════════════════════════════════════════════════

def save_collaboration_log(
    from_division: str, to_division: str,
    from_agent: str, to_agent: str,
    redirected_to: str = "", task_summary: str = "",
) -> int:
    """부서 간 협업 발생 시 로그를 DB에 저장합니다."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO collaboration_logs
               (from_division, to_division, from_agent, to_agent, redirected_to, task_summary)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (from_division, to_division, from_agent, to_agent, redirected_to, task_summary),
        )
        conn.commit()
        return cur.lastrowid or 0
    except Exception:
        return 0
    finally:
        conn.close()


def get_collaboration_logs(days: int = 30, limit: int = 50) -> list[dict]:
    """최근 협업 로그 조회."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT from_division, to_division, from_agent, to_agent,
                      redirected_to, task_summary, created_at
               FROM collaboration_logs
               WHERE created_at >= datetime('now', ?)
               ORDER BY id DESC LIMIT ?""",
            (f"-{days} days", limit),
        ).fetchall()
        return [
            {
                "from_division": r[0], "to_division": r[1],
                "from_agent": r[2], "to_agent": r[3],
                "redirected_to": r[4], "task_summary": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]
    except Exception:
        return []
    finally:
        conn.close()


def get_collaboration_summary(days: int = 30) -> list[dict]:
    """부서 간 협업 빈도 요약 (히트맵용)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT from_division, to_division, COUNT(*) as cnt
               FROM collaboration_logs
               WHERE created_at >= datetime('now', ?)
               GROUP BY from_division, to_division
               ORDER BY cnt DESC""",
            (f"-{days} days",),
        ).fetchall()
        return [{"from": r[0], "to": r[1], "count": r[2]} for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


# ============================================================
# AGORA: AI 법학 토론 시스템
# ============================================================

def agora_create_session(title: str, paper_text: str) -> int:
    conn = get_connection()
    try:
        now = _now_iso()
        cur = conn.execute(
            "INSERT INTO agora_sessions (title, paper_text, status, created_at, updated_at) VALUES (?,?,?,?,?)",
            (title, paper_text, "active", now, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def agora_get_session(session_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM agora_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def agora_update_session(session_id: int, **kwargs) -> None:
    conn = get_connection()
    try:
        kwargs["updated_at"] = _now_iso()
        sets = ", ".join(f"{k}=?" for k in kwargs)
        conn.execute(f"UPDATE agora_sessions SET {sets} WHERE id=?", (*kwargs.values(), session_id))
        conn.commit()
    finally:
        conn.close()


def agora_create_issue(session_id: int, title: str, description: str = "", parent_id: int | None = None) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO agora_issues (session_id, parent_id, title, description, status, created_at) VALUES (?,?,?,?,?,?)",
            (session_id, parent_id, title, description, "pending", _now_iso()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def agora_get_issues(session_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM agora_issues WHERE session_id=? ORDER BY id", (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def agora_update_issue(issue_id: int, **kwargs) -> None:
    conn = get_connection()
    try:
        sets = ", ".join(f"{k}=?" for k in kwargs)
        conn.execute(f"UPDATE agora_issues SET {sets} WHERE id=?", (*kwargs.values(), issue_id))
        conn.commit()
    finally:
        conn.close()


def agora_save_round(issue_id: int, round_num: int, speaker: str,
                     speaker_model: str, content: str,
                     citations: str = "[]", cost_usd: float = 0) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO agora_rounds (issue_id, round_num, speaker, speaker_model, content, citations, cost_usd, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (issue_id, round_num, speaker, speaker_model, content, citations, cost_usd, _now_iso()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def agora_get_rounds(issue_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM agora_rounds WHERE issue_id=? ORDER BY round_num, id", (issue_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def agora_save_paper_version(session_id: int, version_num: int, full_text: str,
                             diff_html: str = "", change_summary: str = "",
                             issue_id: int | None = None) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO agora_paper_versions (session_id, issue_id, version_num, full_text, diff_html, change_summary, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (session_id, issue_id, version_num, full_text, diff_html, change_summary, _now_iso()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def agora_get_paper_latest(session_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM agora_paper_versions WHERE session_id=? ORDER BY version_num DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def agora_get_paper_versions(session_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, session_id, issue_id, version_num, change_summary, created_at FROM agora_paper_versions WHERE session_id=? ORDER BY version_num",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def agora_get_paper_diff(version_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM agora_paper_versions WHERE id=?", (version_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def agora_save_chapter(session_id: int, issue_id: int, chapter_num: int,
                       title: str, content: str) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO agora_book_chapters (session_id, issue_id, chapter_num, title, content, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (session_id, issue_id, chapter_num, title, content, _now_iso()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def agora_get_book(session_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM agora_book_chapters WHERE session_id=? ORDER BY chapter_num",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
