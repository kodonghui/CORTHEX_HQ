# 에이전트 4번 프롬프트: CMO 마케팅고객처 도구 5개

## 너의 역할
너는 CORTHEX HQ 프로젝트의 **CMO 마케팅·고객처 전문 도구**를 만드는 개발자야.
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
- action 파라미터로 기능 분기
- httpx.AsyncClient() 으로 외부 요청
- 크롤링은 httpx + BeautifulSoup (User-Agent 헤더 + 딜레이)
- 결과를 `self._llm_call()` 로 LLM 분석 추가
- 로거: `logger = logging.getLogger("corthex.tools.도구이름")`

### 3) 등록 방법
- `src/tools/pool.py`의 `build_from_config`에: import + tool_classes 딕셔너리에 추가
- `config/tools.yaml`에 tool 정의 추가
- `config/agents.yaml`에서 해당 에이전트의 `allowed_tools`에 추가

---

## 만들어야 할 도구 5개

### 도구 1: SEO 분석기 (`src/tools/seo_analyzer.py`)
- **tool_id**: `seo_analyzer`
- **클래스명**: `SeoAnalyzerTool`
- **하는 일**: 웹사이트의 검색엔진 최적화(SEO) 상태를 자동 점검
- **action 종류**:
  - `action="audit"`: SEO 종합 감사
    - `url`: 분석할 웹사이트 URL (예: "https://example.com")
  - `action="keywords"`: 페이지의 키워드 밀도 분석
    - `url`: 분석할 URL
    - `target_keywords`: 확인할 키워드 (쉼표 구분, 예: "LEET,로스쿨,법학")
  - `action="compare"`: 두 URL의 SEO 점수 비교
    - `url1`: URL 1
    - `url2`: URL 2
- **구현 상세**:
  - httpx로 페이지 HTML 가져오기 → BeautifulSoup으로 파싱
  - SEO 감사 항목 (각 항목별 점수 매기기, 총 100점):
    ```python
    SEO_CHECKS = {
        # ─── 기본 메타 (30점) ───
        "title_tag": {
            "weight": 10,
            "check": "title 태그 존재 여부 + 길이(30~60자 적정)",
            "deduction": "없으면 -10, 너무 짧거나 길면 -5"
        },
        "meta_description": {
            "weight": 10,
            "check": "meta description 존재 여부 + 길이(120~160자 적정)",
        },
        "h1_tag": {
            "weight": 5,
            "check": "h1 태그 존재 여부 + 유일성(1개만 있어야 함)",
        },
        "heading_structure": {
            "weight": 5,
            "check": "h1→h2→h3 순서 올바른지 (건너뛰기 없는지)",
        },
        # ─── 콘텐츠 (25점) ───
        "content_length": {
            "weight": 10,
            "check": "본문 텍스트 길이 (최소 300단어 권장)",
        },
        "keyword_density": {
            "weight": 10,
            "check": "목표 키워드 밀도 (1~3% 적정, 5% 이상은 과다)",
        },
        "image_alt": {
            "weight": 5,
            "check": "img 태그에 alt 속성 있는지 (접근성 + SEO)",
        },
        # ─── 기술 (25점) ───
        "mobile_viewport": {
            "weight": 10,
            "check": "viewport 메타 태그 존재 (모바일 대응)",
        },
        "canonical_tag": {
            "weight": 5,
            "check": "canonical URL 설정 여부",
        },
        "robots_txt": {
            "weight": 5,
            "check": "/robots.txt 존재 여부",
        },
        "sitemap": {
            "weight": 5,
            "check": "/sitemap.xml 존재 여부",
        },
        # ─── 성능 (20점) ───
        "page_load_time": {
            "weight": 10,
            "check": "페이지 응답 시간 (1초 미만 우수, 3초 이상 나쁨)",
        },
        "html_size": {
            "weight": 5,
            "check": "HTML 파일 크기 (100KB 이하 적정)",
        },
        "external_links": {
            "weight": 5,
            "check": "외부 링크 수 + nofollow 여부",
        },
    }
    ```
  - 응답 시간 측정: httpx 요청 시 `time.time()` 으로 측정
  - `keywords` action: 본문에서 target_keywords 각각의 출현 빈도 / 전체 단어 수 = 밀도(%)
  - 결과를 `_llm_call()`로 "SEO 개선 우선순위 + 구체적 수정 가이드" 분석
