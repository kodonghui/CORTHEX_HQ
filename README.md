# CORTHEX HQ

**AI Agent Corporation** - 25명의 AI 에이전트가 운영하는 자동화 회사

## 조직도

```
CEO (동희 님)
│
├─ 비서실 (Chief of Staff)
│  ├─ 보고 요약 Worker
│  ├─ 일정/미결 추적 Worker
│  └─ 사업부 간 정보 중계 Worker
│
├─── [사업부 1] LEET MASTER 본부 ──────
│  ├─ 기술개발처 (CTO)
│  │  ├─ 프론트엔드 Specialist
│  │  ├─ 백엔드/API Specialist
│  │  ├─ DB/인프라 Specialist
│  │  └─ AI 모델 Specialist
│  ├─ 사업기획처 (CSO)
│  │  ├─ 시장조사 / 사업계획서 / 재무모델링
│  ├─ 법무·IP처 (CLO)
│  │  ├─ 저작권 / 특허·약관
│  └─ 마케팅·고객처 (CMO)
│     ├─ 설문·리서치 / 콘텐츠 / 커뮤니티
│
├─── [사업부 2] 금융분석 본부 ──────────
│  └─ 투자분석처 (CIO)
│     ├─ 시황분석 ──┐
│     ├─ 종목분석 ──┼── 병렬 실행
│     ├─ 기술적분석 ┘
│     └─ 리스크관리 ← 순차 실행
│
└─ [AgentTool Pool]
   변리사 / 세무사 / 디자이너 / 번역가 / 웹검색
```

## 빠른 시작

```bash
# 1. 환경 설정
cp .env.example .env
# .env 파일에 API 키 입력 (OPENAI_API_KEY, ANTHROPIC_API_KEY)

# 2. 의존성 설치
pip install -e .

# 3. 실행
python main.py
```

## 사용법

실행 후 한국어로 자유롭게 명령을 입력하세요:

```
CEO> LEET MASTER 서비스의 기술 스택을 제안해줘
CEO> 삼성전자 주가를 분석해줘
CEO> 서비스 이용약관 초안을 만들어줘
CEO> 마케팅 콘텐츠 전략을 수립해줘
```

## 기술 스택

- **Python 3.11+** - 코어 언어
- **OpenAI + Anthropic** - 혼합 AI 모델 (비용/성능 최적화)
- **Pydantic v2** - 메시지 및 설정 검증
- **asyncio** - 비동기 병렬 실행
- **Rich** - 터미널 UI
- **YAML** - 에이전트 설정 (비개발자도 수정 가능)

## 프로젝트 구조

```
CORTHEX_HQ/
├── main.py              # 진입점
├── config/
│   ├── agents.yaml      # 25개 에이전트 설정
│   ├── tools.yaml       # 도구 설정
│   └── models.yaml      # AI 모델 설정
└── src/
    ├── core/            # 코어 프레임워크
    │   ├── agent.py     # BaseAgent, Manager, Specialist, Worker
    │   ├── message.py   # 메시지 시스템
    │   ├── orchestrator.py  # CEO 명령 라우터
    │   └── registry.py  # 에이전트 레지스트리
    ├── llm/             # LLM 프로바이더
    │   ├── openai_provider.py
    │   ├── anthropic_provider.py
    │   └── router.py    # 모델 라우터
    ├── divisions/       # 사업부 에이전트
    │   ├── secretary/   # 비서실
    │   ├── leet_master/ # LEET MASTER 본부
    │   └── finance/     # 금융분석 본부
    ├── tools/           # 도구 풀
    └── cli/             # CLI 인터페이스
```
