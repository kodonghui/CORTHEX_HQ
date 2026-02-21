# CORTHEX HQ — 자율 운영 시스템 v3.00.000 구현 프롬프트

> **이 파일의 목적**: compact 후 새 세션에서 CEO가 이 파일 경로를 주면, 새 Claude가 맥락 없이도 바로 작업을 시작할 수 있도록 하는 완전한 맥락 문서.
>
> **작성일**: 2026-02-18 | **작성자**: Claude Sonnet 4.5

---

## 0. 새 Claude에게 — 이 파일을 읽었으면 다음을 순서대로 하라

1. 이 파일 전체를 읽는다
2. `docs/project-status.md` 읽기
3. `docs/updates/` 폴더 최신 파일 2~3개 읽기 (날짜 최신순)
4. 아래 "반드시 읽어야 할 파일 목록" 6개 읽기
5. 팀 에이전트 FE + BE + QA 3명 구성 후 1단계부터 구현 시작

---

## 1. 프로젝트 기본 정보

| 항목 | 내용 |
|------|------|
| 저장소 | https://github.com/kodonghui/CORTHEX_HQ |
| CEO | 고동희 (비개발자, 한국어로 소통) |
| 서버 | Oracle Cloud ARM 24GB (IP: GitHub Secrets `SERVER_IP_ARM`) |
| 도메인 | `http://corthex-hq.com` (2026-02-18 구매, HTTPS도 설정됨) |
| 작업 브랜치 | `claude/autonomous-system-v3` (새로 만들 것) |
| 목표 버전 | `3.00.000` |
| 현재 버전 | `2.00.000` |

---

## 2. 반드시 먼저 읽어야 할 파일 6개

읽지 않고 코딩하면 기존 코드와 충돌 가능성 높음.

| 파일 경로 | 왜 읽어야 하는가 |
|----------|----------------|
| `web/mini_server.py` | 서버 핵심 파일 (6600줄+). `_call_agent()`, `_broadcast_to_managers()`, WebSocket 핸들러 위치 파악 필수 |
| `web/ai_handler.py` | AI 호출 함수. `ask_ai()`, `SPAWN_AGENT_TOOL_SCHEMA` 위치 확인 |
| `web/db.py` | DB 함수. `save_setting()`, `load_setting()` 사용법 파악 |
| `web/templates/index.html` | 프론트엔드 (5000줄+). Alpine.js 상태, WebSocket, 탭 구조 확인 |
| `config/agents.yaml` | 29명 에이전트 설정. agent_id, system_prompt, allowed_tools |
| `src/tools/cross_agent_protocol.py` | 에이전트 간 통신. `register_call_agent()` 콜백 |

---

## 3. 이미 구현된 것들 (절대 건드리지 말 것)

2026-02-17 세션에서 완료됨.

### 스마트 라우팅 (mini_server.py)
- `_determine_routing_level(message)` — Level 1~4 판단
  - Level 1: 비서실장만 (인사말, 간단 질문)
  - Level 2: 처장 1명만 (특정 담당 업무)
  - Level 3: 처장 + spawn_agent 자율 선택 (복잡한 분석)
  - Level 4: 전원 병렬 (/전체 명령어, 전략 질문)
- `_manager_with_delegation_autonomous()` — Level 3용
- `_chief_finalize()` — 처장 응답 비서실장 종합
- `_broadcast_to_managers_all()` — Level 4 전원 병렬
- `_broadcast_to_managers()` — 라우팅 허브

### spawn_agent 도구 (ai_handler.py)
- `SPAWN_AGENT_TOOL_SCHEMA` — 처장이 Function Calling으로 전문가 자율 호출

### 실시간 에이전트 통신 (cross_agent_protocol.py)
- `register_call_agent(fn)` — 서버 시작 시 콜백 등록
- `_request()` — 파일 저장 + 실시간 AI 호출 동시 지원

### 사령실 수신자 드롭다운 (index.html)
- CEO가 특정 에이전트에게 직접 메시지 가능
- `targetAgentId` Alpine.js 상태, WebSocket 메시지에 `target_agent_id` 포함

---

## 4. 이번 세션에서 구현할 것 — 5가지 자율 운영 시스템

---

### ══════════════════════════════════════════
### 기능 1: 에이전트 장기 기억 (Agent Memory)
### ══════════════════════════════════════════

