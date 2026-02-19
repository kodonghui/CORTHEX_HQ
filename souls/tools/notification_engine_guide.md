# notification_engine — 알림 엔진 도구 가이드

## 이 도구는 뭔가요?
텔레그램이나 이메일로 자동 알림을 보내주는 도구입니다.
CEO에게 긴급 뉴스, 주식 알림, 일일 보고서 등을 텔레그램 메시지로 즉시 전달하거나, 미리 만들어둔 템플릿(양식)을 사용해서 정형화된 알림을 보낼 수 있습니다.
보낸 알림의 이력(기록)도 자동으로 저장되어 나중에 확인할 수 있습니다.

## 어떤 API를 쓰나요?
- **Telegram Bot API** — 텔레그램 메시지 발송 (https://api.telegram.org)
- 비용: **무료** (텔레그램 Bot API는 무료)
- 필요한 키: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CEO_CHAT_ID`

## 사용법

### action=send (즉시 알림 발송)
```
action=send, message="알림 내용", channel="telegram", title="알림 제목(선택)"
```
- 텔레그램 또는 이메일로 즉시 알림을 보냅니다
- channel: "telegram" (기본값), "email", "all" (둘 다)
- title: 알림 제목 (굵은 글씨로 표시, 선택사항)
- 반환: 채널별 발송 성공/실패 결과

**예시:**
- `action=send, message="삼성전자 5% 급등! 현재가 85,000원", title="주식 알림", channel="telegram"` → CEO 텔레그램으로 즉시 발송

### action=template (템플릿으로 발송)
```
action=template, template_name="stock_alert", variables={"stock": "삼성전자", "price": "85,000", "change": "+5%", "comment": "실적 호조"}, channel="telegram"
```
- 미리 정의된 알림 양식(템플릿)에 변수를 넣어서 정형화된 알림을 보냅니다
- 사용 가능한 템플릿:
  - **daily_report**: 일일 보고서 (변수: content, date)
  - **stock_alert**: 주식 알림 (변수: stock, price, change, comment)
  - **legal_alert**: 법률 알림 (변수: law_name, content, impact)
  - **competitor_alert**: 경쟁사 알림 (변수: competitor, content)
  - **system_alert**: 시스템 알림 (변수: alert_type, message, timestamp)
- 반환: 템플릿이 적용된 메시지 + 발송 결과

**예시:**
- `action=template, template_name="daily_report", variables={"content": "오늘 매출 120만원, 신규 가입 15명", "date": "2026-02-19"}` → 정형화된 일일 보고서 발송

### action=history (발송 이력 조회)
```
action=history, limit=20
```
- 최근 보낸 알림의 이력을 확인합니다
- limit: 조회할 건수 (기본값 20, 최대 500건 저장)
- 반환: 시간, 채널, 메시지 요약, 결과를 표로 보여줌

**예시:**
- `action=history, limit=10` → 최근 10건의 알림 발송 기록 조회

## 이 도구를 쓰는 에이전트들

### 1. 비서실장 (chief_of_staff)
**언제 쓰나?** CEO에게 긴급 보고, 일일 요약, 중요 이벤트 알림을 보낼 때
**어떻게 쓰나?**
- send로 긴급 상황 즉시 알림 (서버 다운, 중요 뉴스 등)
- template의 daily_report로 매일 업무 요약 발송
- history로 최근 알림 이력 확인

**실전 시나리오:**
> CEO가 "매일 아침 9시에 어제 요약 보내줘" 라고 하면:
> 1. 전날 주요 이벤트를 취합
> 2. `action=template, template_name="daily_report"`로 정형화된 보고서 발송
> 3. CEO 텔레그램에 아침마다 도착

### 2. 일정 보좌관 (schedule_specialist)
**언제 쓰나?** 일정 알림, 회의 리마인더(미리 알림), 마감 경고
**어떻게 쓰나?**
- send로 "30분 뒤 회의 시작" 같은 리마인더 발송
- calendar_tool과 연동하여 일정 변경 시 자동 알림

**실전 시나리오:**
> 캘린더에 등록된 회의 30분 전:
> 1. calendar_tool로 오늘 일정 확인
> 2. `action=send, message="30분 뒤 투자위원회 회의 (14:00, 회의실A)", title="일정 알림"` 발송

### 3. 기술개발처장 (CTO, cto_manager)
**언제 쓰나?** 서버 장애, 배포 완료, 시스템 이상 감지 시 기술 알림
**어떻게 쓰나?**
- template의 system_alert로 서버 상태 알림
- send로 배포 성공/실패 알림

### 4. 마케팅/고객처장 (CMO, cmo_manager)
**언제 쓰나?** 경쟁사 동향 변화, SNS 반응 급변, 캠페인 결과 알림
**어떻게 쓰나?**
- template의 competitor_alert로 경쟁사 변화 감지 알림
- send로 SNS 캠페인 주요 지표 알림

### 5. 투자분석처장 (CIO, cio_manager)
**언제 쓰나?** 급등/급락 종목 알림, 리스크 경보, 시황 급변 알림
**어떻게 쓰나?**
- template의 stock_alert로 종목 변동 알림
- send로 긴급 리스크 경보 발송

**실전 시나리오:**
> 모니터링 중인 종목이 5% 이상 급변하면:
> 1. `action=template, template_name="stock_alert", variables={"stock": "SK하이닉스", "price": "195,000", "change": "+5.2%", "comment": "HBM4 양산 속보 영향"}` 발송

## 주의사항
- 텔레그램 발송에는 TELEGRAM_BOT_TOKEN과 TELEGRAM_CEO_CHAT_ID가 반드시 필요합니다
- 이메일 발송은 현재 email_sender 도구로 안내됩니다 (직접 SMTP 발송은 미구현)
- 알림 이력은 최근 500건만 저장됩니다 (오래된 기록은 자동 삭제)
- 텔레그램 메시지는 Markdown 형식을 지원합니다 (*굵게*, _기울임_ 등)
- 대량 알림 발송 시 텔레그램 API 속도 제한(Rate Limit)에 주의하세요
