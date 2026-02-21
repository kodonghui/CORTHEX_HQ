# CORTHEX HQ v0.2.0 구현 계획서

> 작성일: 2026-02-12
> 작성자: Claude (AI 개발 에이전트)
> 상태: **구현 완료 (2026-02-12)**

---

## 1. 현재 시스템 분석 (v0.1.0 AS-IS)

### 1-1. 현재 명령 흐름

```
CEO 명령 입력
    │
    ▼
[Orchestrator] ─── LLM으로 분류 (gpt-4o-mini)
    │
    ├──→ leet_master_head (LEET MASTER 본부장)
    │        ├──→ cto_manager (기술개발처장)
    │        │       ├── frontend_specialist
    │        │       ├── backend_specialist
    │        │       ├── infra_specialist
    │        │       └── ai_model_specialist
    │        ├──→ cso_manager (사업기획처장)
    │        │       ├── market_research_specialist
    │        │       ├── business_plan_specialist
    │        │       └── financial_model_specialist
    │        ├──→ clo_manager (법무·IP처장)
    │        │       ├── copyright_specialist
    │        │       └── patent_specialist
    │        └──→ cmo_manager (마케팅·고객처장)
    │                ├── survey_specialist
    │                ├── content_specialist
    │                └── community_specialist
    │
    ├──→ finance_head (금융분석 본부장)
    │        └──→ cio_manager (투자분석처장)
    │                ├── market_condition_specialist [병렬]
    │                ├── stock_analysis_specialist   [병렬]
    │                ├── technical_analysis_specialist [병렬]
    │                └── risk_management_specialist   [순차]
    │
    └──→ chief_of_staff (비서실장) ── fallback
             ├── report_worker
             ├── schedule_worker
             └── relay_worker
```

### 1-2. 현재 문제점

| # | 문제 | 설명 |
|---|------|------|
| 1 | **본부장 레이어가 불필요** | `leet_master_head`와 `finance_head`는 단순히 하위 처장에게 재위임만 함. LLM 호출 1회가 낭비됨 (분류만 하고 종합만 함) |
| 2 | **Orchestrator가 보이지 않음** | 명령 라우팅이 내부 `Orchestrator` 클래스에서 은밀하게 이루어짐. CEO에게 "누가 처리하는지"가 직관적이지 않음 |
| 3 | **비서실장 역할이 애매** | `chief_of_staff`가 fallback 용도로만 사용됨. 조직의 중추 역할을 못 함 |
| 4 | **비용 추적에 에이전트 정보 없음** | `CostRecord`에 `agent_id`가 없어서 "어떤 에이전트가 비용을 얼마나 쓰는지" 추적 불가 |
| 5 | **에이전트 상태 표시 색상이 직관적이지 않음** | idle=회색, working=노랑 인데, 대기중은 amber, 작업중은 초록이 더 직관적 |

---

## 2. 목표 시스템 (v0.2.0 TO-BE)

### 2-1. 새로운 명령 흐름

```
CEO 명령 입력
    │
    ▼
[비서실장 (Chief of Staff)] ─── 명령 분류 + 상태 알림
    │
    ├──→ cto_manager (기술개발처장)
    │       ├── frontend_specialist
    │       ├── backend_specialist
    │       ├── infra_specialist
    │       └── ai_model_specialist
    │
    ├──→ cso_manager (사업기획처장)
    │       ├── market_research_specialist
    │       ├── business_plan_specialist
    │       └── financial_model_specialist
    │
    ├──→ clo_manager (법무·IP처장)
    │       ├── copyright_specialist
    │       └── patent_specialist
    │
    ├──→ cmo_manager (마케팅·고객처장)
    │       ├── survey_specialist
    │       ├── content_specialist
    │       └── community_specialist
    │
    ├──→ cio_manager (투자분석처장)
    │       ├── market_condition_specialist [병렬]
    │       ├── stock_analysis_specialist   [병렬]
    │       ├── technical_analysis_specialist [병렬]
    │       └── risk_management_specialist   [순차]
    │
    └──→ [직접 처리] 일반 질문/보고 요약/일정 추적
             ├── report_worker
             ├── schedule_worker
             └── relay_worker
```

### 2-2. 핵심 변경 사항 요약

| # | 변경 | 상세 |
|---|------|------|
| 1 | **본부장 2명 제거** | `leet_master_head`, `finance_head` 삭제. 처장들이 비서실장 직속으로 승격 |
| 2 | **비서실장 = 오케스트레이터** | `Orchestrator` 클래스의 분류 로직을 `chief_of_staff`가 담당하도록 통합 |
| 3 | **비용 추적 고도화** | `CostRecord`에 `agent_id` 필드 추가, 에이전트별 비용 조회 API 추가 |
| 4 | **UI 색상 체계 변경** | idle=amber, working=green+pulse, inactive=gray |
| 5 | **에이전트 이름 정리** | UI의 `agentNames` 맵핑에서 본부장 관련 항목 제거, 조직도 업데이트 |

