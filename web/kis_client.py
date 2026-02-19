"""한국투자증권 OpenAPI 클라이언트 — 자동매매 연동."""
import os
import asyncio
import logging
from datetime import datetime, timedelta, timezone, time as dtime
from typing import Optional

# 한국 시간대 (UTC+9)
_KST = timezone(timedelta(hours=9))
# 매일 토큰 자동 갱신 시각 (KST)
_RENEWAL_HOUR_KST = 7   # 오전 7시
_RENEWAL_MINUTE_KST = 0

import httpx

logger = logging.getLogger("corthex.kis")

# 환경변수
KIS_APP_KEY = os.getenv("KOREA_INVEST_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KOREA_INVEST_APP_SECRET", "")
_KIS_ACCOUNT_RAW = os.getenv("KOREA_INVEST_ACCOUNT", "")
KIS_IS_MOCK = os.getenv("KOREA_INVEST_IS_MOCK", "true").lower() in ("true", "1", "yes")

# 계좌번호 파싱 (예: "44049763-01" 또는 "4404976301")
if "-" in _KIS_ACCOUNT_RAW:
    _parts = _KIS_ACCOUNT_RAW.split("-")
    KIS_ACCOUNT_NO = _parts[0]   # 8자리 계좌번호
    KIS_ACCOUNT_CODE = _parts[1] if len(_parts) > 1 else "01"  # 상품코드
else:
    KIS_ACCOUNT_NO = _KIS_ACCOUNT_RAW[:8]
    KIS_ACCOUNT_CODE = _KIS_ACCOUNT_RAW[8:] if len(_KIS_ACCOUNT_RAW) > 8 else "01"

# API 기본 URL
KIS_BASE_REAL = "https://openapi.koreainvestment.com:9443"
KIS_BASE_MOCK = "https://openapivts.koreainvestment.com:29443"
KIS_BASE = KIS_BASE_MOCK if KIS_IS_MOCK else KIS_BASE_REAL

# TR_ID (모의투자 vs 실거래)
# 모의투자 TR_ID는 앞에 'V' 붙음
_TR = {
    "buy":     "VTTC0802U" if KIS_IS_MOCK else "TTTC0802U",
    "sell":    "VTTC0801U" if KIS_IS_MOCK else "TTTC0801U",
    "price":   "FHKST01010100",   # 현재가 (모의/실거래 동일)
    "balance": "VTTC8434R" if KIS_IS_MOCK else "TTTC8434R",
}

# 토큰 캐시 (메모리)
_token_cache: dict = {"token": None, "expires": None}
_token_lock = asyncio.Lock()

# DB 토큰 캐시 키 (모의/실거래 구분)
_DB_TOKEN_KEY = "kis_token_mock" if KIS_IS_MOCK else "kis_token_real"


def _load_token_from_db() -> tuple[str | None, datetime | None]:
    """DB에서 토큰 로드. (서버 재시작 후에도 토큰 유지)"""
    try:
        from db import load_setting
        cached = load_setting(_DB_TOKEN_KEY)
        if cached and isinstance(cached, dict):
            token = cached.get("token")
            expires_str = cached.get("expires")
            if token and expires_str:
                expires = datetime.fromisoformat(expires_str)
                if datetime.now() < expires:
                    return token, expires
    except Exception:
        pass
    return None, None


def _save_token_to_db(token: str, expires: datetime) -> None:
    """토큰을 DB에 저장 (서버 재시작해도 유지됨)."""
    try:
        from db import save_setting
        save_setting(_DB_TOKEN_KEY, {
            "token": token,
            "expires": expires.isoformat(),
        })
    except Exception:
        pass


def is_configured() -> bool:
    """KIS API 설정 완료 여부."""
    return bool(KIS_APP_KEY and KIS_APP_SECRET and KIS_ACCOUNT_NO)


