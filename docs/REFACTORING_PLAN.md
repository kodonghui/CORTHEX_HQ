# CORTHEX HQ 대개편 리팩토링 계획서

> **작성일**: 2026-02-23
> **목적**: 전수검사 결과 기반 서버 구조 대개편
> **원칙**: 동작하는 상태를 유지하면서 하나씩 교체 (집 살면서 배관 교체)

---

## 현재 상태 요약 (전수검사 결과)

### 핵심 수치

| 항목 | 현재 | 정상 기준 |
|------|------|----------|
| `mini_server.py` | **11,906줄** | 500줄 이하/모듈 |
| `index.html` | **10,666줄** | 컴포넌트별 분리 |
| 전역 변수 | **44개** | 최소한 + Lock |
| API 엔드포인트 | **55개** (인증 1개만) | 전체 인증 |
| 중복 브로드캐스트 패턴 | **24곳** | 헬퍼 함수 1개 |
| `except Exception: pass` | **40곳 이상** | 구체적 에러 + 로깅 |
| 모델명 하드코딩 위치 | **5곳 이상** | config 2곳만 |
| Config YAML/JSON 이중화 | **3쌍** (동기화 안 됨) | YAML 단일 |
| AI 호출 타임아웃 | **없음** | 60초 제한 |
| 메모리 누수 딕셔너리 | **4개** (정리 없음) | TTL + 정리 |

### 현재 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────┐
│                    mini_server.py (11,906줄)                 │
│                                                             │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────────────────┐ │
│  │WebSocket│ │ 55개 API │ │텔레그램  │ │ 에이전트 라우팅/ │ │
│  │ 핸들러  │ │엔드포인트│ │   봇    │ │ 위임/합성 로직  │ │
│  └────┬────┘ └────┬─────┘ └────┬────┘ └────────┬─────────┘ │
│       │           │            │                │           │
│       └───────────┴────────────┴────────┬───────┘           │
│                                         │                   │
│  ┌──────────────────────────────────────┴────────────────┐  │
│  │              전역 변수 44개 (Lock 없음)               │  │
│  │  connected_clients, _bg_tasks, _batch_queue,          │  │
│  │  _sse_clients, _notion_log, _price_cache ...          │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              │   ai_handler.py       │
              │   (1,651줄)           │
              │   3개 프로바이더      │
              │   도구 호출 루프      │
              │   모델명 하드코딩 10+ │
              └───────────┬───────────┘
                          │
              ┌───────────┴───────────┐
              │     db.py (1,426줄)   │
              │     SQLite 17개 테이블│
              │     (양호)            │
              └───────────────────────┘
```

**문제**: 모든 것이 `mini_server.py` 한 파일에 들어있음. 기능 추가할 때마다 이 파일이 커짐.

---

## 목표 아키텍처

```
web/
├── app.py                    ← FastAPI 앱 생성 + 미들웨어 (100줄)
├── main.py                   ← 서버 시작 진입점 (50줄)
├── auth.py                   ← 인증 미들웨어 (100줄)
├── db.py                     ← DB (현재 유지, 양호)
├── ai_handler.py             ← AI 호출 (리팩토링 후 800줄)
├── state.py                  ← 전역 상태 관리 + Lock (200줄)
├── broadcast.py              ← WebSocket/SSE 브로드캐스트 헬퍼 (100줄)
├── handlers/
│   ├── websocket_handler.py  ← WebSocket 연결 + 메시지 처리 (300줄)
│   ├── agent_handler.py      ← 에이전트 라우팅/위임/합성 (800줄)
│   ├── task_handler.py       ← 작업 관리 API (200줄)
│   ├── batch_handler.py      ← 배치 처리 체인 (500줄)
│   ├── media_handler.py      ← 미디어 서빙/삭제 (100줄)
│   ├── sns_handler.py        ← SNS 큐/승인/발행 (300줄)
│   ├── trading_handler.py    ← 주식 투자 API (400줄)
│   ├── telegram_handler.py   ← 텔레그램 봇 (300줄)
│   ├── quality_handler.py    ← 품질검수 API (200줄)
│   └── debug_handler.py      ← 디버그/로그 엔드포인트 (100줄)
└── templates/
    └── index.html            ← (장기: 컴포넌트 분리)
