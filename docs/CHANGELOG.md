# CORTHEX HQ 변경 이력 (Changelog)

> 이 문서는 CORTHEX HQ의 버전별 변경 사항을 상세히 기록합니다.
> 각 버전마다 **왜 바꿨는지**, **뭘 바꿨는지**, **어떤 파일이 수정됐는지**를 포함합니다.

---

## v1.2.0 (2026-02-12) - 아카이브 탭 + SNS 자동 발행 + 버그 수정 5건

> 상태: **구현 완료**
> 커밋: `b7db37a`

### 한 줄 요약

**부서별 아카이브 전용 탭 신설 + Instagram/YouTube 자동 발행 연동 + GPT-4.x 레거시 삭제 + 모델별 추론 수준 동적 UI + 채팅/Batch 버그 수정**

---

### 왜 바꿨나?

v1.1.0에서 아카이브(중간 보고서)는 작업 상세 화면 하단에 접혀 있어서 찾기 힘들었고, 부서별로 모아보거나 과거 보고서를 검색하기 어려웠습니다. 독립 탭으로 분리해서 부서 필터링 + 날짜 정렬 + 전문 보기가 가능하게 만들었습니다.

또한 마케팅 콘텐츠를 만들어도 수동으로 SNS에 올려야 했고, GPT-4.x 모델이 드롭다운에 남아 있어 혼란을 줬으며, 배치 API에서 `async for` 에러가 발생하고, 채팅창에 보낸 메시지가 표시되지 않는 버그가 있었습니다.

### 뭘 바꿨나?

#### 1. 아카이브 전용 탭 (5번째 탭)

기존에 작업 상세 화면 하단에 숨어 있던 중간 보고서를 **독립된 5번째 탭**으로 분리했습니다.

| 기능 | 설명 |
|------|------|
| 부서 필터 | 좌측 사이드바에서 7개 부서(기술/전략/법무/마케팅/투자/비서실/출판) 선택 |
| 보고서 목록 | 날짜순 정렬, 부서 라벨 + 에이전트 이름 + 날짜 표시 |
| 전문 보기 | 우측 패널에서 마크다운 렌더링된 전체 내용 열람 |
| 건수 표시 | 각 부서별 보고서 건수를 괄호로 표시 |

```
[관제실] [사무실] [지식관리] [작업내역] [아카이브]  ← 신규
                                          │
                                ┌─────────┴─────────┐
                                │ 부서 필터  │ 보고서 목록 │ 상세 내용 │
                                │  전체 (42) │ [전략] 02-12│ (마크다운) │
                                │  기술 (12) │ [마케팅]... │            │
                                │  전략 (8)  │            │            │
                                └───────────┴───────────┘
```

#### 2. SNS 자동 발행 (Instagram + YouTube)

마케팅처 콘텐츠 Specialist가 만든 콘텐츠를 **API 호출 한 번으로 SNS에 자동 게시**할 수 있게 되었습니다.

**Instagram Graph API v21.0:**
- 사진 게시 (`/api/sns/instagram/photo`) — URL 기반 이미지 업로드
- 릴스 게시 (`/api/sns/instagram/reel`) — URL 기반 동영상 업로드
- 3단계 프로세스: 컨테이너 생성 → 상태 확인 (5초 폴링) → 발행
- 일일 게시 상한: 20건 (API 제한 25건 중 안전 마진)

**YouTube Data API v3:**
- 동영상 업로드 (`/api/sns/youtube/upload`) — Resumable upload 방식
- OAuth2 refresh token으로 자동 토큰 갱신
- 제목, 설명, 태그, 공개 범위(private/unlisted/public) 설정 가능
- 일일 업로드 상한: 5건 (쿼터 10,000 유닛, 업로드 1건 ≈ 1,600 유닛)

**관제실 사이드바에 연동 상태 표시:**
```
SNS 연동
  Instagram    미연동 / 키 미설정 / 연결됨
  YouTube      미연동 / 키 미설정 / 연결됨
```

**설정 방법** (`config/sns.yaml`):
```yaml
instagram:
  enabled: true                          # 활성화
  access_token_env: "INSTAGRAM_ACCESS_TOKEN"  # Meta 개발자 콘솔에서 발급
  ig_user_id_env: "INSTAGRAM_USER_ID"         # Business Account ID

youtube:
  enabled: true
  client_id_env: "YOUTUBE_CLIENT_ID"          # Google Cloud Console
  client_secret_env: "YOUTUBE_CLIENT_SECRET"
  refresh_token_env: "YOUTUBE_REFRESH_TOKEN"
```

#### 3. GPT-4.x 레거시 모델 삭제

GPT-5 시리즈가 추가되면서 더 이상 필요 없는 GPT-4.x 모델을 완전히 제거했습니다.

| 삭제된 모델 | 삭제 위치 |
|-------------|-----------|
| gpt-4o | `models.yaml`, `openai_provider.py` |
| gpt-4o-mini | `models.yaml`, `openai_provider.py` |
| gpt-4.1-nano | `models.yaml`, `openai_provider.py` |
| gpt-4.1 / gpt-4.1-mini / o3-mini | `openai_provider.py` |

사무실 탭 모델 드롭다운에 GPT-5 + Claude만 표시됩니다.

#### 4. 모델별 추론 수준 동적 반영

각 모델이 지원하는 추론 수준이 다른데, 기존에는 모든 모델에 동일한 4개 옵션을 보여줬습니다.

**변경 후:** 모델에 따라 드롭다운 옵션이 자동으로 변경됩니다.

```yaml
# models.yaml
gpt-5-mini:       reasoning_levels: ["low", "medium", "high"]
gpt-5:            reasoning_levels: ["low", "medium", "high"]
gpt-5-2:          reasoning_levels: ["low", "medium", "high"]
gpt-5-2-pro:      reasoning_levels: ["low", "medium", "high"]
claude-opus-4-6:  reasoning_levels: ["low", "medium", "high"]
claude-sonnet:    reasoning_levels: ["low", "medium", "high"]
claude-haiku:     reasoning_levels: []  ← 추론 비활성화 (비용 효율)
```

