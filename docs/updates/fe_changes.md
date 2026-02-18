# FE 팀원 작업 보고

## 작업 날짜
2026-02-18

## 수정 파일
`web/templates/index.html` (단 하나의 파일만 수정)

---

## 작업 1: @멘션 드롭다운 투명도 수정

### 문제
- `@멘션` 드롭다운 컨테이너에 `z-10`이 걸려 있고 CSS 변수(`var(--hq-panel)`) 기반 배경을 쓰고 있어서 불투명도 보장이 안 됨
- 뒤에 있는 채팅 내용이 비쳐 보이는 버그 발생

### 수정 내용

**변경 위치: 2077~2079번 줄**

```html
<!-- 수정 전 -->
<div x-show="showMentionDropdown" x-transition
     class="absolute bottom-full mb-2 left-0 w-72 rounded-xl overflow-hidden shadow-2xl z-10"
     style="background: var(--hq-panel, #1a1f2e); border: 1px solid var(--hq-border, #2a3040);">

<!-- 수정 후 -->
<div x-show="showMentionDropdown" x-transition
     class="absolute bottom-full mb-2 left-0 w-72 rounded-xl overflow-hidden shadow-2xl z-50"
     :style="darkMode
       ? 'background:#0d1117; border:1px solid #374158; box-shadow:0 8px 32px rgba(0,0,0,0.6);'
       : 'background:#ffffff; border:1px solid #d1d5db; box-shadow:0 8px 32px rgba(0,0,0,0.12);'">
```

- `z-10` → `z-50`: z-index 높여서 다른 요소 위에 올라오도록
- `darkMode` Alpine.js 변수 기반으로 다크/밝은 모드 배경색 분리
- 다크: `#0d1117` (완전 불투명 진한 배경)
- 밝은: `#ffffff` (완전 흰색)
- 그룹 헤더 배경도 다크모드에 맞게 동적 처리 (`#111827` vs `#f3f4f6`)

---

## 작업 2: @멘션 ↔ 수신자 드롭다운 통합

### 문제
- @멘션 드롭다운: 부서별 그룹화
- 수신자 선택 드롭다운: 직급별 분류 (비서실장/처장/전문가), 하드코딩
- 두 UI가 연동 안 됨 → @멘션으로 에이전트 선택해도 수신자 드롭다운이 그대로

### 수정 내용

**1) insertMention 함수에 targetAgentId 자동 세팅 추가 (약 6351번 줄)**

```javascript
insertMention(agent) {
  // ... 기존 텍스트 입력 로직 ...
  this.showMentionDropdown = false;
  // 추가된 줄: @멘션 선택 시 수신자 드롭다운도 해당 에이전트로 자동 세팅
  this.targetAgentId = agent.id;
  // ...
}
```

**2) 수신자 드롭다운 하드코딩 제거 → 동적 생성으로 교체 (약 2112번 줄)**

```html
<!-- 수정 전: 하드코딩된 optgroup 30개+ -->
<optgroup label="── 비서실 ──">
  <option value="chief_of_staff">비서실장 (직접)</option>
</optgroup>
<optgroup label="── 처장 직접 ──">
  <!-- ... 7개 하드코딩 ... -->
</optgroup>
<optgroup label="── 전문가 직접 ──">
  <!-- ... 18개 하드코딩 ... -->
</optgroup>

<!-- 수정 후: Alpine.js로 agentNames + agentDivision 기반 동적 생성 -->
<template x-for="group in getRecipientGroups()" :key="group.label">
  <optgroup :label="'── ' + group.label + ' ──'">
    <template x-for="agent in group.agents" :key="agent.id">
      <option :value="agent.id" x-text="agent.name"></option>
    </template>
  </optgroup>
</template>
```

**3) getRecipientGroups() 함수 추가 (약 6357번 줄)**

