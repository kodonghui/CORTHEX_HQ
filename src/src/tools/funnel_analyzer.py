"""
AARRR 퍼널 분석 도구 (Funnel Analyzer) — 마케팅 퍼널의 병목을 찾아냅니다.

"고객이 어디서 빠지는가?"를 수학적으로 진단하고,
성장 건강도(Quick Ratio)까지 계산하는 교수급 성장 분석 도구입니다.

학술 근거:
  - Pirate Metrics AARRR (Dave McClure, "Startup Metrics for Pirates", 2007)
  - Growth Accounting & Quick Ratio (Tribe Capital, 2019)
  - RARRA Framework (Thomas Petit & Gabor Papp, Product-led Growth)
  - Funnel Optimization (Andrew Chen, "The Cold Start Problem", 2021)

사용 방법:
  - action="analyze"       : AARRR 퍼널 전환율 분석 (단계별 전환/이탈)
  - action="bottleneck"    : 병목 구간 자동 진단 (가장 큰 이탈 단계)
  - action="growth"        : 성장 건강도 — Quick Ratio + Growth Accounting
  - action="benchmark"     : 업종별 벤치마크 비교 (SaaS/이커머스/교육)
  - action="forecast"      : 퍼널 개선 시 예상 효과 시뮬레이션
  - action="full"          : 종합 분석 (위 전부 포함)

입력 형식:
  - visitors: 방문자 수
  - signups: 가입자 수 (Acquisition)
  - activated: 활성화 사용자 수 (Activation — 핵심 기능 1회 이상 사용)
  - retained: 유지 사용자 수 (Retention — 다음 주/월에도 재방문)
  - revenue_users: 결제 사용자 수 (Revenue)
  - referrers: 추천 사용자 수 (Referral — 다른 사람을 초대한 수)
  - period: 측정 기간 (예: "2026-01", "2026-Q1", "weekly")
  - industry: 업종 (saas/ecommerce/education/media/fintech) — benchmark용

필요 환경변수: 없음
필요 라이브러리: 없음 (순수 Python + numpy)
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.funnel_analyzer")


# ═══════════════════════════════════════════════════════
#  업종별 벤치마크 데이터 (2024-2025 업계 리서치 기준)
# ═══════════════════════════════════════════════════════

_BENCHMARKS: dict[str, dict[str, dict[str, float]]] = {
    "saas": {
        "visitor_to_signup": {"low": 0.02, "median": 0.05, "top": 0.10},
        "signup_to_activated": {"low": 0.20, "median": 0.40, "top": 0.60},
        "activated_to_retained": {"low": 0.15, "median": 0.30, "top": 0.50},
        "retained_to_revenue": {"low": 0.02, "median": 0.05, "top": 0.10},
        "revenue_to_referral": {"low": 0.05, "median": 0.15, "top": 0.30},
        "source": "OpenView 2024 SaaS Benchmarks + First Round Capital",
    },
    "ecommerce": {
        "visitor_to_signup": {"low": 0.01, "median": 0.03, "top": 0.07},
        "signup_to_activated": {"low": 0.30, "median": 0.50, "top": 0.70},
        "activated_to_retained": {"low": 0.10, "median": 0.25, "top": 0.40},
        "retained_to_revenue": {"low": 0.05, "median": 0.12, "top": 0.25},
        "revenue_to_referral": {"low": 0.02, "median": 0.08, "top": 0.20},
        "source": "Shopify 2024 Commerce Report + Baymard Institute",
    },
    "education": {
        "visitor_to_signup": {"low": 0.03, "median": 0.08, "top": 0.15},
        "signup_to_activated": {"low": 0.25, "median": 0.45, "top": 0.65},
        "activated_to_retained": {"low": 0.10, "median": 0.20, "top": 0.35},
        "retained_to_revenue": {"low": 0.01, "median": 0.03, "top": 0.08},
        "revenue_to_referral": {"low": 0.10, "median": 0.25, "top": 0.40},
        "source": "Class Central 2024 + EdSurge Research",
    },
    "media": {
        "visitor_to_signup": {"low": 0.01, "median": 0.04, "top": 0.08},
        "signup_to_activated": {"low": 0.35, "median": 0.55, "top": 0.75},
        "activated_to_retained": {"low": 0.08, "median": 0.18, "top": 0.30},
        "retained_to_revenue": {"low": 0.005, "median": 0.02, "top": 0.05},
        "revenue_to_referral": {"low": 0.03, "median": 0.10, "top": 0.25},
        "source": "Reuters Digital News Report 2024",
    },
    "fintech": {
        "visitor_to_signup": {"low": 0.01, "median": 0.03, "top": 0.06},
        "signup_to_activated": {"low": 0.15, "median": 0.30, "top": 0.50},
        "activated_to_retained": {"low": 0.20, "median": 0.40, "top": 0.60},
        "retained_to_revenue": {"low": 0.10, "median": 0.25, "top": 0.45},
        "revenue_to_referral": {"low": 0.02, "median": 0.08, "top": 0.18},
        "source": "Plaid 2024 Fintech Report + a16z Fintech Metrics",
    },
}

# AARRR 단계별 한국어 매핑
_STAGE_NAMES = {
    "visitor_to_signup": ("방문 → 가입", "Acquisition"),
    "signup_to_activated": ("가입 → 활성화", "Activation"),
    "activated_to_retained": ("활성화 → 유지", "Retention"),
    "retained_to_revenue": ("유지 → 결제", "Revenue"),
    "revenue_to_referral": ("결제 → 추천", "Referral"),
}


# ═══════════════════════════════════════════════════════
#  FunnelAnalyzerTool
# ═══════════════════════════════════════════════════════

class FunnelAnalyzerTool(BaseTool):
    """교수급 AARRR 퍼널 분석 도구 — 전환율 + 병목 진단 + 성장 건강도."""

    # ── 메인 디스패처 ────────────────────────

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        if query and not any(kwargs.get(k) for k in ("visitors", "signups")):
            return (
                "퍼널 데이터를 입력해주세요.\n"
                "필수: visitors(방문자), signups(가입), activated(활성화), "
                "retained(유지), revenue_users(결제), referrers(추천)\n"
                "예: visitors=10000, signups=500, activated=200, "
                "retained=80, revenue_users=20, referrers=5"
            )

        action = kwargs.get("action", "full")

        actions = {
            "analyze": self._analyze_funnel,
            "bottleneck": self._find_bottleneck,
            "growth": self._growth_accounting,
            "benchmark": self._benchmark_compare,
            "forecast": self._forecast_improvement,
            "full": self._full_analysis,
        }

        handler = actions.get(action)
        if handler:
            return await handler(kwargs)

        return (
            f"알 수 없는 action: {action}. "
            "analyze, bottleneck, growth, benchmark, forecast, full 중 하나를 사용하세요."
        )

    # ── 공통: 퍼널 데이터 파싱 ─────────────

    def _parse_funnel(self, kwargs: dict) -> tuple[dict | None, str | None]:
        """입력에서 퍼널 단계별 수치를 추출합니다."""
        try:
            visitors = int(kwargs.get("visitors", 0))
            signups = int(kwargs.get("signups", 0))
            activated = int(kwargs.get("activated", 0))
            retained = int(kwargs.get("retained", 0))
            revenue_users = int(kwargs.get("revenue_users", 0))
            referrers = int(kwargs.get("referrers", 0))
        except (ValueError, TypeError) as e:
            return None, f"숫자 형식이 올바르지 않습니다: {e}"

        if visitors <= 0:
            return None, "visitors(방문자 수)는 1 이상이어야 합니다."
        if signups < 0 or activated < 0 or retained < 0:
            return None, "각 단계의 수치는 0 이상이어야 합니다."

        funnel = {
            "visitors": visitors,
            "signups": signups,
            "activated": activated,
            "retained": retained,
            "revenue_users": revenue_users,
            "referrers": referrers,
        }

        return funnel, None

    def _calc_rates(self, funnel: dict) -> dict:
        """단계별 전환율 계산."""
        v = funnel["visitors"]
        s = funnel["signups"]
        a = funnel["activated"]
        r = funnel["retained"]
        rev = funnel["revenue_users"]
        ref = funnel["referrers"]

        def safe_div(num: int, den: int) -> float:
            return num / den if den > 0 else 0.0

        rates = {
            "visitor_to_signup": safe_div(s, v),
            "signup_to_activated": safe_div(a, s),
            "activated_to_retained": safe_div(r, a),
            "retained_to_revenue": safe_div(rev, r),
            "revenue_to_referral": safe_div(ref, rev),
            "overall": safe_div(rev, v),  # 전체 전환율 (방문→결제)
        }

        # 각 단계별 이탈률
        drops = {
            "visitor_to_signup_drop": 1 - rates["visitor_to_signup"],
            "signup_to_activated_drop": 1 - rates["signup_to_activated"],
            "activated_to_retained_drop": 1 - rates["activated_to_retained"],
            "retained_to_revenue_drop": 1 - rates["retained_to_revenue"],
            "revenue_to_referral_drop": 1 - rates["revenue_to_referral"],
        }

        return {**rates, **drops}

    @staticmethod
    def _pct(val: float) -> str:
        """소수를 퍼센트 문자열로."""
        return f"{val * 100:.1f}%"

    @staticmethod
    def _fmt_num(val: int | float) -> str:
        """숫자 포맷팅 (천 단위 콤마)."""
        if isinstance(val, float):
            return f"{val:,.1f}"
        return f"{val:,}"

    @staticmethod
    def _bar(ratio: float, width: int = 20) -> str:
        """비율을 시각적 막대로."""
        filled = max(0, min(width, int(ratio * width)))
        return "█" * filled + "░" * (width - filled)

    # ═══════════════════════════════════════════
    #  1. 퍼널 전환율 분석 (Analyze)
    # ═══════════════════════════════════════════

    async def _analyze_funnel(self, kwargs: dict) -> str:
        funnel, err = self._parse_funnel(kwargs)
        if err:
            return err
        rates = self._calc_rates(funnel)
        period = kwargs.get("period", "미지정")

        lines = ["## AARRR 퍼널 전환율 분석\n"]
        lines.append(f"측정 기간: **{period}**\n")

        # ── 퍼널 시각화 ──
        lines.append("### 퍼널 흐름")
        stages = [
            ("방문 (Visitors)", funnel["visitors"]),
            ("가입 (Acquisition)", funnel["signups"]),
            ("활성화 (Activation)", funnel["activated"]),
            ("유지 (Retention)", funnel["retained"]),
            ("결제 (Revenue)", funnel["revenue_users"]),
            ("추천 (Referral)", funnel["referrers"]),
        ]

        max_val = max(s[1] for s in stages) or 1
        for name, count in stages:
            ratio = count / max_val
            bar = self._bar(ratio)
            lines.append(f"  {bar} {self._fmt_num(count):>10}명 | {name}")

        # ── 단계별 전환율 테이블 ──
        lines.append("\n### 단계별 전환율")
        lines.append("| 단계 | 전환율 | 이탈률 | 이탈 인원 |")
        lines.append("|------|--------|--------|----------|")

        stage_keys = [
            "visitor_to_signup", "signup_to_activated",
            "activated_to_retained", "retained_to_revenue",
            "revenue_to_referral",
        ]

        stage_pairs = [
            (funnel["visitors"], funnel["signups"]),
            (funnel["signups"], funnel["activated"]),
            (funnel["activated"], funnel["retained"]),
            (funnel["retained"], funnel["revenue_users"]),
            (funnel["revenue_users"], funnel["referrers"]),
        ]

        for key, (prev, curr) in zip(stage_keys, stage_pairs):
            name_ko, name_en = _STAGE_NAMES[key]
            rate = rates[key]
            drop = rates[f"{key}_drop"]
            lost = prev - curr
            lines.append(
                f"| {name_ko} ({name_en}) | "
                f"**{self._pct(rate)}** | {self._pct(drop)} | "
                f"{self._fmt_num(lost)}명 |"
            )

        # ── 전체 전환율 ──
        lines.append(f"\n### 전체 전환율 (방문 → 결제)")
        lines.append(f"  **{self._pct(rates['overall'])}** "
                      f"({self._fmt_num(funnel['visitors'])}명 방문 → "
                      f"{self._fmt_num(funnel['revenue_users'])}명 결제)")

        # ── AARRR 각 단계 해석 ──
        lines.append("\n### AARRR 단계별 해석")

        interpretations = {
            "visitor_to_signup": {
                "good": 0.05, "desc": "방문자가 가입하는 비율. 랜딩 페이지 품질과 가치 제안(Value Proposition)의 명확성을 반영",
            },
            "signup_to_activated": {
                "good": 0.40, "desc": "가입자가 핵심 기능을 처음 사용한 비율. 온보딩 경험의 품질을 반영",
            },
            "activated_to_retained": {
                "good": 0.30, "desc": "활성화된 사용자가 계속 돌아오는 비율. 제품의 핵심 가치와 습관 형성(Hook Model)을 반영",
            },
            "retained_to_revenue": {
                "good": 0.05, "desc": "유지 사용자가 결제하는 비율. 가격 정책과 유료 전환 유인의 효과를 반영",
            },
            "revenue_to_referral": {
                "good": 0.15, "desc": "결제 사용자가 다른 사람을 추천하는 비율. 제품 만족도(NPS)와 바이럴 루프를 반영",
            },
        }

        for key, info in interpretations.items():
            name_ko, name_en = _STAGE_NAMES[key]
            rate = rates[key]
            good = info["good"]
            status = "✅ 양호" if rate >= good else "⚠️ 개선 필요" if rate >= good * 0.5 else "🔴 심각"
            lines.append(f"\n**{name_ko}**: {self._pct(rate)} {status}")
            lines.append(f"  {info['desc']}")
            lines.append(f"  기준: {self._pct(good)} 이상이면 양호")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 Growth Marketing 교수입니다. AARRR 퍼널 데이터를 종합하여:\n"
                "1. 이 퍼널의 전반적 건강 상태 (상/중/하)\n"
                "2. 가장 시급히 개선해야 할 단계 1개와 구체적 개선 방법 3가지\n"
                "3. 이 전환율이 의미하는 비즈니스 상황 (성장기/정체기/위기)\n"
                "4. 다음 한 달간 집중해야 할 핵심 지표 1개\n"
                "Dave McClure의 AARRR 프레임워크에 입각하여 한국어로 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 퍼널 종합 분석\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  2. 병목 진단 (Bottleneck)
    # ═══════════════════════════════════════════

    async def _find_bottleneck(self, kwargs: dict) -> str:
        funnel, err = self._parse_funnel(kwargs)
        if err:
            return err
        rates = self._calc_rates(funnel)

        lines = ["## AARRR 퍼널 병목 진단\n"]

        # ── 이탈률 기준 정렬 ──
        drop_data = []
        stage_pairs = [
            ("visitor_to_signup", funnel["visitors"], funnel["signups"]),
            ("signup_to_activated", funnel["signups"], funnel["activated"]),
            ("activated_to_retained", funnel["activated"], funnel["retained"]),
            ("retained_to_revenue", funnel["retained"], funnel["revenue_users"]),
            ("revenue_to_referral", funnel["revenue_users"], funnel["referrers"]),
        ]

        for key, prev, curr in stage_pairs:
            if prev <= 0:
                continue
            drop_rate = rates[f"{key}_drop"]
            lost_count = prev - curr
            # 이탈 영향도 = 이탈률 × 해당 단계 인원 (절대 손실 규모)
            impact = drop_rate * prev
            drop_data.append({
                "key": key,
                "name_ko": _STAGE_NAMES[key][0],
                "name_en": _STAGE_NAMES[key][1],
                "drop_rate": drop_rate,
                "lost_count": lost_count,
                "prev_count": prev,
                "impact": impact,
            })

        # 이탈률 기준 내림차순
        drop_data.sort(key=lambda x: x["drop_rate"], reverse=True)

        lines.append("### 이탈률 순위 (가장 많이 빠지는 단계)")
        lines.append("| 순위 | 단계 | 이탈률 | 이탈 인원 | 영향도* |")
        lines.append("|------|------|--------|----------|---------|")

        for rank, d in enumerate(drop_data, 1):
            marker = " ← 🔴 **병목**" if rank == 1 else ""
            lines.append(
                f"| {rank}위 | {d['name_ko']} | "
                f"**{self._pct(d['drop_rate'])}** | "
                f"{self._fmt_num(d['lost_count'])}명 | "
                f"{self._fmt_num(d['impact'])}{marker} |"
            )

        lines.append("\n*영향도 = 이탈률 × 해당 단계 인원수 (절대적 손실 규모)*")

        # ── 병목 상세 분석 ──
        if drop_data:
            bottleneck = drop_data[0]
            lines.append(f"\n### 🔴 1위 병목: {bottleneck['name_ko']} ({bottleneck['name_en']})")
            lines.append(f"  이탈률: **{self._pct(bottleneck['drop_rate'])}**")
            lines.append(f"  이탈 인원: **{self._fmt_num(bottleneck['lost_count'])}명**")
            lines.append(f"  (전 단계 {self._fmt_num(bottleneck['prev_count'])}명 중 "
                         f"{self._fmt_num(bottleneck['lost_count'])}명 이탈)")

            # 병목별 전략적 처방전
            prescriptions = {
                "visitor_to_signup": [
                    "랜딩 페이지 가치 제안(Value Proposition) 명확화 — 3초 안에 '이게 왜 필요한지' 전달",
                    "가입 프로세스 간소화 — 필수 입력 3개 이하, 소셜 로그인 추가",
                    "사회적 증거(Social Proof) 배치 — 고객 수, 후기, 미디어 언급을 CTA 근처에",
                    "A/B 테스트: 헤드라인/CTA 버튼 색상/위치 실험",
                ],
                "signup_to_activated": [
                    "온보딩 체크리스트 도입 — 핵심 기능 1회 사용까지 안내 (Aha Moment 유도)",
                    "첫 사용 경험(FTUE) 최적화 — 가입 후 30초 내에 가치를 느끼게",
                    "이메일/푸시 드립 캠페인 — 가입 후 1시간/1일/3일 행동 유도 메시지",
                    "마찰 포인트 제거 — 사용자 세션 녹화(Hotjar) 분석으로 중도 이탈 지점 파악",
                ],
                "activated_to_retained": [
                    "습관 루프(Hook Model) 설계 — Trigger→Action→Reward→Investment 순환 구조",
                    "개인화 콘텐츠 — 사용 패턴 기반 추천 (AI 추천 엔진)",
                    "리인게이지먼트 캠페인 — 비활성 사용자에게 '놓친 업데이트' 알림",
                    "커뮤니티 구축 — 사용자 간 연결로 전환 비용(Switching Cost) 높이기",
                ],
                "retained_to_revenue": [
                    "가격 실험 — Van Westendorp 가격 민감도 조사로 최적 가격 탐색",
                    "무료→유료 전환 모멘트 최적화 — 사용량 제한 도달 시 자연스러운 업그레이드 유도",
                    "가치 강화 — 유료 기능의 체험 기회 제공 (14일 무료 트라이얼)",
                    "결제 마찰 제거 — 결제 수단 다양화, 환불 보장 강조",
                ],
                "revenue_to_referral": [
                    "추천 프로그램 설계 — 양측 모두에게 보상 (추천인 + 피추천인 혜택)",
                    "공유 가능한 콘텐츠 — '내 성과/결과'를 SNS에 자랑할 수 있는 기능",
                    "NPS 측정 후 추천의향 9-10점 고객만 타겟 추천 요청",
                    "바이럴 메커니즘 — 제품 사용 자체가 노출이 되는 구조 (예: 'Powered by X' 배지)",
                ],
            }

            rx = prescriptions.get(bottleneck["key"], [])
            if rx:
                lines.append(f"\n### 처방전 (전략적 개선 방안)")
                for i, item in enumerate(rx, 1):
                    lines.append(f"  {i}. {item}")

        # ── 영향도 기준 정렬 (다른 관점) ──
        impact_sorted = sorted(drop_data, key=lambda x: x["impact"], reverse=True)
        if impact_sorted and impact_sorted[0]["key"] != drop_data[0]["key"]:
            imp = impact_sorted[0]
            lines.append(f"\n### ⚠️ 참고: 영향도 기준 1위")
            lines.append(f"  {imp['name_ko']}: 이탈률 {self._pct(imp['drop_rate'])}이지만 "
                         f"절대 이탈 인원이 {self._fmt_num(imp['lost_count'])}명으로 가장 많음")
            lines.append("  (이탈률은 낮아도 인원이 많으면 개선 효과가 더 클 수 있음)")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 Growth Hacking 교수입니다. 퍼널 병목 데이터를 보고:\n"
                "1. 병목 단계가 왜 문제인지 비즈니스 맥락에서 설명\n"
                "2. 이 병목을 10%p 개선하면 최종 매출에 얼마나 영향을 주는지 계산\n"
                "3. 가장 빠르게 실행할 수 있는 Quick Win 1가지\n"
                "4. 장기적으로 구조적으로 해결하는 방법 1가지\n"
                "Dave McClure + Sean Ellis의 관점에서 한국어로 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 병목 종합 분석\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  3. 성장 건강도 (Growth Accounting)
    # ═══════════════════════════════════════════

    async def _growth_accounting(self, kwargs: dict) -> str:
        funnel, err = self._parse_funnel(kwargs)
        if err:
            return err
        rates = self._calc_rates(funnel)

        # Growth Accounting용 추가 입력
        new_users = int(kwargs.get("new_users", funnel["signups"]))
        resurrected = int(kwargs.get("resurrected", 0))  # 이탈 후 복귀
        churned = int(kwargs.get("churned", 0))  # 이번 기간 이탈
        prev_active = int(kwargs.get("prev_active", 0))  # 이전 기간 활성

        lines = ["## 성장 건강도 분석 (Growth Accounting)\n"]

        # ── Quick Ratio (Tribe Capital) ──
        # Quick Ratio = (신규 + 복귀) / 이탈
        # > 4: 매우 건강 / 2~4: 건강 / 1~2: 위험 / < 1: 축소
        if churned > 0:
            quick_ratio = (new_users + resurrected) / churned
        elif new_users + resurrected > 0:
            quick_ratio = float("inf")
        else:
            quick_ratio = 0

        lines.append("### Quick Ratio (Tribe Capital 방식)")
        lines.append(f"  공식: (신규 + 복귀) / 이탈 = ({self._fmt_num(new_users)} + "
                      f"{self._fmt_num(resurrected)}) / {self._fmt_num(churned)}")

        if quick_ratio == float("inf"):
            lines.append(f"  **Quick Ratio: ∞ (이탈 0명 — 완벽!)**")
            qr_grade = "S"
        else:
            lines.append(f"  **Quick Ratio: {quick_ratio:.2f}**")
            if quick_ratio >= 4:
                qr_grade = "A"
                lines.append("  등급: 🟢 **매우 건강** (4.0 이상) — 고속 성장 구간")
            elif quick_ratio >= 2:
                qr_grade = "B"
                lines.append("  등급: 🟢 **건강** (2.0~4.0) — 안정적 성장")
            elif quick_ratio >= 1:
                qr_grade = "C"
                lines.append("  등급: 🟡 **주의** (1.0~2.0) — 성장이 이탈을 겨우 상회")
            else:
                qr_grade = "D"
                lines.append("  등급: 🔴 **위험** (1.0 미만) — 사용자 순감소 중!")

        lines.append(f"\n  | 지표 | 수치 | 의미 |")
        lines.append(f"  |------|------|------|")
        lines.append(f"  | 신규 가입 | {self._fmt_num(new_users)}명 | 이번 기간 새로 가입한 사용자 |")
        lines.append(f"  | 복귀 | {self._fmt_num(resurrected)}명 | 이탈했다가 돌아온 사용자 |")
        lines.append(f"  | 이탈 | {self._fmt_num(churned)}명 | 이번 기간 떠난 사용자 |")
        if prev_active > 0:
            net_growth = new_users + resurrected - churned
            growth_rate = net_growth / prev_active
            lines.append(f"  | 순증 | {self._fmt_num(net_growth)}명 | 실질 성장 인원 |")
            lines.append(f"  | 성장률 | {self._pct(growth_rate)} | 전 기간 대비 |")

        # ── Retention Curve (간이 계산) ──
        lines.append("\n### 유지율 분석")
        if funnel["signups"] > 0:
            d1_retention = funnel["activated"] / funnel["signups"]
            d7_retention = funnel["retained"] / funnel["signups"]
            d30_retention = funnel["revenue_users"] / funnel["signups"]

            lines.append(f"  Day 1 (활성화): {self._pct(d1_retention)}")
            lines.append(f"  Day 7 (유지): {self._pct(d7_retention)}")
            lines.append(f"  Day 30 (결제): {self._pct(d30_retention)}")

            # 유지율 곡선 형태 판단
            if d7_retention > 0 and d1_retention > 0:
                decay_rate = 1 - (d7_retention / d1_retention)
                if decay_rate > 0.7:
                    lines.append("  곡선 형태: **급강하 (Cliff)** — 핵심 가치 전달 실패")
                elif decay_rate > 0.4:
                    lines.append("  곡선 형태: **완만한 하락 (Gradual)** — 보통")
                else:
                    lines.append("  곡선 형태: **평탄 (Flat)** — 강한 제품-시장 적합성(PMF)")

        # ── RARRA 분석 ──
        lines.append("\n### RARRA 분석 (Retention-first 관점)")
        lines.append("  AARRR은 Acquisition부터 시작하지만, RARRA는 Retention이 먼저입니다.")
        lines.append("  이유: 유지율이 낮으면 아무리 많이 모아도 '물 새는 바가지'")

        if funnel["signups"] > 0 and funnel["retained"] > 0:
            retention_rate = rates["activated_to_retained"]
            if retention_rate < 0.2:
                lines.append(f"  현재 유지율 {self._pct(retention_rate)}: 🔴 **PMF 미달성** "
                             "— Acquisition 투자를 줄이고 제품 개선에 집중")
            elif retention_rate < 0.4:
                lines.append(f"  현재 유지율 {self._pct(retention_rate)}: 🟡 **PMF 진행 중** "
                             "— 유지율 40% 이상 달성 후 마케팅 확대 권장")
            else:
                lines.append(f"  현재 유지율 {self._pct(retention_rate)}: 🟢 **PMF 달성** "
                             "— 마케팅 투자 확대 적기")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 Growth Analytics 교수입니다. 성장 건강도 데이터를 보고:\n"
                "1. Quick Ratio가 의미하는 현재 성장 궤적\n"
                "2. 유지율 곡선이 시사하는 제품-시장 적합성(PMF) 수준\n"
                "3. RARRA 관점에서 지금 집중해야 할 단계\n"
                "4. 3개월 후 예상 시나리오 (현재 추세 유지 시)\n"
                "Tribe Capital의 Growth Accounting 프레임워크로 한국어 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 성장 건강도 종합 분석\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  4. 벤치마크 비교 (Benchmark)
    # ═══════════════════════════════════════════

    async def _benchmark_compare(self, kwargs: dict) -> str:
        funnel, err = self._parse_funnel(kwargs)
        if err:
            return err
        rates = self._calc_rates(funnel)
        industry = kwargs.get("industry", "saas").lower()

        if industry not in _BENCHMARKS:
            available = ", ".join(_BENCHMARKS.keys())
            return f"지원 업종: {available}. industry 파라미터를 확인하세요."

        bench = _BENCHMARKS[industry]
        source = bench.get("source", "")

        lines = [f"## 업종별 벤치마크 비교 ({industry.upper()})\n"]
        lines.append(f"데이터 출처: {source}\n")

        lines.append("### 단계별 비교표")
        lines.append("| 단계 | 우리 | 하위 25% | 중간값 | 상위 25% | 위치 |")
        lines.append("|------|------|---------|--------|---------|------|")

        stage_keys = [
            "visitor_to_signup", "signup_to_activated",
            "activated_to_retained", "retained_to_revenue",
            "revenue_to_referral",
        ]

        grades = []
        for key in stage_keys:
            if key not in bench:
                continue
            name_ko, _ = _STAGE_NAMES[key]
            our = rates[key]
            low = bench[key]["low"]
            med = bench[key]["median"]
            top = bench[key]["top"]

            if our >= top:
                position = "🏆 상위"
                grade = "A"
            elif our >= med:
                position = "✅ 평균 이상"
                grade = "B"
            elif our >= low:
                position = "⚠️ 평균 이하"
                grade = "C"
            else:
                position = "🔴 하위"
                grade = "D"

            grades.append(grade)
            lines.append(
                f"| {name_ko} | **{self._pct(our)}** | "
                f"{self._pct(low)} | {self._pct(med)} | "
                f"{self._pct(top)} | {position} |"
            )

        # ── 종합 등급 ──
        if grades:
            grade_scores = {"A": 4, "B": 3, "C": 2, "D": 1}
            avg_score = np.mean([grade_scores.get(g, 2) for g in grades])
            if avg_score >= 3.5:
                overall = "🏆 A등급 (업계 상위)"
            elif avg_score >= 2.5:
                overall = "✅ B등급 (업계 평균 이상)"
            elif avg_score >= 1.5:
                overall = "⚠️ C등급 (업계 평균 이하)"
            else:
                overall = "🔴 D등급 (업계 하위)"

            lines.append(f"\n### 종합 등급: {overall}")

        # ── 개선 우선순위 ──
        lines.append("\n### 개선 우선순위 (벤치마크 대비 갭이 큰 순)")
        gaps = []
        for key in stage_keys:
            if key not in bench:
                continue
            our = rates[key]
            med = bench[key]["median"]
            gap = med - our  # 양수면 우리가 뒤처짐
            if gap > 0:
                name_ko, _ = _STAGE_NAMES[key]
                gaps.append((name_ko, our, med, gap))

        gaps.sort(key=lambda x: x[3], reverse=True)
        for rank, (name, our, med, gap) in enumerate(gaps, 1):
            lines.append(f"  {rank}. **{name}**: 우리 {self._pct(our)} vs "
                         f"중간값 {self._pct(med)} (갭: {self._pct(gap)})")

        if not gaps:
            lines.append("  모든 단계에서 업종 중간값 이상! 🎉")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 Growth Marketing 교수입니다. 벤치마크 비교 결과를 보고:\n"
                "1. 이 서비스의 전반적 경쟁력 평가\n"
                "2. 업종 특성을 고려한 해석 (예: SaaS는 Activation이 핵심)\n"
                "3. 벤치마크 갭이 가장 큰 1개 단계의 개선 전략\n"
                "4. 벤치마크 상위(Top 25%)에 도달하기 위한 로드맵\n"
                "한국어로 구체적 수치와 함께 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 벤치마크 종합 분석\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  5. 개선 효과 시뮬레이션 (Forecast)
    # ═══════════════════════════════════════════

    async def _forecast_improvement(self, kwargs: dict) -> str:
        funnel, err = self._parse_funnel(kwargs)
        if err:
            return err
        rates = self._calc_rates(funnel)

        # 개선 목표 (기본값: 각 단계 10%p 개선)
        improve_pct = float(kwargs.get("improve_pct", 10)) / 100  # 0.10

        lines = ["## 퍼널 개선 효과 시뮬레이션\n"]
        lines.append(f"시나리오: 각 단계별 전환율을 **{improve_pct * 100:.0f}%p씩 개선**했을 때\n")

        # ── 단계별 개별 개선 시 최종 결제 사용자 변화 ──
        lines.append("### 단계별 개선 효과 (다른 단계는 유지)")
        lines.append("| 개선 단계 | 현재 결제 | 개선 후 결제 | 증가 | 증가율 |")
        lines.append("|----------|----------|------------|------|--------|")

        base_revenue = funnel["revenue_users"]
        stage_keys = [
            "visitor_to_signup", "signup_to_activated",
            "activated_to_retained", "retained_to_revenue",
        ]

        improvements = []
        for target_key in stage_keys:
            # 각 단계의 전환율을 improve_pct만큼 올린 시뮬레이션
            sim_rates = {k: rates[k] for k in stage_keys}
            sim_rates[target_key] = min(1.0, rates[target_key] + improve_pct)

            # 시뮬레이션: 방문자부터 다시 계산
            v = funnel["visitors"]
            s = v * sim_rates["visitor_to_signup"]
            a = s * sim_rates["signup_to_activated"]
            r = a * sim_rates["activated_to_retained"]
            rev = r * sim_rates["retained_to_revenue"]
            rev = int(rev)

            delta = rev - base_revenue
            pct_change = delta / base_revenue if base_revenue > 0 else 0
            name_ko, _ = _STAGE_NAMES[target_key]

            improvements.append((name_ko, rev, delta, pct_change))
            lines.append(
                f"| {name_ko} +{improve_pct * 100:.0f}%p | "
                f"{self._fmt_num(base_revenue)}명 | "
                f"**{self._fmt_num(rev)}명** | "
                f"+{self._fmt_num(delta)}명 | "
                f"+{self._pct(pct_change)} |"
            )

        # 가장 효과적인 개선 단계
        improvements.sort(key=lambda x: x[2], reverse=True)
        if improvements:
            best = improvements[0]
            lines.append(f"\n### 🎯 가장 효과적인 개선: **{best[0]}**")
            lines.append(f"  {improve_pct * 100:.0f}%p 개선 시 결제 사용자 "
                         f"**+{self._fmt_num(best[2])}명** 증가 (+{self._pct(best[3])})")

        # ── 전 단계 동시 개선 시 ──
        all_improved_rates = {k: min(1.0, rates[k] + improve_pct) for k in stage_keys}
        v = funnel["visitors"]
        s = v * all_improved_rates["visitor_to_signup"]
        a = s * all_improved_rates["signup_to_activated"]
        r = a * all_improved_rates["activated_to_retained"]
        rev_all = int(r * all_improved_rates["retained_to_revenue"])
        delta_all = rev_all - base_revenue
        pct_all = delta_all / base_revenue if base_revenue > 0 else 0

        lines.append(f"\n### 전 단계 동시 개선 (각 +{improve_pct * 100:.0f}%p)")
        lines.append(f"  현재 결제: {self._fmt_num(base_revenue)}명 → 개선 후: **{self._fmt_num(rev_all)}명**")
        lines.append(f"  증가: **+{self._fmt_num(delta_all)}명** (+{self._pct(pct_all)})")
        lines.append(f"\n  ⚠️ 복리 효과: 개별 개선 합산({self._fmt_num(sum(i[2] for i in improvements))}명)보다 "
                     f"동시 개선({self._fmt_num(delta_all)}명)이 더 큰 이유는 퍼널이 곱셈 구조이기 때문")
        lines.append("  (1.1 × 1.1 × 1.1 × 1.1 = 1.46 → 46% 증가, 단순 합산 40%보다 큼)")

        formatted = "\n".join(lines)
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 Growth Analytics 교수입니다. 퍼널 시뮬레이션 결과를 보고:\n"
                "1. 어떤 단계에 마케팅 자원을 집중 투입해야 ROI가 가장 높은지\n"
                "2. 각 단계 개선에 필요한 예상 비용/노력 대비 효과\n"
                "3. 실현 가능한 분기별 개선 로드맵\n"
                "4. 퍼널 복리 효과를 활용하는 전략\n"
                "한국어로 구체적 수치와 함께 분석하세요."
            ),
            user_prompt=formatted,
        )
        return f"{formatted}\n\n---\n\n### 교수급 개선 효과 종합 분석\n\n{analysis}"

    # ═══════════════════════════════════════════
    #  6. 종합 분석 (Full)
    # ═══════════════════════════════════════════

    async def _full_analysis(self, kwargs: dict) -> str:
        """모든 분석을 순차 실행하여 종합 리포트를 생성합니다."""
        funnel, err = self._parse_funnel(kwargs)
        if err:
            return err

        period = kwargs.get("period", "미지정")
        industry = kwargs.get("industry", "saas")

        sections = [
            "# AARRR 퍼널 종합 분석 리포트",
            f"**측정 기간**: {period} | **업종**: {industry.upper()}\n",
            "---",
        ]

        # 순차 실행 (데이터 파싱은 이미 검증됨)
        results = []
        for name, handler in [
            ("퍼널 전환율", self._analyze_funnel),
            ("병목 진단", self._find_bottleneck),
            ("성장 건강도", self._growth_accounting),
            ("벤치마크 비교", self._benchmark_compare),
            ("개선 효과 시뮬레이션", self._forecast_improvement),
        ]:
            try:
                result = await handler(kwargs)
                results.append((name, result))
            except Exception as e:
                results.append((name, f"분석 실패: {e}"))

        for name, result in results:
            sections.append(f"\n{result}")
            sections.append("\n---")

        return "\n".join(sections)
