# CORTHEX HQ - Claude 작업 규칙

## 프로젝트 정보
- 저장소: https://github.com/kodonghui/CORTHEX_HQ
- 소유자: kodonghui (비개발자 CEO)
- 언어: 한국어로 소통

## 소통 규칙 (최우선 규칙 — 반드시 지킬 것)
- CEO는 비개발자다. 모든 대화에서 아래 규칙을 예외 없이 지킬 것
- **구체적으로**: 추상적인 말 금지. "최적화했습니다" (X) → "페이지 로딩 속도를 3초에서 1초로 줄였습니다" (O)
- **자세하게**: 생략하지 말 것. 뭘 했는지, 왜 했는지, 결과가 어떤지 다 말할 것
- **이해하기 쉽게**: 초등학생도 알아들을 수 있는 수준으로 말할 것. 전문 용어를 쓸 때는 반드시 괄호 안에 쉬운 설명을 붙일 것 (예: "커밋(저장)", "브랜치(작업 공간)")
- **구조적으로**: 장문일 때는 반드시 제목, 번호 매기기, 표, 구분선 등을 써서 정리할 것. 글 덩어리로 주지 말 것
- **한국어로**: 모든 대화, 질문, 도구 사용 권한 요청 메시지는 **한국어**로 할 것. "grep in?"(X) → "이 폴더에서 검색하시겠습니까?"(O)
- 무엇을 왜 하는지 먼저 설명하고, 그다음 실행할 것
- 작업 결과를 보고할 때는 "뭘 했는지 → 왜 했는지 → 현재 상태 → 다음에 할 일" 순서로 정리할 것
- 존댓말로 할것
- **뻔한 질문 금지**: 당연히 해야 하는 것을 CEO에게 물어보지 말 것. "커밋할까요?", "배포할까요?", "푸시할까요?" 같은 질문은 하지 말고 바로 실행할 것. CEO의 시간을 아낄 것
- **소신 있게 의견 제시 (예스맨 금지)**: CEO가 "A 해줘"라고 해도, B가 더 낫다고 판단하면 반드시 먼저 말할 것
  - 형식: "A 대신 B를 추천합니다. 이유: [구체적 이유]. A로 진행하시겠습니까?" → CEO가 결정
  - 단순 실행자가 아니라 **기술 파트너**로 행동할 것. "시키는 대로만" 하는 것은 CEO에게 도움이 안 됨
  - 예: CEO가 "패턴 번호로 정리해줘" → "번호보다 카테고리 분류가 더 낫습니다. 이유: 나중에 패턴 추가 시 번호 안 바뀜. 카테고리로 할까요?" 이렇게 말할 것
  - 단, CEO가 최종 결정권자. 내 의견 말한 후 CEO가 원래 방식 고집하면 그대로 따를 것
- **중복/불필요한 것은 내 판단으로 정리**: CEO가 모든 세부사항을 결정할 필요 없음. 명백히 중복인 내용, 더 나은 구조 등은 내가 판단해서 정리하고 "이렇게 정리했습니다" 보고만 할 것
- **"로컬에서 확인" 금지**: 이 프로젝트는 Oracle Cloud 서버에 배포되어 있음. 접속 주소: `http://corthex-hq.com` (도메인, 권장) 또는 IP 직접 접속 (GitHub Secrets `SERVER_IP_ARM` 참조). "로컬에서 확인해보세요" 같은 말은 절대 하지 말 것. 확인은 항상 서버에서. 작업 완료 = 커밋 + 푸시 + 배포 + 서버에서 확인까지 끝낸 것

## Git 작업 규칙
- 깃허브의 Claude.md를 매번 반드시 참고할것
- 작업 중간에도 수시로 커밋 + 푸시할 것 (중간 저장)
- 작업이 완전히 끝났을 때, 마지막 커밋 메시지에 반드시 [완료] 를 포함할 것
  - 예: "feat: 로그인 기능 추가 [완료]"
  - [완료]가 있어야 자동 머지가 작동함. 없으면 PR만 만들고 머지는 안 함
- 브랜치명은 반드시 claude/ 로 시작할 것 (자동 머지 트리거 조건)
- 브랜치 작업 후 main에 합치는 것까지 완료해야 "작업 끝"으로 간주

## UI/UX 규칙
- **언어**: 모든 UI 텍스트는 **한국어**로 작성
- **시간대**: `Asia/Seoul` (KST, UTC+9) 기준
- **프레임워크**: Tailwind CSS + Alpine.js (CDN)
- **디자인 시스템**: `hq-*` 커스텀 컬러 토큰 사용

## 하드코딩 금지 규칙 (매우 중요!)
- **모델명, 에이전트 목록, 도구 목록 등을 코드에 직접 쓰지 말 것!**
  - ❌ 나쁜 예: `mini_server.py`에 `model_name: "claude-haiku-4-5-20251001"` 직접 입력
  - ✅ 좋은 예: `config/agents.yaml`에서 읽어서 사용
- **모델명 정의는 딱 2곳만**:
  - `config/agents.yaml` — 에이전트별 모델
  - `config/models.yaml` — 사용 가능한 모델 목록 + 가격
- **mini_server.py, ai_handler.py, index.html에 모델명 문자열을 직접 쓰면 안 됨**
  - 설정 파일(yaml)에서 읽거나, 파일 상단에 상수로 한 번만 정의하고 참조할 것
  - 예: `DEFAULT_MODEL = _load_config("models")["default"]` 이런 식으로
- **새 모델 추가/변경 시 체크리스트** (이전 사고에서 배운 교훈):
  1. `config/agents.yaml` 수정
  2. `config/models.yaml` 수정
  3. `python config/yaml2json.py` 실행 (JSON 재생성)
  4. `mini_server.py`의 AGENTS 리스트가 yaml과 동기화되는지 확인
  5. `mini_server.py`의 `get_available_models()` 함수 확인
  6. `mini_server.py`의 `_TG_MODELS` (텔레그램 모델 목록) 확인
  7. `ai_handler.py`의 `_PRICING` 가격표 확인
  8. `ai_handler.py`의 기본값/폴백 모델 확인
  9. `index.html`의 모델 표시명 매핑 확인
  10. `index.html`의 추론 레벨 매핑 확인
