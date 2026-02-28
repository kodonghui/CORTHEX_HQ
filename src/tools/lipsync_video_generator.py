"""
립싱크 영상 생성 도구 (Replicate API + SadTalker).

AI 인플루언서 이미지 + 음성 → 입이 움직이는 영상을 생성합니다.
Replicate 클라우드 GPU에서 SadTalker를 실행하여 빠르게 처리합니다.

action: generate | from_text
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.lipsync_video_generator")

# 프로젝트 루트 기준 절대경로 (os.getcwd() 의존 제거)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VIDEO_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "output", "videos")
_SITE_URL = os.getenv("SITE_URL", "https://corthex-hq.com")
AUDIO_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "output", "audio")
IMAGE_ASSET_DIR = os.path.join(_PROJECT_ROOT, "assets", "ai-influencer")

# 기본 AI 인플루언서 이미지 (정면 상반신 — 립싱크 최적)
DEFAULT_IMAGE = "Photorealistic_portrait_of_a_Korean_woman_age_25-1771756616360.png"


class LipsyncVideoGeneratorTool(BaseTool):
    """Replicate SadTalker 립싱크 영상 생성 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "generate")
        if action == "generate":
            return await self._generate(kwargs)
        elif action == "from_text":
            return await self._from_text(kwargs)
        else:
            return (
                "## 사용 가능한 action\n"
                "- `generate`: 이미지 + 음성 파일 → 립싱크 영상\n"
                "- `from_text`: 이미지 + 대본 텍스트 → TTS → 립싱크 영상\n"
            )

    @staticmethod
    def _get_api_token() -> str:
        return os.getenv("REPLICATE_API_TOKEN", "")

    @staticmethod
    def _ensure_output_dir() -> str:
        os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
        return VIDEO_OUTPUT_DIR

    def _resolve_image_path(self, kwargs: dict) -> str | None:
        """이미지 경로 결정: 명시적 경로 → 이름만 → 기본 이미지."""
        image = kwargs.get("image", "")
        if image and os.path.isfile(image):
            return image

        # 파일명만 준 경우 assets 폴더에서 찾기
        if image:
            candidate = os.path.join(IMAGE_ASSET_DIR, image)
            if os.path.isfile(candidate):
                return candidate

        # 기본 이미지
        default = os.path.join(IMAGE_ASSET_DIR, DEFAULT_IMAGE)
        if os.path.isfile(default):
            return default

        return None

    def _resolve_audio_path(self, kwargs: dict) -> str | None:
        """오디오 경로 결정: 명시적 경로 → output/audio에서 최신 파일."""
        audio = kwargs.get("audio", "")
        if audio and os.path.isfile(audio):
            return audio

        # 파일명만 준 경우
        if audio:
            candidate = os.path.join(AUDIO_OUTPUT_DIR, audio)
            if os.path.isfile(candidate):
                return candidate

        # output/audio에서 가장 최신 MP3 찾기
        if os.path.isdir(AUDIO_OUTPUT_DIR):
            mp3s = sorted(
                [f for f in os.listdir(AUDIO_OUTPUT_DIR) if f.endswith(".mp3")],
                reverse=True,
            )
            if mp3s:
                return os.path.join(AUDIO_OUTPUT_DIR, mp3s[0])

        return None

    async def _generate(self, kwargs: dict) -> str:
        """이미지 + 음성 → Replicate SadTalker → 립싱크 영상."""
        token = self._get_api_token()
        if not token:
            return (
                "REPLICATE_API_TOKEN 환경변수가 설정되지 않았습니다.\n"
                "https://replicate.com 에서 API 토큰을 발급 후 "
                "GitHub Secrets에 `REPLICATE_API_TOKEN`을 등록해주세요."
            )

        image_path = self._resolve_image_path(kwargs)
        if not image_path:
            return "이미지 파일을 찾을 수 없습니다. image 파라미터에 경로를 지정해주세요."

        audio_path = self._resolve_audio_path(kwargs)
        if not audio_path:
            return (
                "음성 파일을 찾을 수 없습니다. audio 파라미터에 경로를 지정하거나, "
                "먼저 tts_generator 도구로 음성을 생성해주세요."
            )

        try:
            import replicate

            # 이미지/오디오를 data URI로 변환
            with open(image_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode()
            img_ext = os.path.splitext(image_path)[1].lstrip(".")
            img_uri = f"data:image/{img_ext};base64,{img_data}"

            with open(audio_path, "rb") as f:
                aud_data = base64.b64encode(f.read()).decode()
            aud_ext = os.path.splitext(audio_path)[1].lstrip(".")
            aud_mime = "audio/mpeg" if aud_ext == "mp3" else f"audio/{aud_ext}"
            aud_uri = f"data:{aud_mime};base64,{aud_data}"

            logger.info("립싱크 생성 시작: image=%s, audio=%s", image_path, audio_path)

            # Replicate SadTalker 실행
            output = await asyncio.to_thread(
                replicate.run,
                "cjwbw/sadtalker:a519cc0cfebaaeade068b23899165a11ec76e00be0a4a40a0117a56b26b1a0c1",
                input={
                    "source_image": img_uri,
                    "driven_audio": aud_uri,
                    "enhancer": "gfpgan",
                },
            )

            # 결과 영상 다운로드
            out_dir = self._ensure_output_dir()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"lipsync_{ts}.mp4"
            filepath = os.path.join(out_dir, filename)

            if hasattr(output, "read"):
                video_data = await asyncio.to_thread(output.read)
                with open(filepath, "wb") as f:
                    f.write(video_data)
            elif isinstance(output, str) and output.startswith("http"):
                import urllib.request
                await asyncio.to_thread(
                    urllib.request.urlretrieve, output, filepath
                )
            else:
                # FileOutput 또는 iterator
                try:
                    with open(filepath, "wb") as f:
                        for chunk in output:
                            f.write(chunk)
                except TypeError:
                    with open(filepath, "wb") as f:
                        f.write(bytes(output))

            logger.info("립싱크 영상 저장: %s", filepath)

            img_name = os.path.basename(image_path)
            aud_name = os.path.basename(audio_path)

            public_url = f"{_SITE_URL}/api/media/videos/{filename}"

            return (
                f"## 립싱크 영상 생성 완료\n\n"
                f"| 항목 | 값 |\n|------|----|\n"
                f"| 엔진 | Replicate SadTalker |\n"
                f"| 이미지 | `{img_name}` |\n"
                f"| 음성 | `{aud_name}` |\n"
                f"| 보정 | GFPGAN (얼굴 화질 향상) |\n\n"
                f"### 저장된 파일\n"
                f"- `output/videos/{filename}`\n"
                f"- 퍼블릭 URL: `{public_url}`\n\n"
                f"### Instagram 릴스 발행용 URL\n"
                f"- `{public_url}`"
            )

        except ImportError:
            return "replicate 라이브러리가 설치되지 않았습니다. pip install replicate"
        except Exception as e:
            logger.error("립싱크 생성 실패: %s", e)
            return f"립싱크 영상 생성 실패: {e}"

    async def _from_text(self, kwargs: dict) -> str:
        """이미지 + 대본 텍스트 → TTS → 립싱크 영상 (올인원)."""
        text = kwargs.get("text", "")
        topic = kwargs.get("topic", "")

        if not text and not topic:
            return "text(대본) 또는 topic(주제)를 입력해주세요."

        # 1단계: TTS 음성 생성
        from src.tools.tts_generator import TTSGeneratorTool, OUTPUT_DIR as AUDIO_DIR

        tts_tool = TTSGeneratorTool(config=self.config, model_router=self.model_router)
        tts_tool._current_caller_model = self._current_caller_model
        tts_tool._current_caller_temperature = self._current_caller_temperature

        if text:
            tts_result = await tts_tool._generate({
                "text": text,
                "voice": kwargs.get("voice", "nova"),
                "speed": kwargs.get("speed", 1.0),
            })
        else:
            tts_result = await tts_tool._generate_from_topic({
                "topic": topic,
                "duration": kwargs.get("duration", 60),
                "tone": kwargs.get("tone", "친근하고 전문적인"),
                "voice": kwargs.get("voice", "nova"),
            })

        if "실패" in tts_result:
            return f"TTS 생성 실패:\n{tts_result}"

        # 가장 최신 음성 파일 찾기
        audio_path = self._resolve_audio_path({})
        if not audio_path:
            return "TTS 음성 파일 생성 후 찾을 수 없습니다."

        # 2단계: 립싱크 영상 생성
        gen_kwargs = {**kwargs, "audio": audio_path}
        lipsync_result = await self._generate(gen_kwargs)

        return (
            f"## AI 인플루언서 영상 생성 (올인원)\n\n"
            f"### 1단계: TTS 음성\n{tts_result}\n\n"
            f"---\n\n"
            f"### 2단계: 립싱크 영상\n{lipsync_result}"
        )