**한 줄 설명**: 에이전트들이 CEO의 취향, 결정사항, 중요 맥락을 기억하고 다음 대화에서 활용한다.

**비유**: 지금은 매 대화마다 기억이 초기화되는 직원 → 개선 후엔 수첩에 메모해두고 다음에 활용하는 직원.

#### 구현 세부 사항

**① DB 저장 방식** — 기존 `settings` 테이블 활용 (간단)

```python
# db.py에 추가
def save_agent_memory(agent_id: str, memory_dict: dict):
    """에이전트 기억 저장"""
    save_setting(f"memory_{agent_id}", memory_dict)

def load_agent_memory(agent_id: str) -> dict:
    """에이전트 기억 로드"""
    return load_setting(f"memory_{agent_id}", {})
```

**② mini_server.py의 `_call_agent()` 수정**

`_call_agent()` 호출 직전에 해당 에이전트 기억을 DB에서 꺼내 system_prompt 앞에 붙임.

```python
async def _call_agent(agent_id, task, ...):
    system_prompt = agents_config[agent_id]["system_prompt"]

    # ★ 추가: 기억 불러와서 system_prompt 앞에 붙이기
    memory = load_agent_memory(agent_id)
    if memory:
        memory_lines = []
        if memory.get("ceo_preferences"):
            memory_lines.append(f"• CEO 취향: {memory['ceo_preferences']}")
        if memory.get("decisions"):
            memory_lines.append(f"• 중요 결정: {memory['decisions']}")
        if memory.get("warnings"):
            memory_lines.append(f"• 주의사항: {memory['warnings']}")
        if memory.get("context"):
            memory_lines.append(f"• 맥락: {memory['context']}")
        if memory_lines:
            system_prompt = "📌 [에이전트 기억]\n" + "\n".join(memory_lines) + "\n\n" + system_prompt

    # ... 기존 AI 호출 ...

    # ★ 추가: 대화 후 기억 업데이트 (백그라운드)
    asyncio.create_task(_extract_and_save_memory(agent_id, task, response))
    return response
```

**③ `_extract_and_save_memory()` 함수 (새로 추가)**

대화 후 저렴한 모델(haiku)로 "기억할 것" 추출 → DB 저장.

```python
async def _extract_and_save_memory(agent_id, task, response):
    extraction_prompt = f"""
아래 대화에서 기억할 정보가 있으면 JSON으로 추출해라. 없으면 빈 dict {{}} 반환.

[대화]
사용자: {task[:500]}
에이전트: {response[:500]}

[추출 항목]
- ceo_preferences: CEO가 선호하거나 싫어하는 것 (있으면)
- decisions: "~하기로 결정", "~로 확정" 등 중요 결정 (있으면)
- warnings: 이 방법은 안 됨, CEO가 싫다고 함 등 주의사항 (있으면)
- context: 프로젝트 상태, 거래처, 일정 등 중요 맥락 (있으면)

JSON만 반환 (설명 없이):
"""
    try:
        result_text = await ask_ai(extraction_prompt, model="claude-haiku-4-5-20251001", max_tokens=500)
        import json
        new_facts = json.loads(result_text.strip())
        if new_facts:
            existing = load_agent_memory(agent_id)
            # 기존 기억과 병합 (각 필드 append)
            for key, val in new_facts.items():
                if val and val != "null":
                    existing[key] = (existing.get(key, "") + " / " + str(val)).strip(" /")
            save_agent_memory(agent_id, existing)
    except Exception:
        pass  # 기억 추출 실패해도 메인 응답에 영향 없음
```

**④ 기억 관리 API 추가**

```
GET    /api/agent-memory/{agent_id}   → 해당 에이전트 기억 조회
POST   /api/agent-memory/{agent_id}   → 기억 수동 추가 (CEO 직접 입력)
DELETE /api/agent-memory/{agent_id}   → 기억 초기화
```

**⑤ UI (설정 탭에 "에이전트 기억 관리" 섹션 추가)**
- 에이전트 선택 드롭다운 (29명)
- 현재 기억 항목 목록 표시 (카테고리별)
- "기억 추가" 버튼 → 텍스트 직접 입력
- "초기화" 버튼 (에이전트별)

---

### ══════════════════════════════════════════
### 기능 2: 능동적 에이전트 (Proactive Agents)
### ══════════════════════════════════════════

