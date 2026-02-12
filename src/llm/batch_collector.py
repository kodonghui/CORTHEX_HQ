"""
Batch Collector: 여러 에이전트의 LLM 요청을 모아서 Batch API로 제출.

OpenAI/Anthropic 모두 Batch API로 50% 할인 적용.
동시에 들어오는 요청을 0.5초 디바운스로 모아서 한번에 제출한다.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
from uuid import uuid4
from typing import Any, Optional

from src.llm.base import LLMResponse

logger = logging.getLogger("corthex.llm.batch")


class BatchCollector:
    """여러 에이전트의 LLM 요청을 모아서 Batch API로 한번에 제출."""

    def __init__(
        self,
        openai_client: Any = None,
        anthropic_client: Any = None,
    ) -> None:
        self._openai = openai_client
        self._anthropic = anthropic_client
        self._pending: dict[str, asyncio.Future] = {}
        self._requests: list[dict] = []
        self._flush_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def submit(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """요청을 큐에 넣고 결과를 기다림."""
        req_id = uuid4().hex
        loop = asyncio.get_event_loop()
        future: asyncio.Future[LLMResponse] = loop.create_future()

        async with self._lock:
            self._pending[req_id] = future
            self._requests.append({
                "id": req_id,
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "reasoning_effort": reasoning_effort,
            })
            # 0.5초 디바운스: 동시에 들어오는 요청들을 모아서 한번에 제출
            if not self._flush_task or self._flush_task.done():
                self._flush_task = asyncio.create_task(self._flush_after_delay())

        return await future

    async def _flush_after_delay(self) -> None:
        """0.5초 후 모인 요청들을 Batch로 제출."""
        await asyncio.sleep(0.5)

        async with self._lock:
            requests = self._requests.copy()
            self._requests.clear()

        if not requests:
            return

        # provider별 분류
        openai_reqs = [r for r in requests if r["model"].startswith(("gpt-", "o3-", "o1-", "o4-", "o5-"))]
        anthropic_reqs = [r for r in requests if r["model"].startswith("claude-")]

        tasks = []
        if openai_reqs and self._openai:
            tasks.append(self._submit_openai_batch(openai_reqs))
        if anthropic_reqs and self._anthropic:
            tasks.append(self._submit_anthropic_batch(anthropic_reqs))

        # 미지원 요청은 에러로 처리
        unsupported = [r for r in requests if r not in openai_reqs and r not in anthropic_reqs]
        for r in unsupported:
            future = self._pending.pop(r["id"], None)
            if future and not future.done():
                future.set_exception(ValueError(f"Batch 미지원 모델: {r['model']}"))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _submit_anthropic_batch(self, reqs: list[dict]) -> None:
        """Anthropic Message Batches API로 제출."""
        try:
            batch_requests = []
            for r in reqs:
                # Anthropic는 system을 별도 파라미터로 분리
                system_msg = ""
                api_messages = []
                for m in r["messages"]:
                    if m["role"] == "system":
                        system_msg = m["content"]
                    else:
                        api_messages.append({"role": m["role"], "content": m["content"]})
                if not api_messages:
                    api_messages = [{"role": "user", "content": "(no input)"}]

                params: dict[str, Any] = {
                    "model": r["model"],
                    "max_tokens": r["max_tokens"],
                    "messages": api_messages,
                }
                if system_msg:
                    params["system"] = system_msg

                # Extended thinking 지원
                effort = r.get("reasoning_effort")
                budget_map = {"low": 2048, "medium": 8192, "high": 32768}
                if effort and effort in budget_map:
                    params["thinking"] = {"type": "enabled", "budget_tokens": budget_map[effort]}
                else:
                    params["temperature"] = r["temperature"]

                batch_requests.append({
                    "custom_id": r["id"],
                    "params": params,
                })

            batch = await self._anthropic.messages.batches.create(requests=batch_requests)
            logger.info("Anthropic Batch 제출 완료: %s (%d건)", batch.id, len(reqs))

            # 폴링
            while batch.processing_status != "ended":
                await asyncio.sleep(10)
                batch = await self._anthropic.messages.batches.retrieve(batch.id)
                logger.debug("Anthropic Batch %s 상태: %s", batch.id, batch.processing_status)

            # 결과 수집
            async for result in self._anthropic.messages.batches.results(batch.id):
                future = self._pending.pop(result.custom_id, None)
                if not future or future.done():
                    continue

                if result.result.type == "succeeded":
                    msg = result.result.message
                    content = ""
                    for block in msg.content:
                        if block.type == "text":
                            content = block.text
                            break
                    input_tokens = msg.usage.input_tokens
                    output_tokens = msg.usage.output_tokens

                    # Batch = 50% 할인
                    from src.llm.anthropic_provider import AnthropicProvider
                    cost = AnthropicProvider._calculate_cost(
                        result.result.message.model, input_tokens, output_tokens, is_batch=True
                    )

                    future.set_result(LLMResponse(
                        content=content,
                        model=msg.model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost,
                        provider="anthropic",
                    ))
                else:
                    future.set_exception(
                        RuntimeError(f"Batch 요청 실패: {result.result.type}")
                    )

        except Exception as e:
            logger.error("Anthropic Batch 오류: %s", e)
            for r in reqs:
                future = self._pending.pop(r["id"], None)
                if future and not future.done():
                    future.set_exception(e)

    async def _submit_openai_batch(self, reqs: list[dict]) -> None:
        """OpenAI Batch API (JSONL -> upload -> create -> poll -> download)."""
        try:
            # JSONL 생성
            jsonl_lines = []
            for r in reqs:
                body: dict[str, Any] = {
                    "model": r["model"],
                    "messages": r["messages"],
                    "temperature": r["temperature"],
                    "max_tokens": r["max_tokens"],
                }
                if r.get("reasoning_effort"):
                    body["reasoning_effort"] = r["reasoning_effort"]

                jsonl_lines.append(json.dumps({
                    "custom_id": r["id"],
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": body,
                }, ensure_ascii=False))

            jsonl_content = "\n".join(jsonl_lines)

            # 파일 업로드
            file_obj = await self._openai.files.create(
                file=io.BytesIO(jsonl_content.encode("utf-8")),
                purpose="batch",
            )
            logger.info("OpenAI Batch 파일 업로드: %s", file_obj.id)

            # Batch 생성
            batch = await self._openai.batches.create(
                input_file_id=file_obj.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
            )
            logger.info("OpenAI Batch 제출 완료: %s (%d건)", batch.id, len(reqs))

            # 폴링
            while batch.status not in ("completed", "failed", "expired", "cancelled"):
                await asyncio.sleep(10)
                batch = await self._openai.batches.retrieve(batch.id)
                logger.debug("OpenAI Batch %s 상태: %s", batch.id, batch.status)

            if batch.status != "completed":
                raise RuntimeError(f"OpenAI Batch 실패: {batch.status}")

            # 결과 다운로드
            output_file = await self._openai.files.content(batch.output_file_id)
            output_text = output_file.text

            for line in output_text.strip().split("\n"):
                if not line.strip():
                    continue
                result = json.loads(line)
                custom_id = result["custom_id"]
                future = self._pending.pop(custom_id, None)
                if not future or future.done():
                    continue

                resp_body = result.get("response", {}).get("body", {})
                if result.get("error"):
                    future.set_exception(RuntimeError(str(result["error"])))
                    continue

                choice = resp_body.get("choices", [{}])[0]
                usage = resp_body.get("usage", {})
                content = choice.get("message", {}).get("content", "")
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)

                from src.llm.openai_provider import OpenAIProvider
                cost = OpenAIProvider._calculate_cost(
                    resp_body.get("model", reqs[0]["model"]),
                    input_tokens, output_tokens, is_batch=True
                )

                future.set_result(LLMResponse(
                    content=content,
                    model=resp_body.get("model", reqs[0]["model"]),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                    provider="openai",
                ))

        except Exception as e:
            logger.error("OpenAI Batch 오류: %s", e)
            for r in reqs:
                future = self._pending.pop(r["id"], None)
                if future and not future.done():
                    future.set_exception(e)
