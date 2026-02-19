# log_analyzer — 에러 로그 분석기 도구 가이드

## 이 도구는 뭔가요?
서버에서 발생하는 에러(오류) 기록을 자동으로 분석하는 도구입니다.
어떤 에러가 가장 많이 나는지, 언제 집중적으로 나는지, 어떤 모듈에서 나는지를 자동으로 세어주고,
AI가 원인을 추정해서 해결 방법까지 제안해줍니다.

## 어떤 API를 쓰나요?
- **로컬 로그 파일 분석** (외부 API 사용 없음)
- 서버의 `logs/corthex.log` 파일을 직접 읽고 분석합니다
- AI 분석 부분에서 LLM(대형 언어 모델) 호출이 발생합니다
- 비용: **무료** (파일 분석 자체는 무료, AI 분석에 약간의 API 비용)
- 필요한 키: 없음 (AI 분석은 시스템 내부 LLM 사용)

## 사용법

### action=analyze (로그 파일 전체 분석)
```
action=analyze, log_file="logs/corthex.log", level="ERROR", hours=24
```
- 로그 파일을 읽어서 전체적인 분석을 수행합니다
- `log_file`: 분석할 로그 파일 경로 (기본값: "logs/corthex.log")
- `level`: 분석할 로그 레벨 (기본값: "ERROR", 선택: "ALL", "WARNING", "CRITICAL" 등)
- `hours`: 최근 몇 시간의 로그를 분석할지 (기본값: 24시간)
- 레벨별 건수, 모듈별 분포, 에러 메시지 패턴 Top 10을 표시합니다
- AI가 근본 원인을 추정하고 해결 방법을 제안합니다

**예시:**
- `action=analyze, hours=48` → 최근 48시간의 에러 로그 분석 + AI 원인 추정
- `action=analyze, level="ALL"` → 모든 레벨(DEBUG~CRITICAL) 포함 분석

### action=top_errors (가장 많이 발생하는 에러 Top N)
```
action=top_errors, log_file="logs/corthex.log", top_n=10, hours=24
```
- 가장 자주 반복되는 에러 메시지를 순위별로 보여줍니다
- `top_n`: 몇 개까지 보여줄지 (기본값: 10)
- `hours`: 최근 몇 시간 기준 (기본값: 24시간)
- 에러 메시지에서 변하는 부분(IP, 시간, 숫자 등)은 자동으로 패턴화하여 같은 종류끼리 묶어줍니다
- AI가 각 에러의 원인과 해결 우선순위를 분석합니다

**예시:**
- `action=top_errors, top_n=5` → 에러 빈도 Top 5 + AI 해결 우선순위 분석

### action=timeline (시간대별 에러 발생 빈도)
```
action=timeline, log_file="logs/corthex.log", hours=24
```
- 24시간 기준으로 시간대별 에러 발생 건수를 텍스트 막대 그래프로 보여줍니다
- `hours`: 최근 몇 시간 기준 (기본값: 24시간)
- 피크(가장 많이 발생하는) 시간대를 자동으로 감지합니다

**예시:**
- `action=timeline` → "14시: ████████ (32건)" 형태의 시간대별 분포 그래프

## 이 도구를 쓰는 에이전트들

### 1. 기술개발처장 (CTO)
**언제 쓰나?** 서비스 안정성 점검, 에러 현황 CEO 보고, 장애 원인 분석 시
**어떻게 쓰나?**
- `action=analyze`로 전체 에러 현황 파악
- `action=timeline`으로 에러가 집중되는 시간대 확인

**실전 시나리오:**
> CEO가 "서비스 에러 많이 나?" 라고 하면:
> 1. `action=analyze, hours=168`로 최근 1주일 에러 분석
> 2. `action=top_errors`로 가장 많은 에러 Top 5 확인
> 3. CEO에게 "이번 주 에러 N건, 가장 많은 에러는 X이고 원인은 Y입니다" 보고

### 2. 백엔드/API Specialist
**언제 쓰나?** 특정 API에서 에러가 반복될 때, 새 기능 배포 후 에러 확인 시
**어떻게 쓰나?**
- `action=top_errors`로 반복 에러 패턴 파악
- `action=timeline`으로 에러 발생 시점과 배포 시점 교차 확인

**실전 시나리오:**
> 배포 후 에러가 의심될 때:
> 1. `action=analyze, hours=2`로 최근 2시간 에러 확인
> 2. 배포 전후 비교를 위해 `action=timeline`으로 시간대 분포 확인
> 3. 새로 생긴 에러가 있으면 원인 분석 후 수정

### 3. DB/인프라 Specialist
**언제 쓰나?** 서버 인프라 문제로 인한 에러 추적, 가용성(SRE) 분석 시
**어떻게 쓰나?**
- `action=analyze, level="CRITICAL"`로 치명적 에러만 필터링
- `action=timeline`으로 서버 다운타임 시간대 파악

**실전 시나리오:**
> 서버 불안정 신호가 감지될 때:
> 1. `action=analyze, level="CRITICAL"`로 치명적 에러 확인
> 2. `action=timeline`으로 에러 피크 시간대 파악
> 3. 서버 리소스(CPU/메모리) 로그와 교차 분석

## 주의사항
- 로그 파일이 없으면 자동으로 빈 파일을 생성합니다 (에러 없이 "로그가 없습니다" 반환)
- 표준 파이썬 로그 형식(`2026-02-19 14:30:00 - module - ERROR - 메시지`)만 파싱합니다
- 에러 메시지 패턴화 시 IP, URL, UUID, 숫자가 자동으로 치환됩니다 (같은 종류끼리 묶기 위해)
- AI 분석 결과는 추정이므로, 실제 원인 확인은 코드 레벨에서 해야 합니다
- 대용량 로그 파일(수백 MB)은 분석에 시간이 걸릴 수 있습니다
