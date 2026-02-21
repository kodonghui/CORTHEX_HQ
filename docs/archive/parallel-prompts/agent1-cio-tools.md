# 에이전트 1번 프롬프트: CIO 투자분석처 도구 5개

## 너의 역할
너는 CORTHEX HQ 프로젝트의 **CIO 투자분석처 전문 도구**를 만드는 개발자야.
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

### 2) 기존 도구 예시 (dart_api.py 패턴 참고)
- `from src.tools.base import BaseTool` 으로 임포트
- `class XxxTool(BaseTool):` 으로 클래스 생성
- `async def execute(self, **kwargs: Any) -> str:` 메서드 구현
- action 파라미터로 기능 분기 (`kwargs.get("action", "기본값")`)
- API 키는 `os.getenv("KEY_NAME", "")` 으로 환경변수에서 가져옴
- API 키 없을 때 안내 메시지 반환
- httpx.AsyncClient() 으로 외부 API 호출
- 결과를 `self._llm_call()` 로 LLM 분석 추가
- 로거: `logger = logging.getLogger("corthex.tools.도구이름")`

### 3) pool.py 등록 방법
`src/tools/pool.py`의 `build_from_config` 메서드에:
1. 상단에 `from src.tools.파일명 import 클래스명` 추가
2. `tool_classes` 딕셔너리에 `"tool_id": 클래스명` 추가

### 4) tools.yaml 등록 방법
`config/tools.yaml`에 아래 형식으로 추가:
```yaml
  - tool_id: "도구_id"
    name: "English Name"
    name_ko: "한국어 이름"
    description: "도구 설명"
    model_name: "gpt-5-mini"
```

### 5) agents.yaml 등록 방법
`config/agents.yaml`에서 해당 부서 에이전트의 `allowed_tools`에 tool_id 추가.
CIO 소속 도구들은 `cio_manager`와 관련 specialist들에게 배정.

---

## 만들어야 할 도구 5개

### 도구 1: 공시 알리미 (`src/tools/dart_monitor.py`)
- **tool_id**: `dart_monitor`
- **클래스명**: `DartMonitorTool`
- **하는 일**: DART에서 특정 기업의 새 공시를 자동 감지
- **action 종류**:
  - `action="watch"`: 관심 기업 등록 (company 파라미터)
  - `action="unwatch"`: 관심 기업 해제
  - `action="check"`: 등록된 모든 관심 기업의 새 공시 확인
  - `action="list"`: 현재 감시 중인 기업 목록
- **구현 상세**:
  - 관심 기업 목록은 `data/dart_watchlist.json`에 JSON으로 저장
  - `check` 실행 시: DART API(`https://opendart.fss.or.kr/api/list.json`)로 각 기업의 최신 공시 조회
  - 마지막 확인 시각을 `data/dart_last_check.json`에 저장 → 새 공시만 필터링
  - 결과를 `_llm_call()`로 "이 공시가 주가에 미치는 영향" 분석 추가
  - 기업명→corp_code 변환은 기존 `DartApiTool._resolve_corp_code()` 로직 재사용 (또는 `data/dart_corp_codes.json` 캐시 활용)
- **환경변수**: `DART_API_KEY` (기존과 동일)
- **의존 라이브러리**: httpx (이미 설치됨)
- **agents.yaml 배정**: `cio_manager`, `stock_analysis_specialist`

### 도구 2: 종목 스크리너 (`src/tools/stock_screener.py`)
- **tool_id**: `stock_screener`
- **클래스명**: `StockScreenerTool`
- **하는 일**: 조건으로 전체 상장사를 자동 필터링
- **action 종류**:
  - `action="screen"`: 조건 필터링 실행
    - `market`: "KOSPI", "KOSDAQ", "ALL" (기본: "ALL")
    - `min_market_cap`: 최소 시가총액 (억원 단위, 예: 1000)
    - `max_per`: 최대 PER (예: 10)
    - `min_per`: 최소 PER (예: 0, 적자 기업 제외)
    - `min_volume`: 최소 일평균 거래량
    - `top_n`: 결과 개수 (기본: 20)
  - `action="preset"`: 미리 정의된 전략으로 스크리닝
    - `strategy`: "value"(저평가 가치주), "growth"(성장주), "dividend"(배당주), "momentum"(모멘텀)
