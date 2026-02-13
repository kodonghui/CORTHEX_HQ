# STATUS.md

내용을 입력하세요.
# STATUS (LEET MASTER) — 현재 상태 메모

**마지막 업데이트:** 2026-02-08 19:30 KST  
**환경:** Production  
**담당:** 동희 + 개발자 AI

---

## 1) 지금 가장 중요한 한 줄
- **이번 주(2/8~2/14) 할 일 7개: 설문조사, 저작권 문의, 특허 비용, 예창패 사업계획서, 자소서, 이메일 옮기기, 학원 해설서 구매**

---

## 2) 우선순위 TODO

### P0 (긴급) - 모두 완료 ✅
(이전 내용 동일 — 생략)

### P1 (이번 주) - 모두 완료 ✅
- [x] 로고/타이틀 개선, 풀이기록 UI 개선, Batch API 도입
- [x] 모바일 날짜 포맷 개선, 문제 본문 강조, 글자 크기 조정
- [x] **Batch 안전장치 강화** (§3-D 참조)
- [x] **Batch UI 6개 이슈 수정** (Batch-1~5 + UI-1)
- [x] **Cron UI 보안 하드닝** — 토큰 마스킹, cron_runs 로그, 외부 안내 접기
- [x] **옵션 3: 6개 이슈 일괄 수정** — JWT, loadBatchStatus, completed_no_output, AI해설 배치분기, feedback_logs source
- [x] **P0 4건 일괄 수정** — Batch 400에러(max_completion_tokens), error_file파싱, F5로그아웃, 즉시UI, KST보정
- [x] **8개 이슈 일괄 수정** — 취소문구, 재요청허용, 즉시UI, F5재시도, failed배지, 크레딧UI, 결제설정토스트, 프롬프트문서화
- [x] **feedback_logs 모델명/비용 정확화** — 하드코딩→실제 모델 기록 + 모델별 단가맵 + AI_PLAYBOOK 배포규칙(항상 Production)
- [x] **favicon 존재 확인** — public/static/ 하위에 모든 파일 존재 ✅

### P1 (이번 주 2/8~2/14) — 사업화 준비
- [ ] **설문조사 설계 및 배포** — 해설 불일치 경험, 구체적 연도/번호, 메가커피 사례 조사
- [ ] **저작권 문의** — 해설서 파싱·비교 분석의 법적 허용 범위 확인
- [ ] **특허 비용 파악** — 총 200~350만 원 예상, IP 지원사업 활용 가능성 조사
- [ ] **예비창업패키지 사업계획서 골격 잡기** — 평가 5대 기준에 맞춰 초안 작성
- [ ] **자소서 작성 (예창패 1곳 집중)** — 창업자 역량 어필
- [ ] **이메일 옮기기** — 구체적 내용 추가 확인 필요
- [ ] **학원 해설서 전부 구매** — 파싱·비교 분석용 자료 확보

### P1.5 (기술 부채)
- [x] **GitHub push** — 로컬 커밋 8개 push 완료 (9d541c2~f079970) ✅
- [ ] **DB 마이그레이션 적용 확인** — 0013_batch_jobs_model_used.sql 로컬/프로덕션 적용 여부
- [ ] **디자이너 핸드오프 후속** — 피드백 수렴 및 반영

### P2 (나중에)
- [ ] **AI로 내 풀이 다듬기** — 사용자 풀이를 AI가 문법/논리/표현 개선 (실시간 API, gpt-4o-mini, 2~3 크레딧)
- [ ] **풀이과정 및 질문** — UI 레이블 변경, 질문 포함 가능, AI 프롬프트 수정 (DB 변경 없음, 1시간)
- [ ] **공동 학습 피드백** — 같은 문제의 다른 학습자 풀이 참고하여 AI 피드백 (실시간 API, 5~10 크레딧, 4~6시간)
- [ ] **나의 진단** — 최근 10~30문제 기반 학습 패턴/약점/강점 분석 (Batch API, LEET 특화, 10~15시간)
- [ ] 수익분석 중복 정리 (크레딧/결제 메뉴)
- [ ] 이메일 인증 시스템
- [ ] 결제 시스템 고도화
- [ ] Batch 완료 시 사용자 인앱 알림 + 결과 바로가기 UX

---

## 3) Batch API 시스템

### A. 아키텍처
- **메인 앱**: leet-master (Cloudflare Pages) — API + 프론트엔드
- **Cron Worker**: leet-master-cron (Cloudflare Workers) — 5분 주기 자동 실행
- **DB 테이블**: batch_requests, batch_jobs, system_tokens