- **과거 사고**: 2026-02-18에 agents.yaml만 바꾸고 나머지 9곳을 안 바꿔서 Sonnet 4.6이 어디에도 반영 안 된 사건 발생. 4개 파일 60+곳이 구버전으로 남아있었음

## 실제 존재하는 모델명 (정확한 목록 — 이걸 기준으로 쓸 것!)
- **절대 규칙**: 아래 목록에 없는 모델명을 코드에 쓰면 API 오류 발생. "있을 것 같은" 모델명 절대 지어내지 말 것!
- **과거 사고**: QA-1 에이전트가 존재하지 않는 `claude-haiku-4-6`을 만들어내서 10곳에 심은 사건 발생 (2026-02-18)

| 모델 ID (코드에 쓰는 정확한 문자열) | 표시명 | 용도 |
|---|---|---|
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | 기본 (대부분 에이전트) |
| `claude-opus-4-6` | Claude Opus 4.6 | 최고급 (CLO, CSO) |
| `claude-haiku-4-5-20251001` | Claude Haiku 4.5 | 경량 Anthropic |
| `gpt-5.2-pro` | GPT-5.2 Pro | CIO (투자분석처장) |
| `gpt-5.2` | GPT-5.2 | 투자 분석가들 |
| `gpt-5` | GPT-5 | 일반 OpenAI |
| `gpt-5-mini` | GPT-5 Mini | 경량 OpenAI |
| `gemini-3-pro-preview` | Gemini 3.0 Pro | CMO, 콘텐츠, 설문 |
| `gemini-2.5-pro` | Gemini 2.5 Pro | Gemini 고급 |
| `gemini-2.5-flash` | Gemini 2.5 Flash | 경량 Gemini |

- ⚠️ **Haiku 4.6은 존재하지 않는다** — 절대 `claude-haiku-4-6`이라고 쓰지 말 것
- ⚠️ **GPT-4o는 구버전** — 절대 `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini`라고 쓰지 말 것

## 전수검사 프로토콜 (반드시 따를 것!)

### 전수검사란?
- **전수검사 ≠ grep 키워드 검색** — 키워드 검색만 하고 "이상 없음" 선언하면 안 됨
- **전수검사 = 파일을 Read 도구로 처음부터 끝까지 청크(조각)로 나눠서 전부 읽고, 각 함수/로직을 직접 이해하며 검토**
- grep은 "어디 있는지 찾기"용. 실제 검사는 반드시 Read로 읽어야 함

### 전수검사 단계별 프로토콜

**1단계: 파일 전체 읽기 (건너뛰기 금지)**
- 파일을 Read 도구로 처음부터 끝까지 여러 번 나눠서 전부 읽을 것
- 마지막 줄까지 다 읽었는지 확인. 중간에 멈추면 안 됨

**2단계: 함수별 입출력 검증**
- 각 API 함수가 받는 입력 형식이 실제 SDK 규격과 맞는지 확인
  - 예: OpenAI 파일 업로드는 `("파일명.jsonl", bytes)` 튜플이어야 함 — `bytes`만 쓰면 오류
  - 예: Anthropic 배치 결과는 `async for result in client.messages.batches.results(...)` — `await` 두 번 쓰면 오류
- 함수 호출 결과를 사용하는 곳까지 추적 (호출만 보지 말고 결과 처리까지 봐야 함)

**3단계: 모델명 검증 (위 "실제 존재하는 모델명" 목록과 대조)**
- 코드에서 발견한 모델명을 위 목록과 하나씩 대조할 것
- 목록에 없는 모델명 발견 시 → **절대 임의로 "최신버전"으로 업그레이드하지 말 것**
  - 틀린 예: `claude-haiku-4-5-20251001`을 보고 "haiku 4.6이 더 최신이겠지"라고 바꾸는 것
  - 올바른 행동: 위 목록에 `claude-haiku-4-5-20251001`이 있으면 그게 올바른 것임

**4단계: 중복/누락 확인**
- 같은 API 엔드포인트가 두 번 정의됐는지 확인 (FastAPI는 두 번째 것을 무시함)
- 함수가 return 없이 끝나는 곳 없는지 확인
- async 함수에서 await 빠진 곳, await 두 번 쓴 곳 확인

**5단계: 수정 전 반드시 확인**
- 수정하기 전에 해당 코드가 다른 곳에서 어떻게 호출되는지 추적
- 수정 후 grep으로 구버전 문자열이 0건인지 반드시 검증

### 팀 에이전트 전수검사 규칙
- **파일 담당 분리**: 같은 파일을 두 에이전트가 동시에 수정하면 충돌 — 파일마다 담당자 1명만
- **모델명 정보 소스**: 반드시 이 CLAUDE.md의 "실제 존재하는 모델명" 표를 먼저 읽고 작업 시작
- **추측 금지**: 모델명, API 파라미터 형식 등을 "아마 이럴 것 같다"고 추측해서 쓰면 안 됨
  - 모르면 CLAUDE.md를 먼저 읽거나 팀장에게 물어볼 것
- **수정 완료 선언 조건**: grep으로 구버전/잘못된 값이 0건임을 확인한 후에만 "완료" 보고

### 전수검사 팀 편성 — Claude의 판단 기준 (경험 기반)

#### 1단계: 작업 범위 파악 (팀 편성 전 반드시 실행)

팀 구성 전, 나(팀장)가 먼저 아래를 파악한다:
```
1. 수정 대상 파일 목록 → Glob + Grep으로 빠르게 확인
2. 각 파일 줄 수 → 줄 수에 따라 서브에이전트 수 결정
3. 도메인(기능 영역) 수 → 영역마다 전담 배정
```

