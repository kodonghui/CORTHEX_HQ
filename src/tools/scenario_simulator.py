"""
시나리오 시뮬레이터 (Scenario Simulator) — 불확실한 미래를 확률로 예측합니다.

Monte Carlo 시뮬레이션 10,000회 + 3-시나리오 분석 + 민감도 분석으로
"최악의 경우에도 견딜 수 있는가"를 정량적으로 검증합니다.

학술 근거:
  - Monte Carlo Method (Metropolis & Ulam, 1949) — 확률적 시뮬레이션 기법
  - Nassim Taleb, "The Black Swan" (2007) — 극단값(Fat Tail) 리스크
  - McKinsey, "Strategy Under Uncertainty" (2024) — 3-Scenario 프레임워크
  - Tornado Diagram (What-If Analysis) — 민감도 분석의 표준 시각화

사용 방법:
  - action="full"         : 전체 시뮬레이션 종합
  - action="monte_carlo"  : Monte Carlo 10,000회 시뮬레이션
  - action="three_scenario": 보수/기본/낙관 3-시나리오
  - action="sensitivity"  : 토네이도 다이어그램 (민감도)
  - action="breakeven"    : 손익분기점 분석

필요 환경변수: 없음
필요 라이브러리: 없음 (random 표준 라이브러리 사용)
"""
from __future__ import annotations

import logging
import math
import random
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.scenario_simulator")