- Haiku 선택 시 추론 드롭다운이 **비활성화** (회색 처리)
- 모델 변경 시 현재 추론 설정이 새 모델에서 미지원이면 자동 리셋
- `/api/models` 응답에 `reasoning_levels` 필드 포함

#### 5. 채팅창 메시지 표시 버그 수정

관제실에서 메시지를 보내면 **내가 보낸 메시지가 채팅창에 표시되지 않는** 버그를 수정했습니다.

```javascript
// 수정 전: Alpine.js가 push()를 감지 못하는 경우 발생
this.messages.push({ type: 'user', text });

// 수정 후: 새 배열 참조 할당으로 확실한 반응성 트리거
this.messages = [...this.messages, { type: 'user', text }];
```

#### 6. Batch API `async for` 에러 수정

Anthropic Batch API 결과 수집 시 `async for` 에러가 발생하던 문제를 수정했습니다.

```
에러: 'async for' requires an object with __aiter__ method, got coroutine
원인: self._anthropic.messages.batches.results()가 코루틴을 반환
수정: async for result in await self._anthropic.messages.batches.results(batch.id)
```

#### 7. 텔레그램 봇 /start 무응답 수정

`/start` 명령 시 아무 응답이 없던 문제를 수정했습니다.
- 에러 로깅 강화 (`logger.exception` 추가)
- `chat_id` 자동 안내 메시지 추가 (사용자가 자신의 chat_id를 쉽게 확인 가능)

### 새 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/archive` | 부서별 아카이브 보고서 목록 |
| GET | `/api/archive/{division}/{filename}` | 보고서 본문 조회 |
| GET | `/api/sns/status` | Instagram/YouTube 연동 상태 |
| POST | `/api/sns/instagram/photo` | Instagram 사진 게시 |
| POST | `/api/sns/instagram/reel` | Instagram 릴스 게시 |
| POST | `/api/sns/youtube/upload` | YouTube 동영상 업로드 |

### 수정된 파일 (10개 파일, +651줄 / -47줄)

| 파일 | 작업 | 내용 |
|------|------|------|
| `config/models.yaml` | 수정 | GPT-4.x 삭제 + 각 모델에 `reasoning_levels` 추가 |
| `config/sns.yaml` | **신규** | Instagram/YouTube 연동 설정 |
| `config/tools.yaml` | 수정 | `sns_publish` 도구 등록 |
| `config/agents.yaml` | 수정 | content_specialist에 SNS 도구/능력 추가 |
| `src/integrations/sns_publisher.py` | **신규** | Instagram + YouTube API 통합 클래스 (311줄) |
| `src/integrations/telegram_bot.py` | 수정 | /start 에러 로깅 + chat_id 안내 |
| `src/llm/batch_collector.py` | 수정 | `await` 추가 (async for 에러 수정) |
| `src/llm/openai_provider.py` | 수정 | GPT-4.x 가격표 삭제 |
| `web/app.py` | 수정 | 아카이브 API + SNS API 엔드포인트 추가 |
| `web/templates/index.html` | 수정 | 아카이브 탭 + SNS 상태 + 동적 추론 드롭다운 + 채팅 버그 수정 |

---

## v1.1.0 (2026-02-12) - Batch API + 텔레그램 봇 + 모델 대폭 확장 + 추론 제어

> 상태: **구현 완료**
> 커밋: `f1138d9`

### 한 줄 요약

**비서실장 중복 보고 버그 수정 + GPT-5/Claude 4.6 모델 추가 + Batch API 50% 할인 모드 + 텔레그램 봇(모바일 접근) + 에이전트별 추론 깊이 제어 + 중간보고서 아카이브 + GitHub 자동 동기화**

---

### 왜 바꿨나?

1. **비서실장이 같은 보고서를 2번 보내는 버그** — WebSocket 좀비 연결 + 단일 결과 불필요 종합
2. **LLM 비용이 너무 높음** — Batch API로 50% 절감 가능한데 활용 안 하고 있었음
3. **모바일에서 접근 불가** — 외출 중에 명령을 내릴 수 없었음
4. **중간 보고서가 휘발성** — 전문가들의 개별 보고서가 최종 결과에 합쳐지면 원본이 사라짐
5. **모델 선택지 부족** — GPT-5 시리즈 출시됐는데 아직 GPT-4만 사용 중이었음

### 뭘 바꿨나?

#### 1. 비서실장 중복 보고 버그 수정

**원인 1 — WebSocket 좀비 연결:**
브라우저가 재연결할 때 이전 WebSocket이 닫히지 않고 남아서, 같은 결과를 2개 연결 모두 받아 중복 표시되었습니다.

```javascript
// 수정: 새 연결 전에 기존 연결 완전히 정리
if (this.ws) {
  this.ws.onclose = null;
  this.ws.onmessage = null;
  this.ws.close();
}
```

**원인 2 — 단일 결과 바이패스:**
부서가 1곳만 응답한 경우에도 비서실장이 "종합 보고서"를 생성해서, 원본 + 종합 = 2건이 표시되었습니다. 1건이면 종합 없이 바로 전달하도록 수정했습니다.

#### 2. GPT-5 시리즈 + Claude Opus 4.6 추가

| 모델 | 티어 | 입력 비용 (/1M) | 출력 비용 (/1M) | 용도 |
|------|------|----------------|----------------|------|
| `gpt-5-mini` | worker | $0.25 | $2.00 | 간단한 작업, 대량 처리 |
| `gpt-5` | manager | $1.25 | $10.00 | 중간 복잡도 작업 |
| `gpt-5-2` | manager | $1.75 | $14.00 | 고급 분석/작성 |
| `gpt-5-2-pro` | executive | $21.00 | $168.00 | 최고 수준 추론 |
| `claude-opus-4-6` | executive | $5.00 | $25.00 | 비서실장, 고난도 분석 |

