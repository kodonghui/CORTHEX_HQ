# 도구 전수 심사 결과 — 121개 코드 직접 분석

최종 업데이트: 2026-02-27
분석 방법: src/tools/*.py 코드 전수 분석 (3개 에이전트 병렬, Opus 모델)

## 품질 종합

| 등급 | 금융+비서 | 전략+법무 | 마케팅+콘텐츠 | 합계 |
|------|----------|----------|-------------|------|
| 교수급 | 15 | 20 | 13 | **48** |
| 실용급 | 23 | 20 | 22 | **65** |
| 오합지졸 | 0 | 0 | 1 | **1** |

## 조치 완료

### 삭제
- `newsletter_builder` — 오합지졸 (콘텐츠 전부 LLM 의존)
- `dc_lawschool_crawler` — lawschool_community에 통합
- `orbi_crawler` — lawschool_community에 통합
- `rfm_segmentation` — 파일 미존재 (customer_ltv_model에 흡수)

### 서버 사전 계산 전환 (금융분석팀장)
- `technical_analyzer` → quant_section 서버 계산
- `dcf_valuator` → _build_dcf_risk_prompt_section() 서버 계산
- `risk_calculator` → _build_dcf_risk_prompt_section() 서버 계산
- `portfolio_optimizer` → v2로 통합
- `portfolio_optimizer_v2` → STEP2 서버 강제 실행
- `correlation_analyzer` → STEP2 서버 강제 실행
- `us_financial_analyzer` → dcf_risk_section 서버 계산 (US)
- `us_technical_analyzer` → quant_section 서버 계산 (US)

## 미해결 — 합병 대상

### pricing_sensitivity + pricing_optimizer
- PSM, 탄력성, 티어 설계 80% 중복
- pricing_sensitivity: Van Westendorp PSM, Gabor-Granger, 점탄력성 (611줄)
- pricing_optimizer: PSM, 탄력성, 심리적 가격, Good-Better-Best (512줄)
- 제안: 좋은 점 모아 하나로 합병 (pricing_optimizer에 Gabor-Granger 추가)

### customer_ltv_model + cohort_retention + customer_cohort_analyzer
- LTV/리텐션/이탈 분석 부분 중복
- customer_ltv_model(836줄): BG/NBD + Gamma-Gamma — 최고급
- cohort_retention(741줄): Kaplan-Meier + sBG — 최고급
- customer_cohort_analyzer(412줄): 두 도구의 요약판
- 제안: customer_cohort_analyzer의 고유 기능(RFM, CAC 회수)을 다른 두 도구에 분배 후 삭제

### portfolio_optimizer(v1) vs portfolio_optimizer_v2
- v1=한국/pykrx, v2=글로벌/yfinance
- 시장이 달라서 실제 중복 아님
- 제안: v1에 Risk Parity/Kelly 추가하여 학술 수준 동일화

## 실시간 수집(ARGOS형) vs 스폰형 분류

### 실시간 수집 (2개)
- `competitor_monitor` — 경쟁사 웹사이트 변경 감시
- `law_change_monitor` — 법령 변경 감시

### 스폰형 (85개+)
대부분의 도구. 요청 시 서버가 실행 → AI에게 결과 전달

### AI 직접 (30개+)
real_web_search, trading_executor, contract_reviewer, notification_engine 등

## 교수급 도구 목록 (48개)

### 금융분석팀장 (10개)
technical_analyzer(948줄), dcf_valuator(488줄), risk_calculator(410줄), pair_analyzer(365줄), correlation_analyzer(548줄), portfolio_optimizer(347줄), portfolio_optimizer_v2(373줄), sec_edgar(444줄), us_financial_analyzer(412줄), us_technical_analyzer(531줄)

### 비서실장 (5개)
agenda_optimizer(648줄), priority_matrix(726줄), meeting_effectiveness(753줄), delegation_analyzer(631줄), stakeholder_mapper(566줄)

### 전략팀장 (10개)
market_sizer(509줄), business_model_scorer(519줄), competitive_mapper(570줄), growth_forecaster(479줄), scenario_simulator(467줄), pricing_optimizer(512줄), customer_cohort_analyzer(412줄), swot_quantifier(457줄), financial_calculator(325줄), cross_agent_protocol(570줄)

### 법무팀장 (10개)
trademark_similarity(413줄), nda_analyzer(461줄), license_scanner(1232줄), ip_portfolio_manager(504줄), ai_governance_checker(634줄), dispute_simulator(562줄), compliance_checker(681줄), privacy_auditor(732줄), risk_communicator(616줄), risk_matrix(480줄)

### 마케팅팀장 (11개)
funnel_analyzer(819줄), ab_test_engine(634줄), customer_ltv_model(836줄), content_quality_scorer(851줄), pricing_sensitivity(611줄), churn_risk_scorer(641줄), marketing_attribution(825줄), cohort_retention(741줄), viral_coefficient(573줄), pricing_optimizer(512줄), customer_cohort_analyzer(412줄)

### 콘텐츠팀장 (2개)
document_summarizer(555줄), communication_optimizer(692줄)
