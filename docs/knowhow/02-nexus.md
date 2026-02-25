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

### 데이터 구조
```javascript
function buildSystemGraph() {
  const nodes = [];
  const links = [];

  // ① 중심 허브
  nodes.push({ id: 'hub', name: '내 프로젝트', category: 'core' });

  // ② 카테고리별 노드 + 허브 연결
  modules.forEach(m => {
    nodes.push({ id: m.id, name: m.name, category: 'module' });
    links.push({ source: 'hub', target: m.id });
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
const CATEGORY_SIZES = { core: 25, module: 12, feature: 5, api: 7, store: 8 };
```

### ForceGraph3D 초기화
```javascript
const Graph = ForceGraph3D()(document.getElementById('graph-container'))
  .graphData({ nodes, links })
  .backgroundColor('#060a14')
  .nodeColor(n => CATEGORY_COLORS[n.category])
  .nodeVal(n => CATEGORY_SIZES[n.category])
  .nodeLabel(n => `${n.name}\n(${n.category})`)
  .linkColor(() => 'rgba(255,255,255,0.12)')
  .linkWidth(0.4)
  .onNodeClick(n => { /* 노드 클릭 시 동작 */ })
  .d3AlphaDecay(0.02)
  .d3VelocityDecay(0.3);
setTimeout(() => Graph.cameraPosition({ z: 400 }), 500);
```

## 캔버스 더블클릭 이름 편집
```javascript
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

## 풀스크린 오버레이 패턴
```html
<template x-if="nexusOpen">
  <div class="fixed inset-0 z-50 flex flex-col bg-[#060a14]"
       @keydown.escape.window="nexusOpen = false">
    <!-- 헤더 + 본문 + 하단 범례 -->
  </div>
</template>
```
핵심: `fixed inset-0 z-50`, ESC 키로 닫기.

## Claude와 협업 가능성

캔버스 JSON을 서버에 저장 → Claude가 `/api/canvas/load`로 읽어서
시스템 구조를 시각적으로 이해하고 대표님과 논의 가능.
