# AI 모델 호환성 현황 (2026-02-23 기준)

> CORTHEX HQ에서 사용하는 모든 AI 모델의 도구 호출(Function Calling) 호환성 점검 결과.
> 이 문서는 `ai_handler.py`에서 자동 처리하는 내용을 정리한 것입니다.

---

## 🔴 핵심 규칙 (코드 수정 시 반드시 참고)

| # | 규칙 | 위반 시 증상 |
|---|------|------------|
| 1 | **GPT-5.2/5.2-pro + reasoning_effort 사용 시 → temperature 파라미터 전송 금지** | `400 Bad Request` — "temperature is not supported with reasoning_effort" |
| 2 | **GPT-5.2/5.2-pro strict 모드 → 모든 object에 `additionalProperties: false` + `required` 필수** | `400 Bad Request` — "strict mode requires..." |
| 3 | **GPT-5.2-pro → Responses API만 사용** (Chat Completions API 미지원) | `404 Not Found` — "model not found" |
| 4 | **Gemini → `anyOf`/`oneOf`/`$ref` 스키마 사용 금지** | 스키마 파싱 에러 |
| 5 | **Claude → `input_schema` 키 사용** / OpenAI → `parameters` 키 사용 | 도구 인식 실패 |

---

## 모델별 상세

### Claude (Anthropic)

| 항목 | 내용 |
|------|------|
| **사용 모델** | `claude-sonnet-4-6`, `claude-opus-4-6`, `claude-haiku-4-5-20251001` |
| **도구 포맷** | Anthropic 기본 포맷 (`name`, `description`, `input_schema`) |
| **reasoning** | Extended Thinking — `budget_tokens` 파라미터로 추론 깊이 조절 |
| **xhigh** | ✅ 지원 — `budget_tokens: 32000` |
| **temperature** | reasoning 사용 시 반드시 1.0 (SDK 내부 처리) |
| **strict mode** | 불필요 (Claude는 자체적으로 스키마 준수) |
| **스키마 제한** | 없음 — `anyOf`, `oneOf`, 재귀 등 모두 지원 |
| **CORTHEX 처리** | `_call_anthropic()` — 기본 포맷이므로 변환 없이 직접 전달 |

### GPT-5.2 (OpenAI — Chat Completions API)

| 항목 | 내용 |
|------|------|
| **사용 모델** | `gpt-5.2`, `gpt-5`, `gpt-5-mini` |
| **도구 포맷** | OpenAI Function Calling (`type: "function"`, `function.parameters`) |
| **reasoning** | `reasoning_effort` 파라미터 (low/medium/high/xhigh) |
| **xhigh** | ✅ 지원 — `reasoning_effort: "xhigh"` |
| **temperature** | ⚠️ reasoning_effort 사용 시 **전송 금지** (충돌 에러) |
| **strict mode** | ✅ 필수 — `function.strict: true` + 재귀적 `additionalProperties: false` |
| **스키마 제한** | `anyOf`/`oneOf` 제한적, 재귀 스키마 불가, `enum`에 null 불가 |
| **CORTHEX 처리** | `_apply_openai_strict_inline()` 재귀 적용 + reasoning 모델이면 temperature 미전송 |

### GPT-5.2 Pro (OpenAI — Responses API)

| 항목 | 내용 |
|------|------|
| **사용 모델** | `gpt-5.2-pro` |
| **도구 포맷** | Responses API 전용 (`type: "function"`, `name`, `parameters` — 최상위 레벨) |
| **reasoning** | `reasoning.effort` 파라미터 (low/medium/high/xhigh) |
| **xhigh** | ✅ 지원 — `reasoning: {"effort": "xhigh"}` |
| **temperature** | 파라미터 자체가 없음 (Responses API는 temperature 미지원) |
| **strict mode** | Chat Completions와 동일 (strict: true + additionalProperties) |
| **CORTHEX 처리** | `_call_openai_responses()` — Chat Completions 포맷에서 Responses 포맷으로 자동 변환 |

### Gemini 3.1 Pro (Google)