사무실 탭에서 에이전트 모델을 이 중 자유롭게 변경할 수 있습니다.

#### 3. 에이전트별 추론 깊이 제어 (Reasoning Effort)

사무실 탭 에이전트 상세 패널에 **추론 깊이** 드롭다운 추가:

| 설정 | 의미 | 비용 영향 |
|------|------|-----------|
| 기본 | 모델 기본값 사용 | 기본 |
| 낮음 (low) | 빠르고 간결한 응답 | 비용 절감 |
| 중간 (medium) | 균형 잡힌 추론 | 보통 |
| 높음 (high) | 깊은 사고, 장문 추론 | 비용 증가 |

OpenAI: `reasoning_effort` 파라미터 전달
Anthropic: `budget_tokens` + extended thinking 활성화

#### 4. Batch API 50% 할인 모드

**원리:** OpenAI/Anthropic 모두 Batch API 사용 시 토큰 비용 50% 할인 제공. 대신 결과가 즉시가 아닌 수분~수시간 후 도착.

**구현:** `BatchCollector` 클래스 (276줄)
- 0.5초 디바운스로 동시 요청을 모아서 일괄 제출
- 프로바이더 자동 분류 (모델명 prefix로 OpenAI/Anthropic 구분)
- OpenAI: JSONL 파일 업로드 → Batch 생성 → 폴링 → 결과 수집
- Anthropic: `messages.batches.create()` → 폴링 → `results()` 순회
- 결과를 `asyncio.Future`로 대기 → 완료 시 원래 호출자에게 전달

**UI:** 입력창 옆에 `실시간` / `절약 (-50%)` 선택기 추가

```
┌──────────────────────────────────┬───────────┬──────┐
│ 명령을 입력하세요...             │ [실시간 ▾]│ 전송 │
└──────────────────────────────────┴───────────┴──────┘
                                    ↑ "절약 (-50%)" 선택 가능
```

#### 5. 텔레그램 봇 (모바일 접근)

**목적:** 외출 중에도 스마트폰 텔레그램으로 CEO 명령을 내릴 수 있게.

```
[텔레그램 앱]                        [CORTHEX HQ 서버]
사용자 → "삼성전자 분석해줘" ──────→ Telegram Bot API (polling)
                                     → 기존 CORTHEX 파이프라인
사용자 ← 분석 결과 마크다운 ←──────── command_callback()
```

- **Long polling** 방식 (웹훅/공개 URL 불필요)
- **CEO 전용 인증:** `TELEGRAM_ALLOWED_CHAT_ID`로 허용된 사용자만 사용 가능
- **배치 모드 지원:** `/batch 삼성전자 분석` → 50% 할인 모드로 처리
- **깊이 설정:** 텔레그램에서도 작업 깊이 지정 가능
- `python-telegram-bot` 선택적 의존성 (미설치 시 자동 비활성화)

#### 6. 중간 보고서 부서별 아카이브

작업 완료 시 각 전문가의 중간 보고서를 **부서별 폴더**에 자동 저장합니다.

```
archive/
├── tech/           ← 기술개발처
│   └── 20260212_143500_frontend_specialist.md
├── strategy/       ← 사업기획처
├── finance/        ← 투자분석처
├── marketing/      ← 마케팅처
├── legal/          ← 법무처
├── secretary/      ← 비서실
└── publishing/     ← 출판·기록처
```

작업 상세 화면 하단에 "중간 보고서 (에이전트별 원본)" 섹션 추가 — 부서별 색상 코딩, 클릭 시 펼침.

#### 7. GitHub 자동 동기화

작업 완료 시 `archive/`, `output/` 디렉토리의 결과물을 자동으로 `git commit + push`:
- 결과물이 로컬에만 남지 않고 원격 저장소에도 백업
- 커밋 메시지에 task_id 포함

### 새 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/archive` | 부서별 중간 보고서 목록 |
| GET | `/api/archive/{division}/{filename}` | 보고서 본문 조회 |
| PUT | `/api/agents/{id}/reasoning` | 에이전트 추론 깊이 변경 |
| POST | `/api/command` | REST API 명령 (텔레그램 등 외부 연동용) |

### 수정된 파일 (14개 파일, +1,355줄 / -31줄)

| 파일 | 작업 | 내용 |
|------|------|------|
| `config/models.yaml` | 수정 | GPT-5 시리즈 4종 + Claude Opus 4.6 추가 |
| `src/core/agent.py` | 수정 | 단일 결과 바이패스 + reasoning_effort 전달 |
| `src/core/message.py` | 수정 | Message에 reasoning_effort 필드 추가 |
| `src/integrations/__init__.py` | **신규** | integrations 패키지 초기화 |
| `src/integrations/telegram_bot.py` | **신규** | 텔레그램 봇 (142줄) |
| `src/llm/base.py` | 수정 | LLMProvider에 reasoning_effort 파라미터 추가 |
| `src/llm/batch_collector.py` | **신규** | Batch API 수집기 (276줄) |
| `src/llm/anthropic_provider.py` | 수정 | extended thinking + Batch API 지원 |
| `src/llm/openai_provider.py` | 수정 | reasoning_effort + Batch API 지원 |
| `src/llm/router.py` | 수정 | 배치 모드 분기 + reasoning_effort 전달 |
| `web/app.py` | 수정 | 아카이브 API + 추론 API + REST 명령 API + GitHub 동기화 |
| `web/templates/index.html` | 수정 | 아카이브 뷰 + 배치 모드 + 추론 드롭다운 + WS 좀비 수정 |

---

