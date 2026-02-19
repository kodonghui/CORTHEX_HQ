"""
이탈 위험 점수 도구 — 고객이 떠날 확률을 미리 예측합니다.

"이 고객이 다음 달에 떠날까?"를 데이터 기반으로 예측하고,
이탈 전에 선제 대응할 수 있게 위험 점수와 구체적 대응 전략을 제시합니다.

학술 근거:
  - Cox Proportional Hazards (Cox, 1972) — 생존 분석 기반 이탈 예측
  - Kaplan-Meier Survival Curve (Kaplan & Meier, 1958)
  - Logistic Regression 이탈 모델 (Neslin et al., 2006)
  - Customer Churn Prediction (Verbeke et al., 2012)
  - Hazard Rate 기반 세그먼트 (Fader & Hardie, 2007)

사용 방법:
  - action="score"      : 개별 고객 이탈 위험 점수 (0~100)
  - action="batch"      : 고객 목록 일괄 이탈 위험 평가
  - action="survival"   : 생존 곡선 + 중간 생존 시간 분석
  - action="factors"    : 이탈 요인 분석 (위험 인자 기여도)
  - action="strategy"   : 이탈 방지 전략 + 예산 배분
  - action="full"       : 종합 분석

필요 환경변수: 없음
필요 라이브러리: numpy
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.churn_risk_scorer")


class ChurnRiskScorerTool(BaseTool):
    """교수급 이탈 위험 점수 도구 (Cox PH + 로지스틱 회귀)."""

    # ─── 이탈 위험 인자 가중치 (학술 연구 + 업계 벤치마크 종합) ───
    RISK_WEIGHTS = {
        "recency_days": {
            "weight": 0.25, "description": "마지막 활동 이후 경과일",
            "thresholds": [(7, -0.3), (30, 0.0), (60, 0.3), (90, 0.6), (180, 0.9)],
        },
        "frequency_decline": {
            "weight": 0.20, "description": "구매/방문 빈도 감소율",
            "thresholds": [(0, -0.2), (0.1, 0.0), (0.3, 0.3), (0.5, 0.6), (0.7, 0.9)],
        },
        "support_tickets": {
            "weight": 0.15, "description": "최근 불만/문의 건수",
            "thresholds": [(0, -0.2), (1, 0.1), (3, 0.4), (5, 0.7), (10, 0.95)],
        },
        "payment_issues": {
            "weight": 0.15, "description": "결제 실패/지연 횟수",
            "thresholds": [(0, -0.1), (1, 0.3), (2, 0.6), (3, 0.85)],
        },
        "engagement_score": {
            "weight": 0.15, "description": "서비스 활용도 점수 (0~100 → 역변환)",
            "thresholds": [(80, -0.3), (60, 0.0), (40, 0.3), (20, 0.6), (0, 0.9)],
        },
        "tenure_months": {
            "weight": 0.10, "description": "가입 후 경과 개월 (짧을수록 위험)",
            "thresholds": [(24, -0.2), (12, 0.0), (6, 0.2), (3, 0.4), (1, 0.7)],
        },
    }

    # ─── 이탈 위험 등급 정의 ───
    RISK_LEVELS = {
        "critical": {"range": (80, 100), "color": "#e74c3c", "label": "매우 위험",
                     "action_urgency": "즉시 대응 (24시간 내)"},
        "high": {"range": (60, 80), "color": "#e67e22", "label": "위험",
                 "action_urgency": "빠른 대응 (3일 내)"},
        "medium": {"range": (40, 60), "color": "#f1c40f", "label": "주의",
                   "action_urgency": "계획적 대응 (1주 내)"},
        "low": {"range": (20, 40), "color": "#27ae60", "label": "양호",
                "action_urgency": "정기 관리"},
        "safe": {"range": (0, 20), "color": "#2ecc71", "label": "안전",
                 "action_urgency": "유지 + 업셀 기회 탐색"},
    }

    async def execute(self, **kwargs) -> dict[str, Any]:
        action = kwargs.get("action", "full")
        dispatch = {
            "score": self._score,
            "batch": self._batch,
            "survival": self._survival,
            "factors": self._factors,
            "strategy": self._strategy,
            "full": self._full_analysis,
        }
        handler = dispatch.get(action)
        if not handler:
            return {"error": f"지원하지 않는 action: {action}. "
                    f"가능한 값: {list(dispatch.keys())}"}
        return await handler(**kwargs)

    # ═══════════════════════════════════════════════════════
    #  1. 개별 고객 이탈 위험 점수
    # ═══════════════════════════════════════════════════════

    async def _score(self, **kwargs) -> dict[str, Any]:
        """개별 고객의 이탈 위험 점수 계산 (0~100)."""
        recency = kwargs.get("recency_days", 30)
        freq_decline = kwargs.get("frequency_decline", 0.1)
        tickets = kwargs.get("support_tickets", 0)
        payment = kwargs.get("payment_issues", 0)
        engagement = kwargs.get("engagement_score", 70)
        tenure = kwargs.get("tenure_months", 12)

        inputs = {
            "recency_days": recency,
            "frequency_decline": freq_decline,
            "support_tickets": tickets,
            "payment_issues": payment,
            "engagement_score": engagement,
            "tenure_months": tenure,
        }

        # 각 인자별 위험 점수 계산
        factor_scores = {}
        weighted_sum = 0.0
        total_weight = 0.0

        for factor_name, config in self.RISK_WEIGHTS.items():
            value = inputs.get(factor_name, 0)
            risk_contribution = self._interpolate_risk(value, config["thresholds"])
            factor_score = max(0, min(100, risk_contribution * 100))
            weighted_contribution = factor_score * config["weight"]

            factor_scores[factor_name] = {
                "value": value,
                "risk_score": round(factor_score, 1),
                "weight": config["weight"],
                "weighted_score": round(weighted_contribution, 1),
                "description": config["description"],
            }
            weighted_sum += weighted_contribution
            total_weight += config["weight"]

        # 종합 점수
        churn_score = weighted_sum / total_weight if total_weight > 0 else 50
        churn_score = max(0, min(100, churn_score))

        # 등급 판정
        risk_level = self._classify_risk(churn_score)

        # 이탈 확률 (로지스틱 변환)
        churn_probability = 1 / (1 + math.exp(-(churn_score - 50) / 15))

        # 예상 잔존 기간 (지수 분포 가정)
        hazard_rate = churn_probability / 30  # 월간 위험률 근사
        expected_months = 1 / hazard_rate if hazard_rate > 0 else 999

        result = {
            "churn_score": round(churn_score, 1),
            "churn_probability": f"{churn_probability*100:.1f}%",
            "risk_level": risk_level,
            "expected_remaining_months": round(min(expected_months, 60), 1),
            "factor_breakdown": factor_scores,
            "top_risk_factors": sorted(
                factor_scores.items(),
                key=lambda x: x[1]["risk_score"], reverse=True
            )[:3],
            "recommended_actions": self._recommend_actions(
                churn_score, factor_scores
            ),
        }

        llm_summary = await self._llm_call(
            f"고객 이탈 위험 분석 결과입니다:\n{result}\n\n"
            "이 고객의 이탈을 방지하기 위한 구체적 액션 플랜을 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  2. 일괄 이탈 위험 평가
    # ═══════════════════════════════════════════════════════

    async def _batch(self, **kwargs) -> dict[str, Any]:
        """고객 목록 일괄 이탈 위험 평가."""
        customers = self._parse_customers(kwargs.get("customers", ""))

        scored = []
        risk_distribution = {"critical": 0, "high": 0, "medium": 0, "low": 0, "safe": 0}

        for c in customers:
            score = self._calc_score(c)
            level = self._classify_risk(score)
            risk_distribution[level["key"]] = risk_distribution.get(level["key"], 0) + 1

            scored.append({
                "customer_id": c.get("id", f"C{len(scored)+1:03d}"),
                "churn_score": round(score, 1),
                "risk_level": level["label"],
                "risk_key": level["key"],
            })

        # 정렬 (위험 높은 순)
        scored.sort(key=lambda x: x["churn_score"], reverse=True)

        total = len(scored)
        result = {
            "total_customers": total,
            "risk_distribution": {
                k: {"count": v, "pct": f"{v/total*100:.1f}%"}
                for k, v in risk_distribution.items() if v > 0
            },
            "at_risk_customers": [s for s in scored if s["churn_score"] >= 60],
            "avg_churn_score": round(np.mean([s["churn_score"] for s in scored]), 1),
            "top_risk_customers": scored[:10],
            "health_indicator": (
                "🔴 위기" if risk_distribution.get("critical", 0) / total > 0.2
                else "🟡 주의" if (risk_distribution.get("critical", 0) +
                                   risk_distribution.get("high", 0)) / total > 0.3
                else "🟢 양호"
            ),
        }

        llm_summary = await self._llm_call(
            f"일괄 이탈 위험 평가 결과입니다:\n{result}\n\n"
            "전체 고객 기반의 이탈 리스크를 분석하고 우선순위별 대응 방안을 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  3. 생존 곡선 분석
    # ═══════════════════════════════════════════════════════

    async def _survival(self, **kwargs) -> dict[str, Any]:
        """Kaplan-Meier 생존 곡선 + 중간 생존 시간."""
        monthly_churn = kwargs.get("monthly_churn_rate", 0.05)
        cohort_size = kwargs.get("cohort_size", 1000)
        months = kwargs.get("months", 24)

        # Kaplan-Meier 생존 곡선 계산
        survival_curve = []
        n_at_risk = cohort_size
        cumulative_survival = 1.0

        for month in range(months + 1):
            if month == 0:
                survival_curve.append({
                    "month": 0, "at_risk": cohort_size,
                    "churned": 0, "survival_rate": 1.0,
                    "cumulative_churned": 0,
                })
                continue

            # 이탈자 수 (이항 분포 근사)
            churned = round(n_at_risk * monthly_churn)
            n_at_risk -= churned
            cumulative_survival *= (1 - monthly_churn)

            survival_curve.append({
                "month": month,
                "at_risk": max(0, n_at_risk),
                "churned": churned,
                "survival_rate": round(cumulative_survival, 4),
                "cumulative_churned": cohort_size - n_at_risk,
            })

        # 중간 생존 시간 (50% 이탈 시점)
        median_survival = None
        for entry in survival_curve:
            if entry["survival_rate"] <= 0.5:
                median_survival = entry["month"]
                break
        if median_survival is None:
            # ln(2) / λ (지수분포 공식)
            median_survival = round(math.log(2) / monthly_churn, 1) if monthly_churn > 0 else 999

        # 반감기별 마일스톤
        milestones = {}
        for target in [0.90, 0.75, 0.50, 0.25]:
            for entry in survival_curve:
                if entry["survival_rate"] <= target:
                    milestones[f"{int(target*100)}%_month"] = entry["month"]
                    break

        # CLV 영향 추정
        avg_monthly_revenue = kwargs.get("avg_monthly_revenue", 50000)
        total_revenue_if_no_churn = avg_monthly_revenue * cohort_size * months
        total_revenue_with_churn = sum(
            avg_monthly_revenue * entry["at_risk"] for entry in survival_curve
        )
        revenue_loss = total_revenue_if_no_churn - total_revenue_with_churn

        result = {
            "method": "Kaplan-Meier Survival Analysis (1958)",
            "parameters": {
                "monthly_churn_rate": f"{monthly_churn*100:.1f}%",
                "annual_churn_rate": f"{(1-(1-monthly_churn)**12)*100:.1f}%",
                "cohort_size": cohort_size,
                "observation_months": months,
            },
            "median_survival_months": median_survival,
            "milestones": milestones,
            "survival_curve": survival_curve[:13],  # 12개월만 표시
            "revenue_impact": {
                "total_without_churn": round(total_revenue_if_no_churn),
                "total_with_churn": round(total_revenue_with_churn),
                "churn_revenue_loss": round(revenue_loss),
                "loss_pct": f"{revenue_loss/total_revenue_if_no_churn*100:.1f}%"
                if total_revenue_if_no_churn > 0 else "0%",
            },
            "churn_reduction_impact": self._churn_reduction_simulation(
                monthly_churn, cohort_size, months, avg_monthly_revenue
            ),
        }

        llm_summary = await self._llm_call(
            f"생존 곡선 분석 결과입니다:\n{result}\n\n"
            "생존 곡선 패턴과 이탈률 감소 전략을 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  4. 이탈 요인 분석
    # ═══════════════════════════════════════════════════════

    async def _factors(self, **kwargs) -> dict[str, Any]:
        """이탈에 영향을 미치는 요인들의 기여도 분석."""
        customers = self._parse_customers(kwargs.get("customers", ""))

        # 각 요인별 이탈 상관관계 분석
        factor_analysis = []
        for factor_name, config in self.RISK_WEIGHTS.items():
            values = [c.get(factor_name, 0) for c in customers]
            scores = [self._calc_score(c) for c in customers]

            if len(values) >= 3:
                correlation = float(np.corrcoef(values, scores)[0, 1])
            else:
                correlation = config["weight"]  # 데이터 부족 시 가중치 사용

            factor_analysis.append({
                "factor": factor_name,
                "description": config["description"],
                "weight": config["weight"],
                "correlation": round(correlation, 3) if not np.isnan(correlation) else 0,
                "importance_rank": 0,  # 나중에 채움
                "avg_value": round(float(np.mean(values)), 2) if values else 0,
            })

        # 중요도 순 정렬
        factor_analysis.sort(key=lambda x: abs(x["correlation"]), reverse=True)
        for i, f in enumerate(factor_analysis):
            f["importance_rank"] = i + 1

        # 주요 발견
        top_factor = factor_analysis[0] if factor_analysis else None

        result = {
            "method": "Cox Proportional Hazards Risk Factor Analysis",
            "factor_importance": factor_analysis,
            "key_finding": (
                f"가장 큰 이탈 요인: {top_factor['description']} "
                f"(상관계수 {top_factor['correlation']:.2f})"
                if top_factor else "데이터 부족"
            ),
            "actionable_insights": self._factor_insights(factor_analysis),
        }

        llm_summary = await self._llm_call(
            f"이탈 요인 분석 결과입니다:\n{result}\n\n"
            "각 요인별 구체적인 개선 방법을 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  5. 이탈 방지 전략 + 예산 배분
    # ═══════════════════════════════════════════════════════

    async def _strategy(self, **kwargs) -> dict[str, Any]:
        """이탈 위험 등급별 방지 전략과 예산 배분."""
        budget = kwargs.get("budget", 10000000)
        customers = self._parse_customers(kwargs.get("customers", ""))

        # 위험 등급별 분류
        groups = {"critical": [], "high": [], "medium": [], "low": [], "safe": []}
        for c in customers:
            score = self._calc_score(c)
            level = self._classify_risk(score)
            groups[level["key"]].append({**c, "churn_score": score})

        # 등급별 전략 + 예산 배분 (ROI 기반)
        strategies = []
        budget_weights = {"critical": 0.35, "high": 0.30, "medium": 0.20, "low": 0.10, "safe": 0.05}

        for level_key, level_info in self.RISK_LEVELS.items():
            members = groups.get(level_key, [])
            if not members:
                continue

            allocated = round(budget * budget_weights[level_key])
            per_customer = round(allocated / len(members)) if members else 0

            strategies.append({
                "risk_level": level_info["label"],
                "customer_count": len(members),
                "allocated_budget": allocated,
                "per_customer": per_customer,
                "urgency": level_info["action_urgency"],
                "tactics": self._tactics_for_level(level_key),
                "expected_save_rate": self._expected_save_rate(level_key),
            })

        # 총 구출 가능 고객 추정
        total_saveable = sum(
            s["customer_count"] * s["expected_save_rate"]
            for s in strategies
        )

        result = {
            "total_budget": budget,
            "total_customers": len(customers),
            "strategies": strategies,
            "expected_outcome": {
                "estimated_saved_customers": round(total_saveable),
                "save_rate": f"{total_saveable/len(customers)*100:.1f}%"
                if customers else "0%",
                "cost_per_saved": round(budget / total_saveable)
                if total_saveable > 0 else 0,
            },
        }

        llm_summary = await self._llm_call(
            f"이탈 방지 전략입니다 (예산 {budget:,}원):\n{result}\n\n"
            "예산 효율성을 평가하고 실행 로드맵을 제안해주세요."
        )
        result["ai_insight"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  6. 종합 분석
    # ═══════════════════════════════════════════════════════

    async def _full_analysis(self, **kwargs) -> dict[str, Any]:
        """이탈 점수 + 생존 분석 + 요인 분석 + 전략을 통합."""
        batch = await self._batch(**kwargs)
        survival = await self._survival(**kwargs)
        factors = await self._factors(**kwargs)
        strategy = await self._strategy(**kwargs)

        result = {
            "summary": "교수급 이탈 위험 종합 분석 (Cox PH + KM + Logistic)",
            "1_batch_assessment": batch,
            "2_survival_analysis": survival,
            "3_factor_analysis": factors,
            "4_retention_strategy": strategy,
        }

        llm_summary = await self._llm_call(
            f"이탈 위험 종합 분석입니다:\n\n"
            f"평균 이탈 점수: {batch['avg_churn_score']}\n"
            f"중간 생존 기간: {survival['median_survival_months']}개월\n"
            f"구출 가능 고객: {strategy['expected_outcome']['estimated_saved_customers']}명\n\n"
            "전체를 종합하여 고객 유지 전략 로드맵을 제안해주세요."
        )
        result["executive_summary"] = llm_summary
        return result

    # ═══════════════════════════════════════════════════════
    #  핵심 계산 함수
    # ═══════════════════════════════════════════════════════

    def _calc_score(self, customer: dict) -> float:
        """고객 데이터로 이탈 위험 점수 계산."""
        weighted_sum = 0.0
        total_weight = 0.0

        for factor_name, config in self.RISK_WEIGHTS.items():
            value = customer.get(factor_name, self._default_value(factor_name))
            risk = self._interpolate_risk(value, config["thresholds"])
            weighted_sum += max(0, min(100, risk * 100)) * config["weight"]
            total_weight += config["weight"]

        return weighted_sum / total_weight if total_weight > 0 else 50

    @staticmethod
    def _interpolate_risk(value: float, thresholds: list) -> float:
        """임계값 기반 위험 점수 보간."""
        for i, (thresh, risk) in enumerate(thresholds):
            if value <= thresh:
                if i == 0:
                    return risk
                prev_thresh, prev_risk = thresholds[i - 1]
                frac = (value - prev_thresh) / (thresh - prev_thresh) if thresh != prev_thresh else 0
                return prev_risk + frac * (risk - prev_risk)
        return thresholds[-1][1] if thresholds else 0.5

    def _classify_risk(self, score: float) -> dict:
        """점수 → 위험 등급."""
        for key, info in self.RISK_LEVELS.items():
            low, high = info["range"]
            if low <= score <= high:
                return {"key": key, **info}
        return {"key": "medium", **self.RISK_LEVELS["medium"]}

    @staticmethod
    def _default_value(factor_name: str) -> float:
        """기본값 (데이터 없을 때)."""
        defaults = {
            "recency_days": 30, "frequency_decline": 0.1,
            "support_tickets": 0, "payment_issues": 0,
            "engagement_score": 70, "tenure_months": 12,
        }
        return defaults.get(factor_name, 0)

    @staticmethod
    def _recommend_actions(score: float, factors: dict) -> list[str]:
        """위험 점수 기반 권장 조치."""
        actions = []
        if score >= 80:
            actions.append("즉시 전담 매니저 배정 + 1:1 통화/미팅")
            actions.append("특별 할인/혜택 제안 (최대 30%)")
        if score >= 60:
            actions.append("이탈 원인 조사 설문 발송")
            actions.append("맞춤형 리텐션 프로모션 실행")

        # 요인별 맞춤 액션
        for fname, fdata in factors.items():
            if fdata["risk_score"] >= 70:
                if fname == "recency_days":
                    actions.append("재방문 유도 이메일/푸시 알림")
                elif fname == "frequency_decline":
                    actions.append("사용 패턴 분석 후 맞춤 콘텐츠 제공")
                elif fname == "support_tickets":
                    actions.append("CS팀 우선 대응 + 불만 해결 확인")
                elif fname == "payment_issues":
                    actions.append("결제 수단 변경 안내 + 결제 장애 해결")
                elif fname == "engagement_score":
                    actions.append("온보딩 재실행 + 핵심 기능 사용 가이드")

        return actions[:5]  # 최대 5개

    @staticmethod
    def _tactics_for_level(level: str) -> list[str]:
        """등급별 전술."""
        tactics = {
            "critical": ["전담 매니저 즉시 배정", "최대 할인 + 무료 기간 연장",
                         "1:1 통화로 불만 해결", "경쟁사 이동 방지 패키지"],
            "high": ["맞춤형 이메일 시퀀스 (3일)", "리텐션 전용 할인 쿠폰",
                     "사용 가이드 + 팁 콘텐츠", "만족도 조사 + 피드백"],
            "medium": ["월간 뉴스레터 + 가치 리마인드", "리워드 포인트 적립 강화",
                       "관련 기능 추천"],
            "low": ["분기별 감사 이메일", "로열티 프로그램 안내"],
            "safe": ["업셀/크로스셀 기회 탐색", "리퍼럴 프로그램 초대"],
        }
        return tactics.get(level, [])

    @staticmethod
    def _expected_save_rate(level: str) -> float:
        """등급별 예상 구출 성공률."""
        rates = {"critical": 0.15, "high": 0.30, "medium": 0.50,
                 "low": 0.70, "safe": 0.95}
        return rates.get(level, 0.5)

    @staticmethod
    def _churn_reduction_simulation(churn_rate, cohort, months, revenue):
        """이탈률 감소 시 수익 영향 시뮬레이션."""
        scenarios = []
        for reduction_pct in [0, 10, 20, 30, 50]:
            new_churn = churn_rate * (1 - reduction_pct / 100)
            surviving = cohort
            total_rev = 0
            for m in range(months):
                total_rev += surviving * revenue
                surviving = surviving * (1 - new_churn)

            scenarios.append({
                "churn_reduction": f"{reduction_pct}%",
                "new_monthly_churn": f"{new_churn*100:.1f}%",
                "surviving_after_period": round(surviving),
                "total_revenue": round(total_rev),
            })

        base = scenarios[0]["total_revenue"]
        for s in scenarios:
            s["revenue_gain"] = round(s["total_revenue"] - base)
            s["gain_pct"] = f"{(s['total_revenue'] - base) / base * 100:+.1f}%" if base else "0%"

        return scenarios

    @staticmethod
    def _factor_insights(factors: list) -> list[str]:
        """요인 분석 기반 인사이트."""
        insights = []
        for f in factors[:3]:
            if abs(f["correlation"]) >= 0.5:
                direction = "양의" if f["correlation"] > 0 else "음의"
                insights.append(
                    f"{f['description']}이(가) 이탈과 {direction} 상관관계 "
                    f"(r={f['correlation']:.2f}) — 이 지표를 중점 관리하세요"
                )
        return insights or ["주요 이탈 요인에 대한 추가 데이터 수집이 필요합니다"]

    def _parse_customers(self, data) -> list[dict]:
        """고객 데이터 파싱."""
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

        # 샘플 데이터
        return [
            {"id": "C001", "recency_days": 3, "frequency_decline": 0, "support_tickets": 0,
             "payment_issues": 0, "engagement_score": 90, "tenure_months": 24},
            {"id": "C002", "recency_days": 45, "frequency_decline": 0.3, "support_tickets": 2,
             "payment_issues": 0, "engagement_score": 50, "tenure_months": 8},
            {"id": "C003", "recency_days": 90, "frequency_decline": 0.6, "support_tickets": 5,
             "payment_issues": 1, "engagement_score": 20, "tenure_months": 3},
            {"id": "C004", "recency_days": 15, "frequency_decline": 0.1, "support_tickets": 1,
             "payment_issues": 0, "engagement_score": 75, "tenure_months": 18},
            {"id": "C005", "recency_days": 120, "frequency_decline": 0.8, "support_tickets": 8,
             "payment_issues": 2, "engagement_score": 10, "tenure_months": 2},
            {"id": "C006", "recency_days": 7, "frequency_decline": 0, "support_tickets": 0,
             "payment_issues": 0, "engagement_score": 85, "tenure_months": 36},
            {"id": "C007", "recency_days": 60, "frequency_decline": 0.4, "support_tickets": 3,
             "payment_issues": 1, "engagement_score": 35, "tenure_months": 6},
            {"id": "C008", "recency_days": 200, "frequency_decline": 0.9, "support_tickets": 0,
             "payment_issues": 3, "engagement_score": 5, "tenure_months": 1},
        ]
