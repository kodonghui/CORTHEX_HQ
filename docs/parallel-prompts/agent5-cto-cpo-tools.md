# 에이전트 5번 프롬프트: CTO 기술개발처 + CPO 출판기록처 + 공통 도구 7개

## 너의 역할
너는 CORTHEX HQ 프로젝트의 **CTO 기술개발처 + CPO 출판기록처 + 전사 공통** 도구를 만드는 개발자야.
7개의 파이썬 도구를 만들어야 해. 전부 `src/tools/` 폴더에 파이썬 파일로 만들고,
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
- 로거: `logger = logging.getLogger("corthex.tools.도구이름")`
- 결과를 `self._llm_call()` 로 LLM 분석 추가 (적절한 경우)

### 3) 등록 방법
- `src/tools/pool.py`의 `build_from_config`에: import + tool_classes 딕셔너리에 추가
- `config/tools.yaml`에 tool 정의 추가
- `config/agents.yaml`에서 해당 에이전트의 `allowed_tools`에 추가

---

## 만들어야 할 도구 7개

---

### [CTO 도구 1] 웹사이트 상태 모니터 (`src/tools/uptime_monitor.py`)
- **tool_id**: `uptime_monitor`
- **클래스명**: `UptimeMonitorTool`
- **소속**: CTO 기술개발처
- **하는 일**: 웹사이트가 정상 작동하는지 확인하고, 다운되면 보고
- **action 종류**:
  - `action="add"`: 모니터링 대상 추가
    - `url`: URL (예: "https://corthex.com")
    - `name`: 사이트 이름
    - `expected_status`: 기대 HTTP 상태 코드 (기본: 200)
  - `action="remove"`: 대상 제거
  - `action="check"`: 등록된 모든 사이트 상태 확인 (즉시 실행)
  - `action="list"`: 모니터링 목록
  - `action="history"`: 특정 사이트의 응답 시간 이력
    - `url`: 대상 URL
    - `hours`: 최근 N시간 (기본: 24)
- **구현 상세**:
  - 모니터링 목록: `data/uptime_watchlist.json`
  - 응답 이력: `data/uptime_history.json`
    ```json
    {
      "https://corthex.com": [
        {"timestamp": "2026-02-14T10:00:00", "status": 200, "response_ms": 450, "ok": true},
        {"timestamp": "2026-02-14T10:01:00", "status": 503, "response_ms": null, "ok": false, "error": "Service Unavailable"}
      ]
    }
    ```
  - `check` action:
    - httpx.AsyncClient()으로 각 URL에 HEAD 요청 (GET보다 가벼움)
    - `timeout=10` (10초 내 응답 없으면 다운 판정)
    - 응답 시간 측정: `time.time()` 전후 차이
    - 결과 형식:
      ```
      ✅ corthex.com — 200 OK (응답: 0.45초)
      ❌ api.corthex.com — 503 에러 (응답 없음)
      ⚠️ blog.corthex.com — 200 OK (응답: 3.2초, 느림 경고)
      ```
    - 느림 경고 기준: 응답 2초 이상
  - `history` action: 저장된 이력에서 평균 응답시간, 가용률(%), 최장 다운타임 계산
  - 이력은 최대 1000건까지 보관 (오래된 것부터 삭제)
- **환경변수**: 없음
- **의존 라이브러리**: httpx
- **agents.yaml 배정**: `cto_manager`, `infra_specialist`

---

### [CTO 도구 2] 보안 취약점 스캐너 (`src/tools/security_scanner.py`)
- **tool_id**: `security_scanner`
- **클래스명**: `SecurityScannerTool`
- **소속**: CTO 기술개발처
- **하는 일**: 프로젝트 의존성의 알려진 보안 취약점(CVE) 검사
- **action 종류**:
  - `action="scan"`: 취약점 스캔
    - `requirements_file`: requirements.txt 경로 (기본: 프로젝트 루트의 requirements.txt)
  - `action="check_package"`: 특정 패키지 취약점 확인
    - `package`: 패키지명 (예: "requests")
    - `version`: 버전 (예: "2.28.0")
  - `action="report"`: 전체 보안 보고서
