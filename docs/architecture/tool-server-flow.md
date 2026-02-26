# CORTHEX 도구 전수검사 — 서버 vs AI 최적 실행 전략

> 작성일: 2026-02-26 | 분석 범위: config/tools.yaml 전체 131개 도구
> 목적: AI가 "심부름"까지 하는 낭비 구조를 제거하고 최적 실행 경로 설계

---

## 요약

| 분류 | 개수 | 비율 | 전략 |
|------|------|------|------|
| **서버 우위** | 47개 | 35.9% | 서버가 직접 실행. AI 불필요 |
| **서버+AI** | 51개 | 38.9% | 서버가 데이터 수집 → AI가 해석 |
| **AI 우위** | 33개 | 25.2% | AI만 가능. 신중하게 호출 |

**핵심 문제**: `technical_analyzer`가 1회 분석마다 7번 연속 호출 = 수치 계산을 AI가 도구로 호출하는 낭비

---

## 현재 흐름 vs 최적 흐름 (전체 공통)

```mermaid
flowchart TD
    subgraph 현재["❌ 현재 흐름 (낭비)"]
        A1[팀장 분석 시작] --> B1[AI: kr_stock 도구 호출]
        B1 --> C1[AI: dart_api 도구 호출]
        C1 --> D1[AI: naver_news 도구 호출]
        D1 --> E1[AI: technical_analyzer 호출]
        E1 --> F1[AI: 다시 technical_analyzer 호출]
        F1 --> G1[...7번 반복...]
        G1 --> H1[AI: 드디어 판단]
        H1 --> I1[결과]
    end

    subgraph 목표["✅ 최적 흐름 (목표)"]
        A2[팀장 분석 시작] --> B2[서버: 데이터 병렬 수집\n주가+재무+뉴스+기술지표]
        B2 --> C2[서버: 정량 계산\nRSI+MACD+DCF+VaR]
        C2 --> D2[AI: 패키지 받아서 판단만\n뉴스해석+매매결정+전략수립]
        D2 --> E2[결과]
    end

    style 현재 fill:#fff0f0
    style 목표 fill:#f0fff0
```

---

## 1. 서버 우위 도구 (47개) — AI 호출 없애야 함

### 1-1. 한국/미국 주식 데이터 그룹

```mermaid
flowchart LR
    REQ[팀장: 삼성전자 분석해줘] --> SERVER

    SERVER[서버 직접 실행]
    SERVER --> K1[pykrx\nkr_stock]
    SERVER --> K2[pykrx\ntechnical_analyzer]
    SERVER --> K3[pykrx\nstock_screener]
    SERVER --> K4[pykrx\nsector_rotator]
    SERVER --> K5[DART API\ndart_api]
    SERVER --> K6[DART API\ndart_monitor]
    SERVER --> K7[DART API\ninsider_tracker]
    SERVER --> K8[pykrx\ndividend_calendar]
    SERVER --> K9[yfinance\nus_stock]
    SERVER --> K10[yfinance\nglobal_market_tool]
    SERVER --> K11[SEC API\nsec_edgar]
    SERVER --> K12[수학 계산\ndcf_valuator]
    SERVER --> K13[수학 계산\nrisk_calculator]
    SERVER --> K14[수학 계산\nportfolio_optimizer]
    SERVER --> K15[수학 계산\nbacktest_engine]
    SERVER --> K16[수학 계산\npair_analyzer]
    SERVER --> K17[수학 계산\nearnings_surprise]
    SERVER --> K18[옵션 API\noptions_flow]
    SERVER --> K19[Fed API\nmacro_fed_tracker]
    SERVER --> K20[섹터 API\nsector_rotation]
    SERVER --> K21[수학 계산\nus_financial_analyzer]
    SERVER --> K22[ta-lib\nus_technical_analyzer]
    SERVER --> K23[수학 계산\ncorrelation_analyzer]

    K1 & K2 & K3 & K4 & K5 & K6 & K7 & K8 & K9 & K10 --> PACK
    K11 & K12 & K13 & K14 & K15 & K16 & K17 & K18 & K19 & K20 --> PACK
    K21 & K22 & K23 --> PACK

    PACK[📦 데이터 패키지\n현재가+기술지표+재무+공시\n→ 텍스트로 정리] --> AI

    AI[AI: 이 데이터 보고 판단만\n매수/매도/신뢰도/전략] --> OUT[결과 반환]

    style SERVER fill:#e8f5e9
    style AI fill:#e3f2fd
    style PACK fill:#fff9c4
```