- **환경변수**: 없음
- **의존 라이브러리**: httpx, beautifulsoup4
- **agents.yaml 배정**: `cmo_manager`, `content_specialist`, `community_specialist`

### 도구 2: SNS 감정 분석기 (`src/tools/sentiment_analyzer.py`)
- **tool_id**: `sentiment_analyzer`
- **클래스명**: `SentimentAnalyzerTool`
- **하는 일**: 특정 키워드에 대한 온라인 여론의 긍정/부정 분석
- **action 종류**:
  - `action="analyze"`: 키워드 감정 분석
    - `keyword`: 분석 키워드 (예: "CORTHEX", "LEET 해설")
    - `sources`: 소스 (기본: "naver_news,naver_blog")
    - `count`: 수집할 글 수 (기본: 50)
  - `action="trend"`: 시간별 감정 추이
    - `keyword`: 키워드
    - `days`: 분석 기간 (기본: 30)
  - `action="report"`: 종합 여론 보고서
    - `keyword`: 키워드
- **구현 상세**:
  - 데이터 수집:
    - 네이버 뉴스 검색 API: `https://openapi.naver.com/v1/search/news.json?query={keyword}`
    - 네이버 블로그 검색 API: `https://openapi.naver.com/v1/search/blog.json?query={keyword}`
    - 헤더: `X-Naver-Client-Id`, `X-Naver-Client-Secret`
  - 감정 분석 방법 (외부 AI 모델 없이 직접 구현):
    ```python
    # 한국어 감정 사전 (직접 정의)
    POSITIVE_WORDS = [
        "좋다", "훌륭", "추천", "만족", "최고", "편리", "유용", "도움",
        "잘했", "대박", "짱", "꿀팁", "강추", "괜찮", "나이스", "굿",
        "효과적", "깔끔", "정확", "친절", "빠르", "쉽다", "알차",
    ]
    NEGATIVE_WORDS = [
        "별로", "실망", "불만", "최악", "짜증", "부족", "비싸", "불편",
        "쓰레기", "후회", "거지", "노답", "폐급", "사기", "망했",
        "느리", "어렵", "복잡", "불친절", "에러", "오류", "버그",
    ]

    def analyze_sentiment(text: str) -> dict:
        positive_count = sum(1 for w in POSITIVE_WORDS if w in text)
        negative_count = sum(1 for w in NEGATIVE_WORDS if w in text)
        total = positive_count + negative_count
        if total == 0:
            return {"label": "중립", "score": 0.5}
        pos_ratio = positive_count / total
        if pos_ratio > 0.6:
            return {"label": "긍정", "score": pos_ratio}
        elif pos_ratio < 0.4:
            return {"label": "부정", "score": pos_ratio}
        else:
            return {"label": "중립", "score": pos_ratio}
    ```
  - 분석 결과:
    - 전체 긍정/부정/중립 비율 (파이차트 텍스트 표현)
    - 자주 나오는 긍정/부정 키워드 Top 10
    - 대표 긍정/부정 문장 각 3개
  - `trend` action: 날짜별 감정 점수 추이 (일별 긍정 비율)
  - 결과를 `_llm_call()`로 "여론 요약 + PR 대응 전략" 분석
