# 04. 디자인 시스템 패턴 (2026 Edition)

> 비유: 인테리어 통일 규칙 — 벽지, 조명, 가구 스타일을 미리 정해두면 어떤 방을 꾸며도 일관됨

---

## 목표

| 항목 | 나쁜 예 | 좋은 예 | 효과 |
|------|---------|---------|------|
| 색상 | `#3b82f6` 하드코딩 100곳 | CSS 변수 1곳 수정 → 전체 반영 | 다크모드 5분 완성 |
| 폰트 | Google Fonts 5종 import | Variable Font 1~2종 | 로딩 -60% |
| 간격 | `margin: 13px`, `17px` 랜덤 | 4px 배수 체계 (4/8/12/16/24/32) | 정돈된 화면 |
| 반응형 | `@media (max-width: 768px)` 30곳 | Container Query 컴포넌트 단위 | 재사용성 10배 |

---

## 1. 색상 시스템 — OKLCH + 다크모드 자동화

### OKLCH가 뭔가? (2025~2026 CSS 표준)

> 비유: 기존 RGB는 "빨강 얼마, 초록 얼마, 파랑 얼마" → 사람 눈과 안 맞음
> OKLCH는 "밝기 / 채도 / 색상각도" → **사람이 느끼는 대로** 색을 조절

```css
/* ❌ 기존 RGB/HSL — 같은 채도인데 눈으로 보면 밝기가 다름 */
--blue: hsl(220, 80%, 50%);   /* 어두워 보임 */
--yellow: hsl(50, 80%, 50%);  /* 밝아 보임 */

/* ✅ OKLCH — 같은 L(밝기)이면 진짜로 같은 밝기 */
--blue: oklch(0.55 0.20 250);
--yellow: oklch(0.55 0.20 85);
/* 두 색이 눈으로 봐도 동일한 밝기! */
```

### 다크모드 자동화 트릭

```css
:root {
  --surface-l: 0.97;  /* 라이트모드 밝기 */
  --text-l: 0.15;
}
[data-theme="dark"] {
  --surface-l: 0.12;  /* 다크모드 — 밝기만 뒤집기 */
  --text-l: 0.92;
}

/* 색상 정의 — 밝기(L)만 변수, 나머지 고정 */
--surface-0: oklch(var(--surface-l) 0.01 260);
--surface-1: oklch(calc(var(--surface-l) + 0.04) 0.01 260);
--surface-2: oklch(calc(var(--surface-l) + 0.08) 0.02 260);
--text-primary: oklch(var(--text-l) 0.01 260);
```

**핵심**: 밝기(L) 값 하나만 바꾸면 라이트↔다크 전환 완료.

### 다크모드 팔레트 규칙

```
❌ 순검정(#000000) 배경 — 눈 피로, OLED 번인
✅ 레이어드 팔레트:

surface-0: oklch(0.12 ...)  — 최하위 배경 (거의 검정)
surface-1: oklch(0.16 ...)  — 카드/패널
surface-2: oklch(0.20 ...)  — 호버/활성
surface-3: oklch(0.24 ...)  — 팝업/모달

※ Material Design 3 + NN/g 연구 기반
```

---

## 2. 타이포그래피 — Variable Font + Fluid + 한국어

### Variable Font (가변 폰트)

> 비유: 기존 = 얇은 책 / 보통 책 / 두꺼운 책 3권 따로 구매
> 가변 폰트 = **두께 조절 다이얼이 달린 책 1권**으로 전부 가능

```css
/* ❌ 기존 — weight별 파일 3~5개 다운로드 (300KB × 5 = 1.5MB) */
@font-face { font-family: 'Pretendard'; font-weight: 400; src: url(Regular.woff2); }
@font-face { font-family: 'Pretendard'; font-weight: 700; src: url(Bold.woff2); }

/* ✅ Variable Font — 1파일에 모든 weight (500KB) */
@font-face {
  font-family: 'Pretendard';
  font-weight: 100 900;  /* 100~900 자유롭게 */
  src: url(PretendardVariable.woff2) format('woff2-variations');
}

/* 사용: 아무 숫자나 가능 */
h1 { font-weight: 750; }   /* 700도 800도 아닌 딱 750 */
```

### Fluid Typography (반응형 글자 크기)

> 비유: 모바일(작은 화면)에선 14px, 데스크탑(큰 화면)에선 18px
> 중간 크기 화면에서는? **자동으로 16px쯤** → 브레이크포인트 필요 없음

