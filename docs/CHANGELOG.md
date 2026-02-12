# CORTHEX HQ 변경 이력 (Changelog)

> 이 문서는 CORTHEX HQ의 버전별 변경 사항을 기록합니다.
> 노션에 붙여넣어 팀 기록으로 활용하세요.

---

## v0.4.0 (2026-02-12) - 홈페이지 UI/UX 전면 리디자인

> 상태: **구현 완료**

### 한 줄 요약

**CEO 관제실 웹 UI를 브랜드 시스템부터 마이크로 인터랙션까지 5가지 축으로 전면 리디자인하여, "아무 관리자 페이지"에서 "AI 기업 커맨드 센터"로 정체성을 확립했습니다.**

---

### 왜 바꿨나?

v0.3.0까지의 UI는 기능적으로는 동작했지만, 디자인 관점에서 여러 문제가 있었습니다:

| 문제 | 상세 |
|------|------|
| 웰컴 화면이 약함 | `🏢` 이모지 + 텍스트 2줄로는 25명 AI 에이전트 기업의 임팩트가 전달 안 됨 |
| 브랜드 아이덴티티 부재 | 로고 없음, "CORTHEX"라는 이름의 테크/코텍스 느낌이 UI에 반영 안 됨 |
| 사이드바 답답함 | 288px에 조직도 + 활동로그를 욱여넣어 숨이 막힘, 에이전트 시각 구분 불가 |
| 채팅 영역 밋밋함 | 유저/결과/에러 메시지가 비슷비슷한 박스, 에이전트 라이브 감 부족 |
| 인터랙션 부족 | 기본 fade-in만 존재, 호버/포커스 피드백 없음 |

---

### 뭘 바꿨나?

**5가지 핵심 축으로 전면 개편:**

#### 1. 브랜드 시스템 구축

**SVG 로고 신규 제작:**
- 헥사곤(6각형) 형태의 뉴럴 네트워크 심볼 — "코텍스(Cortex)" 컨셉 반영
- 중앙 노드 + 6방향 시냅스 라인 + 이중 헥사곤 보더
- 상단바(28px)와 웰컴 화면(72px) 두 가지 사이즈로 사용

**컬러 시스템 확장:**

| 토큰 | v0.3.0 | v0.4.0 | 용도 |
|------|--------|--------|------|
| `hq-bg` | `#0f172a` | `#0a0e1a` (더 깊은 다크) | 전체 배경 |
| `hq-surface` | — | `#111827` (신규) | 사이드바, 입력바 |
| `hq-cyan` | — | `#06b6d4` (신규) | LEET Master 본부 컬러 |
| `hq-purple` | — | `#8b5cf6` (신규) | 투자분석 본부 컬러 |
| `hq-muted` | — | `#64748b` (신규) | 비활성 텍스트 |
| `hq-text` | — | `#e2e8f0` (신규) | 기본 텍스트 |
| `hq-green` | `#22c55e` | `#10b981` (조정) | 성공/완료 |

**그라디언트 팔레트:**
```
cyan (#06b6d4) → blue (#3b82f6) → purple (#8b5cf6)
```
- `.gradient-text` — 텍스트에 그라디언트 적용 (로고, 타이틀)
- `.glow-cyan/blue/purple` — 요소별 글로우 이펙트
- `.glass` — 글래스모피즘 (반투명 + 블러 배경)

**타이포그래피:**
- `Inter` (300~800 웨이트 확장) — UI 전체
- `JetBrains Mono` (신규) — 모든 모노스페이스 요소 (비용, 토큰, 상태 코드)

#### 2. 웰컴 화면 전면 리디자인

**v0.3.0 (Before):**
```
🏢
CORTHEX HQ
25명의 AI 에이전트가 대기하고 있습니다.

[🖥️ 기술 스택 제안] [📊 주가 분석] [📋 이용약관 작성] [📣 마케팅 전략]
```

