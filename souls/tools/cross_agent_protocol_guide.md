# cross_agent_protocol — 에이전트 협업 프로토콜 도구 가이드

## 이 도구는 뭔가요?
CORTHEX HQ의 에이전트들이 서로 대화하고 협업할 수 있게 해주는 도구입니다.
에이전트 A가 에이전트 B에게 "이 작업 좀 해줘"라고 요청하거나, 전체 에이전트에게 정보를 공유하거나, 자기가 하던 작업을 다른 에이전트에게 넘기는(인계) 것이 가능합니다.
모든 요청과 응답은 데이터베이스(SQLite)에 기록되어 나중에 누가 누구에게 뭘 요청했는지 추적할 수 있습니다.

## 어떤 API를 쓰나요?
- **자체 구현** — SQLite DB (`cross_agent_messages` 테이블)에 메시지 저장
- **mini_server.py의 _call_agent 콜백** — request 액션 시 대상 에이전트를 실시간으로 호출
- 비용: **무료** (메시지 저장 자체는 무료. 실시간 에이전트 호출 시 해당 에이전트의 AI 모델 비용 발생)
- 필요한 키: 없음

## 사용법

### action=request (다른 에이전트에게 작업 요청)
```
action=request, to_agent="cio_manager", task="삼성전자 투자 분석해줘", context="최근 반도체 호황", priority="높음"
```
- 특정 에이전트에게 작업을 요청하고, 실시간으로 응답을 받습니다
- to_agent: 요청할 에이전트 ID (필수)
- task: 작업 내용 (필수)
- context: 배경 정보 (선택)
- priority: 긴급/높음/보통(기본값)/낮음
- 반환: 대상 에이전트의 실시간 응답 (콜백 등록 시), 또는 요청 대기 상태

**예시:**
- `action=request, to_agent="cio_manager", task="오늘 코스피 시황 분석해줘", priority="긴급"` → CIO가 실시간으로 시황 분석 응답

### action=broadcast (전체 에이전트에게 정보 공유)
```
action=broadcast, message="공유할 메시지", tags=["태그1", "태그2"]
```
- 모든 에이전트에게 정보를 공유합니다 (회의 결과, 중요 공지 등)

**예시:**
- `action=broadcast, message="CEO 결정: 2월 말까지 신규 기능 출시 목표", tags=["공지", "일정"]`

### action=handoff (작업 인계)
```
action=handoff, to_agent="대상에이전트", current_result="지금까지 작업 결과", next_task="다음에 해야 할 작업"
```
- 현재 진행 중인 작업을 다른 에이전트에게 넘깁니다

**예시:**
- `action=handoff, to_agent="content_specialist", current_result="시장 분석 데이터 수집 완료", next_task="이 데이터로 블로그 포스트 작성해줘"`

### action=respond (요청에 대한 응답)
```
action=respond, request_id="요청ID", response="응답 내용"
```
- 다른 에이전트의 request에 대해 응답을 등록합니다

### action=status (메시지 현황 조회)
```
action=status, agent_id="에이전트ID(선택)", type="request(선택)", limit=20
```
- 에이전트 간 메시지 현황을 조회합니다

### action=collect (결과 수집)
```
action=collect, request_ids="ID1,ID2,ID3"
```
- 여러 요청의 결과를 한번에 수집하고, AI가 종합 분석합니다

## 이 도구를 쓰는 에이전트들

이 도구는 **거의 모든 에이전트(29명)**에게 배정되어 있습니다. 조직 내 협업의 핵심 도구입니다.

### 주요 사용 패턴별 에이전트

#### 패턴 1: 총괄 조율 (비서실장)
**비서실장 (chief_of_staff)** — 가장 많이 사용
- request로 처장들에게 작업 배분
- collect로 여러 처장의 결과를 종합하여 CEO에게 보고
- broadcast로 CEO 결정 사항을 전체 공유

**실전 시나리오:**
> CEO가 "삼성전자에 투자해도 될까?" 라고 하면:
> 1. `action=request, to_agent="cio_manager", task="삼성전자 투자 분석"` (CIO에게)
> 2. `action=request, to_agent="clo_manager", task="삼성전자 관련 법적 리스크 확인"` (CLO에게)
> 3. `action=collect, request_ids="요청ID1,요청ID2"` (두 결과를 종합)
> 4. CEO에게 종합 보고

#### 패턴 2: 부서 간 협업 (처장급)
**CIO, CSO, CLO, CMO, CTO, CPO** 등 처장급 에이전트
- request로 다른 부서에 전문 분석 요청
- handoff로 자기 분석 결과를 다음 단계 담당자에게 인계

**실전 시나리오:**
> CIO가 투자 분석 중 법률 이슈를 발견하면:
> 1. `action=request, to_agent="clo_manager", task="이 기업의 소송 리스크 확인"` → CLO에게 법률 검토 요청
> 2. CLO 응답을 받아 투자 분석에 반영

#### 패턴 3: 작업 인계 (Specialist급)
**시장조사, 콘텐츠, 회사연대기 Specialist** 등
- handoff로 자기 단계의 작업 결과를 다음 단계에 넘김

## 주의사항
- 메시지는 SQLite DB(cross_agent_messages 테이블)에 영구 저장됩니다
- request 액션에서 실시간 에이전트 호출이 되려면 mini_server.py가 _call_agent 콜백을 등록해야 합니다
- 실시간 호출 시 대상 에이전트의 AI 모델 비용이 발생합니다
- 존재하지 않는 에이전트 ID를 to_agent에 지정하면 실시간 호출이 실패합니다
- collect 액션의 종합 분석은 AI를 호출하므로 추가 토큰 비용이 발생합니다
- broadcast는 실제로 모든 에이전트를 호출하지는 않습니다 — DB에 기록만 남기고, 에이전트가 나중에 조회하는 방식입니다