```css
/* ❌ 브레이크포인트마다 수동 조절 */
body { font-size: 14px; }
@media (min-width: 768px) { body { font-size: 16px; } }
@media (min-width: 1024px) { body { font-size: 18px; } }

/* ✅ clamp() 한 줄이면 끝 */
body {
  font-size: clamp(0.875rem, 0.75rem + 0.5vw, 1.125rem);
  /* 최소 14px — 화면에 비례 — 최대 18px */
}

/* 제목 계층도 같은 패턴 */
h1 { font-size: clamp(1.75rem, 1.2rem + 2vw, 3rem); }    /* 28~48px */
h2 { font-size: clamp(1.375rem, 1rem + 1.5vw, 2.25rem); } /* 22~36px */
h3 { font-size: clamp(1.125rem, 0.9rem + 1vw, 1.75rem); } /* 18~28px */
```

### 한국어 특화

```css
/* 한국어 본문 최적 설정 */
body {
  font-family: 'Pretendard Variable', 'Pretendard', system-ui, sans-serif;
  word-break: keep-all;      /* 한국어 단어 단위 줄바꿈 */
  overflow-wrap: break-word;  /* 긴 URL 등 강제 줄바꿈 */
  letter-spacing: -0.01em;   /* 한글은 약간 좁게 */
  line-height: 1.7;          /* 한글은 영문보다 높게 (1.5 → 1.7) */
}

/* 코드/수치: JetBrains Mono */
code, .mono {
  font-family: 'JetBrains Mono Variable', monospace;
  font-feature-settings: 'liga' on;  /* 리거처: != → ≠ 등 */
}
```

---

## 3. 간격·레이아웃 — Container Queries + 4px 그리드

### 4px 기본 단위 (8pt Grid)

> 비유: 레고 블록 — 모든 블록이 같은 규격이니까 뭘 조합해도 맞음

```css
:root {
  --space-1: 0.25rem;  /* 4px — 아이콘과 텍스트 사이 */
  --space-2: 0.5rem;   /* 8px — 요소 내부 패딩 */
  --space-3: 0.75rem;  /* 12px */
  --space-4: 1rem;     /* 16px — 카드 패딩 */
  --space-6: 1.5rem;   /* 24px — 섹션 간격 */
  --space-8: 2rem;     /* 32px — 큰 섹션 */
  --space-12: 3rem;    /* 48px — 페이지 섹션 */
}

/* Tailwind과 호환 (p-1 = 4px, p-2 = 8px, ...) */
```

### Container Queries (2025~ 표준)

> 비유: 기존 반응형 = "건물 크기에 따라 가구 배치"
> Container Query = "각 **방 크기**에 따라 가구 배치" → 컴포넌트 재사용 자유

```css
/* ❌ 기존 — viewport 기준 (사이드바 안에 넣으면 깨짐) */
@media (min-width: 768px) {
  .card { display: grid; grid-template-columns: 1fr 1fr; }
}

/* ✅ Container Query — 부모 크기 기준 */
.card-wrapper {
  container-type: inline-size;  /* "이 박스를 기준으로 삼아" */
}

@container (min-width: 400px) {
  .card { display: grid; grid-template-columns: 1fr 1fr; }
}
/* → 사이드바(300px)에선 1열, 메인(800px)에선 2열. 자동! */
```

**브라우저 지원**: Chrome 105+, Safari 16+, Firefox 110+ → 2026년 기준 100%

### CSS Subgrid

```css
/* 카드 리스트에서 제목/본문/버튼 높이를 자동 정렬 */
.card-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-6);
}
.card {
  display: grid;
  grid-template-rows: subgrid;  /* 부모 그리드 행에 맞춤 */
  grid-row: span 3;             /* 제목 / 본문 / 버튼 = 3행 */
}
```

---

## 4. 컴포넌트 패턴

### 스켈레톤 로딩 (Skeleton Screen)

> 비유: 레스토랑에서 빈 접시·수저를 미리 세팅 → "곧 음식 나옵니다" 느낌
> NN/g 연구: 스피너보다 체감 대기시간 **-30%**

