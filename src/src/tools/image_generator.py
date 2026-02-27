"""이미지 생성기 도구 — DALL-E 3 API로 이미지 생성."""
from __future__ import annotations

import base64
import logging
import os
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.image_generator")

OUTPUT_DIR = os.path.join(os.getcwd(), "output", "images")


def _get_openai():
    try:
        import openai
        return openai
    except ImportError:
        return None


class ImageGeneratorTool(BaseTool):
    """DALL-E 3를 사용한 AI 이미지 생성 도구."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "generate")
        if action == "generate":
            return await self._generate(kwargs)
        elif action == "edit":
            return await self._edit(kwargs)
        elif action == "variation":
            return await self._variation(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: generate(생성), edit(편집), variation(변형)"
            )

    @staticmethod
    def _get_api_key() -> str:
        return os.getenv("OPENAI_API_KEY", "")

    @staticmethod
    def _key_msg() -> str:
        return "OPENAI_API_KEY 환경변수가 설정되지 않았습니다."

    @staticmethod
    def _ensure_output_dir() -> str:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        return OUTPUT_DIR

    async def _generate(self, kwargs: dict) -> str:
        """프롬프트로 이미지 생성."""
        openai = _get_openai()
        if openai is None:
            return "openai 라이브러리가 설치되지 않았습니다. pip install openai"

        api_key = self._get_api_key()
        if not api_key:
            return self._key_msg()

        prompt = kwargs.get("prompt", "")
        if not prompt:
            return "이미지 프롬프트(prompt)를 입력해주세요."

        size = kwargs.get("size", "1024x1024")
        quality = kwargs.get("quality", "standard")
        style = kwargs.get("style", "vivid")
        n = int(kwargs.get("n", 1))

        # 비용 안내
        cost_per_image = 0.040 if quality == "standard" else 0.080
        estimated_cost = cost_per_image * n

        try:
            client = openai.OpenAI(api_key=api_key)
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                quality=quality,
                style=style,
                n=n,
                response_format="b64_json",
            )

            out_dir = self._ensure_output_dir()
            saved_files: list[str] = []

            for i, image_data in enumerate(response.data):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"generated_{ts}_{i}.png"
                filepath = os.path.join(out_dir, filename)

                img_bytes = base64.b64decode(image_data.b64_json)
                with open(filepath, "wb") as f:
                    f.write(img_bytes)
                saved_files.append(filepath)

            revised_prompt = getattr(response.data[0], "revised_prompt", prompt)
            files_list = "\n".join(f"- {f}" for f in saved_files)

            logger.info("이미지 생성 완료: %d장", len(saved_files))
            return (
                f"## 이미지 생성 완료\n\n"
                f"| 항목 | 값 |\n|------|----|\n"
                f"| 원본 프롬프트 | {prompt[:100]} |\n"
                f"| 수정된 프롬프트 | {revised_prompt[:100]} |\n"
                f"| 크기 | {size} |\n"
                f"| 품질 | {quality} |\n"
                f"| 스타일 | {style} |\n"
                f"| 생성 수 | {len(saved_files)}장 |\n"
                f"| 예상 비용 | ${estimated_cost:.3f} |\n\n"
                f"### 저장된 파일\n{files_list}"
            )

        except Exception as e:
            logger.error("이미지 생성 실패: %s", e)
            return f"이미지 생성 실패: {e}"

    async def _edit(self, kwargs: dict) -> str:
        """기존 이미지 편집 (DALL-E 2 edit API)."""
        openai = _get_openai()
        if openai is None:
            return "openai 라이브러리가 설치되지 않았습니다."

        api_key = self._get_api_key()
        if not api_key:
            return self._key_msg()

        image_path = kwargs.get("image_path", "")
        prompt = kwargs.get("prompt", "")

        if not image_path or not os.path.isfile(image_path):
            return f"이미지 파일을 찾을 수 없습니다: {image_path}"
        if not prompt:
            return "편집 프롬프트(prompt)를 입력해주세요."

        try:
            client = openai.OpenAI(api_key=api_key)
            with open(image_path, "rb") as img_file:
                response = client.images.edit(
                    model="dall-e-2",
                    image=img_file,
                    prompt=prompt,
                    size="1024x1024",
                    response_format="b64_json",
                )

            out_dir = self._ensure_output_dir()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(out_dir, f"edited_{ts}.png")

            img_bytes = base64.b64decode(response.data[0].b64_json)
            with open(filepath, "wb") as f:
                f.write(img_bytes)

            return (
                f"## 이미지 편집 완료\n\n"
                f"- 원본: {image_path}\n"
                f"- 편집 프롬프트: {prompt}\n"
                f"- 저장 경로: {filepath}"
            )
        except Exception as e:
            return f"이미지 편집 실패: {e}"

    async def _variation(self, kwargs: dict) -> str:
        """기존 이미지의 변형 생성."""
        openai = _get_openai()
        if openai is None:
            return "openai 라이브러리가 설치되지 않았습니다."

        api_key = self._get_api_key()
        if not api_key:
            return self._key_msg()

        image_path = kwargs.get("image_path", "")
        if not image_path or not os.path.isfile(image_path):
            return f"이미지 파일을 찾을 수 없습니다: {image_path}"

        n = int(kwargs.get("n", 1))

        try:
            client = openai.OpenAI(api_key=api_key)
            with open(image_path, "rb") as img_file:
                response = client.images.create_variation(
                    model="dall-e-2",
                    image=img_file,
                    n=n,
                    size="1024x1024",
                    response_format="b64_json",
                )

            out_dir = self._ensure_output_dir()
            saved: list[str] = []
            for i, data in enumerate(response.data):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = os.path.join(out_dir, f"variation_{ts}_{i}.png")
                img_bytes = base64.b64decode(data.b64_json)
                with open(filepath, "wb") as f:
                    f.write(img_bytes)
                saved.append(filepath)

            files_list = "\n".join(f"- {f}" for f in saved)
            return (
                f"## 이미지 변형 생성 완료\n\n"
                f"- 원본: {image_path}\n"
                f"- 변형 수: {len(saved)}장\n\n"
                f"### 저장된 파일\n{files_list}"
            )
        except Exception as e:
            return f"이미지 변형 생성 실패: {e}"
