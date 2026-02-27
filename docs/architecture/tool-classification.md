# 도구 분류표 — 서버 실행 vs AI 직접 작동

최종 업데이트: 2026-02-27
분석 방법: src/tools/*.py 코드 전수 분석 (141개 파일)

---

## 분류 기준

| 분류 | 정의 | 특징 |
|------|------|------|
| **서버 실행** | 서버가 Python/API로 계산 → 결과를 AI에게 전달 | numpy, scipy, pykrx, yfinance, API 호출. AI 판단 불필요. |
| **AI 직접** | AI가 상황 판단 후 직접 호출해야 하는 도구 | 웹 검색 해석, 텍스트 생성, 에이전트 협업, 매매 실행 등 |

---

## 부서별 도구 분류

### 비서실장 (Chief of Staff) — 14개

| 도구 ID | 도구명 | 분류 | 근거 |
|---------|--------|------|------|
| real_web_search | 웹 검색 | **AI 직접** | 검색 결과 해석 필요 |
| naver_news | 뉴스 수집 | **AI 직접** | 뉴스 해석/필터링 필요 |
| notification_engine | 알림 발송 | **AI 직접** | 메시지 내용 판단 필요 |
| calendar_tool | 일정 관리 | **AI 직접** | 일정 우선순위 판단 필요 |
| schedule_tool | 스케줄 조정 | **AI 직접** | 시간 조정 판단 필요 |
| email_sender | 이메일 발송 | **AI 직접** | 수신자/내용 판단 필요 |
| decision_tracker | 의사결정 기록 | 서버 실행 | DB 저장/조회만 |
| cross_agent_protocol | 에이전트 통신 | **AI 직접** | 에이전트 간 협업 판단 필요 |
| agenda_optimizer | 일정 최적화 | **AI 직접** | 로직/우선순위 판단 필요 |
| priority_matrix | 우선순위 매트릭스 | **AI 직접** | 중요도 판단 필요 |
| meeting_effectiveness | 회의 효율성 | **AI 직접** | 분석 판단 필요 |
| delegation_analyzer | 위임 분석 | **AI 직접** | 조직 판단 필요 |
| stakeholder_mapper | 이해관계자 분석 | **AI 직접** | 관계 분석 필요 |
| read_knowledge | 지식 읽기 | **AI 직접** | 해석/활용 판단 필요 |

**소계: 서버 1개, AI 13개 (서버 7%)**

---

### 전략팀장 (CSO) — 24개

| 도구 ID | 도구명 | 분류 | 근거 |
|---------|--------|------|------|
| naver_datalab | 검색량 데이터 | 서버 실행 | Naver API 데이터 수집 |
| public_data | 공공데이터포털 | 서버 실행 | API 데이터 수집 |
| platform_market_scraper | 플랫폼 수집 | 서버 실행 | 웹 스크래핑 (코드 계산) |
| scholar_scraper | 논문 수집 | 서버 실행 | 데이터 수집 |
| spreadsheet_tool | 스프레드시트 | 서버 실행 | pandas 데이터 처리 |
| chart_generator | 차트 생성 | 서버 실행 | matplotlib/plotly |
| financial_calculator | 재무 계산 | 서버 실행 | numpy_financial 수식 |
| decision_tracker | 의사결정 추적 | 서버 실행 | DB 저장 |
| lawschool_community | 법학 커뮤니티 | 서버 실행 | 데이터 수집 |
| dc_lawschool_crawler | DC 법학 크롤러 | 서버 실행 | 웹 스크래핑 |
| orbi_crawler | 오르비 크롤러 | 서버 실행 | 웹 스크래핑 |
| real_web_search | 웹 검색 | **AI 직접** | 검색 해석 필요 |
| cross_agent_protocol | 에이전트 통신 | **AI 직접** | 협업 판단 필요 |
| competitor_monitor | 경쟁사 모니터링 | **AI 직접** | 분석/해석 필요 |
| subsidy_finder | 보조금 검색 | **AI 직접** | 해석/판단 필요 |
| market_sizer | 시장 규모 추정 | **AI 직접** | 분석 판단 필요 |
| business_model_scorer | 비즈니스 모델 평가 | **AI 직접** | 점수 판단 필요 |
| competitive_mapper | 경쟁 지도 분석 | **AI 직접** | 분석/평가 필요 |
| growth_forecaster | 성장 예측 | **AI 직접** | 예측 판단 필요 |
| scenario_simulator | 시나리오 분석 | **AI 직접** | 시뮬레이션 판단 필요 |
| pricing_optimizer | 가격 최적화 | **AI 직접** | 전략 판단 필요 |
| customer_cohort_analyzer | 고객 코호트 분석 | **AI 직접** | 분석 판단 필요 |
| swot_quantifier | SWOT 정량화 | **AI 직접** | 평가 기준 판단 필요 |
| read_knowledge | 지식 읽기 | **AI 직접** | 해석 필요 |

**소계: 서버 11개, AI 13개 (서버 46%)**

---

### 법무팀장 (CLO) — 19개

| 도구 ID | 도구명 | 분류 | 근거 |
|---------|--------|------|------|
| kipris | 특허 검색 | 서버 실행 | KIPRIS API 데이터 수집 |
| law_search | 법령 검색 | 서버 실행 | 법제처 API 검색 |
| trademark_similarity | 상표 유사도 | 서버 실행 | 알고리즘 유사도 계산 |
| license_scanner | 라이선스 스캔 | 서버 실행 | 데이터 검색/수집 |
| real_web_search | 웹 검색 | **AI 직접** | 검색 해석 필요 |
| cross_agent_protocol | 에이전트 통신 | **AI 직접** | 협업 판단 필요 |
| precedent_analyzer | 판례 분석 | **AI 직접** | 법리 해석 필요 |
| contract_reviewer | 계약서 검토 | **AI 직접** | 법적 판단 필요 |
| nda_analyzer | NDA 분석 | **AI 직접** | 법적 해석 필요 |
| ip_portfolio_manager | IP 포트폴리오 | **AI 직접** | 포트폴리오 판단 필요 |
| ai_governance_checker | AI 거버넌스 | **AI 직접** | 규제 해석 필요 |
| law_change_monitor | 법 변화 모니터링 | **AI 직접** | 변화 해석 필요 |
| regulation_radar | 규제 레이더 | **AI 직접** | 규제 해석 필요 |
| dispute_simulator | 분쟁 시뮬레이터 | **AI 직접** | 판단 시나리오 필요 |
| compliance_checker | 규정 준수 확인 | **AI 직접** | 준수 판단 필요 |
| privacy_auditor | 개인정보 감사 | **AI 직접** | 감사 판단 필요 |
| risk_communicator | 위험 전달 | **AI 직접** | 커뮤니케이션 판단 필요 |
| risk_matrix | 위험 매트릭스 | **AI 직접** | 평가 판단 필요 |
| read_knowledge | 지식 읽기 | **AI 직접** | 해석 필요 |

**소계: 서버 4개, AI 15개 (서버 21%)**

---

### 마케팅팀장 (CMO) — 30개

| 도구 ID | 도구명 | 분류 | 근거 |
|---------|--------|------|------|
| naver_datalab | 검색량 데이터 | 서버 실행 | Naver API 수집 |
| platform_market_scraper | 플랫폼 수집 | 서버 실행 | 웹 스크래핑 |
| youtube_analyzer | 유튜브 분석 | 서버 실행 | YouTube API 데이터 수집 |
| naver_news | 뉴스 수집 | 서버 실행 | API 수집 |
| ab_test_engine | A/B 테스트 | 서버 실행 | 통계 검정 계산 |
| customer_ltv_model | LTV 모델 | 서버 실행 | 수식 계산 |
| rfm_segmentation | RFM 분석 | 서버 실행 | 분할 알고리즘 계산 |
| pricing_sensitivity | 가격 민감도 | 서버 실행 | 통계 계산 |
| churn_risk_scorer | 이탈 위험 점수 | 서버 실행 | 점수 계산 |
| marketing_attribution | 마케팅 귀속 | 서버 실행 | 통계 계산 |
| cohort_retention | 코호트 유지율 | 서버 실행 | 데이터 분석 |
| viral_coefficient | 바이럴 계수 | 서버 실행 | 수식 계산 |
| tts_generator | TTS 생성 | 서버 실행 | 음성 합성 API |
| lipsync_video_generator | 립싱크 영상 | 서버 실행 | 알고리즘 처리 |
| video_editor | 영상 편집 | 서버 실행 | 미디어 처리 |
| sentiment_analyzer | 감정 분석 | **AI 직접** | NLP 판단 필요 |
| hashtag_recommender | 해시태그 추천 | **AI 직접** | 추천 판단 필요 |
| email_optimizer | 이메일 최적화 | **AI 직접** | 최적화 판단 필요 |
| competitor_sns_monitor | 경쟁사 SNS | **AI 직접** | 모니터링 해석 필요 |
| seo_analyzer | SEO 분석 | **AI 직접** | 분석/판단 필요 |
| sns_manager | SNS 관리 | **AI 직접** | 퍼블리싱 판단 필요 |
| notification_engine | 알림 엔진 | **AI 직접** | 알림 실행 |
| cross_agent_protocol | 에이전트 통신 | **AI 직접** | 협업 판단 필요 |
| funnel_analyzer | 퍼널 분석 | **AI 직접** | 분석 판단 필요 |
| content_quality_scorer | 콘텐츠 점수 | **AI 직접** | 평가 판단 필요 |
| gemini_image_generator | 이미지 생성 | **AI 직접** | 생성AI (프롬프트 판단) |
| gemini_video_generator | 영상 생성 | **AI 직접** | 생성AI (프롬프트 판단) |
| pricing_optimizer | 가격 최적화 | **AI 직접** | 전략 판단 필요 |
| customer_cohort_analyzer | 고객 코호트 | **AI 직접** | 분석 판단 필요 |
| read_knowledge | 지식 읽기 | **AI 직접** | 해석 필요 |

**소계: 서버 15개, AI 15개 (서버 50%)**

---

### 금융분석팀장 (CIO) — 24개

| 도구 ID | 도구명 | 분류 | 근거 |
|---------|--------|------|------|
| stock_screener | 종목 스크리너 | 서버 실행 | pykrx 데이터 필터링 |
| backtest_engine | 백테스트 | 서버 실행 | pandas-ta 시뮬레이션 계산 |
| insider_tracker | 내부자 거래 | 서버 실행 | API 데이터 수집 |
| dividend_calendar | 배당 캘린더 | 서버 실행 | API 데이터 수집 |
| financial_calculator | 재무 계산 | 서버 실행 | numpy_financial 수식 계산 |
| chart_generator | 차트 생성 | 서버 실행 | matplotlib/plotly |
| spreadsheet_tool | 스프레드시트 | 서버 실행 | pandas 데이터 처리 |
| technical_analyzer | 기술적 분석 | 서버 실행 | pykrx + pandas-ta 계산 |
| dcf_valuator | DCF 가치평가 | 서버 실행 | numpy 수식 계산 |
| portfolio_optimizer | 포트폴리오 최적화 | 서버 실행 | scipy 최적화 계산 |
| risk_calculator | 리스크 계산 | 서버 실행 | numpy VaR/MDD/Sharpe |
| pair_analyzer | 페어 트레이딩 | 서버 실행 | 통계 분석 계산 |
| sec_edgar | SEC 공시 | 서버 실행 | SEC API 데이터 수집 |
| us_financial_analyzer | 미국 재무 분석 | 서버 실행 | yfinance + numpy 계산 |
| us_technical_analyzer | 미국 기술 분석 | 서버 실행 | yfinance + pandas-ta |
| options_flow | 옵션 흐름 | 서버 실행 | yfinance 데이터 분석 |
| portfolio_optimizer_v2 | 포트폴리오 최적화 V2 | 서버 실행 | numpy/scipy MVO+Kelly |
| correlation_analyzer | 상관관계 + 꼬리위험 | 서버 실행 | numpy DCC-GARCH 계산 |
| trading_settings_control | 거래 설정 제어 | **AI 직접** | AI가 설정값 판단 후 변경 |
| trading_executor | 매매 실행 | **AI 직접** | 주문 판단 후 실행 |
| real_web_search | 웹 검색 | **AI 직접** | 검색 결과 해석 필요 |
| notification_engine | 알림 | **AI 직접** | 알림 실행 |
| cross_agent_protocol | 에이전트 통신 | **AI 직접** | 협업 판단 필요 |
| read_knowledge | 지식 읽기 | **AI 직접** | 해석 필요 |

**소계: 서버 18개, AI 6개 (서버 75%)**

---

### 콘텐츠팀장 (CPO) — 10개

| 도구 ID | 도구명 | 분류 | 근거 |
|---------|--------|------|------|
| decision_tracker | 의사결정 기록 | 서버 실행 | DB 저장/조회만 |
| doc_converter | 문서 변환 | 서버 실행 | 파일 형식 변환 |
| cross_agent_protocol | 에이전트 통신 | **AI 직접** | 협업 판단 필요 |
| report_generator | 보고서 생성 | **AI 직접** | 콘텐츠 생성 필요 |
| meeting_formatter | 회의록 정리 | **AI 직접** | 텍스트 정리 필요 |
| newsletter_builder | 뉴스레터 | **AI 직접** | 콘텐츠 생성 필요 |
| document_summarizer | 문서 요약 | **AI 직접** | NLP 요약 필요 |
| terms_generator | 용어 생성 | **AI 직접** | 텍스트 생성 필요 |
| communication_optimizer | 소통 최적화 | **AI 직접** | 텍스트 최적화 필요 |
| read_knowledge | 지식 읽기 | **AI 직접** | 해석 필요 |

**소계: 서버 2개, AI 8개 (서버 20%)**

---

## 종합 요약 표

| 부서 | 서버 실행 | AI 직접 | 합계 | 서버 비율 |
|------|----------|--------|------|----------|
| 비서실장 | 1 | 13 | 14 | 7% |
| 전략팀장 | 11 | 13 | 24 | 46% |
| 법무팀장 | 4 | 15 | 19 | 21% |
| 마케팅팀장 | 15 | 15 | 30 | 50% |
| **금융분석팀장** | **18** | **6** | **24** | **75%** |
| 콘텐츠팀장 | 2 | 8 | 10 | 20% |
| **전체** | **51** | **70** | **121** | **42%** |

---

## 핵심 인사이트

### 서버로 옮겨야 할 우선순위
1. **금융분석팀장 (CIO)**: 18개가 이미 서버 실행 대상 — 구현 우선순위 최고
   - technical_analyzer, dcf_valuator, risk_calculator, correlation_analyzer, portfolio_optimizer_v2 → 이미 STEP2 강제 실행 구현됨 (2026-02-27)
   - 나머지도 서버 사전 계산으로 전환하면 AI 도구 호출 횟수 0에 가까워짐

2. **마케팅팀장 (CMO)**: 데이터 분석 15개가 이미 서버 실행 대상
   - ab_test_engine, rfm_segmentation, churn_risk_scorer 등 통계 계산 도구

3. **비서실장/콘텐츠팀장**: 본질적으로 AI 업무 — 서버화 불필요

### 구조적 방향
- **서버 실행 도구** → allowed_tools에서 제거 + 프롬프트에 사전 주입
- **AI 직접 도구** → allowed_tools 유지 (AI가 상황 판단 후 호출)
- 장점: AI 도구 호출 횟수 감소 → 비용 절감 + 속도 향상
