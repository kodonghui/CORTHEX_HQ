---
stepsCompleted: [step-01-validate-prerequisites, step-02-design-epics, step-03-create-stories, complete]
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/ux-design-specification.md
---

# CORTHEX v2 - Epic & Story Breakdown

## Epic List

| Epic | 이름 | Phase | 스토리 수 |
|------|------|-------|-----------|
| E1 | 프로젝트 초기화 & 인프라 | P1 | 5 |
| E2 | 관리자 콘솔 | P1 | 6 |
| E3 | 인증 & 워크스페이스 | P1 | 4 |
| E4 | AI 에이전트 채팅 | P1 | 5 |
| E5 | 비서 오케스트레이션 | P1 | 3 |
| E6 | 보고 시스템 | P2 | 4 |
| E7 | 도구 호출 & 전략실 | P2 | 4 |
| E8 | 야간 작업 큐 | P2 | 3 |
| E9 | SNS & 운영 도구 | P3 | 5 |
| E10 | 스케치바이브 | P4 | 2 |

---

## Epic 1: 프로젝트 초기화 & 인프라

모노레포 세팅, DB, 서버, 배포 파이프라인 구축. 나머지 모든 에픽의 전제 조건.

### Story 1.1: Turborepo 모노레포 초기화

As a 개발자, I want 모노레포가 세팅되어 있기를, So that 관리자/유저앱/서버/공유타입을 한 리포에서 관리할 수 있다.

**AC:**
- **Given** 빈 디렉토리 **When** `bun create` 실행 **Then** packages/{admin,app,server,shared,ui} 구조 생성
- **Given** 모노레포 **When** `turbo build` **Then** 모든 패키지 빌드 성공

### Story 1.2: PostgreSQL + Drizzle ORM 세팅

As a 개발자, I want DB가 준비되어 있기를, So that 데이터를 저장하고 조회할 수 있다.

**AC:**
- **Given** 서버 **When** PostgreSQL 설치 **Then** 연결 성공
- **Given** Drizzle **When** 스키마 정의 **Then** 12개 테이블 마이그레이션 성공
- **And** 모든 테이블에 company_id 컬럼 존재

### Story 1.3: Hono API 서버 기본 세팅

As a 개발자, I want API 서버가 동작하기를, So that 프론트엔드가 백엔드와 통신할 수 있다.

**AC:**
- **Given** Bun + Hono **When** 서버 시작 **Then** `/api/health` 200 응답
- **And** 에러 핸들링 미들웨어 동작 (표준 에러 코드)

### Story 1.4: React + Vite 프론트엔드 세팅

As a 개발자, I want 프론트엔드가 동작하기를, So that 유저가 브라우저로 접근할 수 있다.

**AC:**
- **Given** admin 패키지 **When** `bun dev` **Then** 관리자 콘솔 로컬 실행
- **Given** app 패키지 **When** `bun dev` **Then** 유저 앱 로컬 실행
- **And** Tailwind CSS 4 + shadcn/ui 동작
- **And** 다크/라이트 모드 토글 동작

### Story 1.5: Nginx + 배포 파이프라인

As a 관리자, I want v2가 서버에 배포되기를, So that 브라우저에서 접근할 수 있다.

**AC:**
- **Given** Oracle Cloud **When** Nginx 설정 **Then** v2.corthex-hq.com → v2 앱 라우팅
- **And** v1 (corthex-hq.com) 정상 운영 유지
- **Given** GitHub push **When** Actions 실행 **Then** 자동 배포 성공

---

## Epic 2: 관리자 콘솔

별도 URL의 관리자 앱. 회사/직원/에이전트/부서/도구 CRUD.

### Story 2.1: 관리자 로그인

As a 관리자, I want 별도 계정으로 로그인하기를, So that 관리 기능에 접근할 수 있다.

**AC:**
- **Given** admin URL **When** ID/PW 입력 **Then** admin JWT 발급 + 대시보드 표시
- **And** 유저 앱 JWT로는 관리자 콘솔 접근 불가

### Story 2.2: 회사 & 직원 CRUD

As a 관리자, I want 회사와 직원을 관리하기를, So that 새 H를 5분 안에 세팅할 수 있다.

**AC:**
- **Given** 관리자 콘솔 **When** 회사 생성 **Then** DB에 company 레코드 생성
- **Given** 회사 선택 **When** 직원 추가 **Then** ID/PW 발급 + users 테이블 생성
- **And** 직원 목록 테이블 표시

