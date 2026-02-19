# token_counter — 토큰 카운터 도구 가이드

## 이 도구는 뭔가요?
AI에게 보내는 텍스트가 "토큰(AI가 읽는 단위)"으로 몇 개인지 세어주고, 비용이 얼마나 드는지 예측해주는 도구입니다.
AI 모델은 글자가 아니라 "토큰" 단위로 비용을 계산하는데, 한국어 한 글자가 보통 1~3개의 토큰이 됩니다.
텍스트가 모델의 최대 한도를 넘을 때 자동으로 잘라주는 기능도 있고, 같은 텍스트를 여러 모델에서 토큰 수/비용이 어떻게 다른지 비교도 할 수 있습니다.

## 어떤 API를 쓰나요?
- **tiktoken** — OpenAI의 토큰 계산 라이브러리 (로컬에서 실행, API 호출 없음)
- **config/models.yaml** — 모델별 가격 정보를 읽어서 비용 계산
- 비용: **무료** (토큰 세는 것 자체는 무료. 실제 AI 호출은 안 함)
- 필요한 키: 없음

## 사용법

### action=count (토큰 수 계산)
```
action=count, text="토큰 수를 셀 텍스트", model="gpt-5-mini"
```
- 텍스트의 토큰 수, 글자 수, 글자/토큰 비율을 계산합니다
- model: 기준이 되는 AI 모델 (기본값: gpt-5-mini)
- 반환: 모델명, 글자 수, 토큰 수, 글자/토큰 비율

**예시:**
- `action=count, text="삼성전자의 2026년 1분기 실적 전망을 분석해주세요."` → 약 25~35토큰

### action=estimate_cost (비용 예측)
```
action=estimate_cost, text="비용을 예측할 텍스트", model="claude-sonnet-4-6", expected_output_tokens=1000
```
- 텍스트를 특정 모델에 보낼 때 예상 비용을 달러($)로 계산합니다
- expected_output_tokens: AI가 보낼 응답의 예상 토큰 수 (기본값: 1,000)
- 반환: 입력 토큰 수, 예상 출력 토큰 수, 입력/출력 각각의 비용, 총 예상 비용

**예시:**
- `action=estimate_cost, text="긴 보고서 내용...", model="claude-opus-4-6", expected_output_tokens=2000` → 입력 $0.03 + 출력 $0.06 = 총 $0.09 예상

### action=truncate (토큰 한도 맞춤 자르기)
```
action=truncate, text="매우 긴 텍스트...", max_tokens=4000, model="gpt-5-mini"
```
- 텍스트가 지정한 토큰 한도를 넘으면 한도에 맞게 잘라줍니다
- 이미 한도 내이면 원본 그대로 반환합니다
- 반환: 원본 토큰 수, 한도, 잘린 토큰 수, 자른 후의 텍스트

**예시:**
- `action=truncate, text="(매우 긴 문서)", max_tokens=4000` → 4,000토큰까지만 자른 텍스트 반환

### action=compare (모델별 토큰/비용 비교)
```
action=compare, text="비교할 텍스트", models="gpt-5-mini,claude-sonnet-4-6,claude-opus-4-6"
```
- 같은 텍스트를 여러 모델에서 토큰 수와 입력 비용이 어떻게 다른지 비교표를 보여줍니다
- 반환: 모델별 토큰 수, 입력 비용, 사용 인코딩 비교표

**예시:**
- `action=compare, text="CORTHEX HQ 분기 보고서 내용..."` → gpt-5-mini: 500토큰/$0.001, claude-sonnet-4-6: 480토큰/$0.002 등 비교

## 이 도구를 쓰는 에이전트들

### 1. 기술개발처장 (CTO, cto_manager)
**언제 쓰나?** AI 비용 관리, 에이전트별 토큰 사용량 분석, 프롬프트 최적화(길이 줄이기)
**어떻게 쓰나?**
- estimate_cost로 새 기능 추가 시 예상 비용 산출
- compare로 같은 작업을 더 저렴한 모델로 할 수 있는지 비교
- truncate로 API 한도를 넘는 텍스트를 자동 처리

**실전 시나리오:**
> CEO가 "이번 달 AI 비용이 너무 많이 나왔어" 라고 하면:
> 1. 자주 쓰는 프롬프트의 `action=estimate_cost`로 모델별 비용 산출
> 2. `action=compare`로 저렴한 모델 대안 제시
> 3. "CIO의 시스템 프롬프트를 sonnet에서 haiku로 바꾸면 월 $5 절약됩니다" 같은 구체적 제안

### 2. AI 모델 Specialist (ai_model_specialist)
**언제 쓰나?** 모델 교체 검토 시 비용 비교, 배치(일괄처리) 작업의 비용 사전 계산
**어떻게 쓰나?**
- compare로 신규 모델과 기존 모델의 토큰/비용 차이 분석
- estimate_cost로 배치 작업 전 전체 비용 예측
- count로 에이전트 시스템 프롬프트가 너무 긴지 확인

**실전 시나리오:**
> CEO가 "29명 에이전트 전체 배치 돌리면 얼마 드나?" 라고 하면:
> 1. 각 에이전트의 시스템 프롬프트를 `action=count`로 토큰 수 파악
> 2. `action=estimate_cost`로 29명 x 예상 출력 토큰으로 전체 비용 산출
> 3. "전체 배치 1회 예상 비용: $2.50" 같은 구체적 수치 보고

## 주의사항
- 토큰 계산에 tiktoken 라이브러리가 필요합니다 (없으면 설치 안내 표시)
- Claude 모델의 정확한 토큰화는 tiktoken과 다를 수 있습니다 (근사값으로 참고)
- 비용 예측은 config/models.yaml의 가격 기준이며, 실제 과금은 다를 수 있습니다
- 한국어는 영어보다 토큰당 글자 수가 적습니다 (한국어 1자 = 약 1~3토큰, 영어 1단어 = 약 1~2토큰)
