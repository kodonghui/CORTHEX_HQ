"""
바이럴 계수 분석 도구 — 제품이 얼마나 자연스럽게 퍼지는지 측정합니다.

"한 명의 고객이 몇 명의 새 고객을 데려오는가?"를 수학적으로 분석합니다.
K-factor > 1이면 자체적으로 성장하는 바이럴 루프가 작동 중입니다.

학술 근거:
  - Bass Diffusion Model (Bass, 1969) — 혁신 확산의 수학적 모델
  - K-factor (Viral Coefficient) — K = i × c (초대 수 × 전환율)
  - R₀ (Basic Reproduction Number) — 감염병학에서 차용한 확산 지표
  - SIR Model (Kermack & McKendrick, 1927) — 감수성-감염-회복 모델 차용
  - Network Effect Valuation (Metcalfe's Law + Reed's Law)

사용 방법:
  - action="kfactor"     : K-factor 바이럴 계수 계산 + 분석
  - action="bass"        : Bass 확산 모델 시뮬레이션 (S자 곡선)
  - action="simulate"    : 바이럴 루프 N세대 시뮬레이션
  - action="benchmark"   : 업종별 K-factor 벤치마크 비교
  - action="optimize"    : 바이럴 루프 최적화 포인트 분석
  - action="full"        : 종합 분석

필요 환경변수: 없음
필요 라이브러리: 없음 (순수 Python)
"""
from __future__ import annotations

import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.viral_coefficient")


def _mean(vals: list) -> float:
    return sum(vals) / len(vals) if vals else 0.0


