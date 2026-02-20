"""
시장 규모 추정 도구 (Market Sizer) — TAM/SAM/SOM을 과학적으로 산출합니다.

Top-down(거시→미시) + Bottom-up(고객단위→적산) + Fermi(페르미 추정)
3가지 방법론을 교차 검증하여 시장 규모의 신뢰 구간을 제시합니다.

학술 근거:
  - Kotler & Keller, "Marketing Management" (16th ed., 2021) — TAM/SAM/SOM 프레임워크
  - Sequoia Capital "Writing a Business Plan" (2023) — Bottom-up SOM 산출 기준
  - a16z "Marketplace Sizing" (2024) — 양면 플랫폼 시장규모 산정
  - Fermi Estimation (Enrico Fermi, 1938) — 대략적 근사치 기법

사용 방법:
  - action="full"      : 전체 시장규모 종합 (3가지 방법론 교차검증)
  - action="top_down"  : Top-down 분석 (산업보고서 기반 축소)
  - action="bottom_up" : Bottom-up 분석 (고객수 × ARPU 적산)
  - action="fermi"     : Fermi 추정 (가정 기반 근사)
  - action="compare"   : 3가지 결과 교차 비교 + 신뢰도 평가
  - action="growth"    : 시장 성장률 예측 (CAGR + 드라이버)

필요 환경변수: 없음 (순수 Python 계산)
필요 라이브러리: 없음 (표준 라이브러리만 사용)
"""
from __future__ import annotations

import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.market_sizer")

# ─── 학술 기반 벤치마크 데이터 ─────────────────────────────

# 산업별 평균 시장 침투율 (McKinsey, 2024 / Statista)
_PENETRATION_RATES: dict[str, dict] = {
    "SaaS_B2B": {"early": 0.02, "growth": 0.08, "mature": 0.20, "avg_arpu_usd": 1200},
    "SaaS_B2C": {"early": 0.03, "growth": 0.12, "mature": 0.35, "avg_arpu_usd": 120},
    "EdTech": {"early": 0.01, "growth": 0.05, "mature": 0.15, "avg_arpu_usd": 300},
    "FinTech": {"early": 0.02, "growth": 0.10, "mature": 0.25, "avg_arpu_usd": 500},
    "HealthTech": {"early": 0.01, "growth": 0.04, "mature": 0.12, "avg_arpu_usd": 800},
    "E-Commerce": {"early": 0.05, "growth": 0.15, "mature": 0.40, "avg_arpu_usd": 200},
    "AI_Service": {"early": 0.01, "growth": 0.06, "mature": 0.18, "avg_arpu_usd": 2000},
    "LegalTech": {"early": 0.01, "growth": 0.03, "mature": 0.10, "avg_arpu_usd": 600},
    "Gaming": {"early": 0.05, "growth": 0.20, "mature": 0.45, "avg_arpu_usd": 50},
    "Marketplace": {"early": 0.02, "growth": 0.08, "mature": 0.22, "avg_arpu_usd": 150},
}

# 시장 단계별 CAGR 범위 (CB Insights, PitchBook 2024 통계)
_GROWTH_RATES: dict[str, dict] = {
    "nascent": {"min_cagr": 0.25, "max_cagr": 0.80, "desc": "태동기 (시장 형성 초기)"},
    "emerging": {"min_cagr": 0.15, "max_cagr": 0.40, "desc": "부상기 (빠른 성장)"},
    "growth": {"min_cagr": 0.08, "max_cagr": 0.20, "desc": "성장기 (안정 성장)"},
    "mature": {"min_cagr": 0.02, "max_cagr": 0.08, "desc": "성숙기 (저성장)"},
    "declining": {"min_cagr": -0.10, "max_cagr": 0.02, "desc": "쇠퇴기 (축소 가능)"},
}

