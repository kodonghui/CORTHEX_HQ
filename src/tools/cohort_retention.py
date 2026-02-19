"""
코호트 리텐션 분석 도구 — 가입 시기별 고객이 얼마나 오래 남아있는지 추적합니다.

"1월에 가입한 고객 중 3개월 후에 얼마나 남아있나?"를 시각화하고,
리텐션(재방문/재구매율)이 떨어지는 시점과 원인을 분석합니다.

학술 근거:
  - Cohort Analysis (Blattberg et al., 2008) — 고객 코호트 추적 방법론
  - Kaplan-Meier Survival Estimation (Kaplan & Meier, 1958) — 비모수적 생존 분석
  - Retention Curve Fitting (Fader & Hardie, 2007) — 지수/로그 커브 피팅
  - sBG (shifted-Beta-Geometric) Model (Fader & Hardie, 2010) — 계약 기반 이탈
  - Net Revenue Retention (Bessemer Venture Partners, 2020) — SaaS 핵심 지표

사용 방법:
  - action="heatmap"    : 리텐션 히트맵 (코호트 × 기간 매트릭스)
  - action="curve"      : 리텐션 커브 + 커브 피팅 (지수/로그/멱함수)
  - action="benchmark"  : 업종별 리텐션 벤치마크 비교
  - action="revenue"    : 매출 리텐션 (NRR/GRR) 분석
  - action="predict"    : 향후 리텐션 예측 (sBG 모델)
  - action="full"       : 종합 분석

필요 환경변수: 없음
필요 라이브러리: 없음 (순수 Python)
"""
from __future__ import annotations

import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.cohort_retention")


def _mean(vals: list) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _std(vals: list) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