**한 줄 설명**: 에이전트들이 CEO의 질문 없이도 스스로 판단해서 먼저 보고하고 알림을 보낸다.

**비유**: 지금은 CEO가 전화해야만 연락되는 직원 → 개선 후엔 이상 감지 시 먼저 알리는 야간 당직 직원.

#### 구현 세부 사항

**① 능동 스케줄 기본값 설정**

```python
# mini_server.py 상단 상수로 추가
DEFAULT_PROACTIVE_SCHEDULES = [
    {
        "id": "morning_brief",
        "name": "조간 보고",
        "agent_id": "chief_of_staff",
        "enabled": True,
        "trigger_type": "schedule",
        "schedule": "0 9 * * *",       # 매일 오전 9시 KST
        "condition": None,
        "prompt": "CEO에게 오늘의 조간 보고를 작성해라. 오늘 날짜, 요일, 주요 일정(있으면), 주요 시장 현황을 1페이지로 정리.",
        "output": ["telegram", "chat"],
        "last_run": None
    },
    {
        "id": "weekly_investment",
        "name": "주간 투자 보고",
        "agent_id": "cio_manager",
        "enabled": True,
        "trigger_type": "schedule",
        "schedule": "0 9 * * MON",     # 매주 월요일 오전 9시
        "condition": None,
        "prompt": "주간 투자 현황 보고서를 작성해라. 지난 주 포트폴리오 성과, 주요 종목 동향, 이번 주 주목할 이벤트, 투자 권고사항을 A4 1장 분량으로.",
        "output": ["telegram", "chat"],
        "last_run": None
    },
    {
        "id": "budget_alert",
        "name": "예산 소진 경고",
        "agent_id": "cso_manager",
        "enabled": True,
        "trigger_type": "schedule",
        "schedule": "0 0 * * *",       # 매일 자정 체크
        "condition": None,
        "prompt": "이번 달 예산 소진 현황을 점검하고, 80% 이상 소진됐거나 이상이 있으면 CEO에게 보고해라. 정상이면 보고 생략.",
        "output": ["telegram"],
        "last_run": None
    }
]
```

**② 백그라운드 스케줄러 (mini_server.py 서버 시작 부분에 추가)**

```python
async def start_proactive_scheduler():
    """서버 시작 시 백그라운드 스케줄러 시작"""
    asyncio.create_task(_proactive_scheduler_loop())

async def _proactive_scheduler_loop():
    """1분마다 스케줄 체크하는 무한 루프"""
    while True:
        try:
            await _check_and_run_proactive_agents()
            await _check_and_run_workflows()  # 기능5 워크플로우도 함께 체크
        except Exception as e:
            logger.error(f"스케줄러 오류: {e}")
        await asyncio.sleep(60)  # 1분마다

async def _check_and_run_proactive_agents():
    """실행 조건이 된 능동 에이전트 찾아서 실행"""
    schedules = load_setting("proactive_schedules", DEFAULT_PROACTIVE_SCHEDULES)
    now_kst = _get_kst_now()

    for schedule in schedules:
        if not schedule.get("enabled"):
            continue
        if _should_run_cron(schedule.get("schedule"), schedule.get("last_run"), now_kst):
            asyncio.create_task(_run_proactive_agent(schedule))
            schedule["last_run"] = now_kst.isoformat()

    save_setting("proactive_schedules", schedules)

async def _run_proactive_agent(schedule):
    """능동 에이전트 실제 실행 → 텔레그램/채팅으로 전송"""
    result = await _call_agent(schedule["agent_id"], schedule["prompt"])

    if "telegram" in schedule.get("output", []):
        await _send_telegram(f"🤖 [{schedule['name']}]\n\n{result}")
    if "chat" in schedule.get("output", []):
        await _broadcast_to_websocket({
            "type": "proactive_message",
            "agent_id": schedule["agent_id"],
            "schedule_name": schedule["name"],
            "content": result
        })

def _should_run_cron(cron_expr, last_run_iso, now_kst):
    """cron 표현식 기반으로 지금 실행해야 하는지 판단"""
    # 간단 구현: last_run이 없거나, cron 조건이 현재 시간과 맞으면 True
    # 실제로는 croniter 라이브러리 또는 간단한 파싱 사용
    # cron_expr 예: "0 9 * * *" → 매일 9시 0분
    if not cron_expr:
        return False
    parts = cron_expr.split()
    if len(parts) != 5:
        return False
    minute, hour, day, month, weekday = parts
    now_minute = now_kst.minute
    now_hour = now_kst.hour
    now_weekday = now_kst.weekday()  # 0=월요일

    minute_match = (minute == "*" or int(minute) == now_minute)
    hour_match = (hour == "*" or int(hour) == now_hour)
    weekday_map = {"MON":0,"TUE":1,"WED":2,"THU":3,"FRI":4,"SAT":5,"SUN":6}
    if weekday == "*":
        weekday_match = True
    else:
        wd = weekday_map.get(weekday, -1)
        weekday_match = (wd == now_weekday)

    if not (minute_match and hour_match and weekday_match):
        return False

    # last_run이 오늘 이미 실행됐으면 스킵
    if last_run_iso:
        from datetime import datetime
        last_run = datetime.fromisoformat(last_run_iso)
        if (now_kst - last_run).total_seconds() < 3300:  # 55분 이내면 스킵
            return False
    return True
```

