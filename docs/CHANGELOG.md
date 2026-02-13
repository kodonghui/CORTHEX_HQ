# CORTHEX HQ 변경 이력 (Changelog)

> 이 문서는 CORTHEX HQ의 버전별 변경 사항을 기록합니다.
> 노션에 붙여넣어 팀 기록으로 활용하세요.

---

## v0.4.0 (2026-02-12) - 보고서 자동 아카이브 & GitHub 자동 업로드

> 상태: **구현 완료**

### 한 줄 요약

**모든 에이전트(비서실장, 처장, Specialist, Worker)가 작업을 마칠 때마다 산출물을 부서별/날짜별 폴더에 자동 저장하고, CEO 명령 처리가 완전히 끝나면 GitHub에 한 번에 자동 푸시합니다.**

---

### 왜 바꿨나? (문제점)

v0.3.0까지 CORTHEX HQ에는 두 가지 문제가 있었습니다.

**문제 1: 산출물이 사라진다**

CEO가 "삼성전자 주가 분석해줘"라고 명령하면, 내부적으로 시황분석 Specialist, 종목분석 Specialist, 기술적분석 Specialist, 리스크관리 Specialist가 각각 분석을 수행하고, CIO가 종합하고, 비서실장이 최종 보고서를 만듭니다.

그런데 CEO한테는 **비서실장의 최종 보고서만** CLI/웹 화면에 표시되고, 각 Specialist가 만든 **중간 산출물은 어디에도 남지 않았습니다.**

```
v0.3.0의 문제:

시황분석 Specialist → 분석 결과 생성 → 메모리에만 존재 → CIO한테 전달 후 소멸 ❌
종목분석 Specialist → 분석 결과 생성 → 메모리에만 존재 → CIO한테 전달 후 소멸 ❌
CIO 종합 보고서      → CIO가 합성     → 메모리에만 존재 → 비서실장 전달 후 소멸 ❌
비서실장 최종 보고서   → 화면에 표시    → 화면 닫으면 소멸 ❌
```

CEO가 나중에 "저번에 CTO가 뭐라고 했더라?", "시황분석이 구체적으로 뭐였지?"하면 **다시 처음부터 물어봐야** 했습니다.

**문제 2: GitHub에 수동으로 올려야 한다**

로컬에서 작업한 결과물을 팀원이나 다른 기기에서 보려면, 매번 터미널에서 `git add → git commit → git push`를 직접 해야 했습니다. 까먹으면 로컬에만 존재해서 다른 곳에서 접근할 수 없었습니다.

---

### 뭘 바꿨나? (변경 내역)

#### 1. 모든 에이전트의 산출물 자동 아카이브

**핵심: `BaseAgent.handle_task()`가 완료되는 시점에 자동으로 보고서를 파일로 저장합니다.**

CORTHEX HQ의 모든 에이전트(25명)는 `BaseAgent`를 상속합니다. `handle_task()`는 모든 에이전트가 작업을 처리할 때 공통으로 거치는 메서드입니다. 여기에 `_save_to_archive()`를 추가했으므로, **어떤 에이전트든 작업이 끝나면 자동으로 보고서가 저장됩니다.**

```python
# src/core/agent.py — BaseAgent.handle_task() (변경 후)

async def handle_task(self, request):
    result = await self.execute(request)      # 기존: 작업 수행
    self.context.log_message(result)           # 기존: 로그 기록
    self._save_to_archive(request, result)     # 🆕 보고서 파일로 저장
    return result
```

**저장 위치: `reports/{날짜}/{부서}/{에이전트}_{시간}.md`**

각 에이전트의 `division` 설정값(agents.yaml에 정의됨)을 폴더 경로로 변환합니다:

| 에이전트 | division 값 | 저장 경로 |
|----------|------------|-----------|
| 비서실장 | `secretary` | `reports/2026-02-12/secretary/chief_of_staff_143032.md` |
| CTO 처장 | `leet_master.tech` | `reports/2026-02-12/leet_master/tech/cto_manager_143027.md` |
| 프론트엔드 | `leet_master.tech` | `reports/2026-02-12/leet_master/tech/frontend_specialist_143028.md` |
| CSO 처장 | `leet_master.strategy` | `reports/2026-02-12/leet_master/strategy/cso_manager_143030.md` |
| CIO 처장 | `finance.investment` | `reports/2026-02-12/finance/investment/cio_manager_143031.md` |
| 시황분석 | `finance.investment` | `reports/2026-02-12/finance/investment/market_condition_specialist_143025.md` |