**v0.4.0 (After):**
```
[72px 헥사곤 SVG 로고 + 블러 글로우]

CORTHEX HQ  ← 그라디언트 텍스트
AI Agent Corporation Command Center
25 agents across 5 divisions, ready for your command

[4 Divisions] [25 Agents] [5 Tools] [2 LLMs]  ← 글래스 stat 카드

┌─────────────────┐  ┌─────────────────┐
│ [코드 아이콘]    │  │ [차트 아이콘]    │
│ 기술 스택 제안   │  │ 주가 분석        │
│ CTO + 기술팀이...│  │ 4명의 투자분석...│
└─────────────────┘  └─────────────────┘
┌─────────────────┐  ┌─────────────────┐
│ [문서 아이콘]    │  │ [마케팅 아이콘]  │
│ 이용약관 작성   │  │ 마케팅 전략      │
│ CLO + 법무팀이...│  │ CMO + 마케팅팀...│
└─────────────────┘  └─────────────────┘
```

**변경 포인트:**
- 이모지 제거 → SVG 아이콘 전면 교체
- 가로 나열 → 2x2 그리드 카드형
- 프리셋별 담당 팀 설명 추가 ("CTO + 기술팀이 최적의 아키텍처를 설계합니다")
- 글래스모피즘 카드 + hover-lift 인터랙션
- 채팅 영역 배경에 `.bg-grid` (미세 그리드 패턴 + 펄스 애니메이션) 추가

#### 3. 사이드바 리팩토링

**에이전트 아바타 시스템 도입:**

| 레벨 | v0.3.0 | v0.4.0 |
|------|--------|--------|
| CEO | `👤` 이모지 + 텍스트 | 28px 아바타 (blue-purple 그라디언트) + "Command Center" 서브타이틀 |
| 본부 (LEET/투자) | `🏗️`/`📊` 이모지 | 28px 아바타 (LM/FN 이니셜, 디비전 컬러) |
| 처장 (CTO 등) | `●` 작은 점 | 28px 아바타 (CTO/CSO/CLO/CMO/CIO 이니셜) |
| Specialist/Worker | `●` 작은 점 | 1.5px 상태 점 (유지, 호버 반응 추가) |

**상태 표시 개선:**

| 요소 | v0.3.0 | v0.4.0 |
|------|--------|--------|
| 섹션 상태 | 텍스트 ("3명 작업중") | 뱃지 (`bg-yellow/15 border-yellow/20`, "3 active") |
| 에이전트 작업중 | 이름만 표시 | 이름 + 실시간 % 표시 (font-mono) |
| 접기 화살표 | `▼`/`▶` 텍스트 전환 | `▶` 유니코드 + `rotate-90` CSS 트랜지션 |
| 트리 호버 | `hover:bg-white/5` | `hover:bg-white/[0.03]` (더 미세한 반응) |

**활동 로그 개선:**
- 고정 48px 높이 → **접이식 토글** (최대 208px)
- 건수 카운트 뱃지 추가 (`activityLogs.length`)
- 로그 항목에 `.log-item` 호버 하이라이트
- agent_id를 cyan 컬러로 강조
- 최대 표시 20건 → 30건

#### 4. 채팅 UX 업그레이드

**유저 메시지 (CEO Command):**
- 배경: `bg-hq-accent/20` → `bg-gradient-to-br from-hq-accent/20 to-hq-purple/10`
- CEO 아바타 아이콘 추가 (5px 라운드, user 실루엣 SVG)
- 라벨: "CEO" → "CEO COMMAND" (uppercase tracking-wider)
- `.glow-blue` 글로우 이펙트

**처리중 표시 (Agents Working):**
- 타이틀 옆 3-dot 펄스 애니메이션 (staggered delay)
- 에이전트별 아바타 + 이니셜 (getAgentInitials/getAgentAvatarClass)
- 프로그레스 바: 단색 blue → `bg-gradient-to-r from-hq-yellow to-hq-accent`

**결과 카드 (Result):**