- **구현 상세**:
  - 방법 1: `pip-audit` 라이브러리 활용 (있으면)
    ```python
    import subprocess
    result = subprocess.run(
        ["pip-audit", "--format=json", "-r", requirements_file],
        capture_output=True, text=True
    )
    ```
  - 방법 2: PyPI JSON API로 직접 확인 (pip-audit 없을 때 fallback)
    ```python
    # 각 패키지의 알려진 취약점 조회
    # https://pypi.org/pypi/{package}/{version}/json → info.vulnerabilities
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://pypi.org/pypi/{package}/{version}/json")
        data = resp.json()
        vulns = data.get("vulnerabilities", [])
    ```
  - 방법 3: OSV (Open Source Vulnerabilities) API
    ```python
    # https://api.osv.dev/v1/query
    # POST body: {"package": {"name": "requests", "ecosystem": "PyPI"}, "version": "2.28.0"}
    ```
  - requirements.txt 파싱:
    ```python
    def parse_requirements(file_path: str) -> list[tuple[str, str]]:
        packages = []
        with open(file_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                # "requests==2.28.0" → ("requests", "2.28.0")
                if "==" in line:
                    name, version = line.split("==", 1)
                    packages.append((name.strip(), version.strip()))
                elif ">=" in line:
                    name = line.split(">=")[0].strip()
                    packages.append((name, "latest"))
        return packages
    ```
  - 결과 형식:
    ```
    ## 보안 스캔 결과
    총 패키지: 45개 | 취약점 발견: 3개 | 안전: 42개

    🔴 [높음] requests 2.28.0 — CVE-2023-32681: 인증 정보 유출 위험
       → 해결: pip install requests>=2.31.0
    🟡 [중간] pillow 9.0.0 — CVE-2023-44271: 이미지 처리 DoS
       → 해결: pip install pillow>=10.0.1
    🟢 [낮음] urllib3 1.26.0 — CVE-2023-43804: 쿠키 정보 노출
       → 해결: pip install urllib3>=2.0.6
    ```
  - 결과를 `_llm_call()`로 "전체 보안 상태 평가 + 우선 조치 사항" 분석
- **환경변수**: 없음
- **의존 라이브러리**: httpx (OSV API용)
- **agents.yaml 배정**: `cto_manager`, `backend_specialist`, `infra_specialist`

---

### [CTO 도구 3] 에러 로그 분석기 (`src/tools/log_analyzer.py`)
- **tool_id**: `log_analyzer`
- **클래스명**: `LogAnalyzerTool`
- **소속**: CTO 기술개발처
- **하는 일**: 로그 파일을 분석하여 에러 유형/빈도/패턴을 자동 통계
- **action 종류**:
  - `action="analyze"`: 로그 파일 분석
    - `log_file`: 로그 파일 경로 (기본: `logs/corthex.log`)
    - `level`: 분석할 로그 레벨 ("ERROR", "WARNING", "ALL", 기본: "ERROR")
    - `hours`: 최근 N시간 (기본: 24)
  - `action="top_errors"`: 가장 많이 발생하는 에러 Top N
    - `top_n`: 상위 N개 (기본: 10)
  - `action="timeline"`: 시간대별 에러 발생 빈도
    - `log_file`: 로그 파일 경로
    - `hours`: 분석 기간 (기본: 24)
- **구현 상세**:
  - 로그 파싱 정규식:
    ```python
    import re
    # 표준 파이썬 로그 형식: "2026-02-14 10:30:45,123 - corthex.tools.dart_api - ERROR - 메시지"
    LOG_PATTERN = re.compile(
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}),?\d*\s*[-–]\s*"
        r"([\w.]+)\s*[-–]\s*(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*[-–]\s*(.*)"
    )
    ```
  - 파싱 결과를 리스트로 수집:
    ```python
    @dataclass
    class LogEntry:
        timestamp: datetime
        logger_name: str
        level: str
        message: str
    ```
  - 분석 항목:
    - 레벨별 건수: ERROR 42건, WARNING 128건, INFO 3,450건
    - 에러 메시지 그룹핑: 비슷한 메시지를 묶어서 빈도 집계
      - 메시지의 변수 부분을 제거하고 패턴화 (숫자→`{N}`, URL→`{URL}`)
    - 시간대별 분포: 어느 시간에 에러가 집중되는지
    - 모듈별 분포: 어떤 모듈(logger_name)에서 에러가 많은지
  - `timeline` action: 시간대별 에러 빈도를 텍스트 막대 그래프로 표현
    ```
    00시: ██ (3건)
    01시:  (0건)
    ...
    14시: ████████████ (15건)
    15시: ██████ (8건)
    ```
  - 결과를 `_llm_call()`로 "에러 근본 원인 추정 + 수정 우선순위" 분석
