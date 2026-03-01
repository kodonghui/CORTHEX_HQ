# v5.1 배포 후 긴급 수정 — 다음 세션 프롬프트

> 날짜: 2026-03-02
> 빌드: #763 배포됨 (PR #730 v5.1 workspace + #731 docs)
> 상태: 🔴 **프론트엔드 4곳 깨짐 + 전력분석 시체 에이전트**

---

## 다음 세션 시작 시 이 프롬프트를 붙여넣어:

```
docs/handoff/2026-03-02_v51-bugfix-needed.md 읽고 시작해.

v5.1 workspace 배포(빌드 #763)했는데 프론트엔드 버그 4개 + 전력분석 시체 에이전트 문제가 있다. 전부 수정해.

## 버그 목록

### 버그 1: CEO 사이드바에 에이전트 안 보임 🔴
- 증상: 사이드바에 "사주 본부" 헤더만 보이고 에이전트 카드 0개
- 원인: workspace.sidebarFilter 기본값 'all' → HTML x-show="workspace.sidebarFilter === 'ceo'" → 'all' !== 'ceo' → 전부 숨김
- 추가 원인: /api/agents 응답에 cli_owner 필드 안 들어갈 수 있음 → JS agents 배열에 cli_owner 없으면 필터 실패
- 수정: (1) HTML x-show에 || !workspace.sidebarFilter || workspace.sidebarFilter === 'all' 폴백 추가 (2) /api/agents에 cli_owner 포함 확인

### 버그 2: 사무실 뷰 구형 하드코딩 레이아웃 🟡
- 증상: 사무실이 workspace.officeLayout이 아닌 옛날 "CORTHEX STAFF — 팀장 6명" 하드코딩 표시
- 원인: PR #730이 사이드바만 변경, 사무실 뷰는 안 건드림
- 수정: index.html 사무실 뷰를 x-for="section in workspace.officeLayout" 순회 렌더링으로 교체. architecture.md 설계 3 참조.

### 버그 3: 로그아웃 버튼 안 보임 🔴
- 증상: CEO 로그인해도 로그아웃 버튼 없음
- 원인: index.html에서 로그아웃 버튼의 x-show 조건 확인 필요 (bootstrapMode 또는 workspace 관련 깨짐)
- 수정: 로그아웃 버튼 x-show 조건 확인 후 복원

### 버그 4: 전력분석(Soul Gym) 시체 에이전트 🟡
- 증상: 전력분석 탭에 cio_manager, cso_manager, clo_manager, cmo_manager, cto_manager 등 구 ID + specialist 에이전트들이 "unknown" 상태로 좌르르 나옴
- 원인: soul_gym_rounds DB 테이블에 구 에이전트 ID로 된 오래된 기록이 남아있음. v5에서 ID를 리네임했지만(cio_manager→fin_analyst 등) DB 데이터는 안 지움
- 수정 옵션:
  (A) soul_gym_rounds 테이블에서 구 ID 기록 DELETE (깨끗하게)
  (B) 전력분석 UI에서 현재 agents.yaml에 없는 ID는 필터링 (방어적)
  (C) 둘 다

## 수정 파일
- web/templates/index.html — 사이드바 + 사무실 뷰 + 로그아웃 버튼
- web/static/js/corthex-app.js — agents cli_owner 확인 + workspace 기본값
- (DB) soul_gym_rounds 시체 정리 또는 UI 필터링

## 이미 정상인 것 (건드리지 마)
- config/workspaces.yaml, config_loader.py, arm_server.py /api/workspace-profile — 전부 정상
- 백엔드 데이터 격리 (orgScope) — API 레벨 정상
- CLAUDE.md, architecture.md, docs 갱신 — 완료

## 절대 규칙
- role if/else 하드코딩 절대 금지 (workspace.* 설정 데이터만 사용)
- 네이버 모델: 같은 기능(탭/뷰/NEXUS), 다른 데이터(에이전트/로그/문서)
- 슬랙 모델: 사이드바/@멘션 = 내 CLI 직원만 (cli_owner 기반 필터)
- CEO 데이터가 누나한테 보이면 사형

수정 끝나면 배포 + corthex-hq.com CEO/누나 양쪽 직접 QA까지 끝내놔.
```