### Story 2.3: CLI & API key 연동

As a 관리자, I want CLI 토큰과 API key를 등록하기를, So that 에이전트가 H의 CLI로 실행될 수 있다.

**AC:**
- **Given** 직원 선택 **When** CLI 토큰 입력 **Then** AES-256 암호화 저장
- **Given** 회사 **When** 공용 API key 등록 **Then** 암호화 저장

### Story 2.4: 부서 & 에이전트 CRUD

As a 관리자, I want 부서와 에이전트를 관리하기를, So that 조직 구조를 설정할 수 있다.

**AC:**
- **Given** 회사 **When** 부서 생성 **Then** departments 테이블 생성
- **Given** 부서 **When** 에이전트 추가 **Then** 이름/역할/소울/도구/CLI 설정 + 즉시 활성화
- **And** 서버 재시작 불필요

### Story 2.5: 도구 할당 & 보고 라인

As a 관리자, I want 도구와 보고 라인을 설정하기를, So that 에이전트가 올바른 도구만 사용하고 보고가 올바르게 흐른다.

**AC:**
- **Given** 본부 **When** 도구 체크박스 ON/OFF **Then** agent_tools 매핑 업데이트
- **Given** 직원 **When** 보고 라인 설정 **Then** report_lines 테이블 업데이트

### Story 2.6: 비서 배정 & 세션 관리

As a 관리자, I want 비서를 배정하고 세션을 관리하기를, So that H에게 비서를 달아주고 보안 사고 시 세션을 종료할 수 있다.

**AC:**
- **Given** 직원 **When** 비서 배정 **Then** 에이전트에 비서 역할 플래그 설정
- **Given** 보안 사고 **When** 세션 강제 종료 **Then** 해당 유저 JWT 즉시 무효화

---

## Epic 3: 인증 & 워크스페이스

유저 앱 로그인 + 독립 워크스페이스 + 개인 설정.

### Story 3.1: 유저 로그인

As a H, I want ID/PW로 로그인하기를, So that 내 워크스페이스에 접근할 수 있다.

**AC:**
- **Given** 유저 앱 **When** ID/PW 입력 **Then** JWT 발급 + 홈 화면 표시
- **And** "안녕하세요 {이름}님" 표시

### Story 3.2: 독립 워크스페이스

As a H, I want 내 데이터만 보기를, So that 다른 유저의 정보에 접근할 수 없다.

**AC:**
- **Given** H 로그인 **When** 어떤 API 호출 **Then** 자기 company_id + user_id 데이터만 반환
- **And** 다른 유저 데이터 0건 노출 (자동화 격리 테스트 100% 통과)

### Story 3.3: 개인 API key 등록

As a H, I want 내 개인 API key를 등록하기를, So that KIS/노션/이메일/텔레그램을 연동할 수 있다.

**AC:**
- **Given** 설정 페이지 **When** API key 입력 **Then** AES-256 암호화 저장
- **And** 4종 지원: KIS, 노션, 이메일, 텔레그램

### Story 3.4: 홈 화면

As a H, I want 로그인 후 내 팀을 보기를, So that 내 에이전트 상태를 즉시 확인할 수 있다.

**AC:**
- **Given** 로그인 **When** 홈 표시 **Then** 내 에이전트 목록 + 상태(🟢🟡🔴) 표시
- **And** 빈 상태: "아직 업무 기록이 없습니다" + 채팅 시작 유도

---

## Epic 4: AI 에이전트 채팅

핵심 기능. 멀티턴 + 세션 연속성 + CLI 격리.

### Story 4.1: 기본 채팅

As a H, I want AI 에이전트와 채팅하기를, So that 업무를 지시할 수 있다.

**AC:**
- **Given** 에이전트 선택 **When** 메시지 전송 **Then** WebSocket으로 실시간 응답 스트리밍
- **And** CLI 격리: 내 CLI 토큰으로만 실행

### Story 4.2: 세션 연속성 & 메모리

As a H, I want 어제 대화를 이어가기를, So that AI가 진짜 직원처럼 기억하고 일한다.

**AC:**
- **Given** 다음 날 로그인 **When** 채팅 열기 **Then** 어제 대화 히스토리 표시
- **And** 에이전트가 "어제 요청하신 건 처리됐습니다" 수준의 연속성

### Story 4.3: 에이전트 상태 표시

As a H, I want 에이전트 상태를 보기를, So that 현재 작업 중인지, 오류인지 알 수 있다.