# SAM/SOM 축소 비율 가이드 (Sequoia Capital, a16z)
_SHRINK_RATIOS: dict[str, dict] = {
    "conservative": {"tam_to_sam": 0.15, "sam_to_som": 0.05, "desc": "보수적 (신규 진입)"},
    "moderate": {"tam_to_sam": 0.30, "sam_to_som": 0.10, "desc": "중립적 (경쟁 존재)"},
    "aggressive": {"tam_to_sam": 0.50, "sam_to_som": 0.20, "desc": "공격적 (강한 PMF)"},
}


class MarketSizer(BaseTool):
    """시장 규모 추정 도구 — TAM/SAM/SOM Top-down + Bottom-up + Fermi 교차검증."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_analysis,
            "top_down": self._top_down,
            "bottom_up": self._bottom_up,
            "fermi": self._fermi_estimation,
            "compare": self._compare_methods,
            "growth": self._growth_projection,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return (
            f"알 수 없는 action: {action}. "
            "full, top_down, bottom_up, fermi, compare, growth 중 하나를 사용하세요."
        )

    # ── Full: 3가지 방법론 교차검증 종합 ──────────────────

    async def _full_analysis(self, p: dict) -> str:
        td = await self._top_down(p)
        bu = await self._bottom_up(p)
        fm = await self._fermi_estimation(p)
        comp = await self._compare_methods(p)
        growth = await self._growth_projection(p)

        lines = [
            "# 📊 시장 규모 종합 분석 보고서",
            "",
            "## 1. Top-Down 분석 (거시→미시 축소법)",
            td,
            "",
            "## 2. Bottom-Up 분석 (고객단위 적산법)",
            bu,
            "",
            "## 3. Fermi 추정 (가정 기반 근사법)",
            fm,
            "",
            "## 4. 교차 비교 및 신뢰도 평가",
            comp,
            "",
            "## 5. 시장 성장률 전망",
            growth,
            "",
            "---",
            "학술 참고: Kotler & Keller (2021), Sequoia Capital (2023), a16z Marketplace Sizing (2024)",
        ]
        return "\n".join(lines)

    # ── Top-Down: 전체시장→축소 ──────────────────────────

    async def _top_down(self, p: dict) -> str:
        total_market = float(p.get("total_market", 0))
        industry = p.get("industry", "SaaS_B2B")
        stance = p.get("stance", "moderate")
        currency = p.get("currency", "억원")

        if total_market <= 0:
            return self._top_down_guide(industry)

        ratios = _SHRINK_RATIOS.get(stance, _SHRINK_RATIOS["moderate"])
        tam = total_market
        sam = tam * ratios["tam_to_sam"]
        som = sam * ratios["sam_to_som"]

        pen = _PENETRATION_RATES.get(industry, _PENETRATION_RATES["SaaS_B2B"])
        stages = {
            "초기(1~2년)": pen["early"],
            "성장(3~5년)": pen["growth"],
            "성숙(5년+)": pen["mature"],
        }

        lines = [
            f"### Top-Down 시장규모 ({ratios['desc']})",
            f"| 구분 | 규모 ({currency}) | 산출 근거 |",
            "|------|---------|---------|",
            f"| TAM (전체 시장) | {tam:,.0f} | 산업보고서 기준 전체 시장 |",
            f"| SAM (접근 가능) | {sam:,.0f} | TAM × {ratios['tam_to_sam']:.0%} (지역·세그먼트 필터) |",
            f"| SOM (획득 목표) | {som:,.0f} | SAM × {ratios['sam_to_som']:.0%} (현실적 점유) |",
            "",
            f"### {industry} 산업 시장 침투율 벤치마크",
            "| 단계 | 침투율 | SOM 기준 예상 매출 |",
            "|------|--------|------------------|",
        ]
        for stage_name, rate in stages.items():
            rev = som * rate
            lines.append(f"| {stage_name} | {rate:.1%} | {rev:,.0f} {currency} |")

        lines.extend([
            "",
            f"📌 **핵심**: TAM {tam:,.0f} → SOM {som:,.0f} ({currency}). ",
            f"   {industry} 초기 침투율 {pen['early']:.1%} 적용 시 첫해 예상 {som * pen['early']:,.0f} {currency}.",
        ])
        return "\n".join(lines)

    def _top_down_guide(self, industry: str) -> str:
        pen = _PENETRATION_RATES.get(industry, _PENETRATION_RATES["SaaS_B2B"])
        lines = [
            "### Top-Down 분석을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| total_market | 전체 시장 규모 (숫자) | 50000 (= 5조원이면 50000억원) |",
            "| industry | 산업 분류 | SaaS_B2B, EdTech, AI_Service 등 |",
            "| stance | 추정 성향 | conservative, moderate, aggressive |",
            "| currency | 단위 | 억원, 만달러 등 |",
            "",
            "### 지원되는 산업 분류:",
            "| 산업 | 초기 침투율 | 성장기 침투율 | 평균 ARPU(USD) |",
            "|------|-----------|-------------|--------------|",
        ]
        for ind, data in _PENETRATION_RATES.items():
            lines.append(f"| {ind} | {data['early']:.1%} | {data['growth']:.1%} | ${data['avg_arpu_usd']:,} |")
        return "\n".join(lines)

    # ── Bottom-Up: 고객수 × ARPU 적산 ──────────────────

    async def _bottom_up(self, p: dict) -> str:
        target_customers = int(p.get("target_customers", 0))
        arpu_monthly = float(p.get("arpu_monthly", 0))
        arpu_yearly = float(p.get("arpu_yearly", arpu_monthly * 12))
        conversion_rate = float(p.get("conversion_rate", 0.03))
        total_addressable = int(p.get("total_addressable", 0))
        currency = p.get("currency", "원")

        if target_customers <= 0 and total_addressable <= 0:
            return self._bottom_up_guide()

        if target_customers <= 0 and total_addressable > 0:
            target_customers = int(total_addressable * conversion_rate)

        if arpu_monthly <= 0 and arpu_yearly <= 0:
            industry = p.get("industry", "SaaS_B2B")
            pen = _PENETRATION_RATES.get(industry, _PENETRATION_RATES["SaaS_B2B"])
            arpu_yearly = pen["avg_arpu_usd"] * 1350  # 환율 근사
            arpu_monthly = arpu_yearly / 12

        annual_rev = target_customers * arpu_yearly
        monthly_rev = target_customers * arpu_monthly

        # 3가지 시나리오 (Sequoia Capital 권장)
        scenarios = {
            "보수적 (P10)": 0.5,
            "기본 (P50)": 1.0,
            "낙관적 (P90)": 1.8,
        }

        lines = [
            "### Bottom-Up 시장규모 (고객단위 적산법)",
            "",
            f"**기본 가정:**",
            f"- 목표 유료 고객 수: {target_customers:,}명",
            f"- ARPU (월): {arpu_monthly:,.0f}{currency}",
            f"- ARPU (연): {arpu_yearly:,.0f}{currency}",
        ]
        if total_addressable > 0:
            lines.append(f"- 전체 도달 가능 고객: {total_addressable:,}명 × 전환율 {conversion_rate:.1%}")

        lines.extend([
            "",
            "| 시나리오 | 고객 수 | 월 매출 | 연 매출 |",
            "|---------|--------|--------|--------|",
        ])
        for name, mult in scenarios.items():
            cust = int(target_customers * mult)
            m_rev = cust * arpu_monthly
            y_rev = cust * arpu_yearly
            lines.append(f"| {name} | {cust:,}명 | {m_rev:,.0f}{currency} | {y_rev:,.0f}{currency} |")

        # SOM 역산 (Bottom-up이 Top-down보다 현실적)
        som_estimate = annual_rev
        lines.extend([
            "",
            f"📌 **Bottom-up SOM 추정**: 연 {som_estimate:,.0f}{currency}",
            f"   (이 방식은 VC가 가장 신뢰하는 SOM 산출법입니다 — Sequoia Capital, 2023)",
        ])
        return "\n".join(lines)

    def _bottom_up_guide(self) -> str:
        return "\n".join([
            "### Bottom-Up 분석을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| target_customers | 목표 유료 고객 수 | 5000 |",
            "| arpu_monthly | 월 객단가 | 29900 (원) |",
            "| total_addressable | 전체 도달 가능 고객 수 | 500000 |",
            "| conversion_rate | 유료 전환율 | 0.03 (3%) |",
            "| currency | 통화 단위 | 원, USD 등 |",
            "",
            "💡 **팁**: target_customers 대신 total_addressable + conversion_rate를 넣으면 자동 계산합니다.",
        ])

    # ── Fermi: 가정 기반 빠른 근사 ─────────────────────────

    # 한국 시장 기본값 — Fermi 추정 시 population=0 또는 market="KR"이면 자동 적용
    # 통계청 (2025) 기준 인구 + 산업별 합리적 가정값
    _KR_DEFAULTS: dict[str, dict] = {
        "population": 52_000_000,  # 대한민국 인구 (통계청, 2025)
        "industry_defaults": {
            "SaaS_B2B": {"target_ratio": 0.08, "awareness": 0.12, "trial": 0.06, "conversion": 0.04},
            "SaaS_B2C": {"target_ratio": 0.25, "awareness": 0.15, "trial": 0.08, "conversion": 0.03},
            "EdTech": {"target_ratio": 0.20, "awareness": 0.20, "trial": 0.10, "conversion": 0.04},
            "FinTech": {"target_ratio": 0.35, "awareness": 0.25, "trial": 0.12, "conversion": 0.05},
            "HealthTech": {"target_ratio": 0.15, "awareness": 0.08, "trial": 0.04, "conversion": 0.03},
            "E-Commerce": {"target_ratio": 0.60, "awareness": 0.30, "trial": 0.15, "conversion": 0.06},
            "AI_Service": {"target_ratio": 0.10, "awareness": 0.10, "trial": 0.05, "conversion": 0.03},
            "LegalTech": {"target_ratio": 0.05, "awareness": 0.08, "trial": 0.04, "conversion": 0.03},
            "Gaming": {"target_ratio": 0.40, "awareness": 0.35, "trial": 0.20, "conversion": 0.05},
            "Marketplace": {"target_ratio": 0.30, "awareness": 0.20, "trial": 0.10, "conversion": 0.04},
        },
    }

    async def _fermi_estimation(self, p: dict) -> str:
        # Fermi 추정: 큰 수를 작은 가정의 곱으로 분해
        population = int(p.get("population", 0))
        market = p.get("market", "")
        industry = p.get("industry", "SaaS_B2B")
        target_ratio = float(p.get("target_ratio", 0))
        awareness_rate = float(p.get("awareness_rate", 0))
        trial_rate = float(p.get("trial_rate", 0))
        conversion_rate = float(p.get("conversion_rate", 0))
        arpu_yearly = float(p.get("arpu_yearly", 0))
        currency = p.get("currency", "원")

        # 한국 시장 자동 기본값: market="KR" 또는 population=0이면 적용
        use_kr_defaults = (market.upper() == "KR") or (population <= 0)

        if use_kr_defaults:
            kr = self._KR_DEFAULTS
            kr_ind = kr["industry_defaults"].get(industry, kr["industry_defaults"]["SaaS_B2B"])
            if population <= 0:
                population = kr["population"]
            if target_ratio <= 0:
                target_ratio = kr_ind["target_ratio"]
            if awareness_rate <= 0:
                awareness_rate = kr_ind["awareness"]
            if trial_rate <= 0:
                trial_rate = kr_ind["trial"]
            if conversion_rate <= 0:
                conversion_rate = kr_ind["conversion"]

        if population <= 0:
            return self._fermi_guide()

        # 명시적 입력이 없었던 비율에 안전 기본값 적용
        if target_ratio <= 0:
            target_ratio = 0.10
        if awareness_rate <= 0:
            awareness_rate = 0.10
        if trial_rate <= 0:
            trial_rate = 0.05
        if conversion_rate <= 0:
            conversion_rate = 0.03

        target_pop = population * target_ratio
        aware = target_pop * awareness_rate
        trialed = aware * trial_rate
        paying = trialed * conversion_rate

        if arpu_yearly <= 0:
            pen = _PENETRATION_RATES.get(industry, _PENETRATION_RATES["SaaS_B2B"])
            arpu_yearly = pen["avg_arpu_usd"] * 1350

        total_rev = paying * arpu_yearly

        # 각 단계별 퍼널
        kr_notice = f"\n> 한국 시장({industry}) 기본값 자동 적용됨 (통계청 2025 + 산업별 벤치마크)\n" if use_kr_defaults else ""
        lines = [
            "### Fermi 추정 (Enrico Fermi 스타일 분해 추정법)",
            kr_notice,
            "**가정 체인 (각 단계의 곱):**",
            "",
            "| 단계 | 비율/수치 | 누적 인원 | 설명 |",
            "|------|---------|----------|------|",
            f"| 전체 인구/모수 | {population:,} | {population:,} | 출발점 |",
            f"| 대상 비율 | {target_ratio:.1%} | {target_pop:,.0f} | 우리 서비스 대상자 |",
            f"| 인지율 | {awareness_rate:.1%} | {aware:,.0f} | 서비스 존재를 아는 사람 |",
            f"| 시도율 | {trial_rate:.1%} | {trialed:,.0f} | 한번이라도 써보는 사람 |",
            f"| 유료 전환율 | {conversion_rate:.1%} | {paying:,.0f} | 돈을 내는 사람 |",
            "",
            f"**Fermi SOM 추정: {paying:,.0f}명 × {arpu_yearly:,.0f}{currency}/년 = {total_rev:,.0f}{currency}/년**",
            "",
            "### 민감도 분석 (핵심 가정 ±50%)",
            "| 변수 | -50% | 기본 | +50% |",
            "|------|------|------|------|",
        ]

        # 민감도 분석
        for var_name, var_val, var_key in [
            ("인지율", awareness_rate, "awareness"),
            ("시도율", trial_rate, "trial"),
            ("전환율", conversion_rate, "conversion"),
            ("ARPU", arpu_yearly, "arpu"),
        ]:
            low = total_rev * 0.5
            high = total_rev * 1.5
            if var_key == "awareness":
                low = (target_pop * (awareness_rate * 0.5) * trial_rate * conversion_rate * arpu_yearly)
                high = (target_pop * min(awareness_rate * 1.5, 1.0) * trial_rate * conversion_rate * arpu_yearly)
            elif var_key == "trial":
                low = (aware * (trial_rate * 0.5) * conversion_rate * arpu_yearly)
                high = (aware * min(trial_rate * 1.5, 1.0) * conversion_rate * arpu_yearly)
            elif var_key == "conversion":
                low = (trialed * (conversion_rate * 0.5) * arpu_yearly)
                high = (trialed * min(conversion_rate * 1.5, 1.0) * arpu_yearly)
            elif var_key == "arpu":
                low = paying * arpu_yearly * 0.5
                high = paying * arpu_yearly * 1.5

            lines.append(f"| {var_name} | {low:,.0f}{currency} | {total_rev:,.0f}{currency} | {high:,.0f}{currency} |")

        lines.extend([
            "",
            "📌 **Fermi 추정은 '대략 맞는 답'을 빠르게 구하는 기법**입니다.",
            "   정밀한 수치보다 '자릿수(order of magnitude)'가 맞는지가 핵심입니다.",
        ])
        return "\n".join(lines)

    def _fermi_guide(self) -> str:
        return "\n".join([
            "### Fermi 추정을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| population | 전체 모수 (인구, 기업수 등) | 52000000 (한국 인구) |",
            "| market | 시장 (KR이면 한국 기본값 자동) | KR |",
            "| industry | 산업 분류 | AI_Service, FinTech 등 |",
            "| target_ratio | 대상 비율 | 0.10 (10%) |",
            "| awareness_rate | 인지율 (서비스를 아는 비율) | 0.10 (10%) |",
            "| trial_rate | 시도율 (써보는 비율) | 0.05 (5%) |",
            "| conversion_rate | 유료 전환율 | 0.03 (3%) |",
            "| arpu_yearly | 연간 객단가 | 360000 (원) |",
            "",
            "💡 **간편 모드**: `market=\"KR\"` + `industry=\"AI_Service\"`만 입력하면",
            "   한국 인구(5,200만) + 산업별 벤치마크가 자동 적용됩니다.",
            "",
            "💡 **Fermi 추정의 핵심**: 정확한 숫자보다 '자릿수'를 맞추는 것이 목표입니다.",
            "   Enrico Fermi는 이 방법으로 원자폭탄 폭발력을 ±50% 이내로 추정했습니다.",
        ])

    # ── Compare: 3가지 결과 교차 비교 ─────────────────────

    async def _compare_methods(self, p: dict) -> str:
        td_som = float(p.get("td_som", 0))
        bu_som = float(p.get("bu_som", 0))
        fermi_som = float(p.get("fermi_som", 0))
        currency = p.get("currency", "억원")

        values = [v for v in [td_som, bu_som, fermi_som] if v > 0]
        if len(values) < 2:
            return self._compare_guide()

        avg = sum(values) / len(values)
        # 변동계수(CV) = 표준편차 / 평균 — 일치도 측정
        variance = sum((v - avg) ** 2 for v in values) / len(values)
        std_dev = math.sqrt(variance)
        cv = std_dev / avg if avg > 0 else 0

        # 신뢰도 등급 (CV 기준, 통계학 표준)
        if cv < 0.15:
            grade = "A (매우 높음)"
            comment = "3가지 방법론 결과가 15% 이내로 수렴합니다. 높은 신뢰도입니다."
        elif cv < 0.30:
            grade = "B (양호)"
            comment = "적절한 범위 내 수렴. 가정 재검토로 정밀도를 높일 수 있습니다."
        elif cv < 0.50:
            grade = "C (주의 필요)"
            comment = "방법론 간 차이가 큽니다. 가정의 출처와 근거를 재검토하세요."
        else:
            grade = "D (재분석 필요)"
            comment = "방법론 간 차이가 매우 큽니다. 기초 데이터부터 재검증 필요합니다."

        min_val = min(values)
        max_val = max(values)

        lines = [
            "### 3가지 방법론 교차 비교",
            "",
            "| 방법론 | SOM 추정치 | 평균 대비 |",
            "|--------|----------|---------|",
        ]
        if td_som > 0:
            lines.append(f"| Top-Down | {td_som:,.0f} {currency} | {(td_som/avg - 1):+.1%} |")
        if bu_som > 0:
            lines.append(f"| Bottom-Up | {bu_som:,.0f} {currency} | {(bu_som/avg - 1):+.1%} |")
        if fermi_som > 0:
            lines.append(f"| Fermi 추정 | {fermi_som:,.0f} {currency} | {(fermi_som/avg - 1):+.1%} |")

        lines.extend([
            "",
            f"**통계적 수렴도:**",
            f"- 평균(Mean): {avg:,.0f} {currency}",
            f"- 표준편차(SD): {std_dev:,.0f} {currency}",
            f"- 변동계수(CV): {cv:.1%}",
            f"- 범위: {min_val:,.0f} ~ {max_val:,.0f} {currency}",
            f"- **신뢰도 등급: {grade}**",
            "",
            f"📌 {comment}",
            "",
            "### 추천 SOM 범위",
            f"- 보수적: {min_val:,.0f} {currency}",
            f"- 기본: {avg:,.0f} {currency}",
            f"- 낙관적: {max_val:,.0f} {currency}",
        ])
        return "\n".join(lines)

    def _compare_guide(self) -> str:
        return "\n".join([
            "### 교차 비교를 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| td_som | Top-Down SOM 결과 | 500 (억원) |",
            "| bu_som | Bottom-Up SOM 결과 | 400 (억원) |",
            "| fermi_som | Fermi 추정 SOM 결과 | 450 (억원) |",
            "",
            "💡 **최소 2개** 이상의 결과가 있어야 교차 비교가 가능합니다.",
            "   CV(변동계수) < 15%면 높은 신뢰도, > 50%면 재분석이 필요합니다.",
        ])

    # ── Growth: CAGR + 성장 드라이버 ──────────────────────

    async def _growth_projection(self, p: dict) -> str:
        current_size = float(p.get("current_size", 0))
        stage = p.get("stage", "growth")
        years = int(p.get("years", 5))
        currency = p.get("currency", "억원")

        if current_size <= 0:
            return self._growth_guide()

        growth = _GROWTH_RATES.get(stage, _GROWTH_RATES["growth"])
        min_cagr = growth["min_cagr"]
        max_cagr = growth["max_cagr"]
        mid_cagr = (min_cagr + max_cagr) / 2

        lines = [
            f"### 시장 성장률 전망 — {growth['desc']}",
            "",
            f"현재 시장 규모: {current_size:,.0f} {currency}",
            f"CAGR 범위: {min_cagr:.0%} ~ {max_cagr:.0%} (중간: {mid_cagr:.0%})",
            "",
            f"### {years}년 시장 규모 전망",
            "| 연도 | 보수적 ({:.0%}) | 기본 ({:.0%}) | 낙관적 ({:.0%}) |".format(min_cagr, mid_cagr, max_cagr),
            "|------|------------|---------|------------|",
        ]

        for yr in range(1, years + 1):
            low = current_size * ((1 + min_cagr) ** yr)
            mid = current_size * ((1 + mid_cagr) ** yr)
            high = current_size * ((1 + max_cagr) ** yr)
            lines.append(f"| {yr}년 후 | {low:,.0f} | {mid:,.0f} | {high:,.0f} |")

        # 72의 법칙 (Rule of 72) — 시장 2배 시점
        double_yr_low = 72 / (min_cagr * 100) if min_cagr > 0 else float('inf')
        double_yr_mid = 72 / (mid_cagr * 100) if mid_cagr > 0 else float('inf')
        double_yr_high = 72 / (max_cagr * 100) if max_cagr > 0 else float('inf')

        lines.extend([
            "",
            "### 72의 법칙 (시장 2배 달성 예상 시점)",
            f"- 보수적: {double_yr_low:.1f}년",
            f"- 기본: {double_yr_mid:.1f}년",
            f"- 낙관적: {double_yr_high:.1f}년",
            "",
            "### 시장 단계별 CAGR 벤치마크 (CB Insights, PitchBook 2024)",
            "| 단계 | CAGR 범위 | 설명 |",
            "|------|----------|------|",
        ])
        for stg, data in _GROWTH_RATES.items():
            marker = " ← 현재" if stg == stage else ""
            lines.append(f"| {data['desc']} | {data['min_cagr']:.0%}~{data['max_cagr']:.0%} | {stg}{marker} |")

        return "\n".join(lines)

    def _growth_guide(self) -> str:
        return "\n".join([
            "### 성장률 전망을 위해 필요한 입력값:",
            "",
            "| 파라미터 | 설명 | 예시 |",
            "|---------|------|------|",
            "| current_size | 현재 시장 규모 | 1000 (억원) |",
            "| stage | 시장 단계 | nascent, emerging, growth, mature, declining |",
            "| years | 전망 기간 | 5 (년) |",
            "",
            "💡 **72의 법칙**: CAGR이 X%일 때, 시장이 2배가 되는 시간 = 72/X 년.",
        ])
