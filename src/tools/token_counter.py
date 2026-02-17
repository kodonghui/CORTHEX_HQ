"""토큰 카운터 도구 — AI 모델 토큰 수 계산 및 비용 예측."""
from __future__ import annotations

import logging
import os
from typing import Any

import yaml

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.token_counter")


def _get_tiktoken():
    """tiktoken 지연 임포트."""
    try:
        import tiktoken
        return tiktoken
    except ImportError:
        return None


# 모델별 tiktoken 인코딩 매핑
_MODEL_ENCODINGS: dict[str, str] = {
    "gpt-5-mini": "o200k_base",
    "gpt-5": "o200k_base",
    "gpt-5.1": "o200k_base",
    "gpt-5.2": "o200k_base",
    "gpt-5.2-pro": "o200k_base",
    "claude-opus-4-6": "cl100k_base",
    "claude-sonnet-4-6": "cl100k_base",
    "claude-haiku-4-5-20251001": "cl100k_base",
}


class TokenCounterTool(BaseTool):
    """텍스트의 토큰 수 계산, 비용 예측, 토큰 한도 맞춤 자르기."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "count")
        if action == "count":
            return await self._count(kwargs)
        elif action == "estimate_cost":
            return await self._estimate_cost(kwargs)
        elif action == "truncate":
            return await self._truncate(kwargs)
        elif action == "compare":
            return await self._compare(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: count(토큰 수 계산), estimate_cost(비용 예측), "
                "truncate(토큰 한도 자르기), compare(모델별 비교)"
            )

    # ── 내부 메서드 ──

    def _get_encoder(self, model: str):
        """모델에 맞는 tiktoken 인코더 반환."""
        tiktoken = _get_tiktoken()
        if tiktoken is None:
            return None

        encoding_name = _MODEL_ENCODINGS.get(model, "cl100k_base")
        try:
            return tiktoken.get_encoding(encoding_name)
        except Exception:
            return tiktoken.get_encoding("cl100k_base")

    def _load_model_prices(self) -> dict[str, dict]:
        """models.yaml에서 모델별 가격 정보 로드."""
        config_path = os.path.join(os.getcwd(), "config", "models.yaml")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            prices: dict[str, dict] = {}
            for provider in data.get("providers", []):
                for model in provider.get("models", []):
                    model_id = model.get("model_id", "")
                    prices[model_id] = {
                        "input_per_1m": model.get("input_per_1m_tokens_usd", 0),
                        "output_per_1m": model.get("output_per_1m_tokens_usd", 0),
                    }
            return prices
        except Exception:
            return {}

    async def _count(self, kwargs: dict) -> str:
        """텍스트의 토큰 수 계산."""
        text = kwargs.get("text", "")
        model = kwargs.get("model", "gpt-5-mini")

        if not text:
            return "텍스트(text)를 입력해주세요."

        tiktoken = _get_tiktoken()
        if tiktoken is None:
            return "tiktoken 라이브러리가 설치되지 않았습니다. pip install tiktoken"

        encoder = self._get_encoder(model)
        if encoder is None:
            return "tiktoken 인코더를 로드할 수 없습니다."

        tokens = encoder.encode(text)
        token_count = len(tokens)
        char_count = len(text)
        ratio = char_count / token_count if token_count > 0 else 0

        return (
            f"## 토큰 계산 결과\n\n"
            f"| 항목 | 값 |\n"
            f"|------|----|\n"
            f"| 모델 | {model} |\n"
            f"| 글자 수 | {char_count:,} |\n"
            f"| 토큰 수 | {token_count:,} |\n"
            f"| 글자/토큰 비율 | {ratio:.1f} |\n"
        )

    async def _estimate_cost(self, kwargs: dict) -> str:
        """텍스트를 특정 모델에 보낼 때 예상 비용 계산."""
        text = kwargs.get("text", "")
        model = kwargs.get("model", "gpt-5-mini")
        output_tokens = int(kwargs.get("expected_output_tokens", 1000))

        if not text:
            return "텍스트(text)를 입력해주세요."

        tiktoken = _get_tiktoken()
        if tiktoken is None:
            return "tiktoken 라이브러리가 설치되지 않았습니다. pip install tiktoken"

        encoder = self._get_encoder(model)
        if encoder is None:
            return "tiktoken 인코더를 로드할 수 없습니다."

        input_tokens = len(encoder.encode(text))
        prices = self._load_model_prices()
        model_price = prices.get(model, {"input_per_1m": 0, "output_per_1m": 0})

        input_cost = (input_tokens / 1_000_000) * model_price["input_per_1m"]
        output_cost = (output_tokens / 1_000_000) * model_price["output_per_1m"]
        total_cost = input_cost + output_cost

        return (
            f"## 비용 예측 결과\n\n"
            f"| 항목 | 값 |\n"
            f"|------|----|\n"
            f"| 모델 | {model} |\n"
            f"| 입력 토큰 | {input_tokens:,} |\n"
            f"| 예상 출력 토큰 | {output_tokens:,} |\n"
            f"| 입력 비용 | ${input_cost:.6f} |\n"
            f"| 출력 비용 | ${output_cost:.6f} |\n"
            f"| **총 예상 비용** | **${total_cost:.6f}** |\n"
            f"\n> 가격 기준: 입력 ${model_price['input_per_1m']}/1M, "
            f"출력 ${model_price['output_per_1m']}/1M"
        )

    async def _truncate(self, kwargs: dict) -> str:
        """토큰 한도에 맞게 텍스트 자르기."""
        text = kwargs.get("text", "")
        max_tokens = int(kwargs.get("max_tokens", 4000))
        model = kwargs.get("model", "gpt-5-mini")

        if not text:
            return "텍스트(text)를 입력해주세요."

        tiktoken = _get_tiktoken()
        if tiktoken is None:
            return "tiktoken 라이브러리가 설치되지 않았습니다. pip install tiktoken"

        encoder = self._get_encoder(model)
        if encoder is None:
            return "tiktoken 인코더를 로드할 수 없습니다."

        tokens = encoder.encode(text)
        original_count = len(tokens)

        if original_count <= max_tokens:
            return (
                f"텍스트가 이미 한도 내입니다.\n"
                f"- 현재 토큰 수: {original_count:,}\n"
                f"- 한도: {max_tokens:,}\n\n"
                f"{text}"
            )

        truncated_tokens = tokens[:max_tokens]
        truncated_text = encoder.decode(truncated_tokens)

        return (
            f"## 텍스트 자르기 완료\n\n"
            f"- 원본 토큰: {original_count:,}\n"
            f"- 한도: {max_tokens:,}\n"
            f"- 잘린 토큰: {original_count - max_tokens:,}\n\n"
            f"---\n\n{truncated_text}"
        )

    async def _compare(self, kwargs: dict) -> str:
        """여러 모델의 토큰화 차이 비교."""
        text = kwargs.get("text", "")
        models = kwargs.get("models", ["gpt-5-mini", "claude-sonnet-4-6"])

        if not text:
            return "텍스트(text)를 입력해주세요."

        if isinstance(models, str):
            models = [m.strip() for m in models.split(",")]

        tiktoken = _get_tiktoken()
        if tiktoken is None:
            return "tiktoken 라이브러리가 설치되지 않았습니다. pip install tiktoken"

        prices = self._load_model_prices()
        lines = ["## 모델별 토큰 비교\n"]
        lines.append(f"- 텍스트 길이: {len(text):,}자\n")
        lines.append("| 모델 | 토큰 수 | 입력 비용 (1회) | 인코딩 |")
        lines.append("|------|---------|---------------|--------|")

        for model in models:
            encoder = self._get_encoder(model)
            if encoder is None:
                lines.append(f"| {model} | 계산 불가 | - | - |")
                continue

            token_count = len(encoder.encode(text))
            model_price = prices.get(model, {"input_per_1m": 0})
            cost = (token_count / 1_000_000) * model_price.get("input_per_1m", 0)
            encoding_name = _MODEL_ENCODINGS.get(model, "cl100k_base")
            lines.append(f"| {model} | {token_count:,} | ${cost:.6f} | {encoding_name} |")

        return "\n".join(lines)