- **구현 상세**:
  - pykrx의 `stock.get_market_cap_by_ticker(date, market)` 로 시가총액/거래량 데이터
  - pykrx의 `stock.get_market_fundamental_by_ticker(date, market)` 로 PER/PBR/배당수익률
  - pandas DataFrame으로 조건 필터링: `df[(df['시가총액'] >= min_cap) & (df['PER'] <= max_per)]`
  - preset 전략 예시:
    - value: PER<10, PBR<1, 배당수익률>2%, 시가총액>1000억
    - growth: 영업이익 증가율>20%, 시가총액>500억
    - dividend: 배당수익률>3%, 시가총액>3000억
    - momentum: 최근 20일 수익률 상위
  - 결과를 `_llm_call()`로 "스크리닝 결과 요약 + 주목할 종목" 분석
- **환경변수**: 없음 (pykrx는 무료)
- **의존 라이브러리**: pykrx, pandas
- **agents.yaml 배정**: `cio_manager`, `stock_analysis_specialist`

### 도구 3: 포트폴리오 백테스터 (`src/tools/backtest_engine.py`)
- **tool_id**: `backtest_engine`
- **클래스명**: `BacktestEngineTool`
- **하는 일**: 투자 전략을 과거 데이터로 시뮬레이션
- **action 종류**:
  - `action="backtest"`: 백테스트 실행
    - `ticker` 또는 `name`: 종목코드/종목명
    - `strategy`: 전략명 ("golden_cross", "rsi", "macd", "buy_and_hold")
    - `start_date`: 시작일 (YYYYMMDD, 기본: 1년 전)
    - `end_date`: 종료일 (YYYYMMDD, 기본: 오늘)
    - `initial_capital`: 초기 자금 (기본: 10000000 = 1천만원)
  - `action="compare"`: 여러 전략 비교
    - `ticker`: 종목
    - `strategies`: 쉼표 구분 전략명 ("golden_cross,rsi,buy_and_hold")
- **구현 상세**:
  - pykrx로 OHLCV 데이터 로드
  - 전략 구현:
    - `golden_cross`: 5일 이동평균이 20일 이동평균을 상향돌파 시 매수, 하향돌파 시 매도
    - `rsi`: RSI<30이면 매수, RSI>70이면 매도
    - `macd`: MACD가 시그널선 상향돌파 시 매수, 하향돌파 시 매도
    - `buy_and_hold`: 처음에 사서 끝까지 보유
  - 성과 지표 계산:
    - 총 수익률, 연환산 수익률(CAGR)
    - 최대 낙폭(MDD = Maximum Drawdown)
    - 승률(이긴 거래 수 / 전체 거래 수)
    - 샤프 비율(위험 대비 수익)
  - 거래 내역 리스트: [{날짜, 매수/매도, 가격, 수량, 잔고}]
  - 결과를 `_llm_call()`로 종합 분석
- **환경변수**: 없음
- **의존 라이브러리**: pykrx, pandas, pandas-ta (기술적 지표 계산용)
- **agents.yaml 배정**: `cio_manager`, `technical_analysis_specialist`, `risk_management_specialist`

### 도구 4: 내부자 거래 추적기 (`src/tools/insider_tracker.py`)
- **tool_id**: `insider_tracker`
- **클래스명**: `InsiderTrackerTool`
- **하는 일**: 대주주/임원의 자사주 매매를 감지
- **action 종류**:
  - `action="track"`: 특정 기업의 내부자 거래 조회
    - `company`: 기업명
    - `days`: 최근 N일 (기본: 90)
  - `action="scan"`: 전체 시장에서 대규모 내부자 거래 스캔
    - `min_amount`: 최소 거래금액 (기본: 10억원)
    - `days`: 최근 N일 (기본: 30)
  - `action="alert"`: 주목할 만한 내부자 거래 패턴 분석
