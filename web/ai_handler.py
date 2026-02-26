"""
CORTHEX HQ - AI Handler (멀티 프로바이더)

Anthropic (Claude), Google (Gemini), OpenAI (GPT) 3개 프로바이더를 지원합니다.
모델명 접두사로 프로바이더를 자동 판별합니다:
  - claude-*  → Anthropic API
  - gemini-*  → Google Generative AI API
  - gpt-*     → OpenAI API

arm_server.py에서 import하여 사용합니다.
"""
from __future__ import annotations

import copy
import json
import os
import time
import logging
import asyncio
import random
from pathlib import Path

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

# Google Gemini (멀티 키 로테이션 지원)
_google_client = None          # 호환성 유지용 (첫 번째 클라이언트 참조)
_google_clients: list = []     # 여러 프로젝트의 클라이언트 리스트
_google_client_idx = 0         # 라운드로빈 인덱스
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


# ── 도구 결과 최대 길이 (상수) ──
TOOL_RESULT_MAX_CHARS = 4000

# ── 모델 가격표 (models.yaml에서 자동 로드, 폴백: 하드코딩) ──
def _load_pricing_from_yaml() -> dict:
    """config/models.yaml에서 가격 정보를 로드합니다."""
    pricing = {}
    try:
        import yaml
        yaml_path = Path(__file__).parent.parent / "config" / "models.yaml"
        if yaml_path.exists():
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for provider_data in (data.get("providers") or {}).values():
                for m in provider_data.get("models", []):
                    name = m.get("name", "")
                    inp = m.get("cost_per_1m_input", 0)
                    out = m.get("cost_per_1m_output", 0)
                    if name and (inp or out):
                        pricing[name] = {"input": inp, "output": out}
    except Exception as e:
        logger.warning("models.yaml 가격 로드 실패, 기본값 사용: %s", e)
    return pricing

_PRICING_FALLBACK = {
    "claude-opus-4-6": {"input": 5.00, "output": 25.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gpt-5.2-pro": {"input": 21.00, "output": 168.00},
    "gpt-5.2": {"input": 1.75, "output": 14.00},
    "gpt-5": {"input": 1.25, "output": 10.00},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
}
_PRICING = _load_pricing_from_yaml() or _PRICING_FALLBACK


# ── Google API 전역 속도 제한기 ──
# Google Gemini는 분당 요청 제한(RPM)이 엄격함.
# 모든 에이전트가 같은 API 키 공유 → 전역적으로 호출 간격 제어 필요.
# 비유: 식당 앞 번호표 기계 — 동시 입장 2명, 입장 간격 최소 4초.
class _GoogleRateLimiter:
    """Google API 전역 속도 제한기.

    - 동시 호출 최대 max_concurrent개 (세마포어)
    - 호출 시작 간 최소 min_interval초 (쓰로틀)
    """

    def __init__(self, max_concurrent: int = 2, min_interval: float = 4.0):
        self._max_concurrent = max_concurrent
        self._min_interval = min_interval
        self._last_call_time = 0.0
        # asyncio 객체는 이벤트 루프 안에서 생성해야 안전 → lazy init
        self._semaphore: asyncio.Semaphore | None = None
        self._lock: asyncio.Lock | None = None

    def _ensure_init(self):
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
            self._lock = asyncio.Lock()

    async def acquire(self):
        """호출 전 대기. 동시성 제한 + 최소 간격 모두 적용."""
        self._ensure_init()
        await self._semaphore.acquire()
        async with self._lock:
            now = time.time()
            wait = self._min_interval - (now - self._last_call_time)
            if wait > 0:
                logger.debug("Google 속도 제한: %.1f초 대기 (간격 유지)", wait)
                await asyncio.sleep(wait)
            self._last_call_time = time.time()

    def release(self):
        """호출 완료 후 슬롯 반납."""
        if self._semaphore:
            self._semaphore.release()


_google_rate_limiter = _GoogleRateLimiter(max_concurrent=2, min_interval=4.0)


def _next_google_client():
    """다음 Google 클라이언트를 라운드로빈으로 반환.

    비유: 식당 4개에 번호표 돌려쓰기 — 1번 식당 → 2번 → 3번 → 4번 → 다시 1번.
    각 프로젝트(식당)마다 별도 RPM 할당이라 요율 제한 분산.
    """
    global _google_client_idx
    if not _google_clients:
        return None
    client = _google_clients[_google_client_idx % len(_google_clients)]
    _google_client_idx += 1
    return client


# ── reasoning_effort 관련 상수 ──

# reasoning_effort → temperature 매핑 (추론 모델은 반드시 1.0)
REASONING_TEMPERATURE_MAP = {
    "low": 1.0,
    "medium": 1.0,
    "high": 1.0,
    "xhigh": 1.0,
}

# reasoning_effort → Claude extended thinking budget_tokens 매핑
REASONING_BUDGET_TOKENS_MAP = {
    "low": 1024,
    "medium": 8192,
    "high": 16000,
    "xhigh": 32000,
}

# reasoning_effort → OpenAI reasoning_effort 값 매핑 (GPT-5.2/5.2-pro 모두 xhigh 지원)
OPENAI_REASONING_MAP = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
}

# OpenAI reasoning 지원 모델 목록 (temperature 없이 reasoning_effort만 사용)
OPENAI_REASONING_MODELS = {"o3", "o4-mini", "gpt-5.2", "gpt-5.2-pro", "o3-mini", "gpt-5-mini"}

# Responses API 전용 모델 (Chat Completions API 미지원 → client.responses.create 사용)
OPENAI_RESPONSES_ONLY_MODELS = {"gpt-5.2-pro"}

# Responses API용 reasoning_effort 매핑 (gpt-5.2-pro는 xhigh 지원)
RESPONSES_REASONING_MAP = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
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


# ── 도구 스키마 로딩 & 변환 ──

# 프로젝트 루트 경로 (config/ 폴더가 있는 곳)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _build_tool_schemas(tool_configs: list, allowed_tools: list | None = None) -> list:
    """tools.yaml의 도구 정의를 Anthropic tool_use 포맷으로 변환합니다.

    tools.yaml의 파라미터 형식:
      1) parameters 없음 → 기본 query 파라미터
      2) 평면(flat) 형식 → {"action": {"type": "string", ...}, ...}
      3) JSON Schema 형식 → {"type": "object", "properties": {...}}

    2)를 자동으로 3)으로 변환합니다.
    """
    _DEFAULT_SCHEMA = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "도구에 전달할 질문 또는 명령",
            }
        },
        "required": ["query"],
    }

    schemas = []
    for tool in tool_configs:
        tool_id = tool.get("tool_id", "")
        if not tool_id:
            continue
        if allowed_tools and tool_id not in allowed_tools:
            continue

        params = tool.get("parameters")
        if not params:
            # 파라미터 없음 → 기본 query
            input_schema = _DEFAULT_SCHEMA.copy()
        elif params.get("type") == "object" and "properties" in params:
            # 이미 JSON Schema 형식
            input_schema = params
        else:
            # 평면(flat) 형식 → JSON Schema로 변환
            properties = {}
            required = []
            for pname, pdef in params.items():
                if not isinstance(pdef, dict):
                    continue
                prop = {k: v for k, v in pdef.items() if k != "required"}
                if not prop.get("type"):
                    prop["type"] = "string"
                properties[pname] = prop
                if pdef.get("required"):
                    required.append(pname)
            input_schema = {
                "type": "object",
                "properties": properties,
                "required": required if required else ["action"] if "action" in properties else list(properties.keys())[:1],
            }

        schema = {
            "name": tool_id,
            "description": tool.get("description", tool.get("name_ko", tool_id)),
            "input_schema": input_schema,
        }
        schemas.append(schema)
    return schemas


def _apply_openai_strict_inline(obj: dict) -> None:
    """OpenAI strict 모드: 모든 레벨 object에 additionalProperties/required 재귀 적용.

    ★ 모듈 레벨 함수 — _load_tool_schemas()와 ask_ai() 양쪽에서 호출됨.
    이전에 _load_tool_schemas() 안의 지역 함수로 정의되어 있어서
    ask_ai()에서 호출 시 NameError 발생 → GPT 모델 전문가 즉사 버그 원인이었음.
    """
    if obj.get("type") == "object":
        props = obj.get("properties", {})
        obj["additionalProperties"] = False
        obj["required"] = list(props.keys())
        for prop in props.values():
            if isinstance(prop, dict):
                if isinstance(prop.get("enum"), list):
                    prop["enum"] = [e for e in prop["enum"] if e is not None]
                if prop.get("type") == "object":
                    _apply_openai_strict_inline(prop)
                if prop.get("type") == "array":
                    items = prop.get("items", {})
                    if isinstance(items, dict) and items.get("type") == "object":
                        _apply_openai_strict_inline(items)