#### 2단계: 팀원 수 결정 공식

CEO가 인원수 미지정 시 내가 판단. CEO 지정이 항상 우선.

| 작업 규모 | 팀원 수 | 이유 |
|----------|--------|------|
| 단일 버그 수정 (파일 1~2개) | 1~2명 + QA | 팀 오버헤드가 더 큼 |
| 기능 영역 점검 (예: 배치 시스템만) | 3~5명 + QA | 관련 파일들 분산 처리 |
| 전체 코드베이스 전수검사 | **파일 수 + 주요 도메인 수** = 보통 10~15명 | 파일마다 1명이 최소 단위 |
| 도구 154개 개별 검사 | 20~30명도 투입 가능 | 도구 그룹별 분산 |

#### 3단계: 서브에이전트 수 결정 — 파일 크기 기준

팀원마다 서브에이전트(Explore 타입)를 붙여서 파일 병렬 읽기. 내 경험상 가장 효과적인 기준:

| 파일 크기 | 서브에이전트 수 | 각 서브에이전트 담당 구간 |
|----------|--------------|----------------------|
| ~500줄 | 2명 | 절반씩 |
| 500~2000줄 | 3명 | 3등분 |
| 2000~5000줄 | 4명 | 4등분 |
| 5000줄 이상 (index.html 8000줄, mini_server.py 7000줄) | **5명** | 1600줄씩 동시 읽기 |

→ 5명이 동시에 읽으면 8000줄도 각자 1600줄씩 처리. 순차 읽기 대비 5배 빠름.

#### 4단계: CORTHEX HQ 전체 전수검사 기준 팀 편성표

파일별 담당 1명 고정 (같은 파일 두 명 → 충돌). 이게 제일 중요한 규칙.

| 팀원 | 담당 파일 (이 파일만 수정) | 서브에이전트 수 | 핵심 검사 항목 |
|------|--------------------------|--------------|--------------|
| **FE** | `web/templates/index.html` (8000줄) | **5명** | 하드코딩 배열, SNS 연결 상태, 배치 탭, 작전현황, 사령관실, 다크모드 opacity |
| **BE** | `web/mini_server.py` (7000줄) | **5명** | API 중복 정의, 에이전트 목록, 배치 엔드포인트, async/await |
| **AI** | `web/ai_handler.py` + `src/llm/` (~3000줄) | **4명** | 배치 SDK 형식(OpenAI 튜플, Anthropic async for), 모델명, _PRICING |
| **TG** | `src/telegram/` (~1000줄) | **3명** | 명령어 처리, 배치 연동, /result /cancel /models 구현 여부 |
| **AGENT** | `src/core/` (~2000줄) | **3명** | soul DB 저장 여부, quality_gate, 도구 루프 최대 5회 |
| **TOOL** | `src/tools/` (파일 수십 개) | **4명** (도구 그룹별 분담) | 도구 스키마 일치, Instagram API, Selenium 설정 |
| **SNS** | `src/integrations/` (~1500줄) | **3명** | SNS 발행 로직, 환경변수 체크, Tistory 처리 |
| **CONFIG** | `config/` (yaml 파일들) | **2명** | 모델명 목록, yaml2json.py 변환 목록 완전성 |
| **DEVOPS** | `.github/workflows/` (~300줄) | **2명** | git fetch+reset 사용 여부, 환경변수 전달, Selenium 설치 |
| **QA** | 전체 (읽기만, 수정 없음) | **3명** | 금지 모델명 grep 0건 확인, 하드코딩 잔재, 결과 검증 |

→ 총: 팀장 1 + 팀원 10 + 서브에이전트 34 = **45개 에이전트**

#### 5단계: 팀원 역할 분리 — 팀장 vs 팀원

**팀장(나)이 하는 일:**
- 팀 편성 + spawn (한 번에 전원 동시 run_in_background=true)
- CLAUDE.md 업데이트 (팀원들이 작업하는 동안 병행)
- 팀원 보고 수신 + 충돌 조정
- 최종 커밋/푸시/배포

**팀원이 하는 일:**
1. 서브에이전트 먼저 spawn (담당 파일 구간 나눠서 병렬 읽기)
2. 서브에이전트 결과 받으면 → 내가 직접 수정 실행
3. 수정 후 grep으로 구버전 0건 확인
4. SendMessage로 팀장에게 보고 (발견 버그 목록 + 수정 내용)

**팀원 spawn 시 프롬프트에 반드시 포함:**
- 담당 파일 명시 + "이 파일만 수정" 강조
- 서브에이전트 몇 명, 어떤 구간 담당하는지 구체적으로
- 검사 항목 상세 목록
- 허용/금지 모델명 목록 (CLAUDE.md에서 복사)
- 작업 경로 절대경로
- "완료 후 SendMessage로 팀장에게 보고" 지시

### 전수검사에서 쌓인 교훈들 (카테고리별 — 번호 없음, 추가 시 해당 카테고리 아래에 줄 추가)

#### 배포/서버
- `git pull` 대신 반드시 `git fetch + git reset --hard` 사용. pull은 충돌 시 조용히 실패하고 계속 진행됨
- 배포 성공이어도 Actions 로그 전체 확인 필수. 중간 에러가 있어도 최종 결과는 "success"일 수 있음
- 새 .yaml 파일 추가 시 yaml2json.py 변환 목록에 반드시 같이 추가. 세트로 움직임

#### API 설계 (FastAPI)
- 같은 경로 엔드포인트 중복 정의 시 FastAPI는 두 번째를 무시 → mini_server.py에 새 API 추가 전 grep으로 중복 확인
- 서버 API 응답 구조와 프론트엔드 접근 코드는 반드시 동시에 확인. 서버가 `{"instagram": {...}}` 반환하는데 프론트가 `sns.oauthStatus.platforms`로 접근하면 전부 깨짐
- async/await 빠진 곳, await 두 번 쓴 곳 — FastAPI 전수검사 시 반드시 확인