- **구현 상세**:
  - DART API의 `elestock.json` (임원·주요주주 소유보고) 엔드포인트 사용
    - URL: `https://opendart.fss.or.kr/api/elestock.json`
    - params: `crtfc_key`, `corp_code`
  - 또는 DART `majorstock.json` (대량보유 상황보고) 엔드포인트
  - 변동 유형 분류: 장내매수, 장내매도, 장외취득, 장외처분, 스톡옵션행사 등
  - 대량 매수/매도 패턴 감지 → "최근 3개월간 임원 5명이 연속 매수" 같은 시그널
  - 결과를 `_llm_call()`로 "이 내부자 거래의 의미" 분석
- **환경변수**: `DART_API_KEY`
- **의존 라이브러리**: httpx
- **agents.yaml 배정**: `cio_manager`, `stock_analysis_specialist`, `risk_management_specialist`

### 도구 5: 배당 캘린더 (`src/tools/dividend_calendar.py`)
- **tool_id**: `dividend_calendar`
- **클래스명**: `DividendCalendarTool`
- **하는 일**: 기업 배당 일정과 배당 이력을 정리
- **action 종류**:
  - `action="calendar"`: 월별 배당 일정표
    - `month`: 대상 월 (기본: 현재 월, 형식: "2026-03")
  - `action="history"`: 특정 기업의 과거 배당 이력
    - `company`: 기업명
    - `years`: 조회 연수 (기본: 5)
  - `action="top"`: 배당수익률 상위 종목
    - `market`: "KOSPI"/"KOSDAQ"/"ALL"
    - `top_n`: 상위 N개 (기본: 20)
- **구현 상세**:
  - pykrx의 `stock.get_market_fundamental_by_ticker(date)` 로 배당수익률(DIV) 조회
  - DART API의 배당 관련 공시 데이터 활용
  - `calendar` action: 이번 달에 배당 기준일/지급일이 있는 기업 목록
  - `history` action: 연도별 주당배당금, 배당수익률, 배당성향 추이
  - `top` action: 현재 배당수익률 높은 순으로 정렬
  - 결과를 `_llm_call()`로 배당 투자 관점에서 분석
- **환경변수**: `DART_API_KEY` (선택), 없어도 pykrx만으로 기본 기능 동작
- **의존 라이브러리**: pykrx, pandas, httpx
- **agents.yaml 배정**: `cio_manager`, `stock_analysis_specialist`

---

## 최종 체크리스트

모든 도구 작성 후 반드시 확인:

1. [ ] `src/tools/dart_monitor.py` 생성 완료
2. [ ] `src/tools/stock_screener.py` 생성 완료
3. [ ] `src/tools/backtest_engine.py` 생성 완료
4. [ ] `src/tools/insider_tracker.py` 생성 완료
5. [ ] `src/tools/dividend_calendar.py` 생성 완료
6. [ ] `src/tools/pool.py`에 5개 도구 전부 import + tool_classes에 등록
7. [ ] `config/tools.yaml`에 5개 도구 설정 추가 (`# ─── CIO 투자분석처 신규 도구 ───` 섹션)
8. [ ] `config/agents.yaml`에서 `cio_manager`, `stock_analysis_specialist`, `technical_analysis_specialist`, `risk_management_specialist`의 `allowed_tools`에 해당 도구 추가
9. [ ] 모든 파일에 한국어 docstring 포함 (사용 방법, 필요 환경변수)
10. [ ] 커밋 메시지: `feat: CIO 투자분석처 신규 도구 5개 추가 (공시알리미/종목스크리너/백테스터/내부자추적/배당캘린더) [완료]`
11. [ ] 브랜치 `claude/corthex-improvements-kE0ii`에 push
