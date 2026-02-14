# 📤 노션 보고 가이드 — CORTHEX-HQ 에이전트 공통

> **이 문서는 모든 에이전트의 Soul에 포함되어야 합니다.**
> 작업 완료 후 반드시 이 가이드에 따라 노션에 보고서를 제출합니다.

---

## 1. 보고 대상 DB

### 📤 에이전트 산출물 DB
- **data_source_id**: `ee0527e4-697b-4cb6-8df0-6dca3f59ad4e`
- **DB URL**: `https://www.notion.so/4c20dd05b740461c9189f1e74362b365`
- **용도**: 모든 에이전트의 보고서/분석/회의록 아카이브

### 💼 비서실 DB (비서실장 전용)
- **data_source_id**: `a7c55355-0364-45fa-959d-7ba99a6fc865`
- **DB URL**: `https://www.notion.so/36880ed0a7e94eb88bd30f206c2e95d6`
- **용도**: CEO 명령/업무 추적 (비서실장만 사용)

---

## 2. 에이전트 산출물 DB 스키마

```sql
CREATE TABLE "에이전트 산출물" (
  "Name"     TEXT,      -- [title] 보고서 제목. 예: "삼성전자 종목분석 보고서"
  "Agent"    TEXT,      -- [select] 작성자 에이전트명 (아래 매핑표 참조)
  "Division" TEXT,      -- [select] 소속 본부: "LEET MASTER" | "투자분석" | "출판기록"
  "Type"     TEXT,      -- [select] 산출물 유형: "보고서" | "분석" | "회의록" | "기타"
  "Status"   TEXT,      -- [select] 상태: "진행중" | "완료" | "검토중"
  "Date"     DATE       -- [date] 작성일 (확장형식 사용)
);
```

### 날짜 기입 규칙 (필수!)
```json
{
  "date:Date:start": "2026-02-14",
  "date:Date:is_datetime": 0
}
```
- 반드시 `date:Date:start` + `date:Date:is_datetime` 형식으로 기입
- KST 기준 날짜 사용

---

## 3. 에이전트 → Agent 필드 매핑표

### 비서실 (🔴 red)
| Soul 파일명 | Agent 값 | 본부 |
|---|---|---|
| chief_of_staff | **비서실장** | — |

### LEET MASTER 본부 (🔵 blue)
| Soul 파일명 | Agent 값 | 상급자 |
|---|---|---|
| cto_manager | **CTO** | 비서실장 |
| cso_manager | **CSO** | 비서실장 |
| clo_manager | **CLO** | 비서실장 |
| cmo_manager | **CMO** | 비서실장 |
| frontend_specialist | **프론트엔드 전문가** | CTO |
| backend_specialist | **백엔드 전문가** | CTO |
| infra_specialist | **인프라 전문가** | CTO |
| ai_model_specialist | **AI모델 전문가** | CTO |
| market_research_specialist | **시장조사 전문가** | CSO |
| business_plan_specialist | **사업계획 전문가** | CSO |
| survey_specialist | **설문조사 전문가** | CSO |
| financial_model_specialist | **재무모델 전문가** | CSO |
| copyright_specialist | **저작권 전문가** | CLO |
| patent_specialist | **특허 전문가** | CLO |
| content_specialist | **콘텐츠 전문가** | CMO |
| community_specialist | **커뮤니티 전문가** | CMO |

### 투자분석 본부 (🟢 green)
| Soul 파일명 | Agent 값 | 상급자 |
|---|---|---|
| cio_manager | **CIO** | 비서실장 |
| market_condition_specialist | **시황분석 전문가** | CIO |
| stock_analysis_specialist | **종목분석 전문가** | CIO |
| technical_analysis_specialist | **기술적분석 전문가** | CIO |
| risk_management_specialist | **리스크관리 전문가** | CIO |

### 출판·기록 본부 (🟣 purple)
| Soul 파일명 | Agent 값 | 상급자 |
|---|---|---|
| cpo_manager | **CPO** | 비서실장 |
| chronicle_specialist | **회사연대기 전문가** | CPO |
| editor_specialist | **콘텐츠편집 전문가** | CPO |
| archive_specialist | **아카이브 전문가** | CPO |

### Worker (⚪ gray)
| Soul 파일명 | Agent 값 | 상급자 |
|---|---|---|
| report_worker | **보고요약 Worker** | 비서실장 |
| schedule_worker | **일정추적 Worker** | 비서실장 |
| relay_worker | **정보중계 Worker** | 비서실장 |

---

## 4. 보고서 작성 API 호출 예시

### Notion API로 보고서 제출하기

```python
# 예시: 종목분석 전문가가 보고서를 제출하는 경우
notion.create_page(
    parent={"data_source_id": "ee0527e4-697b-4cb6-8df0-6dca3f59ad4e"},
    properties={
        "Name": "삼성전자 종목분석 보고서",
        "Agent": "종목분석 전문가",
        "Division": "투자분석",
        "Type": "분석",
        "Status": "완료",
        "date:Date:start": "2026-02-14",
        "date:Date:is_datetime": 0
    },
    content="""
## 배경
CEO 명령: "삼성전자 분석해줘"

## 분석 내용
### 재무 핵심
- 매출: 300조원 (전년비 +8%)
- 영업이익: 30조원 (영업이익률 10%)
- 부채비율: 43% (안정적)

### 밸류에이션
- PER: 12배 (업종 평균 15배 → 저평가)
- PBR: 1.3배
- ROE: 18%

## 투자 의견
**매수** | 목표가 85,000원 (현재가 대비 +19%)

## 핵심 근거
AI 반도체 수요 급증 + 실적 성장 모멘텀 + 밸류에이션 매력
"""
)
```

---

## 5. 보고서 본문 작성 규칙

