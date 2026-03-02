# SketchVibe 이용법

> NEXUS 캔버스 + Claude Code 협업 다이어그램 도구.
> 대표님이 노드로 그림 → Claude가 읽고 Mermaid로 덧그림 → "맞아"로 캔버스에 반영 → 반복.

---

## 기본 워크플로우

```
1. NEXUS에서 노드 그리기 (팔레트 클릭 → 드래그)
2. 저장 버튼 클릭
3. Claude Code에게 "이거 봐줘" / "DB 노드 추가해줘" 등 말하기
4. Claude가 read_canvas로 읽고 Mermaid 다이어그램 전송 → 오버레이 표시
5. "✓ 맞아" 클릭 → Claude 그림이 캔버스에 노드로 반영
6. 원하면 노드 추가/수정 → 다시 저장 → 다시 말하기 → 반복
```

"← 캔버스로" 클릭 = Claude 그림 버리고 원래 캔버스로 복귀 (아니야 효과)

---

## 노드 팔레트

| 노드 | 색상 | 용도 |
|------|------|------|
| 에이전트 | 보라 | AI 에이전트, 처리 주체 |
| 시스템 | 파랑 | 서버, 백엔드, 내부 컴포넌트 |
| 외부 API | 초록 | 외부 서비스, REST API |
| 결정 분기 | 주황 | if/else 조건 분기 (다이아몬드) |
| 시작 | 연두 | 플로우 시작점 (pill 모양) |
| 종료 | 빨강 | 플로우 종료점 (원형) |
| 메모 | 회색 | 주석, 설명 |

---

## 캔버스 조작

| 동작 | 방법 |
|------|------|
| 노드 추가 | 팔레트 버튼 클릭 (뷰포트 중앙에 배치됨) |
| 노드 삭제 | 노드 클릭 → Delete 키 |
| 노드 이름 변경 | 노드 더블클릭 → 인라인 입력 |
| 연결선 그리기 | 노드 오른쪽 점 드래그 → 다른 노드 왼쪽 점 |
| 연결선 라벨 | 연결선 더블클릭 → 설명 입력 |
| 저장 | 상단 "저장" 버튼 (이름 없으면 입력 프롬프트) |
| 불러오기 | 왼쪽 저장된 캔버스 목록 클릭 |
| 삭제 | 저장된 캔버스 hover → × 버튼 |
| 초기화 | 상단 "초기화" 버튼 |

---

## Claude Code에서 사용하는 도구

```
read_canvas   → 현재 저장된 캔버스 읽기 (텍스트 파싱 결과)
update_canvas → Mermaid 코드 전송 → 브라우저 오버레이 표시
```

### 예시 사용법
```
# 대표님이 저장 후 "이거 봐줘" 하면:
1. read_canvas 호출 → 노드/연결 파악
2. 분석 후 Mermaid 코드 작성
3. update_canvas(mermaid_code) → 브라우저에 오버레이 표시
4. 대표님이 "맞아" → 캔버스에 노드로 반영됨
```

---

## Mermaid → Drawflow 변환 규칙

Claude가 전송한 Mermaid가 "맞아" 후 아래 규칙으로 노드로 변환:

| Mermaid 문법 | 변환 노드 | 모양 |
|-------------|---------|------|
| `id([label])` | start | pill |
| `id((label))` | end | 원형 |
| `id{label}` | decide | 다이아몬드 |
| `id[(label)]` | db | 원통 |
| `id>label]` | note | 각진 말풍선 |
| `id[label]` | system/agent/api | 네모 |
| `A -->|label| B` | 연결 + 라벨 | - |

---

## 저장 위치

- 캔버스 파일: `knowledge/flowcharts/이름.json` (서버 파일시스템)
- Claude 읽기용: SQLite `sketchvibe:current_canvas` (저장 버튼 클릭 시 자동 업데이트)

---

## 관련 파일

- 핸들러: `web/handlers/sketchvibe_handler.py`
- 프론트엔드: `web/static/js/corthex-app.js` (`initNexusCanvas`, `_importMermaidToCanvas`, `_parseMermaidNodes`)
- UI: `web/templates/index.html` (NEXUS 섹션, `x-show="currentTab === 'nexus'"`)