### B. Status 전이도 (DB 실제 값, 코드와 완전 일치)

**batch_requests (개별 요청):**
```
pending → submitted → completed
                    → failed
```
- `pending`: 사용자가 요청, Cron/관리자가 아직 OpenAI에 미제출
- `submitted`: OpenAI Batch에 제출됨 (batch_job_id 연결)
- `completed`: OpenAI 결과 수신 + DB 반영 완료
- `failed`: OpenAI에서 실패 반환 또는 Batch job 자체 실패/만료

**batch_jobs (Batch 단위):**
```
submitted → validating → in_progress → finalizing → completed
                                                   → failed
                                                   → expired
                                                   → cancelled
```
- `submitted`: 우리 측에서 OpenAI에 제출한 직후 (DB 저장 시)
- `validating`, `in_progress`, `finalizing`: OpenAI 측 진행 상태 (check가 poll해서 DB 반영)
- `completed`: **결과 파일 다운로드 + 개별 request 처리까지 완료된 후에만** DB에 반영 (조기 completed 방지)
- `failed`, `expired`, `cancelled`: OpenAI 측 실패/만료/취소 → 크레딧 전액 환불

> 주의: `processing`이라는 값은 사용하지 않음. 항상 `in_progress` 사용.

### C. 크레딧 처리 정책: **사전 홀드(차감) + 자동 환불 방식 (B)**

| 시점 | 동작 | 코드 위치 (batch.ts) |
|------|------|---------------------|
| 사용자 요청 시 | `credits -= creditsRequired`, transaction_type=`reserve` 기록 | 728~744행 |
| OpenAI 성공 시 | 예약 vs 실제 사용량 차이(refundDiff) 환불, transaction_type=`use` 기록 | 436~496행 |
| OpenAI 실패 시 | `credits += credits_reserved` 전액 환불, transaction_type=`refund` 기록 | 394~413행 |
| Batch job 실패/만료/취소 시 | 해당 job의 모든 submitted requests 전액 환불 | 530~571행 |
| 사용자 취소 시 (pending만 가능) | `credits += credits_reserved` 전액 환불 + 요청 삭제 | 877~905행 |

**핵심**: 실패/만료 시 크레딧은 **반드시 전액 환불**됨. 부분 차감 후 미환불 경로는 없음.

### D. 안전장치 상세 (2026-02-06 추가)

| 위험 포인트 | 방어 코드 |
|---|---|
| 중복 제출 | `WHERE status = 'pending'`만 조회 → 제출 즉시 `submitted`로 변경 |
| 동시 Cron 중복 처리 | check 시작 시 `submitted → in_progress` 원자적 UPDATE |
| 완료 건 재다운로드 | check 쿼리가 `completed` 제외, 결과 처리 후에만 `completed` 저장 |
| 사용자 과다 요청 | 크레딧 사전 홀드 + 동일 문제 중복 pending/submitted 방지 |
| openai_called 정확성 | 실제 fetch() 호출 직후에만 카운터 증가, 추정값 아닌 실측값 |

### E. 응답 형식 (Cron/관리자 로그 확인용)

```json
// process (할 일 없음 → OpenAI 비용 $0)
{ "pending_found": 0, "processed": 0, "openai_called": false }

// process (할 일 있음 → OpenAI Batch 제출)
{ "pending_found": 3, "processed": 3, "openai_called": true }

// check (할 일 없음 → OpenAI 비용 $0)
{ "processing_found": 0, "checked": 0, "completed": 0, "failed": 0, "openai_called": false }

// check (할 일 있음 → OpenAI 상태 조회 + 결과 다운로드)
{ "processing_found": 1, "checked": 1, "completed": 3, "failed": 0, "openai_called": true, "openai_call_count": 2 }
```

### F. 엔드포인트
| 경로 | 메서드 | 인증 | 설명 |
|------|--------|------|------|
| /api/batch | POST | JWT | 심층분석 예약 요청 |
| /api/batch/status | GET | JWT | 내 요청 상태 조회 |
| /api/batch/:id | DELETE | JWT | pending 취소+환불 |
| /api/batch/admin/process | POST | JWT(admin) | 관리자 수동: pending → OpenAI 제출 |
| /api/batch/admin/check | POST | JWT(admin) | 관리자 수동: 결과 확인 → DB 반영 |
| /api/batch/admin/dashboard | GET | JWT(admin) | 관리자 대시보드 데이터 |
| /api/batch/cron/process | POST | Cron 토큰 | Cron 자동: pending → OpenAI 제출 |
| /api/batch/cron/check | POST | Cron 토큰 | Cron 자동: 결과 확인 → DB 반영 |
| /api/batch/admin/token/regenerate | POST | JWT(admin) | Cron 토큰 재생성 |
| /api/batch/admin/token/copy | POST | JWT(admin) | Cron 토큰 전체 조회 (1회성 복사) |

