# youtube_analyzer — 유튜브 분석기 도구 가이드

## 이 도구는 뭔가요?
유튜브 채널의 영상 데이터를 수집하고 콘텐츠 전략을 분석하는 도구입니다.
"이 채널에서 어떤 영상이 잘 되나?", "LEET 관련 유튜브 콘텐츠 트렌드는?" 같은 질문에 답해줍니다.
채널 분석, 키워드 검색, 인기 동영상 분석 3가지 기능을 지원합니다.

## 어떤 API를 쓰나요?
- **yt-dlp** (Python 라이브러리) — 유튜브 메타데이터 추출 (영상을 다운로드하지 않고 정보만 가져옴)
- 비용: **무료**
- 필요한 키: 없음
- 필수 라이브러리: `yt-dlp` (`pip install yt-dlp`)

## 사용법

### action=channel (채널 분석)
```
action=channel, channel_url="채널URL", video_count=20
```
- `channel_url` (필수): 유튜브 채널 URL (예: "https://www.youtube.com/@channelname")
- `video_count` (선택, 기본 20, 최대 50): 분석할 최근 영상 개수

반환 정보:
- 분석 영상 수, 평균/중앙값/최고/최저 조회수
- 조회수 상위 5개 영상
- 조회수 하위 5개 영상

AI가 추가로 분석:
1. 잘 되는 영상의 공통 패턴 (제목, 주제, 형식)
2. 안 되는 영상의 공통 패턴
3. 콘텐츠 전략 제안
4. 벤치마킹 인사이트

**예시:**
- `action=channel, channel_url="https://www.youtube.com/@leet_channel"` → 채널 분석
- `action=channel, channel_url="https://www.youtube.com/@competitor", video_count=50` → 최근 50개 영상 분석

### action=search (키워드 영상 검색)
```
action=search, query="검색어", count=20
```
- `query` (필수): 유튜브에서 검색할 키워드
- `count` (선택, 기본 20, 최대 50): 검색 결과 개수

반환 정보: 영상 제목, 채널명, 조회수, 영상 길이, URL

AI가 추가로 분석:
1. 검색 결과에서 발견되는 트렌드/패턴
2. 조회수가 높은 영상의 공통 특징
3. 콘텐츠 기회 (경쟁이 적거나 수요가 높은 영역)
4. 우리가 만들 수 있는 콘텐츠 제안

**예시:**
- `action=search, query="LEET 해설"` → LEET 해설 관련 유튜브 영상 검색
- `action=search, query="로스쿨 합격 전략", count=30` → 로스쿨 관련 영상 30개 검색

### action=trending (인기 동영상)
```
action=trending, category="all"
```
- `category` (선택, 기본 "all"): `all`(전체) 또는 `education`(교육 카테고리)

반환 정보: 한국 기준 인기 동영상 상위 20개 (제목, 채널, 조회수)

AI가 추가로 분석:
1. 현재 유행하는 콘텐츠 주제/형식
2. 교육 분야 트렌드 (해당 시)
3. 벤치마킹할 만한 채널/콘텐츠

**예시:**
- `action=trending` → 한국 전체 인기 동영상 분석
- `action=trending, category="education"` → 교육 분야 인기 동영상

## 이 도구를 쓰는 에이전트들

### 1. 시장조사 Specialist
**언제 쓰나?** 유튜브 기반 콘텐츠 시장 조사
**어떻게 쓰나?**
- search로 키워드별 영상 현황 파악
- channel로 경쟁 채널 분석
- platform_market_scraper(플랫폼 시장)와 함께 온라인 교육 시장 종합 분석

### 2. 마케팅·고객처장 (CMO)
**언제 쓰나?** 유튜브 콘텐츠 마케팅 전략 수립
**어떻게 쓰나?**
- 경쟁사 유튜브 채널 벤치마킹
- trending으로 현재 유행 트렌드 파악
- "어떤 주제의 영상을 만들면 좋을지" 데이터 기반 제안

**실전 시나리오:**
> CEO가 "LEET 관련 유튜브 콘텐츠 현황 분석해줘" 라고 하면:
> 1. `action=search, query="LEET 해설", count=30` → LEET 관련 영상 30개 검색
> 2. 조회수 높은 영상의 공통점 분석 (제목 패턴, 영상 길이, 채널 규모)
> 3. `action=channel, channel_url="경쟁채널URL"` → 주요 경쟁 채널 상세 분석
> 4. "LEET 해설 영상은 10~15분 길이가 가장 조회수가 높고, '무료 해설' 키워드가 들어간 제목이 평균 2배 높은 조회수를 기록합니다. 우리도 무료 맛보기 해설 시리즈를 만들면 효과적입니다" 식의 구체적 제안

## 주의사항
- `yt-dlp` 라이브러리가 설치되어 있어야 함 (`pip install yt-dlp`)
- 영상을 다운로드하지 않고 **메타데이터(제목, 조회수 등)만** 가져옴
- 채널 URL 형식: `https://www.youtube.com/@채널이름` 또는 `https://www.youtube.com/channel/채널ID`
- 유튜브 정책 변경 시 데이터 추출이 안 될 수 있음
- 비공개 영상이나 삭제된 영상은 수집 불가
- 조회수가 0으로 나오는 경우 메타데이터 추출 문제일 수 있음 (실제 조회수가 0이 아닐 수 있음)
- trending 기능은 한국(KR) 기준으로 설정됨