**③ 능동 에이전트 관리 API**

```
GET    /api/proactive-schedules          → 전체 스케줄 목록
PUT    /api/proactive-schedules/{id}     → 수정 (활성화/비활성화, 프롬프트, 시간)
POST   /api/proactive-schedules          → 새 스케줄 추가
DELETE /api/proactive-schedules/{id}     → 삭제
POST   /api/proactive-schedules/{id}/run → 즉시 실행 (테스트)
```

**④ UI (설정 탭에 "능동 에이전트" 섹션 추가)**
- 스케줄 카드 목록 (이름, 담당, 실행 주기, on/off 토글)
- "지금 실행" 버튼 (테스트)
- 최근 실행 이력 (언제, 어떤 에이전트가 실행됐는지)
- "새 스케줄 추가" 버튼 → 폼 (이름, 에이전트 선택, 실행 주기, 지시문)

---

### ══════════════════════════════════════════
### 기능 3: 비동기 작업 (Async Task Queue)
### ══════════════════════════════════════════

**한 줄 설명**: 긴 AI 작업을 맡기면 즉시 접수 확인 받고, 완료 시 알림 받는다. 기다리지 않아도 된다.

**비유**: 음식점 주문번호 시스템. 37번 받고 자유롭게 있다가 번호 불리면 받는 방식.

#### 구현 세부 사항

**① DB 테이블 — settings 테이블 활용 또는 별도 테이블**

별도 테이블 권장 (작업 이력 관리 용이):

```sql
-- web/db.py의 _init_db() 안에 추가
CREATE TABLE IF NOT EXISTS async_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    status TEXT DEFAULT 'pending',   -- pending|running|completed|failed|cancelled
    agent_id TEXT,
    prompt TEXT NOT NULL,
    result TEXT,
    progress INTEGER DEFAULT 0,
    progress_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,
    output_channels TEXT DEFAULT '["chat"]'
);
```

**② 비동기 작업 판단 + 실행 흐름**

```python
def _is_async_task(message: str) -> bool:
    """이 메시지가 비동기 처리가 필요한 긴 작업인지 판단"""
    # 방법 1: 명시적 태그
    if message.startswith("@비동기") or message.startswith("@async"):
        return True
    # 방법 2: 긴 작업 키워드
    async_keywords = ["보고서 작성", "전체 분석", "종합 분석", "월간", "주간 정리", "심층 분석", "포트폴리오 전체"]
    return any(kw in message for kw in async_keywords)

async def _submit_async_task(agent_id, message, output_channels=["chat", "telegram"]):
    """비동기 작업 등록 → 즉시 접수 메시지 반환"""
    from datetime import datetime
    task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # DB에 저장
    _save_async_task(task_id, message[:50]+"...", agent_id, message, output_channels)

    # 백그라운드 실행
    asyncio.create_task(_run_async_task(task_id))

    return f"✅ 작업이 접수됐습니다 (#{task_id})\n📋 담당: {agent_id}\n완료되면 텔레그램과 채팅으로 알려드립니다."

async def _run_async_task(task_id):
    """백그라운드 작업 실행"""
    task = _load_async_task(task_id)
    _update_task_status(task_id, "running", 10, "작업 시작 중...")
    _push_task_progress(task_id, 10, "작업 시작 중...")

    try:
        _update_task_status(task_id, "running", 30, "데이터 수집 중...")
        _push_task_progress(task_id, 30, "데이터 수집 중...")

        result = await _call_agent(task["agent_id"], task["prompt"])

        _update_task_status(task_id, "completed", 100, "완료")
        _save_task_result(task_id, result)

        # 결과 전송
        channels = task.get("output_channels", ["chat"])
        if "telegram" in channels:
            await _send_telegram(f"🔔 작업 완료 (#{task_id})\n\n{result[:1000]}...")
        if "chat" in channels:
            await _broadcast_to_websocket({
                "type": "task_completed",
                "task_id": task_id,
                "content": result
            })
    except Exception as e:
        _update_task_status(task_id, "failed", 0, f"실패: {str(e)}")

def _push_task_progress(task_id, progress, message):
    """WebSocket으로 진행률 실시간 전송"""
    # 기존 _broadcast_to_websocket() 사용
    asyncio.create_task(_broadcast_to_websocket({
        "type": "task_progress",
        "task_id": task_id,
        "progress": progress,
        "message": message
    }))
```