## v0.7.0 (2026-02-12) - 출판·기록 본부 신설

> 상태: **구현 완료**
> 커밋: `26cb678`

### 한 줄 요약

**CPO(출판·기록처장) + 전문가 3명(연대기/편집/아카이브)을 신설하여 총 29명 에이전트 체제로 확대**

---

### 왜 바꿨나?

CORTHEX HQ가 생산하는 보고서, 분석 결과, 전략 문서 등이 체계적으로 기록·편집·보관되지 않았습니다. 출판·기록 전문 부서를 신설하여 조직의 지식을 체계적으로 관리합니다.

### 뭘 바꿨나?

| 에이전트 | 역할 |
|----------|------|
| CPO (출판·기록처장) | 출판·기록 총괄, 편집 방향 결정 |
| Chronicle Specialist | 연대기/이력 기록 |
| Editor Specialist | 문서 편집/교정 |
| Archive Specialist | 문서 보관/분류/검색 |

에이전트 총원: 25명 → **29명**

### 수정된 파일

| 파일 | 내용 |
|------|------|
| `config/agents.yaml` | CPO + 전문가 3명 추가 |
| `web/templates/index.html` | 사이드바에 출판·기록 본부 섹션 추가 |

---

## v0.6.1 (2026-02-12) - 버그 수정

> 상태: **구현 완료**

### 한 줄 요약

**`OUTPUT_DIR` 정의 순서 오류로 서버 시작이 안 되던 버그 수정 + 프로젝트 문서 전면 개편**

---

### 뭘 바꿨나?

#### 1. OUTPUT_DIR NameError 수정

`web/app.py`에서 `OUTPUT_DIR`이 54번째 줄에서 사용되는데, 정의는 62번째 줄에 있어서 서버 시작 시 `NameError`가 발생하던 문제를 수정했습니다.

```python
# 기존 (에러 발생):
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")  # 54줄
# ... 중간 코드 ...
OUTPUT_DIR = PROJECT_DIR / "output"  # 62줄 ← 여기서 정의되지만 이미 위에서 사용됨

# 수정 후:
OUTPUT_DIR = PROJECT_DIR / "output"  # 정의를 먼저!
# ...
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
```

#### 2. 프로젝트 문서 전면 개편

| 파일 | 변경 |
|------|------|
| `README.md` | 전면 재작성 — 조직도, 빠른 시작, 사용법, 프로젝트 구조, API 엔드포인트, 기술 스택 상세 문서화 |
| `CONTEXT.md` | **신규** — 프로젝트 배경, 아키텍처, 핵심 개념, 모듈 설명 등 전체 컨텍스트 문서 |
| `docs/CHANGELOG.md` | 전체 버전 이력에 git 커밋 해시 매핑 추가 + v0.6.1 추가 |

### 수정된 파일

| 파일 | 작업 | 내용 |
|------|------|------|
| `web/app.py` | 수정 | OUTPUT_DIR 정의를 사용 코드 위로 이동 |
| `README.md` | 재작성 | 프로젝트 전체 문서 상세화 |
| `CONTEXT.md` | **신규** | 프로젝트 컨텍스트 문서 |
| `docs/CHANGELOG.md` | 수정 | v0.6.1 추가 + 전체 커밋 이력 보강 |

---

## v0.6.0 (2026-02-12) - 자율 에이전트 시스템

> 상태: **구현 완료**
> 커밋: `6ab062f`

### 한 줄 요약

**큰 업무를 시키면 전문가 에이전트들이 자율적으로 멀티스텝 작업 → 결과를 파일로 저장 → 작업내역에서 열람 가능**

---

### 왜 바꿨나?

기존에는 "인스타 전략 만들어"라고 하면 전문가가 **LLM 1번 호출**하고 끝이었습니다. 짧고 얕은 답변만 나왔어요.

사용자가 원하는 건 **진짜 직원처럼 깊이 있게 작업하는 것**:
- 계획 세우고 → 조사하고 → 초안 쓰고 → 정리해서 → 보고

또한 브라우저를 닫으면 작업이 사라지고, 과거 결과를 다시 볼 수 없는 문제가 있었습니다.

### 뭘 바꿨나?

#### 1. SpecialistAgent 자율 멀티스텝 (Deep Work)

전문가가 이제 **여러 단계로 자율 작업**합니다:

```
기존: think() 1번 → 끝
변경: 계획 수립 → 단계1 실행 → 단계2 실행 → ... → 최종 결과물
```

**깊이 선택** (입력창 옆 드롭다운):
| 옵션 | 단계 수 | 비용 (Haiku 기준) | 용도 |
|------|---------|-------------------|------|
| 빠른 | 1단계 | ~5원 | 간단한 질문 |
| 보통 | 3단계 | ~15원 | 일반 업무 |
| 심화 | 5단계 | ~30원 | 전략/보고서 |

**전체 흐름 예시:**
```
CEO: "CMO, 인스타 전략 풀패키지 만들어" [심화 선택]

비서실장 → CMO에게 배정
CMO → 3명 전문가에게 분배 (asyncio.gather 병렬):

  설문/리서치 전문가 (5단계 자율 작업):
    1단계: 타겟 고객 분석 계획
    2단계: 경쟁사 인스타 벤치마킹
    3단계: 인사이트 정리
    4단계: 최종 리서치 보고서

  콘텐츠 전문가 (5단계 자율 작업):
    1단계: 콘텐츠 방향성 기획
    2단계: 게시물 유형별 전략
    3단계: 예시 게시물 3개 작성
    4단계: 최종 콘텐츠 가이드

  커뮤니티 전문가 (5단계 자율 작업):
    1단계: 채널 운영 전략
    2단계: 주간 포스팅 캘린더
    3단계: 팔로워 성장 전략
    4단계: 최종 운영 매뉴얼

CMO → 3명 결과 취합 → 종합 보고서 작성
비서실장 → CEO에게 최종 보고
```