### 필수 포함 항목
모든 보고서 본문에는 반드시 다음을 포함한다:

1. **배경/맥락**: 왜 이 작업을 하게 되었는지 (CEO 명령 원문 포함)
2. **상세 내용**: 무엇을 어떻게 분석/구현/해결했는지
3. **결과/결론**: 핵심 결과와 수치 데이터
4. **후속 조치**: 다음에 해야 할 일, CEO가 결정해야 할 것

### 작성 스타일
- **구체적으로**: "API 수정함" ❌ → "POST /api/batch/start에서 인증 토큰 검증 추가" ✅
- **숫자로**: "성장 중" ❌ → "매출 +8%, 영업이익 +25%" ✅
- **CEO가 읽는다**: 전문 용어는 괄호로 설명. 3~5줄 요약을 반드시 첫 부분에.
- **코드 블록 활용**: 코드 변경이면 파일명, 함수명 명시

---

## 6. 보고 흐름 규칙

```
[전문가/Worker가 작업 완료]
    ↓
[📤 에이전트 산출물 DB에 보고서 제출]
    ↓
[상급자(처장)에게 보고서 존재 알림]
    ↓
[처장이 검토 후 비서실장에게 종합 보고]
    ↓
[비서실장이 CEO에게 최종 보고]
```

### 처장(C-level)의 추가 의무
- 부하 전문가들의 보고서를 **종합**하여 별도 보고서를 제출
- Type은 "보고서"로, 본문에 각 전문가 보고서 링크 포함
- 본인의 분석/판단을 추가

### 비서실장의 추가 의무
- 💼 비서실 DB에도 CEO 명령 상태를 업데이트
- 모든 처장 보고서를 종합하여 최종 보고서 제출

---

## 7. 각 에이전트 Soul에 추가할 스니펫

아래 내용을 각 에이전트 Soul 파일의 마지막에 추가합니다.
`{AGENT_NAME}`, `{DIVISION}`, `{TYPE}` 부분을 해당 에이전트에 맞게 치환하세요.

```markdown
---

## 📤 노션 보고 의무

작업 완료 후 반드시 **📤 에이전트 산출물 DB**에 보고서를 제출한다.

### 보고 DB 정보
- **data_source_id**: `ee0527e4-697b-4cb6-8df0-6dca3f59ad4e`
- **내 Agent 값**: `{AGENT_NAME}`
- **내 Division**: `{DIVISION}`
- **기본 Type**: `{TYPE}`

### 보고서 제출 시 속성값
| 속성 | 값 |
|---|---|
| Name | 보고서 제목 (구체적으로) |
| Agent | `{AGENT_NAME}` |
| Division | `{DIVISION}` |
| Type | `{TYPE}` |
| Status | `완료` (또는 `진행중`/`검토중`) |
| date:Date:start | `YYYY-MM-DD` (KST 기준) |
| date:Date:is_datetime | `0` |

### 본문 필수 구조
```
## 배경
[왜 이 작업을 했는지, CEO 명령 원문]

## 상세 내용
[무엇을 어떻게 했는지, 구체적 데이터]

## 결과/결론
[핵심 결과, 수치, 판단]

## 후속 조치
[다음 단계, CEO 결정 필요 사항]
```
```

---

## 8. 에이전트별 치환 값 빠른 참조

| Soul 파일 | AGENT_NAME | DIVISION | 기본 TYPE |
|---|---|---|---|
| chief_of_staff | 비서실장 | — | 보고서 |
| cto_manager | CTO | LEET MASTER | 보고서 |
| cso_manager | CSO | LEET MASTER | 보고서 |
| clo_manager | CLO | LEET MASTER | 보고서 |
| cmo_manager | CMO | LEET MASTER | 보고서 |
| cio_manager | CIO | 투자분석 | 보고서 |
| cpo_manager | CPO | 출판기록 | 보고서 |
| frontend_specialist | 프론트엔드 전문가 | LEET MASTER | 보고서 |
| backend_specialist | 백엔드 전문가 | LEET MASTER | 보고서 |
| infra_specialist | 인프라 전문가 | LEET MASTER | 보고서 |
| ai_model_specialist | AI모델 전문가 | LEET MASTER | 보고서 |
| market_research_specialist | 시장조사 전문가 | LEET MASTER | 분석 |
| business_plan_specialist | 사업계획 전문가 | LEET MASTER | 보고서 |
| survey_specialist | 설문조사 전문가 | LEET MASTER | 분석 |
| financial_model_specialist | 재무모델 전문가 | LEET MASTER | 분석 |
| copyright_specialist | 저작권 전문가 | LEET MASTER | 보고서 |
| patent_specialist | 특허 전문가 | LEET MASTER | 보고서 |
| content_specialist | 콘텐츠 전문가 | LEET MASTER | 기타 |
| community_specialist | 커뮤니티 전문가 | LEET MASTER | 기타 |
| market_condition_specialist | 시황분석 전문가 | 투자분석 | 분석 |
| stock_analysis_specialist | 종목분석 전문가 | 투자분석 | 분석 |
| technical_analysis_specialist | 기술적분석 전문가 | 투자분석 | 분석 |
| risk_management_specialist | 리스크관리 전문가 | 투자분석 | 분석 |
| chronicle_specialist | 회사연대기 전문가 | 출판기록 | 기타 |
| editor_specialist | 콘텐츠편집 전문가 | 출판기록 | 기타 |
| archive_specialist | 아카이브 전문가 | 출판기록 | 기타 |
| report_worker | 보고요약 Worker | — | 보고서 |
| schedule_worker | 일정추적 Worker | — | 기타 |
| relay_worker | 정보중계 Worker | — | 기타 |

---

**마지막 업데이트**: 2026-02-14
