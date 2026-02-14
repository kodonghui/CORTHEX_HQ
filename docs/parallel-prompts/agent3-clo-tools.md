# 에이전트 3번 프롬프트: CLO 법무IP처 + CSO 잔여 도구 5개

## 너의 역할
너는 CORTHEX HQ 프로젝트의 **CLO 법무IP처 + CSO 사업기획처** 전문 도구를 만드는 개발자야.
5개의 파이썬 도구를 만들어야 해. 전부 `src/tools/` 폴더에 파이썬 파일로 만들고,
`src/tools/pool.py`에 등록하고, `config/tools.yaml`에 설정을 추가해야 해.

## 작업할 저장소
- 저장소: https://github.com/kodonghui/CORTHEX_HQ
- 브랜치: `claude/corthex-improvements-kE0ii` (이 브랜치에서 작업)

## 기존 코드 패턴 (반드시 이 패턴을 따를 것)

### 1) 모든 도구의 부모 클래스 (`src/tools/base.py`)
```python
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.llm.router import ModelRouter

class ToolConfig(BaseModel):
    tool_id: str
    name: str
    name_ko: str
    description: str
    model_name: str = "gpt-4o-mini"

class BaseTool(ABC):
    def __init__(self, config: ToolConfig, model_router: ModelRouter) -> None:
        self.config = config
        self.model_router = model_router

    @property
    def tool_id(self) -> str:
        return self.config.tool_id

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        ...

    async def _llm_call(self, system_prompt: str, user_prompt: str) -> str:
        response = await self.model_router.complete(
            model_name=self.config.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return response.content
```

### 2) 도구 파일 작성 규칙
- `from src.tools.base import BaseTool` 으로 임포트
- `class XxxTool(BaseTool):` 으로 클래스 생성
- `async def execute(self, **kwargs: Any) -> str:` 메서드 구현
- action 파라미터로 기능 분기 (`kwargs.get("action", "기본값")`)
- API 키는 `os.getenv("KEY_NAME", "")` 으로 환경변수에서 가져옴
- httpx.AsyncClient() 으로 외부 API 호출
- 결과를 `self._llm_call()` 로 LLM 분석 추가
- 로거: `logger = logging.getLogger("corthex.tools.도구이름")`

### 3) 등록 방법 (pool.py, tools.yaml, agents.yaml)
- `src/tools/pool.py`의 `build_from_config`에: import + tool_classes 딕셔너리에 추가
- `config/tools.yaml`에 tool 정의 추가
- `config/agents.yaml`에서 해당 에이전트의 `allowed_tools`에 추가

### 4) 기존 CLO 관련 도구 참고
이미 존재하는 도구들 (재사용/연동 가능):
- `kipris.py`: KIPRIS 특허/상표 검색 (KIPRIS API 키 사용)
- `law_search.py`: 국가법령정보센터 법령/판례 검색 (법제처 API)
- `patent_attorney.py`: 특허 분석 LLM 도구

---

## 만들어야 할 도구 5개

### 도구 1: 크몽/탈잉 시장 조사기 (`src/tools/platform_market_scraper.py`)
- **tool_id**: `platform_market_scraper`
- **클래스명**: `PlatformMarketScraperTool`
- **소속**: CSO 사업기획처
- **하는 일**: 크몽, 탈잉, 클래스101 등에서 특정 분야 서비스의 가격/리뷰/판매량 수집
- **action 종류**:
  - `action="search"`: 플랫폼에서 서비스 검색
    - `platform`: "kmong", "taling", "class101", "all" (기본: "all")
    - `query`: 검색 키워드 (예: "LEET", "법학", "로스쿨")
    - `count`: 결과 수 (기본: 20)
  - `action="analyze"`: 수집 결과 시장 분석
    - `query`: 분석할 키워드
  - `action="price_range"`: 가격대 분포 분석
    - `query`: 키워드