### G. Cron Worker (leet-master-cron)
- **배포 URL**: https://leet-master-cron.elddlwkd.workers.dev
- **스케줄**: */5 * * * * (5분 주기)
- **Secrets**: CRON_TOKEN (Bearer 토큰)
- **환경변수**: TARGET_BASE_URL (기본: https://leet-master.pages.dev)
- **수동 확인 엔드포인트**:
  - GET /health — 상태 확인
  - POST /run-once (Authorization: Bearer {CRON_TOKEN}) — 수동 1회 실행

### H. 심층 분석 프롬프트 구조 (일원화 완료)
- **우선순위**: DB `feedback_level_settings` (level='deep') → 하드코딩 `DEFAULT_DEEP_PROMPTS` 폴백
- **소스 위치**: `src/routes/batch.ts:21~` (DEFAULT_DEEP_PROMPTS), `src/routes/batch.ts:111~131` (DB 조회)
- **관리자 설정 반영**: 관리자가 UI에서 프롬프트/모델을 변경 → DB 즉시 저장 → 다음 Cron process 시 자동 적용
- **템플릿 변수**: `{year}`, `{number}`, `{correct_answer}`, `{user_answer}`, `{is_correct}`, `{user_explanation}`, `{passage}`, `{choices}`, `{ai_explanation}`, `{max_chars}`
- **모델 기본값**: `gpt-4o` (DB 미설정 시), max_chars `4000`
- **reasoning 모델**: `o1/o3/o4` 접두사 → `max_completion_tokens` + `reasoning_effort` 사용

### I. Cron 실행 로그 (cron_runs 테이블, 2026-02-06 추가)
- **용도:** 매 Cron 실행(process/check) 시 결과를 D1에 기록, 관리자 UI에서 최신 1건 표시
- **보안:** dashboard API에서 `cron_token` → `cron_token_masked`로 변경. 전체 토큰은 `/admin/token/copy`로만 접근 가능
- **UI 변경:**
  - "Cron 자동 실행 상태" 섹션: 마지막 실행 시각(KST), 결과 요약, 30분 초과 경고
  - 외부 Cron 안내: `<details>` 접기 (기본 닫힘)
  - 토큰: 마스킹 표시 + [복사] 버튼 (전용 API) + [재생성] 버튼
- **데이터 보관:** 하루 576행(5분×2엔드포인트), 추후 30일 자동 정리 예정

---

## 4) Batch UI 이슈 수정 (2026-02-06)

| 이슈 | 설명 | 해결 |
|------|------|------|
| Batch-1 | 관리자 수동 버튼 클릭 불가 (0건 시 disabled) | 항상 활성 + 0건 시 사유 알림 |
| Batch-2 | 로그인 직후 배치 알림 안 뜸 | handleLoginSubmit에 loadBatchStatus() 추가 |
| Batch-3 | 상대시간 "9시간 전" 오류 (UTC/KST 파싱) | 모든 날짜함수에 UTC 명시 파싱 + KST timeZone |
| Batch-4 | 풀이기록에 배치 상태 미표시 | answers.ts LEFT JOIN + 프론트 배지 |
| Batch-5 | 처리 중 심층 버튼 재요청 가능 | showDeepAnalysisModal에서 기존 배치 확인 |
| UI-1 | 글자크기 불일치 + 사용자 설정 | CSS 변수 + DB 저장 + 마이페이지 설정 |

## 5) 최근 변경/배포 기록 (최대 5개)

| 날짜 | URL | 커밋 | 변경 요약 |
|------|-----|------|----------|
| 2026-02-07 | https://4edf0c2b.leet-master.pages.dev | c95c579 | **feedback_logs 모델명/비용 정확화** — 하드코딩→실제 모델 기록 + 모델별 단가맵 + AI_PLAYBOOK 배포규칙 |
| 2026-02-06 | https://1f7c2eb5.leet-master.pages.dev | 7818f25 | 8개 이슈: 취소문구, 재요청허용, 즉시UI, F5재시도, failed배지, 크레딧UI, 결제설정토스트, 프롬프트문서화 |
| 2026-02-06 | https://c3ad0233.leet-master.pages.dev | 9d541c2 | P0 4건: max_tokens→max_completion_tokens, error_file파싱, F5로그아웃수정, 즉시UI, KST보정 |
| 2026-02-06 | https://6bdd567f.leet-master.pages.dev | 2eba1e3 | 옵션 3: JWT+loadBatch+completed_no_output+AI해설배치+feedback_logs source |
| 2026-02-06 | https://5a883435.leet-master.pages.dev | 1f7cfbd | Cron UI 보안 하드닝 + cron_runs 로그 |

---

## 6) 현재 열려있는 이슈

### ISSUE-004: Batch 자동 실행 모니터링
- **상태:** 운영 중 (Cron Worker 5분 주기)
- **확인 방법:** 관리자 > Batch 탭 > "Cron 자동 실행 상태" 섹션 (cron_runs 로그 기반)
- **보조 확인:** Cloudflare Dashboard → Workers → leet-master-cron → Logs

---

## 7) GitHub 저장소
- **URL:** https://github.com/kodonghui/leet-master
- **브랜치:** main
- **최신 push**: f079970 (2026-02-08 19:30 KST) ✅
- **Push 완료**: 모든 로컬 커밋이 GitHub에 동기화됨

---

## 8) DB 마이그레이션 상태
- **최신 파일:** 0013_batch_jobs_model_used.sql (batch_jobs.model_used 컬럼 추가)
- **로컬 적용:** 미확인 (요 확인)
- **프로덕션 적용:** 미확인 (요 확인)

---

## 9) 운영 확인 체크리스트 (Batch API)
1. Cron Worker 배포 확인: `curl https://leet-master-cron.elddlwkd.workers.dev/health`
2. E2E 테스트: `/run-once` → process + check 응답에 `openai_called` 필드 확인
3. Production DB: batch_requests, batch_jobs 테이블 존재 + model_used 컬럼 확인 필요
4. CRON_TOKEN: Worker secret 설정 완료
5. 관리자 대시보드: 관리자 > Batch 탭에서 수동 실행 가능
6. Cron 실행 로그: cron_runs 테이블에 매 실행 기록 + 관리자 UI에 최신 1건 표시
7. 보안: Network 탭에서 dashboard 응답에 cron_token 평문 없음 확인
8. feedback_logs: model, total_cost 정확 기록 확인

---

## 10) 새로 생긴 리스크/주의사항
1. **마이그레이션 0013 미적용 시**: batch_jobs.model_used 컬럼 누락 → 관리자 대시보드 모델명 표시 안됨
2. **GitHub push 누락**: 최신 5개 커밋이 GitHub에 없음 → 협업/백업 문제
3. **AI_PLAYBOOK 배포규칙 변경**: "항상 Production까지 진행" → Preview만 따로 대기하지 않음 (주의 필요)

---

## 11) 다음 액션 (우선순위별)

### 이번 주 (2/8~2/14) — 사업화 준비 최우선
1. **[P1] 설문조사 설계 및 배포** — 해설 불일치 경험 조사 (메가커피 사례 포함)
2. **[P1] 저작권 문의** — 해설서 파싱·비교 분석의 법적 허용 범위
3. **[P1] 특허 비용 파악** — 200~350만 원 예상, IP 지원사업 활용
4. **[P1] 예비창업패키지 사업계획서** — 평가 5대 기준에 맞춰 초안
5. **[P1] 자소서 작성** — 공기업/예창패, 9일까지
6. **[P1] 이메일 옮기기** — 구체적 내용 확인 필요
7. **[P1] 학원 해설서 전부 구매** — 파싱·비교 분석용

### 기술 부채 (P1.5)
1. **GitHub push** — 로컬 커밋 7개 push (9d541c2~b9ae8b4)
2. **DB 마이그레이션 적용 확인** — 0013 로컬/프로덕션 적용
3. **디자이너 핸드오프 후속** — 피드백 수렴 및 반영

### 기능 개발 (P2)
1. **수익분석 중복 정리** — 크레딧/결제 메뉴 통합
2. **Batch 완료 알림 UX** — 인앱 알림 + 결과 바로가기
3. **TODO.md 정리** — 완료/미완 항목 정확히 반영

---

## 12) 재현 방법 (버그 없음, 생략)

---
현 방법 (버그 없음, 생략)

---