```

---

## 실행 계획 (12 Step)

> 매 Step 완료 후 배포 + 서버 정상 확인 + 커밋
> 하나라도 깨지면 롤백 후 원인 분석

---

### Step 1: 브로드캐스트 헬퍼 추출

**문제**: WebSocket 브로드캐스트 코드가 24곳에 복붙되어 있음
```python
# 이 패턴이 24번 반복됨
for c in connected_clients[:]:
    try:
        await c.send_json({"event": "...", "data": {...}})
    except Exception:
        pass
```

**작업 내용**:
1. `web/broadcast.py` 생성
2. `broadcast_ws(event, data)` 함수 작성 (타임아웃 2초, 실패 시 클라이언트 제거)
3. `broadcast_sse(msg_data)` 함수 작성
4. `mini_server.py`의 24곳을 `broadcast_ws()` 호출로 교체
5. `connected_clients` 리스트에 `asyncio.Lock` 추가

**검증**: 웹에서 프롬프트 보내기 → 응답 정상 수신 확인

**예상 효과**: mini_server.py **-200줄**, 레이스컨디션 해결

---

### Step 2: 전역 상태 관리 모듈

**문제**: 44개 전역 변수가 mini_server.py에 흩어져 있고, Lock 없이 여러 async 태스크에서 동시 접근

**작업 내용**:
1. `web/state.py` 생성
2. 모든 전역 변수를 `AppState` 클래스로 이동:
   ```python
   class AppState:
       def __init__(self):
           self.connected_clients: list[WebSocket] = []
           self.clients_lock = asyncio.Lock()
           self.bg_tasks: dict[str, asyncio.Task] = {}
           self.bg_results: dict[str, dict] = {}
           self.bg_current_task_id: str | None = None
           self.batch_queue: list[dict] = []
           self.batch_lock = asyncio.Lock()
           self.sse_clients: list[asyncio.Queue] = []
           self.notion_log: list[dict] = []
           # ... 나머지 44개 변수

   app_state = AppState()
   ```
3. `mini_server.py`에서 `global` 키워드 전부 제거, `app_state.xxx`로 교체
4. `_bg_current_task_id` 레이스컨디션: Lock으로 보호

**검증**: 서버 시작 → 동시 2개 브라우저 탭에서 프롬프트 전송 → 충돌 없음

**예상 효과**: 레이스컨디션 5개 해결, 메모리 누수 추적 가능

---

### Step 3: 메모리 누수 수정 + AI 호출 타임아웃

**문제**:
- `_bg_tasks`, `_bg_results` 딕셔너리가 무한히 커짐
- `_notion_log` 리스트가 무한히 커짐
- AI 호출(`ask_ai()`)에 타임아웃 없어서 행(hang) 가능

**작업 내용**:
1. `AppState`에 TTL 기반 정리 메서드 추가:
   ```python
   async def cleanup_old_tasks(self, max_age_seconds=3600):
       """1시간 이상 된 완료 태스크 정리"""
       cutoff = time.time() - max_age_seconds
       old_keys = [k for k, v in self.bg_results.items()
                   if v.get("_completed_at", 0) < cutoff]
       for k in old_keys:
           self.bg_results.pop(k, None)
           self.bg_tasks.pop(k, None)
   ```
2. 서버 시작 시 주기적 정리 태스크 등록 (10분마다)
3. `_notion_log` 최대 500개로 제한 (FIFO)
4. `ask_ai()` 호출 전부에 `asyncio.wait_for(timeout=120)` 래핑
5. 타임아웃 시 사용자에게 "AI 응답 시간 초과" 메시지 전송

**검증**: 서버 1시간 운영 후 메모리 사용량 확인 (증가 안 해야 함)

**예상 효과**: 메모리 누수 해결, 무한 대기 해결

---

### Step 4: 에러 핸들링 정리

**문제**: `except Exception: pass`가 40곳 이상. 에러가 삼켜져서 디버깅 불가능

**작업 내용**:
1. 모든 `except Exception: pass` 검색 (40곳+)
2. 각각 다음 중 하나로 교체:
   - **무시해도 되는 것**: `except Exception: pass` → 주석으로 이유 명시
   - **로깅 필요**: `except Exception as e: logger.warning("...: %s", e)`
   - **전파 필요**: `except SpecificError` 또는 `raise`
3. 에러 반환 형식 통일: 모든 함수가 `{"error": "메시지"}` 또는 예외 발생 중 하나만 사용

**검증**: 의도적으로 잘못된 API 키로 호출 → 에러 로그 확인

**예상 효과**: 디버깅 시간 50% 단축

---

### Step 5: 핸들러 모듈 분리 — 미디어 + SNS + 디버그

**문제**: 미디어, SNS, 디버그 엔드포인트가 mini_server.py에 섞여 있음

**작업 내용**:
1. `web/handlers/` 디렉토리 생성
2. `media_handler.py` 추출:
   - `/api/media/images/{filename}`, `/api/media/videos/{filename}`
   - `/api/media/list`, `/api/media/{type}/{filename}` DELETE
   - `/api/media/delete-batch`
3. `sns_handler.py` 추출:
   - `/api/sns/status`, `/api/sns/queue`, `/api/sns/approve/{id}`
   - `/api/sns/reject/{id}`, `/api/sns/publish/{id}`
   - `/api/sns/queue` DELETE, `/api/sns/events`
   - OAuth 관련 엔드포인트 전부
4. `debug_handler.py` 추출:
   - `/api/debug/server-logs`, 기타 디버그 엔드포인트
5. FastAPI Router 사용:
   ```python
   # web/handlers/media_handler.py
   from fastapi import APIRouter
   router = APIRouter(prefix="/api/media", tags=["media"])

   @router.get("/list")
   async def list_media(): ...
   ```
6. `mini_server.py`에서 `app.include_router(media_router)` 등록

**검증**: 미디어 탭 열기, SNS 승인큐 열기, 서버 로그 확인 — 전부 정상

**예상 효과**: mini_server.py **-800줄**

---

### Step 6: 핸들러 모듈 분리 — 작업 + 배치 + 품질

**작업 내용**:
1. `task_handler.py` 추출:
   - `/api/tasks` GET/POST/DELETE/PUT 전부
   - `/api/tasks/{id}/bookmark`, `/api/tasks/{id}/cancel` 등
2. `batch_handler.py` 추출:
   - `/api/batch/*` 전부 (큐, 체인, API 배치, 히스토리)
   - `_run_batch_chain()`, `_start_batch_chain()` 함수
3. `quality_handler.py` 추출:
   - `/api/quality`, `/api/quality-rules/*`
   - 품질검수 관련 로직

**검증**: 배치 체인 실행, 품질검수 탭, 작업 목록 — 전부 정상

**예상 효과**: mini_server.py **-2,000줄**

---

### Step 7: 핸들러 모듈 분리 — 에이전트 + 텔레그램

**작업 내용**:
1. `agent_handler.py` 추출:
   - `_process_ai_command()`, `_route_task()`, `_call_agent()`
   - `_manager_with_delegation()`, `_broadcast_to_managers_all()`
   - 에이전트 라우팅, 분류, 위임 체인 전체
2. `telegram_handler.py` 추출:
   - 텔레그램 봇 초기화, 핸들러, CEO 알림
3. `websocket_handler.py` 추출:
   - WebSocket 연결 관리, 메시지 라우팅
   - `_run_agent_bg()` 백그라운드 태스크

**검증**: 웹 채팅, 텔레그램 메시지, 에이전트 응답 — 전부 정상

**예상 효과**: mini_server.py → **app.py (500줄)** 으로 축소. 11,906줄 → 500줄 달성

---

### Step 8: ai_handler.py 리팩토링

**문제**:
- 모델명 10곳 이상 하드코딩
- 3개 프로바이더 도구 호출 코드 3벌 복붙
- 도구 결과 truncation `[:4000]` 3곳 하드코딩
- Extended thinking 메모리 누적

**작업 내용**:
1. 모델명 → `config/models.yaml`에서 읽도록 변경
   ```python
   # 변경 전: 하드코딩
   default_model = "claude-sonnet-4-6"

   # 변경 후: config에서 로드
   default_model = MODELS_CONFIG["defaults"]["anthropic"]
   ```
2. 프로바이더별 도구 호출 공통 패턴 추출:
   ```python
   async def _execute_tool_loop(provider, messages, tools, executor, max_iter=10):
       """3개 프로바이더 공통 도구 호출 루프"""
   ```
3. `TOOL_RESULT_MAX_CHARS = 4000` 상수화
4. Extended thinking 블록 → 루프 반복 시 제거 (메모리 절약)
5. `_PRICING` 딕셔너리 → `models.yaml`에서 로드

**검증**: 3개 프로바이더(Claude, GPT, Gemini) 각각 도구 호출 테스트

**예상 효과**: ai_handler.py 1,651줄 → 800줄, 모델 변경 시 config만 수정

---

### Step 9: Config 이중화 해결

**문제**: YAML과 JSON이 동기화 안 됨. 서버가 구버전 JSON 로드 위험

**작업 내용**:
1. `deploy.yml`에 yaml2json 자동 실행 단계 추가:
   ```yaml
   - name: YAML → JSON 동기화
     run: cd config && python yaml2json.py
   ```
2. `yaml2json.py` 오류 시 배포 중단 (exit 1)
3. 서버 코드: YAML 직접 로드로 통일 (JSON 폴백 제거)
4. `config/*.json` 파일 → `.gitignore`에 추가 (서버에서만 생성)

**검증**: 배포 후 `agents.yaml` 수정 → 서버 반영 확인

**예상 효과**: Config 동기화 문제 영구 해결

---

### Step 10: 인증 미들웨어 추가

**문제**: 55개 엔드포인트 중 1개만 인증. 누구나 API 호출 가능

**작업 내용**:
1. `web/auth.py` 생성
2. FastAPI 미들웨어로 전체 `/api/*` 경로에 토큰 검증:
   ```python
   @app.middleware("http")
   async def auth_middleware(request: Request, call_next):
       # /api/auth/login, /api/debug/server-logs 등 화이트리스트 제외
       if request.url.path.startswith("/api/") and not is_whitelisted(path):
           token = request.headers.get("x-auth-token")
           if not verify_token(token):
               return JSONResponse({"error": "인증 필요"}, 401)
       return await call_next(request)
   ```
3. 화이트리스트: `/api/auth/*`, `/api/debug/server-logs` (Cloudflare WAF Skip)
4. `hmac.compare_digest()` 사용 (타이밍 공격 방지)

**검증**: 토큰 없이 API 호출 → 401, 토큰 있으면 정상

**예상 효과**: 보안 취약점 해결

---

### Step 11: 입력 검증 + 서버 셧다운 정리

**문제**:
- WebSocket 메시지 크기 제한 없음 (1MB JSON 가능)
- 서버 종료 시 백그라운드 태스크 정리 안 됨

**작업 내용**:
1. WebSocket 메시지 최대 크기 제한 (64KB)
2. API POST body 최대 크기 제한 (1MB)
3. 서버 셧다운 핸들러에 태스크 정리 추가:
   ```python
   @app.on_event("shutdown")
   async def on_shutdown():
       # 모든 백그라운드 태스크 취소
       for task_id, task in app_state.bg_tasks.items():
           task.cancel()
       # 텔레그램 봇 종료
       await stop_telegram_bot()
       # DB 연결 정리
       close_db()
   ```
4. `asyncio.create_task()` 호출 시 모두 `app_state.bg_tasks`에 등록

**검증**: 서버 재시작 시 "graceful shutdown" 로그 확인

---

### Step 12: index.html 구조 정리 (장기)

**문제**: 10,666줄 단일 HTML. Alpine.js 데이터/메서드가 3,000줄 이상

**작업 내용** (점진적):
1. Alpine.js 메서드를 외부 JS 파일로 분리:
   ```
   web/static/js/
   ├── app.js          ← Alpine.js 메인 데이터
   ├── chat.js         ← 채팅 관련 메서드
   ├── sns.js          ← SNS/미디어 관련 메서드
   ├── trading.js      ← 주식 관련 메서드
   └── utils.js        ← 공통 유틸 (showToast 등)
   ```
2. HTML 템플릿을 Jinja2 include로 분리:
   ```
   web/templates/
   ├── index.html          ← 메인 레이아웃만
   ├── partials/
   │   ├── chat_panel.html
   │   ├── sns_panel.html
   │   ├── trading_panel.html
   │   └── sidebar.html
   ```

**검증**: 모든 탭 정상 동작 + 모바일 UI 확인

**예상 효과**: HTML 유지보수성 대폭 향상

---

## 실행 순서 & 의존성

```
Step 1 (브로드캐스트 헬퍼) ──┐
Step 2 (전역 상태 관리)     ──┼── Step 5~7 (핸들러 분리)
Step 3 (메모리+타임아웃)    ──┘        │
Step 4 (에러 핸들링)        ──────────┘
                                       │
Step 8 (ai_handler 리팩토링) ──────────┤
Step 9 (Config 이중화)       ──────────┤
Step 10 (인증 미들웨어)      ──────────┤
Step 11 (입력검증+셧다운)    ──────────┤
Step 12 (index.html 분리)    ──────────┘
```

**Step 1~4는 기반 작업** → 이게 끝나야 5~7 분리 가능
**Step 5~7은 핵심** → mini_server.py를 11,906줄 → 500줄로 줄임
**Step 8~12는 마무리** → 품질 향상

---

## 예상 결과

| 항목 | 현재 | 완료 후 |
|------|------|---------|
| `mini_server.py` | 11,906줄 | **~500줄** (라우터 등록만) |
| 전역 변수 | 44개 (Lock 없음) | **AppState 1개** (Lock 있음) |
| 중복 코드 | 24곳 브로드캐스트 | **헬퍼 1개** |
| 에러 핸들링 | `pass` 40곳 | **구체적 로깅** |
| 인증 | 1/55 엔드포인트 | **전체 미들웨어** |
| 모델명 관리 | 5곳 분산 | **config 2곳** |
| AI 호출 타임아웃 | 없음 | **120초 제한** |
| 메모리 누수 | 무한 증가 | **TTL 자동 정리** |

---

## 주의사항

1. **매 Step 완료 = 커밋 + 배포 + 서버 정상 확인** (깨진 상태로 넘어가지 않음)
2. **Step 실패 시**: 해당 Step만 롤백, 원인 분석 후 재시도
3. **새 기능 추가 금지**: 리팩토링 중에는 기능 추가 안 함 (코드 충돌 방지)
4. **대표님 확인 필요한 시점**: Step 5~7 완료 후 (서버 구조 대변경)
5. **컴팩(context compaction) 대비**: 이 문서가 GitHub에 있으므로 새 세션에서도 읽을 수 있음

---

## 이 문서 사용법 (Claude 세션용)

1. 새 세션 시작 시 이 파일 읽기: `docs/REFACTORING_PLAN.md`
2. 현재 어디까지 완료했는지 확인 (Step N 커밋 메시지)
3. 다음 Step 실행
4. 완료 시 이 문서의 해당 Step에 ✅ 표시 + 날짜 기록
