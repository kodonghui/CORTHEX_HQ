"""
CORTHEX HQ - AI Handler (멀티 프로바이더)

AI 호출, 모델 라우팅, 에이전트 분류, 비용 계산을 담당합니다.
Anthropic (Claude), Google (Gemini), OpenAI (GPT) 3개 회사 AI를 지원합니다.
mini_server.py에서 import하여 사용합니다.
"""
import json
import os
import time
import logging

logger = logging.getLogger("corthex.ai")

# ── 프로바이더별 SDK 선택적 로드 ──
_anthropic_available = False
_google_available = False
_openai_available = False

_client = None           # Anthropic AsyncAnthropic
_google_configured = False  # Google genai.configure() 완료 여부
_openai_client = None    # OpenAI AsyncOpenAI

try:
    from anthropic import AsyncAnthropic
    _anthropic_available = True
except ImportError:
    pass

try:
    import google.generativeai as genai
    _google_available = True
except ImportError:
    genai = None

try:
    from openai import AsyncOpenAI
    _openai_available = True
except ImportError:
    pass

# ── 모델 가격표 (1M 토큰당 USD) ──
_PRICING = {
    # Anthropic (Claude)
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-opus-4-6": {"input": 5.00, "output": 25.00},
    # Google (Gemini)
    "gemini-3-pro-preview": {"input": 1.25, "output": 10.00},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    # OpenAI (GPT)
    "gpt-5.2-pro": {"input": 10.00, "output": 30.00},
    "gpt-5.2": {"input": 2.50, "output": 10.00},
    "gpt-5.1": {"input": 2.50, "output": 10.00},
    "gpt-5": {"input": 2.50, "output": 10.00},
    "gpt-5-mini": {"input": 0.15, "output": 0.60},
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
    """모델 이름으로 AI 회사(프로바이더)를 판별합니다."""
    if model.startswith("claude-"):
        return "anthropic"
    elif model.startswith("gemini-"):
        return "google"
    elif model.startswith(("gpt-", "o3-", "o4-")):
        return "openai"
    return "anthropic"  # 기본값


def init_ai_client() -> bool:
    """모든 AI 클라이언트 초기화. 반환: 하나라도 성공했는지."""
    global _client, _google_configured, _openai_client
    any_ok = False

    # 1) Anthropic (Claude) — 기본 AI
    if _anthropic_available:
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if key:
            _client = AsyncAnthropic(api_key=key)
            logger.info("Anthropic (Claude) 초기화 완료 ✅")
            any_ok = True
        else:
            logger.warning("ANTHROPIC_API_KEY 미설정")

    # 2) Google (Gemini)
    if _google_available and genai is not None:
        key = os.getenv("GOOGLE_API_KEY", "")
        if key:
            genai.configure(api_key=key)
            _google_configured = True
            logger.info("Google (Gemini) 초기화 완료 ✅")
            any_ok = True
        else:
            logger.info("GOOGLE_API_KEY 미설정 — Gemini 비활성화")

    # 3) OpenAI (GPT)
    if _openai_available:
        key = os.getenv("OPENAI_API_KEY", "")
        if key:
            _openai_client = AsyncOpenAI(api_key=key)
            logger.info("OpenAI (GPT) 초기화 완료 ✅")
            any_ok = True
        else:
            logger.info("OPENAI_API_KEY 미설정 — GPT 비활성화")

    if not any_ok:
        logger.warning("AI 클라이언트 없음 — API 키를 확인하세요")

    return any_ok


def is_ai_ready() -> bool:
    """하나라도 AI 호출이 가능한 상태인지 확인."""
    return _client is not None or _google_configured or _openai_client is not None


def _is_provider_ready(provider: str) -> bool:
    """특정 프로바이더가 준비되었는지 확인."""
    if provider == "anthropic":
        return _client is not None
    elif provider == "google":
        return _google_configured
    elif provider == "openai":
        return _openai_client is not None
    return False


def _provider_error_msg(provider: str) -> str:
    """프로바이더가 미설정일 때 안내 메시지."""
    msgs = {
        "anthropic": "Anthropic(Claude) API 키가 설정되지 않았습니다.\n설정 방법: 서버 환경변수에 ANTHROPIC_API_KEY를 추가하세요.",
        "google": "Google(Gemini) API 키가 설정되지 않았습니다.\n설정 방법: 서버 환경변수에 GOOGLE_API_KEY를 추가하세요.\n(Google AI Studio에서 무료 API 키 발급 가능)",
        "openai": "OpenAI(GPT) API 키가 설정되지 않았습니다.\n설정 방법: 서버 환경변수에 OPENAI_API_KEY를 추가하세요.",
    }
    sdk_msgs = {
        "anthropic": "anthropic 패키지가 서버에 설치되지 않았습니다. (pip install anthropic)",
        "google": "google-generativeai 패키지가 서버에 설치되지 않았습니다. (pip install google-generativeai)",
        "openai": "openai 패키지가 서버에 설치되지 않았습니다. (pip install openai)",
    }
    sdk_available = {
        "anthropic": _anthropic_available,
        "google": _google_available,
        "openai": _openai_available,
    }
    if not sdk_available.get(provider, False):
        return sdk_msgs.get(provider, f"{provider} SDK 미설치")
    return msgs.get(provider, f"{provider} 미설정")


def select_model(text: str, override: str | None = None) -> str:
    """메시지 내용에 따라 적절한 모델을 선택합니다.

    - 수동 모드: override 모델을 즉시 반환
    - 자동 모드: 짧은 질문 → haiku, 복잡한 질문 → sonnet
    """
    if override:
        return override
    is_complex = any(kw in text for kw in _COMPLEX_KEYWORDS)
    if len(text) <= 50 and not is_complex:
        return "claude-haiku-4-5-20251001"
    return "claude-sonnet-4-5-20250929"


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """비용 계산 (USD)."""
    p = _PRICING.get(model, {"input": 3.0, "output": 15.0})
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


# ── 프로바이더별 AI 호출 함수 ──

async def _ask_anthropic(user_message: str, system_prompt: str, model: str) -> dict:
    """Anthropic (Claude) API 호출."""
    messages = [{"role": "user", "content": user_message}]
    kwargs = {
        "model": model,
        "max_tokens": 4096,
        "messages": messages,
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    if "haiku" in model:
        kwargs["temperature"] = 0.5
    else:
        kwargs["temperature"] = 0.3

    start = time.time()
    try:
        resp = await _client.messages.create(**kwargs)
    except Exception as e:
        logger.error("Anthropic 호출 실패: %s", e)
        return {"error": f"Claude 호출 실패: {str(e)[:200]}"}

    elapsed = time.time() - start
    content = ""
    for block in resp.content:
        if block.type == "text":
            content = block.text
            break

    input_tokens = resp.usage.input_tokens
    output_tokens = resp.usage.output_tokens
    cost = _calc_cost(model, input_tokens, output_tokens)

    return {
        "content": content,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
        "time_seconds": round(elapsed, 2),
    }


async def _ask_google(user_message: str, system_prompt: str, model: str) -> dict:
    """Google (Gemini) API 호출."""
    gen_config = {"temperature": 0.3, "max_output_tokens": 4096}
    model_kwargs = {"model_name": model, "generation_config": gen_config}
    if system_prompt:
        model_kwargs["system_instruction"] = system_prompt

    gmodel = genai.GenerativeModel(**model_kwargs)

    start = time.time()
    try:
        resp = await gmodel.generate_content_async(user_message)
    except Exception as e:
        logger.error("Gemini 호출 실패: %s", e)
        return {"error": f"Gemini 호출 실패: {str(e)[:200]}"}

    elapsed = time.time() - start
    content = resp.text or ""

    input_tokens = 0
    output_tokens = 0
    if resp.usage_metadata:
        input_tokens = getattr(resp.usage_metadata, "prompt_token_count", 0) or 0
        output_tokens = getattr(resp.usage_metadata, "candidates_token_count", 0) or 0
    cost = _calc_cost(model, input_tokens, output_tokens)

    return {
        "content": content,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
        "time_seconds": round(elapsed, 2),
    }


async def _ask_openai(user_message: str, system_prompt: str, model: str) -> dict:
    """OpenAI (GPT) API 호출."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_message})

    start = time.time()
    try:
        resp = await _openai_client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=4096,
            temperature=0.3,
        )
    except Exception as e:
        logger.error("OpenAI 호출 실패: %s", e)
        return {"error": f"GPT 호출 실패: {str(e)[:200]}"}

    elapsed = time.time() - start
    content = resp.choices[0].message.content or "" if resp.choices else ""
    input_tokens = resp.usage.prompt_tokens if resp.usage else 0
    output_tokens = resp.usage.completion_tokens if resp.usage else 0
    cost = _calc_cost(model, input_tokens, output_tokens)

    return {
        "content": content,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
        "time_seconds": round(elapsed, 2),
    }


# ── 메인 AI 호출 함수 ──

async def classify_task(text: str) -> dict:
    """CEO 명령을 분류하여 적합한 에이전트 ID를 반환합니다.

    Haiku 모델로 저비용 분류를 수행합니다 (~$0.001/건).
    Anthropic 미연결 시 → 비서실장이 직접 처리.
    """
    if not _is_provider_ready("anthropic"):
        return {"agent_id": "chief_of_staff", "reason": "분류용 Claude 미연결", "cost_usd": 0}

    result = await ask_ai(
        user_message=text,
        system_prompt=_CLASSIFY_PROMPT,
        model="claude-haiku-4-5-20251001",
    )

    if "error" in result:
        return {"agent_id": "chief_of_staff", "reason": f"분류 실패: {result['error'][:50]}", "cost_usd": 0}

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


async def ask_ai(
    user_message: str,
    system_prompt: str = "",
    model: str | None = None,
) -> dict:
    """AI에게 질문합니다. 모델 이름에 따라 적절한 AI 회사를 자동 선택합니다.

    반환: {"content", "model", "input_tokens", "output_tokens", "cost_usd", "time_seconds"}
    AI 불가 시: {"error": "사유"}
    """
    if not is_ai_ready():
        return {"error": "AI 미연결 — API 키를 확인하세요 (ANTHROPIC_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY)"}

    if model is None:
        model = select_model(user_message)

    provider = _get_provider(model)

    # 해당 프로바이더가 준비되지 않았으면 에러
    if not _is_provider_ready(provider):
        return {"error": _provider_error_msg(provider)}

    # 프로바이더별 호출
    if provider == "anthropic":
        return await _ask_anthropic(user_message, system_prompt, model)
    elif provider == "google":
        return await _ask_google(user_message, system_prompt, model)
    elif provider == "openai":
        return await _ask_openai(user_message, system_prompt, model)

    return {"error": f"알 수 없는 모델: {model}"}
