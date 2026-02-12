# CORTHEX HQ 변경 이력 (Changelog)

> 이 문서는 CORTHEX HQ의 버전별 변경 사항을 기록합니다.
> 노션에 붙여넣어 팀 기록으로 활용하세요.

---

## v0.4.0 (2026-02-12) - SNS 통합 퍼블리싱 시스템

> 상태: **구현 완료**

### 한 줄 요약

**Tistory·YouTube·Instagram·LinkedIn 4개 플랫폼에 콘텐츠를 자동으로 올릴 수 있는 SNS 퍼블리싱 시스템을 도입합니다. CEO 승인 후에만 발행되는 안전한 퍼블리싱 플로우입니다.**

---

### 왜 만들었나?

마케팅·고객처(CMO) 산하에 콘텐츠 Specialist와 커뮤니티 Specialist가 있지만,
실제로 SNS에 글을 올리려면 사람이 직접 각 플랫폼에 로그인해서 복붙해야 했습니다.

**기존 문제:**
- 콘텐츠 Specialist가 글을 "작성"만 할 수 있고, 실제 "발행"은 불가
- 각 플랫폼마다 별도 로그인 → 수동 작업 반복
- 발행 전 CEO 검수/승인 프로세스 없음

**목표:**
- 콘텐츠 작성 → CEO 승인 → 자동 발행의 **원스톱 파이프라인**
- 4개 플랫폼 통합 관리
- 잘못된 콘텐츠가 무단 발행되는 것을 CEO 승인으로 방지

---

### 뭘 만들었나?

#### 1. 전체 아키텍처

```
콘텐츠 Specialist ──(작성)──→ sns_manager(submit) ──→ 승인 큐
                                                         │
                         CEO ← 비서실장 보고 ←───────────┘
                          │
                     승인(approve) / 거절(reject)
                          │
                    CMO ──(publish)──→ sns_manager ──→ 실제 SNS 발행
                                          │
                              ┌────────────┼────────────┐─────────────┐
                           Tistory     YouTube     Instagram     LinkedIn
```

#### 2. CEO 승인 플로우 (핵심!)

| 단계 | 누가 | 뭘 하나 | 도구 호출 |
|------|------|---------|-----------|
| ① 작성 | 콘텐츠 Specialist | 블로그 글/SNS 포스트 작성 후 발행 요청 | `sns_manager(action=submit)` |
| ② 검토 | LLM (자동) | 콘텐츠를 CEO 보고용으로 자동 요약 | 내부 LLM 호출 |
| ③ 보고 | CMO → 비서실장 | CEO에게 "이런 콘텐츠를 올려도 될까요?" 보고 | 기존 에이전트 체인 |
| ④ 승인 | **CEO (사람)** | 대시보드 또는 API로 승인/거절 | `POST /api/sns/approve/{id}` |
| ⑤ 발행 | CMO | 승인된 건만 실제 퍼블리싱 실행 | `sns_manager(action=publish)` |

**권한 제어:**
- `submit` → 콘텐츠 Specialist, 커뮤니티 Specialist, CMO 모두 가능
- `approve/reject` → CEO만 가능 (웹 대시보드 / API)
- `publish` → **CMO 이상만** 실행 가능 (코드 레벨 강제)

#### 3. 지원 플랫폼 상세

| 플랫폼 | API | 기능 | 인증 방식 |
|--------|-----|------|-----------|
| **Tistory** | Tistory Open API | 글 작성/수정/삭제, 카테고리 관리, 태그 | Tistory OAuth (카카오 개발자) |
| **YouTube** | YouTube Data API v3 | 영상 업로드(Resumable), 메타데이터 수정, 공개 설정 | Google OAuth 2.0 |
| **Instagram** | Instagram Graph API v21.0 | 이미지 게시, 릴스(동영상), 캐러셀(여러 장), 해시태그 | Meta OAuth (비즈니스 계정) |
| **LinkedIn** | LinkedIn Marketing API v2 | 텍스트 포스트, 이미지 포스트, 링크 공유 | LinkedIn OAuth 2.0 |

#### 4. OAuth 토큰 관리자

