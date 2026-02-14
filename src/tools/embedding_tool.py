"""임베딩 도구 — 텍스트 벡터화, 유사도 계산, 클러스터링."""
from __future__ import annotations

import logging
import math
import os
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.embedding_tool")


def _get_openai():
    try:
        import openai
        return openai
    except ImportError:
        return None


class EmbeddingTool(BaseTool):
    """텍스트를 AI 벡터로 변환하고, 유사도 계산, 클러스터링하는 도구."""

    DEFAULT_MODEL = "text-embedding-3-small"

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "embed")
        if action == "embed":
            return await self._embed(kwargs)
        elif action == "similarity":
            return await self._similarity(kwargs)
        elif action == "batch":
            return await self._batch(kwargs)
        elif action == "cluster":
            return await self._cluster(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: embed(벡터 변환), similarity(유사도 계산), "
                "batch(일괄 임베딩), cluster(그룹핑)"
            )

    @staticmethod
    def _get_api_key() -> str:
        return os.getenv("OPENAI_API_KEY", "")

    @staticmethod
    def _key_msg() -> str:
        return (
            "OPENAI_API_KEY 환경변수가 설정되지 않았습니다.\n"
            "OpenAI API 키를 .env에 추가하세요."
        )

    async def _get_embedding(self, text: str, model: str | None = None) -> list[float] | str:
        """텍스트를 벡터로 변환. 성공 시 float 리스트, 실패 시 에러 문자열."""
        openai = _get_openai()
        if openai is None:
            return "openai 라이브러리가 설치되지 않았습니다. pip install openai"

        api_key = self._get_api_key()
        if not api_key:
            return self._key_msg()

        model = model or self.DEFAULT_MODEL
        try:
            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(
                model=model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error("임베딩 생성 실패: %s", e)
            return f"임베딩 생성 실패: {e}"

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """코사인 유사도 계산."""
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def _embed(self, kwargs: dict) -> str:
        """단일 텍스트 임베딩."""
        text = kwargs.get("text", "")
        model = kwargs.get("model", self.DEFAULT_MODEL)

        if not text:
            return "텍스트(text)를 입력해주세요."

        result = await self._get_embedding(text, model)
        if isinstance(result, str):
            return result

        dim = len(result)
        preview = result[:5]

        return (
            f"## 임베딩 결과\n\n"
            f"- 모델: {model}\n"
            f"- 차원: {dim}\n"
            f"- 텍스트 길이: {len(text)}자\n"
            f"- 벡터 미리보기: [{', '.join(f'{v:.6f}' for v in preview)}, ...]\n"
            f"\n> 이 벡터는 텍스트의 의미를 숫자로 표현한 것입니다. "
            f"비슷한 의미의 텍스트는 비슷한 벡터를 가집니다."
        )

    async def _similarity(self, kwargs: dict) -> str:
        """두 텍스트의 유사도 계산."""
        text_a = kwargs.get("text_a", "")
        text_b = kwargs.get("text_b", "")
        model = kwargs.get("model", self.DEFAULT_MODEL)

        if not text_a or not text_b:
            return "두 텍스트(text_a, text_b)를 입력해주세요."

        vec_a = await self._get_embedding(text_a, model)
        if isinstance(vec_a, str):
            return vec_a

        vec_b = await self._get_embedding(text_b, model)
        if isinstance(vec_b, str):
            return vec_b

        similarity = self._cosine_similarity(vec_a, vec_b)

        # 유사도 해석
        if similarity >= 0.9:
            interpretation = "매우 유사 (거의 같은 의미)"
        elif similarity >= 0.7:
            interpretation = "상당히 유사 (관련성 높음)"
        elif similarity >= 0.5:
            interpretation = "보통 유사 (어느 정도 관련)"
        elif similarity >= 0.3:
            interpretation = "약간 유사 (관련성 낮음)"
        else:
            interpretation = "유사하지 않음 (관련 없음)"

        return (
            f"## 텍스트 유사도 분석\n\n"
            f"**텍스트 A:** {text_a[:100]}{'...' if len(text_a) > 100 else ''}\n\n"
            f"**텍스트 B:** {text_b[:100]}{'...' if len(text_b) > 100 else ''}\n\n"
            f"---\n\n"
            f"| 항목 | 값 |\n|------|----|\n"
            f"| 코사인 유사도 | {similarity:.4f} |\n"
            f"| 유사도 (%) | {similarity * 100:.1f}% |\n"
            f"| 해석 | {interpretation} |\n"
        )

    async def _batch(self, kwargs: dict) -> str:
        """여러 텍스트 일괄 임베딩."""
        texts = kwargs.get("texts", [])
        model = kwargs.get("model", self.DEFAULT_MODEL)

        if not texts:
            return "텍스트 목록(texts)을 입력해주세요. 예: [\"텍스트1\", \"텍스트2\", ...]"

        if isinstance(texts, str):
            import json
            try:
                texts = json.loads(texts)
            except Exception:
                texts = [t.strip() for t in texts.split(",")]

        openai = _get_openai()
        if openai is None:
            return "openai 라이브러리가 설치되지 않았습니다. pip install openai"

        api_key = self._get_api_key()
        if not api_key:
            return self._key_msg()

        try:
            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(model=model, input=texts)
            embeddings = [item.embedding for item in response.data]
            dim = len(embeddings[0]) if embeddings else 0

            return (
                f"## 일괄 임베딩 완료\n\n"
                f"- 모델: {model}\n"
                f"- 처리된 텍스트: {len(embeddings)}개\n"
                f"- 벡터 차원: {dim}\n"
                f"- 총 토큰: {response.usage.total_tokens:,}\n\n"
                f"### 처리 목록\n"
                + "\n".join(f"- {i+1}. {t[:50]}... → {dim}차원 벡터" for i, t in enumerate(texts))
            )
        except Exception as e:
            return f"일괄 임베딩 실패: {e}"

    async def _cluster(self, kwargs: dict) -> str:
        """텍스트 목록을 유사도 기반 그룹핑."""
        texts = kwargs.get("texts", [])
        threshold = float(kwargs.get("threshold", 0.7))

        if not texts:
            return "텍스트 목록(texts)을 입력해주세요."

        if isinstance(texts, str):
            import json
            try:
                texts = json.loads(texts)
            except Exception:
                texts = [t.strip() for t in texts.split(",")]

        if len(texts) < 2:
            return "최소 2개 이상의 텍스트가 필요합니다."

        # 모든 텍스트 임베딩
        openai = _get_openai()
        if openai is None:
            return "openai 라이브러리가 설치되지 않았습니다. pip install openai"

        api_key = self._get_api_key()
        if not api_key:
            return self._key_msg()

        try:
            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(model=self.DEFAULT_MODEL, input=texts)
            embeddings = [item.embedding for item in response.data]
        except Exception as e:
            return f"임베딩 생성 실패: {e}"

        # 간단한 클러스터링 (greedy, threshold 기반)
        clusters: list[list[int]] = []
        assigned: set[int] = set()

        for i in range(len(texts)):
            if i in assigned:
                continue
            cluster = [i]
            assigned.add(i)
            for j in range(i + 1, len(texts)):
                if j in assigned:
                    continue
                sim = self._cosine_similarity(embeddings[i], embeddings[j])
                if sim >= threshold:
                    cluster.append(j)
                    assigned.add(j)
            clusters.append(cluster)

        # 결과 포맷팅
        lines = [
            f"## 텍스트 클러스터링 결과\n\n"
            f"- 텍스트 수: {len(texts)}개\n"
            f"- 유사도 기준: {threshold * 100:.0f}%\n"
            f"- 그룹 수: {len(clusters)}개\n"
        ]

        for g_idx, cluster in enumerate(clusters, 1):
            lines.append(f"\n### 그룹 {g_idx} ({len(cluster)}개)")
            for idx in cluster:
                lines.append(f"- {texts[idx][:80]}{'...' if len(texts[idx]) > 80 else ''}")

        return "\n".join(lines)
