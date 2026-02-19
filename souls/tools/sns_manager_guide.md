# sns_manager — SNS 매니저 도구 가이드

## 이 도구는 뭔가요?
Tistory, YouTube, Instagram, 네이버카페, 네이버블로그, 다음카페 등 여러 SNS 플랫폼에 글/영상/이미지를 한 번에 올릴 수 있는 통합 퍼블리싱(발행) 도구입니다.
CEO 승인 없이는 실제 발행이 안 되는 안전장치(승인 큐)가 내장되어 있습니다.
콘텐츠 Specialist가 작성 → CMO가 검토 → CEO가 승인 → CMO가 발행하는 워크플로우입니다.

## 어떤 API를 쓰나요?
- **Instagram Graph API** (공식 API, OAuth 인증)
- **YouTube Data API v3** (공식 API, OAuth 인증)
- **네이버 카페 API** (Official API, OAuth 인증)
- **Tistory** (Selenium 기반 — 카카오 로그인으로 자동 발행)
- **네이버 블로그** (Selenium 기반 — 네이버 로그인으로 자동 발행)
- **다음 카페** (Selenium 기반 — 다음 로그인으로 자동 발행)
- 비용: **무료** (각 플랫폼 API 무료 한도 내)
- 필요한 키: `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_ACCESS_TOKEN`, `KAKAO_ID`, `KAKAO_PW`, `NAVER_ID`, `NAVER_PW`, `DAUM_ID`, `DAUM_PW` 등 (플랫폼별 상이)

## 사용법

### action=submit (발행 요청 — 승인 큐에 등록)
```
action="submit", platform="tistory", title="제목", body="본문 내용", tags=["태그1","태그2"]
```
- 콘텐츠를 CEO 승인 대기 큐에 등록합니다
- 아직 실제로 발행되지 않음 — CEO 승인이 필요합니다
- 등록 시 AI가 콘텐츠 요약을 자동 생성하여 CEO 보고용으로 준비합니다
- 반환: request_id (이 ID로 승인/거절/발행 진행)

**예시:**
- `action="submit", platform="tistory", title="LEET 준비 가이드", body="..."` → 승인 대기 큐에 등록됨

### action=approve (CEO 승인)
```
action="approve", request_id="abc12345"
```
- CEO가 대기 중인 발행 요청을 승인합니다
- 승인 후 CMO가 publish 액션으로 실제 발행합니다

### action=reject (CEO 거절)
```
action="reject", request_id="abc12345", reason="제목 수정 필요"
```
- CEO가 발행 요청을 거절합니다
- 거절 사유를 함께 전달합니다

### action=publish (실제 발행 — CMO 이상만 가능)
```
action="publish", request_id="abc12345"
```
- 승인된 요청을 해당 SNS 플랫폼에 실제로 발행합니다
- CMO(마케팅처장) 또는 비서실장만 실행 가능 — 다른 에이전트는 권한 없음
- 반환: 발행 성공 여부, 게시물 URL, 게시물 ID

### action=queue (승인 대기 큐 조회)
```
action="queue"
```
- 현재 대기/승인/발행/거절된 모든 요청 목록을 보여줍니다
- 상태별로 분류: pending(대기), approved(승인), published(발행), rejected(거절)

### action=status (플랫폼 연결 상태 조회)
```
action="status"
```
- 각 SNS 플랫폼의 연결(인증) 상태를 확인합니다
- OAuth 인증 플랫폼: 토큰 만료 여부 표시
- Selenium 플랫폼: credential(로그인 정보) 존재 여부 표시

### action=auth_url (OAuth 인증 URL 생성)
```
action="auth_url", platform="instagram"
```
- OAuth 인증이 필요한 플랫폼의 인증 URL을 생성합니다

### action=exchange_code (OAuth 코드 교환)
```
action="exchange_code", platform="instagram", code="인증코드"
```
- OAuth 인증 코드를 액세스 토큰으로 교환합니다

## 이 도구를 쓰는 에이전트들

### 1. CMO 마케팅처장 (cmo_manager)
**언제 쓰나?** 콘텐츠 발행 검토/실행, 전체 SNS 전략 관리 시
**어떻게 쓰나?**
- 콘텐츠 Specialist가 submit한 요청을 검토
- CEO 승인 후 publish 액션으로 실제 발행 실행 (publish 권한 보유)
- status로 전체 SNS 연결 상태 모니터링
- queue로 발행 대기/완료 현황 파악

**실전 시나리오:**
> CEO가 "이번 주 블로그 글 올려줘" 라고 하면:
> 1. 콘텐츠 Specialist에게 글 작성 지시
> 2. Specialist가 `action=submit, platform="tistory"` 로 큐에 등록
> 3. CEO에게 승인 요청 보고
> 4. CEO 승인 후 CMO가 `action=publish` 실행

### 2. 콘텐츠 Specialist (content_specialist)
**언제 쓰나?** 작성한 콘텐츠를 발행 요청할 때
**어떻게 쓰나?**
- submit 액션만 사용 (발행 권한 없음)
- 글/이미지/영상 콘텐츠를 승인 큐에 등록

**실전 시나리오:**
> CMO가 "인스타그램에 올릴 이미지 게시물 준비해" 라고 하면:
> 1. 콘텐츠 작성 완료 후 `action=submit, platform="instagram"` 실행
> 2. AI가 자동 요약 생성 → CEO 보고 준비 완료

### 3. 커뮤니티 Specialist (community_specialist)
**언제 쓰나?** 커뮤니티(카페) 게시물 발행 요청 시
**어떻게 쓰나?**
- submit으로 네이버카페/다음카페 게시물 발행 요청
- 커뮤니티 반응 모니터링 후 추가 게시물 요청

### 4. 비서실장 (chief_of_staff)
**언제 쓰나?** 긴급 공지나 CEO 직접 요청 발행 시
**어떻게 쓰나?**
- publish 권한 보유 (CMO와 동일)
- 긴급 상황 시 CMO 대신 발행 가능

## 지원 플랫폼

| 플랫폼 | 인증 방식 | 필요 키/정보 |
|--------|----------|-------------|
| Tistory | Selenium (카카오 로그인) | `KAKAO_ID`, `KAKAO_PW` |
| YouTube | OAuth 2.0 | Google OAuth 설정 |
| Instagram | OAuth / Graph API | `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET` |
| 네이버 카페 | Official API | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` + club_id, menu_id |
| 네이버 블로그 | Selenium (네이버 로그인) | `NAVER_ID`, `NAVER_PW` |
| 다음 카페 | Selenium (다음 로그인) | `DAUM_ID`, `DAUM_PW` |

## 주의사항
- **CEO 승인 없이 publish 절대 불가** — submit → approve → publish 순서 필수
- **publish 권한은 CMO, 비서실장만 보유** — 다른 에이전트가 실행하면 권한 오류 발생
- **미지원 플랫폼**: Twitter/X, Facebook, Threads — 이 플랫폼들은 현재 지원하지 않으므로 보고서나 제안에 절대 포함하지 말 것
- 승인 큐 데이터는 SQLite DB에 저장되어 배포(서버 재시작)해도 유지됩니다
- Selenium 기반 플랫폼(Tistory, 네이버블로그, 다음카페)은 로그인 세션 만료 시 재로그인 필요