| 요소 | v0.3.0 | v0.4.0 |
|------|--------|--------|
| 구조 | 단일 박스 | **헤더 / 바디 분리** (border-b) |
| 헤더 | 이름 + 시간/비용 텍스트 | 이름 + 시계 아이콘/달러 아이콘 + 모노 값 |
| 바디 | 텍스트 직접 | padding 분리, 여유 있는 레이아웃 |
| 보더 | `border-hq-border` | `border-hq-green/20` (성공 테마) |
| 배경 | `bg-hq-panel` | `.glass` (반투명 블러) |

**에러 메시지:**
- 텍스트 "오류" → SVG 경고 삼각형 아이콘 + "ERROR" (uppercase)

#### 5. 마이크로 인터랙션 추가

| 클래스 | 효과 | 적용 위치 |
|--------|------|-----------|
| `.hover-lift` | translateY(-2px) + shadow 24px | 프리셋 카드 |
| `.hover-glow` | box-shadow 24px blue/12% + border 밝아짐 | 프리셋 카드, stat 카드 |
| `.input-glow` | focus 시 ring 3px blue/15% + glow 20px | 명령 입력 필드 |
| `.fade-in-up` | opacity 0→1 + translateY 12→0px | 메시지 등장 |
| `.slide-in-left` | opacity 0→1 + translateX -16→0px | 사이드바 요소 |
| `.log-item:hover` | background blue/5% | 활동 로그 항목 |
| `.agent-avatar:hover` | scale(1.1) | 에이전트 아바타 |
| `rotate-90 transition` | 200ms 회전 트랜지션 | 트리 접기 화살표 |
| 3-dot stagger pulse | 0s/0.3s/0.6s delay | 처리중 인디케이터 |

**상단바 개선:**
- `header` → `.glass` (반투명 블러 + z-20)
- 시스템 상태: 텍스트 → 뱃지형 (`bg-green/10 border-green/20 rounded-lg`)
- 상태 라벨: "대기중/처리중/오류" → "READY/PROCESSING/ERROR"
- 비용/토큰: SVG 아이콘 추가 (달러, 태그)
- 연결 상태: "연결됨/연결 끊김" → "LIVE/OFFLINE" (font-mono)
- `CEO MODE` 뱃지 추가 (cyan 테마)

**입력바 개선:**
- 배경: `.glass` → `bg-hq-surface/80 backdrop-blur-sm`
- 입력 필드: `focus:ring-1` → `.input-glow` (커스텀 글로우)
- Enter 힌트 표시 (`⏎`, 빈 입력 시에만 표시)
- 전송 버튼: 단색 blue → `bg-gradient-to-r from-hq-accent to-hq-purple`
- 전송 버튼 hover: `shadow-lg shadow-hq-accent/20`
- 보내기 라벨: "보내기/처리중" → "Send/Working"

**마크다운 스타일 개선:**
- `code` 인라인: `#334155` → `#0f172a` + cyan 글자색 (`#7dd3fc`) + border
- `pre` 블록: border 추가, 더 깊은 배경
- `blockquote`: blue 좌측 보더 + muted 텍스트
- `a` 링크: blue + underline-offset
- 테이블 헤더: semibold + muted 텍스트

---

### 수정된 파일 (1개)

| 파일 | 변경 | 규모 |
|------|------|------|
| `web/templates/index.html` | UI/UX 전면 리디자인 | **+670줄 / -251줄** (727줄 → 1146줄) |

**변경 없는 파일:** 백엔드(app.py), WebSocket(ws_manager.py), 에이전트(agents.yaml), JavaScript 로직(WebSocket 핸들링, Alpine.js 상태 관리) — 모두 100% 호환 유지

---

### JavaScript 변경 사항

**추가된 데이터:**

| 속성 | 용도 |
|------|------|
| `logExpanded` | 활동 로그 접기/펼치기 상태 |
| `agentInitials` | 에이전트 ID → 이니셜 매핑 (25명) |
| `agentColorMap` | 디비전 → 아바타 컬러 클래스 매핑 |

**추가된 메서드:**