- **구현 상세**:
  - 크몽: `https://kmong.com/search?q={query}` httpx + BeautifulSoup으로 크롤링
    - 수집: 서비스명, 가격, 별점, 리뷰수, 판매수
  - 탈잉: `https://taling.me/search/?query={query}` 크롤링
    - 수집: 수업명, 가격, 별점, 수강생수
  - 클래스101: `https://class101.net/search?query={query}` 크롤링
    - 수집: 클래스명, 가격, 별점, 수강생수
  - 크롤링 시 User-Agent 헤더 필수, 요청 간 1~2초 딜레이
  - `price_range`: 가격대 구간별 분포 (5만원 이하, 5~10만원, 10~30만원, 30만원 이상)
  - 결과를 `_llm_call()`로 "시장 가격 포지셔닝, 경쟁 강도, 차별화 기회" 분석
- **환경변수**: 없음
- **의존 라이브러리**: httpx, beautifulsoup4
- **agents.yaml 배정**: `cso_manager`, `market_research_specialist`

### 도구 2: 판례 트렌드 분석기 (`src/tools/precedent_analyzer.py`)
- **tool_id**: `precedent_analyzer`
- **클래스명**: `PrecedentAnalyzerTool`
- **소속**: CLO 법무IP처
- **하는 일**: 특정 법률 분야의 판례를 대량 수집해서 판결 경향 분석
- **action 종류**:
  - `action="analyze"`: 판례 트렌드 분석
    - `query`: 검색 키워드 (예: "저작권 침해", "개인정보 유출")
    - `years`: 분석 기간 (기본: 5년)
    - `count`: 분석할 판례 수 (기본: 50)
  - `action="summary"`: 특정 판례 요약
    - `case_id`: 판례 번호
  - `action="risk"`: 특정 사업/행위의 법적 리스크 분석
    - `topic`: 분석 주제 (예: "AI 생성 콘텐츠 저작권")
- **구현 상세**:
  - 기존 `law_search.py`의 법제처 API 로직을 활용/연동
    - 법제처 판례 검색 API: `http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=prec&query={query}&type=JSON`
  - 판례 대량 수집 후 분석:
    - 연도별 판례 건수 추이 (증가/감소 트렌드)
    - 원고 승소율 vs 피고 승소율
    - 평균 배상금액 (금액이 언급된 경우)
    - 자주 인용되는 법 조문 (예: "저작권법 제136조")
    - 핵심 판시사항 키워드 빈도
  - `risk` action: 관련 판례 기반으로 법적 리스크 수준 평가 (상/중/하)
  - 결과를 `_llm_call()`로 "법적 트렌드 요약, 사업 리스크, 대응 전략" 분석
  - **주의**: "이 분석은 참고용이며, 실제 법률 문제는 변호사와 상담하세요" 면책 문구 항상 포함
- **환경변수**: 없음 (법제처 API는 무료, 키 불필요)
- **의존 라이브러리**: httpx
- **agents.yaml 배정**: `clo_manager`, `copyright_specialist`, `patent_specialist`

### 도구 3: 상표 유사도 검사기 (`src/tools/trademark_similarity.py`)
- **tool_id**: `trademark_similarity`
- **클래스명**: `TrademarkSimilarityTool`
- **소속**: CLO 법무IP처
- **하는 일**: 브랜드명/상표명이 기존 등록 상표와 얼마나 유사한지 자동 판별
- **action 종류**:
  - `action="check"`: 상표 유사도 검사
    - `name`: 검사할 상표명 (예: "CORTHEX")
    - `nice_class`: 니스 분류 (상표 카테고리, 예: "41" = 교육/오락, 선택사항)
  - `action="batch"`: 여러 후보 상표명 일괄 검사
    - `names`: 쉼표 구분 상표명 (예: "CORTHEX,코텍스,CORTEX HQ")