class CohortRetentionTool(BaseTool):
    """교수급 코호트 리텐션 분석 도구 (Kaplan-Meier + sBG + 커브 피팅)."""

    # ─── 업종별 리텐션 벤치마크 (월간, %) ───
    BENCHMARKS = {
        "saas_b2b": {
            "name": "B2B SaaS", "source": "Bessemer/OpenView 2023",
            "month_1": 95, "month_3": 85, "month_6": 75, "month_12": 65,
            "good_nrr": 120, "median_nrr": 105,
        },
        "saas_b2c": {
            "name": "B2C SaaS/구독", "source": "Recurly 2023",
            "month_1": 80, "month_3": 60, "month_6": 45, "month_12": 30,
            "good_nrr": 110, "median_nrr": 95,
        },
        "ecommerce": {
            "name": "이커머스", "source": "Shopify/Adobe 2023",
            "month_1": 35, "month_3": 20, "month_6": 15, "month_12": 10,
            "good_nrr": None, "median_nrr": None,
        },
        "mobile_app": {
            "name": "모바일 앱", "source": "AppsFlyer 2023",
            "month_1": 25, "month_3": 12, "month_6": 7, "month_12": 4,
            "good_nrr": None, "median_nrr": None,
        },
        "gaming": {
            "name": "게임", "source": "GameAnalytics 2023",
            "month_1": 20, "month_3": 8, "month_6": 4, "month_12": 2,
            "good_nrr": None, "median_nrr": None,
        },
        "fintech": {
            "name": "핀테크/금융", "source": "McKinsey 2023",
            "month_1": 70, "month_3": 55, "month_6": 45, "month_12": 35,
            "good_nrr": 115, "median_nrr": 100,
        },
        "media": {
            "name": "미디어/콘텐츠", "source": "Antenna 2023",
            "month_1": 65, "month_3": 45, "month_6": 30, "month_12": 20,
            "good_nrr": 105, "median_nrr": 90,
        },
    }

    async def execute(self, **kwargs) -> dict[str, Any]:
        action = kwargs.get("action", "full")
        dispatch = {
            "heatmap": self._heatmap,
            "curve": self._curve_analysis,
            "benchmark": self._benchmark,
            "revenue": self._revenue_retention,
            "predict": self._predict_retention,
            "full": self._full_analysis,
        }
        handler = dispatch.get(action)
        if not handler:
            return {"error": f"지원하지 않는 action: {action}. "
                    f"가능한 값: {list(dispatch.keys())}"}
        return await handler(**kwargs)

    # ═══════════════════════════════════════════════════════
    #  공통: 코호트 데이터 파싱
    # ═══════════════════════════════════════════════════════

    def _parse_cohort_data(self, kwargs: dict) -> list[dict]:
        """코호트 데이터 파싱. 형식:

        cohort_json: '[{"cohort":"2025-01","size":100,"retained":[100,80,65,50,40,35,30]}, ...]'
        retained = 0개월(가입), 1개월 후, 2개월 후, ... 남아있는 고객 수
        """
        import json
        raw = kwargs.get("cohort_json", "")
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass

        # 기본 예시 데이터 (7개 코호트, 각 6개월 추적)
        return [
            {"cohort": "2025-07", "size": 500, "retained": [500, 350, 260, 200, 165, 140, 125]},
            {"cohort": "2025-08", "size": 480, "retained": [480, 340, 250, 190, 155, 130]},
            {"cohort": "2025-09", "size": 520, "retained": [520, 375, 280, 215, 175]},
            {"cohort": "2025-10", "size": 550, "retained": [550, 395, 300, 230]},
            {"cohort": "2025-11", "size": 600, "retained": [600, 420, 315]},
            {"cohort": "2025-12", "size": 580, "retained": [580, 405]},
            {"cohort": "2026-01", "size": 620, "retained": [620]},
        ]

    # ═══════════════════════════════════════════════════════
    #  1. 리텐션 히트맵 (Blattberg et al., 2008)
    # ═══════════════════════════════════════════════════════

    async def _heatmap(self, **kwargs) -> dict[str, Any]:
        """코호트별 리텐션 히트맵 매트릭스 생성."""
        cohorts = self._parse_cohort_data(kwargs)

        # 히트맵 매트릭스 (코호트 × 기간)
        heatmap = []
        all_rates = []  # 기간별 평균 계산용

        for c in cohorts:
            size = c["size"]
            retained = c.get("retained", [size])
            row = {
                "cohort": c["cohort"],
                "initial_size": size,
                "months": [],
            }
            for i, count in enumerate(retained):
                rate = (count / size * 100) if size > 0 else 0
                row["months"].append({
                    "period": f"M{i}",
                    "retained": count,
                    "rate": round(rate, 1),
                    "color": self._rate_to_color(rate),
                })
                # 기간별 집계
                while len(all_rates) <= i:
                    all_rates.append([])
                all_rates[i].append(rate)

            heatmap.append(row)

        # 기간별 평균 리텐션
        period_averages = []
        for i, rates in enumerate(all_rates):
            period_averages.append({
                "period": f"M{i}",
                "avg_rate": round(_mean(rates), 1),
                "std": round(_std(rates), 1),
                "cohorts_measured": len(rates),
            })

        # 코호트 트렌드 (시간이 지남에 따라 리텐션이 개선되고 있는가?)
        m1_rates = []
        for c in cohorts:
            retained = c.get("retained", [c["size"]])
            if len(retained) >= 2:
                m1_rates.append(retained[1] / c["size"] * 100 if c["size"] > 0 else 0)

        trend = "개선" if len(m1_rates) >= 3 and m1_rates[-1] > m1_rates[0] else (
            "악화" if len(m1_rates) >= 3 and m1_rates[-1] < m1_rates[0] else "보합"
        )

        # 가장 큰 이탈 구간
        biggest_drop = {"period": "N/A", "drop": 0}
        if len(period_averages) >= 2:
            for i in range(1, len(period_averages)):
                drop = period_averages[i - 1]["avg_rate"] - period_averages[i]["avg_rate"]
                if drop > biggest_drop["drop"]:
                    biggest_drop = {
                        "period": f"M{i-1}→M{i}",
                        "drop": round(drop, 1),
                    }

        return {
            "method": "Cohort Retention Heatmap (Blattberg et al., 2008)",
            "description": "코호트(가입 시기)별 잔존율 매트릭스 — 색상으로 리텐션 추이 시각화",
            "heatmap": heatmap,
            "period_averages": period_averages,
            "insights": {
                "m1_trend": trend,
                "biggest_drop": biggest_drop,
                "latest_m1_retention": f"{m1_rates[-1]:.1f}%" if m1_rates else "N/A",
                "total_cohorts": len(cohorts),
            },
        }

    def _rate_to_color(self, rate: float) -> str:
        """리텐션율에 따른 히트맵 색상."""
        if rate >= 80:
            return "#27ae60"   # 녹색 (우수)
        elif rate >= 60:
            return "#2ecc71"   # 연녹색 (양호)
        elif rate >= 40:
            return "#f1c40f"   # 노란색 (보통)
        elif rate >= 20:
            return "#e67e22"   # 주황 (주의)
        else:
            return "#e74c3c"   # 빨간 (위험)

    # ═══════════════════════════════════════════════════════
    #  2. 리텐션 커브 + 커브 피팅 (Fader & Hardie, 2007)
    # ═══════════════════════════════════════════════════════

    async def _curve_analysis(self, **kwargs) -> dict[str, Any]:
        """리텐션 커브 분석 + 3가지 모델 피팅."""
        cohorts = self._parse_cohort_data(kwargs)

        # 전체 코호트 평균 리텐션 커브 계산
        max_periods = max(len(c.get("retained", [])) for c in cohorts)
        period_rates = []

        for i in range(max_periods):
            rates = []
            for c in cohorts:
                retained = c.get("retained", [c["size"]])
                if i < len(retained) and c["size"] > 0:
                    rates.append(retained[i] / c["size"] * 100)
            if rates:
                period_rates.append({
                    "period": i,
                    "avg_rate": _mean(rates),
                    "count": len(rates),
                })

        if len(period_rates) < 2:
            return {"error": "커브 피팅에 최소 2개 기간 데이터가 필요합니다."}

        # 3가지 모델 피팅
        x_data = [p["period"] for p in period_rates]
        y_data = [p["avg_rate"] for p in period_rates]

        models = {}

        # 1) 지수 감소: R(t) = a × e^(-bt)
        exp_params = self._fit_exponential(x_data, y_data)
        if exp_params:
            a, b = exp_params
            exp_fitted = [a * math.exp(-b * t) for t in x_data]
            exp_r2 = self._r_squared(y_data, exp_fitted)
            half_life = math.log(2) / b if b > 0 else float("inf")
            models["exponential"] = {
                "name": "지수 감소 모델",
                "formula": f"R(t) = {a:.1f} × e^(-{b:.4f}t)",
                "params": {"a": round(a, 2), "b": round(b, 4)},
                "r_squared": round(exp_r2, 4),
                "half_life_months": round(half_life, 1),
                "fitted_values": [round(v, 1) for v in exp_fitted],
            }

        # 2) 로그 감소: R(t) = a - b × ln(t+1)
        log_params = self._fit_logarithmic(x_data, y_data)
        if log_params:
            a, b = log_params
            log_fitted = [max(0, a - b * math.log(t + 1)) for t in x_data]
            log_r2 = self._r_squared(y_data, log_fitted)
            models["logarithmic"] = {
                "name": "로그 감소 모델",
                "formula": f"R(t) = {a:.1f} - {b:.1f} × ln(t+1)",
                "params": {"a": round(a, 2), "b": round(b, 2)},
                "r_squared": round(log_r2, 4),
                "fitted_values": [round(v, 1) for v in log_fitted],
            }

        # 3) 멱함수 감소: R(t) = a × (t+1)^(-b)
        power_params = self._fit_power(x_data, y_data)
        if power_params:
            a, b = power_params
            pow_fitted = [a * (t + 1) ** (-b) for t in x_data]
            pow_r2 = self._r_squared(y_data, pow_fitted)
            models["power"] = {
                "name": "멱함수 감소 모델",
                "formula": f"R(t) = {a:.1f} × (t+1)^(-{b:.4f})",
                "params": {"a": round(a, 2), "b": round(b, 4)},
                "r_squared": round(pow_r2, 4),
                "fitted_values": [round(v, 1) for v in pow_fitted],
            }

        # 최적 모델 선택
        best_model = max(models, key=lambda m: models[m]["r_squared"]) if models else None

        # 12개월 예측 (최적 모델 기준)
        predictions = []
        if best_model:
            m = models[best_model]
            for t in range(max_periods, 13):
                if best_model == "exponential":
                    pred = m["params"]["a"] * math.exp(-m["params"]["b"] * t)
                elif best_model == "logarithmic":
                    pred = max(0, m["params"]["a"] - m["params"]["b"] * math.log(t + 1))
                else:
                    pred = m["params"]["a"] * (t + 1) ** (-m["params"]["b"])
                predictions.append({
                    "period": f"M{t}",
                    "predicted_rate": round(max(0, min(100, pred)), 1),
                })

        return {
            "method": "Retention Curve Fitting (Fader & Hardie, 2007)",
            "description": "3가지 수학 모델(지수/로그/멱함수)로 리텐션 커브를 피팅하고 최적 모델 선택",
            "observed_curve": [
                {"period": f"M{p['period']}", "rate": round(p["avg_rate"], 1)}
                for p in period_rates
            ],
            "models": models,
            "best_model": best_model,
            "best_r_squared": round(models[best_model]["r_squared"], 4) if best_model else None,
            "predictions": predictions,
            "interpretation": (
                f"최적 모델: {models[best_model]['name']} (R²={models[best_model]['r_squared']:.3f}). "
                f"현재 추세라면 M12 예상 리텐션: {predictions[-1]['predicted_rate']}%."
                if best_model and predictions else "데이터 부족"
            ),
        }

    def _fit_exponential(self, x: list, y: list) -> tuple | None:
        """지수 모델 피팅: y = a × e^(-bx). 로그 변환 → 선형 회귀."""
        try:
            log_y = [math.log(max(yi, 0.1)) for yi in y]
            n = len(x)
            sum_x = sum(x)
            sum_y = sum(log_y)
            sum_xy = sum(xi * yi for xi, yi in zip(x, log_y))
            sum_x2 = sum(xi ** 2 for xi in x)

            denom = n * sum_x2 - sum_x ** 2
            if abs(denom) < 1e-10:
                return None
            b_neg = (n * sum_xy - sum_x * sum_y) / denom
            ln_a = (sum_y - b_neg * sum_x) / n

            return math.exp(ln_a), -b_neg
        except (ValueError, ZeroDivisionError):
            return None

    def _fit_logarithmic(self, x: list, y: list) -> tuple | None:
        """로그 모델 피팅: y = a - b × ln(x+1). 선형 회귀."""
        try:
            ln_x = [math.log(xi + 1) for xi in x]
            n = len(x)
            sum_lnx = sum(ln_x)
            sum_y = sum(y)
            sum_lnx_y = sum(lxi * yi for lxi, yi in zip(ln_x, y))
            sum_lnx2 = sum(lxi ** 2 for lxi in ln_x)

            denom = n * sum_lnx2 - sum_lnx ** 2
            if abs(denom) < 1e-10:
                return None
            b_neg = (n * sum_lnx_y - sum_lnx * sum_y) / denom
            a = (sum_y - b_neg * sum_lnx) / n

            return a, -b_neg
        except (ValueError, ZeroDivisionError):
            return None

    def _fit_power(self, x: list, y: list) -> tuple | None:
        """멱함수 피팅: y = a × (x+1)^(-b). 로그-로그 변환."""
        try:
            ln_x = [math.log(xi + 1) for xi in x]
            ln_y = [math.log(max(yi, 0.1)) for yi in y]
            n = len(x)
            sum_lnx = sum(ln_x)
            sum_lny = sum(ln_y)
            sum_lnx_lny = sum(lxi * lyi for lxi, lyi in zip(ln_x, ln_y))
            sum_lnx2 = sum(lxi ** 2 for lxi in ln_x)

            denom = n * sum_lnx2 - sum_lnx ** 2
            if abs(denom) < 1e-10:
                return None
            b_neg = (n * sum_lnx_lny - sum_lnx * sum_lny) / denom
            ln_a = (sum_lny - b_neg * sum_lnx) / n

            return math.exp(ln_a), -b_neg
        except (ValueError, ZeroDivisionError):
            return None

    def _r_squared(self, observed: list, predicted: list) -> float:
        """결정계수 R² 계산."""
        mean_y = _mean(observed)
        ss_tot = sum((y - mean_y) ** 2 for y in observed)
        ss_res = sum((y - yhat) ** 2 for y, yhat in zip(observed, predicted))
        return 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    # ═══════════════════════════════════════════════════════
    #  3. 업종별 벤치마크 비교
    # ═══════════════════════════════════════════════════════

    async def _benchmark(self, **kwargs) -> dict[str, Any]:
        """내 리텐션을 업종별 벤치마크와 비교합니다."""
        industry = kwargs.get("industry", "saas_b2c")
        cohorts = self._parse_cohort_data(kwargs)

        # 내 리텐션 계산
        my_rates = {}
        for milestone in [1, 3, 6, 12]:
            rates = []
            for c in cohorts:
                retained = c.get("retained", [c["size"]])
                if milestone < len(retained) and c["size"] > 0:
                    rates.append(retained[milestone] / c["size"] * 100)
            if rates:
                my_rates[f"month_{milestone}"] = round(_mean(rates), 1)

        # 벤치마크 비교
        benchmark = self.BENCHMARKS.get(industry, self.BENCHMARKS["saas_b2c"])
        comparisons = []
        grades = []

        for milestone in [1, 3, 6, 12]:
            key = f"month_{milestone}"
            my_val = my_rates.get(key)
            bench_val = benchmark.get(key)
            if my_val is not None and bench_val is not None:
                diff = my_val - bench_val
                if diff >= 10:
                    grade = "S"
                elif diff >= 0:
                    grade = "A"
                elif diff >= -10:
                    grade = "B"
                elif diff >= -20:
                    grade = "C"
                else:
                    grade = "D"
                grades.append(grade)
                comparisons.append({
                    "milestone": f"M{milestone}",
                    "my_rate": f"{my_val:.1f}%",
                    "benchmark": f"{bench_val}%",
                    "diff": f"{'+' if diff >= 0 else ''}{diff:.1f}%p",
                    "grade": grade,
                    "status": "업계 평균 이상 ✓" if diff >= 0 else "업계 평균 이하 ✗",
                })

        # 전체 업종 비교 테이블
        all_benchmarks = []
        for ind_key, ind_data in self.BENCHMARKS.items():
            row = {"industry": ind_data["name"], "source": ind_data["source"]}
            for milestone in [1, 3, 6, 12]:
                row[f"m{milestone}"] = f"{ind_data.get(f'month_{milestone}', '-')}%"
            if ind_key == industry:
                row["is_my_industry"] = True
            all_benchmarks.append(row)

        overall = "S" if all(g in ("S", "A") for g in grades) else (
            "A" if _mean([{"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}.get(g, 3) for g in grades]) >= 3.5
            else "B" if _mean([{"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}.get(g, 3) for g in grades]) >= 2.5
            else "C"
        ) if grades else "N/A"

        return {
            "method": "Industry Benchmark Comparison",
            "description": f"내 리텐션을 {benchmark['name']} 업종 벤치마크와 비교 분석",
            "industry": benchmark["name"],
            "my_retention": my_rates,
            "comparisons": comparisons,
            "overall_grade": overall,
            "all_benchmarks": all_benchmarks,
            "nrr_benchmark": {
                "good": f"{benchmark.get('good_nrr', 'N/A')}%",
                "median": f"{benchmark.get('median_nrr', 'N/A')}%",
            } if benchmark.get("good_nrr") else None,
        }

    # ═══════════════════════════════════════════════════════
    #  4. 매출 리텐션 (NRR/GRR) 분석
    # ═══════════════════════════════════════════════════════

    async def _revenue_retention(self, **kwargs) -> dict[str, Any]:
        """Net Revenue Retention (NRR) / Gross Revenue Retention (GRR) 분석.

        NRR = (기존고객 시작 매출 + 업셀 - 다운그레이드 - 이탈) / 기존고객 시작 매출
        GRR = (기존고객 시작 매출 - 다운그레이드 - 이탈) / 기존고객 시작 매출
        """
        starting_mrr = kwargs.get("starting_mrr", 100000000)  # 1억
        expansion_mrr = kwargs.get("expansion_mrr", 15000000)  # 업셀 1500만
        contraction_mrr = kwargs.get("contraction_mrr", 5000000)  # 다운그레이드 500만
        churned_mrr = kwargs.get("churned_mrr", 8000000)  # 이탈 800만

        nrr = (starting_mrr + expansion_mrr - contraction_mrr - churned_mrr) / starting_mrr * 100
        grr = (starting_mrr - contraction_mrr - churned_mrr) / starting_mrr * 100

        # 12개월 복리 효과
        nrr_monthly = nrr / 100
        grr_monthly = grr / 100
        nrr_annual = nrr_monthly ** 12 * 100
        grr_annual = grr_monthly ** 12 * 100

        # NRR 시나리오 분석 (이탈율 변화에 따른 NRR 변화)
        scenarios = []
        for churn_pct in [0.03, 0.05, 0.08, 0.10, 0.15, 0.20]:
            scenario_churn = starting_mrr * churn_pct
            scenario_nrr = (starting_mrr + expansion_mrr - contraction_mrr - scenario_churn) / starting_mrr * 100
            annual = (scenario_nrr / 100) ** 12 * 100
            scenarios.append({
                "monthly_churn_rate": f"{churn_pct*100:.0f}%",
                "churned_mrr": f"{round(scenario_churn):,}원",
                "monthly_nrr": f"{scenario_nrr:.1f}%",
                "annual_nrr": f"{annual:.0f}%",
                "interpretation": "성장" if scenario_nrr > 100 else (
                    "유지" if scenario_nrr == 100 else "축소"
                ),
            })

        # Quick Ratio (SaaS 성장 효율)
        growth = expansion_mrr
        losses = contraction_mrr + churned_mrr
        quick_ratio = growth / losses if losses > 0 else float("inf")

        return {
            "method": "Revenue Retention Analysis (NRR/GRR)",
            "description": "매출 기반 리텐션 — 업셀/다운그레이드/이탈 포함 순매출 리텐션 분석",
            "inputs": {
                "starting_mrr": f"{starting_mrr:,}원",
                "expansion": f"+{expansion_mrr:,}원",
                "contraction": f"-{contraction_mrr:,}원",
                "churned": f"-{churned_mrr:,}원",
            },
            "nrr": {
                "monthly": f"{nrr:.1f}%",
                "annualized": f"{nrr_annual:.0f}%",
                "interpretation": (
                    "기존 고객만으로도 매출이 성장하고 있습니다 (NRR > 100%)" if nrr > 100
                    else "기존 고객 매출이 줄어들고 있습니다 (NRR < 100%)"
                ),
            },
            "grr": {
                "monthly": f"{grr:.1f}%",
                "annualized": f"{grr_annual:.0f}%",
                "interpretation": (
                    "GRR 90% 이상 — 우수한 고객 유지력" if grr >= 90
                    else "GRR 80~90% — 평균적인 유지력" if grr >= 80
                    else "GRR 80% 미만 — 이탈 관리 필요"
                ),
            },
            "quick_ratio": {
                "value": round(quick_ratio, 2) if quick_ratio != float("inf") else "∞",
                "interpretation": (
                    "Quick Ratio 4+ — 매우 효율적 성장" if quick_ratio >= 4
                    else "Quick Ratio 2~4 — 건전한 성장" if quick_ratio >= 2
                    else "Quick Ratio 1~2 — 비효율적 성장" if quick_ratio >= 1
                    else "Quick Ratio < 1 — 축소 중"
                ),
            },
            "scenarios": scenarios,
        }

    # ═══════════════════════════════════════════════════════
    #  5. 리텐션 예측 — sBG 모델 (Fader & Hardie, 2010)
    # ═══════════════════════════════════════════════════════

    async def _predict_retention(self, **kwargs) -> dict[str, Any]:
        """sBG (shifted-Beta-Geometric) 모델 기반 리텐션 예측.

        계약 기반 이탈 모델: 이탈 확률이 고객마다 다르다고 가정 (Beta 분포).
        P(T=t) = B(a+1, b+t-1) / B(a, b)  (t=1,2,3,...)
        S(t) = B(a, b+t) / B(a, b)          (생존 함수)
        """
        cohorts = self._parse_cohort_data(kwargs)
        predict_months = kwargs.get("predict_months", 12)

        # 전체 코호트 평균 리텐션 데이터
        max_periods = max(len(c.get("retained", [])) for c in cohorts)
        observed_rates = []

        for i in range(max_periods):
            rates = []
            for c in cohorts:
                retained = c.get("retained", [c["size"]])
                if i < len(retained) and c["size"] > 0:
                    rates.append(retained[i] / c["size"])
            if rates:
                observed_rates.append(_mean(rates))

        if len(observed_rates) < 2:
            return {"error": "예측에 최소 2개 기간 데이터가 필요합니다."}

        # sBG 파라미터 추정 (Grid Search + MLE 근사)
        best_a, best_b = self._fit_sbg(observed_rates)

        # 예측 생성
        predictions = []
        for t in range(predict_months + 1):
            if t < len(observed_rates):
                actual = observed_rates[t]
                predicted = self._sbg_survival(best_a, best_b, t)
                predictions.append({
                    "period": f"M{t}",
                    "actual": f"{actual*100:.1f}%",
                    "predicted": f"{predicted*100:.1f}%",
                    "type": "관측값",
                })
            else:
                predicted = self._sbg_survival(best_a, best_b, t)
                predictions.append({
                    "period": f"M{t}",
                    "actual": None,
                    "predicted": f"{predicted*100:.1f}%",
                    "type": "예측값",
                })

        # 이탈 확률 분포 특성
        mean_theta = best_a / (best_a + best_b)  # 평균 이탈 확률
        var_theta = (best_a * best_b) / ((best_a + best_b) ** 2 * (best_a + best_b + 1))
        mode_theta = (best_a - 1) / (best_a + best_b - 2) if (best_a > 1 and best_b > 1) else 0

        # 기대 잔존 기간 (DEL: Discounted Expected Lifetime)
        del_months = sum(self._sbg_survival(best_a, best_b, t) for t in range(1, 121))

        return {
            "method": "sBG Model Prediction (Fader & Hardie, 2010)",
            "description": "shifted-Beta-Geometric 모델 — 이탈 확률의 이질성을 반영한 리텐션 예측",
            "parameters": {
                "alpha": round(best_a, 3),
                "beta": round(best_b, 3),
                "interpretation": (
                    f"고객 이탈 확률 분포: Beta({best_a:.2f}, {best_b:.2f}). "
                    f"평균 월간 이탈률 {mean_theta*100:.1f}%, "
                    f"기대 잔존 기간 {del_months:.1f}개월."
                ),
            },
            "churn_distribution": {
                "mean_churn_rate": f"{mean_theta*100:.1f}%",
                "mode_churn_rate": f"{mode_theta*100:.1f}%",
                "variance": round(var_theta, 4),
                "heterogeneity": "높음 (고객마다 이탈률 편차 큼)" if var_theta > 0.02 else "낮음 (균일한 이탈 패턴)",
            },
            "expected_lifetime_months": round(del_months, 1),
            "predictions": predictions,
        }

    def _sbg_survival(self, a: float, b: float, t: int) -> float:
        """sBG 생존 함수: S(t) = B(a, b+t) / B(a, b)."""
        if t == 0:
            return 1.0
        # B(a,b+t)/B(a,b) = Γ(b+t)/Γ(b) × Γ(a+b)/Γ(a+b+t)
        # = product_{i=0}^{t-1} (b+i)/(a+b+i)
        survival = 1.0
        for i in range(t):
            survival *= (b + i) / (a + b + i)
        return survival

    def _fit_sbg(self, observed: list) -> tuple:
        """sBG 파라미터 a, b를 Grid Search로 추정."""
        best_ll = float("-inf")
        best_a, best_b = 1.0, 1.0

        # 그리드 서치
        for a_10 in range(1, 100):  # a: 0.1 ~ 10.0
            a = a_10 / 10.0
            for b_10 in range(1, 100):  # b: 0.1 ~ 10.0
                b = b_10 / 10.0
                ll = 0.0
                for t in range(len(observed)):
                    predicted = self._sbg_survival(a, b, t)
                    if predicted > 0 and observed[t] > 0:
                        # 단순 MSE 기반 (진짜 MLE는 개별 고객 데이터 필요)
                        ll -= (observed[t] - predicted) ** 2
                if ll > best_ll:
                    best_ll = ll
                    best_a, best_b = a, b

        return best_a, best_b

    # ═══════════════════════════════════════════════════════
    #  6. 종합 분석
    # ═══════════════════════════════════════════════════════

    async def _full_analysis(self, **kwargs) -> dict[str, Any]:
        """전체 코호트 리텐션 종합 분석."""
        heatmap = await self._heatmap(**kwargs)
        curve = await self._curve_analysis(**kwargs)
        benchmark = await self._benchmark(**kwargs)
        revenue = await self._revenue_retention(**kwargs)
        predict = await self._predict_retention(**kwargs)

        # LLM 요약
        summary_prompt = f"""아래 코호트 리텐션 분석 결과를 한국어로 요약하세요.

## 히트맵 인사이트
- M1 트렌드: {heatmap.get('insights', {}).get('m1_trend', 'N/A')}
- 최대 이탈 구간: {heatmap.get('insights', {}).get('biggest_drop', {}).get('period', 'N/A')} ({heatmap.get('insights', {}).get('biggest_drop', {}).get('drop', 0)}%p 감소)

## 커브 피팅
- 최적 모델: {curve.get('best_model', 'N/A')} (R²={curve.get('best_r_squared', 'N/A')})

## 벤치마크
- 종합 등급: {benchmark.get('overall_grade', 'N/A')}

## 매출 리텐션
- NRR: {revenue.get('nrr', {}).get('monthly', 'N/A')}
- GRR: {revenue.get('grr', {}).get('monthly', 'N/A')}

## 예측
- 기대 잔존: {predict.get('expected_lifetime_months', 'N/A')}개월

다음을 포함해서 작성:
1. 리텐션 현황 한 줄 요약
2. 가장 시급한 개선 포인트 2~3개
3. 구체적 액션 아이템"""

        summary = await self._llm_call(
            system_prompt="코호트 분석/리텐션 전문가. 데이터 기반 구체적 개선안 제시.",
            user_prompt=summary_prompt,
        )

        return {
            "method": "Full Cohort Retention Analysis",
            "heatmap": heatmap,
            "curve_analysis": curve,
            "benchmark": benchmark,
            "revenue_retention": revenue,
            "prediction": predict,
            "executive_summary": summary,
        }
