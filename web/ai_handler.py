"""
CORTHEX HQ - AI Handler

비서실장 AI 호출, 모델 라우팅, 비용 계산을 담당합니다.
mini_server.py에서 import하여 사용합니다.
"""
import os
import time
import logging

logger = logging.getLogger("corthex.ai")

# ── Anthropic 선택적 로드 ──
_ai_available = False
_client = None
try:
    from anthropic import AsyncAnthropic
    _ai_available = True
except ImportError:
    logger.warning("anthropic 패키지 미설치 — AI 기능 비활성화")

# ── 모델 가격표 (1M 토큰당 USD) ──
_PRICING = {
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-opus-4-6": {"input": 5.00, "output": 25.00},
}

# ── 모델 라우팅 키워드 ──
_COMPLEX_KEYWORDS = [
    "분석", "보고서", "전략", "계획", "비교", "평가", "조사",
    "설계", "리포트", "검토", "진단", "예측",
]


def init_ai_client() -> bool:
    """AI 클라이언트 초기화. 반환: 성공 여부."""
    global _client
    if not _ai_available:
        return False
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY 미설정 — AI 기능 비활성화")
        return False
    _client = AsyncAnthropic(api_key=api_key)
    logger.info("AI 클라이언트 초기화 완료")
    return True


def is_ai_ready() -> bool:
    """AI 호출이 가능한 상태인지 확인."""
    return _client is not None


def select_model(text: str) -> str:
    """메시지 내용에 따라 적절한 모델을 선택합니다.

    - 짧은 질문(50자 이하, 복잡 키워드 없음) → haiku (저비용)
    - 복잡한 분석/보고서 요청 → sonnet (고품질)
    - 그 외 → sonnet (기본)
    """
    is_complex = any(kw in text for kw in _COMPLEX_KEYWORDS)
    if len(text) <= 50 and not is_complex:
        return "claude-haiku-4-5-20251001"
    return "claude-sonnet-4-5-20250929"


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """비용 계산 (USD)."""
    p = _PRICING.get(model, {"input": 3.0, "output": 15.0})
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


async def ask_ai(
    user_message: str,
    system_prompt: str = "",
    model: str | None = None,
) -> dict:
    """비서실장 AI에게 질문합니다.

    반환: {"content", "model", "input_tokens", "output_tokens", "cost_usd", "time_seconds"}
    AI 불가 시: {"error": "사유"}
    """
    if not is_ai_ready():
        return {"error": "AI 미연결 — ANTHROPIC_API_KEY를 확인하세요"}

    if model is None:
        model = select_model(user_message)

    messages = [{"role": "user", "content": user_message}]

    kwargs = {
        "model": model,
        "max_tokens": 4096,
        "messages": messages,
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    # sonnet은 temperature 0.3, haiku는 0.5
    if "haiku" in model:
        kwargs["temperature"] = 0.5
    else:
        kwargs["temperature"] = 0.3

    start = time.time()
    try:
        resp = await _client.messages.create(**kwargs)
    except Exception as e:
        logger.error("AI 호출 실패: %s", e)
        return {"error": f"AI 호출 실패: {str(e)[:200]}"}

    elapsed = time.time() - start

    # 응답 텍스트 추출
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