**절감 효과**: 23개 도구 호출이 서버 1회 배치로 → AI 토큰 0 (데이터 수집 단계)

---

### 1-2. 공공/경제 데이터 그룹

```mermaid
flowchart LR
    REQ2[팀장: 시장 환경 분석] --> SRV2[서버 직접 실행]

    SRV2 --> E1[한국은행 ECOS API\necos_macro]
    SRV2 --> E2[Naver DataLab API\nnaver_datalab]
    SRV2 --> E3[공공데이터포털 API\npublic_data]
    SRV2 --> E4[KIPRIS API\nkipris]
    SRV2 --> E5[국가법령 API\nlaw_search]

    E1 & E2 & E3 & E4 & E5 --> PACK2[📦 경제지표 패키지\n금리+GDP+트렌드+법령]

    PACK2 --> AI2[AI: 거시경제 해석만]
    AI2 --> OUT2[결과]

    style SRV2 fill:#e8f5e9
    style AI2 fill:#e3f2fd
```

---

### 1-3. 개발/인프라 도구 그룹 (AI 완전 불필요)

```mermaid
flowchart TD
    REQ3[개발팀장 요청] --> SRV3[서버 단독 실행\nAI 완전 불필요]

    SRV3 --> D1[GitHub API\ngithub_tool]
    SRV3 --> D2[bandit+ruff+pytest\ncode_quality]
    SRV3 --> D3[pip-audit+OSV\nsecurity_scanner]
    SRV3 --> D4[HTTP 체크\nuptime_monitor]
    SRV3 --> D5[HTTP 성능 테스트\napi_benchmark]
    SRV3 --> D6[로그 파일 I/O\nlog_analyzer]
    SRV3 --> D7[tiktoken\ntoken_counter]
    SRV3 --> D8[pandas\nspreadsheet_tool]
    SRV3 --> D9[matplotlib\nchart_generator]
    SRV3 --> D10[PyPDF\npdf_parser]
    SRV3 --> D11[pandoc\ndoc_converter]
    SRV3 --> D12[ffmpeg\nvideo_editor]

    D1 & D2 & D3 & D4 & D5 & D6 --> OUT3[즉시 결과 반환]
    D7 & D8 & D9 & D10 & D11 & D12 --> OUT3

    style SRV3 fill:#e8f5e9
    style OUT3 fill:#f3e5f5
```

---

### 1-4. 운영/자동화 도구 그룹 (AI 완전 불필요)

```mermaid
flowchart LR
    REQ4[비서실장/시스템 요청] --> SRV4[서버 단독 실행]

    SRV4 --> O1[Notion API\nnotion_api]
    SRV4 --> O2[Google Calendar API\ncalendar_tool]
    SRV4 --> O3[SMTP/AWS SES\nemail_sender]
    SRV4 --> O4[Telegram Bot API\nnotification_engine]
    SRV4 --> O5[APScheduler\nschedule_tool]
    SRV4 --> O6[DB 저장\ndecision_tracker]
    SRV4 --> O7[KIS API\ntrading_executor]
    SRV4 --> O8[DB 설정\ntrading_settings_control]
    SRV4 --> O9[SerpAPI\nreal_web_search]
    SRV4 --> O10[diff 알고리즘\ncompetitor_monitor]

    O1 & O2 & O3 & O4 & O5 --> OUT4[즉시 실행]
    O6 & O7 & O8 & O9 & O10 --> OUT4

    style SRV4 fill:#e8f5e9
```

