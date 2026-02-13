# CONTEXT.md

내용을 입력하세요.
# LEET MASTER 프로젝트 컨텍스트

> 마지막 업데이트: 2026-02-08 19:30 KST
> 담당 개발자: Claude (Genspark AI Developer)

---

## 1. 프로젝트 개요

### 목적
LEET(법학적성시험) 추리논증 영역 학습 플랫폼

### 사용자 시나리오
1. 사용자가 회원가입/로그인
2. 연도별 문제 풀이 (715문제, 전개)
3. 풀이 후 AI 피드백 요청 (간단/상세/심층)
   - **풀이과정 및 질문 작성** — 풀이 + 질문 모두 가능 ⭐ 신규
   - **공동 학습 피드백** — 다른 학습자 풀이 참고 옵션 ⭐ 신규
4. 심층 분석은 Batch API로 비동기 처리 (30% 할인)
5. **나의 진단** — 최근 10~30문제 기반 학습 패턴/약점/강점 분석 (Batch API) ⭐ 신규
6. 통계 확인, 오답노트, 풀이기록 관리
7. 관리자: 문제 업로드, 사용자 크레딧 관리, AI 피드백 설정, Batch 모니터링

### 핵심 가치
- 고품질 AI 피드백 (GPT-4o-mini, GPT-4o, GPT-5.2 활용)
- **공동 학습 피드백** — 다른 학습자 풀이 참고 옵션 ⭐
- **나의 진단** — 학습 패턴/약점/강점 분석 (LEET 특화) ⭐
- 크레딧 기반 과금 시스템 + Batch API 30% 할인
- 학습 통계 및 분석
- Cloudflare Cron Worker 기반 완전 자동화

---

## 2. 기술 스택

| 구분 | 기술 |
|------|------|
| **Backend** | Hono (TypeScript) on Cloudflare Workers |
| **Database** | Cloudflare D1 (SQLite) |
| **Frontend** | Vanilla JS + TailwindCSS (CDN) |
| **배포** | Cloudflare Pages |
| **AI** | OpenAI API (gpt-4o-mini, gpt-4o, gpt-5.2) |
| **Cron** | Cloudflare Workers (leet-master-cron) — 5분 주기 |

---

## 3. 실행 방법

### 로컬 개발
```bash
cd /home/user/webapp
npm run build                    # Vite 빌드
pm2 start ecosystem.config.cjs   # 개발 서버 시작 (port 3000)
```

### 배포
```bash
npm run build
npx wrangler pages deploy dist --project-name leet-master
```

### DB 마이그레이션
```bash
# 로컬
npx wrangler d1 migrations apply leet-master-db --local

# 프로덕션
npx wrangler d1 migrations apply leet-master-db --remote
```

### 환경변수/시크릿
```bash
npx wrangler pages secret put OPENAI_API_KEY --project-name leet-master
npx wrangler pages secret put OPENAI_BASE_URL --project-name leet-master
```

---

## 4. 폴더 구조

```
/home/user/webapp/
├── src/
│   ├── index.tsx           # 메인 Hono 앱 (라우터 + JWT 미들웨어)
│   ├── routes/
│   │   ├── auth.ts         # 인증 (로그인, 회원가입, settings/ui, profile)
│   │   ├── problems.ts     # 문제 API
│   │   ├── answers.ts      # 답안 제출
│   │   ├── stats.ts        # 통계 API
│   │   ├── feedback.ts     # AI 피드백 API ⭐ + 로그 조회/삭제/내보내기
│   │   ├── ai-analysis.ts  # AI 해설 페이지 (batchInfo 포함)
│   │   ├── batch.ts        # Batch API 전체 (요청/처리/Cron/관리자)
│   │   ├── admin.ts        # 관리자 API
│   │   ├── review.ts       # 복습 API
│   │   ├── payments.ts     # 결제 API
│   │   └── upload.ts       # 문제 업로드
│   ├── lib/
│   │   └── auth.ts         # JWT + 비밀번호 해싱 (Web Crypto SHA-256)
│   └── types/
│       └── index.ts        # TypeScript 타입 정의
├── public/
│   └── static/
│       └── app.js          # 프론트엔드 (7500줄+)
├── migrations/             # D1 마이그레이션 SQL (0001~0013)
├── wrangler.jsonc          # Cloudflare 설정
├── package.json
├── ecosystem.config.cjs    # PM2 설정
├── context.md              # 이 파일
└── STATUS.md               # 운영 상태 요약
```

