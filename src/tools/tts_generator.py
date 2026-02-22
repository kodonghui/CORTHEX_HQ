"""
TTS 음성 생성 도구.

OpenAI TTS API(gpt-4o-mini-tts)로 한국어/영어 텍스트를 자연스러운 음성으로 변환합니다.
AI 인플루언서 영상 제작 파이프라인의 1단계(대본→음성).

action: generate | script
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.tts_generator")

OUTPUT_DIR = os.path.join(os.getcwd(), "output", "audio")

# OpenAI TTS 음성 옵션
VOICE_OPTIONS = {
    "alloy": "중성적",
    "ash": "따뜻한 남성",
    "ballad": "부드러운",
    "coral": "밝은 여성",
    "echo": "차분한 남성",
    "fable": "영국식",
    "nova": "친근한 여성 (기본)",
    "onyx": "깊은 남성",
    "sage": "지적인",
    "shimmer": "가벼운 여성",
}


class TTSGeneratorTool(BaseTool):
    """OpenAI TTS(gpt-4o-mini-tts) 음성 생성 도구."""

    _TTS_MODEL = "gpt-4o-mini-tts"

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "generate")
        if action == "generate":
            return await self._generate(kwargs)
        elif action == "script":
            return await self._generate_from_topic(kwargs)
        else:
            voices_md = "\n".join(f"  - `{k}`: {v}" for k, v in VOICE_OPTIONS.items())
            return (
                "## 사용 가능한 action\n"
                "- `generate`: 텍스트 → 음성 파일 생성\n"
                "- `script`: 주제 → 대본 작성 → 음성 생성\n\n"
                f"### 음성 옵션 (voice)\n{voices_md}"
            )

    @staticmethod
    def _get_api_key() -> str:
        return os.getenv("OPENAI_API_KEY", "")

    @staticmethod
    def _ensure_output_dir() -> str:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        return OUTPUT_DIR

    async def _generate(self, kwargs: dict) -> str:
        """텍스트 → TTS 음성 파일 생성."""
        api_key = self._get_api_key()
        if not api_key:
            return "OPENAI_API_KEY 환경변수가 설정되지 않았습니다."

        text = kwargs.get("text", "")
        if not text:
            return "음성으로 변환할 텍스트(text)를 입력해주세요."

        voice = kwargs.get("voice", "nova")
        if voice not in VOICE_OPTIONS:
            voice = "nova"

        speed = float(kwargs.get("speed", 1.0))
        speed = max(0.25, min(4.0, speed))

        instructions = kwargs.get("instructions", "")

        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)

            tts_kwargs: dict[str, Any] = {
                "model": self._TTS_MODEL,
                "voice": voice,
                "input": text,
                "speed": speed,
            }
            if instructions:
                tts_kwargs["instructions"] = instructions

            response = await asyncio.to_thread(
                client.audio.speech.create, **tts_kwargs
            )

            out_dir = self._ensure_output_dir()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"tts_{ts}.mp3"
            filepath = os.path.join(out_dir, filename)

            await asyncio.to_thread(response.stream_to_file, filepath)
            logger.info("TTS 음성 저장: %s", filepath)

            char_count = len(text)
            cost_est = char_count / 1_000_000 * 12  # $12/1M chars 기준

            return (
                f"## TTS 음성 생성 완료\n\n"
                f"| 항목 | 값 |\n|------|----|\n"
                f"| 모델 | `{self._TTS_MODEL}` |\n"
                f"| 음성 | {voice} ({VOICE_OPTIONS.get(voice, '')}) |\n"
                f"| 글자 수 | {char_count:,}자 |\n"
                f"| 속도 | {speed}x |\n"
                f"| 예상 비용 | ~${cost_est:.4f} |\n\n"
                f"### 저장된 파일\n"
                f"- `output/audio/{filename}`\n"
                f"- 서버 경로: `{filepath}`"
            )

        except Exception as e:
            logger.error("TTS 생성 실패: %s", e)
            return f"TTS 생성 실패: {e}"

    async def _generate_from_topic(self, kwargs: dict) -> str:
        """주제 → LLM 대본 작성 → TTS 음성 생성."""
        topic = kwargs.get("topic", "")
        if not topic:
            return "대본을 작성할 주제(topic)를 입력해주세요."

        duration_sec = int(kwargs.get("duration", 60))
        char_target = duration_sec * 4  # 한국어 기준 초당 ~4글자

        tone = kwargs.get("tone", "친근하고 전문적인")
        target_audience = kwargs.get("target_audience", "20~30대 투자/자기계발 관심층")

        script = await self._llm_call(
            system_prompt=(
                "당신은 인스타그램/유튜브 쇼츠용 AI 인플루언서 대본 작가입니다.\n"
                "- 자연스러운 구어체로 작성\n"
                "- 첫 문장에 시청자를 사로잡는 훅(hook)\n"
                "- 핵심 내용은 짧고 임팩트 있게\n"
                "- 마지막에 CTA(행동유도) 포함\n"
                "- 대본만 출력 (지시사항/메타 정보 제외)"
            ),
            user_prompt=(
                f"주제: {topic}\n"
                f"톤: {tone}\n"
                f"타겟: {target_audience}\n"
                f"분량: 약 {char_target}자 ({duration_sec}초 분량)\n\n"
                f"위 조건에 맞는 영상 대본을 작성해주세요."
            ),
        )

        kwargs_gen = {
            **kwargs,
            "text": script,
        }
        result = await self._generate(kwargs_gen)

        return (
            f"## 대본 자동 생성 + TTS\n\n"
            f"### 생성된 대본\n"
            f"```\n{script}\n```\n\n"
            f"---\n\n{result}"
        )