#### 배치 시스템 (Batch)
- OpenAI file 업로드: `file=bytes_data` → TypeError. 올바른 형식: `file=("batch.jsonl", bytes_data)` 튜플
- Anthropic batch results: `await await client.messages.batches.results(...)` → TypeError. async for로만 순회
- 배치 오류는 로그에만 남고 사용자에게는 "실패"로만 표시 → SDK 공식 문서 형식 반드시 확인

#### 하드코딩/중복
- 에이전트 목록, 플랫폼 목록 등 배열이 여러 파일에 하드코딩되면 한 곳만 바꾸고 나머지를 놓침 → 단일 소스(yaml)에서 동적으로 읽어야 함
- 설치/추가 작업 전 기존 파일 먼저 확인. 예: `grep -i selenium requirements.txt`

#### 모델명
- AI 에이전트가 "있을 것 같은" 모델명을 지어냄 (claude-haiku-4-6 사건) → CLAUDE.md의 "실제 존재하는 모델명" 표가 절대 기준

#### 팀 작업
- 같은 파일을 두 팀원이 수정하면 나중에 수정한 쪽이 먼저 수정한 내용을 덮어씀 → 파일마다 담당자 1명만

#### CSS/프론트엔드
- 콘텐츠 있는 요소에 `opacity` 애니메이션 직접 걸면 글자/카드 전부 투명해짐 → 반드시 `::before` 가상 요소로 분리

### 전수검사 시작 전 체크리스트 (팀장 실행)

**팀 spawn 전 반드시 확인**
1. `docs/project-status.md` 읽기 — 현재 상태 파악
2. `docs/updates/` 최근 2~3개 파일 읽기 — 이전 작업 맥락
3. 각 팀원에게 **파일 담당 명확히 배정** — 같은 파일 두 명 배정 금지
4. 팀원 spawn 프롬프트에 반드시 포함:
   - 담당 파일 명시
   - 서브에이전트 3명 활용 방법
   - 허용/금지 모델명 목록
   - 작업 완료 후 SendMessage 보고 지시

### 전수검사 완료 후 체크리스트 (팀장 실행)

**모든 팀원 보고 받은 후**
1. QA 팀원의 금지 모델명 0건 확인 결과 확인
2. 각 팀원이 수정한 내용 취합
3. CLAUDE.md 업데이트 (이번에 발견한 새 패턴 추가)
4. `config/yaml2json.py` 실행 (JSON 재생성)
5. 커밋 + 푸시 + 배포 ([완료] 태그 포함)
6. `docs/updates/YYYY-MM-DD_작업요약.md` 작성
7. `docs/project-status.md` 갱신
8. CEO에게 빌드 번호 확인 체크리스트 표 제공

## 데이터 저장 규칙 (SQLite DB)
- **웹에서 사용자가 저장/수정/삭제하는 모든 데이터는 반드시 SQLite DB(`settings` 테이블)에 저장할 것**
  - 프리셋, 예약, 워크플로우, 메모리, 피드백, 예산, 에이전트 설정, 품질 검수 기준, 에이전트 소울 등 전부 포함
  - JSON 파일(`data/*.json`)에 저장하면 안 됨 — 배포(`git reset --hard`) 시 날아감
- **저장 방법**: `db.py`의 `save_setting(key, value)` / `load_setting(key, default)` 사용
  - `value`는 자동으로 JSON 직렬화됨 (dict, list, str 등 아무거나 가능)
  - 예: `save_setting("presets", [{"name": "기본", ...}])` → DB에 영구 저장
- **기존 JSON 데이터 자동 마이그레이션**: `_load_data(name)`은 DB를 먼저 확인하고, 없으면 JSON 파일에서 읽어서 DB로 자동 이전함
- **DB 위치**: 서버에서는 `/home/ubuntu/corthex.db` (git 저장소 밖) → 배포해도 데이터 안 날아감
- **config 설정 저장**: `_save_config_file(name, data)` → `config_{name}` 키로 DB에 저장

## 업데이트 기록 규칙
- 모든 작업 내용을 `docs/updates/` 폴더에 기록할 것
- 파일명 형식: `YYYY-MM-DD_작업요약.md` (예: `2026-02-13_홈페이지-디자인.md`)
- 하나의 세션(작업)이 끝날 때마다 반드시 기록 파일을 만들 것
- 노션(Notion)에 바로 복붙할 수 있는 마크다운 형식으로 작성할 것
- 기록 파일에 반드시 포함할 내용:
  1. **작업 제목** — 한 줄로 뭘 했는지 (예: "홈페이지 메인 디자인 구현")
  2. **작업 날짜** — YYYY-MM-DD 형식
  3. **버전** — `X.YY.ZZZ` 형식의 버전 번호 (아래 "버전 번호 규칙" 참고)
  4. **작업 브랜치** — 어떤 브랜치에서 작업했는지 (예: claude/design-homepage-ui-e96Bb)
  5. **변경 사항 요약** — 뭘 바꿨는지 비개발자도 알 수 있게 쉽게 설명
     - 새로 만든 파일, 수정한 파일 목록 포함
     - 각 파일이 뭐 하는 파일인지 괄호로 설명 (예: `index.html (홈페이지 메인 화면)`)
  6. **현재 상태** — 작업이 완료됐는지, 진행 중인지, 문제가 있는지
  7. **다음에 할 일** — 이 작업 이후에 해야 할 것들 (있으면)
- 전문 용어는 절대 그냥 쓰지 말고, 반드시 괄호 안에 쉬운 설명을 붙일 것
- CEO가 읽고 바로 이해할 수 있는 수준으로 작성할 것. 이해 못 하면 의미 없음