> **쉽게 말하면:** 각 SNS의 "로그인 열쇠"를 안전하게 보관하고, 만료되면 자동으로 새 열쇠로 바꿔주는 시스템

| 기능 | 설명 |
|------|------|
| 토큰 저장 | `data/sns_tokens.json`에 JSON으로 저장 |
| 자동 갱신 | `refresh_token`으로 만료 1분 전 자동 갱신 |
| 인증 URL 생성 | 플랫폼별 OAuth 인증 URL 자동 생성 |
| 코드 교환 | 인증 완료 후 code → access_token 자동 교환 |
| 상태 조회 | 4개 플랫폼의 연결/만료 상태 한눈에 확인 |

**인증 흐름:**
```
① CEO가 대시보드에서 "Tistory 연결" 클릭
② GET /api/sns/auth/tistory → 인증 URL 반환
③ 브라우저에서 Tistory 로그인 + 권한 허용
④ Tistory가 /oauth/callback/tistory?code=xxx 로 리다이렉트
⑤ 서버가 code → access_token 교환 후 저장
⑥ "연결 완료!" 페이지 표시 → 이후 자동으로 글 올리기 가능
```

#### 5. Webhook 수신기

> **쉽게 말하면:** SNS에서 뭔가 일어나면 (댓글, 좋아요 등) 우리한테 자동으로 알려주는 전화기

| 플랫폼 | 수신 방식 | 이벤트 |
|--------|-----------|--------|
| YouTube | PubSubHubbub (Atom XML) | 새 영상, 댓글 알림 |
| Instagram | Graph API Webhook (JSON + HMAC 서명 검증) | 댓글, 멘션 |
| LinkedIn | Webhook (JSON) | 댓글, 반응 |
| Tistory | 커스텀 폴링 → Webhook 포맷 변환 | 방명록, 댓글 |

**보안:**
- Instagram Webhook은 `HMAC-SHA256` 서명 검증
- Webhook 구독 검증 (`hub.challenge`) 자동 처리