| 메서드 | 용도 |
|--------|------|
| `getAgentInitials(id)` | 에이전트 아바타 이니셜 반환 (FE, BE, AI 등) |
| `getAgentAvatarClass(id)` | 디비전 기반 아바타 CSS 클래스 반환 |
| `getSectionBadgeClass(section)` | 섹션 상태 뱃지 CSS 클래스 반환 (hidden/yellow/green) |

**변경된 기본값:**

| 항목 | v0.3.0 | v0.4.0 |
|------|--------|--------|
| 비활성 에이전트 dot | `bg-amber-500` | `bg-hq-muted/40` |
| 섹션 상태 텍스트 | "3명 작업중 / 2명 완료" | "3 active / 2 done" |

---

### Before vs After 비교

```
v0.3.0 웰컴 화면:                    v0.4.0 웰컴 화면:
┌─────────────────────┐              ┌─────────────────────┐
│                     │              │   ⬡ (SVG 로고+글로우) │
│     🏢              │              │                     │
│  CORTHEX HQ         │              │  CORTHEX HQ (그라디언트)│
│  25명의 AI 에이전트... │              │  AI Agent Corporation│
│                     │              │                     │
│ [🖥️ 기술] [📊 주가]  │              │ [4] [25] [5] [2]    │
│ [📋 약관] [📣 마케팅] │              │                     │
│                     │              │ ┌────────┐┌────────┐ │
│                     │              │ │<> 기술  ││📈 주가  │ │
│                     │              │ │CTO+기술팀││투자분석팀│ │
│                     │              │ ├────────┤├────────┤ │
│                     │              │ │📄 약관  ││📣 마케팅│ │
│                     │              │ │CLO+법무팀││CMO+마케팅│ │
│                     │              │ └────────┘└────────┘ │
└─────────────────────┘              └─────────────────────┘
```

---

### 디자인 원칙 (이번 리디자인에 적용)

1. **계층적 시각 구분** — CEO > 본부 > 처장 > Specialist 각각 다른 시각적 비중
2. **디비전별 컬러 코딩** — LEET Master(cyan), 투자분석(purple), 비서실(yellow)
3. **글래스모피즘 + 글로우** — 다크 테마에서 깊이감과 고급감 부여
4. **정보 밀도 최적화** — 필요한 정보는 보이되, 시각적 과부하 방지
5. **일관된 마이크로 인터랙션** — 모든 인터랙티브 요소에 호버/포커스 피드백

---

## v0.3.0 (2026-02-12) - 본부 라벨 분리 (LEET Master / 투자분석)

> 상태: **구현 완료**

### 한 줄 요약

**본부장 에이전트 없이, "LEET Master 본부"와 "투자분석 본부"를 라벨/그룹 개념으로 도입하여 UI와 프롬프트에서 두 사업 영역을 구분합니다.**

---

### 왜 바꿨나?

v0.2.0에서 본부장을 삭제하고 5개 처장을 비서실장 아래 동급으로 배치했는데,
실제로는 CTO/CSO/CLO/CMO는 **LEET Master 제품**을 만드는 팀이고,
CIO는 **주식 투자 분석**이라는 완전히 다른 도메인입니다.

비서실장이 명령을 분류할 때도 "이건 제품 관련인지, 투자 관련인지" 구분이 필요했고,
UI에서도 16명의 제품팀과 4명의 투자팀이 섞여 있으면 한눈에 안 들어왔습니다.

### 뭘 바꿨나?

**핵심: 본부장 에이전트 추가 없이, 3곳에만 "본부" 개념을 반영**

| 반영 위치 | 변경 내용 |
|-----------|-----------|
| 비서실장 system_prompt | "LEET Master 본부 / 투자분석 본부" 조직 구조와 배분 규칙 명시 |
| 웹 UI 사이드바 | 본부 단위 접기/펼치기 래퍼 추가, 처장은 본부 안에 중첩 |
| CLI 조직도 | LEET Master 본부 / 투자분석 본부 그룹핑 표시 |