---

### 1-5. 마케팅 분석 (수치 계산만) 그룹

```mermaid
flowchart LR
    REQ5[마케팅팀장 요청] --> SRV5[서버 수치 계산]

    SRV5 --> M1[scipy.stats\nab_test_engine]
    SRV5 --> M2[lifetimes\ncustomer_ltv_model]
    SRV5 --> M3[pandas\nrfm_segmentation]
    SRV5 --> M4[분위수 계산\nfunnel_analyzer]
    SRV5 --> M5[game theory\nmarketing_attribution]
    SRV5 --> M6[생존분석\nchurn_risk_scorer]
    SRV5 --> M7[cohort\ncohort_retention]
    SRV5 --> M8[Bass 모델\nviral_coefficient]
    SRV5 --> M9[PSM 공식\npricing_sensitivity]
    SRV5 --> M10[재무계산\nfinancial_calculator]

    M1 & M2 & M3 & M4 & M5 --> PACK5[📦 수치 계산 결과]
    M6 & M7 & M8 & M9 & M10 --> PACK5

    PACK5 --> AI5[AI: 전략 수립만]
    AI5 --> OUT5[결과]

    style SRV5 fill:#e8f5e9
    style AI5 fill:#e3f2fd
```

---

## 2. 서버+AI 도구 (51개) — 역할 분리 필요

### 2-1. 뉴스/감성 분석 그룹

```mermaid
flowchart TD
    REQ6[팀장: 삼성전자 뉴스 분석] --> SPLIT[역할 분리]

    SPLIT --> SRV6[서버 담당]
    SPLIT --> AI6[AI 담당]

    SRV6 --> N1[Naver Search API\nnaver_news\n뉴스 원문 수집]
    SRV6 --> N2[감정사전 점수 계산\nsentiment_scorer\n긍/부/중립 비율]
    SRV6 --> N3[뉴스 API 수집\nsentiment_nlp\nFear&Greed지수]

    N1 & N2 & N3 --> PACK6[📦 뉴스+수치 패키지\n원문 5건 + 감정점수]

    PACK6 --> AI6
    AI6 --> I1[맥락 해석\n주가 영향도 판단]
    AI6 --> I2[투자 시사점 도출]

    I1 & I2 --> OUT6[뉴스 분석 결과]

    style SRV6 fill:#e8f5e9
    style AI6 fill:#e3f2fd
    style PACK6 fill:#fff9c4
```

---

### 2-2. 법무 데이터 + 해석 그룹

```mermaid
flowchart TD
    REQ7[법무팀장: 법령/판례 분석] --> SPLIT7[역할 분리]

    SPLIT7 --> SRV7[서버 담당]
    SPLIT7 --> AI7[AI 담당]

    SRV7 --> L1[국가법령정보 API\nlaw_search\n법령 원문 조회]
    SRV7 --> L2[KIPRIS API\nkipris\n특허 데이터 조회]
    SRV7 --> L3[판례 DB\nprecedent_analyzer\n판례 수집+통계]
    SRV7 --> L4[법령 변경 감지\nlaw_change_monitor\n개정 감지]
    SRV7 --> L5[KIPRIS\nip_portfolio_manager\nIP 데이터 수집]

    L1 & L2 & L3 & L4 & L5 --> PACK7[📦 법무 데이터 패키지\n원문+통계+변경이력]

    PACK7 --> AI7
    AI7 --> LI1[법적 해석\n리스크 평가]
    AI7 --> LI2[전략 수립\n대응 방안]

    LI1 & LI2 --> OUT7[법무 분석 결과]

    style SRV7 fill:#e8f5e9
    style AI7 fill:#e3f2fd
```

---

### 2-3. 크롤링 + 분석 그룹 (커뮤니티/리뷰)