class ScenarioSimulator(BaseTool):
    """시나리오 시뮬레이터 — Monte Carlo + 3-Scenario + 민감도 분석."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_simulation,
            "monte_carlo": self._monte_carlo,
            "three_scenario": self._three_scenario,
            "sensitivity": self._sensitivity,
            "breakeven": self._breakeven,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return (
            f"알 수 없는 action: {action}. "
            "full, monte_carlo, three_scenario, sensitivity, breakeven 중 하나를 사용하세요."
        )

    # ── Full: 전체 종합 ──────────────────────────────────

    async def _full_simulation(self, p: dict) -> str:
        mc = await self._monte_carlo(p)
        ts = await self._three_scenario(p)
        sens = await self._sensitivity(p)
        be = await self._breakeven(p)

        lines = [
            "# 🎲 시나리오 시뮬레이션 종합 보고서",
            "",
            "## 1. Monte Carlo 시뮬레이션 (10,000회)",
            mc,
            "",
            "## 2. 3-시나리오 분석",
            ts,
            "",
            "## 3. 민감도 분석 (토네이도 다이어그램)",
            sens,
            "",
            "## 4. 손익분기점 분석",
            be,
            "",
            "---",
            "학술 참고: Metropolis & Ulam (1949), McKinsey Strategy (2024), Taleb (2007)",
        ]
        return "\n".join(lines)

    # ── Monte Carlo: 10,000회 시뮬레이션 ──────────────────

    @staticmethod
    def _beta_params(low: float, high: float, mode: float) -> tuple[float, float]:
        """min/max/mode에서 Beta 분포의 alpha/beta 파라미터를 도출.

        PERT 방식 (Malcolm et al., 1959): mode를 기반으로 평균을 추정한 뒤
        alpha, beta를 역산. lambda=4(표준 PERT 가중치) 사용.
        """
        if high <= low:
            return 2.0, 2.0  # 퇴화 방지
        # PERT 평균: (low + lambda*mode + high) / (lambda+2)
        lam = 4.0
        mean = (low + lam * mode + high) / (lam + 2)
        # 평균을 [0,1] 범위로 정규화
        mu = (mean - low) / (high - low)
        mu = max(0.01, min(0.99, mu))  # 경계값 보호
        # Method of moments: alpha + beta 를 결정하는 스케일
        # 분산이 작을수록 alpha+beta가 커짐. PERT에서는 (high-low)^2/36 사용
        variance = ((high - low) / 6) ** 2
        var_norm = variance / ((high - low) ** 2) if high > low else 0.04
        var_norm = max(0.001, min(0.24, var_norm))  # Beta 분포 유효 범위
        alpha = mu * (mu * (1 - mu) / var_norm - 1)
        beta = (1 - mu) * (mu * (1 - mu) / var_norm - 1)
        # 최소값 보장 (alpha, beta > 0)
        alpha = max(0.5, alpha)
        beta = max(0.5, beta)
        return alpha, beta

    @staticmethod
    def _lognormal_params(low: float, high: float) -> tuple[float, float]:
        """min/max에서 Log-normal 분포의 mu/sigma를 도출.

        가정: low ≈ P5, high ≈ P95 (90% 신뢰구간).
        ln(low) = mu - 1.645*sigma, ln(high) = mu + 1.645*sigma 로 역산.
        Limpert et al. (2001) "Log-normal Distributions across the Sciences" 참고.
        """
        if low <= 0:
            low = 0.01  # log(0) 방지
        if high <= low:
            high = low * 2
        ln_low = math.log(low)
        ln_high = math.log(high)
        sigma = (ln_high - ln_low) / (2 * 1.645)
        sigma = max(0.01, sigma)  # 최소 분산 보장
        mu = (ln_low + ln_high) / 2
        return mu, sigma

    async def _monte_carlo(self, p: dict) -> str:
        # 핵심 변수: 각각 (최소, 최대, 기대값)
        revenue_min = float(p.get("revenue_min", 0))
        revenue_max = float(p.get("revenue_max", 0))
        revenue_mode = float(p.get("revenue_mode", 0))
        cost_min = float(p.get("cost_min", 0))
        cost_max = float(p.get("cost_max", 0))
        cost_mode = float(p.get("cost_mode", 0))
        currency = p.get("currency", "만원")
        n_simulations = int(p.get("n_simulations", 10000))
        distribution = p.get("distribution", "triangular")  # triangular | beta | lognormal

        if revenue_max <= 0 or cost_max <= 0:
            return self._monte_carlo_guide()

        # mode 기본값 (삼각분포 + Beta 분포에서 사용)
        if revenue_mode <= 0:
            revenue_mode = (revenue_min + revenue_max) / 2
        if cost_mode <= 0:
            cost_mode = (cost_min + cost_max) / 2

        # 분포별 파라미터 사전 계산
        if distribution == "beta":
            # Beta-PERT 분포 (Malcolm et al., 1959) — 삼각분포보다 꼬리가 두꺼움
            rev_a, rev_b = self._beta_params(revenue_min, revenue_max, revenue_mode)
            cost_a, cost_b = self._beta_params(cost_min, cost_max, cost_mode)
        elif distribution == "lognormal":
            # 로그정규분포 (Limpert et al., 2001) — 우측 꼬리가 긴 비대칭 분포
            rev_mu, rev_sigma = self._lognormal_params(revenue_min, revenue_max)
            cost_mu, cost_sigma = self._lognormal_params(cost_min, cost_max)

        profits = []
        random.seed(42)  # 재현성 보장
        for _ in range(n_simulations):
            if distribution == "beta":
                # Beta(alpha, beta) → [0,1] 값을 [min, max]로 스케일링
                rev = revenue_min + random.betavariate(rev_a, rev_b) * (revenue_max - revenue_min)
                cost = cost_min + random.betavariate(cost_a, cost_b) * (cost_max - cost_min)
            elif distribution == "lognormal":
                rev = random.lognormvariate(rev_mu, rev_sigma)
                cost = random.lognormvariate(cost_mu, cost_sigma)
            else:
                # 기본: 삼각분포 (Triangular Distribution)
                rev = random.triangular(revenue_min, revenue_max, revenue_mode)
                cost = random.triangular(cost_min, cost_max, cost_mode)
            profits.append(rev - cost)

        profits.sort()
        mean_profit = sum(profits) / len(profits)
        median_profit = profits[len(profits) // 2]
        p5 = profits[int(len(profits) * 0.05)]
        p10 = profits[int(len(profits) * 0.10)]
        p25 = profits[int(len(profits) * 0.25)]
        p75 = profits[int(len(profits) * 0.75)]
        p90 = profits[int(len(profits) * 0.90)]
        p95 = profits[int(len(profits) * 0.95)]
        min_profit = profits[0]
        max_profit = profits[-1]

        # 표준편차, 변동계수
        variance = sum((x - mean_profit) ** 2 for x in profits) / len(profits)
        std_dev = math.sqrt(variance)
        cv = abs(std_dev / mean_profit) if mean_profit != 0 else float('inf')

        # 손실 확률 (이익 < 0)
        loss_count = sum(1 for x in profits if x < 0)
        loss_prob = loss_count / len(profits) * 100

        # 히스토그램 (ASCII)
        n_bins = 20
        bin_width = (max_profit - min_profit) / n_bins if max_profit > min_profit else 1
        bins = [0] * n_bins
        for p_val in profits:
            idx = min(int((p_val - min_profit) / bin_width), n_bins - 1)
            bins[idx] += 1
        max_bin = max(bins) if bins else 1

        # 분포 표시명
        _dist_labels = {
            "triangular": "삼각분포(Triangular)",
            "beta": "Beta-PERT 분포(Malcolm et al., 1959)",
            "lognormal": "로그정규분포(Limpert et al., 2001)",
        }
        dist_label = _dist_labels.get(distribution, distribution)

        lines = [
            f"### Monte Carlo 시뮬레이션 ({n_simulations:,}회)",
            "",
            f"**입력 변수 ({dist_label}):**",
            f"- 매출: {revenue_min:,.0f} ~ {revenue_max:,.0f} (기대: {revenue_mode:,.0f}) {currency}",
            f"- 비용: {cost_min:,.0f} ~ {cost_max:,.0f} (기대: {cost_mode:,.0f}) {currency}",
            "",
            "**시뮬레이션 결과:**",
            "",
            "| 통계량 | 값 | 설명 |",
            "|--------|-----|------|",
            f"| 평균 이익 | {mean_profit:,.0f} {currency} | 기대 수익 |",
            f"| 중간값 | {median_profit:,.0f} {currency} | 50% 확률 이상 |",
            f"| 표준편차 | {std_dev:,.0f} {currency} | 불확실성 크기 |",
            f"| 변동계수(CV) | {cv:.2f} | {'안정' if cv < 0.5 else '불안정'} |",
            f"| **손실 확률** | **{loss_prob:.1f}%** | **이익 < 0인 경우** |",
            "",
            "### 백분위수 분포",
            "| 백분위 | 이익 | 의미 |",
            "|--------|------|------|",
            f"| P5 (최악) | {p5:,.0f} {currency} | 95% 확률로 이보다 나음 |",
            f"| P10 | {p10:,.0f} {currency} | 90% 확률로 이보다 나음 |",
            f"| P25 | {p25:,.0f} {currency} | 75% 확률로 이보다 나음 |",
            f"| **P50 (중간)** | **{median_profit:,.0f} {currency}** | **가장 가능성 높은 구간** |",
            f"| P75 | {p75:,.0f} {currency} | 25% 확률로 이보다 나음 |",
            f"| P90 | {p90:,.0f} {currency} | 10% 확률로 이보다 나음 |",
            f"| P95 (최선) | {p95:,.0f} {currency} | 5% 확률로 이보다 나음 |",
            "",
            "### 분포 히스토그램",
        ]

        for i, count in enumerate(bins):
            left = min_profit + i * bin_width
            bar_len = int(count / max_bin * 40) if max_bin > 0 else 0
            bar = "█" * bar_len
            marker = " ◀ 평균" if left <= mean_profit < left + bin_width else ""
            lines.append(f"  {left:>10,.0f} |{bar}{marker}")

        lines.extend([
            "",
            f"📌 **VaR(95%)**: 최악의 경우(5% 확률) 손실 = {abs(p5):,.0f} {currency}" if p5 < 0 else "",
            f"📌 **결론**: {n_simulations:,}회 시뮬레이션 결과, 이익 발생 확률 {100 - loss_prob:.1f}%.",
        ])
        return "\n".join(lines)

    def _monte_carlo_guide(self) -> str:
        return "\n".join([
            "### Monte Carlo 시뮬레이션을 위해 필요한 입력값:",
            "",
            "매출과 비용 각각의 범위(최소/최대/기대값)를 입력합니다:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| revenue_min | 매출 최소 | 1000 |",
            "| revenue_max | 매출 최대 | 5000 |",
            "| revenue_mode | 매출 기대값 | 3000 |",
            "| cost_min | 비용 최소 | 800 |",
            "| cost_max | 비용 최대 | 3000 |",
            "| cost_mode | 비용 기대값 | 1500 |",
            "| currency | 단위 | 만원 |",
            "| n_simulations | 시뮬레이션 횟수 | 10000 |",
            "| distribution | 확률분포 종류 | triangular (기본) |",
            "",
            "**지원 분포:**",
            "- `triangular` (기본): 삼각분포 — 최소/최대/기대값 3개로 불확실성 표현",
            "- `beta`: Beta-PERT 분포 — 삼각분포보다 꼬리가 두꺼워 극단값 반영에 유리 (Malcolm et al., 1959)",
            "- `lognormal`: 로그정규분포 — 우측 꼬리가 긴 비대칭 분포, 매출/비용 같은 양수 변수에 적합 (Limpert et al., 2001)",
        ])

    # ── Three Scenario: 보수/기본/낙관 ────────────────────

    async def _three_scenario(self, p: dict) -> str:
        base_revenue = float(p.get("base_revenue", 0))
        base_cost = float(p.get("base_cost", 0))
        growth_rate = float(p.get("growth_rate", 0.10))
        years = int(p.get("years", 3))
        currency = p.get("currency", "만원")

        if base_revenue <= 0:
            return self._three_scenario_guide()

        if base_cost <= 0:
            base_cost = base_revenue * 0.7

        # McKinsey 3-Scenario Framework
        scenarios = {
            "보수적 (P10)": {"rev_mult": 0.7, "cost_mult": 1.2, "growth_mult": 0.5},
            "기본 (P50)": {"rev_mult": 1.0, "cost_mult": 1.0, "growth_mult": 1.0},
            "낙관적 (P90)": {"rev_mult": 1.3, "cost_mult": 0.8, "growth_mult": 1.5},
        }

        lines = [
            "### 3-시나리오 분석 (McKinsey Framework)",
            "",
        ]

        for sc_name, sc_data in scenarios.items():
            rev = base_revenue * sc_data["rev_mult"]
            cost = base_cost * sc_data["cost_mult"]
            gr = growth_rate * sc_data["growth_mult"]
            profit = rev - cost
            margin = (profit / rev * 100) if rev > 0 else 0

            lines.extend([
                f"#### {sc_name}",
                f"- 초기 매출: {rev:,.0f} {currency} / 비용: {cost:,.0f} {currency}",
                f"- 이익: {profit:,.0f} {currency} (마진 {margin:.1f}%)",
                f"- 성장률: {gr:.1%}/년",
                "",
            ])

            lines.append(f"| 연도 | 매출 | 비용 | 이익 | 누적 이익 |")
            lines.append(f"|------|------|------|------|---------|")
            cumul = 0
            for yr in range(1, years + 1):
                yr_rev = rev * ((1 + gr) ** yr)
                yr_cost = cost * ((1 + gr * 0.5) ** yr)  # 비용은 매출보다 느리게 성장
                yr_profit = yr_rev - yr_cost
                cumul += yr_profit
                lines.append(f"| {yr}년차 | {yr_rev:,.0f} | {yr_cost:,.0f} | {yr_profit:,.0f} | {cumul:,.0f} |")
            lines.append("")

        return "\n".join(lines)

    def _three_scenario_guide(self) -> str:
        return "\n".join([
            "### 3-시나리오 분석을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| base_revenue | 기본 연매출 | 10000 (만원) |",
            "| base_cost | 기본 연비용 | 7000 (만원) |",
            "| growth_rate | 기본 성장률 | 0.20 (20%) |",
            "| years | 전망 기간 | 3 (년) |",
            "",
            "💡 보수적(-30%)/기본/낙관적(+30%) 3가지 시나리오를 자동 생성합니다.",
        ])

    # ── Sensitivity: 토네이도 다이어그램 ────────────────────

    async def _sensitivity(self, p: dict) -> str:
        base_profit = float(p.get("base_profit", 0))
        variables_raw = p.get("variables", "")

        if base_profit <= 0 or not variables_raw:
            return self._sensitivity_guide()

        # "변수명:기본값:변동폭" 형식 파싱
        variables = []
        if isinstance(variables_raw, str):
            for item in variables_raw.split(","):
                parts = item.strip().split(":")
                if len(parts) >= 3:
                    try:
                        variables.append({
                            "name": parts[0].strip(),
                            "base": float(parts[1]),
                            "swing_pct": float(parts[2]),
                        })
                    except ValueError:
                        continue
        elif isinstance(variables_raw, list):
            for item in variables_raw:
                if isinstance(item, dict):
                    variables.append({
                        "name": item.get("name", ""),
                        "base": float(item.get("base", 0)),
                        "swing_pct": float(item.get("swing_pct", 20)),
                    })

        if not variables:
            return self._sensitivity_guide()

        # 각 변수의 영향도 계산 (1-at-a-time)
        impacts = []
        for var in variables:
            # 단순 선형 근사: 이익 변동폭 = 기본값 × 변동폭%
            swing = var["base"] * (var["swing_pct"] / 100)
            low_profit = base_profit - swing
            high_profit = base_profit + swing
            impact_range = high_profit - low_profit
            impacts.append({
                "name": var["name"],
                "low": low_profit,
                "high": high_profit,
                "range": abs(impact_range),
            })

        # 영향도 순 정렬 (토네이도 다이어그램)
        impacts.sort(key=lambda x: x["range"], reverse=True)
        max_range = impacts[0]["range"] if impacts else 1
        currency = p.get("currency", "만원")

        lines = [
            "### 민감도 분석 — 토네이도 다이어그램",
            f"(기준 이익: {base_profit:,.0f} {currency})",
            "",
            "각 변수를 ±변동폭으로 변화시켰을 때 이익에 미치는 영향:",
            "",
        ]

        for imp in impacts:
            bar_width = 30
            left_len = int((base_profit - imp["low"]) / max_range * bar_width) if max_range > 0 else 0
            right_len = int((imp["high"] - base_profit) / max_range * bar_width) if max_range > 0 else 0
            left_bar = "◄" + "█" * left_len
            right_bar = "█" * right_len + "►"
            lines.append(f"  {imp['name']:>15s} {imp['low']:>10,.0f} {left_bar}|{right_bar} {imp['high']:>10,.0f}")

        lines.extend([
            "",
            f"  {'':>15s} {'':>10s} {'기준선':^{bar_width * 2 + 1}s}",
            "",
            "### 영향도 순위",
            "| 순위 | 변수 | 하한 | 상한 | 범위 (영향도) |",
            "|------|------|------|------|------------|",
        ])
        for i, imp in enumerate(impacts, 1):
            lines.append(f"| {i} | {imp['name']} | {imp['low']:,.0f} | {imp['high']:,.0f} | {imp['range']:,.0f} |")

        lines.extend([
            "",
            f"📌 **가장 큰 영향**: {impacts[0]['name']} — 이 변수가 변하면 이익이 {impacts[0]['range']:,.0f} {currency} 변동",
            f"📌 **핵심 관리 포인트**: 상위 3개 변수를 집중 모니터링하세요.",
        ])
        return "\n".join(lines)

    def _sensitivity_guide(self) -> str:
        return "\n".join([
            "### 민감도 분석을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| base_profit | 기준 이익 | 3000 (만원) |",
            '| variables | "변수명:기본값:변동폭%" | "매출:10000:20,비용:7000:15,고객수:500:25" |',
            "",
            "💡 토네이도 다이어그램: 어떤 변수가 이익에 가장 큰 영향을 미치는지 시각화합니다.",
        ])

    # ── Breakeven: 손익분기점 ────────────────────────────

    async def _breakeven(self, p: dict) -> str:
        fixed_cost = float(p.get("fixed_cost", 0))
        price = float(p.get("price", 0))
        variable_cost = float(p.get("variable_cost", 0))
        currency = p.get("currency", "원")

        if fixed_cost <= 0 or price <= 0:
            return self._breakeven_guide()

        contribution = price - variable_cost
        if contribution <= 0:
            return f"⚠️ 단위당 공헌이익이 음수입니다 (가격 {price:,.0f} - 변동비 {variable_cost:,.0f} = {contribution:,.0f}). 가격을 변동비보다 높게 설정하세요."

        bep_units = math.ceil(fixed_cost / contribution)
        bep_revenue = bep_units * price
        margin_pct = contribution / price * 100

        # 다양한 판매량에서의 손익
        lines = [
            "### 손익분기점 (Break-Even Point) 분석",
            "",
            f"**핵심 수치:**",
            f"- 고정비: {fixed_cost:,.0f}{currency}",
            f"- 판매 가격: {price:,.0f}{currency}/단위",
            f"- 변동비: {variable_cost:,.0f}{currency}/단위",
            f"- **공헌이익: {contribution:,.0f}{currency}/단위 (마진 {margin_pct:.1f}%)**",
            f"- **손익분기 판매량: {bep_units:,}단위**",
            f"- **손익분기 매출: {bep_revenue:,.0f}{currency}**",
            "",
            "### 판매량별 손익표",
            "| 판매량 | 매출 | 총비용 | 이익 | 상태 |",
            "|--------|------|--------|------|------|",
        ]

        check_points = [
            int(bep_units * 0.25),
            int(bep_units * 0.50),
            int(bep_units * 0.75),
            bep_units,
            int(bep_units * 1.25),
            int(bep_units * 1.50),
            int(bep_units * 2.00),
        ]
        for qty in check_points:
            rev = qty * price
            total_cost = fixed_cost + qty * variable_cost
            profit = rev - total_cost
            status = "🟢 이익" if profit > 0 else ("🔵 BEP" if qty == bep_units else "🔴 손실")
            lines.append(f"| {qty:,} | {rev:,.0f} | {total_cost:,.0f} | {profit:,.0f} | {status} |")

        # BEP 차트 (ASCII)
        lines.extend([
            "",
            "### 손익분기점 시각화",
            "  이익 ↑",
        ])
        chart_width = 40
        for mult in [2.0, 1.5, 1.25, 1.0, 0.75, 0.5, 0.25]:
            qty = int(bep_units * mult)
            profit = qty * price - (fixed_cost + qty * variable_cost)
            bar_len = int(abs(profit) / (bep_units * price) * chart_width)
            bar_len = min(bar_len, chart_width)
            if profit >= 0:
                bar = " " * 5 + "|" + "█" * bar_len + f" +{profit:,.0f}"
            else:
                bar = " " * max(0, 5 - bar_len) + "█" * min(bar_len, 5) + "|" + f" {profit:,.0f}"
            marker = " ◀ BEP" if mult == 1.0 else ""
            lines.append(f"  {qty:>6,} {bar}{marker}")
        lines.append("         " + "─" * 30 + "→ 판매량")

        lines.extend([
            "",
            f"📌 **공식**: BEP = 고정비 ÷ 공헌이익 = {fixed_cost:,.0f} ÷ {contribution:,.0f} = {bep_units:,}단위",
            f"📌 **안전 마진**: BEP 대비 20% 추가 판매({int(bep_units * 1.2):,}단위)부터 안정적 수익 구간",
        ])
        return "\n".join(lines)

    def _breakeven_guide(self) -> str:
        return "\n".join([
            "### 손익분기점 분석을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| fixed_cost | 월 고정비 (임대, 인건비 등) | 5000000 |",
            "| price | 판매 가격 (단위당) | 29900 |",
            "| variable_cost | 변동비 (단위당, AI API비용 등) | 5000 |",
            "",
            "💡 **공헌이익** = 가격 - 변동비. 이 값으로 고정비를 커버하는 데 필요한 판매량을 계산합니다.",
        ])
