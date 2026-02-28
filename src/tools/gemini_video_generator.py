"""
Veo 3.1 — 실제 영상 생성 도구.

Google Veo 3.1 모델(veo-3.1-generate-preview)로 마케팅 영상을 직접 생성합니다.
릴스/쇼츠/광고 영상 등 SNS 콘텐츠용 짧은 영상을 생성합니다.

action: generate | reels | ad | extend
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.gemini_video_generator")

# 프로젝트 루트의 output/videos/ (os.getcwd() 의존 제거)
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "output", "videos")
_SITE_URL = os.getenv("SITE_URL", "https://corthex-hq.com")


def _get_genai():
    """google-genai SDK 임포트."""
    try:
        from google import genai
        return genai
    except ImportError:
        return None


# Veo 3.1 설정 상수
_VALID_RESOLUTIONS = ("720p", "1080p", "4k")
_VALID_DURATIONS = ("4", "6", "8")
_VALID_ASPECTS = ("16:9", "9:16")


class GeminiVideoGeneratorTool(BaseTool):
    """Veo 3.1 (veo-3.1-generate-preview) 실제 영상 생성 도구."""

    _VIDEO_MODEL = "veo-3.1-generate-preview"

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "generate")
        if action == "generate":
            return await self._generate(kwargs)
        elif action == "reels":
            return await self._generate_reels(kwargs)
        elif action == "ad":
            return await self._generate_ad(kwargs)
        else:
            return (
                "## 사용 가능한 action\n"
                "- `generate`: 프롬프트로 영상 생성\n"
                "- `reels`: 릴스/쇼츠용 세로 영상 (9:16)\n"
                "- `ad`: 광고용 가로 영상 (16:9)\n"
            )

    @staticmethod
    def _get_api_key() -> str:
        return os.getenv("GOOGLE_API_KEY", "")

    @staticmethod
    def _ensure_output_dir() -> str:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        return OUTPUT_DIR

    async def _generate(self, kwargs: dict) -> str:
        """Veo 3.1 API로 실제 영상 생성."""
        genai = _get_genai()
        if genai is None:
            return "google-genai 라이브러리가 설치되지 않았습니다. pip install google-genai"

        api_key = self._get_api_key()
        if not api_key:
            return "GOOGLE_API_KEY 환경변수가 설정되지 않았습니다."

        prompt = kwargs.get("prompt", "")
        if not prompt:
            return "영상 프롬프트(prompt)를 입력해주세요."

        # 설정값 파싱
        resolution = kwargs.get("resolution", "1080p")
        if resolution not in _VALID_RESOLUTIONS:
            resolution = "1080p"

        duration = str(kwargs.get("duration", "8"))
        if duration not in _VALID_DURATIONS:
            duration = "8"

        aspect_ratio = kwargs.get("aspect_ratio", "16:9")
        if aspect_ratio not in _VALID_ASPECTS:
            aspect_ratio = "16:9"

        negative_prompt = kwargs.get("negative_prompt", "low quality, blurry, distorted, watermark")

        try:
            from google.genai import types

            client = genai.Client(api_key=api_key)

            # 비동기 → 동기 polling을 asyncio에서 실행
            operation = await asyncio.to_thread(
                client.models.generate_videos,
                model=self._VIDEO_MODEL,
                prompt=prompt,
                config=types.GenerateVideosConfig(
                    resolution=resolution,
                    duration_seconds=duration,
                    aspect_ratio=aspect_ratio,
                    negative_prompt=negative_prompt,
                ),
            )

            # 폴링: 완료 대기 (최대 10분 — Veo 3.1은 생성에 시간 소요)
            max_polls = 60
            for poll_i in range(max_polls):
                if operation.done:
                    break
                await asyncio.sleep(10)
                operation = await asyncio.to_thread(
                    client.operations.get, operation
                )
                if poll_i % 6 == 5:
                    logger.info("영상 생성 폴링 %d/%d (진행중...)", poll_i + 1, max_polls)

            if not operation.done:
                return (
                    "## 영상 생성 진행 중 (10분 초과)\n\n"
                    "Veo 3.1 영상 생성이 아직 완료되지 않았습니다.\n"
                    "Google 서버에서 계속 처리 중이며, 완료되면 output/videos/에 저장됩니다.\n"
                    "잠시 후 다시 확인해주세요."
                )

            # 영상 저장
            out_dir = self._ensure_output_dir()
            saved_files: list[str] = []

            for i, gen_video in enumerate(operation.response.generated_videos):
                await asyncio.to_thread(
                    client.files.download, file=gen_video.video
                )
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"veo_{ts}_{i}.mp4"
                filepath = os.path.join(out_dir, filename)
                await asyncio.to_thread(gen_video.video.save, filepath)
                saved_files.append(filename)
                logger.info("영상 저장: %s", filepath)

            if not saved_files:
                return "영상 생성 완료되었으나 파일 저장에 실패했습니다."

            files_md = "\n".join(
                f"- `/api/media/videos/{f}` → `{_SITE_URL}/api/media/videos/{f}`"
                for f in saved_files
            )
            public_urls = [f"{_SITE_URL}/api/media/videos/{f}" for f in saved_files]
            cost_est = float(duration) * 0.25  # 대략적 비용 추정

            return (
                f"## 영상 생성 완료 (Veo 3.1)\n\n"
                f"| 항목 | 값 |\n|------|----|\n"
                f"| 모델 | `{self._VIDEO_MODEL}` |\n"
                f"| 해상도 | {resolution} |\n"
                f"| 길이 | {duration}초 |\n"
                f"| 비율 | {aspect_ratio} |\n"
                f"| 예상 비용 | ~${cost_est:.2f} |\n\n"
                f"### 저장된 파일\n{files_md}\n\n"
                f"### Instagram 릴스 발행용 URL\n"
                + "\n".join(f"- `{u}`" for u in public_urls)
            )

        except Exception as e:
            logger.error("영상 생성 실패: %s", e)
            return f"영상 생성 실패: {e}"

    async def _generate_reels(self, kwargs: dict) -> str:
        """릴스/쇼츠용 세로 영상 (9:16, 8초)."""
        topic = kwargs.get("topic", kwargs.get("prompt", ""))
        prompt = kwargs.get("prompt", "")
        if not prompt and topic:
            prompt = (
                f"Create a visually stunning vertical video for Instagram Reels/YouTube Shorts. "
                f"Topic: {topic}. Dynamic motion, eye-catching transitions, trendy aesthetic. "
                f"Vertical format, mobile-optimized."
            )
        enriched = {
            **kwargs,
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "duration": "8",
            "resolution": kwargs.get("resolution", "1080p"),
        }
        return await self._generate(enriched)

    async def _generate_ad(self, kwargs: dict) -> str:
        """광고용 가로 영상 (16:9)."""
        topic = kwargs.get("topic", kwargs.get("prompt", ""))
        prompt = kwargs.get("prompt", "")
        if not prompt and topic:
            prompt = (
                f"Create a professional advertising video. "
                f"Topic: {topic}. Cinematic quality, clear brand message, "
                f"compelling visuals that drive conversions."
            )
        enriched = {
            **kwargs,
            "prompt": prompt,
            "aspect_ratio": "16:9",
            "duration": kwargs.get("duration", "8"),
            "resolution": kwargs.get("resolution", "1080p"),
        }
        return await self._generate(enriched)