def _load_tool_schemas(allowed_tools: list | None = None) -> dict:
    """config/tools.yaml (또는 tools.json)에서 도구 정의를 읽어서
    프로바이더별 포맷으로 변환합니다.

    반환: {
        "anthropic": [Anthropic tool 포맷 리스트],
        "openai":    [OpenAI function calling 포맷 리스트],
        "google":    [Google Gemini 포맷용 원본 리스트],
    }

    파일을 읽지 못하면 빈 dict를 반환합니다.
    """
    # 1) tools.json 우선 시도 (서버에는 yaml2json.py가 미리 변환해둠)
    json_path = _PROJECT_ROOT / "config" / "tools.json"
    yaml_path = _PROJECT_ROOT / "config" / "tools.yaml"
    tool_configs = []

    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            tool_configs = data.get("tools", [])
        except Exception as e:
            logger.warning("tools.json 읽기 실패: %s", e)

    if not tool_configs and yaml_path.exists():
        try:
            import yaml
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            tool_configs = data.get("tools", [])
        except ImportError:
            logger.warning("PyYAML 미설치 — tools.yaml을 읽을 수 없습니다")
        except Exception as e:
            logger.warning("tools.yaml 읽기 실패: %s", e)

    if not tool_configs:
        logger.warning("도구 설정을 로드하지 못했습니다 (tools.json/yaml 모두 실패)")
        return {}

    # 2) Anthropic 포맷으로 빌드 (기준 포맷)
    anthropic_schemas = _build_tool_schemas(tool_configs, allowed_tools)

    # 3) OpenAI 포맷으로 변환 (GPT-5.2 strict-compatible)
    # _apply_openai_strict_inline()는 모듈 레벨에 정의됨 (ask_ai에서도 사용)
    openai_schemas = []
    for t in anthropic_schemas:
        schema = copy.deepcopy(t.get("input_schema", {"type": "object", "properties": {}}))
        # 안전장치: type이 없거나 object가 아닌 경우 강제 보정
        if schema.get("type") != "object":
            schema = {"type": "object", "properties": {"query": {"type": "string", "description": "도구에 전달할 질문"}}, "required": ["query"]}
        if not schema.get("properties"):
            schema["properties"] = {"query": {"type": "string", "description": "도구에 전달할 질문"}}
        # strict 모드: 모든 레벨의 object에 additionalProperties/required 재귀 적용
        _apply_openai_strict_inline(schema)
        openai_schemas.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "strict": True,
                "parameters": schema,
            },
        })

    # 4) Google (Gemini) 포맷은 API 호출 시 직접 변환하므로 원본(Anthropic 포맷)을 그대로 전달
    return {
        "anthropic": anthropic_schemas,
        "openai": openai_schemas,
        "google": anthropic_schemas,  # _call_google_with_tools 내부에서 Gemini 포맷으로 변환
    }


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

    # Google Gemini — 멀티 프로젝트 키 로테이션 지원
    # 비유: 식당 여러 개 등록 → 요율 제한(RPM) 분산
    if _google_available:
        _google_clients.clear()
        # 기본 키
        key = os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        if key:
            _google_clients.append(genai.Client(api_key=key))
        # 추가 키 (GOOGLE_API_KEY_2, _3, _4, ...)
        for i in range(2, 10):
            extra_key = os.getenv(f"GOOGLE_API_KEY_{i}", "")
            if extra_key:
                _google_clients.append(genai.Client(api_key=extra_key))
        if _google_clients:
            _google_client = _google_clients[0]  # 호환성 유지
            # 키 개수에 비례하여 속도 제한 완화
            n = len(_google_clients)
            _google_rate_limiter._min_interval = max(1.0, 4.0 / n)
            _google_rate_limiter._max_concurrent = min(6, n * 2)
            logger.info("Google Gemini 클라이언트 %d개 초기화 완료 (속도제한: 동시%d개, 간격%.1f초)",
                        n, _google_rate_limiter._max_concurrent, _google_rate_limiter._min_interval)
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


_exhausted_providers: set[str] = set()  # 크레딧 소진된 프로바이더 (런타임 중 기억)


def mark_provider_exhausted(provider: str) -> None:
    """프로바이더를 크레딧 소진 상태로 표시합니다."""
    _exhausted_providers.add(provider)
    logger.warning("⚠️ %s 프로바이더 크레딧 소진 → 이번 세션 동안 자동 우회", provider)


def reset_exhausted_providers() -> None:
    """소진 표시를 초기화합니다 (크레딧 충전 후 호출)."""
    _exhausted_providers.clear()
    logger.info("프로바이더 소진 상태 초기화 완료")


def get_available_providers() -> dict:
    """현재 사용 가능한 프로바이더 상태를 반환합니다."""
    return {
        "anthropic": _anthropic_client is not None and "anthropic" not in _exhausted_providers,
        "google": _google_client is not None and "google" not in _exhausted_providers,
        "openai": _openai_client is not None and "openai" not in _exhausted_providers,
    }


def _pick_fallback_model(provider: str, *, exclude: str | None = None) -> str | None:
    """요청한 프로바이더가 없을 때, 사용 가능한 다른 모델을 반환합니다.

    Args:
        provider: 원래 요청했던 프로바이더
        exclude: 추가로 제외할 프로바이더 (크레딧 소진 등)
    """
    _skip = {provider} | _exhausted_providers
    if exclude:
        _skip.add(exclude)
    if "anthropic" not in _skip and _anthropic_client:
        return "claude-sonnet-4-6"
    if "google" not in _skip and _google_client:
        return "gemini-2.5-flash"
    if "openai" not in _skip and _openai_client:
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

    # 자동 모드: 사용 가능한 프로바이더 중에서 선택 (소진된 프로바이더 건너뜀)
    is_complex = any(kw in text for kw in _COMPLEX_KEYWORDS)

    if _anthropic_client and "anthropic" not in _exhausted_providers:
        if len(text) <= 50 and not is_complex:
            return "claude-haiku-4-5-20251001"
        return "claude-sonnet-4-6"
    elif _google_client and "google" not in _exhausted_providers:
        if len(text) <= 50 and not is_complex:
            return "gemini-2.5-flash"
        return "gemini-2.5-pro"
    elif _openai_client and "openai" not in _exhausted_providers:
        if len(text) <= 50 and not is_complex:
            return "gpt-5-mini"
        return "gpt-5.2"

    return "claude-sonnet-4-6"  # 아무것도 없으면 기본값


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

    # 분류용 모델: 가장 저렴한 모델 선택 (Gemini Flash → GPT Mini → Claude)
    if _google_client:
        classify_model = "gemini-2.5-flash"
    elif _openai_client:
        classify_model = "gpt-5-mini"
    elif _anthropic_client:
        classify_model = "claude-sonnet-4-6"
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

