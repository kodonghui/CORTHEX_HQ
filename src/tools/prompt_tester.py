"""프롬프트 테스터 도구 — 여러 AI 모델로 프롬프트 비교·평가."""
from __future__ import annotations

import logging
import time
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.prompt_tester")


class PromptTesterTool(BaseTool):
    """프롬프트를 여러 AI 모델로 실행하여 결과를 비교하고 평가하는 도구."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "test")
        if action == "test":
            return await self._test(kwargs)
        elif action == "compare":
            return await self._compare(kwargs)
        elif action == "evaluate":
            return await self._evaluate(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: test(다중 모델 테스트), compare(프롬프트 A/B 비교), "
                "evaluate(프롬프트 품질 평가)"
            )

    async def _test(self, kwargs: dict) -> str:
        """프롬프트를 여러 모델로 실행, 결과 비교."""
        prompt = kwargs.get("prompt", "")
        system_prompt = kwargs.get("system_prompt", "당신은 도움이 되는 AI 어시스턴트입니다.")
        models = kwargs.get("models", ["gpt-5-mini", "claude-haiku-4-6"])

        if not prompt:
            return "테스트할 프롬프트(prompt)를 입력해주세요."

        if isinstance(models, str):
            models = [m.strip() for m in models.split(",")]

        results: list[dict] = []
        for model_name in models:
            start = time.time()
            try:
                response = await self.model_router.complete(
                    model_name=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                )
                elapsed = time.time() - start
                results.append({
                    "model": model_name,
                    "response": response.content,
                    "time": elapsed,
                    "tokens": getattr(response, "usage_total", 0),
                    "success": True,
                })
            except Exception as e:
                elapsed = time.time() - start
                results.append({
                    "model": model_name,
                    "response": f"오류: {e}",
                    "time": elapsed,
                    "tokens": 0,
                    "success": False,
                })

        # 결과 포맷팅
        lines = [f"## 프롬프트 테스트 결과\n\n**프롬프트:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}\n"]

        # 비교표
        lines.append("### 모델별 비교\n")
        lines.append("| 모델 | 응답 시간 | 성공 |")
        lines.append("|------|---------|------|")
        for r in results:
            status = "성공" if r["success"] else "실패"
            lines.append(f"| {r['model']} | {r['time']:.2f}초 | {status} |")

        # 각 모델 응답
        for r in results:
            lines.append(f"\n### {r['model']} 응답\n")
            lines.append(f"```\n{r['response'][:2000]}\n```")

        return "\n".join(lines)

    async def _compare(self, kwargs: dict) -> str:
        """프롬프트 A vs B 비교 (동일 모델)."""
        prompt_a = kwargs.get("prompt_a", "")
        prompt_b = kwargs.get("prompt_b", "")
        model = kwargs.get("model", self.config.model_name)

        if not prompt_a or not prompt_b:
            return "비교할 두 프롬프트(prompt_a, prompt_b)를 입력해주세요."

        # 두 프롬프트 실행
        response_a = await self.model_router.complete(
            model_name=model,
            messages=[{"role": "user", "content": prompt_a}],
            temperature=0.2,
        )
        response_b = await self.model_router.complete(
            model_name=model,
            messages=[{"role": "user", "content": prompt_b}],
            temperature=0.2,
        )

        # LLM이 두 결과를 비교 평가
        evaluation = await self._llm_call(
            system_prompt=(
                "당신은 프롬프트 엔지니어링 전문가입니다. "
                "두 프롬프트의 응답 결과를 비교하고 어떤 것이 더 효과적인지 평가하세요.\n"
                "평가 기준: 1) 응답의 정확성 2) 구체성 3) 유용성 4) 간결성"
            ),
            user_prompt=(
                f"## 프롬프트 A\n{prompt_a}\n\n## 응답 A\n{response_a.content[:1500]}\n\n"
                f"## 프롬프트 B\n{prompt_b}\n\n## 응답 B\n{response_b.content[:1500]}"
            ),
        )

        return (
            f"## 프롬프트 A/B 비교 (모델: {model})\n\n"
            f"### 프롬프트 A\n```\n{prompt_a}\n```\n\n"
            f"### 프롬프트 B\n```\n{prompt_b}\n```\n\n"
            f"---\n\n"
            f"### 응답 A (요약)\n{response_a.content[:500]}...\n\n"
            f"### 응답 B (요약)\n{response_b.content[:500]}...\n\n"
            f"---\n\n"
            f"### 평가\n\n{evaluation}"
        )

    async def _evaluate(self, kwargs: dict) -> str:
        """프롬프트 품질 평가."""
        prompt = kwargs.get("prompt", "")
        if not prompt:
            return "평가할 프롬프트(prompt)를 입력해주세요."

        evaluation = await self._llm_call(
            system_prompt=(
                "당신은 프롬프트 엔지니어링 전문가입니다. 주어진 프롬프트를 아래 기준으로 평가하세요.\n\n"
                "1. **명확성** (0-100): 지시사항이 명확한가?\n"
                "2. **구체성** (0-100): 원하는 결과가 구체적으로 기술되었는가?\n"
                "3. **맥락 제공** (0-100): 충분한 배경 정보가 있는가?\n"
                "4. **제약 조건** (0-100): 형식, 길이 등 제약이 명시되었는가?\n"
                "5. **종합 점수** (0-100)\n\n"
                "각 항목에 점수와 이유를 제시하고, 구체적인 개선 방안을 제안하세요.\n"
                "개선된 프롬프트 예시도 함께 작성하세요."
            ),
            user_prompt=f"평가할 프롬프트:\n\n{prompt}",
        )

        return f"## 프롬프트 품질 평가\n\n**원본 프롬프트:**\n```\n{prompt}\n```\n\n---\n\n{evaluation}"
