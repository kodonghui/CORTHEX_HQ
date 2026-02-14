# 에이전트 2번 프롬프트: CSO 사업기획처 도구 6개

## 너의 역할
너는 CORTHEX HQ 프로젝트의 **CSO 사업기획처 전문 도구**를 만드는 개발자야.
6개의 파이썬 도구를 만들어야 해. 전부 `src/tools/` 폴더에 파이썬 파일로 만들고,
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
- API 키 없을 때 안내 메시지 반환
- httpx.AsyncClient() 으로 외부 API 호출
- 크롤링은 httpx + BeautifulSoup 사용 (Selenium은 최후의 수단)
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
CSO 소속 도구들은 `cso_manager`와 관련 specialist들에게 배정.

---

## 만들어야 할 도구 6개

### 도구 1: 경쟁사 웹사이트 변화 감지기 (`src/tools/competitor_monitor.py`)
- **tool_id**: `competitor_monitor`
- **클래스명**: `CompetitorMonitorTool`
- **하는 일**: 경쟁사 웹사이트의 변경사항을 자동 감지
- **action 종류**:
  - `action="add"`: 감시 대상 웹사이트 추가
    - `url`: 감시할 URL
    - `name`: 경쟁사 이름 (예: "메가로스쿨")
    - `selector`: CSS 셀렉터 (특정 영역만 감시, 선택사항. 예: ".price-section")
  - `action="remove"`: 감시 대상 해제
    - `url`: 해제할 URL
  - `action="check"`: 등록된 모든 사이트 변경사항 확인
  - `action="list"`: 현재 감시 중인 사이트 목록
  - `action="diff"`: 특정 사이트의 이전/현재 차이점 상세 보기
    - `url`: 대상 URL
- **구현 상세**:
  - 감시 목록은 `data/competitor_watchlist.json`에 저장
    - 형식: `[{"url": "...", "name": "...", "selector": "...", "last_hash": "...", "last_check": "..."}]`
  - 각 사이트의 HTML을 httpx로 가져옴 → BeautifulSoup으로 파싱
  - selector가 있으면 해당 영역만, 없으면 `<body>` 전체 텍스트 추출
  - 텍스트의 해시(hashlib.md5)를 이전 저장값과 비교 → 다르면 "변경 감지"
  - 변경 시: difflib.unified_diff()로 이전/현재 텍스트 차이점 생성
  - 이전 스냅샷은 `data/competitor_snapshots/` 폴더에 `{url_hash}_{timestamp}.txt`로 저장
  - 결과를 `_llm_call()`로 "어떤 변경이 사업적으로 의미 있는지" 분석
- **환경변수**: 없음
- **의존 라이브러리**: httpx, beautifulsoup4
- **agents.yaml 배정**: `cso_manager`, `market_research_specialist`

### 도구 2: 앱스토어 리뷰 수집기 (`src/tools/app_review_scraper.py`)
- **tool_id**: `app_review_scraper`
- **클래스명**: `AppReviewScraperTool`
- **하는 일**: 구글 플레이스토어에서 앱 리뷰를 대량 수집 + 분석
- **action 종류**:
  - `action="reviews"`: 앱 리뷰 수집
    - `app_id`: 구글 플레이 앱 ID (예: "com.megastudy.leet")
    - `count`: 수집할 리뷰 수 (기본: 100, 최대: 500)
    - `sort`: 정렬 ("newest", "rating", "relevance")
    - `lang`: 언어 (기본: "ko")
  - `action="analyze"`: 수집된 리뷰 분석
    - `app_id`: 앱 ID
  - `action="compare"`: 두 앱 리뷰 비교
    - `app_ids`: 쉼표 구분 앱 ID들 (예: "com.app1,com.app2")
- **구현 상세**:
  - `google-play-scraper` 라이브러리 사용 (pip install google-play-scraper)
    ```python
    from google_play_scraper import reviews, Sort
    result, _ = reviews('com.app.id', lang='ko', country='kr', sort=Sort.NEWEST, count=100)
    ```
  - 라이브러리 없으면 안내 메시지 반환 (기존 kr_stock.py의 _install_msg 패턴 참고)
  - 수집 데이터: 별점, 내용, 날짜, 좋아요 수, 앱 버전
  - 분석 항목:
    - 별점 분포 (1~5점 각각 몇 %)
    - 긍정/부정 키워드 빈도 (Counter 사용)
    - 시간별 별점 추이 (최근 별점이 올라가는지 내려가는지)
  - 결과를 `_llm_call()`로 "핵심 불만/칭찬, 개선 우선순위" 분석
