"""
Gemini 나노바나나 Pro — 실제 이미지 생성 도구.

gemini-3-pro-image-preview 모델(Nano Banana Pro)로 마케팅 이미지를 직접 생성합니다.
기존 교수급 디자인 지식(플랫폼 사양, 스타일 가이드, 색상 심리학)을
프롬프트 엔지니어링에 자동 반영하여 전문가급 이미지를 생성합니다.

학술/실무 근거:
  - Canva Design School (2024), Meta Ads Creative Best Practices (2024)
  - Google Ads Image Requirements (2024), Labrecque & Milne (2012) — Color Psychology
  - Lidwell et al. (2010) — Visual Hierarchy / Universal Principles of Design

action: generate | banner | card_news | infographic | thumbnail | logo
        ad_creative | social_post | product_mockup | full
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.gemini_image_generator")

OUTPUT_DIR = os.path.join(os.getcwd(), "output", "images")

# Gemini API 지원 aspect_ratio 값
_VALID_ASPECTS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")


def _get_genai():
    """google-genai SDK 임포트."""
    try:
        from google import genai
        return genai
    except ImportError:
        return None


# ═══════════════════════════════════════════════════════
#  플랫폼별 권장 이미지 크기 (Canva Design School, 2024)
# ═══════════════════════════════════════════════════════

_IMAGE_SIZES: dict[str, dict[str, str]] = {
    "instagram_feed": {"size": "1080x1080", "ratio": "1:1", "label": "Instagram Feed"},
    "instagram_story": {"size": "1080x1920", "ratio": "9:16", "label": "Instagram Story"},
    "facebook_feed": {"size": "1200x630", "ratio": "16:9", "label": "Facebook Feed"},
    "facebook_ad": {"size": "1080x1080", "ratio": "1:1", "label": "Facebook Ad"},
    "youtube_thumbnail": {"size": "1280x720", "ratio": "16:9", "label": "YouTube Thumbnail"},
    "youtube_banner": {"size": "2560x1440", "ratio": "16:9", "label": "YouTube Banner"},
    "blog_hero": {"size": "1920x1080", "ratio": "16:9", "label": "Blog Hero"},
    "naver_blog": {"size": "960x960", "ratio": "1:1", "label": "Naver Blog"},
    "twitter_post": {"size": "1600x900", "ratio": "16:9", "label": "Twitter/X"},
    "linkedin_post": {"size": "1200x627", "ratio": "16:9", "label": "LinkedIn"},
    "google_display": {"size": "1200x628", "ratio": "16:9", "label": "Google Display"},
    "newsletter": {"size": "600x300", "ratio": "16:9", "label": "Newsletter Header"},
    "kakao_channel": {"size": "720x720", "ratio": "1:1", "label": "Kakao Channel"},
    "app_icon": {"size": "1024x1024", "ratio": "1:1", "label": "App Icon"},
    "og_image": {"size": "1200x630", "ratio": "16:9", "label": "OG Image"},
}

# ═══════════════════════════════════════════════════════
#  디자인 스타일 가이드 (5가지)
# ═══════════════════════════════════════════════════════

_STYLE_GUIDES: dict[str, dict[str, Any]] = {
    "minimal": {
        "name_ko": "미니멀",
        "prompt_hint": "minimalist clean design, large white space, 2-3 colors only, sans-serif typography, single focal point",
        "avoid": "cluttered layout, decorative fonts, complex gradients, busy patterns",
    },
    "corporate": {
        "name_ko": "기업형",
        "prompt_hint": "professional corporate design, grid-based layout, clear visual hierarchy, brand consistency, authoritative tone",
        "avoid": "casual emoji, handwritten fonts, neon colors, playful elements",
    },
    "playful": {
        "name_ko": "캐주얼/재미",
        "prompt_hint": "bright colorful palette, rounded corners, organic shapes, illustrations, fun and approachable mood",
        "avoid": "rigid grid, monochrome palette, angular layout, formal tone",
    },
    "luxury": {
        "name_ko": "럭셔리",
        "prompt_hint": "dark background with gold/silver accents, serif typography, generous white space, symmetric composition, elegant premium feel",
        "avoid": "neon colors, cartoon fonts, busy backgrounds, low-quality textures",
    },
    "tech": {
        "name_ko": "테크",
        "prompt_hint": "dark mode base, neon cyan/purple accents, geometric patterns, futuristic gradients, innovative smart look",
        "avoid": "pastel colors, handwriting fonts, vintage textures, warm tones",
    },
}

# ═══════════════════════════════════════════════════════
#  플랫폼별 세부 사양 (Meta, Google, 각 플랫폼 공식 문서)
# ═══════════════════════════════════════════════════════

_PLATFORM_SPECS: dict[str, dict[str, str]] = {
    "instagram": {"ratio": "1:1", "hint": "eye-catching in first 0.5s, bold colors or close-up faces"},
    "instagram_story": {"ratio": "9:16", "hint": "full-screen vertical, swipe-up CTA area at bottom"},
    "facebook": {"ratio": "16:9", "hint": "clear CTA area, faces increase engagement 2x"},
    "youtube": {"ratio": "16:9", "hint": "high contrast, large text 3-5 words, expressive faces for CTR"},
    "naver_blog": {"ratio": "1:1", "hint": "mobile-optimized square, representative image drives search ranking"},
    "twitter": {"ratio": "16:9", "hint": "high contrast to stand out in timeline scroll"},
    "linkedin": {"ratio": "16:9", "hint": "professional tone, data visualization triples engagement"},
    "kakao": {"ratio": "1:1", "hint": "mobile-first square, avoid yellow (#FEE500) background clash"},
}

# ═══════════════════════════════════════════════════════
#  색상 심리학 → 프롬프트 힌트 (Labrecque & Milne, 2012)
# ═══════════════════════════════════════════════════════

_COLOR_PSYCHOLOGY: dict[str, str] = {
    "#E74C3C": "passionate red for urgency/sales CTA",
    "#E67E22": "friendly orange for creative CTA buttons",
    "#27AE60": "growth green for health/eco/finance",
    "#2980B9": "trustworthy blue for corporate/tech/medical",
    "#8E44AD": "luxury purple for beauty/education/AI",
    "#2C3E50": "sophisticated dark for premium brands",
    "#D4A017": "premium gold for VIP/luxury/awards",
}


class GeminiImageGeneratorTool(BaseTool):
    """나노바나나 Pro (gemini-3-pro-image-preview) 실제 이미지 생성 도구."""

    _IMAGE_MODEL = "gemini-3-pro-image-preview"

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "generate")
        typed_actions = {
            "banner", "card_news", "infographic", "thumbnail",
            "logo", "ad_creative", "social_post", "product_mockup",
        }
        if action == "generate":
            return await self._generate(kwargs)
        elif action in typed_actions:
            return await self._generate_typed(action, kwargs)
        elif action == "full":
            return await self._generate_full_set(kwargs)
        else:
            all_actions = ["generate"] + sorted(typed_actions) + ["full"]
            return (
                f"## 알 수 없는 action: `{action}`\n\n"
                "사용 가능한 action:\n"
                + "\n".join(f"- `{a}`" for a in all_actions)
            )

    # ─── API 키 / 출력 디렉토리 ──────────────────────

    @staticmethod
    def _get_api_key() -> str:
        return os.getenv("GOOGLE_API_KEY", "")

    @staticmethod
    def _ensure_output_dir() -> str:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        return OUTPUT_DIR

    # ─── 파라미터 파싱 ────────────────────────────────

    @staticmethod
    def _parse_params(kwargs: dict) -> dict[str, str]:
        return {
            "topic": kwargs.get("topic", "CORTHEX HQ AI"),
            "style": kwargs.get("style", "minimal"),
            "colors": kwargs.get("colors", ""),
            "text_overlay": kwargs.get("text_overlay", ""),
            "platform": kwargs.get("platform", ""),
            "context": kwargs.get("context", ""),
        }

    # ─── 프롬프트 구축 (교수급 디자인 지식 자동 반영) ──

    def _build_prompt(self, action: str, kwargs: dict) -> str:
        """action 유형 + 스타일 + 플랫폼 + 색상 지식을 결합한 영문 프롬프트."""
        p = self._parse_params(kwargs)
        user_prompt = kwargs.get("prompt", "") or p["topic"]

        # 유형별 지시
        type_hints = {
            "banner": "Professional marketing banner image for web/social media promotion.",
            "card_news": "Clean card-news slide image, single panel, suitable for Instagram carousel.",
            "infographic": "Informative infographic with clear data visualization and visual hierarchy.",
            "thumbnail": "Eye-catching click-optimized thumbnail with bold text and high contrast.",
            "logo": "Clean simple logo/icon design, flat vector style, scalable.",
            "ad_creative": "Conversion-focused advertising creative with clear CTA area.",
            "social_post": "Social media post image optimized for maximum engagement.",
            "product_mockup": "Realistic product mockup in professional setting.",
            "generate": "High-quality professional image.",
        }
        type_hint = type_hints.get(action, type_hints["generate"])

        # 스타일 가이드
        sg = _STYLE_GUIDES.get(p["style"], _STYLE_GUIDES["minimal"])
        style_part = f"Design style: {sg['prompt_hint']}. Avoid: {sg['avoid']}."

        # 플랫폼 힌트
        plat = _PLATFORM_SPECS.get(p["platform"], {})
        plat_part = f"Platform optimization: {plat['hint']}." if plat.get("hint") else ""

        # 색상 심리학
        color_hints = []
        if p["colors"]:
            for hex_code, meaning in _COLOR_PSYCHOLOGY.items():
                if hex_code.lower() in p["colors"].lower():
                    color_hints.append(meaning)
        color_part = f"Color psychology: {', '.join(color_hints)}." if color_hints else ""
        color_spec = f"Use brand colors: {p['colors']}." if p["colors"] else ""

        # 텍스트 오버레이
        text_part = f'Include text overlay: "{p["text_overlay"]}".' if p["text_overlay"] else ""

        # 추가 맥락
        ctx_part = f"Additional context: {p['context']}." if p["context"] else ""

        parts = [type_hint, user_prompt, style_part, plat_part, color_spec, color_part, text_part, ctx_part]
        return " ".join(part for part in parts if part).strip()

    # ─── aspect ratio 결정 ────────────────────────────

    def _resolve_aspect_ratio(self, action: str, kwargs: dict) -> str:
        """kwargs → 플랫폼 → action 기본값 순서로 aspect ratio 결정."""
        # 1) 명시적 지정
        explicit = kwargs.get("aspect_ratio", "")
        if explicit in _VALID_ASPECTS:
            return explicit

        # 2) 플랫폼 기반
        platform = kwargs.get("platform", "")
        plat = _PLATFORM_SPECS.get(platform, {})
        if plat.get("ratio") in _VALID_ASPECTS:
            return plat["ratio"]

        # 3) action 기본값
        action_defaults = {
            "banner": "16:9",
            "card_news": "1:1",
            "infographic": "3:4",
            "thumbnail": "16:9",
            "logo": "1:1",
            "ad_creative": "1:1",
            "social_post": "1:1",
            "product_mockup": "4:3",
        }
        return action_defaults.get(action, "1:1")

    # ─── 핵심: 실제 이미지 생성 ───────────────────────

    async def _generate(self, kwargs: dict) -> str:
        """Gemini 나노바나나 Pro API로 실제 이미지 생성."""
        genai = _get_genai()
        if genai is None:
            return "google-genai 라이브러리가 설치되지 않았습니다. pip install google-genai"

        api_key = self._get_api_key()
        if not api_key:
            return "GOOGLE_API_KEY 환경변수가 설정되지 않았습니다."

        prompt = kwargs.get("prompt", "")
        if not prompt:
            return "이미지 프롬프트(prompt)를 입력해주세요."

        aspect_ratio = kwargs.get("aspect_ratio", "1:1")
        if aspect_ratio not in _VALID_ASPECTS:
            aspect_ratio = "1:1"

        try:
            from google.genai import types

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=self._IMAGE_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=aspect_ratio,
                    ),
                ),
            )

            out_dir = self._ensure_output_dir()
            saved_files: list[str] = []
            text_parts: list[str] = []

            for part in response.parts:
                if part.text is not None:
                    text_parts.append(part.text)
                elif image := part.as_image():
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"gemini_{ts}_{len(saved_files)}.png"
                    filepath = os.path.join(out_dir, filename)
                    image.save(filepath)
                    saved_files.append(filename)
                    logger.info("이미지 저장: %s", filepath)

            if not saved_files:
                text_resp = "\n".join(text_parts)[:500] if text_parts else "(응답 없음)"
                return f"이미지 생성 실패 — 텍스트 응답만 수신:\n{text_resp}"

            files_md = "\n".join(f"- `/api/media/images/{f}`" for f in saved_files)
            text_resp = "\n".join(text_parts) if text_parts else ""

            result = (
                f"## 이미지 생성 완료 (나노바나나 Pro)\n\n"
                f"| 항목 | 값 |\n|------|----|\n"
                f"| 모델 | `{self._IMAGE_MODEL}` |\n"
                f"| 비율 | {aspect_ratio} |\n"
                f"| 생성 수 | {len(saved_files)}장 |\n\n"
                f"### 저장된 파일\n{files_md}"
            )
            if text_resp:
                result += f"\n\n### AI 코멘트\n{text_resp}"
            return result

        except Exception as e:
            logger.error("이미지 생성 실패: %s", e)
            return f"이미지 생성 실패: {e}"

    # ─── 유형별 이미지 생성 (프롬프트 자동 구축) ───────

    async def _generate_typed(self, action: str, kwargs: dict) -> str:
        """유형별 이미지 생성 — 교수급 디자인 지식 프롬프트 자동 구축."""
        prompt = self._build_prompt(action, kwargs)
        aspect_ratio = self._resolve_aspect_ratio(action, kwargs)

        enriched = {**kwargs, "prompt": prompt, "aspect_ratio": aspect_ratio}
        return await self._generate(enriched)

    # ─── 종합 세트 생성 ──────────────────────────────

    async def _generate_full_set(self, kwargs: dict) -> str:
        """주요 유형 이미지를 한 번에 생성 (배너 + 소셜 + 썸네일)."""
        actions = ["banner", "social_post", "thumbnail"]
        results: list[str] = []
        for act in actions:
            res = await self._generate_typed(act, kwargs)
            results.append(f"### {act.upper()}\n{res}")

        return (
            f"# 마케팅 이미지 세트 생성 완료\n\n"
            + "\n\n---\n\n".join(results)
        )
