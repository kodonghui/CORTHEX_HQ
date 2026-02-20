"""
고객 코호트 분석 도구 (Customer Cohort Analyzer)

코호트 리텐션 + LTV(3가지 방법) + 이탈 분석 + RFM + CAC 회수 기간으로
"고객이 얼마나 오래 머물고, 얼마나 가치 있는가"를 정량화합니다.

학술 근거:
  - Fader & Hardie, "Probability Models for CLV" (2005) — BG/NBD, Pareto/NBD
  - Peter Fader, "Customer Centricity" (Wharton, 2020) — 고객 가치 차별화
  - Bessemer Venture Partners, "Cloud Index" (2024) — SaaS 이탈율 벤치마크
  - RFM Analysis (Arthur Hughes, 1994) — 고객 세분화

사용 방법:
  - action="full"      : 전체 코호트 분석 종합
  - action="retention"  : 코호트 리텐션 매트릭스
  - action="ltv"        : LTV 계산 (Simple, DCF, Cohort 3가지)
  - action="churn"      : 이탈 분석 + 벤치마크
  - action="rfm"        : RFM 세분화
  - action="payback"    : CAC 회수 기간 분석

필요 환경변수: 없음
필요 라이브러리: 없음 (표준 라이브러리만 사용)
"""
from __future__ import annotations

import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.customer_cohort_analyzer")

# 산업별 이탈률 벤치마크 (Bessemer, ProfitWell 2024)
_CHURN_BENCHMARKS: dict[str, dict] = {
    "SaaS_B2B_Enterprise": {"monthly": 0.5, "annual": 6, "desc": "B2B 엔터프라이즈 SaaS"},
    "SaaS_B2B_SMB": {"monthly": 3.0, "annual": 31, "desc": "B2B 중소기업 SaaS"},
    "SaaS_B2C": {"monthly": 5.0, "annual": 46, "desc": "B2C SaaS"},
    "Mobile_App": {"monthly": 8.0, "annual": 63, "desc": "모바일 앱"},
    "E-Commerce": {"monthly": 6.0, "annual": 52, "desc": "이커머스"},
    "EdTech": {"monthly": 4.0, "annual": 39, "desc": "에드테크"},
    "FinTech": {"monthly": 2.5, "annual": 26, "desc": "핀테크"},
    "Streaming": {"monthly": 5.5, "annual": 49, "desc": "스트리밍 서비스"},
}

# LTV:CAC 등급 (a16z, David Skok)
_LTV_CAC_GRADES = {
    "world_class": {"min": 5.0, "grade": "A+", "desc": "세계 최고 수준"},
    "excellent": {"min": 4.0, "grade": "A", "desc": "우수"},
    "healthy": {"min": 3.0, "grade": "B", "desc": "건강 (SaaS 최소 기준)"},
    "concerning": {"min": 2.0, "grade": "C", "desc": "주의 (개선 필요)"},
    "danger": {"min": 1.0, "grade": "D", "desc": "위험 (CAC > LTV 가능)"},
    "critical": {"min": 0, "grade": "F", "desc": "심각 (사업 재검토)"},
}

# 리텐션 벤치마크 (Bessemer, Mixpanel)
_RETENTION_BENCHMARKS = {
    "month_1": {"excellent": 80, "good": 60, "poor": 40},
    "month_3": {"excellent": 60, "good": 40, "poor": 20},
    "month_6": {"excellent": 45, "good": 30, "poor": 15},
    "month_12": {"excellent": 35, "good": 20, "poor": 10},
}


