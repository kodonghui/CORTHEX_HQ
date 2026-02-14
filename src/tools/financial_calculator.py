"""재무 계산기 도구 — DCF, NPV, IRR, 대출, ROI, 손익분기점 계산."""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.financial_calculator")


def _get_npf():
    """numpy-financial 지연 임포트."""
    try:
        import numpy_financial as npf
        return npf
    except ImportError:
        return None


def _get_numpy():
    try:
        import numpy as np
        return np
    except ImportError:
        return None


class FinancialCalculatorTool(BaseTool):
    """재무 분석 계산 도구 — DCF, NPV, IRR, 대출 시뮬레이션, ROI, 손익분기점."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "dcf")
        if action == "dcf":
            return await self._dcf(kwargs)
        elif action == "npv":
            return await self._npv(kwargs)
        elif action == "irr":
            return await self._irr(kwargs)
        elif action == "loan":
            return await self._loan(kwargs)
        elif action == "roi":
            return await self._roi(kwargs)
        elif action == "breakeven":
            return await self._breakeven(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: dcf(기업가치), npv(순현재가치), irr(내부수익률), "
                "loan(대출 시뮬레이션), roi(투자수익률), breakeven(손익분기점)"
            )

    async def _dcf(self, kwargs: dict) -> str:
        """DCF 기업가치 평가 (할인현금흐름)."""
        npf = _get_npf()
        np = _get_numpy()
        if npf is None or np is None:
            return "numpy-financial 라이브러리가 필요합니다. pip install numpy-financial numpy"

        cashflows = kwargs.get("cashflows", [])
        discount_rate = float(kwargs.get("discount_rate", 0.1))
        terminal_growth = float(kwargs.get("terminal_growth", 0.02))

        if not cashflows:
            return (
                "DCF 계산에 필요한 인자:\n"
                "- cashflows: 예상 미래 현금흐름 리스트 (예: [100, 110, 120, 130, 140])\n"
                "- discount_rate: 할인율 (기본: 0.1 = 10%)\n"
                "- terminal_growth: 영구성장률 (기본: 0.02 = 2%)"
            )

        if isinstance(cashflows, str):
            cashflows = [float(v.strip()) for v in cashflows.split(",")]

        # 각 연도 현재가치 계산
        pv_cashflows = []
        lines = ["| 연도 | 현금흐름 | 할인계수 | 현재가치 |", "|------|---------|---------|---------|"]
        for i, cf in enumerate(cashflows, 1):
            discount_factor = 1 / (1 + discount_rate) ** i
            pv = cf * discount_factor
            pv_cashflows.append(pv)
            lines.append(f"| {i}년 | {cf:,.0f} | {discount_factor:.4f} | {pv:,.0f} |")

        # 터미널 가치 (영구 성장 모델)
        last_cf = cashflows[-1]
        terminal_value = last_cf * (1 + terminal_growth) / (discount_rate - terminal_growth)
        terminal_pv = terminal_value / (1 + discount_rate) ** len(cashflows)

        total_pv = sum(pv_cashflows)
        enterprise_value = total_pv + terminal_pv

        return (
            f"## DCF 기업가치 평가\n\n"
            f"### 입력 조건\n"
            f"- 할인율: {discount_rate * 100:.1f}%\n"
            f"- 영구성장률: {terminal_growth * 100:.1f}%\n"
            f"- 예측 기간: {len(cashflows)}년\n\n"
            f"### 연도별 현금흐름 현재가치\n\n"
            + "\n".join(lines) + "\n\n"
            f"### 결과\n\n"
            f"| 항목 | 금액 |\n"
            f"|------|------|\n"
            f"| 예측기간 현재가치 합계 | {total_pv:,.0f} |\n"
            f"| 터미널 가치 (Terminal Value) | {terminal_value:,.0f} |\n"
            f"| 터미널 현재가치 | {terminal_pv:,.0f} |\n"
            f"| **기업가치 (Enterprise Value)** | **{enterprise_value:,.0f}** |\n"
        )

    async def _npv(self, kwargs: dict) -> str:
        """순현재가치 (NPV) 계산."""
        npf = _get_npf()
        if npf is None:
            return "numpy-financial 라이브러리가 필요합니다. pip install numpy-financial"

        rate = float(kwargs.get("rate", 0.1))
        cashflows = kwargs.get("cashflows", [])

        if not cashflows:
            return (
                "NPV 계산에 필요한 인자:\n"
                "- rate: 할인율 (예: 0.1 = 10%)\n"
                "- cashflows: 현금흐름 리스트 (첫 값은 투자금, 음수. 예: [-1000, 300, 400, 500])"
            )

        if isinstance(cashflows, str):
            cashflows = [float(v.strip()) for v in cashflows.split(",")]

        result = npf.npv(rate, cashflows)
        investment = abs(cashflows[0]) if cashflows[0] < 0 else 0

        lines = ["| 시점 | 현금흐름 |", "|------|---------|"]
        for i, cf in enumerate(cashflows):
            label = "초기 투자" if i == 0 else f"{i}년차"
            lines.append(f"| {label} | {cf:,.0f} |")

        decision = "투자 가치 있음 (NPV > 0)" if result > 0 else "투자 부적합 (NPV < 0)"

        return (
            f"## NPV (순현재가치) 계산 결과\n\n"
            f"- 할인율: {rate * 100:.1f}%\n"
            f"- 초기 투자금: {investment:,.0f}\n\n"
            + "\n".join(lines) + "\n\n"
            f"### 결과\n"
            f"- **NPV = {result:,.0f}**\n"
            f"- 판단: {decision}"
        )

    async def _irr(self, kwargs: dict) -> str:
        """내부수익률 (IRR) 계산."""
        npf = _get_npf()
        if npf is None:
            return "numpy-financial 라이브러리가 필요합니다. pip install numpy-financial"

        cashflows = kwargs.get("cashflows", [])
        if not cashflows:
            return (
                "IRR 계산에 필요한 인자:\n"
                "- cashflows: 현금흐름 리스트 (첫 값은 투자금, 음수. 예: [-1000, 300, 400, 500, 200])"
            )

        if isinstance(cashflows, str):
            cashflows = [float(v.strip()) for v in cashflows.split(",")]

        try:
            result = npf.irr(cashflows)
        except Exception as e:
            return f"IRR 계산 실패: {e}"

        if result is None or str(result) == "nan":
            return "IRR을 계산할 수 없습니다. 현금흐름 데이터를 확인해주세요."

        hurdle_rate = float(kwargs.get("hurdle_rate", 0.1))
        decision = "투자 가치 있음 (IRR > 기준수익률)" if result > hurdle_rate else "투자 부적합 (IRR < 기준수익률)"

        return (
            f"## IRR (내부수익률) 계산 결과\n\n"
            f"### 현금흐름\n"
            + "\n".join(f"- {'초기 투자' if i == 0 else f'{i}년차'}: {cf:,.0f}" for i, cf in enumerate(cashflows))
            + f"\n\n### 결과\n"
            f"- **IRR = {result * 100:.2f}%**\n"
            f"- 기준수익률: {hurdle_rate * 100:.1f}%\n"
            f"- 판단: {decision}"
        )

    async def _loan(self, kwargs: dict) -> str:
        """대출 상환 시뮬레이션."""
        np = _get_numpy()
        npf = _get_npf()
        if np is None or npf is None:
            return "numpy-financial 라이브러리가 필요합니다. pip install numpy-financial numpy"

        principal = float(kwargs.get("principal", 0))
        annual_rate = float(kwargs.get("annual_rate", 0))
        years = int(kwargs.get("years", 0))
        method = kwargs.get("method", "equal_payment")

        if not principal or not annual_rate or not years:
            return (
                "대출 시뮬레이션에 필요한 인자:\n"
                "- principal: 대출 원금 (예: 100000000)\n"
                "- annual_rate: 연 이자율 (예: 0.05 = 5%)\n"
                "- years: 대출 기간 (년)\n"
                "- method: 상환 방식 (equal_payment=원리금균등, equal_principal=원금균등)"
            )

        monthly_rate = annual_rate / 12
        total_months = years * 12

        lines = ["| 회차 | 월 납입금 | 원금 | 이자 | 잔액 |", "|------|---------|------|------|------|"]
        total_interest = 0
        remaining = principal

        if method == "equal_payment":
            monthly_payment = npf.pmt(monthly_rate, total_months, -principal)
            for m in range(1, total_months + 1):
                interest = remaining * monthly_rate
                principal_part = monthly_payment - interest
                remaining -= principal_part
                total_interest += interest
                if m <= 12 or m > total_months - 3 or m % 12 == 0:
                    lines.append(
                        f"| {m} | {monthly_payment:,.0f} | {principal_part:,.0f} | "
                        f"{interest:,.0f} | {max(0, remaining):,.0f} |"
                    )
                elif m == 13:
                    lines.append("| ... | ... | ... | ... | ... |")
        else:
            monthly_principal = principal / total_months
            for m in range(1, total_months + 1):
                interest = remaining * monthly_rate
                payment = monthly_principal + interest
                remaining -= monthly_principal
                total_interest += interest
                if m <= 12 or m > total_months - 3 or m % 12 == 0:
                    lines.append(
                        f"| {m} | {payment:,.0f} | {monthly_principal:,.0f} | "
                        f"{interest:,.0f} | {max(0, remaining):,.0f} |"
                    )
                elif m == 13:
                    lines.append("| ... | ... | ... | ... | ... |")

        total_payment = principal + total_interest
        method_name = "원리금균등" if method == "equal_payment" else "원금균등"

        return (
            f"## 대출 상환 시뮬레이션\n\n"
            f"| 항목 | 값 |\n|------|----|\n"
            f"| 대출 원금 | {principal:,.0f} |\n"
            f"| 연 이자율 | {annual_rate * 100:.2f}% |\n"
            f"| 대출 기간 | {years}년 ({total_months}개월) |\n"
            f"| 상환 방식 | {method_name} |\n"
            f"| 총 이자 | {total_interest:,.0f} |\n"
            f"| 총 상환액 | {total_payment:,.0f} |\n\n"
            f"### 상환 스케줄\n\n"
            + "\n".join(lines)
        )

    async def _roi(self, kwargs: dict) -> str:
        """투자 수익률 계산 (단순 ROI + CAGR)."""
        initial = float(kwargs.get("initial", 0))
        final = float(kwargs.get("final", 0))
        years = float(kwargs.get("years", 1))

        if not initial:
            return (
                "ROI 계산에 필요한 인자:\n"
                "- initial: 초기 투자금\n"
                "- final: 최종 가치\n"
                "- years: 투자 기간 (년)"
            )

        simple_roi = ((final - initial) / initial) * 100
        profit = final - initial

        # CAGR (연평균성장률)
        if years > 0 and initial > 0 and final > 0:
            cagr = ((final / initial) ** (1 / years) - 1) * 100
        else:
            cagr = 0

        return (
            f"## 투자 수익률 분석\n\n"
            f"| 항목 | 값 |\n|------|----|\n"
            f"| 초기 투자 | {initial:,.0f} |\n"
            f"| 최종 가치 | {final:,.0f} |\n"
            f"| 투자 기간 | {years:.1f}년 |\n"
            f"| 순수익 | {profit:,.0f} |\n"
            f"| **단순 ROI** | **{simple_roi:.2f}%** |\n"
            f"| **CAGR (연평균성장률)** | **{cagr:.2f}%** |\n"
        )

    async def _breakeven(self, kwargs: dict) -> str:
        """손익분기점 분석."""
        fixed_cost = float(kwargs.get("fixed_cost", 0))
        variable_cost = float(kwargs.get("variable_cost_per_unit", 0))
        price = float(kwargs.get("price_per_unit", 0))

        if not fixed_cost or not price:
            return (
                "손익분기점 계산에 필요한 인자:\n"
                "- fixed_cost: 고정비 (예: 월 임대료, 인건비 등)\n"
                "- variable_cost_per_unit: 단위당 변동비\n"
                "- price_per_unit: 단위당 판매가격"
            )

        if price <= variable_cost:
            return (
                f"단위당 판매가({price:,.0f})가 변동비({variable_cost:,.0f}) 이하입니다.\n"
                f"이 조건에서는 손익분기점에 도달할 수 없습니다."
            )

        contribution_margin = price - variable_cost
        bep_units = fixed_cost / contribution_margin
        bep_revenue = bep_units * price

        return (
            f"## 손익분기점 분석\n\n"
            f"| 항목 | 값 |\n|------|----|\n"
            f"| 고정비 | {fixed_cost:,.0f} |\n"
            f"| 단위당 변동비 | {variable_cost:,.0f} |\n"
            f"| 단위당 판매가 | {price:,.0f} |\n"
            f"| 단위당 공헌이익 | {contribution_margin:,.0f} |\n"
            f"| **손익분기 수량** | **{bep_units:,.0f}개** |\n"
            f"| **손익분기 매출** | **{bep_revenue:,.0f}** |\n"
        )