```css
/* 스켈레톤 기본 애니메이션 */
.skeleton {
  background: linear-gradient(
    90deg,
    oklch(0.20 0.01 260) 25%,
    oklch(0.25 0.01 260) 37%,
    oklch(0.20 0.01 260) 63%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 0.25rem;
}
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

```html
<!-- 사용 예: 카드 스켈레톤 -->
<div class="card">
  <div class="skeleton h-5 w-3/4 mb-3"></div>   <!-- 제목 자리 -->
  <div class="skeleton h-3 w-full mb-2"></div>   <!-- 본문 1줄 -->
  <div class="skeleton h-3 w-5/6 mb-2"></div>    <!-- 본문 2줄 -->
  <div class="skeleton h-8 w-24 mt-4"></div>     <!-- 버튼 자리 -->
</div>
```

### Empty State (빈 상태)

> 비유: 빈 냉장고를 열었을 때 "장 볼 목록 추천" 메모가 붙어있는 것

```html
<!-- ❌ 그냥 빈 화면 -->
<div></div>

<!-- ✅ Empty State — 안내 + 행동 유도 -->
<div class="flex flex-col items-center justify-center py-16 text-center">
  <!-- 아이콘 (크기 48~64px) -->
  <svg class="w-16 h-16 text-hq-muted/40 mb-4">...</svg>
  <!-- 제목 -->
  <h3 class="text-lg font-semibold text-hq-text mb-2">아직 데이터가 없습니다</h3>
  <!-- 설명 -->
  <p class="text-sm text-hq-muted mb-6 max-w-sm">
    첫 번째 항목을 추가하면 여기에 표시됩니다
  </p>
  <!-- 행동 유도 버튼 -->
  <button class="px-4 py-2 bg-accent text-white rounded-lg">
    + 새로 만들기
  </button>
</div>
```

### Toast 알림

```javascript
// 위치: 우측 하단 고정
// 자동 사라짐: 3~5초
// 종류: success(초록) / error(빨강) / info(파랑) / warning(노랑)

function showToast(message, type = 'info', duration = 4000) {
  const toast = document.createElement('div');
  const colors = {
    success: 'bg-emerald-500/90',
    error: 'bg-red-500/90',
    info: 'bg-blue-500/90',
    warning: 'bg-amber-500/90',
  };
  toast.className = `fixed bottom-4 right-4 z-[9999] px-4 py-3 rounded-lg
    text-white text-sm font-medium shadow-lg backdrop-blur
    ${colors[type]} animate-slide-in`;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('animate-slide-out');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}
```

### Modal (모달 다이얼로그)

```html
<!-- 규칙: ESC 닫기 + 배경 클릭 닫기 + 포커스 트랩 -->
<template x-if="modalOpen">
  <div class="fixed inset-0 z-50 flex items-center justify-center"
       @keydown.escape.window="modalOpen = false">
    <!-- 배경 오버레이 -->
    <div class="absolute inset-0 bg-black/60 backdrop-blur-sm"
         @click="modalOpen = false"></div>
    <!-- 모달 본체 -->
    <div class="relative bg-surface-1 rounded-xl shadow-2xl
                max-w-lg w-full mx-4 p-6"
         @click.stop>
      <h2 class="text-lg font-bold mb-4">제목</h2>
      <div class="mb-6">내용</div>
      <div class="flex justify-end gap-3">
        <button @click="modalOpen = false"
                class="px-4 py-2 text-sm text-hq-muted hover:text-hq-text">
          취소
        </button>
        <button class="px-4 py-2 text-sm bg-accent text-white rounded-lg">
          확인
        </button>
      </div>
    </div>
  </div>
</template>
```

---

## 5. 인터랙션 — View Transitions + Scroll + Micro

### View Transitions API (탭 전환 애니메이션)

> 비유: 파워포인트 슬라이드 전환 효과 — 페이지가 "뚝" 바뀌지 않고 부드럽게

```javascript
// ❌ 기존 — 탭 전환이 즉시 (딱딱한 느낌)
function switchTab(tab) {
  this.activeTab = tab;
}

// ✅ View Transitions — 크로스페이드 전환
async function switchTab(tab) {
  if (!document.startViewTransition) {
    this.activeTab = tab;  // 미지원 브라우저 폴백
    return;
  }
  document.startViewTransition(() => {
    this.activeTab = tab;
  });
}
```

```css
/* 전환 커스터마이징 */
::view-transition-old(root) {
  animation: fade-out 200ms ease-out;
}
::view-transition-new(root) {
  animation: fade-in 200ms ease-in;
}