- **환경변수**: 없음
- **의존 라이브러리**: google-play-scraper (없으면 설치 안내)
- **agents.yaml 배정**: `cso_manager`, `market_research_specialist`

### 도구 3: 유튜브 채널 분석기 (`src/tools/youtube_analyzer.py`)
- **tool_id**: `youtube_analyzer`
- **클래스명**: `YoutubeAnalyzerTool`
- **하는 일**: 유튜브 채널의 영상 데이터를 수집하고 분석
- **action 종류**:
  - `action="channel"`: 채널 정보 + 최근 영상 분석
    - `channel_url`: 채널 URL (예: "https://www.youtube.com/@channelname")
    - `video_count`: 분석할 최근 영상 수 (기본: 20)
  - `action="search"`: 유튜브 키워드 검색 결과 분석
    - `query`: 검색 키워드 (예: "LEET 해설")
    - `count`: 결과 수 (기본: 20)
  - `action="trending"`: 특정 카테고리 인기 동영상
    - `category`: 카테고리 ("education", "all")
- **구현 상세**:
  - `yt-dlp` 라이브러리 사용 (pip install yt-dlp) — 메타데이터만 추출, 영상 다운로드 안 함
    ```python
    import yt_dlp
    ydl_opts = {'quiet': True, 'extract_flat': True, 'playlistend': 20}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
    ```
  - 또는 httpx로 YouTube 페이지를 직접 파싱 (API 키 불필요 방식)
  - 수집 데이터: 영상 제목, 조회수, 좋아요, 댓글 수, 업로드 날짜, 영상 길이
  - 분석 항목:
    - 평균 조회수, 조회수 중앙값
    - 업로드 빈도 (주당 몇 개)
    - 조회수 상위/하위 영상 비교 → 어떤 주제가 잘 되는지
    - 성장 추세 (최근 영상 조회수 vs 과거)
  - 결과를 `_llm_call()`로 "콘텐츠 전략 분석 + 벤치마킹 인사이트" 제공
- **환경변수**: 없음
- **의존 라이브러리**: yt-dlp (없으면 설치 안내)
- **agents.yaml 배정**: `cso_manager`, `market_research_specialist`

### 도구 4: 정부 지원금/보조금 찾기 (`src/tools/subsidy_finder.py`)
- **tool_id**: `subsidy_finder`
- **클래스명**: `SubsidyFinderTool`
- **하는 일**: 받을 수 있는 정부 지원사업을 자동 검색
- **action 종류**:
  - `action="search"`: 지원사업 검색
    - `keyword`: 검색 키워드 (예: "AI", "교육", "스타트업")
    - `category`: 분류 ("창업", "기술개발", "인력", "수출", "전체")
    - `region`: 지역 ("서울", "전국", 기본: "전국")
    - `count`: 결과 수 (기본: 20)
  - `action="detail"`: 특정 지원사업 상세 정보
    - `url`: 지원사업 상세 페이지 URL
  - `action="match"`: 우리 회사 조건에 맞는 지원사업 필터링
    - `company_type`: "예비창업자", "창업3년이내", "중소기업" 등
    - `industry`: "교육", "IT", "서비스" 등
- **구현 상세**:
  - 기업마당 API 활용: `https://www.bizinfo.go.kr/uss/rss/bizRssList.do` (RSS 피드)
  - 또는 httpx로 기업마당 검색 페이지 크롤링
    - 검색 URL: `https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/list.do`
  - K-Startup (`https://www.k-startup.go.kr`) 지원사업 목록도 크롤링
  - BeautifulSoup으로 파싱: 사업명, 지원기관, 지원규모, 신청기간, 지원대상
  - `match` action: 조건 필터링 (업종, 기업유형, 지역 매칭)
  - 결과를 `_llm_call()`로 "우리 회사에 가장 적합한 지원사업 추천 + 신청 전략" 분석
- **환경변수**: 없음
- **의존 라이브러리**: httpx, beautifulsoup4
- **agents.yaml 배정**: `cso_manager`, `business_plan_specialist`, `financial_model_specialist`

### 도구 5: 네이버 플레이스 리뷰 수집기 (`src/tools/naver_place_scraper.py`)
- **tool_id**: `naver_place_scraper`
- **클래스명**: `NaverPlaceScraperTool`
- **하는 일**: 네이버 플레이스(지도)에서 매장/학원 리뷰 수집 + 분석
- **action 종류**:
  - `action="search"`: 네이버 플레이스에서 장소 검색
    - `query`: 검색어 (예: "LEET 학원 서울")
    - `count`: 결과 수 (기본: 10)
  - `action="reviews"`: 특정 장소의 리뷰 수집
    - `place_id`: 네이버 플레이스 ID
    - `count`: 리뷰 수 (기본: 100)
  - `action="analyze"`: 수집된 리뷰 분석
    - `place_id`: 장소 ID