- **환경변수**: 없음
- **의존 라이브러리**: 없음 (순수 파이썬)
- **agents.yaml 배정**: `cto_manager`, `backend_specialist`, `infra_specialist`

---

### [CTO 도구 4] API 성능 측정기 (`src/tools/api_benchmark.py`)
- **tool_id**: `api_benchmark`
- **클래스명**: `ApiBenchmarkTool`
- **소속**: CTO 기술개발처
- **하는 일**: 프로젝트의 모든 도구/API의 응답 속도와 성공률을 측정
- **action 종류**:
  - `action="benchmark"`: 등록된 도구들의 성능 측정
    - `tools`: 측정할 도구 ID들 (쉼표 구분, 기본: "all")
    - `iterations`: 반복 횟수 (기본: 3)
  - `action="single"`: 단일 API 엔드포인트 측정
    - `url`: 측정할 URL
    - `method`: "GET" or "POST" (기본: "GET")
    - `iterations`: 반복 횟수 (기본: 5)
  - `action="report"`: 전체 성능 보고서 (이전 측정 결과 기반)
- **구현 상세**:
  - 도구 벤치마크 (`benchmark` action):
    - 각 도구에 간단한 테스트 요청을 보내고 응답 시간 측정
    - 테스트 케이스 정의:
      ```python
      BENCHMARK_CASES = {
          "kr_stock": {"action": "price", "name": "삼성전자", "days": 5},
          "dart_api": {"action": "company", "company": "삼성전자"},
          "naver_news": {"action": "search", "query": "테스트", "count": 3},
          "web_search": {"action": "search", "query": "test", "count": 3},
          # ... 각 도구별 가벼운 테스트 케이스
      }
      ```
    - 각 도구의 `execute()` 메서드를 직접 호출하지는 않고,
      시간 측정만 담당 (실제 실행은 pool.invoke()를 통해)
    - 또는 간단히: 해당 도구의 환경변수가 설정되어 있는지만 확인 + 응답 시간 추정
  - 단일 API 측정 (`single` action):
    ```python
    import time
    times = []
    errors = 0
    for i in range(iterations):
        start = time.time()
        try:
            resp = await client.request(method, url, timeout=30)
            elapsed = (time.time() - start) * 1000  # ms
            times.append(elapsed)
            if resp.status_code >= 400:
                errors += 1
        except Exception:
            errors += 1
        await asyncio.sleep(0.5)  # 요청 간 간격
    ```
  - 성능 지표 계산:
    - 평균 응답시간 (ms)
    - P50 (중앙값), P95, P99 응답시간
    - 성공률 (%)
    - 최소/최대 응답시간
  - 벤치마크 결과 저장: `data/benchmark_results.json` (시간별 누적)
  - 결과를 `_llm_call()`로 "병목 지점, 성능 개선 우선순위" 분석
- **환경변수**: 없음
- **의존 라이브러리**: httpx
- **agents.yaml 배정**: `cto_manager`, `backend_specialist`, `infra_specialist`

---

### [CPO 도구 5] 보고서 자동 생성기 (`src/tools/report_generator.py`)
- **tool_id**: `report_generator`
- **클래스명**: `ReportGeneratorTool`
- **소속**: CPO 출판기록처
- **하는 일**: 분석 결과를 전문적인 마크다운/HTML 보고서로 자동 생성
- **action 종류**:
  - `action="generate"`: 보고서 생성
    - `title`: 보고서 제목
    - `sections`: 섹션 데이터 (JSON 문자열 또는 딕셔너리)
    - `format`: "markdown", "html" (기본: "markdown")
    - `template`: "investment"(투자보고서), "market"(시장분석), "weekly"(주간보고), "custom"
  - `action="weekly"`: 주간 종합 보고서 자동 생성
    - `week_start`: 주 시작일 (기본: 이번 주 월요일)
  - `action="templates"`: 사용 가능한 보고서 템플릿 목록
