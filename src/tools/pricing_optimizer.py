"""
가격 최적화 도구 (Pricing Optimizer) — 최적 가격을 과학적으로 산출합니다.

Van Westendorp PSM + Gabor-Granger + 가격 탄력성 + 수익 최적화 +
경쟁사 포지셔닝 + 마진 시뮬레이션으로
"얼마를 받아야 최적인가"를 정량적으로 결정합니다.

학술 근거:
  - Van Westendorp, "Price Sensitivity Meter" (1976) — 최적 가격 범위 산출
  - Gabor & Granger (1966) — 직접 가격 수용도 측정
  - Marshall, "Principles of Economics" (1890) — 가격 탄력성 이론
  - Phillips, "Pricing and Revenue Optimization" (2005) — 수익 최적화 모델
  - Simon & Fassnacht, "Price Management" (2019) — 디지털 시대 가격 전략
  - Patrick Campbell, "SaaS Pricing" (ProfitWell, 2024) — SaaS 가격 벤치마크
  - Madhavan Ramanujam, "Monetizing Innovation" (2016) — 가격 중심 제품 설계

사용 방법:
  - action="full"           : 전체 가격 분석 종합
  - action="psm"            : Van Westendorp 가격 민감도 측정
  - action="gabor_granger"  : Gabor-Granger 가격 수용도
  - action="elasticity"     : 가격 탄력성 시뮬레이션
  - action="optimize"       : 수익 최적화 가격 탐색
  - action="competitor"     : 경쟁사 가격 포지셔닝
  - action="margin"         : 가격별 마진 시뮬레이션
  - action="bundle"         : 번들/티어 가격 설계

필요 환경변수: 없음
필요 라이브러리: 없음 (표준 라이브러리만 사용)
"""
from __future__ import annotations

import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.pricing_optimizer")

# ─── 산업별 가격 탄력성 벤치마크 ───────────────────────

_ELASTICITY_REFS: dict[str, dict] = {
    "SaaS_B2B": {"elasticity": -1.2, "desc": "B2B SaaS (중간 탄력)"},
    "SaaS_B2C": {"elasticity": -1.8, "desc": "B2C SaaS (높은 탄력)"},
    "EdTech": {"elasticity": -1.5, "desc": "에드테크 (중~높은 탄력)"},
    "Premium_SaaS": {"elasticity": -0.8, "desc": "프리미엄 SaaS (낮은 탄력)"},
    "E-Commerce": {"elasticity": -2.0, "desc": "이커머스 (매우 높은 탄력)"},
    "FinTech": {"elasticity": -1.0, "desc": "핀테크 (낮은~중간 탄력)"},
    "Gaming": {"elasticity": -2.5, "desc": "게임 (매우 높은 탄력)"},
    "LegalTech": {"elasticity": -0.7, "desc": "리걸테크 (낮은 탄력)"},
    "Healthcare": {"elasticity": -0.5, "desc": "헬스케어 (매우 낮은 탄력)"},
    "Luxury": {"elasticity": -0.3, "desc": "럭셔리 (비탄력적)"},
    "Commodity": {"elasticity": -3.0, "desc": "범용 상품 (극히 탄력적)"},
    "Consulting": {"elasticity": -0.6, "desc": "컨설팅 (비탄력적)"},
}

# 심리적 가격 포인트 (Charm Pricing)
_PSYCHOLOGICAL_PRICES = [
    9900, 14900, 19900, 24900, 29900, 39900, 49900, 59900, 79900, 99900,
    149000, 199000, 249000, 299000, 399000, 499000, 990000,
]

