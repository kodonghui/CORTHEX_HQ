# v5.1 Config-driven Workspace 구현 핸드오프

> 작성: 2026-03-02
> 상태: 아키텍처 완료 + 코드 80% 완료, 배포/QA 미완
> 워크트리: `.claude/worktrees/workspace-arch` (브랜치 `worktree-workspace-arch`)
> 아키텍처 문서: `_bmad-output/planning-artifacts/architecture.md` (v5.1 섹션)

---

## 핵심 원칙 (대표님 직접 결정 — 절대 변경 금지)

1. **네이버 모델**: 기능(탭/뷰/NEXUS) = 모든 사용자 동일. 기능 차별 금지.
2. **슬랙 모델**: 사이드바/@멘션 = 내 CLI 직원만 보임. cli_owner 기반 필터.
3. **데이터 스코프**: API 데이터 = workspace.orgScope으로 필터 (CEO=전체, sister=saju)
4. **role if/else 절대 금지**: `if (auth.role === 'sister')` 패턴 1줄이라도 있으면 아키텍처 위반. `workspace.*` 설정 데이터만 사용.
5. **내 CLI = 내 직원**: `agents.yaml`의 `cli_owner` 필드 기준. CEO 로그인 → cli_owner='ceo' 에이전트만, sister 로그인 → cli_owner='sister' 에이전트만.

---

## 완료된 작업

| 파일 | 변경 내용 | 커밋 |
|------|----------|------|
| `config/workspaces.yaml` | 신규 생성 — CEO/sister 프로파일 (브랜딩+데이터스코프) | f1d2d51 |
| `web/config_loader.py` | `load_workspace_profiles()` + `get_workspace_profile()` 추가 | f1d2d51 |
| `web/arm_server.py` | `GET /api/workspace-profile` 엔드포인트 추가 | f1d2d51 |
| `web/static/js/corthex-app.js` | `initWorkspace()`, 멘션/archive/logs/conversation org 필터 → workspace 기반 | f1d2d51 |
| `web/templates/index.html` | auth.role x-show 17곳 제거 → workspace.sidebarFilter 기반 | f1d2d51 |
| `CLAUDE.md` | role if/else 하드코딩 절대 금지 규칙 1순위 추가 | f1d2d51 |
| 전체 | sidebarFilter/mentionFilter를 org→cli_owner 기반으로 변경 | e0686f7 |

---

## 미완료 — 다음 세션에서 해야 할 것

### 1. 브랜치 정리 + 푸시
```bash
# 워크트리 브랜치 → claude/v5-sister-space에 머지 또는 직접 푸시
git push origin worktree-workspace-arch
# 또는 PR 생성
gh pr create --title "feat: v5.1 Config-driven Workspace (네이버+슬랙 모델)" --base main --head worktree-workspace-arch
```

### 2. 배포 후 QA (필수 — 버그 있으면 사형)

**CEO 계정 테스트:**
- [ ] 로그인 → 모든 탭 보이는지 (작전현황, 사령관실, 전략실, 통신로그, 작전일지, 기밀문서 + 전력분석, 자동화, 크론기지, 통신국, 정보국, ARGOS)
- [ ] 사이드바 → CEO CLI 에이전트만 보이는지 (비서실장, 리트마스터 4명, 금융분석팀장, saju_executive)
- [ ] 로그아웃 버튼 보이는지
- [ ] 사무실 뷰 → officeLayout 4개 섹션 정상 표시
- [ ] 기밀문서 → 전체/리트마스터/스케치바이브/사주/공통 필터 전부 보이는지
- [ ] 통신로그 → 전체 에이전트 로그 보이는지 (orgScope: null)
- [ ] @멘션 → CEO CLI 에이전트만 뜨는지
- [ ] 채팅 → 정상 작동

**누나(sister) 계정 테스트:**
- [ ] 로그인 → 모든 탭 보이는지 (CEO와 동일 — 네이버 모델)
- [ ] 사이드바 → sister CLI 에이전트만 보이는지 (saju_eden, saju_zoe, saju_sage)
- [ ] 비서실장, 리트마스터 본부 사이드바에 안 보이는지
- [ ] 로그아웃 버튼 보이는지
- [ ] 사무실 뷰 → 사주냥 TEAM 섹션만 표시
- [ ] 기밀문서 → 전체/리트마스터/스케치바이브/사주/공통 필터 전부 보이는지 (기능 동일), 데이터는 ?org=saju 필터
- [ ] 통신로그 → saju org 에이전트 로그만 보이는지 (orgScope: saju)
- [ ] @멘션 → sister CLI 에이전트만 뜨는지 (saju_eden, saju_zoe, saju_sage)
- [ ] 채팅 → 정상 작동
- [ ] 대화 목록 → saju org 대화만 보이는지

### 3. CLAUDE.md 전면 정리 (대표님 요청)
- 'v3 시절 처장 = 5번째 분석가' 같은 구식 규칙 제거
- 현재 아키텍처(v5.1 네이버+슬랙 모델) 반영
- role if/else 금지 규칙 최상단 유지

### 4. 문서 업데이트 (작업 완료 7단계)
- [ ] `docs/updates/2026-03-02_v51-workspace-architecture.md` 작성
- [ ] `docs/project-status.md` 업데이트
- [ ] `docs/todo/BACKLOG.md` 갱신

---

## 주의사항

1. **deploy.yml**: `config/workspaces.yaml`이 배포 시 서버에 복사되는지 확인. `config/` 폴더는 이미 배포 대상이므로 OK일 가능성 높지만 확인 필요.
2. **YAML→JSON 자동 변환**: `config_loader.py`의 `_load_config()`는 JSON 우선 → YAML 폴백. `deploy.yml`이 `yaml2json.py`로 변환하는지 확인. `workspaces.yaml` → `workspaces.json` 변환이 포함되어야 함.
3. **initWorkspace 타이밍**: 로그인 성공 후 + 페이지 새로고침 시(initAuth) 모두 호출됨. workspace 로드 실패 시 기본값 사용 (label:'', sidebarFilter:'all' 등).
4. **기존 v5 하드코딩 잔존 가능성**: `web/static/js/corthex-app.js`의 line 5042 근처 `bunbu === 'saju'` 헬퍼 함수 — 확인 필요.
