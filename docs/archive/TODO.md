# CORTHEX HQ - 전체 TODO (풀 구현 로드맵)

> **작성일**: 2026-02-15
> **전략**: Oracle Cloud ARM 서버 업그레이드 → `app.py` 풀 백엔드 전환 → 전 기능 활성화
> **현재 버전**: 0.09.001
> **현재 서버**: Oracle Cloud 168.107.28.100 (E2.1.Micro, 1GB RAM, 무료)
> **목표 서버**: Oracle Cloud A1.Flex ARM (4코어, 24GB RAM, 무료)

---

## 왜 서버를 업그레이드하나요?

지금 서버(1GB RAM)에서는 `arm_server.py` 1개 파일로 가볍게 돌리고 있습니다.
그런데 프로젝트에는 **이미 완성된 풀 백엔드(`app.py` + `src/` 160개 파일)**가 있습니다.

| 비교 | arm_server.py (지금) | app.py + src/ (풀 백엔드) |
|------|----------------------|--------------------------|
| 파일 수 | 1개 (1,707줄) | 160개+ (수만 줄) |
| AI 모델 | Anthropic만 | Anthropic + **OpenAI** |
| 에이전트 협업 | 단순 위임 | **Orchestrator** (멀티 에이전트 협업) |
| 예약 실행 | ❌ 저장만 | ✅ **cron 자동 실행** |
| 워크플로우 | ❌ "미지원" 에러 | ✅ **순차 실행 엔진** |
| 품질 검수 | ❌ 항상 0점 | ✅ **QualityGate** AI 자동 검수 |
| 리플레이 | ❌ 빈 데이터 | ✅ **실행 과정 추적** |
| 성능 통계 | ❌ 빈 화면 | ✅ **실시간 통계** |
| 전문 도구 | 없음 | **80개+** (주식분석, 차트, DART, 법률, 번역 등) |
| SNS 연동 | 플레이스홀더 | **OAuth + 실제 발행** (인스타, 유튜브 등) |
| WebSocket | 직접 관리 | **ConnectionManager** 클래스 |
| 작업 취소 | ❌ | ✅ WebSocket cancel 처리 |
| Git 자동 동기화 | ❌ | ✅ archive/output 자동 push |

**결론**: 서버만 키우면 이 모든 기능이 바로 살아납니다.

---

## Phase 6: Oracle Cloud ARM 서버 생성

> **목표**: 무료 ARM 서버(4코어 24GB)를 만들고, 기존 서버의 모든 것을 옮기기
> **난이도**: ★★★☆☆ (클라우드 콘솔 작업 + SSH 설정)
> **CEO가 해야 할 것**: Oracle Cloud 콘솔에서 ARM 인스턴스 생성 (아래 가이드 따라하기)

### 6-1. ARM 인스턴스 생성 (CEO가 직접)

Oracle Cloud는 ARM 서버를 **무료로** 줍니다 (Always Free Tier):
- CPU: **최대 4코어** (Ampere A1)
- RAM: **최대 24GB**
- 디스크: **최대 200GB**
- 네트워크: **월 10TB** 무료 트래픽

