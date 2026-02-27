"""
A/B 테스트 통계 검정 도구 (AB Test Engine) — 실험 결과를 수학적으로 판정합니다.

"A안과 B안 중 진짜 더 나은 것은?"을 통계적으로 검증하고,
표본 크기 계산부터 베이지안 승률까지 제공하는 교수급 실험 분석 도구입니다.

학술 근거:
  - Fisher의 정확 검정 (Ronald Fisher, 1935)
  - Neyman-Pearson 가설검정 프레임워크 (1933)
  - Bayesian A/B Testing (VWO Whitepaper, 2019)
  - 표본 크기 계산 (Lehr's formula + 연속성 보정)
  - Cohen's d 효과 크기 (Jacob Cohen, "Statistical Power Analysis", 1988)

사용 방법:
  - action="test"         : A/B 전환율 검정 (Z-test + 베이지안)
  - action="sample_size"  : 실험 전 필요 표본 크기 계산
  - action="power"        : 검정력(Power) 분석
  - action="revenue"      : 매출 기반 A/B 검정 (t-test 기반)
  - action="multi"        : A/B/C/n 다변량 검정 (본페로니 보정)
  - action="full"         : 종합 분석

필요 환경변수: 없음
필요 라이브러리: numpy, scipy (통계 함수)
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.ab_test_engine")


# ═══════════════════════════════════════════════════════
#  scipy 임포트 (없으면 순수 Python 폴백)
# ═══════════════════════════════════════════════════════

def _import_scipy_stats():
    try:
        from scipy import stats
        return stats
    except ImportError:
        return None


# ═══════════════════════════════════════════════════════
#  순수 Python 통계 폴백 (scipy 없을 때)
# ═══════════════════════════════════════════════════════

def _norm_cdf(x: float) -> float:
    """표준정규분포 CDF — scipy 없을 때 근사 계산 (Abramowitz & Stegun)."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_ppf(p: float) -> float:
    """표준정규분포 역CDF — Rational approximation (Peter Acklam)."""
    if p <= 0:
        return -10.0
    if p >= 1:
        return 10.0
    if p == 0.5:
        return 0.0

    # Rational approximation
    a = [-3.969683028665376e1, 2.209460984245205e2,
         -2.759285104469687e2, 1.383577518672690e2,
         -3.066479806614716e1, 2.506628277459239e0]
    b = [-5.447609879822406e1, 1.615858368580409e2,
         -1.556989798598866e2, 6.680131188771972e1,
         -1.328068155288572e1]
    c = [-7.784894002430293e-3, -3.223964580411365e-1,
         -2.400758277161838e0, -2.549732539343734e0,
         4.374664141464968e0, 2.938163982698783e0]
    d = [7.784695709041462e-3, 3.224671290700398e-1,
         2.445134137142996e0, 3.754408661907416e0]

    p_low = 0.02425
    p_high = 1 - p_low

    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    elif p <= p_high:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    else:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


# ═══════════════════════════════════════════════════════
#  베이지안 A/B 테스트 (Beta 분포 시뮬레이션)
# ═══════════════════════════════════════════════════════

def _bayesian_ab(
    successes_a: int, trials_a: int,
    successes_b: int, trials_b: int,
    n_sim: int = 100_000,
) -> dict:
    """베이지안 A/B 테스트: Beta 분포 Monte Carlo 시뮬레이션."""
    # 무정보 사전분포 Beta(1, 1)
    alpha_a = 1 + successes_a
    beta_a = 1 + (trials_a - successes_a)
    alpha_b = 1 + successes_b
    beta_b = 1 + (trials_b - successes_b)

    # Monte Carlo 샘플링
    samples_a = np.random.beta(alpha_a, beta_a, n_sim)
    samples_b = np.random.beta(alpha_b, beta_b, n_sim)

    prob_b_wins = float(np.mean(samples_b > samples_a))
    prob_a_wins = float(np.mean(samples_a > samples_b))

    # 기대 리프트 (B의 A 대비 개선율)
    lift = (samples_b - samples_a) / np.where(samples_a > 0, samples_a, 1e-10)
    expected_lift = float(np.mean(lift))

    # 95% 신용구간 (Credible Interval)
    ci_a = (float(np.percentile(samples_a, 2.5)), float(np.percentile(samples_a, 97.5)))
    ci_b = (float(np.percentile(samples_b, 2.5)), float(np.percentile(samples_b, 97.5)))

    return {
        "prob_b_wins": prob_b_wins,
        "prob_a_wins": prob_a_wins,
        "expected_lift": expected_lift,
        "ci_a_95": ci_a,
        "ci_b_95": ci_b,
    }


