# CORTHEX HQ

**AI Agent Corporation** — 25명의 AI 에이전트가 회사처럼 운영되는 멀티 에이전트 자동화 시스템

> CEO(사용자)가 한국어로 명령을 내리면, 비서실장이 판단해서 적절한 부서에 배분하고,
> 전문가들이 병렬로 작업한 뒤, 결과를 종합 보고서로 합쳐서 돌려줍니다.

---

## 핵심 특징

| 특징 | 설명 |
|------|------|
| **25명 AI 에이전트** | 실제 회사 조직도처럼 비서실장 → 처장(Manager) → 전문가(Specialist) → 워커(Worker) 계층 |
| **자동 업무 배분** | "삼성전자 주가 분석해줘" → 비서실장이 CIO에게 배분 → 4명 전문가가 병렬 분석 → 종합 보고 |
| **멀티스텝 딥워크** | 전문가가 1회 답변이 아니라 계획→조사→초안→정리→보고까지 자율적으로 수행 |
| **실시간 웹 대시보드** | 에이전트 상태, 작업 진행률, 비용을 브라우저에서 실시간 모니터링 |
| **멀티 LLM** | OpenAI(GPT)와 Anthropic(Claude)을 혼합 사용, 에이전트별 모델 개별 설정 가능 |
| **백그라운드 작업** | 브라우저를 닫아도 작업 계속 진행, 결과는 마크다운 파일로 자동 저장 |

---

## 조직도

```
CEO (사용자)
│
└─ 비서실장 (Chief of Staff) ← 모든 명령의 총괄 관리자
    │
    ├─ 보고 요약 Worker
    ├─ 일정/미결 추적 Worker
    ├─ 사업부 간 정보 중계 Worker
    │
    ├─── [LEET MASTER 본부] ──────────────────
    │  │
    │  ├─ CTO 기술개발처장 (Manager)
    │  │   ├─ 프론트엔드 Specialist
    │  │   ├─ 백엔드/API Specialist
    │  │   ├─ DB/인프라 Specialist
    │  │   └─ AI 모델 Specialist
    │  │
    │  ├─ CSO 사업기획처장 (Manager)
    │  │   ├─ 시장조사 Specialist
    │  │   ├─ 사업계획서 Specialist
    │  │   └─ 재무모델링 Specialist
    │  │
    │  ├─ CLO 법무·IP처장 (Manager)
    │  │   ├─ 저작권 Specialist
    │  │   └─ 특허·약관 Specialist
    │  │
    │  └─ CMO 마케팅·고객처장 (Manager)
    │      ├─ 설문·리서치 Specialist
    │      ├─ 콘텐츠 Specialist
    │      └─ 커뮤니티 Specialist
    │
    └─── [투자분석 본부] ─────────────────────
       │
       └─ CIO 투자분석처장 (Manager)
           ├─ 시황분석 Specialist  ──┐
           ├─ 종목분석 Specialist  ──┼── 병렬 실행
           ├─ 기술적분석 Specialist ─┘
           └─ 리스크관리 Specialist ← 순차 실행

[AgentTool Pool] 변리사 / 세무사 / 디자이너 / 번역가 / 웹검색
```

---

## 빠른 시작

### 필요한 것

- **Python 3.11 이상**
- **API 키**: OpenAI 또는 Anthropic (둘 중 하나 이상)

### 설치

```bash
# 1. 저장소 클론
git clone https://github.com/kodonghui/CORTHEX_HQ.git
cd CORTHEX_HQ

# 2. 환경 설정
cp .env.example .env
# .env 파일을 열어 API 키 입력:
#   OPENAI_API_KEY=sk-...
#   ANTHROPIC_API_KEY=sk-ant-...

# 3. 의존성 설치 (자동 가상환경)
# Linux/Mac:
bash setup.sh

# Windows:
setup.bat
```

### 실행

```bash
# 웹 대시보드 (권장)
python run_web.py
# → 브라우저에서 http://localhost:8000 자동 오픈

# Windows 원클릭 실행
run.bat

# CLI 모드 (터미널)
python main.py
```

---

## 사용법

### 웹 대시보드 (CEO 관제실)

브라우저에서 `http://localhost:8000` 접속 후 한국어로 명령을 입력합니다.

