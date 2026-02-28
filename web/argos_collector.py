"""ARGOS — 자동 데이터 수집 레이어 (Phase 6-5).

비유: 정보국 "현장 수집반" — 주가/뉴스/공시/매크로/재무/업종을
외부 API(pykrx, yfinance, 네이버, DART, ECOS)에서 가져와 DB에 쌓는 역할.
AI 호출 없이 서버가 심부름(데이터 수집)만 하고, AI는 판단만 합니다.

arm_server.py에서 분리 (P4 리팩토링).
"""
import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta

from db import get_connection, save_activity_log
from config_loader import _load_data, KST

# ══════════════════════════════════════════════════════════════════
# 타이밍 상수 + 전역 변수
# ══════════════════════════════════════════════════════════════════

_ARGOS_LAST_PRICE     = 0.0    # 마지막 주가 수집 시각
_ARGOS_LAST_NEWS      = 0.0    # 마지막 뉴스 수집 시각 (30분)
_ARGOS_LAST_DART      = 0.0    # 마지막 DART 수집 시각 (1시간)
_ARGOS_LAST_MACRO     = 0.0    # 마지막 매크로 수집 시각 (1일)
_ARGOS_LAST_FINANCIAL = 0.0    # 마지막 재무지표 수집 시각 (1일)
_ARGOS_LAST_SECTOR    = 0.0    # 마지막 업종지수 수집 시각 (1일)
_ARGOS_LAST_MONTHLY_RL = 0.0   # 마지막 월간 RL 분석 시각

_ARGOS_NEWS_INTERVAL      = 1800    # 30분
_ARGOS_DART_INTERVAL      = 3600    # 1시간
_ARGOS_MACRO_INTERVAL     = 86400   # 1일
_ARGOS_FINANCIAL_INTERVAL = 86400   # 1일
_ARGOS_SECTOR_INTERVAL    = 86400   # 1일
_ARGOS_MONTHLY_INTERVAL   = 2592000 # 30일

_argos_logger = logging.getLogger("corthex.argos")


# ══════════════════════════════════════════════════════════════════
# 상태 기록
# ══════════════════════════════════════════════════════════════════