## 버전 번호 규칙
- **형식**: `X.YY.ZZZ` (예: `0.01.001`, `0.02.015`, `1.00.000`)
- **각 자리의 의미**:
  - `X` (메이저): 프로젝트의 큰 단계. 0 = 개발 중, 1 = 정식 출시
  - `YY` (마이너): 주요 기능 추가 시 올림 (예: 새 탭 추가, 새 시스템 구현)
  - `ZZZ` (패치): 버그 수정, 소소한 개선, 설정 변경 등 작은 변경 시 올림
- **현재 버전**: `3.01.000` (전수검사 + 모델 전면 개편 — ARM 24GB 서버, 154개 도구, 배치 체인)
- **버전 올리는 규칙**:
  - 새 탭, 새 시스템, 새 부서 추가 등 **큰 변경** → 마이너(YY) 올리고 패치(ZZZ) 000으로 리셋
  - 버그 수정, UI 개선, 설정 변경 등 **작은 변경** → 패치(ZZZ)만 올림
  - 정식 출시 시 → 메이저(X) 1로 올림
- **작업 파일에 기록**: 모든 `docs/updates/` 파일의 상단에 버전 번호 포함
- **project-status.md에도 현재 버전 기록**: "마지막 업데이트" 섹션에 현재 버전 포함
- **예시**:
  ```
  # 에이전트 스킬 표시 문제 해결

  ## 버전
  0.05.048

  ## 작업 날짜
  2026-02-15
  ```

