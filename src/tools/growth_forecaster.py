"""
성장 예측 도구 (Growth Forecaster) — S-curve와 Bass 모델로 성장을 예측합니다.

Bass Diffusion Model + S-curve + 기술 채택 라이프사이클 + SaaS 성장 지표를 통해
"언제 폭발적 성장이 오고, 언제 둔화되는가"를 예측합니다.

학술 근거:
  - Frank Bass, "A New Product Growth Model" (1969) — 혁신 확산 모델
  - Everett Rogers, "Diffusion of Innovations" (1962) — 기술 채택 곡선
  - Pierre-Francois Verhulst (1838) — 로지스틱 S-curve
  - Christensen, "The Innovator's Dilemma" (1997) — S-curve 전환점
  - Neeraj Agrawal (Battery Ventures), "T2D3" (2015) — SaaS 성장 공식

사용 방법:
  - action="full"       : 전체 성장 분석 종합
  - action="bass"       : Bass Diffusion Model 시뮬레이션
  - action="scurve"     : S-curve 적합 + 변곡점 예측
  - action="adoption"   : 기술 채택 라이프사이클 진단
  - action="saas"       : SaaS 성장 지표 (T2D3, Rule of 40, Magic Number)
  - action="projection" : N년 성장 시나리오 전망

필요 환경변수: 없음
필요 라이브러리: 없음 (표준 라이브러리 math, random만 사용)
"""
from __future__ import annotations

import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.growth_forecaster")

# ─── Bass Diffusion 산업별 파라미터 (Bass, 1969 + 후속 연구) ─

_BASS_PARAMS: dict[str, dict] = {
    "SaaS_B2B": {"p": 0.01, "q": 0.25, "desc": "B2B SaaS (느린 혁신, 빠른 모방)"},
    "SaaS_B2C": {"p": 0.03, "q": 0.38, "desc": "B2C SaaS (빠른 확산)"},
    "Mobile_App": {"p": 0.05, "q": 0.50, "desc": "모바일 앱 (매우 빠른 확산)"},
    "EdTech": {"p": 0.02, "q": 0.30, "desc": "에드테크 (중간 속도)"},
    "FinTech": {"p": 0.01, "q": 0.28, "desc": "핀테크 (규제로 느린 시작)"},
    "AI_Service": {"p": 0.03, "q": 0.45, "desc": "AI 서비스 (빠른 확산, 높은 모방)"},
    "Enterprise_SW": {"p": 0.005, "q": 0.20, "desc": "엔터프라이즈 SW (매우 느린)"},
    "E-Commerce": {"p": 0.04, "q": 0.42, "desc": "이커머스 (빠른 확산)"},
    "Healthcare": {"p": 0.008, "q": 0.15, "desc": "헬스케어 (매우 느린, 규제)"},
    "Consumer_Electronics": {"p": 0.03, "q": 0.38, "desc": "가전 (Bass 원본 기반)"},
    "Platform": {"p": 0.02, "q": 0.35, "desc": "플랫폼 (네트워크 효과)"},
}

# 기술 채택 5단계 (Everett Rogers, 1962)
_ADOPTION_STAGES = [
    {"name": "혁신가 (Innovators)", "pct": 2.5, "cum_pct": 2.5, "trait": "기술 마니아, 리스크 감수"},
    {"name": "얼리어답터 (Early Adopters)", "pct": 13.5, "cum_pct": 16.0, "trait": "비전 있는 리더, 오피니언 리더"},
    {"name": "초기 다수 (Early Majority)", "pct": 34.0, "cum_pct": 50.0, "trait": "실용적, 검증 후 채택"},
    {"name": "후기 다수 (Late Majority)", "pct": 34.0, "cum_pct": 84.0, "trait": "보수적, 압력에 의한 채택"},
    {"name": "지각 수용자 (Laggards)", "pct": 16.0, "cum_pct": 100.0, "trait": "전통 고수, 마지막 채택"},
]

# SaaS 성장 벤치마크
_SAAS_BENCHMARKS = {
    "t2d3_years": [2, 3, 3, 3, 3],  # T2D3: Triple, Triple, Double, Double, Double
    "t2d3_labels": ["3배", "3배", "2배", "2배", "2배"],
    "rule_of_40_excellent": 60,
    "rule_of_40_good": 40,
    "rule_of_40_concern": 20,
    "magic_number_great": 1.0,
    "magic_number_good": 0.75,
}


