"""
경쟁 분석 도구 (Competitive Mapper) — 경쟁 구조를 정량적으로 매핑합니다.

Porter 5 Forces + 2D 포지셔닝 맵 + 경쟁 우위(Moat) 분석을 통해
"이 시장에서 우리가 이길 수 있는가"를 구조적으로 판단합니다.

학술 근거:
  - Michael Porter, "Competitive Strategy" (Harvard, 1980) — 5 Forces
  - Porter, "Competitive Advantage" (1985) — Value Chain, Generic Strategies
  - Pat Dorsey, "The Little Book That Builds Wealth" (2008) — Economic Moat
  - Hamilton Helmer, "7 Powers" (2016) — 지속 가능한 경쟁 우위 7가지
  - Kim & Mauborgne, "Blue Ocean Strategy" (INSEAD, 2005) — ERRC/Value Curve

사용 방법:
  - action="full"         : 전체 경쟁 분석 종합
  - action="five_forces"  : Porter 5 Forces 정량 분석
  - action="positioning"  : 2D 포지셔닝 맵 생성
  - action="competitors"  : 경쟁사 비교표 생성
  - action="moat"         : 경쟁 우위(Moat) 진단
  - action="entry"        : 시장 진입 장벽 분석

필요 환경변수: 없음
필요 라이브러리: 없음 (표준 라이브러리만 사용)
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.competitive_mapper")

# ─── Porter 5 Forces 채점 기준 ─────────────────────────

_FORCE_CRITERIA: dict[str, list[dict]] = {
    "rivalry": [
        {"factor": "경쟁사 수", "low": "3개 이하", "mid": "4~10개", "high": "10개 초과"},
        {"factor": "시장 성장률", "low": "고성장(20%+)", "mid": "중성장(5~20%)", "high": "저성장(<5%)"},
        {"factor": "제품 차별화", "low": "높은 차별화", "mid": "중간", "high": "범용(commodity)"},
        {"factor": "전환 비용", "low": "높음", "mid": "중간", "high": "낮음"},
        {"factor": "고정비 비중", "low": "낮음(<30%)", "mid": "중간(30~60%)", "high": "높음(>60%)"},
    ],
    "new_entrants": [
        {"factor": "초기 투자 규모", "low": "대규모(100억+)", "mid": "중규모(10~100억)", "high": "소규모(<10억)"},
        {"factor": "규제 장벽", "low": "인허가 필수", "mid": "부분 규제", "high": "규제 없음"},
        {"factor": "기술 장벽", "low": "특허/독점기술", "mid": "높은 전문성", "high": "범용 기술"},
        {"factor": "규모의 경제", "low": "강함", "mid": "중간", "high": "약함"},
        {"factor": "브랜드 충성도", "low": "강함", "mid": "중간", "high": "약함"},
    ],
    "substitutes": [
        {"factor": "대체재 수", "low": "없음", "mid": "1~3개", "high": "다수"},
        {"factor": "대체재 가격", "low": "비쌈", "mid": "비슷", "high": "저렴"},
        {"factor": "전환 노력", "low": "매우 어려움", "mid": "중간", "high": "쉬움"},
        {"factor": "대체재 품질", "low": "열등", "mid": "유사", "high": "우월"},
    ],
    "buyer_power": [
        {"factor": "구매자 집중도", "low": "분산", "mid": "중간", "high": "소수 대형"},
        {"factor": "전환 비용", "low": "높음", "mid": "중간", "high": "낮음"},
        {"factor": "가격 민감도", "low": "낮음", "mid": "중간", "high": "높음"},
        {"factor": "정보 접근성", "low": "제한적", "mid": "보통", "high": "완전 투명"},
    ],
    "supplier_power": [
        {"factor": "공급자 수", "low": "다수", "mid": "중간", "high": "소수/독점"},
        {"factor": "전환 비용", "low": "낮음", "mid": "중간", "high": "높음"},
        {"factor": "공급자 차별화", "low": "범용", "mid": "중간", "high": "독점 기술"},
        {"factor": "전방 통합 위협", "low": "없음", "mid": "가능성", "high": "활발"},
    ],
}

_FORCE_NAMES_KO = {
    "rivalry": "기존 경쟁자 경쟁 강도",
    "new_entrants": "신규 진입자 위협",
    "substitutes": "대체재 위협",
    "buyer_power": "구매자 교섭력",
    "supplier_power": "공급자 교섭력",
}

# ─── Moat (경쟁 우위) 유형 (Pat Dorsey + Hamilton Helmer) ─

_MOAT_TYPES: dict[str, dict] = {
    "network_effect": {
        "name": "네트워크 효과",
        "desc": "사용자가 늘수록 가치 증가 (예: 카카오톡, LinkedIn)",
        "strength": "매우 강함",
        "examples": "플랫폼, SNS, 마켓플레이스",
        "score_weight": 1.5,
    },
    "switching_cost": {
        "name": "전환 비용",
        "desc": "다른 제품으로 바꾸기 어려움 (예: SAP, Salesforce)",
        "strength": "강함",
        "examples": "B2B SaaS, 엔터프라이즈 SW",
        "score_weight": 1.3,
    },
    "cost_advantage": {
        "name": "원가 우위",
        "desc": "경쟁사보다 낮은 비용 구조 (예: Costco, Southwest Airlines)",
        "strength": "중간",
        "examples": "제조, 유통, 클라우드",
        "score_weight": 1.0,
    },
    "intangible_assets": {
        "name": "무형 자산",
        "desc": "브랜드, 특허, 라이선스 (예: Apple 브랜드, 제약 특허)",
        "strength": "강함",
        "examples": "브랜드 기업, 제약, 프랜차이즈",
        "score_weight": 1.2,
    },
    "efficient_scale": {
        "name": "효율적 규모",
        "desc": "시장이 작아 2개 기업이 공존 불가 (예: 지역 독점 유틸리티)",
        "strength": "강함",
        "examples": "인프라, 유틸리티, 니치 시장",
        "score_weight": 1.1,
    },
    "counter_positioning": {
        "name": "역포지셔닝 (Helmer)",
        "desc": "기존 기업이 따라하면 자기 사업을 잠식 (예: Netflix vs Blockbuster)",
        "strength": "매우 강함",
        "examples": "파괴적 혁신 기업",
        "score_weight": 1.4,
    },
    "process_power": {
        "name": "프로세스 파워 (Helmer)",
        "desc": "내부 프로세스 자체가 경쟁 우위 (예: Toyota 생산시스템)",
        "strength": "중간",
        "examples": "제조, 물류, DevOps 우수 기업",
        "score_weight": 1.0,
    },
}


class CompetitiveMapper(BaseTool):
    """경쟁 분석 도구 — Porter 5 Forces + 포지셔닝 + Moat 진단."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_analysis,
            "five_forces": self._five_forces,
            "positioning": self._positioning_map,
            "competitors": self._competitor_table,
            "moat": self._moat_analysis,
            "entry": self._entry_barrier,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return (
            f"알 수 없는 action: {action}. "
            "full, five_forces, positioning, competitors, moat, entry 중 하나를 사용하세요."
        )

    # ── Full: 경쟁 분석 종합 ──────────────────────────────

    async def _full_analysis(self, p: dict) -> str:
        ff = await self._five_forces(p)
        pos = await self._positioning_map(p)
        comp = await self._competitor_table(p)
        moat = await self._moat_analysis(p)
        entry = await self._entry_barrier(p)

        lines = [
            "# 🏁 경쟁 분석 종합 보고서",
            "",
            "## 1. Porter 5 Forces 분석",
            ff,
            "",
            "## 2. 경쟁 포지셔닝 맵",
            pos,
            "",
            "## 3. 경쟁사 비교표",
            comp,
            "",
            "## 4. 경쟁 우위(Moat) 진단",
            moat,
            "",
            "## 5. 시장 진입 장벽",
            entry,
            "",
            "---",
            "학술 참고: Porter (1980, 1985), Dorsey (2008), Helmer 7 Powers (2016)",
        ]
        return "\n".join(lines)

    # ── Five Forces: Porter 5 Forces 정량 분석 ───────────

    async def _five_forces(self, p: dict) -> str:
        scores: dict[str, int] = {}
        for force_key in _FORCE_CRITERIA:
            raw = p.get(force_key, 0)
            try:
                scores[force_key] = max(1, min(10, int(raw))) if raw else 0
            except (ValueError, TypeError):
                scores[force_key] = 0

        has_scores = any(v > 0 for v in scores.values())
        if not has_scores:
            return self._five_forces_guide()

        total = sum(scores.values())
        max_total = len(scores) * 10
        overall_pct = total / max_total * 100

        if overall_pct > 70:
            verdict = "매우 높은 경쟁 강도 — 레드 오션"
            advice = "차별화 없이 진입하면 가격 경쟁 불가피. 블루오션 전략 필요."
        elif overall_pct > 50:
            verdict = "높은 경쟁 강도 — 선택적 진입"
            advice = "특정 니치에서 강한 포지션 확보 후 확장 전략 추천."
        elif overall_pct > 30:
            verdict = "중간 경쟁 강도 — 기회 존재"
            advice = "적절한 차별화와 실행력으로 시장 선점 가능."
        else:
            verdict = "낮은 경쟁 강도 — 블루 오션"
            advice = "빠른 진입과 선점 효과 극대화 전략 추천."

        # ASCII 레이더 차트 (5각형 근사)
        labels = ["경쟁강도", "진입위협", "대체재", "구매자", "공급자"]
        force_keys = ["rivalry", "new_entrants", "substitutes", "buyer_power", "supplier_power"]

        lines = [
            "### Porter 5 Forces 정량 분석",
            "",
            "| 힘(Force) | 점수(1~10) | 위협 수준 | 핵심 요인 |",
            "|-----------|-----------|---------|---------|",
        ]
        for key, label in zip(force_keys, labels):
            sc = scores.get(key, 0)
            level = "🔴 높음" if sc >= 7 else ("🟡 중간" if sc >= 4 else "🟢 낮음")
            lines.append(f"| {_FORCE_NAMES_KO.get(key, key)} | {sc}/10 | {level} | — |")

        lines.extend([
            "",
            f"**종합 경쟁 강도: {total}/{max_total} ({overall_pct:.0f}%)**",
            f"**판정: {verdict}**",
            f"**전략 제안: {advice}**",
            "",
            "### 5 Forces 시각화 (점수 막대)",
        ])
        for key, label in zip(force_keys, labels):
            sc = scores.get(key, 0)
            bar = "█" * sc + "░" * (10 - sc)
            lines.append(f"  {label:6s} [{bar}] {sc}/10")

        return "\n".join(lines)

    def _five_forces_guide(self) -> str:
        lines = [
            "### Porter 5 Forces 분석을 위해 필요한 입력값:",
            "",
            "각 Force를 1(낮음)~10(높음) 척도로 입력합니다:",
            "",
            "| 파라미터 | 의미 | 높은 점수 = |",
            "|---------|------|-----------|",
            "| rivalry | 기존 경쟁자 강도 | 치열한 경쟁 |",
            "| new_entrants | 신규 진입자 위협 | 진입 장벽 낮음 |",
            "| substitutes | 대체재 위협 | 대체재 많음 |",
            "| buyer_power | 구매자 교섭력 | 구매자 우위 |",
            "| supplier_power | 공급자 교섭력 | 공급자 우위 |",
            "",
            "### 채점 참고 기준:",
        ]
        for force_key, criteria in _FORCE_CRITERIA.items():
            lines.append(f"\n**{_FORCE_NAMES_KO[force_key]}:**")
            lines.append("| 요인 | 1~3 (낮음) | 4~6 (중간) | 7~10 (높음) |")
            lines.append("|------|----------|----------|-----------|")
            for c in criteria:
                lines.append(f"| {c['factor']} | {c['low']} | {c['mid']} | {c['high']} |")
        return "\n".join(lines)

    # ── Positioning: 2D 포지셔닝 맵 ──────────────────────

    async def _positioning_map(self, p: dict) -> str:
        competitors_raw = p.get("competitors", "")
        x_axis = p.get("x_axis", "가격")
        y_axis = p.get("y_axis", "품질")

        if not competitors_raw:
            return self._positioning_guide()

        # "회사명:x:y" 형식 파싱
        comps = []
        if isinstance(competitors_raw, str):
            for item in competitors_raw.split(","):
                parts = item.strip().split(":")
                if len(parts) >= 3:
                    try:
                        comps.append({"name": parts[0].strip(), "x": float(parts[1]), "y": float(parts[2])})
                    except ValueError:
                        continue
        elif isinstance(competitors_raw, list):
            for item in competitors_raw:
                if isinstance(item, dict) and "name" in item:
                    comps.append({"name": item["name"], "x": float(item.get("x", 5)), "y": float(item.get("y", 5))})

        if not comps:
            return self._positioning_guide()

        # ASCII 2D 맵 (10x10 그리드)
        grid_size = 10
        grid = [["·" for _ in range(grid_size + 1)] for _ in range(grid_size + 1)]

        for i, c in enumerate(comps):
            gx = max(0, min(grid_size, int(c["x"])))
            gy = max(0, min(grid_size, int(c["y"])))
            marker = chr(65 + i) if i < 26 else str(i)
            grid[grid_size - gy][gx] = marker

        lines = [
            f"### 2D 포지셔닝 맵 (X: {x_axis}, Y: {y_axis})",
            "",
            f"  {y_axis} ↑",
        ]
        for row_idx, row in enumerate(grid):
            y_val = grid_size - row_idx
            prefix = f" {y_val:2d}|"
            lines.append(prefix + " ".join(row))
        lines.append("    " + "—" * (grid_size * 2 + 1))
        x_labels = "    " + "  ".join(str(i) for i in range(grid_size + 1))
        lines.append(x_labels)
        lines.append(f"    → {x_axis}")

        lines.append("\n### 범례")
        lines.append("| 기호 | 기업 | X좌표 | Y좌표 |")
        lines.append("|------|------|------|------|")
        for i, c in enumerate(comps):
            marker = chr(65 + i) if i < 26 else str(i)
            lines.append(f"| {marker} | {c['name']} | {c['x']:.1f} | {c['y']:.1f} |")

        # 전략적 인사이트
        if len(comps) >= 2:
            avg_x = sum(c["x"] for c in comps) / len(comps)
            avg_y = sum(c["y"] for c in comps) / len(comps)
            lines.extend([
                "",
                f"### 전략적 인사이트",
                f"- 경쟁 중심점: ({avg_x:.1f}, {avg_y:.1f})",
                f"- 차별화 기회: 중심점에서 먼 사분면이 블루오션 가능성",
                f"- 고{x_axis}·고{y_axis} 영역: 프리미엄 전략",
                f"- 저{x_axis}·고{y_axis} 영역: 가치 혁신 (블루오션)",
            ])
        return "\n".join(lines)

    def _positioning_guide(self) -> str:
        return "\n".join([
            "### 포지셔닝 맵을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            '| competitors | "회사:X:Y" 형식, 쉼표 구분 | "네이버:8:7,카카오:6:8,쿠팡:9:5" |',
            '| x_axis | X축 이름 | "가격" |',
            '| y_axis | Y축 이름 | "품질" |',
            "",
            "좌표는 0~10 범위입니다. 자사를 포함시켜 경쟁 포지션을 시각화하세요.",
        ])

    # ── Competitors: 경쟁사 비교표 ──────────────────────

    async def _competitor_table(self, p: dict) -> str:
        competitors_raw = p.get("competitors", "")
        if not competitors_raw:
            return "경쟁사 비교를 위해 competitors 파라미터에 경쟁사 목록을 입력하세요.\n(예: \"네이버,카카오,쿠팡\" 또는 positioning 형식)"

        names = []
        if isinstance(competitors_raw, str):
            for item in competitors_raw.split(","):
                name = item.strip().split(":")[0].strip()
                if name:
                    names.append(name)
        elif isinstance(competitors_raw, list):
            for item in competitors_raw:
                if isinstance(item, dict):
                    names.append(item.get("name", ""))
                else:
                    names.append(str(item))

        dimensions = [
            "시장 점유율", "제품 차별화", "가격 경쟁력",
            "기술력", "브랜드 인지도", "고객 만족도",
            "성장세", "재무 건전성",
        ]

        lines = [
            "### 경쟁사 다차원 비교 프레임워크",
            "",
            "아래 표에 각 기업별 점수(1~10)를 채워 비교하세요:",
            "",
            "| 차원 | " + " | ".join(names) + " |",
            "|------|" + "|".join(["------" for _ in names]) + "|",
        ]
        for dim in dimensions:
            cells = " | ".join(["_/10" for _ in names])
            lines.append(f"| {dim} | {cells} |")

        lines.extend([
            "",
            "### 비교 분석 가이드",
            "- **총점 합산**으로 전반적 경쟁력 순위 확인",
            "- **차원별 최고점** 기업 = 해당 영역 벤치마크",
            "- **자사 약점** = 경쟁사 최고점 대비 3점 이상 차이나는 차원",
            "- **전략 기회** = 모든 경쟁사가 낮은 점수를 보이는 차원",
        ])
        return "\n".join(lines)

    # ── Moat: 경쟁 우위 진단 ──────────────────────────────

    async def _moat_analysis(self, p: dict) -> str:
        moat_scores: dict[str, int] = {}
        for moat_key in _MOAT_TYPES:
            raw = p.get(moat_key, 0)
            try:
                moat_scores[moat_key] = max(0, min(10, int(raw))) if raw else 0
            except (ValueError, TypeError):
                moat_scores[moat_key] = 0

        has_scores = any(v > 0 for v in moat_scores.values())
        if not has_scores:
            return self._moat_guide()

        # 가중 점수 계산
        weighted_total = 0
        max_weighted = 0
        for key, info in _MOAT_TYPES.items():
            sc = moat_scores.get(key, 0)
            w = info["score_weight"]
            weighted_total += sc * w
            max_weighted += 10 * w

        moat_pct = weighted_total / max_weighted * 100 if max_weighted > 0 else 0

        if moat_pct >= 70:
            grade = "Wide Moat (넓은 해자)"
            desc = "강력하고 지속 가능한 경쟁 우위. 장기 독점적 지위 가능."
        elif moat_pct >= 50:
            grade = "Narrow Moat (좁은 해자)"
            desc = "유의미한 경쟁 우위가 있지만, 지속적 강화 필요."
        elif moat_pct >= 30:
            grade = "Developing Moat (형성 중)"
            desc = "경쟁 우위의 싹이 보임. 전략적 투자로 강화 가능."
        else:
            grade = "No Moat (해자 없음)"
            desc = "경쟁 우위가 약함. 가격 경쟁에 취약할 수 있음."

        lines = [
            f"### 경쟁 우위(Moat) 진단 — {grade}",
            "",
            "| Moat 유형 | 점수 | 가중치 | 가중점수 | 설명 |",
            "|----------|------|--------|---------|------|",
        ]
        for key, info in _MOAT_TYPES.items():
            sc = moat_scores.get(key, 0)
            w = info["score_weight"]
            ws = sc * w
            level = "●" * min(sc, 10) + "○" * (10 - min(sc, 10))
            lines.append(
                f"| {info['name']} | {sc}/10 | ×{w:.1f} | {ws:.1f} | {level} |"
            )

        lines.extend([
            "",
            f"**가중 총점: {weighted_total:.1f} / {max_weighted:.1f} ({moat_pct:.0f}%)**",
            f"**등급: {grade}**",
            f"**평가: {desc}**",
            "",
            "### Moat 강화 우선순위 (점수가 낮고 가중치가 높은 순)",
        ])

        # 개선 우선순위: (10 - 점수) × 가중치 = 개선 여지
        improvement = []
        for key, info in _MOAT_TYPES.items():
            sc = moat_scores.get(key, 0)
            gap = (10 - sc) * info["score_weight"]
            improvement.append((key, info, sc, gap))
        improvement.sort(key=lambda x: x[3], reverse=True)

        lines.append("| 순위 | Moat 유형 | 현재 점수 | 개선 여지 | 적용 사례 |")
        lines.append("|------|----------|---------|---------|---------|")
        for i, (key, info, sc, gap) in enumerate(improvement[:5], 1):
            lines.append(f"| {i} | {info['name']} | {sc}/10 | {gap:.1f} | {info['examples']} |")

        return "\n".join(lines)

    def _moat_guide(self) -> str:
        lines = [
            "### Moat 진단을 위해 필요한 입력값:",
            "",
            "각 Moat 유형을 0(없음)~10(최강) 척도로 평가합니다:",
            "",
            "| 파라미터 | 유형 | 설명 | 가중치 |",
            "|---------|------|------|--------|",
        ]
        for key, info in _MOAT_TYPES.items():
            lines.append(f"| {key} | {info['name']} | {info['desc']} | ×{info['score_weight']} |")
        lines.extend([
            "",
            "📌 **가중치**: 네트워크 효과(×1.5)와 역포지셔닝(×1.4)이 가장 강력한 해자입니다.",
            "   Pat Dorsey(Morningstar): \"해자가 없는 기업은 결국 평균으로 회귀합니다.\"",
        ])
        return "\n".join(lines)

    # ── Entry: 시장 진입 장벽 분석 ──────────────────────

    async def _entry_barrier(self, p: dict) -> str:
        barriers = {
            "capital": {"name": "자본 요구량", "desc": "초기 투자 규모"},
            "technology": {"name": "기술 장벽", "desc": "핵심 기술 난이도"},
            "regulation": {"name": "규제 장벽", "desc": "인허가·법률 요건"},
            "brand": {"name": "브랜드 장벽", "desc": "브랜드 인지도 필요성"},
            "distribution": {"name": "유통 장벽", "desc": "채널 접근 난이도"},
            "scale": {"name": "규모의 경제", "desc": "최소 효율 규모 요구"},
        }

        scores = {}
        for key in barriers:
            raw = p.get(key, 0)
            try:
                scores[key] = max(0, min(10, int(raw))) if raw else 0
            except (ValueError, TypeError):
                scores[key] = 0

        has_scores = any(v > 0 for v in scores.values())
        if not has_scores:
            lines = [
                "### 시장 진입 장벽 분석을 위해 필요한 입력값:",
                "",
                "| 파라미터 | 장벽 유형 | 설명 |",
                "|---------|---------|------|",
            ]
            for key, info in barriers.items():
                lines.append(f"| {key} | {info['name']} | {info['desc']} |")
            lines.append("\n각 항목을 0(없음)~10(극히 높음) 척도로 입력하세요.")
            return "\n".join(lines)

        total = sum(scores.values())
        max_total = len(barriers) * 10
        pct = total / max_total * 100

        if pct >= 70:
            grade = "매우 높음 (요새 시장)"
            implication = "진입 어렵지만, 진입 후 경쟁 보호 강함."
        elif pct >= 50:
            grade = "높음 (장벽 시장)"
            implication = "상당한 준비와 자원이 필요하지만, 진입 가치 있음."
        elif pct >= 30:
            grade = "중간 (선택적 진입)"
            implication = "차별화 전략 없이도 진입 가능하지만, 경쟁 치열."
        else:
            grade = "낮음 (자유 진입)"
            implication = "쉬운 진입이지만, 그만큼 경쟁자도 쉽게 진입."

        lines = [
            f"### 시장 진입 장벽 분석 — {grade}",
            "",
            "| 장벽 유형 | 점수 | 수준 |",
            "|---------|------|------|",
        ]
        for key, info in barriers.items():
            sc = scores.get(key, 0)
            bar = "█" * sc + "░" * (10 - sc)
            lines.append(f"| {info['name']} | [{bar}] {sc}/10 | {info['desc']} |")

        lines.extend([
            "",
            f"**종합 진입 장벽: {total}/{max_total} ({pct:.0f}%)**",
            f"**등급: {grade}**",
            f"**시사점: {implication}**",
        ])
        return "\n".join(lines)