```mermaid
flowchart TD
    REQ8[콘텐츠팀장: 커뮤니티 분석] --> SPLIT8[역할 분리]

    SPLIT8 --> SRV8[서버 담당 크롤링]
    SPLIT8 --> AI8[AI 담당 분석]

    SRV8 --> C1[웹 크롤링\ndaum_cafe\n카페 게시글 수집]
    SRV8 --> C2[멀티채널\nleet_survey\n6개 커뮤니티 수집]
    SRV8 --> C3[DC갤\ndc_lawschool_crawler\n게시글 수집]
    SRV8 --> C4[오르비\norbi_crawler\n게시글 수집]
    SRV8 --> C5[통합\nlawschool_community\n3채널 수집]
    SRV8 --> C6[Play Store\napp_review_scraper\n리뷰 수집]
    SRV8 --> C7[네이버 플레이스\nnaver_place_scraper\n리뷰 수집]
    SRV8 --> C8[Google Scholar\nscholar_scraper\n논문 수집]

    C1 & C2 & C3 & C4 --> PACK8[📦 커뮤니티 데이터\n원문+메타정보]
    C5 & C6 & C7 & C8 --> PACK8

    PACK8 --> AI8
    AI8 --> CI1[트렌드 해석]
    AI8 --> CI2[감정/의견 분석]
    AI8 --> CI3[인사이트 도출]

    CI1 & CI2 & CI3 --> OUT8[커뮤니티 분석 결과]

    style SRV8 fill:#e8f5e9
    style AI8 fill:#e3f2fd
```

---

### 2-4. 마케팅 채널/경쟁사 + AI 그룹

```mermaid
flowchart LR
    REQ9[마케팅팀장: 경쟁사/채널 분석] --> SPLIT9[역할 분리]

    SPLIT9 --> SRV9[서버 담당]
    SPLIT9 --> AI9[AI 담당]

    SRV9 --> MC1[SNS API\nsns_manager\n발행/수집]
    SRV9 --> MC2[크롤링\ncompetitor_sns_monitor\n경쟁사 SNS 활동]
    SRV9 --> MC3[YouTube API\nyoutube_analyzer\n채널 데이터]
    SRV9 --> MC4[정부 포털\nsubsidy_finder\n지원사업 검색]
    SRV9 --> MC5[크롤링\nplatform_market_scraper\n플랫폼 가격]

    MC1 & MC2 & MC3 & MC4 & MC5 --> PACK9[📦 마케팅 데이터]

    PACK9 --> AI9
    AI9 --> MI1[전략 분석]
    AI9 --> MI2[경쟁 우위 평가]
    AI9 --> MI3[콘텐츠 전략]

    MI1 & MI2 & MI3 --> OUT9[마케팅 전략 결과]

    style SRV9 fill:#e8f5e9
    style AI9 fill:#e3f2fd
```

---

### 2-5. 사업기획 분석 그룹

```mermaid
flowchart TD
    REQ10[전략팀장: 사업 분석] --> SPLIT10[역할 분리]

    SPLIT10 --> SRV10[서버 계산]
    SPLIT10 --> AI10[AI 판단]

    SRV10 --> B1[Bass 모델 계산\ngrowth_forecaster]
    SRV10 --> B2[Monte Carlo\nscenario_simulator]
    SRV10 --> B3[상표 유사도\ntrademark_similarity]
    SRV10 --> B4[AHP+SWOT 점수\nswot_quantifier]
    SRV10 --> B5[Eisenhower+RICE\npriority_matrix]
    SRV10 --> B6[리스크 매트릭스\nrisk_matrix]
    SRV10 --> B7[PSM+탄력성\npricing_optimizer]
    SRV10 --> B8[코호트 계산\ncustomer_cohort_analyzer]
    SRV10 --> B9[Mitchell 매트릭스\nstakeholder_mapper]

    B1 & B2 & B3 & B4 & B5 --> PACK10[📦 분석 수치]
    B6 & B7 & B8 & B9 --> PACK10

    PACK10 --> AI10
    AI10 --> BI1[전략 판단]
    AI10 --> BI2[위험 평가]
    AI10 --> BI3[실행 계획]

    BI1 & BI2 & BI3 --> OUT10[사업 분석 결과]

    style SRV10 fill:#e8f5e9
    style AI10 fill:#e3f2fd
```