**전체 디렉토리 구조 예시:**
```
reports/
  2026-02-12/                             ← 날짜별 폴더
    secretary/                            ← 비서실
      chief_of_staff_143032.md
      report_worker_143025.md
      schedule_worker_143026.md
      relay_worker_143026.md
    leet_master/                          ← LEET Master 본부
      tech/                              ← 기술개발처
        cto_manager_143027.md
        frontend_specialist_143028.md
        backend_specialist_143028.md
        infra_specialist_143028.md
        ai_model_specialist_143028.md
      strategy/                          ← 사업기획처
        cso_manager_143030.md
        market_research_specialist_143029.md
        business_plan_specialist_143029.md
        financial_model_specialist_143029.md
      legal/                             ← 법무·IP처
        clo_manager_143030.md
        copyright_specialist_143029.md
        patent_specialist_143029.md
      marketing/                         ← 마케팅·고객처
        cmo_manager_143030.md
        survey_specialist_143029.md
        content_specialist_143029.md
        community_specialist_143029.md
    finance/                             ← 투자분석 본부
      investment/                        ← 투자분석처
        cio_manager_143031.md
        market_condition_specialist_143025.md
        stock_analysis_specialist_143026.md
        technical_analysis_specialist_143027.md
        risk_management_specialist_143028.md
  2026-02-13/                            ← 다음 날은 새 폴더
    ...
```

**각 보고서 파일 내용 예시:**
```markdown
# 시황분석 Specialist (market_condition_specialist) 보고서

- **일시**: 2026-02-12 14:30:25 UTC
- **부서**: finance.investment
- **역할**: specialist
- **지시 내용**: 삼성전자 관련 거시경제 환경 및 시장 동향을 분석하세요
- **상태**: SUCCESS
- **처리 시간**: 2.8초

---

## 거시경제 환경 분석

### 1. 금리 환경
- 한국은행 기준금리: 3.00% (동결 기조)
- 미국 Fed 금리: 4.75% (인하 기대)
...
```

#### 2. GitHub 자동 업로드

**핵심: 에이전트들이 각자 저장 → 전부 끝나면 Orchestrator가 한 번에 push**

v0.3.0까지의 방식과 비교:
```
v0.3.0: 저장 안 됨, push 안 됨 (화면에만 표시)

v0.4.0:
  각 에이전트 handle_task() 완료 → 보고서 파일 저장 (git 안 건드림)
  각 에이전트 handle_task() 완료 → 보고서 파일 저장 (git 안 건드림)
  각 에이전트 handle_task() 완료 → 보고서 파일 저장 (git 안 건드림)
  ...전부 끝...
  Orchestrator.process_command() 마지막 → git add reports/ → commit → push (딱 1회)
```

왜 에이전트마다 push하지 않고 마지막에 한 번만 하느냐?
- CEO가 명령 1개를 내리면 에이전트 5~10명이 동시에 일함
- 각각 push하면 git commit이 10개 생기고, push도 10번 → 느리고 커밋 로그가 지저분해짐
- 그래서 **전부 저장만 해두고, 맨 마지막에 한 번에** `git add reports/ → commit → push`

**push 실패 대비:**

네트워크 문제로 push가 실패할 수 있으므로, exponential backoff 방식으로 최대 4회 재시도합니다:

| 시도 | 대기 시간 | 누적 |
|------|-----------|------|
| 1회차 실패 | 2초 대기 | 2초 |
| 2회차 실패 | 4초 대기 | 6초 |
| 3회차 실패 | 8초 대기 | 14초 |
| 4회차 실패 | 16초 대기 | 30초 |
| 4회 모두 실패 | 포기 (로그에 기록) | — |

---

### 동작 흐름 (전체 시나리오)