class GrowthForecaster(BaseTool):
    """성장 예측 도구 — Bass Diffusion + S-curve + 기술 채택 + SaaS 성장 지표."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_forecast,
            "bass": self._bass_diffusion,
            "scurve": self._scurve_fit,
            "adoption": self._adoption_stage,
            "saas": self._saas_growth,
            "projection": self._projection,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return (
            f"알 수 없는 action: {action}. "
            "full, bass, scurve, adoption, saas, projection 중 하나를 사용하세요."
        )

    # ── Full ──────────────────────────────────────────────

    async def _full_forecast(self, p: dict) -> str:
        bass = await self._bass_diffusion(p)
        sc = await self._scurve_fit(p)
        adopt = await self._adoption_stage(p)
        saas = await self._saas_growth(p)

        lines = [
            "# 📈 성장 예측 종합 보고서",
            "", "## 1. Bass Diffusion Model", bass,
            "", "## 2. S-curve 분석", sc,
            "", "## 3. 기술 채택 라이프사이클", adopt,
            "", "## 4. SaaS 성장 지표", saas,
            "", "---",
            "학술 참고: Bass (1969), Rogers (1962), Verhulst (1838), T2D3 (2015)",
        ]
        return "\n".join(lines)

    # ── Bass Diffusion Model ──────────────────────────────

    async def _bass_diffusion(self, p: dict) -> str:
        market_size = int(p.get("market_size", 0))
        industry = p.get("industry", "SaaS_B2B")
        years = int(p.get("years", 10))

        if market_size <= 0:
            return self._bass_guide()

        params = _BASS_PARAMS.get(industry, _BASS_PARAMS["SaaS_B2B"])
        pp = float(p.get("p", params["p"]))  # 혁신 계수
        q = float(p.get("q", params["q"]))   # 모방 계수

        # Bass Model: f(t) = [p + q*F(t)] * [1 - F(t)]
        # F(t) = [1 - e^(-(p+q)*t)] / [1 + (q/p)*e^(-(p+q)*t)]
        adopters_cum = []
        adopters_new = []
        for t in range(years + 1):
            exp_term = math.exp(-(pp + q) * t)
            ft = (1 - exp_term) / (1 + (q / pp) * exp_term) if pp > 0 else 0
            cum = market_size * ft
            adopters_cum.append(cum)
            if t > 0:
                adopters_new.append(cum - adopters_cum[t - 1])
            else:
                adopters_new.append(0)

        # 피크 시점 (t* = ln(q/p) / (p+q))
        if q > pp and pp > 0:
            peak_time = math.log(q / pp) / (pp + q)
        else:
            peak_time = 0

        peak_year = max(1, round(peak_time))
        peak_adopters = adopters_new[min(peak_year, years)] if peak_year <= years else 0

        # 50% 침투 시점
        half_time = 0
        for t, cum in enumerate(adopters_cum):
            if cum >= market_size * 0.5:
                half_time = t
                break

        lines = [
            f"### Bass Diffusion Model — {params['desc']}",
            "",
            f"**파라미터:**",
            f"- 시장 규모(M): {market_size:,}",
            f"- 혁신 계수(p): {pp:.4f} (광고/마케팅 효과)",
            f"- 모방 계수(q): {q:.4f} (입소문/네트워크 효과)",
            f"- q/p 비율: {q/pp:.1f} ({'입소문 주도' if q/pp > 10 else '광고+입소문 혼합'})",
            "",
            "| 연도 | 신규 채택 | 누적 채택 | 침투율 |",
            "|------|---------|---------|--------|",
        ]

        for t in range(years + 1):
            cum = adopters_cum[t]
            new = adopters_new[t]
            pct = cum / market_size * 100 if market_size > 0 else 0
            marker = " ← 피크" if t == peak_year else ""
            lines.append(f"| {t}년 | {new:,.0f} | {cum:,.0f} | {pct:.1f}%{marker} |")

        # ASCII 성장 곡선
        max_new = max(adopters_new) if adopters_new else 1
        lines.extend(["", "### 신규 채택 곡선 (종 모양 = 정상)"])
        for t in range(years + 1):
            bar_len = int(adopters_new[t] / max_new * 40) if max_new > 0 else 0
            bar = "█" * bar_len
            lines.append(f"  {t:2d}년 |{bar}")

        lines.extend([
            "",
            f"📌 **피크 시점**: {peak_year}년차 (신규 {peak_adopters:,.0f}명/년)",
            f"📌 **50% 침투 시점**: {half_time}년차",
            f"📌 **Bass (1969)**: p는 광고 효과, q는 입소문 효과. q가 클수록 폭발적 성장 후 급감.",
        ])
        return "\n".join(lines)

    def _bass_guide(self) -> str:
        lines = [
            "### Bass Diffusion Model을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| market_size | 전체 잠재 시장 규모 (명) | 100000 |",
            "| industry | 산업 분류 | SaaS_B2B, AI_Service 등 |",
            "| years | 예측 기간 (년) | 10 |",
            "| p | 혁신 계수 (선택) | 0.01 |",
            "| q | 모방 계수 (선택) | 0.25 |",
            "",
            "### 산업별 기본 파라미터:",
            "| 산업 | p (혁신) | q (모방) | 특성 |",
            "|------|---------|---------|------|",
        ]
        for ind, data in _BASS_PARAMS.items():
            lines.append(f"| {ind} | {data['p']:.3f} | {data['q']:.2f} | {data['desc']} |")
        return "\n".join(lines)

    # ── S-curve: 로지스틱 성장 곡선 ────────────────────

    async def _scurve_fit(self, p: dict) -> str:
        current_users = int(p.get("current_users", 0))
        market_size = int(p.get("market_size", 0))
        growth_rate = float(p.get("growth_rate", 0))
        current_year = int(p.get("current_year", 1))
        years = int(p.get("years", 10))

        if current_users <= 0 or market_size <= 0:
            return "S-curve 분석: current_users(현재 사용자), market_size(시장 규모)를 입력하세요."

        if growth_rate <= 0:
            growth_rate = 0.5  # 기본 50%

        # 로지스틱 S-curve: N(t) = K / (1 + e^(-r*(t-t0)))
        # K = market_size, r = growth_rate
        # t0 계산: 현재 위치에서 역산
        penetration = current_users / market_size
        if 0 < penetration < 1:
            t0_offset = -math.log(market_size / current_users - 1) / growth_rate
        else:
            t0_offset = 0
        t0 = current_year - t0_offset

        # 변곡점 (S-curve 가속→감속 전환) = t0 (침투율 50%)
        inflection_year = round(t0)

        lines = [
            "### S-curve (로지스틱 성장 곡선)",
            "",
            f"**현재 위치:** {current_users:,}명 / {market_size:,}명 (침투율 {penetration:.1%})",
            f"**성장률(r):** {growth_rate:.2f}",
            f"**변곡점 예상:** {inflection_year}년차 (침투율 50% 시점)",
            "",
            "| 연도 | 예상 사용자 | 침투율 | 성장 단계 |",
            "|------|----------|--------|---------|",
        ]

        for t in range(current_year, current_year + years + 1):
            exp_val = -growth_rate * (t - t0)
            if exp_val > 500:
                users = 0
            elif exp_val < -500:
                users = market_size
            else:
                users = market_size / (1 + math.exp(exp_val))
            pct = users / market_size * 100
            if pct < 16:
                stage = "초기 (Innovators+Early Adopters)"
            elif pct < 50:
                stage = "가속 (Early Majority)"
            elif pct < 84:
                stage = "감속 (Late Majority)"
            else:
                stage = "포화 (Laggards)"
            marker = " ← 현재" if t == current_year else (" ← 변곡점" if t == inflection_year else "")
            lines.append(f"| {t}년차 | {users:,.0f} | {pct:.1f}% | {stage}{marker} |")

        # ASCII S-curve
        lines.extend(["", "### S-curve 시각화"])
        for t in range(current_year, current_year + years + 1):
            exp_val = -growth_rate * (t - t0)
            if exp_val > 500:
                users = 0
            elif exp_val < -500:
                users = market_size
            else:
                users = market_size / (1 + math.exp(exp_val))
            bar_len = int(users / market_size * 50)
            bar = "█" * bar_len + "░" * (50 - bar_len)
            marker = "◀" if t == current_year else " "
            lines.append(f"  {t:2d}년 [{bar}] {users/market_size:.0%} {marker}")

        lines.extend([
            "",
            "📌 **변곡점(Inflection Point)**: 침투율 50% = 성장 가속→감속 전환 시점",
            "📌 **Christensen**: 변곡점 전에 투자를 집중하라. 변곡점 후에는 이미 늦다.",
        ])
        return "\n".join(lines)

    # ── Adoption Stage: 현재 채택 단계 진단 ───────────────

    async def _adoption_stage(self, p: dict) -> str:
        penetration_pct = float(p.get("penetration_pct", 0))
        if penetration_pct <= 0:
            current_users = int(p.get("current_users", 0))
            market_size = int(p.get("market_size", 0))
            if current_users > 0 and market_size > 0:
                penetration_pct = current_users / market_size * 100
            else:
                return "채택 단계 진단: penetration_pct(침투율 %) 또는 current_users + market_size를 입력하세요."

        current_stage = None
        for stage in _ADOPTION_STAGES:
            if penetration_pct <= stage["cum_pct"]:
                current_stage = stage
                break
        if not current_stage:
            current_stage = _ADOPTION_STAGES[-1]

        lines = [
            "### 기술 채택 라이프사이클 (Rogers, 1962)",
            f"**현재 침투율: {penetration_pct:.1f}% → {current_stage['name']}**",
            "",
            "| 단계 | 비율 | 누적 | 특성 | 상태 |",
            "|------|------|------|------|------|",
        ]

        for stage in _ADOPTION_STAGES:
            if stage == current_stage:
                status = "◀ 현재"
            elif stage["cum_pct"] < penetration_pct:
                status = "✅ 완료"
            else:
                status = "⏳ 미래"
            lines.append(
                f"| {stage['name']} | {stage['pct']}% | {stage['cum_pct']}% | {stage['trait']} | {status} |"
            )

        # 캐즘(Chasm) 경고
        if penetration_pct < 16 and penetration_pct > 2.5:
            lines.extend([
                "",
                "⚠️ **캐즘(Chasm) 경고**: 현재 얼리어답터 → 초기 다수 전환 구간입니다.",
                "   Geoffrey Moore: \"캐즘을 넘으려면 단일 세그먼트에 집중하라 (Bowling Alley 전략).\"",
                "   - 캐즘 이전: 비전 판매 (이 기술이 미래다)",
                "   - 캐즘 이후: 실용 판매 (이 기능이 문제를 해결한다)",
            ])

        # ASCII 채택 곡선 (종 모양)
        lines.extend(["", "### 채택 곡선 시각화"])
        bell = [2, 5, 8, 12, 15, 18, 20, 22, 20, 18, 15, 12, 8, 5, 2]
        for i, height in enumerate(bell):
            pct_pos = (i + 1) / len(bell) * 100
            bar = "█" * height
            marker = " ◀◀◀ HERE" if abs(pct_pos - penetration_pct) < 100 / len(bell) else ""
            lines.append(f"  {bar}{marker}")

        return "\n".join(lines)

    # ── SaaS Growth: T2D3 + Rule of 40 ────────────────────

    async def _saas_growth(self, p: dict) -> str:
        arr = float(p.get("arr", 0))  # Annual Recurring Revenue (억원)
        growth_pct = float(p.get("growth_pct", 0))
        profit_margin_pct = float(p.get("profit_margin_pct", 0))
        new_mrr = float(p.get("new_mrr", 0))
        prev_quarter_spend = float(p.get("prev_quarter_spend", 0))
        currency = p.get("currency", "억원")

        if arr <= 0:
            return self._saas_guide()

        lines = [
            "### SaaS 성장 지표 분석",
            "",
        ]

        # T2D3 전망
        lines.append("#### T2D3 성장 전망 (Battery Ventures)")
        lines.append("T2D3 = ARR 100만달러 달성 후 Triple, Triple, Double, Double, Double\n")
        lines.append("| 연차 | 성장률 | 예상 ARR |")
        lines.append("|------|--------|---------|")
        t2d3_arr = arr
        t2d3_mults = [3, 3, 2, 2, 2]
        t2d3_labels = ["3배 (Triple)", "3배 (Triple)", "2배 (Double)", "2배 (Double)", "2배 (Double)"]
        for i, (mult, label) in enumerate(zip(t2d3_mults, t2d3_labels)):
            t2d3_arr *= mult
            lines.append(f"| {i+1}년차 | {label} | {t2d3_arr:,.1f} {currency} |")

        # Rule of 40
        if growth_pct > 0 or profit_margin_pct != 0:
            r40 = growth_pct + profit_margin_pct
            if r40 >= 60:
                r40_grade = "🏆 최상급 (Rule of 60+)"
            elif r40 >= 40:
                r40_grade = "✅ 건강 (Rule of 40 충족)"
            elif r40 >= 20:
                r40_grade = "⚠️ 주의 (개선 필요)"
            else:
                r40_grade = "🔴 위험 (긴급 조치 필요)"

            lines.extend([
                "",
                "#### Rule of 40 (Bain & Company)",
                f"- 성장률: {growth_pct:.0f}%",
                f"- 이익률: {profit_margin_pct:.0f}%",
                f"- **Rule of 40 점수: {r40:.0f}** → {r40_grade}",
                "",
                "Rule of 40 = 매출 성장률 + 이익률 ≥ 40이면 건강한 SaaS",
            ])

        # Magic Number
        if new_mrr > 0 and prev_quarter_spend > 0:
            magic = (new_mrr * 12 * 4) / prev_quarter_spend  # 연환산 / 전분기 지출
            if magic >= 1.0:
                mn_grade = "🟢 공격적 투자 가능"
            elif magic >= 0.75:
                mn_grade = "🟡 효율적 성장"
            else:
                mn_grade = "🔴 마케팅 효율 점검 필요"

            lines.extend([
                "",
                "#### Magic Number (Scale VP)",
                f"- 신규 MRR: {new_mrr:,.1f} {currency}",
                f"- 전분기 S&M 지출: {prev_quarter_spend:,.1f} {currency}",
                f"- **Magic Number: {magic:.2f}** → {mn_grade}",
            ])

        return "\n".join(lines)

    def _saas_guide(self) -> str:
        return "\n".join([
            "### SaaS 성장 지표 분석을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| arr | 연간 반복 매출 (ARR) | 10 (억원) |",
            "| growth_pct | 매출 성장률 (%) | 50 |",
            "| profit_margin_pct | 이익률 (%) | -10 (적자 허용) |",
            "| new_mrr | 신규 MRR | 0.5 (억원) |",
            "| prev_quarter_spend | 전분기 S&M 지출 | 2 (억원) |",
        ])

    # ── Projection: N년 성장 시나리오 ─────────────────────

    async def _projection(self, p: dict) -> str:
        current_value = float(p.get("current_value", 0))
        growth_rate = float(p.get("growth_rate", 0))
        years = int(p.get("years", 5))
        metric_name = p.get("metric_name", "매출")
        currency = p.get("currency", "억원")

        if current_value <= 0 or growth_rate <= 0:
            return "성장 전망: current_value(현재값), growth_rate(성장률 소수) 를 입력하세요."

        scenarios = {
            "보수적": growth_rate * 0.5,
            "기본": growth_rate,
            "낙관적": growth_rate * 1.5,
            "T2D3 (이상적)": None,  # Special handling
        }

        lines = [
            f"### {metric_name} {years}년 성장 전망",
            f"현재: {current_value:,.1f} {currency}, 기본 성장률: {growth_rate:.0%}/년",
            "",
        ]

        for sc_name, sc_rate in scenarios.items():
            lines.append(f"#### {sc_name}")
            lines.append(f"| 연도 | {metric_name} | 전년비 성장 |")
            lines.append("|------|--------|---------|")
            val = current_value
            for yr in range(1, years + 1):
                if sc_name == "T2D3 (이상적)":
                    mult = [3, 3, 2, 2, 2][min(yr - 1, 4)]
                    val = val * mult
                    gr = f"×{mult}"
                else:
                    val = val * (1 + sc_rate)
                    gr = f"+{sc_rate:.0%}"
                lines.append(f"| {yr}년차 | {val:,.1f} {currency} | {gr} |")
            lines.append("")

        return "\n".join(lines)