**조직도 변화:**
```
v0.2.0 (플랫):                    v0.3.0 (본부 그룹핑):
├── CTO                           ├── LEET Master 본부
├── CSO                           │    ├── CTO
├── CLO                           │    ├── CSO
├── CMO                           │    ├── CLO
├── CIO                           │    └── CMO
                                  └── 투자분석 본부
                                       └── CIO
```

**LLM 비용 추가: 0** (본부장 에이전트가 없으므로)

### 수정된 파일 (5개)

| 파일 | 변경 |
|------|------|
| `config/agents.yaml` | 비서실장 system_prompt에 본부 구조 + 배분 규칙 명시 |
| `web/templates/index.html` | 사이드바 본부 래퍼 + JS (expanded, getSectionAgentIds, auto-expand) |
| `src/cli/app.py` | 조직도 본부 그룹핑 + 버전 v0.3.0 |
| `web/app.py` | FastAPI 버전 v0.3.0 |
| `docs/CHANGELOG.md` | 이 문서 |

---

## v0.2.0 (2026-02-12) - 비서실장 오케스트레이터 통합 + 비용 추적 고도화

> 상태: **구현 완료**

### 한 줄 요약

**불필요한 본부장 레이어를 제거하고, 비서실장이 CEO의 모든 명령을 직접 관리하도록 변경했습니다.**

---

### 왜 바꿨나? (문제점)

v0.1.0에서 CEO가 "삼성전자 주가 분석해줘"라고 명령하면 이런 일이 벌어졌습니다:

```
CEO: "삼성전자 주가 분석해줘"
  │
  ▼
① Orchestrator가 LLM을 호출해서 "이건 금융 관련이니 finance_head에게 보내자" 판단  ← LLM 호출 1회
  │
  ▼
② finance_head(금융분석 본부장)가 LLM을 호출해서 "이건 cio_manager에게 보내자" 판단  ← LLM 호출 1회 (낭비!)
  │
  ▼
③ cio_manager(투자분석처장)가 실제로 부하 전문가들에게 배분  ← LLM 호출 1회
  │
  ▼
④ 전문가들이 분석 실행
```

**문제가 뭐냐면:**
- **②번이 완전히 쓸데없음.** 본부장은 "아 이거 내 밑에 CIO한테 보내야겠다" 이것만 하고 끝. 분류 역할만 하는데 그게 LLM 호출 1회 비용이 드는 것
- 본부장이 2명(LEET MASTER 본부장, 금융분석 본부장)이었는데, 둘 다 같은 문제
- 반면 **비서실장**은 "일반 질문"의 fallback으로만 쓰여서 거의 놀고 있었음

---

### 뭘 바꿨나? (변경 내역)

#### 1. 조직 구조 개편 — 본부장 2명 삭제, 비서실장 승격

**v0.1.0 (AS-IS) — 4단계 명령 흐름:**
```
CEO
 └→ Orchestrator (숨겨진 LLM 분류기)
      ├→ LEET MASTER 본부장 ─── 중계만 하는 허브
      │    ├→ CTO 기술개발처장 → 전문가 4명
      │    ├→ CSO 사업기획처장 → 전문가 3명
      │    ├→ CLO 법무·IP처장 → 전문가 2명
      │    └→ CMO 마케팅·고객처장 → 전문가 3명
      │
      ├→ 금융분석 본부장 ─── 중계만 하는 허브
      │    └→ CIO 투자분석처장 → 전문가 4명
      │
      └→ 비서실장 (fallback용) → Worker 3명
```

**v0.2.0 (TO-BE) — 3단계 명령 흐름:**
```
CEO
 └→ 비서실장 (Chief of Staff) ← 총괄 오케스트레이터로 승격!
      ├→ CTO 기술개발처장 → 전문가 4명
      ├→ CSO 사업기획처장 → 전문가 3명
      ├→ CLO 법무·IP처장 → 전문가 2명
      ├→ CMO 마케팅·고객처장 → 전문가 3명
      ├→ CIO 투자분석처장 → 전문가 4명
      └→ Worker 3명 (보고요약, 일정추적, 정보중계)
```