# 티어 설계 비율 (Good-Better-Best)
_TIER_RATIOS: dict[str, dict] = {
    "standard": {"ratios": [1.0, 2.0, 3.5], "names": ["Basic", "Pro", "Enterprise"], "desc": "일반적 SaaS"},
    "value": {"ratios": [1.0, 1.5, 2.5], "names": ["Starter", "Growth", "Scale"], "desc": "가치 중심"},
    "premium": {"ratios": [1.0, 3.0, 7.0], "names": ["Free", "Pro", "Enterprise"], "desc": "프리미엄 전략"},
    "usage": {"ratios": [0, 1.0, 2.5], "names": ["Free Tier", "Pay-as-you-go", "Volume"], "desc": "사용량 기반"},
    "freemium": {"ratios": [0, 1.0, 3.0], "names": ["Free", "Premium", "Business"], "desc": "프리미엄(무료+유료)"},
}


class PricingOptimizer(BaseTool):
    """가격 최적화 도구 — PSM + 탄력성 + 마진 시뮬레이션 + 티어 설계."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_analysis,
            "psm": self._psm_analysis,
            "gabor_granger": self._gabor_granger,
            "elasticity": self._elasticity_sim,
            "optimize": self._revenue_optimization,
            "competitor": self._competitor_positioning,
            "margin": self._margin_simulation,
            "bundle": self._bundle_design,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return (
            f"알 수 없는 action: {action}. "
            "full, psm, gabor_granger, elasticity, optimize, competitor, margin, bundle 중 하나를 사용하세요."
        )

    # ── Full: 종합 ──────────────────────────────────────

    async def _full_analysis(self, p: dict) -> str:
        psm = await self._psm_analysis(p)
        gabor = await self._gabor_granger(p)
        elast = await self._elasticity_sim(p)
        optimize = await self._revenue_optimization(p)
        margin = await self._margin_simulation(p)
        bundle = await self._bundle_design(p)

        lines = [
            "# 💰 가격 최적화 종합 보고서",
            "",
            "## 1. 가격 민감도 측정 (PSM)",
            psm,
            "",
            "## 2. Gabor-Granger 가격 수용도",
            gabor,
            "",
            "## 3. 가격 탄력성 시뮬레이션",
            elast,
            "",
            "## 4. 수익 최적화",
            optimize,
            "",
            "## 5. 가격별 마진 시뮬레이션",
            margin,
            "",
            "## 6. 번들/티어 가격 설계",
            bundle,
            "",
            "---",
            "학술 참고: Van Westendorp (1976), Gabor & Granger (1966), Phillips (2005), ProfitWell (2024)",
        ]
        return "\n".join(lines)

    # ── PSM: Van Westendorp 가격 민감도 ────────────────

    async def _psm_analysis(self, p: dict) -> str:
        too_cheap = float(p.get("too_cheap", 0))
        cheap = float(p.get("cheap", 0))
        expensive = float(p.get("expensive", 0))
        too_expensive = float(p.get("too_expensive", 0))
        currency = p.get("currency", "원")

        if too_expensive <= 0:
            return self._psm_guide()

        # Van Westendorp 4개 교차점
        # OPP (Optimal Price Point): too_cheap ↔ too_expensive 교차
        # IDP (Indifference Price): cheap ↔ expensive 교차
        # PMC (Point of Marginal Cheapness): too_cheap ↔ expensive 교차
        # PME (Point of Marginal Expensiveness): cheap ↔ too_expensive 교차

        opp = (too_cheap + too_expensive) / 2  # 최적 가격점 근사
        idp = (cheap + expensive) / 2  # 무차별 가격점
        acceptable_low = max(too_cheap, cheap * 0.8)
        acceptable_high = min(too_expensive, expensive * 1.2)
        optimal_range_low = (cheap + too_cheap) / 2
        optimal_range_high = (expensive + too_expensive) / 2

        # 가장 가까운 심리적 가격 찾기
        nearest_psych = min(_PSYCHOLOGICAL_PRICES, key=lambda x: abs(x - opp))

        lines = [
            "### Van Westendorp 가격 민감도 측정 (PSM)",
            "",
            "**4개 가격 인식 포인트:**",
            f"- 너무 싸다 (품질 의심): {too_cheap:,.0f}{currency}",
            f"- 적당히 싸다 (좋은 거래): {cheap:,.0f}{currency}",
            f"- 비싸다 (고민): {expensive:,.0f}{currency}",
            f"- 너무 비싸다 (포기): {too_expensive:,.0f}{currency}",
            "",
            "**PSM 교차점 분석:**",
            "",
            "| 교차점 | 가격 | 의미 |",
            "|--------|------|------|",
            f"| OPP (최적 가격) | **{opp:,.0f}{currency}** | '너무 싼' 것도 '너무 비싼' 것도 아닌 균형점 |",
            f"| IDP (무차별 가격) | {idp:,.0f}{currency} | '싸다'와 '비싸다'가 같아지는 점 |",
            "",
            f"**수용 가격 범위: {acceptable_low:,.0f} ~ {acceptable_high:,.0f}{currency}**",
            f"**최적 가격대: {optimal_range_low:,.0f} ~ {optimal_range_high:,.0f}{currency}**",
            "",
            f"### 추천 가격: {nearest_psych:,.0f}{currency} (심리적 가격 적용)",
            "",
            "### PSM 시각화 (가격 스펙트럼)",
        ]

        # ASCII 가격 스펙트럼
        price_min = too_cheap * 0.8
        price_max = too_expensive * 1.2
        price_range = price_max - price_min
        width = 50

        def to_pos(val: float) -> int:
            return max(0, min(width, int((val - price_min) / price_range * width)))

        spectrum = [" "] * (width + 1)
        spectrum[to_pos(too_cheap)] = "◁"
        spectrum[to_pos(cheap)] = "["
        spectrum[to_pos(opp)] = "★"
        spectrum[to_pos(expensive)] = "]"
        spectrum[to_pos(too_expensive)] = "▷"

        lines.append("  " + "".join(spectrum))
        lines.append(f"  {'◁너무싸':>8s}{'[적당싸':^12s}{'★최적':^10s}{'비싸]':^12s}{'너무비싸▷':>8s}")

        lines.extend([
            "",
            f"📌 **Van Westendorp (1976)**: 소비자 인식 4개 교차점으로 최적 가격대를 산출하는 표준 기법",
            f"📌 **Charm Pricing**: {nearest_psych:,.0f}{currency} ({opp:,.0f}의 심리적 가격 변환)",
        ])
        return "\n".join(lines)

    def _psm_guide(self) -> str:
        return "\n".join([
            "### PSM 분석을 위해 필요한 입력값:",
            "",
            "소비자에게 아래 4가지 질문의 답변 중간값을 입력합니다:",
            "",
            "| 파라미터 | 질문 | 예시 |",
            "|---------|------|------|",
            "| too_cheap | 이 가격이면 품질이 의심된다 | 5000 |",
            "| cheap | 이 가격이면 좋은 거래다 | 15000 |",
            "| expensive | 이 가격이면 비싸지만 고려한다 | 35000 |",
            "| too_expensive | 이 가격이면 절대 안 산다 | 60000 |",
            "",
            "💡 설문 20~30명이면 유의미한 결과를 얻을 수 있습니다.",
        ])

    # ── Elasticity: 가격 탄력성 시뮬레이션 ────────────────

    async def _elasticity_sim(self, p: dict) -> str:
        current_price = float(p.get("current_price", 0))
        current_demand = float(p.get("current_demand", 0))
        industry = p.get("industry", "SaaS_B2B")
        currency = p.get("currency", "원")

        if current_price <= 0 or current_demand <= 0:
            return self._elasticity_guide()

        ref = _ELASTICITY_REFS.get(industry, _ELASTICITY_REFS["SaaS_B2B"])
        e = ref["elasticity"]

        # 가격 변동 시나리오 (±5%, ±10%, ±20%, ±30%)
        changes = [-30, -20, -10, -5, 0, 5, 10, 20, 30]

        lines = [
            f"### 가격 탄력성 시뮬레이션 — {ref['desc']}",
            f"(탄력성 계수: {e:.1f})",
            "",
            f"현재: 가격 {current_price:,.0f}{currency} × 수요 {current_demand:,.0f} = 매출 {current_price * current_demand:,.0f}{currency}",
            "",
            "| 가격 변동 | 새 가격 | 예상 수요 | 예상 매출 | 매출 변동 | 최적? |",
            "|---------|--------|---------|---------|---------|------|",
        ]

        base_revenue = current_price * current_demand
        best_revenue = base_revenue
        best_change = 0

        for chg in changes:
            new_price = current_price * (1 + chg / 100)
            # 수요 변화 = 가격 변화율 × 탄력성
            demand_change_pct = (chg / 100) * e
            new_demand = current_demand * (1 + demand_change_pct)
            new_demand = max(0, new_demand)
            new_revenue = new_price * new_demand
            rev_change = ((new_revenue / base_revenue) - 1) * 100 if base_revenue > 0 else 0

            if new_revenue > best_revenue:
                best_revenue = new_revenue
                best_change = chg

            marker = " ← 현재" if chg == 0 else (" ← 최적" if chg == best_change and chg != 0 else "")
            lines.append(
                f"| {chg:+d}% | {new_price:,.0f} | {new_demand:,.0f} | {new_revenue:,.0f} | {rev_change:+.1f}% | {marker} |"
            )

        lines.extend([
            "",
            f"### 분석 결과",
            f"- **현재 탄력성**: {e:.1f} ({ref['desc']})",
            f"  - |E| > 1: 탄력적 → 가격 인하가 매출 증가",
            f"  - |E| < 1: 비탄력적 → 가격 인상이 매출 증가",
            f"  - |E| = 1: 단위 탄력적 → 매출 변동 없음",
            "",
        ])
        if abs(e) > 1:
            lines.append(f"📌 **추천**: 탄력적 시장(|E|={abs(e):.1f})이므로 **가격 인하**가 매출 증대에 유리합니다.")
        else:
            lines.append(f"📌 **추천**: 비탄력적 시장(|E|={abs(e):.1f})이므로 **가격 인상**이 매출 증대에 유리합니다.")

        if best_change != 0:
            lines.append(f"📌 **최적 가격**: 현재 대비 {best_change:+d}%인 {current_price * (1 + best_change / 100):,.0f}{currency}")

        return "\n".join(lines)

    def _elasticity_guide(self) -> str:
        lines = [
            "### 가격 탄력성 시뮬레이션을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| current_price | 현재 가격 | 29900 |",
            "| current_demand | 현재 수요(월 고객 수) | 1000 |",
            "| industry | 산업 분류 | SaaS_B2B |",
            "",
            "### 산업별 가격 탄력성 벤치마크:",
            "| 산업 | 탄력성 | 해석 |",
            "|------|--------|------|",
        ]
        for ind, data in _ELASTICITY_REFS.items():
            lines.append(f"| {ind} | {data['elasticity']:.1f} | {data['desc']} |")
        return "\n".join(lines)

    # ── Competitor: 경쟁사 가격 포지셔닝 ──────────────────

    async def _competitor_positioning(self, p: dict) -> str:
        competitors_raw = p.get("competitors", "")
        our_price = float(p.get("our_price", 0))
        currency = p.get("currency", "원")

        if not competitors_raw or our_price <= 0:
            return "경쟁사 가격 포지셔닝: competitors=\"경쟁사1:가격1,경쟁사2:가격2\", our_price=29900 형식으로 입력하세요."

        comps = []
        if isinstance(competitors_raw, str):
            for item in competitors_raw.split(","):
                parts = item.strip().split(":")
                if len(parts) >= 2:
                    try:
                        comps.append({"name": parts[0].strip(), "price": float(parts[1])})
                    except ValueError:
                        continue

        if not comps:
            return "경쟁사 파싱 실패. \"회사명:가격\" 형식으로 입력하세요."

        comps.append({"name": "★ 자사", "price": our_price})
        comps.sort(key=lambda x: x["price"])

        avg_price = sum(c["price"] for c in comps) / len(comps)
        our_position = "시장 평균 대비 " + (
            f"{(our_price / avg_price - 1) * 100:+.0f}%" if avg_price > 0 else "N/A"
        )

        lines = [
            "### 경쟁사 가격 포지셔닝 맵",
            "",
            "| 순위 | 기업 | 가격 | 평균 대비 |",
            "|------|------|------|---------|",
        ]
        for i, c in enumerate(comps, 1):
            diff = (c["price"] / avg_price - 1) * 100 if avg_price > 0 else 0
            marker = " ★" if c["name"] == "★ 자사" else ""
            lines.append(f"| {i} | {c['name']}{marker} | {c['price']:,.0f}{currency} | {diff:+.0f}% |")

        # 가격 스펙트럼
        min_p = comps[0]["price"]
        max_p = comps[-1]["price"]
        width = 50
        price_range = max_p - min_p if max_p > min_p else 1

        lines.extend(["", "### 가격 스펙트럼"])
        for c in comps:
            pos = int((c["price"] - min_p) / price_range * width)
            bar = " " * pos + "●"
            label = f" {c['name']} ({c['price']:,.0f})"
            lines.append(f"  {bar}{label}")
        lines.append("  " + "─" * (width + 10))
        lines.append(f"  저가{'':^{width - 8}}고가")

        lines.extend([
            "",
            f"📌 **자사 위치**: {our_position}",
            f"📌 **시장 평균 가격**: {avg_price:,.0f}{currency}",
        ])
        return "\n".join(lines)

    # ── Margin: 가격별 마진 시뮬레이션 ────────────────────

    async def _margin_simulation(self, p: dict) -> str:
        prices = p.get("prices", "")
        variable_cost = float(p.get("variable_cost", 0))
        fixed_cost_monthly = float(p.get("fixed_cost_monthly", 0))
        expected_customers = int(p.get("expected_customers", 0))
        currency = p.get("currency", "원")

        if variable_cost <= 0 or expected_customers <= 0:
            return self._margin_guide()

        price_list = []
        if isinstance(prices, str) and prices:
            for item in prices.split(","):
                try:
                    price_list.append(float(item.strip()))
                except ValueError:
                    continue
        if not price_list:
            # 자동 가격 범위 생성
            base = variable_cost * 2
            price_list = [base * mult for mult in [0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]]

        lines = [
            "### 가격별 마진 시뮬레이션",
            f"(변동비: {variable_cost:,.0f}{currency}/건, 고정비: {fixed_cost_monthly:,.0f}{currency}/월, 예상 {expected_customers:,}명/월)",
            "",
            "| 가격 | 공헌이익 | GM% | 월매출 | 월이익 | 연이익 | BEP(명) |",
            "|------|---------|-----|--------|--------|--------|---------|",
        ]

        best_profit = float('-inf')
        best_price = 0

        for price in sorted(price_list):
            contribution = price - variable_cost
            gm = (contribution / price * 100) if price > 0 else 0
            monthly_rev = price * expected_customers
            monthly_profit = (contribution * expected_customers) - fixed_cost_monthly
            yearly_profit = monthly_profit * 12
            bep = math.ceil(fixed_cost_monthly / contribution) if contribution > 0 else float('inf')

            if monthly_profit > best_profit:
                best_profit = monthly_profit
                best_price = price

            status = "🏆" if price == best_price and monthly_profit > 0 else ("🟢" if monthly_profit > 0 else "🔴")
            bep_str = f"{bep:,}" if bep < float('inf') else "불가"
            lines.append(
                f"| {price:,.0f} | {contribution:,.0f} | {gm:.0f}% | {monthly_rev:,.0f} | {monthly_profit:,.0f} | {yearly_profit:,.0f} | {bep_str} | {status}"
            )

        nearest = min(_PSYCHOLOGICAL_PRICES, key=lambda x: abs(x - best_price))
        lines.extend([
            "",
            f"📌 **최고 수익 가격**: {best_price:,.0f}{currency} (월 이익 {best_profit:,.0f}{currency})",
            f"📌 **추천 심리적 가격**: {nearest:,.0f}{currency}",
        ])
        return "\n".join(lines)

    def _margin_guide(self) -> str:
        return "\n".join([
            "### 마진 시뮬레이션을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| variable_cost | 변동비 (1건당) | 5000 |",
            "| fixed_cost_monthly | 월 고정비 | 3000000 |",
            "| expected_customers | 예상 월 고객 수 | 200 |",
            '| prices | 시뮬레이션할 가격들 (쉼표 구분) | "19900,29900,39900,49900" |',
        ])

    # ── Gabor-Granger: 가격 수용도 ──────────────────────

    async def _gabor_granger(self, p: dict) -> str:
        """Gabor-Granger 직접 가격 수용도 분석 (Gabor & Granger, 1966).

        여러 가격점에서 구매 수용률 → 수익 곡선으로 최적 가격 도출.
        """
        prices_str = p.get("prices", "")
        acceptance_str = p.get("acceptance_rates", "")
        currency = p.get("currency", "원")

        if not prices_str or not acceptance_str:
            return self._gabor_guide()

        prices = [float(x.strip()) for x in str(prices_str).split(",")]
        acceptance = [
            float(x.strip()) / 100 if float(x.strip()) > 1 else float(x.strip())
            for x in str(acceptance_str).split(",")
        ]

        if len(prices) != len(acceptance):
            return "prices와 acceptance_rates의 개수가 일치해야 합니다."

        # Revenue = Price × Acceptance Rate
        revenues = [p_ * a for p_, a in zip(prices, acceptance)]
        max_idx = max(range(len(revenues)), key=lambda i: revenues[i])
        optimal_price = prices[max_idx]
        optimal_acc = acceptance[max_idx]
        max_rev = revenues[max_idx]

        # 구간별 탄력성
        elasticities: list[str] = []
        for i in range(1, len(prices)):
            pct_q = (acceptance[i] - acceptance[i - 1]) / acceptance[i - 1] if acceptance[i - 1] else 0
            pct_p = (prices[i] - prices[i - 1]) / prices[i - 1] if prices[i - 1] else 0
            if pct_p != 0:
                e = pct_q / pct_p
                etype = "탄력적" if abs(e) > 1 else "비탄력적"
                elasticities.append(
                    f"| {prices[i-1]:,.0f}→{prices[i]:,.0f} | {e:.2f} | {etype} |"
                )

        lines = [
            "### Gabor-Granger 가격 수용도 (1966)",
            "",
            "| 가격 | 수용률 | 기대 수익 | 최적? |",
            "|------|--------|---------|-------|",
        ]
        for i, (pr, ac, rv) in enumerate(zip(prices, acceptance, revenues)):
            marker = " ★" if i == max_idx else ""
            lines.append(f"| {pr:,.0f}{currency} | {ac*100:.0f}% | {rv:,.0f}{currency} | {marker} |")

        lines.extend([
            "",
            f"**최적 가격: {optimal_price:,.0f}{currency}** (수용률 {optimal_acc*100:.0f}%, 기대수익 {max_rev:,.0f}{currency})",
        ])

        if elasticities:
            lines.extend([
                "",
                "### 구간별 탄력성",
                "| 가격 구간 | 탄력성 | 유형 |",
                "|----------|--------|------|",
            ] + elasticities)

        nearest = min(_PSYCHOLOGICAL_PRICES, key=lambda x: abs(x - optimal_price))
        lines.extend([
            "",
            f"📌 **추천 심리적 가격**: {nearest:,.0f}{currency}",
        ])
        return "\n".join(lines)

    def _gabor_guide(self) -> str:
        return "\n".join([
            "### Gabor-Granger 분석을 위해 필요한 입력값:",
            "",
            "각 가격에 대해 \"이 가격에 구매하시겠습니까?\" 설문 결과를 입력합니다.",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            '| prices | 테스트할 가격들 (쉼표 구분) | "10000,20000,30000,40000,50000" |',
            '| acceptance_rates | 각 가격의 수용률 % (쉼표 구분) | "95,85,70,50,30" |',
            "",
            "💡 5~8개 가격점이 적절합니다. 수용률은 가격이 오를수록 낮아져야 합니다.",
        ])

    # ── Optimize: 수익 최적화 가격 탐색 ──────────────────

    async def _revenue_optimization(self, p: dict) -> str:
        """수익/이익 최적화 가격 탐색 (Phillips 2005).

        일정 탄력성 모델(Q = Q0 × (P/P0)^e)로 가격별 수요·수익·이익 시뮬레이션.
        """
        base_price = float(p.get("base_price", 0))
        base_demand = float(p.get("base_demand", 0))
        variable_cost = float(p.get("variable_cost", 0))
        fixed_cost = float(p.get("fixed_cost", 0))
        elasticity = float(p.get("elasticity", -1.5))
        currency = p.get("currency", "원")

        if base_price <= 0 or base_demand <= 0:
            return self._optimize_guide()

        # 가격 범위: 기본가의 50%~200%, 20단계
        steps = 20
        price_min = base_price * 0.5
        price_max = base_price * 2.0
        step_size = (price_max - price_min) / steps

        best_revenue_entry: dict[str, Any] = {}
        best_profit_entry: dict[str, Any] = {}
        max_rev = float("-inf")
        max_prof = float("-inf")
        bep_price = None
        table_rows: list[str] = []

        for i in range(steps + 1):
            price = price_min + step_size * i
            # 일정 탄력성 모델
            demand = base_demand * (price / base_price) ** elasticity
            demand = max(0, demand)
            revenue = price * demand
            total_cost = fixed_cost + variable_cost * demand
            profit = revenue - total_cost
            margin = profit / revenue if revenue > 0 else 0

            entry = {
                "price": round(price), "demand": round(demand),
                "revenue": round(revenue), "profit": round(profit),
                "margin": round(margin, 3),
            }

            if revenue > max_rev:
                max_rev = revenue
                best_revenue_entry = entry
            if profit > max_prof:
                max_prof = profit
                best_profit_entry = entry
            if bep_price is None and profit >= 0:
                bep_price = round(price)

            # 10% 간격으로 테이블에 추가
            if i % 2 == 0:
                marker = ""
                if entry["price"] == best_profit_entry.get("price"):
                    marker = " ★이익최대"
                elif entry["price"] == best_revenue_entry.get("price"):
                    marker = " ★매출최대"
                table_rows.append(
                    f"| {price:,.0f} | {demand:,.0f} | {revenue:,.0f} | {profit:,.0f} | {margin*100:.0f}% |{marker}"
                )

        lines = [
            f"### 수익 최적화 (Phillips 2005)",
            f"(기준가 {base_price:,.0f}{currency}, 수요 {base_demand:,.0f}, 탄력성 {elasticity:.1f})",
            "",
            "| 가격 | 예상 수요 | 매출 | 이익 | 마진 | 비고 |",
            "|------|---------|------|------|------|------|",
        ] + table_rows

        lines.extend([
            "",
            f"**매출 최대화 가격**: {best_revenue_entry.get('price', 0):,}{currency} "
            f"(매출 {best_revenue_entry.get('revenue', 0):,}{currency})",
            f"**이익 최대화 가격**: {best_profit_entry.get('price', 0):,}{currency} "
            f"(이익 {best_profit_entry.get('profit', 0):,}{currency})",
        ])
        if bep_price:
            lines.append(f"**손익분기 가격**: {bep_price:,}{currency}")

        # 전략 추천
        bp = best_profit_entry.get("price", base_price)
        if bp > base_price * 1.1:
            rec = f"현재({base_price:,}) 대비 이익최적({bp:,})이 높음 → 가격 인상 권장"
        elif bp < base_price * 0.9:
            rec = f"현재({base_price:,}) 대비 이익최적({bp:,})이 낮음 → 가격 인하+볼륨 전략 권장"
        else:
            rec = f"현재 가격({base_price:,})이 이익 최적 근처 → 현 가격 유지 권장"

        lines.extend(["", f"📌 **전략**: {rec}"])
        return "\n".join(lines)

    def _optimize_guide(self) -> str:
        return "\n".join([
            "### 수익 최적화를 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| base_price | 현재/기준 가격 | 30000 |",
            "| base_demand | 현재 수요 (월) | 1000 |",
            "| variable_cost | 변동비 (건당) | 10000 |",
            "| fixed_cost | 고정비 (월) | 5000000 |",
            "| elasticity | 가격 탄력성 (음수) | -1.5 |",
        ])

    # ── Bundle: 번들/티어 가격 설계 ──────────────────────

    async def _bundle_design(self, p: dict) -> str:
        base_price = float(p.get("base_price", 0))
        strategy = p.get("strategy", "standard")
        currency = p.get("currency", "원")

        if base_price <= 0:
            return self._bundle_guide()

        tier = _TIER_RATIOS.get(strategy, _TIER_RATIOS["standard"])

        lines = [
            f"### 티어/번들 가격 설계 — {tier['desc']}",
            "",
            f"기준 가격: {base_price:,.0f}{currency}",
            "",
            "| 티어 | 가격 | 배율 | 추천 기능 | 타겟 고객 |",
            "|------|------|------|---------|---------|",
        ]

        tier_targets = {
            0: ("최소 기능, 제한 사용량", "체험/평가 고객"),
            1: ("핵심 기능 전체", "일반 유료 고객"),
            2: ("전체 기능 + 우선 지원 + 커스텀", "파워 유저 / 기업"),
        }

        for i, (ratio, name) in enumerate(zip(tier["ratios"], tier["names"])):
            price = base_price * ratio
            target = tier_targets.get(i, ("", ""))
            # 심리적 가격 적용
            if price > 0:
                nearest = min(_PSYCHOLOGICAL_PRICES, key=lambda x: abs(x - price))
            else:
                nearest = 0
            lines.append(f"| {name} | {nearest:,.0f}{currency} | ×{ratio:.1f} | {target[0]} | {target[1]} |")

        # Good-Better-Best 원칙
        lines.extend([
            "",
            "### Good-Better-Best 가격 전략 원칙",
            "| 원칙 | 설명 |",
            "|------|------|",
            "| Anchor Effect | 최고가 티어가 중간 티어를 합리적으로 보이게 함 |",
            "| Decoy Effect | 3개 옵션 중 2번째가 가장 많이 선택됨 (70~80%) |",
            "| 10x Rule | 최고가 티어는 최저가의 3~7배가 적절 |",
            "| Feature Gating | 무료→유료 전환 트리거 기능을 명확히 |",
            "",
            "### 전략 유형별 비교:",
            "| 전략 | 비율 구조 | 적합한 경우 |",
            "|------|---------|-----------|",
        ])
        for key, data in _TIER_RATIOS.items():
            marker = " ← 현재" if key == strategy else ""
            ratios_str = " : ".join(f"×{r}" for r in data["ratios"])
            lines.append(f"| {data['desc']}{marker} | {ratios_str} | {' / '.join(data['names'])} |")

        lines.extend([
            "",
            "📌 ProfitWell(2024): \"3-티어 가격이 2-티어보다 ARPU 25% 높음\"",
            "📌 Madhavan Ramanujam: \"가격은 제품 설계 전에 결정하라\"",
        ])
        return "\n".join(lines)

    def _bundle_guide(self) -> str:
        lines = [
            "### 번들/티어 설계를 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| base_price | 기준(최저) 가격 | 29900 |",
            "| strategy | 티어 전략 | standard, value, premium, usage, freemium |",
            "",
            "### 지원되는 전략:",
        ]
        for key, data in _TIER_RATIOS.items():
            ratios_str = " : ".join(f"×{r}" for r in data["ratios"])
            lines.append(f"- **{key}**: {data['desc']} ({ratios_str})")
        return "\n".join(lines)