---

### 2-6. 콘텐츠 품질 + AI 그룹

```mermaid
flowchart LR
    REQ11[콘텐츠팀장: 콘텐츠 평가] --> SPLIT11[역할 분리]

    SPLIT11 --> SRV11[서버 점수 계산]
    SPLIT11 --> AI11[AI 개선안 생성]

    SRV11 --> CO1[Flesch-Kincaid\ncontent_quality_scorer\n가독성+SEO 점수]
    SRV11 --> CO2[이메일 8개 규칙\nemail_optimizer\n제목 점수]
    SRV11 --> CO3[SEO 14개 항목\nseo_analyzer\nSEO 점수]
    SRV11 --> CO4[Flesch+Cialdini\ncommunication_optimizer\n설득력 점수]
    SRV11 --> CO5[Pareto 계산\nmeeting_effectiveness\nROI 점수]

    CO1 & CO2 & CO3 & CO4 & CO5 --> PACK11[📦 점수 패키지\n수치+약점 목록]

    PACK11 --> AI11
    AI11 --> COI1[개선안 작성]
    AI11 --> COI2[A/B 대안 생성]

    COI1 & COI2 --> OUT11[콘텐츠 개선안]

    style SRV11 fill:#e8f5e9
    style AI11 fill:#e3f2fd
```

---

### 2-7. 뉴스레터/보고서 생성 그룹

```mermaid
flowchart TD
    REQ12[비서실장/콘텐츠팀장: 뉴스레터 생성] --> SPLIT12[역할 분리]

    SPLIT12 --> SRV12[서버: 소재 수집]
    SPLIT12 --> AI12[AI: 글쓰기]

    SRV12 --> NL1[Naver API\n뉴스 수집]
    SRV12 --> NL2[pykrx\n주가 데이터]
    SRV12 --> NL3[ECOS\n경제지표]

    NL1 & NL2 & NL3 --> PACK12[📦 소재 패키지]
    PACK12 --> AI12

    AI12 --> NLO1[newsletter_builder\n뉴스레터 작성]
    AI12 --> NLO2[report_generator\n보고서 작성]
    AI12 --> NLO3[meeting_formatter\n회의록 정리]
    AI12 --> NLO4[document_summarizer\n문서 요약]
    AI12 --> NLO5[terms_generator\n용어집 생성]

    NLO1 & NLO2 & NLO3 & NLO4 & NLO5 --> OUT12[최종 문서]

    style SRV12 fill:#e8f5e9
    style AI12 fill:#e3f2fd
```

---

## 3. AI 우위 도구 (33개) — AI만 가능, 신중하게 호출