class ViralCoefficientTool(BaseTool):
    """교수급 바이럴 계수 분석 도구 (Bass Diffusion + K-factor + SIR)."""

    # ─── 업종별 K-factor 벤치마크 ───
    BENCHMARKS = {
        "messaging": {"name": "메신저/커뮤니케이션", "avg_k": 0.9, "top_k": 1.5,
                       "examples": "카카오톡, 라인, WhatsApp"},
        "social_media": {"name": "소셜 미디어", "avg_k": 0.7, "top_k": 1.3,
                          "examples": "인스타그램, TikTok"},
        "marketplace": {"name": "마켓플레이스", "avg_k": 0.4, "top_k": 0.8,
                          "examples": "당근마켓, 에어비앤비"},
        "saas_b2b": {"name": "B2B SaaS", "avg_k": 0.15, "top_k": 0.5,
                      "examples": "Slack, Notion"},
        "saas_b2c": {"name": "B2C SaaS/구독", "avg_k": 0.2, "top_k": 0.6,
                      "examples": "Dropbox, Spotify"},
        "ecommerce": {"name": "이커머스", "avg_k": 0.1, "top_k": 0.4,
                       "examples": "쿠팡, 아마존"},
        "gaming": {"name": "게임", "avg_k": 0.5, "top_k": 1.2,
                    "examples": "Among Us, Wordle"},
        "fintech": {"name": "핀테크", "avg_k": 0.2, "top_k": 0.5,
                     "examples": "토스, 카카오뱅크"},
        "content": {"name": "콘텐츠/미디어", "avg_k": 0.3, "top_k": 0.7,
                     "examples": "넷플릭스, 유튜브"},
        "education": {"name": "교육/에드테크", "avg_k": 0.25, "top_k": 0.6,
                       "examples": "Duolingo, 클래스101"},
    }

    async def execute(self, **kwargs) -> dict[str, Any]:
        action = kwargs.get("action", "full")
        dispatch = {
            "kfactor": self._kfactor_analysis,
            "bass": self._bass_diffusion,
            "simulate": self._viral_simulation,
            "benchmark": self._benchmark,
            "optimize": self._optimize_viral,
            "full": self._full_analysis,
        }
        handler = dispatch.get(action)
        if not handler:
            return {"error": f"지원하지 않는 action: {action}. "
                    f"가능한 값: {list(dispatch.keys())}"}
        return await handler(**kwargs)

    # ═══════════════════════════════════════════════════════
    #  1. K-factor 바이럴 계수 분석
    # ═══════════════════════════════════════════════════════

    async def _kfactor_analysis(self, **kwargs) -> dict[str, Any]:
        """K-factor 계산 + 바이럴 루프 분석.

        K = i × c
        - i (invitations): 한 사용자가 보내는 평균 초대 수
        - c (conversion): 초대받은 사람의 가입 전환율
        """
        invites_per_user = kwargs.get("invites_per_user", 5.0)
        invite_conversion = kwargs.get("invite_conversion", 0.15)
        current_users = kwargs.get("current_users", 1000)
        cycle_days = kwargs.get("cycle_days", 14)  # 바이럴 사이클 기간

        k_factor = invites_per_user * invite_conversion

        # 유효 바이럴 계수 (이탈 고려)
        churn_rate = kwargs.get("monthly_churn_rate", 0.05)
        cycle_churn = churn_rate * (cycle_days / 30)
        effective_k = k_factor * (1 - cycle_churn)

        # 확산 속도 분석 (세대별 성장)
        generations = []
        users = current_users
        for gen in range(10):
            new_users = users * effective_k
            total = users + new_users
            generations.append({
                "generation": gen,
                "existing_users": round(users),
                "new_viral_users": round(new_users),
                "total_users": round(total),
                "growth_rate": f"{(new_users/users*100) if users > 0 else 0:.1f}%",
            })
            users = total

        # R₀ (기본 재생산 수) — 감염병학 차용
        # R₀ > 1이면 자체 확산, < 1이면 외부 유입 없이 소멸
        r_naught = effective_k

        # 이론적 최대 도달 사용자 (평형점)
        if effective_k >= 1:
            equilibrium = "무한 성장 (K≥1: 바이럴 루프 자체 지속)"
        else:
            # 기하급수 수렴: 총 = 초기 / (1 - K)
            theoretical_max = current_users / (1 - effective_k)
            equilibrium = f"최대 {round(theoretical_max):,}명 (K<1: 외부 유입 필요)"

        # 바이럴 루프 분해
        loop_analysis = {
            "exposure": f"사용자 1명이 {invites_per_user}명에게 노출",
            "activation": f"노출된 {invites_per_user}명 중 {invite_conversion*100:.0f}%가 가입",
            "new_users_per_cycle": f"사이클({cycle_days}일)당 신규 {k_factor:.2f}명",
            "churn_adjusted": f"이탈 반영 실제 신규 {effective_k:.2f}명",
            "doubling_time": (
                f"{math.log(2) / math.log(1 + effective_k) * cycle_days:.0f}일"
                if effective_k > 0 else "∞"
            ),
        }

        return {
            "method": "K-factor Viral Coefficient",
            "description": "바이럴 계수(K) = 초대 수(i) × 전환율(c). K≥1이면 자체 성장 달성",
            "k_factor": round(k_factor, 3),
            "effective_k": round(effective_k, 3),
            "r_naught": round(r_naught, 3),
            "inputs": {
                "invites_per_user": invites_per_user,
                "invite_conversion": f"{invite_conversion*100:.1f}%",
                "current_users": f"{current_users:,}명",
                "cycle_days": f"{cycle_days}일",
                "monthly_churn": f"{churn_rate*100:.1f}%",
            },
            "viral_status": (
                "바이럴 성장 중 (K≥1) — 외부 마케팅 없이도 성장 가능" if k_factor >= 1
                else "부분 바이럴 (0.5≤K<1) — 마케팅 비용 절감 효과" if k_factor >= 0.5
                else "약한 바이럴 (0.2≤K<0.5) — 보조적 성장" if k_factor >= 0.2
                else "바이럴 미발생 (K<0.2) — 유료 획득 의존"
            ),
            "equilibrium": equilibrium,
            "loop_analysis": loop_analysis,
            "generation_growth": generations,
        }

    # ═══════════════════════════════════════════════════════
    #  2. Bass 확산 모델 (Bass, 1969)
    # ═══════════════════════════════════════════════════════

    async def _bass_diffusion(self, **kwargs) -> dict[str, Any]:
        """Bass Diffusion Model — 신제품 확산의 S자 곡선 시뮬레이션.

        f(t) = [p + q × F(t)] × [1 - F(t)]

        - p: 혁신 계수 (외부 영향 — 광고, PR)
        - q: 모방 계수 (내부 영향 — 입소문, 바이럴)
        - m: 시장 잠재 규모 (최대 도달 가능 사용자 수)
        """
        p = kwargs.get("innovation_coeff", 0.03)    # 혁신 계수
        q = kwargs.get("imitation_coeff", 0.38)     # 모방 계수
        m = kwargs.get("market_potential", 100000)   # 시장 잠재 규모
        periods = kwargs.get("periods", 24)          # 시뮬레이션 기간 (월)

        # Bass 모델 시뮬레이션
        cumulative = 0.0
        results = []
        peak_adoption = 0
        peak_period = 0

        for t in range(periods + 1):
            f_t = cumulative / m if m > 0 else 0  # 누적 채택률
            adoption_rate = (p + q * f_t) * (1 - f_t)
            new_adopters = m * adoption_rate
            new_adopters = max(0, min(new_adopters, m - cumulative))

            if new_adopters > peak_adoption:
                peak_adoption = new_adopters
                peak_period = t

            cumulative += new_adopters
            results.append({
                "period": t,
                "new_adopters": round(new_adopters),
                "cumulative_adopters": round(cumulative),
                "adoption_rate": f"{(cumulative/m*100) if m > 0 else 0:.1f}%",
                "growth_phase": (
                    "도입기" if cumulative < m * 0.1
                    else "성장기" if cumulative < m * 0.5
                    else "성숙기" if cumulative < m * 0.9
                    else "포화기"
                ),
            })

        # 이론적 채택 정점 시기
        # t* = [ln(q) - ln(p)] / (p + q)
        if p > 0 and q > 0:
            t_star = (math.log(q) - math.log(p)) / (p + q) if q > p else 0
        else:
            t_star = 0

        # p/q 비율 해석
        pq_ratio = p / q if q > 0 else float("inf")
        if pq_ratio > 0.5:
            pq_interpretation = "광고/PR 주도 확산 (p가 q에 비해 큼)"
        elif pq_ratio > 0.1:
            pq_interpretation = "혼합형 확산 (광고 + 입소문 균형)"
        else:
            pq_interpretation = "입소문 주도 확산 (q가 p보다 압도적)"

        # 주요 마일스톤
        milestones = {}
        for target_pct in [10, 25, 50, 75, 90]:
            target = m * target_pct / 100
            for r in results:
                if r["cumulative_adopters"] >= target:
                    milestones[f"{target_pct}%_adoption"] = {
                        "period": r["period"],
                        "months": f"{r['period']}개월",
                    }
                    break

        return {
            "method": "Bass Diffusion Model (Bass, 1969)",
            "description": "혁신 확산 S자 곡선 — 외부 영향(p)과 내부 바이럴(q)의 상호작용 모델",
            "parameters": {
                "p_innovation": p,
                "q_imitation": q,
                "market_potential": f"{m:,}명",
                "p_q_ratio": round(pq_ratio, 3),
                "interpretation": pq_interpretation,
            },
            "peak_adoption": {
                "theoretical_peak": round(t_star, 1),
                "simulated_peak": peak_period,
                "peak_new_users": round(peak_adoption),
            },
            "milestones": milestones,
            "simulation": results,
            "final_adoption": f"{results[-1]['cumulative_adopters']:,}명 / {m:,}명 "
                             f"({results[-1]['adoption_rate']})",
        }

    # ═══════════════════════════════════════════════════════
    #  3. 바이럴 루프 N세대 시뮬레이션 (SIR 차용)
    # ═══════════════════════════════════════════════════════

    async def _viral_simulation(self, **kwargs) -> dict[str, Any]:
        """바이럴 루프 시뮬레이션 — SIR 모델을 제품 확산에 적용.

        S → I → R (Susceptible → Infected → Recovered)
        = 잠재고객 → 활성사용자 → 비활성/이탈
        """
        seed_users = kwargs.get("seed_users", 100)
        total_market = kwargs.get("total_market", 50000)
        k_factor = kwargs.get("k_factor", 0.75)
        cycle_days = kwargs.get("cycle_days", 14)
        monthly_churn = kwargs.get("monthly_churn_rate", 0.05)
        simulation_months = kwargs.get("simulation_months", 12)
        paid_acquisition = kwargs.get("paid_monthly_acquisition", 200)  # 월 유료 획득

        cycles_per_month = 30 / cycle_days
        total_cycles = int(simulation_months * cycles_per_month)

        # SIR 기반 시뮬레이션
        susceptible = total_market - seed_users
        active = seed_users
        churned = 0
        total_acquired = seed_users

        timeline = []
        for cycle in range(total_cycles + 1):
            month = cycle / cycles_per_month

            # 바이럴 획득 (활성 사용자 × K-factor × 잠재고객 비율)
            market_saturation = 1 - (susceptible / total_market) if total_market > 0 else 1
            adjusted_k = k_factor * (1 - market_saturation)  # 시장 포화도 반영
            viral_new = active * adjusted_k
            viral_new = min(viral_new, susceptible)

            # 유료 획득 (사이클당)
            paid_new = paid_acquisition / cycles_per_month
            paid_new = min(paid_new, susceptible - viral_new)

            total_new = viral_new + paid_new

            # 이탈
            cycle_churn_rate = monthly_churn / cycles_per_month
            churn_count = active * cycle_churn_rate

            # 상태 업데이트
            susceptible -= total_new
            active = active + total_new - churn_count
            churned += churn_count
            total_acquired += total_new

            if cycle % max(1, int(cycles_per_month)) == 0:  # 월 단위로만 기록
                timeline.append({
                    "month": round(month),
                    "active_users": round(max(0, active)),
                    "total_acquired": round(total_acquired),
                    "susceptible": round(max(0, susceptible)),
                    "churned": round(churned),
                    "viral_acquisition": round(viral_new * cycles_per_month),
                    "paid_acquisition": round(paid_new * cycles_per_month),
                    "market_penetration": f"{(total_acquired/total_market*100) if total_market > 0 else 0:.1f}%",
                })

        # 바이럴 vs 유료 비율
        total_viral = sum(t.get("viral_acquisition", 0) for t in timeline)
        total_paid = sum(t.get("paid_acquisition", 0) for t in timeline)
        viral_pct = total_viral / (total_viral + total_paid) * 100 if (total_viral + total_paid) > 0 else 0

        return {
            "method": "Viral Loop Simulation (SIR-inspired)",
            "description": "SIR 감염병 모델을 차용한 바이럴 확산 시뮬레이션 — 시장 포화도 반영",
            "inputs": {
                "seed_users": f"{seed_users:,}명",
                "total_market": f"{total_market:,}명",
                "k_factor": k_factor,
                "cycle_days": f"{cycle_days}일",
                "monthly_churn": f"{monthly_churn*100:.1f}%",
                "paid_monthly": f"{paid_acquisition:,}명/월",
            },
            "final_state": timeline[-1] if timeline else {},
            "acquisition_split": {
                "viral_total": round(total_viral),
                "paid_total": round(total_paid),
                "viral_pct": f"{viral_pct:.1f}%",
                "paid_pct": f"{100-viral_pct:.1f}%",
            },
            "timeline": timeline,
        }

    # ═══════════════════════════════════════════════════════
    #  4. 업종별 K-factor 벤치마크
    # ═══════════════════════════════════════════════════════

    async def _benchmark(self, **kwargs) -> dict[str, Any]:
        """내 K-factor를 업종별 벤치마크와 비교합니다."""
        my_k = kwargs.get("k_factor", 0.3)
        industry = kwargs.get("industry", "saas_b2c")

        # 내 업종 벤치마크
        my_bench = self.BENCHMARKS.get(industry, self.BENCHMARKS["saas_b2c"])
        diff = my_k - my_bench["avg_k"]

        if my_k >= my_bench["top_k"]:
            grade = "S"
            status = "업계 최상위 바이럴 수준"
        elif my_k >= my_bench["avg_k"]:
            grade = "A"
            status = "업계 평균 이상"
        elif my_k >= my_bench["avg_k"] * 0.7:
            grade = "B"
            status = "업계 평균 근접"
        elif my_k >= my_bench["avg_k"] * 0.4:
            grade = "C"
            status = "업계 평균 이하 — 개선 필요"
        else:
            grade = "D"
            status = "바이럴 효과 미미 — 근본적 재설계 필요"

        # 전체 업종 비교
        all_benchmarks = []
        for ind_key, ind_data in sorted(self.BENCHMARKS.items(),
                                         key=lambda x: x[1]["avg_k"], reverse=True):
            row = {
                "industry": ind_data["name"],
                "avg_k": ind_data["avg_k"],
                "top_k": ind_data["top_k"],
                "examples": ind_data["examples"],
            }
            if ind_key == industry:
                row["is_my_industry"] = True
            all_benchmarks.append(row)

        # K=1 달성에 필요한 개선
        if my_k < 1:
            invites = kwargs.get("invites_per_user", 5.0)
            conv = kwargs.get("invite_conversion", my_k / invites if invites > 0 else 0.1)
            needed_invites = 1.0 / conv if conv > 0 else float("inf")
            needed_conv = 1.0 / invites if invites > 0 else float("inf")
            gap_analysis = {
                "current_k": my_k,
                "target_k": 1.0,
                "gap": round(1.0 - my_k, 3),
                "option_a": f"초대 수를 {invites:.1f}→{needed_invites:.1f}로 늘리기 (전환율 유지)",
                "option_b": f"전환율을 {conv*100:.1f}%→{needed_conv*100:.1f}%로 올리기 (초대 수 유지)",
            }
        else:
            gap_analysis = {"status": "K≥1 달성됨 — 자체 성장 루프 작동 중"}

        return {
            "method": "K-factor Benchmark Comparison",
            "description": f"내 K-factor({my_k})를 {my_bench['name']} 업종 벤치마크와 비교 분석",
            "my_kfactor": my_k,
            "industry": my_bench["name"],
            "comparison": {
                "avg": my_bench["avg_k"],
                "top": my_bench["top_k"],
                "diff_from_avg": f"{'+' if diff >= 0 else ''}{diff:.3f}",
                "grade": grade,
                "status": status,
            },
            "all_benchmarks": all_benchmarks,
            "gap_to_viral": gap_analysis,
        }

    # ═══════════════════════════════════════════════════════
    #  5. 바이럴 루프 최적화 포인트
    # ═══════════════════════════════════════════════════════

    async def _optimize_viral(self, **kwargs) -> dict[str, Any]:
        """바이럴 루프의 각 단계를 분석하고 최적화 포인트를 찾습니다."""
        invites = kwargs.get("invites_per_user", 5.0)
        invite_open_rate = kwargs.get("invite_open_rate", 0.4)
        invite_click_rate = kwargs.get("invite_click_rate", 0.3)
        signup_rate = kwargs.get("signup_rate", 0.5)
        activation_rate = kwargs.get("activation_rate", 0.6)

        # 전체 전환율 = 열기 × 클릭 × 가입 × 활성화
        overall_conversion = invite_open_rate * invite_click_rate * signup_rate * activation_rate
        current_k = invites * overall_conversion

        # 각 단계의 이탈 영향도 (민감도 분석)
        stages = [
            ("invite_open_rate", "초대 열기율", invite_open_rate),
            ("invite_click_rate", "초대 클릭율", invite_click_rate),
            ("signup_rate", "가입 전환율", signup_rate),
            ("activation_rate", "활성화율", activation_rate),
        ]

        sensitivity = []
        for name, label, current_rate in stages:
            # 10%p 개선 시 K 변화
            improved = min(1.0, current_rate + 0.1)
            rates = {
                "invite_open_rate": invite_open_rate,
                "invite_click_rate": invite_click_rate,
                "signup_rate": signup_rate,
                "activation_rate": activation_rate,
            }
            rates[name] = improved
            new_conv = rates["invite_open_rate"] * rates["invite_click_rate"] * rates["signup_rate"] * rates["activation_rate"]
            new_k = invites * new_conv
            k_impact = new_k - current_k

            # K=1 달성에 필요한 이 단계의 수치
            target_rate = 1.0 / (invites * overall_conversion / current_rate) if (invites * overall_conversion / current_rate) > 0 else float("inf")

            sensitivity.append({
                "stage": label,
                "current_rate": f"{current_rate*100:.0f}%",
                "k_impact_per_10pp": round(k_impact, 3),
                "priority": "높음" if k_impact > 0.1 else ("중간" if k_impact > 0.05 else "낮음"),
                "needed_for_k1": f"{min(target_rate, 1.0)*100:.0f}%" if target_rate <= 1.0 else "불가능 (다른 단계도 필요)",
                "improvement_difficulty": (
                    "쉬움" if current_rate < 0.3
                    else "보통" if current_rate < 0.6
                    else "어려움 (이미 높음)"
                ),
            })

        # ROI가 가장 높은 개선 포인트 (낮은 현재율 + 높은 임팩트)
        sensitivity.sort(key=lambda x: x["k_impact_per_10pp"], reverse=True)
        best_lever = sensitivity[0] if sensitivity else None

        # 초대 수 증가 시나리오
        invite_scenarios = []
        for extra in [2, 5, 10, 15, 20]:
            new_k = extra * overall_conversion
            invite_scenarios.append({
                "invites_per_user": extra,
                "k_factor": round(new_k, 3),
                "viral_status": "자체 성장" if new_k >= 1 else "보조 성장",
            })

        return {
            "method": "Viral Loop Optimization Analysis",
            "description": "바이럴 루프 4단계(열기→클릭→가입→활성화)별 민감도 분석 + 최적화 포인트",
            "current_state": {
                "invites_per_user": invites,
                "overall_conversion": f"{overall_conversion*100:.2f}%",
                "k_factor": round(current_k, 3),
            },
            "funnel_breakdown": {
                "invited": f"{invites:.1f}명",
                "opened": f"{invites * invite_open_rate:.1f}명 ({invite_open_rate*100:.0f}%)",
                "clicked": f"{invites * invite_open_rate * invite_click_rate:.1f}명 ({invite_click_rate*100:.0f}%)",
                "signed_up": f"{invites * invite_open_rate * invite_click_rate * signup_rate:.1f}명 ({signup_rate*100:.0f}%)",
                "activated": f"{invites * overall_conversion:.2f}명 ({activation_rate*100:.0f}%)",
            },
            "sensitivity_analysis": sensitivity,
            "best_optimization_lever": {
                "stage": best_lever["stage"] if best_lever else "N/A",
                "reason": f"10%p 개선 시 K가 {best_lever['k_impact_per_10pp']:.3f} 증가 (가장 큰 영향)" if best_lever else "N/A",
            },
            "invite_scenarios": invite_scenarios,
        }

    # ═══════════════════════════════════════════════════════
    #  6. 종합 분석
    # ═══════════════════════════════════════════════════════

    async def _full_analysis(self, **kwargs) -> dict[str, Any]:
        """전체 바이럴 계수 종합 분석."""
        kfactor = await self._kfactor_analysis(**kwargs)
        bass = await self._bass_diffusion(**kwargs)
        simulate = await self._viral_simulation(**kwargs)
        benchmark = await self._benchmark(**kwargs)
        optimize = await self._optimize_viral(**kwargs)

        # LLM 요약
        summary_prompt = f"""아래 바이럴 계수 분석 결과를 한국어로 요약하세요.

## K-factor
- 바이럴 계수: {kfactor.get('k_factor', 'N/A')}
- 유효 K (이탈 반영): {kfactor.get('effective_k', 'N/A')}
- 상태: {kfactor.get('viral_status', 'N/A')}

## Bass 확산 모델
- 혁신계수(p): {bass.get('parameters', {}).get('p_innovation', 'N/A')}
- 모방계수(q): {bass.get('parameters', {}).get('q_imitation', 'N/A')}
- 최종 채택률: {bass.get('final_adoption', 'N/A')}

## 벤치마크
- 등급: {benchmark.get('comparison', {}).get('grade', 'N/A')}

## 최적화 포인트
- 최우선 레버: {optimize.get('best_optimization_lever', {}).get('stage', 'N/A')}

다음을 포함해서 작성:
1. 바이럴 현황 한 줄 요약
2. K=1 달성을 위한 구체적 로드맵 (또는 K>1이면 유지 전략)
3. 예산 효율 관점의 추천"""

        summary = await self._llm_call(
            system_prompt="바이럴 마케팅/성장 해킹 전문가. 데이터 기반 구체적 성장 전략 제시.",
            user_prompt=summary_prompt,
        )

        return {
            "method": "Full Viral Coefficient Analysis",
            "kfactor_analysis": kfactor,
            "bass_diffusion": bass,
            "viral_simulation": simulate,
            "benchmark": benchmark,
            "optimization": optimize,
            "executive_summary": summary,
        }
