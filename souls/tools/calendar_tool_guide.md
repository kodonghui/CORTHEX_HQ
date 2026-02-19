# calendar_tool — 캘린더 도구 가이드

## 이 도구는 뭔가요?
Google Calendar(구글 캘린더)와 연동하여 일정을 조회하고, 새 일정을 만들고, 수정하고, 삭제하는 도구입니다.
향후 며칠간의 일정을 한눈에 보거나, 키워드로 일정을 검색하거나, 비어있는 시간대를 확인할 수도 있습니다.

## 어떤 API를 쓰나요?
- **Google Calendar API v3** (https://developers.google.com/calendar)
- 비용: **무료** (Google Workspace/개인 Gmail 계정으로 사용 가능)
- 필요한 키: `GOOGLE_CALENDAR_CREDENTIALS` (Google OAuth 인증 JSON 파일 경로)

## 사용법

### action=list (일정 조회)
```
action=list, days=7
```
- 오늘부터 지정한 일수만큼의 일정을 시간순으로 보여줍니다
- days: 조회 기간 (기본값 7일)
- 반환: 날짜/시간, 일정 제목, 장소 정보가 표로 정리됨

**예시:**
- `action=list, days=3` → 향후 3일간 일정 목록
- `action=list, days=30` → 이번 달 전체 일정

### action=create (새 일정 생성)
```
action=create, title="일정 제목", start="2026-02-20T10:00:00+09:00", end="2026-02-20T11:00:00+09:00", description="설명", location="장소"
```
- Google Calendar에 새 일정을 만듭니다
- title: 일정 제목 (필수)
- start: 시작 시간 (필수, ISO 8601 형식)
- end: 종료 시간 (선택, 미지정 시 시작 후 1시간)
- description: 일정 설명 (선택)
- location: 장소 (선택)
- 반환: 생성된 일정의 ID, 링크

**예시:**
- `action=create, title="투자위원회 회의", start="2026-02-20T14:00:00+09:00", location="회의실A"` → 2/20 오후 2시 회의 생성

### action=update (일정 수정)
```
action=update, event_id="이벤트ID", title="수정된 제목", start="새 시작시간"
```
- 기존 일정의 제목, 시간, 설명, 장소를 수정합니다
- event_id: 수정할 일정의 ID (필수, list나 search에서 확인 가능)
- 나머지: 변경할 항목만 입력 (입력하지 않은 항목은 유지)

**예시:**
- `action=update, event_id="abc123", title="투자위원회 회의 (연기)", start="2026-02-21T14:00:00+09:00"` → 회의를 하루 뒤로 연기

### action=delete (일정 삭제)
```
action=delete, event_id="이벤트ID"
```
- 일정을 삭제합니다
- event_id: 삭제할 일정의 ID (필수)

### action=search (일정 검색)
```
action=search, query="검색어"
```
- 키워드로 일정을 검색합니다
- 반환: 검색된 일정 목록 (제목, 시간, ID)

**예시:**
- `action=search, query="회의"` → "회의"가 포함된 모든 일정 검색

### action=free (빈 시간 조회)
```
action=free, days=3, work_start=9, work_end=18
```
- 지정 기간 내 비어있는 시간대를 확인합니다
- days: 조회 기간 (기본값 3일)
- work_start/work_end: 업무 시간 (기본값 9시~18시)

## 이 도구를 쓰는 에이전트들

### 1. 비서실장 (chief_of_staff)
**언제 쓰나?** CEO 일정 관리, 회의 예약, 일정 충돌 확인
**어떻게 쓰나?**
- list로 CEO의 주간 일정을 파악하고 보고
- create로 회의/미팅 일정 등록
- free로 새 미팅을 잡을 수 있는 빈 시간 확인

**실전 시나리오:**
> CEO가 "이번 주 일정 알려줘" 라고 하면:
> 1. `action=list, days=7`로 이번 주 일정 조회
> 2. 표로 정리해서 보고

### 2. 일정 보좌관 (schedule_specialist)
**언제 쓰나?** 일정 전문 관리 — 일정 충돌 방지, 최적 시간대 추천
**어떻게 쓰나?**
- list + free를 조합하여 최적의 미팅 시간 추천
- notification_engine과 연동하여 일정 알림 발송

**실전 시나리오:**
> CEO가 "다음 주에 3시간짜리 회의를 잡아줘" 라고 하면:
> 1. `action=free, days=7`로 다음 주 빈 시간 확인
> 2. 3시간 연속 비어있는 시간대를 찾아서 추천
> 3. CEO가 승인하면 `action=create`로 일정 생성

## 주의사항
- Google Calendar API 인증(OAuth)이 완료되어야 사용 가능합니다
- GOOGLE_CALENDAR_CREDENTIALS 환경변수에 인증 JSON 파일 경로를 설정해야 합니다
- 시간은 반드시 ISO 8601 형식으로 입력해야 합니다 (예: 2026-02-20T10:00:00+09:00)
- 시간대는 Asia/Seoul (한국 시간, UTC+9) 기준으로 자동 설정됩니다
- free 액션의 상세한 빈 시간 계산은 추후 Google FreeBusy API 연동으로 개선 예정입니다