async def _get_token() -> str:
    """OAuth2 액세스 토큰 발급.
    우선순위: 메모리 캐시 → DB 캐시 → KIS API 신규 발급
    (서버 재시작 후에도 24시간 내 토큰 재사용, 분당 1회 제한 회피)
    """
    async with _token_lock:
        now = datetime.now()

        # 1순위: 메모리 캐시
        if _token_cache["token"] and _token_cache["expires"] and now < _token_cache["expires"]:
            return _token_cache["token"]

        # 2순위: DB 캐시 (서버 재시작 후에도 살아있음)
        db_token, db_expires = _load_token_from_db()
        if db_token and db_expires:
            _token_cache["token"] = db_token
            _token_cache["expires"] = db_expires
            logger.info("[KIS] DB에서 토큰 복원 (만료까지 %s분)", int((db_expires - now).total_seconds() // 60))
            return db_token

        # 3순위: KIS API 신규 발급
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{KIS_BASE}/oauth2/tokenP",
                json={
                    "grant_type": "client_credentials",
                    "appkey": KIS_APP_KEY,
                    "appsecret": KIS_APP_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            token = data["access_token"]
            expires_in = int(data.get("expires_in", 86400))
            expires = now + timedelta(seconds=expires_in - 300)  # 5분 여유
            _token_cache["token"] = token
            _token_cache["expires"] = expires
            _save_token_to_db(token, expires)
            mode = "모의투자" if KIS_IS_MOCK else "실거래"
            logger.info("[KIS] 액세스 토큰 신규 발급 (%s, 만료: %s분 후)", mode, expires_in // 60)
            return token


async def get_current_price(ticker: str) -> int:
    """국내 주식 현재가 조회 (원).

    Args:
        ticker: 종목코드 (예: "005930" = 삼성전자)
    Returns:
        현재가 (원), 실패 시 0
    """
    if not is_configured():
        logger.warning("[KIS] API 미설정 — 현재가 조회 불가")
        return 0
    try:
        token = await _get_token()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price",
                headers={
                    "authorization": f"Bearer {token}",
                    "appkey": KIS_APP_KEY,
                    "appsecret": KIS_APP_SECRET,
                    "tr_id": _TR["price"],
                },
                params={
                    "fid_cond_mrkt_div_code": "J",
                    "fid_input_iscd": ticker,
                },
            )
            data = resp.json()
            price = int(data.get("output", {}).get("stck_prpr", "0") or "0")
            logger.info("[KIS] %s 현재가: %s원", ticker, f"{price:,}")
            return price
    except Exception as e:
        logger.error("[KIS] 현재가 조회 실패 (%s): %s", ticker, e)
        return 0


async def place_order(
    ticker: str,
    action: str,       # "buy" or "sell"
    qty: int,
    price: int = 0,    # 0 = 시장가
) -> dict:
    """주식 주문 실행 (매수/매도).

    Returns:
        {"success": bool, "order_no": str, "message": str, "raw": dict}
    """
    if not is_configured():
        return {"success": False, "message": "KIS API 미설정", "order_no": ""}

    if action not in ("buy", "sell"):
        return {"success": False, "message": f"잘못된 action: {action}", "order_no": ""}

    order_type = "01" if price == 0 else "00"  # 01=시장가, 00=지정가
    mode = "모의투자" if KIS_IS_MOCK else "실거래"

    try:
        token = await _get_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{KIS_BASE}/uapi/domestic-stock/v1/trading/order-cash",
                headers={
                    "authorization": f"Bearer {token}",
                    "appkey": KIS_APP_KEY,
                    "appsecret": KIS_APP_SECRET,
                    "tr_id": _TR[action],
                    "content-type": "application/json",
                },
                json={
                    "CANO": KIS_ACCOUNT_NO,
                    "ACNT_PRDT_CD": KIS_ACCOUNT_CODE,
                    "PDNO": ticker,
                    "ORD_DVSN": order_type,
                    "ORD_QTY": str(qty),
                    "ORD_UNPR": str(price),
                },
            )
            data = resp.json()

            rt_cd = data.get("rt_cd", "1")
            msg = data.get("msg1", "")
            order_no = data.get("output", {}).get("ODNO", "")
            success = rt_cd == "0"

            action_kr = "매수" if action == "buy" else "매도"
            if success:
                logger.info("[KIS %s] %s %s %d주 주문 완료 (주문번호: %s)", mode, action_kr, ticker, qty, order_no)
            else:
                logger.warning("[KIS %s] %s %s %d주 주문 실패: %s", mode, action_kr, ticker, qty, msg)

            return {
                "success": success,
                "order_no": order_no,
                "message": msg,
                "mode": mode,
                "raw": data,
            }
    except Exception as e:
        logger.error("[KIS] 주문 실패 (%s %s): %s", action, ticker, e)
        return {"success": False, "message": str(e), "order_no": ""}


async def get_balance() -> dict:
    """계좌 잔고 조회.

    Returns:
        {"cash": int, "holdings": [...], "total_eval": int, "success": bool}
    """
    if not is_configured():
        return {"success": False, "cash": 0, "holdings": [], "total_eval": 0}

    try:
        token = await _get_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{KIS_BASE}/uapi/domestic-stock/v1/trading/inquire-balance",
                headers={
                    "authorization": f"Bearer {token}",
                    "appkey": KIS_APP_KEY,
                    "appsecret": KIS_APP_SECRET,
                    "tr_id": _TR["balance"],
                },
                params={
                    "CANO": KIS_ACCOUNT_NO,
                    "ACNT_PRDT_CD": KIS_ACCOUNT_CODE,
                    "AFHR_FLPR_YN": "N",
                    "OFL_YN": "",
                    "INQR_DVSN": "02",
                    "UNPR_DVSN": "01",
                    "FUND_STTL_ICLD_YN": "N",
                    "FNCG_AMT_AUTO_RDPT_YN": "N",
                    "PRCS_DVSN": "01",
                    "CTX_AREA_FK100": "",
                    "CTX_AREA_NK100": "",
                },
            )
            data = resp.json()
            output1 = data.get("output1", [])  # 보유 종목
            output2 = data.get("output2", [{}])  # 계좌 요약

            cash = int((output2[0] if output2 else {}).get("dnca_tot_amt", "0") or "0")
            total_eval = int((output2[0] if output2 else {}).get("tot_evlu_amt", "0") or "0")

            holdings = []
            for item in output1:
                qty = int(item.get("hldg_qty", "0") or "0")
                if qty > 0:
                    holdings.append({
                        "ticker": item.get("pdno", ""),
                        "name": item.get("prdt_name", ""),
                        "qty": qty,
                        "avg_price": int(item.get("pchs_avg_pric", "0") or "0"),
                        "current_price": int(item.get("prpr", "0") or "0"),
                        "eval_profit": int(item.get("evlu_pfls_amt", "0") or "0"),
                    })

            return {
                "success": True,
                "cash": cash,
                "holdings": holdings,
                "total_eval": total_eval,
                "mode": "모의투자" if KIS_IS_MOCK else "실거래",
            }
    except Exception as e:
        logger.error("[KIS] 잔고 조회 실패: %s", e)
        return {"success": False, "cash": 0, "holdings": [], "total_eval": 0}


async def _force_renew_token() -> None:
    """토큰 강제 갱신 (캐시 무효화 후 신규 발급)."""
    async with _token_lock:
        _token_cache["token"] = None
        _token_cache["expires"] = None
    # 락 해제 후 _get_token() 호출 (내부에서 다시 락 획득)
    try:
        await _get_token()
        mode = "모의투자" if KIS_IS_MOCK else "실거래"
        logger.info("[KIS] 토큰 자동 갱신 완료 (%s, 오전 %d시 스케줄)", mode, _RENEWAL_HOUR_KST)
    except Exception as e:
        logger.error("[KIS] 토큰 자동 갱신 실패: %s", e)


async def start_daily_token_renewal() -> None:
    """매일 KST 오전 7시에 KIS 토큰을 자동 갱신하는 백그라운드 태스크.
    mini_server.py의 startup 이벤트에서 asyncio.create_task()로 실행할 것.
    """
    if not is_configured():
        logger.info("[KIS] API 미설정 — 토큰 자동 갱신 스케줄러 비활성화")
        return

    logger.info("[KIS] 토큰 자동 갱신 스케줄러 시작 (매일 KST %02d:%02d)", _RENEWAL_HOUR_KST, _RENEWAL_MINUTE_KST)

    while True:
        now_kst = datetime.now(_KST)
        # 오늘 오전 7시 (KST)
        today_renewal = now_kst.replace(
            hour=_RENEWAL_HOUR_KST, minute=_RENEWAL_MINUTE_KST, second=0, microsecond=0
        )
        # 이미 지났으면 내일 오전 7시
        if now_kst >= today_renewal:
            today_renewal += timedelta(days=1)

        wait_seconds = (today_renewal - now_kst).total_seconds()
        logger.info(
            "[KIS] 다음 토큰 자동 갱신: %s (%.0f분 후)",
            today_renewal.strftime("%m-%d %H:%M KST"),
            wait_seconds / 60,
        )

        await asyncio.sleep(wait_seconds)
        await _force_renew_token()
