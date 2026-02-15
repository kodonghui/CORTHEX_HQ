"""
CORTHEX HQ - AI Handler (멀티 프로바이더)

Anthropic (Claude), Google (Gemini), OpenAI (GPT) 3개 프로바이더를 지원합니다.
모델명 접두사로 프로바이더를 자동 판별합니다:
  - claude-*  → Anthropic API
  - gemini-*  → Google Generative AI API
  - gpt-*     → OpenAI API

mini_server.py에서 import하여 사용합니다.
"""
import json
import os
import time
import logging

logger = logging.getLogger("corthex.ai")

# ── 프로바이더별 클라이언트 (선택적 로드) ──

# Anthropic
_anthropic_client = None
_anthropic_available = False
try:
    from anthropic import AsyncAnthropic
    _anthropic_available = True
except ImportError:
    logger.warning("anthropic 패키지 미설치")

# Google Gemini
_google_client = None
_google_available = False
try:
    from google import genai
    _google_available = True
except ImportError:
    logger.warning("google-genai 패키지 미설치")

# OpenAI
_openai_client = None
_openai_available = False
try:
    from openai import AsyncOpenAI
    _openai_available = True
except ImportError:
    logger.warning("openai 패키지 미설치")


# ── 모델 가격표 (1M 토큰당 USD) ──
_PRICING = {
    # Anthropic
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
    # Google Gemini
    "gemini-3-pro-preview": {"input": 2.50, "output": 15.00},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    # OpenAI
    "gpt-5.2-pro": {"input": 18.00, "output": 90.00},
    "gpt-5.2": {"input": 5.00, "output": 25.00},
    "gpt-5.1": {"input": 4.00, "output": 20.00},
    "gpt-5": {"input": 2.50, "output": 10.00},
    "gpt-5-mini": {"input": 0.50, "output": 2.00},
}

# ── 모델 라우팅 키워드 ──
_COMPLEX_KEYWORDS = [
    "분석", "보고서", "전략", "계획", "비교", "평가", "조사",
    "설계", "리포트", "검토", "진단", "예측",
]

# ── 분류 시스템 프롬프트 ──
_CLASSIFY_PROMPT = """당신은 업무 분류 전문가입니다.
CEO의 명령을 읽고 어느 부서가 처리해야 하는지 판단하세요.

## 부서 목록
- cto_manager: 기술개발 (코드, 웹사이트, API, 서버, 배포, 프론트엔드, 백엔드, 버그, UI, 디자인, 데이터베이스)
- cso_manager: 사업기획 (시장조사, 사업계획, 매출 예측, 비즈니스모델, 수익, 경쟁사)
- clo_manager: 법무IP (저작권, 특허, 상표, 약관, 계약, 법률, 소송)
- cmo_manager: 마케팅고객 (마케팅, 광고, SNS, 인스타그램, 유튜브, 콘텐츠, 브랜딩, 설문)
- cio_manager: 투자분석 (주식, 투자, 종목, 시황, 포트폴리오, 코스피, 나스닥, 차트, 금리)
- cpo_manager: 출판기록 (회사기록, 연대기, 블로그, 출판, 편집, 회고, 빌딩로그)
- chief_of_staff: 일반 질문, 요약, 일정 관리, 기타 (위 부서에 해당하지 않는 경우)

## 출력 형식
반드시 아래 JSON 형식으로만 답하세요. 다른 텍스트는 쓰지 마세요.
{"agent_id": "부서ID", "reason": "한줄 이유"}"""


def _get_provider(model: str) -> str:
    """모델명으로 프로바이더를 판별합니다."""
    if model.startswith("claude-"):
        return "anthropic"
    elif model.startswith("gemini-"):
        return "google"
    elif model.startswith("gpt-"):
        return "openai"
    return "anthropic"  # 알 수 없으면 기본값


