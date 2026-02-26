"""
ARGOS DB 리더 — 에이전트 도구가 서버 수집 데이터를 읽는 공통 헬퍼.

서버(ARGOS)가 1분~24시간 주기로 수집한 데이터를 DB에서 직접 읽습니다.
외부 API 호출 없이 DB 캐시를 사용하므로 빠르고 API 쿼터를 절약합니다.
DB 데이터가 없거나 너무 오래된 경우 None을 반환하여 폴백을 유도합니다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("corthex.tools.argos_reader")

# 데이터 유형별 허용 최대 경과 시간 (분)
_STALENESS = {
    "price": 10,       # 주가: 10분
    "news": 60,        # 뉴스: 1시간
    "dart": 120,       # 공시: 2시간
    "macro": 1440,     # 매크로: 24시간
}


def _get_conn():
    """서버 DB 커넥션을 가져옵니다. 서버 외부에서는 None."""
    try:
        from web.db import get_connection
        return get_connection()
    except Exception:
        return None


def _is_fresh(data_type: str) -> bool:
    """ARGOS 수집 데이터가 신선한지 확인합니다."""
    conn = _get_conn()
    if not conn:
        return False
    try:
        row = conn.execute(
            "SELECT last_collected FROM argos_collection_status WHERE data_type=?",
            (data_type,)
        ).fetchone()
        if not row or not row[0]:
            return False
        last = datetime.fromisoformat(row[0].replace("Z", "+00:00").replace("+00:00", ""))
        elapsed = (datetime.utcnow() - last).total_seconds() / 60
        return elapsed < _STALENESS.get(data_type, 60)
    except Exception as e:
        logger.debug("ARGOS freshness check failed: %s", e)
        return False


def get_price_data(ticker: str, days: int = 90) -> list[dict] | None:
    """ARGOS DB에서 주가 데이터를 읽습니다.

    Returns: [{date, open, high, low, close, volume, change_pct}, ...] or None
    """
    conn = _get_conn()
    if not conn:
        return None
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT trade_date, open_price, high_price, low_price, close_price,
                      volume, change_pct
               FROM argos_price_history
               WHERE ticker=? AND trade_date >= ?
               ORDER BY trade_date""",
            (ticker, cutoff),
        ).fetchall()
        if not rows:
            return None
        return [
            {
                "date": r[0], "open": r[1], "high": r[2], "low": r[3],
                "close": r[4], "volume": r[5], "change_pct": r[6],
            }
            for r in rows
        ]
    except Exception as e:
        logger.debug("ARGOS price read failed: %s", e)
        return None


def get_price_dataframe(ticker: str, days: int = 200):
    """ARGOS DB에서 주가를 pandas DataFrame으로 반환 (kr_stock/technical_analyzer 호환).

    Returns: DataFrame with columns [시가,고가,저가,종가,거래량] index=DatetimeIndex, or None
    """
    data = get_price_data(ticker, days)
    if not data:
        return None
    try:
        import pandas as pd
        df = pd.DataFrame(data)
        df.index = pd.to_datetime(df["date"])
        df = df.rename(columns={
            "open": "시가", "high": "고가", "low": "저가",
            "close": "종가", "volume": "거래량",
        })
        df = df[["시가", "고가", "저가", "종가", "거래량"]]
        if len(df) < 5:
            return None
        return df
    except Exception as e:
        logger.debug("ARGOS DataFrame conversion failed: %s", e)
        return None


def get_news_data(keyword: str, days: int = 7) -> list[dict] | None:
    """ARGOS DB에서 뉴스 캐시를 읽습니다.

    Returns: [{title, description, link, pub_date, source}, ...] or None
    """
    conn = _get_conn()
    if not conn:
        return None
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT title, description, link, pub_date, source
               FROM argos_news_cache
               WHERE keyword=? AND collected_at >= ?
               ORDER BY pub_date DESC LIMIT 20""",
            (keyword, cutoff),
        ).fetchall()
        if not rows:
            return None
        return [
            {"title": r[0], "description": r[1], "link": r[2],
             "pub_date": r[3], "source": r[4]}
            for r in rows
        ]
    except Exception as e:
        logger.debug("ARGOS news read failed: %s", e)
        return None


def get_dart_filings(ticker: str, days: int = 90) -> list[dict] | None:
    """ARGOS DB에서 DART 공시 목록을 읽습니다."""
    conn = _get_conn()
    if not conn:
        return None
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT corp_name, report_nm, rcept_no, flr_nm, rcept_dt
               FROM argos_dart_filings
               WHERE ticker=? AND rcept_dt >= ?
               ORDER BY rcept_dt DESC LIMIT 20""",
            (ticker, cutoff),
        ).fetchall()
        if not rows:
            return None
        return [
            {"corp_name": r[0], "report_nm": r[1], "rcept_no": r[2],
             "flr_nm": r[3], "rcept_dt": r[4]}
            for r in rows
        ]
    except Exception as e:
        logger.debug("ARGOS dart read failed: %s", e)
        return None


def get_macro_data() -> dict[str, list[dict]] | None:
    """ARGOS DB에서 매크로 지표를 읽습니다.

    Returns: {"USD_KRW": [{date, value}, ...], "KOSPI": [...], ...} or None
    """
    conn = _get_conn()
    if not conn:
        return None
    try:
        rows = conn.execute(
            """SELECT indicator, trade_date, value
               FROM argos_macro_data
               ORDER BY indicator, trade_date"""
        ).fetchall()
        if not rows:
            return None
        result: dict[str, list] = {}
        for r in rows:
            result.setdefault(r[0], []).append({"date": r[1], "value": r[2]})
        return result if result else None
    except Exception as e:
        logger.debug("ARGOS macro read failed: %s", e)
        return None