**핵심 변화:**
| 항목 | v0.1.0 | v0.2.0 |
|------|--------|--------|
| 에이전트 수 | 27명 (본부장 2명 포함) | **25명** (본부장 삭제) |
| CEO 명령 → 결과 단계 | 4단계 | **3단계** |
| 명령당 불필요 LLM 호출 | 1~2회 (본부장 분류) | **0회** |
| 비서실장 역할 | fallback (거의 안 쓰임) | **모든 명령의 총괄 관리** |
| 명령 분류 담당 | 숨겨진 Orchestrator 클래스 | **비서실장이 직접 분류** |

#### 2. 비용 추적 고도화 — 에이전트별 비용 추적

v0.1.0에서는 "어떤 **모델**을 얼마나 썼는지"만 알 수 있었습니다.
v0.2.0에서는 "어떤 **에이전트**가 얼마나 썼는지", "어떤 **프로바이더**(OpenAI/Anthropic)에 얼마나 썼는지"도 알 수 있습니다.

**v0.1.0의 비용 데이터:**
```json
{
  "total_cost": 0.0342,
  "by_model": {
    "gpt-4o": {"calls": 5, "cost_usd": 0.03},
    "gpt-4o-mini": {"calls": 10, "cost_usd": 0.004}
  }
}
```

**v0.2.0의 비용 데이터:**
```json
{
  "total_cost": 0.0342,
  "by_model": { ... },
  "by_agent": {
    "chief_of_staff": {"calls": 3, "cost_usd": 0.012},
    "cto_manager": {"calls": 2, "cost_usd": 0.008},
    "frontend_specialist": {"calls": 1, "cost_usd": 0.002}
  },
  "by_provider": {
    "openai": {"calls": 12, "cost_usd": 0.030},
    "anthropic": {"calls": 3, "cost_usd": 0.004}
  }
}
```

**구현 방법:**
LLM을 호출할 때마다 "누가 호출했는지(agent_id)"를 함께 기록하도록 전체 호출 체인을 수정:
```
에이전트.think() → ModelRouter.complete(agent_id=...) → CostTracker.record(agent_id=...)
```

#### 3. UI 변경 — 사이드바 플랫 구조 + 색상 변경

**사이드바 조직도:**
| v0.1.0 | v0.2.0 |
|--------|--------|
| 3단계 중첩 (본부 → 처 → 전문가) | **2단계 플랫** (처 → 전문가) |
| LEET MASTER 본부 접기/펼치기 존재 | 삭제 (각 처가 독립) |
| 금융분석 본부 접기/펼치기 존재 | 삭제 (CIO가 직접 표시) |

**에이전트 상태 표시 색상:**
| 상태 | v0.1.0 | v0.2.0 | 이유 |
|------|--------|--------|------|
| 대기중 (standby) | 🔘 회색 | 🟠 **앰버** | "준비됨"을 더 명확히 표현 |
| 작업중 (working) | 🟡 노랑 깜빡 | 🟢 **초록 깜빡** | "활발히 동작"을 직관적으로 |
| 완료 (done) | 🟢 초록 | 🟢 초록 (유지) | - |
| 유휴 (idle) | 🔘 회색 | 🟠 **앰버** | 대기중과 동일 |
| 비활성 (inactive) | 🔘 회색 | 🔘 회색 (유지) | - |

**JavaScript에서 삭제된 것들:**
- `agentNames`에서 `leet_master_head`, `finance_head` 제거
- `agentDivision`에서 `leet_master_head`, `finance_head` 제거
- `expanded` 객체에서 `leet` 섹션 제거
- `getSectionAgentIds()`에서 `leet` 분기 제거
- `handleWsMessage`에서 leet 자동 펼치기 로직 제거

---

### 수정된 파일 상세 (9개 파일, +168줄 / -241줄)