def init_ai_client() -> bool:
    """모든 AI 클라이언트 초기화. 최소 1개라도 성공하면 True 반환."""
    global _anthropic_client, _google_client, _openai_client
    any_ok = False

    # Anthropic
    if _anthropic_available:
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if key:
            _anthropic_client = AsyncAnthropic(api_key=key)
            logger.info("Anthropic 클라이언트 초기화 완료")
            any_ok = True
        else:
            logger.warning("ANTHROPIC_API_KEY 미설정")

    # Google Gemini
    if _google_available:
        key = os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        if key:
            _google_client = genai.Client(api_key=key)
            logger.info("Google Gemini 클라이언트 초기화 완료")
            any_ok = True
        else:
            logger.warning("GOOGLE_API_KEY 미설정")

    # OpenAI
    if _openai_available:
        key = os.getenv("OPENAI_API_KEY", "")
        if key:
            _openai_client = AsyncOpenAI(api_key=key)
            logger.info("OpenAI 클라이언트 초기화 완료")
            any_ok = True
        else:
            logger.warning("OPENAI_API_KEY 미설정")

    if not any_ok:
        logger.warning("사용 가능한 AI 프로바이더가 없습니다")
    return any_ok


def is_ai_ready() -> bool:
    """최소 1개 AI 프로바이더가 사용 가능한 상태인지 확인."""
    return any([_anthropic_client, _google_client, _openai_client])


def get_available_providers() -> dict:
    """현재 사용 가능한 프로바이더 상태를 반환합니다."""
    return {
        "anthropic": _anthropic_client is not None,
        "google": _google_client is not None,
        "openai": _openai_client is not None,
    }


def _pick_fallback_model(provider: str) -> str | None:
    """요청한 프로바이더가 없을 때, 사용 가능한 다른 모델을 반환합니다."""
    if _anthropic_client:
        return "claude-sonnet-4-5-20250929"
    if _google_client:
        return "gemini-2.5-flash"
    if _openai_client:
        return "gpt-5-mini"
    return None


def select_model(text: str, override: str | None = None) -> str:
    """메시지 내용에 따라 적절한 모델을 선택합니다.

    - 수동 모드: override 모델을 반환 (해당 프로바이더가 없으면 폴백)
    - 자동 모드: 짧은 질문 → 저비용 모델, 복잡한 질문 → 고급 모델
    """
    if override:
        provider = _get_provider(override)
        providers = get_available_providers()
        if providers.get(provider):
            return override
        # 해당 프로바이더 사용 불가 → 폴백
        fallback = _pick_fallback_model(provider)
        if fallback:
            logger.warning("%s 프로바이더 사용 불가 → %s로 폴백", provider, fallback)
            return fallback
        return override  # 폴백도 없으면 그냥 반환 (ask_ai에서 에러 처리)

    # 자동 모드: 사용 가능한 프로바이더 중에서 선택
    is_complex = any(kw in text for kw in _COMPLEX_KEYWORDS)

    if _anthropic_client:
        if len(text) <= 50 and not is_complex:
            return "claude-haiku-4-5-20251001"
        return "claude-sonnet-4-5-20250929"
    elif _google_client:
        if len(text) <= 50 and not is_complex:
            return "gemini-2.5-flash"
        return "gemini-2.5-pro"
    elif _openai_client:
        if len(text) <= 50 and not is_complex:
            return "gpt-5-mini"
        return "gpt-5.2"

    return "claude-sonnet-4-5-20250929"  # 아무것도 없으면 기본값


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """비용 계산 (USD)."""
    p = _PRICING.get(model, {"input": 3.0, "output": 15.0})
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


async def classify_task(text: str) -> dict:
    """CEO 명령을 분류하여 적합한 에이전트 ID를 반환합니다.

    가장 저렴한 사용 가능 모델로 분류를 수행합니다.
    반환: {"agent_id": "cto_manager", "reason": "...", "cost_usd": 0.001}
    """
    if not is_ai_ready():
        return {"agent_id": "chief_of_staff", "reason": "AI 미연결", "cost_usd": 0}

    # 분류용 모델: 가장 저렴한 모델 선택
    if _anthropic_client:
        classify_model = "claude-haiku-4-5-20251001"
    elif _google_client:
        classify_model = "gemini-2.5-flash"
    elif _openai_client:
        classify_model = "gpt-5-mini"
    else:
        return {"agent_id": "chief_of_staff", "reason": "AI 미연결", "cost_usd": 0}

    result = await ask_ai(
        user_message=text,
        system_prompt=_CLASSIFY_PROMPT,
        model=classify_model,
    )

    if "error" in result:
        return {"agent_id": "chief_of_staff", "reason": f"분류 실패: {result['error'][:50]}", "cost_usd": 0}

    # JSON 파싱
    content = result.get("content", "").strip()
    try:
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        parsed = json.loads(content)
        return {
            "agent_id": parsed.get("agent_id", "chief_of_staff"),
            "reason": parsed.get("reason", ""),
            "cost_usd": result.get("cost_usd", 0),
        }
    except (json.JSONDecodeError, IndexError):
        logger.warning("분류 JSON 파싱 실패: %s", content[:100])
        return {"agent_id": "chief_of_staff", "reason": "분류 결과 파싱 실패", "cost_usd": result.get("cost_usd", 0)}