---

## 상세 원인 분석

### 사이드바 근본 원인 (전체 흐름)

1. 페이지 로드 → `initAuth()` → 서버에 세션 없음 (배포 후 재시작) → bootstrap_mode=true
2. `initWorkspace()` 호출 → `/api/workspace-profile` → **토큰 없음** → `get_auth_role()` → `"viewer"` → 404
3. workspace 기본값 유지: `sidebarFilter: 'all'`
4. HTML `x-show="workspace.sidebarFilter === 'ceo'"` → `'all' === 'ceo'` = **false** → CEO 섹션 전부 숨김
5. 사주 본부 외부 div에 x-show 없음 → 헤더만 보임, 내부 에이전트는 cli_owner 매칭 실패로 안 보임

**로그인 후에도 안 보이는 추가 원인**:
- `doLogin()` → `initWorkspace()` 호출 → 이번엔 토큰 있어서 API 성공
- **하지만** `/api/agents` 응답에 `cli_owner` 필드가 포함 안 될 수 있음
- agents 배열의 각 에이전트에 `cli_owner`가 없으면 → `a.cli_owner === 'ceo'` → `undefined === 'ceo'` = false → 전부 숨김

### 전력분석 시체 원인

- v5에서 에이전트 ID 리네임: `cio_manager → fin_analyst`, `cso_manager → leet_strategist`, `clo_manager → leet_legal`, `cmo_manager → leet_marketer`, `cpo_manager → leet_publisher`
- `soul_gym_rounds` DB 테이블에 구 ID로 된 과거 라운드 기록이 그대로 남음
- 전력분석 UI가 DB에서 읽은 agent_id를 그대로 표시 → agents.yaml에 없는 ID = "unknown"
- `cto_manager`도 보임 — 이건 v4에서 삭제된 에이전트
- `technical_analysis_specialist`, `market_condition_specialist`, `risk_management_specialist`, `stock_analysis_specialist`, `business_plan_specialist` — 이건 CIO 하위 전문가(v3 시절), 이미 삭제됨

### 사무실 뷰 원인

- PR #730에서 사이드바의 auth.role x-show만 workspace.sidebarFilter로 교체
- **사무실 뷰(office 탭) HTML은 전혀 수정하지 않음**
- 사무실 뷰에 남은 구 코드는 v4~v5 하드코딩 레이아웃 그대로
- architecture.md 설계 3에 officeLayout 순회 렌더링이 명시되어 있으나 구현 안 함

---

## API 검증 결과 (참고)

```bash
# CEO 토큰 발급 + workspace-profile → 정상
CEO_TOKEN=$(curl -s -X POST https://corthex-hq.com/api/auth/login -H "Content-Type: application/json" -d '{"role":"ceo","password":"corthex2026"}' | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
curl -s https://corthex-hq.com/api/workspace-profile -H "Authorization: Bearer $CEO_TOKEN"
# → {"label":"CEO 관제","sidebarFilter":"ceo","orgScope":null,...}

# Sister 토큰 발급 + workspace-profile → 정상
SISTER_TOKEN=$(curl -s -X POST https://corthex-hq.com/api/auth/login -H "Content-Type: application/json" -d '{"role":"sister","password":"sister2026"}' | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
curl -s https://corthex-hq.com/api/workspace-profile -H "Authorization: Bearer $SISTER_TOKEN"
# → {"label":"사주냥 관제","sidebarFilter":"sister","orgScope":"saju",...}
```

## 현재 브랜치

- main에 전부 머지됨 (PR #730 + #731)
- 빌드 #763 배포 상태
- 워크트리 `.claude/worktrees/workspace-arch` 삭제됨