def _argos_update_status(data_type: str, error: str = "", count_delta: int = 0) -> None:
    """ARGOS 수집 상태를 DB에 기록합니다."""
    try:
        conn = get_connection()
        now = datetime.now(KST).isoformat()
        conn.execute(
            """INSERT INTO argos_collection_status(data_type, last_collected, last_error, total_count, updated_at)
               VALUES(?, ?, ?, ?, ?)
               ON CONFLICT(data_type) DO UPDATE SET
                 last_collected = CASE WHEN excluded.last_error='' THEN excluded.last_collected ELSE last_collected END,
                 last_error = excluded.last_error,
                 total_count = total_count + excluded.total_count,
                 updated_at = excluded.updated_at""",
            (data_type, now if not error else "", error, count_delta, now)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        _argos_logger.debug("상태 기록 실패: %s", e)


# ══════════════════════════════════════════════════════════════════
# 주가 수집 (pykrx + yfinance)
# ══════════════════════════════════════════════════════════════════

_argos_price_running = False  # 동시 실행 방지 플래그

async def _argos_collect_prices() -> int:
    """관심종목 주가를 pykrx/yfinance로 수집해 DB에 누적합니다 (90일 보존).
    타임아웃: 종목당 20초. 동시 실행 방지 플래그.
    Returns: 저장된 행 수
    """
    global _argos_price_running
    if _argos_price_running:
        _argos_logger.debug("ARGOS 주가 수집 이미 진행 중 — 스킵")
        return 0

    _argos_price_running = True
    try:
        watchlist = _load_data("trading_watchlist", [])
        if not watchlist:
            return 0

        conn = get_connection()
        saved = 0
        now_str = datetime.now(KST).isoformat()
        today = datetime.now(KST).strftime("%Y%m%d")
        # 첫 수집은 7일만 (빠르게), DB에 데이터 있으면 3일만 보충
        try:
            existing = conn.execute("SELECT COUNT(*) FROM argos_price_history").fetchone()[0]
        except Exception:
            existing = 0
        fetch_days = 7 if existing == 0 else 3
        start = (datetime.now(KST) - timedelta(days=fetch_days)).strftime("%Y%m%d")

        kr_tickers = [w for w in watchlist if w.get("market", "KR") == "KR"]
        us_tickers = [w for w in watchlist if w.get("market") == "US"]
        PER_TICKER_TIMEOUT = 20  # 초

        try:
            # ── 한국 주식 (pykrx) ──
            if kr_tickers:
                try:
                    from pykrx import stock as pykrx_stock
                    for w in kr_tickers:
                        ticker = w["ticker"]
                        try:
                            df = await asyncio.wait_for(
                                asyncio.to_thread(
                                    pykrx_stock.get_market_ohlcv_by_date, start, today, ticker
                                ),
                                timeout=PER_TICKER_TIMEOUT,
                            )
                            if df is None or df.empty:
                                _argos_logger.debug("PRICE KR %s: 데이터 없음", ticker)
                                continue
                            ticker_saved = 0
                            for dt_idx, row in df.iterrows():
                                trade_date = str(dt_idx)[:10]
                                close = float(row.get("종가", 0))
                                if close <= 0:
                                    continue
                                prev_rows = df[df.index < dt_idx]
                                prev_close = float(prev_rows.iloc[-1]["종가"]) if not prev_rows.empty else close
                                change_pct = round((close - prev_close) / prev_close * 100, 2) if prev_close else 0
                                conn.execute(
                                    """INSERT OR IGNORE INTO argos_price_history
                                       (ticker, market, trade_date, open_price, high_price, low_price,
                                        close_price, volume, change_pct, collected_at)
                                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                                    (ticker, "KR", trade_date,
                                     float(row.get("시가", close)), float(row.get("고가", close)),
                                     float(row.get("저가", close)), close,
                                     int(row.get("거래량", 0)), change_pct, now_str)
                                )
                                ticker_saved += 1
                            conn.commit()  # 종목별 즉시 커밋 → DB 잠금 최소화
                            saved += ticker_saved
                            _argos_logger.info("PRICE KR %s: %d행 저장 (%d일)", ticker, ticker_saved, fetch_days)
                        except asyncio.TimeoutError:
                            _argos_logger.warning("KR %s: %d초 타임아웃 — 스킵", ticker, PER_TICKER_TIMEOUT)
                        except Exception as e:
                            _argos_logger.debug("KR 주가 파싱 실패 (%s): %s", ticker, e)
                except ImportError:
                    _argos_logger.debug("pykrx 미설치 — 국내 주가 수집 불가")

            # ── 미국 주식 (yfinance) ──
            if us_tickers:
                try:
                    import yfinance as yf
                    period = "7d" if existing == 0 else "3d"
                    for w in us_tickers:
                        ticker = w["ticker"]
                        try:
                            t_obj = yf.Ticker(ticker)
                            hist = await asyncio.wait_for(
                                asyncio.to_thread(lambda t=t_obj, p=period: t.history(period=p)),
                                timeout=PER_TICKER_TIMEOUT,
                            )
                            if hist is None or hist.empty:
                                _argos_logger.debug("PRICE US %s: 데이터 없음", ticker)
                                continue
                            ticker_saved = 0
                            prev_close_val = None
                            for dt_idx, row in hist.iterrows():
                                trade_date = str(dt_idx)[:10]
                                close = round(float(row["Close"]), 4)
                                if close <= 0:
                                    continue
                                chg = round((close - prev_close_val) / prev_close_val * 100, 2) if prev_close_val else 0
                                conn.execute(
                                    """INSERT OR IGNORE INTO argos_price_history
                                       (ticker, market, trade_date, open_price, high_price, low_price,
                                        close_price, volume, change_pct, collected_at)
                                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                                    (ticker, "US", trade_date,
                                     round(float(row.get("Open", close)), 4),
                                     round(float(row.get("High", close)), 4),
                                     round(float(row.get("Low", close)), 4),
                                     close, int(row.get("Volume", 0)), chg, now_str)
                                )
                                ticker_saved += 1
                                prev_close_val = close
                            conn.commit()  # 종목별 즉시 커밋 → DB 잠금 최소화
                            saved += ticker_saved
                            _argos_logger.info("PRICE US %s: %d행 저장 (%s)", ticker, ticker_saved, period)
                        except asyncio.TimeoutError:
                            _argos_logger.warning("US %s: %d초 타임아웃 — 스킵", ticker, PER_TICKER_TIMEOUT)
                        except Exception as e:
                            _argos_logger.debug("US 주가 파싱 실패 (%s): %s", ticker, e)
                except ImportError:
                    _argos_logger.debug("yfinance 미설치 — 해외 주가 수집 불가")

            conn.commit()

            # 90일 초과 데이터 정리
            cutoff = (datetime.now(KST) - timedelta(days=90)).strftime("%Y-%m-%d")
            conn.execute("DELETE FROM argos_price_history WHERE trade_date < ?", (cutoff,))
            conn.commit()
        finally:
            conn.close()

        _argos_logger.info("ARGOS 주가 수집 완료: %d행 (fetch_days=%d)", saved, fetch_days)
        return saved
    finally:
        _argos_price_running = False


# ══════════════════════════════════════════════════════════════════
# 뉴스 수집 (네이버 뉴스 API)
# ══════════════════════════════════════════════════════════════════

async def _argos_collect_news() -> int:
    """네이버 뉴스 API로 관심종목 뉴스를 수집해 DB에 저장합니다 (30일 보존).
    Returns: 저장된 행 수
    """
    naver_id = os.getenv("NAVER_CLIENT_ID", "")
    naver_secret = os.getenv("NAVER_CLIENT_SECRET", "")
    if not naver_id or not naver_secret:
        _argos_logger.debug("NAVER_CLIENT_ID/SECRET 미설정 — 뉴스 수집 불가")
        return 0

    watchlist = _load_data("trading_watchlist", [])
    if not watchlist:
        return 0

    import urllib.request
    import urllib.parse
    conn = get_connection()
    saved = 0
    now_str = datetime.now(KST).isoformat()

    try:
        for w in watchlist[:10]:  # 과부하 방지: 최대 10종목
            keyword = w.get("name") or w.get("ticker", "")
            if not keyword:
                continue
            try:
                encoded = urllib.parse.quote(keyword)
                url = f"https://openapi.naver.com/v1/search/news.json?query={encoded}&display=20&sort=date"
                req = urllib.request.Request(url, headers={
                    "X-Naver-Client-Id": naver_id,
                    "X-Naver-Client-Secret": naver_secret,
                })
                def _fetch(r=req):
                    with urllib.request.urlopen(r, timeout=5) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                data = await asyncio.to_thread(_fetch)
                for item in data.get("items", []):
                    title = re.sub(r"<[^>]+>", "", item.get("title", ""))
                    desc = re.sub(r"<[^>]+>", "", item.get("description", ""))
                    pub_date = item.get("pubDate", now_str)
                    link = item.get("link", "")
                    conn.execute(
                        """INSERT OR IGNORE INTO argos_news_cache
                           (keyword, title, description, link, pub_date, source, collected_at)
                           VALUES(?,?,?,?,?,?,?)""",
                        (keyword, title, desc, link, pub_date, "naver", now_str)
                    )
                    saved += 1
                conn.commit()  # 키워드별 즉시 커밋 → DB 잠금 최소화
            except Exception as e:
                _argos_logger.debug("뉴스 수집 실패 (%s): %s", keyword, e)

        cutoff = (datetime.now(KST) - timedelta(days=30)).isoformat()
        conn.execute("DELETE FROM argos_news_cache WHERE pub_date < ?", (cutoff,))
        conn.commit()
    finally:
        conn.close()

    return saved


# ══════════════════════════════════════════════════════════════════
# DART 공시 수집
# ══════════════════════════════════════════════════════════════════

async def _argos_collect_dart() -> int:
    """DART 공시를 수집해 DB에 저장합니다 (90일 보존).
    Returns: 저장된 행 수
    """
    dart_key = os.getenv("DART_API_KEY", "")
    if not dart_key:
        _argos_logger.debug("DART_API_KEY 미설정 — DART 수집 불가")
        return 0

    watchlist = _load_data("trading_watchlist", [])
    kr_tickers = [w for w in watchlist if w.get("market", "KR") == "KR"]
    if not kr_tickers:
        return 0

    import urllib.request
    import urllib.parse
    conn = get_connection()
    saved = 0
    now_str = datetime.now(KST).isoformat()
    bgn_de = (datetime.now(KST) - timedelta(days=90)).strftime("%Y%m%d")

    try:
        for w in kr_tickers[:10]:  # 과부하 방지
            ticker = w["ticker"]
            try:
                params = urllib.parse.urlencode({
                    "crtfc_key": dart_key,
                    "stock_code": ticker,
                    "bgn_de": bgn_de,
                    "sort": "date",
                    "sort_mth": "desc",
                    "page_count": 20,
                })
                url = f"https://opendart.fss.or.kr/api/list.json?{params}"
                def _fetch(u=url):
                    with urllib.request.urlopen(u, timeout=8) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                data = await asyncio.to_thread(_fetch)
                for item in data.get("list", []):
                    conn.execute(
                        """INSERT OR IGNORE INTO argos_dart_filings
                           (ticker, corp_name, report_nm, rcept_no, flr_nm, rcept_dt, collected_at)
                           VALUES(?,?,?,?,?,?,?)""",
                        (ticker, item.get("corp_name",""), item.get("report_nm",""),
                         item.get("rcept_no",""), item.get("flr_nm",""),
                         item.get("rcept_dt",""), now_str)
                    )
                    saved += 1
                conn.commit()  # 종목별 즉시 커밋 → DB 잠금 최소화
            except Exception as e:
                _argos_logger.debug("DART 수집 실패 (%s): %s", ticker, e)

        cutoff = (datetime.now(KST) - timedelta(days=90)).strftime("%Y%m%d")
        conn.execute("DELETE FROM argos_dart_filings WHERE rcept_dt < ?", (cutoff,))
        conn.commit()
    finally:
        conn.close()

    return saved


# ══════════════════════════════════════════════════════════════════
# 매크로 지표 수집 (USD/KRW, KOSPI, KOSDAQ, VIX, S&P500, NASDAQ, US10Y, KR기준금리)
# ══════════════════════════════════════════════════════════════════

async def _argos_collect_macro() -> int:
    """KOSPI/KOSDAQ/환율 등 매크로 지표를 수집합니다.
    타임아웃: 항목당 15초.
    Returns: 저장된 행 수
    """
    MACRO_TIMEOUT = 15  # 초
    conn = get_connection()
    saved = 0
    now_str = datetime.now(KST).isoformat()
    today_iso = datetime.now(KST).strftime("%Y-%m-%d")

    try:
        # USD/KRW — yfinance
        try:
            import yfinance as yf
            def _fetch_fx():
                t = yf.Ticker("USDKRW=X")
                h = t.history(period="5d")
                return float(h.iloc[-1]["Close"]) if h is not None and not h.empty else None
            rate = await asyncio.wait_for(asyncio.to_thread(_fetch_fx), timeout=MACRO_TIMEOUT)
            if rate:
                conn.execute(
                    "INSERT OR IGNORE INTO argos_macro_data(indicator,trade_date,value,source,collected_at) VALUES(?,?,?,?,?)",
                    ("USD_KRW", today_iso, round(rate, 2), "yfinance", now_str)
                )
                saved += 1
                conn.commit()  # 즉시 커밋
                _argos_logger.info("MACRO USD/KRW: %.2f", rate)
        except asyncio.TimeoutError:
            _argos_logger.warning("USD/KRW: %d초 타임아웃", MACRO_TIMEOUT)
        except Exception as e:
            _argos_logger.debug("USD/KRW 수집 실패: %s", e)

        # KOSPI / KOSDAQ — pykrx
        try:
            from pykrx import stock as pykrx_stock
            today = datetime.now(KST).strftime("%Y%m%d")
            start = (datetime.now(KST) - timedelta(days=7)).strftime("%Y%m%d")
            for ticker, label in [("1001", "KOSPI"), ("2001", "KOSDAQ")]:
                try:
                    df = await asyncio.wait_for(
                        asyncio.to_thread(
                            pykrx_stock.get_index_ohlcv_by_date, start, today, ticker
                        ),
                        timeout=MACRO_TIMEOUT,
                    )
                    if df is not None and not df.empty:
                        close = float(df.iloc[-1]["종가"])
                        trade_date = str(df.index[-1])[:10]
                        conn.execute(
                            "INSERT OR IGNORE INTO argos_macro_data(indicator,trade_date,value,source,collected_at) VALUES(?,?,?,?,?)",
                            (label, trade_date, round(close, 2), "pykrx", now_str)
                        )
                        conn.commit()  # 즉시 커밋
                        saved += 1
                        _argos_logger.info("MACRO %s: %.2f", label, close)
                except asyncio.TimeoutError:
                    _argos_logger.warning("%s: %d초 타임아웃", label, MACRO_TIMEOUT)
                except Exception as e:
                    _argos_logger.debug("%s 수집 실패: %s", label, e)
        except ImportError:
            pass

        # VIX — yfinance
        try:
            import yfinance as yf
            def _fetch_vix():
                t = yf.Ticker("^VIX")
                h = t.history(period="5d")
                return float(h.iloc[-1]["Close"]) if h is not None and not h.empty else None
            vix = await asyncio.wait_for(asyncio.to_thread(_fetch_vix), timeout=MACRO_TIMEOUT)
            if vix:
                conn.execute(
                    "INSERT OR IGNORE INTO argos_macro_data(indicator,trade_date,value,source,collected_at) VALUES(?,?,?,?,?)",
                    ("VIX", today_iso, round(vix, 2), "yfinance", now_str)
                )
                conn.commit()  # 즉시 커밋
                saved += 1
                _argos_logger.info("MACRO VIX: %.2f", vix)
        except asyncio.TimeoutError:
            _argos_logger.warning("VIX: %d초 타임아웃", MACRO_TIMEOUT)
        except Exception as e:
            _argos_logger.debug("VIX 수집 실패: %s", e)


        # S&P500 / 나스닥 / 미국 10년 국채금리 — yfinance
        for yf_ticker, label in [("^GSPC", "SP500"), ("^IXIC", "NASDAQ"), ("^TNX", "US10Y")]:
            try:
                import yfinance as yf
                def _fetch_yf(sym=yf_ticker):
                    t = yf.Ticker(sym)
                    h = t.history(period="5d")
                    return float(h.iloc[-1]["Close"]) if h is not None and not h.empty else None
                val = await asyncio.wait_for(asyncio.to_thread(_fetch_yf), timeout=MACRO_TIMEOUT)
                if val:
                    conn.execute(
                        "INSERT OR IGNORE INTO argos_macro_data(indicator,trade_date,value,source,collected_at) VALUES(?,?,?,?,?)",
                        (label, today_iso, round(val, 4), "yfinance", now_str)
                    )
                    conn.commit()
                    saved += 1
                    _argos_logger.info("MACRO %s: %.4f", label, val)
            except asyncio.TimeoutError:
                _argos_logger.warning("%s: %d초 타임아웃", label, MACRO_TIMEOUT)
            except Exception as e:
                _argos_logger.debug("%s 수집 실패: %s", label, e)

        # 한국 기준금리 — ECOS API
        try:
            ecos_key = os.getenv("ECOS_API_KEY", "")
            if ecos_key:
                import urllib.request
                ecos_url = (
                    f"https://ecos.bok.or.kr/api/StatisticSearch/{ecos_key}/json/kr"
                    f"/1/5/722Y001/M/{today_iso[:4]}{today_iso[5:7]}/{today_iso[:4]}{today_iso[5:7]}"
                )
                def _fetch_ecos(url=ecos_url):
                    with urllib.request.urlopen(url, timeout=10) as r:
                        import json as _json
                        return _json.loads(r.read().decode("utf-8"))
                ecos_data = await asyncio.wait_for(asyncio.to_thread(_fetch_ecos), timeout=MACRO_TIMEOUT)
                rows_ecos = ecos_data.get("StatisticSearch", {}).get("row", [])
                if rows_ecos:
                    rate = float(rows_ecos[-1].get("DATA_VALUE", 0))
                    period = rows_ecos[-1].get("TIME", today_iso[:7])
                    trade_date_ecos = f"{period[:4]}-{period[4:6]}-01"
                    conn.execute(
                        "INSERT OR IGNORE INTO argos_macro_data(indicator,trade_date,value,source,collected_at) VALUES(?,?,?,?,?)",
                        ("KR_RATE", trade_date_ecos, rate, "ecos", now_str)
                    )
                    conn.commit()
                    saved += 1
                    _argos_logger.info("MACRO KR_RATE: %.2f%%", rate)
        except asyncio.TimeoutError:
            _argos_logger.warning("KR_RATE: %d초 타임아웃", MACRO_TIMEOUT)
        except Exception as e:
            _argos_logger.debug("KR_RATE 수집 실패: %s", e)

        cutoff = (datetime.now(KST) - timedelta(days=365)).strftime("%Y-%m-%d")
        conn.execute("DELETE FROM argos_macro_data WHERE trade_date < ?", (cutoff,))
        conn.commit()
    finally:
        conn.close()

    _argos_logger.info("ARGOS 매크로 수집 완료: %d건", saved)
    return saved


# ══════════════════════════════════════════════════════════════════
# 순차 수집 오케스트레이터 + 안전 래퍼
# ══════════════════════════════════════════════════════════════════

_argos_seq_lock = asyncio.Lock()  # 순차 수집 중복 실행 방지 (Lock 기반)

async def _argos_sequential_collect(now_ts: float):
    """ARGOS 수집을 순차 실행합니다 (DB lock 방지).
    동시에 여러 수집이 DB를 잡지 않도록 하나씩 순서대로.
    """
    global _ARGOS_LAST_NEWS, _ARGOS_LAST_DART, _ARGOS_LAST_MACRO, _ARGOS_LAST_FINANCIAL, _ARGOS_LAST_SECTOR
    if _argos_seq_lock.locked():
        return
    async with _argos_seq_lock:
        try:
            # 1) 주가 — 매 사이클
            await _argos_collect_prices_safe()

            # 2) 뉴스 — 30분마다
            if now_ts - _ARGOS_LAST_NEWS > _ARGOS_NEWS_INTERVAL:
                _ARGOS_LAST_NEWS = now_ts
                await _argos_collect_news_safe()

            # 3) DART — 1시간마다
            if now_ts - _ARGOS_LAST_DART > _ARGOS_DART_INTERVAL:
                _ARGOS_LAST_DART = now_ts
                await _argos_collect_dart_safe()

            # 4) 매크로 — 1일마다 (S&P500/나스닥/국채금리/기준금리 포함)
            if now_ts - _ARGOS_LAST_MACRO > _ARGOS_MACRO_INTERVAL:
                _ARGOS_LAST_MACRO = now_ts
                await _argos_collect_macro_safe()

            # 5) 재무지표 — 1일마다 (PER/PBR/EPS/BPS)
            if now_ts - _ARGOS_LAST_FINANCIAL > _ARGOS_FINANCIAL_INTERVAL:
                _ARGOS_LAST_FINANCIAL = now_ts
                await _argos_collect_financial_safe()

            # 6) 업종지수 — 1일마다 (전기전자/화학/금융 등 11개)
            if now_ts - _ARGOS_LAST_SECTOR > _ARGOS_SECTOR_INTERVAL:
                _ARGOS_LAST_SECTOR = now_ts
                await _argos_collect_sector_safe()
        except Exception as e:
            _argos_logger.error("ARGOS 순차 수집 오류: %s", e)


async def _argos_collect_prices_safe():
    """주가 수집 — 예외 안전 래퍼. 전체 3분 타임아웃."""
    try:
        n = await asyncio.wait_for(_argos_collect_prices(), timeout=180)
        if n > 0:
            _argos_update_status("price", count_delta=n)
    except asyncio.TimeoutError:
        _argos_update_status("price", error="전체 3분 타임아웃")
        _argos_logger.error("ARGOS 주가 수집: 전체 3분 타임아웃")
    except Exception as e:
        _argos_update_status("price", error=str(e)[:200])
        _argos_logger.error("ARGOS 주가 수집 실패: %s", e)


async def _argos_collect_news_safe():
    """뉴스 수집 — 예외 안전 래퍼. 전체 2분 타임아웃."""
    try:
        n = await asyncio.wait_for(_argos_collect_news(), timeout=120)
        _argos_update_status("news", count_delta=n)
        _argos_logger.info("ARGOS 뉴스 수집 완료: %d건", n)
    except asyncio.TimeoutError:
        _argos_update_status("news", error="전체 2분 타임아웃")
        _argos_logger.error("ARGOS 뉴스 수집: 전체 2분 타임아웃")
    except Exception as e:
        _argos_update_status("news", error=str(e)[:200])
        _argos_logger.error("ARGOS 뉴스 수집 실패: %s", e)


async def _argos_collect_dart_safe():
    """DART 수집 — 예외 안전 래퍼. 전체 2분 타임아웃."""
    try:
        n = await asyncio.wait_for(_argos_collect_dart(), timeout=120)
        _argos_update_status("dart", count_delta=n)
        _argos_logger.info("ARGOS DART 수집 완료: %d건", n)
    except asyncio.TimeoutError:
        _argos_update_status("dart", error="전체 2분 타임아웃")
        _argos_logger.error("ARGOS DART 수집: 전체 2분 타임아웃")
    except Exception as e:
        _argos_update_status("dart", error=str(e)[:200])
        _argos_logger.error("ARGOS DART 수집 실패: %s", e)


async def _argos_collect_macro_safe():
    """매크로 수집 — 예외 안전 래퍼. 전체 2분 타임아웃."""
    try:
        n = await asyncio.wait_for(_argos_collect_macro(), timeout=120)
        _argos_update_status("macro", count_delta=n)
        _argos_logger.info("ARGOS 매크로 수집 완료: %d건", n)
    except asyncio.TimeoutError:
        _argos_update_status("macro", error="전체 2분 타임아웃")
        _argos_logger.error("ARGOS 매크로 수집: 전체 2분 타임아웃")
    except Exception as e:
        _argos_update_status("macro", error=str(e)[:200])
        _argos_logger.error("ARGOS 매크로 수집 실패: %s", e)


# ══════════════════════════════════════════════════════════════════
# 재무지표 수집 (PER/PBR/EPS/BPS — pykrx)
# ══════════════════════════════════════════════════════════════════

async def _argos_collect_financial() -> int:
    """pykrx로 관심종목 재무지표(PER/PBR/EPS 등)를 수집해 DB에 저장 (1일 1회).
    Returns: 저장된 행 수
    """
    conn = get_connection()
    saved = 0
    now_str = datetime.now(KST).isoformat()
    # 장이 마감된 후(15:30 KST)에만 오늘 데이터 가용 → 15:30 이전은 전날 사용
    now_kst = datetime.now(KST)
    if now_kst.hour < 16:
        ref_date = (now_kst - timedelta(days=1)).strftime("%Y%m%d")
        ref_date_iso = (now_kst - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        ref_date = now_kst.strftime("%Y%m%d")
        ref_date_iso = now_kst.strftime("%Y-%m-%d")
    today = ref_date
    today_iso = ref_date_iso

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS argos_financial_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                per REAL, pbr REAL, eps REAL, dps REAL, bps REAL,
                source TEXT DEFAULT 'pykrx',
                collected_at TEXT,
                UNIQUE(ticker, trade_date)
            )
        """)
        conn.commit()

        from pykrx import stock as pykrx_stock
        watchlist = _load_data("trading_watchlist", [])
        kr_tickers = [w for w in watchlist if w.get("market", "KR") == "KR"]
        if not kr_tickers:
            return 0

        for w in kr_tickers:
            ticker = w["ticker"]
            try:
                df = await asyncio.wait_for(
                    asyncio.to_thread(pykrx_stock.get_market_fundamental, today, today, ticker),
                    timeout=20,
                )
                if df is not None and not df.empty:
                    row = df.iloc[-1]
                    conn.execute(
                        """INSERT OR IGNORE INTO argos_financial_data
                           (ticker, trade_date, per, pbr, eps, dps, bps, source, collected_at)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (ticker, today_iso,
                         float(row.get("PER", 0) or 0),
                         float(row.get("PBR", 0) or 0),
                         float(row.get("EPS", 0) or 0),
                         float(row.get("DPS", 0) or 0),
                         float(row.get("BPS", 0) or 0),
                         "pykrx", now_str)
                    )
                    conn.commit()
                    saved += 1
                    _argos_logger.info("FINANCIAL %s: PER=%.1f PBR=%.2f", ticker,
                                       row.get("PER", 0), row.get("PBR", 0))
            except asyncio.TimeoutError:
                _argos_logger.warning("FINANCIAL %s: 20초 타임아웃", ticker)
            except Exception as e:
                _argos_logger.warning("FINANCIAL %s 실패: %s", ticker, e)

        cutoff = (datetime.now(KST) - timedelta(days=90)).strftime("%Y-%m-%d")
        conn.execute("DELETE FROM argos_financial_data WHERE trade_date < ?", (cutoff,))
        conn.commit()
    except ImportError:
        _argos_logger.debug("pykrx 미설치 — 재무지표 수집 불가")
    finally:
        conn.close()

    _argos_logger.info("ARGOS 재무지표 수집 완료: %d건", saved)
    return saved


