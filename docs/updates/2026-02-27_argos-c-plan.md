# ARGOS C안 구현 완료 — 재무지표·업종지수·매크로 확장

날짜: 2026-02-27 (KST)
빌드: #644~#647

## 작업 배경

금융분석팀장이 분석 시 실시간 pykrx API를 직접 400회 호출 → 40분+ 지연 발생.
ARGOS 서버 수집 레이어 강화로 금융분석팀장은 DB에서만 데이터를 읽도록 구조 개선.

## 완료된 작업

### 1. sector_rotator 등 10개 실시간 수집 도구 제거
- 금융분석팀장(cio_manager) allowed_tools에서 제거
- 서버가 이미 수집하는 데이터를 에이전트가 중복 호출하지 않도록 차단

### 2. thinking type 버그 수정 (빌드 #642)
- `{"type": "adaptive"}` → `{"type": "enabled"}` (400 에러 해결)

### 3. technical_analyzer divide-by-zero 수정 (빌드 #642)
- `(cl - op) / op * 100` → `if op != 0 else 0.0`

### 4. ARGOS C안 — 3가지 새 수집기 추가 (빌드 #643~647)

#### ④ 매크로 확장 (`_argos_collect_macro` 수정)
- S&P500 (^GSPC), NASDAQ (^IXIC), 미국 10년물 국채금리 (^TNX) — yfinance
- 한국 기준금리 — 한국은행 ECOS API (코드: 722Y001)
- 기존 원달러환율·유가·금 유지

#### ⑤ 재무지표 수집 (`_argos_collect_financial` 신규)
- pykrx `get_market_fundamental(date, date, ticker)` — KR 관심종목 PER/PBR/EPS/DPS/BPS
- 1일 1회, 90일 보관 (`argos_financial_data` 테이블)
- KST 16시 이전 = 전날 데이터 사용 (pykrx는 장마감 후 당일 데이터 제공)
- **수집 확인: 7개 KR 종목 모두 정상 수집**

#### ⑥ 업종지수 수집 (`_argos_collect_sector` 신규)
- pykrx 11개 업종 지수: 전기전자/화학/의약품/철강금속/기계/유통업/건설업/통신업/금융업/서비스업/비금속광물
- 1일 1회, 90일 보관 (`argos_sector_data` 테이블)
- **수집 확인: 8개 업종 정상 수집**

### 5. API 추가
- `/api/argos/collect/now` → financial, sector 즉시수집 타입 지원

## 버그 수정 내역

| 버그 | 원인 | 수정 |
|------|------|------|
| financial 0건 | `get_market_fundamental(today, ticker=ticker)` — keyword arg 미지원 | `(today, today, ticker)` 위치 인수로 변경 |
| financial 빈 DataFrame | 장중 pykrx 당일 데이터 미제공 | KST 16시 전 = 전날 기준 날짜 사용 |

## 검증 결과

```
financial: 7건 (삼성전자·SK하이닉스·한화솔루션·한화시스템·두산에너빌리티·LG전자·LG)
sector: 8건 (11개 업종 중 데이터 있는 8개)
macro: 11건 (환율·유가·금·S&P500·NASDAQ·10년물·기준금리)
```
