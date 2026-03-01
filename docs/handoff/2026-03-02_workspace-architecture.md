# 핸드오프: 워크스페이스 아키텍처 재설계

> 새 세션에서 이 파일 읽고 시작할 것

---

## 현재 상태

- **브랜치**: `claude/v5-sister-space` (main 기준)
- **이미 수정된 파일** (부분 완료, 하드코딩 방식 — 재작성 필요):
  - `web/templates/index.html` — 헤더 "CEO 관제" → role 분기 (x-show 방식)
  - `web/static/js/corthex-app.js` — `getPrimaryTabs()` / `getSecondaryTabs()` if/else 하드코딩
- **architecture.md** — v5.1 섹션 추가됨 (하드코딩 방식 — 전면 재작성 필요)
- **config.yaml** — BMAD 언어 Korean으로 변경됨

---

## 핵심 문제

**현재 코드 (쓰레기):**
```javascript
if (this.auth.role === 'sister') { return ['command', 'activityLog', 'archive']; }
if (this.auth.role === 'ceo') { return ['home', 'command', 'trading', ...]; }
// → 한 명 더 들어오면? 또 if/else 추가. 확장 불가.
```

**대표님이 원하는 것 (네이버 모델):**
- 네이버: 계정 A 로그인 → A의 메일/카페/블로그. 계정 B 로그인 → B의 메일/카페/블로그.
- CORTHEX도 동일: 로그인한 사람 기준으로 **설정 파일이 정의한 워크스페이스**가 자동 로드
- role별 if/else **절대 금지** — 설정 데이터 기반 동적 렌더링
- 새 사람 추가 = 설정 파일에 프로파일 1개 추가하면 끝. 코드 수정 0줄.

---

## create-architecture에 줄 프롬프트

아래를 `/bmad-agent-bmm-architect` 실행 후 → CA (Create Architecture) 선택 → N (New) 으로 시작할 때 입력:

```
기존 architecture.md (_bmad-output/planning-artifacts/architecture.md)의 v5 아키텍처를 기반으로,
v5.1 "워크스페이스 아키텍처"를 새로 설계해줘.

## 핵심 요구사항

네이버 모델: 로그인한 사용자마다 완전히 다른 워크스페이스가 뜸.
- CEO 로그인 → CEO 워크스페이스 (전체 탭, 전체 에이전트, CEO 사무실)
- 누나 로그인 → 누나 워크스페이스 (사주 탭만, 사주 에이전트만, 사주냥 사무실)
- 새 직원 추가 → 설정 파일에 프로파일 1줄 추가하면 끝. 코드 수정 0줄.

## 절대 금지

- `if (role === 'sister')` 같은 role 하드코딩 금지
- `x-show="auth.role !== 'sister'"` 같은 숨기기 금지
- role 추가할 때마다 코드 수정해야 하는 구조 금지

## 설계해야 할 것

1. **워크스페이스 프로파일 설정** (YAML 또는 JSON)
   - role별: 헤더 텍스트, 색상, 보이는 탭 목록, 뷰 모드 목록, 사무실 에이전트 목록, 사이드바 필터
   - 예: config/workspaces.yaml 또는 agents.yaml에 통합

2. **백엔드 API** (/api/workspace-profile)
   - 로그인 시 해당 role의 워크스페이스 프로파일 전달
   - 프론트엔드는 이 데이터만 보고 렌더링

3. **프론트엔드 동적 렌더링**
   - 탭: workspace.primaryTabs 배열 순회 렌더링
   - 뷰 토글: workspace.viewModes 배열 순회 렌더링
   - 사무실: workspace.officeAgents 배열 순회 렌더링
   - 사이드바: workspace.sidebarFilter 기준 필터
   - 헤더: workspace.label, workspace.color 사용
   - if/else 없이 데이터만으로 UI 구성

4. **기존 v5 아키텍처와 호환**
   - agents.yaml의 org/cli_owner 체계는 유지
   - DB org 컬럼 격리는 유지
   - agent_router.py CLI 격리는 유지
   - 프론트엔드 렌더링 방식만 변경

## 참고 파일
- 기존 아키텍처: _bmad-output/planning-artifacts/architecture.md
- 현재 JS: web/static/js/corthex-app.js (tabs 배열, getPrimaryTabs 등)
- 현재 HTML: web/templates/index.html (사무실 뷰, 뷰 토글, 사이드바)
- 에이전트 설정: config/agents.yaml

## 기술 스택
- Python FastAPI + SQLite
- Alpine.js SPA (CDN) + Tailwind CSS
- 설정: YAML (agents.yaml 등)
```

---

## 새 세션 시작 순서

1. `git checkout claude/v5-sister-space` (이미 존재)
2. `docs/handoff/2026-03-02_workspace-architecture.md` 읽기 (이 파일)
3. `/bmad-agent-bmm-architect` 실행
4. CA → 위 프롬프트 입력 (기존 architecture.md R 아님, 새로 N으로)
5. 아키텍처 설계 완료 후 → 구현

---

## 현재 브랜치 수정 내역 (되돌려도 됨)

```
M  _bmad/bmm/config.yaml          ← communication_language: Korean (유지)
M  web/static/js/corthex-app.js   ← getPrimaryTabs/getSecondaryTabs 하드코딩 (재작성 필요)
M  web/templates/index.html       ← 헤더 role 분기 x-show (재작성 필요)
```

architecture.md v5.1 섹션도 전면 재작성 필요 (현재 하드코딩 방식).
