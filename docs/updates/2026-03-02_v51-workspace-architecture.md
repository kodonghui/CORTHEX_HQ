# 2026-03-02 — v5.1 Config-driven Workspace Architecture (빌드 #762)

## 핵심 변경

**role if/else 전면 폐기** → `config/workspaces.yaml` 설정 기반 동적 렌더링

### 네이버+슬랙 모델
- **네이버 모델**: 같은 기능(탭/뷰/NEXUS), 다른 데이터(에이전트/로그/문서)
- **슬랙 모델**: 사이드바/@멘션 = 내 CLI 직원만 (`cli_owner` 기반 필터)
- **새 사람 추가**: `workspaces.yaml` 프로파일 1개 추가 + 인증 추가. **코드 수정 0줄**

## PR #730 — 변경 파일 8개

| 파일 | 변경 |
|------|------|
| `config/workspaces.yaml` | 신규 — CEO/sister 워크스페이스 프로파일 |
| `config/yaml2json.py` | workspaces 변환 추가 (배포 시 JSON 생성) |
| `web/config_loader.py` | `load_workspace_profiles()` + `get_workspace_profile()` |
| `web/arm_server.py` | `GET /api/workspace-profile` 엔드포인트 |
| `web/static/js/corthex-app.js` | `initWorkspace()`, workspace 기반 필터 (role if/else 17곳 제거) |
| `web/templates/index.html` | `workspace.sidebarFilter` 기반 렌더링 (x-show role 제거) |
| `CLAUDE.md` | v5.1 워크스페이스 규칙 반영, v3 잔재 제거 |
| `docs/handoff/2026-03-02_v51-workspace-impl.md` | 구현 핸드오프 문서 |

## 제거된 하드코딩 패턴 (전부 → workspace.* 대체)

```javascript
// 전부 제거됨:
if (this.auth.role === 'sister') { ... }
x-show="auth.role !== 'sister'"
x-show="auth.role === 'sister'"
this.auth.role === 'sister' ? '?org=saju' : ''
id.startsWith('saju_')
```

## QA 결과

| 항목 | CEO | 누나 | 상태 |
|------|-----|------|------|
| workspace-profile API | label: "CEO 관제", 4섹션 | label: "사주냥 관제", 1섹션 | ✅ |
| sidebarFilter | `ceo` (CEO CLI) | `sister` (sister CLI) | ✅ |
| orgScope | `null` (전체) | `saju` (격리) | ✅ |
| 데이터 격리 | CEO 데이터 전체 | saju 데이터만 | ✅ |

## architecture.md 업데이트
- sidebarFilter/mentionFilter: org 기반 → **cli_owner 기반**으로 수정
- PATTERN-10-v2: `a.org ===` → `a.cli_owner ===` 코드 예시 수정
- HTML 예시: 실제 구현(x-show + cli_owner 필터) 반영