/* 특정 요소에 이름 부여 → 개별 전환 */
.card { view-transition-name: card-hero; }
```

**브라우저**: Chrome 111+, Safari 18.2+, Firefox 126+

### Scroll-driven Animations (스크롤 기반 애니메이션)

> 비유: 스크롤하면 자연스럽게 나타나는 요소 — JavaScript 없이 CSS만으로

```css
/* 스크롤하면 페이드인 */
.reveal {
  animation: fade-slide-up linear both;
  animation-timeline: view();
  animation-range: entry 0% entry 100%;
}

@keyframes fade-slide-up {
  from { opacity: 0; transform: translateY(30px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* 스크롤 진행률 표시 바 */
.progress-bar {
  animation: grow-width linear;
  animation-timeline: scroll();
  transform-origin: left;
}
@keyframes grow-width {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}
```

### Micro-interactions (미세 인터랙션)

> 비유: 엘리베이터 버튼 누르면 불 들어오는 것 — "눌렸다"는 피드백

```css
/* 버튼 클릭 피드백 — 200ms 이내 */
.btn {
  transition: transform 150ms ease, box-shadow 150ms ease;
}
.btn:active {
  transform: scale(0.97);
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.2);
}

/* 토글 스위치 — 300ms */
.toggle-knob {
  transition: transform 300ms cubic-bezier(0.4, 0, 0.2, 1);
}

/* 호버 하이라이트 — 카드 */
.card {
  transition: transform 200ms ease, box-shadow 200ms ease;
}
.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(0,0,0,0.15);
}

/* ⚡ 규칙: 애니메이션 시간 */
/* 즉각 반응: 100~200ms (버튼, 토글) */
/* 전환: 200~400ms (패널 열기, 탭 전환) */
/* 강조: 400~700ms (알림 등장, 축하 효과) */
/* 800ms 초과 금지 — 느려 보임 */
```

---

## 6. AI UI 패턴 — Streaming + Progressive Disclosure

### SSE 토큰 스트리밍 렌더링

> 비유: 친구가 카톡 치는 걸 실시간으로 보는 것 (다 쳐서 보내기 vs 글자마다 보이기)

```javascript
// SSE 스트리밍 — 토큰 단위 실시간 표시
async function streamResponse(url, targetEl) {
  const response = await fetch(url);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();  // 미완성 라인 보관

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = JSON.parse(line.slice(6));
      if (data.token) {
        targetEl.textContent += data.token;
        // 자동 스크롤
        targetEl.scrollTop = targetEl.scrollHeight;
      }
    }
  }
}
```

### 타이핑 인디케이터

```css
/* AI가 생각 중일 때 점 3개 애니메이션 */
.typing-indicator span {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.4;
  animation: typing-bounce 1.4s infinite ease-in-out;
}
.typing-indicator span:nth-child(1) { animation-delay: 0ms; }
.typing-indicator span:nth-child(2) { animation-delay: 200ms; }
.typing-indicator span:nth-child(3) { animation-delay: 400ms; }

@keyframes typing-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-4px); opacity: 1; }
}
```

### Progressive Disclosure (점진적 공개)

> 비유: 뉴스 기사 → 제목 먼저 → 클릭하면 본문 → 더보기 누르면 상세

```html
<!-- 단계별 정보 공개 -->
<!-- Level 1: 한 줄 요약 (항상 보임) -->
<div class="flex items-center justify-between">
  <span>분석 완료: 매수 추천 (신뢰도 87%)</span>
  <button @click="expanded = !expanded" class="text-accent text-sm">
    상세 보기 ▾
  </button>
</div>

<!-- Level 2: 상세 내용 (클릭 시) -->
<template x-if="expanded">
  <div class="mt-3 space-y-2 text-sm text-hq-muted">
    <p>근거 1: RSI 30 이하 과매도 구간</p>
    <p>근거 2: 거래량 3일 연속 증가</p>
    <button @click="showRaw = true" class="text-accent">
      원본 데이터 →
    </button>
  </div>
</template>

<!-- Level 3: 원본 데이터 (요청 시만) -->
<template x-if="showRaw">
  <pre class="mt-2 p-3 bg-surface-0 rounded text-xs overflow-x-auto">
    { "rsi": 28.4, "volume_change": [1.2, 1.5, 1.8], ... }
  </pre>