**생성 방법**:
1. [Oracle Cloud 콘솔](https://cloud.oracle.com) 로그인
2. 왼쪽 메뉴 → **컴퓨트** → **인스턴스** → **인스턴스 생성**
3. 설정:
   - 이름: `corthex-hq-arm`
   - 이미지: **Ubuntu 24.04** (Canonical)
   - Shape: **VM.Standard.A1.Flex** (Ampere, Always Free eligible)
   - OCPU: **4** / RAM: **24GB**
   - 부트 볼륨: **100GB**
   - 리전: 춘천(ap-chuncheon-1) — 기존 서버와 같은 리전
   - SSH 키: 기존 키 사용 또는 새로 생성
4. **생성** 클릭 → 2~3분 후 Public IP 부여됨

> ⚠️ "Out of capacity" 에러가 나면:
> - Shape을 **VM.Standard.A1.Flex 1 OCPU / 6GB**로 줄여서 먼저 만들기
> - 또는 다른 Availability Domain 선택
> - 30분~1시간 후 재시도 (ARM 재고는 수시로 변동)

### 6-2. 새 서버 초기 설정 (클로드가 작업)

```
아래 프롬프트를 클로드에게 주세요:

"새로 만든 ARM 서버에 CORTHEX HQ를 설치해줘.
서버 IP는 [새 IP 주소]이고, SSH 키는 GitHub Secrets의 SERVER_SSH_KEY야.
기존 서버(168.107.28.100)에서 SQLite DB 파일과 환경변수를 복사해와야 해."
```

설치할 것:
- Python 3.12+ (ubuntu 24.04 기본 포함)
- pip + venv (가상환경)
- nginx (웹서버)
- git
- PyYAML, anthropic, openai, python-telegram-bot, python-dotenv, pydantic
- uvicorn (FastAPI 서버)
- systemd 서비스 등록 (corthex.service)
- certbot (HTTPS용, Phase 12에서 활성화)

### 6-3. 데이터 마이그레이션

기존 서버(168.107.28.100)에서 복사해올 것:
| 파일 | 경로 | 설명 |
|------|------|------|
| SQLite DB | `/home/ubuntu/corthex.db` | 모든 메시지, 작업, 설정 데이터 |
| 환경변수 | `/home/ubuntu/corthex.env` | API 키들 (Anthropic, OpenAI, Telegram, Notion) |
| 설정 파일 | `/home/ubuntu/CORTHEX_HQ/config/*.json` | YAML→JSON 변환된 설정들 |

### 6-4. GitHub Secrets 업데이트

| Secret 이름 | 변경 내용 |
|-------------|----------|
| `SERVER_IP` | 새 ARM 서버 IP로 변경 |
| `SERVER_SSH_KEY` | 새 서버 SSH 키로 변경 (또는 기존 키 등록) |

### 6-5. deploy.yml 업데이트

```
아래 프롬프트를 클로드에게 주세요:

"deploy.yml을 ARM 서버용으로 업데이트해줘.
변경 사항:
1. app.py + src/ 폴더 전체를 서버에 배포
2. arm_server.py 대신 app.py를 uvicorn으로 실행
3. Python venv 사용 (시스템 Python 오염 방지)
4. pip install로 모든 의존성 설치 (requirements.txt 기반)
5. corthex.service가 app.py를 실행하도록 변경
6. 기존 빌드번호 주입 + nginx 캐시 방지 유지"
```

### 6-6. 기존 서버 유지/제거

- 새 서버가 안정적으로 동작하면 기존 E2 서버는 종료
- 또는 백업 서버로 유지 (무료이므로 비용 없음)

---

## Phase 7: 풀 백엔드 전환 (arm_server.py → app.py)

> **목표**: 서버에서 실제로 app.py를 돌리고, arm_server.py가 하던 모든 것이 유지되게 하기
> **난이도**: ★★★★☆ (코드 병합 필요)
> **핵심**: app.py가 arm_server.py의 SQLite DB 기능을 물려받아야 함

### 7-1. requirements.txt 생성

```
아래 프롬프트를 클로드에게 주세요:

"src/ 폴더의 모든 파일을 분석해서 필요한 pip 패키지를 전부 찾아내고,
requirements.txt를 만들어줘.
각 패키지 옆에 주석으로 어디서 쓰는지 적어줘."
```

이미 파악된 핵심 패키지:
| 패키지 | 용도 | 어디서 쓰나 |
|--------|------|-----------|
| `fastapi` | 웹 프레임워크 | app.py |
| `uvicorn` | 서버 실행기 | app.py 실행 |
| `anthropic` | Claude AI API | src/llm/anthropic_provider.py |
| `openai` | OpenAI API | src/llm/openai_provider.py |
| `pyyaml` | 설정 파일 읽기 | app.py, 각종 매니저 |
| `python-dotenv` | 환경변수 로드 | app.py |
| `pydantic` | 데이터 검증 | API 요청 모델 |
| `python-telegram-bot` | 텔레그램 봇 | src/telegram/ |
| `aiosqlite` | SQLite 비동기 | db.py (추가 필요할 수 있음) |
| `httpx` | HTTP 클라이언트 | src/tools/ 전반 |
| `beautifulsoup4` | 웹 스크래핑 | src/tools/naver_news.py 등 |
| `matplotlib` | 차트 생성 | src/tools/chart_generator.py |
| `pandas` | 데이터 분석 | src/tools/backtest_engine.py 등 |

### 7-2. app.py에 SQLite DB 통합

```
아래 프롬프트를 클로드에게 주세요:

"app.py가 arm_server.py의 SQLite DB(db.py)를 사용하도록 수정해줘.

현재 상황:
- app.py는 YAML/JSON 파일로 데이터를 저장함 (재배포하면 날아감)
- arm_server.py는 SQLite DB(db.py)로 영구 저장함 (재배포해도 유지)

해야 할 것:
1. app.py 시작 시 db.init_db() 호출
2. 대화 기록: orchestrator 결과를 db.save_message()로 저장
3. 작업 기록: task_store 대신 db.save_task() 사용 (또는 task_store가 DB를 백엔드로 사용)
4. 활동 로그: db.save_activity_log() 사용
5. 설정 데이터: 예약/워크플로우/프리셋/메모리/피드백을 db.save_setting()으로 저장
6. /api/conversation이 db.get_messages()에서 실제 대화 기록 반환

주의:
- src/core/의 매니저 클래스들(PresetManager, Scheduler 등)은 각자 YAML 파일을 읽는데,
  이것들도 DB에서 읽도록 수정하거나, 시작 시 DB→YAML 동기화 메커니즘 추가
- 기존 arm_server.py의 인증 시스템(비밀번호 해싱, 세션)도 유지
- settings 테이블의 key-value 구조 활용"
```

### 7-3. app.py 알려진 버그 수정

| 버그 | 위치 | 설명 |
|------|------|------|
| `sns_oauth_status()` 중복 선언 | app.py 1300행, 1624행 | 같은 이름의 함수가 2번 정의됨. 두 번째가 첫 번째를 덮어씀 |
| `_execute_command_for_api()` 미사용 | app.py 1376행 | 선언만 되고 어디서도 호출 안 함 |
| `_auto_sync_to_github()`에서 `git pull` 사용 | app.py 1564행 | CLAUDE.md 규칙 위반: git pull 금지 |

### 7-4. corthex.service 변경

```ini
# 기존 (arm_server.py)
ExecStart=/usr/bin/python3 -m uvicorn arm_server:app --host 0.0.0.0 --port 8000
WorkingDirectory=/home/ubuntu/CORTHEX_HQ/web

# 변경 후 (app.py + venv)
ExecStart=/home/ubuntu/CORTHEX_HQ/venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000
WorkingDirectory=/home/ubuntu/CORTHEX_HQ
EnvironmentFile=/home/ubuntu/corthex.env
```

### 7-5. 전환 후 확인 체크리스트

| # | 확인 항목 | 방법 |
|---|----------|------|
| 1 | 서버 정상 기동 | `http://[새IP]` 접속 → 빌드번호 표시 |
| 2 | 로그인 | 기존 비밀번호로 로그인 |
| 3 | AI 명령 | "안녕하세요" 입력 → 비서실장 답변 |
| 4 | 에이전트 위임 | "시장 분석해줘" → CSO 부서로 위임 |
| 5 | 텔레그램 봇 | 텔레그램에서 메시지 → 웹에 반영 |
| 6 | 예약 CRUD | 예약 만들기/수정/삭제 |
| 7 | 설정 저장 | 에이전트 소울 수정 → 저장 → 새로고침 → 유지 |
| 8 | 대화 유지 | AI 대화 → 새로고침 → 대화 유지 |

---

## Phase 8: 풀 백엔드로 해결되는 기능들 (자동 활성화)

> **목표**: app.py 전환만으로 바로 살아나는 기능들을 확인하고 프론트엔드와 연결
> **난이도**: ★★☆☆☆ (대부분 app.py에 이미 구현됨)

### 자동으로 살아나는 기능 목록

| # | 기능 | 이전 상태 | 전환 후 | 담당 모듈 |
|---|------|---------|---------|----------|
| 8-1 | **성능 탭** | 빈 화면 | 실시간 통계 | `src/core/performance.py` |
| 8-2 | **품질 검수** | 항상 0점 | AI 자동 검수 | `src/core/quality_gate.py` |
| 8-3 | **리플레이** | 빈 데이터 | 실행 과정 추적 | `src/core/replay.py` |
| 8-4 | **예약 자동 실행** | 저장만 됨 | cron 자동 실행 | `src/core/scheduler.py` |
| 8-5 | **워크플로우 실행** | "미지원" 에러 | 순차 실행 | `src/core/workflow.py` |
| 8-6 | **작업 취소** | 안 됨 | WebSocket cancel | `app.py` 1441행 |
| 8-7 | **에이전트 실시간 상태** | 항상 idle | working/done/idle | `ws_manager.py` + `app.py` |
| 8-8 | **OpenAI 모델** | 선택만 됨 | 실제 동작 | `src/llm/openai_provider.py` |
| 8-9 | **에이전트 협업** | 단순 위임 | Orchestrator 협업 | `src/core/orchestrator.py` |
| 8-10 | **전문 도구 80개+** | 없음 | 에이전트가 사용 가능 | `src/tools/` |
| 8-11 | **아카이브 자동 저장** | 수동 | 작업 완료 시 자동 | `app.py` _archive_agent_report() |
| 8-12 | **Git 자동 동기화** | 없음 | archive/output 자동 push | `app.py` _auto_sync_to_github() |

### 프론트엔드 수정이 필요한 것

```
아래 프롬프트를 클로드에게 주세요:

"app.py 전환 후 프론트엔드(index.html)에서 수정이 필요한 부분을 찾아서 고쳐줘:

1. commandInput 버그 (2509, 2513, 2517행)
   - 'commandInput' 변수가 정의 안 됨 → 'inputText'로 변경

2. /api/tools 이중 호출
   - init()에서 fetchTools()가 2번 호출됨 → 1번으로 줄이기

3. 수동 모드 모델 선택 UI
   - modelOverride 변수가 선언됐지만 UI에서 선택할 수 있는 드롭다운이 없음
   - 명령 입력창 옆에 모델 선택 드롭다운 추가

4. 비밀번호 변경 UI
   - /api/auth/change-password API는 있지만 화면에 UI 없음
   - 설정 탭에 비밀번호 변경 폼 추가

5. 활동 로그 필터 UI
   - activityLogFilter 변수가 선언됐지만 필터 UI 없음
   - (낮은 우선순위 — 나중에 해도 됨)"
```

---

## Phase 9: 외부 연동 활성화

> **목표**: API 키를 등록하고 외부 서비스 연동 실제로 작동시키기
> **난이도**: ★★★★☆ (코드는 있음, API 키 + 테스트 필요)
> **CEO가 해야 할 것**: API 키 발급 + GitHub Secrets 등록

### 9-1. OpenAI API 연동

`src/llm/openai_provider.py`가 이미 구현되어 있음. API 키만 넣으면 됨.

**CEO 할 일**:
1. [OpenAI Platform](https://platform.openai.com)에서 API 키 발급
2. GitHub → Settings → Secrets → `OPENAI_API_KEY` 등록
3. deploy.yml이 자동으로 서버 환경변수에 주입

**테스트**: 웹에서 수동모드 → GPT-4.5 선택 → "안녕하세요" → 답변 확인

### 9-2. 노션 API 연동

`src/tools/notion_api.py`가 구현되어 있음.

**CEO 할 일**:
1. [Notion Integrations](https://www.notion.so/my-integrations)에서 Internal Integration 생성
2. API 키를 GitHub Secrets → `NOTION_API_KEY` 등록
3. 연동할 노션 DB의 ID를 `NOTION_DB_ID`로 등록
4. 해당 노션 DB에 Integration 초대 (DB 우측 상단 ··· → 연결 → Integration 추가)

```
아래 프롬프트를 클로드에게 주세요:

"에이전트가 작업 완료 시 노션에 자동으로 보고서를 올리는 기능을 활성화해줘.
src/tools/notion_api.py가 이미 있으니 이걸 활용해서:
1. 작업 완료 시 → 노션 DB에 새 페이지 생성
2. 페이지 내용: 작업 제목, 담당 에이전트, 소요시간, 비용, 결과 요약
3. 실패해도 서버가 죽지 않게 try-except로 감싸기
NOTION_API_KEY가 없으면 조용히 건너뛰기."
```

### 9-3. SNS 연동 (인스타그램, 유튜브 등)

`src/tools/sns/` 폴더에 7개 플랫폼 퍼블리셔가 구현되어 있음:
- `instagram_publisher.py` — 사진/릴스 게시
- `youtube_publisher.py` — 동영상 업로드
- `linkedin_publisher.py` — LinkedIn 포스트
- `tistory_publisher.py` — 티스토리 블로그
- `naver_blog_publisher.py` — 네이버 블로그
- `naver_cafe_publisher.py` — 네이버 카페
- `daum_cafe_publisher.py` — 다음 카페

`oauth_manager.py`가 OAuth 흐름 관리, `webhook_receiver.py`가 콜백 수신.

**CEO 할 일** (인스타그램 예시):
1. [Meta Developer](https://developers.facebook.com)에서 앱 생성
2. Instagram Graph API 권한 추가
3. Client ID, Client Secret을 GitHub Secrets에 등록
4. OAuth 콜백 URL 설정: `http://[서버IP]/oauth/callback/instagram`

> ⚠️ SNS 연동은 각 플랫폼마다 개발자 계정 승인이 필요해서 시간이 걸립니다.
> 인스타그램 먼저 연동하고, 나머지는 순차적으로 하는 것을 추천합니다.

### 9-4. 텔레그램 봇 업그레이드

현재 `arm_server.py`의 텔레그램 봇은 기본 기능만 있음.
`src/telegram/` 폴더에 향상된 버전이 있음:
- `bot.py` — 양방향 브릿지 (웹↔텔레그램 실시간 연동)
- `bridge.py` — 에이전트 이벤트를 텔레그램으로 중계
- `notifier.py` — SNS 승인 요청 자동 알림
- `formatter.py` — 마크다운 서식 처리
- `auth.py` — 텔레그램 사용자 인증

```
아래 프롬프트를 클로드에게 주세요:

"app.py의 텔레그램 봇(src/telegram/)이 제대로 동작하는지 확인하고,
환경변수 TELEGRAM_ENABLED=1일 때 자동으로 시작되게 해줘.
corthex.env에 TELEGRAM_ENABLED=1 추가하고,
봇이 시작/실패할 때 서버 로그에 명확히 표시되게 해줘."
```

---

## Phase 10: 전문 도구 활성화 및 검증

> **목표**: `src/tools/`의 80개+ 전문 도구가 에이전트에게 제대로 연결되는지 확인
> **난이도**: ★★★☆☆ (코드는 있음, 테스트 + 외부 API 키 필요)

### 10-1. 도구 분류 및 상태 확인

```
아래 프롬프트를 클로드에게 주세요:

"src/tools/ 폴더의 모든 도구를 분석해서 3가지로 분류해줘:

1. **바로 사용 가능** — 외부 API 키 없이 동작하는 것
   (예: chart_generator, doc_converter, translator, token_counter 등)

2. **API 키 필요** — 외부 API 키를 등록해야 동작하는 것
   (예: dart_api, naver_datalab, kipris 등)

3. **수정 필요** — 코드가 미완성이거나 스텁(빈 함수)인 것

각 도구별로:
- 파일명, 기능 설명, 필요한 API 키, 어느 에이전트가 사용하는지
를 표로 정리해줘."
```

### 10-2. 부서별 도구 할당 확인

`config/tools.yaml`에 부서별 도구 할당이 정의되어 있음.
`config/agents.yaml`의 `allowed_tools` 필드와 매칭되는지 확인 필요.

### 10-3. 주요 도구 테스트

| 우선순위 | 도구 | 부서 | 테스트 방법 |
|----------|------|------|-----------|
| 높음 | `web_search.py` | 전체 | "삼성전자 최근 뉴스 검색해줘" |
| 높음 | `chart_generator.py` | CIO | "삼성전자 주가 차트 만들어줘" |
| 높음 | `naver_news.py` | 전체 | "오늘의 뉴스 요약해줘" |
| 중간 | `dart_api.py` | CIO | "삼성전자 최근 공시 확인해줘" |
| 중간 | `kr_stock.py` | CIO | "코스피 시황 분석해줘" |
| 중간 | `law_search.py` | CLO | "개인정보보호법 검색해줘" |
| 중간 | `contract_reviewer.py` | CLO | 계약서 파일 업로드 → 검토 |
| 낮음 | `backtest_engine.py` | CIO | 투자 전략 백테스트 |
| 낮음 | `competitor_monitor.py` | CSO | 경쟁사 모니터링 |

---

## Phase 11: 에이전트 소울 업그레이드 (29명)

> **목표**: 29명의 AI 에이전트에게 성격, 말투, 행동 규칙을 부여
> **난이도**: ★★☆☆☆ (프롬프트 작성 작업)
> **참고**: `docs/PROMPT-에이전트-소울-업그레이드.md`

```
아래 프롬프트를 클로드에게 주세요:

"docs/PROMPT-에이전트-소울-업그레이드.md를 읽고,
29명 에이전트의 소울 파일을 전부 업그레이드해줘.

각 에이전트마다:
1. 성격 (한 문장 캐릭터 설명)
2. 말투 (존댓말/반말, 말끝 특징, 자주 쓰는 표현)
3. 전문 분야 (뭘 잘하는지)
4. 금지사항 (뭘 하면 안 되는지)
5. 보고 형식 (결과를 어떻게 전달하는지)

을 포함해서 작성해줘.

부서별 에이전트 목록:
- 비서실: chief_of_staff(비서실장), relay_worker(총괄보좌관), report_worker(진행보좌관), schedule_worker(소통보좌관)
- CTO실: cto_manager(CTO), frontend(프론트), backend(백엔드), ai_model(AI모델), infra(인프라)
- CSO실: cso_manager(CSO), business_plan(사업기획), market_research(시장조사), financial_model(재무모델)
- CLO실: clo_manager(CLO), copyright(저작권), patent(특허)
- CMO실: cmo_manager(CMO), content(콘텐츠), community(커뮤니티), survey(설문)
- CIO실: cio_manager(CIO), stock_analysis(주식분석), market_analysis(시장분석), risk_management(리스크), technical_analysis(기술분석)
- CPO실: cpo_manager(CPO, 출판기록)"
```

---

## Phase 12: 프로덕션 레디 (안정화)

> **목표**: 실제 서비스로 쓸 수 있게 마무리
> **난이도**: ★★★☆☆

### 12-1. HTTPS 설정 (Let's Encrypt)

```
아래 프롬프트를 클로드에게 주세요:

"ARM 서버에 HTTPS를 설정해줘.
도메인이 없으면 IP로 접속하되, 나중에 도메인 연결할 준비를 해줘.
certbot + nginx 설정으로 자동 갱신되게 해줘."
```

### 12-2. 도메인 연결

CEO가 도메인(예: corthex.com)을 구매하면:
1. DNS A 레코드에 서버 IP 등록
2. nginx에 도메인 설정 추가
3. Let's Encrypt SSL 인증서 발급

### 12-3. 모니터링 및 알림

```
아래 프롬프트를 클로드에게 주세요:

"서버 모니터링 시스템을 만들어줘:
1. /api/health 엔드포인트가 서버 상태 반환 (이미 있음)
2. 매 5분마다 health 체크 → 실패 시 텔레그램으로 CEO에게 알림
3. 디스크 사용량 80% 이상 → 경고 알림
4. SQLite DB 크기 체크 → 500MB 이상 → 오래된 로그 자동 정리
5. 서버 메모리/CPU 사용량을 /api/system-stats에서 반환"
```

### 12-4. 자동 백업 시스템

```
아래 프롬프트를 클로드에게 주세요:

"SQLite DB 자동 백업 시스템을 만들어줘:
1. 매일 새벽 3시 cron으로 corthex.db를 백업
2. 백업 위치: /home/ubuntu/backups/corthex_YYYYMMDD.db
3. 7일 넘은 백업은 자동 삭제
4. 백업 성공/실패를 서버 로그에 기록"
```

---

## Phase 계획 요약 (타임라인)

```
Phase 6: ARM 서버 생성 ─────── CEO 클릭 작업 (30분)
    │
Phase 7: 풀 백엔드 전환 ────── 코드 병합 + 배포 (2-3 세션)
    │   ├── requirements.txt 생성
    │   ├── app.py에 SQLite DB 통합
    │   ├── 알려진 버그 수정
    │   ├── corthex.service 변경
    │   └── 전환 확인 테스트
    │
Phase 8: 기능 활성화 확인 ──── 대부분 자동 (1 세션)
    │   └── 프론트엔드 버그 수정
    │
Phase 9: 외부 연동 ────────── API 키 등록 + 테스트 (2-3 세션)
    │   ├── OpenAI 연동
    │   ├── 노션 연동
    │   ├── SNS 연동 (인스타 우선)
    │   └── 텔레그램 업그레이드
    │
Phase 10: 전문 도구 검증 ──── 부서별 테스트 (1-2 세션)
    │
Phase 11: 에이전트 소울 ───── 프롬프트 작업 (1 세션)
    │
Phase 12: 프로덕션 마무리 ─── HTTPS + 모니터링 (1 세션)
```

---

## 즉시 해결 가능한 프론트엔드 버그 (Phase 관계없이)

| # | 버그 | 위치 | 수정 방법 |
|---|------|------|----------|
| F1 | `commandInput` 변수 미정의 | index.html 2509, 2513, 2517행 | `commandInput` → `inputText` |
| F2 | `/api/tools` 이중 호출 | index.html init() | fetchTools() 호출 1회로 줄이기 |
| F3 | 미사용 상태 변수들 | index.html | `activityLogFilter`, `taskHistory.filterDateFrom/To` 등 — UI 연결 필요 또는 삭제 |

---

## 참고: 현재 정상 작동하는 기능 (건드리지 말 것)

| 기능 | 상태 |
|------|------|
| CEO 명령 → AI 답변 (웹/텔레그램) | ✅ 정상 |
| 비서실장 → 6개 부서 자동 위임 | ✅ 정상 |
| 모델 자동/수동 전환 | ✅ 정상 |
| 일일 예산 제한 ($7) | ✅ 정상 |
| 로그인/로그아웃 | ✅ 정상 |
| 에이전트 소울/모델 설정 저장 | ✅ 정상 |
| 품질검수 루브릭 설정 저장 | ✅ 정상 |
| 예약/워크플로우/지식파일 CRUD | ✅ 정상 (저장만, 실행은 Phase 8에서 활성화) |
| 작업 내역 검색/필터/북마크 | ✅ 정상 |
| 활동 로그 표시 | ✅ 정상 |
| 아카이브 목록/상세 | ✅ 정상 |
| 프리셋 저장/삭제 | ✅ 정상 |
| 에이전트 메모리 CRUD | ✅ 정상 |
| 피드백 (좋아요/싫어요) | ✅ 정상 |
| 대화 내보내기 (마크다운 다운로드) | ✅ 정상 |
| GitHub Actions 자동 배포 | ✅ 정상 |
| 텔레그램 봇 (실시간/배치 모드) | ✅ 정상 |
| 빌드 번호 표시 | ✅ 정상 |

---

## 미사용 코드 인벤토리 (src/ 전체)

### src/core/ — 핵심 엔진 (16개 모듈)
| 파일 | 기능 | Phase 8에서 활성화 |
|------|------|-------------------|
| `orchestrator.py` | 멀티 에이전트 협업 조율 | ✅ |
| `scheduler.py` | cron 기반 예약 자동 실행 | ✅ |
| `workflow.py` | 워크플로우 순차 실행 | ✅ |
| `replay.py` | 실행 과정 기록/재생 | ✅ |
| `performance.py` | 에이전트 성과 리포트 | ✅ |
| `quality_gate.py` | AI 산출물 품질 검수 | ✅ |
| `quality_rules_manager.py` | 검수 규칙 관리 | ✅ |
| `agent.py` | 에이전트 기본 클래스 | ✅ |
| `context.py` | 공유 컨텍스트 | ✅ |
| `registry.py` | 에이전트 등록부 | ✅ |
| `knowledge.py` | 지식 파일 관리 | ✅ |
| `memory.py` | 에이전트 장기 기억 | ✅ |
| `feedback.py` | CEO 피드백 관리 | ✅ |
| `task_store.py` | 작업 저장소 | ✅ |
| `budget.py` | 예산 관리 | ✅ |
| `auth.py` | 인증 관리 | ✅ |
| `preset.py` | 명령 프리셋 | ✅ |
| `report_saver.py` | 보고서 자동 저장 | ✅ |
| `git_sync.py` | Git 자동 동기화 | ✅ |

### src/llm/ — AI 모델 (6개 모듈)
| 파일 | 기능 | 활성화 시점 |
|------|------|-----------|
| `anthropic_provider.py` | Claude API | Phase 8 |
| `openai_provider.py` | OpenAI API | Phase 9 (API 키 필요) |
| `router.py` | 멀티 모델 라우팅 | Phase 8 |
| `batch_collector.py` | Batch API (50% 할인) | Phase 8 |
| `cost_tracker.py` | 비용 추적 | Phase 8 |
| `base.py` | 프로바이더 인터페이스 | Phase 8 |

### src/tools/ — 전문 도구 (50개+)
| 분류 | 도구들 | Phase |
|------|--------|-------|
| **투자/금융** | kr_stock, backtest_engine, dart_api, chart_generator, stock_screener, dividend_calendar, insider_tracker, financial_calculator, global_market_tool, ecos_macro | Phase 10 |
| **법률/IP** | law_search, contract_reviewer, patent_attorney, kipris, trademark_similarity, precedent_analyzer, law_change_monitor | Phase 10 |
| **마케팅/SNS** | hashtag_recommender, email_optimizer, email_sender, seo_analyzer, competitor_sns_monitor, app_review_scraper, naver_datalab, leet_survey | Phase 10 |
| **뉴스/검색** | naver_news, web_search, real_web_search, scholar_scraper | Phase 10 |
| **문서/변환** | doc_converter, pdf_parser, report_generator, spreadsheet_tool, meeting_formatter, newsletter_builder | Phase 10 |
| **개발/인프라** | code_quality, api_benchmark, security_scanner, log_analyzer, github_tool, uptime_monitor | Phase 10 |
| **AI/유틸** | translator, audio_transcriber, image_generator, embedding_tool, vector_knowledge, token_counter, sentiment_analyzer, prompt_tester, designer | Phase 10 |
| **플랫폼** | naver_place_scraper, platform_market_scraper, public_data, subsidy_finder, tax_accountant, daum_cafe, calendar_tool | Phase 10 |

### src/tools/sns/ — SNS 퍼블리셔 (11개)
| 파일 | 플랫폼 | Phase |
|------|--------|-------|
| `instagram_publisher.py` | 인스타그램 | Phase 9 |
| `youtube_publisher.py` | 유튜브 | Phase 9 |
| `linkedin_publisher.py` | LinkedIn | Phase 9 |
| `tistory_publisher.py` | 티스토리 | Phase 9 |
| `naver_blog_publisher.py` | 네이버 블로그 | Phase 9 |
| `naver_cafe_publisher.py` | 네이버 카페 | Phase 9 |
| `daum_cafe_publisher.py` | 다음 카페 | Phase 9 |
| `oauth_manager.py` | OAuth 관리 | Phase 9 |
| `sns_manager.py` | 통합 관리 | Phase 9 |
| `webhook_receiver.py` | 콜백 수신 | Phase 9 |
| `base_publisher.py` | 기본 클래스 | Phase 9 |

### src/divisions/ — 부서별 에이전트 (29명)
| 부서 | 파일들 | Phase |
|------|--------|-------|
| 비서실 | chief_of_staff, relay_worker, report_worker, schedule_worker | Phase 8 |
| CTO실 | cto_manager, frontend, backend, ai_model, infra | Phase 8 |
| CSO실 | cso_manager, business_plan, market_research, financial_model | Phase 8 |
| CLO실 | clo_manager, copyright, patent | Phase 8 |
| CMO실 | cmo_manager, content, community, survey | Phase 8 |
| CIO실 | cio_manager, stock_analysis, market_analysis, risk_management, technical_analysis | Phase 8 |
| CPO실 | division_head (CPO) | Phase 8 |

### src/telegram/ — 텔레그램 봇 (5개)
| 파일 | 기능 | Phase |
|------|------|-------|
| `bot.py` | 봇 메인 + 양방향 브릿지 | Phase 9 |
| `bridge.py` | 에이전트↔텔레그램 이벤트 중계 | Phase 9 |
| `notifier.py` | SNS 승인 요청 알림 | Phase 9 |
| `formatter.py` | 마크다운 서식 처리 | Phase 9 |
| `auth.py` | 텔레그램 사용자 인증 | Phase 9 |