- **구현 상세**:
  - 네이버 플레이스 API (비공식, 무료):
    - 검색: `https://map.naver.com/v5/api/search?query={query}&type=all`
    - 리뷰: `https://map.naver.com/v5/api/sites/summary/{place_id}/review`
  - httpx로 요청 시 User-Agent 헤더 필수
  - 수집 데이터: 리뷰 텍스트, 별점, 작성일, 방문 목적, 키워드 태그
  - 분석 항목:
    - 평균 별점, 별점 분포
    - 자주 언급되는 긍정/부정 키워드 (Counter)
    - 시간별 별점 추이
    - 경쟁 매장 간 비교 (여러 place_id 비교 가능)
  - 결과를 `_llm_call()`로 "고객 만족/불만 요인, 경쟁 우위 포인트" 분석
- **환경변수**: 없음
- **의존 라이브러리**: httpx
- **agents.yaml 배정**: `cso_manager`, `market_research_specialist`

### 도구 6: 학술 논문 검색기 (`src/tools/scholar_scraper.py`)
- **tool_id**: `scholar_scraper`
- **클래스명**: `ScholarScraperTool`
- **하는 일**: Google Scholar에서 논문 검색 + 트렌드 분석
- **action 종류**:
  - `action="search"`: 논문 검색
    - `query`: 검색 키워드 (예: "법학적성시험 예측타당도")
    - `count`: 결과 수 (기본: 20)
    - `year_from`: 시작 연도 (선택)
    - `sort_by`: "relevance" 또는 "date"
  - `action="cite"`: 특정 논문의 인용 정보
    - `title`: 논문 제목
  - `action="trend"`: 분야별 논문 발표 추이
    - `query`: 키워드
    - `years`: 조회 기간 (기본: 10년)
- **구현 상세**:
  - `scholarly` 라이브러리 사용 (pip install scholarly)
    ```python
    from scholarly import scholarly
    search_query = scholarly.search_pubs(query)
    results = [next(search_query) for _ in range(count)]
    ```
  - 라이브러리 없으면: httpx로 Google Scholar 직접 크롤링 (fallback)
    - URL: `https://scholar.google.com/scholar?q={query}&hl=ko`
    - BeautifulSoup으로 파싱: 제목, 저자, 초록, 인용수, 연도
  - 주의: Google Scholar는 과도한 요청 시 차단 → 요청 간 1~2초 딜레이 필수 (`asyncio.sleep()`)
  - `trend` action: 연도별 논문 수 집계 → 관심 증가/감소 추세
  - 결과를 `_llm_call()`로 "핵심 연구 동향, 사업에 활용 가능한 학술 근거" 분석
- **환경변수**: 없음
- **의존 라이브러리**: scholarly (없으면 httpx + beautifulsoup4로 fallback)
- **agents.yaml 배정**: `cso_manager`, `market_research_specialist`, `business_plan_specialist`

---

## 최종 체크리스트

모든 도구 작성 후 반드시 확인:

1. [ ] `src/tools/competitor_monitor.py` 생성 완료
2. [ ] `src/tools/app_review_scraper.py` 생성 완료
3. [ ] `src/tools/youtube_analyzer.py` 생성 완료
4. [ ] `src/tools/subsidy_finder.py` 생성 완료
5. [ ] `src/tools/naver_place_scraper.py` 생성 완료
6. [ ] `src/tools/scholar_scraper.py` 생성 완료
7. [ ] `src/tools/pool.py`에 6개 도구 전부 import + tool_classes에 등록
8. [ ] `config/tools.yaml`에 6개 도구 설정 추가 (`# ─── CSO 사업기획처 신규 도구 ───` 섹션)
9. [ ] `config/agents.yaml`에서 `cso_manager`, `market_research_specialist`, `business_plan_specialist`, `financial_model_specialist`의 `allowed_tools`에 해당 도구 추가
10. [ ] 모든 파일에 한국어 docstring 포함 (사용 방법, 필요 환경변수)
11. [ ] 외부 라이브러리 없을 때 설치 안내 메시지 반환 (ImportError 처리)
12. [ ] 크롤링 시 User-Agent 헤더 설정 + 요청 간 딜레이
13. [ ] 커밋 메시지: `feat: CSO 사업기획처 신규 도구 6개 추가 (경쟁사감지/앱리뷰/유튜브분석/지원금/네이버플레이스/논문검색) [완료]`
14. [ ] 브랜치 `claude/corthex-improvements-kE0ii`에 push