async def _call_anthropic(
    user_message: str,
    system_prompt: str,
    model: str,
    tools: list | None = None,
    tool_executor: callable | None = None,
    reasoning_effort: str = "",
    conversation_history: list | None = None,
    ai_call_timeout: int = 180,
) -> dict:
    """Anthropic (Claude) API 호출.

    tools가 주어지면 tool_use 블록을 처리하는 루프를 실행합니다.
    tool_executor는 async 함수로, (tool_name, tool_input) -> result를 반환해야 합니다.
    reasoning_effort가 주어지면 extended thinking을 활성화합니다.
    """
    messages = []
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})
    kwargs = {"model": model, "max_tokens": 16384, "messages": messages}
    if system_prompt:
        kwargs["system"] = system_prompt

    # temperature 설정 — reasoning_effort가 있으면 extended thinking 활성화
    if reasoning_effort and reasoning_effort in REASONING_TEMPERATURE_MAP:
        kwargs["temperature"] = 1.0  # 추론 모델 필수값
        budget = REASONING_BUDGET_TOKENS_MAP.get(reasoning_effort, 8192)
        kwargs["thinking"] = {"type": "adaptive", "budget_tokens": budget}
        # max_tokens = thinking budget + 응답 여유 (잘림 방지)
        kwargs["max_tokens"] = budget + 16384
    elif "haiku" in model:
        kwargs["temperature"] = 0.5
    else:
        kwargs["temperature"] = 0.7

    # 도구 스키마가 있으면 API에 포함
    if tools:
        kwargs["tools"] = tools

    # extended thinking 사용 시 스트리밍 필수 (Anthropic API 요구사항)
    async def _do_create(kw):
        if "thinking" in kw:
            async with _anthropic_client.messages.stream(**kw) as stream:
                return await stream.get_final_message()
        return await _anthropic_client.messages.create(**kw)

    try:
        resp = await asyncio.wait_for(_do_create(kwargs), timeout=ai_call_timeout)
    except asyncio.TimeoutError:
        raise  # 상위 ask_ai()에서 처리
    except Exception as e:
        if reasoning_effort and "thinking" in str(e):
            logger.warning("extended thinking 미지원 — 폴백으로 재시도: %s", e)
            kwargs.pop("thinking", None)
            kwargs["temperature"] = 1.0
            resp = await asyncio.wait_for(_anthropic_client.messages.create(**kwargs), timeout=ai_call_timeout)
        else:
            raise

    total_input_tokens = resp.usage.input_tokens
    total_output_tokens = resp.usage.output_tokens

    # tool_use 블록 처리 루프 (최대 10회 반복 — 기술적분석 등 복합 도구 워크플로우 지원)
    if tools and tool_executor:
        for _ in range(10):
            tool_calls = [b for b in resp.content if b.type == "tool_use"]
            if not tool_calls:
                break

            # 도구 실행
            tool_results = []
            for tc in tool_calls:
                try:
                    result = await tool_executor(tc.name, tc.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": str(result)[:TOOL_RESULT_MAX_CHARS],
                    })
                except Exception as e:
                    logger.warning("도구 실행 실패 (%s): %s", tc.name, e)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": f"오류: {e}",
                        "is_error": True,
                    })

            # 어시스턴트 응답을 대화에 추가 (모든 블록을 직렬화, thinking 블록 포함)
            assistant_content = []
            for b in resp.content:
                if b.type == "thinking":
                    block = {"type": "thinking", "thinking": b.thinking}
                    if hasattr(b, "signature") and b.signature:
                        block["signature"] = b.signature
                    assistant_content.append(block)
                elif b.type == "text":
                    assistant_content.append({"type": "text", "text": b.text})
                elif b.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": b.id,
                        "name": b.name,
                        "input": b.input,
                    })
            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

            # 다시 AI 호출 (도구 결과를 포함하여 재호출 — 개별 타임아웃 적용)
            kwargs["messages"] = messages
            resp = await asyncio.wait_for(_do_create(kwargs), timeout=ai_call_timeout)
            total_input_tokens += resp.usage.input_tokens
            total_output_tokens += resp.usage.output_tokens

    # 최종 텍스트 응답 추출
    text_blocks = [b.text for b in resp.content if b.type == "text"]
    content = "\n".join(text_blocks) if text_blocks else ""

    return {
        "content": content,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }


async def _call_google(
    user_message: str,
    system_prompt: str,
    model: str,
    tools: list | None = None,
    tool_executor: callable | None = None,
    reasoning_effort: str = "",
    conversation_history: list | None = None,
    ai_call_timeout: int = 180,
) -> dict:
    """Google Gemini API 호출 (google-genai SDK 사용).

    tools가 주어지면 function calling을 처리합니다.
    tools는 Anthropic 포맷 리스트이며, 내부에서 Gemini 포맷으로 변환합니다.
    reasoning_effort가 있으면 temperature를 1.0으로 설정합니다.
    """
    temp = 1.0 if reasoning_effort else 0.7
    config = {"max_output_tokens": 16384, "temperature": temp}
    if system_prompt:
        config["system_instruction"] = system_prompt

    # Gemini function calling용 도구 변환
    gemini_tools = None
    if tools and _google_available:
        try:
            from google.genai import types
            func_declarations = []
            for t in tools:
                params = t.get("input_schema", {"type": "object", "properties": {}})
                func_declarations.append(
                    types.FunctionDeclaration(
                        name=t["name"],
                        description=t.get("description", ""),
                        parameters=params,
                    )
                )
            gemini_tools = [types.Tool(function_declarations=func_declarations)]
        except Exception as e:
            logger.warning("Gemini 도구 스키마 변환 실패: %s", e)

    total_input_tokens = 0
    total_output_tokens = 0

    # google-genai SDK는 동기 API → asyncio.to_thread로 비동기 실행
    # _next_google_client()로 라운드로빈 키 로테이션 적용
    def _sync_call(contents, cfg, g_tools=None):
        client = _next_google_client()
        call_kwargs = {"model": model, "contents": contents, "config": cfg}
        if g_tools:
            call_kwargs["config"]["tools"] = g_tools
        response = client.models.generate_content(**call_kwargs)
        return response

    # 대화 기록이 있으면 contents를 리스트로 구성
    if conversation_history:
        contents = []
        for msg in conversation_history:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        contents.append({"role": "user", "parts": [{"text": user_message}]})
    else:
        contents = user_message

    resp = await asyncio.wait_for(asyncio.to_thread(_sync_call, contents, config.copy(), gemini_tools), timeout=ai_call_timeout)

    usage = getattr(resp, "usage_metadata", None)
    total_input_tokens += getattr(usage, "prompt_token_count", 0) if usage else 0
    total_output_tokens += getattr(usage, "candidates_token_count", 0) if usage else 0

    # function call 처리 루프 (최대 10회 — 복합 도구 워크플로우 지원)
    if gemini_tools and tool_executor:
        for _ in range(10):
            # Gemini 응답에서 function_call 파트 추출
            func_calls = []
            if resp.candidates and resp.candidates[0].content and resp.candidates[0].content.parts:
                for part in resp.candidates[0].content.parts:
                    fc = getattr(part, "function_call", None)
                    if fc:
                        func_calls.append(fc)

            if not func_calls:
                break

            # 도구 실행 및 결과 수집
            from google.genai import types
            func_responses = []
            for fc in func_calls:
                try:
                    args = dict(fc.args) if fc.args else {}
                    result = await tool_executor(fc.name, args)
                    func_responses.append(
                        types.FunctionResponse(
                            name=fc.name,
                            response={"result": str(result)[:TOOL_RESULT_MAX_CHARS]},
                        )
                    )
                except Exception as e:
                    logger.warning("도구 실행 실패 (%s): %s", fc.name, e)
                    func_responses.append(
                        types.FunctionResponse(
                            name=fc.name,
                            response={"error": str(e)},
                        )
                    )

            # 대화를 이어서 재호출 (function_response를 포함)
            if not resp.candidates:
                break
            contents = [
                user_message,
                resp.candidates[0].content,
                types.Content(parts=[types.Part(function_response=fr) for fr in func_responses]),
            ]

            def _sync_followup(c, cfg, g_tools=None):
                client = _next_google_client()
                call_kwargs = {"model": model, "contents": c, "config": cfg}
                if g_tools:
                    call_kwargs["config"]["tools"] = g_tools
                return client.models.generate_content(**call_kwargs)

            resp = await asyncio.wait_for(asyncio.to_thread(_sync_followup, contents, config.copy(), gemini_tools), timeout=ai_call_timeout)
            usage = getattr(resp, "usage_metadata", None)
            total_input_tokens += getattr(usage, "prompt_token_count", 0) if usage else 0
            total_output_tokens += getattr(usage, "candidates_token_count", 0) if usage else 0

    # 최종 텍스트 추출
    content = ""
    if resp.candidates and resp.candidates[0].content and resp.candidates[0].content.parts:
        text_parts = []
        for part in resp.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                text_parts.append(part.text)
        content = "\n".join(text_parts)
    if not content:
        content = getattr(resp, "text", "") or ""

    return {
        "content": content,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }


async def _call_openai(
    user_message: str,
    system_prompt: str,
    model: str,
    tools: list | None = None,
    tool_executor: callable | None = None,
    reasoning_effort: str = "",
    conversation_history: list | None = None,
    ai_call_timeout: int = 300,
) -> dict:
    """OpenAI (GPT) API 호출.

    tools가 주어지면 function calling을 처리합니다.
    tools는 OpenAI 포맷 리스트 ({"type": "function", "function": {...}}).
    reasoning_effort가 있으면 o-series/GPT-5.2 모델에 reasoning_effort 파라미터를 전달합니다.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    # reasoning 지원 모델 판별 (OPENAI_REASONING_MODELS: temperature 파라미터 미지원)
    supports_reasoning = model in OPENAI_REASONING_MODELS

    if supports_reasoning:
        if reasoning_effort:
            # o-series/GPT-5.2: reasoning_effort 파라미터 사용
            openai_reasoning = OPENAI_REASONING_MAP.get(reasoning_effort, "medium")
            kwargs = {
                "model": model,
                "messages": messages,
                "max_completion_tokens": 65536,
                "reasoning_effort": openai_reasoning,
            }
        else:
            # reasoning 모델은 temperature 미지원 — 파라미터 없이 호출
            kwargs = {
                "model": model,
                "messages": messages,
                "max_completion_tokens": 65536,
            }
    elif reasoning_effort:
        # reasoning_effort가 있지만 reasoning 미지원 모델 → temperature 1.0
        kwargs = {"model": model, "messages": messages, "max_completion_tokens": 65536, "temperature": 1.0}
    else:
        kwargs = {"model": model, "messages": messages, "max_completion_tokens": 65536, "temperature": 0.7}

    if tools:
        kwargs["tools"] = tools

    resp = await asyncio.wait_for(_openai_client.chat.completions.create(**kwargs), timeout=ai_call_timeout)

    total_input_tokens = resp.usage.prompt_tokens if resp.usage else 0
    total_output_tokens = resp.usage.completion_tokens if resp.usage else 0

    # tool_calls 처리 루프 (최대 10회 — 기술적분석 등 복합 도구 워크플로우 지원)
    if tools and tool_executor:
        for _ in range(10):
            if not resp.choices:
                break
            msg = resp.choices[0].message
            if not msg.tool_calls:
                break

            # 어시스턴트 메시지를 대화에 추가 (딕셔너리로 변환 — ChatCompletionMessage 객체를 그대로 넣으면
            # "messages must be a list of dictionaries" 오류 발생)
            assistant_dict: dict = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                assistant_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant_dict)

            # 각 도구 호출 실행
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    result = await tool_executor(tc.function.name, args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(result)[:TOOL_RESULT_MAX_CHARS],
                    })
                except Exception as e:
                    logger.warning("도구 실행 실패 (%s): %s", tc.function.name, e)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": f"오류: {e}",
                    })

            # 다시 AI 호출 (도구 결과 포함 재호출 — 개별 타임아웃 적용)
            kwargs["messages"] = messages
            resp = await asyncio.wait_for(_openai_client.chat.completions.create(**kwargs), timeout=ai_call_timeout)
            if resp.usage:
                total_input_tokens += resp.usage.prompt_tokens
                total_output_tokens += resp.usage.completion_tokens

    content = resp.choices[0].message.content or "" if resp.choices else ""

    return {
        "content": content,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }


async def _call_openai_responses(
    user_message: str,
    system_prompt: str,
    model: str,
    tools: list | None = None,
    tool_executor: callable | None = None,
    reasoning_effort: str = "",
    conversation_history: list | None = None,
    ai_call_timeout: int = 300,
) -> dict:
    """OpenAI Responses API 호출 (gpt-5.2-pro 등 Responses API 전용 모델용).

    Chat Completions API와 달리:
    - system message → instructions 파라미터
    - messages → input 파라미터
    - reasoning_effort → reasoning.effort 파라미터 (xhigh 지원)
    - tool_calls → function_call 아이템 + previous_response_id 패턴
    """
    # input 구성 (대화 이력 + 사용자 메시지)
    input_items = []
    if conversation_history:
        input_items.extend(conversation_history)
    input_items.append({"role": "user", "content": user_message})

    kwargs = {
        "model": model,
        "input": input_items,
    }

    # 시스템 프롬프트 → instructions
    if system_prompt:
        kwargs["instructions"] = system_prompt

    # reasoning effort (gpt-5.2-pro는 xhigh 지원)
    if reasoning_effort and reasoning_effort != "none":
        effort = RESPONSES_REASONING_MAP.get(reasoning_effort, "medium")
        kwargs["reasoning"] = {"effort": effort}

    # 도구 변환: Chat Completions 형식 → Responses API 형식
    # Chat Completions: {"type": "function", "function": {"name": ..., "parameters": ...}}
    # Responses API:    {"type": "function", "name": ..., "parameters": ...}
    resp_tools = None
    if tools and tool_executor:
        resp_tools = []
        for t in tools:
            if t.get("type") == "function" and "function" in t:
                func = t["function"]
                tool_def = {
                    "type": "function",
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {"type": "object", "properties": {}}),
                }
                if func.get("strict"):
                    tool_def["strict"] = True
                resp_tools.append(tool_def)
            else:
                resp_tools.append(t)
        kwargs["tools"] = resp_tools

    resp = await asyncio.wait_for(_openai_client.responses.create(**kwargs), timeout=ai_call_timeout)

    total_input_tokens = resp.usage.input_tokens if resp.usage else 0
    total_output_tokens = resp.usage.output_tokens if resp.usage else 0

    # tool calling 처리 루프 (최대 10회)
    if resp_tools and tool_executor:
        for _ in range(10):
            function_calls = [item for item in resp.output if item.type == "function_call"]
            if not function_calls:
                break

            tool_results = []
            for fc in function_calls:
                try:
                    args = json.loads(fc.arguments) if fc.arguments else {}
                    result = await tool_executor(fc.name, args)
                    tool_results.append({
                        "type": "function_call_output",
                        "call_id": fc.call_id,
                        "output": str(result)[:TOOL_RESULT_MAX_CHARS],
                    })
                except Exception as e:
                    logger.warning("도구 실행 실패 (%s): %s", fc.name, e)
                    tool_results.append({
                        "type": "function_call_output",
                        "call_id": fc.call_id,
                        "output": f"오류: {e}",
                    })

            # 이전 응답 ID로 연결하여 도구 결과 전달 (개별 타임아웃 적용)
            resp = await asyncio.wait_for(_openai_client.responses.create(
                model=model,
                input=tool_results,
                previous_response_id=resp.id,
                tools=resp_tools,
            ), timeout=ai_call_timeout)
            if resp.usage:
                total_input_tokens += resp.usage.input_tokens
                total_output_tokens += resp.usage.output_tokens

    content = resp.output_text or ""

    return {
        "content": content,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }


# ── spawn_agent 도구 스키마 (arm_server.py가 처장에게 제공) ──
SPAWN_AGENT_TOOL_SCHEMA = {
    "name": "spawn_agent",
    "description": "소속 전문가 에이전트를 호출하여 특정 분석/작업을 수행합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "호출할 전문가 에이전트 ID",
            },
            "task": {
                "type": "string",
                "description": "전문가에게 지시할 구체적인 작업 내용",
            },
        },
        "required": ["agent_id", "task"],
    },
}


async def ask_ai(
    user_message: str,
    system_prompt: str = "",
    model: str | None = None,
    tools: list | None = None,
    tool_executor: callable | None = None,
    reasoning_effort: str = "",
    conversation_history: list | None = None,
) -> dict:
    """AI에게 질문합니다 (프로바이더 자동 판별).

    Args:
        user_message: 사용자 메시지 (질문/명령)
        system_prompt: 시스템 프롬프트 (AI의 역할/맥락 설정)
        model: 사용할 AI 모델명 (None이면 자동 선택)
        tools: 도구 스키마 리스트 (Anthropic 포맷 기준).
            _load_tool_schemas()["anthropic"] 또는 _build_tool_schemas()의 반환값을 전달.
            프로바이더별 변환은 내부에서 자동 처리됩니다.
            None이면 도구 없이 기존과 동일하게 텍스트만 반환합니다.
        tool_executor: 도구 실행 함수 (async callable).
            시그니처: async def executor(tool_name: str, tool_input: dict) -> Any
            예: ToolPool.invoke를 래핑한 함수
        reasoning_effort: 추론 강도 ("low" | "medium" | "high" | "xhigh").
            Claude는 extended thinking을 활성화하고, OpenAI reasoning 모델은 reasoning_effort를 전달합니다.
            빈 문자열("")이면 일반 모드로 동작합니다.
        conversation_history: 이전 대화 기록 리스트 (선택).
            [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
            제공하면 현재 메시지 앞에 삽입하여 대화 맥락을 유지합니다.

    반환: {"content", "model", "input_tokens", "output_tokens", "cost_usd", "time_seconds"}
    AI 불가 시: {"error": "사유"}
    """
    if not is_ai_ready():
        return {"error": "AI 미연결 — API 키를 확인하세요"}

    # 현재 한국 날짜/시간(KST) 자동 주입 — AI가 항상 정확한 날짜를 알 수 있도록
    from datetime import datetime, timezone, timedelta
    _kst = timezone(timedelta(hours=9))
    _now_kst = datetime.now(_kst)
    _date_prefix = (
        f"[현재 한국 날짜/시간] {_now_kst.strftime('%Y년 %m월 %d일 %H:%M')} (KST)\n\n"
    )
    _title_rule = (
        "[보고서 작성 규칙] 보고서 첫 줄은 반드시 주제를 요약하는 제목으로 시작하세요. "
        "예: 'NVDA 기술적 분석 — 단기 상승 전환 신호'. "
        "나쁜 예: '죄송합니다', '안녕하세요', 에이전트 이름만.\n\n"
    )
    if system_prompt:
        system_prompt = _date_prefix + _title_rule + system_prompt
    else:
        system_prompt = _date_prefix + _title_rule

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

    # 프로바이더별 도구 스키마 변환
    provider_tools = None
    if tools and tool_executor:
        if provider == "anthropic":
            # Anthropic 포맷은 그대로 사용
            provider_tools = tools
        elif provider == "openai":
            # OpenAI function calling 포맷으로 변환
            # GPT-5.2 strict 모드: 재귀적 additionalProperties 적용
            provider_tools = []
            for t in tools:
                schema = copy.deepcopy(t.get("input_schema", {"type": "object", "properties": {}}))
                if schema.get("type") != "object":
                    schema = {"type": "object", "properties": {"query": {"type": "string", "description": "도구에 전달할 질문"}}, "required": ["query"]}
                if not schema.get("properties"):
                    schema["properties"] = {"query": {"type": "string", "description": "도구에 전달할 질문"}}
                _apply_openai_strict_inline(schema)
                provider_tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "strict": True,
                        "parameters": schema,
                    },
                })
        elif provider == "google":
            # Google Gemini 포맷은 _call_google 내부에서 변환
            provider_tools = tools

    # 개별 AI API 호출 타임아웃 (도구 실행 시간은 제외됨)
    # 도구 사용 시 AI가 여러 번 호출되므로, 각 호출마다 독립 타임아웃 적용
    AI_CALL_TIMEOUT = 600  # 10분 — 개별 AI 호출 1회당 최대 대기 시간 (GPT-5.2-pro 추론 모델 대응)

    start = time.time()
    try:
        if provider == "anthropic":
            coro = _call_anthropic(
                user_message, system_prompt, model,
                tools=provider_tools, tool_executor=tool_executor,
                reasoning_effort=reasoning_effort,
                conversation_history=conversation_history,
                ai_call_timeout=AI_CALL_TIMEOUT,
            )
        elif provider == "google":
            coro = _call_google(
                user_message, system_prompt, model,
                tools=provider_tools, tool_executor=tool_executor,
                reasoning_effort=reasoning_effort,
                conversation_history=conversation_history,
                ai_call_timeout=AI_CALL_TIMEOUT,
            )
        elif provider == "openai":
            if model in OPENAI_RESPONSES_ONLY_MODELS:
                # Responses API 전용 모델 (gpt-5.2-pro 등)
                coro = _call_openai_responses(
                    user_message, system_prompt, model,
                    tools=provider_tools, tool_executor=tool_executor,
                    reasoning_effort=reasoning_effort,
                    conversation_history=conversation_history,
                    ai_call_timeout=AI_CALL_TIMEOUT,
                )
            else:
                coro = _call_openai(
                    user_message, system_prompt, model,
                    tools=provider_tools, tool_executor=tool_executor,
                    reasoning_effort=reasoning_effort,
                    conversation_history=conversation_history,
                    ai_call_timeout=AI_CALL_TIMEOUT,
                )
        else:
            return {"error": f"알 수 없는 프로바이더: {provider}"}

        # 도구 실행 시간은 타임아웃에서 제외 — 개별 AI API 호출에만 타임아웃 적용됨
        result = await coro
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        logger.error("AI 응답 시간 초과 (%s/%s): %.1f초", provider, model, elapsed)
        return {"error": f"AI 응답 시간 초과 ({provider}/{model}) — {AI_CALL_TIMEOUT}초 제한 초과 (도구 시간 제외, 순수 AI 응답만)"}
    except Exception as e:
        err_str = str(e)
        err_type = type(e).__name__
        logger.error("AI 호출 실패 (%s/%s): %s", provider, model, err_str[:500])

        # 429 에러 (요율 제한): 충분한 대기 후 재시도 (Google 쿨타임 ≥ 60초)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "ResourceExhausted" in err_type:
            _RETRY_DELAYS = [15, 30, 60, 60, 120]  # 이전: 2,4,8,16,32 → 쿨타임 부족
            for retry_i in range(1, 6):
                delay = _RETRY_DELAYS[retry_i - 1] + random.uniform(1, 5)  # 지터 추가 (동시 재시도 방지)
                logger.warning("429 요율 제한 (%s) → %.0f초 후 재시도 (%d/5)", model, delay, retry_i)
                await asyncio.sleep(delay)
                try:
                    if provider == "anthropic":
                        retry_coro = _call_anthropic(
                            user_message, system_prompt, model,
                            tools=provider_tools, tool_executor=tool_executor,
                            reasoning_effort=reasoning_effort,
                            conversation_history=conversation_history,
                            ai_call_timeout=AI_CALL_TIMEOUT,
                        )
                    elif provider == "google":
                        retry_coro = _call_google(
                            user_message, system_prompt, model,
                            tools=provider_tools, tool_executor=tool_executor,
                            reasoning_effort=reasoning_effort,
                            conversation_history=conversation_history,
                            ai_call_timeout=AI_CALL_TIMEOUT,
                        )
                    elif provider == "openai":
                        if model in OPENAI_RESPONSES_ONLY_MODELS:
                            retry_coro = _call_openai_responses(
                                user_message, system_prompt, model,
                                tools=provider_tools, tool_executor=tool_executor,
                                reasoning_effort=reasoning_effort,
                                conversation_history=conversation_history,
                                ai_call_timeout=AI_CALL_TIMEOUT,
                            )
                        else:
                            retry_coro = _call_openai(
                                user_message, system_prompt, model,
                                tools=provider_tools, tool_executor=tool_executor,
                                reasoning_effort=reasoning_effort,
                                conversation_history=conversation_history,
                                ai_call_timeout=AI_CALL_TIMEOUT,
                            )
                    else:
                        break
                    result = await retry_coro
                    elapsed = time.time() - start
                    input_tokens = result.get("input_tokens", 0)
                    output_tokens = result.get("output_tokens", 0)
                    cost = _calc_cost(model, input_tokens, output_tokens)
                    logger.info("429 재시도 %d/5 성공 (%s): %.1f초", retry_i, model, elapsed)
                    return {
                        "content": result["content"],
                        "model": model,
                        "provider": provider,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cost_usd": round(cost, 6),
                        "time_seconds": round(elapsed, 2),
                        "retry_count": retry_i,
                    }
                except Exception as retry_e:
                    retry_err = str(retry_e)
                    if "429" not in retry_err and "RESOURCE_EXHAUSTED" not in retry_err:
                        logger.error("429 재시도 %d/5 중 다른 에러: %s", retry_i, retry_err[:200])
                        break
                    logger.warning("429 재시도 %d/5 실패 (%s)", retry_i, model)
            logger.error("429 재시도 5회 모두 실패 (%s/%s) → 다른 프로바이더로 폴백 시도", provider, model)
            # 429 5회 실패 → 다른 프로바이더로 폴백
            _fb_429 = _pick_fallback_model(provider, exclude=provider)
            if _fb_429:
                _fb_429_provider = _get_provider(_fb_429)
                logger.warning("429 프로바이더 폴백: %s → %s (%s)", model, _fb_429, _fb_429_provider)
                try:
                    return await ask_ai(
                        user_message, system_prompt, model=_fb_429,
                        tools=tools, tool_executor=tool_executor,
                        reasoning_effort=reasoning_effort,
                        conversation_history=conversation_history,
                    )
                except Exception as fb_e:
                    logger.error("429 폴백도 실패: %s", str(fb_e)[:200])
            return {"error": f"AI 호출 실패 ({provider}): 요율 제한 5회 재시도 + 폴백 모두 실패 — {err_str[:300]}"}

        # 404 에러 (모델 미지원): 동일 프로바이더 내 폴백 → 다른 프로바이더 폴백
        if "404" in err_str or "NotFoundError" in err_type:
            _FALLBACK_MODELS = {
                # OpenAI 체인
                "gpt-5.2-pro": "gpt-5.2", "gpt-5.2": "gpt-5", "gpt-5": "gpt-5-mini",
                # Anthropic 체인
                "claude-opus-4-6": "claude-sonnet-4-6", "claude-sonnet-4-6": "claude-haiku-4-5-20251001",
                # Google 체인
                "gemini-3.1-pro-preview": "gemini-2.5-pro", "gemini-2.5-pro": "gemini-2.5-flash",
            }
            fallback = _FALLBACK_MODELS.get(model)
            if not fallback:
                # 동일 프로바이더 내 폴백 없으면 다른 프로바이더로
                fallback = _pick_fallback_model(provider, exclude=provider)
            if fallback:
                logger.warning("모델 %s 404 에러 → %s로 폴백 재시도", model, fallback)
                try:
                    return await ask_ai(
                        user_message, system_prompt, model=fallback,
                        tools=tools, tool_executor=tool_executor,
                        reasoning_effort=reasoning_effort,
                        conversation_history=conversation_history,
                    )
                except Exception as fallback_e:
                    logger.error("폴백 모델 %s도 실패: %s", fallback, str(fallback_e)[:200])

        # 400 크레딧/빌링 소진: 다른 프로바이더로 폴백
        _is_credit_error = (
            ("400" in err_str or "BadRequest" in err_type)
            and any(kw in err_str.lower() for kw in ("credit balance", "billing", "insufficient_quota", "quota"))
        )
        if _is_credit_error:
            logger.error("=== %s 크레딧 소진 감지 ===\n%s", provider, err_str[:500])
            mark_provider_exhausted(provider)  # 이후 호출에서도 이 프로바이더 건너뜀
            _fb = _pick_fallback_model(provider, exclude=provider)
            if _fb:
                _fb_provider = _get_provider(_fb)
                logger.warning("%s 크레딧 소진 → %s(%s)로 폴백 재시도", provider, _fb, _fb_provider)
                try:
                    if _fb_provider == "anthropic":
                        fb_coro = _call_anthropic(
                            user_message, system_prompt, _fb,
                            tools=provider_tools, tool_executor=tool_executor,
                            reasoning_effort=reasoning_effort,
                            conversation_history=conversation_history,
                            ai_call_timeout=AI_CALL_TIMEOUT,
                        )
                    elif _fb_provider == "google":
                        fb_coro = _call_google(
                            user_message, system_prompt, _fb,
                            tools=provider_tools, tool_executor=tool_executor,
                            reasoning_effort=reasoning_effort,
                            conversation_history=conversation_history,
                            ai_call_timeout=AI_CALL_TIMEOUT,
                        )
                    elif _fb_provider == "openai":
                        if _fb in OPENAI_RESPONSES_ONLY_MODELS:
                            fb_coro = _call_openai_responses(
                                user_message, system_prompt, _fb,
                                tools=provider_tools, tool_executor=tool_executor,
                                reasoning_effort=reasoning_effort,
                                conversation_history=conversation_history,
                                ai_call_timeout=AI_CALL_TIMEOUT,
                            )
                        else:
                            fb_coro = _call_openai(
                                user_message, system_prompt, _fb,
                                tools=provider_tools, tool_executor=tool_executor,
                                reasoning_effort=reasoning_effort,
                                conversation_history=conversation_history,
                                ai_call_timeout=AI_CALL_TIMEOUT,
                            )
                    else:
                        fb_coro = None
                    if fb_coro:
                        result = await fb_coro
                        elapsed = time.time() - start
                        input_tokens = result.get("input_tokens", 0)
                        output_tokens = result.get("output_tokens", 0)
                        cost = _calc_cost(_fb, input_tokens, output_tokens)
                        logger.info("크레딧 소진 폴백 성공: %s → %s (%.1f초)", model, _fb, elapsed)
                        return {
                            "content": result["content"],
                            "model": _fb,
                            "provider": _fb_provider,
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "cost_usd": round(cost, 6),
                            "time_seconds": round(elapsed, 2),
                            "fallback_from": model,
                            "fallback_reason": "credit_exhausted",
                        }
                except Exception as fb_e:
                    logger.error("크레딧 소진 폴백(%s)도 실패: %s", _fb, str(fb_e)[:200])

        # 400 에러 상세 로깅 (디버깅용)
        if "400" in err_str or "BadRequest" in err_type:
            logger.error("=== 400 에러 전문 ===\n%s\n=== 끝 ===", err_str[:2000])
        return {"error": f"AI 호출 실패 ({provider}): {err_str[:500]}"}

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


# ══════════════════════════════════════════════════════════════
# ── AI Batch API (프로바이더별 대량 요청 — 실시간보다 저렴) ──
# ══════════════════════════════════════════════════════════════

async def batch_submit(
    requests: list[dict],
    model: str | None = None,
) -> dict:
    """여러 AI 요청을 Batch API로 한꺼번에 제출합니다.

    각 프로바이더의 배치 API를 사용하여 실시간보다 저렴하게(~50% 할인) 처리합니다.
    요청이 접수되면 batch_id가 반환되며, 결과는 나중에 batch_retrieve()로 가져옵니다.

    Args:
        requests: [{"custom_id": "req-1", "message": "...", "system_prompt": "...", "model": "..."}]
        model: 기본 모델 (개별 요청에 model이 없을 때 사용)

    Returns:
        {"batch_id": "...", "provider": "...", "status": "submitted", "count": N}
        실패 시: {"error": "사유"}
    """
    if not requests:
        return {"error": "요청 목록이 비어있습니다"}

    if model is None:
        model = "claude-sonnet-4-6"

    provider = _get_provider(model)

    try:
        if provider == "anthropic":
            return await _batch_submit_anthropic(requests, model)
        elif provider == "openai":
            return await _batch_submit_openai(requests, model)
        elif provider == "google":
            return await _batch_submit_google(requests, model)
        else:
            return {"error": f"알 수 없는 프로바이더: {provider}"}
    except Exception as e:
        logger.error("배치 제출 실패 (%s): %s", provider, e)
        return {"error": f"배치 제출 실패 ({provider}): {str(e)[:200]}"}


async def batch_check(batch_id: str, provider: str) -> dict:
    """배치 상태를 확인합니다.

    Returns:
        {"batch_id": "...", "status": "processing|completed|failed|expired",
         "progress": {"completed": N, "total": M}}
    """
    try:
        if provider == "anthropic":
            return await _batch_check_anthropic(batch_id)
        elif provider == "openai":
            return await _batch_check_openai(batch_id)
        elif provider == "google":
            return await _batch_check_google(batch_id)
        else:
            return {"error": f"알 수 없는 프로바이더: {provider}"}
    except Exception as e:
        logger.error("배치 상태 확인 실패 (%s/%s): %s", provider, batch_id, e)
        return {"error": str(e)[:200]}


async def batch_retrieve(batch_id: str, provider: str) -> dict:
    """완료된 배치의 결과를 가져옵니다.

    Returns:
        {"batch_id": "...", "results": [{"custom_id": "...", "content": "...", "error": None}]}
    """
    try:
        if provider == "anthropic":
            return await _batch_retrieve_anthropic(batch_id)
        elif provider == "openai":
            return await _batch_retrieve_openai(batch_id)
        elif provider == "google":
            return await _batch_retrieve_google(batch_id)
        else:
            return {"error": f"알 수 없는 프로바이더: {provider}"}
    except Exception as e:
        logger.error("배치 결과 조회 실패 (%s/%s): %s", provider, batch_id, e)
        return {"error": str(e)[:200]}


# ── Anthropic Batch API ──

async def _batch_submit_anthropic(requests: list[dict], default_model: str) -> dict:
    """Anthropic Message Batches API로 제출합니다."""
    if not _anthropic_client:
        return {"error": "Anthropic API 키가 설정되지 않았습니다"}

    batch_requests = []
    for req in requests:
        model = req.get("model", default_model)
        messages = [{"role": "user", "content": req.get("message", "")}]
        params = {
            "model": model,
            "max_tokens": req.get("max_tokens", 16384),
            "messages": messages,
        }
        if req.get("system_prompt"):
            params["system"] = req["system_prompt"]

        batch_requests.append({
            "custom_id": req.get("custom_id", f"req-{len(batch_requests)}"),
            "params": params,
        })

    batch = await _anthropic_client.messages.batches.create(
        requests=batch_requests
    )

    return {
        "batch_id": batch.id,
        "provider": "anthropic",
        "status": "submitted",
        "count": len(batch_requests),
        "processing_status": getattr(batch, "processing_status", "in_progress"),
    }


async def _batch_check_anthropic(batch_id: str) -> dict:
    """Anthropic 배치 상태를 확인합니다."""
    if not _anthropic_client:
        return {"error": "Anthropic API 키가 설정되지 않았습니다"}

    batch = await _anthropic_client.messages.batches.retrieve(batch_id)

    # processing_status: in_progress, ended, canceling, canceled, expired
    status_map = {
        "in_progress": "processing",
        "ended": "completed",
        "canceling": "processing",
        "canceled": "failed",
        "expired": "expired",
    }
    status = status_map.get(getattr(batch, "processing_status", ""), "processing")

    counts = getattr(batch, "request_counts", None)
    progress = {}
    if counts:
        progress = {
            "completed": getattr(counts, "succeeded", 0) + getattr(counts, "errored", 0),
            "total": getattr(counts, "processing", 0) + getattr(counts, "succeeded", 0)
                   + getattr(counts, "errored", 0) + getattr(counts, "canceled", 0),
            "succeeded": getattr(counts, "succeeded", 0),
            "errored": getattr(counts, "errored", 0),
        }

    return {"batch_id": batch_id, "provider": "anthropic", "status": status, "progress": progress}


async def _batch_retrieve_anthropic(batch_id: str) -> dict:
    """Anthropic 배치 결과를 가져옵니다."""
    if not _anthropic_client:
        return {"error": "Anthropic API 키가 설정되지 않았습니다"}

    results = []
    async for result in _anthropic_client.messages.batches.results(batch_id):
        custom_id = result.custom_id
        if result.result.type == "succeeded":
            msg = result.result.message
            text_blocks = [b.text for b in msg.content if b.type == "text"]
            content = "\n".join(text_blocks) if text_blocks else ""
            in_tok = msg.usage.input_tokens if msg.usage else 0
            out_tok = msg.usage.output_tokens if msg.usage else 0
            model = msg.model or ""
            results.append({
                "custom_id": custom_id,
                "content": content,
                "model": model,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": round(_calc_cost(model, in_tok, out_tok), 6),
                "error": None,
            })
        else:
            error_msg = str(getattr(result.result, "error", "알 수 없는 오류"))
            results.append({
                "custom_id": custom_id,
                "content": "",
                "error": error_msg,
            })

    return {"batch_id": batch_id, "provider": "anthropic", "results": results}


# ── OpenAI Batch API ──

async def _batch_submit_openai(requests: list[dict], default_model: str) -> dict:
    """OpenAI Batch API로 제출합니다."""
    if not _openai_client:
        return {"error": "OpenAI API 키가 설정되지 않았습니다"}

    # JSONL 파일 생성
    lines = []
    for req in requests:
        model = req.get("model", default_model)
        messages = []
        if req.get("system_prompt"):
            messages.append({"role": "system", "content": req["system_prompt"]})
        messages.append({"role": "user", "content": req.get("message", "")})

        line = {
            "custom_id": req.get("custom_id", f"req-{len(lines)}"),
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": model,
                "messages": messages,
                "max_completion_tokens": req.get("max_completion_tokens", 65536),
            },
        }
        lines.append(json.dumps(line, ensure_ascii=False))

    jsonl_content = "\n".join(lines)

    # 파일 업로드 — OpenAI SDK는 (파일명, bytes) 튜플 또는 파일 객체가 필요
    file_obj = await _openai_client.files.create(
        file=("batch.jsonl", jsonl_content.encode("utf-8")),
        purpose="batch",
    )

    # 배치 생성
    batch = await _openai_client.batches.create(
        input_file_id=file_obj.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )

    return {
        "batch_id": batch.id,
        "provider": "openai",
        "status": "submitted",
        "count": len(lines),
        "input_file_id": file_obj.id,
    }


async def _batch_check_openai(batch_id: str) -> dict:
    """OpenAI 배치 상태를 확인합니다."""
    if not _openai_client:
        return {"error": "OpenAI API 키가 설정되지 않았습니다"}

    batch = await _openai_client.batches.retrieve(batch_id)

    status_map = {
        "validating": "processing",
        "in_progress": "processing",
        "finalizing": "processing",
        "completed": "completed",
        "failed": "failed",
        "expired": "expired",
        "cancelling": "processing",
        "cancelled": "failed",
    }
    status = status_map.get(batch.status, "processing")

    counts = batch.request_counts or {}
    progress = {
        "completed": getattr(counts, "completed", 0),
        "total": getattr(counts, "total", 0),
        "failed": getattr(counts, "failed", 0),
    }

    return {
        "batch_id": batch_id,
        "provider": "openai",
        "status": status,
        "progress": progress,
        "output_file_id": getattr(batch, "output_file_id", None),
    }


async def _batch_retrieve_openai(batch_id: str) -> dict:
    """OpenAI 배치 결과를 가져옵니다."""
    if not _openai_client:
        return {"error": "OpenAI API 키가 설정되지 않았습니다"}

    # 배치 상태에서 output_file_id 가져오기
    batch = await _openai_client.batches.retrieve(batch_id)
    output_file_id = getattr(batch, "output_file_id", None)
    if not output_file_id:
        return {"error": "아직 결과 파일이 없습니다 (배치 진행 중)"}

    # 결과 파일 다운로드
    content = await _openai_client.files.content(output_file_id)
    text = content.text if hasattr(content, "text") else content.read().decode("utf-8")

    results = []
    for line in text.strip().split("\n"):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            custom_id = obj.get("custom_id", "")
            response = obj.get("response", {})
            body = response.get("body", {})
            choices = body.get("choices", [])

            if choices:
                msg_content = choices[0].get("message", {}).get("content", "")
                usage = body.get("usage", {})
                model = body.get("model", "")
                in_tok = usage.get("prompt_tokens", 0)
                out_tok = usage.get("completion_tokens", 0)
                results.append({
                    "custom_id": custom_id,
                    "content": msg_content,
                    "model": model,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "cost_usd": round(_calc_cost(model, in_tok, out_tok), 6),
                    "error": None,
                })
            else:
                error = obj.get("error", {})
                results.append({
                    "custom_id": custom_id,
                    "content": "",
                    "error": error.get("message", "결과 없음"),
                })
        except json.JSONDecodeError:
            continue

    return {"batch_id": batch_id, "provider": "openai", "results": results}


# ── Google Gemini Batch API ──
# google-genai SDK의 client.batches.create()를 사용합니다.
# API 키 방식으로 사용 가능합니다 (Vertex AI 불필요).
# 50% 할인된 가격, 24시간 내 처리.

# Gemini 배치 메타 저장소 (custom_id 매핑용 — 메모리 내)
_google_batch_meta: dict[str, dict] = {}


async def _batch_submit_google(requests: list[dict], default_model: str) -> dict:
    """Gemini Batch API로 제출합니다.

    google-genai SDK의 client.batches.create()를 사용합니다.
    인라인 요청 방식 (20MB 이하).
    """
    if not _google_client:
        return {"error": "Google API 키가 설정되지 않았습니다"}

    # 인라인 요청 포맷으로 변환
    # system_instruction은 SDK 배치에서 인식 안 됨 → 메시지에 합쳐서 보냄
    # (CEO Apps Script 코드 패턴: basePrompt + "\n\n---\n\n" + userText)
    inline_requests = []
    custom_id_map = {}  # batch 내 인덱스 → custom_id 매핑

    for i, req in enumerate(requests):
        # 시스템 프롬프트를 사용자 메시지 앞에 합침
        user_text = req.get("message", "")
        if req.get("system_prompt"):
            user_text = req["system_prompt"] + "\n\n---\n\n" + user_text

        request_body = {
            "contents": [
                {
                    "parts": [{"text": user_text}],
                    "role": "user",
                }
            ],
            "generation_config": {
                "temperature": req.get("temperature", 0.3),
                "max_output_tokens": req.get("max_output_tokens", 16384),
            },
        }

        inline_requests.append(request_body)
        custom_id_map[i] = req.get("custom_id", f"req-{i}")

    model = requests[0].get("model", default_model) if requests else default_model

    def _sync_submit():
        return _google_client.batches.create(
            model=model,
            src=inline_requests,
            config={"display_name": f"corthex_batch_{int(time.time())}"},
        )

    batch_job = await asyncio.to_thread(_sync_submit)

    # custom_id 매핑 저장 (결과 조회 시 필요)
    _google_batch_meta[batch_job.name] = {
        "custom_id_map": custom_id_map,
        "model": model,
    }

    return {
        "batch_id": batch_job.name,
        "provider": "google",
        "status": "submitted",
        "count": len(inline_requests),
    }


async def _batch_check_google(batch_id: str) -> dict:
    """Gemini 배치 상태를 확인합니다."""
    if not _google_client:
        return {"error": "Google API 키가 설정되지 않았습니다"}

    def _sync_get():
        return _google_client.batches.get(name=batch_id)

    batch_job = await asyncio.to_thread(_sync_get)

    # Gemini 상태 → 우리 표준 상태로 변환
    state_name = batch_job.state.name if batch_job.state else "UNKNOWN"
    status_map = {
        "JOB_STATE_PENDING": "processing",
        "JOB_STATE_RUNNING": "processing",
        "JOB_STATE_SUCCEEDED": "completed",
        "JOB_STATE_FAILED": "failed",
        "JOB_STATE_CANCELLED": "failed",
        "JOB_STATE_EXPIRED": "expired",
    }
    status = status_map.get(state_name, "processing")

    return {
        "batch_id": batch_id,
        "provider": "google",
        "status": status,
        "progress": {"state": state_name},
    }


async def _batch_retrieve_google(batch_id: str) -> dict:
    """Gemini 배치 결과를 가져옵니다."""
    if not _google_client:
        return {"error": "Google API 키가 설정되지 않았습니다"}

    def _sync_get():
        return _google_client.batches.get(name=batch_id)

    batch_job = await asyncio.to_thread(_sync_get)

    state_name = batch_job.state.name if batch_job.state else "UNKNOWN"
    if state_name != "JOB_STATE_SUCCEEDED":
        return {"error": f"아직 처리 중입니다 (상태: {state_name})"}

    # custom_id 매핑 가져오기
    meta = _google_batch_meta.get(batch_id, {})
    custom_id_map = meta.get("custom_id_map", {})
    model = meta.get("model", "gemini-2.5-flash")

    results = []

    # 인라인 결과 추출
    dest = getattr(batch_job, "dest", None)
    inlined = getattr(dest, "inlined_responses", None) if dest else None

    if inlined:
        for i, resp_item in enumerate(inlined):
            custom_id = custom_id_map.get(i, f"req-{i}")
            try:
                response = getattr(resp_item, "response", None)
                if response:
                    # 텍스트 추출
                    content = ""
                    if hasattr(response, "text"):
                        content = response.text
                    elif hasattr(response, "candidates") and response.candidates:
                        text_parts = []
                        for part in response.candidates[0].content.parts:
                            if hasattr(part, "text") and part.text:
                                text_parts.append(part.text)
                        content = "\n".join(text_parts)

                    # 토큰 사용량 추출
                    usage = getattr(response, "usage_metadata", None)
                    in_tok = getattr(usage, "prompt_token_count", 0) if usage else 0
                    out_tok = getattr(usage, "candidates_token_count", 0) if usage else 0

                    results.append({
                        "custom_id": custom_id,
                        "content": content,
                        "model": model,
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "cost_usd": round(_calc_cost(model, in_tok, out_tok) * 0.5, 6),
                        "error": None,
                    })
                else:
                    results.append({
                        "custom_id": custom_id,
                        "content": "",
                        "error": "응답이 비어있습니다",
                    })
            except Exception as e:
                results.append({
                    "custom_id": custom_id,
                    "content": "",
                    "error": str(e),
                })

    # 파일 기반 결과 처리 (대용량 배치일 때)
    elif dest and getattr(dest, "file_name", None):
        try:
            def _sync_download():
                return _google_client.files.download(file=dest.file_name)

            file_content = await asyncio.to_thread(_sync_download)
            text = file_content.decode("utf-8") if isinstance(file_content, bytes) else str(file_content)

            for i, line in enumerate(text.strip().split("\n")):
                if not line.strip():
                    continue
                custom_id = custom_id_map.get(i, f"req-{i}")
                try:
                    obj = json.loads(line)
                    candidates = obj.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        content = "\n".join(p.get("text", "") for p in parts if "text" in p)
                        usage = obj.get("usageMetadata", {})
                        in_tok = usage.get("promptTokenCount", 0)
                        out_tok = usage.get("candidatesTokenCount", 0)
                        results.append({
                            "custom_id": custom_id,
                            "content": content,
                            "model": model,
                            "input_tokens": in_tok,
                            "output_tokens": out_tok,
                            "cost_usd": round(_calc_cost(model, in_tok, out_tok) * 0.5, 6),
                            "error": None,
                        })
                    else:
                        error = obj.get("error", {})
                        results.append({
                            "custom_id": custom_id,
                            "content": "",
                            "error": error.get("message", "결과 없음") if isinstance(error, dict) else str(error),
                        })
                except json.JSONDecodeError:
                    results.append({
                        "custom_id": custom_id,
                        "content": "",
                        "error": f"결과 파싱 실패",
                    })
        except Exception as e:
            return {"error": f"결과 파일 다운로드 실패: {str(e)[:200]}"}

    # 메모리 정리 (결과 반환 후 1시간 뒤 삭제)
    try:
        asyncio.get_running_loop().call_later(3600, lambda: _google_batch_meta.pop(batch_id, None))
    except Exception:
        pass

    return {"batch_id": batch_id, "provider": "google", "results": results}


# ══════════════════════════════════════════════════════════════
# ── 프로바이더별 그룹 배치 제출 (배치 체인용) ──
# ══════════════════════════════════════════════════════════════

async def batch_submit_grouped(
    requests: list[dict],
) -> list[dict]:
    """여러 AI 요청을 프로바이더별로 자동 그룹화하여 각각의 Batch API에 제출합니다.

    각 요청에 "model"이 있으면 해당 모델의 프로바이더로 분류됩니다.
    같은 프로바이더끼리 모아서 하나의 Batch API 호출로 제출합니다.

    예: Claude 에이전트 2명 + GPT 에이전트 1명 + Gemini 에이전트 1명
        → Anthropic Batch (2건) + OpenAI Batch (1건) + Google Batch (1건)
        → 3개 배치가 각각 제출됨

    Args:
        requests: [
            {
                "custom_id": "agent_stock_analysis",
                "message": "삼성전자 주가 분석",
                "system_prompt": "당신은 주식 분석 전문가입니다...",
                "model": "claude-sonnet-4-6",
            },
            ...
        ]

    Returns:
        [
            {
                "batch_id": "batch_abc123",
                "provider": "anthropic",
                "status": "submitted",
                "count": 2,
                "custom_ids": ["agent_1", "agent_2"],
            },
            {
                "batch_id": "batch_xyz789",
                "provider": "openai",
                "status": "submitted",
                "count": 1,
                "custom_ids": ["agent_3"],
            },
        ]
        실패한 프로바이더는 {"provider": "...", "error": "..."} 형태로 포함됩니다.
    """
    if not requests:
        return [{"error": "요청 목록이 비어있습니다"}]

    providers = get_available_providers()

    # 프로바이더별 그룹화
    groups: dict[str, list[dict]] = {}
    for req in requests:
        model = req.get("model", "claude-sonnet-4-6")
        provider = _get_provider(model)
        groups.setdefault(provider, []).append(req)

    # 폴백용 모델 매핑 (프로바이더 실패 시 다른 프로바이더로 재시도)
    _fallback_models = {
        "anthropic": "gemini-2.5-flash" if providers.get("google") else ("gpt-5-mini" if providers.get("openai") else None),
        "google": "claude-sonnet-4-6" if providers.get("anthropic") else ("gpt-5-mini" if providers.get("openai") else None),
        "openai": "claude-sonnet-4-6" if providers.get("anthropic") else ("gemini-2.5-flash" if providers.get("google") else None),
    }

    results = []
    for provider, group_reqs in groups.items():
        default_model = group_reqs[0].get("model", "claude-sonnet-4-6")
        try:
            result = await batch_submit(group_reqs, model=default_model)
            if "error" not in result:
                result["custom_ids"] = [r.get("custom_id", "") for r in group_reqs]
                results.append(result)
            else:
                # 배치 제출 실패 → 폴백 프로바이더로 재시도
                fallback_model = _fallback_models.get(provider)
                if fallback_model:
                    logger.warning("배치 제출 실패 (%s) → %s로 폴백 재시도", provider, _get_provider(fallback_model))
                    for req in group_reqs:
                        req["model"] = fallback_model
                    retry_result = await batch_submit(group_reqs, model=fallback_model)
                    if "error" not in retry_result:
                        retry_result["custom_ids"] = [r.get("custom_id", "") for r in group_reqs]
                        retry_result["fallback_from"] = provider
                    results.append(retry_result)
                else:
                    results.append(result)
        except Exception as e:
            logger.error("배치 그룹 제출 실패 (%s): %s", provider, e)
            # 예외 발생 시에도 폴백 시도
            fallback_model = _fallback_models.get(provider)
            if fallback_model:
                try:
                    logger.warning("배치 예외 (%s) → %s로 폴백", provider, _get_provider(fallback_model))
                    for req in group_reqs:
                        req["model"] = fallback_model
                    retry_result = await batch_submit(group_reqs, model=fallback_model)
                    if "error" not in retry_result:
                        retry_result["custom_ids"] = [r.get("custom_id", "") for r in group_reqs]
                        retry_result["fallback_from"] = provider
                    results.append(retry_result)
                except Exception as e2:
                    logger.error("폴백도 실패 (%s → %s): %s", provider, _get_provider(fallback_model), e2)
                    results.append({
                        "provider": provider,
                        "error": f"제출 실패 (폴백 포함): {str(e)[:100]} / {str(e2)[:100]}",
                        "custom_ids": [r.get("custom_id", "") for r in group_reqs],
                    })
            else:
                results.append({
                    "provider": provider,
                    "error": f"제출 실패: {str(e)[:200]}",
                    "custom_ids": [r.get("custom_id", "") for r in group_reqs],
                })

    return results