**AC:**
- **Given** 채팅 **When** 에이전트 작업 중 **Then** 🟡 작업중 표시
- **Given** CLI 끊김 **When** 상태 변경 **Then** 🔴 오류 + "CLI 연결 끊김" 메시지

### Story 4.4: CLI 격리 & 협업 규칙

As a 시스템, I want CLI 기반 격리를, So that 비용과 데이터가 유저별로 완전 분리된다.

**AC:**
- **Given** 같은 CLI 에이전트 **When** 작업 **Then** 양방향 협업 허용
- **Given** 다른 CLI 에이전트 **When** 협업 시도 **Then** 차단

### Story 4.5: 사이드바 에이전트 목록

As a H, I want 사이드바에서 내 에이전트를 보기를, So that 원하는 에이전트를 선택해서 채팅할 수 있다.

**AC:**
- **Given** 좌측 사이드바 **When** 표시 **Then** 내 에이전트만 목록 (다른 유저 에이전트 안 보임)
- **And** 클릭 시 해당 에이전트 채팅 화면으로 전환

---

## Epic 5: 비서 오케스트레이션

비서 → 부서 위임 → 최종 보고서 구조.

### Story 5.1: 비서 위임

As a H, I want 비서에게 지시하면 부서별로 배분되기를, So that 한 번에 여러 에이전트에게 일을 시킬 수 있다.

**AC:**
- **Given** 비서 채팅 **When** "마케팅 분석해줘" **Then** 비서가 해당 부서 에이전트에게 위임

### Story 5.2: 최종 보고서

As a H, I want 비서가 정리한 보고서를 받기를, So that 에이전트별 결과를 읽을 필요 없이 종합본만 확인한다.

**AC:**
- **Given** 위임 완료 **When** 에이전트 작업 끝 **Then** 비서가 종합 보고서 생성 + H에게 전달

### Story 5.3: 비서 선택적 배정

As a 관리자, I want 비서를 선택적으로 배정하기를, So that 비서 없이도 에이전트와 직접 채팅이 가능하다.

**AC:**
- **Given** 비서 미배정 유저 **When** 채팅 **Then** 에이전트와 직접 대화 (비서 경유 안 함)

---

## Epic 6: 보고 시스템 (P2)

H → CEO 보고 + 코멘트 피드백.

### Story 6.1~6.4: 보고서 CRUD + "CEO에게 보고" 버튼 + 코멘트 + 유저별 격리

(FR-5.1~5.4 각각 1 스토리)

---

## Epic 7: 도구 호출 & 전략실 (P2)

에이전트 도구 자동호출 + 3단계 할당 + KIS.

### Story 7.1~7.4: 도구 자동호출 + 3단계 할당 + 본부별 DB + KIS 연동

(FR-6.1~6.3, FR-8.1~8.2 각각 1 스토리)

---

## Epic 8: 야간 작업 큐 (P2)

"시켜놓고 퇴근" 기능. pg-boss 기반.

### Story 8.1~8.3: 작업 큐 등록 + 야간 실행 + 완료/실패 알림

(FR-7.1~7.4)

---

## Epic 9: SNS & 운영 도구 (P3)

v1 나머지 기능 이식.

### Story 9.1~9.5: SNS + 작전일지 + 대시보드 + 텔레그램 + 사내 메신저

(FR-9~10 전부)

---

## Epic 10: 스케치바이브 (P4)

NEXUS 2D 캔버스 조직 편집.

### Story 10.1~10.2: 캔버스 편집 + 코드 반영

(FR-11.1~11.2)

---

## FR Coverage Map

| FR | Epic | Story |
|----|------|-------|
| FR-1.1~1.11 | E2 | 2.1~2.6 |
| FR-2.1~2.5 | E3 | 3.1~3.4 |
| FR-3.1~3.7 | E4 | 4.1~4.5 |
| FR-4.1~4.3 | E5 | 5.1~5.3 |
| FR-5.1~5.4 | E6 | 6.1~6.4 |
| FR-6.1~6.3 | E7 | 7.1~7.3 |
| FR-7.1~7.4 | E8 | 8.1~8.3 |
| FR-8.1~8.2 | E7 | 7.4 |
| FR-9.1~9.3 | E9 | 9.1~9.3 |
| FR-10.1~10.5 | E9 | 9.4~9.5 |
| FR-11.1~11.2 | E10 | 10.1~10.2 |

**전체 FR 45개 → 10개 에픽, ~41개 스토리로 분해 완료.**
