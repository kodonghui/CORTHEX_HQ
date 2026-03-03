---
stepsCompleted: [step-01-init, step-02-context, step-03-starter, step-04-decisions, step-05-patterns, step-06-structure, step-07-validation, step-08-complete]
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/product-brief-CORTHEX_HQ-2026-03-02.md
  - docs/project-status.md
  - docs/ceo-ideas.md
  - CONTEXT.md
workflowType: 'architecture'
project_name: 'CORTHEX_HQ v2'
user_name: 'Elddl'
date: '2026-03-03'
---

# Architecture Decision Document — CORTHEX v2

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
- FR 11개 그룹, 50개+ 개별 기능
- **핵심 아키텍처 드라이버**: CLI 격리 (FR-3.4~3.7), 멀티테넌시 (FR-2.3), 에이전트 메모리 (FR-3.3), 비서 오케스트레이션 (FR-4), 야간 작업 큐 (FR-7)
- **두 개의 독립 앱**: 관리자 콘솔 (FR-1) + 유저 앱 (FR-2~11) — 별도 URL, 별도 인증

**Non-Functional Requirements:**
- 동시 접속 5명, WebSocket 5개, 채팅 3초, 페이지 2초
- 테넌트 격리 자동화 테스트 100%
- API key AES-256 암호화
- Oracle Cloud ARM 서버 (v1과 동일)

**Scale & Complexity:**
- Primary domain: Full-stack SaaS (관리자 + 유저 앱)
- Complexity: High
- 아키텍처 컴포넌트: 15개

### 아키텍처 컴포넌트 목록 (Party Mode 확정)

1. 관리자 콘솔 (React + Vite 프론트엔드)
2. 유저 앱 (React + Vite 프론트엔드)
3. API 서버 (Bun + Hono)
4. WebSocket 서버
5. 인증 모듈 (JWT)
6. 테넌트 격리 미들웨어
7. CLI 매니저 (Claude CLI 프로세스 관리)
8. 에이전트 오케스트레이터 (비서/위임-보고)
9. 에이전트 메모리 서비스
10. 작업 큐 (야간 작업)
11. 보고서/문서 서비스
12. 도구 레지스트리
13. PostgreSQL DB
14. 파일 스토리지
15. 자동화 테스트 러너

### Technical Constraints & Dependencies

| 제약 | 영향 |
|------|------|
| Oracle Cloud ARM 4코어 24GB | v1과 v2 공존. 포트 분리 + Nginx 리버스 프록시 |
| TypeScript (Bun + Hono) | 풀스택. Bun ARM64 지원됨 |
| React + Vite | 프론트엔드. Next.js 아님 (SSR/SEO 불필요) |
| Claude CLI Max 구독 | 에이전트 실행 전제. CLI 프로세스 관리 필요 |
| PostgreSQL | v1 SQLite → v2 PostgreSQL 전환 |
| Tailwind CSS | 빌드 포함 (CDN 아님) |

### v1/v2 공존 전략 (Party Mode 확정)

**개발 중:**
```
Oracle Cloud ARM (24GB)
├── v1: Python/FastAPI — 포트 8000 → corthex-hq.com
├── v2: TypeScript/Bun — 포트 3000 → v2.corthex-hq.com
├── PostgreSQL — 포트 5432 (v2 전용)
└── Nginx 리버스 프록시 — 도메인별 라우팅
```

메모리 배분:
- v1 Python: ~2GB
- v2 Bun: ~1GB
- PostgreSQL: ~2GB
- Nginx + OS: ~1GB
- 여유: ~18GB → 충분

**P3 완료 후 (도메인 전환):**
```
corthex-hq.com       → v2 유저 앱
admin.corthex-hq.com → v2 관리자 콘솔
v1.corthex-hq.com    → v1 백업 (이후 종료)
```
Cloudflare DNS 레코드 전환. 5분.

### Cross-Cutting Concerns

| 관심사 | 영향 범위 |
|--------|-----------|
| **테넌트 격리** | 모든 API, DB 쿼리, WebSocket, 파일 저장 |
| **CLI 토큰 관리** | 에이전트 실행, 채팅, 야간 작업, 협업 |
| **인증/세션** | 관리자 콘솔 + 유저 앱 두 곳 |
| **실시간 통신** | 채팅, 에이전트 상태, 알림, 사내 메신저 |
| **에이전트 메모리** | 채팅 히스토리, 작업 로그, 세션 연속성 |

### 프론트엔드 기술 결정 (Party Mode 확정)

| 항목 | 결정 | 이유 |
|------|------|------|
| 프레임워크 | **React + Vite** | 실시간 채팅, 복잡한 상태 관리, TS 풀스택 통일, 에코시스템 |
| Next.js | **사용 안 함** | SSR/SEO 불필요 (로그인 후 사용 앱) |
| 스타일링 | **Tailwind CSS** (빌드 포함) | v1과 동일 디자인 언어, 유틸리티 퍼스트 |
| 관리자 콘솔 | React + Vite | CRUD 위주. 유저 앱과 컴포넌트 공유 가능 |
| 유저 앱 | React + Vite | 채팅 + 실시간 + 에이전트 상태 |

