#!/usr/bin/env python3
"""
CORTHEX v5 DB 마이그레이션
실행: python scripts/migrate_v5.py [--dry-run]

변경 내용:
  1. DB 스냅샷 백업 (corthex_backup_v4_{timestamp}.db)
  2. 기존 프로토타입 데이터 전체 삭제
     (conversations, documents, activity_logs, reports, batch_results)
  3. org 컬럼 추가 (conversations, documents, activity_logs, reports)
  4. sns_accounts 테이블 신규 생성 + 사주 Instagram 자리 확보
"""
import os
import sys
import shutil
import sqlite3
from datetime import datetime

# ── DB 경로 결정 (web/db.py와 동일 로직) ──────────────────────────────────────
def _get_db_path() -> str:
    env_path = os.getenv("CORTHEX_DB_PATH")
    if env_path:
        return env_path
    if os.path.exists("/home/ubuntu"):
        return "/home/ubuntu/corthex.db"
    # 로컬 개발 환경 폴백
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "web", "corthex.db")

DB_PATH = _get_db_path()
DRY_RUN = "--dry-run" in sys.argv


def log(msg: str):
    print(f"  {msg}")


def run_migration():
    if not os.path.exists(DB_PATH):
        print(f"❌ DB 파일 없음: {DB_PATH}")
        sys.exit(1)

    print(f"\n{'[DRY-RUN] ' if DRY_RUN else ''}CORTHEX v5 DB 마이그레이션")
    print(f"  대상 DB: {DB_PATH}")
    print()

    # ── 1. 백업 ──────────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.dirname(DB_PATH)
    backup_path = os.path.join(backup_dir, f"corthex_backup_v4_{ts}.db")

    if not DRY_RUN:
        shutil.copy2(DB_PATH, backup_path)
        log(f"✅ 백업 완료: {backup_path}")
    else:
        log(f"[DRY-RUN] 백업 생략 → {backup_path}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    try:
        # ── 2. 기존 데이터 삭제 ───────────────────────────────────────────────
        tables_to_clear = ["conversations", "documents", "activity_logs", "reports"]
        print("  [STEP 2] 기존 프로토타입 데이터 삭제")
        for tbl in tables_to_clear:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                if not DRY_RUN:
                    conn.execute(f"DELETE FROM {tbl}")
                log(f"  {'[DRY-RUN] ' if DRY_RUN else ''}삭제: {tbl} ({count}행)")
            except sqlite3.OperationalError:
                log(f"  ⚠️  {tbl} 테이블 없음 — 스킵")

        # batch_results 테이블 drop
        try:
            if not DRY_RUN:
                conn.execute("DROP TABLE IF EXISTS batch_results")
            log(f"  {'[DRY-RUN] ' if DRY_RUN else ''}삭제: batch_results (DROP TABLE)")
        except Exception as e:
            log(f"  ⚠️  batch_results 삭제 실패: {e}")

        # ── 3. org 컬럼 추가 ──────────────────────────────────────────────────
        print("  [STEP 3] org 컬럼 추가")
        for tbl in tables_to_clear:
            try:
                # 이미 컬럼이 있으면 스킵 (idempotent)
                cols = [row[1] for row in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
                if "org" in cols:
                    log(f"  ⏭️  {tbl}.org — 이미 존재")
                    continue
                if not DRY_RUN:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN org TEXT DEFAULT ''")
                log(f"  {'[DRY-RUN] ' if DRY_RUN else ''}✅ {tbl}.org 컬럼 추가")
            except sqlite3.OperationalError as e:
                log(f"  ⚠️  {tbl} org 컬럼 추가 실패: {e}")

        # ── 4. sns_accounts 테이블 생성 + 사주 자리 확보 ─────────────────────
        print("  [STEP 4] sns_accounts 테이블 생성")
        if not DRY_RUN:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sns_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    account_name TEXT DEFAULT '',
                    access_token TEXT DEFAULT '',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 사주 Instagram 자리 사전 확보 (토큰은 계정 생성 후 채움)
            existing = conn.execute(
                "SELECT id FROM sns_accounts WHERE org = 'saju' AND platform = 'instagram'"
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO sns_accounts (org, platform, account_name) VALUES ('saju', 'instagram', '')"
                )
                log("  ✅ sns_accounts 생성 + 사주 Instagram 자리 확보")
            else:
                log("  ⏭️  sns_accounts.saju/instagram — 이미 존재")
        else:
            log("  [DRY-RUN] sns_accounts 생성 스킵")

        if not DRY_RUN:
            conn.commit()
            print()
            print("✅ 마이그레이션 완료!")
        else:
            print()
            print("[DRY-RUN] 실제 변경 없이 시뮬레이션 완료.")
            print("  실제 실행: python scripts/migrate_v5.py")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ 오류 발생: {e}")
        if not DRY_RUN:
            print(f"  롤백 완료. 백업에서 복구: {backup_path}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