**③ API 추가**

```
GET    /api/async-tasks                    → 작업 목록 (최근 20개)
GET    /api/async-tasks/{task_id}          → 특정 작업 상태/결과
POST   /api/async-tasks/{task_id}/cancel   → 작업 취소
```

**④ UI (사령실 탭에 "진행 중인 작업" 패널 추가)**
- 채팅창 위쪽 또는 사이드에 미니 패널
- 각 작업: 아이콘 + 작업명 + 담당 + 진행률 바 + 경과 시간
- 완료 클릭 → 결과 전체보기 모달
- 취소 버튼 (진행 중만)
- 작업 없으면 패널 숨김 (깔끔하게)

---

### ══════════════════════════════════════════
### 기능 4: 에이전트 토론 시스템 (Agent Debate)
### ══════════════════════════════════════════

**한 줄 설명**: 처장들이 서로 반박하며 토론해서 더 나은 결론을 도출한다.

**비유**: 지금은 각 처장이 독립 보고서 제출 → 개선 후엔 처장들이 서로 의견을 반박하는 "임원 회의".

#### 핵심 설계 원칙 (CEO가 직접 만든 startup_investment.py에서 검증된 패턴)

**원칙 1: 2바퀴 구조 (필수)**
```
바퀴 1: 각 처장 독립 의견 (병렬 실행, 서로 모름)
바퀴 2: 각 처장이 바퀴1 전체 읽고 반박/보완 (순차 실행)
최종: 비서실장이 합의점/이견 구분해서 CEO에게 보고
```

**원칙 2: "동의 금지" 규칙 (한 줄이지만 효과 극대)**

각 처장 system_prompt에 추가 (agents.yaml 수정 또는 debate 호출 시 system_prompt에 append):
```
"다른 처장의 의견에서 반드시 최소 1가지 문제점이나 반박 근거를 찾아서 지적해라.
'동의합니다', '좋은 의견입니다', '전적으로 공감합니다' 같은 빈 동의 표현은 절대 금지."
```

**원칙 3: 처장별 방법론 태그 강제**

| 처장 | 필수 태그 | 역할 |
|------|---------|------|
| cio_manager | [ROI] [리스크등급] [예상수익] | 투자/재무 관점 |
| cto_manager | [기술판정] [개발공수] [확장성] | 기술 타당성 |
| cso_manager | [리스크시나리오] [발생확률] [대응책] | 전략/리스크 |
| cmo_manager | [채널] [전환율] [CAC] [LTV] | 마케팅/성장 |
| clo_manager | [법적리스크] [준수여부] [권고사항] | 법무/컴플라이언스 |
| cpo_manager | [우선순위] [사용자가치] [운영비용] | 제품/운영 |

**원칙 4: 발언 순서 균등 로테이션**

```python
DEBATE_ROTATION = {
    (1, 1): ["cio_manager", "cto_manager", "cso_manager", "cmo_manager", "clo_manager", "cpo_manager"],
    (1, 2): ["cto_manager", "cso_manager", "cio_manager", "clo_manager", "cmo_manager", "cpo_manager"],
    (2, 1): ["cso_manager", "cmo_manager", "cto_manager", "cio_manager", "cpo_manager", "clo_manager"],
    # 계속 순환...
}
```