---

## 3. 상세 구현 계획

### Phase 1: 본부장 레이어 제거 + 비서실장 오케스트레이터화

#### 3-1-A. `config/agents.yaml` 수정

**삭제할 에이전트:**
- `leet_master_head` (LEET MASTER 본부장) - 에이전트 정의 전체 삭제
- `finance_head` (금융분석 본부장) - 에이전트 정의 전체 삭제

**수정할 에이전트:**

`chief_of_staff` 비서실장의 `subordinate_ids` 확장:
```yaml
# 변경 전
subordinate_ids:
  - "report_worker"
  - "schedule_worker"
  - "relay_worker"

# 변경 후
subordinate_ids:
  - "report_worker"
  - "schedule_worker"
  - "relay_worker"
  - "cto_manager"
  - "cso_manager"
  - "clo_manager"
  - "cmo_manager"
  - "cio_manager"
```

각 처장의 `superior_id` 변경:
```yaml
# cto_manager, cso_manager, clo_manager, cmo_manager:
superior_id: "leet_master_head"  →  superior_id: "chief_of_staff"

# cio_manager:
superior_id: "finance_head"  →  superior_id: "chief_of_staff"
```

`chief_of_staff`의 `system_prompt`도 업데이트:
```yaml
system_prompt: |
  당신은 CORTHEX HQ의 비서실장이자 총괄 오케스트레이터입니다.
  CEO의 명령을 분석하여 가장 적합한 처장(CTO, CSO, CLO, CMO, CIO)에게 배분하세요.
  복수 부서가 필요한 경우 모두 포함하세요.
  일반 질문이나 보고서 요약은 직접 처리하세요.
  항상 한국어로 간결하고 명확하게 보고하세요.
```

`chief_of_staff`의 `capabilities` 업데이트:
```yaml
capabilities:
  - "명령 분류 및 배분"
  - "보고서 요약"
  - "일정 추적"
  - "사업부 간 중계"
  - "일반 질문 응대"
```

#### 3-1-B. `src/core/orchestrator.py` 수정

`_classify_command()` 메서드를 **모든 명령이 `chief_of_staff`로 가도록** 변경:

```python
async def process_command(self, user_input: str) -> TaskResult:
    """Main entry: all commands go through chief_of_staff."""
    request = TaskRequest(
        sender_id="ceo",
        receiver_id="chief_of_staff",
        task_description=user_input,
        context={},
    )

    try:
        agent = self.registry.get_agent("chief_of_staff")
        result = await agent.handle_task(request)
    except Exception as e:
        logger.error("명령 처리 실패: %s", e)
        result = TaskResult(
            sender_id="chief_of_staff",
            receiver_id="ceo",
            correlation_id=request.correlation_id,
            success=False,
            result_data={"error": str(e)},
            summary=f"오류: {e}",
        )
    return result
```

**핵심 포인트:**
- `_classify_command()` 의 LLM 호출이 제거됨 (gpt-4o-mini 1회 호출 비용 절감)
- 대신 `chief_of_staff`가 `ManagerAgent`이므로, `_plan_decomposition()`에서 자연스럽게 LLM이 분류를 수행
- 즉 기존: Orchestrator LLM 분류 → 본부장 LLM 분류 → 처장 LLM 분류 (3단계)
- 변경 후: 비서실장 LLM 분류 → 처장 LLM 분류 (2단계, **LLM 호출 1회 절감**)

#### 3-1-C. `src/core/registry.py` 수정

`list_division_heads()` 수정 (현재 `superior_id is None`인 에이전트도 반환하는데, 비서실장이 유일한 top-level이 되므로 이 메서드의 역할 재검토):

```python
def list_division_heads(self) -> list[dict]:
    """Return summary of managers directly under chief_of_staff."""
    heads = []
    for agent in self._agents.values():
        if agent.config.superior_id == "chief_of_staff" and agent.config.role == "manager":
            heads.append({
                "agent_id": agent.agent_id,
                "name_ko": agent.config.name_ko,
                "division": agent.config.division,
                "capabilities": agent.config.capabilities,
            })
    return heads
```

### Phase 2: 비용 추적 고도화

#### 3-2-A. `src/llm/cost_tracker.py` 수정

`CostRecord`에 `agent_id` 필드 추가:
```python
@dataclass
class CostRecord:
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    agent_id: str = ""  # NEW
```

