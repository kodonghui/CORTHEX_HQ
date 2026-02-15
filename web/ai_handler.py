"""
CORTHEX HQ - AI Handler

AI 호출, 모델 라우팅, 에이전트 분류, 비용 계산을 담당합니다.
mini_server.py에서 import하여 사용합니다.
"""
import json
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


def select_model(text: str, override: str | None = None) -> str:
    """메시지 내용에 따라 적절한 모델을 선택합니다.

    Args:
        text: 메시지 내용
        override: 수동 모드에서 강제 지정할 모델명 (None이면 자동 모드)

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


async def classify_task(text: str) -> dict:
    """CEO 명령을 분류하여 적합한 에이전트 ID를 반환합니다.

    Haiku 모델로 저비용 분류를 수행합니다 (~$0.001/건).
    반환: {"agent_id": "cto_manager", "reason": "...", "cost_usd": 0.001}
    실패 시: {"agent_id": "chief_of_staff", "reason": "분류 실패", "cost_usd": 0}
    """
    if not is_ai_ready():
        return {"agent_id": "chief_of_staff", "reason": "AI 미연결", "cost_usd": 0}

    result = await ask_ai(
        user_message=text,
        system_prompt=_CLASSIFY_PROMPT,
        model="claude-haiku-4-5-20251001",
    )

    if "error" in result:
        return {"agent_id": "chief_of_staff", "reason": f"분류 실패: {result['error'][:50]}", "cost_usd": 0}

    # JSON 파싱
    content = result.get("content", "").strip()
    try:
        # JSON 블록이 ```로 감싸져 있을 수 있음
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
    """AI에게 질문합니다.

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