**원칙 5: 별첨 분석 → spawn_agent 연결**

처장 발언 중 `[심층분석요청: X]` 태그 감지 → 해당 전문가 spawn_agent 호출 → 결과를 다음 바퀴에 추가.
(이미 구현된 spawn_agent 기능 활용)

#### 구현 위치

새 함수 `_broadcast_with_debate()` 추가 (mini_server.py). 기존 `_broadcast_to_managers_all()`은 건드리지 말 것.

```python
async def _broadcast_with_debate(ceo_message, rounds=2):
    """임원 회의 방식 토론 — CEO 메시지를 처장들이 다단계 토론"""
    debate_history = ""
    all_round_responses = {}

    for round_num in range(1, rounds + 1):
        rotation_key = (round_num, 1) if round_num == 1 else (round_num - 1, 2)
        manager_ids = DEBATE_ROTATION.get(rotation_key, list(_MANAGER_SPECIALISTS.keys()))

        if round_num == 1:
            # 바퀴 1: 병렬 (서로 모르고 독립 의견)
            debate_system_append = "\n\n[토론 규칙]\n다른 참가자의 의견에서 반드시 최소 1가지 문제점 지적 필수. '동의합니다' 금지."
            tasks = [_call_agent_debate(mid, ceo_message, "", debate_system_append) for mid in manager_ids]
            responses = await asyncio.gather(*tasks)
            for mid, resp in zip(manager_ids, responses):
                all_round_responses[mid] = resp
                debate_history += f"\n[{mid} - 1라운드]\n{resp}\n"
        else:
            # 바퀴 2+: 순차 (이전 바퀴 전체 읽고 반박)
            rebuttal_instruction = "\n\n[재반박 라운드]\n이전 발언들을 읽고:\n1. 다른 처장 의견 중 문제점 최소 1가지 구체적으로 지적\n2. '동의합니다' 금지\n3. 기존 주장의 약점 파고들기"
            for mid in manager_ids:
                resp = await _call_agent_debate(mid, ceo_message, debate_history, rebuttal_instruction)
                all_round_responses[mid] = resp
                debate_history += f"\n[{mid} - {round_num}라운드]\n{resp}\n"

    # 비서실장 종합
    final = await _chief_finalize_debate(ceo_message, debate_history)
    return final

async def _call_agent_debate(agent_id, topic, history, extra_instruction):
    """토론용 에이전트 호출"""
    prompt = f"[토론 주제]\n{topic}\n\n[이전 발언들]\n{history if history else '(첫 발언)'}\n\n{extra_instruction}"
    return await _call_agent(agent_id, prompt)
```

#### 토론 진입 방법

```python
# _process_ai_command() 또는 WebSocket 핸들러에서 처리
if message.startswith("/토론"):
    result = await _broadcast_with_debate(message.replace("/토론", "").strip(), rounds=2)
elif message.startswith("/심층토론"):
    result = await _broadcast_with_debate(message.replace("/심층토론", "").strip(), rounds=3)
```

---

### ══════════════════════════════════════════
### 기능 5: 워크플로우 빌더 (No-code Workflow)
### ══════════════════════════════════════════

**한 줄 설명**: CEO가 코드 없이 "이 순서대로 이렇게 해라"는 업무 절차서를 UI에서 직접 만들면 CORTHEX가 자동 반복 실행한다.

**비유**: IFTTT. "만약 월요일 9시면 CIO처장이 투자 보고서 작성하고 텔레그램으로 보내라" 설정 저장 → 자동 실행.

#### 구현 세부 사항

**① 워크플로우 데이터 구조 (JSON → settings 테이블 저장)**

```python
WORKFLOW_SCHEMA_EXAMPLE = {
    "id": "wf_001",
    "name": "주간 투자 보고서",
    "description": "매주 월요일 CIO → 비서실장 → 텔레그램",
    "enabled": True,
    "trigger": {
        "type": "schedule",       # "schedule" | "manual"
        "cron": "0 9 * * MON",   # 매주 월요일 9시 (KST)
    },
    "steps": [
        {
            "step_id": "s1",
            "name": "CIO 분석",
            "agent_id": "cio_manager",
            "prompt": "이번 주 포트폴리오 현황과 주요 종목 동향을 분석해줘",
            "output_to_next": True   # True면 이 결과를 다음 단계 prompt 앞에 붙임
        },
        {
            "step_id": "s2",
            "name": "비서실장 정리",
            "agent_id": "chief_of_staff",
            "prompt": "CIO처장 분석을 CEO에게 전달할 형식으로 정리해줘",
            "depends_on": "s1",
            "output_to_next": False
        }
    ],
    "output": ["telegram", "chat"],
    "created_at": "2026-02-18",
    "last_run": None,
    "run_count": 0
}
```