**명령 예시:**
```
LEET MASTER 서비스의 기술 스택을 제안해줘
삼성전자 주가를 분석해줘
서비스 이용약관 초안을 만들어줘
인스타그램 마케팅 전략을 수립해줘
```

**작업 깊이 선택** (입력창 옆 드롭다운):

| 옵션 | 단계 수 | 용도 |
|------|---------|------|
| 빠른 | 1단계 | 간단한 질문, 빠른 답변 |
| 보통 | 3단계 | 일반 업무 (기본값) |
| 심화 | 5단계 | 전략 수립, 상세 보고서 |

### 4개 탭

| 탭 | 기능 |
|----|------|
| **명령** | 명령 입력 + 실시간 활동 로그 + 에이전트 상태 트리 + 비용 모니터 |
| **사무실** | 25명 에이전트 카드 그리드 + 클릭해서 상세 보기 + Soul(시스템 프롬프트) 편집 + 모델 변경 |
| **지식관리** | knowledge/ 폴더의 마크다운 지식파일 생성/수정/삭제 (에이전트 프롬프트에 자동 주입) |
| **작업내역** | 과거 작업 결과 열람 + 마크다운 렌더링 + 파일 다운로드 |

### CLI 모드

```
CEO> 삼성전자 주가를 분석해줘
CEO> 조직도
CEO> 비용
CEO> 종료
```

---

## 명령 처리 흐름

사용자가 명령을 입력하면 내부에서 이런 일이 벌어집니다:

```
1. CEO: "인스타 마케팅 전략 만들어줘" (심화 모드)
         │
2. 비서실장: "이건 마케팅이니 CMO에게 보내자" (LLM 판단)
         │
3. CMO(처장): "3명 전문가에게 나눠서 시키자" (업무 분해 → 병렬 배분)
         │
         ├─ 설문/리서치 전문가 (5단계 자율 딥워크)
         │   ├─ 1단계: 타겟 고객 분석 계획
         │   ├─ 2단계: 경쟁사 벤치마킹
         │   ├─ 3단계: 인사이트 정리
         │   └─ 4단계: 최종 리서치 보고서
         │
         ├─ 콘텐츠 전문가 (5단계 자율 딥워크)   ← 병렬 실행
         │   └─ ...
         │
         └─ 커뮤니티 전문가 (5단계 자율 딥워크)
             └─ ...
         │
4. CMO: 3명 결과 취합 → 종합 보고서 작성
         │
5. 비서실장: CEO에게 최종 보고
         │
6. 결과가 output/ 폴더에 마크다운으로 자동 저장
```

---

## 프로젝트 구조