</template>
```

---

## 7. 접근성 (Accessibility)

### 모션 감소 (Reduced Motion)

> 비유: 놀이기구 타기 싫은 사람에게 강제로 태우지 않는 것

```css
/* 사용자가 "애니메이션 줄여줘" 설정했을 때 */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
  .skeleton { animation: none; background: oklch(0.22 0.01 260); }
}
```

### 명도 대비 (Contrast)

```
WCAG AA 기준:
- 일반 텍스트: 4.5:1 이상
- 큰 텍스트(18px+): 3:1 이상
- UI 요소(버튼 테두리 등): 3:1 이상

다크모드에서 흔한 실수:
❌ 회색 텍스트 oklch(0.45 ...) on 배경 oklch(0.12 ...) → 대비 2.8:1 (불합격)
✅ 회색 텍스트 oklch(0.60 ...) on 배경 oklch(0.12 ...) → 대비 5.2:1 (합격)
```

### 키보드 내비게이션

```css
/* 포커스 링 — 마우스에선 숨기고, 키보드에선 표시 */
:focus-visible {
  outline: 2px solid oklch(0.70 0.15 250);
  outline-offset: 2px;
}
:focus:not(:focus-visible) {
  outline: none;
}
```

---

## 8. 체크리스트 — 새 프로젝트 시작 시

### 기본 설정 (Day 1)

- [ ] 색상 토큰 정의 (OKLCH 기반, surface-0~3 + accent + text)
- [ ] 다크모드 변수 세팅 (`--surface-l` 밝기 토글 방식)
- [ ] 폰트 2종 선택 (본문 Variable + 코드 Mono)
- [ ] Fluid Typography 설정 (`clamp()` 3단계: body/h2/h1)
- [ ] 간격 체계 확정 (4px 배수: 4/8/12/16/24/32/48)
- [ ] `[x-cloak] { display: none }` CSS 추가 (Alpine.js 필수)

### 컴포넌트 (Week 1)

- [ ] 스켈레톤 로딩 컴포넌트 (shimmer 애니메이션)
- [ ] Empty State 템플릿 (아이콘 + 메시지 + CTA)
- [ ] Toast 알림 시스템 (success/error/info/warning)
- [ ] Modal 기본 틀 (ESC + 배경 클릭 + 포커스 트랩)
- [ ] 버튼 3종 (primary/secondary/ghost) + active 피드백

### 인터랙션 (Week 2)

- [ ] View Transitions 탭 전환 (폴백 포함)
- [ ] Micro-interaction: 버튼(150ms) / 카드 호버(200ms) / 토글(300ms)
- [ ] `prefers-reduced-motion` 대응
- [ ] 키보드 `:focus-visible` 스타일

### AI 기능이 있다면

- [ ] SSE 스트리밍 렌더러 (토큰 단위)
- [ ] 타이핑 인디케이터 (점 3개 bounce)
- [ ] Progressive Disclosure 3단계 (요약 → 상세 → 원본)

---

## CORTHEX 실전 적용

| 패턴 | 적용 현황 | 효과 |
|------|-----------|------|
| 다크모드 | `hq-*` 토큰 체계 | 테마 변경 CSS 1줄 |
| Variable Font | Pretendard + JetBrains Mono | 폰트 파일 2개 |
| Fluid Type | `clamp()` 미적용 (향후) | — |
| Container Query | 미적용 (향후) | — |
| 스켈레톤 | 차트/분석 로딩 | 체감 속도 향상 |
| Toast | `showToast()` 전역 | 알림 통일 |
| SSE 스트리밍 | `_connectCommsSSE()` | 실시간 AI 응답 |
| Empty State | 일부 탭 적용 | 빈 화면 방지 |
| View Transitions | 미적용 (향후) | — |
| Micro-interactions | 버튼/카드 hover | 피드백 즉각 |

---

## 참고 자료

- [OKLCH Color Space](https://oklch.com/) — Evil Martians 도구
- [W3C Design Tokens](https://design-tokens.github.io/community-group/format/) — 2025.10 안정화
- [Material Design 3](https://m3.material.io/) — 다크모드 가이드
- [Smashing Magazine: Fluid Typography](https://www.smashingmagazine.com/2022/01/modern-fluid-typography-css-clamp/)
- [NN/g: Skeleton Screens](https://www.nngroup.com/articles/skeleton-screens/) — 체감 속도 연구
- [MDN: View Transitions API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transitions_API)
- [MDN: Container Queries](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_containment/Container_queries)