#### 6. 웹 API 엔드포인트 (CEO 대시보드용)

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/sns/status` | 4개 플랫폼 연결 상태 조회 |
| `GET` | `/api/sns/queue` | 발행 승인 큐 (대기/승인/발행/거절 분류) |
| `POST` | `/api/sns/approve/{id}` | CEO가 발행 요청 승인 |
| `POST` | `/api/sns/reject/{id}` | CEO가 발행 요청 거절 (사유 포함) |
| `GET` | `/api/sns/auth/{platform}` | OAuth 인증 URL 생성 |
| `GET` | `/oauth/callback/{platform}` | OAuth 콜백 (자동 토큰 교환) |
| `POST` | `/webhook/{platform}` | Webhook 이벤트 수신 |
| `GET` | `/webhook/{platform}` | Webhook 구독 검증 |
| `GET` | `/api/sns/events` | 최근 Webhook 이벤트 로그 |

---

### 수정된 파일 상세

#### 신규 파일 (9개)

| 파일 | 설명 | 줄 수 |
|------|------|-------|
| `src/tools/sns/__init__.py` | SNS 모듈 패키지 | 1 |
| `src/tools/sns/oauth_manager.py` | OAuth 토큰 관리자 (저장/갱신/교환/상태) | ~230 |
| `src/tools/sns/base_publisher.py` | 퍼블리셔 공통 인터페이스 (`PostContent`, `PublishResult`) | ~70 |
| `src/tools/sns/tistory_publisher.py` | Tistory API 연동 (글 작성/삭제/카테고리) | ~95 |
| `src/tools/sns/youtube_publisher.py` | YouTube Data API v3 (Resumable Upload) | ~170 |
| `src/tools/sns/instagram_publisher.py` | Instagram Graph API (이미지/릴스/캐러셀) | ~190 |
| `src/tools/sns/linkedin_publisher.py` | LinkedIn Marketing API (텍스트/이미지/링크) | ~200 |
| `src/tools/sns/sns_manager.py` | SNS 통합 도구 (승인 큐 + ToolPool 등록) | ~250 |
| `src/tools/sns/webhook_receiver.py` | Webhook 수신 및 이벤트 디스패치 | ~130 |

#### 수정 파일 (5개)

| 파일 | 변경 내용 |
|------|----------|
| `config/tools.yaml` | `sns_manager` 도구 정의 추가 |
| `config/agents.yaml` | CMO: 모델 gpt-4o 승격 + 퍼블리싱 권한 부여. 콘텐츠 Specialist: submit 권한 + 프롬프트에 SNS 플로우 안내. 커뮤니티 Specialist: 모니터링 역할 + sns_manager 도구 허용 |
| `src/tools/pool.py` | `SNSManager`를 ToolPool에 등록 (import + tool_classes 딕셔너리) |
| `web/app.py` | OAuth 콜백, 승인/거절 API, Webhook 수신 등 9개 엔드포인트 추가. `OAuthManager`, `WebhookReceiver` 초기화 |
| `.env.example` | Tistory/Google/Instagram/LinkedIn API 키 설정 템플릿 추가 |

---

### 조직 구조 변화

```
v0.3.0:                                    v0.4.0:
├── CMO 마케팅·고객처장                     ├── CMO 마케팅·고객처장 ← gpt-4o 승격!
│   ├── 설문/리서치                        │   ├── 설문/리서치
│   ├── 콘텐츠 (글만 작성)                 │   ├── 콘텐츠 ← submit 권한 추가
│   └── 커뮤니티 (전략만 수립)              │   └── 커뮤니티 ← 모니터링 권한 추가
│                                          │
│   (SNS 도구 없음)                        │   🆕 sns_manager 도구
│                                          │      ├── Tistory 퍼블리셔
│                                          │      ├── YouTube 퍼블리셔
│                                          │      ├── Instagram 퍼블리셔
│                                          │      ├── LinkedIn 퍼블리셔
│                                          │      ├── OAuth 토큰 관리자
│                                          │      └── Webhook 수신기
```

---

### 사용 방법 (퀵 스타트)

#### 1단계: API 키 설정

```bash
# .env 파일에 추가
TISTORY_CLIENT_ID=your-id
TISTORY_CLIENT_SECRET=your-secret
TISTORY_BLOG_NAME=your-blog
# ... (나머지 플랫폼도 동일)
```

#### 2단계: SNS 계정 연결 (OAuth)

```
브라우저에서 → http://localhost:8000/api/sns/auth/tistory
→ Tistory 로그인 → 권한 허용 → 자동 연결 완료!
(각 플랫폼별 1회만 수행)
```

#### 3단계: 콘텐츠 발행 프로세스

```
CEO: "LEET Master 소개 블로그 글 써서 Tistory에 올려줘"
  │
  ▼
비서실장 → CMO에게 배분 → 콘텐츠 Specialist가 글 작성
  │
  ▼
콘텐츠 Specialist → sns_manager(action=submit, platform=tistory, title=..., body=...)
  │
  ▼
CEO에게 보고: "이런 글을 올려도 될까요?" + 자동 요약
  │
  ▼
CEO가 승인: POST /api/sns/approve/abc123
  │
  ▼
CMO → sns_manager(action=publish, request_id=abc123)
  │
  ▼
