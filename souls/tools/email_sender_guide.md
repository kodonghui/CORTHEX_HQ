# email_sender — 이메일 발송기 도구 가이드

## 이 도구는 뭔가요?
SMTP(이메일 전송 프로토콜)를 통해 이메일을 자동으로 보내주는 도구입니다.
단순 텍스트 이메일부터 HTML(디자인 이메일), 첨부파일 포함, AI 초안 작성, 템플릿 발송, 대량 발송까지 지원합니다.

## 어떤 API를 쓰나요?
- **SMTP 프로토콜** (aiosmtplib 라이브러리 사용)
- Gmail, Outlook 등 대부분의 이메일 서비스와 호환
- 비용: **무료** (이메일 서비스 제공자의 발송 한도 내)
- 필요한 키: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`

## 사용법

### action=send (이메일 발송)
```
action="send", to="recipient@example.com", subject="제목", body="본문 내용"
```
- 지정한 수신자에게 이메일을 발송합니다
- html=true 로 설정하면 HTML 형식 이메일 발송 가능
- attachments 파라미터로 첨부파일 추가 가능

**파라미터:**
- `to` (필수): 수신자 이메일 주소
- `subject` (필수): 이메일 제목
- `body` (필수): 이메일 본문
- `html` (선택): true면 HTML 이메일, 기본값 false(텍스트)
- `attachments` (선택): 첨부 파일 경로 목록

**예시:**
- `action="send", to="ceo@corthex.com", subject="주간 보고서", body="이번 주 성과를 보고드립니다..."` → 텍스트 이메일 발송
- `action="send", to="ceo@corthex.com", subject="뉴스레터", body="<h1>제목</h1><p>내용</p>", html=true` → HTML 이메일 발송

### action=draft (AI 초안 작성)
```
action="draft", purpose="프로젝트 진행 상황 보고", recipient_type="CEO", tone="비즈니스"
```
- AI가 목적에 맞는 이메일 초안을 자동으로 작성합니다
- 제목, 인사, 본문, 마무리 인사를 포함한 완성형 초안
- 초안을 수정한 뒤 send 액션으로 실제 발송 가능

**파라미터:**
- `purpose` (필수): 이메일 목적 (예: "미팅 일정 조율", "프로젝트 보고")
- `recipient_type` (선택): 수신자 유형 (예: "CEO", "파트너사", "고객"). 기본값 "일반"
- `tone` (선택): 톤 (예: "비즈니스", "친근한", "격식체"). 기본값 "비즈니스"
- `key_points` (선택): 핵심 내용 포인트

**예시:**
- `action="draft", purpose="투자 미팅 후속 메일", recipient_type="투자자", tone="격식체"` → 격식체 후속 이메일 초안 생성

### action=template (템플릿 발송)
```
action="template", template_name="weekly_report", variables={"date":"2026-02-19","content":"이번 주 성과..."}, to="ceo@corthex.com"
```
- 미리 정의된 템플릿에 변수를 채워서 이메일을 생성/발송합니다
- to 파라미터가 있으면 바로 발송, 없으면 미리보기만

**사용 가능 템플릿:**

| 템플릿명 | 용도 | 필요 변수 |
|---------|------|----------|
| weekly_report | 주간 보고서 | date, content |
| newsletter | 뉴스레터 | title, content |
| alert | 알림 | alert_type, message, timestamp |

**예시:**
- `action="template", template_name="alert", variables={"alert_type":"서버 장애","message":"응답 시간 초과","timestamp":"2026-02-19 14:00"}` → 알림 이메일 미리보기

### action=bulk (대량 발송)
```
action="bulk", recipients=["a@b.com","c@d.com"], subject="공지사항", body="본문"
```
- 여러 수신자에게 같은 이메일을 한 번에 발송합니다
- 레이트 리밋(과다 발송 방지)을 위해 발송 간 1초 간격을 둡니다
- 결과: 총 수신자 수, 성공/실패 수, 각 수신자별 결과

**예시:**
- `action="bulk", recipients=["user1@example.com","user2@example.com"], subject="이벤트 안내", body="..."` → 2명에게 동시 발송

## 이 도구를 쓰는 에이전트들

### 1. 비서실장 (chief_of_staff)
**언제 쓰나?** CEO 대신 이메일을 발송하거나, 사내 공지를 전달할 때
**어떻게 쓰나?**
- draft로 이메일 초안 작성 → CEO 확인 후 send로 발송
- template으로 정기 보고서 이메일 자동 발송
- bulk로 전체 팀원에게 공지 발송

**실전 시나리오:**
> CEO가 "파트너사에 미팅 일정 확인 메일 보내줘" 라고 하면:
> 1. `action="draft", purpose="미팅 일정 확인", recipient_type="파트너사"` 로 초안 생성
> 2. CEO에게 초안 보여드리고 확인 받기
> 3. `action="send", to="partner@example.com", subject="미팅 일정 확인", body="..."` 로 발송

## 주의사항
- SMTP 설정(`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`)이 환경변수에 등록되어 있어야 발송 가능
- Gmail 사용 시 "앱 비밀번호"(App Password)를 사용해야 함 (일반 비밀번호로는 발송 안됨)
- `aiosmtplib` 라이브러리가 설치되어 있어야 함 (미설치 시 오류 메시지 표시)
- 대량 발송 시 이메일 서비스 제공자의 일일 발송 한도 주의 (Gmail: 일 500통)
- HTML 이메일은 모든 이메일 클라이언트에서 동일하게 보이지 않을 수 있음
- 스팸 필터에 걸리지 않도록 제목과 본문에 주의 (email_optimizer 도구로 사전 점검 권장)