- **구현 상세**:
  - 기존 `kipris.py`의 KIPRIS API를 활용하여 유사 상표 검색
  - 유사도 알고리즘 3가지를 직접 구현:
    1. **글자 유사도 (편집 거리)**: Levenshtein distance
       ```python
       def levenshtein_distance(s1: str, s2: str) -> int:
           # DP(동적프로그래밍)로 편집 거리 계산
           # 유사도 = 1 - (distance / max(len(s1), len(s2)))
       ```
    2. **발음 유사도 (한글 자모 분리)**:
       ```python
       # "코텍스" → "ㅋㅗㅌㅔㄱㅅㅡ" 로 분리 후 비교
       # 한글 유니코드 분해: (char - 0xAC00) → 초성/중성/종성
       CHOSUNG = ['ㄱ','ㄲ','ㄴ','ㄷ','ㄸ','ㄹ','ㅁ','ㅂ','ㅃ','ㅅ','ㅆ','ㅇ','ㅈ','ㅉ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ']
       JUNGSUNG = ['ㅏ','ㅐ','ㅑ','ㅒ','ㅓ','ㅔ','ㅕ','ㅖ','ㅗ','ㅘ','ㅙ','ㅚ','ㅛ','ㅜ','ㅝ','ㅞ','ㅟ','ㅠ','ㅡ','ㅢ','ㅣ']
       JONGSUNG = ['','ㄱ','ㄲ','ㄳ','ㄴ','ㄵ','ㄶ','ㄷ','ㄹ','ㄺ','ㄻ','ㄼ','ㄽ','ㄾ','ㄿ','ㅀ','ㅁ','ㅂ','ㅄ','ㅅ','ㅆ','ㅇ','ㅈ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ']
       ```
    3. **외관 유사도**: 영문 대소문자 무시 비교 + 한글↔영문 발음 변환 비교
  - 종합 유사도 점수: (글자 40% + 발음 40% + 외관 20%) → 0~100점
  - 위험 수준 판정:
    - 80점 이상: "위험 — 등록 거절 가능성 매우 높음"
    - 60~80점: "주의 — 유사 상표 존재, 전문가 검토 필요"
    - 40~60점: "보통 — 일부 유사성 있으나 구분 가능"
    - 40점 미만: "안전 — 유사 상표 없음"
  - 결과를 `_llm_call()`로 "상표 등록 가능성 판단 + 대안 브랜드명 제안" 분석
- **환경변수**: `KIPRIS_API_KEY` (기존과 동일)
- **의존 라이브러리**: httpx
- **agents.yaml 배정**: `clo_manager`, `copyright_specialist`, `patent_specialist`

### 도구 4: 계약서 자동 검토기 (`src/tools/contract_reviewer.py`)
- **tool_id**: `contract_reviewer`
- **클래스명**: `ContractReviewerTool`
- **소속**: CLO 법무IP처
- **하는 일**: 계약서 텍스트에서 위험/불리 조항을 자동 탐지
- **action 종류**:
  - `action="review"`: 계약서 검토
    - `text`: 계약서 전문 텍스트 (직접 입력)
    - `file_path`: 또는 파일 경로 (.txt, .md)
  - `action="checklist"`: 계약서 유형별 필수 조항 체크리스트
    - `contract_type`: "서비스이용약관", "업무위탁", "투자계약", "고용계약", "NDA"
  - `action="compare"`: 두 계약서 비교
    - `text1`: 계약서 1
    - `text2`: 계약서 2
- **구현 상세**:
  - 위험 조항 패턴 데이터베이스 (파이썬 딕셔너리로 내장):
    ```python
    RISK_PATTERNS = {
        "높음": [
            {"pattern": r"일방적[으로]?\s*해지", "desc": "상대방만 일방적으로 해지 가능"},
            {"pattern": r"손해배상.{0,20}무제한", "desc": "손해배상 한도 없음"},
            {"pattern": r"위약금.{0,10}\d{2,}%", "desc": "과도한 위약금"},
            {"pattern": r"지적재산권.{0,30}양도", "desc": "IP 권리 양도 조항"},
            {"pattern": r"경업금지.{0,20}\d+년", "desc": "경업금지 기간 확인 필요"},
            {"pattern": r"자동\s*갱신", "desc": "자동 갱신 조항 — 해지 절차 확인 필요"},
        ],
        "중간": [
            {"pattern": r"재판관할.{0,20}(서울|수원|부산)", "desc": "재판관할 지역 확인"},
            {"pattern": r"준거법.{0,20}(외국|미국|중국)", "desc": "외국법 준거 — 분쟁 시 불리"},
            {"pattern": r"비밀유지.{0,20}\d+년", "desc": "비밀유지 기간 확인"},
        ],
        "참고": [
            {"pattern": r"제\d+조", "desc": "조문 번호 확인"},
            {"pattern": r"갑.{0,5}을", "desc": "갑을 관계 확인"},
        ]
    }
    ```
  - 필수 조항 체크리스트 (유형별):
    ```python
    REQUIRED_CLAUSES = {
        "서비스이용약관": ["개인정보처리", "환불규정", "면책조항", "분쟁해결", "서비스변경/중단"],
        "업무위탁": ["업무범위", "대가지급", "비밀유지", "지적재산권", "손해배상", "계약해지"],
        ...
    }
    ```
  - 정규식(re 모듈)으로 패턴 매칭 → 위험도별 분류
  - 빠진 필수 조항도 체크 (텍스트에 해당 키워드가 없으면 "누락")
  - 결과를 `_llm_call()`로 "종합 리스크 평가 + 수정 권고사항" 분석
  - **주의**: "이 검토는 참고용이며, 중요한 계약은 변호사 검토를 받으세요" 면책 문구 포함