## Starter Template Decision

### 기반 참조

| 항목 | 결정 |
|------|------|
| **참조 템플릿** | [bun-hono-react-monorepo](https://github.com/hbinduni/bun-hono-react-monorepo) — 레퍼런스만. 직접 세팅 |
| **런타임** | Bun |
| **백엔드** | Hono |
| **프론트엔드** | React 19 + Vite 7 |
| **DB** | PostgreSQL + **Drizzle ORM** (Prisma 아님. Bun 궁합 + 가벼움 + SQL에 가까움) |
| **스타일** | Tailwind CSS 4 (빌드 포함) |
| **모노레포** | Turborepo |

### 모노레포 패키지 구조 (Party Mode 확정)

```
corthex-v2/
├── packages/
│   ├── admin/        → 관리자 콘솔 (React + Vite)
│   ├── app/          → 유저 앱 (React + Vite)
│   ├── server/       → API 서버 (Bun + Hono)
│   ├── shared/       → 공유 타입 (TypeScript 인터페이스)
│   └── ui/           → 공유 UI 컴포넌트 (버튼, 테이블 등)
├── turbo.json
├── package.json
└── bun.lockb
```

### 프로젝트 초기화 방법

`bun create` + Hono 공식 스타터로 깨끗하게 시작. 스타터 템플릿은 구조 참고만.

### 추가 구축 필요 (스타터에 없는 것)

- WebSocket 서버
- CLI 매니저 (Claude CLI 프로세스 관리)
- 테넌트 격리 미들웨어
- 에이전트 오케스트레이터 (비서/위임-보고)
- 에이전트 메모리 서비스
- 작업 큐 시스템 (야간 작업)
- 자동화 격리 테스트

## Core Architectural Decisions

### 전체 기술 스택 요약

```
TypeScript 풀스택 (Bun 런타임)
├── 프론트엔드: React 19 + Vite 7 + Tailwind CSS 4
├── 백엔드: Hono (API + WebSocket)
├── DB: PostgreSQL + Drizzle ORM
├── 작업 큐: pg-boss (PostgreSQL 기반, Redis 불필요)
├── 인증: Hono 내장 JWT (Better Auth 불필요)
├── 상태 관리: Zustand + TanStack Query
├── 모노레포: Turborepo
└── 인프라: Oracle Cloud ARM + Nginx + GitHub Actions
```

### Decision 1: 인증 — Hono 내장 JWT

| 항목 | 결정 |
|------|------|
| 방식 | `hono/jwt` 미들웨어 |
| 이유 | 소셜 로그인 불필요 (ID/PW만). 외부 의존성 최소화 |
| 관리자 | 별도 JWT (admin 전용 토큰, 별도 시크릿) |
| 유저 | ID/PW → JWT 발급 → HttpOnly 쿠키 저장 |
| API key 저장 | AES-256 암호화 |

### Decision 2: API 패턴 — REST

| 항목 | 결정 |
|------|------|
| 방식 | REST API |
| 이유 | v1도 REST. GraphQL은 과도함. 학습 비용 0 |
| 문서화 | Hono OpenAPI 미들웨어로 자동 생성 |
| 에러 처리 | 표준 HTTP 상태 코드 + 구조화된 에러 응답 |

### Decision 3: 프론트엔드 상태 관리 — Zustand + TanStack Query

| 항목 | 결정 |
|------|------|
| 클라이언트 상태 | **Zustand** — 가볍고 직관적. 보일러플레이트 최소 |
| 서버 상태 | **TanStack Query** — API 데이터 캐싱, 자동 리페칭, 로딩/에러 상태 |
| 이유 | Redux는 과도함. Zustand(2KB) + TanStack Query 조합이 2026년 표준 |

### Decision 4: WebSocket — Hono 내장

| 항목 | 결정 |
|------|------|
| 방식 | Hono WebSocket (내장) |
| 용도 | 채팅 스트리밍, 에이전트 상태, 알림, 사내 메신저 |
| 격리 | WebSocket 연결 시 JWT 검증 → 유저별 채널 분리 |

### Decision 5: 작업 큐 — pg-boss (Party Mode 수정)

| 항목 | 결정 |
|------|------|
| 방식 | **pg-boss** (PostgreSQL 기반 작업 큐) |
| 이유 | Redis 불필요. 인프라 심플화 (PostgreSQL 하나로 DB + 큐 통합) |
| 용도 | 야간 작업, 예약 작업, 실패 재시도 |
| 규모 | 5명 동시 유저에 충분. 초당 수천 건 불필요 |

### 인프라 심플화 (Party Mode 확정)

```
변경 전: PostgreSQL + Redis (2개 서비스)
변경 후: PostgreSQL만 (1개 서비스)
  └── DB + 작업 큐(pg-boss) + 세션 통합
```

### Decision Impact Analysis

**구현 순서:**
1. PostgreSQL + Drizzle 세팅
2. Hono API + JWT 인증
3. WebSocket 서버
4. React 프론트엔드 (admin + app)
5. CLI 매니저
6. 에이전트 오케스트레이터
7. pg-boss 작업 큐
8. 테넌트 격리 미들웨어 + 자동화 테스트

**Cross-Component Dependencies:**
- 테넌트 격리 → 모든 API, DB 쿼리, WebSocket에 적용
- JWT 인증 → API + WebSocket 양쪽
- Drizzle 스키마 → `shared/` 패키지에서 타입 공유

## Implementation Patterns & Consistency Rules

### 네이밍 규칙

| 대상 | 규칙 | 예시 |
|------|------|------|
| DB 테이블 | snake_case, 복수형 | `users`, `agents`, `chat_messages` |
| DB 컬럼 | snake_case | `company_id`, `cli_token`, `created_at` |
| API 엔드포인트 | kebab-case, REST 명사 | `/api/agents`, `/api/chat-messages` |
| TS 변수/함수 | camelCase | `getAgentsByUser()`, `cliToken` |
| TS 타입/인터페이스 | PascalCase | `Agent`, `ChatMessage`, `UserProfile` |
| React 컴포넌트 | PascalCase | `ChatWindow`, `AgentCard` |
| 파일명 | kebab-case | `chat-window.tsx`, `agent-service.ts` |
| 환경변수 | SCREAMING_SNAKE | `DATABASE_URL`, `JWT_SECRET` |

### 테넌트 격리 패턴

```typescript
// TenantContext — 모든 핸들러에 자동 주입 (미들웨어)
type TenantContext = {
  companyId: string
  userId: string
  cliTokenId: string
  role: 'admin' | 'user'
}

// 모든 DB 쿼리에 company_id + user_id 필터 필수
// ctx.companyId 없이 DB 접근 = TypeScript 컴파일 에러로 차단
```

### API 응답 패턴

```typescript
// 성공
{ data: T, meta?: { page, total } }

// 에러
{ error: { code: string, message: string, details?: any } }
```

### 에러 코드 표준 (Party Mode 추가)

```
AUTH_001: 로그인 실패
AUTH_002: 토큰 만료
AUTH_003: 권한 없음
TENANT_001: 격리 위반 시도
TENANT_002: 다른 회사 데이터 접근 차단
AGENT_001: CLI 연결 끊김
AGENT_002: 에이전트 실행 실패
AGENT_003: 에이전트 메모리 로드 실패
QUEUE_001: 야간 작업 실패
QUEUE_002: 재시도 한도 초과
```

### 에이전트 실행 패턴

```typescript
// CLI 격리: 반드시 해당 유저의 CLI 토큰으로 실행
async function executeAgent(agentId: string, ctx: TenantContext) {
  const cliToken = await getCliToken(ctx.userId)  // 유저별 토큰
  // NEVER use another user's token
}
```

### DB 스키마 핵심 테이블 (Party Mode 추가)

```
P1 테이블 (12개):
companies        → 회사. 테넌트 최상위 단위
users            → 인간 유저 (CEO, H). company_id 필수
agents           → AI 에이전트. company_id + user_id 필수
departments      → 부서. company_id 필수
cli_credentials  → CLI 토큰 (AES-256 암호화). user_id 필수
api_keys         → 개인 API key (암호화). user_id 필수
chat_sessions    → 채팅 세션. user_id + agent_id
chat_messages    → 채팅 메시지 히스토리. session_id
agent_memory     → 에이전트 장기 기억. agent_id
tools            → 도구 정의 (플랫폼/회사/본부 레벨)
agent_tools      → 에이전트-도구 매핑
report_lines     → 보고 라인 (H → 상위자). company_id

모든 테이블에 company_id 컬럼 필수 (테넌트 격리)
```

### 파일 구조 패턴

```
packages/server/src/
├── routes/           → API 라우터 (Hono)
│   ├── auth.ts
│   ├── agents.ts
│   ├── chat.ts
│   └── admin/        → 관리자 전용 라우트
├── middleware/        → 미들웨어
│   ├── auth.ts       → JWT 검증
│   ├── tenant.ts     → 테넌트 격리 (TenantContext 주입)
│   └── error.ts      → 에러 핸들링
├── services/         → 비즈니스 로직
│   ├── agent-service.ts
│   ├── chat-service.ts
│   └── cli-manager.ts
├── db/               → Drizzle 스키마 + 마이그레이션
│   ├── schema.ts
│   └── migrations/
└── ws/               → WebSocket 핸들러
    └── chat-ws.ts
```

## Validation

### 아키텍처 검증 체크리스트

- [ ] 모든 API에 테넌트 격리 미들웨어 적용 확인
- [ ] WebSocket 연결 시 JWT 검증 확인
- [ ] CLI 토큰 격리 테스트 (유저 A의 에이전트가 유저 B CLI 사용 불가)
- [ ] DB 스키마 모든 테이블에 company_id 존재 확인
- [ ] 에러 코드 표준 적용 확인
- [ ] 모노레포 빌드 (turbo build) 성공 확인
- [ ] v1/v2 동시 운영 (포트 분리) 확인