async def _argos_collect_financial_safe():
    """재무지표 수집 — 예외 안전 래퍼. 전체 3분 타임아웃."""
    try:
        n = await asyncio.wait_for(_argos_collect_financial(), timeout=180)
        _argos_update_status("financial", count_delta=n)
        _argos_logger.info("ARGOS 재무지표 수집 완료: %d건", n)
    except asyncio.TimeoutError:
        _argos_update_status("financial", error="전체 3분 타임아웃")
        _argos_logger.error("ARGOS 재무지표 수집: 전체 3분 타임아웃")
    except Exception as e:
        _argos_update_status("financial", error=str(e)[:200])
        _argos_logger.error("ARGOS 재무지표 수집 실패: %s", e)


# ══════════════════════════════════════════════════════════════════
# 업종지수 수집 (11개 업종 — pykrx)
# ══════════════════════════════════════════════════════════════════

async def _argos_collect_sector() -> int:
    """pykrx로 주요 업종지수를 수집해 DB에 저장 (1일 1회).
    Returns: 저장된 행 수
    """
    SECTOR_CODES = [
        ("1028", "전기전자"), ("1003", "화학"), ("1004", "의약품"),
        ("1006", "철강금속"), ("1008", "기계"), ("1022", "유통업"),
        ("1024", "건설업"), ("1027", "통신업"), ("1029", "금융업"),
        ("1032", "서비스업"), ("1005", "비금속광물"),
    ]
    conn = get_connection()
    saved = 0
    now_str = datetime.now(KST).isoformat()

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS argos_sector_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sector_name TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close_val REAL,
                change_pct REAL,
                source TEXT DEFAULT 'pykrx',
                collected_at TEXT,
                UNIQUE(sector_name, trade_date)
            )
        """)
        conn.commit()

        from pykrx import stock as pykrx_stock
        today = datetime.now(KST).strftime("%Y%m%d")
        start = (datetime.now(KST) - timedelta(days=7)).strftime("%Y%m%d")

        for code, name in SECTOR_CODES:
            try:
                df = await asyncio.wait_for(
                    asyncio.to_thread(pykrx_stock.get_index_ohlcv_by_date, start, today, code),
                    timeout=15,
                )
                if df is not None and not df.empty:
                    close = float(df.iloc[-1]["종가"])
                    trade_date = str(df.index[-1])[:10]
                    # 전일 대비 등락률
                    change_pct = 0.0
                    if len(df) >= 2:
                        prev = float(df.iloc[-2]["종가"])
                        change_pct = (close - prev) / prev * 100 if prev != 0 else 0.0
                    conn.execute(
                        """INSERT OR IGNORE INTO argos_sector_data
                           (sector_name, trade_date, close_val, change_pct, source, collected_at)
                           VALUES(?,?,?,?,?,?)""",
                        (name, trade_date, round(close, 2), round(change_pct, 2), "pykrx", now_str)
                    )
                    conn.commit()
                    saved += 1
                    _argos_logger.info("SECTOR %s: %.2f (%+.2f%%)", name, close, change_pct)
            except asyncio.TimeoutError:
                _argos_logger.warning("SECTOR %s: 15초 타임아웃", name)
            except Exception as e:
                _argos_logger.debug("SECTOR %s 실패: %s", name, e)

        cutoff = (datetime.now(KST) - timedelta(days=90)).strftime("%Y-%m-%d")
        conn.execute("DELETE FROM argos_sector_data WHERE trade_date < ?", (cutoff,))
        conn.commit()
    except ImportError:
        _argos_logger.debug("pykrx 미설치 — 업종지수 수집 불가")
    finally:
        conn.close()

    _argos_logger.info("ARGOS 업종지수 수집 완료: %d건", saved)
    return saved


async def _argos_collect_sector_safe():
    """업종지수 수집 — 예외 안전 래퍼. 전체 3분 타임아웃."""
    try:
        n = await asyncio.wait_for(_argos_collect_sector(), timeout=180)
        _argos_update_status("sector", count_delta=n)
        _argos_logger.info("ARGOS 업종지수 수집 완료: %d건", n)
    except asyncio.TimeoutError:
        _argos_update_status("sector", error="전체 3분 타임아웃")
        _argos_logger.error("ARGOS 업종지수 수집: 전체 3분 타임아웃")
    except Exception as e:
        _argos_update_status("sector", error=str(e)[:200])
        _argos_logger.error("ARGOS 업종지수 수집 실패: %s", e)


# ══════════════════════════════════════════════════════════════════
# 월간 강화학습 패턴 분석 (Phase 6-9)
# ══════════════════════════════════════════════════════════════════

async def _argos_monthly_rl_analysis():
    """월 1회: AI에게 최근 오답 패턴 분석 요청 → error_patterns 테이블 업데이트.
    Phase 6-9 강화학습 파이프라인.
    """
    _argos_logger.info("📊 월간 강화학습 패턴 분석 시작")
    save_activity_log("system", "📊 월간 강화학습 패턴 분석 시작 (크론)", "info")
    try:
        conn = get_connection()
        # 최근 30일 내 틀린 예측 집계
        rows = conn.execute(
            """SELECT ticker, direction, confidence, return_pct_7d, analyzed_at
               FROM cio_predictions
               WHERE correct_7d = 0
                 AND analyzed_at >= datetime('now', '-30 days')
               ORDER BY analyzed_at DESC
               LIMIT 30"""
        ).fetchall()
        conn.close()

        if not rows:
            _argos_logger.info("최근 30일 오답 없음 — 패턴 분석 스킵")
            return

        wrong_list = [
            f"- {r[0]} ({r[1]}, 신뢰도 {r[2]}%) → 실제수익 {r[3]}% ({r[4][:10]})"
            for r in rows
        ]
        prompt = (
            "다음은 최근 30일간 틀린 매매 예측 목록입니다:\n"
            + "\n".join(wrong_list)
            + "\n\n공통 패턴을 분석해주세요: "
            "① 어떤 종목/방향에서 많이 틀렸나? "
            "② 높은 신뢰도인데 틀린 케이스 원인? "
            "③ 다음 분석 시 주의사항 3가지를 간결하게 요약하세요."
        )

        from ai_handler import ask_ai
        result = await ask_ai(
            agent_id="secretary",
            messages=[{"role": "user", "content": prompt}],
            model=None,  # config/models.yaml에서 자동 선택
            task_id=f"rl_monthly_{datetime.now(KST).strftime('%Y%m')}",
        )

        analysis_text = result.get("content", "")
        if analysis_text:
            conn = get_connection()
            conn.execute(
                """INSERT INTO error_patterns
                   (pattern_type, description, ticker_filter, direction_filter,
                    confidence_threshold, active, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                ("monthly_rl", analysis_text[:2000], "", "", 0.0, 1,
                 datetime.now(KST).isoformat(), datetime.now(KST).isoformat())
            )
            conn.commit()
            conn.close()
            save_activity_log("system", f"📊 월간 RL 패턴 분석 완료 ({len(rows)}건 분석)", "success")
            _argos_logger.info("월간 RL 패턴 분석 완료: %d건", len(rows))
    except Exception as e:
        _argos_logger.error("월간 RL 패턴 분석 실패: %s", e)


