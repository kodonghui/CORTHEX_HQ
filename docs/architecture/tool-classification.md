# 🔴🔴🔴 CORTHEX 도구 분류 마스터 문서 🔴🔴🔴

> **최종 업데이트**: 2026-02-27 (빌드 #650)
> **분석 방법**: `src/tools/*.py` 141개 파일 코드 전수 분석 (Opus 에이전트 3개 병렬)
> **심사 결과**: 교수급 48개 / 실용급 65개 / 오합지졸 1개 (삭제됨)

---

# ════════════════════════════════════════
# 📌 4분류 체계
# ════════════════════════════════════════

| 분류 | 의미 | 비유 | 예시 |
|------|------|------|------|
| 🟢 **서버 실시간** | ARGOS가 **24시간 자동 수집**하는 데이터. AI가 부를 필요 없음 | CCTV처럼 항상 녹화 중 | 주가, 뉴스, 공시, 매크로 |
| 🔵 **서버 스폰** | 팀장이 분석 요청하면 **서버가 Python으로 직접 계산**. AI 판단 불필요 | 계산기에 숫자 넣으면 답 나오는 것 | DCF, RSI, 포트폴리오 최적화 |
| 🟡 **팀장 AI 직접** | **AI가 상황 판단 후 직접 호출**해야 하는 도구 | 사람이 생각해서 결정하는 것 | 매매 실행, 법률 해석, 웹 검색 |
| ⛔ **삭제/제거** | 쓰레기 도구 삭제 + 중복 합병 + ARGOS 대체 | 퇴출 | newsletter_builder 등 |

---

# ════════════════════════════════════════
# 📊 부서별 종합 현황
# ════════════════════════════════════════

| 부서 | 🟢 서버실시간 | 🔵 서버스폰 | 🟡 AI직접 | ⛔ 제거 | 합계 | AI가 쓰는 도구 |
|------|:-----------:|:---------:|:--------:|:------:|:----:|:------------:|
| **금융분석팀장** | 10개 (ARGOS) | 8개 (사전계산) | **15개** | 0 | 33 | 15개 |
| **마케팅팀장** | 0 | 15개 | **15개** | 1 | 31 | 30개 |
| **전략팀장** | 0 | 10개 | **11개** | 2 | 23 | 21개 |
| **법무팀장** | 0 | 4개 | **15개** | 0 | 19 | 19개 |
| **비서실장** | 0 | 1개 | **12개** | 0 | 13 | 13개 |
| **콘텐츠팀장** | 0 | 2개 | **7개** | 1 | 10 | 9개 |
| **전체** | **10** | **40** | **75** | **4** | **129** | **107** |

> **핵심**: 금융분석팀장은 원래 33개 도구 중 **18개를 서버가 대신** 처리 → AI가 쓰는 도구 15개로 축소

---

# ════════════════════════════════════════
# 🏦 금융분석팀장 (CIO) — 가장 큰 변화
# ════════════════════════════════════════

### 🟢 서버 실시간 (ARGOS 수집 — AI 호출 0회)

> ARGOS가 cron으로 자동 수집 → DB 저장 → 팀장 프롬프트에 자동 주입

| 도구 | 원래 하던 일 | 대체한 ARGOS 수집 | DB 테이블 |
|------|------------|-----------------|----------|
| ~~kr_stock~~ | pykrx 주가 수집 | `argos_price_history` (1분마다) | argos_price_history |
| ~~us_stock~~ | yfinance 주가 수집 | `argos_price_history` (1분마다) | argos_price_history |
| ~~naver_news~~ | 네이버 뉴스 API | `argos_news` (30분마다) | argos_news |
| ~~dart_monitor~~ | DART 공시 API | `argos_dart` (1시간마다) | argos_dart |
| ~~macro_fed_tracker~~ | FRED/yfinance 매크로 | `argos_macro` (1일 1회) | argos_macro |
| ~~macro_regime~~ | ECOS 금리/환율 | `argos_macro` (1일 1회) | argos_macro |
| ~~sector_rotator~~ | pykrx 업종 400회 | `argos_price_history` | argos_price_history |
| ~~sector_rotation~~ | yfinance 업종 | `argos_price_history` | argos_price_history |
| ~~sentiment_nlp~~ | SERPAPI 감성분석 | `argos_news` | argos_news |
| ~~sentiment_scorer~~ | 네이버 감성점수 | `argos_news` | argos_news |

**결과**: 팀장이 이 10개 도구 호출하느라 **40분 걸리던 것 → 0초** (DB에서 읽기)

---

### 🔵 서버 스폰 (서버 사전계산 — AI 호출 0회)

> 서버가 `pool.invoke()`로 Python 직접 실행 → 결과를 프롬프트에 주입

| 도구 | 계산 내용 | 서버 함수 | 주입 위치 |
|------|---------|----------|----------|
| ~~technical_analyzer~~ | RSI/MACD/볼린저/거래량 | `_build_quant_prompt_section()` | quant_section |
| ~~us_technical_analyzer~~ | 미국 RSI/MACD | `_build_quant_prompt_section()` | quant_section |
| ~~dcf_valuator~~ | DCF 적정가 계산 (numpy) | `_build_dcf_risk_prompt_section()` | dcf_risk_section |
| ~~us_financial_analyzer~~ | 미국 DCF (yfinance) | `_build_dcf_risk_prompt_section()` | dcf_risk_section |
| ~~risk_calculator~~ | VaR/MDD/Sharpe (numpy) | `_build_dcf_risk_prompt_section()` | dcf_risk_section |
| ~~portfolio_optimizer~~ | v2로 통합 | — | — |
| ~~portfolio_optimizer_v2~~ | MVO+Kelly 최적 비중 (scipy) | STEP2 서버 강제 실행 | step2_section |
| ~~correlation_analyzer~~ | DCC-GARCH 동시하락 (numpy) | STEP2 서버 강제 실행 | step2_section |

**결과**: 기존 44회 도구 호출 → **0회**. 서버가 전부 계산해서 넣어줌

---

### 🟡 팀장 AI 직접 (allowed_tools에 남아있는 것)

| 도구 | 왜 AI가 직접 해야 하나 |
|------|---------------------|
| `stock_screener` | 조건 판단 필요 (어떤 기준으로 필터할지) |
| `backtest_engine` | 전략 설계 판단 필요 |
| `insider_tracker` | 내부자 거래 해석 필요 |
| `dividend_calendar` | 배당 일정 판단 |
| `financial_calculator` | 재무 계산 (어떤 계산할지 판단) |
| `chart_generator` | 어떤 차트 그릴지 판단 |
| `spreadsheet_tool` | 데이터 가공 판단 |
| `pair_analyzer` | 페어 트레이딩 판단 |
| `sec_edgar` | SEC 공시 해석 |
| `options_flow` | 옵션 흐름 해석 |
| `trading_settings_control` | ⚠️ 매매 설정 변경 판단 |
| `trading_executor` | ⚠️ **실제 주문 실행** |
| `real_web_search` | 검색 결과 해석 |
| `notification_engine` | 알림 발송 판단 |
| `cross_agent_protocol` | 부서 간 협업 판단 |
| `read_knowledge` | 지식 파일 해석 |

---

# ════════════════════════════════════════
# 📈 전략팀장 (CSO) — 21개
# ════════════════════════════════════════

### 🔵 서버 스폰 (10개)

| 도구 | 실행 방식 | 비고 |
|------|---------|------|
| `naver_datalab` | Naver API 데이터 수집 | 검색량 트렌드 |
| `public_data` | 공공데이터포털 API | 정부 오픈데이터 |
| `platform_market_scraper` | 웹 스크래핑 | 플랫폼 시장 수집 |
| `scholar_scraper` | 논문 수집 | Google Scholar |
| `spreadsheet_tool` | pandas 데이터 처리 | |
| `chart_generator` | matplotlib/plotly | |
| `financial_calculator` | numpy_financial 수식 | IRR, NPV 등 |
| `decision_tracker` | DB 저장/조회 | |
| `lawschool_community` | 커뮤니티 수집 | ~~dc_lawschool_crawler~~, ~~orbi_crawler~~ 통합 |
| `competitor_monitor` | 경쟁사 웹 변경 감시 | 🟢 실시간 성격 |

### 🟡 팀장 AI 직접 (11개)

| 도구 | 왜 AI가 직접 해야 하나 |
|------|---------------------|
| `real_web_search` | 검색 결과 해석 |
| `cross_agent_protocol` | 부서 간 협업 |
| `market_sizer` | TAM/SAM/SOM 추정 판단 |
| `business_model_scorer` | 비즈니스 모델 평가 판단 |
| `competitive_mapper` | 경쟁 구도 분석 판단 |
| `growth_forecaster` | 성장 예측 판단 |
| `scenario_simulator` | 시나리오 분석 판단 |
| `pricing_optimizer` | 가격 전략 판단 |
| `customer_cohort_analyzer` | 고객 분석 판단 |
| `swot_quantifier` | SWOT 정량화 판단 |
| `read_knowledge` | 지식 해석 |

### ⛔ 삭제 (2개)

| 도구 | 사유 |
|------|------|
| ~~dc_lawschool_crawler~~ | `lawschool_community`에 완전 통합 |
| ~~orbi_crawler~~ | `lawschool_community`에 완전 통합 |

---

# ════════════════════════════════════════
# ⚖️ 법무팀장 (CLO) — 19개
# ════════════════════════════════════════

### 🔵 서버 스폰 (4개)

| 도구 | 실행 방식 |
|------|---------|
| `kipris` | KIPRIS 특허 API 검색 |
| `law_search` | 법제처 법령 API 검색 |
| `trademark_similarity` | 알고리즘 유사도 계산 |
| `license_scanner` | 오픈소스 라이선스 검색 (1,232줄 교수급) |

### 🟡 팀장 AI 직접 (15개)

| 도구 | 왜 AI가 직접 해야 하나 |
|------|---------------------|
| `precedent_analyzer` | **판례 법리 해석** 필요 |
| `contract_reviewer` | **계약서 법적 판단** 필요 |
| `nda_analyzer` | NDA 법적 해석 |
| `ip_portfolio_manager` | IP 포트폴리오 판단 |
| `ai_governance_checker` | AI 규제 해석 |
| `law_change_monitor` | 법 변화 해석 (🟢 실시간 성격) |
| `regulation_radar` | 규제 동향 해석 |
| `dispute_simulator` | 분쟁 시나리오 판단 |
| `compliance_checker` | 규정 준수 판단 |
| `privacy_auditor` | 개인정보 감사 판단 |
| `risk_communicator` | 위험 커뮤니케이션 판단 |
| `risk_matrix` | 위험 매트릭스 평가 |
| `real_web_search` | 검색 해석 |
| `cross_agent_protocol` | 부서 간 협업 |
| `read_knowledge` | 지식 해석 |

---

# ════════════════════════════════════════
# 📣 마케팅팀장 (CMO) — 30개
# ════════════════════════════════════════

### 🔵 서버 스폰 (15개)

| 도구 | 실행 방식 | 비고 |
|------|---------|------|
| `naver_datalab` | Naver API 검색량 | 트렌드 데이터 |
| `platform_market_scraper` | 웹 스크래핑 | 플랫폼 데이터 |
| `youtube_analyzer` | YouTube API | 조회수/댓글 수집 |
| `naver_news` | 네이버 뉴스 API | |
| `ab_test_engine` | 통계 검정 (634줄 교수급) | scipy t-test/chi2 |
| `customer_ltv_model` | BG/NBD+Gamma (836줄 교수급) | LTV 계산 |
| `pricing_sensitivity` | Van Westendorp PSM (611줄) | 가격 민감도 |
| `churn_risk_scorer` | 이탈 위험 점수 (641줄) | 로지스틱 모델 |
| `marketing_attribution` | 마케팅 귀속 (825줄 교수급) | Shapley/Markov |
| `cohort_retention` | Kaplan-Meier (741줄 교수급) | 리텐션 곡선 |
| `viral_coefficient` | K-factor 계산 (573줄) | 바이럴 계수 |
| `tts_generator` | 음성 합성 API | |
| `lipsync_video_generator` | 립싱크 알고리즘 | |
| `video_editor` | 미디어 처리 | |
| `customer_cohort_analyzer` | RFM/CAC 회수 (412줄) | |

### 🟡 팀장 AI 직접 (15개)

| 도구 | 왜 AI가 직접 해야 하나 |
|------|---------------------|
| `sentiment_analyzer` | NLP 감정 판단 |
| `hashtag_recommender` | 추천 판단 |
| `email_optimizer` | 이메일 최적화 판단 |
| `competitor_sns_monitor` | 경쟁사 SNS 해석 |
| `seo_analyzer` | SEO 분석 판단 |
| `sns_manager` | SNS 퍼블리싱 판단 |
| `notification_engine` | 알림 판단 |
| `cross_agent_protocol` | 부서 간 협업 |
| `funnel_analyzer` | 퍼널 분석 판단 (819줄 교수급) |
| `content_quality_scorer` | 콘텐츠 평가 판단 (851줄) |
| `gemini_image_generator` | 이미지 생성 프롬프트 판단 |
| `gemini_video_generator` | 영상 생성 프롬프트 판단 |
| `pricing_optimizer` | 가격 전략 판단 |
| `swot_quantifier` | SWOT 정량화 |
| `read_knowledge` | 지식 해석 |

### ⛔ 삭제 (1개)

| 도구 | 사유 |
|------|------|
| ~~rfm_segmentation~~ | 파일 미존재, `customer_ltv_model` segment에 흡수 |

---

# ════════════════════════════════════════
# 🗂️ 비서실장 — 13개
# ════════════════════════════════════════

### 🔵 서버 스폰 (1개)

| 도구 | 실행 방식 |
|------|---------|
| `decision_tracker` | DB 저장/조회만 |

### 🟡 팀장 AI 직접 (12개)

| 도구 | 역할 |
|------|------|
| `real_web_search` | 검색 해석 |
| `naver_news` | 뉴스 해석 |
| `notification_engine` | 알림 판단 |
| `calendar_tool` | 일정 판단 |
| `schedule_tool` | 스케줄 조정 |
| `email_sender` | 이메일 판단 |
| `cross_agent_protocol` | 부서 간 협업 |
| `agenda_optimizer` | 일정 최적화 (648줄 교수급) |
| `priority_matrix` | 우선순위 판단 (726줄 교수급) |
| `meeting_effectiveness` | 회의 분석 (753줄 교수급) |
| `delegation_analyzer` | 위임 분석 (631줄 교수급) |
| `stakeholder_mapper` | 이해관계자 분석 (566줄 교수급) |

---

# ════════════════════════════════════════
# 📝 콘텐츠팀장 (CPO) — 9개
# ════════════════════════════════════════

### 🔵 서버 스폰 (2개)

| 도구 | 실행 방식 |
|------|---------|
| `decision_tracker` | DB 저장/조회 |
| `doc_converter` | 파일 형식 변환 |

### 🟡 팀장 AI 직접 (7개)

| 도구 | 역할 |
|------|------|
| `report_generator` | 보고서 생성 판단 |
| `meeting_formatter` | 회의록 정리 판단 |
| `document_summarizer` | 문서 요약 (555줄) |
| `terms_generator` | 용어 생성 |
| `communication_optimizer` | 소통 최적화 (692줄 교수급) |
| `cross_agent_protocol` | 부서 간 협업 |
| `read_knowledge` | 지식 해석 |

### ⛔ 삭제 (1개)

| 도구 | 사유 |
|------|------|
| ~~newsletter_builder~~ | 오합지졸 — 콘텐츠 전부 LLM 의존, 도구 로직 없음 |

---

# ════════════════════════════════════════
# 🏆 교수급 도구 TOP 48 (학술 논문 참조 + 복잡 알고리즘)
# ════════════════════════════════════════

| 부서 | 도구 | 줄 수 | 핵심 알고리즘 |
|------|------|:-----:|-------------|
| **금융** | technical_analyzer | 948 | pykrx + pandas-ta 20종 지표 |
| | correlation_analyzer | 548 | DCC-GARCH 동시하락 위험 |
| | us_technical_analyzer | 531 | yfinance + 글로벌 기술분석 |
| | dcf_valuator | 488 | numpy DCF 3단계 모델 |
| | sec_edgar | 444 | SEC EDGAR 전자공시 파서 |
| | us_financial_analyzer | 412 | yfinance + DCF + 비교분석 |
| | risk_calculator | 410 | VaR/MDD/Sharpe/Sortino |
| | portfolio_optimizer_v2 | 373 | MVO + Kelly + Risk Parity |
| | pair_analyzer | 365 | 공적분 검정 + 스프레드 |
| | portfolio_optimizer | 347 | scipy MVO 한국 특화 |
| **비서** | meeting_effectiveness | 753 | 다차원 회의 효율성 모델 |
| | priority_matrix | 726 | Eisenhower + 가중 스코어링 |
| | agenda_optimizer | 648 | GTD + 시간블록 최적화 |
| | delegation_analyzer | 631 | RACI + 역량 매칭 |
| | stakeholder_mapper | 566 | 이해관계자 영향력 매핑 |
| **전략** | cross_agent_protocol | 570 | 에이전트 간 통신 프로토콜 |
| | competitive_mapper | 570 | Porter 5 Forces + 가치사슬 |
| | business_model_scorer | 519 | Business Model Canvas 스코어 |
| | market_sizer | 509 | TAM/SAM/SOM 3단계 추정 |
| | growth_forecaster | 479 | Bass 확산 + S-curve |
| | scenario_simulator | 467 | Monte Carlo 시뮬레이션 |
| | swot_quantifier | 457 | SWOT 정량화 매트릭스 |
| | customer_cohort_analyzer | 412 | RFM + CAC 회수 |
| | pricing_optimizer | 512 | PSM + 탄력성 + GBB |
| | financial_calculator | 325 | IRR/NPV/WACC |
| **법무** | license_scanner | 1232 | 오픈소스 라이선스 전수 분석 |
| | privacy_auditor | 732 | PIPA 2024 전조문 체크 |
| | compliance_checker | 681 | 규제 체크리스트 엔진 |
| | ai_governance_checker | 634 | AI 기본법 2026 대응 |
| | risk_communicator | 616 | 위험 커뮤니케이션 프레임 |
| | dispute_simulator | 562 | 분쟁 시나리오 트리 |
| | ip_portfolio_manager | 504 | IP 포트폴리오 가치평가 |
| | risk_matrix | 480 | 확률×영향 매트릭스 |
| | nda_analyzer | 461 | NDA 조항별 위험도 분석 |
| | trademark_similarity | 413 | 유사상표 알고리즘 |
| **마케팅** | content_quality_scorer | 851 | 다차원 콘텐츠 품질 모델 |
| | customer_ltv_model | 836 | BG/NBD + Gamma-Gamma |
| | marketing_attribution | 825 | Shapley + Markov 체인 |
| | funnel_analyzer | 819 | 퍼널 병목 자동 탐지 |
| | cohort_retention | 741 | Kaplan-Meier 생존 분석 |
| | churn_risk_scorer | 641 | 로지스틱 이탈 예측 |
| | ab_test_engine | 634 | Bayesian A/B 테스트 |
| | pricing_sensitivity | 611 | Van Westendorp PSM |
| | viral_coefficient | 573 | K-factor + 네트워크 효과 |
| | pricing_optimizer | 512 | PSM + 심리적 가격 |
| | customer_cohort_analyzer | 412 | RFM + CAC payback |
| **콘텐츠** | communication_optimizer | 692 | Flesch-Kincaid + 가독성 |
| | document_summarizer | 555 | 추출+추상 요약 하이브리드 |

---

# ════════════════════════════════════════
# ⛔ 전체 삭제/제거 이력
# ════════════════════════════════════════

## 도구 완전 삭제 (agents.yaml에서 제거)

| 도구 | 부서 | 사유 |
|------|------|------|
| `newsletter_builder` | 콘텐츠 | 오합지졸 — 로직 없이 LLM에만 의존 |
| `dc_lawschool_crawler` | 전략 | `lawschool_community`에 완전 통합 (중복) |
| `orbi_crawler` | 전략 | `lawschool_community`에 완전 통합 (중복) |
| `rfm_segmentation` | 마케팅 | 파일 미존재 — `customer_ltv_model` segment에 흡수 |

## 금융팀장 allowed_tools에서 제거 (서버 대체)

### ARGOS 실시간 대체 (10개)

| 도구 | 대체 수집 |
|------|---------|
| `dart_monitor` | ARGOS `argos_dart` |
| `sector_rotator` | ARGOS `price_history` |
| `sector_rotation` | ARGOS `price_history` |
| `global_market_tool` | ARGOS `price_history` |
| `macro_fed_tracker` | ARGOS `argos_macro` |
| `macro_regime` | ARGOS `argos_macro` |
| `sentiment_nlp` | ARGOS `argos_news` |
| `sentiment_scorer` | ARGOS `argos_news` |
| `earnings_surprise` | ARGOS 수집 |
| `earnings_ai` | ARGOS 수집 |

### 서버 사전계산 대체 (8개)

| 도구 | 대체 함수 |
|------|---------|
| `technical_analyzer` | `_build_quant_prompt_section()` |
| `us_technical_analyzer` | `_build_quant_prompt_section()` |
| `dcf_valuator` | `_build_dcf_risk_prompt_section()` |
| `us_financial_analyzer` | `_build_dcf_risk_prompt_section()` |
| `risk_calculator` | `_build_dcf_risk_prompt_section()` |
| `portfolio_optimizer` | v2로 통합 |
| `portfolio_optimizer_v2` | STEP2 서버 강제 실행 |
| `correlation_analyzer` | STEP2 서버 강제 실행 |

---

# ════════════════════════════════════════
# 🔄 미해결 — 합병 대상 (TODO)
# ════════════════════════════════════════

### 1. pricing_sensitivity + pricing_optimizer

- PSM, 탄력성, 티어 설계 **80% 중복**
- `pricing_sensitivity` (611줄): Van Westendorp PSM, Gabor-Granger, 점탄력성
- `pricing_optimizer` (512줄): PSM, 탄력성, 심리적 가격, Good-Better-Best
- **제안**: pricing_optimizer에 Gabor-Granger 추가 → pricing_sensitivity 삭제

### 2. customer_ltv_model + cohort_retention + customer_cohort_analyzer

- LTV/리텐션/이탈 분석 **부분 중복**
- `customer_ltv_model` (836줄): BG/NBD + Gamma-Gamma — 최고급
- `cohort_retention` (741줄): Kaplan-Meier + sBG — 최고급
- `customer_cohort_analyzer` (412줄): 위 두 도구의 요약판
- **제안**: customer_cohort_analyzer의 고유 기능(RFM, CAC 회수)을 다른 두 도구에 분배 후 삭제

---

# ════════════════════════════════════════
# 🏗️ 아키텍처 데이터 흐름 (금융분석팀장 기준)
# ════════════════════════════════════════

```
[1계층 — 서버 실시간 수집 (ARGOS)]
  ↓ cron (1분/30분/1시간/1일)
  ↓ argos_price_history, argos_news, argos_dart, argos_macro, argos_financial_data
  ↓
[2계층 — 서버 스폰 계산 (pool.invoke)]
  ├─ _build_quant_prompt_section()    → RSI/MACD/볼린저/추세 (quant_section)
  ├─ _build_argos_context_section()   → 주가/뉴스/공시/매크로 (argos_section)
  ├─ _build_dcf_risk_prompt_section() → DCF적정가/VaR/MDD (dcf_risk_section)
  └─ STEP2 강제 실행                   → 상관관계/포트폴리오 (step2_section)
  ↓
  ↓ 전부 프롬프트에 주입
  ↓
[3계층 — AI 판단 (금융분석팀장)]
  → 서버 제공 데이터만으로 매수/매도/관망 판단
  → 필요시만 stock_screener, backtest_engine 등 AI 직접 도구 호출
  ↓
[4계층 — 실행]
  → trading_executor (AI가 직접 주문)
  → notification_engine (보고)
```

---

> **이 문서는 `src/tools/*.py` 141개 파일을 3개 Opus 에이전트가 코드 한 줄 한 줄 읽고 분류한 결과입니다.**
> **변경 시 반드시 코드와 대조하세요.**
