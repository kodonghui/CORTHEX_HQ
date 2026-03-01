---
paths:
  - "web/templates/**"
  - "web/static/**"
---

# 프론트엔드 규칙

`web/templates/` 또는 `web/static/` 파일 수정 시 이 규칙이 자동 적용됩니다.

## 필수 규칙

### 파일 수정
- `web/templates/index.html` — **Write 전체 덮어쓰기 절대 금지** → Edit 부분 수정만
- 단일 파일 3,000줄 초과 시 분리 BACKLOG에 추가

### 프레임워크
- Alpine.js `x-show` / `x-if` / `x-for` 사용. **jQuery 절대 금지**
- 새 라이브러리 추가 시 `_loadScript()` 동적 로드만. blocking `<script>` 금지

### 스타일
- **`hq-*` 컬러 토큰만** 사용. 임의 색상(`#fff`, `blue-500` 등) 금지
- **폰트**: Pretendard + JetBrains Mono 2개만. 새 Google 폰트 / `font-sans` 오버라이드 금지
- CSS `@import` 금지 → `<link rel="preload">` 사용

### 탭 구조
- 새 탭: `<template x-if>` 필수 (x-show는 home/command/schedule/knowledge 탭만)
- 탭 진입 시 lazy load (`switchTab()`). `init()`에 API 추가 금지

### SSE / 인터벌
- SSE 1개만 (`_connectCommsSSE()`). 추가 SSE 연결 금지
- `setInterval`은 탭 진입/이탈 시 등록/해제 관리

## 🚨 보안 — role 하드코딩 금지
```
금지:
x-show="auth.role === 'sister'"
x-if="auth.role == 'brother'"
if (auth.role === ...) { ... }

허용:
x-show="workspace.show_sister_tab"
x-if="workspace.feature_enabled"
```
위반 시 security-reviewer 에이전트 자동 호출.

## UI/UX 기준
- 새 기능 구현 전 WebSearch로 "best practices [기능명] 2026" 검색 필수
- 빈 상태 / 로딩 스켈레톤 / 에러 메시지 UX 반드시 구현
- 한국어 UI | KST 날짜/시간 표시

## 다이어그램 (HTML 뷰어)
- 다이어그램 생성 시 `.md` + `.html` + `file:///` URL 3벌 제공
- mermaid.js CDN + dark 테마 + `useMaxWidth: false`
