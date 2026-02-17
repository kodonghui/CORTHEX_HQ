# FE 전수검사 결과 보고서

## 버전
3.01.001

## 작업 날짜
2026-02-18

## 작업 브랜치
claude/autonomous-system-v3

---

## 검사 대상 파일
`web/templates/index.html` (총 8,588줄)

---

## 검사 항목별 결과

### 1. 금지 모델명 검사

| 금지 모델명 | 발견 여부 | 처리 |
|------------|----------|------|
| `claude-haiku-4-6` | 없음 | - |
| `gpt-4o` | 없음 | - |
| `gpt-4o-mini` | 없음 | - |
| `gpt-4.1` | 없음 | - |
| `gpt-4.1-mini` | 없음 | - |
| `claude-sonnet-4-5-20250929` | 없음 | - |
| **`gpt-5.1`** | **발견 (2곳)** | **수정 완료** |

**버그 상세 — gpt-5.1:**
- **위치 1 (구 6576줄)**: `getModelDisplayName()` 함수의 표시명 매핑 딕셔너리
  ```javascript
  // 수정 전 (버그):
  'gpt-5.2': 'GPT-5.2',
  'gpt-5.1': 'GPT-5.1',   // ← 존재하지 않는 모델
  'gpt-5': 'GPT-5',

  // 수정 후:
  'gpt-5.2': 'GPT-5.2',
  'gpt-5': 'GPT-5',
  ```
- **위치 2 (구 6594줄)**: `_getDefaultReasoning()` 함수의 추론 레벨 매핑 딕셔너리
  ```javascript
  // 수정 전 (버그):
  'gpt-5': ['none','low','medium','high'],
  'gpt-5.1': ['none','low','medium','high'],   // ← 존재하지 않는 모델
  'gpt-5.2': ['none','low','medium','high','xhigh'],

  // 수정 후:
  'gpt-5': ['none','low','medium','high'],
  'gpt-5.2': ['none','low','medium','high','xhigh'],
  ```
- **수정 후 검증**: grep으로 `gpt-5.1` 0건 확인 완료

---

### 2. 허용 모델명 존재 여부 확인

CLAUDE.md의 허용 모델 10개 전부 정상 확인:

| 모델 ID | getModelDisplayName() | _getDefaultReasoning() | 상태 |
|---------|----------------------|----------------------|------|
| `claude-opus-4-6` | 'Claude Opus 4.6' | `['low','medium','high']` | 정상 |
| `claude-sonnet-4-6` | 'Claude Sonnet 4.6' | `['low','medium','high']` | 정상 |
| `claude-haiku-4-5-20251001` | 'Claude Haiku 4.5' | `[]` | 정상 |
| `gpt-5.2-pro` | 'GPT-5.2 Pro' | `['medium','high','xhigh']` | 정상 |
| `gpt-5.2` | 'GPT-5.2' | `['none','low','medium','high','xhigh']` | 정상 |
| `gpt-5` | 'GPT-5' | `['none','low','medium','high']` | 정상 |
| `gpt-5-mini` | 'GPT-5 Mini' | `['low','medium','high']` | 정상 |
| `gemini-3-pro-preview` | 'Gemini 3.0 Pro Preview' | `['low','high']` | 정상 |
| `gemini-2.5-pro` | 'Gemini 2.5 Pro' | `['low','medium','high']` | 정상 |
| `gemini-2.5-flash` | 'Gemini 2.5 Flash' | `['none','low','medium','high']` | 정상 |

---

### 3. bg-grid opacity 애니메이션 검사

**결과: 정상 (::before 패턴 올바르게 적용됨)**

줄 309-327에서 확인:
```css
.bg-grid { position: relative; }
.bg-grid::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: linear-gradient(...), linear-gradient(90deg, ...);
  background-size: 40px 40px;
  animation: gridPulse 8s ease-in-out infinite;  /* 가상 요소에만 적용 */
  pointer-events: none;
  z-index: 0;
}
.bg-grid > * { position: relative; z-index: 1; }
```
- gridPulse 애니메이션이 `.bg-grid` 본체가 아닌 `::before` 가상 요소에 적용됨
- 글자/카드/콘텐츠에 opacity 영향 없음
- 과거 사고(2026-02-15) 수정이 유지되고 있음

---

### 4. 기밀문서 탭 "전체 삭제" 버튼 확인

**결과: 정상 (버튼 존재함)**

줄 3428-3432에서 확인:
```html
<button @click="showDeleteAllArchiveModal = true"
        class="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-500/30 transition"
        x-show="archive.files.length > 0">
  전체 삭제
</button>
```
- 클릭 시 `showDeleteAllArchiveModal = true`로 확인 모달 열림
- 파일이 하나도 없을 때는 `x-show`로 숨김 (정상 UX)
- 줄 5464-5481에 확인 모달도 정상 구현됨
- 줄 7811-7825에 `deleteAllArchives()` 함수도 정상 구현됨

---

### 5. 작전현황 탭 (home 탭) 확인

**결과: 정상**