| 항목 | 내용 |
|------|------|
| **사용 모델** | `gemini-3.1-pro-preview`, `gemini-2.5-pro`, `gemini-2.5-flash` |
| **도구 포맷** | `FunctionDeclaration` (google-genai SDK 타입) |
| **reasoning** | reasoning_effort 파라미터 없음 — temperature로만 조절 |
| **xhigh** | ❌ 미지원 — reasoning_effort 있으면 temperature 1.0으로 대체 |
| **temperature** | 항상 사용 가능 (기본 0.7, reasoning 있으면 1.0) |
| **strict mode** | 불필요 |
| **스키마 제한** | ⚠️ `anyOf`/`oneOf`/`$ref`/재귀 스키마 **사용 불가** (OpenAPI 3.0 서브셋) |
| **CORTHEX 처리** | `_call_google()` — Anthropic 포맷(`input_schema`)에서 `FunctionDeclaration`으로 자동 변환 |

---

## 도구 스키마 호환성 매트릭스

| 스키마 기능 | Claude | GPT-5.2 | GPT-5.2-pro | Gemini |
|------------|--------|---------|-------------|--------|
| 단순 object | ✅ | ✅ | ✅ | ✅ |
| 중첩 object | ✅ | ✅ (strict 필요) | ✅ (strict 필요) | ✅ |
| array | ✅ | ✅ | ✅ | ✅ |
| enum | ✅ | ✅ (null 제외) | ✅ (null 제외) | ✅ |
| anyOf/oneOf | ✅ | ⚠️ 제한적 | ⚠️ 제한적 | ❌ |
| $ref (재귀) | ✅ | ❌ | ❌ | ❌ |
| additionalProperties | 선택 | 필수 false | 필수 false | 무시 |

> **현재 CORTHEX 도구 131개**: 모두 단순 object 스키마 사용 → **모든 모델에서 100% 호환**

---

## `ai_handler.py` 자동 처리 흐름

```
config/tools.yaml
    │
    ▼
_build_tool_schemas()  ──→  Anthropic 포맷 (기준)
    │                           │
    │                           ├──→ _apply_openai_strict_inline()  ──→  OpenAI 포맷
    │                           │         └── 재귀적으로 additionalProperties/required 추가
    │                           │
    │                           └──→ Google 변환 (_call_google 내부)  ──→  Gemini 포맷
    │                                     └── FunctionDeclaration 타입으로 변환
    │
    ▼
ask_ai()  ──→  프로바이더 자동 감지
    │
    ├── claude-*     → _call_anthropic()     [Anthropic 포맷 직접 사용]
    ├── gpt-5.2-pro  → _call_openai_responses() [Responses API 포맷]
    ├── gpt-*        → _call_openai()        [Chat Completions 포맷]
    └── gemini-*     → _call_google()        [Gemini 포맷 변환]
```

---

## reasoning_effort 처리 매트릭스

| reasoning_effort | Claude | GPT-5.2 | GPT-5.2-pro | Gemini |
|-----------------|--------|---------|-------------|--------|
| none/미지정 | 일반 모드 | 일반 모드 | 일반 모드 | temp 0.7 |
| low | budget 1,024 | reasoning_effort: low | reasoning.effort: low | temp 1.0 |
| medium | budget 8,192 | reasoning_effort: medium | reasoning.effort: medium | temp 1.0 |
| high | budget 16,000 | reasoning_effort: high | reasoning.effort: high | temp 1.0 |
| xhigh | budget 32,000 | reasoning_effort: xhigh | reasoning.effort: xhigh | temp 1.0 |

---

## ⚠️ 알려진 제한사항 (2026-02-23)

1. **GPT-5.2 도구 호출 실패율 ~6%**: OpenAI 측 문제. 재시도 로직으로 보완 (최대 10회 루프)
2. **Gemini 동기 API**: `asyncio.to_thread`로 비동기화. 응답 느릴 수 있음
3. **Claude extended thinking**: 첫 응답에 `signature` 필드 필수 (4.x SDK 자동 처리)

---

*마지막 업데이트: 2026-02-23 | 작성: Claude (ai_handler.py 코드 분석 기반)*
