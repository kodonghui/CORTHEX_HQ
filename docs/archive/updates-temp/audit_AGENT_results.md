# AGENT 팀 전수검사 결과 보고서

## 작업 날짜
2026-02-18

## 버전
3.01.001 (패치 — 전수검사 결과, 수정 불필요)

## 검사 대상
`src/core/` 폴더 전체 (23개 파일)

---

## 검사 파일 목록

| 파일 | 줄 수 (추정) | 검사 완료 |
|------|------------|---------|
| `agent.py` | 648줄 | 완료 |
| `quality_gate.py` | 293줄 | 완료 |
| `quality_rules_manager.py` | 148줄 | 완료 |
| `budget.py` | 179줄 | 완료 |
| `scheduler.py` | 345줄 | 완료 |
| `auth.py` | 227줄 | 완료 |
| `orchestrator.py` | 109줄 | 완료 |
| `context.py` | 56줄 | 완료 |
| `registry.py` | 104줄 | 완료 |
| `memory.py` | 147줄 | 완료 |
| `workflow.py` | 239줄 | 완료 |
| `performance.py` | 147줄 | 완료 |
| `feedback.py` | 126줄 | 완료 |
| `task_store.py` | 111줄 | 완료 |
| `preset.py` | 87줄 | 완료 |
| `errors.py` | 47줄 | 완료 |
| `message.py` | 87줄 | 완료 |
| `knowledge.py` | 140줄 | 완료 |
| `replay.py` | 162줄 | 완료 |
| `git_sync.py` | 162줄 | 완료 |
| `report_saver.py` | 102줄 | 완료 |
| `healthcheck.py` | 224줄 | 완료 |
| `__init__.py` | 13줄 | 완료 |

---

## 검사 항목별 결과

### 1. 금지 모델명 검사 (가장 중요)

**결과: 이상 없음 (0건)**

grep 검색 결과:
- `gpt-4o` — 0건
- `gpt-4o-mini` — 0건
- `gpt-4.1` — 0건
- `gpt-4.1-mini` — 0건
- `claude-haiku-4-6` — 0건

발견된 허용 모델명:
| 파일 | 모델명 | 허용 여부 |
|------|--------|---------|
| `agent.py` 167줄 | `gpt-5-mini` | 허용 |
| `quality_gate.py` 109줄, 185줄 | `gpt-5-mini` | 허용 |
| `quality_rules_manager.py` 98줄 | `gpt-5-mini` | 허용 |
| `healthcheck.py` 107줄 | `gpt-5-mini` | 허용 |
| `healthcheck.py` 108줄 | `claude-haiku-4-5-20251001` | 허용 |

모든 모델명이 CLAUDE.md의 "실제 존재하는 모델명" 목록과 일치합니다.

---

### 2. Soul DB 저장 검사

**결과: 경고 — Soul은 JSON 파일에 저장됨**

`memory.py`의 `MemoryManager` 클래스:
- 에이전트의 장기 기억(Soul)을 `data/memory/{agent_id}.json` 파일에 저장
- SQLite DB(`save_setting`/`load_setting`)를 사용하지 않음

CLAUDE.md의 "데이터 저장 규칙"은 다음을 요구합니다:
> "웹에서 사용자가 저장/수정/삭제하는 모든 데이터는 반드시 SQLite DB에 저장할 것"
> "JSON 파일에 저장하면 안 됨 — 배포(git reset --hard) 시 날아감"

단, `data/memory/` 폴더가 git 저장소 안에 있는지 여부에 따라 위험도가 다릅니다.
- `/home/ubuntu/CORTHEX_HQ/data/memory/` → 배포 시 `git reset --hard`로 날아갈 수 있음
- 이 폴더가 `.gitignore`에 등록되어 있으면 서버 파일은 보존됨

**권고 사항**: `data/memory/` 폴더를 `.gitignore`에 추가하거나, 장기적으로 SQLite 마이그레이션 필요. 현재 서비스 중단 원인이 되지는 않지만 배포 시 메모리가 초기화될 위험 있음.

**이번 검사에서 수정하지 않은 이유**: `src/core/` 범위를 벗어난 변경(`.gitignore`, `web/arm_server.py` 수정)이 필요하므로 팀장에게 보고.

---

### 3. 도구 루프 최대 5회 제한 검사

**결과: 해당 없음 (도구 루프가 src/core/에 없음)**

`src/core/agent.py`의 `use_tool()` 메서드는 도구를 1회 호출하는 단순 래퍼입니다.
실제 도구 자동호출 루프(Function Calling Loop)는 `web/arm_server.py`의 `_call_agent()` 함수에 구현되어 있습니다.
이 파일은 BE 팀원의 담당 영역이므로 이번 검사에서 제외했습니다.

---

### 4. async/await 오류 검사

**결과: 이상 없음 (0건)**

`await await` 패턴 — 0건
모든 async 함수의 await 사용이 올바릅니다.