- **구현 상세**:
  - 보고서 템플릿 (파이썬 문자열):
    ```python
    TEMPLATES = {
        "investment": """
    # {title}
    **작성일**: {date} | **작성자**: CORTHEX 투자분석처

    ---

    ## 1. 시장 현황
    {market_overview}

    ## 2. 종목 분석
    {stock_analysis}

    ## 3. 기술적 분석
    {technical_analysis}

    ## 4. 리스크 평가
    {risk_assessment}

    ## 5. 투자 의견
    {investment_opinion}

    ---
    *본 보고서는 AI 분석 기반이며, 투자 결정의 최종 책임은 투자자에게 있습니다.*
    """,
        "market": "...",  # 시장 분석 보고서 템플릿
        "weekly": "...",  # 주간 보고서 템플릿
    }
    ```
  - HTML 변환: 마크다운을 간단한 HTML로 변환 (정규식 기반)
    ```python
    def md_to_html(md: str) -> str:
        html = md
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.M)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.M)
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\n\n', r'</p><p>', html)
        return f"<html><body><p>{html}</p></body></html>"
    ```
  - `weekly` action: `data/` 폴더의 최근 데이터 파일들을 자동 수집하여 종합
  - 생성된 보고서는 `data/reports/` 폴더에 저장
  - 결과를 `_llm_call()`로 보고서 내용 보강 (요약, 인사이트 추가)
- **환경변수**: 없음
- **의존 라이브러리**: 없음 (순수 파이썬)
- **agents.yaml 배정**: `cpo_manager`, `editor_specialist`, `chronicle_specialist`

---

### [CPO 도구 6] 회의록 자동 정리기 (`src/tools/meeting_formatter.py`)
- **tool_id**: `meeting_formatter`
- **클래스명**: `MeetingFormatterTool`
- **소속**: CPO 출판기록처
- **하는 일**: 회의 내용에서 결정사항/할일/담당자를 자동 추출
- **action 종류**:
  - `action="format"`: 회의록 정리
    - `text`: 회의 내용 텍스트
    - `meeting_type`: "일반", "투자검토", "기획회의", "기술회의" (기본: "일반")
  - `action="action_items"`: 할일 목록만 추출
    - `text`: 회의 내용 텍스트
  - `action="template"`: 회의록 양식 제공
    - `meeting_type`: 회의 유형
- **구현 상세**:
  - `format` action: 회의 텍스트를 `_llm_call()`로 구조화
    - 시스템 프롬프트:
      ```
      당신은 회의록 정리 전문가입니다.
      회의 내용을 다음 구조로 정리하세요:

      1. 회의 개요: 날짜, 참석자, 안건
      2. 논의 사항: 주요 논의 내용 요약
      3. 결정 사항: 확정된 결정 목록 (번호 매기기)
      4. Action Items (할 일):
         - [ ] 할일 내용 | 담당: OO | 기한: YYYY-MM-DD
      5. 다음 회의: 일정, 안건

      비전문가도 이해할 수 있게 쉽게 작성하세요.
      ```
  - `action_items` action:
    - 텍스트에서 할일 관련 패턴 추출 (정규식 + LLM):
      ```python
      ACTION_PATTERNS = [
          r"해야\s*(합니다|함|할\s*것)",
          r"까지\s*(완료|제출|보고)",
          r"담당[:\s]*([\w]+)",
          r"기한[:\s]*([\d/\-]+)",
          r"TODO[:\s]*(.*)",
          r"\[ \]\s*(.*)",  # 체크박스 형식
      ]
      ```
    - + LLM으로 추가 추출 (패턴으로 못 잡는 것)
  - `template` action: 회의 유형별 빈 양식 제공
    ```python
    MEETING_TEMPLATES = {
        "일반": "# 회의록\n\n## 기본 정보\n- 날짜: \n- 참석자: \n...",
        "투자검토": "# 투자 검토 회의록\n\n## 검토 종목\n...",
        "기획회의": "# 기획 회의록\n\n## 안건\n...",
    }
    ```
- **환경변수**: 없음
- **의존 라이브러리**: 없음 (순수 파이썬 + LLM)
- **agents.yaml 배정**: `cpo_manager`, `editor_specialist`, `archive_specialist`

---

### [공통 도구 7] 자동 뉴스레터 생성기 (`src/tools/newsletter_builder.py`)
- **tool_id**: `newsletter_builder`
- **클래스명**: `NewsletterBuilderTool`
- **소속**: 전사 공통 (CPO 관할)
- **하는 일**: 주간/월간 뉴스레터를 자동 생성
- **action 종류**:
  - `action="build"`: 뉴스레터 생성
    - `period`: "weekly", "monthly" (기본: "weekly")
    - `topic`: 뉴스레터 주제 (기본: "LEET/법학")
    - `sections`: 포함할 섹션 (쉼표 구분, 기본: "news,trends,community,tips")
  - `action="preview"`: 미리보기 (마크다운)
    - `newsletter_id`: 뉴스레터 ID
  - `action="templates"`: 사용 가능한 뉴스레터 템플릿 목록