# ── 프로바이더별 API 호출 ──

async def _call_anthropic(user_message: str, system_prompt: str, model: str) -> dict:
    """Anthropic (Claude) API 호출."""
    messages = [{"role": "user", "content": user_message}]
    kwargs = {"model": model, "max_tokens": 4096, "messages": messages}
    if system_prompt:
        kwargs["system"] = system_prompt
    if "haiku" in model:
        kwargs["temperature"] = 0.5
    else:
        kwargs["temperature"] = 0.3

    resp = await _anthropic_client.messages.create(**kwargs)

    content = ""
    for block in resp.content:
        if block.type == "text":
            content = block.text
            break

    return {
        "content": content,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }


async def _call_google(user_message: str, system_prompt: str, model: str) -> dict:
    """Google Gemini API 호출 (google-genai SDK 사용)."""
    import asyncio

    config = {"max_output_tokens": 4096, "temperature": 0.3}
    if system_prompt:
        config["system_instruction"] = system_prompt

    # google-genai SDK는 동기 API → asyncio.to_thread로 비동기 실행
    def _sync_call():
        response = _google_client.models.generate_content(
            model=model,
            contents=user_message,
            config=config,
        )
        return response

    resp = await asyncio.to_thread(_sync_call)

    content = resp.text or ""
    # 토큰 사용량 추출
    usage = getattr(resp, "usage_metadata", None)
    input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
    output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

    return {
        "content": content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


async def _call_openai(user_message: str, system_prompt: str, model: str) -> dict:
    """OpenAI (GPT) API 호출."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_message})

    resp = await _openai_client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=4096,
        temperature=0.3,
    )

    content = resp.choices[0].message.content or ""
    input_tokens = resp.usage.prompt_tokens if resp.usage else 0
    output_tokens = resp.usage.completion_tokens if resp.usage else 0

    return {
        "content": content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


async def ask_ai(
    user_message: str,
    system_prompt: str = "",
    model: str | None = None,
) -> dict:
    """AI에게 질문합니다 (프로바이더 자동 판별).

    반환: {"content", "model", "input_tokens", "output_tokens", "cost_usd", "time_seconds"}
    AI 불가 시: {"error": "사유"}
    """
    if not is_ai_ready():
        return {"error": "AI 미연결 — API 키를 확인하세요"}

    if model is None:
        model = select_model(user_message)

    provider = _get_provider(model)
    providers = get_available_providers()

    # 해당 프로바이더 사용 불가 시 폴백
    if not providers.get(provider):
        fallback = _pick_fallback_model(provider)
        if fallback:
            logger.warning("%s 프로바이더 사용 불가 → %s로 폴백", provider, fallback)
            model = fallback
            provider = _get_provider(model)
        else:
            return {"error": f"{provider} API 키가 설정되지 않았습니다"}

    start = time.time()
    try:
        if provider == "anthropic":
            result = await _call_anthropic(user_message, system_prompt, model)
        elif provider == "google":
            result = await _call_google(user_message, system_prompt, model)
        elif provider == "openai":
            result = await _call_openai(user_message, system_prompt, model)
        else:
            return {"error": f"알 수 없는 프로바이더: {provider}"}
    except Exception as e:
        logger.error("AI 호출 실패 (%s/%s): %s", provider, model, e)
        return {"error": f"AI 호출 실패 ({provider}): {str(e)[:200]}"}

    elapsed = time.time() - start

    input_tokens = result.get("input_tokens", 0)
    output_tokens = result.get("output_tokens", 0)
    cost = _calc_cost(model, input_tokens, output_tokens)

    return {
        "content": result["content"],
        "model": model,
        "provider": provider,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
        "time_seconds": round(elapsed, 2),
    }