**토큰 폭발 방지:** 이전 단계 결과 중 최근 3개만 다음 프롬프트에 포함

#### 2. 백그라운드 작업 큐

| 항목 | 기존 | 변경 |
|------|------|------|
| 실행 방식 | WebSocket 블로킹 (결과 올 때까지 대기) | `asyncio.create_task()` 백그라운드 |
| 브라우저 닫으면 | 작업 사라짐 | **작업 계속 진행** |
| 결과 전달 | 특정 WebSocket 연결에만 | **모든 연결에 broadcast** |

```
명령 입력 → "작업 접수됨 (#abc12345)" 즉시 표시
→ 백그라운드에서 에이전트들 작업
→ 실시간 진행률 표시 (단계 1/3, 2/3...)
→ 완료 시 모든 브라우저 탭에 결과 전송
```

#### 3. 결과 파일 자동 저장

완료된 작업은 `output/` 폴더에 마크다운으로 자동 저장:
```
output/
├── 20260212_143500_인스타그램_홍보_전략.md
├── 20260212_150000_시황_분석.md
└── ...
```
각 파일에 메타데이터 포함: task_id, 소요시간, 비용, 토큰 수

#### 4. 작업내역 탭 (4번째 탭)

- 좌측: 작업 목록 (상태 표시 — 진행중/완료/실패)
- 우측: 선택한 작업의 마크다운 결과 렌더링
- 다운로드 버튼으로 .md 파일 저장

#### 5. StatusUpdate 메시지 활성화

`message.py`에 정의만 되어 있던 `StatusUpdate` 타입을 실제 사용:
- 전문가가 각 단계 완료할 때마다 진행률 브로드캐스트
- 프론트엔드 activity_log에 "단계 1/3 - 타겟 분석" 표시

### 새 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/tasks` | 전체 작업 목록 |
| GET | `/api/tasks/{task_id}` | 작업 상세 (결과 포함) |

### 수정된 파일

| 파일 | 작업 | 내용 |
|------|------|------|
| `src/core/task_store.py` | **신규** | TaskStore, StoredTask, TaskStatus 클래스 |
| `src/core/agent.py` | 수정 | SpecialistAgent에 `_deep_work()`, `_parse_steps()` 추가 |
| `src/core/orchestrator.py` | 수정 | `process_command()`에 `context` 파라미터 추가 |
| `web/app.py` | 수정 | 백그라운드 실행, 작업 API, 결과 저장, StatusUpdate 처리 |
| `web/templates/index.html` | 수정 | 작업내역 탭, 깊이 선택기, task_accepted/completed 이벤트 |

---

## v0.5.0 (2026-02-12) - 지식파일 폴더 아코디언 + Claude 전환 + 모델 선택기

> 상태: **구현 완료**
> 커밋: `9457ecf`

### 한 줄 요약

**지식파일을 폴더별로 그룹핑 + 전체 모델을 Claude로 전환 + 사무실 탭에서 에이전트 모델을 드롭다운으로 변경 가능**

---

### 뭘 바꿨나?

#### 1. 지식파일 폴더별 아코디언

지식관리 탭의 파일 목록이 flat list에서 **폴더별 접기/펼치기**로 변경:

```
기존:                          변경:
📄 company_rules.md            📁 shared (전체 공유) [2개]
  shared/                        📄 company_rules.md
📄 product_info.md               📄 CONTEXT.md
  leet_master/                 📁 leet_master (LEET Master) [1개]
📄 investment_policy.md          📄 product_info.md
  finance/                     📁 finance (투자분석) [1개]
                                  📄 investment_policy.md
```

색상: shared=회색, leet_master=시안, finance=보라

#### 2. 전체 모델 Claude로 전환

**원인:** `.env`의 `DEFAULT_MODEL`은 `agents.yaml`의 개별 `model_name`을 덮어쓰지 않음. 사용자가 .env만 바꿨는데 실제로는 24/25 에이전트가 여전히 GPT 사용 중이었음.

| 역할 | 기존 모델 | 변경 모델 |
|------|----------|----------|
| 매니저 5명 | gpt-4o | **claude-sonnet-4-5-20250929** |
| 전문가/워커 19명 | gpt-4o-mini | **claude-haiku-4-5-20251001** |
| _summarize() 하드코딩 | gpt-4o-mini | **claude-haiku-4-5-20251001** |

#### 3. 웹에서 모델 변경 드롭다운

사무실 탭 → 에이전트 클릭 → 기존에 읽기 전용이었던 모델 태그가 **드롭다운**으로 변경:
- 5개 모델 중 선택 가능 (gpt-4o, gpt-4o-mini, gpt-4.1-nano, claude-sonnet, claude-haiku)
- 선택 즉시 저장 (`agents.yaml` 자동 업데이트 + 핫리로드)
- 서버 재시작 불필요

### 새 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/models` | 사용 가능한 모델 목록 (models.yaml 기반) |
| PUT | `/api/agents/{id}/model` | 에이전트 모델 변경 + YAML 저장 + 핫리로드 |

### 수정된 파일

| 파일 | 내용 |
|------|------|
| `config/agents.yaml` | 25개 에이전트 model_name 전부 Claude로 변경 |
| `src/core/agent.py` | `_summarize()` 하드코딩 모델 변경 |
| `web/app.py` | GET /api/models, PUT /api/agents/{id}/model 추가 |
| `web/templates/index.html` | 폴더 아코디언 + 모델 드롭다운 + JS helpers |

---

## v0.4.0 (2026-02-12) - 가상 사무실 + Soul 편집기 + 지식관리 시스템

> 상태: **구현 완료**
> 커밋: `1fde7e7`

### 한 줄 요약

**웹 UI에 가상 사무실(에이전트 카드 그리드), Soul(시스템 프롬프트) 실시간 편집기, 마크다운 지식파일 관리 기능 추가**

