# api_benchmark — API 성능 측정기 도구 가이드

## 이 도구는 뭔가요?
우리 서비스의 API(서버에 데이터를 요청하는 통로)가 얼마나 빠르게 응답하는지 측정하는 도구입니다.
같은 요청을 여러 번 반복해서 평균 속도, 가장 빠른/느린 속도, 성공률을 계산하고,
병목(느린 지점)을 찾아서 성능 개선 방향을 제시합니다.

## 어떤 API를 쓰나요?
- **HTTP 요청** (httpx 라이브러리)
- 지정된 URL에 반복 접속하여 응답 시간을 측정합니다
- AI 분석에서 LLM 호출이 발생합니다
- 비용: **무료** (측정 자체는 무료, AI 분석에 약간의 API 비용)
- 필요한 키: 없음

## 사용법

### action=single (단일 API 엔드포인트 측정)
```
action=single, url="https://corthex-hq.com/api/health", method="GET", iterations=5
```
- 하나의 URL을 여러 번 호출하여 성능을 측정합니다
- `url`: 측정할 API 주소 (필수)
- `method`: HTTP 메서드 (기본값: "GET", 선택: "POST", "PUT" 등)
- `iterations`: 반복 횟수 (기본값: 5회)
- 결과: 평균 응답시간, P50(중앙값), P95, P99, 최소/최대, 성공률

**예시:**
- `action=single, url="https://corthex-hq.com", iterations=10` → 10회 측정 후 "평균 350ms, P95 520ms, 성공률 100%"
- `action=single, url="https://corthex-hq.com/api/agents", method="GET"` → 에이전트 API 속도 측정

### action=benchmark (등록된 도구들의 성능 측정)
```
action=benchmark, tools="all", iterations=3
```
- CORTHEX HQ에 등록된 내부 도구들의 테스트 케이스를 확인합니다
- `tools`: 측정할 도구 (기본값: "all" = 전체, 또는 "kr_stock,naver_news" 형식으로 지정)
- `iterations`: 반복 횟수 (기본값: 3회)
- 사전 정의된 테스트 케이스가 있는 도구: kr_stock, dart_api, naver_news, web_search, translator, github_tool, daum_cafe, naver_datalab, ecos_macro

**예시:**
- `action=benchmark, tools="kr_stock,naver_news"` → 주식/뉴스 도구의 테스트 케이스 확인
- `action=benchmark` → 전체 9개 도구의 테스트 케이스 확인

### action=report (전체 성능 보고서)
```
action=report
```
- 이전에 측정한 결과들을 종합하여 성능 보고서를 생성합니다
- 최근 20건의 측정 기록을 보여줍니다
- AI가 병목 지점을 식별하고 성능 개선 우선순위를 제안합니다

**예시:**
- `action=report` → 최근 측정 이력 + AI 성능 분석 보고서

## 이 도구를 쓰는 에이전트들

### 1. 기술개발처장 (CTO)
**언제 쓰나?** 서비스 성능 전체 점검, CEO에게 성능 현황 보고 시
**어떻게 쓰나?**
- `action=report`로 전체 성능 현황 파악
- 정기적으로 `action=single`로 주요 엔드포인트 성능 추적

**실전 시나리오:**
> CEO가 "서비스가 좀 느린 것 같아" 라고 하면:
> 1. `action=single, url="https://corthex-hq.com"` 으로 메인 페이지 속도 측정
> 2. `action=single, url="https://corthex-hq.com/api/chat"` 으로 채팅 API 속도 측정
> 3. 측정 결과를 비교하여 "메인 페이지 350ms(정상), 채팅 API 2100ms(느림)" 보고

### 2. 백엔드/API Specialist
**언제 쓰나?** API 성능 최적화 작업 시, 코드 변경 후 성능 비교 시
**어떻게 쓰나?**
- 코드 수정 전후로 `action=single`을 실행하여 성능 변화 비교
- `action=benchmark`로 내부 도구들의 상태 점검

**실전 시나리오:**
> API 최적화 후 효과를 측정할 때:
> 1. 수정 전 `action=single, url="...", iterations=10`으로 기준값 측정
> 2. 코드 수정 후 같은 조건으로 재측정
> 3. "평균 응답시간 800ms → 200ms로 75% 개선" 보고

### 3. DB/인프라 Specialist
**언제 쓰나?** 서버 성능 저하 원인 파악, 인프라 변경 후 성능 확인 시
**어떻게 쓰나?**
- `action=single`로 여러 엔드포인트를 순차 측정하여 병목 지점 파악
- `action=report`로 시간에 따른 성능 변화 추적

**실전 시나리오:**
> 서버 성능이 저하된 것 같을 때:
> 1. 주요 API 5개를 `action=single`로 각각 측정
> 2. P95(100번 중 95번째로 느린 응답) 기준으로 병목 식별
> 3. "DB 조회 API가 P95 3초로 가장 느림 — 인덱스 추가 필요" 진단

## 주의사항
- 각 반복 호출 사이에 0.5초 간격을 두어 서버에 과부하를 주지 않습니다
- 측정 결과는 `data/benchmark_results.json`에 저장됩니다 (최대 100건)
- P50은 중앙값(절반이 이 속도 이하), P95는 100번 중 95번째 속도, P99는 100번 중 99번째 속도입니다
- 타임아웃은 30초로 설정되어 있습니다 (30초 내 응답 없으면 실패 처리)
- 네트워크 상태, 서버 부하 등에 따라 같은 API도 측정할 때마다 결과가 달라질 수 있습니다
- `action=benchmark`의 도구 테스트는 테스트 케이스 확인까지만 하며, 실제 실행은 ToolPool을 통해야 합니다