---

## 5. 중요 결정사항 (ADR)

### ADR-001: AI 피드백 레벨 시스템
- **결정**: 3단계 피드백 (simple → gpt-4o-mini, detailed → gpt-4o, deep → gpt-5.2 Batch)
- **구현**: DB `feedback_level_settings` 테이블로 레벨별 모델/토큰/프롬프트 관리

### ADR-002: 크레딧 시스템
- **결정**: 토큰 기반 크레딧 차감 (10토큰 = 1크레딧, 마진율 2.0)
- **구현**: `users.credits` 컬럼, `credit_transactions` 로그 테이블
- **Batch 할인**: 심층 분석은 30% 할인 (BATCH_DISCOUNT_RATE = 0.3)

### ADR-003: Batch API 방식
- **결정**: OpenAI Batch API + Cloudflare Cron Worker (5분 폴링)
- **이유**: Workers 30초 제한 → 긴 대기 불가, Cron 폴링이 최적
- **크레딧 정책**: 사전 홀드 → 성공 시 실제 차감 + 차액 환불 → 실패 시 전액 환불

### ADR-004: GPT-5 계열 파라미터
- **결정**: `max_completion_tokens` 사용, `temperature` 제거, `reasoning_effort` 지원

### ADR-005: Cron 보안
- **결정**: dashboard API에서 토큰 마스킹, 전체 토큰은 별도 `/admin/token/copy` API로만 접근
- **UI**: 외부 Cron 안내를 `<details>` 접기로 처리, curl 예시에 `<YOUR_TOKEN>` 플레이스홀더

---

## 6. 현재 구현 상태