- **구현 상세**:
  - 뉴스레터 템플릿 (Jinja2 스타일이지만 순수 파이썬 str.format으로 구현):
    ```python
    NEWSLETTER_TEMPLATE = """
    # 📰 CORTHEX 위클리 — {period_label}

    > {intro_text}

    ---

    ## 📋 이번 주 주요 뉴스
    {news_section}

    ## 📊 트렌드 & 데이터
    {trends_section}

    ## 💬 커뮤니티 이야기
    {community_section}

    ## 💡 이번 주의 팁
    {tips_section}

    ---

    *이 뉴스레터는 CORTHEX AI가 자동 생성했습니다.*
    *구독 해지: [링크]*
    """
    ```
  - 섹션별 데이터 수집:
    - `news`: `data/` 폴더에서 최근 뉴스 분석 결과 파일 활용
      - 또는 `_llm_call()`로 "이번 주 LEET/법학 관련 주요 이슈" 생성
    - `trends`: 기존 트렌드 데이터 파일 활용 또는 LLM 생성
    - `community`: 커뮤니티 분석 결과 활용 또는 LLM 생성
    - `tips`: LLM으로 "이번 주 공부 팁" 생성
  - 생성된 뉴스레터는 `data/newsletters/` 폴더에 저장
    - 파일명: `newsletter_{period}_{date}.md`
  - HTML 버전도 동시 생성 (이메일 발송용):
    - 간단한 마크다운→HTML 변환 (정규식 기반)
    - 인라인 CSS 스타일 포함 (이메일 클라이언트 호환)
  - 결과를 `_llm_call()`로 "뉴스레터 품질 검토 + 제목 최적화" 분석
- **환경변수**: 없음
- **의존 라이브러리**: 없음 (순수 파이썬 + LLM)
- **agents.yaml 배정**: `cpo_manager`, `editor_specialist`, `content_specialist`

---

## 최종 체크리스트

모든 도구 작성 후 반드시 확인:

1. [ ] `src/tools/uptime_monitor.py` 생성 완료
2. [ ] `src/tools/security_scanner.py` 생성 완료
3. [ ] `src/tools/log_analyzer.py` 생성 완료
4. [ ] `src/tools/api_benchmark.py` 생성 완료
5. [ ] `src/tools/report_generator.py` 생성 완료
6. [ ] `src/tools/meeting_formatter.py` 생성 완료
7. [ ] `src/tools/newsletter_builder.py` 생성 완료
8. [ ] `src/tools/pool.py`에 7개 도구 전부 import + tool_classes에 등록
9. [ ] `config/tools.yaml`에 7개 도구 설정 추가:
   - `# ─── CTO 기술개발처 신규 도구 ───` 섹션에 4개
   - `# ─── CPO 출판기록처 신규 도구 ───` 섹션에 2개
   - `# ─── 전사 공통 도구 ───` 섹션에 1개
10. [ ] `config/agents.yaml`에서 관련 에이전트의 `allowed_tools`에 추가:
    - CTO 도구: `cto_manager`, `backend_specialist`, `infra_specialist`
    - CPO 도구: `cpo_manager`, `editor_specialist`, `chronicle_specialist`, `archive_specialist`
    - 뉴스레터: `cpo_manager`, `editor_specialist`, `content_specialist`
11. [ ] 모든 파일에 한국어 docstring 포함
12. [ ] 로그 분석기: 표준 파이썬 로그 형식 파싱 지원
13. [ ] 보안 스캐너: pip-audit 없을 때 OSV API fallback
14. [ ] 보고서 생성기: 최소 3개 템플릿 (투자/시장/주간)
15. [ ] data/ 하위 폴더 자동 생성 (`Path.mkdir(parents=True, exist_ok=True)`)
16. [ ] 커밋 메시지: `feat: CTO+CPO+공통 신규 도구 7개 추가 (업타임/보안/로그/벤치마크/보고서/회의록/뉴스레터) [완료]`
17. [ ] 브랜치 `claude/corthex-improvements-kE0ii`에 push