## 빌드 번호 규칙 (배포 확인용)
- **목적**: 배포가 완료됐는지 확인하기 위해 빌드 번호 시스템 사용
- **빌드 번호란?**: GitHub Actions의 `deploy.yml` 워크플로우 실행 횟수 (예: 빌드 #38)
- **빌드 번호 소스는 오직 하나**: `deploy.yml`의 `${{ github.run_number }}`
  - `mini_server.py`는 빌드 번호를 자체 생성하지 않음 (로컬에서는 "dev"로 표시)
  - Git 커밋 개수(`git rev-list --count HEAD`)는 빌드 번호와 **무관함** (절대 사용하지 말 것)
- **빌드 번호는 사전에 알 수 없음**: 배포가 실행되어야 번호가 매겨짐
- **작업 완료 시 반드시 할 것**:
  1. `gh run list --workflow=deploy.yml --limit=1` 명령으로 최신 배포의 빌드 번호를 확인
  2. CEO에게 아래 형식으로 **확인 체크리스트 표**를 만들어 줄 것:
     - 이번 세션에서 뭘 바꿨는지, 웹 화면 어디서 확인할 수 있는지 한눈에 정리
     - CEO가 대화 위로 스크롤해서 찾아볼 필요 없게, 마지막에 모든 확인 사항을 모아서 보여줄 것
  3. `docs/project-status.md`를 최신 상태로 갱신
  4. 배포 완료 후 웹 화면 좌측 상단에서 빌드 번호 확인 가능 (http://corthex-hq.com)
- **빌드 번호 확인 방법**:
  - 웹 화면: 좌측 상단에 "빌드 #XX" 표시
  - 배포 상태 JSON: `http://corthex-hq.com/deploy-status.json` 접속
  - GitHub Actions: https://github.com/kodonghui/CORTHEX_HQ/actions 에서 "Deploy to Oracle Cloud Server" 실행 번호 확인
- **예시** (반드시 이 형식으로):
  ```
  ## 빌드 #56 배포 확인 체크리스트

  | # | 확인할 곳 | 확인할 내용 | 이전 | 이후 |
  |---|----------|-----------|------|------|
  | 1 | 좌측 상단 | 빌드 번호 | #55 | #56 |
  | 2 | 설정 > 품질 검수 | 부서별 검수 기준 7개 부서 표시 | 빈 화면 | 7개 부서 목록 |
  | 3 | 설정 > 품질 검수 | "(루브릭)" 텍스트 삭제됨 | "부서별 검수 기준 (루브릭)" | "부서별 검수 기준" |

  확인 방법: http://corthex-hq.com 접속 후 위 표대로 확인해주세요.
  안 바뀌었으면 Ctrl+Shift+R (강력 새로고침) 해보세요.
  ```

## 기억력 보완 규칙 (대화 맥락 유지)
- **세션 시작 시**:
  1. 반드시 `docs/project-status.md` 파일을 먼저 읽을 것. 이 파일에 프로젝트의 현재 상태가 적혀 있음
  2. `docs/updates/` 폴더의 **최근 파일 2~3개**도 읽을 것. 이 폴더에 매 작업의 상세 기록이 날짜별로 저장되어 있음
     - 파일명 형식: `YYYY-MM-DD_작업요약.md` → 날짜가 최신인 파일부터 읽으면 됨
     - 이 기록에는 뭘 왜 어떻게 했는지, 수정한 파일 목록, 현재 상태, 다음에 할 일이 적혀 있음
     - 이걸 읽으면 "이전 세션에서 무슨 작업을 했는지" 맥락을 바로 파악할 수 있음
- **작업 완료 시**: `docs/project-status.md` 파일을 최신 상태로 업데이트할 것
  - "현재 완료된 주요 기능", "진행 중인 작업", "다음에 할 일" 섹션을 갱신
- **대화가 길어질 때**: 중간중간 핵심 내용을 요약해서 대화에 다시 언급할 것
- **중요한 결정이 내려졌을 때**: `docs/project-status.md`의 "중요한 결정 사항" 섹션에 즉시 기록할 것
- 이 규칙의 목적: CEO와 대화 중에 클로드가 맥락을 잃어버리는 것을 방지하기 위함

## 서버 배포 규칙 (Oracle Cloud — ARM 24GB 서버)
- **서버 스펙**: ARM Ampere A1, 4코어 24GB RAM (Oracle Cloud 춘천 리전, 무료 Always Free)
- **서버 접속 정보**:
  - IP: GitHub Secrets `SERVER_IP_ARM`에 등록
  - SSH 키: GitHub Secrets `SERVER_SSH_KEY_ARM`에 등록
  - 사용자: `ubuntu`
- **도메인**: `corthex-hq.com` (2026-02-18 구매, Cloudflare 등록 — DNS: corthex-hq.com → 158.179.165.97)
- **HTTPS**: Let's Encrypt(무료 인증서) 설정됨 — deploy.yml에서 certbot 자동 설치. `http://` 접속 시 `https://`로 자동 리다이렉트. 최초 배포 1회에만 인증서 발급하고, 이후 배포마다 만료 전 자동 갱신. CERTBOT_EMAIL Secret 없어도 동작(--register-unsafely-without-email 폴백)
- **이전 서버 (폐기됨)**: `168.107.28.100` (1GB 마이크로 — 더 이상 사용 안 함)
- **자동 배포 흐름** (전체 과정):
  1. claude/ 브랜치에 [완료] 커밋 push
  2. `auto-merge-claude.yml`이 PR 생성 + main에 자동 머지
  3. 머지 성공 후 → `deploy.yml`을 **직접 실행(trigger)**시킴
  4. 새 서버에 SSH 접속 → `git fetch + git reset --hard` → 파일 복사 → 서버 재시작
  - **중요**: GitHub 보안 정책상, 워크플로우가 만든 push는 다른 워크플로우를 자동 실행시키지 않음. 그래서 auto-merge에서 `gh workflow run deploy.yml`로 직접 실행시키는 구조
  - **중요**: 서버에서 `git pull`을 쓰면 안 됨! 반드시 `git fetch + git reset --hard` 사용
- **워크플로우 파일**:
  - `.github/workflows/auto-merge-claude.yml` — 자동 머지 + 배포 트리거
  - `.github/workflows/deploy.yml` — 실제 서버 배포 (SSH로 접속해서 파일 복사)
- **수동 배포**: GitHub → Actions 탭 → "Deploy to Oracle Cloud Server" → "Run workflow" 버튼 클릭
- **주의사항**:
  - 서버 파일을 직접 수정하지 말 것 (GitHub에서 코드 수정 → 자동 배포가 정상 흐름)
  - 배포 실패 시 GitHub Actions 로그를 먼저 확인할 것
  - ARM 아키텍처(aarch64) — 대부분의 Python 패키지 호환됨
- **서버 디렉토리 구조**:
  - `/home/ubuntu/CORTHEX_HQ/` — git 저장소 (전체 코드)
  - `/home/ubuntu/CORTHEX_HQ/web/` — 백엔드 서버 (mini_server.py 실행됨)
  - `/home/ubuntu/CORTHEX_HQ/src/` — 도구 모듈, 에이전트 모듈 (100개+ 도구)
  - `/home/ubuntu/CORTHEX_HQ/config/` — 설정 파일 (agents.yaml, tools.yaml 등)
  - `/home/ubuntu/corthex.db` — SQLite DB (git 저장소 밖 → 배포해도 데이터 안 날아감)
  - `/home/ubuntu/corthex.env` — API 키 등 환경변수 (배포 시 자동 업데이트)
  - `/var/www/html/` — nginx가 서빙하는 정적 파일 (index.html)
- **서버 설정 파일 규칙 (중요!)**:
  - 배포 시 `config/yaml2json.py`가 YAML → JSON 자동 변환
  - **config/agents.yaml 또는 config/tools.yaml을 수정하면 자동 배포 후 JSON이 재생성됨** (별도 작업 불필요)
  - `deploy.yml` 안에 Python 코드를 직접 넣으면 YAML 들여쓰기 문제가 생김 → **반드시 별도 .py 파일로 분리**할 것

## 배포 트러블슈팅 (문제 해결 가이드)

### 배포 안 되는 흔한 원인들

| 증상 | 원인 | 해결 |
|------|------|------|
| 배포 성공인데 화면이 안 바뀜 | **브라우저 캐시** — 브라우저가 옛날 파일을 기억 | `Ctrl+Shift+R` (강력 새로고침) 또는 주소 뒤에 `?v=2` 붙이기 |
| 배포 성공인데 화면이 안 바뀜 (2) | **nginx 캐시** — 서버가 브라우저에 캐시 허용 | deploy.yml이 자동으로 nginx에 `no-cache` 헤더 설정 (2026-02-15 추가) |
| 배포 성공인데 화면이 안 바뀜 (3) | **서버 git pull 실패** — 이전 배포가 서버 파일을 수정해서 git pull이 충돌 에러를 냄 | `git pull` 대신 `git fetch + git reset --hard` 사용 (deploy.yml에 이미 반영됨). **Actions 로그에서 "error: Your local changes would be overwritten" 메시지가 있으면 이 문제** |
| GitHub Actions "success"인데 서버 접속 안됨 | **서버 다운** 또는 **방화벽 차단** | Oracle Cloud 콘솔에서 인스턴스 상태 확인 → Security List에서 포트 80 열려있는지 확인 |
| `pip 설치 실패` 경고 | PyYAML 패키지 설치 실패 | 무시 가능 (yaml 없이도 서버 동작함) |
| 빌드 번호가 `BUILD_NUMBER_PLACEHOLDER`로 표시 | HTML을 로컬에서 직접 열었음 (서버 아님) | 반드시 `http://corthex-hq.com`으로 접속해야 함. 로컬 파일을 브라우저로 열면 빌드 번호가 주입 안됨 |
| `https://` 접속 안 됨 (자물쇠 없음) | certbot 아직 실행 안 됨 | 배포 한 번 더 실행하면 자동 발급됨. 또는 GitHub → Actions → "Deploy to Oracle Cloud Server" → Run workflow. `CERTBOT_EMAIL` Secret 추가하면 더 좋음 |

### 배포 확인하는 3가지 방법
1. **웹 화면**: `http://corthex-hq.com` 접속 → 좌측 상단 "빌드 #XX" 확인
2. **배포 상태 JSON**: `http://corthex-hq.com/deploy-status.json` 직접 접속 → 빌드 번호와 시간 확인
3. **GitHub Actions**: https://github.com/kodonghui/CORTHEX_HQ/actions → "Deploy to Oracle Cloud Server" 워크플로우 확인

### 배포 흐름 상세 (디버깅용)
```
[코드 수정] → [git push] → [auto-merge.yml] → [PR 생성 + main 머지]
    → [deploy.yml 직접 실행] → [서버 SSH 접속]
    → [git fetch + git reset --hard] (⚠️ git pull 아님!)
    → [sed로 빌드번호 주입] → [/var/www/html/index.html 복사]
    → [corthex 서비스 재시작] → [deploy-status.json 생성]
```

### nginx 캐시 방지 (2026-02-15 추가)
- deploy.yml이 첫 배포 시 nginx 설정에 `Cache-Control: no-cache` 헤더를 자동 추가
- 이후 배포부터는 브라우저가 항상 최신 파일을 받아감
- 수동으로 확인: `curl -I http://corthex-hq.com` → `Cache-Control: no-cache` 헤더 있으면 정상

## 과거 사고 기록 (같은 실수 반복 금지!)

### 사고 1: 서버 배포 안 되는 문제 (2026-02-15)

- **증상**: 코드를 고치고 배포했는데, 서버에 아무 변화가 없음. 빌드 번호는 올라가지만 코드는 옛날 것 그대로
- **원인 (2가지가 겹침)**:
  1. `deploy.yml`이 서버에서 `git pull origin main`을 쓰고 있었음
  2. 그런데 이전 배포에서 `sed` 명령어가 `index.html`에 빌드 번호를 주입하면서 파일을 수정함
  3. 그래서 다음 배포 때 `git pull`이 "로컬 변경사항이 있어서 못 가져온다" 에러를 냄
  4. **git pull이 실패해도** 배포 스크립트가 계속 진행됨 → 옛날 코드로 빌드 번호만 새로 주입 → 겉보기엔 "배포 성공"이지만 실제로는 코드가 안 바뀜
- **해결**: `git pull` 대신 `git fetch origin main` + `git reset --hard origin/main` 사용
  - `git fetch`는 최신 코드를 다운만 받고
  - `git reset --hard`는 로컬 파일을 다운받은 코드로 **강제 덮어씌움** (로컬 변경사항 무시)
- **교훈**:
  - **deploy.yml에서 `git pull`은 절대 쓰지 말 것** → `git fetch + git reset --hard`만 사용
  - GitHub Actions 로그에서 "error" 문자열이 있는지 반드시 확인할 것
  - "배포 성공"이라고 뜨더라도 Actions 로그 전체를 확인해야 함 (중간에 에러가 있어도 최종 결과가 "success"일 수 있음)

### 사고 2: 다크모드에서 화면이 안 보이는 문제 (2026-02-15)

- **증상**: 다크모드에서 모든 글자, 카드, 버튼이 거의 안 보임. 색상을 아무리 바꿔도 안 나음
- **원인**: `.bg-grid` 클래스의 `gridPulse` 애니메이션 때문
  ```css
  /* ❌ 잘못된 코드 — 이렇게 하면 안 됨! */
  @keyframes gridPulse {
    0%, 100% { opacity: 0.03; }  /* 투명도 3% */
    50% { opacity: 0.06; }       /* 투명도 6% */
  }
  .bg-grid {
    background-image: 격자 무늬;
    animation: gridPulse 8s infinite;  /* ← 이게 문제! */
  }
  ```
  - CSS의 `opacity`는 **요소 전체**(배경 + 글자 + 자식 요소 전부)에 적용됨
  - 배경 무늬만 깜빡이게 하려던 의도였지만, 글자/카드/버튼까지 전부 투명도 3%가 되어 안 보임
  - `.bg-grid`가 12개 메인 콘텐츠 영역에 전부 사용되어 모든 탭이 영향받음
- **해결**: 격자 무늬를 `::before` 가상 요소로 분리
  ```css
  /* ✅ 올바른 코드 — 현재 적용된 방식 */
  .bg-grid { position: relative; }
  .bg-grid::before {
    content: ''; position: absolute; inset: 0;
    background-image: 격자 무늬;
    animation: gridPulse 8s infinite;  /* 가상 요소에만 적용 → 콘텐츠 영향 없음 */
    pointer-events: none; z-index: 0;
  }
  .bg-grid > * { position: relative; z-index: 1; }
  ```
- **교훈**:
  - **CSS `opacity` 애니메이션을 콘텐츠가 있는 요소에 직접 걸면 안 됨** → 반드시 `::before`/`::after` 가상 요소로 분리
  - 다크모드 문제가 생기면 색상보다 **투명도(opacity)부터 확인**할 것
  - `index.html`에서 `opacity`가 들어간 애니메이션을 수정할 때는 어떤 요소에 적용되는지 반드시 확인할 것

### 사고 3: 부서별 검수 기준이 안 뜨는 문제 (2026-02-15)

- **증상**: 설정 화면에서 "부서별 검수 기준" 섹션이 빈 칸으로 표시됨. 부서 목록이 하나도 안 나옴
- **원인 (2가지가 겹침)**:
  1. `mini_server.py`의 `/api/quality-rules` API가 빈 데이터(`{"model": "", "rubrics": {}}`)만 반환
  2. `config/yaml2json.py`가 `agents`와 `tools`만 JSON으로 변환하고, `quality_rules`는 변환 안 함
  3. 서버에 PyYAML이 없어서 YAML 파일을 직접 못 읽음 → JSON이 없으니 빈 설정 사용
  4. 프론트엔드는 `qualityRules.known_divisions` 배열로 부서 목록을 그리는데, 이 데이터가 없으니 아무것도 안 뜸
- **해결**:
  1. `mini_server.py`가 `_load_config("quality_rules")`로 설정 파일을 읽어서 `rules`, `rubrics`, `known_divisions`, `division_labels`를 반환하도록 수정
  2. `yaml2json.py`에 `quality_rules`도 변환 대상에 추가
- **교훈**:
  - **새 설정 파일(`.yaml`)을 추가하면 반드시 `yaml2json.py`의 변환 목록에도 추가할 것**
  - **미니서버 API가 빈 데이터를 반환하면 프론트엔드가 작동 안 함** → API 추가/수정 시 실제 데이터를 반환하는지 반드시 확인
  - 프론트엔드가 빈 화면이면 → 브라우저 개발자 도구(F12)에서 API 응답부터 확인할 것

## AI 도구 자동호출 규칙 (Function Calling)
- **ai_handler.py**의 `ask_ai()`가 `tools` + `tool_executor` 파라미터를 받아서 3개 프로바이더 모두 도구 자동호출 지원
- **도구 스키마**: `config/tools.yaml` (또는 `tools.json`)에서 `_load_tool_schemas()`로 로드
- **에이전트별 도구 제한**: `config/agents.yaml`의 `allowed_tools` 필드로 에이전트마다 사용 가능한 도구를 제한
  - CIO(투자분석): 투자 관련 도구만, CTO(기술개발): 기술 도구만
- **프로바이더별 차이**:
  - Anthropic: `tools` 파라미터 → `tool_use` 블록 처리
  - OpenAI: `tools` 파라미터 (function 포맷) → `tool_calls` 응답 처리
  - Google Gemini: `FunctionDeclaration` → `function_call` 파트 처리 (google-genai SDK 사용)
- **도구 실행**: `mini_server.py`의 `_call_agent()`에서 ToolPool을 통해 도구 실행
- **최대 루프**: 도구 호출 루프는 최대 5회 반복 (무한 루프 방지)

## 팀 에이전트 규칙 (Agent Teams)

### 기본 원칙
- **평소에는 팀 없이 일반 세션으로 작업** — 작은 작업에 팀은 낭비
- CEO가 **"팀으로 해줘"**, **"기본팀으로 해결해줘"** 라고 하면 아래 기본팀을 구성해서 작업
- CEO가 인원수를 직접 지정하면 그대로 따를 것 (예: "FE 2명, BE 1명으로 해줘")

### 팀 인원 원칙
- **인원 제한 없음** — 작업 규모에 따라 필요한 만큼 투입. 100명도 가능
- CEO가 인원수를 지정하면 그대로 따를 것
- 기본 가이드 (어디까지나 참고용, 제한 아님):

| 상황 | 참고 구성 |
|------|---------|
| 큰 기능 추가 (새 탭, 새 시스템) | FE + BE + QA (3명) |
| 이슈 5개 이상 한꺼번에 | 이슈 수에 맞게 자유롭게 구성 |
| 전체 코드 전수검사 | 파일/영역별로 분리해서 최대한 많이 투입 |

### 팀을 쓰지 않아도 되는 상황
- 버그 1~3개 수정
- 한 파일만 수정하는 작업
- 간단한 UI 수정

### 기본팀 (3명) — "팀으로 해줘" 하면 이 구성
| 팀원 | 코드명 | 담당 파일 | 역할 |
|------|--------|----------|------|
| 팀원1 | **FE** | index.html, CSS, Alpine.js | 화면, 디자인, 다크/밝은 모드, 레이아웃 |
| 팀원2 | **BE** | mini_server.py, db.py, src/tools/, config/*.yaml | API, DB, 도구, 서버 로직 |
| 팀원3 | **QA** | 전체 | 수정 결과 검증, 다크모드 체크, 파일 충돌 확인 |

### 확장 역할 (필요할 때만 추가)
| 코드명 | 담당 | 언제 추가? |
|--------|------|-----------|
| **TOOL** | src/tools/ 도구 개발, tools.yaml 스키마 | 새 도구 만들 때 |
| **DEVOPS** | deploy.yml, nginx, 서버 설정 | 배포/인프라 문제일 때 |
| **PLAN** | 구조 설계, 작업 순서 결정 | 큰 기능 기획할 때 |

### 서브에이전트 활용 규칙 (필수!)
- **모든 팀원은 서브에이전트(Task 도구)를 적극 활용할 것**
- 코드 탐색, 파일 검색, 구조 분석 같은 조사 작업은 서브에이전트에게 시킬 것
- 팀원 본인은 서브에이전트가 가져온 결과를 바탕으로 **판단 + 수정에 집중**
- 서브에이전트를 2개 이상 병렬로 돌려서 조사 시간을 단축할 것
- 예시:
  - FE 팀원 → 서브에이전트1: "다크모드 관련 CSS 찾아와" + 서브에이전트2: "Alpine.js 바인딩 목록 정리해와" → 결과 받고 수정
  - BE 팀원 → 서브에이전트1: "API 엔드포인트 목록 분석해와" + 서브에이전트2: "DB 스키마 확인해와" → 결과 받고 수정

### 팀 작업 효율 규칙
- **같은 파일을 두 팀원이 동시에 수정하지 말 것** — 충돌남. 팀장이 파일별로 담당을 명확히 배정할 것
- 팀원은 자기 담당 파일만 수정. 다른 팀원 담당 파일을 건드려야 하면 팀장에게 먼저 알릴 것
- 불필요한 탐색 금지 — 서브에이전트로 빠르게 조사하고, 바로 수정에 들어갈 것
- 작업 끝나면 팀장에게 즉시 보고. 놀고 있지 말고 다음 이슈 받을 것

## 환경 설정
- gh CLI가 없으면 세션 시작 시 설치: `(type gh > /dev/null 2>&1) || (curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null && sudo apt update && sudo apt install gh -y)`