`summary_by_agent()` 메서드 추가:
```python
def summary_by_agent(self) -> dict[str, dict]:
    """Group costs by agent for the CEO dashboard."""
    summary: dict[str, dict] = defaultdict(
        lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    )
    for r in self._records:
        s = summary[r.agent_id or "unknown"]
        s["calls"] += 1
        s["input_tokens"] += r.input_tokens
        s["output_tokens"] += r.output_tokens
        s["cost_usd"] += r.cost_usd
    return dict(summary)
```

`summary_by_provider()` 메서드 추가:
```python
def summary_by_provider(self) -> dict[str, dict]:
    """Group costs by provider (openai / anthropic)."""
    summary: dict[str, dict] = defaultdict(
        lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    )
    for r in self._records:
        s = summary[r.provider]
        s["calls"] += 1
        s["input_tokens"] += r.input_tokens
        s["output_tokens"] += r.output_tokens
        s["cost_usd"] += r.cost_usd
    return dict(summary)
```

#### 3-2-B. `src/llm/router.py` 수정

`complete()` 메서드에 `agent_id` 파라미터 추가:
```python
async def complete(
    self,
    model_name: str,
    messages: list[dict[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 4096,
    agent_id: str = "",  # NEW
) -> LLMResponse:
    provider = self._resolve_provider(model_name)
    response = await provider.complete(
        model=model_name,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    self.cost_tracker.record(response, agent_id=agent_id)  # CHANGED
    return response
```

#### 3-2-C. `src/core/agent.py` 수정

`think()` 메서드에서 `agent_id`를 전달:
```python
async def think(self, messages: list[dict[str, str]]) -> str:
    response = await self.model_router.complete(
        model_name=self.config.model_name,
        messages=messages,
        temperature=self.config.temperature,
        agent_id=self.agent_id,  # NEW
    )
    return response.content
```

`_summarize()` 메서드에서도 `agent_id` 전달:
```python
async def _summarize(self, result: Any) -> str:
    text = str(result)
    if len(text) < 200:
        return text
    response = await self.model_router.complete(
        model_name="gpt-4o-mini",
        messages=[...],
        temperature=0.0,
        agent_id=self.agent_id,  # NEW
    )
    return response.content
```

#### 3-2-D. `web/app.py` 수정

`/api/cost` 엔드포인트에 agent별, provider별 데이터 추가:
```python
@app.get("/api/cost")
async def get_cost() -> dict:
    if not model_router:
        return {"total_cost": 0, "total_tokens": 0, "by_model": {}}
    tracker = model_router.cost_tracker
    return {
        "total_cost": tracker.total_cost,
        "total_tokens": tracker.total_tokens,
        "total_calls": tracker.total_calls,
        "by_model": tracker.summary_by_model(),
        "by_agent": tracker.summary_by_agent(),      # NEW
        "by_provider": tracker.summary_by_provider(), # NEW
    }
```

### Phase 3: UI 업데이트

#### 3-3-A. `web/templates/index.html` - 조직도 변경

**삭제:**
- LEET MASTER 본부 섹션의 최상위 wrapper (본부장 없이 처장 4개가 비서실장 직속)
- 금융분석 본부 섹션의 최상위 wrapper (본부장 없이 CIO가 비서실장 직속)

**변경 후 사이드바 구조:**
```
CEO (동희 님)
├── 비서실장 (Chief of Staff) ← 오케스트레이터 겸용
│   ├── 보고 요약 Worker
│   ├── 일정/미결 추적 Worker
│   └── 정보 중계 Worker
├── 기술개발처 (CTO)
│   ├── 프론트엔드
│   ├── 백엔드/API
│   ├── DB/인프라
│   └── AI 모델
├── 사업기획처 (CSO)
│   ├── 시장조사
│   ├── 사업계획서
│   └── 재무모델링
├── 법무·IP처 (CLO)
│   ├── 저작권
│   └── 특허/약관
├── 마케팅·고객처 (CMO)
│   ├── 설문/리서치
│   ├── 콘텐츠
│   └── 커뮤니티
├── 투자분석처 (CIO)
│   ├── 시황분석 [병렬]
│   ├── 종목분석 [병렬]
│   ├── 기술적분석 [병렬]
│   └── 리스크관리 [순차]
└── AgentTool Pool
    ├── 변리사 Tool
    ├── 세무사 Tool
    ├── 디자이너 Tool
    ├── 번역가 Tool
    └── 웹검색 Tool
```

#### 3-3-B. `web/templates/index.html` - 에이전트 이름 맵핑

`agentNames` 객체에서 삭제:
```javascript
// 삭제
'leet_master_head': 'LEET MASTER 본부장',
'finance_head': '금융분석 본부장',
```

`agentDivision` 객체에서도 삭제:
```javascript
// 삭제
'leet_master_head': 'leet',
'finance_head': 'finance',
```

#### 3-3-C. `web/templates/index.html` - 상태 색상 변경

