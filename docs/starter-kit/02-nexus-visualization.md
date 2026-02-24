# 02. NEXUS — 시스템 시각화 패턴

> 비유: 지하철 노선도 — 복잡한 시스템을 한눈에 보는 지도

---

## 핵심 개념

NEXUS = **마우스로 시스템을 탐색하는 공간**

어떤 프로젝트든 이 3가지가 있으면 "시스템 전체를 파악"할 수 있음:
1. **3D 네트워크 그래프** — 구성요소 간 관계를 공간에서 탐색
2. **비주얼 캔버스** — 직접 노드를 그려가며 설계
3. **풀스크린 오버레이** — 일반 UI와 분리된 몰입 공간

## 기술 스택 (검증 완료)

| 기능 | 라이브러리 | CDN |
|------|-----------|-----|
| 3D 그래프 | 3d-force-graph (vasturiano) | `unpkg.com/3d-force-graph@1` |
| 캔버스 에디터 | Drawflow (jerosoler) | `cdn.jsdelivr.net/npm/drawflow` |
| 전체화면 UI | Alpine.js + Tailwind | 프레임워크 무관 |

## 3D 그래프 구현 패턴

### 데이터 구조 설계

```javascript
// 어떤 시스템이든 이 구조로 표현 가능
function buildSystemGraph() {
  const nodes = [];
  const links = [];

  // ① 중심 허브 (프로젝트 이름)
  nodes.push({ id: 'hub', name: '내 프로젝트', category: 'core' });

  // ② 카테고리별 노드 생성 + 허브 연결
  modules.forEach(m => {
    nodes.push({ id: m.id, name: m.name, category: 'module' });
    links.push({ source: 'hub', target: m.id });
  });

  // ③ 하위 항목 → 상위 항목 연결
  features.forEach(f => {
    nodes.push({ id: f.id, name: f.name, category: 'feature' });
    links.push({ source: f.parentModule, target: f.id });
  });

  return { nodes, links };
}
```

### 색상/크기 규칙

```javascript
const CATEGORY_COLORS = {
  core:    '#e879f9',  // 핑크 — 중심 허브
  module:  '#60a5fa',  // 파랑 — 주요 모듈
  feature: '#34d399',  // 초록 — 세부 기능
  api:     '#fb923c',  // 주황 — 외부 연동
  store:   '#fbbf24',  // 노랑 — 데이터 저장소
};

const CATEGORY_SIZES = {
  core: 25, module: 12, feature: 5, api: 7, store: 8,
};
```

### ForceGraph3D 초기화

```javascript
const Graph = ForceGraph3D()(document.getElementById('graph-container'))
  .graphData({ nodes, links })
  .backgroundColor('#060a14')
  .nodeColor(n => CATEGORY_COLORS[n.category])
  .nodeVal(n => CATEGORY_SIZES[n.category])
  .nodeOpacity(0.9)
  .nodeLabel(n => `${n.name}\n(${n.category})`)
  .linkColor(() => 'rgba(255,255,255,0.12)')
  .linkWidth(0.4)
  .onNodeClick(n => { /* 노드 클릭 시 동작 */ })
  .d3AlphaDecay(0.02)
  .d3VelocityDecay(0.3);

// 카메라 줌아웃
setTimeout(() => Graph.cameraPosition({ z: 400 }), 500);
```

## 캔버스 구현 패턴

### 초기화 + 더블클릭 이름 편집

```javascript
const editor = new Drawflow(document.getElementById('canvas'));
editor.reroute = true;
editor.start();

// 더블클릭으로 노드 이름 편집
el.addEventListener('dblclick', (e) => {
  const nodeEl = e.target.closest('.my-node');
  if (!nodeEl) return;
  const current = nodeEl.textContent.trim();
  const input = document.createElement('input');
  input.value = current;
  nodeEl.textContent = '';
  nodeEl.appendChild(input);
  input.focus();
  input.addEventListener('blur', () => {
    nodeEl.textContent = input.value.trim() || current;
  }, { once: true });
});
```

### 저장/불러오기

```javascript
// 저장: JSON 직렬화
const data = editor.export();
await fetch('/api/save', {
  method: 'POST',
  body: JSON.stringify({ content: JSON.stringify(data, null, 2) })
});

// 불러오기: JSON 역직렬화
const saved = await fetch('/api/load').then(r => r.json());
editor.import(JSON.parse(saved.content));
```

## 풀스크린 오버레이 패턴

```html
<!-- Alpine.js 예시 -->
<template x-if="nexusOpen">
  <div class="fixed inset-0 z-50 flex flex-col bg-[#060a14]">
    <!-- 헤더: 로고 + 모드 전환 + ESC 닫기 -->
    <!-- 본문: 3D 또는 캔버스 -->
    <!-- 하단: 범례 또는 안내 -->
  </div>
</template>
```

핵심: `fixed inset-0 z-50`으로 전체 화면 덮기, ESC 키로 닫기.

## CORTHEX 실전 적용

| 카테고리 | 노드 수 | 예시 |
|----------|---------|------|
| 코어 | 1 | CORTHEX HQ |
| UI 탭 | 13 | 홈, 사령관실, 투자, ... |
| 부서 | 7 | 비서실, 기술개발처, ... |
| 에이전트 | 29 | CIO, 전문가 4명, ... |
| 저장소 | 4 | SQLite, 노션, ... |
| 외부서비스 | 8 | Anthropic, KIS, ... |
| 프로세스 | 5 | 라우팅, QA, ... |
| **합계** | **~70** | |
