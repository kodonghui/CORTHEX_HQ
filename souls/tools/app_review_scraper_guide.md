# app_review_scraper — 앱 리뷰 수집기 도구 가이드

## 이 도구는 뭔가요?
구글 플레이스토어에서 앱 리뷰를 대량으로 수집하고 분석하는 도구입니다.
별점 분포, 인기 리뷰, 불만 사항 TOP 5 등을 자동으로 정리해줍니다.
경쟁 앱 비교 분석도 가능합니다.
"경쟁 앱 리뷰가 어떤가?", "사용자들이 뭘 가장 불만스러워하나?" 같은 질문에 답해줍니다.

## 어떤 API를 쓰나요?
- **google-play-scraper** (Python 라이브러리) — 구글 플레이스토어 리뷰 크롤링
- 비용: **무료**
- 필요한 키: 없음
- 필수 라이브러리: `google-play-scraper` (`pip install google-play-scraper`)

## 사용법

### action=reviews (리뷰 수집)
```
action=reviews, app_id="앱패키지명", count=100, lang="ko", sort="newest"
```
- `app_id` (필수): 구글 플레이스토어 앱 패키지명 (예: "com.megastudy.leet")
- `count` (선택, 기본 100, 최대 500): 수집할 리뷰 개수
- `lang` (선택, 기본 "ko"): 리뷰 언어
- `sort` (선택, 기본 "newest"): 정렬 방식. `newest`(최신순) 또는 `rating`/`relevance`(관련도순)

반환 정보:
- 별점 분포 (5점~1점 각각 몇 건, 비율%)
- 평균 별점
- 인기 리뷰 상위 10개 (좋아요 많은 순)

**예시:**
- `action=reviews, app_id="com.megastudy.leet"` → 메가스터디 LEET 앱 리뷰 100건
- `action=reviews, app_id="com.example.app", count=300, sort="newest"` → 최신 리뷰 300건

### action=analyze (리뷰 분석)
```
action=analyze, app_id="앱패키지명", count=200
```
- `app_id` (필수): 분석할 앱 패키지명
- `count` (선택, 기본 200, 최대 500): 분석할 리뷰 개수

리뷰를 수집한 뒤 AI가 종합 분석:
1. 핵심 불만 사항 TOP 5
2. 칭찬 포인트 TOP 3
3. 개선 우선순위 (시급한 순서대로)
4. 경쟁사 대비 차별화 포인트
5. 사업 관점에서의 시사점

**예시:**
- `action=analyze, app_id="com.megastudy.leet"` → LEET 앱 종합 분석 보고서

### action=compare (앱 비교 분석)
```
action=compare, app_ids="앱1패키지명,앱2패키지명"
```
- `app_ids` (필수): 비교할 앱 패키지명들 (쉼표 구분, 최소 2개, 최대 3개)

각 앱의 리뷰 100건씩 수집 후 AI가 비교 분석:
1. 각 앱의 강점/약점 비교표
2. 사용자가 선호하는 앱과 그 이유
3. 각 앱의 개선 기회
4. 사업 전략 시사점

**예시:**
- `action=compare, app_ids="com.app1,com.app2"` → 두 앱 리뷰 비교 분석
- `action=compare, app_ids="com.megastudy.leet,com.peet.app,com.jinhak.leet"` → 3개 앱 비교

## 이 도구를 쓰는 에이전트들

### 1. 시장조사 Specialist
**언제 쓰나?** 경쟁 앱의 사용자 반응 분석
**어떻게 쓰나?**
- analyze로 경쟁 앱의 강점/약점 파악
- compare로 경쟁 앱 간 비교 분석
- platform_market_scraper(플랫폼 시장 데이터)와 함께 종합 경쟁 분석

### 2. 설문/리서치 Specialist
**언제 쓰나?** 사용자 리서치 시 앱 리뷰 기반 인사이트 수집
**어떻게 쓰나?**
- 앱 리뷰에서 사용자 니즈(필요) 파악
- 설문 문항 설계 시 리뷰에서 나온 주요 이슈 반영

**실전 시나리오:**
> CEO가 "경쟁 LEET 앱들 리뷰 분석해줘" 라고 하면:
> 1. `action=compare, app_ids="com.mega.leet,com.peet.leet"` → 경쟁 앱 비교
> 2. 각 앱의 불만 사항과 칭찬 포인트 정리
> 3. "메가 앱은 콘텐츠는 좋지만 UI 불만이 많고, 피트 앱은 UI는 좋지만 콘텐츠가 부족합니다. 우리는 두 가지 다 잡으면 됩니다" 식의 전략 제안

## 주의사항
- `google-play-scraper` 라이브러리가 설치되어 있어야 함 (`pip install google-play-scraper`)
- 앱 패키지명(app_id)은 구글 플레이스토어 URL에서 확인 가능 (예: play.google.com/store/apps/details?id=**com.example.app**)
- **앱스토어(iOS)는 지원하지 않음** — 구글 플레이스토어만
- 리뷰 텍스트는 300자까지 수집됨
- 한 번에 최대 500건까지 수집 가능
- 구글 플레이스토어 정책 변경 시 수집이 안 될 수 있음