# ═══════════════════════════════════════════════════════
#  AbTestEngineTool
# ═══════════════════════════════════════════════════════

class AbTestEngineTool(BaseTool):
    """교수급 A/B 테스트 통계 검정 도구 — 빈도론 + 베이지안 이중 검증."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")

        actions = {
            "test": self._ab_test,
            "sample_size": self._calc_sample_size,
            "power": self._power_analysis,
            "revenue": self._revenue_test,
            "multi": self._multi_variant,
            "full": self._full_analysis,
        }

        handler = actions.get(action)
        if handler:
            return await handler(kwargs)

        return (
            f"알 수 없는 action: {action}. "
            "test, sample_size, power, revenue, multi, full 중 하나를 사용하세요."
        )

    @staticmethod
    def _pct(val: float) -> str:
        return f"{val * 100:.2f}%"

    @staticmethod
    def _fmt(val: float, d: int = 4) -> str:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return "N/A"
        return f"{val:.{d}f}"

    # ═══════════════════════════════════════════
    #  1. A/B 전환율 검정 (Z-test + Bayesian)
    # ═══════════════════════════════════════════

    async def _ab_test(self, kwargs: dict) -> str:
        visitors_a = int(kwargs.get("visitors_a", 0))
        conversions_a = int(kwargs.get("conversions_a", 0))
        visitors_b = int(kwargs.get("visitors_b", 0))
        conversions_b = int(kwargs.get("conversions_b", 0))
        alpha = float(kwargs.get("alpha", 0.05))

        if visitors_a <= 0 or visitors_b <= 0:
            return ("A/B 데이터를 입력해주세요.\n"
                    "필수: visitors_a, conversions_a, visitors_b, conversions_b\n"
                    "예: visitors_a=5000, conversions_a=150, visitors_b=5000, conversions_b=180")

        p_a = conversions_a / visitors_a
        p_b = conversions_b / visitors_b
        lift = (p_b - p_a) / p_a if p_a > 0 else 0

        lines = ["## A/B 테스트 결과 분석\n"]
        lines.append("### 기본 데이터")
        lines.append("| 그룹 | 방문자 | 전환 | 전환율 |")
        lines.append("|------|--------|------|--------|")
        lines.append(f"| A (대조군) | {visitors_a:,} | {conversions_a:,} | **{self._pct(p_a)}** |")
        lines.append(f"| B (실험군) | {visitors_b:,} | {conversions_b:,} | **{self._pct(p_b)}** |")
        lines.append(f"| 리프트 | — | — | **{lift*100:+.2f}%** |")

        # ── 빈도론 검정 (Two-proportion Z-test) ──
        lines.append("\n### 1. 빈도론 검정 (Two-proportion Z-test)")

        p_pool = (conversions_a + conversions_b) / (visitors_a + visitors_b)
        se = math.sqrt(p_pool * (1 - p_pool) * (1/visitors_a + 1/visitors_b))

        if se > 0:
            z_stat = (p_b - p_a) / se
            p_value = 2 * (1 - _norm_cdf(abs(z_stat)))
        else:
            z_stat = 0
            p_value = 1.0

        significant = p_value < alpha

        lines.append(f"  Z-통계량: {self._fmt(z_stat, 3)}")
        lines.append(f"  p-value: {self._fmt(p_value, 6)}")
        lines.append(f"  유의수준 α: {alpha}")

        if significant:
            winner = "B" if p_b > p_a else "A"
            lines.append(f"  결과: ✅ **통계적으로 유의** (p < {alpha})")
            lines.append(f"  승자: **{winner}안** (전환율 {self._pct(max(p_a, p_b))})")
        else:
            lines.append(f"  결과: ❌ **통계적으로 유의하지 않음** (p ≥ {alpha})")
            lines.append("  해석: A와 B의 차이가 우연일 가능성이 있습니다.")

        # 신뢰구간
        se_diff = math.sqrt(p_a*(1-p_a)/visitors_a + p_b*(1-p_b)/visitors_b)
        z_crit = _norm_ppf(1 - alpha/2)
        ci_low = (p_b - p_a) - z_crit * se_diff
        ci_high = (p_b - p_a) + z_crit * se_diff

        lines.append(f"\n  차이의 {(1-alpha)*100:.0f}% 신뢰구간: "
                     f"[{ci_low*100:+.3f}%p, {ci_high*100:+.3f}%p]")
        if ci_low > 0:
            lines.append("  → 구간 전체가 양수: B가 확실히 더 나음")
        elif ci_high < 0:
            lines.append("  → 구간 전체가 음수: A가 확실히 더 나음")
        else:
            lines.append("  → 구간이 0을 포함: 차이 불확실")

        # ── 효과 크기 (Cohen's h) ──
        lines.append("\n### 2. 효과 크기 (Cohen's h)")
        h = 2 * (math.asin(math.sqrt(p_b)) - math.asin(math.sqrt(p_a)))
        abs_h = abs(h)

        if abs_h >= 0.8:
            h_interp = "큰 효과 (Large)"
        elif abs_h >= 0.5:
            h_interp = "중간 효과 (Medium)"
        elif abs_h >= 0.2:
            h_interp = "작은 효과 (Small)"
        else:
            h_interp = "미미한 효과 (Negligible)"

        lines.append(f"  Cohen's h: {self._fmt(h, 3)} — **{h_interp}**")
        lines.append("  기준: |h| < 0.2 미미 / 0.2~0.5 작음 / 0.5~0.8 중간 / 0.8+ 큼")

        # ── 베이지안 분석 ──
        lines.append("\n### 3. 베이지안 분석 (Monte Carlo 10만 회 시뮬레이션)")
        bayes = _bayesian_ab(conversions_a, visitors_a, conversions_b, visitors_b)

        lines.append(f"  B가 A보다 나을 확률: **{bayes['prob_b_wins']*100:.1f}%**")
        lines.append(f"  A가 B보다 나을 확률: **{bayes['prob_a_wins']*100:.1f}%**")
        lines.append(f"  기대 리프트: {bayes['expected_lift']*100:+.2f}%")
        lines.append(f"  A의 95% 신용구간: [{self._pct(bayes['ci_a_95'][0])}, {self._pct(bayes['ci_a_95'][1])}]")
        lines.append(f"  B의 95% 신용구간: [{self._pct(bayes['ci_b_95'][0])}, {self._pct(bayes['ci_b_95'][1])}]")

        if bayes["prob_b_wins"] >= 0.95:
            lines.append("  베이지안 판정: ✅ **B안 채택 (95%+ 확신)**")
        elif bayes["prob_a_wins"] >= 0.95:
            lines.append("  베이지안 판정: ✅ **A안 유지 (95%+ 확신)**")
        elif max(bayes["prob_b_wins"], bayes["prob_a_wins"]) >= 0.85:
            lines.append("  베이지안 판정: 🟡 **기울어진 결과 (85~95% — 추가 데이터 권장)**")
        else:
            lines.append("  베이지안 판정: ❌ **불확실 (추가 데이터 필요)**")

        # ── 실무 의사결정 가이드 ──
        lines.append("\n### 4. 실무 의사결정 가이드")
        if significant and bayes["prob_b_wins"] >= 0.95:
            lines.append("  빈도론 + 베이지안 모두 일치 → **B안 즉시 적용 권장**")
        elif significant and bayes["prob_b_wins"] < 0.95:
            lines.append("  빈도론은 유의하지만 베이지안은 불확실 → **1주 더 실험 후 재판단**")
        elif not significant and bayes["prob_b_wins"] >= 0.90:
            lines.append("  빈도론은 무의미하지만 베이지안은 유력 → **표본 부족 가능, 실험 연장**")
        else:
            lines.append("  양쪽 모두 불확실 → **A안 유지 (변경 리스크 > 기대 이득)**")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 실험 통계학 교수입니다. A/B 테스트 결과를 보고:\n"
                "1. 통계적 유의성과 실무적 유의성(Effect Size)의 차이 설명\n"
                "2. 이 실험 결과를 경영진에게 보고할 때 주의점\n"
                "3. 결과의 한계 (표본 편향, 노벨티 효과 등 가능성)\n"
                "4. 후속 실험 추천 (있다면)\n"
                "한국어로 비개발자도 이해할 수 있게 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 A/B 테스트 종합 판정\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  2. 표본 크기 계산 (Sample Size)
    # ═══════════════════════════════════════════

    async def _calc_sample_size(self, kwargs: dict) -> str:
        baseline = float(kwargs.get("baseline_rate", 0.05))
        mde = float(kwargs.get("mde", 0.01))  # Minimum Detectable Effect
        alpha = float(kwargs.get("alpha", 0.05))
        power = float(kwargs.get("power", 0.80))

        if baseline <= 0 or baseline >= 1:
            return "baseline_rate는 0~1 사이 값이어야 합니다. 예: baseline_rate=0.05 (5%)"

        target = baseline + mde

        z_alpha = _norm_ppf(1 - alpha / 2)
        z_beta = _norm_ppf(power)

        # 표본 크기 공식 (두 비율 비교)
        p_bar = (baseline + target) / 2
        n = ((z_alpha * math.sqrt(2 * p_bar * (1 - p_bar)) +
              z_beta * math.sqrt(baseline * (1 - baseline) + target * (1 - target))) ** 2) / (mde ** 2)
        n = math.ceil(n)

        lines = ["## A/B 테스트 표본 크기 계산\n"]
        lines.append("### 입력 파라미터")
        lines.append(f"  현재 전환율 (baseline): **{self._pct(baseline)}**")
        lines.append(f"  최소 감지 효과 (MDE): **{mde * 100:+.1f}%p** → 목표 전환율: {self._pct(target)}")
        lines.append(f"  유의수준 α: {alpha} (= 틀릴 확률 {alpha*100:.0f}%)")
        lines.append(f"  검정력 (1-β): {power} (= 감지 확률 {power*100:.0f}%)")

        lines.append(f"\n### 결과")
        lines.append(f"  그룹당 필요 표본: **{n:,}명**")
        lines.append(f"  총 필요 표본 (A+B): **{n*2:,}명**")

        # 일별 필요 트래픽 추정
        lines.append(f"\n### 실험 기간 추정")
        daily_options = [100, 500, 1000, 5000, 10000]
        lines.append("| 일일 트래픽 | 예상 기간 |")
        lines.append("|-----------|---------|")
        for daily in daily_options:
            days = math.ceil(n * 2 / daily)
            weeks = days / 7
            lines.append(f"| {daily:,}명/일 | **{days}일** ({weeks:.1f}주) |")

        # MDE 민감도 분석
        lines.append("\n### MDE별 표본 크기 (민감도 분석)")
        lines.append("| MDE | 목표 전환율 | 그룹당 표본 | 총 표본 |")
        lines.append("|-----|----------|----------|--------|")
        for mde_test in [0.005, 0.01, 0.02, 0.03, 0.05]:
            target_test = baseline + mde_test
            if target_test >= 1:
                continue
            p_bar_t = (baseline + target_test) / 2
            n_t = ((z_alpha * math.sqrt(2 * p_bar_t * (1 - p_bar_t)) +
                    z_beta * math.sqrt(baseline * (1 - baseline) + target_test * (1 - target_test))) ** 2) / (mde_test ** 2)
            n_t = math.ceil(n_t)
            marker = " ← 현재" if abs(mde_test - mde) < 0.0001 else ""
            lines.append(f"| {mde_test*100:+.1f}%p | {self._pct(target_test)} | "
                         f"{n_t:,} | **{n_t*2:,}**{marker} |")

        lines.append("\n### ⚠️ 주의사항")
        lines.append("  1. **p-hacking 금지**: 중간에 결과를 보고 실험을 조기 중단하면 안 됩니다")
        lines.append("  2. **계절 효과**: 최소 1주일(평일+주말 포함) 이상 실험하세요")
        lines.append("  3. **노벨티 효과**: 새로운 것에 대한 일시적 관심 → 2주 이상 권장")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 실험 설계 교수입니다. 표본 크기 계산 결과를 보고:\n"
                "1. 이 실험이 현실적으로 가능한지 (필요 기간과 트래픽 고려)\n"
                "2. MDE를 조정해야 하는지에 대한 조언\n"
                "3. 표본 크기를 줄이면서도 신뢰할 수 있는 방법 (있다면)\n"
                "한국어로 실무자가 바로 적용할 수 있게 조언하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 실험 설계 조언\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  3. 검정력 분석 (Power Analysis)
    # ═══════════════════════════════════════════

    async def _power_analysis(self, kwargs: dict) -> str:
        visitors_a = int(kwargs.get("visitors_a", 0))
        conversions_a = int(kwargs.get("conversions_a", 0))
        visitors_b = int(kwargs.get("visitors_b", 0))
        conversions_b = int(kwargs.get("conversions_b", 0))
        alpha = float(kwargs.get("alpha", 0.05))

        if visitors_a <= 0 or visitors_b <= 0:
            return "visitors_a, visitors_b (각 그룹 방문자 수)를 입력해주세요."

        p_a = conversions_a / visitors_a
        p_b = conversions_b / visitors_b
        n = min(visitors_a, visitors_b)

        z_alpha = _norm_ppf(1 - alpha / 2)

        # 효과 크기
        h = 2 * (math.asin(math.sqrt(p_b)) - math.asin(math.sqrt(p_a)))

        # 검정력 계산: Power = Φ(|h|√n - z_α/2)
        power_val = _norm_cdf(abs(h) * math.sqrt(n) - z_alpha)

        lines = ["## 검정력 (Statistical Power) 분석\n"]
        lines.append(f"  전환율 A: {self._pct(p_a)} | 전환율 B: {self._pct(p_b)}")
        lines.append(f"  그룹당 표본: {n:,}명 | 유의수준 α: {alpha}")
        lines.append(f"  효과 크기 (Cohen's h): {self._fmt(h, 3)}")
        lines.append(f"  **검정력: {power_val*100:.1f}%**")

        if power_val >= 0.80:
            lines.append("  등급: ✅ **충분** (80% 이상)")
        elif power_val >= 0.60:
            lines.append("  등급: 🟡 **부족** (60~80%) — 실험 연장 권장")
        else:
            lines.append("  등급: 🔴 **매우 부족** (60% 미만) — 이 결과는 신뢰하기 어려움")

        lines.append("\n### 검정력이란?")
        lines.append("  실제 차이가 있을 때 그것을 탐지할 확률")
        lines.append(f"  현재 {power_val*100:.0f}% → A와 B에 진짜 차이가 있어도 "
                     f"**{(1-power_val)*100:.0f}% 확률로 놓침**")

        # 80% 검정력 달성을 위한 추가 표본
        if power_val < 0.80 and abs(h) > 0:
            needed_n = math.ceil(((z_alpha + _norm_ppf(0.80)) / abs(h)) ** 2)
            additional = max(0, needed_n - n)
            lines.append(f"\n### 80% 검정력 달성을 위한 추가 표본")
            lines.append(f"  필요 그룹당 표본: {needed_n:,}명")
            lines.append(f"  현재 보유: {n:,}명")
            lines.append(f"  **추가 필요: {additional:,}명/그룹**")

        formatted = "\n".join(lines)
        return formatted

    # ═══════════════════════════════════════════
    #  4. 매출 기반 검정 (Revenue T-test)
    # ═══════════════════════════════════════════

    async def _revenue_test(self, kwargs: dict) -> str:
        # 매출 데이터는 리스트 형태로 입력 (또는 요약 통계)
        mean_a = float(kwargs.get("mean_a", 0))
        mean_b = float(kwargs.get("mean_b", 0))
        std_a = float(kwargs.get("std_a", 0))
        std_b = float(kwargs.get("std_b", 0))
        n_a = int(kwargs.get("n_a", 0))
        n_b = int(kwargs.get("n_b", 0))
        alpha = float(kwargs.get("alpha", 0.05))

        if n_a <= 0 or n_b <= 0:
            return ("매출 데이터를 입력해주세요.\n"
                    "필수: mean_a(A평균매출), std_a(A표준편차), n_a(A표본수), "
                    "mean_b, std_b, n_b\n"
                    "예: mean_a=50000, std_a=15000, n_a=500, "
                    "mean_b=55000, std_b=16000, n_b=500")

        lines = ["## 매출 기반 A/B 테스트 (Welch's t-test)\n"]

        # Welch's t-test (분산이 다를 수 있음)
        se = math.sqrt(std_a**2/n_a + std_b**2/n_b) if (std_a > 0 or std_b > 0) else 1
        t_stat = (mean_b - mean_a) / se if se > 0 else 0

        # 자유도 (Welch-Satterthwaite)
        if std_a > 0 and std_b > 0:
            df_num = (std_a**2/n_a + std_b**2/n_b) ** 2
            df_den = ((std_a**2/n_a)**2 / (n_a-1)) + ((std_b**2/n_b)**2 / (n_b-1))
            df = df_num / df_den if df_den > 0 else n_a + n_b - 2
        else:
            df = n_a + n_b - 2

        # p-value (정규 근사, df가 충분히 크면)
        p_value = 2 * (1 - _norm_cdf(abs(t_stat)))

        lift_pct = (mean_b - mean_a) / mean_a * 100 if mean_a > 0 else 0

        lines.append("### 기본 데이터")
        lines.append("| 그룹 | 평균 매출 | 표준편차 | 표본 수 |")
        lines.append("|------|---------|---------|--------|")
        lines.append(f"| A | {mean_a:,.0f}원 | {std_a:,.0f}원 | {n_a:,}명 |")
        lines.append(f"| B | {mean_b:,.0f}원 | {std_b:,.0f}원 | {n_b:,}명 |")
        lines.append(f"| 차이 | {mean_b - mean_a:+,.0f}원 ({lift_pct:+.1f}%) | — | — |")

        lines.append(f"\n### Welch's t-test 결과")
        lines.append(f"  t-통계량: {self._fmt(t_stat, 3)}")
        lines.append(f"  자유도: {self._fmt(df, 1)}")
        lines.append(f"  p-value: {self._fmt(p_value, 6)}")

        significant = p_value < alpha
        if significant:
            winner = "B" if mean_b > mean_a else "A"
            lines.append(f"  결과: ✅ **통계적으로 유의** → {winner}안 우위")
        else:
            lines.append(f"  결과: ❌ 통계적으로 유의하지 않음")

        # Cohen's d
        pooled_sd = math.sqrt((std_a**2 + std_b**2) / 2) if (std_a > 0 or std_b > 0) else 1
        cohens_d = (mean_b - mean_a) / pooled_sd

        if abs(cohens_d) >= 0.8:
            d_interp = "큰 효과"
        elif abs(cohens_d) >= 0.5:
            d_interp = "중간 효과"
        elif abs(cohens_d) >= 0.2:
            d_interp = "작은 효과"
        else:
            d_interp = "미미한 효과"

        lines.append(f"\n  Cohen's d: {self._fmt(cohens_d, 3)} — {d_interp}")

        # 연간 영향 추정
        monthly_users = n_a + n_b
        annual_impact = (mean_b - mean_a) * monthly_users * 12
        lines.append(f"\n### 비즈니스 영향 추정")
        lines.append(f"  월 대상 사용자: {monthly_users:,}명 기준")
        lines.append(f"  B안 적용 시 연간 매출 변화: **{annual_impact:+,.0f}원**")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 마케팅 분석 교수입니다. 매출 기반 A/B 테스트 결과를 보고:\n"
                "1. 통계적 결과와 비즈니스 결과가 일치하는지\n"
                "2. 매출 분포의 비대칭성(고액 결제자) 가능성 언급\n"
                "3. 최종 의사결정 추천\n"
                "한국어로 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 매출 A/B 종합 판정\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  5. 다변량 검정 (Multi-variant)
    # ═══════════════════════════════════════════

    async def _multi_variant(self, kwargs: dict) -> str:
        # variants: "A:5000:150,B:5000:180,C:5000:200"
        variants_str = kwargs.get("variants", "")
        alpha = float(kwargs.get("alpha", 0.05))

        if not variants_str:
            return ("다변량 데이터를 입력해주세요.\n"
                    "형식: variants='A:방문자:전환,B:방문자:전환,C:방문자:전환'\n"
                    "예: variants='A:5000:150,B:5000:180,C:5000:200'")

        variants = []
        for part in variants_str.split(","):
            tokens = part.strip().split(":")
            if len(tokens) != 3:
                return f"형식 오류: '{part}'. 올바른 형식: '이름:방문자:전환'"
            name, vis, conv = tokens[0], int(tokens[1]), int(tokens[2])
            variants.append({"name": name, "visitors": vis, "conversions": conv,
                            "rate": conv / vis if vis > 0 else 0})

        n_variants = len(variants)
        if n_variants < 2:
            return "최소 2개 이상의 변형이 필요합니다."

        # 본페로니 보정
        n_comparisons = n_variants * (n_variants - 1) // 2
        adjusted_alpha = alpha / n_comparisons

        lines = [f"## A/B/n 다변량 테스트 ({n_variants}개 변형)\n"]
        lines.append(f"본페로니 보정: α = {alpha} / {n_comparisons} = **{adjusted_alpha:.4f}**")
        lines.append("(다중 비교 시 거짓 양성 방지를 위해 유의수준을 더 엄격하게 적용)\n")

        lines.append("### 변형별 성과")
        lines.append("| 변형 | 방문자 | 전환 | 전환율 |")
        lines.append("|------|--------|------|--------|")
        for v in sorted(variants, key=lambda x: x["rate"], reverse=True):
            lines.append(f"| {v['name']} | {v['visitors']:,} | "
                        f"{v['conversions']:,} | **{self._pct(v['rate'])}** |")

        # 모든 쌍 비교
        lines.append("\n### 쌍별 비교 (Pairwise Comparison)")
        lines.append("| 비교 | Z-stat | p-value | 유의? |")
        lines.append("|------|--------|---------|-------|")

        best = max(variants, key=lambda x: x["rate"])
        for i in range(n_variants):
            for j in range(i + 1, n_variants):
                a = variants[i]
                b = variants[j]
                p_pool = (a["conversions"] + b["conversions"]) / (a["visitors"] + b["visitors"])
                se = math.sqrt(p_pool * (1 - p_pool) * (1/a["visitors"] + 1/b["visitors"]))
                z = (b["rate"] - a["rate"]) / se if se > 0 else 0
                p_val = 2 * (1 - _norm_cdf(abs(z)))
                sig = "✅" if p_val < adjusted_alpha else "❌"
                lines.append(f"| {a['name']} vs {b['name']} | "
                            f"{self._fmt(z, 3)} | {self._fmt(p_val, 6)} | {sig} |")

        lines.append(f"\n### 결론: 최고 성과 변형 — **{best['name']}** ({self._pct(best['rate'])})")

        formatted = "\n".join(lines)
        return formatted

    # ═══════════════════════════════════════════
    #  6. 종합 분석 (Full)
    # ═══════════════════════════════════════════

    async def _full_analysis(self, kwargs: dict) -> str:
        visitors_a = int(kwargs.get("visitors_a", 0))
        visitors_b = int(kwargs.get("visitors_b", 0))

        if visitors_a <= 0 or visitors_b <= 0:
            return ("A/B 테스트 데이터를 입력해주세요.\n"
                    "전환율 검정: visitors_a, conversions_a, visitors_b, conversions_b\n"
                    "표본 크기 계산: baseline_rate, mde\n"
                    "매출 검정: mean_a, std_a, n_a, mean_b, std_b, n_b")

        sections = ["# A/B 테스트 종합 분석 리포트\n", "---"]

        # 전환율 검정
        try:
            result = await self._ab_test(kwargs)
            sections.append(f"\n{result}")
        except Exception as e:
            sections.append(f"\n전환율 검정 실패: {e}")

        sections.append("\n---")

        # 검정력 분석
        try:
            result = await self._power_analysis(kwargs)
            sections.append(f"\n{result}")
        except Exception as e:
            sections.append(f"\n검정력 분석 실패: {e}")

        return "\n".join(sections)