주요 확인 사항:
- `agent.py`의 `handle_task()`, `execute()`, `think()` — 모두 정상
- `quality_gate.py`의 `llm_review()` — 정상 (1번만 await)
- `scheduler.py`의 `_check_and_run()` — 정상
- `workflow.py`의 `run()` — 정상
- `git_sync.py`의 `_run_git()` — `proc.communicate()` 1번만 await, 정상

---

### 5. 예산 초과 시 에이전트 중단 검사

**결과: 경고 — 예산 초과 시 에이전트를 중단하지 않음**

`budget.py`의 `BudgetManager`:
- `get_status()`: 현재 사용량 반환
- `check_warning()`: 초과/경고 메시지 반환
- **에이전트 실행을 자동으로 중단하는 코드 없음**

즉, 예산이 초과되어도 에이전트 명령은 계속 실행됩니다. `check_warning()`을 호출해서 경고 메시지만 반환할 뿐, 실제로 실행을 막지는 않습니다. 실제 차단 로직이 `web/arm_server.py`에 있는지 별도 확인이 필요합니다.

---

### 6. 추가 발견 사항

#### 6-1. YAML 파일 저장 사용 (배포 시 날아갈 위험)

다음 파일들이 YAML 파일에 데이터를 저장합니다:
- `scheduler.py` → `config/schedules.yaml`
- `workflow.py` → `config/workflows.yaml`
- `preset.py` → `config/presets.yaml`
- `quality_rules_manager.py` → `config/quality_rules.yaml`
- `budget.py` → `config/budget.yaml`

이 YAML 파일들이 SQLite DB가 아닌 파일 시스템에 저장되고, git reset --hard 배포 방식을 쓰기 때문에 배포 시 사용자 데이터가 초기화될 위험이 있습니다.

단, `arm_server.py`에서 일부 데이터를 DB로 마이그레이션하는 로직이 있을 수 있으므로 BE 팀에서 추가 확인 필요합니다.

#### 6-2. auth.py — 사용자 데이터 JSON 파일 저장

`auth.py`의 `AuthManager`:
- 사용자 목록을 JSON 파일에 저장 (`_load()`, `_save()` 메서드)
- SQLite DB 미사용

배포 시 등록된 사용자가 사라질 수 있습니다.

#### 6-3. memory.py — 캐시 방식 관찰

```python
def load(self, agent_id: str) -> list[MemoryEntry]:
    if agent_id in self._cache:
        return self._cache[agent_id]
```

서버 재시작 시 캐시가 초기화되고 파일에서 다시 읽어옵니다. 정상 동작입니다.

#### 6-4. healthcheck.py — provider_count 계산 범위 제한

```python
provider_count = sum(
    1 for name in ("openai", "anthropic")
    if model_router._providers.get(name) is not None
)
```

Google Gemini 프로바이더를 계산에서 제외하고 있습니다. 기능 오류는 아니지만 healthcheck 결과가 실제보다 낮게 표시될 수 있습니다.

---

## 수정 사항

**이번 검사에서 직접 수정한 항목: 없음**

이유:
1. 금지 모델명이 0건으로 코드 수정 불필요
2. async/await 오류 0건
3. 경고 사항들은 `src/core/` 범위를 벗어난 변경(`.gitignore`, `arm_server.py`, SQLite 마이그레이션)이 필요하여 팀장에게 보고

---

## 팀장에게 보고할 이슈 목록

| 우선순위 | 이슈 | 위험도 | 필요 작업 |
|---------|------|--------|---------|
| 높음 | 예약/워크플로우/프리셋 YAML 저장 → 배포 시 날아갈 수 있음 | 높음 | `arm_server.py`에서 SQLite 마이그레이션 확인 |
| 높음 | 에이전트 메모리(Soul) JSON 저장 → 배포 시 초기화 가능성 | 높음 | `.gitignore` 추가 또는 SQLite 마이그레이션 |
| 높음 | auth.py 사용자 데이터 JSON 저장 → 배포 시 날아갈 수 있음 | 높음 | SQLite 마이그레이션 확인 |
| 중간 | 예산 초과 시 에이전트 자동 중단 없음 | 중간 | `arm_server.py`에서 예산 체크 후 차단하는지 확인 |
| 낮음 | healthcheck에서 Gemini provider 카운트 제외 | 낮음 | 표시 수정 (cosmetic) |

---

## 결론

`src/core/` 폴더의 전수검사 완료.

- **금지 모델명: 0건 (이상 없음)**
- **async/await 오류: 0건**
- **도구 루프 최대 5회 제한: src/core/에는 해당 코드 없음 (BE 팀 확인 필요)**
- **Soul DB 저장: JSON 파일 사용 중 (배포 시 초기화 위험 — 팀장 보고)**
- **예산 초과 차단: src/core/에는 없음 (arm_server.py에서 확인 필요)**