# ══════════════════════════════════════════════════════════════════
# ARGOS 컨텍스트 빌더 (팀장 프롬프트 주입용)
# ══════════════════════════════════════════════════════════════════

async def _build_argos_context_section(market_watchlist: list, market: str = "KR") -> str:
    """ARGOS DB에서 수집된 데이터를 꺼내 팀장 프롬프트에 직접 주입.

    서버가 심부름(데이터 수집)을 완료 → 팀장은 해석만.
    DB에 데이터 없으면 해당 섹션 생략 (팀장이 판단하도록).
    """
    conn = get_connection()
    sections = []

    # ① 종목별 최근 주가 (최근 10거래일)
    price_rows_all = []
    for w in market_watchlist:
        ticker = w["ticker"]
        try:
            rows = conn.execute(
                """SELECT trade_date, close_price, change_pct, volume
                   FROM argos_price_history
                   WHERE ticker=?
                   ORDER BY trade_date DESC LIMIT 10""",
                (ticker,)
            ).fetchall()
            if rows:
                price_rows_all.append((w["name"], ticker, rows))
        except Exception:
            pass

    if price_rows_all:
        lines = ["\n\n## 📈 최근 주가 (ARGOS 수집 — 서버 제공)"]
        for name, ticker, rows in price_rows_all:
            latest = rows[0]
            unit = "원" if market == "KR" else "USD"
            lines.append(f"\n### {name} ({ticker})")
            lines.append(f"  현재가: {latest[1]:,.0f}{unit}  전일대비: {(latest[2] or 0):+.2f}%")
            lines.append("  | 날짜 | 종가 | 등락률 | 거래량 |")
            lines.append("  |------|------|--------|--------|")
            for r in rows:
                lines.append(f"  | {r[0]} | {r[1]:,.0f} | {(r[2] or 0):+.2f}% | {(r[3] or 0):,.0f} |")
        sections.append("\n".join(lines))

    # ② 매크로 지표 (KOSPI, USD_KRW 등)
    try:
        macro_rows = conn.execute(
            """SELECT indicator, trade_date, value
               FROM argos_macro_data
               ORDER BY indicator, trade_date DESC"""
        ).fetchall()
        if macro_rows:
            macro_dict: dict = {}
            for r in macro_rows:
                if r[0] not in macro_dict:
                    macro_dict[r[0]] = (r[1], r[2])
            lines = ["\n\n## 🌐 매크로 지표 (ARGOS 수집 — 서버 제공)"]
            for indicator, (dt, val) in macro_dict.items():
                lines.append(f"  {indicator}: {val:,.2f} ({dt})")
            sections.append("\n".join(lines))
    except Exception:
        pass

    # ③ 최신 공시 (DART — ticker 기준)
    dart_found = []
    for w in market_watchlist:
        ticker = w["ticker"]
        try:
            rows = conn.execute(
                """SELECT corp_name, report_nm, rcept_dt
                   FROM argos_dart_filings
                   WHERE ticker=?
                   ORDER BY rcept_dt DESC LIMIT 5""",
                (ticker,)
            ).fetchall()
            if rows:
                dart_found.append((w["name"], ticker, rows))
        except Exception:
            pass

    if dart_found:
        lines = ["\n\n## 📋 최신 공시 (ARGOS 수집 — 서버 제공)"]
        for name, ticker, rows in dart_found:
            lines.append(f"\n### {name} ({ticker})")
            for r in rows:
                lines.append(f"  [{r[2]}] {r[1]}")
        sections.append("\n".join(lines))

    # ④ 뉴스 캐시 (종목명 키워드)
    news_found = []
    for w in market_watchlist:
        keyword = w["name"]
        try:
            rows = conn.execute(
                """SELECT title, description, pub_date
                   FROM argos_news_cache
                   WHERE keyword=?
                   ORDER BY pub_date DESC LIMIT 5""",
                (keyword,)
            ).fetchall()
            if rows:
                news_found.append((keyword, rows))
        except Exception:
            pass

    if news_found:
        lines = ["\n\n## 📰 최신 뉴스 (ARGOS 수집 — 서버 제공)"]
        for keyword, rows in news_found:
            lines.append(f"\n### {keyword}")
            for r in rows:
                title = (r[0] or "")[:60]
                desc = (r[1] or "")[:80]
                lines.append(f"  [{r[2][:10] if r[2] else ''}] {title}")
                if desc:
                    lines.append(f"    → {desc}")
        sections.append("\n".join(lines))

    # ⑤ 재무지표 (PER/PBR/EPS — pykrx 1일 수집)
    try:
        conn2 = get_connection()
        fin_found = []
        for w in market_watchlist:
            ticker = w["ticker"]
            try:
                row = conn2.execute(
                    """SELECT trade_date, per, pbr, eps, bps
                       FROM argos_financial_data
                       WHERE ticker=?
                       ORDER BY trade_date DESC LIMIT 1""",
                    (ticker,)
                ).fetchone()
                if row:
                    fin_found.append((w["name"], ticker, row))
            except Exception:
                pass
        conn2.close()
        if fin_found:
            lines = ["\n\n## 💹 재무지표 (ARGOS 수집 — 서버 제공)"]
            lines.append("  | 종목 | PER | PBR | EPS | BPS | 기준일 |")
            lines.append("  |------|-----|-----|-----|-----|--------|")
            for name, ticker, r in fin_found:
                lines.append(f"  | {name}({ticker}) | {r[1]:.1f} | {r[2]:.2f} | {r[3]:,.0f} | {r[4]:,.0f} | {r[0]} |")
            sections.append("\n".join(lines))
    except Exception:
        pass

    # ⑥ 업종지수 (pykrx 11개 업종 — 1일 수집)
    try:
        conn3 = get_connection()
        sector_rows = conn3.execute(
            """SELECT s1.sector_name, s1.close_val, s1.change_pct, s1.trade_date
               FROM argos_sector_data s1
               INNER JOIN (
                   SELECT sector_name, MAX(trade_date) AS max_date
                   FROM argos_sector_data GROUP BY sector_name
               ) s2 ON s1.sector_name=s2.sector_name AND s1.trade_date=s2.max_date
               ORDER BY s1.change_pct DESC"""
        ).fetchall()
        conn3.close()
        if sector_rows:
            lines = ["\n\n## 🏭 업종지수 (ARGOS 수집 — 서버 제공)"]
            lines.append("  | 업종 | 지수 | 등락률 | 기준일 |")
            lines.append("  |------|------|--------|--------|")
            for r in sector_rows:
                arrow = "▲" if r[2] > 0 else ("▼" if r[2] < 0 else "─")
                lines.append(f"  | {r[0]} | {r[1]:,.2f} | {arrow}{abs(r[2]):.2f}% | {r[3]} |")
            sections.append("\n".join(lines))
    except Exception:
        pass

    if not sections:
        return "\n\n## 📡 ARGOS 수집 데이터 없음 (수집 중이거나 관심종목 미등록)"

    return "".join(sections)
