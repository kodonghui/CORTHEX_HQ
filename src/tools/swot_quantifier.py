"""
SWOT 정량화 도구 (SWOT Quantifier) — 정성적 SWOT를 숫자로 바꿉니다.

가중 점수 SWOT + IFE/EFE 매트릭스 + TOWS 교차 전략 + 우선순위 평가로
"어떤 전략을 먼저 실행해야 하는가"를 정량적으로 결정합니다.

학술 근거:
  - Fred R. David, "Strategic Management" (2023) — IFE/EFE Matrix
  - Heinz Weihrich, "The TOWS Matrix" (1982) — SWOT 교차 전략
  - Barney, "Gaining and Sustaining Competitive Advantage" (2014) — VRIO Framework
  - IE Matrix (Internal-External Matrix) — 전략 방향 결정

사용 방법:
  - action="full"      : 전체 SWOT 종합 분석
  - action="score"     : 가중 점수 SWOT (항목별 중요도×등급)
  - action="ife_efe"   : IFE/EFE 매트릭스 산출
  - action="tows"      : TOWS 교차 전략 생성
  - action="priority"  : 전략 우선순위 평가
  - action="benchmark" : SWOT 벤치마크 비교

필요 환경변수: 없음
필요 라이브러리: 없음 (표준 라이브러리만 사용)
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.swot_quantifier")

# IFE/EFE 해석 기준 (Fred R. David)
_IFE_INTERPRETATION = {
    "strong": {"min": 3.0, "max": 4.0, "desc": "강한 내부 역량", "color": "🟢"},
    "average": {"min": 2.5, "max": 3.0, "desc": "평균 수준 내부 역량", "color": "🟡"},
    "weak": {"min": 1.0, "max": 2.5, "desc": "약한 내부 역량", "color": "🔴"},
}

_EFE_INTERPRETATION = {
    "responsive": {"min": 3.0, "max": 4.0, "desc": "외부 기회에 잘 대응", "color": "🟢"},
    "average": {"min": 2.5, "max": 3.0, "desc": "평균 수준 대응", "color": "🟡"},
    "poor": {"min": 1.0, "max": 2.5, "desc": "외부 위협에 취약", "color": "🔴"},
}

# IE Matrix 9-Cell 전략 방향
_IE_STRATEGIES = {
    "grow": {"positions": [(1,1),(1,2),(2,1)], "strategy": "성장/구축 (Grow & Build)", "actions": "시장 침투, 시장 개발, 제품 개발"},
    "hold": {"positions": [(1,3),(2,2),(3,1)], "strategy": "유지/보호 (Hold & Maintain)", "actions": "시장 침투, 제품 개발"},
    "harvest": {"positions": [(2,3),(3,2),(3,3)], "strategy": "수확/철수 (Harvest & Divest)", "actions": "비용 절감, 매각 검토"},
}


class SwotQuantifier(BaseTool):
    """SWOT 정량화 도구 — 가중 SWOT + IFE/EFE + TOWS + 우선순위."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_analysis,
            "score": self._weighted_swot,
            "ife_efe": self._ife_efe_matrix,
            "tows": self._tows_strategy,
            "priority": self._priority_eval,
            "benchmark": self._benchmark,
            "vrio": self._vrio_analysis,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return (
            f"알 수 없는 action: {action}. "
            "full, score, ife_efe, tows, priority, benchmark, vrio 중 하나를 사용하세요."
        )

    # ── 파싱 헬퍼 ──────────────────────────────────────

    def _parse_items(self, raw: Any) -> list[dict]:
        """'항목:중요도:등급' 형식 파싱. 예: '기술력:0.15:4,브랜드:0.10:3'"""
        items = []
        if isinstance(raw, str):
            for entry in raw.split(","):
                parts = entry.strip().split(":")
                if len(parts) >= 3:
                    try:
                        items.append({
                            "name": parts[0].strip(),
                            "weight": float(parts[1]),
                            "rating": int(parts[2]),
                        })
                    except (ValueError, IndexError):
                        continue
                elif len(parts) == 2:
                    try:
                        items.append({
                            "name": parts[0].strip(),
                            "weight": 0,
                            "rating": int(parts[1]),
                        })
                    except ValueError:
                        continue
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    items.append({
                        "name": item.get("name", ""),
                        "weight": float(item.get("weight", 0)),
                        "rating": int(item.get("rating", 3)),
                    })
        return items

    def _auto_weights(self, items: list[dict]) -> list[dict]:
        """가중치가 0이면 균등 배분."""
        total_w = sum(i["weight"] for i in items)
        if total_w <= 0 and items:
            equal_w = round(1.0 / len(items), 3)
            for item in items:
                item["weight"] = equal_w
        return items

    # ── Full ──────────────────────────────────────────────

    async def _full_analysis(self, p: dict) -> str:
        score = await self._weighted_swot(p)
        ife = await self._ife_efe_matrix(p)
        tows = await self._tows_strategy(p)
        prio = await self._priority_eval(p)
        vrio = await self._vrio_analysis(p)

        lines = [
            "# 🎯 SWOT 정량 분석 종합 보고서",
            "", "## 1. 가중 점수 SWOT", score,
            "", "## 2. IFE/EFE 매트릭스", ife,
            "", "## 3. TOWS 교차 전략", tows,
            "", "## 4. 전략 우선순위", prio,
            "", "## 5. VRIO 분석", vrio,
            "", "---",
            "학술 참고: David (2023), Weihrich TOWS (1982), Barney VRIO (2014)",
        ]
        return "\n".join(lines)

    # ── Weighted SWOT: 가중 점수 ──────────────────────────

    async def _weighted_swot(self, p: dict) -> str:
        strengths = self._auto_weights(self._parse_items(p.get("strengths", "")))
        weaknesses = self._auto_weights(self._parse_items(p.get("weaknesses", "")))
        opportunities = self._auto_weights(self._parse_items(p.get("opportunities", "")))
        threats = self._auto_weights(self._parse_items(p.get("threats", "")))

        all_items = strengths + weaknesses + opportunities + threats
        if not all_items:
            return self._swot_guide()

        def score_table(items: list[dict], category: str) -> list[str]:
            lines = [
                f"\n**{category}:**",
                "| 항목 | 중요도(W) | 등급(R) | 가중점수(W×R) |",
                "|------|---------|--------|------------|",
            ]
            total_ws = 0
            for item in items:
                ws = item["weight"] * item["rating"]
                total_ws += ws
                lines.append(f"| {item['name']} | {item['weight']:.2f} | {item['rating']} | {ws:.2f} |")
            lines.append(f"| **소계** | | | **{total_ws:.2f}** |")
            return lines

        lines = ["### 가중 점수 SWOT 분석"]
        if strengths:
            lines.extend(score_table(strengths, "강점 (Strengths)"))
        if weaknesses:
            lines.extend(score_table(weaknesses, "약점 (Weaknesses)"))
        if opportunities:
            lines.extend(score_table(opportunities, "기회 (Opportunities)"))
        if threats:
            lines.extend(score_table(threats, "위협 (Threats)"))

        # 종합 점수
        s_score = sum(i["weight"] * i["rating"] for i in strengths) if strengths else 0
        w_score = sum(i["weight"] * i["rating"] for i in weaknesses) if weaknesses else 0
        o_score = sum(i["weight"] * i["rating"] for i in opportunities) if opportunities else 0
        t_score = sum(i["weight"] * i["rating"] for i in threats) if threats else 0

        internal = s_score - w_score
        external = o_score - t_score

        lines.extend([
            "",
            "### 종합 SWOT 점수",
            f"- 강점 총점: {s_score:.2f} / 약점 총점: {w_score:.2f}",
            f"- **내부 순점수(S-W): {internal:+.2f}** {'(내부 우위)' if internal > 0 else '(내부 열위)'}",
            f"- 기회 총점: {o_score:.2f} / 위협 총점: {t_score:.2f}",
            f"- **외부 순점수(O-T): {external:+.2f}** {'(기회 우세)' if external > 0 else '(위협 우세)'}",
        ])

        # 전략 방향 추천
        if internal > 0 and external > 0:
            direction = "SO 전략 (공격적 성장) — 강점으로 기회를 활용"
        elif internal > 0 and external <= 0:
            direction = "ST 전략 (다각화) — 강점으로 위협을 방어"
        elif internal <= 0 and external > 0:
            direction = "WO 전략 (역량 보강) — 약점 보완 후 기회 활용"
        else:
            direction = "WT 전략 (방어적 축소) — 약점과 위협 동시 관리"

        lines.append(f"\n📌 **추천 전략 방향: {direction}**")
        return "\n".join(lines)

    def _swot_guide(self) -> str:
        return "\n".join([
            "### SWOT 분석을 위해 필요한 입력값:",
            "",
            "각 카테고리를 '항목:중요도:등급' 형식으로 입력 (쉼표 구분):",
            "",
            "| 파라미터 | 형식 | 예시 |",
            "|---------|------|------|",
            '| strengths | "항목:가중치:등급" | "기술력:0.20:4,팀역량:0.15:3" |',
            '| weaknesses | "항목:가중치:등급" | "자금부족:0.25:2,인지도:0.10:1" |',
            '| opportunities | "항목:가중치:등급" | "시장성장:0.30:4,규제완화:0.15:3" |',
            '| threats | "항목:가중치:등급" | "대기업진입:0.20:3,규제강화:0.15:2" |',
            "",
            "- **가중치(W)**: 0.00~1.00 (각 카테고리 내 합=1.0, 비우면 균등 배분)",
            "- **등급(R)**: 1~4 (1=매우 약함, 4=매우 강함)",
            "- 가중점수 = W × R (Fred R. David 방법론)",
        ])

    # ── IFE/EFE Matrix ──────────────────────────────────

    async def _ife_efe_matrix(self, p: dict) -> str:
        strengths = self._auto_weights(self._parse_items(p.get("strengths", "")))
        weaknesses = self._auto_weights(self._parse_items(p.get("weaknesses", "")))
        opportunities = self._auto_weights(self._parse_items(p.get("opportunities", "")))
        threats = self._auto_weights(self._parse_items(p.get("threats", "")))

        if not (strengths or weaknesses) and not (opportunities or threats):
            return "IFE/EFE 매트릭스: strengths, weaknesses, opportunities, threats를 입력하세요."

        lines = []

        # IFE (Internal Factor Evaluation)
        if strengths or weaknesses:
            ife_items = strengths + weaknesses
            ife_score = sum(i["weight"] * i["rating"] for i in ife_items)

            ife_interp = _IFE_INTERPRETATION["weak"]
            for key, interp in _IFE_INTERPRETATION.items():
                if interp["min"] <= ife_score <= interp["max"]:
                    ife_interp = interp
                    break
                if ife_score >= interp["min"]:
                    ife_interp = interp

            lines.extend([
                "### IFE (Internal Factor Evaluation) 매트릭스",
                f"**IFE 총점: {ife_score:.2f}/4.0 → {ife_interp['color']} {ife_interp['desc']}**",
                "",
                "| 내부 요인 | W | R | W×R | 유형 |",
                "|---------|---|---|-----|------|",
            ])
            for item in strengths:
                ws = item["weight"] * item["rating"]
                lines.append(f"| {item['name']} | {item['weight']:.2f} | {item['rating']} | {ws:.2f} | 강점 |")
            for item in weaknesses:
                ws = item["weight"] * item["rating"]
                lines.append(f"| {item['name']} | {item['weight']:.2f} | {item['rating']} | {ws:.2f} | 약점 |")
            lines.append(f"| **합계** | **1.00** | | **{ife_score:.2f}** | |")

        # EFE (External Factor Evaluation)
        if opportunities or threats:
            efe_items = opportunities + threats
            efe_score = sum(i["weight"] * i["rating"] for i in efe_items)

            efe_interp = _EFE_INTERPRETATION["poor"]
            for key, interp in _EFE_INTERPRETATION.items():
                if interp["min"] <= efe_score <= interp["max"]:
                    efe_interp = interp
                    break
                if efe_score >= interp["min"]:
                    efe_interp = interp

            lines.extend([
                "",
                "### EFE (External Factor Evaluation) 매트릭스",
                f"**EFE 총점: {efe_score:.2f}/4.0 → {efe_interp['color']} {efe_interp['desc']}**",
                "",
                "| 외부 요인 | W | R | W×R | 유형 |",
                "|---------|---|---|-----|------|",
            ])
            for item in opportunities:
                ws = item["weight"] * item["rating"]
                lines.append(f"| {item['name']} | {item['weight']:.2f} | {item['rating']} | {ws:.2f} | 기회 |")
            for item in threats:
                ws = item["weight"] * item["rating"]
                lines.append(f"| {item['name']} | {item['weight']:.2f} | {item['rating']} | {ws:.2f} | 위협 |")
            lines.append(f"| **합계** | **1.00** | | **{efe_score:.2f}** | |")

        # IE Matrix 포지션
        if (strengths or weaknesses) and (opportunities or threats):
            ife_score = sum(i["weight"] * i["rating"] for i in (strengths + weaknesses))
            efe_score = sum(i["weight"] * i["rating"] for i in (opportunities + threats))
            ie_row = 1 if ife_score >= 3.0 else (2 if ife_score >= 2.0 else 3)
            ie_col = 1 if efe_score >= 3.0 else (2 if efe_score >= 2.0 else 3)

            strategy = "성장"
            for key, data in _IE_STRATEGIES.items():
                if (ie_row, ie_col) in data["positions"]:
                    strategy = data["strategy"]
                    actions = data["actions"]
                    break

            lines.extend([
                "",
                f"### IE Matrix 포지션: ({ie_row},{ie_col}) → **{strategy}**",
                f"추천 행동: {actions}",
            ])

        return "\n".join(lines)

    # ── TOWS: 교차 전략 ──────────────────────────────────

    async def _tows_strategy(self, p: dict) -> str:
        strengths = self._parse_items(p.get("strengths", ""))
        weaknesses = self._parse_items(p.get("weaknesses", ""))
        opportunities = self._parse_items(p.get("opportunities", ""))
        threats = self._parse_items(p.get("threats", ""))

        if not (strengths and opportunities):
            return "TOWS 분석: 최소 strengths와 opportunities를 입력하세요."

        s_names = [i["name"] for i in strengths[:3]]
        w_names = [i["name"] for i in weaknesses[:3]]
        o_names = [i["name"] for i in opportunities[:3]]
        t_names = [i["name"] for i in threats[:3]]

        lines = [
            "### TOWS 교차 전략 매트릭스 (Weihrich, 1982)",
            "",
            f"| | **기회(O)** | **위협(T)** |",
            f"| | {', '.join(o_names)} | {', '.join(t_names)} |",
            f"|---|---|---|",
            f"| **강점(S)** | **SO 전략 (Maxi-Maxi)** | **ST 전략 (Maxi-Mini)** |",
            f"| {', '.join(s_names)} | 강점으로 기회 활용 | 강점으로 위협 방어 |",
            f"| **약점(W)** | **WO 전략 (Mini-Maxi)** | **WT 전략 (Mini-Mini)** |",
            f"| {', '.join(w_names)} | 약점 보완 후 기회 활용 | 약점·위협 동시 최소화 |",
            "",
            "### 구체적 전략 도출",
            "",
        ]

        # SO 전략
        if s_names and o_names:
            lines.append("**SO 전략 (공격적 성장):**")
            for s in s_names[:2]:
                for o in o_names[:2]:
                    lines.append(f"  - [{s}] × [{o}] → {s}을(를) 활용하여 {o} 기회를 극대화")
            lines.append("")

        # WO 전략
        if w_names and o_names:
            lines.append("**WO 전략 (역량 보강):**")
            for w in w_names[:2]:
                for o in o_names[:2]:
                    lines.append(f"  - [{w}] → [{o}] → {w}을(를) 보완하여 {o} 기회에 대비")
            lines.append("")

        # ST 전략
        if s_names and t_names:
            lines.append("**ST 전략 (다각화/방어):**")
            for s in s_names[:2]:
                for t in t_names[:2]:
                    lines.append(f"  - [{s}] ← [{t}] → {s}을(를) 활용하여 {t} 위협을 방어")
            lines.append("")

        # WT 전략
        if w_names and t_names:
            lines.append("**WT 전략 (수비적 축소):**")
            for w in w_names[:2]:
                for t in t_names[:2]:
                    lines.append(f"  - [{w}] + [{t}] → {w}과(와) {t} 리스크를 동시에 관리")

        return "\n".join(lines)

    # ── Priority: 전략 우선순위 ──────────────────────────

    async def _priority_eval(self, p: dict) -> str:
        strategies_raw = p.get("strategies", "")
        if not strategies_raw:
            return "전략 우선순위: strategies=\"전략:영향도:실현가능성:긴급성\" 형식으로 입력하세요."

        strategies = []
        if isinstance(strategies_raw, str):
            for entry in strategies_raw.split(","):
                parts = entry.strip().split(":")
                if len(parts) >= 4:
                    try:
                        strategies.append({
                            "name": parts[0].strip(),
                            "impact": int(parts[1]),
                            "feasibility": int(parts[2]),
                            "urgency": int(parts[3]),
                        })
                    except ValueError:
                        continue

        if not strategies:
            return "전략 파싱 실패. \"전략명:영향도(1~10):실현가능성(1~10):긴급성(1~10)\" 형식으로 입력하세요."

        # 가중 종합 점수 (영향도 40% + 실현가능성 35% + 긴급성 25%)
        for s in strategies:
            s["total"] = s["impact"] * 0.4 + s["feasibility"] * 0.35 + s["urgency"] * 0.25

        strategies.sort(key=lambda x: x["total"], reverse=True)

        lines = [
            "### 전략 우선순위 매트릭스",
            "(가중치: 영향도 40% + 실현가능성 35% + 긴급성 25%)",
            "",
            "| 순위 | 전략 | 영향도 | 실현가능성 | 긴급성 | 종합 | 실행 권고 |",
            "|------|------|--------|---------|--------|------|---------|",
        ]

        for i, s in enumerate(strategies, 1):
            if s["total"] >= 7:
                rec = "🟢 즉시 실행"
            elif s["total"] >= 5:
                rec = "🟡 계획 수립"
            else:
                rec = "🔴 보류/재검토"
            bar = "█" * int(s["total"]) + "░" * (10 - int(s["total"]))
            lines.append(
                f"| {i} | {s['name']} | {s['impact']}/10 | {s['feasibility']}/10 | {s['urgency']}/10 | [{bar}] {s['total']:.1f} | {rec} |"
            )

        return "\n".join(lines)

    # ── Benchmark: 비교 ──────────────────────────────────

    async def _benchmark(self, p: dict) -> str:
        return "\n".join([
            "### SWOT 분석 벤치마크 가이드",
            "",
            "**IFE/EFE 점수 해석 기준 (Fred R. David):**",
            "",
            "| 점수 범위 | IFE 해석 | EFE 해석 |",
            "|---------|---------|---------|",
            "| 3.0~4.0 | 🟢 강한 내부 역량 | 🟢 기회에 잘 대응 |",
            "| 2.5~3.0 | 🟡 평균 수준 | 🟡 평균 수준 대응 |",
            "| 1.0~2.5 | 🔴 약한 내부 역량 | 🔴 위협에 취약 |",
            "",
            "**등급(Rating) 부여 기준:**",
            "| 등급 | 강점/기회 의미 | 약점/위협 의미 |",
            "|------|-------------|-------------|",
            "| 4 | 주요 강점/핵심 기회 | 약한 약점/낮은 위협 |",
            "| 3 | 보통 강점/보통 기회 | 보통 약점/보통 위협 |",
            "| 2 | 약한 강점/작은 기회 | 심각한 약점/높은 위협 |",
            "| 1 | 미미한 강점/미미한 기회 | 치명적 약점/극심한 위협 |",
            "",
            "📌 **핵심**: 가중치(W) 합계는 카테고리별로 1.0이어야 합니다.",
            "📌 **TOWS**: SO 전략이 최우선, WT 전략은 최후의 수단입니다.",
        ])

    # ── VRIO: 자원 기반 경쟁우위 분석 ─────────────────────

    async def _vrio_analysis(self, p: dict) -> str:
        """VRIO 분석 — Barney (2014) 자원기반관점(RBV) 프레임워크.

        VRIO = Value(가치) × Rarity(희소성) × Imitability(모방불가성) × Organization(조직역량).
        각 자원의 경쟁우위 유형을 V×R×I×O 곱으로 정량 판별합니다.
        """
        resources_raw = p.get("resources", "")
        if not resources_raw:
            return self._vrio_guide()

        # 파싱: "자원명:V:R:I:O" 형식 (각 1~5)
        resources: list[dict] = []
        if isinstance(resources_raw, str):
            for entry in resources_raw.split(","):
                parts = entry.strip().split(":")
                if len(parts) >= 5:
                    try:
                        resources.append({
                            "name": parts[0].strip(),
                            "V": int(parts[1]),
                            "R": int(parts[2]),
                            "I": int(parts[3]),
                            "O": int(parts[4]),
                        })
                    except (ValueError, IndexError):
                        continue
        elif isinstance(resources_raw, list):
            for item in resources_raw:
                if isinstance(item, dict):
                    resources.append({
                        "name": item.get("name", ""),
                        "V": int(item.get("V", 1)),
                        "R": int(item.get("R", 1)),
                        "I": int(item.get("I", 1)),
                        "O": int(item.get("O", 1)),
                    })

        if not resources:
            return self._vrio_guide()

        def _classify(v: int, r: int, i: int, o: int) -> tuple[str, str]:
            """V×R×I×O 곱 및 패턴으로 경쟁우위 유형 분류.

            Barney (2014) 분류 기준:
            - V 낮으면 → 경쟁 열위
            - V만 높으면 → 경쟁 균형
            - V+R 높고 I 낮으면 → 일시적 우위
            - V+R+I 높고 O 낮으면 → 미활용 잠재력
            - 모두 높으면 → 지속적 경쟁우위
            """
            product = v * r * i * o
            if v <= 2:
                return "경쟁 열위 (Competitive Disadvantage)", "🔴"
            if r <= 2:
                return "경쟁 균형 (Competitive Parity)", "🟡"
            if i <= 2:
                return "일시적 우위 (Temporary Advantage)", "🔵"
            if o <= 2:
                return "미활용 잠재력 (Unused Potential)", "🟠"
            # V, R, I, O 모두 3 이상 + 곱이 충분히 높으면 지속적 우위
            if product > 256:
                return "지속적 경쟁우위 (Sustained Competitive Advantage)", "🟢"
            if product > 100:
                return "미활용 잠재력 (Unused Potential)", "🟠"
            return "일시적 우위 (Temporary Advantage)", "🔵"

        # 분석 결과 테이블
        lines = [
            "### VRIO 분석 — 자원기반 경쟁우위 (Barney, 2014)",
            "",
            "| 자원/역량 | V(가치) | R(희소성) | I(모방불가) | O(조직역량) | V×R×I×O | 경쟁우위 유형 |",
            "|---------|--------|---------|----------|----------|---------|-----------|",
        ]

        advantage_counts: dict[str, int] = {}
        for res in resources:
            product = res["V"] * res["R"] * res["I"] * res["O"]
            adv_type, icon = _classify(res["V"], res["R"], res["I"], res["O"])
            advantage_counts[adv_type] = advantage_counts.get(adv_type, 0) + 1
            lines.append(
                f"| {res['name']} | {res['V']}/5 | {res['R']}/5 | {res['I']}/5 | "
                f"{res['O']}/5 | {product} | {icon} {adv_type} |"
            )

        # 요약 통계
        total = len(resources)
        sustained = advantage_counts.get("지속적 경쟁우위 (Sustained Competitive Advantage)", 0)
        unused = advantage_counts.get("미활용 잠재력 (Unused Potential)", 0)
        temporary = advantage_counts.get("일시적 우위 (Temporary Advantage)", 0)
        parity = advantage_counts.get("경쟁 균형 (Competitive Parity)", 0)
        disadvantage = advantage_counts.get("경쟁 열위 (Competitive Disadvantage)", 0)

        lines.extend([
            "",
            "### VRIO 분포 요약",
            f"| 유형 | 개수 | 비율 | 시각화 |",
            f"|------|------|------|--------|",
            f"| 🟢 지속적 경쟁우위 | {sustained} | {sustained/total:.0%} | {'█' * sustained}{'░' * (total - sustained)} |",
            f"| 🟠 미활용 잠재력 | {unused} | {unused/total:.0%} | {'█' * unused}{'░' * (total - unused)} |",
            f"| 🔵 일시적 우위 | {temporary} | {temporary/total:.0%} | {'█' * temporary}{'░' * (total - temporary)} |",
            f"| 🟡 경쟁 균형 | {parity} | {parity/total:.0%} | {'█' * parity}{'░' * (total - parity)} |",
            f"| 🔴 경쟁 열위 | {disadvantage} | {disadvantage/total:.0%} | {'█' * disadvantage}{'░' * (total - disadvantage)} |",
            "",
            "### VRIO 전략 권고",
        ])

        # 전략 권고
        if sustained > 0:
            lines.append(f"- **🟢 지속적 경쟁우위 자원({sustained}개)**: 핵심 역량으로 보호·강화. 전략의 중심축으로 활용")
        if unused > 0:
            lines.append(f"- **🟠 미활용 잠재력({unused}개)**: 조직 체계(O)를 보강하면 지속적 우위로 전환 가능. 우선 투자 대상")
        if temporary > 0:
            lines.append(f"- **🔵 일시적 우위({temporary}개)**: 모방 장벽(I) 구축 시급. 특허, 네트워크 효과, 전환비용 등 검토")
        if parity > 0:
            lines.append(f"- **🟡 경쟁 균형({parity}개)**: 차별화 요소 개발 또는 효율성으로 비용 우위 확보")
        if disadvantage > 0:
            lines.append(f"- **🔴 경쟁 열위({disadvantage}개)**: 아웃소싱 또는 파트너십으로 보완. 내재화 ROI 재검토")

        lines.extend([
            "",
            "📌 **VRIO 핵심 원리** (Barney, 2014):",
            "   자원이 경쟁우위를 만들려면 4가지가 **모두** 충족되어야 합니다.",
            "   하나라도 부족하면 우위는 일시적이거나 존재하지 않습니다.",
        ])
        return "\n".join(lines)

    def _vrio_guide(self) -> str:
        return "\n".join([
            "### VRIO 분석을 위해 필요한 입력값:",
            "",
            "각 자원/역량을 '자원명:V:R:I:O' 형식으로 입력 (쉼표 구분):",
            "",
            "| 파라미터 | 형식 | 예시 |",
            "|---------|------|------|",
            '| resources | "자원명:V:R:I:O" | "AI기술:5:4:4:3,브랜드:4:3:2:4,특허:5:5:5:3" |',
            "",
            "**VRIO 축 (각 1~5점):**",
            "- **V (Value, 가치)**: 이 자원이 외부 기회를 활용하거나 위협을 방어하는가?",
            "- **R (Rarity, 희소성)**: 소수의 경쟁자만 보유하고 있는가?",
            "- **I (Imitability, 모방불가성)**: 경쟁자가 모방하기 어려운가? (비용/시간)",
            "- **O (Organization, 조직역량)**: 이 자원을 충분히 활용할 조직 체계가 있는가?",
            "",
            "**경쟁우위 판별 기준 (Barney, 2014):**",
            "| V | R | I | O | 경쟁우위 유형 |",
            "|---|---|---|---|-----------|",
            "| 높 | 높 | 높 | 높 | 🟢 지속적 경쟁우위 |",
            "| 높 | 높 | 높 | 낮 | 🟠 미활용 잠재력 |",
            "| 높 | 높 | 낮 | — | 🔵 일시적 우위 |",
            "| 높 | 낮 | — | — | 🟡 경쟁 균형 |",
            "| 낮 | — | — | — | 🔴 경쟁 열위 |",
        ])
