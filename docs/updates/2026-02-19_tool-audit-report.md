# 전사 도구 점검 보고서 (2026-02-19)

> 아카이브(corthex-archive-20260219) 기반 전수 취합

## 전사 현황

- ✅ 즉시 가동: 약 47%
- ⚠️ 조건부 가동: 약 31%
- ❌ 불가: 약 22%

---

## 유형 A — 라이브러리 미설치 (pip install로 즉시 해결)

```bash
pip install bandit ruff pytest pytest-cov pytest-mock \
            chromadb pandas-ta numpy-financial numpy \
            notion-client google-play-scraper yt-dlp
```

| 도구명 | 필수 패키지 | 영향 처 |
|--------|-----------|---------|
| financial_calculator | numpy-financial | CIO, CSO |
| backtest_engine | pandas-ta | CIO |
| kr_stock (indicators) | pandas-ta | CIO |
| code_quality | bandit, ruff, pytest | CTO |
| vector_knowledge | chromadb | CTO, CPO |
| notion_api 도구 | notion-client | CMO, CPO, 비서실 |
| app_review_scraper | google-play-scraper | CSO |
| youtube_analyzer | yt-dlp | CSO |

⚠️ NOTE: requirements.txt에 pandas-ta, numpy-financial 이미 있음. 설치 실패 원인은 pip 의존성 충돌일 가능성. deploy.yml에서 개별 설치 강제 추가 필요.

---

## 유형 B — 파라미터 파싱 오류 (코드 수정 필요)

| 도구명 | 증상 | 영향 처 |
|--------|------|---------|
| dart_api | company/action 파라미터 인식 불가 | CIO, CSO |
| insider_tracker | 동일 파싱 오류 | CIO |
| global_market_tool | action 파라미터 인식 불가 | CIO |
| notification_engine | 파라미터 파싱 실패 | CIO |
| prompt_tester | prompt vs query 불일치 | CTO |
| embedding_tool | text vs query 불일치 | CTO |
| token_counter | text vs query 불일치 | CTO |

---

## 유형 C — API 키/인증 미등록

| 도구명 | 문제 |
|--------|------|
| sns_manager | YouTube/Instagram/LinkedIn/네이버카페 OAuth 만료 |
| public_data | PUBLIC_DATA_API_KEY 환경변수 미등록 |

---

## 노션 업로드 현황

- CIO만 notion_create_page 성공
- CMO, CPO, 비서실: notion-client 미설치로 실패
- CLO, CTO, CSO: 미시도

노션 실패 원인: notion-client 패키지 미설치 + NOTION_API_KEY 설정 필요

---

## 즉시 조치 항목

1. deploy.yml에 pip install 추가 (유형 A 해결)
2. dart_api/global_market_tool 파라미터 파싱 수정 (유형 B)
3. notion-client 설치 + notion 도구 테스트

---

## 부서별 전투력

| 처 | 전투력 | 주요 문제 |
|----|--------|----------|
| CLO | ~90% | 설정만 필요 |
| CTO | ~76% | 배포 금지 상태(pytest 없음) |
| CIO | ~45% | pandas-ta/numpy-financial |
| CSO | ~47% | 다수 패키지 미설치 |
| CMO | ~50% | SNS OAuth 만료 |
| CPO | ~60% | notion/chromadb 미설치 |
