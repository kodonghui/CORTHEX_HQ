# NEXUS — 시스템 탐색 & 비주얼 설계 공간

> CEO 아이디어: "자비스처럼 시스템을 시각적으로 탐색하고, 마우스로 그리면서 Claude와 논의"
> 재사용: 이 설계는 다른 프로젝트에서도 적용 가능한 패턴

## 핵심 컨셉

- **전체화면 오버레이**: 헤더 바(채팅/사무실/대시보드)에서 직접 접근, ESC로 닫기
- **2가지 모드**: 3D 시스템 맵 + 비주얼 캔버스
- **Claude 연동 구상**: 캔버스 JSON을 Claude가 읽어서 시각적 논의 (MCP 연결 시)

## Mode 1: 3D 시스템 맵

### 기술 스택
- `3d-force-graph` (vasturiano) — WebGL / Three.js 기반
- `three-spritetext` — 3D 공간에 텍스트 라벨 렌더링

### 데이터 구조 (7개 카테고리)
```
노드 카테고리:
├── core      — CORTHEX HQ (중앙 허브, 크기 22)
├── tab       — UI 탭 13종 (작전현황, 사령관실, ...)
├── division  — 부서 7개 (비서실, CIO팀, CTO팀, ...)
├── agent     — 에이전트 29명 (API에서 동적 로드)
├── store     — 데이터 저장소 3종 (SQLite, 기밀문서, 지식베이스)
├── service   — 외부 서비스 8종 (Telegram, KIS, Claude API, ...)
└── process   — 핵심 프로세스 5종 (라우팅, QA, 반려, Kelly, Soul진화)
```

### 인터랙션
- 마우스 회전/줌/이동 (Three.js OrbitControls)
- 에이전트 노드 클릭 → 사령관실 이동 + @에이전트 자동입력
- 부서별 색상, 직급별 크기, 카테고리별 구분

### 알고리즘
```
1. CDN 로드: forcegraph3d + spritetext (병렬)
2. GET /api/architecture/hierarchy → 에이전트 노드/엣지
3. _buildSystemGraphData() → 7개 카테고리 노드 + 연결선 구축
4. ForceGraph3D 초기화:
   - nodeThreeObject → SpriteText (색상 배경 + 테두리 + 한글 라벨)
   - onNodeClick → 에이전트면 사령관실 이동
   - d3AlphaDecay: 0.02, warmupTicks: 50
5. 카메라 초기 위치: z=350
```

## Mode 2: 비주얼 캔버스

### 기술 스택
- `Drawflow` (jerosoler) — 순수 JS 노드 에디터, MIT 라이선스

### 노드 팔레트 (7종)
| 타입 | 라벨 | 색상 |
|------|------|------|
| agent | 에이전트 | #8b5cf6 |
| system | 시스템 | #3b82f6 |
| api | 외부 API | #059669 |
| decide | 결정 분기 | #f59e0b |
| start | 시작 | #22c55e |
| end | 종료 | #ef4444 |
| note | 메모 | #6b7280 |

### 인터랙션
- 팔레트 클릭 → 캔버스에 노드 추가
- 포트 드래그 → 연결선 생성
- **더블클릭 → 노드 이름 수정** (인라인 input 변환)
- Ctrl+S → JSON 저장 (`knowledge/flowcharts/`)
- 저장된 캔버스 불러오기/초기화

### 저장 형식
```json
{
  "drawflow": {
    "Home": {
      "data": {
        "1": { "name": "agent", "data": { "label": "CIO" }, "html": "...", "pos_x": 200, "pos_y": 200, ... }
      }
    }
  }
}
```

## 전체화면 오버레이 패턴

```
구현 방식:
- fixed inset-0 z-50 (전체 화면 덮기)
- 헤더바에서 NEXUS 버튼 클릭 → nexusOpen = true
- ESC 키 또는 X 버튼 → nexusOpen = false
- Alpine.js x-if="nexusOpen" (닫혀있으면 DOM에 없음)

UI 구조:
┌─────────────────────────────────────┐
│ [NEXUS 로고] [3D맵|캔버스]    [ESC] │ ← 헤더
├─────────────────────────────────────┤
│                                     │
│      3D 시스템 맵 or 캔버스         │ ← 메인 영역
│                                     │
├─────────────────────────────────────┤
│ [범례/색상 가이드]    [조작법 안내]  │ ← 하단바 (3D만)
└─────────────────────────────────────┘
```

## 재사용 가이드 (다른 프로젝트)

1. **CDN 3개** 추가: forcegraph3d, spritetext, drawflow (+css)
2. **_loadScript / _loadCSS** 헬퍼 복사
3. **_buildSystemGraphData()** 함수를 프로젝트에 맞게 수정 (노드/엣지 정의)
4. **HTML 오버레이** 템플릿 복사 (fixed inset-0 z-50 패턴)
5. **Drawflow 더블클릭 편집** 패턴 복사 (dblclick → input 변환)