class CustomerCohortAnalyzer(BaseTool):
    """고객 코호트 분석 — 리텐션 + LTV(3법) + 이탈 + RFM + CAC 회수."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_analysis,
            "retention": self._retention_matrix,
            "ltv": self._ltv_calculation,
            "churn": self._churn_analysis,
            "rfm": self._rfm_segmentation,
            "payback": self._cac_payback,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return (
            f"알 수 없는 action: {action}. "
            "full, retention, ltv, churn, rfm, payback 중 하나를 사용하세요."
        )

    # ── Full ──────────────────────────────────────────────

    async def _full_analysis(self, p: dict) -> str:
        ret = await self._retention_matrix(p)
        ltv = await self._ltv_calculation(p)
        churn = await self._churn_analysis(p)
        rfm = await self._rfm_segmentation(p)
        payback = await self._cac_payback(p)

        lines = [
            "# 👥 고객 코호트 분석 종합 보고서",
            "", "## 1. 코호트 리텐션", ret,
            "", "## 2. LTV 계산 (3가지 방법)", ltv,
            "", "## 3. 이탈 분석", churn,
            "", "## 4. RFM 세분화", rfm,
            "", "## 5. CAC 회수 기간", payback,
            "", "---",
            "학술 참고: Fader & Hardie (2005), Bessemer (2024), Hughes RFM (1994)",
        ]
        return "\n".join(lines)

    # ── Retention: 코호트 리텐션 매트릭스 ──────────────────

    async def _retention_matrix(self, p: dict) -> str:
        initial_users = int(p.get("initial_users", 0))
        monthly_churn_pct = float(p.get("monthly_churn_pct", 0))
        months = int(p.get("months", 12))

        if initial_users <= 0:
            return "코호트 리텐션: initial_users(초기 사용자 수), monthly_churn_pct(월 이탈률%) 를 입력하세요."

        if monthly_churn_pct <= 0:
            monthly_churn_pct = 5.0  # 기본 5%

        retention_rate = 1 - (monthly_churn_pct / 100)

        lines = [
            "### 코호트 리텐션 매트릭스",
            f"(초기: {initial_users:,}명, 월 이탈률: {monthly_churn_pct:.1f}%)",
            "",
            "| 월 | 잔존 고객 | 리텐션율 | 이탈 고객 | 벤치마크 |",
            "|-----|---------|---------|---------|---------|",
        ]

        for m in range(months + 1):
            remaining = initial_users * (retention_rate ** m)
            ret_pct = (retention_rate ** m) * 100
            churned = initial_users - remaining

            # 벤치마크 비교
            bm_key = f"month_{m}" if m in [1, 3, 6, 12] else None
            if bm_key and bm_key in _RETENTION_BENCHMARKS:
                bm = _RETENTION_BENCHMARKS[bm_key]
                if ret_pct >= bm["excellent"]:
                    bm_str = "🟢 상위"
                elif ret_pct >= bm["good"]:
                    bm_str = "🟡 보통"
                else:
                    bm_str = "🔴 하위"
            else:
                bm_str = "—"

            lines.append(f"| {m}개월 | {remaining:,.0f} | {ret_pct:.1f}% | {churned:,.0f} | {bm_str} |")

        # 리텐션 커브 시각화
        lines.extend(["", "### 리텐션 커브"])
        for m in range(months + 1):
            ret_pct = (retention_rate ** m) * 100
            bar_len = int(ret_pct / 2)
            bar = "█" * bar_len + "░" * (50 - bar_len)
            lines.append(f"  {m:2d}M [{bar}] {ret_pct:.0f}%")

        # 반감기 계산
        half_life = math.log(0.5) / math.log(retention_rate) if retention_rate > 0 and retention_rate < 1 else float('inf')
        lines.append(f"\n📌 **반감기(Half-Life)**: {half_life:.1f}개월 (50% 이탈까지 걸리는 시간)")

        return "\n".join(lines)

    # ── LTV: 3가지 방법 ──────────────────────────────────

    async def _ltv_calculation(self, p: dict) -> str:
        arpu = float(p.get("arpu_monthly", 0))
        monthly_churn = float(p.get("monthly_churn_pct", 0))
        gross_margin = float(p.get("gross_margin_pct", 70))
        discount_rate_annual = float(p.get("discount_rate_annual", 10))
        currency = p.get("currency", "원")

        if arpu <= 0:
            return self._ltv_guide()

        if monthly_churn <= 0:
            monthly_churn = 5.0

        churn_decimal = monthly_churn / 100
        gm_decimal = gross_margin / 100
        monthly_discount = discount_rate_annual / 100 / 12

        # 방법 1: Simple LTV (Skok)
        ltv_simple = arpu * gm_decimal / churn_decimal

        # 방법 2: DCF LTV (할인된 현금흐름)
        ltv_dcf = arpu * gm_decimal / (churn_decimal + monthly_discount)

        # 방법 3: Cohort LTV (36개월 시뮬레이션)
        retention_rate = 1 - churn_decimal
        ltv_cohort = 0
        for m in range(1, 37):
            surviving_pct = retention_rate ** m
            monthly_revenue = arpu * gm_decimal * surviving_pct
            discount_factor = 1 / ((1 + monthly_discount) ** m)
            ltv_cohort += monthly_revenue * discount_factor

        avg_ltv = (ltv_simple + ltv_dcf + ltv_cohort) / 3
        avg_lifetime = 1 / churn_decimal  # 평균 고객 수명 (개월)

        lines = [
            "### LTV 계산 — 3가지 방법 비교",
            "",
            f"**입력값:** ARPU={arpu:,.0f}{currency}/월, 이탈률={monthly_churn:.1f}%/월, "
            f"마진={gross_margin:.0f}%, 할인율={discount_rate_annual:.0f}%/년",
            "",
            "| 방법 | LTV | 공식/설명 |",
            "|------|-----|---------|",
            f"| Simple (Skok) | **{ltv_simple:,.0f}{currency}** | ARPU × GM ÷ Churn |",
            f"| DCF | **{ltv_dcf:,.0f}{currency}** | ARPU × GM ÷ (Churn + 할인율) |",
            f"| Cohort (36M) | **{ltv_cohort:,.0f}{currency}** | 36개월 코호트 DCF 합산 |",
            "",
            f"**평균 LTV: {avg_ltv:,.0f}{currency}**",
            f"**평균 고객 수명: {avg_lifetime:.1f}개월 ({avg_lifetime/12:.1f}년)**",
            "",
            "### 방법별 특징",
            "| 방법 | 장점 | 단점 | 적합한 경우 |",
            "|------|------|------|---------|",
            "| Simple | 간단, 빠른 계산 | 화폐 시간가치 무시 | 빠른 추정 |",
            "| DCF | 할인율 반영 | 일정 이탈률 가정 | 투자자 보고 |",
            "| Cohort | 가장 현실적 | 데이터 필요 | 정밀 분석 |",
        ]
        return "\n".join(lines)

    def _ltv_guide(self) -> str:
        return "\n".join([
            "### LTV 계산을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| arpu_monthly | 월 평균 매출 (ARPU) | 29900 |",
            "| monthly_churn_pct | 월 이탈률 (%) | 5.0 |",
            "| gross_margin_pct | 매출총이익률 (%) | 70 |",
            "| discount_rate_annual | 연 할인율 (%) | 10 |",
        ])

    # ── Churn: 이탈 분석 ─────────────────────────────────

    async def _churn_analysis(self, p: dict) -> str:
        monthly_churn = float(p.get("monthly_churn_pct", 0))
        industry = p.get("industry", "SaaS_B2B_SMB")

        if monthly_churn <= 0:
            return self._churn_guide()

        annual_churn = (1 - (1 - monthly_churn / 100) ** 12) * 100
        bm = _CHURN_BENCHMARKS.get(industry, _CHURN_BENCHMARKS["SaaS_B2B_SMB"])

        if monthly_churn <= bm["monthly"] * 0.5:
            grade = "🏆 최상급"
        elif monthly_churn <= bm["monthly"]:
            grade = "🟢 양호"
        elif monthly_churn <= bm["monthly"] * 1.5:
            grade = "🟡 주의"
        else:
            grade = "🔴 위험"

        lines = [
            "### 이탈 분석",
            f"**월 이탈률: {monthly_churn:.1f}% → 연환산: {annual_churn:.1f}%**",
            f"**{bm['desc']} 벤치마크 대비: {grade}**",
            "",
            "### 산업별 이탈률 벤치마크 (Bessemer, ProfitWell 2024)",
            "| 산업 | 월 이탈률 | 연 이탈률 | 상태 |",
            "|------|---------|---------|------|",
        ]

        for key, data in _CHURN_BENCHMARKS.items():
            marker = " ← 기준" if key == industry else ""
            lines.append(f"| {data['desc']}{marker} | {data['monthly']:.1f}% | {data['annual']}% | — |")

        # 이탈 영향 시뮬레이션
        lines.extend([
            "",
            "### 이탈률 개선 효과 (1% 감소 시)",
            "| 개선 | 월 이탈률 | 연 잔존율 | 평균 수명 | LTV 배수 |",
            "|------|---------|---------|---------|---------|",
        ])
        for delta in [0, -1, -2, -3]:
            new_churn = max(0.5, monthly_churn + delta)
            annual_ret = ((1 - new_churn / 100) ** 12) * 100
            lifetime = 1 / (new_churn / 100)
            ltv_mult = (monthly_churn / 100) / (new_churn / 100) if new_churn > 0 else 1
            label = "현재" if delta == 0 else f"{delta:+d}%p"
            lines.append(f"| {label} | {new_churn:.1f}% | {annual_ret:.1f}% | {lifetime:.1f}개월 | ×{ltv_mult:.2f} |")

        lines.append(f"\n📌 **핵심**: 이탈률 1%p 감소 = LTV {(monthly_churn / max(0.5, monthly_churn - 1) - 1) * 100:.0f}% 증가")
        return "\n".join(lines)

    def _churn_guide(self) -> str:
        return "이탈 분석: monthly_churn_pct(월 이탈률 %), industry(산업 분류)를 입력하세요."

    # ── RFM: 고객 세분화 ─────────────────────────────────

    @staticmethod
    def _quintile_scores(values: list[float], reverse: bool = False) -> list[int]:
        """값 목록을 실제 분포 기준 5분위(quintile)로 나눠 1~5 점수 부여.

        Arthur Hughes (1994) RFM 원전: 고객을 각 축별로 균등 5등분.
        reverse=True면 값이 작을수록 높은 점수 (Recency에 사용: 최근일수록 높은 점수).
        """
        if not values:
            return []
        n = len(values)
        # (값, 원래 인덱스) 정렬
        indexed = sorted(enumerate(values), key=lambda x: x[1], reverse=reverse)
        scores = [0] * n
        for rank, (orig_idx, _) in enumerate(indexed):
            # 균등 5분위: rank 0~(n/5-1) → 5점, 다음 → 4점, ...
            quintile = min(int(rank / max(n / 5, 1)), 4)
            scores[orig_idx] = 5 - quintile
        return scores

    @staticmethod
    def _classify_rfm(r: int, f: int, m: int) -> tuple[str, str]:
        """RFM 점수 조합으로 세그먼트 분류 (Hughes, 1994 + Putler 확장).

        Returns: (세그먼트명, 추천 액션)
        """
        avg = (r + f + m) / 3
        if r >= 4 and f >= 4 and m >= 4:
            return "VIP (Champions)", "독점 혜택, 충성도 프로그램, 신제품 얼리 액세스"
        if f >= 4 and m >= 4:
            return "충성 고객 (Loyal)", "업셀/크로스셀, 추천 프로그램, 리워드"
        if r >= 4 and f >= 3:
            return "잠재 충성 (Potential Loyalist)", "관계 강화, 멤버십 제안, 개인화 추천"
        if r >= 4 and f <= 2:
            return "신규 고객 (New)", "온보딩 최적화, 첫 구매 경험 극대화"
        if r <= 2 and f >= 3 and m >= 3:
            return "관심 필요 (At Risk)", "재참여 캠페인, 할인 제공, 피드백 요청"
        if r <= 2 and f <= 2:
            return "이탈 위험 (Hibernating)", "윈백 캠페인, 설문 조사, 특별 오퍼"
        if avg <= 2:
            return "이탈 (Lost)", "최종 할인 or 포기 (ROI 낮음)"
        return "일반 고객 (Regular)", "정기 커뮤니케이션, 가치 제안 강화"

    async def _rfm_segmentation(self, p: dict) -> str:
        total_customers = int(p.get("total_customers", 0))
        customers_raw = p.get("customers", None)

        # ── 동적 RFM: 개별 고객 데이터가 제공된 경우 실제 분위수 계산 ──
        if customers_raw and isinstance(customers_raw, list) and len(customers_raw) > 0:
            return self._rfm_dynamic(customers_raw)

        # ── 정적 폴백: total_customers만 제공된 경우 업계 평균 비율 적용 ──
        if total_customers <= 0:
            return self._rfm_guide()

        # RFM 세그먼트별 비율 (업계 평균 기준)
        segments = [
            {"name": "VIP (Champions)", "rfm": "555", "pct": 8, "action": "독점 혜택, 충성도 프로그램"},
            {"name": "충성 고객 (Loyal)", "rfm": "X4X", "pct": 12, "action": "업셀/크로스셀, 추천 프로그램"},
            {"name": "잠재 충성 (Potential)", "rfm": "X3X", "pct": 15, "action": "관계 강화, 멤버십 제안"},
            {"name": "신규 고객 (New)", "rfm": "5X1", "pct": 10, "action": "온보딩 최적화, 첫 구매 경험"},
            {"name": "관심 필요 (At Risk)", "rfm": "2XX", "pct": 18, "action": "재참여 캠페인, 할인 제공"},
            {"name": "이탈 위험 (Hibernating)", "rfm": "1XX", "pct": 20, "action": "윈백 캠페인, 설문 조사"},
            {"name": "이탈 (Lost)", "rfm": "111", "pct": 17, "action": "최종 할인 or 포기 (ROI 낮음)"},
        ]

        lines = [
            "### RFM 세분화 분석 (Arthur Hughes, 1994)",
            f"(전체 고객: {total_customers:,}명 — 업계 평균 비율 적용)",
            "",
            "| 세그먼트 | RFM 패턴 | 비율 | 예상 고객수 | 추천 전략 |",
            "|---------|---------|------|----------|---------|",
        ]

        for seg in segments:
            count = int(total_customers * seg["pct"] / 100)
            lines.append(
                f"| {seg['name']} | {seg['rfm']} | {seg['pct']}% | {count:,}명 | {seg['action']} |"
            )

        # RFM 피라미드
        lines.extend([
            "",
            "### RFM 고객 피라미드",
            "```",
            "          /\\",
            "         /VIP\\          8%",
            "        /------\\",
            "       / Loyal  \\      12%",
            "      /----------\\",
            "     / Potential  \\    15%",
            "    /--------------\\",
            "   /  At Risk       \\  18%",
            "  /------------------\\",
            " / Hibernating+Lost  \\ 37%",
            "/____________________\\",
            "```",
            "",
            "**RFM 축 설명:**",
            "- **R (Recency)**: 최근성 — 마지막 구매/방문이 얼마나 최근인가 (1=오래됨, 5=최근)",
            "- **F (Frequency)**: 빈도 — 얼마나 자주 구매/방문하는가 (1=드물게, 5=자주)",
            "- **M (Monetary)**: 금액 — 얼마나 많이 소비하는가 (1=적게, 5=많이)",
            "",
            "💡 **팁**: customers 파라미터로 개별 고객 데이터를 전달하면 실제 분위수 기반 동적 RFM을 수행합니다.",
        ])
        return "\n".join(lines)

    def _rfm_dynamic(self, customers: list[dict]) -> str:
        """개별 고객 데이터 기반 동적 RFM 세분화.

        각 고객의 recency/frequency/monetary 값으로 실제 5분위(quintile)를 계산하고
        RFM 점수를 부여합니다. Hughes (1994) 원전 방법론 충실 구현.

        customers: [{recency: int, frequency: int, monetary: float, name?: str}, ...]
        """
        # 데이터 정제
        parsed: list[dict] = []
        for i, c in enumerate(customers):
            if not isinstance(c, dict):
                continue
            parsed.append({
                "name": c.get("name", f"고객_{i+1}"),
                "recency": float(c.get("recency", 0)),
                "frequency": float(c.get("frequency", 0)),
                "monetary": float(c.get("monetary", 0)),
            })

        if not parsed:
            return self._rfm_guide()

        n = len(parsed)

        # 각 축별 실제 분위수(quintile) 점수 계산
        r_values = [c["recency"] for c in parsed]
        f_values = [c["frequency"] for c in parsed]
        m_values = [c["monetary"] for c in parsed]

        # Recency: 값이 작을수록(최근일수록) 높은 점수 → reverse=True
        r_scores = self._quintile_scores(r_values, reverse=True)
        # Frequency, Monetary: 값이 클수록 높은 점수 → reverse=False
        f_scores = self._quintile_scores(f_values, reverse=False)
        m_scores = self._quintile_scores(m_values, reverse=False)

        # 각 고객에 점수 부여 + 세그먼트 분류
        segment_counts: dict[str, int] = {}
        segment_actions: dict[str, str] = {}
        scored_customers: list[dict] = []

        for i, c in enumerate(parsed):
            r, f, m = r_scores[i], f_scores[i], m_scores[i]
            seg_name, action = self._classify_rfm(r, f, m)
            segment_counts[seg_name] = segment_counts.get(seg_name, 0) + 1
            segment_actions[seg_name] = action
            scored_customers.append({
                "name": c["name"],
                "R": r, "F": f, "M": m,
                "rfm": f"{r}{f}{m}",
                "segment": seg_name,
            })

        # 5분위 경계값 계산 (분석 재현성을 위해 표시)
        def _quintile_boundaries(values: list[float]) -> list[float]:
            s = sorted(values)
            return [s[max(0, int(len(s) * q / 5) - 1)] for q in range(1, 6)]

        r_bounds = _quintile_boundaries(r_values)
        f_bounds = _quintile_boundaries(f_values)
        m_bounds = _quintile_boundaries(m_values)

        lines = [
            "### RFM 세분화 분석 — 동적 분위수 기반 (Arthur Hughes, 1994)",
            f"(전체 고객: {n:,}명 — 실제 데이터 기반 quintile 산출)",
            "",
            "### 분위수(Quintile) 경계값",
            "| 축 | Q1(하위20%) | Q2 | Q3 | Q4 | Q5(상위20%) |",
            "|---|-----------|---|---|---|-----------|",
            f"| R (Recency) | ≤{r_bounds[0]:.0f} | ≤{r_bounds[1]:.0f} | ≤{r_bounds[2]:.0f} | ≤{r_bounds[3]:.0f} | ≤{r_bounds[4]:.0f} |",
            f"| F (Frequency) | ≤{f_bounds[0]:.0f} | ≤{f_bounds[1]:.0f} | ≤{f_bounds[2]:.0f} | ≤{f_bounds[3]:.0f} | ≤{f_bounds[4]:.0f} |",
            f"| M (Monetary) | ≤{m_bounds[0]:.0f} | ≤{m_bounds[1]:.0f} | ≤{m_bounds[2]:.0f} | ≤{m_bounds[3]:.0f} | ≤{m_bounds[4]:.0f} |",
            "",
            "### 세그먼트별 분포",
            "| 세그먼트 | 고객수 | 비율 | 추천 전략 |",
            "|---------|-------|------|---------|",
        ]

        # 세그먼트를 고객수 내림차순 정렬
        sorted_segs = sorted(segment_counts.items(), key=lambda x: x[1], reverse=True)
        for seg_name, count in sorted_segs:
            pct = count / n * 100
            action = segment_actions[seg_name]
            lines.append(f"| {seg_name} | {count:,}명 | {pct:.1f}% | {action} |")

        # 상위/하위 고객 샘플 (최대 5명씩)
        # RFM 합산 점수로 정렬
        scored_customers.sort(key=lambda x: x["R"] + x["F"] + x["M"], reverse=True)

        if n > 5:
            lines.extend([
                "",
                "### 상위 고객 (RFM 합산 Top 5)",
                "| 고객 | R | F | M | RFM 코드 | 세그먼트 |",
                "|------|---|---|---|---------|---------|",
            ])
            for c in scored_customers[:5]:
                lines.append(f"| {c['name']} | {c['R']} | {c['F']} | {c['M']} | {c['rfm']} | {c['segment']} |")

            lines.extend([
                "",
                "### 하위 고객 (RFM 합산 Bottom 5)",
                "| 고객 | R | F | M | RFM 코드 | 세그먼트 |",
                "|------|---|---|---|---------|---------|",
            ])
            for c in scored_customers[-5:]:
                lines.append(f"| {c['name']} | {c['R']} | {c['F']} | {c['M']} | {c['rfm']} | {c['segment']} |")

        lines.extend([
            "",
            "**RFM 축 설명:**",
            "- **R (Recency)**: 최근성 — 값이 작을수록(최근) 높은 점수 (역순 quintile)",
            "- **F (Frequency)**: 빈도 — 값이 클수록 높은 점수",
            "- **M (Monetary)**: 금액 — 값이 클수록 높은 점수",
            "",
            f"📌 **분석 기준**: {n:,}명의 실제 분포에서 각 축을 5등분(quintile)하여 1~5점 부여.",
            "   업계 평균이 아닌 **자사 데이터 기반** 상대 평가입니다.",
        ])
        return "\n".join(lines)

    def _rfm_guide(self) -> str:
        return "\n".join([
            "### RFM 세분화를 위해 필요한 입력값:",
            "",
            "**방법 1 — 간편 (업계 평균 비율 적용):**",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| total_customers | 전체 고객수 | 10000 |",
            "",
            "**방법 2 — 동적 분위수 (실제 데이터 기반, 권장):**",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            '| customers | 고객 리스트 | [{recency: 5, frequency: 12, monetary: 150000}, ...] |',
            "",
            "- **recency**: 마지막 구매 이후 경과일 (작을수록 좋음)",
            "- **frequency**: 구매 횟수 (클수록 좋음)",
            "- **monetary**: 총 구매 금액 (클수록 좋음)",
            "- **name** (선택): 고객 식별자",
        ])

    # ── CAC Payback: 회수 기간 ──────────────────────────

    async def _cac_payback(self, p: dict) -> str:
        cac = float(p.get("cac", 0))
        arpu = float(p.get("arpu_monthly", 0))
        gross_margin = float(p.get("gross_margin_pct", 70))
        currency = p.get("currency", "원")

        if cac <= 0 or arpu <= 0:
            return "CAC 회수 기간: cac(고객 획득 비용), arpu_monthly(월 ARPU)를 입력하세요."

        gm = gross_margin / 100
        monthly_contribution = arpu * gm
        payback_months = cac / monthly_contribution if monthly_contribution > 0 else float('inf')

        if payback_months <= 6:
            grade = "🏆 최상급 (6개월 이내)"
        elif payback_months <= 12:
            grade = "🟢 양호 (12개월 이내)"
        elif payback_months <= 18:
            grade = "🟡 주의 (18개월 이내)"
        else:
            grade = "🔴 위험 (18개월 초과)"

        # LTV:CAC 계산
        monthly_churn = float(p.get("monthly_churn_pct", 5))
        ltv = arpu * gm / (monthly_churn / 100) if monthly_churn > 0 else 0
        ltv_cac = ltv / cac if cac > 0 else 0

        ltv_cac_grade = "F"
        for key, data in _LTV_CAC_GRADES.items():
            if ltv_cac >= data["min"]:
                ltv_cac_grade = f"{data['grade']} ({data['desc']})"
                break

        lines = [
            "### CAC 회수 기간 분석",
            "",
            f"- CAC: {cac:,.0f}{currency}",
            f"- ARPU: {arpu:,.0f}{currency}/월",
            f"- Gross Margin: {gross_margin:.0f}%",
            f"- 월 공헌이익: {monthly_contribution:,.0f}{currency}",
            "",
            f"**CAC 회수 기간: {payback_months:.1f}개월 → {grade}**",
            f"**LTV: {ltv:,.0f}{currency} / LTV:CAC = {ltv_cac:.1f}:1 → {ltv_cac_grade}**",
            "",
            "### 회수 시뮬레이션",
            "| 월 | 누적 공헌이익 | CAC 잔여 | 상태 |",
            "|-----|-----------|---------|------|",
        ]

        for m in range(1, min(25, int(payback_months * 2) + 1)):
            cumul = monthly_contribution * m
            remaining = cac - cumul
            status = "✅ 회수" if remaining <= 0 else "⏳ 미회수"
            lines.append(f"| {m}개월 | {cumul:,.0f} | {max(0, remaining):,.0f} | {status} |")
            if remaining <= 0 and m > payback_months:
                break

        return "\n".join(lines)
