"""한국투자증권 OpenAPI 클라이언트 — 자동매매 연동."""
import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

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

# 토큰 캐시
_token_cache: dict = {"token": None, "expires": None}
_token_lock = asyncio.Lock()


def is_configured() -> bool:
    """KIS API 설정 완료 여부."""
    return bool(KIS_APP_KEY and KIS_APP_SECRET and KIS_ACCOUNT_NO)


async def _get_token() -> str:
    """OAuth2 액세스 토큰 발급 (만료 시 자동 갱신)."""
    async with _token_lock:
        now = datetime.now()
        if _token_cache["token"] and _token_cache["expires"] and now < _token_cache["expires"]:
            return _token_cache["token"]

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
            _token_cache["token"] = data["access_token"]
            expires_in = int(data.get("expires_in", 86400))
            _token_cache["expires"] = now + timedelta(seconds=expires_in - 300)
            mode = "모의투자" if KIS_IS_MOCK else "실거래"
            logger.info("[KIS] 액세스 토큰 발급 완료 (%s, 만료: %s분 후)", mode, expires_in // 60)
            return _token_cache["token"]


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