### ✅ 완료 (2026-02-06 기준)
- [x] 사용자 인증 (JWT) — /api/auth/settings/*, /api/auth/profile에 JWT 미들웨어 적용
- [x] 문제 CRUD (715문제, 전개년)
- [x] 답안 제출 및 채점
- [x] AI 피드백 (간단/상세 실시간, 심층 Batch)
- [x] Batch API 시스템 (batch_requests, batch_jobs, cron_runs)
- [x] Cron Worker 운영 (5분 주기 자동 처리)
- [x] Cron 보안 하드닝 (토큰 마스킹, 로그 기록, 30분 경고)
- [x] 통계 (정답률, 연도별, 오답노트)
- [x] 관리자 페이지 (문제 업로드, 크레딧 지급, 피드백 설정, Batch 대시보드)
- [x] 크레딧 시스템 + Batch 30% 할인
- [x] GPT-5.2 + reasoning_effort 지원
- [x] 글자크기 사용자 설정 (DB 저장 + 로컬 폴백)
- [x] AI 해설 페이지에 배치 상태 분기 (처리중/완료/실패 표시)
- [x] feedback_logs에 source 컬럼 (realtime/batch 구분) + 필터 탭
- [x] completed_no_output 대응: error_file_id 다운로드 + 2시간 초과 시 failed 전환 + 환불
- [x] 로그인 직후 배치 알림 표시 (loadBatchStatus → render 호출)

### ❌ 미구현/TODO
- [ ] **풀이과정 및 질문** — UI 레이블 변경, 질문 포함 가능, AI 프롬프트 수정 (1시간)
- [ ] **공동 학습 피드백** — 같은 문제의 다른 학습자 풀이 참고 (4~6시간)
- [ ] **나의 진단** — 최근 10~30문제 기반 학습 패턴/약점/강점 분석 (Batch API, LEET 특화, 10~15시간)
- [ ] 배치 알림 즉시 표시 고도화 (인앱 알림 시스템)
- [ ] favicon 개선 (저울 아이콘 선명화)
- [ ] 수익분석 중복 정리 (크레딧/결제 메뉴)
- [ ] 이메일 인증 시스템
- [ ] 결제 시스템 고도화

---

## 7. DB 테이블 (24개)

| 테이블 | 용도 |
|--------|------|
| users | 사용자 (email, password_hash, credits, is_admin, ui_font_scale) |
| problems | 문제 (year, problem_number, passage, question, options, answer) |
| answers | 사용자 답안 (selected_answer, is_correct, ai_feedback, batch_status, **user_explanation: 풀이과정 및 질문**) |
| answer_history | 풀이 이력 |
| feedback_logs | AI 피드백 로그 (**source: realtime/batch/community**) |
| feedback_level_settings | 수준별 프롬프트/모델 설정 |
| feedback_settings | 전역 피드백 설정 (enabled, api_key) |
| ai_feedback_logs | AI 피드백 부가 로그 |
| ai_explanation_unlocks | AI 해설 잠금해제 기록 |
| ai_bookmarks | AI 해설 북마크 |
| batch_requests | Batch 개별 요청 (pending→submitted→completed/failed) |
| batch_jobs | Batch 단위 job (submitted→in_progress→completed, **model_used 컬럼 추가 2026-02-07**) |
| cron_runs | Cron 실행 로그 (endpoint, success, message, duration_ms) |
| system_tokens | 시스템 토큰 (batch_cron_token) |
| system_settings | 시스템 설정 |
| credit_transactions | 크레딧 거래 로그 |
| credit_products | 크레딧 상품 |
| payment_requests | 결제 요청 |
| review_status | 복습 상태 |
| invite_codes | 초대코드 |
| announcements | 공지사항 |
| api_pricing | API 가격 정보 |
| d1_migrations | 마이그레이션 이력 |
| learning_reports | **나의 진단 결과** (user_id, analysis_type, report_text, model, tokens, cost) ⭐ 예정 |

### 마이그레이션 이력
- 0001~0010: 기본 스키마, 배치, UI 설정
- **0011_cron_runs.sql**: cron_runs 테이블 생성
- **0012_feedback_log_source.sql**: feedback_logs에 source 컬럼 추가 (realtime/batch)
- **0013_batch_jobs_model_used.sql**: batch_jobs에 model_used 컬럼 추가 (실제 사용 모델명 저장)
- **0014_learning_reports.sql** (예정): learning_reports 테이블 생성 (나의 진단 결과 저장)

---

## 8. Batch API 시스템

### A. 아키텍처
- **메인 앱**: leet-master (Cloudflare Pages)
- **Cron Worker**: leet-master-cron (Cloudflare Workers, 5분 주기)
- **DB 테이블**: batch_requests, batch_jobs, system_tokens, cron_runs

### B. Status 전이도

**batch_requests:** `pending → submitted → completed / failed`
**batch_jobs:** `submitted → validating → in_progress → finalizing → completed / failed / expired / cancelled`

### C. 크레딧 정책: 사전 홀드 + 자동 환불

| 시점 | 동작 |
|------|------|
| 요청 시 | 사전 차감 (reserve) |
| 성공 시 | 실제 사용량 기준 차감 + 차액 환불 (use) |
| 실패 시 | 전액 환불 (refund) |
| 취소 시 | 전액 환불 + 요청 삭제 |

### D. completed_no_output 대응 (2026-02-06)
- OpenAI가 completed 반환했으나 output_file_id가 null인 경우
- **error_file_id 우선 시도**: 에러 파일이 있으면 다운로드 → 실패 처리 + 환불
- **2시간 초과**: submitted_at 기준 2시간 경과 시 failed 전환 + 환불
- **그 외**: 다음 5분 크론 사이클에서 재시도

### E. 엔드포인트

| 경로 | 메서드 | 인증 | 설명 |
|------|--------|------|------|
| /api/batch | POST | JWT | 심층분석 예약 요청 |
| /api/batch/status | GET | JWT | 내 요청 상태 조회 |
| /api/batch/:id | DELETE | JWT | pending 취소+환불 |
| /api/batch/admin/process | POST | JWT(admin) | 관리자 수동 제출 |
| /api/batch/admin/check | POST | JWT(admin) | 관리자 수동 결과 확인 |
| /api/batch/admin/dashboard | GET | JWT(admin) | 대시보드 (마스킹) |
| /api/batch/admin/token/regenerate | POST | JWT(admin) | Cron 토큰 재생성 |
| /api/batch/admin/token/copy | POST | JWT(admin) | Cron 토큰 전체 조회 |
| /api/batch/cron/process | POST | Cron 토큰 | 자동 제출 |
| /api/batch/cron/check | POST | Cron 토큰 | 자동 결과 확인 |

### F. Cron Worker
- **URL**: https://leet-master-cron.elddlwkd.workers.dev
- **스케줄**: `*/5 * * * *`
- **Secrets**: CRON_TOKEN
- **수동 확인**: GET /health, POST /run-once (Bearer 토큰 필요)

---

## 9. 절대 바꾸면 안 되는 제약

### API 계약
- `/api/auth/me` 응답에 `credits` 필드 필수
- `/api/feedback` 응답에 `success`, `feedback`, `credits_remaining` 필수
- 인증: JWT Bearer 토큰 방식 유지

### 보안
- API 키는 환경변수/시크릿으로만 관리 (코드에 하드코딩 금지)
- 관리자 API는 `is_admin=1` 검증 필수
- Cron 토큰은 DB에서만 관리, dashboard API에서 마스킹
- feedback_logs에 배치 결과 기록 시 source='batch' 명시

### 데이터베이스
- `users.credits`: INTEGER, 기본값 0
- `feedback_logs`: 모든 피드백 요청 로깅 필수 (source 컬럼 포함)
- `cron_runs`: 매 Cron 실행 기록 필수

### 프론트엔드
- TailwindCSS CDN 사용 (빌드 없음)
- FontAwesome 아이콘 CDN 사용
- state 패턴 (SPA 라우팅)

---

## 10. 주요 URL

| 구분 | URL |
|------|-----|
| **Production** | https://leet-master.pages.dev |
| **최신 Preview** | https://6bdd567f.leet-master.pages.dev |
| **GitHub** | https://github.com/kodonghui/leet-master |
| **Cron Worker** | https://leet-master-cron.elddlwkd.workers.dev |

---

## 11. 최근 변경 사항 (2026-02-06 후반)

### 옵션 3 구현 — 6개 이슈 일괄 수정

| 이슈 | 파일 | 변경 내용 |
|------|------|----------|
| (1) 로그인 후 배치 알림 안 뜸 | app.js | loadBatchStatus() 후 render() 호출 추가 |
| (5) 글자크기 Unauthorized | index.tsx | JWT 미들웨어를 /api/auth/settings/*, /api/auth/profile에 추가 |
| (4-D) completed_no_output | batch.ts | error_file_id 우선 처리 + 2시간 초과 시 failed 전환 + 환불 |
| (4-A) 처리중 클릭 시 상태 미표시 | ai-analysis.ts, app.js | batchInfo 필드 추가, 처리중/완료/실패 분기 UI |
| (4-C) 피드백 로그에 배치 미포함 | batch.ts, feedback.ts, app.js | batch 완료 시 feedback_logs INSERT(source='batch'), 로그 필터 탭 |
| (4-C) 마이그레이션 | 0012_feedback_log_source.sql | feedback_logs에 source 컬럼 추가 |

---

## 12. 자주 쓰는 명령어

```bash
# 빌드 & 배포
cd /home/user/webapp && npm run build && npx wrangler pages deploy dist --project-name leet-master

# DB 조회 (원격)
npx wrangler d1 execute leet-master-db --remote --command="SELECT * FROM users LIMIT 5"

# 피드백 로그 확인 (배치 포함)
npx wrangler d1 execute leet-master-db --remote --command="SELECT id, source, created_at FROM feedback_logs ORDER BY created_at DESC LIMIT 10"

# Cron 실행 로그 확인
npx wrangler d1 execute leet-master-db --remote --command="SELECT * FROM cron_runs ORDER BY created_at DESC LIMIT 5"

# 시크릿 목록
npx wrangler pages secret list --project-name leet-master

# PM2 관리
pm2 list
pm2 logs leet-study --nostream
pm2 restart leet-study
```

---

## 13. 새 채팅에서 이어서 작업하는 방법

```
새 채팅 첫 메시지:
"프로젝트의 context.md를 기준으로 작업하자. [할 일]을 진행해줘."

예시:
"프로젝트의 context.md를 기준으로 작업하자. 배치 완료 인앱 알림 시스템을 구현해줘."
```

---

*이 파일은 대화(세션)가 바뀌어도 프로젝트 맥락을 유지하기 위한 인수인계 문서입니다.*
