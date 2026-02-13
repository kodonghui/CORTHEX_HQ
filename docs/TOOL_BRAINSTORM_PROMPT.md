# CORTHEX HQ 신규 도구 아이디어 브레인스토밍 프롬프트

아래 전체를 복사해서 Claude에게 붙여넣으세요.

---

## [프롬프트 시작]

당신은 AI 스타트업의 제품 기획자이자 파이썬 개발자입니다.

나는 **CORTHEX HQ**라는 AI 에이전트 시스템을 운영하고 있습니다. 이 시스템은 회사 조직도처럼 여러 AI 에이전트가 계층적으로 협업합니다. 에이전트들이 외부 작업을 수행할 때 **"도구(Tool)"**를 호출하는 구조입니다.

### 시스템 구조

```
CEO (사람인 나)
  └─ 비서실장 (명령 분류/배분)
       ├─ CTO 기술개발처장
       │    ├─ 프론트엔드 Specialist
       │    ├─ 백엔드 Specialist
       │    ├─ DB/인프라 Specialist
       │    └─ AI 모델 Specialist
       ├─ CSO 사업기획처장
       │    ├─ 시장조사 Specialist    ← daum_cafe, leet_survey, web_search 도구 사용
       │    ├─ 사업계획서 Specialist
       │    └─ 재무모델링 Specialist  ← tax_accountant 도구 사용
       ├─ CLO 법무처장
       │    ├─ 저작권 Specialist
       │    └─ 특허/약관 Specialist   ← patent_attorney 도구 사용
       ├─ CMO 마케팅처장
       │    ├─ 설문/리서치 Specialist  ← leet_survey 도구 사용
       │    ├─ 콘텐츠 Specialist      ← sns_manager, translator, designer 도구 사용
       │    └─ 커뮤니티 Specialist
       └─ CIO 투자분석처장
            ├─ 시황분석 Specialist     ← web_search 도구 사용
            ├─ 종목분석 Specialist
            ├─ 기술적분석 Specialist
            └─ 리스크관리 Specialist
```

### 현재 등록된 도구 8개

| 도구 ID | 이름 | 하는 일 | 기술 방식 |
|---------|------|---------|----------|
| `web_search` | 웹검색 | 실시간 웹 검색 | API 호출 |
| `daum_cafe` | 다음 카페 검색 | 카카오 API로 카페 글 검색 + LLM 분석 | API 호출 |
| `leet_survey` | LEET 해설 서베이 | 6개 커뮤니티에서 부정의견 수집 → LLM 분석 | **Python 스크래퍼를 subprocess로 실행** |
| `sns_manager` | SNS 매니저 | Tistory/YouTube/Instagram/LinkedIn 글 발행 | API 호출 |
| `patent_attorney` | 변리사 | 특허 출원/선행기술 조사 | LLM 역할극 |
| `tax_accountant` | 세무사 | 세무 조언/절세 전략 | LLM 역할극 |
| `designer` | 디자이너 | UI/UX 디자인 조언 | LLM 역할극 |
| `translator` | 번역가 | 한영/영한 번역 | LLM 역할극 |

### 도구가 작동하는 방식

1. **에이전트가 도구를 호출**합니다 (예: `await self.use_tool("leet_survey", action="survey", platforms="dcinside")`)
2. 도구는 `BaseTool`을 상속하는 Python 클래스입니다
3. 도구가 할 수 있는 것:
   - 외부 API 호출 (REST API, OAuth 등)
   - Python 프로그램을 subprocess로 실행하고 결과를 받아옴
   - 웹 스크래핑 (Selenium, BeautifulSoup, requests)
   - 파일 읽기/쓰기 (JSON, CSV, PDF 등)
   - LLM을 호출하여 수집한 데이터를 분석/요약
4. 도구의 결과는 텍스트로 에이전트에게 전달되고, 에이전트가 상급자에게 보고합니다

### 도구 코드 구조 (참고)

```python
# src/tools/base.py
class BaseTool(ABC):
    def __init__(self, config: ToolConfig, model_router: ModelRouter):
        self.config = config
        self.model_router = model_router

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """에이전트가 호출하면 이 메서드가 실행됨"""
        ...

    async def _llm_call(self, system_prompt: str, user_prompt: str) -> str:
        """수집한 데이터를 LLM으로 분석할 때 사용"""
        ...
```

```python
# 도구 예시: leet_survey.py (외부 Python 프로그램 실행 패턴)
class LeetSurveyTool(BaseTool):
    async def execute(self, **kwargs):
        action = kwargs.get("action")
        if action == "survey":
            # subprocess로 외부 스크래퍼 실행
            result = subprocess.run([sys.executable, "main.py", "--platforms", ...])
            # 결과 JSON 파일 읽기
            with open("output/results.json") as f:
                data = json.load(f)
            # LLM으로 분석
            analysis = await self._llm_call("분석 프롬프트", 수집_데이터)
            return analysis
```

### 우리 사업 배경

- **LEET Master**: 법학적성시험(LEET) 수험생을 위한 AI 기반 학습/해설 서비스를 만들고 있습니다
- 시장: 한국 로스쿨 입시 시장 (매년 약 1만명 응시)
- 경쟁사: 메가로스쿨, 피트, 진학사, 이그잼포유 등 기존 입시학원/출판사
- 우리의 차별점: AI로 기출문제 해설을 자동 생성하고, 학생 수준에 맞게 커스텀 설명 제공

### 요청사항

위 시스템에 **새로 추가하면 유용할 도구 아이디어**를 브레인스토밍해주세요.

다음 기준으로 평가해주세요:

1. **실용성**: 에이전트가 실제로 자주 호출할 도구인가? (일회성이 아니라 반복적으로 쓸 수 있는가?)
2. **자동화 가치**: 사람이 수동으로 하면 오래 걸리지만, 프로그램으로 자동화하면 빠른 작업인가?
3. **구현 가능성**: Python으로 만들 수 있는가? 필요한 API가 있는가? 비용은?
4. **사업 연관성**: LEET Master 사업이나 회사 운영에 도움이 되는가?

### 출력 형식

각 아이디어를 이렇게 정리해주세요:

```
## 도구 이름 (tool_id)

**한줄 설명**: ~

**사용하는 에이전트**: 어떤 Specialist가 이 도구를 호출하는가

**사용 시나리오**:
- CEO가 "~해줘"라고 말하면
- → ~ Specialist가 이 도구를 호출하여
- → 결과를 분석하여 보고

**기술 구현 방식**:
- API: 어떤 API를 사용하는가
- 또는 스크래핑: 어떤 사이트를 어떻게 스크래핑하는가
- 또는 파일처리: 어떤 파일을 어떻게 처리하는가

**필요한 것**: API 키, 로그인 정보, 외부 라이브러리 등

**구현 난이도**: 쉬움 / 보통 / 어려움

**우선순위**: 높음 / 중간 / 낮음 (왜?)
```

가능하면 **10개 이상** 아이디어를 내주세요. 카테고리별로 묶어주면 좋겠습니다:
- 시장조사/리서치 관련
- 콘텐츠 제작 관련
- 사업 운영 관련
- 기술/개발 관련
- 금융/투자 관련
- 기타 창의적인 아이디어

단, "LLM 역할극"(프롬프트만 넣어서 답변하는 방식)은 이미 충분합니다.
**실제로 외부 데이터를 가져오거나, 파일을 처리하거나, API를 호출하는** 도구 위주로 제안해주세요.

## [프롬프트 끝]