```mermaid
flowchart TD
    subgraph AI_ONLY["🤖 AI 전용 도구 — 배치 처리로 효율화"]

        subgraph LAW["법무 해석"]
            L1[contract_reviewer\n계약서 위험 조항]
            L2[nda_analyzer\nNDA 리스크]
            L3[license_scanner\n라이선스 해석]
            L4[ai_governance_checker\nAI 규제 준수]
            L5[compliance_checker\nGDPR/개보법]
            L6[privacy_auditor\nPIA/DPIA]
            L7[dispute_simulator\n분쟁 시뮬레이션]
            L8[risk_communicator\n위기 커뮤니케이션]
        end

        subgraph TECH["기술 판단"]
            T1[architecture_evaluator\n아키텍처 평가]
            T2[performance_profiler\n병목 탐지]
            T3[tech_debt_analyzer\n기술부채 판단]
            T4[system_design_advisor\n시스템 설계]
            T5[ai_model_evaluator\nAI 모델 비교]
            T6[prompt_tester\n프롬프트 평가]
        end

        subgraph BIZ["사업 판단"]
            B1[market_sizer\n시장규모 추정]
            B2[business_model_scorer\n비즈니스 모델 평가]
            B3[competitive_mapper\n경쟁 전략]
            B4[agenda_optimizer\n회의 설계]
            B5[delegation_analyzer\n위임 전략]
        end

        subgraph CONTENT["콘텐츠 생성"]
            C1[hashtag_recommender\n해시태그 추천]
            C2[report_generator\n전문 보고서]
            C3[document_summarizer\n문서 요약]
            C4[terms_generator\n용어집]
            C5[agenda_optimizer\n안건 최적화]
        end

        subgraph MEDIA["미디어 생성"]
            M1[image_generator\nDALL-E 이미지]
            M2[gemini_image_generator\nGemini 이미지]
            M3[gemini_video_generator\nVeo 영상]
            M4[tts_generator\nOpenAI TTS]
            M5[lipsync_video_generator\n립싱크 영상]
            M6[audio_transcriber\nWhisper STT]
        end

        subgraph VECTOR["AI 인프라"]
            V1[embedding_tool\n벡터 임베딩]
            V2[vector_knowledge\nRAG 검색]
            V3[cross_agent_protocol\n에이전트 통신]
        end

    end

    CALL[팀장 요청] --> BATCH[배치 처리\n관련 도구 1번 호출에 묶기]
    BATCH --> AI_ONLY
    AI_ONLY --> RESULT[결과]

    style AI_ONLY fill:#e3f2fd
    style BATCH fill:#fff9c4
```

---

## 4. 현재 CIO 분석 흐름 개선안 (가장 낭비 심한 케이스)

### 현재 (❌)

```mermaid
sequenceDiagram
    participant 팀장
    participant AI
    participant 도구

    팀장->>AI: 삼성전자 분석해줘
    AI->>도구: kr_stock 호출 (1회)
    도구-->>AI: 현재가 반환
    AI->>도구: technical_analyzer 호출 (2회)
    도구-->>AI: RSI 반환
    AI->>도구: technical_analyzer 호출 (3회)
    도구-->>AI: MACD 반환
    AI->>도구: technical_analyzer 호출 (4회)
    도구-->>AI: 볼린저밴드 반환
    AI->>도구: dart_api 호출 (5회)
    도구-->>AI: 재무제표 반환
    AI->>도구: naver_news 호출 (6회)
    도구-->>AI: 뉴스 반환
    AI->>도구: technical_analyzer 호출 (7회)
    도구-->>AI: 추가 지표 반환
    AI-->>팀장: 분석 결과

    note over AI,도구: 도구 7회 호출 / 소요 3~5분 / AI가 심부름도 함
```

### 최적화 후 (✅)

```mermaid
sequenceDiagram
    participant 팀장
    participant 서버
    participant AI

    팀장->>서버: 삼성전자 분석 요청
    서버->>서버: pykrx 직접 호출 (현재가+OHLCV 60일)
    서버->>서버: RSI/MACD/BB/거래량/추세 계산 (이미 구현됨)
    서버->>서버: DART API 직접 호출 (재무제표)
    서버->>서버: Naver API 직접 호출 (뉴스 5건)
    서버->>AI: 패키지 전달\n"현재가: 72,000 / RSI: 28.3(과매도) / MACD: 골든크로스 / 뉴스: ..."
    AI-->>서버: 매수 72% / 근거: RSI과매도+골든크로스, 뉴스 긍정적
    서버-->>팀장: 분석 결과

    note over 서버: 서버가 전부 수집 (0.5초)
    note over AI: AI는 판단만 (1회 호출)
    note over 팀장: 도구 1회 / 소요 30초 / AI는 생각만
```

---

## 5. 도구별 최적화 우선순위 및 절감 효과