- **환경변수**: 없음
- **의존 라이브러리**: 없음 (순수 파이썬 + re 모듈)
- **agents.yaml 배정**: `clo_manager`, `copyright_specialist`, `patent_specialist`

### 도구 5: 법령 변경 알리미 (`src/tools/law_change_monitor.py`)
- **tool_id**: `law_change_monitor`
- **클래스명**: `LawChangeMonitorTool`
- **소속**: CLO 법무IP처
- **하는 일**: 관련 법령의 개정/신설/폐지를 자동 감지
- **action 종류**:
  - `action="watch"`: 감시 법령 등록
    - `law_name`: 법령명 (예: "저작권법", "개인정보보호법")
  - `action="unwatch"`: 감시 해제
  - `action="check"`: 등록된 법령의 변경사항 확인
  - `action="list"`: 감시 중인 법령 목록
  - `action="recent"`: 최근 개정된 주요 법령 목록
    - `days`: 최근 N일 (기본: 30)
    - `category`: "교육", "정보통신", "금융", "전체"
- **구현 상세**:
  - 감시 목록: `data/law_watchlist.json`
    - 형식: `[{"law_name": "저작권법", "last_revision": "2025-01-15", "law_id": "..."}]`
  - 법제처 API 활용 (기존 law_search.py와 동일 엔드포인트):
    - `http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=law&query={법령명}&type=JSON`
  - `check` 실행 시:
    - 각 감시 법령의 현재 시행일/개정일을 API로 조회
    - 저장된 `last_revision`과 비교 → 다르면 "개정 감지"
    - 변경된 조문 목록 추출 (가능한 경우)
  - `recent` action: 최근 N일간 관보에 게재된 법령 변경 목록
  - 결과를 `_llm_call()`로 "이 법령 변경이 우리 사업에 미치는 영향" 분석
- **환경변수**: 없음 (법제처 API 무료)
- **의존 라이브러리**: httpx
- **agents.yaml 배정**: `clo_manager`, `copyright_specialist`, `patent_specialist`

---

## 최종 체크리스트

모든 도구 작성 후 반드시 확인:

1. [ ] `src/tools/platform_market_scraper.py` 생성 완료
2. [ ] `src/tools/precedent_analyzer.py` 생성 완료
3. [ ] `src/tools/trademark_similarity.py` 생성 완료
4. [ ] `src/tools/contract_reviewer.py` 생성 완료
5. [ ] `src/tools/law_change_monitor.py` 생성 완료
6. [ ] `src/tools/pool.py`에 5개 도구 전부 import + tool_classes에 등록
7. [ ] `config/tools.yaml`에 5개 도구 설정 추가
8. [ ] `config/agents.yaml`에서 관련 에이전트의 `allowed_tools`에 추가:
   - platform_market_scraper → `cso_manager`, `market_research_specialist`
   - precedent_analyzer, trademark_similarity, contract_reviewer, law_change_monitor → `clo_manager`, `copyright_specialist`, `patent_specialist`
9. [ ] 모든 파일에 한국어 docstring 포함
10. [ ] 상표 유사도 검사기: 한글 자모 분리 로직 직접 구현 (외부 라이브러리 없이)
11. [ ] 계약서 검토기: 위험 패턴 최소 15개 이상 포함
12. [ ] 법률 관련 도구에 면책 문구 포함
13. [ ] 커밋 메시지: `feat: CLO+CSO 신규 도구 5개 추가 (플랫폼시장조사/판례분석/상표유사도/계약서검토/법령알리미) [완료]`
14. [ ] 브랜치 `claude/corthex-improvements-kE0ii`에 push
