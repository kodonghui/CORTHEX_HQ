"""
비즈니스 모델 건강도 평가 도구 (Business Model Scorer)

Unit Economics 12개 핵심 지표로 사업의 건강 상태를 A+~F 등급으로 진단합니다.
"이 사업이 돈이 되는 구조인가"를 숫자로 증명합니다.

학술 근거:
  - Andreessen Horowitz, "16 Startup Metrics" (2024) — SaaS 지표 표준
  - David Skok, "SaaS Metrics 2.0" (Matrix Partners, 2023) — LTV/CAC 기준
  - OpenView Partners, "SaaS Benchmarks" (2024) — 단계별 벤치마크
  - Ash Maurya, "Running Lean" (2012) — Lean Canvas 진단
  - Alexander Osterwalder, "Business Model Generation" (2010) — BMC

사용 방법:
  - action="full"       : 전체 건강도 종합 (12지표 + 등급 + 처방)
  - action="unit"       : Unit Economics 핵심 4지표 (LTV, CAC, Payback, Margin)
  - action="saas"       : SaaS 8대 지표 (ARR, Churn, NRR, Quick Ratio 등)
  - action="lean_canvas": Lean Canvas 9블록 완성도 진단
  - action="benchmark"  : 업계 벤치마크 대비 성적표
  - action="diagnosis"  : 종합 진단 + 처방전

필요 환경변수: 없음
필요 라이브러리: 없음 (표준 라이브러리만 사용)
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.business_model_scorer")

# ─── SaaS 벤치마크 (OpenView, a16z, Bessemer 2024) ──────

_SAAS_BENCHMARKS: dict[str, dict] = {
    "ltv_cac_ratio": {
        "name": "LTV:CAC 비율",
        "unit": "배",
        "grades": {"A+": 5.0, "A": 4.0, "B": 3.0, "C": 2.0, "D": 1.5, "F": 0},
        "ideal": "≥ 3:1",
        "source": "David Skok, Matrix Partners (2023)",
    },
    "cac_payback_months": {
        "name": "CAC 회수 기간",
        "unit": "개월",
        "grades": {"A+": 6, "A": 9, "B": 12, "C": 18, "D": 24, "F": 999},
        "ideal": "≤ 12개월",
        "source": "a16z SaaS Benchmarks (2024)",
        "lower_is_better": True,
    },
    "gross_margin_pct": {
        "name": "매출총이익률",
        "unit": "%",
        "grades": {"A+": 80, "A": 70, "B": 60, "C": 50, "D": 40, "F": 0},
        "ideal": "≥ 70%",
        "source": "OpenView SaaS Benchmarks (2024)",
    },
    "monthly_churn_pct": {
        "name": "월간 이탈률",
        "unit": "%",
        "grades": {"A+": 1.0, "A": 2.0, "B": 3.0, "C": 5.0, "D": 7.0, "F": 100},
        "ideal": "≤ 2%",
        "source": "Bessemer Cloud Index (2024)",
        "lower_is_better": True,
    },
    "nrr_pct": {
        "name": "순매출유지율 (NRR)",
        "unit": "%",
        "grades": {"A+": 130, "A": 120, "B": 110, "C": 100, "D": 90, "F": 0},
        "ideal": "≥ 120%",
        "source": "Bessemer — Snowflake 158%, Datadog 130%",
    },
    "quick_ratio": {
        "name": "Quick Ratio",
        "unit": "배",
        "grades": {"A+": 6.0, "A": 4.0, "B": 3.0, "C": 2.0, "D": 1.5, "F": 0},
        "ideal": "≥ 4",
        "source": "Mamoon Hamid, Social Capital (2023)",
    },
    "magic_number": {
        "name": "Magic Number",
        "unit": "",
        "grades": {"A+": 1.5, "A": 1.0, "B": 0.75, "C": 0.5, "D": 0.25, "F": 0},
        "ideal": "≥ 0.75",
        "source": "Scale Venture Partners",
    },
    "burn_multiple": {
        "name": "Burn Multiple",
        "unit": "배",
        "grades": {"A+": 1.0, "A": 1.5, "B": 2.0, "C": 3.0, "D": 5.0, "F": 999},
        "ideal": "≤ 2x",
        "source": "David Sacks, Craft Ventures (2024)",
        "lower_is_better": True,
    },
}

# Unit Economics 4대 핵심 지표
_UNIT_METRICS = ["ltv_cac_ratio", "cac_payback_months", "gross_margin_pct", "monthly_churn_pct"]

# Lean Canvas 9블록
_LEAN_CANVAS_BLOCKS = [
    {"key": "problem", "name": "문제 (Problem)", "desc": "고객의 핵심 고통 3가지", "weight": 1.5},
    {"key": "solution", "name": "솔루션 (Solution)", "desc": "문제 해결 방법", "weight": 1.0},
    {"key": "uvp", "name": "고유 가치 제안 (UVP)", "desc": "경쟁사와 다른 단 하나의 이유", "weight": 1.5},
    {"key": "unfair_advantage", "name": "경쟁 우위 (Unfair Advantage)", "desc": "쉽게 따라할 수 없는 것", "weight": 1.3},
    {"key": "customer_segments", "name": "고객 세그먼트", "desc": "초기 타겟 고객 정의", "weight": 1.2},
    {"key": "channels", "name": "채널 (Channels)", "desc": "고객 도달 경로", "weight": 0.8},
    {"key": "revenue_streams", "name": "수익 구조", "desc": "어떻게 돈을 버는가", "weight": 1.3},
    {"key": "cost_structure", "name": "비용 구조", "desc": "주요 비용 항목", "weight": 1.0},
    {"key": "key_metrics", "name": "핵심 지표", "desc": "성공 측정 기준", "weight": 1.0},
]


class BusinessModelScorer(BaseTool):
    """비즈니스 모델 건강도 평가 — 12지표 A+~F 등급 진단."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_score,
            "unit": self._unit_economics,
            "saas": self._saas_metrics,
            "lean_canvas": self._lean_canvas,
            "benchmark": self._benchmark_compare,
            "diagnosis": self._diagnosis,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return (
            f"알 수 없는 action: {action}. "
            "full, unit, saas, lean_canvas, benchmark, diagnosis 중 하나를 사용하세요."
        )

    # ── 등급 산정 헬퍼 ──────────────────────────────────

    def _get_grade(self, metric_key: str, value: float) -> str:
        info = _SAAS_BENCHMARKS.get(metric_key)
        if not info:
            return "N/A"
        grades = info["grades"]
        lower_is_better = info.get("lower_is_better", False)

        if lower_is_better:
            for grade in ["A+", "A", "B", "C", "D"]:
                if value <= grades[grade]:
                    return grade
            return "F"
        else:
            for grade in ["A+", "A", "B", "C", "D"]:
                if value >= grades[grade]:
                    return grade
            return "F"

    def _grade_to_gpa(self, grade: str) -> float:
        return {"A+": 4.3, "A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0}.get(grade, 0)

    def _gpa_to_overall(self, gpa: float) -> str:
        if gpa >= 4.0: return "A+ (최우수)"
        if gpa >= 3.5: return "A (우수)"
        if gpa >= 3.0: return "B (양호)"
        if gpa >= 2.0: return "C (개선 필요)"
        if gpa >= 1.0: return "D (위험)"
        return "F (심각)"

    # ── Full: 전체 종합 ──────────────────────────────────

    async def _full_score(self, p: dict) -> str:
        unit = await self._unit_economics(p)
        saas = await self._saas_metrics(p)
        diag = await self._diagnosis(p)

        lines = [
            "# 📋 비즈니스 모델 건강도 종합 보고서",
            "",
            "## 1. Unit Economics 핵심 4지표",
            unit,
            "",
            "## 2. SaaS 8대 지표 성적표",
            saas,
            "",
            "## 3. 종합 진단 및 처방",
            diag,
            "",
            "---",
            "학술 참고: a16z (2024), David Skok (2023), OpenView Benchmarks (2024)",
        ]
        return "\n".join(lines)

    # ── Unit Economics 4대 핵심 ──────────────────────────

    async def _unit_economics(self, p: dict) -> str:
        # 입력 파싱
        arpu = float(p.get("arpu_monthly", 0))
        cac = float(p.get("cac", 0))
        churn = float(p.get("monthly_churn_pct", 0))
        gross_margin = float(p.get("gross_margin_pct", 0))
        currency = p.get("currency", "원")

        if arpu <= 0 or cac <= 0:
            return self._unit_guide()

        # LTV 계산 (Skok 공식)
        if churn <= 0:
            churn = 5.0  # 기본 5%
        ltv = arpu * (gross_margin / 100 if gross_margin > 0 else 0.7) / (churn / 100)
        ltv_cac = ltv / cac if cac > 0 else 0
        payback = cac / (arpu * (gross_margin / 100 if gross_margin > 0 else 0.7)) if arpu > 0 else 0

        # 등급
        g_ltv_cac = self._get_grade("ltv_cac_ratio", ltv_cac)
        g_payback = self._get_grade("cac_payback_months", payback)
        g_margin = self._get_grade("gross_margin_pct", gross_margin)
        g_churn = self._get_grade("monthly_churn_pct", churn)

        grades = [g_ltv_cac, g_payback, g_margin, g_churn]
        avg_gpa = sum(self._grade_to_gpa(g) for g in grades) / len(grades)
        overall = self._gpa_to_overall(avg_gpa)

        lines = [
            "### Unit Economics 핵심 4지표",
            "",
            f"**종합 등급: {overall} (GPA {avg_gpa:.1f}/4.3)**",
            "",
            "| 지표 | 값 | 등급 | 건강 기준 | 출처 |",
            "|------|-----|------|---------|------|",
            f"| LTV (고객 생애가치) | {ltv:,.0f}{currency} | — | — | 산출값 |",
            f"| CAC (고객 획득비용) | {cac:,.0f}{currency} | — | — | 입력값 |",
            f"| **LTV:CAC 비율** | **{ltv_cac:.1f}:1** | **{g_ltv_cac}** | ≥ 3:1 | David Skok |",
            f"| **CAC 회수 기간** | **{payback:.1f}개월** | **{g_payback}** | ≤ 12개월 | a16z |",
            f"| **매출총이익률** | **{gross_margin:.1f}%** | **{g_margin}** | ≥ 70% | OpenView |",
            f"| **월간 이탈률** | **{churn:.1f}%** | **{g_churn}** | ≤ 2% | Bessemer |",
            "",
            "### 산출 공식 (David Skok, SaaS Metrics 2.0)",
            f"- LTV = ARPU({arpu:,.0f}) × Gross Margin({gross_margin:.0f}%) ÷ Churn({churn:.1f}%) = {ltv:,.0f}{currency}",
            f"- LTV:CAC = {ltv:,.0f} ÷ {cac:,.0f} = {ltv_cac:.1f}:1",
            f"- CAC Payback = {cac:,.0f} ÷ ({arpu:,.0f} × {gross_margin:.0f}%) = {payback:.1f}개월",
        ]

        # 경고/권고
        if ltv_cac < 1:
            lines.append("\n⚠️ **위험**: LTV < CAC — 고객 1명 획득할수록 손해. 즉시 CAC 절감 또는 ARPU 인상 필요.")
        elif ltv_cac < 3:
            lines.append(f"\n⚠️ **주의**: LTV:CAC {ltv_cac:.1f}:1 — 건강 기준(3:1) 미달. {'CAC 절감' if cac > ltv * 0.5 else 'ARPU/Retention 개선'} 우선.")
        if payback > 18:
            lines.append(f"\n⚠️ **주의**: CAC 회수 {payback:.0f}개월 — 캐시 플로우 압박. 12개월 이내 회수 필요.")

        return "\n".join(lines)

    def _unit_guide(self) -> str:
        return "\n".join([
            "### Unit Economics 분석을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| arpu_monthly | 월 평균 객단가 (ARPU) | 29900 |",
            "| cac | 고객 획득 비용 (CAC) | 50000 |",
            "| monthly_churn_pct | 월간 이탈률 (%) | 3.0 |",
            "| gross_margin_pct | 매출총이익률 (%) | 70 |",
            "| currency | 통화 단위 | 원 |",
            "",
            "💡 **LTV:CAC ≥ 3:1**이 SaaS 건강의 최소 기준입니다 (a16z, 2024).",
        ])

    # ── SaaS 8대 지표 성적표 ────────────────────────────

    async def _saas_metrics(self, p: dict) -> str:
        results = []
        for key, info in _SAAS_BENCHMARKS.items():
            raw = p.get(key, 0)
            try:
                val = float(raw) if raw else 0
            except (ValueError, TypeError):
                val = 0
            if val > 0 or (info.get("lower_is_better") and raw):
                grade = self._get_grade(key, val)
                results.append((key, info, val, grade))

        if not results:
            return self._saas_guide()

        gpas = [self._grade_to_gpa(r[3]) for r in results]
        avg_gpa = sum(gpas) / len(gpas) if gpas else 0
        overall = self._gpa_to_overall(avg_gpa)

        lines = [
            f"### SaaS 지표 성적표 — {overall}",
            "",
            "| 지표 | 값 | 등급 | 기준 | 출처 |",
            "|------|-----|------|------|------|",
        ]
        for key, info, val, grade in results:
            emoji = {"A+": "🏆", "A": "✅", "B": "👍", "C": "⚠️", "D": "🔴", "F": "💀"}.get(grade, "")
            lines.append(
                f"| {info['name']} | {val:.1f}{info['unit']} | {emoji} {grade} | {info['ideal']} | {info['source'][:30]} |"
            )

        lines.extend([
            "",
            f"**종합 GPA: {avg_gpa:.1f}/4.3 → {overall}**",
            f"**평가 지표 수: {len(results)}/{len(_SAAS_BENCHMARKS)}**",
        ])

        # A+ 지표와 F 지표 하이라이트
        top = [r for r in results if r[3] in ("A+", "A")]
        weak = [r for r in results if r[3] in ("D", "F")]
        if top:
            lines.append(f"\n**강점**: {', '.join(r[1]['name'] for r in top)}")
        if weak:
            lines.append(f"**약점**: {', '.join(r[1]['name'] for r in weak)} — 즉시 개선 필요")

        return "\n".join(lines)

    def _saas_guide(self) -> str:
        lines = [
            "### SaaS 8대 지표를 위해 필요한 입력값:",
            "",
            "| 파라미터 | 지표 | 단위 | 건강 기준 |",
            "|---------|------|------|---------|",
        ]
        for key, info in _SAAS_BENCHMARKS.items():
            lines.append(f"| {key} | {info['name']} | {info['unit']} | {info['ideal']} |")
        lines.append("\n모든 값을 넣을 필요 없습니다. 알고 있는 값만 넣으면 해당 지표만 평가합니다.")
        return "\n".join(lines)

    # ── Lean Canvas 완성도 진단 ──────────────────────────

    async def _lean_canvas(self, p: dict) -> str:
        scores = []
        for block in _LEAN_CANVAS_BLOCKS:
            raw = p.get(block["key"], "")
            # 텍스트 입력의 구체성을 점수화 (0~10)
            if isinstance(raw, (int, float)):
                sc = max(0, min(10, int(raw)))
            elif isinstance(raw, str) and raw.strip():
                # 길이와 구체성 기반 자동 점수
                length = len(raw.strip())
                if length > 200:
                    sc = 10
                elif length > 100:
                    sc = 8
                elif length > 50:
                    sc = 6
                elif length > 20:
                    sc = 4
                else:
                    sc = 2
            else:
                sc = 0
            scores.append((block, sc))

        filled = sum(1 for _, sc in scores if sc > 0)
        if filled == 0:
            return self._lean_canvas_guide()

        total_weighted = sum(sc * b["weight"] for b, sc in scores)
        max_weighted = sum(10 * b["weight"] for b, _ in scores)
        pct = total_weighted / max_weighted * 100 if max_weighted > 0 else 0

        if pct >= 80:
            grade = "A (실행 가능)"
            advice = "캔버스가 충분히 구체적입니다. 가장 불확실한 가정부터 검증 시작하세요."
        elif pct >= 60:
            grade = "B (보완 필요)"
            advice = "핵심은 있지만 일부 블록이 약합니다. 빈 곳을 채우세요."
        elif pct >= 40:
            grade = "C (미완성)"
            advice = "주요 블록이 비어있습니다. 특히 Problem/UVP를 먼저 구체화하세요."
        else:
            grade = "D (초기 단계)"
            advice = "아직 캔버스가 초안 수준입니다. 9블록 모두 1줄이라도 채우세요."

        lines = [
            f"### Lean Canvas 완성도 — {grade}",
            "",
            "| 블록 | 점수 | 가중치 | 가중점수 | 상태 |",
            "|------|------|--------|---------|------|",
        ]
        for block, sc in scores:
            ws = sc * block["weight"]
            status = "✅ 구체적" if sc >= 7 else ("⚠️ 보완 필요" if sc >= 4 else ("📝 초안" if sc > 0 else "❌ 비어있음"))
            bar = "█" * sc + "░" * (10 - sc)
            lines.append(f"| {block['name']} | [{bar}] | ×{block['weight']} | {ws:.1f} | {status} |")

        lines.extend([
            "",
            f"**완성도: {pct:.0f}% ({filled}/9 블록 작성)**",
            f"**등급: {grade}**",
            f"**권고: {advice}**",
            "",
            "### Lean Canvas 검증 순서 (Ash Maurya, Running Lean)",
            "1. Problem → Customer Segments (문제가 진짜인지 확인)",
            "2. UVP → Solution (고유 가치가 명확한지)",
            "3. Revenue Streams → Cost Structure (수익 > 비용인지)",
            "4. Key Metrics (성공 측정 기준 설정)",
        ])
        return "\n".join(lines)

    def _lean_canvas_guide(self) -> str:
        lines = [
            "### Lean Canvas 9블록 진단을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 블록 | 설명 | 가중치 |",
            "|---------|------|------|--------|",
        ]
        for block in _LEAN_CANVAS_BLOCKS:
            lines.append(f"| {block['key']} | {block['name']} | {block['desc']} | ×{block['weight']} |")
        lines.extend([
            "",
            "각 블록에 텍스트(구체적일수록 높은 점수) 또는 0~10 점수를 입력하세요.",
            "💡 **Ash Maurya**: \"9블록 중 가장 위험한 가정 1개를 먼저 검증하라.\"",
        ])
        return "\n".join(lines)

    # ── Benchmark: 업계 비교 ─────────────────────────────

    async def _benchmark_compare(self, p: dict) -> str:
        stage = p.get("stage", "seed")

        # 단계별 벤치마크 (OpenView 2024 Expansion SaaS Benchmarks)
        stage_benchmarks = {
            "seed": {"arr": 0, "churn": 7.0, "ltv_cac": 1.5, "nrr": 95, "label": "시드 (Seed)"},
            "series_a": {"arr": 10, "churn": 5.0, "ltv_cac": 2.5, "nrr": 105, "label": "시리즈 A"},
            "series_b": {"arr": 50, "churn": 3.0, "ltv_cac": 3.5, "nrr": 115, "label": "시리즈 B"},
            "series_c": {"arr": 200, "churn": 2.0, "ltv_cac": 4.0, "nrr": 120, "label": "시리즈 C"},
            "growth": {"arr": 500, "churn": 1.5, "ltv_cac": 5.0, "nrr": 130, "label": "성장기 (Growth)"},
        }

        bm = stage_benchmarks.get(stage, stage_benchmarks["seed"])

        lines = [
            f"### 업계 벤치마크 — {bm['label']} 단계",
            "",
            "| 지표 | 업계 중간값 | 상위 25% | 설명 |",
            "|------|----------|---------|------|",
            f"| ARR (억원) | {bm['arr']}+ | {bm['arr'] * 2}+ | 연간 반복 매출 |",
            f"| 월 이탈률 | {bm['churn']}% | {bm['churn'] * 0.6:.1f}% | 낮을수록 좋음 |",
            f"| LTV:CAC | {bm['ltv_cac']:.1f}:1 | {bm['ltv_cac'] * 1.5:.1f}:1 | 높을수록 좋음 |",
            f"| NRR | {bm['nrr']}% | {bm['nrr'] + 15}% | 기존 고객 매출 유지+확장 |",
            "",
            "### 단계별 비교",
            "| 단계 | ARR 기준(억) | 이탈률 | LTV:CAC | NRR |",
            "|------|-----------|--------|---------|-----|",
        ]
        for key, data in stage_benchmarks.items():
            marker = " ← 현재" if key == stage else ""
            lines.append(f"| {data['label']}{marker} | {data['arr']}+ | {data['churn']}% | {data['ltv_cac']:.1f} | {data['nrr']}% |")

        lines.extend([
            "",
            "📌 출처: OpenView 2024 SaaS Expansion Benchmarks, Bessemer Cloud Index",
        ])
        return "\n".join(lines)

    # ── Diagnosis: 종합 진단 + 처방 ──────────────────────

    async def _diagnosis(self, p: dict) -> str:
        issues = []
        strengths = []

        # 지표별 진단
        for key, info in _SAAS_BENCHMARKS.items():
            raw = p.get(key, 0)
            try:
                val = float(raw) if raw else 0
            except (ValueError, TypeError):
                val = 0
            if val <= 0 and not info.get("lower_is_better"):
                continue
            grade = self._get_grade(key, val)
            if grade in ("D", "F"):
                issues.append({"name": info["name"], "value": val, "grade": grade, "ideal": info["ideal"]})
            elif grade in ("A+", "A"):
                strengths.append({"name": info["name"], "value": val, "grade": grade})

        if not issues and not strengths:
            return "진단을 위해 최소 1개 이상의 지표를 입력하세요. (예: ltv_cac_ratio=3.0)"

        lines = ["### 비즈니스 모델 종합 진단"]

        if strengths:
            lines.extend([
                "",
                "**강점 (유지/강화):**",
                "| 지표 | 현재값 | 등급 |",
                "|------|-------|------|",
            ])
            for s in strengths:
                lines.append(f"| {s['name']} | {s['value']:.1f} | {s['grade']} |")

        if issues:
            lines.extend([
                "",
                "**처방전 (즉시 개선 필요):**",
                "| 지표 | 현재값 | 등급 | 건강 기준 | 처방 |",
                "|------|-------|------|---------|------|",
            ])
            for iss in issues:
                prescription = self._get_prescription(iss["name"])
                lines.append(f"| {iss['name']} | {iss['value']:.1f} | {iss['grade']} | {iss['ideal']} | {prescription} |")

        if not issues:
            lines.append("\n✅ 모든 입력 지표가 건강 기준을 충족합니다.")

        return "\n".join(lines)

    def _get_prescription(self, metric_name: str) -> str:
        prescriptions = {
            "LTV:CAC 비율": "CAC 절감(채널 최적화) 또는 ARPU 인상(업셀/크로스셀)",
            "CAC 회수 기간": "자연 유입(SEO/콘텐츠) 비중 확대, 유료 채널 ROI 재점검",
            "매출총이익률": "AI API 비용 최적화, 프리미엄 플랜 도입",
            "월간 이탈률": "온보딩 개선, NPS 측정+조치, 핵심 기능 사용률 추적",
            "순매출유지율 (NRR)": "업셀 경로 설계, 사용량 기반 과금 도입",
            "Quick Ratio": "신규 획득 강화 + 이탈 감소 동시 추진",
            "Magic Number": "영업/마케팅 효율 점검, 전환율 개선",
            "Burn Multiple": "비용 구조 재점검, 불필요한 지출 삭감",
        }
        return prescriptions.get(metric_name, "전문가 상담 권장")
