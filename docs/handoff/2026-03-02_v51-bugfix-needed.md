# v5.1 배포 후 버그 수정 필요 — 핸드오프

> 날짜: 2026-03-02
> 빌드: #762~#763 배포됨 (PR #730 + #731)
> 상태: 🔴 **사이드바 + 사무실 뷰 + 로그아웃 버튼 3곳 깨짐**

---

## 현재 상황

v5.1 workspace 코드가 main에 머지+배포됨. 백엔드 API는 정상 동작하지만 **프론트엔드 UI 3곳이 깨짐**.

### 버그 1: CEO 사이드바에 에이전트 안 보임 🔴

**증상**: 사이드바에 "사주 본부" 헤더만 보이고 에이전트 카드 0개. 비서실장/리트마스터/금융 전부 안 보임.

**근본 원인**: bootstrap 모드(토큰 없음) → `initWorkspace()` → `/api/workspace-profile` 호출 시 토큰 없음 → `get_auth_role()` → `"viewer"` 반환 → 404 → workspace 기본값 `sidebarFilter: 'all'` 유지 → HTML의 `x-show="workspace.sidebarFilter === 'ceo'"` → `'all' === 'ceo'` = false → 전부 숨김

**로그인 후에도 안 보이는 이유**: `doLogin()` 후 `initWorkspace()` 호출은 됨. 하지만 `agents` 배열에 `cli_owner` 필드가 없을 가능성. `/api/agents` 응답에 cli_owner가 포함되는지 확인 필요.

**수정 방향**:
1. **JS 기본값**: `sidebarFilter: 'all'`일 때 전체 에이전트 보이게 (현재는 'ceo'/'sister' 매칭만 됨)
2. **HTML**: 각 섹션의 x-show 조건에 `|| workspace.sidebarFilter === 'all'` 추가
3. **또는**: bootstrap 모드에서 workspace 기본값을 `sidebarFilter: 'ceo'`로 설정

### 버그 2: 사무실 뷰 구형 레이아웃 🟡

**증상**: 사무실 뷰가 `workspace.officeLayout` 순회가 아닌 **구형 하드코딩 레이아웃** 표시

**근본 원인**: **사무실 뷰 HTML을 workspace.officeLayout 기반으로 변환하지 않았음**. PR #730은 사이드바만 변경했고, 사무실 뷰(office 탭)는 건드리지 않음.

**수정 방향**: `index.html`의 사무실 뷰 섹션을 `x-for="section in workspace.officeLayout"` 순회로 교체. architecture.md의 설계 3 참조.

### 버그 3: 로그아웃 버튼 안 보임 🔴

**증상**: CEO 로그인해도 로그아웃 버튼이 없음

**근본 원인**: 추정 — `bootstrapMode`가 true로 남아있거나, 로그아웃 버튼 x-show 조건이 workspace 관련으로 깨졌을 가능성. index.html에서 로그아웃 버튼 x-show 조건 확인 필요.

---

## 수정해야 할 파일

| 파일 | 수정 내용 |
|------|----------|
| `web/templates/index.html` | 사이드바 x-show에 'all' 폴백 추가 + 사무실 뷰 officeLayout 순회 + 로그아웃 버튼 확인 |
| `web/static/js/corthex-app.js` | `agents` 데이터에 cli_owner 포함 확인 + workspace 기본값 검토 |

## 이미 완료된 것 (건드리지 마)

- ✅ `config/workspaces.yaml` — 정상
- ✅ `web/config_loader.py` — load_workspace_profiles() 정상
- ✅ `web/arm_server.py` — `/api/workspace-profile` 정상 (curl 검증 완료)
- ✅ `config/yaml2json.py` — workspaces 변환 포함됨
- ✅ JS role if/else 17곳 제거 → workspace.* 사용 (이 부분은 맞음)
- ✅ 백엔드 데이터 격리 (orgScope) — API 레벨 정상
- ✅ 문서: CLAUDE.md 정리, architecture.md cli_owner 반영, updates/project-status/BACKLOG 갱신

## API 검증 결과 (정상)

```
CEO:    {"label":"CEO 관제","sidebarFilter":"ceo","orgScope":null,...}
Sister: {"label":"사주냥 관제","sidebarFilter":"sister","orgScope":"saju",...}
```

## 수정 우선순위

1. 🔴 사이드바 에이전트 표시 복원 (sidebarFilter 'all' 폴백)
2. 🔴 로그아웃 버튼 복원
3. 🟡 사무실 뷰 officeLayout 순회 (시간 있으면)

## 절대 규칙 (유지)

- role if/else 하드코딩 금지 (workspace.* 데이터만 사용)
- 네이버 모델: 같은 기능, 다른 데이터
- 슬랙 모델: cli_owner 기반 내 CLI 직원만
