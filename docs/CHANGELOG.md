# CORTHEX HQ 변경 이력 (Changelog)

> 이 문서는 CORTHEX HQ의 버전별 변경 사항을 기록합니다.
> 노션에 붙여넣어 팀 기록으로 활용하세요.

---

## v0.2.0 (예정) - 비서실장 오케스트레이터 통합 + 비용 추적 고도화

> 상태: **구현 대기 (CEO 승인 필요)**

### 무엇이 바뀌나요?

한 줄 요약: **불필요한 본부장 레이어를 제거하고, 비서실장이 CEO의 모든 명령을 직접 관리하도록 변경합니다.**

### 변경 사항

#### 조직 구조 개편

| 구분 | v0.1.0 (기존) | v0.2.0 (변경 후) |
|------|---------------|------------------|
| 명령 라우팅 | 숨겨진 Orchestrator가 LLM으로 분류 | **비서실장**이 직접 분류 및 배분 |
| LEET MASTER 본부장 | 존재 (중간 전달 역할) | **삭제** - 처장들이 비서실장 직속 |
| 금융분석 본부장 | 존재 (중간 전달 역할) | **삭제** - CIO가 비서실장 직속 |
| 비서실장 역할 | fallback 용도 | **총괄 오케스트레이터** |

**Before (4단계):**
```
CEO → Orchestrator(LLM 분류) → 본부장(LLM 분류) → 처장(LLM 분류) → Specialist
```

**After (3단계):**
```
CEO → 비서실장(LLM 분류) → 처장(LLM 분류) → Specialist
```

#### 비용 추적 고도화

| 구분 | v0.1.0 (기존) | v0.2.0 (변경 후) |
|------|---------------|------------------|
| 비용 기록 | 모델별만 추적 | 모델별 + **에이전트별** + **프로바이더별** 추적 |
| CostRecord | model, provider, tokens, cost | + **agent_id** 필드 추가 |
| API 응답 | `/api/cost`에 `by_model`만 | + `by_agent` + `by_provider` 추가 |

#### UI 변경

| 구분 | v0.1.0 (기존) | v0.2.0 (변경 후) |
|------|---------------|------------------|
| 사이드바 조직도 | 본부 → 처 → Specialist 3단계 | 비서실장 → 처 → Specialist 2단계 |
| 에이전트 대기 색상 | 회색 (gray-600) | **앰버** (amber-500) |
| 에이전트 작업중 색상 | 노랑 깜빡 (yellow pulse) | **초록 깜빡** (green pulse) |
| 에이전트 비활성 색상 | 회색 (gray-600) | 회색 유지 (gray-600) |

#### 수정된 파일 (9개)

```
config/agents.yaml           - 본부장 삭제, 비서실장 확장
src/core/orchestrator.py      - 분류 LLM 호출 제거
src/core/registry.py          - list_division_heads() 수정
src/core/agent.py             - think()에 agent_id 전달
src/llm/router.py             - complete()에 agent_id 파라미터 추가
src/llm/cost_tracker.py       - CostRecord + 분석 메서드 추가
web/templates/index.html      - 사이드바/색상/이름 전면 수정
web/app.py                    - /api/cost 응답 확장
src/cli/app.py                - CLI 조직도 업데이트
```

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
