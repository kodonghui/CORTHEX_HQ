# KIS Open API 참고 문서

> 공식 소스: https://github.com/koreainvestment/open-trading-api
> API 포털: https://apiportal.koreainvestment.com

## Base URL

| 환경 | URL |
|------|-----|
| 실전 | `https://openapi.koreainvestment.com:9443` |
| 모의 | `https://openapivts.koreainvestment.com:29443` |

## 공통 헤더

```
authorization: Bearer {ACCESS_TOKEN}
appkey: {APP_KEY}
appsecret: {APP_SECRET}
tr_id: {해당 TR_ID}
content-type: application/json; charset=utf-8
custtype: P
```

## 모의투자 TR_ID 변환 규칙

실전 TR_ID의 **첫 글자 T → V**로 변환 (KIS 공식 GitHub 기준)

---

## 국내주식

### 주문 (현금) — POST `/uapi/domestic-stock/v1/trading/order-cash`

| 주문유형 | 실전 TR_ID | 모의 TR_ID |
|---------|-----------|-----------|
| **매수** | `TTTC0012U` | `VTTC0012U` |
| **매도** | `TTTC0011U` | `VTTC0011U` |
| 정정/취소 | `TTTC0013U` | `VTTC0013U` |

> ⚠️ 구 TR_ID (`TTTC0802U`/`TTTC0801U`)는 사전고지 없이 차단 가능!

**Request Body:**

| 파라미터 | 설명 | 예시 |
|---------|------|------|
| `CANO` | 종합계좌번호 8자리 | `"12345678"` |
| `ACNT_PRDT_CD` | 계좌상품코드 2자리 | `"01"` |
| `PDNO` | 종목코드 (6자리, ETN 7자리) | `"005930"` |
| `ORD_DVSN` | 주문구분 | `"00"`=지정가, `"01"`=시장가 |
| `ORD_QTY` | 주문수량 (문자열) | `"1"` |
| `ORD_UNPR` | 주문단가 (시장가 시 `"0"`) | `"55000"` |
| `SLL_TYPE` | 매도유형 | 매도시 `"01"`, 매수시 `""` |
| `EXCG_ID_DVSN_CD` | 거래소구분 | `"KRX"`=한국거래소, `"SOR"`=스마트주문, `"NXT"`=대체거래소 (빈문자열 불가!) |
| `CNDT_PRIC` | 조건가격 | `""` |

### 잔고조회 — GET `/uapi/domestic-stock/v1/trading/inquire-balance`

| 환경 | TR_ID |
|------|-------|
| 실전 | `TTTC8434R` |
| 모의 | `VTTC8434R` |

---

## 해외주식

### 주문 — POST `/uapi/overseas-stock/v1/trading/order`

**매수 TR_ID:**

| 시장 | 실전 | 모의 |
|------|------|------|
| 미국 (NASD/NYSE/AMEX) | `TTTT1002U` | `VTTT1002U` |
| 홍콩 | `TTTS1002U` | `VTTS1002U` |
| 일본 | `TTTS0308U` | `VTTS0308U` |
| 중국 상해 | `TTTS0202U` | `VTTS0202U` |
| 중국 심천 | `TTTS0305U` | `VTTS0305U` |
| 베트남 | `TTTS0311U` | `VTTS0311U` |

**매도 TR_ID:**

| 시장 | 실전 | 모의 |
|------|------|------|
| 미국 (NASD/NYSE/AMEX) | `TTTT1006U` | `VTTT1006U` |
| 홍콩 | `TTTS1001U` | `VTTS1001U` |
| 일본 | `TTTS0307U` | `VTTS0307U` |
| 중국 상해 | `TTTS1005U` | `VTTS1005U` |
| 중국 심천 | `TTTS0304U` | `VTTS0304U` |
| 베트남 | `TTTS0310U` | `VTTS0310U` |

**Request Body:**

| 파라미터 | 설명 | 예시 |
|---------|------|------|
| `CANO` | 종합계좌번호 | `"12345678"` |
| `ACNT_PRDT_CD` | 계좌상품코드 | `"01"` |
| `OVRS_EXCG_CD` | 거래소코드 | `"NASD"` |
| `PDNO` | 종목심볼 | `"AAPL"` |
| `ORD_QTY` | 수량 (문자열) | `"1"` |
| `OVRS_ORD_UNPR` | 단가 (문자열) | `"150.00"` |
| `ORD_DVSN` | 주문구분 | `"00"`=지정가 |
| `SLL_TYPE` | 매도구분 | 매도시 `"00"`, 매수시 `""` |
| `ORD_SVR_DVSN_CD` | 서버구분 | `"0"` |

> ⚠️ 해외주식은 **지정가만 가능** (시장가 미지원). 모의투자도 지정가(`"00"`)만.

### 잔고조회 — GET `/uapi/overseas-stock/v1/trading/inquire-balance`

| 환경 | TR_ID |
|------|-------|
| 실전 | `TTTS3012R` |
| 모의 | `VTTS3012R` |

### 체결기준현재잔고 — GET `/uapi/overseas-stock/v1/trading/inquire-present-balance`

| 환경 | TR_ID |
|------|-------|
| 실전 | `CTRP6504R` |
| 모의 | `VTRP6504R` |

---

## 거래소 코드 (OVRS_EXCG_CD)

| 코드 | 시장 | 비고 |
|------|------|------|
| `NASD` | 나스닥 | 실전 잔고조회 시 미국 전체 |
| `NYSE` | 뉴욕 | |
| `AMEX` | 아멕스 | |
| `SEHK` | 홍콩 | |
| `SHAA` | 중국 상해 | |
| `SZAA` | 중국 심천 | |
| `TKSE` | 일본 | |
| `HASE` | 베트남 하노이 | |
| `VNSE` | 베트남 호치민 | |

---

## 인증 (토큰)

- **엔드포인트**: `POST /oauth2/tokenP`
- **Body**: `{"grant_type": "client_credentials", "appkey": ..., "appsecret": ...}`
- **만료**: 24시간
- **제한**: 1분당 1회 발급 (초과 시 `EGW00133` 에러)

---

*최종 업데이트: 2026-02-21 | 소스: KIS 공식 GitHub + API 포털 문서*
