"""
고객 생애가치(CLV) 예측 도구 — 고객 한 명이 평생 가져다줄 매출을 수학적으로 예측합니다.

"이 고객은 앞으로 얼마치를 쓸까?"를 확률 모델로 추정하고,
고객 세그먼트별 투자 우선순위를 제시하는 교수급 CLV 분석 도구입니다.

학술 근거:
  - BG/NBD 모델 (Fader, Hardie & Lee, "Counting Your Customers", 2005)
  - Gamma-Gamma 모델 (Fader & Hardie, "The Gamma-Gamma Model of Monetary Value", 2013)
  - Pareto/NBD 모델 (Schmittlein, Morrison & Colombo, 1987)
  - RFM 기반 CLV 추정 (Hughes, "Strategic Database Marketing", 1994)
  - 할인 CLV (Gupta & Lehmann, "Customers as Assets", 2005)
  - 고객 수익성 분석 (Pfeifer, Haskins & Conroy, 2005)

사용 방법:
  - action="predict"    : 개별 고객 CLV 예측 (BG/NBD + Gamma-Gamma)
  - action="segment"    : 고객군별 CLV 세그먼트 분석
  - action="cohort"     : 가입 코호트별 CLV 비교
  - action="unit_economics" : 유닛 이코노믹스 (CAC vs CLV)
  - action="discount"   : 할인 CLV (화폐의 시간가치 반영)
  - action="full"       : 종합 CLV 분석

필요 환경변수: 없음
필요 라이브러리: numpy
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.customer_ltv_model")


# ═══════════════════════════════════════════════════════
#  BG/NBD 확률 함수 (순수 Python — lifetimes 패키지 불필요)
# ═══════════════════════════════════════════════════════

def _beta_function(a: float, b: float) -> float:
    """베타 함수 B(a,b) = Gamma(a)*Gamma(b)/Gamma(a+b)."""
    return math.exp(math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b))


def _hyp2f1_simple(a: float, b: float, c: float, z: float,
                   max_iter: int = 200) -> float:
    """Gauss 초기하급수 2F1(a,b;c;z) — BG/NBD 생존확률 계산에 필요.

    |z| < 1 범위에서 급수 전개 (BG/NBD에서는 항상 이 범위).
    """
    result = 1.0
    term = 1.0
    for n in range(1, max_iter):
        term *= (a + n - 1) * (b + n - 1) / (c + n - 1) * z / n
        result += term
        if abs(term) < 1e-12:
            break
    return result


class CustomerLtvModelTool(BaseTool):
    """교수급 고객 생애가치 예측 도구 (BG/NBD + Gamma-Gamma)."""

    # ─── 업종별 벤치마크 데이터 ───
    BENCHMARKS = {
        "saas": {
            "avg_monthly_churn": 0.05,  # 월 5%
            "avg_arpu": 50000,          # 월 5만원
            "avg_cac": 150000,
            "good_ltv_cac_ratio": 3.0,
            "great_ltv_cac_ratio": 5.0,
        },
        "ecommerce": {
            "avg_monthly_churn": 0.08,
            "avg_arpu": 35000,
            "avg_cac": 25000,
            "good_ltv_cac_ratio": 3.0,
            "great_ltv_cac_ratio": 5.0,
        },
        "subscription_box": {
            "avg_monthly_churn": 0.10,
            "avg_arpu": 30000,
            "avg_cac": 40000,
            "good_ltv_cac_ratio": 2.5,
            "great_ltv_cac_ratio": 4.0,
        },
        "mobile_app": {
            "avg_monthly_churn": 0.15,
            "avg_arpu": 5000,
            "avg_cac": 3000,
            "good_ltv_cac_ratio": 3.0,
            "great_ltv_cac_ratio": 5.0,
        },
        "fintech": {
            "avg_monthly_churn": 0.03,
            "avg_arpu": 80000,
            "avg_cac": 200000,
            "good_ltv_cac_ratio": 3.0,
            "great_ltv_cac_ratio": 6.0,
        },
    }

    # ─── BG/NBD 디폴트 파라미터 (업종 평균) ───
    # (r, alpha, a, b) — Fader & Hardie (2005) Table 1 참고
    DEFAULT_BGNBD_PARAMS = {
        "saas":             (0.243, 4.414, 0.793, 2.426),
        "ecommerce":        (0.525, 6.183, 0.891, 1.614),
        "subscription_box": (0.389, 3.756, 1.052, 1.238),
        "mobile_app":       (0.712, 8.921, 1.234, 0.987),
        "fintech":          (0.183, 3.142, 0.654, 3.215),
        "default":          (0.350, 5.000, 0.900, 1.800),
    }

    async def execute(self, **kwargs) -> dict[str, Any]:
        action = kwargs.get("action", "full")
        dispatch = {
            "predict": self._predict,
            "segment": self._segment,
            "cohort": self._cohort,
            "unit_economics": self._unit_economics,
            "discount": self._discount_clv,
            "full": self._full_analysis,
        }
        handler = dispatch.get(action)
        if not handler:
            return {"error": f"지원하지 않는 action: {action}. "
                    f"가능한 값: {list(dispatch.keys())}"}
        return await handler(**kwargs)

    # ═══════════════════════════════════════════════════════
    #  1. 개별 고객 CLV 예측 (BG/NBD + Gamma-Gamma)
    # ═══════════════════════════════════════════════════════

    async def _predict(self, **kwargs) -> dict[str, Any]:
        """BG/NBD로 미래 구매 횟수 예측 + Gamma-Gamma로 객단가 추정 → CLV."""
        frequency = kwargs.get("frequency", 5)       # 반복 구매 횟수
        recency = kwargs.get("recency", 30)           # 최근 구매까지 경과일
        T = kwargs.get("T", 365)                      # 관찰 기간 (일)
        monetary = kwargs.get("monetary", 50000)      # 평균 주문금액
        horizon = kwargs.get("horizon", 365)          # 예측 기간 (일)
        industry = kwargs.get("industry", "default")

        # BG/NBD 파라미터 선택
        r, alpha, a, b = self.DEFAULT_BGNBD_PARAMS.get(
            industry, self.DEFAULT_BGNBD_PARAMS["default"]
        )

        # ─── BG/NBD: 미래 기대 구매 횟수 E[X(t)|x, t_x, T] ───
        # Fader, Hardie & Lee (2005), Equation 10
        x = frequency
        t_x = recency

        # 생존 확률 P(alive | x, t_x, T)
        p_alive = self._bg_nbd_p_alive(x, t_x, T, r, alpha, a, b)

        # 기대 미래 구매 횟수
        expected_purchases = self._bg_nbd_expected_purchases(
            horizon, x, t_x, T, r, alpha, a, b
        )

        # ─── Gamma-Gamma: 기대 평균 거래금액 E[M|x, m_x] ───
        # Fader & Hardie (2013), Equation 2
        # 파라미터 (p, q, gamma)
        p_gg, q_gg, gamma_gg = 1.2, 0.8, 15000.0  # 업종 디폴트
        expected_monetary = self._gamma_gamma_expected_value(
            x, monetary, p_gg, q_gg, gamma_gg
        )

        # ─── CLV = 기대 구매횟수 × 기대 객단가 ───
        clv = expected_purchases * expected_monetary

        # 신뢰구간 (몬테카를로 시뮬레이션)
        clv_simulations = self._simulate_clv(
            x, t_x, T, monetary, horizon, r, alpha, a, b,
            p_gg, q_gg, gamma_gg, n_sim=5000
        )
        ci_lower = float(np.percentile(clv_simulations, 5))
        ci_upper = float(np.percentile(clv_simulations, 95))

        result = {
            "model": "BG/NBD + Gamma-Gamma",
            "customer_input": {
                "frequency": x,
                "recency_days": t_x,
                "observation_days": T,
                "avg_order_value": monetary,
                "prediction_horizon_days": horizon,
            },
            "predictions": {
                "p_alive": round(p_alive, 4),
                "p_alive_pct": f"{p_alive*100:.1f}%",
                "expected_future_purchases": round(expected_purchases, 2),
                "expected_avg_order_value": round(expected_monetary),
                "predicted_clv": round(clv),
                "clv_90_ci": [round(ci_lower), round(ci_upper)],
            },
            "interpretation": self._interpret_prediction(
                p_alive, expected_purchases, clv, industry
            ),
            "academic_reference": (
                "Fader, Hardie & Lee (2005) 'Counting Your Customers the Easy Way' + "
                "Fader & Hardie (2013) 'The Gamma-Gamma Model of Monetary Value'"
            ),
        }

        # LLM 인사이트 합성
        llm_summary = await self._llm_call(
            f"고객 CLV 예측 결과를 분석해주세요:\n{result}\n\n"
            "이 고객의 가치와 관리 전략을 구체적으로 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  2. 고객군별 CLV 세그먼트 분석
    # ═══════════════════════════════════════════════════════

    async def _segment(self, **kwargs) -> dict[str, Any]:
        """고객 데이터를 CLV 기반으로 4~5개 세그먼트로 분류."""
        customers_json = kwargs.get("customers", "")
        industry = kwargs.get("industry", "default")

        # 샘플 데이터 또는 실제 데이터 파싱
        customers = self._parse_customers(customers_json)

        r, alpha, a, b = self.DEFAULT_BGNBD_PARAMS.get(
            industry, self.DEFAULT_BGNBD_PARAMS["default"]
        )
        p_gg, q_gg, gamma_gg = 1.2, 0.8, 15000.0

        # 각 고객의 CLV 계산
        clv_list = []
        for c in customers:
            freq = c.get("frequency", 1)
            rec = c.get("recency", 30)
            obs = c.get("T", 365)
            mon = c.get("monetary", 30000)

            p_alive = self._bg_nbd_p_alive(freq, rec, obs, r, alpha, a, b)
            exp_purch = self._bg_nbd_expected_purchases(
                365, freq, rec, obs, r, alpha, a, b
            )
            exp_mon = self._gamma_gamma_expected_value(
                freq, mon, p_gg, q_gg, gamma_gg
            )
            clv = exp_purch * exp_mon

            clv_list.append({
                "customer_id": c.get("id", f"C{len(clv_list)+1:03d}"),
                "frequency": freq,
                "recency": rec,
                "monetary": mon,
                "p_alive": round(p_alive, 3),
                "predicted_clv": round(clv),
            })

        # CLV 기반 세그먼트 분류
        clv_values = [c["predicted_clv"] for c in clv_list]
        if len(clv_values) >= 4:
            q25, q50, q75 = (
                float(np.percentile(clv_values, 25)),
                float(np.percentile(clv_values, 50)),
                float(np.percentile(clv_values, 75)),
            )
        else:
            avg = np.mean(clv_values)
            q25, q50, q75 = avg * 0.5, avg, avg * 1.5

        segments = {
            "Champions (최우수)": [],
            "Loyal (충성)": [],
            "Potential (잠재 성장)": [],
            "At Risk (관리 필요)": [],
        }
        for c in clv_list:
            clv = c["predicted_clv"]
            if clv >= q75:
                segments["Champions (최우수)"].append(c)
            elif clv >= q50:
                segments["Loyal (충성)"].append(c)
            elif clv >= q25:
                segments["Potential (잠재 성장)"].append(c)
            else:
                segments["At Risk (관리 필요)"].append(c)

        segment_summary = {}
        for seg_name, members in segments.items():
            if members:
                seg_clvs = [m["predicted_clv"] for m in members]
                segment_summary[seg_name] = {
                    "count": len(members),
                    "pct": f"{len(members)/len(clv_list)*100:.1f}%",
                    "avg_clv": round(np.mean(seg_clvs)),
                    "total_clv": round(sum(seg_clvs)),
                    "strategy": self._segment_strategy(seg_name),
                }

        result = {
            "total_customers": len(clv_list),
            "total_predicted_clv": round(sum(clv_values)),
            "avg_clv": round(np.mean(clv_values)),
            "clv_distribution": {
                "min": round(min(clv_values)),
                "q25": round(q25),
                "median": round(q50),
                "q75": round(q75),
                "max": round(max(clv_values)),
            },
            "segments": segment_summary,
            "pareto_principle": self._check_pareto(clv_values),
        }

        llm_summary = await self._llm_call(
            f"고객 CLV 세그먼트 분석 결과입니다:\n{result}\n\n"
            "각 세그먼트별 구체적인 마케팅/관리 전략을 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  3. 코호트별 CLV 비교
    # ═══════════════════════════════════════════════════════

    async def _cohort(self, **kwargs) -> dict[str, Any]:
        """가입 시기(코호트)별 CLV 추이 분석."""
        cohorts_json = kwargs.get("cohorts", "")
        industry = kwargs.get("industry", "default")

        cohorts = self._parse_cohorts(cohorts_json)

        r, alpha, a, b = self.DEFAULT_BGNBD_PARAMS.get(
            industry, self.DEFAULT_BGNBD_PARAMS["default"]
        )

        cohort_results = []
        for cohort in cohorts:
            name = cohort.get("name", "Unknown")
            size = cohort.get("size", 100)
            avg_freq = cohort.get("avg_frequency", 3)
            avg_rec = cohort.get("avg_recency", 60)
            avg_T = cohort.get("avg_T", 180)
            avg_mon = cohort.get("avg_monetary", 40000)

            p_alive = self._bg_nbd_p_alive(avg_freq, avg_rec, avg_T, r, alpha, a, b)
            exp_purch = self._bg_nbd_expected_purchases(
                365, avg_freq, avg_rec, avg_T, r, alpha, a, b
            )
            avg_clv = exp_purch * avg_mon
            total_clv = avg_clv * size * p_alive

            cohort_results.append({
                "cohort": name,
                "size": size,
                "avg_frequency": avg_freq,
                "avg_monetary": avg_mon,
                "survival_rate": f"{p_alive*100:.1f}%",
                "avg_clv": round(avg_clv),
                "total_cohort_clv": round(total_clv),
            })

        # 코호트 간 비교
        if len(cohort_results) >= 2:
            best = max(cohort_results, key=lambda x: x["avg_clv"])
            worst = min(cohort_results, key=lambda x: x["avg_clv"])
            improvement = ((best["avg_clv"] - worst["avg_clv"])
                           / worst["avg_clv"] * 100) if worst["avg_clv"] > 0 else 0
        else:
            best = worst = cohort_results[0] if cohort_results else {}
            improvement = 0

        result = {
            "cohorts": cohort_results,
            "comparison": {
                "best_cohort": best.get("cohort", "N/A"),
                "worst_cohort": worst.get("cohort", "N/A"),
                "clv_gap_pct": f"{improvement:.1f}%",
            },
            "trend_analysis": "최근 코호트의 CLV가 증가 추세"
            if len(cohort_results) >= 2 and
            cohort_results[-1]["avg_clv"] > cohort_results[0]["avg_clv"]
            else "최근 코호트의 CLV가 감소 추세 — 원인 분석 필요",
        }

        llm_summary = await self._llm_call(
            f"코호트별 CLV 비교 결과입니다:\n{result}\n\n"
            "코호트 간 차이의 원인과 개선 방향을 분석해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  4. 유닛 이코노믹스 (CAC vs CLV)
    # ═══════════════════════════════════════════════════════

    async def _unit_economics(self, **kwargs) -> dict[str, Any]:
        """CAC 대비 CLV 비율, 회수 기간, 채널별 ROI 분석."""
        clv = kwargs.get("clv", 300000)
        cac = kwargs.get("cac", 100000)
        monthly_revenue = kwargs.get("monthly_revenue", 25000)
        gross_margin = kwargs.get("gross_margin", 0.7)
        monthly_churn = kwargs.get("monthly_churn", 0.05)
        industry = kwargs.get("industry", "default")

        # ─── CLV:CAC 비율 ───
        ltv_cac_ratio = clv / cac if cac > 0 else float("inf")

        # ─── CAC 회수 기간 (Payback Period) ───
        monthly_margin = monthly_revenue * gross_margin
        payback_months = cac / monthly_margin if monthly_margin > 0 else float("inf")

        # ─── 단순 CLV 계산 (보조 지표) ───
        # CLV_simple = ARPU × Gross Margin / Churn Rate
        simple_clv = (monthly_revenue * gross_margin / monthly_churn
                      if monthly_churn > 0 else 0)

        # ─── 마진 조정 CLV ───
        margin_adjusted_clv = clv * gross_margin

        # ─── Gupta & Lehmann (2005) 할인 CLV ───
        discount_rate = 0.10 / 12  # 연 10% → 월 할인율
        retention_rate = 1 - monthly_churn
        dcf_clv = (monthly_revenue * gross_margin * retention_rate
                   / (1 + discount_rate - retention_rate)
                   if (1 + discount_rate - retention_rate) > 0 else 0)

        # 벤치마크 비교
        bench = self.BENCHMARKS.get(industry, {})
        bench_ratio = bench.get("good_ltv_cac_ratio", 3.0)

        # 건강도 판정
        if ltv_cac_ratio >= 5:
            health = "🟢 탁월 — CLV가 CAC의 5배 이상. 마케팅 투자 확대 가능"
        elif ltv_cac_ratio >= 3:
            health = "🟢 건강 — 업계 기준 충족. 안정적 성장 가능"
        elif ltv_cac_ratio >= 1:
            health = "🟡 주의 — CAC 회수는 되지만 마진이 얇음. 리텐션 강화 필요"
        else:
            health = "🔴 위험 — 고객 1명당 손실 발생. CAC 절감 또는 CLV 향상 시급"

        result = {
            "unit_economics": {
                "clv": round(clv),
                "cac": round(cac),
                "ltv_cac_ratio": round(ltv_cac_ratio, 2),
                "payback_months": round(payback_months, 1),
                "gross_margin": f"{gross_margin*100:.0f}%",
                "monthly_churn": f"{monthly_churn*100:.1f}%",
            },
            "clv_methods_comparison": {
                "bg_nbd_clv": round(clv),
                "simple_clv": round(simple_clv),
                "margin_adjusted_clv": round(margin_adjusted_clv),
                "dcf_clv_gupta_lehmann": round(dcf_clv),
            },
            "health_check": health,
            "benchmark": {
                "industry": industry,
                "recommended_ltv_cac": f"≥ {bench_ratio}x",
                "your_ratio": f"{ltv_cac_ratio:.1f}x",
                "gap": f"{ltv_cac_ratio - bench_ratio:+.1f}x",
            },
            "improvement_levers": self._improvement_levers(
                ltv_cac_ratio, payback_months, monthly_churn
            ),
        }

        llm_summary = await self._llm_call(
            f"유닛 이코노믹스 분석 결과입니다:\n{result}\n\n"
            "현재 사업의 수익 구조를 평가하고 개선 우선순위를 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  5. 할인 CLV (화폐의 시간가치 반영)
    # ═══════════════════════════════════════════════════════

    async def _discount_clv(self, **kwargs) -> dict[str, Any]:
        """DCF 방식으로 미래 수익의 현재가치를 계산하는 정밀 CLV."""
        monthly_revenue = kwargs.get("monthly_revenue", 50000)
        gross_margin = kwargs.get("gross_margin", 0.7)
        monthly_churn = kwargs.get("monthly_churn", 0.05)
        annual_discount_rate = kwargs.get("discount_rate", 0.10)
        horizon_months = kwargs.get("horizon_months", 60)

        retention = 1 - monthly_churn
        monthly_discount = annual_discount_rate / 12
        monthly_margin = monthly_revenue * gross_margin

        # ─── 월별 할인 현금흐름 ───
        dcf_monthly = []
        cumulative = 0.0
        survival_prob = 1.0

        for month in range(1, horizon_months + 1):
            survival_prob *= retention
            discount_factor = 1 / (1 + monthly_discount) ** month
            present_value = monthly_margin * survival_prob * discount_factor
            cumulative += present_value
            dcf_monthly.append({
                "month": month,
                "survival_rate": round(survival_prob, 4),
                "nominal_value": round(monthly_margin * survival_prob),
                "present_value": round(present_value),
                "cumulative_pv": round(cumulative),
            })

        # 무한 기간 해석적 CLV (Gupta & Lehmann 공식)
        infinite_clv = (monthly_margin * retention
                        / (1 + monthly_discount - retention)
                        if (1 + monthly_discount - retention) > 0 else 0)

        # 수렴도: horizon 기간 CLV / 무한 CLV
        convergence = cumulative / infinite_clv if infinite_clv > 0 else 1.0

        # 주요 마일스톤 (25%, 50%, 75% 도달 시점)
        milestones = {}
        for target_pct in [0.25, 0.50, 0.75]:
            target_val = infinite_clv * target_pct
            for entry in dcf_monthly:
                if entry["cumulative_pv"] >= target_val:
                    milestones[f"{int(target_pct*100)}%_month"] = entry["month"]
                    break

        # 민감도: 이탈률 ±1%p, 할인율 ±2%p
        sensitivity = []
        for churn_adj in [-0.02, -0.01, 0, 0.01, 0.02]:
            for disc_adj in [-0.02, 0, 0.02]:
                adj_churn = max(0.001, monthly_churn + churn_adj)
                adj_disc = max(0.001, annual_discount_rate + disc_adj) / 12
                adj_ret = 1 - adj_churn
                adj_clv = (monthly_margin * adj_ret
                           / (1 + adj_disc - adj_ret)
                           if (1 + adj_disc - adj_ret) > 0 else 0)
                sensitivity.append({
                    "churn": f"{adj_churn*100:.1f}%",
                    "discount": f"{(annual_discount_rate + disc_adj)*100:.0f}%",
                    "clv": round(adj_clv),
                })

        result = {
            "discount_clv": {
                "horizon_months": horizon_months,
                "horizon_clv": round(cumulative),
                "infinite_clv": round(infinite_clv),
                "convergence": f"{convergence*100:.1f}%",
            },
            "parameters": {
                "monthly_revenue": monthly_revenue,
                "gross_margin": f"{gross_margin*100:.0f}%",
                "monthly_churn": f"{monthly_churn*100:.1f}%",
                "annual_discount_rate": f"{annual_discount_rate*100:.0f}%",
            },
            "milestones": milestones,
            "monthly_projection": dcf_monthly[:12],  # 처음 12개월만 표시
            "sensitivity_analysis": sensitivity,
            "academic_reference": "Gupta & Lehmann (2005) 'Customers as Assets'",
        }

        llm_summary = await self._llm_call(
            f"할인 CLV 분석 결과입니다:\n{result}\n\n"
            "민감도 분석 결과를 포함해 CLV 극대화 전략을 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  6. 종합 분석
    # ═══════════════════════════════════════════════════════

    async def _full_analysis(self, **kwargs) -> dict[str, Any]:
        """개별 예측 + 유닛 이코노믹스 + 할인 CLV를 통합."""
        prediction = await self._predict(**kwargs)
        unit_econ = await self._unit_economics(
            clv=prediction["predictions"]["predicted_clv"],
            **{k: v for k, v in kwargs.items() if k not in ("action",)}
        )
        discount = await self._discount_clv(**kwargs)

        result = {
            "summary": "교수급 CLV 종합 분석 (BG/NBD + Gamma-Gamma + DCF)",
            "1_individual_prediction": prediction,
            "2_unit_economics": unit_econ,
            "3_discount_clv": discount,
        }

        llm_summary = await self._llm_call(
            f"CLV 종합 분석 결과입니다:\n\n"
            f"개별 예측 CLV: {prediction['predictions']['predicted_clv']:,}원\n"
            f"LTV:CAC 비율: {unit_econ['unit_economics']['ltv_cac_ratio']}\n"
            f"할인 CLV: {discount['discount_clv']['infinite_clv']:,}원\n\n"
            "전체를 종합하여 고객 가치 관리 전략 로드맵을 제안해주세요."
        )
        result["executive_summary"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  BG/NBD 핵심 수학 함수
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def _bg_nbd_p_alive(x: int, t_x: float, T: float,
                        r: float, alpha: float,
                        a: float, b: float) -> float:
        """BG/NBD P(alive | x, t_x, T) — Fader et al. (2005) Eq. 7.

        고객이 아직 '활동 중'일 확률을 계산합니다.
        """
        if x == 0:
            # 구매 이력 없으면 → 간단 근사
            p_alive = (b / (a + b - 1)) ** max(0, T - t_x) if a + b > 1 else 0.5
            return max(0.0, min(1.0, p_alive))

        # A1 = (a / (b + x - 1)) * ((alpha + T) / (alpha + t_x))^(r + x)
        try:
            ratio = (alpha + T) / (alpha + t_x) if (alpha + t_x) > 0 else 1.0
            A1 = (a / (b + x - 1)) * (ratio ** (r + x))
            p_alive = 1.0 / (1.0 + A1)
        except (OverflowError, ZeroDivisionError):
            p_alive = 0.5

        return max(0.0, min(1.0, p_alive))

    @staticmethod
    def _bg_nbd_expected_purchases(t: float, x: int, t_x: float, T: float,
                                   r: float, alpha: float,
                                   a: float, b: float) -> float:
        """BG/NBD E[X(t) | x, t_x, T] — 미래 t일간 기대 구매 횟수.

        Fader et al. (2005) Eq. 10의 간소화 버전.
        """
        # 간소화: λ 추정 (개인 구매율)
        # E[λ] ≈ (r + x) / (alpha + T)
        lambda_est = (r + x) / (alpha + T) if (alpha + T) > 0 else 0

        # P(alive) 반영
        p_alive = CustomerLtvModelTool._bg_nbd_p_alive(
            x, t_x, T, r, alpha, a, b
        )

        # E[X(t)] = λ × t × P(alive)
        expected = lambda_est * t * p_alive
        return max(0.0, expected)

    @staticmethod
    def _gamma_gamma_expected_value(x: int, monetary: float,
                                    p: float, q: float,
                                    gamma: float) -> float:
        """Gamma-Gamma E[M | x, m_x] — 기대 평균 거래금액.

        Fader & Hardie (2013) Eq. 2.
        """
        if x <= 0:
            return monetary

        # E[M | x, m_x] = (q * gamma + x * m_x) / (q + x - 1)
        expected = (q * gamma + x * monetary) / (q + x - 1) if (q + x - 1) > 0 else monetary
        return max(0.0, expected)

    # ═══════════════════════════════════════════════════════
    #  몬테카를로 시뮬레이션
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def _simulate_clv(x, t_x, T, monetary, horizon,
                      r, alpha, a, b,
                      p_gg, q_gg, gamma_gg,
                      n_sim: int = 5000) -> np.ndarray:
        """CLV 신뢰구간을 위한 몬테카를로 시뮬레이션."""
        rng = np.random.default_rng(42)

        # λ (구매율) 사후 분포: Gamma(r+x, alpha+T)
        lambda_samples = rng.gamma(r + x, 1.0 / (alpha + T), size=n_sim)

        # p (이탈 확률) 사후 분포: Beta(a, b+x)
        p_dropout = rng.beta(a, max(0.01, b + x), size=n_sim)

        # 객단가 변동: 정규분포 근사
        monetary_samples = rng.normal(monetary, monetary * 0.2, size=n_sim)
        monetary_samples = np.maximum(monetary_samples, 1000)

        # 각 시뮬레이션에서 CLV 계산
        alive_prob = 1 - p_dropout
        expected_purchases = lambda_samples * horizon * alive_prob
        clv_samples = expected_purchases * monetary_samples

        return clv_samples

    # ═══════════════════════════════════════════════════════
    #  헬퍼 함수들
    # ═══════════════════════════════════════════════════════

    def _parse_customers(self, data) -> list[dict]:
        """고객 데이터 파싱 (JSON 문자열 또는 리스트)."""
        if isinstance(data, list) and data:
            return data
        if isinstance(data, str) and data.strip():
            import json
            try:
                parsed = json.loads(data)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        # 샘플 데이터 반환 (실제 데이터 없을 때)
        return [
            {"id": "C001", "frequency": 12, "recency": 5,   "T": 365, "monetary": 85000},
            {"id": "C002", "frequency": 3,  "recency": 90,  "T": 365, "monetary": 42000},
            {"id": "C003", "frequency": 8,  "recency": 15,  "T": 300, "monetary": 63000},
            {"id": "C004", "frequency": 1,  "recency": 200, "T": 365, "monetary": 28000},
            {"id": "C005", "frequency": 20, "recency": 2,   "T": 365, "monetary": 120000},
            {"id": "C006", "frequency": 2,  "recency": 150, "T": 365, "monetary": 35000},
            {"id": "C007", "frequency": 6,  "recency": 30,  "T": 180, "monetary": 55000},
            {"id": "C008", "frequency": 15, "recency": 7,   "T": 365, "monetary": 95000},
        ]

    def _parse_cohorts(self, data) -> list[dict]:
        """코호트 데이터 파싱."""
        if isinstance(data, list) and data:
            return data
        if isinstance(data, str) and data.strip():
            import json
            try:
                parsed = json.loads(data)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        return [
            {"name": "2025-Q3", "size": 500, "avg_frequency": 2, "avg_recency": 120,
             "avg_T": 180, "avg_monetary": 35000},
            {"name": "2025-Q4", "size": 600, "avg_frequency": 3, "avg_recency": 60,
             "avg_T": 120, "avg_monetary": 42000},
            {"name": "2026-Q1", "size": 450, "avg_frequency": 4, "avg_recency": 20,
             "avg_T": 60, "avg_monetary": 48000},
        ]

    @staticmethod
    def _interpret_prediction(p_alive, expected_purchases, clv, industry):
        """예측 결과를 사람이 읽기 쉬운 해석으로 변환."""
        lines = []
        if p_alive >= 0.8:
            lines.append("이 고객은 현재 활동 중일 확률이 높습니다 (생존 확률 80%+).")
        elif p_alive >= 0.5:
            lines.append("이 고객은 활동 중일 가능성이 있지만 주의가 필요합니다.")
        else:
            lines.append("이 고객은 이탈했을 가능성이 높습니다. 재활성화 캠페인을 고려하세요.")

        if expected_purchases >= 10:
            lines.append(f"향후 1년간 약 {expected_purchases:.0f}회 구매가 예상됩니다 (고빈도 고객).")
        elif expected_purchases >= 3:
            lines.append(f"향후 1년간 약 {expected_purchases:.0f}회 구매가 예상됩니다 (중간 빈도).")
        else:
            lines.append(f"향후 1년간 약 {expected_purchases:.1f}회 구매가 예상됩니다 (저빈도).")

        return " ".join(lines)

    @staticmethod
    def _segment_strategy(segment_name: str) -> str:
        """세그먼트별 권장 전략."""
        strategies = {
            "Champions (최우수)": "VIP 혜택, 신제품 얼리엑세스, 리퍼럴 프로그램 우선 타겟",
            "Loyal (충성)": "업셀/크로스셀 기회 발굴, 로열티 포인트 적립 강화",
            "Potential (잠재 성장)": "개인화 추천, 할인 쿠폰, 사용 패턴 분석 후 맞춤 제안",
            "At Risk (관리 필요)": "재활성화 이메일, 한정 프로모션, 이탈 원인 조사",
        }
        return strategies.get(segment_name, "")

    @staticmethod
    def _check_pareto(clv_values: list) -> dict:
        """파레토 법칙(80/20) 검증."""
        sorted_clvs = sorted(clv_values, reverse=True)
        total = sum(sorted_clvs)
        top_20_count = max(1, int(len(sorted_clvs) * 0.2))
        top_20_value = sum(sorted_clvs[:top_20_count])
        top_20_pct = top_20_value / total * 100 if total > 0 else 0

        return {
            "top_20_pct_customers": f"{top_20_count}명 ({20}%)",
            "top_20_pct_clv": f"{top_20_pct:.1f}%",
            "pareto_holds": top_20_pct >= 60,
            "interpretation": (
                f"상위 20% 고객이 전체 CLV의 {top_20_pct:.0f}%를 차지합니다."
                + (" 파레토 법칙이 강하게 성립합니다." if top_20_pct >= 70 else "")
            ),
        }

    @staticmethod
    def _improvement_levers(ltv_cac: float, payback: float,
                            churn: float) -> list[dict]:
        """개선 레버 우선순위 제안."""
        levers = []
        if churn > 0.08:
            levers.append({
                "priority": 1,
                "lever": "이탈률 감소",
                "current": f"{churn*100:.1f}%/월",
                "target": f"{churn*100*0.7:.1f}%/월 (-30%)",
                "impact": "이탈률 30% 감소 시 CLV 약 43% 증가 (1/churn 관계)",
            })
        if payback > 12:
            levers.append({
                "priority": 2 if levers else 1,
                "lever": "CAC 회수 기간 단축",
                "current": f"{payback:.0f}개월",
                "target": "12개월 이하",
                "impact": "온보딩 개선, 빠른 가치 전달로 초기 이탈 방지",
            })
        if ltv_cac < 3:
            levers.append({
                "priority": len(levers) + 1,
                "lever": "CLV:CAC 비율 개선",
                "current": f"{ltv_cac:.1f}x",
                "target": "3.0x 이상",
                "impact": "마진 개선 + 업셀 + 리텐션 복합 전략 필요",
            })
        if not levers:
            levers.append({
                "priority": 1,
                "lever": "성장 투자 확대",
                "current": "건강한 유닛 이코노믹스",
                "target": "CAC 허용 범위 내에서 볼륨 확대",
                "impact": "현재 비율 유지하며 마케팅 예산 증액 가능",
            })
        return levers