| 파일 | 변경 요약 | 상세 |
|------|-----------|------|
| `config/agents.yaml` | 본부장 삭제, 비서실장 확장 | `leet_master_head`, `finance_head` 정의 삭제. `chief_of_staff`에 5개 처장을 subordinate로 추가. 처장들의 `superior_id`를 `chief_of_staff`로 변경 |
| `src/core/orchestrator.py` | LLM 분류 호출 제거 | `_classify_command()`(LLM으로 명령 분류) 삭제. 모든 명령을 `chief_of_staff`에게 직행. `_parse_json()` 삭제 |
| `src/core/registry.py` | 조직도 조회 수정 | `list_division_heads()`: 비서실장 직속 manager만 반환하도록 조건 변경 |
| `src/core/agent.py` | agent_id 전파 | `think()`, `_summarize()`에서 `agent_id=self.agent_id`를 router에 전달 |
| `src/llm/router.py` | agent_id 파라미터 추가 | `complete()`에 `agent_id` 파라미터 추가, `cost_tracker.record()`에 전달 |
| `src/llm/cost_tracker.py` | 비용 분석 메서드 추가 | `CostRecord`에 `agent_id` 필드 추가. `summary_by_agent()`, `summary_by_provider()` 메서드 추가 |
| `web/templates/index.html` | 사이드바 + JS 전면 수정 | HTML: 본부 wrapper 제거, 플랫 구조. JS: 본부장 참조 제거, 색상 변경, leet 관련 로직 삭제 |
| `web/app.py` | API 응답 확장 + 버전 업 | `/api/cost`에 `by_agent`, `by_provider` 추가. FastAPI 버전 `0.2.0` |
| `src/cli/app.py` | CLI 조직도 + 버전 업 | `_show_org_chart()` 본부장 레이어 제거. 배너 `v0.2.0` |

---

### 예상 효과

| 항목 | 수치 |
|------|------|
| 명령당 LLM 호출 절감 | **1~2회** (본부장 분류 + 종합 제거) |
| 명령당 비용 절감 | 약 **$0.002~0.005** (gpt-4o 1회 기준) |
| 명령 처리 시간 단축 | 본부장 처리 대기 시간 제거 |
| 비용 추적 세분화 | 모델별 → 모델별 + **에이전트별** + **프로바이더별** |

---

## v0.1.0 (2026-02-12) - 최초 릴리즈

> 상태: **배포 완료 (현재 버전)**

### 무엇이 만들어졌나요?

한 줄 요약: **CORTHEX HQ 멀티 에이전트 시스템의 첫 번째 버전. 25명의 AI 에이전트가 CEO 명령을 자동 처리합니다.**

### 핵심 기능

#### 1. 멀티 에이전트 조직 구조
- **25명의 AI 에이전트**가 회사 조직도 형태로 구성
- 역할 기반 계층: 본부장 → 처장 → Specialist → Worker
- 각 에이전트가 고유한 AI 모델, 시스템 프롬프트, 역할을 가짐

#### 2. 조직 구성

| 부서 | 에이전트 수 | 주요 역할 |
|------|-------------|-----------|
| 비서실 | 4명 | 보고 요약, 일정 추적, 정보 중계 |
| LEET MASTER 본부 | 15명 | 기술개발(CTO), 사업기획(CSO), 법무(CLO), 마케팅(CMO) |
| 금융분석 본부 | 5명 | 시황분석, 종목분석, 기술적분석, 리스크관리 |
| Tool Pool | 5개 | 변리사, 세무사, 디자이너, 번역가, 웹검색 |

#### 3. 지능형 명령 라우팅
- Orchestrator가 CEO 명령을 LLM으로 분류
- 가장 적합한 사업부에 자동 배분
- 처장(Manager)이 세부 업무를 Specialist에게 **병렬 위임**
- 결과를 **종합 보고서**로 합성하여 CEO에게 반환

#### 4. CEO 관제실 웹 UI
- FastAPI + WebSocket 기반 실시간 대시보드
- 조직도 트리 뷰 (에이전트 상태 실시간 표시)
- 마크다운 렌더링 결과 표시
- 활동 로그 실시간 스트리밍
- 누적 비용/토큰 모니터링

#### 5. Rich Terminal CLI
- 터미널에서도 CEO 명령 입력 가능
- 조직도 트리 표시
- 비용 요약 테이블
- 마크다운 결과 렌더링