```javascript
getRecipientGroups() {
  const divLabels = { 'secretary': '비서실', 'tech': '기술개발처', ... };
  const divOrder = ['secretary', 'tech', 'strategy', 'legal', 'marketing', 'finance', 'publishing'];
  const allAgents = Object.entries(this.agentNames)
    .map(([id, name]) => ({ id, name, div: this.agentDivision[id] || '' }));
  // 부서별 그룹화 후 반환
}
```

- 새 에이전트가 agents.yaml에 추가되면 수신자 드롭다운에도 자동 반영됨 (하드코딩 불필요)

---

## 작업 3: 진행률 표시 — 가짜 % → 도구 호출 횟수 기반 실제 %

### 문제
- `simulateProgress()` 함수가 0.8ms마다 랜덤으로 0.05~0.15씩 진행률을 올려서 0.9(=90%)까지 증가
- 에이전트가 막 시작했는데 80~90%로 표시되는 가짜 진행률

### 수정 내용

**1) agentToolCallCount 변수 추가 (5483번 줄)**

```javascript
agentToolCallCount: {},  // 에이전트별 도구 호출 횟수 (진행률 계산용)
```

**2) agent_status 이벤트 처리 로직 교체 (약 5957번 줄)**

```javascript
// 수정 전: 백엔드에서 받은 progress 값 그대로 사용 + simulateProgress 호출
this.activeAgents[d.agent_id] = {
  status: d.status,
  progress: d.progress || 0,  // 0.2, 0.5 등 고정값
  detail: d.detail || '',
};
if (d.status === 'working' && d.progress < 0.9) {
  this.simulateProgress(d.agent_id);  // 랜덤 증가
}

// 수정 후: 도구 호출 횟수 기반 진행률 계산
// detail에 "🔧"가 있으면 도구 호출로 감지 → 카운터 증가
// 진행률 = 카운터 / 5 (최대 5회 = 100%)
if (d.detail && d.detail.includes('🔧')) {
  this.agentToolCallCount[d.agent_id] = Math.min(count + 1, 5);
}
toolProgress = callCount / 5;  // 0%, 20%, 40%, 60%, 80%, 100%
```

**3) simulateProgress 함수 제거 (약 6177번 줄)**

- 가짜 랜덤 진행률 함수 삭제 → 주석으로 대체

**4) sendMessage에서 카운터 초기화 (약 6200번 줄)**

```javascript
this.agentToolCallCount = {};  // 새 메시지 전송 시 카운터 리셋
```

**5) 작업 완료 시 카운터 리셋 (약 6138번 줄)**

```javascript
this.agentToolCallCount[id] = 0;  // done 전환 시 리셋
```

### 진행률 대응표
| 도구 호출 횟수 | 진행률 |
|---|---|
| 0회 (시작) | 0% |
| 1회 | 20% |
| 2회 | 40% |
| 3회 | 60% |
| 4회 | 80% |
| 5회 이상 | 100% |
| 완료 (done) | 100% |

---

## 현재 상태
- 3개 작업 모두 완료
- 수정 파일: `web/templates/index.html` 1개만 수정
- 다른 파일 건드리지 않음

---

## 추가 작업 (2차): WebSocket 실시간 연동 + 협업 흐름도 패널

### 변경 내용 요약 (한 줄)
delegation_log를 8초 폴링에서 WebSocket 실시간 수신으로 전환하고, 협업 흐름도 시각화 패널 추가 — `handleWsMessage`에 `delegation_log_update` case 삽입, `toggleDelegationLog`에서 `setInterval(8000)` 제거, `showCollabFlow` Alpine.js 상태 변수 추가, 흐름도 토글 버튼 + 흐름도 패널 HTML 삽입

### 수정 항목
1. `case 'delegation_log_update'` — handleWsMessage switch문에 추가 (6192줄)
2. `setInterval(() => this.fetchDelegationLogs(), 8000)` 제거 — toggleDelegationLog 단순화
3. `showCollabFlow: false` — Alpine.js data 객체에 추가 (5647줄)
4. 흐름도 토글 버튼 — 내부통신 패널 헤더에 추가 (2070줄)
5. 협업 흐름도 패널 HTML — delegation_log 패널 바로 다음에 삽입 (2143줄)