| 우선순위 | 도구 | 현재 낭비 | 개선 방법 | 예상 절감 |
|---------|------|---------|---------|---------|
| ⭐⭐⭐ | `technical_analyzer` | 1분석당 7회 호출 | 서버 직접 계산 (이미 구현) | 토큰 70% ↓ |
| ⭐⭐⭐ | `kr_stock` | 매번 AI 경유 | pykrx 직접 (이미 가능) | 토큰 100% ↓ |
| ⭐⭐⭐ | `dart_api` | AI가 API 호출 | DART API 서버 직접 | 토큰 100% ↓ |
| ⭐⭐⭐ | `naver_news` | AI가 검색 | Naver API 서버 직접 | 토큰 100% ↓ |
| ⭐⭐ | `ecos_macro` | AI가 API 호출 | ECOS API 서버 직접 | 토큰 100% ↓ |
| ⭐⭐ | `sentiment_scorer` | AI가 점수 계산 | 감정사전 서버 계산 | 토큰 60% ↓ |
| ⭐⭐ | `dcf_valuator` | AI가 수식 계산 | numpy 서버 직접 | 토큰 100% ↓ |
| ⭐⭐ | `portfolio_optimizer` | AI가 MVO 계산 | scipy 서버 직접 | 토큰 100% ↓ |
| ⭐ | `real_web_search` | AI 경유 | SerpAPI 직접 | 토큰 100% ↓ |
| ⭐ | `notification_engine` | AI 경유 | Telegram API 직접 | 토큰 100% ↓ |

---

## 6. 구현 단계별 로드맵

```mermaid
gantt
    title 도구 서버화 로드맵
    dateFormat YYYY-MM-DD
    section Phase 1 즉시 (이미 준비됨)
        technical_analyzer 서버화       :done, p1a, 2026-02-26, 1d
        quant_score 프롬프트 주입        :done, p1b, 2026-02-26, 1d
    section Phase 2 단기 (1~2주)
        DART API 서버 직접 호출          :p2a, 2026-02-27, 3d
        Naver News API 서버 직접         :p2b, 2026-02-27, 2d
        ECOS 경제지표 서버 직접           :p2c, 2026-03-01, 2d
        데이터 패키지 빌더 구현            :p2d, 2026-03-02, 3d
    section Phase 3 중기 (2~4주)
        DCF/포트폴리오 계산 서버화         :p3a, 2026-03-08, 5d
        감정사전 서버 계산                :p3b, 2026-03-08, 3d
        컨텍스트 패키저 (전종목)           :p3c, 2026-03-10, 5d
    section Phase 4 장기 (1~2달)
        도구별 캐싱 (TTL 1시간)           :p4a, 2026-03-20, 7d
        모델 티어링 (Haiku→Sonnet→Opus)  :p4b, 2026-03-25, 5d
        전체 비용 대시보드                :p4c, 2026-04-01, 5d
```

---

## 7. 비용 시뮬레이션

| 시나리오 | AI 호출/분석 | 예상 토큰 | 월간 비용 (분석 100회) |
|---------|------------|---------|---------------------|
| 현재 (낭비) | 15~25회 | ~20,000 | ~$50~100 |
| Phase 2 완료 후 | 5~8회 | ~8,000 | ~$20~40 |
| Phase 4 완료 후 | 2~3회 | ~3,000 | ~$5~15 |

**예상 총 절감: 월 $35~85 (70~85% 절감)**

---

## 8. 크롤링 판단 기준

| 조건 | 분류 | 이유 |
|------|------|------|
| 정해진 URL + 정형 HTML | 서버 우위 | BeautifulSoup으로 충분 |
| 로그인 필요 / SPA | 서버+AI | 서버가 Selenium → AI가 파싱 |
| 비정형 텍스트 해석 필요 | AI 우위 | 의미 추출은 AI만 가능 |
| API 없고 HTML 불규칙 | 서버+AI | 서버가 HTML → AI가 데이터 추출 |

**결론**: 크롤링은 "데이터 수집"은 서버, "의미 추출"은 AI. 대부분의 CORTHEX 크롤링 도구는 서버+AI 패턴이 적합.

---

> 이 문서 기반으로 구현 시 `docs/architecture/` 폴더에 세부 구현 문서 추가 예정
> VSCode에서 `Ctrl+Shift+V` 누르시면 mermaid 플로우차트가 그림으로 보입니다