---

### 뭘 바꿨나?

#### 1. 가상 사무실 탭 (2번째 탭)

에이전트 25명을 **부서별 색상 카드**로 표시하는 사무실 뷰:
- 각 카드: 이모지 + 한글 이름 + 상태 표시
- 클릭 시 우측 상세 패널 열림 (역할, 모델, 능력치, 부하직원, 상관)

부서별 색상:
| 부서 | 색상 |
|------|------|
| 기술개발 | 파랑 |
| 사업기획 | 초록 |
| 법무·IP | 보라 |
| 마케팅 | 주황 |
| 투자분석 | 빨강 |
| 비서실 | 회색 |

#### 2. Soul(영혼) 편집기

에이전트의 시스템 프롬프트를 웹에서 직접 수정:
- 상세 패널 하단 textarea에서 편집
- "Soul 저장 (즉시 반영)" 버튼 → `agents.yaml` 파일에 즉시 저장 + 메모리 핫리로드
- 서버 재시작 없이 에이전트 성격/역할 변경 가능

#### 3. 지식관리 탭 (3번째 탭)

`knowledge/` 폴더의 마크다운 파일을 웹에서 CRUD:
- **조회:** 파일 목록 + 내용 보기
- **생성:** 폴더 선택 + 파일명 입력 → 즉시 생성
- **수정:** 에디터에서 내용 수정 → 저장
- **삭제:** 파일 삭제 (확인 다이얼로그)

지식 파일은 에이전트 system_prompt에 자동 주입:
- `shared/` → 모든 에이전트
- `leet_master/` → LEET Master 본부 에이전트만
- `finance/` → 투자분석 본부 에이전트만

### 수정된 파일

| 파일 | 내용 |
|------|------|
| `web/templates/index.html` | 사무실 탭 + Soul 편집기 + 지식관리 탭 전체 구현 |
| `web/app.py` | Soul PUT API + Knowledge CRUD API 추가 |
| `run.bat` | 윈도우 원클릭 실행 배치 파일 |

---

## v0.3.0 (2026-02-12) - 본부 라벨 분리 (LEET Master / 투자분석)

> 상태: **구현 완료**
> 커밋: `38d4105`

### 한 줄 요약

**본부장 에이전트 없이, "LEET Master 본부"와 "투자분석 본부"를 라벨/그룹 개념으로 도입하여 UI와 프롬프트에서 두 사업 영역을 구분합니다.**

---

### 왜 바꿨나?

v0.2.0에서 본부장을 삭제하고 5개 처장을 비서실장 아래 동급으로 배치했는데,
실제로는 CTO/CSO/CLO/CMO는 **LEET Master 제품**을 만드는 팀이고,
CIO는 **주식 투자 분석**이라는 완전히 다른 도메인입니다.

비서실장이 명령을 분류할 때도 "이건 제품 관련인지, 투자 관련인지" 구분이 필요했고,
UI에서도 16명의 제품팀과 4명의 투자팀이 섞여 있으면 한눈에 안 들어왔습니다.

### 뭘 바꿨나?

**핵심: 본부장 에이전트 추가 없이, 3곳에만 "본부" 개념을 반영**

| 반영 위치 | 변경 내용 |
|-----------|-----------|
| 비서실장 system_prompt | "LEET Master 본부 / 투자분석 본부" 조직 구조와 배분 규칙 명시 |
| 웹 UI 사이드바 | 본부 단위 접기/펼치기 래퍼 추가, 처장은 본부 안에 중첩 |
| CLI 조직도 | LEET Master 본부 / 투자분석 본부 그룹핑 표시 |

**조직도 변화:**
```
v0.2.0 (플랫):                    v0.3.0 (본부 그룹핑):
├── CTO                           ├── LEET Master 본부
├── CSO                           │    ├── CTO
├── CLO                           │    ├── CSO
├── CMO                           │    ├── CLO
├── CIO                           │    └── CMO
                                  └── 투자분석 본부
                                       └── CIO
```

**LLM 비용 추가: 0** (본부장 에이전트가 없으므로)

### 수정된 파일 (5개)

| 파일 | 변경 |
|------|------|
| `config/agents.yaml` | 비서실장 system_prompt에 본부 구조 + 배분 규칙 명시 |
| `web/templates/index.html` | 사이드바 본부 래퍼 + JS (expanded, getSectionAgentIds, auto-expand) |
| `src/cli/app.py` | 조직도 본부 그룹핑 + 버전 v0.3.0 |
| `web/app.py` | FastAPI 버전 v0.3.0 |
| `docs/CHANGELOG.md` | 이 문서 |

---

## v0.2.0 (2026-02-12) - 비서실장 오케스트레이터 통합 + 비용 추적 고도화

> 상태: **구현 완료**
> 커밋: `6512b6e`

### 한 줄 요약

**불필요한 본부장 레이어를 제거하고, 비서실장이 CEO의 모든 명령을 직접 관리하도록 변경했습니다.**

---

### 왜 바꿨나? (문제점)

v0.1.0에서 CEO가 "삼성전자 주가 분석해줘"라고 명령하면 이런 일이 벌어졌습니다:

```
CEO: "삼성전자 주가 분석해줘"
  │
  ▼
① Orchestrator가 LLM을 호출해서 "이건 금융 관련이니 finance_head에게 보내자" 판단  ← LLM 호출 1회
  │
  ▼
② finance_head(금융분석 본부장)가 LLM을 호출해서 "이건 cio_manager에게 보내자" 판단  ← LLM 호출 1회 (낭비!)
  │
  ▼
③ cio_manager(투자분석처장)가 실제로 부하 전문가들에게 배분  ← LLM 호출 1회
  │
  ▼
④ 전문가들이 분석 실행
```

