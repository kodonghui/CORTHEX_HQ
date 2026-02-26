# 2026-02-26 Phase 6 ARGOS + 정보국 구현

## 개요
Phase 6 승인 작업 전체 구현 완료.

## 변경 내용

### 6-0: 서버 200GB 업그레이드
- Oracle Cloud ARM 24GB → 200GB 업그레이드 (대표님 직접 진행)

### 6-5: ARGOS 데이터 수집 레이어
**db.py**: 새 테이블 5개 추가
- `argos_price_history` — 주가 이력 (90일, UNIQUE(ticker, trade_date))
- `argos_news_cache` — 뉴스 캐시 (30일, Naver API)
- `argos_dart_filings` — DART 공시 (90일, rcept_no UNIQUE)
- `argos_macro_data` — 매크로 지표 (1년, UNIQUE(indicator, trade_date))
- `argos_collection_status` — 수집 상태 현황 (data_type UNIQUE)

**arm_server.py**: 수집 함수 5개 + 크론 통합
- `_argos_collect_prices()` — pykrx(KR) / yfinance(US) 1분마다
- `_argos_collect_news()` — Naver News API 30분마다
- `_argos_collect_dart()` — DART 공시 API 1시간마다
- `_argos_collect_macro()` — KOSPI/KOSDAQ/USD_KRW/VIX 1일마다
- `_argos_update_status()` — 수집 상태 DB 기록
- `_cron_loop()`에 ARGOS 수집 트리거 5개 삽입

### 6-6: 도구 서버화 Phase 2 (ARGOS DB 캐시 API)
- `GET /api/argos/price/{ticker}` — 주가 이력 서빙 (days=90)
- `GET /api/argos/news/{keyword}` — 뉴스 캐시 서빙 (days=7)
- `GET /api/argos/dart/{ticker}` — DART 공시 서빙 (days=90)
- `GET /api/argos/macro` — 매크로 지표 서빙
- `GET /api/argos/status` — 수집 현황 (마지막 수집 시각, 에러, DB 건수)
- `POST /api/argos/collect/now` — 수동 즉시 수집 트리거

### 6-7: 신뢰도 완전 서버화
- `GET /api/argos/confidence/{ticker}` — 서버 계산 신뢰도
  - ① Quant Score (RSI×0.25 + MA×0.25 + BB×0.2 + 거래량×0.15 + 추세×0.15)
  - ② Calibration Factor (`_compute_calibration_factor()` 재사용)
  - ③ Bayesian 버킷 보정 (confidence_calibration 테이블)
  - ④ ELO 가중치 (analyst_elo_ratings)
  - AI 안내문: "서버 계산 {N}%. ±15%p 범위 내 조정 (이탈 시 이유 명시)"

### 6-8: 정보국 탭 + 상단 상태바
**index.html**:
- 상단 고정 상태바 (항상 보임): 📡 데이터 / 🤖 AI / 🎯 트리거 / 💸 비용 / 🚨 에러
- ARGOS 정보국 탭 (`intelligence`): 수집 상태 4카드 + 트리거 목록 + AI 활동 + 비용 추적 + 에러 로그
- 더보기 탭에 ARGOS 추가 + 모바일 시트에 ARGOS 추가

**corthex-app.js**:
- `intelligence` 탭 추가 (tabs 배열)
- `intelligence` 데이터 상태 초기화
- `loadIntelligence()` — `/api/intelligence/status` 호출
- `argosCollectNow(type)` — 수동 수집 트리거
- `_fmtArgosTime(iso)` — 시간 포맷 ("방금/N분 전/N시간 전")
- `switchTab('intelligence')` → `loadIntelligence()` lazy load
- 서버 시작 2초 후 자동 초기 로드

**arm_server.py**:
- `GET /api/intelligence/status` — 정보국 통합 상태 API
  (ARGOS 상태 + 트리거 + AI 활동 + 비용 + 에러)

### 6-9: 강화학습 파이프라인
- `_argos_monthly_rl_analysis()` — 월 1회 크론
  - 최근 30일 오답 집계 → 비서실장에게 패턴 분석 요청
  - 결과 → `error_patterns` 테이블 `monthly_rl` 타입으로 저장
- 기존 `_run_confidence_learning_pipeline()` 유지 (7일 검증 후 ELO/Calibration/Bayesian 자동 갱신)

## 아키텍처 원칙 달성 현황
- 서버 우위: 주가/지수/환율/공시 → API 호출 없이 DB에서 직접
- AI 역할: 뉴스 맥락 해석 + ±15%p 조정만
- 데이터 3계층: 수집(ARGOS) → 계산(서버 수식) → 판단(AI)