- **환경변수**: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` (기존과 동일)
- **의존 라이브러리**: httpx
- **agents.yaml 배정**: `cmo_manager`, `survey_specialist`, `community_specialist`

### 도구 3: 해시태그 추천기 (`src/tools/hashtag_recommender.py`)
- **tool_id**: `hashtag_recommender`
- **클래스명**: `HashtagRecommenderTool`
- **하는 일**: SNS 게시물에 효과적인 해시태그를 자동 추천
- **action 종류**:
  - `action="recommend"`: 해시태그 추천
    - `topic`: 게시물 주제 (예: "LEET 공부법")
    - `platform`: "instagram", "youtube", "tiktok" (기본: "instagram")
    - `count`: 추천 개수 (기본: 30)
  - `action="analyze"`: 특정 해시태그의 인기도 분석
    - `hashtags`: 분석할 해시태그들 (쉼표 구분, 예: "#LEET,#로스쿨,#법학")
  - `action="trending"`: 현재 인기 해시태그
    - `category`: "교육", "금융", "기술", "라이프스타일"
- **구현 상세**:
  - 해시태그 추천 전략 (3단계):
    1. **시드 해시태그 생성**: 주제에서 핵심 키워드 추출 → 관련 해시태그 변형
       ```python
       # "LEET 공부법" → #LEET, #리트, #로스쿨, #법학적성시험, #LEET공부, #리트공부법, ...
       ```
    2. **카테고리별 분류**:
       - 대형 (100만+ 게시물): 노출은 크지만 경쟁 치열 → 2~3개만
       - 중형 (1만~100만): 최적 노출 영역 → 15~20개
       - 소형 (1만 미만): 타겟 정확 → 5~10개
    3. **조합 최적화**: 대+중+소 혼합하여 최적 세트 구성
  - 인스타그램 해시태그 데이터 수집:
    - `https://www.instagram.com/explore/tags/{hashtag}/` 페이지의 게시물 수 추출
    - httpx로 요청 (로그인 불필요, 공개 데이터)
    - 주의: 인스타그램 차단 방지를 위해 요청 간 2~3초 딜레이
  - 한국어 해시태그 사전 (분야별 내장 데이터):
    ```python
    HASHTAG_DB = {
        "교육": {
            "대형": ["#공부", "#공부그램", "#공스타그램", "#합격", "#수험생"],
            "중형": ["#법학", "#로스쿨", "#LEET", "#법대", "#사법시험"],
            "소형": ["#리트공부", "#LEET준비", "#로스쿨준비", "#법학적성시험"],
        },
        "금융": { ... },
        "기술": { ... },
    }
    ```
  - 결과를 `_llm_call()`로 "왜 이 조합이 좋은지 + 게시 시간 추천" 분석
- **환경변수**: 없음
- **의존 라이브러리**: httpx
- **agents.yaml 배정**: `cmo_manager`, `content_specialist`

### 도구 4: 이메일 마케팅 최적화기 (`src/tools/email_optimizer.py`)
- **tool_id**: `email_optimizer`
- **클래스명**: `EmailOptimizerTool`
- **하는 일**: 마케팅 이메일의 효과를 예측하고 개선안을 제시
- **action 종류**:
  - `action="analyze"`: 이메일 분석
    - `subject`: 이메일 제목
    - `body`: 이메일 본문 (선택)
    - `audience`: 대상 ("수험생", "직장인", "일반", 기본: "일반")
  - `action="suggest"`: 제목 개선안 생성
    - `subject`: 원래 제목
    - `count`: 대안 개수 (기본: 5)
  - `action="ab_test"`: A/B 테스트용 제목 쌍 생성
    - `topic`: 이메일 주제
    - `pairs`: 쌍 개수 (기본: 3)
- **구현 상세**:
  - 이메일 제목 점수 산정 (100점 만점):
    ```python
    SUBJECT_RULES = {
        # ─── 길이 (20점) ───
        "length": {
            "optimal": (20, 50),  # 20~50자가 최적
            "weight": 20,
        },
        # ─── 개인화 (15점) ───
        "personalization": {
            "patterns": [r"\{이름\}", r"\{name\}", "님", "당신"],
            "weight": 15,
        },
        # ─── 긴급성 (15점) ───
        "urgency": {
            "words": ["마감", "오늘만", "한정", "지금", "놓치지", "서두르", "마지막"],
            "weight": 15,
            "warning": "과도하면 스팸 느낌 → 1개만 권장"
        },
        # ─── 숫자/구체성 (15점) ───
        "specificity": {
            "patterns": [r"\d+%", r"\d+가지", r"\d+일", r"\d+만원"],
            "weight": 15,
        },
        # ─── 이모지 (10점) ───
        "emoji": {
            "weight": 10,
            "optimal_count": (0, 2),  # 0~2개 적정
        },
        # ─── 질문형 (10점) ───
        "question": {
            "patterns": [r"\?$", r"할까요", r"인가요", r"일까요"],
            "weight": 10,
        },
        # ─── 스팸 단어 감점 (-15점) ───
        "spam_words": {
            "words": ["무료", "공짜", "100%", "클릭", "당첨", "대박"],
            "penalty": -15,
        },
    }
    ```
  - 본문 분석 (선택):
    - 본문 길이 (200~500자 권장)
    - CTA(Call to Action) 버튼/링크 존재 여부
    - 이미지 대 텍스트 비율
  - `suggest` action: 제목 개선 규칙 적용 → `_llm_call()`로 개선된 제목 생성
  - `ab_test` action: 같은 주제에 대해 스타일이 다른 제목 쌍 생성 (긴급형 vs 호기심형 vs 혜택형)