#### 6. 멀티 LLM 지원
- OpenAI (gpt-4o, gpt-4o-mini) 지원
- Anthropic (claude-sonnet-4-5-20250929) 지원
- 모델명 prefix로 자동 프로바이더 라우팅
- 에이전트별 독립적인 모델 설정 가능

#### 7. 지식 관리 시스템
- `knowledge/` 디렉토리의 .md 파일을 에이전트 system_prompt에 자동 주입
- 부서(division)별 지식 매칭
- 서버 시작 시 1회 로딩

#### 8. 도구(Tool) 시스템
- 변리사, 세무사, 디자이너, 번역가, 웹검색 5개 Tool
- 에이전트별 허용 도구 제한 (`allowed_tools`)
- 권한 없는 도구 호출 시 `ToolPermissionError`

#### 9. 비용 추적
- 모든 LLM 호출의 토큰 사용량 및 비용 자동 기록
- 모델별 비용 요약 (`summary_by_model()`)
- CLI `비용` 명령어 및 `/api/cost` 엔드포인트

### 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| 언어 | Python 3.11+ |
| 웹 프레임워크 | FastAPI |
| 실시간 통신 | WebSocket |
| 프론트엔드 | Tailwind CSS + Alpine.js |
| CLI | Rich |
| 설정 관리 | YAML + Pydantic |
| LLM 통신 | httpx (async) |

### 프로젝트 구조

```
CORTHEX_HQ/
├── config/
│   ├── agents.yaml          # 에이전트 설정 (25명)
│   └── tools.yaml           # 도구 설정 (5개)
├── knowledge/               # 부서별 지식 파일
├── src/
│   ├── core/
│   │   ├── orchestrator.py  # CEO 명령 라우터
│   │   ├── agent.py         # 에이전트 기본 클래스 (Manager/Specialist/Worker)
│   │   ├── registry.py      # 에이전트 팩토리 + 레지스트리
│   │   ├── context.py       # 공유 컨텍스트 (대화 기록, 상태 콜백)
│   │   ├── message.py       # 메시지 타입 (TaskRequest, TaskResult, StatusUpdate)
│   │   ├── knowledge.py     # 지식 관리자
│   │   └── errors.py        # 커스텀 예외
│   ├── llm/
│   │   ├── base.py          # LLMProvider 추상 클래스 + LLMResponse
│   │   ├── router.py        # 모델 라우터 (OpenAI/Anthropic 자동 분기)
│   │   ├── openai_provider.py
│   │   ├── anthropic_provider.py
│   │   └── cost_tracker.py  # 비용 추적
│   ├── tools/               # 도구 구현체 (5개)
│   ├── divisions/           # 부서별 커스텀 로직 (선택적)
│   └── cli/
│       └── app.py           # Rich CLI 인터페이스
├── web/
│   ├── app.py               # FastAPI 웹 서버
│   ├── ws_manager.py        # WebSocket 매니저
│   └── templates/
│       └── index.html       # CEO 관제실 SPA
├── main.py                  # CLI 진입점
├── main_web.py              # 웹 서버 진입점
└── .env                     # API 키 설정
```

### Git 커밋 이력

| 커밋 | 설명 |
|------|------|
| `436e915` | Initial commit |
| `a03c1b7` | feat: CORTHEX HQ 멀티 에이전트 시스템 전체 구현 |
| `4ece0c0` | feat: CEO 관제실 웹 UI + 지식 관리 시스템 + 원클릭 설치 |
| `ccd31a5` | ci: claude 브랜치 → main 자동 머지 워크플로우 추가 |
| `cb09825` | docs: README.md 상세 사용 설명서로 전면 개편 |

---

## 버전 관리 규칙

- **MAJOR** (x.0.0): 시스템 아키텍처 대폭 변경
- **MINOR** (0.x.0): 새 기능 추가 또는 기존 기능 개편
- **PATCH** (0.0.x): 버그 수정, 문서 수정, 소규모 개선