✅ Tistory에 글 발행 완료!
```

---

### 향후 확장 가능

| 기능 | 설명 | 난이도 |
|------|------|--------|
| 예약 발행 | 특정 시간에 자동 발행 (cron 기반) | 중 |
| 멀티 플랫폼 동시 발행 | 한 콘텐츠를 4개 플랫폼에 동시 게시 | 낮 |
| 성과 분석 | 각 플랫폼의 조회수/좋아요/댓글 수집 | 중 |
| 대시보드 SNS 패널 | 웹 UI에 SNS 승인 큐 + 상태 패널 추가 | 중 |
| Twitter/X 추가 | Twitter API v2 연동 | 낮 |

---

### Git 커밋

| 커밋 | 설명 |
|------|------|
| `8308549` | feat: SNS 통합 퍼블리싱 시스템 구현 (Tistory/YouTube/Instagram/LinkedIn) |

---

## v0.3.0 (2026-02-12) - 본부 라벨 분리 (LEET Master / 투자분석)

> 상태: **구현 완료**

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

---

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
  "by_model": { ... },
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

#### 3. UI 변경 — 사이드바 플랫 구조 + 색상 변경

**사이드바 조직도:**
| v0.1.0 | v0.2.0 |
|--------|--------|
| 3단계 중첩 (본부 → 처 → 전문가) | **2단계 플랫** (처 → 전문가) |
| LEET MASTER 본부 접기/펼치기 존재 | 삭제 (각 처가 독립) |
| 금융분석 본부 접기/펼치기 존재 | 삭제 (CIO가 직접 표시) |

**에이전트 상태 표시 색상:**
| 상태 | v0.1.0 | v0.2.0 | 이유 |
|------|--------|--------|------|
| 대기중 (standby) | 🔘 회색 | 🟠 **앰버** | "준비됨"을 더 명확히 표현 |
| 작업중 (working) | 🟡 노랑 깜빡 | 🟢 **초록 깜빡** | "활발히 동작"을 직관적으로 |
| 완료 (done) | 🟢 초록 | 🟢 초록 (유지) | - |
| 유휴 (idle) | 🔘 회색 | 🟠 **앰버** | 대기중과 동일 |
| 비활성 (inactive) | 🔘 회색 | 🔘 회색 (유지) | - |

**JavaScript에서 삭제된 것들:**
- `agentNames`에서 `leet_master_head`, `finance_head` 제거
- `agentDivision`에서 `leet_master_head`, `finance_head` 제거
- `expanded` 객체에서 `leet` 섹션 제거
- `getSectionAgentIds()`에서 `leet` 분기 제거
- `handleWsMessage`에서 leet 자동 펼치기 로직 제거

---

### 수정된 파일 상세 (9개 파일, +168줄 / -241줄)

| 파일 | 변경 요약 | 상세 |
|------|-----------|------|
| `config/agents.yaml` | 본부장 삭제, 비서실장 확장 | `leet_master_head`, `finance_head` 정의 삭제. `chief_of_staff`에 5개 처장을 subordinate로 추가. 처장들의 `superior_id`를 `chief_of_staff`로 변경 |
| `src/core/orchestrator.py` | LLM 분류 호출 제거 | `_classify_command()`(LLM으로 명령 분류) 삭제. 모든 명령을 `chief_of_staff`에게 직행. `_parse_json()` 삭제 |
| `src/core/registry.py` | 조직도 조회 수정 | `list_division_heads()`: 비서실장 직속 manager만 반환하도록 조건 변경 |
| `src/core/agent.py` | agent_id 전파 | `think()`, `_summarize()`에서 `agent_id=self.agent_id`를 router에 전달 |
| `src/llm/router.py` | agent_id 파라미터 추가 | `complete()`에 `agent_id` 파라미터 추가, `cost_tracker.record()`에 전달 |
| `src/llm/cost_tracker.py` | 비용 분석 메서드 추가 | `CostRecord`에 `agent_id` 필드 추가. `summary_by_agent()`, `summary_by_provider()` 메서드 추가 |
| `web/templates/index.html` | 사이드바 + JS 전면 수정 | HTML: 본부 wrapper 제거, 플랫 구조. JS: 본부장 참조 제거, 색상 변경, leet 관련 로직 삭제 |
| `web/app.py` | API 응답 확장 + 버전 업 | `/api/cost`에 `by_agent`, `by_provider` 추가. FastAPI 버전 `0.2.0` |
| `src/cli/app.py` | CLI 조직도 + 버전 업 | `_show_org_chart()` 본부장 레이어 제거. 배너 `v0.2.0` |

---

### 예상 효과

| 항목 | 수치 |
|------|------|
| 명령당 LLM 호출 절감 | **1~2회** (본부장 분류 + 종합 제거) |
| 명령당 비용 절감 | 약 **$0.002~0.005** (gpt-4o 1회 기준) |
| 명령 처리 시간 단축 | 본부장 처리 대기 시간 제거 |
| 비용 추적 세분화 | 모델별 → 모델별 + **에이전트별** + **프로바이더별** |

---

## v0.1.0 (2026-02-12) - 최초 릴리즈

> 상태: **배포 완료 (현재 버전)**

### 무엇이 만들어졌나요?

한 줄 요약: **CORTHEX HQ 멀티 에이전트 시스템의 첫 번째 버전. 25명의 AI 에이전트가 CEO 명령을 자동 처리합니다.**

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
- 조직도 트리 표시
- 비용 요약 테이블
- 마크다운 결과 렌더링

#### 6. 멀티 LLM 지원
- OpenAI (gpt-4o, gpt-4o-mini) 지원
- Anthropic (claude-sonnet-4-5-20250929) 지원
- 모델명 prefix로 자동 프로바이더 라우팅
- 에이전트별 독립적인 모델 설정 가능

#### 7. 지식 관리 시스템
- `knowledge/` 디렉토리의 .md 파일을 에이전트 system_prompt에 자동 주입
- 부서(division)별 지식 매칭
- 서버 시작 시 1회 로딩

#### 8. 도구(Tool) 시스템
- 변리사, 세무사, 디자이너, 번역가, 웹검색 5개 Tool
- 에이전트별 허용 도구 제한 (`allowed_tools`)
- 권한 없는 도구 호출 시 `ToolPermissionError`

#### 9. 비용 추적
- 모든 LLM 호출의 토큰 사용량 및 비용 자동 기록
- 모델별 비용 요약 (`summary_by_model()`)
- CLI `비용` 명령어 및 `/api/cost` 엔드포인트

### 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| 언어 | Python 3.11+ |
| 웹 프레임워크 | FastAPI |
| 실시간 통신 | WebSocket |
| 프론트엔드 | Tailwind CSS + Alpine.js |
| CLI | Rich |
| 설정 관리 | YAML + Pydantic |
| LLM 통신 | httpx (async) |

### 프로젝트 구조

```
CORTHEX_HQ/
├── config/
│   ├── agents.yaml          # 에이전트 설정 (25명)
│   └── tools.yaml           # 도구 설정 (5개)
├── knowledge/               # 부서별 지식 파일
├── src/
│   ├── core/
│   │   ├── orchestrator.py  # CEO 명령 라우터
│   │   ├── agent.py         # 에이전트 기본 클래스 (Manager/Specialist/Worker)
│   │   ├── registry.py      # 에이전트 팩토리 + 레지스트리
│   │   ├── context.py       # 공유 컨텍스트 (대화 기록, 상태 콜백)
│   │   ├── message.py       # 메시지 타입 (TaskRequest, TaskResult, StatusUpdate)
│   │   ├── knowledge.py     # 지식 관리자
│   │   └── errors.py        # 커스텀 예외
│   ├── llm/
│   │   ├── base.py          # LLMProvider 추상 클래스 + LLMResponse
│   │   ├── router.py        # 모델 라우터 (OpenAI/Anthropic 자동 분기)
│   │   ├── openai_provider.py
│   │   ├── anthropic_provider.py
│   │   └── cost_tracker.py  # 비용 추적
│   ├── tools/               # 도구 구현체 (5개)
│   ├── divisions/           # 부서별 커스텀 로직 (선택적)
│   └── cli/
│       └── app.py           # Rich CLI 인터페이스
├── web/
│   ├── app.py               # FastAPI 웹 서버
│   ├── ws_manager.py        # WebSocket 매니저
│   └── templates/
│       └── index.html       # CEO 관제실 SPA
├── main.py                  # CLI 진입점
├── main_web.py              # 웹 서버 진입점
└── .env                     # API 키 설정
```

### Git 커밋 이력

| 커밋 | 설명 |
|------|------|
| `436e915` | Initial commit |
| `a03c1b7` | feat: CORTHEX HQ 멀티 에이전트 시스템 전체 구현 |
| `4ece0c0` | feat: CEO 관제실 웹 UI + 지식 관리 시스템 + 원클릭 설치 |
| `ccd31a5` | ci: claude 브랜치 → main 자동 머지 워크플로우 추가 |
| `cb09825` | docs: README.md 상세 사용 설명서로 전면 개편 |

---

## 버전 관리 규칙

- **MAJOR** (x.0.0): 시스템 아키텍처 대폭 변경
- **MINOR** (0.x.0): 새 기능 추가 또는 기존 기능 개편
- **PATCH** (0.0.x): 버그 수정, 문서 수정, 소규모 개선