- 탭 ID: `home`, 레이블: `작전현황` (줄 5505)
- 데이터 표시: `dashboard.todayTasks`, `dashboard.todayCompleted`, `dashboard.totalCost` 등 Alpine.js 바인딩 정상
- `loadDashboard()` 함수 (줄 6890-6926): `/api/dashboard`, `/api/budget`, `/api/quality` 3개 API 병렬 호출 정상
- 배포 상태 표시: `loadDeployStatus()` (줄 6928-6960): `deploy-status.json` + GitHub Actions API 호출 정상
- 대시보드 카드들: 오늘 명령 수, 완료, 실패, 비용 카드 모두 올바른 데이터 바인딩

---

### 6. 사령관실 탭 (command 탭) 확인

**결과: 정상**

- 탭 ID: `command`, 레이블: `사령관실` (줄 5506)
- 채팅 메시지 타입: `user`, `processing`, `result`, `error` — 모두 구현됨
- 배치 토글: `useBatch` 상태변수 + WebSocket `batch` 파라미터 전송 (줄 6213)
- 배치 진행 상태: `batchProgress` 객체 + WebSocket `batch_chain_progress` 이벤트 처리 (줄 6010-6021)
- 슬래시 명령어 자동완성: `/전체`, `/순차`, `/도구점검`, `/배치실행`, `/배치상태` 등 8개 명령어 (줄 5576-5584)
- @멘션 기능: `agentNames` 딕셔너리 기반 필터링 (줄 6307-6311)
- 중복 응답 방지: `task_id + content` 기반 중복 체크 (줄 6072-6082)

---

### 7. SNS 통신국 연결 상태 확인

**결과: 정상**

줄 7828-7838에서 `loadSNS()` 함수 확인:
```javascript
async loadSNS() {
  const [status, oauth] = await Promise.all([
    fetch('/api/sns/status').then(r => r.ok ? r.json() : {}),
    fetch('/api/sns/oauth/status').then(r => r.ok ? r.json() : {}),
  ]);
  this.sns.status = status;
  this.sns.oauthStatus = oauth;
}
```
- `/api/sns/status`와 `/api/sns/oauth/status` 2개 API 병렬 호출
- `sns.oauthStatus` 객체에 저장됨
- 플랫폼 연결 상태는 이 객체를 통해 표시됨 (정상)

---

### 8. 작전일지 탭 (history 탭) 확인

**결과: 정상**

- 다중 선택 (bulkDelete, bulkBookmark, bulkTag, bulkArchive) 모두 구현됨
- `/api/tasks/bulk` POST — `action`, `task_ids` 파라미터로 호출 (줄 7129-7138)
- 그룹핑: `getGroupedTaskHistory()` — 오늘/어제/날짜별 그룹화 (줄 8337-8371)
- 페이지네이션: `taskHistoryPage × taskHistoryPageSize` 기반 (줄 8333-8377)
- 작업 비교 모달: `compareMode`, `compareA`, `compareB` 상태 정상 구현

---

### 9. JavaScript 상태 변수 구조 확인

**결과: 정상**

- `corthexApp()` 함수 (줄 5484): Alpine.js 앱 진입점
- 탭 목록 (`tabs` 배열, 줄 5504-5516): 11개 탭 정의
- 에이전트 이름 매핑 (`agentNames`, 줄 5726-5756): 28명 에이전트 하드코딩 (동적 로딩으로 덮어씌워짐)
- `loadAgentsAndTools()` (줄 7524-7557): `/api/agents`, `/api/tools` API에서 동적 로드 — 하드코딩을 덮어씌움

---

## 수정 완료 항목 요약

| # | 위치 | 문제 | 조치 |
|---|------|------|------|
| 1 | 줄 6576 (구) | `'gpt-5.1': 'GPT-5.1'` — 존재하지 않는 모델명 하드코딩 | 해당 줄 삭제 |
| 2 | 줄 6594 (구) | `'gpt-5.1': ['none','low','medium','high']` — 존재하지 않는 모델명 하드코딩 | 해당 줄 삭제 |

---

## 이상 없음 확인 항목

| 항목 | 상태 |
|------|------|
| bg-grid opacity 애니메이션 (::before 분리) | 정상 |
| 기밀문서 전체 삭제 버튼 | 정상 |
| 작전현황 탭 데이터 표시 | 정상 |
| 사령관실 탭 배치 UI | 정상 |
| SNS 통신국 연결 상태 표시 | 정상 |
| claude-sonnet-4-6 표시명 매핑 | 정상 |
| 모든 허용 모델 10개 존재 확인 | 정상 |
| 다크모드 전환 로직 | 정상 |
| 키보드 단축키 (Ctrl+K, Esc) | 정상 |

---

## grep 최종 검증 결과 (0건 확인)

```
gpt-5.1        : 0건
claude-haiku-4-6 : 0건
gpt-4o         : 0건
gpt-4.1        : 0건
claude-sonnet-4-5-20250929 : 0건
```

---

## 다음에 할 일

- 없음 (이번 검사에서 발견된 모든 버그 수정 완료)
- gpt-5.1은 CLAUDE.md의 허용 모델 목록에 없는 모델 — 향후 모델 추가/변경 시 CLAUDE.md 체크리스트 10단계를 반드시 따를 것