- **환경변수**: 없음
- **의존 라이브러리**: 없음 (순수 파이썬 + re 모듈)
- **agents.yaml 배정**: `cmo_manager`, `content_specialist`

### 도구 5: 경쟁사 SNS 모니터 (`src/tools/competitor_sns_monitor.py`)
- **tool_id**: `competitor_sns_monitor`
- **클래스명**: `CompetitorSnsMonitorTool`
- **하는 일**: 경쟁사의 SNS 활동을 자동 수집하고 분석
- **action 종류**:
  - `action="add"`: 감시 대상 추가
    - `name`: 경쟁사 이름
    - `blog_url`: 네이버 블로그 URL (선택)
    - `instagram`: 인스타그램 사용자명 (선택)
    - `youtube`: 유튜브 채널 URL (선택)
  - `action="remove"`: 감시 해제
  - `action="check"`: 등록된 경쟁사의 최근 SNS 활동 확인
  - `action="report"`: 경쟁사 SNS 전략 종합 보고서
    - `name`: 경쟁사 이름 (특정 1곳) 또는 "all"
  - `action="list"`: 감시 중인 경쟁사 목록
- **구현 상세**:
  - 감시 목록: `data/competitor_sns_watchlist.json`
    ```json
    [
      {
        "name": "메가로스쿨",
        "blog_url": "https://blog.naver.com/mega_leet",
        "instagram": "mega_leet",
        "youtube": "https://www.youtube.com/@mega_leet",
        "last_check": "2026-02-14T10:00:00"
      }
    ]
    ```
  - 네이버 블로그 수집:
    - RSS 피드: `https://rss.blog.naver.com/{blog_id}.xml`
    - httpx로 RSS XML 파싱 → 최근 게시물 제목, 날짜, URL 추출
  - 인스타그램 수집:
    - `https://www.instagram.com/{username}/` 페이지 크롤링
    - 게시물 수, 팔로워 수, 최근 게시물 개수 (로그인 없이 가능한 범위)
    - 주의: 인스타그램은 제한적 → 가능한 만큼만, 차단 시 graceful 처리
  - 유튜브 수집:
    - 채널 페이지 또는 `yt-dlp`으로 최근 영상 메타데이터 추출
    - 영상 제목, 조회수, 업로드일
  - 분석 항목:
    - 게시 빈도 (주당 몇 개)
    - 콘텐츠 유형 분류 (텍스트/이미지/영상/리뷰/광고)
    - 반응도 (좋아요, 댓글, 조회수)
    - 최근 콘텐츠 주제 트렌드
  - 결과를 `_llm_call()`로 "경쟁사 SNS 전략 분석 + 우리의 대응 전략" 분석
- **환경변수**: 없음
- **의존 라이브러리**: httpx, beautifulsoup4
- **agents.yaml 배정**: `cmo_manager`, `content_specialist`, `community_specialist`

---

## 최종 체크리스트

모든 도구 작성 후 반드시 확인:

1. [ ] `src/tools/seo_analyzer.py` 생성 완료
2. [ ] `src/tools/sentiment_analyzer.py` 생성 완료
3. [ ] `src/tools/hashtag_recommender.py` 생성 완료
4. [ ] `src/tools/email_optimizer.py` 생성 완료
5. [ ] `src/tools/competitor_sns_monitor.py` 생성 완료
6. [ ] `src/tools/pool.py`에 5개 도구 전부 import + tool_classes에 등록
7. [ ] `config/tools.yaml`에 5개 도구 설정 추가 (`# ─── CMO 마케팅고객처 신규 도구 ───` 섹션)
8. [ ] `config/agents.yaml`에서 `cmo_manager`, `content_specialist`, `survey_specialist`, `community_specialist`의 `allowed_tools`에 해당 도구 추가
9. [ ] 모든 파일에 한국어 docstring 포함
10. [ ] 감정 분석기: 한국어 감정 단어 사전 최소 각 20개 이상 포함
11. [ ] SEO 분석기: 점수 항목 최소 10개 이상
12. [ ] 이메일 최적화기: 점수 규칙 최소 7개 이상
13. [ ] 크롤링 시 User-Agent 헤더 + 요청 간 딜레이
14. [ ] 커밋 메시지: `feat: CMO 마케팅고객처 신규 도구 5개 추가 (SEO분석/감정분석/해시태그/이메일최적화/경쟁사SNS) [완료]`
15. [ ] 브랜치 `claude/corthex-improvements-kE0ii`에 push
