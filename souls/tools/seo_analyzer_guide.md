# seo_analyzer — SEO 분석기 도구 가이드

## 이 도구는 뭔가요?
웹사이트가 구글/네이버 같은 검색엔진에서 잘 찾아지는지 자동으로 점검해주는 도구입니다.
메타태그, 콘텐츠 품질, 기술 요소, 성능 등 14개 항목을 100점 만점으로 점수를 매기고, 어떻게 개선해야 하는지 알려줍니다.

## 어떤 API를 쓰나요?
- **직접 HTTP 요청** (httpx + BeautifulSoup으로 웹페이지 HTML 분석)
- 외부 유료 API 없음 — 웹페이지를 직접 다운로드하여 분석
- 비용: **무료**
- 필요한 키: 없음

## 사용법

### action=audit (SEO 종합 감사)
```
action="audit", url="https://example.com"
```
- 웹페이지의 SEO 상태를 14개 항목으로 점검합니다
- 각 항목별 점수와 상세 설명 제공
- AI가 가장 시급히 개선해야 할 3가지와 구체적 수정 방법을 제시합니다

**점검 항목 (총 100점):**

| 카테고리 | 항목 | 배점 |
|---------|------|------|
| 기본 메타 (30점) | title 태그 | 10점 |
| | meta description | 10점 |
| | h1 태그 | 5점 |
| | heading 순서 | 5점 |
| 콘텐츠 (25점) | 본문 길이 | 10점 |
| | 키워드 밀도 | 10점 |
| | 이미지 alt 속성 | 5점 |
| 기술 (25점) | 모바일 viewport | 10점 |
| | canonical URL | 5점 |
| | robots.txt | 5점 |
| | sitemap.xml | 5점 |
| 성능 (20점) | 페이지 응답 시간 | 10점 |
| | HTML 크기 | 5점 |
| | 외부 링크 수 | 5점 |

**예시:**
- `action="audit", url="https://corthex-hq.com"` → SEO 점수 75/100 (등급 B), 개선안 3가지 제시

### action=keywords (키워드 밀도 분석)
```
action="keywords", url="https://example.com", target_keywords="LEET,로스쿨,법학"
```
- 지정한 키워드가 페이지 본문에 몇 번 나오는지, 밀도(비율)가 적절한지 분석합니다
- 키워드 밀도 1~3%가 적정, 5% 이상이면 스팸으로 인식될 수 있음
- AI가 밀도 조절 방법과 추가 키워드 5개를 추천합니다

**예시:**
- `action="keywords", url="https://blog.example.com/leet-guide", target_keywords="LEET,리트,법학적성시험"` → 각 키워드별 출현 횟수, 밀도(%), 평가

### action=compare (두 사이트 SEO 비교)
```
action="compare", url1="https://our-site.com", url2="https://competitor.com"
```
- 두 웹사이트의 SEO 점수를 14개 항목별로 나란히 비교합니다
- 어느 사이트가 더 유리한지, 서로 배울 점은 무엇인지 분석합니다
- 경쟁사 대비 우리 사이트의 강점/약점을 파악할 수 있습니다

**예시:**
- `action="compare", url1="https://corthex-hq.com", url2="https://competitor.com"` → 항목별 점수 비교 표 + AI 분석

## 이 도구를 쓰는 에이전트들

### 1. CMO 마케팅처장 (cmo_manager)
**언제 쓰나?** 웹사이트/블로그의 검색 노출 상태를 점검하고 개선 전략을 세울 때
**어떻게 쓰나?**
- audit로 자사 웹사이트 SEO 점수 확인
- compare로 경쟁사 대비 SEO 상태 비교
- keywords로 타겟 키워드 최적화 상태 확인
- 콘텐츠 Specialist에게 SEO 개선 방향 지시

**실전 시나리오:**
> CEO가 "우리 사이트가 검색에 잘 안 나오는데 왜 그런지 확인해줘" 라고 하면:
> 1. `action="audit", url="https://corthex-hq.com"` 실행
> 2. 점수가 낮은 항목 확인 (예: meta description 없음, sitemap 없음)
> 3. CEO에게 "현재 SEO 점수 58점(D등급), 가장 시급한 것은 meta description 추가입니다" 보고
> 4. CTO에게 기술적 수정 요청

## 주의사항
- 페이지 접근이 차단된 사이트(로그인 필요, 봇 차단)는 분석 불가
- 응답 시간 측정은 서버(Oracle Cloud)에서 측정한 값이므로 실제 사용자 체감 속도와 다를 수 있음
- JavaScript로 렌더링되는 SPA(Single Page Application) 사이트는 정확한 분석이 어려울 수 있음
- 키워드 밀도 분석 시 target_keywords를 지정하지 않으면 title 태그 기준으로 분석
