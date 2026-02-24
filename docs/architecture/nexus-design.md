# NEXUS — 시스템 탐색 & 시각화 공간

> 대표님 아이디어 #009 (2026-02-25)
> "마우스로 시스템 전체를 탐색하고, Claude와 시각적으로 논의하는 자비스 공간"

---

## 개요

NEXUS는 CORTHEX HQ의 **전체 시스템을 3D/캔버스로 시각화**하는 풀스크린 오버레이.
헤더의 채팅/사무실/대시보드 옆 4번째 버튼으로 진입, ESC로 닫기.

---

## 모드 2가지

### Mode 1: 3D 시스템 맵
- **라이브러리**: 3d-force-graph (WebGL/Three.js) + three-spritetext
- **노드 7종**: CORTHEX 허브 / UI 탭 13개 / 부서 7개 / 에이전트 29명 / 저장소 4개 / 외부서비스 8개 / 핵심프로세스 5개
- **시각화**: SpriteText 라벨 (색상 직사각형 + 한글 텍스트)
- **인터랙션**: 마우스 회전/줌/이동 + 에이전트 노드 클릭 → 사령관실 @멘션

### Mode 2: 비주얼 캔버스
- **라이브러리**: Drawflow (jerosoler)
- **노드 팔레트 7종**: 에이전트 / 시스템 / 외부API / 결정분기 / 시작 / 종료 / 메모
- **인터랙션**: 클릭 추가 / 포트 드래그 연결 / **더블클릭 노드 이름 편집** / JSON 저장·불러오기

---

## 알고리즘: _buildSystemGraphData()

```
입력: agentNodes (API /api/architecture/hierarchy), agentEdges
출력: { nodes[], links[], CAT{} }

1. 코어 허브 노드 1개 생성 (id: corthex_hq)
2. UI 탭 13개 생성 → 코어에 연결
3. 부서 7개 생성 → 코어에 연결
4. 에이전트 (API) → 소속 부서에 연결 (없으면 코어)
5. 저장소 4개 (SQLite, 아카이브, 지식베이스, 노션) → 코어 연결
6. 외부서비스 8개 (Anthropic, OpenAI, Google, 텔레그램, KIS, GitHub, CF, Oracle) → 코어 연결
7. 핵심프로세스 5개 (라우팅, QA, 재작업, 켈리, 소울) → 코어 연결
```

총 노드: ~70개 / 총 링크: ~80개

---

## 색상 코드

| 카테고리 | 색상 | 설명 |
|----------|------|------|
| core | #e879f9 | CORTHEX HQ 중심 허브 |
| tab | #60a5fa | UI 탭 (13개) |
| division | #a78bfa | 부서 (7개) |
| agent | #34d399 | 에이전트 (29명) |
| store | #fbbf24 | 데이터 저장소 |
| service | #fb923c | 외부 서비스 |
| process | #f87171 | 핵심 프로세스 |

---

## 재사용 가이드

이 설계는 다른 프로젝트에서도 사용 가능:
1. `_buildSystemGraphData()` 함수를 복사
2. 노드/엣지 데이터를 해당 프로젝트에 맞게 수정
3. 3d-force-graph + SpriteText CDN 로드
4. ForceGraph3D 초기화 코드 복사
