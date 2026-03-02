# NEXUS 캔버스 Mermaid 네이티브 전환

## 날짜: 2026-03-02

## 변경 내용
- **Drawflow 라이브러리 완전 제거** → Mermaid.js를 캔버스 엔진으로 직접 사용
- **변환 0번 아키텍처**: 사용자가 보는 것 = Claude가 읽는 것 = 저장되는 것 (Mermaid 코드가 SSOT)
- **노드 8종 지원**: 에이전트, 시스템, 외부API, 결정분기, 데이터베이스(신규), 시작, 종료, 메모
- **SVG 인터랙션**: 클릭 선택, 더블클릭 이름 편집, Delete 삭제, 연결 모드
- **자동 레이아웃**: Mermaid Dagre 엔진 (LR/TD/RL/BT 전환 가능)
- **레거시 호환**: 기존 Drawflow JSON 파일 자동 마이그레이션

## 수정 파일
- `web/static/js/corthex-app.js` — Drawflow → Mermaid 네이티브 전면 교체
- `web/templates/index.html` — NEXUS 오버레이 HTML 수정
- `web/handlers/sketchvibe_handler.py` — Drawflow 파싱 ~150줄 제거, Mermaid 직접 저장
- `web/mcp_sketchvibe.py` — read_canvas() Mermaid 코드 직접 반환

## CEO 아이디어
"칠판 자체를 mermaid가 들어갈 수 있게 최적화 하는거야. 본질적으로."
→ Drawflow ↔ Mermaid 변환 갭을 원천 제거하는 근본 해결