**문제가 뭐냐면:**
- **②번이 완전히 쓸데없음.** 본부장은 "아 이거 내 밑에 CIO한테 보내야겠다" 이것만 하고 끝. 분류 역할만 하는데 그게 LLM 호출 1회 비용이 드는 것
- 본부장이 2명(LEET MASTER 본부장, 금융분석 본부장)이었는데, 둘 다 같은 문제
- 반면 **비서실장**은 "일반 질문"의 fallback으로만 쓰여서 거의 놀고 있었음

### 뭘 바꿨나? (변경 내역)

#### 1. 조직 구조 개편 — 본부장 2명 삭제, 비서실장 승격

**v0.1.0 (AS-IS) — 4단계 명령 흐름:**
```
CEO
 └→ Orchestrator (숨겨진 LLM 분류기)
      ├→ LEET MASTER 본부장 ─── 중계만 하는 허브
      │    ├→ CTO 기술개발처장 → 전문가 4명
      │    ├→ CSO 사업기획처장 → 전문가 3명
      │    ├→ CLO 법무·IP처장 → 전문가 2명
      │    └→ CMO 마케팅·고객처장 → 전문가 3명
      │
      ├→ 금융분석 본부장 ─── 중계만 하는 허브
      │    └→ CIO 투자분석처장 → 전문가 4명
      │
      └→ 비서실장 (fallback용) → Worker 3명
```

**v0.2.0 (TO-BE) — 3단계 명령 흐름:**
```
CEO
 └→ 비서실장 (Chief of Staff) ← 총괄 오케스트레이터로 승격!
      ├→ CTO 기술개발처장 → 전문가 4명
      ├→ CSO 사업기획처장 → 전문가 3명
      ├→ CLO 법무·IP처장 → 전문가 2명
      ├→ CMO 마케팅·고객처장 → 전문가 3명
      ├→ CIO 투자분석처장 → 전문가 4명
      └→ Worker 3명 (보고요약, 일정추적, 정보중계)
```

**핵심 변화:**
| 항목 | v0.1.0 | v0.2.0 |
|------|--------|--------|
| 에이전트 수 | 27명 (본부장 2명 포함) | **25명** (본부장 삭제) |
| CEO 명령 → 결과 단계 | 4단계 | **3단계** |
| 명령당 불필요 LLM 호출 | 1~2회 (본부장 분류) | **0회** |
| 비서실장 역할 | fallback (거의 안 쓰임) | **모든 명령의 총괄 관리** |
| 명령 분류 담당 | 숨겨진 Orchestrator 클래스 | **비서실장이 직접 분류** |

#### 2. 비용 추적 고도화 — 에이전트별 비용 추적

v0.1.0에서는 "어떤 **모델**을 얼마나 썼는지"만 알 수 있었습니다.
v0.2.0에서는 "어떤 **에이전트**가 얼마나 썼는지", "어떤 **프로바이더**(OpenAI/Anthropic)에 얼마나 썼는지"도 알 수 있습니다.

**v0.1.0의 비용 데이터:**
```json
{
  "total_cost": 0.0342,
  "by_model": {
    "gpt-4o": {"calls": 5, "cost_usd": 0.03},
    "gpt-4o-mini": {"calls": 10, "cost_usd": 0.004}
  }
}
```

**v0.2.0의 비용 데이터:**
```json
{
  "total_cost": 0.0342,
  "by_model": { "..." : "..." },
  "by_agent": {
    "chief_of_staff": {"calls": 3, "cost_usd": 0.012},
    "cto_manager": {"calls": 2, "cost_usd": 0.008},
    "frontend_specialist": {"calls": 1, "cost_usd": 0.002}
  },
  "by_provider": {
    "openai": {"calls": 12, "cost_usd": 0.030},
    "anthropic": {"calls": 3, "cost_usd": 0.004}
  }
}
```

**구현 방법:**
LLM을 호출할 때마다 "누가 호출했는지(agent_id)"를 함께 기록하도록 전체 호출 체인을 수정:
```
에이전트.think() → ModelRouter.complete(agent_id=...) → CostTracker.record(agent_id=...)
```

### 수정된 파일 (9개 파일, +168줄 / -241줄)

| 파일 | 변경 요약 |
|------|-----------|
| `config/agents.yaml` | `leet_master_head`, `finance_head` 삭제. `chief_of_staff`에 5개 처장을 subordinate로 추가 |
| `src/core/orchestrator.py` | `_classify_command()` LLM 분류 호출 삭제. 모든 명령을 `chief_of_staff`에게 직행 |
| `src/core/registry.py` | `list_division_heads()` 조건 변경 |
| `src/core/agent.py` | `think()`, `_summarize()`에서 `agent_id` 전달 |
| `src/llm/router.py` | `complete()`에 `agent_id` 파라미터 추가 |
| `src/llm/cost_tracker.py` | `CostRecord`에 `agent_id` 필드 추가. `summary_by_agent()`, `summary_by_provider()` 추가 |
| `web/templates/index.html` | 본부 wrapper 제거, 플랫 구조. 상태 색상 변경 |
| `web/app.py` | `/api/cost`에 `by_agent`, `by_provider` 추가 |
| `src/cli/app.py` | 조직도 본부장 레이어 제거 |

### 예상 효과

| 항목 | 수치 |
|------|------|
| 명령당 LLM 호출 절감 | **1~2회** (본부장 분류 + 종합 제거) |
| 명령당 비용 절감 | 약 **$0.002~0.005** (gpt-4o 1회 기준) |
| 명령 처리 시간 단축 | 본부장 처리 대기 시간 제거 |
| 비용 추적 세분화 | 모델별 → 모델별 + **에이전트별** + **프로바이더별** |

---

## v0.1.0 (2026-02-12) - 최초 릴리즈

> 상태: **배포 완료**
> 커밋: `4ece0c0`, `a03c1b7`

### 한 줄 요약

