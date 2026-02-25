# 03. 웹 속도 최적화 패턴

> 비유: 배달 속도 최적화 — 주문 넣자마자 바로 오게 만드는 것

---

## 목표

| 지표 | 나쁨 | 목표 | CORTHEX 실적 |
|------|------|------|-------------|
| 첫 화면 표시 (FCP) | 3초+ | 1.5초 이하 | 1.2초 |
| DOM 노드 수 | 8,000+ | 3,000 이하 | ~2,800 |
| 폰트 | 3종+ | 2종 이하 | 2종 |

## 규칙 7가지

### 1. CDN 동적 로드 (`_loadScript` 패턴)

```javascript
const _scriptCache = {};
function _loadScript(url) {
  if (_scriptCache[url]) return _scriptCache[url];
  _scriptCache[url] = new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${url}"]`)) { resolve(); return; }
    const s = document.createElement('script');
    s.src = url; s.onload = resolve; s.onerror = reject;
    document.head.appendChild(s);
  });
  return _scriptCache[url];
}

// 사용: 차트 탭 들어갈 때만 Chart.js 로드
async switchToChart() {
  await _loadScript('https://cdn.jsdelivr.net/npm/chart.js');
}
```

### 2. Lazy 렌더링 (`template x-if`)

```html
<!-- ❌ x-show: 숨겨도 DOM에 존재 (메모리 차지) -->
<div x-show="activeTab === 'chart'">무거운 차트...</div>

<!-- ✅ x-if: 조건 충족 시에만 DOM 생성 -->
<template x-if="activeTab === 'chart'">
  <div>무거운 차트...</div>
</template>
```

**규칙**: 메인 4개 탭만 `x-show`, 나머지는 전부 `template x-if`.

### 3. 폰트 최소화

```html
<!-- ✅ 2개만, preload로 -->
<link rel="preload" href="/fonts/Pretendard.woff2" as="font" crossorigin>
<link rel="preload" href="/fonts/JetBrainsMono.woff2" as="font" crossorigin>
```

### 4. SSE/WebSocket 1개만

```javascript
// ✅ 하나의 연결에서 이벤트 타입으로 구분
const sse = new EventSource('/api/comms-stream');
sse.addEventListener('chat', handler);
sse.addEventListener('log', handler);
sse.addEventListener('trade', handler);
```

### 5. 타이머 탭 관리

```javascript
// ✅ 탭 진입 시 시작, 이탈 시 정리
switchTab(tab) {
  clearInterval(this._timer);
  if (tab === 'trading') {
    this._timer = setInterval(() => this.refreshPrices(), 30000);
  }
}
```

### 6. CSS @import 금지

`@import` → 추가 네트워크 요청 (렌더 차단). `preload` 사용.

### 7. init()에 API 추가 금지

```javascript
// ✅ 각 탭 진입 시에만 로드
async switchTab(tab) {
  if (tab === 'trading') await this.loadTrading();
}
```
