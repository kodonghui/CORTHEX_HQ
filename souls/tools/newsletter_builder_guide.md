# newsletter_builder — 자동 뉴스레터 생성기 도구 가이드

## 이 도구는 뭔가요?
주간/월간 뉴스레터를 AI가 자동으로 만들어주는 도구입니다.
뉴스, 트렌드, 커뮤니티 이야기, 팁 등 여러 섹션을 포함한 뉴스레터를 마크다운과 HTML(이메일 발송용) 두 가지 형식으로 생성합니다.
data/ 폴더의 기존 수집 데이터(뉴스, 시장 데이터 등)가 있으면 자동으로 참고하여 더 풍부한 내용을 만듭니다.

## 어떤 API를 쓰나요?
- **AI 생성** (각 섹션 콘텐츠, 인트로, 품질 검토 모두 AI가 작성)
- **내장 마크다운→HTML 변환기** (이메일 호환 HTML로 자동 변환)
- 비용: **무료** (AI 호출 비용만 발생)
- 필요한 키: 없음 (AI 모델 키는 시스템에서 자동 사용)

## 사용법

### action=build (뉴스레터 생성)
```
action="build", period="weekly", topic="LEET/법학", sections="news,trends,community,tips"
```
- AI가 지정된 주제와 섹션으로 뉴스레터를 자동 생성합니다
- 생성 결과: 마크다운 파일(.md) + HTML 이메일 파일(.html)
- AI가 뉴스레터 품질 검토(추천 제목, 품질 점수, 개선 포인트)도 함께 수행합니다
- data/ 폴더에 관련 데이터 파일(뉴스, 트렌드 등)이 있으면 자동으로 활용합니다

**파라미터:**
- `period` (선택): "weekly"(주간, 기본) 또는 "monthly"(월간)
- `topic` (선택): 뉴스레터 주제 (기본: "LEET/법학")
- `sections` (선택): 포함할 섹션 목록, 쉼표 구분 (기본: "news,trends,community,tips")

**사용 가능 섹션:**

| 섹션 키 | 이름 | 내용 |
|--------|------|------|
| news | 주요 뉴스 | 주제 관련 이번 주 주요 뉴스/이슈 3~5개 |
| trends | 트렌드 & 데이터 | 최근 트렌드와 수치 데이터 3개 |
| community | 커뮤니티 이야기 | 커뮤니티 화제 이야기 2~3개 |
| tips | 이번 주의 팁 | 실용적인 팁 2~3개 |
| tech | 기술 업데이트 | 기술 개발 진행 상황 |
| market | 시장 동향 | 시장 데이터와 동향 |

**자동 참고 데이터:**
- news 섹션 → `data/naver_news_*.json`, `data/web_search_*.json`
- trends 섹션 → `data/naver_datalab_*.json`, `data/public_data_*.json`
- community 섹션 → `data/daum_cafe_*.json`, `data/leet_survey_*.json`
- market 섹션 → `data/kr_stock_*.json`, `data/ecos_macro_*.json`

**예시:**
- `action="build", topic="LEET 입시"` → 주간 LEET 뉴스레터 자동 생성 (4개 섹션)
- `action="build", period="monthly", topic="투자", sections="news,market,tips"` → 월간 투자 뉴스레터 (3개 섹션)

### action=preview (뉴스레터 미리보기)
```
action="preview", newsletter_id="newsletter_weekly_2026-02-19"
```
- 기존에 생성된 뉴스레터를 불러와 미리보기합니다
- newsletter_id를 지정하지 않으면 가장 최근 뉴스레터를 표시합니다

**예시:**
- `action="preview"` → 가장 최근 생성된 뉴스레터 표시

### action=templates (템플릿 목록)
```
action="templates"
```
- 사용 가능한 뉴스레터 기간 유형, 섹션 목록, 사용 예시를 보여줍니다
- 기존에 생성된 뉴스레터 목록도 최근 10개까지 표시합니다

## 이 도구를 쓰는 에이전트들

### 1. CPO 출판기록처장 (cpo_manager)
**언제 쓰나?** 정기 뉴스레터 발행 시, 출판 콘텐츠 기획 시
**어떻게 쓰나?**
- build로 주간/월간 뉴스레터 자동 생성
- preview로 생성된 뉴스레터 검토
- 편집 필요 시 콘텐츠편집 Specialist에게 수정 지시
- 최종본을 email_sender 도구로 발송

**실전 시나리오:**
> CEO가 "이번 주 뉴스레터 만들어줘" 라고 하면:
> 1. `action="build", topic="LEET 입시"` 로 뉴스레터 자동 생성
> 2. 생성된 품질 검토 결과 확인 (점수 8/10 이상이면 OK)
> 3. 필요시 editor_specialist에게 수정 요청
> 4. CEO에게 최종본 보고 후 email_sender로 발송

### 2. 회사연대기 Specialist (chronicle_specialist)
**언제 쓰나?** 회사 성장 이야기를 뉴스레터 형태로 공유할 때
**어떻게 쓰나?**
- build로 tech 섹션 중심의 뉴스레터 생성
- 회사 연대기/빌딩로그 내용을 뉴스레터에 포함

### 3. 콘텐츠편집 Specialist (editor_specialist)
**언제 쓰나?** 생성된 뉴스레터의 문장/구조를 다듬을 때
**어떻게 쓰나?**
- preview로 뉴스레터 내용 확인
- 가독성 개선, 용어 통일, 문장 다듬기
- 최종 편집본을 CPO에게 보고

## 주의사항
- 생성된 뉴스레터는 `data/newsletters/` 폴더에 마크다운(.md)과 HTML(.html) 두 파일로 저장됩니다
- data/ 폴더에 관련 데이터 파일이 있으면 더 정확한 뉴스레터가 생성됩니다 (없어도 AI가 자체 생성)
- AI가 생성한 내용이므로 실제 최신 뉴스와 다를 수 있음 — 발행 전 사실 확인(fact-check) 권장
- HTML 변환은 간단한 규칙 기반이므로, 복잡한 레이아웃은 지원하지 않음
- 뉴스레터 ID는 `newsletter_{period}_{날짜}` 형식으로 자동 생성됩니다