**② 워크플로우 실행 엔진 (mini_server.py)**

```python
async def _run_workflow(workflow: dict):
    """워크플로우 단계별 순서대로 실행"""
    step_results = {}

    for step in workflow["steps"]:
        prompt = step["prompt"]
        if step.get("depends_on"):
            prev = step_results.get(step["depends_on"], "")
            prompt = f"[이전 단계 결과]\n{prev}\n\n[현재 지시]\n{prompt}"

        result = await _call_agent(step["agent_id"], prompt)
        step_results[step["step_id"]] = result

    final = step_results[workflow["steps"][-1]["step_id"]]

    if "telegram" in workflow.get("output", []):
        await _send_telegram(f"🔄 [{workflow['name']}]\n\n{final}")
    if "chat" in workflow.get("output", []):
        await _broadcast_to_websocket({"type": "workflow_result", "workflow_name": workflow["name"], "content": final})

    workflow["last_run"] = _get_kst_now().isoformat()
    workflow["run_count"] = workflow.get("run_count", 0) + 1

async def _check_and_run_workflows():
    """스케줄러에서 1분마다 호출 — 실행 시간 된 워크플로우 실행"""
    workflows = load_setting("workflows", [])
    now_kst = _get_kst_now()
    for wf in workflows:
        if wf.get("enabled") and wf.get("trigger", {}).get("type") == "schedule":
            if _should_run_cron(wf["trigger"]["cron"], wf.get("last_run"), now_kst):
                asyncio.create_task(_run_workflow(wf))
    save_setting("workflows", workflows)
```

**③ 워크플로우 API**

```
GET    /api/workflows               → 전체 목록
POST   /api/workflows               → 새 워크플로우 생성
PUT    /api/workflows/{id}          → 수정
DELETE /api/workflows/{id}          → 삭제
PUT    /api/workflows/{id}/toggle   → 활성화/비활성화
POST   /api/workflows/{id}/run-now  → 즉시 실행 (테스트)
GET    /api/workflows/{id}/history  → 실행 이력
```

**④ UI (새 탭 "워크플로우" 추가 — 사이드바에)**

목록 화면:
- 워크플로우 카드 (이름, 설명, 다음 실행 예정, on/off 토글, "지금 실행" 버튼)
- "새 워크플로우 만들기" 버튼

생성/편집 화면 (사이드 패널):
- 이름, 설명 입력
- 실행 조건 선택: 수동 / 매일(시간) / 매주(요일+시간) / 매달(날짜+시간)
- 단계 추가 (+버튼): 에이전트 선택 + 지시문 + "이전 결과 포함" 체크박스
- 단계 순서 변경 (드래그 or 위/아래 버튼)
- 출력 채널 선택 (텔레그램, 채팅)
- 저장 버튼

---

## 5. 팀 구성

기본팀 3명으로 진행.

| 팀원 | 코드명 | 담당 파일 | 역할 |
|------|--------|----------|------|
| 팀원1 | FE | `web/templates/index.html` | 기능 1,2,3,5의 UI 구현 |
| 팀원2 | BE | `web/mini_server.py`, `web/db.py` | 기능 1,2,3,4,5의 서버 로직 구현 |
| 팀원3 | QA | 전체 | 다크모드 확인, API 응답 검증, 파일 충돌 점검 |

**팀 규칙:**
- FE와 BE가 같은 파일을 동시에 수정하지 말 것
- BE가 API 완성하면 FE가 연결하는 순서 지킬 것
- 서브에이전트(Explore) 적극 활용해서 코드 파악

---

## 6. 작업 순서 (1단계부터 순서대로)