**CORTHEX HQ 멀티 에이전트 시스템의 첫 번째 버전. 25명의 AI 에이전트가 CEO 명령을 자동 처리합니다.**

### 핵심 기능

#### 1. 멀티 에이전트 조직 구조
- **25명의 AI 에이전트**가 회사 조직도 형태로 구성
- 역할 기반 계층: 본부장 → 처장 → Specialist → Worker
- 각 에이전트가 고유한 AI 모델, 시스템 프롬프트, 역할을 가짐

#### 2. 조직 구성

| 부서 | 에이전트 수 | 주요 역할 |
|------|-------------|-----------|
| 비서실 | 4명 | 보고 요약, 일정 추적, 정보 중계 |
| LEET MASTER 본부 | 15명 | 기술개발(CTO), 사업기획(CSO), 법무(CLO), 마케팅(CMO) |
| 금융분석 본부 | 5명 | 시황분석, 종목분석, 기술적분석, 리스크관리 |
| Tool Pool | 5개 | 변리사, 세무사, 디자이너, 번역가, 웹검색 |

#### 3. 지능형 명령 라우팅
- Orchestrator가 CEO 명령을 LLM으로 분류
- 가장 적합한 사업부에 자동 배분
- 처장(Manager)이 세부 업무를 Specialist에게 **병렬 위임**
- 결과를 **종합 보고서**로 합성하여 CEO에게 반환

#### 4. CEO 관제실 웹 UI
- FastAPI + WebSocket 기반 실시간 대시보드
- 조직도 트리 뷰 (에이전트 상태 실시간 표시)
- 마크다운 렌더링 결과 표시
- 활동 로그 실시간 스트리밍
- 누적 비용/토큰 모니터링

#### 5. Rich Terminal CLI
- 터미널에서도 CEO 명령 입력 가능
- 조직도 트리 표시 + 비용 요약 테이블 + 마크다운 결과 렌더링

#### 6. 멀티 LLM 지원
- OpenAI (gpt-4o, gpt-4o-mini) + Anthropic (claude-sonnet) 지원
- 모델명 prefix로 자동 프로바이더 라우팅
- 에이전트별 독립적인 모델 설정 가능

#### 7. 지식 관리 시스템
- `knowledge/` 디렉토리의 .md 파일을 에이전트 system_prompt에 자동 주입
- 부서(division)별 지식 매칭

#### 8. 도구(Tool) 시스템
- 변리사, 세무사, 디자이너, 번역가, 웹검색 5개 Tool
- 에이전트별 허용 도구 제한 (`allowed_tools`)
- 권한 없는 도구 호출 시 `ToolPermissionError`

#### 9. 비용 추적
- 모든 LLM 호출의 토큰 사용량 및 비용 자동 기록
- 모델별 비용 요약 (`summary_by_model()`)

### 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| 언어 | Python 3.11+ |
| 웹 프레임워크 | FastAPI |
| 실시간 통신 | WebSocket |
| 프론트엔드 | Tailwind CSS + Alpine.js |
| CLI | Rich |
| 설정 관리 | YAML + Pydantic v2 |
| LLM 통신 | httpx (async) |

---

## 전체 Git 커밋 이력

| 커밋 해시 | 버전 | 설명 |
|-----------|------|------|
| `b7db37a` | v1.2.0 | feat: 아카이브 탭 + SNS 자동 발행 + 버그 수정 5건 |
| `5642b7a` | v1.1.1 | fix: 텔레그램 봇 /start 무응답 — 에러 로깅 + chat_id 안내 |
| `f1138d9` | v1.1.0 | feat: Batch API + 텔레그램 봇 + 모델 확장 + 추론 제어 + 아카이브 |
| `26cb678` | v0.7.0 | feat: 출판·기록 본부 신설 (CPO + 전문가 3명, 총 29명) |
| `810d2a9` | v0.6.1 | fix: OUTPUT_DIR 정의 순서 수정 — NameError 해결 |
| `072d25c` | v0.6.0 | docs: v0.4.0~v0.6.0 전체 변경이력 문서 업데이트 |
| `6ab062f` | v0.6.0 | feat: 자율 에이전트 시스템 — 멀티스텝 딥워크 + 백그라운드 작업 + 작업내역 |
| `9457ecf` | v0.5.0 | feat: 지식파일 폴더 아코디언 + 모델 전체 Claude 전환 + 웹 모델 선택기 |
| `1aec4d7` | v0.4.0 | fix: 서버 초기화 오류 수정 + run.bat 추가 |
| `1fde7e7` | v0.4.0 | feat: v0.4.0 가상 사무실 + Soul 편집기 + 지식관리 시스템 |
| `db27749` | - | fix: add missing web/static directory |
| `38d4105` | v0.3.0 | feat: v0.3.0 본부 라벨 분리 — LEET Master 본부 / 투자분석 본부 |
| `0e7fa45` | v0.2.0 | docs: v0.2.0 변경 이력 상세 업데이트 |
| `6512b6e` | v0.2.0 | feat: v0.2.0 본부장 레이어 제거 및 비서실장 오케스트레이터 승격 |
| `18bcd84` | v0.2.0 | docs: v0.2.0 구현 계획서 + 버전별 변경 이력 문서 추가 |
| `4ece0c0` | v0.1.0 | feat: CEO 관제실 웹 UI + 지식 관리 시스템 + 원클릭 설치 |
| `a03c1b7` | v0.1.0 | feat: CORTHEX HQ 멀티 에이전트 시스템 전체 구현 |
| `436e915` | - | Initial commit |

---

## 버전 관리 규칙

- **MAJOR** (x.0.0): 시스템 아키텍처 대폭 변경
- **MINOR** (0.x.0): 새 기능 추가 또는 기존 기능 개편
- **PATCH** (0.0.x): 버그 수정, 문서 수정, 소규모 개선
