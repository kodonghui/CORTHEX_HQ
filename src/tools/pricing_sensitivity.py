"""
가격 민감도 분석 도구 — "고객이 얼마까지 낼 의향이 있나?"를 수학적으로 분석합니다.

가격을 올리면 수요가 얼마나 줄까? 최적 가격대는? 프리미엄 전략이 가능한가?
설문 데이터로 최적 가격대(OPP)와 허용 가격 범위를 과학적으로 도출합니다.

학술 근거:
  - Van Westendorp PSM (Peter Van Westendorp, 1976) — 가격 민감도 미터
  - Gabor-Granger Method (Gabor & Granger, 1966) — 직접 가격 수용도 측정
  - Price Elasticity of Demand (Marshall, 1890) — 가격 탄력성
  - Conjoint Analysis 기반 WTP 추정 (Green & Srinivasan, 1978)
  - Revenue Optimization (Phillips, 2005) — 수익 최적화 모델

사용 방법:
  - action="psm"           : Van Westendorp 가격 민감도 미터
  - action="gabor_granger"  : Gabor-Granger 가격 수용도
  - action="elasticity"     : 가격 탄력성 계산
  - action="optimize"       : 수익 최적화 가격 탐색
  - action="tier"           : 가격 티어(단계) 설계
  - action="full"           : 종합 분석

필요 환경변수: 없음
필요 라이브러리: numpy
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.pricing_sensitivity")


class PricingSensitivityTool(BaseTool):
    """교수급 가격 민감도 분석 도구."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        action = kwargs.get("action", "full")
        dispatch = {
            "psm": self._psm,
            "gabor_granger": self._gabor_granger,
            "elasticity": self._elasticity,
            "optimize": self._optimize,
            "tier": self._tier_design,
            "full": self._full_analysis,
        }
        handler = dispatch.get(action)
        if not handler:
            return {"error": f"지원하지 않는 action: {action}. "
                    f"가능한 값: {list(dispatch.keys())}"}
        return await handler(**kwargs)

    # ═══════════════════════════════════════════════════════
    #  1. Van Westendorp PSM (Price Sensitivity Meter)
    # ═══════════════════════════════════════════════════════

    async def _psm(self, **kwargs) -> dict[str, Any]:
        """Van Westendorp 가격 민감도 미터.

        4가지 질문의 누적 분포를 교차시켜 최적 가격대를 도출합니다.
        - 너무 싸다 (Too Cheap): 품질 의심이 가는 가격
        - 싸다 (Cheap/Bargain): 괜찮은 가격
        - 비싸다 (Expensive): 비싸지만 고려할 수 있는 가격
        - 너무 비싸다 (Too Expensive): 절대 안 살 가격
        """
        # 설문 데이터 파싱
        too_cheap = self._parse_prices(kwargs.get("too_cheap", ""))
        cheap = self._parse_prices(kwargs.get("cheap", ""))
        expensive = self._parse_prices(kwargs.get("expensive", ""))
        too_expensive = self._parse_prices(kwargs.get("too_expensive", ""))

        # 샘플 데이터 (실제 데이터 없을 때)
        if not too_cheap:
            rng = np.random.default_rng(42)
            too_cheap = sorted(rng.normal(15000, 5000, 200).clip(1000).astype(int).tolist())
            cheap = sorted(rng.normal(25000, 6000, 200).clip(5000).astype(int).tolist())
            expensive = sorted(rng.normal(45000, 8000, 200).clip(15000).astype(int).tolist())
            too_expensive = sorted(rng.normal(60000, 10000, 200).clip(20000).astype(int).tolist())

        # 가격 범위 설정
        all_prices = too_cheap + cheap + expensive + too_expensive
        price_range = np.linspace(min(all_prices), max(all_prices), 200)

        # 누적 분포 함수 (CDF) 계산
        n = len(too_cheap)
        cdf_too_cheap = np.array([sum(1 for x in too_cheap if x <= p) / n for p in price_range])
        cdf_cheap = np.array([sum(1 for x in cheap if x <= p) / n for p in price_range])
        cdf_expensive = np.array([sum(1 for x in expensive if x <= p) / n for p in price_range])
        cdf_too_expensive = np.array([sum(1 for x in too_expensive if x <= p) / n for p in price_range])

        # PSM 교차점 계산
        # 1 - CDF(too_cheap) = "너무 싸지 않다" 누적
        not_too_cheap = 1 - cdf_too_cheap
        not_cheap = 1 - cdf_cheap

        # OPP (Optimal Price Point): "너무 비싸다" CDF와 "너무 싸다" 역CDF 교차
        opp = self._find_intersection(price_range, cdf_too_expensive, not_too_cheap)

        # IDP (Indifference Price Point): "비싸다" CDF와 "싸다" 역CDF 교차
        idp = self._find_intersection(price_range, cdf_expensive, not_cheap)

        # PMC (Point of Marginal Cheapness): "너무 싸다" 역CDF와 "비싸다" CDF 교차
        pmc = self._find_intersection(price_range, not_too_cheap, cdf_expensive)

        # PME (Point of Marginal Expensiveness): "너무 비싸다" CDF와 "싸다" 역CDF 교차
        pme = self._find_intersection(price_range, cdf_too_expensive, not_cheap)

        # 허용 가격 범위
        acceptable_range = (round(pmc), round(pme))

        result = {
            "method": "Van Westendorp Price Sensitivity Meter (1976)",
            "sample_size": n,
            "key_prices": {
                "OPP_optimal_price": round(opp),
                "OPP_description": "최적 가격 — '너무 비싸다'와 '너무 싸다'의 교차점",
                "IDP_indifference": round(idp),
                "IDP_description": "무차별 가격 — '비싸다'와 '싸다'의 교차점",
                "PMC_marginal_cheap": round(pmc),
                "PMC_description": "한계 저가 — 이보다 싸면 품질 의심",
                "PME_marginal_expensive": round(pme),
                "PME_description": "한계 고가 — 이보다 비싸면 구매 거부",
            },
            "acceptable_range": {
                "min": acceptable_range[0],
                "max": acceptable_range[1],
                "range_width": acceptable_range[1] - acceptable_range[0],
                "interpretation": f"{acceptable_range[0]:,}원 ~ {acceptable_range[1]:,}원이 수용 가능 범위",
            },
            "distribution_stats": {
                "too_cheap": {"mean": round(np.mean(too_cheap)), "median": round(np.median(too_cheap))},
                "cheap": {"mean": round(np.mean(cheap)), "median": round(np.median(cheap))},
                "expensive": {"mean": round(np.mean(expensive)), "median": round(np.median(expensive))},
                "too_expensive": {"mean": round(np.mean(too_expensive)), "median": round(np.median(too_expensive))},
            },
            "pricing_strategy": self._psm_strategy(opp, idp, pmc, pme),
        }

        llm_summary = await self._llm_call(
            f"Van Westendorp PSM 분석 결과입니다:\n{result}\n\n"
            "최적 가격 전략과 포지셔닝을 구체적으로 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  2. Gabor-Granger 가격 수용도
    # ═══════════════════════════════════════════════════════

    async def _gabor_granger(self, **kwargs) -> dict[str, Any]:
        """Gabor-Granger 직접 가격 수용도 분석.

        여러 가격점에서 "이 가격에 구매하시겠습니까?" 응답률 분석.
        """
        prices_str = kwargs.get("prices", "10000,20000,30000,40000,50000,60000")
        acceptance_str = kwargs.get("acceptance_rates", "95,85,70,50,30,10")

        prices = [float(x.strip()) for x in prices_str.split(",")]
        acceptance = [float(x.strip()) / 100 if float(x.strip()) > 1
                      else float(x.strip()) for x in acceptance_str.split(",")]

        if len(prices) != len(acceptance):
            return {"error": "prices와 acceptance_rates의 개수가 일치해야 합니다."}

        # 수익 곡선: Revenue = Price × Acceptance Rate
        revenues = [p * a for p, a in zip(prices, acceptance)]
        max_revenue_idx = int(np.argmax(revenues))
        optimal_price = prices[max_revenue_idx]
        optimal_acceptance = acceptance[max_revenue_idx]
        max_revenue = revenues[max_revenue_idx]

        # 가격 탄력성 (각 구간)
        elasticities = []
        for i in range(1, len(prices)):
            pct_q_change = (acceptance[i] - acceptance[i-1]) / acceptance[i-1]
            pct_p_change = (prices[i] - prices[i-1]) / prices[i-1]
            if pct_p_change != 0:
                e = pct_q_change / pct_p_change
                elasticities.append({
                    "from_price": prices[i-1],
                    "to_price": prices[i],
                    "elasticity": round(e, 2),
                    "type": "탄력적" if abs(e) > 1 else "비탄력적",
                })

        # 가격 데이터 테이블
        price_table = []
        for i, (p, a, r) in enumerate(zip(prices, acceptance, revenues)):
            price_table.append({
                "price": round(p),
                "acceptance_rate": f"{a*100:.0f}%",
                "estimated_revenue": round(r),
                "is_optimal": i == max_revenue_idx,
            })

        result = {
            "method": "Gabor-Granger Method (1966)",
            "optimal_price": round(optimal_price),
            "optimal_acceptance": f"{optimal_acceptance*100:.0f}%",
            "max_revenue_per_customer": round(max_revenue),
            "price_table": price_table,
            "elasticities": elasticities,
            "recommendation": (
                f"최적 가격은 {optimal_price:,.0f}원 (수용률 {optimal_acceptance*100:.0f}%, "
                f"고객당 기대 수익 {max_revenue:,.0f}원)"
            ),
        }

        llm_summary = await self._llm_call(
            f"Gabor-Granger 가격 수용도 분석 결과입니다:\n{result}\n\n"
            "가격 설정과 수요 예측에 대한 전략을 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  3. 가격 탄력성 분석
    # ═══════════════════════════════════════════════════════

    async def _elasticity(self, **kwargs) -> dict[str, Any]:
        """가격 탄력성(PED) 분석 — Marshall (1890)."""
        current_price = kwargs.get("current_price", 30000)
        current_quantity = kwargs.get("current_quantity", 1000)
        new_price = kwargs.get("new_price", 35000)
        new_quantity = kwargs.get("new_quantity", 850)

        # 점탄력성 (Point Elasticity)
        pct_q = (new_quantity - current_quantity) / current_quantity
        pct_p = (new_price - current_price) / current_price
        point_elasticity = pct_q / pct_p if pct_p != 0 else 0

        # 호탄력성 (Arc Elasticity) — 중점법
        avg_q = (current_quantity + new_quantity) / 2
        avg_p = (current_price + new_price) / 2
        arc_elasticity = ((new_quantity - current_quantity) / avg_q /
                          ((new_price - current_price) / avg_p)
                          if (new_price - current_price) != 0 else 0)

        # 수익 영향
        current_revenue = current_price * current_quantity
        new_revenue = new_price * new_quantity
        revenue_change = new_revenue - current_revenue
        revenue_change_pct = revenue_change / current_revenue * 100 if current_revenue else 0

        # 최적 가격 추정 (선형 수요 가정)
        # Q = a - bP, 수익 R = PQ = aP - bP²
        # dR/dP = a - 2bP = 0 → P* = a/(2b)
        if current_price != new_price:
            b = -(new_quantity - current_quantity) / (new_price - current_price)
            a = current_quantity + b * current_price
            if b > 0:
                optimal_price = a / (2 * b)
                optimal_quantity = a - b * optimal_price
                optimal_revenue = optimal_price * optimal_quantity
            else:
                optimal_price = new_price  # 수요가 가격에 양의 반응 (기펜재?)
                optimal_quantity = new_quantity
                optimal_revenue = new_revenue
        else:
            optimal_price = current_price
            optimal_quantity = current_quantity
            optimal_revenue = current_revenue

        # 탄력성 해석
        abs_e = abs(point_elasticity)
        if abs_e > 1:
            interpretation = "탄력적 — 가격 변화에 수요가 민감. 가격 인하 시 매출 증가 가능"
            strategy = "가격 인하 전략 또는 프로모션이 효과적"
        elif abs_e == 1:
            interpretation = "단위 탄력적 — 가격 변화와 수요 변화가 정비례"
            strategy = "현재 가격이 수익 극대화 근처"
        else:
            interpretation = "비탄력적 — 가격 변화에 수요가 둔감. 가격 인상 시 매출 증가 가능"
            strategy = "가격 인상 여력 있음 (프리미엄 전략 가능)"

        # 시뮬레이션 (±10%, ±20%, ±30%)
        simulations = []
        for pct in [-30, -20, -10, 0, 10, 20, 30]:
            sim_price = current_price * (1 + pct / 100)
            # 선형 수요 가정
            sim_quantity = current_quantity * (1 + point_elasticity * pct / 100)
            sim_quantity = max(0, sim_quantity)
            sim_revenue = sim_price * sim_quantity
            simulations.append({
                "price_change": f"{pct:+d}%",
                "price": round(sim_price),
                "est_quantity": round(sim_quantity),
                "est_revenue": round(sim_revenue),
                "revenue_vs_current": f"{(sim_revenue / current_revenue - 1) * 100:+.1f}%"
                if current_revenue > 0 else "N/A",
            })

        result = {
            "method": "Price Elasticity of Demand (Marshall 1890)",
            "elasticity": {
                "point_elasticity": round(point_elasticity, 3),
                "arc_elasticity": round(arc_elasticity, 3),
                "absolute_value": round(abs_e, 3),
                "type": "탄력적" if abs_e > 1 else "단위탄력적" if abs_e == 1 else "비탄력적",
            },
            "interpretation": interpretation,
            "strategy": strategy,
            "revenue_impact": {
                "current": round(current_revenue),
                "new": round(new_revenue),
                "change": round(revenue_change),
                "change_pct": f"{revenue_change_pct:+.1f}%",
            },
            "optimal_price_estimate": {
                "price": round(optimal_price),
                "quantity": round(optimal_quantity),
                "revenue": round(optimal_revenue),
                "note": "선형 수요 가정 하의 추정치",
            },
            "price_simulations": simulations,
        }

        llm_summary = await self._llm_call(
            f"가격 탄력성 분석 결과입니다:\n{result}\n\n"
            "탄력성 기반 가격 전략을 구체적으로 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  4. 수익 최적화 가격 탐색
    # ═══════════════════════════════════════════════════════

    async def _optimize(self, **kwargs) -> dict[str, Any]:
        """다양한 시나리오에서 수익을 최대화하는 가격을 탐색."""
        base_price = kwargs.get("base_price", 30000)
        base_demand = kwargs.get("base_demand", 1000)
        variable_cost = kwargs.get("variable_cost", 10000)
        fixed_cost = kwargs.get("fixed_cost", 5000000)
        elasticity = kwargs.get("elasticity", -1.5)

        # 가격 범위 탐색 (기본가의 50%~200%)
        price_range = np.linspace(base_price * 0.5, base_price * 2.0, 100)

        results = []
        for price in price_range:
            # 수요 예측 (일정 탄력성 모델: Q = Q0 × (P/P0)^e)
            demand = base_demand * (price / base_price) ** elasticity
            demand = max(0, demand)

            revenue = price * demand
            total_cost = fixed_cost + variable_cost * demand
            profit = revenue - total_cost
            margin = profit / revenue if revenue > 0 else 0

            results.append({
                "price": round(float(price)),
                "demand": round(float(demand)),
                "revenue": round(float(revenue)),
                "profit": round(float(profit)),
                "margin": round(float(margin), 3),
            })

        # 최대 수익 가격
        max_revenue_entry = max(results, key=lambda x: x["revenue"])
        # 최대 이익 가격
        max_profit_entry = max(results, key=lambda x: x["profit"])
        # 손익분기점
        bep_entries = [r for r in results if r["profit"] >= 0]
        bep_price = bep_entries[0]["price"] if bep_entries else None

        result = {
            "method": "Revenue & Profit Optimization (Phillips 2005)",
            "parameters": {
                "base_price": base_price,
                "base_demand": base_demand,
                "variable_cost": variable_cost,
                "fixed_cost": fixed_cost,
                "price_elasticity": elasticity,
            },
            "optimal_prices": {
                "max_revenue": {
                    "price": max_revenue_entry["price"],
                    "demand": max_revenue_entry["demand"],
                    "revenue": max_revenue_entry["revenue"],
                    "profit": max_revenue_entry["profit"],
                },
                "max_profit": {
                    "price": max_profit_entry["price"],
                    "demand": max_profit_entry["demand"],
                    "revenue": max_profit_entry["revenue"],
                    "profit": max_profit_entry["profit"],
                },
                "breakeven_price": bep_price,
            },
            "profit_curve": results[::10],  # 10개 간격으로 표시
            "recommendation": self._optimize_recommendation(
                max_revenue_entry, max_profit_entry, base_price
            ),
        }

        llm_summary = await self._llm_call(
            f"수익 최적화 분석 결과입니다:\n{result}\n\n"
            "최적 가격 전략과 리스크를 분석해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  5. 가격 티어 설계
    # ═══════════════════════════════════════════════════════

    async def _tier_design(self, **kwargs) -> dict[str, Any]:
        """가격 티어(Free/Basic/Pro/Enterprise) 설계."""
        base_price = kwargs.get("base_price", 30000)
        product_name = kwargs.get("product_name", "서비스")
        features_str = kwargs.get("features", "")

        features = [f.strip() for f in features_str.split(",") if f.strip()] if features_str else [
            "기본 기능", "고급 분석", "API 접근", "우선 지원",
            "맞춤 보고서", "전담 매니저", "SLA 보장", "무제한 사용"
        ]

        # 가격 심리학 기반 티어 설계
        tiers = [
            {
                "name": "Free",
                "name_ko": "무료",
                "price": 0,
                "purpose": "진입 장벽 제거, 바이럴 유도 (Freemium)",
                "features": features[:2],
                "psychology": "앵커링 효과 — 무료 체험이 유료 전환의 기준점이 됨",
                "target": "탐색 단계 사용자",
            },
            {
                "name": "Basic",
                "name_ko": "베이직",
                "price": round(base_price * 0.6),
                "purpose": "가격 민감 고객 확보, 볼륨 확대",
                "features": features[:4],
                "psychology": "미끼 효과(Decoy) — Pro 대비 가치 차이를 느끼게 함",
                "target": "개인/소규모 사용자",
            },
            {
                "name": "Pro",
                "name_ko": "프로",
                "price": round(base_price),
                "purpose": "주력 수익원 (가장 많이 팔려야 할 플랜)",
                "features": features[:6],
                "psychology": "타협 효과(Compromise) — 3개 중 가운데를 가장 많이 선택",
                "target": "성장 중인 팀/기업",
                "is_recommended": True,
            },
            {
                "name": "Enterprise",
                "name_ko": "엔터프라이즈",
                "price": round(base_price * 2.5),
                "purpose": "앵커링 — 높은 가격이 Pro를 합리적으로 보이게 함",
                "features": features,
                "psychology": "앵커링 효과 — 최고가가 다른 플랜을 저렴하게 느끼게 함",
                "target": "대기업/기관",
            },
        ]

        # 수익 시뮬레이션 (가정: 고객 1000명)
        distribution = {"Free": 0.50, "Basic": 0.20, "Pro": 0.22, "Enterprise": 0.08}
        total_customers = 1000
        revenue_sim = []
        total_revenue = 0
        for tier in tiers:
            pct = distribution.get(tier["name"], 0)
            customers = round(total_customers * pct)
            rev = customers * tier["price"]
            total_revenue += rev
            revenue_sim.append({
                "tier": tier["name"],
                "price": tier["price"],
                "customers": customers,
                "pct": f"{pct*100:.0f}%",
                "revenue": rev,
            })

        # ARPU 계산
        paying = sum(r["customers"] for r in revenue_sim if r["price"] > 0)
        arpu = total_revenue / paying if paying > 0 else 0

        result = {
            "product": product_name,
            "tiers": tiers,
            "pricing_psychology": {
                "anchoring": "Enterprise가 Pro를 합리적으로 보이게 하는 앵커 역할",
                "compromise": "3~4개 옵션 중 가운데(Pro)를 가장 많이 선택하는 심리",
                "decoy": "Basic이 Pro 대비 가치 열등해 Pro 선택 유도",
                "charm_pricing": f"끝자리를 9,900원으로 설정하면 인지 가격 낮아짐",
            },
            "revenue_simulation": {
                "total_customers": total_customers,
                "by_tier": revenue_sim,
                "total_monthly_revenue": total_revenue,
                "arpu": round(arpu),
                "free_to_paid_rate": f"{(1 - distribution['Free'])*100:.0f}%",
            },
        }

        llm_summary = await self._llm_call(
            f"가격 티어 설계 결과입니다 (제품: {product_name}):\n{result}\n\n"
            "각 티어의 적정성을 평가하고 개선 제안을 해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  6. 종합 분석
    # ═══════════════════════════════════════════════════════

    async def _full_analysis(self, **kwargs) -> dict[str, Any]:
        """PSM + Gabor-Granger + 탄력성 + 최적화를 통합."""
        psm = await self._psm(**kwargs)
        gabor = await self._gabor_granger(**kwargs)
        elasticity = await self._elasticity(**kwargs)
        optimize = await self._optimize(**kwargs)

        result = {
            "summary": "교수급 가격 민감도 종합 분석",
            "1_van_westendorp_psm": psm,
            "2_gabor_granger": gabor,
            "3_price_elasticity": elasticity,
            "4_revenue_optimization": optimize,
        }

        llm_summary = await self._llm_call(
            f"가격 민감도 종합 분석입니다:\n\n"
            f"PSM 최적 가격: {psm['key_prices']['OPP_optimal_price']:,}원\n"
            f"Gabor-Granger 최적: {gabor['optimal_price']:,}원\n"
            f"수익 최대화 가격: {optimize['optimal_prices']['max_profit']['price']:,}원\n\n"
            "세 가지 방법의 결과를 종합하여 최종 가격 전략을 제안해주세요."
        )
        result["executive_summary"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  헬퍼 함수
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def _parse_prices(data) -> list[float]:
        """가격 데이터 파싱 (쉼표 구분 문자열 또는 리스트)."""
        if isinstance(data, list) and data:
            return [float(x) for x in data]
        if isinstance(data, str) and data.strip():
            try:
                return [float(x.strip()) for x in data.split(",") if x.strip()]
            except ValueError:
                return []
        return []

    @staticmethod
    def _find_intersection(x: np.ndarray, y1: np.ndarray,
                           y2: np.ndarray) -> float:
        """두 곡선의 교차점 찾기 (선형 보간)."""
        diff = y1 - y2
        sign_changes = np.where(np.diff(np.sign(diff)))[0]
        if len(sign_changes) == 0:
            return float(x[len(x) // 2])  # 교차점 없으면 중간값

        idx = sign_changes[0]
        # 선형 보간
        if diff[idx + 1] - diff[idx] != 0:
            frac = -diff[idx] / (diff[idx + 1] - diff[idx])
            return float(x[idx] + frac * (x[idx + 1] - x[idx]))
        return float(x[idx])

    @staticmethod
    def _psm_strategy(opp, idp, pmc, pme) -> dict:
        """PSM 결과 기반 전략 제안."""
        strategies = []
        if opp < idp:
            strategies.append(
                f"최적가({opp:,.0f}원)가 무차별가({idp:,.0f}원)보다 낮음 "
                "→ 가격 인상 여력 있음"
            )
        else:
            strategies.append(
                f"최적가({opp:,.0f}원)가 무차별가({idp:,.0f}원)보다 높음 "
                "→ 가격에 민감한 시장, 프로모션 전략 필요"
            )

        range_width = pme - pmc
        if range_width > opp * 0.5:
            strategies.append("허용 범위가 넓음 → 세분화된 가격 티어 전략 가능")
        else:
            strategies.append("허용 범위가 좁음 → 가격 차별화 어려움, 가치 차별화에 집중")

        return {"strategies": strategies, "recommended_price_range": f"{pmc:,.0f}원 ~ {pme:,.0f}원"}

    @staticmethod
    def _optimize_recommendation(max_rev, max_prof, base) -> str:
        """최적화 결과 기반 추천."""
        if max_prof["price"] > base * 1.1:
            return (f"현재 가격({base:,}원) 대비 이익 최적 가격이 "
                    f"{max_prof['price']:,}원으로 높음 → 가격 인상 권장")
        elif max_prof["price"] < base * 0.9:
            return (f"현재 가격({base:,}원) 대비 이익 최적 가격이 "
                    f"{max_prof['price']:,}원으로 낮음 → 가격 인하 + 볼륨 전략 권장")
        else:
            return f"현재 가격({base:,}원)이 이익 최적 가격 근처 → 현 가격 유지 권장"
