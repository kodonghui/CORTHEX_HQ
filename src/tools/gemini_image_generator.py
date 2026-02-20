"""
Gemini 기반 마케팅 이미지 생성 도구 — CMO(마케팅·고객처) 전용 이미지 프롬프트 엔지니어링.

학술·실무 근거:
  - Canva Design School (2024), Meta Ads Creative Best Practices (2024)
  - Google Ads Image Requirements (2024), Labrecque & Milne (2012) — Color Psychology
  - Lidwell et al. (2010) — Visual Hierarchy / Universal Principles of Design

action: banner | card_news | infographic | thumbnail | logo | ad_creative
        social_post | product_mockup | full
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.gemini_image_generator")


# ═══════════════════════════════════════════════════════
#  플랫폼별 권장 이미지 크기 (Canva Design School, 2024)
# ═══════════════════════════════════════════════════════

_IMAGE_SIZES: dict[str, dict[str, str]] = {
    "instagram_feed": {"size": "1080x1080", "ratio": "1:1", "label": "인스타그램 피드"},
    "instagram_story": {"size": "1080x1920", "ratio": "9:16", "label": "인스타그램 스토리"},
    "facebook_feed": {"size": "1200x630", "ratio": "1.91:1", "label": "페이스북 피드"},
    "facebook_ad": {"size": "1080x1080", "ratio": "1:1", "label": "페이스북 광고"},
    "youtube_thumbnail": {"size": "1280x720", "ratio": "16:9", "label": "유튜브 썸네일"},
    "youtube_banner": {"size": "2560x1440", "ratio": "16:9", "label": "유튜브 배너"},
    "blog_hero": {"size": "1920x1080", "ratio": "16:9", "label": "블로그 히어로 이미지"},
    "naver_blog": {"size": "960x960", "ratio": "1:1", "label": "네이버 블로그"},
    "twitter_post": {"size": "1600x900", "ratio": "16:9", "label": "트위터/X 포스트"},
    "linkedin_post": {"size": "1200x627", "ratio": "1.91:1", "label": "링크드인 포스트"},
    "google_display": {"size": "1200x628", "ratio": "1.91:1", "label": "구글 디스플레이"},
    "newsletter": {"size": "600x300", "ratio": "2:1", "label": "뉴스레터 헤더"},
    "kakao_channel": {"size": "720x720", "ratio": "1:1", "label": "카카오 채널"},
    "app_icon": {"size": "1024x1024", "ratio": "1:1", "label": "앱 아이콘"},
    "og_image": {"size": "1200x630", "ratio": "1.91:1", "label": "OG 이미지 (링크 미리보기)"},
}

# ═══════════════════════════════════════════════════════
#  디자인 스타일 가이드 (5가지)
# ═══════════════════════════════════════════════════════

_STYLE_GUIDES: dict[str, dict[str, Any]] = {
    "minimal": {
        "name_ko": "미니멀",
        "principles": ["여백 70% 이상 유지", "색상 2~3개 제한", "산세리프 폰트", "핵심 메시지 하나에 집중"],
        "mood": "깔끔, 세련, 고급, 신뢰",
        "avoid": "그라데이션 과다, 장식 폰트, 복잡한 패턴",
        "best_for": "SaaS, 테크, 프리미엄 브랜드, B2B",
    },
    "corporate": {
        "name_ko": "기업형",
        "principles": ["브랜드 컬러 일관성", "격자 기반 정렬", "명확한 시각 계층", "로고 배치 규칙 준수"],
        "mood": "전문적, 안정적, 권위적, 신뢰",
        "avoid": "과도한 이모지, 캐주얼 폰트, 네온 컬러",
        "best_for": "금융, 컨설팅, 법률, 헬스케어, B2B",
    },
    "playful": {
        "name_ko": "캐주얼/재미",
        "principles": ["밝은 색상 팔레트 4~5색", "둥근 모서리·유기적 형태", "일러스트/캐릭터 활용", "움직임 암시"],
        "mood": "친근, 재미, 활기, 접근성",
        "avoid": "딱딱한 격자, 모노톤, 각진 레이아웃",
        "best_for": "F&B, 교육, 키즈, 라이프스타일, D2C",
    },
    "luxury": {
        "name_ko": "럭셔리",
        "principles": ["다크 배경 (블랙/네이비)", "골드·실버 악센트", "세리프 폰트", "넉넉한 여백 + 대칭 구도"],
        "mood": "고급, 우아, 세련, 독점적",
        "avoid": "네온 컬러, 만화 폰트, 복잡한 배경",
        "best_for": "명품, 주얼리, 호텔, 와인, 부동산",
    },
    "tech": {
        "name_ko": "테크",
        "principles": ["다크 모드 기반", "네온 악센트 (시안/퍼플)", "기하학적 패턴", "미래적 그라데이션"],
        "mood": "혁신, 미래, 첨단, 스마트",
        "avoid": "파스텔 위주, 손글씨 폰트, 빈티지 텍스처",
        "best_for": "AI, SaaS, 핀테크, 블록체인, 스타트업",
    },
}

# ═══════════════════════════════════════════════════════
#  플랫폼별 세부 사양 (Meta, Google, 각 플랫폼 공식 문서)
# ═══════════════════════════════════════════════════════

_PLATFORM_SPECS: dict[str, dict[str, Any]] = {
    "instagram": {
        "text_ratio": "20% 이하 (텍스트 최소화가 성과 최적)",
        "safe_zone": "상하좌우 14.3% 마진",
        "max_file_size": "30MB",
        "key_rule": "첫 0.5초에 시선을 사로잡아야 함 — 강렬한 컬러 or 인물 클로즈업",
    },
    "facebook": {
        "text_ratio": "20% 이하 (Meta 정책: 텍스트 과다 시 도달률 감소)",
        "safe_zone": "광고는 상단 15% 프로필 영역 피하기",
        "max_file_size": "30MB",
        "key_rule": "명확한 CTA 버튼 영역 확보, 얼굴 포함 시 성과 2배",
    },
    "youtube": {
        "text_ratio": "30% 이하 (썸네일은 텍스트 3~5단어가 최적)",
        "safe_zone": "우하단 타임스탬프 영역(20%) 피하기",
        "max_file_size": "2MB",
        "key_rule": "고대비 컬러, 큰 폰트, 인물 표정이 핵심 (CTR +30%)",
    },
    "naver_blog": {
        "text_ratio": "자유 (네이버는 텍스트 비율 제한 없음)",
        "safe_zone": "모바일 기준 양쪽 5% 마진",
        "max_file_size": "10MB/장",
        "key_rule": "정사각형(1:1) 또는 4:3이 모바일 최적, 대표 이미지가 검색 노출 결정",
    },
    "twitter": {
        "text_ratio": "25% 이하",
        "safe_zone": "16:9 비율 권장, 모바일에서 자동 크롭 주의",
        "max_file_size": "5MB (정지), 15MB (GIF)",
        "key_rule": "타임라인 스크롤 중 눈에 띄는 고대비 디자인",
    },
    "linkedin": {
        "text_ratio": "30% 이하",
        "safe_zone": "1.91:1 비율, 중앙 정렬 권장",
        "max_file_size": "10MB",
        "key_rule": "전문적 톤, 데이터 시각화 포함 시 인게이지먼트 3배",
    },
    "google_ads": {
        "text_ratio": "20% 이하 (구글 정책 준수)",
        "safe_zone": "핵심 요소는 중앙 80% 영역에 배치",
        "max_file_size": "5120KB",
        "key_rule": "명확한 제품/서비스 이미지 + 로고, 워터마크 금지",
    },
    "kakao": {
        "text_ratio": "자유",
        "safe_zone": "1:1 비율, 원형 프로필 영역 고려",
        "max_file_size": "5MB",
        "key_rule": "모바일 최적화 필수, 카카오 옐로우(#FEE500) 배경과 충돌 주의",
    },
    "newsletter": {
        "text_ratio": "40% 이하",
        "safe_zone": "이메일 클라이언트별 600px 폭 기준",
        "max_file_size": "1MB 이하 권장 (로딩 속도)",
        "key_rule": "ALT 텍스트 필수, 이미지 차단 시 대체 텍스트 보임",
    },
    "app_store": {
        "text_ratio": "자유",
        "safe_zone": "앱 아이콘은 자동 라운드 처리 고려",
        "max_file_size": "아이콘 1024x1024 필수",
        "key_rule": "앱 아이콘은 심플한 단일 심볼, 텍스트 배제 권장",
    },
}

# ═══════════════════════════════════════════════════════
#  색상 심리학 (Labrecque & Milne, 2012)
# ═══════════════════════════════════════════════════════

_COLOR_PSYCHOLOGY: dict[str, dict[str, str]] = {
    "red": {
        "hex": "#E74C3C", "name_ko": "빨강",
        "emotion": "열정, 긴급, 에너지, 흥분",
        "marketing_use": "할인/세일, CTA 버튼, 긴급 프로모션, 음식 업종",
    },
    "orange": {
        "hex": "#E67E22", "name_ko": "오렌지",
        "emotion": "친근, 재미, 활력, 창의",
        "marketing_use": "CTA 버튼(전환율 높음), 무료 체험 유도, 젊은 타깃",
    },
    "green": {
        "hex": "#27AE60", "name_ko": "초록",
        "emotion": "성장, 건강, 자연, 안정",
        "marketing_use": "친환경, 건강식품, 금융(수익), 승인/완료 표시",
    },
    "blue": {
        "hex": "#2980B9", "name_ko": "파랑",
        "emotion": "신뢰, 안정, 전문성, 평온",
        "marketing_use": "기업/B2B, 금융, 테크, 의료 — 가장 보편적 비즈니스 컬러",
    },
    "purple": {
        "hex": "#8E44AD", "name_ko": "보라",
        "emotion": "고급, 창의, 신비, 지혜",
        "marketing_use": "뷰티/코스메틱, 럭셔리, 교육, AI/테크",
    },
    "black": {
        "hex": "#2C3E50", "name_ko": "블랙",
        "emotion": "고급, 세련, 권위, 미스터리",
        "marketing_use": "럭셔리, 패션, 테크, 프리미엄 브랜드",
    },
    "white": {
        "hex": "#FFFFFF", "name_ko": "화이트",
        "emotion": "깨끗, 미니멀, 순수, 모던",
        "marketing_use": "미니멀 브랜드, 애플 스타일, 헬스케어, 여백 강조",
    },
    "gold": {
        "hex": "#D4A017", "name_ko": "골드",
        "emotion": "고급, 성공, 부, 따뜻한 프리미엄",
        "marketing_use": "럭셔리, 금융, VIP/프리미엄 등급, 수상/인증",
    },
}


class GeminiImageGeneratorTool(BaseTool):
    """Gemini 기반 마케팅 이미지 프롬프트 생성 도구 (CMO 전용)."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "banner")
        dispatch = {
            "banner": self._generate_banner,
            "card_news": self._generate_card_news,
            "infographic": self._generate_infographic,
            "thumbnail": self._generate_thumbnail,
            "logo": self._generate_logo,
            "ad_creative": self._generate_ad_creative,
            "social_post": self._generate_social_post,
            "product_mockup": self._generate_product_mockup,
            "full": self._generate_full_set,
        }
        handler = dispatch.get(action)
        if not handler:
            return (
                f"## 알 수 없는 action: `{action}`\n\n"
                f"사용 가능한 action 목록:\n"
                + "\n".join(f"- `{k}` : {self._action_label(k)}" for k in dispatch)
            )
        return await handler(kwargs)

    # ─── action 라벨 헬퍼 ─────────────────────────────
    @staticmethod
    def _action_label(action: str) -> str:
        labels = {
            "banner": "배너 이미지 생성 (웹/소셜 배너, 프로모션)",
            "card_news": "카드뉴스 생성 (인스타그램/블로그 슬라이드)",
            "infographic": "인포그래픽 생성 (데이터 시각화, 프로세스 설명)",
            "thumbnail": "썸네일 생성 (유튜브/블로그/뉴스레터)",
            "logo": "로고/아이콘 생성 (브랜드 로고, 앱 아이콘)",
            "ad_creative": "광고 크리에이티브 생성 (페이스북/구글 광고)",
            "social_post": "소셜 미디어 포스트 이미지 (인스타/트위터/링크드인)",
            "product_mockup": "제품 목업 이미지 (앱 스크린샷, 패키징)",
            "full": "마케팅 이미지 세트 종합 생성",
        }
        return labels.get(action, action)

    # ─── 공통 파라미터 파싱 ─────────────────────────────
    @staticmethod
    def _parse_params(kwargs: dict) -> dict[str, str]:
        return {
            "topic": kwargs.get("topic", "CORTHEX HQ AI 비서 서비스"),
            "style": kwargs.get("style", "minimal"),
            "colors": kwargs.get("colors", "#3B82F6, #1E293B, #FFFFFF"),
            "text_overlay": kwargs.get("text_overlay", ""),
            "size": kwargs.get("size", "1080x1080"),
            "context": kwargs.get("context", ""),
        }

    def _get_style_guide(self, style: str) -> dict[str, Any]:
        return _STYLE_GUIDES.get(style, _STYLE_GUIDES["minimal"])

    @staticmethod
    def _get_size_info(size: str) -> str:
        for key, info in _IMAGE_SIZES.items():
            if info["size"] == size:
                return f"{info['label']} ({info['size']}, 비율 {info['ratio']})"
        return f"커스텀 크기 ({size})"

    @staticmethod
    def _get_color_insights(colors: str) -> list[str]:
        insights = []
        color_str = colors.lower().replace(" ", "")
        for ckey, cdata in _COLOR_PSYCHOLOGY.items():
            if cdata["hex"].lower() in color_str:
                insights.append(
                    f"  - {cdata['name_ko']}({cdata['hex']}): {cdata['emotion']} → {cdata['marketing_use']}"
                )
        if not insights:
            insights.append("  - 커스텀 컬러 사용 — 브랜드 가이드에 맞춰 일관성 유지 필요")
        return insights

    # ─── 1. 배너 ───

    async def _generate_banner(self, kwargs: dict) -> str:
        """웹/소셜 배너 이미지 프롬프트 생성."""
        p = self._parse_params(kwargs)
        sg = self._get_style_guide(p["style"])

        system_prompt = (
            "당신은 세계적 수준의 마케팅 디자이너입니다. "
            "배너 이미지 생성을 위한 상세한 Gemini Imagen 프롬프트를 작성합니다.\n"
            "반드시 한국어로 응답하세요. 프롬프트는 영문으로 작성하되, 가이드는 한국어로.\n"
            "구체적인 구도, 색상 배치, 타이포그래피 위치까지 상세하게 명시하세요."
        )
        user_prompt = (
            f"## 배너 이미지 생성 요청\n\n"
            f"- **주제**: {p['topic']}\n"
            f"- **스타일**: {sg['name_ko']} ({p['style']})\n"
            f"- **브랜드 컬러**: {p['colors']}\n"
            f"- **텍스트 오버레이**: {p['text_overlay'] or '없음'}\n"
            f"- **크기**: {self._get_size_info(p['size'])}\n"
            f"- **추가 맥락**: {p['context'] or '없음'}\n\n"
            f"### 스타일 원칙\n" + "\n".join(f"- {pr}" for pr in sg["principles"]) + "\n\n"
            f"다음을 포함해서 작성해주세요:\n"
            f"1. Gemini Imagen용 영문 프롬프트 (200자 이상 상세)\n"
            f"2. 네거티브 프롬프트 (피해야 할 요소)\n"
            f"3. 레이아웃 구도 설명 (ASCII 또는 텍스트)\n"
            f"4. 마케팅 활용 가이드 (어디에 어떻게 쓸 수 있는지)\n"
            f"5. A/B 테스트 변형 제안 2가지"
        )
        result = await self._llm_call(system_prompt=system_prompt, user_prompt=user_prompt)
        return self._wrap_output("배너 이미지", p, sg, result)

    # ─── 2. 카드뉴스 ───

    async def _generate_card_news(self, kwargs: dict) -> str:
        """인스타그램/블로그용 카드뉴스 슬라이드 프롬프트 생성."""
        p = self._parse_params(kwargs)
        sg = self._get_style_guide(p["style"])
        slide_count = kwargs.get("slide_count", 5)

        system_prompt = (
            "당신은 인스타그램 카드뉴스 전문 디자이너입니다. "
            "각 슬라이드별 상세 이미지 프롬프트와 텍스트 배치를 설계합니다.\n"
            "한국어로 응답. 프롬프트는 영문, 가이드는 한국어."
        )
        user_prompt = (
            f"## 카드뉴스 생성 요청 ({slide_count}장 슬라이드)\n\n"
            f"- **주제**: {p['topic']}\n"
            f"- **스타일**: {sg['name_ko']}\n"
            f"- **브랜드 컬러**: {p['colors']}\n"
            f"- **슬라이드 수**: {slide_count}장\n"
            f"- **크기**: 1080x1080 (인스타그램 피드 최적)\n"
            f"- **추가 맥락**: {p['context'] or '없음'}\n\n"
            f"각 슬라이드별로:\n"
            f"1. 슬라이드 번호 + 역할 (표지/내용/CTA)\n"
            f"2. Gemini Imagen용 영문 프롬프트\n"
            f"3. 텍스트 오버레이 내용 + 위치\n"
            f"4. 배경 설명 + 컬러 사용법\n"
            f"5. 슬라이드 간 시각적 연결성(일관성) 방안\n\n"
            f"마지막에 전체 카드뉴스 마케팅 전략 포함."
        )
        result = await self._llm_call(system_prompt=system_prompt, user_prompt=user_prompt)
        return self._wrap_output("카드뉴스", p, sg, result)

    # ═══════════════════════════════════════════════════════
    #  3. 인포그래픽 생성
    # ═══════════════════════════════════════════════════════

    async def _generate_infographic(self, kwargs: dict) -> str:
        """데이터 시각화 인포그래픽 프롬프트 생성."""
        p = self._parse_params(kwargs)
        sg = self._get_style_guide(p["style"])
        data_points = kwargs.get("data_points", "")

        system_prompt = (
            "당신은 정보 디자인 전문가입니다. "
            "데이터를 시각적으로 명확하게 전달하는 인포그래픽을 설계합니다.\n"
            "한국어 응답. 시각 계층 구조를 반드시 포함하세요."
        )
        user_prompt = (
            f"## 인포그래픽 생성 요청\n\n"
            f"- **주제**: {p['topic']}\n"
            f"- **스타일**: {sg['name_ko']}\n"
            f"- **브랜드 컬러**: {p['colors']}\n"
            f"- **크기**: {p['size']} (세로 긴 형태 권장: 800x2000)\n"
            f"- **데이터 포인트**: {data_points or '자동 구성'}\n"
            f"- **추가 맥락**: {p['context'] or '없음'}\n\n"
            f"다음을 포함:\n"
            f"1. 인포그래픽 전체 구조 (상→하 섹션별 설명)\n"
            f"2. 각 섹션별 Gemini Imagen 영문 프롬프트\n"
            f"3. 데이터 시각화 방법 (차트 유형, 아이콘, 비교 표현)\n"
            f"4. 타이포그래피 계층 (제목/소제목/본문/숫자)\n"
            f"5. 아이콘·일러스트 스타일 가이드\n"
            f"6. 소셜 미디어 공유 최적화 팁"
        )
        result = await self._llm_call(system_prompt=system_prompt, user_prompt=user_prompt)
        return self._wrap_output("인포그래픽", p, sg, result)

    # ═══════════════════════════════════════════════════════
    #  4. 썸네일 생성
    # ═══════════════════════════════════════════════════════

    async def _generate_thumbnail(self, kwargs: dict) -> str:
        """유튜브/블로그/뉴스레터 썸네일 프롬프트 생성."""
        p = self._parse_params(kwargs)
        sg = self._get_style_guide(p["style"])
        platform = kwargs.get("platform", "youtube")
        yt_spec = _PLATFORM_SPECS.get(platform, _PLATFORM_SPECS["youtube"])

        system_prompt = (
            "당신은 유튜브 썸네일 전문 디자이너입니다 (CTR 전문가). "
            "클릭률을 극대화하는 썸네일 디자인을 제안합니다.\n"
            "한국어 응답. 프롬프트는 영문."
        )
        user_prompt = (
            f"## 썸네일 생성 요청 ({platform})\n\n"
            f"- **주제**: {p['topic']}\n"
            f"- **스타일**: {sg['name_ko']}\n"
            f"- **브랜드 컬러**: {p['colors']}\n"
            f"- **텍스트 오버레이**: {p['text_overlay'] or '자동 제안'}\n"
            f"- **크기**: {_IMAGE_SIZES.get(f'{platform}_thumbnail', {}).get('size', '1280x720')}\n\n"
            f"### 플랫폼 사양\n"
            f"- 텍스트 비율: {yt_spec['text_ratio']}\n"
            f"- 안전 영역: {yt_spec['safe_zone']}\n"
            f"- 핵심 규칙: {yt_spec['key_rule']}\n\n"
            f"다음을 포함:\n"
            f"1. Gemini Imagen용 영문 프롬프트 (고대비, 시선 유도 요소)\n"
            f"2. 네거티브 프롬프트\n"
            f"3. 텍스트 오버레이 가이드 (폰트 크기, 위치, 효과)\n"
            f"4. CTR 최적화 체크리스트\n"
            f"5. 변형 3가지 (A/B/C 테스트용)"
        )
        result = await self._llm_call(system_prompt=system_prompt, user_prompt=user_prompt)
        return self._wrap_output("썸네일", p, sg, result)

    # ═══════════════════════════════════════════════════════
    #  5. 로고/아이콘 생성
    # ═══════════════════════════════════════════════════════

    async def _generate_logo(self, kwargs: dict) -> str:
        """브랜드 로고/앱 아이콘 프롬프트 생성."""
        p = self._parse_params(kwargs)
        sg = self._get_style_guide(p["style"])
        logo_type = kwargs.get("logo_type", "symbol")

        system_prompt = (
            "당신은 브랜드 아이덴티티 전문 디자이너입니다. "
            "심볼 마크, 워드 마크, 컴비네이션 마크를 설계합니다.\n"
            "한국어 응답. 확대/축소 시 가독성을 반드시 고려하세요."
        )
        user_prompt = (
            f"## 로고/아이콘 생성 요청\n\n"
            f"- **브랜드명**: {p['topic']}\n"
            f"- **로고 유형**: {logo_type} (symbol/wordmark/combination)\n"
            f"- **스타일**: {sg['name_ko']}\n"
            f"- **브랜드 컬러**: {p['colors']}\n"
            f"- **크기**: 1024x1024 (앱 아이콘 겸용)\n"
            f"- **추가 맥락**: {p['context'] or '없음'}\n\n"
            f"다음을 포함:\n"
            f"1. Gemini Imagen용 영문 프롬프트 (심플한 벡터 스타일)\n"
            f"2. 네거티브 프롬프트 (복잡한 디테일 배제)\n"
            f"3. 로고 사용 가이드 (최소 크기, 여백 규정, 컬러 변형)\n"
            f"4. 다양한 배경(밝은/어두운)에서의 활용 방법\n"
            f"5. 파비콘(16x16) 축소 시 가독성 확인 포인트\n"
            f"6. 경쟁사 로고와의 차별화 포인트"
        )
        result = await self._llm_call(system_prompt=system_prompt, user_prompt=user_prompt)
        return self._wrap_output("로고/아이콘", p, sg, result)

    # ═══════════════════════════════════════════════════════
    #  6. 광고 크리에이티브 생성
    # ═══════════════════════════════════════════════════════

    async def _generate_ad_creative(self, kwargs: dict) -> str:
        """페이스북/구글 광고 크리에이티브 프롬프트 생성."""
        p = self._parse_params(kwargs)
        sg = self._get_style_guide(p["style"])
        ad_platform = kwargs.get("ad_platform", "facebook")
        ad_spec = _PLATFORM_SPECS.get(
            "google_ads" if ad_platform == "google" else ad_platform,
            _PLATFORM_SPECS["facebook"],
        )

        system_prompt = (
            "당신은 퍼포먼스 마케팅 크리에이티브 전문가입니다. "
            "ROAS를 극대화하는 광고 이미지를 설계합니다.\n"
            "한국어 응답. 광고 정책 준수 여부를 반드시 체크하세요."
        )
        user_prompt = (
            f"## 광고 크리에이티브 생성 요청 ({ad_platform})\n\n"
            f"- **제품/서비스**: {p['topic']}\n"
            f"- **스타일**: {sg['name_ko']}\n"
            f"- **브랜드 컬러**: {p['colors']}\n"
            f"- **CTA 텍스트**: {p['text_overlay'] or '지금 시작하기'}\n"
            f"- **추가 맥락**: {p['context'] or '없음'}\n\n"
            f"### 플랫폼 광고 정책\n"
            f"- 텍스트 비율: {ad_spec['text_ratio']}\n"
            f"- 안전 영역: {ad_spec['safe_zone']}\n"
            f"- 핵심 규칙: {ad_spec['key_rule']}\n"
            f"- 파일 제한: {ad_spec['max_file_size']}\n\n"
            f"다음을 포함:\n"
            f"1. 3가지 크기별 Gemini Imagen 영문 프롬프트 (정사각/가로/세로)\n"
            f"2. 네거티브 프롬프트\n"
            f"3. 광고 정책 준수 체크리스트\n"
            f"4. CTA 배치 가이드\n"
            f"5. A/B 테스트 전략 (이미지 변수 3가지)\n"
            f"6. 예상 CTR 개선 포인트"
        )
        result = await self._llm_call(system_prompt=system_prompt, user_prompt=user_prompt)
        return self._wrap_output("광고 크리에이티브", p, sg, result)

    # ═══════════════════════════════════════════════════════
    #  7. 소셜 미디어 포스트 이미지
    # ═══════════════════════════════════════════════════════

    async def _generate_social_post(self, kwargs: dict) -> str:
        """인스타/트위터/링크드인 포스트 이미지 프롬프트 생성."""
        p = self._parse_params(kwargs)
        sg = self._get_style_guide(p["style"])
        platform = kwargs.get("platform", "instagram")
        plat_spec = _PLATFORM_SPECS.get(platform, _PLATFORM_SPECS["instagram"])

        system_prompt = (
            "당신은 소셜 미디어 비주얼 콘텐츠 전문가입니다. "
            "플랫폼 알고리즘에 최적화된 이미지를 설계합니다.\n"
            "한국어 응답. 프롬프트는 영문."
        )
        user_prompt = (
            f"## 소셜 포스트 이미지 생성 요청 ({platform})\n\n"
            f"- **주제**: {p['topic']}\n"
            f"- **스타일**: {sg['name_ko']}\n"
            f"- **브랜드 컬러**: {p['colors']}\n"
            f"- **텍스트 오버레이**: {p['text_overlay'] or '없음'}\n"
            f"- **추가 맥락**: {p['context'] or '없음'}\n\n"
            f"### 플랫폼 사양 ({platform})\n"
            f"- 텍스트 비율: {plat_spec['text_ratio']}\n"
            f"- 안전 영역: {plat_spec['safe_zone']}\n"
            f"- 핵심 규칙: {plat_spec['key_rule']}\n\n"
            f"다음을 포함:\n"
            f"1. Gemini Imagen용 영문 프롬프트\n"
            f"2. 네거티브 프롬프트\n"
            f"3. 캡션 제안 (해시태그 포함)\n"
            f"4. 게시 최적 시간대 (KST 기준)\n"
            f"5. 인게이지먼트 극대화 팁\n"
            f"6. 리포스팅 변형 가이드 (크로스 플랫폼)"
        )
        result = await self._llm_call(system_prompt=system_prompt, user_prompt=user_prompt)
        return self._wrap_output("소셜 포스트 이미지", p, sg, result)

    # ═══════════════════════════════════════════════════════
    #  8. 제품 목업 이미지
    # ═══════════════════════════════════════════════════════

    async def _generate_product_mockup(self, kwargs: dict) -> str:
        """앱 스크린샷/패키징 제품 목업 프롬프트 생성."""
        p = self._parse_params(kwargs)
        sg = self._get_style_guide(p["style"])
        mockup_type = kwargs.get("mockup_type", "app_screenshot")

        system_prompt = (
            "당신은 제품 시각화 전문가입니다. "
            "실제 사용 환경에서의 제품 목업을 사실적으로 설계합니다.\n"
            "한국어 응답. 프롬프트는 영문."
        )
        user_prompt = (
            f"## 제품 목업 생성 요청\n\n"
            f"- **제품**: {p['topic']}\n"
            f"- **목업 유형**: {mockup_type} (app_screenshot/packaging/device/print)\n"
            f"- **스타일**: {sg['name_ko']}\n"
            f"- **브랜드 컬러**: {p['colors']}\n"
            f"- **추가 맥락**: {p['context'] or '없음'}\n\n"
            f"다음을 포함:\n"
            f"1. Gemini Imagen용 영문 프롬프트 (사실적 목업 씬)\n"
            f"2. 네거티브 프롬프트\n"
            f"3. 카메라 앵글 + 조명 설정 설명\n"
            f"4. 배경 환경 설정 (데스크/카페/스튜디오 등)\n"
            f"5. 디바이스 프레임 가이드 (iPhone/MacBook/iPad)\n"
            f"6. 앱 스토어 스크린샷 최적화 팁"
        )
        result = await self._llm_call(system_prompt=system_prompt, user_prompt=user_prompt)
        return self._wrap_output("제품 목업", p, sg, result)

    # ═══════════════════════════════════════════════════════
    #  9. 종합 (full) — 마케팅 이미지 세트
    # ═══════════════════════════════════════════════════════

    async def _generate_full_set(self, kwargs: dict) -> str:
        """전체 마케팅 이미지 세트를 한 번에 생성."""
        p = self._parse_params(kwargs)
        sg = self._get_style_guide(p["style"])

        # 개별 생성 결과 수집
        sections: list[str] = []
        actions = ["banner", "card_news", "thumbnail", "social_post", "ad_creative"]
        action_handlers = {
            "banner": self._generate_banner,
            "card_news": self._generate_card_news,
            "thumbnail": self._generate_thumbnail,
            "social_post": self._generate_social_post,
            "ad_creative": self._generate_ad_creative,
        }
        for act in actions:
            handler = action_handlers[act]
            section_result = await handler(kwargs)
            sections.append(section_result)

        # 종합 가이드 생성
        system_prompt = (
            "당신은 마케팅 크리에이티브 디렉터입니다. "
            "모든 채널의 이미지 일관성을 관리하는 종합 가이드를 작성합니다.\n"
            "한국어로 응답하세요."
        )
        user_prompt = (
            f"## 마케팅 이미지 세트 종합 가이드\n\n"
            f"- **브랜드**: {p['topic']}\n"
            f"- **스타일**: {sg['name_ko']}\n"
            f"- **컬러**: {p['colors']}\n\n"
            f"다음을 포함하는 종합 가이드 작성:\n"
            f"1. 브랜드 비주얼 일관성 체크리스트\n"
            f"2. 채널별 이미지 우선순위 (ROI 기준)\n"
            f"3. 콘텐츠 캘린더 제안 (주간 이미지 제작 스케줄)\n"
            f"4. A/B 테스트 로드맵\n"
            f"5. 이미지 성과 측정 KPI (CTR, 인게이지먼트율, 전환율)\n"
            f"6. 비용 최적화 팁 (무료 도구 활용법)"
        )
        comprehensive_guide = await self._llm_call(
            system_prompt=system_prompt, user_prompt=user_prompt
        )

        divider = "\n\n---\n\n"
        return (
            f"# 마케팅 이미지 세트 종합 리포트\n\n"
            f"**브랜드**: {p['topic']} | **스타일**: {sg['name_ko']} | "
            f"**컬러**: {p['colors']}\n\n"
            f"---\n\n"
            + divider.join(sections)
            + divider
            + f"# 종합 크리에이티브 가이드\n\n{comprehensive_guide}"
        )

    # ═══════════════════════════════════════════════════════
    #  출력 포맷팅 헬퍼
    # ═══════════════════════════════════════════════════════

    def _wrap_output(
        self,
        image_type: str,
        params: dict[str, str],
        style_guide: dict[str, Any],
        llm_result: str,
    ) -> str:
        """통일된 마크다운 출력 포맷."""
        color_insights = self._get_color_insights(params["colors"])
        size_info = self._get_size_info(params["size"])

        return (
            f"## {image_type} 생성 결과\n\n"
            f"### 요청 파라미터\n"
            f"| 항목 | 값 |\n"
            f"|------|----|\n"
            f"| 주제 | {params['topic']} |\n"
            f"| 스타일 | {style_guide['name_ko']} ({params['style']}) |\n"
            f"| 브랜드 컬러 | {params['colors']} |\n"
            f"| 크기 | {size_info} |\n"
            f"| 텍스트 오버레이 | {params['text_overlay'] or '없음'} |\n\n"
            f"### 스타일 가이드 ({style_guide['name_ko']})\n"
            f"- **분위기**: {style_guide['mood']}\n"
            f"- **피해야 할 것**: {style_guide['avoid']}\n"
            f"- **적합한 업종**: {style_guide['best_for']}\n"
            f"- **디자인 원칙**:\n"
            + "\n".join(f"  - {pr}" for pr in style_guide["principles"])
            + "\n\n"
            f"### 색상 심리학 분석\n"
            + "\n".join(color_insights)
            + "\n\n"
            f"---\n\n"
            f"### 생성 프롬프트 & 가이드\n\n"
            f"{llm_result}\n\n"
            f"---\n\n"
            f"### 참고 자료\n"
            f"- Canva Design School (2024) — 플랫폼별 이미지 사이즈 가이드\n"
            f"- Meta Ads Creative Best Practices (2024) — 광고 크리에이티브 가이드라인\n"
            f"- Google Ads Image Requirements (2024) — 이미지 사양 및 정책\n"
            f"- Labrecque & Milne (2012) — 색상 심리학과 마케팅\n"
            f"- Lidwell et al. (2010) — Universal Principles of Design"
        )