```
1단계: 에이전트 기억 시스템 ← 가장 쉬움, DB만 있으면 됨
   BE: db.py 함수 추가 + _call_agent() 수정 + API 3개
   FE: 설정 탭에 "에이전트 기억 관리" 섹션 추가

2단계: 능동적 에이전트 ← 스케줄러 추가
   BE: 백그라운드 루프 + 스케줄 체크 함수 + API 5개
   FE: 설정 탭에 "능동 에이전트" 섹션 추가

3단계: 비동기 작업 ← WebSocket 활용
   BE: async_tasks 테이블 + 실행 로직 + API 3개
   FE: 사령실에 "진행 중인 작업" 패널 추가

4단계: 에이전트 토론 ← 핵심 기능
   BE: _broadcast_with_debate() + DEBATE_ROTATION
   agents.yaml: 처장 system_prompt에 방법론 태그 강제 추가
   FE: /토론, /심층토론 명령어 처리

5단계: 워크플로우 빌더 ← 가장 복잡
   BE: 워크플로우 엔진 + 스케줄러 통합 + API 7개
   FE: 새 탭 "워크플로우" 전체 (목록 + 편집)
```

---

## 7. 절대 금지 사항

| 금지 | 이유 |
|------|------|
| `_determine_routing_level()` 수정 | 스마트 라우팅 망가짐 |
| `_broadcast_to_managers()` 라우팅 허브 로직 수정 | CEO 메시지 처리 망가짐 |
| agents.yaml system_prompt 기존 내용 삭제 | Soul 파괴됨, 추가만 가능 |
| `git pull` 사용 | 배포 충돌, 반드시 `git fetch + git reset --hard` |
| JSON 파일에 사용자 데이터 저장 | 배포 시 날아감, 반드시 SQLite |
| 기존 API 엔드포인트 URL 변경 | 프론트엔드 연결 끊어짐 |

---

## 8. 커밋/배포 규칙

- 작업 브랜치: `claude/autonomous-system-v3`
- 중간 커밋 + 푸시 수시로
- 마지막 커밋 메시지: `feat: 자율 운영 시스템 v3.00.000 구현 [완료]`
- `[완료]` 있어야 자동 머지 → 자동 배포 작동

---

## 9. 완료 기준 체크리스트

```
□ 기능1: 에이전트와 대화 후 DB에 기억 저장됨. 다음 대화 시 기억이 system_prompt에 포함됨.
□ 기능2: 매일 9시 비서실장이 자동 조간 보고 → 텔레그램 발송.
□ 기능3: "보고서 작성" 요청 시 즉시 접수 메시지. 완료 후 텔레그램 알림. 진행률 표시.
□ 기능4: "/토론" 입력 시 처장 2바퀴 토론 후 합의 결론. "동의합니다" 표현 없음.
□ 기능5: 워크플로우 탭에서 새 워크플로우 생성/저장. "지금 실행"으로 즉시 테스트 가능.
□ 배포: GitHub Actions 빌드 완료. http://corthex-hq.com 에서 모든 기능 정상.
□ docs/updates/ 에 작업 기록 파일 생성.
□ docs/project-status.md 버전 3.00.000으로 업데이트.
```

---

## 10. 참고 — startup_investment.py 토론 패턴 요약

CEO가 직접 만든 별도 프로젝트의 토론 시스템. 기능 4 구현 시 이 패턴을 따를 것.

**검증된 핵심 패턴:**
1. `passes: 2` — 2바퀴 구조 (발언 + 재반박)
2. `pass_instruction` — 2바퀴에 "동의 금지, 반박 1개 이상" 지시문 자동 추가
3. `ROTATION_TABLE` — 발언 순서 미리 고정 (랜덤 제거, 균등 기회)
4. 역할별 방법론 태그 강제 (CEO=PDCA, CTO=6시그마, CMO=AARRR)
5. `[별첨 제안: X]` 태그 → CORTHEX에서는 `[심층분석요청: X]` → spawn_agent 트리거
6. CEO/비서실장을 마지막 발언자로 고정 (최종 합의 도출)

**CORTHEX 적용 차이점:**
- startup_investment.py는 외부 스크립트로 Claude/Gemini/GPT 각각 직접 호출
- CORTHEX는 mini_server.py 내부에서 `_call_agent()`로 처장들 호출
- 다른 AI 모델은 `ai_handler.py`의 `ask_ai(model=...)` 파라미터로 지정 가능
  (예: CTO처장에게 gemini-2.0-flash 배정 가능)
```
