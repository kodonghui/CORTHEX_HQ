# 2026-02-25 — 설계실(플로우차트) 탭 + 뼈대 다이어그램

## 작업 요약

대표님 아이디어: "전체 기능 뼈대 플로우차트를 먼저 그리고, 새 기능 추가 시 이어붙이는 방식"

### 완료 항목

✅ **뼈대 플로우차트 문서 6개** (`docs/architecture/flowcharts/` + `knowledge/flowcharts/`)
- 00-top-level.md — 최상위 전체 구조
- 01-agent-org.md — 에이전트 29명 조직도
- 02-request-flow.md — 명령 처리 흐름 (Level 1~4 라우팅)
- 03-trading-flow.md — CIO 매매 신호 7단계
- 04-ui-tabs.md — 13개 탭 기능 맵
- 05-data-flow.md — 데이터 저장 흐름

✅ **설계실 탭 신규 추가** (더보기 탭 마지막)
- 3분할 레이아웃: 파일 사이드바 | Mermaid 코드 에디터 | 미리보기 캔버스
- 실시간 렌더링 (400ms 디바운스, 타이핑하면 자동 그림)
- 마우스 휠 줌 + 드래그 패닝 (Excalidraw UX 오마주)
- VS Code 스타일 에디터 (라인 번호 + 다크 테마 + Tab 들여쓰기)
- Ctrl+S 저장 단축키
- SVG 내보내기 버튼
- 템플릿 4종 (flowchart/sequence/ER/mindmap)
- 전체화면 미리보기 토글
- 새 다이어그램 생성 모달

✅ **CLAUDE.md 규칙 추가** — "새 기능 구현 시 최신 레퍼런스 분석 후 착수" (172줄)

## 레퍼런스 오마주

| 참조 도구 | 차용한 요소 |
|-----------|-------------|
| Mermaid Live Editor (mermaid.live) | 코드 + 미리보기 분할 레이아웃 |
| VS Code | 라인 번호, 다크 에디터, Ctrl+S |
| Excalidraw | 마우스 휠 줌, 드래그 패닝, 격자 배경 |
| Linear | 파일 사이드바 그룹화 (뼈대/내 작업) |

## 수정 파일

- `web/templates/index.html` — 설계실 HTML 템플릿 추가
- `web/static/js/corthex-app.js` — flowchart 상태/함수 추가 (약 150줄)
- `docs/architecture/flowcharts/` — 신규 폴더 + 6개 파일
- `knowledge/flowcharts/` — 신규 폴더 + 5개 파일 (웹 UI용)
- `CLAUDE.md` — 레퍼런스 분석 규칙 추가

## 향후 논의 중인 아이디어

- **3D 플로우차트**: `3d-force-graph` 라이브러리 (WebGL) — 조직도/아키텍처 3D 뷰
- **자비스 비전**: 모든 시스템을 시각적으로 연결하고 논의하는 설계 공간