CEO가 "삼성전자 주가 분석해줘"라고 입력했을 때:

```
① CEO 명령 입력: "삼성전자 주가 분석해줘"
   │
② Orchestrator → 비서실장(chief_of_staff)에게 전달
   │
③ 비서실장이 명령을 분석하고 CIO에게 배분
   │
④ CIO(cio_manager)가 4명의 Specialist에게 병렬 배분
   │
   ├─ 시황분석 Specialist ──→ 분석 수행 ──→ 결과 반환
   │   └─ 📄 저장: reports/2026-02-12/finance/investment/market_condition_specialist_143025.md
   │
   ├─ 종목분석 Specialist ──→ 분석 수행 ──→ 결과 반환
   │   └─ 📄 저장: reports/2026-02-12/finance/investment/stock_analysis_specialist_143026.md
   │
   ├─ 기술적분석 Specialist ──→ 분석 수행 ──→ 결과 반환
   │   └─ 📄 저장: reports/2026-02-12/finance/investment/technical_analysis_specialist_143027.md
   │
   └─ 리스크관리 Specialist ──→ 분석 수행 ──→ 결과 반환
       └─ 📄 저장: reports/2026-02-12/finance/investment/risk_management_specialist_143028.md
   │
⑤ CIO가 4명의 결과를 종합하여 보고
   └─ 📄 저장: reports/2026-02-12/finance/investment/cio_manager_143031.md
   │
⑥ 비서실장이 최종 보고서 작성
   └─ 📄 저장: reports/2026-02-12/secretary/chief_of_staff_143032.md
   │
⑦ CEO 화면에 최종 결과 표시
   │
⑧ Orchestrator: git add reports/ → git commit → git push (1회)
   └─ GitHub에 6개 파일 자동 업로드 완료
```

---

### 수정된 파일 상세 (5개 파일)

| 파일 | 상태 | 변경 내용 |
|------|------|-----------|
| `src/core/report_saver.py` | **신규** | `save_agent_report()` 함수. AgentConfig의 division 값을 폴더 경로로 변환하고, 날짜/시간 기반 파일명으로 마크다운 보고서를 저장 |
| `src/core/git_sync.py` | **신규** | `auto_push_reports()` 함수. `reports/` 디렉토리 전체를 `git add → commit → push`. push 실패 시 exponential backoff 재시도 (최대 4회) |
| `src/core/agent.py` | **수정** | `BaseAgent.handle_task()` 끝에 `_save_to_archive()` 호출 추가. 모든 에이전트(25명)가 상속하므로 한 곳만 수정하면 전체 적용 |
| `src/core/orchestrator.py` | **수정** | `process_command()` 끝에 `auto_push_reports()` 호출 추가. 에이전트들의 개별 저장과 분리하여 마지막에 한 번만 push |
| `.env.example` | **수정** | `CORTHEX_AUTO_UPLOAD=1` 환경변수 추가 (자동 업로드 ON/OFF 제어) |

### 설정 방법

`.env` 파일에서 자동 업로드를 켜고 끌 수 있습니다:
```
CORTHEX_AUTO_UPLOAD=1   # 켜기 (기본값 — 설정 안 하면 자동으로 ON)
CORTHEX_AUTO_UPLOAD=0   # 끄기 (로컬 저장만 하고 GitHub push 안 함)
```

**참고:** `CORTHEX_AUTO_UPLOAD=0`으로 해도 `reports/` 폴더에 보고서 **저장은 됩니다.** GitHub push만 안 할 뿐입니다.

### v0.3.0 → v0.4.0 비교

| 항목 | v0.3.0 | v0.4.0 |
|------|--------|--------|
| 최종 보고서 저장 | 화면 표시만 | 파일 저장 + GitHub push |
| 중간 산출물 보존 | 소멸 (접근 불가) | **전부 파일로 보존** |
| 아카이브 구조 | 없음 | **날짜/부서별 폴더** |
| GitHub 업로드 | 수동 | **자동 (매 명령마다)** |
| 네트워크 실패 대응 | — | **4회 재시도 (exponential backoff)** |
| ON/OFF 제어 | — | **환경변수로 제어 가능** |

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