`getAgentDotClass()` 함수 수정:
```javascript
// 변경 전
getAgentDotClass(id) {
    const status = this.activeAgents[id];
    if (!status) return 'bg-gray-600';        // idle = 회색
    switch (status.status) {
        case 'working': return 'bg-hq-yellow pulse-dot';  // working = 노랑
        case 'done': return 'bg-hq-green';    // done = 초록
        default: return 'bg-gray-600';
    }
}

// 변경 후
getAgentDotClass(id) {
    const status = this.activeAgents[id];
    if (!status) return 'bg-amber-500';       // standby = 앰버 (대기중)
    switch (status.status) {
        case 'working': return 'bg-hq-green pulse-dot';   // working = 초록 깜빡
        case 'done': return 'bg-hq-green';    // done = 초록 (고정)
        case 'idle': return 'bg-amber-500';   // idle = 앰버
        default: return 'bg-gray-600';        // inactive = 회색
    }
}
```

Tailwind config에 `hq-orange` 추가 (필요시):
```javascript
colors: {
    // 기존
    'hq-bg': '#0f172a',
    'hq-panel': '#1e293b',
    'hq-border': '#334155',
    'hq-accent': '#3b82f6',
    'hq-green': '#22c55e',
    'hq-yellow': '#eab308',
    'hq-red': '#ef4444',
    // 추가
    'hq-orange': '#f97316',
}
```

#### 3-3-D. `src/cli/app.py` - CLI 조직도 업데이트

`_show_org_chart()` 메서드 수정:
- 본부장 레이어 제거
- 비서실장 아래에 처장들이 직접 표시되도록 변경
- 버전 표시 `v0.1.0` → `v0.2.0`

---

## 4. 영향 받는 파일 목록

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `config/agents.yaml` | **수정** | 본부장 2명 삭제, 비서실장 role 확장, 처장들 superior_id 변경 |
| `src/core/orchestrator.py` | **수정** | 분류 LLM 호출 제거, 모든 명령을 chief_of_staff로 직행 |
| `src/core/registry.py` | **수정** | `list_division_heads()` 로직 변경 |
| `src/core/agent.py` | **수정** | `think()`, `_summarize()`에 agent_id 전달 |
| `src/llm/router.py` | **수정** | `complete()`에 agent_id 파라미터 추가 |
| `src/llm/cost_tracker.py` | **수정** | CostRecord에 agent_id 추가, summary_by_agent/provider 메서드 추가 |
| `web/templates/index.html` | **수정** | 사이드바 조직도, agentNames, 색상 체계 변경 |
| `web/app.py` | **수정** | /api/cost 응답에 by_agent, by_provider 추가 |
| `src/cli/app.py` | **수정** | CLI 조직도, 버전 표시 업데이트 |

---

## 5. 리스크 및 주의사항

| 리스크 | 영향도 | 대응 |
|--------|--------|------|
| 비서실장이 분류를 잘못할 수 있음 | 중 | 기존 본부장의 system_prompt를 비서실장에 흡수하여 분류 정확도 유지 |
| 기존 Orchestrator의 `_classify_command()` 삭제 시 하위 호환 | 저 | v0.1.0은 첫 릴리즈이므로 하위 호환 불필요 |
| `complete()` 시그니처 변경 시 모든 호출처 수정 필요 | 중 | `agent_id=""` 기본값으로 하위 호환 유지 |
| 조직도 사이드바 HTML 대폭 변경 | 저 | 단순 구조 변경, 기능 변경 없음 |

---

## 6. 예상 효과

- **LLM 호출 비용 절감**: 명령당 LLM 호출 최소 1~2회 감소 (본부장 분류 + 종합 제거)
- **응답 속도 향상**: 중간 레이어 제거로 CEO 명령 → 최종 결과까지의 latency 감소
- **비용 투명성**: 어떤 에이전트가 얼마나 비용을 쓰는지 추적 가능
- **직관적 UI**: CEO가 조직 구조를 더 명확하게 파악 가능
- **비서실장 역할 명확화**: "보이지 않는 라우터" → "보이는 총괄 비서"로 전환

---

## 7. 구현 순서 (권장)

```
1단계: config/agents.yaml 수정 (본부장 제거 + 비서실장 확장)
   ↓
2단계: src/core/orchestrator.py 수정 (분류 로직 단순화)
   ↓
3단계: src/core/registry.py 수정 (list_division_heads 업데이트)
   ↓
4단계: src/llm/cost_tracker.py + router.py + agent.py 수정 (비용 추적)
   ↓
5단계: web/templates/index.html 수정 (UI 전면 업데이트)
   ↓
6단계: web/app.py + src/cli/app.py 수정 (API + CLI 업데이트)
   ↓
7단계: 통합 테스트 및 최종 확인
```

---

**위 순서대로 구현이 완료되었습니다. (2026-02-12)**