```
CORTHEX_HQ/
│
├── main.py                 # CLI 진입점
├── run_web.py              # 웹 서버 진입점
├── run.bat                 # Windows 원클릭 실행
├── setup.sh / setup.bat    # 설치 스크립트
├── pyproject.toml          # Python 패키지 설정
├── .env.example            # API 키 템플릿
│
├── config/                 # YAML 설정 (비개발자도 수정 가능)
│   ├── agents.yaml         # 25개 에이전트 정의 (역할, 모델, 프롬프트, 계층)
│   ├── models.yaml         # AI 모델 목록 및 가격
│   └── tools.yaml          # 도구(변리사/세무사 등) 설정
│
├── src/
│   ├── core/               # 코어 프레임워크
│   │   ├── orchestrator.py # CEO 명령 → 비서실장 라우팅
│   │   ├── agent.py        # BaseAgent, ManagerAgent, SpecialistAgent, WorkerAgent
│   │   ├── registry.py     # 에이전트 팩토리 (YAML → 인스턴스 생성)
│   │   ├── context.py      # 공유 상태 (대화 기록, 게시판, 상태 콜백)
│   │   ├── message.py      # 메시지 타입 (TaskRequest, TaskResult, StatusUpdate 등)
│   │   ├── knowledge.py    # 지식파일 로더 (마크다운 → 프롬프트 주입)
│   │   ├── task_store.py   # 백그라운드 작업 저장소
│   │   └── errors.py       # 커스텀 예외
│   │
│   ├── llm/                # LLM 프로바이더
│   │   ├── router.py       # 모델명으로 OpenAI/Anthropic 자동 분기
│   │   ├── openai_provider.py
│   │   ├── anthropic_provider.py
│   │   ├── cost_tracker.py # 비용 추적 (모델별/에이전트별/프로바이더별)
│   │   └── base.py         # LLMProvider 추상 클래스
│   │
│   ├── divisions/          # 부서별 에이전트 모듈
│   │   ├── secretary/      # 비서실 (비서실장 + 워커 3명)
│   │   ├── leet_master/    # LEET Master 본부 (CTO/CSO/CLO/CMO + 전문가 12명)
│   │   └── finance/        # 투자분석 본부 (CIO + 전문가 4명)
│   │
│   ├── tools/              # 도구 풀 (변리사, 세무사, 디자이너, 번역가, 웹검색)
│   └── cli/                # Rich 터미널 CLI
│
├── web/                    # 웹 대시보드
│   ├── app.py              # FastAPI 서버 (REST API + WebSocket)
│   ├── ws_manager.py       # WebSocket 연결 관리 + 브로드캐스트
│   ├── templates/
│   │   └── index.html      # CEO 관제실 SPA (Tailwind + Alpine.js)
│   └── static/             # 정적 파일
│
├── knowledge/              # 에이전트 지식 파일 (.md)
│   ├── shared/             # 전체 에이전트 공유 지식
│   ├── leet_master/        # LEET Master 본부 전용
│   └── finance/            # 투자분석 본부 전용
│
├── output/                 # 작업 결과 자동 저장 (마크다운)
└── docs/                   # 프로젝트 문서
    ├── CHANGELOG.md        # 버전별 변경 이력
    └── IMPLEMENTATION_PLAN.md
```

---

## 기술 스택

| 구성 요소 | 기술 | 역할 |
|-----------|------|------|
| **언어** | Python 3.11+ | 비동기 타입 힌트 활용 |
| **웹 프레임워크** | FastAPI | REST API + WebSocket 서버 |
| **실시간 통신** | WebSocket | 에이전트 상태/진행률 실시간 푸시 |
| **프론트엔드** | Tailwind CSS + Alpine.js | 반응형 SPA (빌드 도구 불필요) |
| **CLI** | Rich | 터미널 마크다운 렌더링 + 테이블 |
| **비동기 실행** | asyncio | 에이전트 병렬 작업 (asyncio.gather) |
| **LLM** | OpenAI + Anthropic SDK | 멀티 프로바이더 지원 |
| **설정** | YAML + Pydantic v2 | 비개발자도 수정 가능한 에이전트 설정 |
| **서버** | Uvicorn | ASGI 서버 |

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | CEO 관제실 대시보드 |
| GET | `/api/health` | 시스템 상태 확인 |
| GET | `/api/agents` | 전체 에이전트 목록 + 계층 |
| GET | `/api/agents/{id}` | 에이전트 상세 정보 |
| PUT | `/api/agents/{id}/soul` | 에이전트 시스템 프롬프트 수정 |
| PUT | `/api/agents/{id}/model` | 에이전트 모델 변경 |
| GET | `/api/cost` | 비용 요약 (모델별/에이전트별/프로바이더별) |
| GET | `/api/models` | 사용 가능한 AI 모델 목록 |
| GET | `/api/tools` | 사용 가능한 도구 목록 |
| GET | `/api/tasks` | 전체 작업 내역 |
| GET | `/api/tasks/{id}` | 작업 상세 + 결과 |
| GET | `/api/knowledge` | 지식파일 목록 |
| POST | `/api/knowledge` | 지식파일 생성/수정 |
| DELETE | `/api/knowledge/{folder}/{filename}` | 지식파일 삭제 |
| WS | `/ws` | 실시간 명령 실행 + 상태 스트리밍 |

---

## 환경 변수

```bash
# 필수 (둘 중 하나 이상)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# 선택 (기본값 있음)
DEFAULT_MODEL=claude-sonnet-4-5-20250929
MANAGER_MODEL=claude-sonnet-4-5-20250929
SPECIALIST_MODEL=claude-haiku-4-5-20251001
WORKER_MODEL=claude-haiku-4-5-20251001
LOG_LEVEL=INFO
```

---

## 라이선스

이 프로젝트는 개인 프로젝트입니다.
