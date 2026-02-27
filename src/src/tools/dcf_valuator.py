"""
DCF 가치평가 도구 (DCF Valuator) — 기업의 적정 주가를 계산합니다.

현금흐름할인법(DCF)을 포함한 다중 밸류에이션 모델로
"이 주식이 비싼지 싼지"를 정량적으로 판단합니다.

학술 근거:
  - 기업재무론 (Aswath Damodaran, "Investment Valuation")
  - Graham & Dodd의 가치투자 ("Security Analysis")
  - 배당할인모형 (Gordon Growth Model, 1962)

사용 방법:
  - action="full"         : 전체 가치평가 종합 (DCF + 상대 + 그레이엄)
  - action="dcf"          : DCF 모델 (EPS 기반 현금흐름 할인)
  - action="relative"     : 상대 가치평가 (PER/PBR 역사 비교)
  - action="graham"       : 그레이엄 넘버 (보수적 내재가치)
  - action="ddm"          : 배당할인모형 (배당주 전용)
  - action="sensitivity"  : 민감도 분석 (성장률/할인율 매트릭스)

필요 환경변수: 없음 (pykrx 무료)
필요 라이브러리: pykrx, pandas, numpy
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.dcf_valuator")


def _import_pykrx():
    try:
        from pykrx import stock
        return stock
    except ImportError:
        return None


class DcfValuatorTool(BaseTool):
    """기업 적정 주가 계산 도구 — DCF + 상대가치 + 그레이엄 + 배당할인모형."""

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        if query and not kwargs.get("name") and not kwargs.get("ticker"):
            kwargs["name"] = query

        action = kwargs.get("action", "full")
        actions = {
            "full": self._full_valuation,
            "dcf": self._dcf_model,
            "relative": self._relative_valuation,
            "graham": self._graham_number,
            "ddm": self._dividend_discount,
            "sensitivity": self._sensitivity_analysis,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return (
            f"알 수 없는 action: {action}. "
            "full, dcf, relative, graham, ddm, sensitivity 중 하나를 사용하세요."
        )

    # ── 공통: 종목 데이터 로드 ──────────────────

    async def _load_fundamentals(self, kwargs: dict) -> tuple:
        """종목의 펀더멘털 + 가격 데이터를 로드합니다."""
        stock = _import_pykrx()
        if stock is None:
            return None, None, None, "pykrx 라이브러리가 필요합니다.\npip install pykrx"

        ticker = kwargs.get("ticker", "")
        name = kwargs.get("name", "")
        if not ticker and not name:
            return None, None, None, "종목코드(ticker) 또는 종목명(name)을 입력해주세요."

        if name and not ticker:
            ticker = await self._resolve_ticker(stock, name)
            if not ticker:
                return None, None, None, f"'{name}' 종목을 찾을 수 없습니다."

        stock_name = await self._get_stock_name(stock, ticker)

        # 최근 3년 펀더멘털 (PER, PBR, EPS, BPS, DIV, DPS)
        end = datetime.now().strftime("%Y%m%d")
        start_3y = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y%m%d")
        start_5y = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y%m%d")

        try:
            fund_df = await asyncio.to_thread(
                stock.get_market_fundamental, start_3y, end, ticker
            )
            ohlcv_df = await asyncio.to_thread(
                stock.get_market_ohlcv_by_date, start_5y, end, ticker
            )
        except Exception as e:
            return None, None, None, f"데이터 조회 실패: {e}"

        if fund_df.empty or len(fund_df) < 30:
            return None, None, None, f"'{stock_name}' 펀더멘털 데이터가 부족합니다."

        return ticker, stock_name, {"fund": fund_df, "ohlcv": ohlcv_df}, None

    async def _resolve_ticker(self, stock, name: str) -> str | None:
        try:
            today = datetime.now().strftime("%Y%m%d")
            tickers = await asyncio.to_thread(stock.get_market_ticker_list, today, market="ALL")
            for t in tickers:
                t_name = await asyncio.to_thread(stock.get_market_ticker_name, t)
                if t_name == name:
                    return t
        except Exception:
            pass
        return None

    async def _get_stock_name(self, stock, ticker: str) -> str:
        try:
            return await asyncio.to_thread(stock.get_market_ticker_name, ticker)
        except Exception:
            return ticker

    @staticmethod
    def _fmt(val, decimals=0) -> str:
        if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
            return "N/A"
        if abs(val) >= 1_000_000:
            return f"{val / 10000:,.0f}만"
        if abs(val) >= 1000:
            return f"{val:,.0f}"
        return f"{val:.{decimals}f}"

    # ── 1. 전체 가치평가 종합 ──────────────────

    async def _full_valuation(self, kwargs: dict) -> str:
        ticker, name, data, err = await self._load_fundamentals(kwargs)
        if err:
            return err

        fund_df = data["fund"]
        ohlcv_df = data["ohlcv"]
        current_price = int(ohlcv_df["종가"].iloc[-1])

        results = []
        results.append(f"{'='*50}")
        results.append(f"📊 {name} ({ticker}) 종합 가치평가")
        results.append(f"{'='*50}")
        results.append(f"현재가: {current_price:,}원\n")

        # DCF
        dcf_val = self._calc_dcf(fund_df, current_price)
        results.append(f"▸ DCF 적정가: {self._fmt(dcf_val)}원 ({self._updown(dcf_val, current_price)})")

        # Graham
        graham_val = self._calc_graham(fund_df)
        results.append(f"▸ 그레이엄 넘버: {self._fmt(graham_val)}원 ({self._updown(graham_val, current_price)})")

        # DDM
        ddm_val = self._calc_ddm(fund_df, current_price)
        if ddm_val:
            results.append(f"▸ 배당할인 적정가: {self._fmt(ddm_val)}원 ({self._updown(ddm_val, current_price)})")
        else:
            results.append("▸ 배당할인: 해당 없음 (배당 미지급)")

        # Relative
        rel = self._calc_relative(fund_df, current_price)
        results.append(f"\n▸ 현재 PER: {self._fmt(rel['per_now'], 1)}배 (3년 평균: {self._fmt(rel['per_avg'], 1)}배)")
        results.append(f"▸ 현재 PBR: {self._fmt(rel['pbr_now'], 2)}배 (3년 평균: {self._fmt(rel['pbr_avg'], 2)}배)")
        results.append(f"▸ PER 기준 적정가: {self._fmt(rel['per_fair'])}원")
        results.append(f"▸ PBR 기준 적정가: {self._fmt(rel['pbr_fair'])}원")

        # 종합 판단
        valuations = [v for v in [dcf_val, graham_val, ddm_val, rel["per_fair"], rel["pbr_fair"]] if v and v > 0]
        if valuations:
            avg_fair = np.mean(valuations)
            margin = ((avg_fair - current_price) / current_price) * 100
            results.append(f"\n{'─'*50}")
            results.append(f"▸ 모델 평균 적정가: {self._fmt(avg_fair)}원")
            results.append(f"▸ 괴리율: {margin:+.1f}% ({'저평가' if margin > 0 else '고평가'})")

        raw_text = "\n".join(results)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 Aswath Damodaran 교수 수준의 기업가치평가 전문가입니다. "
                "DCF, 상대가치, 그레이엄 넘버, 배당할인 모델 결과를 종합하여 "
                "이 주식이 현재 매수 적격인지 판단하세요. "
                "구체적인 숫자를 근거로 들고, 리스크 요인도 언급하세요. 한국어로 답변하세요."
            ),
            user_prompt=raw_text,
            caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
        )
        return f"{raw_text}\n\n{'='*50}\n🎓 교수급 종합 분석\n{'='*50}\n{analysis}"

    # ── 2. DCF 모델 ──────────────────────────

    async def _dcf_model(self, kwargs: dict) -> str:
        ticker, name, data, err = await self._load_fundamentals(kwargs)
        if err:
            return err

        fund_df = data["fund"]
        ohlcv_df = data["ohlcv"]
        current_price = int(ohlcv_df["종가"].iloc[-1])
        dcf_val = self._calc_dcf(fund_df, current_price)

        # EPS 성장 추이
        eps_data = fund_df["EPS"].dropna()
        yearly_eps = eps_data.resample("YE").last().dropna()

        results = [f"📊 {name} DCF 가치평가"]
        results.append(f"현재가: {current_price:,}원")
        results.append(f"DCF 적정가: {self._fmt(dcf_val)}원 ({self._updown(dcf_val, current_price)})")
        results.append(f"\n연도별 EPS 추이:")
        for date, eps in yearly_eps.items():
            results.append(f"  {date.year}: {self._fmt(eps)}원")

        raw_text = "\n".join(results)
        analysis = await self._llm_call(
            system_prompt="DCF 모델 결과를 해석하는 기업가치평가 전문가입니다. 한국어로 분석하세요.",
            user_prompt=raw_text,
            caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
        )
        return f"{raw_text}\n\n🎓 분석:\n{analysis}"

    # ── 3. 상대가치 분석 ─────────────────────

    async def _relative_valuation(self, kwargs: dict) -> str:
        ticker, name, data, err = await self._load_fundamentals(kwargs)
        if err:
            return err

        fund_df = data["fund"]
        ohlcv_df = data["ohlcv"]
        current_price = int(ohlcv_df["종가"].iloc[-1])
        rel = self._calc_relative(fund_df, current_price)

        results = [f"📊 {name} 상대가치 분석"]
        results.append(f"현재가: {current_price:,}원\n")
        results.append(f"▸ 현재 PER: {self._fmt(rel['per_now'], 1)}배")
        results.append(f"  - 3년 평균 PER: {self._fmt(rel['per_avg'], 1)}배")
        results.append(f"  - PER 기준 적정가: {self._fmt(rel['per_fair'])}원 ({self._updown(rel['per_fair'], current_price)})")
        results.append(f"\n▸ 현재 PBR: {self._fmt(rel['pbr_now'], 2)}배")
        results.append(f"  - 3년 평균 PBR: {self._fmt(rel['pbr_avg'], 2)}배")
        results.append(f"  - PBR 기준 적정가: {self._fmt(rel['pbr_fair'])}원 ({self._updown(rel['pbr_fair'], current_price)})")
        results.append(f"\n▸ EPS (최근): {self._fmt(rel['eps_now'])}원")
        results.append(f"▸ BPS (최근): {self._fmt(rel['bps_now'])}원")

        raw_text = "\n".join(results)
        analysis = await self._llm_call(
            system_prompt="상대가치 분석 전문가입니다. PER/PBR 밴드 분석으로 매매 판단을 내려주세요. 한국어.",
            user_prompt=raw_text,
            caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
        )
        return f"{raw_text}\n\n🎓 분석:\n{analysis}"

    # ── 4. 그레이엄 넘버 ─────────────────────

    async def _graham_number(self, kwargs: dict) -> str:
        ticker, name, data, err = await self._load_fundamentals(kwargs)
        if err:
            return err

        fund_df = data["fund"]
        ohlcv_df = data["ohlcv"]
        current_price = int(ohlcv_df["종가"].iloc[-1])
        graham_val = self._calc_graham(fund_df)

        eps = fund_df["EPS"].dropna().iloc[-1] if not fund_df["EPS"].dropna().empty else 0
        bps = fund_df["BPS"].dropna().iloc[-1] if not fund_df["BPS"].dropna().empty else 0

        results = [f"📊 {name} 그레이엄 넘버"]
        results.append(f"현재가: {current_price:,}원")
        results.append(f"EPS: {self._fmt(eps)}원 / BPS: {self._fmt(bps)}원")
        results.append(f"그레이엄 공식: √(22.5 × EPS × BPS)")
        results.append(f"그레이엄 넘버: {self._fmt(graham_val)}원 ({self._updown(graham_val, current_price)})")
        if graham_val and graham_val > 0:
            margin = ((graham_val - current_price) / current_price) * 100
            results.append(f"안전마진: {margin:+.1f}%")
            if margin > 30:
                results.append("→ 충분한 안전마진 확보 (가치투자 관점 매수 적격)")
            elif margin > 0:
                results.append("→ 소폭 저평가 (추가 분석 필요)")
            else:
                results.append("→ 그레이엄 기준 고평가 (가치투자 관점 부적합)")

        return "\n".join(results)

    # ── 5. 배당할인모형 ──────────────────────

    async def _dividend_discount(self, kwargs: dict) -> str:
        ticker, name, data, err = await self._load_fundamentals(kwargs)
        if err:
            return err

        fund_df = data["fund"]
        ohlcv_df = data["ohlcv"]
        current_price = int(ohlcv_df["종가"].iloc[-1])
        ddm_val = self._calc_ddm(fund_df, current_price)

        dps = fund_df["DPS"].dropna()
        div_yield = fund_df["DIV"].dropna()

        results = [f"📊 {name} 배당할인모형 (DDM)"]
        results.append(f"현재가: {current_price:,}원")

        if dps.empty or dps.iloc[-1] <= 0:
            return "\n".join(results + ["이 종목은 배당을 지급하지 않아 DDM 적용이 불가합니다."])

        results.append(f"주당 배당금(DPS): {self._fmt(dps.iloc[-1])}원")
        results.append(f"배당수익률: {self._fmt(div_yield.iloc[-1] if not div_yield.empty else 0, 2)}%")

        # 배당 성장률 추정
        yearly_dps = dps.resample("YE").last().dropna()
        if len(yearly_dps) >= 2:
            growth_rates = yearly_dps.pct_change().dropna()
            avg_growth = growth_rates.mean() * 100
            results.append(f"배당 성장률 (평균): {avg_growth:.1f}%")

        if ddm_val:
            results.append(f"DDM 적정가: {self._fmt(ddm_val)}원 ({self._updown(ddm_val, current_price)})")

        return "\n".join(results)

    # ── 6. 민감도 분석 ───────────────────────

    async def _sensitivity_analysis(self, kwargs: dict) -> str:
        ticker, name, data, err = await self._load_fundamentals(kwargs)
        if err:
            return err

        fund_df = data["fund"]
        ohlcv_df = data["ohlcv"]
        current_price = int(ohlcv_df["종가"].iloc[-1])

        eps = fund_df["EPS"].dropna().iloc[-1] if not fund_df["EPS"].dropna().empty else 0
        if eps <= 0:
            return f"{name}: EPS가 음수이므로 DCF 민감도 분석이 불가합니다."

        growth_rates = [0.02, 0.05, 0.08, 0.10, 0.15]
        discount_rates = [0.08, 0.10, 0.12, 0.15]

        results = [f"📊 {name} DCF 민감도 분석"]
        results.append(f"현재가: {current_price:,}원 / 기준 EPS: {self._fmt(eps)}원\n")
        results.append("성장률 \\ 할인율 |" + " | ".join(f"{r*100:.0f}%" for r in discount_rates))
        results.append("-" * 60)

        for g in growth_rates:
            row = f"  {g*100:.0f}%          |"
            for r in discount_rates:
                val = self._dcf_formula(eps, g, r)
                diff = ((val - current_price) / current_price) * 100
                row += f" {self._fmt(val)} ({diff:+.0f}%) |"
            results.append(row)

        results.append(f"\n* 5년 성장 후 영구성장률 2%, 예측기간 10년 가정")

        raw_text = "\n".join(results)
        analysis = await self._llm_call(
            system_prompt="DCF 민감도 분석 결과를 해석하는 전문가입니다. 어떤 시나리오가 가장 합리적인지 판단해주세요. 한국어.",
            user_prompt=raw_text,
            caller_model=kwargs.get("_caller_model"), caller_temperature=kwargs.get("_caller_temperature"),
        )
        return f"{raw_text}\n\n🎓 분석:\n{analysis}"

    # ═══ 계산 엔진 ═══════════════════════════

    def _calc_dcf(self, fund_df, current_price: int) -> float | None:
        """EPS 기반 간이 DCF."""
        eps_data = fund_df["EPS"].dropna()
        if eps_data.empty:
            return None
        eps = eps_data.iloc[-1]
        if eps <= 0:
            return None

        # EPS 성장률 추정 (최근 연간 데이터)
        yearly_eps = eps_data.resample("YE").last().dropna()
        if len(yearly_eps) >= 2:
            positive_eps = yearly_eps[yearly_eps > 0]
            if len(positive_eps) >= 2:
                growth = (positive_eps.iloc[-1] / positive_eps.iloc[0]) ** (1 / (len(positive_eps) - 1)) - 1
                growth = max(min(growth, 0.30), -0.10)  # -10% ~ +30% 클램프
            else:
                growth = 0.05
        else:
            growth = 0.05

        discount_rate = 0.10  # 기본 할인율 10%
        return self._dcf_formula(eps, growth, discount_rate)

    def _dcf_formula(self, eps: float, growth: float, discount: float) -> float:
        """10년 DCF 공식. 5년 고성장 → 5년 체감 → 영구가치."""
        if eps <= 0 or discount <= growth:
            return 0
        terminal_growth = 0.02
        total_pv = 0

        fcf = eps
        for yr in range(1, 11):
            if yr <= 5:
                fcf *= (1 + growth)
            else:
                blend = growth - (growth - terminal_growth) * ((yr - 5) / 5)
                fcf *= (1 + blend)
            total_pv += fcf / ((1 + discount) ** yr)

        # 영구가치 (Terminal Value)
        tv = fcf * (1 + terminal_growth) / (discount - terminal_growth)
        total_pv += tv / ((1 + discount) ** 10)
        return total_pv

    def _calc_graham(self, fund_df) -> float | None:
        """그레이엄 넘버 = √(22.5 × EPS × BPS)."""
        eps_data = fund_df["EPS"].dropna()
        bps_data = fund_df["BPS"].dropna()
        if eps_data.empty or bps_data.empty:
            return None
        eps = eps_data.iloc[-1]
        bps = bps_data.iloc[-1]
        if eps <= 0 or bps <= 0:
            return None
        return math.sqrt(22.5 * eps * bps)

    def _calc_ddm(self, fund_df, current_price: int) -> float | None:
        """Gordon Growth Model: P = DPS × (1+g) / (r - g)."""
        dps_data = fund_df["DPS"].dropna()
        if dps_data.empty or dps_data.iloc[-1] <= 0:
            return None
        dps = dps_data.iloc[-1]

        # 배당 성장률
        yearly_dps = dps_data.resample("YE").last().dropna()
        if len(yearly_dps) >= 2:
            positive_dps = yearly_dps[yearly_dps > 0]
            if len(positive_dps) >= 2:
                g = (positive_dps.iloc[-1] / positive_dps.iloc[0]) ** (1 / (len(positive_dps) - 1)) - 1
                g = max(min(g, 0.15), 0.0)
            else:
                g = 0.02
        else:
            g = 0.02

        r = 0.10  # 요구수익률 10%
        if r <= g:
            return None
        return dps * (1 + g) / (r - g)

    def _calc_relative(self, fund_df, current_price: int) -> dict:
        """PER/PBR 기반 상대가치 분석."""
        per = fund_df["PER"].replace(0, np.nan).dropna()
        pbr = fund_df["PBR"].replace(0, np.nan).dropna()
        eps = fund_df["EPS"].dropna()
        bps = fund_df["BPS"].dropna()

        per_now = per.iloc[-1] if not per.empty else None
        pbr_now = pbr.iloc[-1] if not pbr.empty else None
        eps_now = eps.iloc[-1] if not eps.empty else None
        bps_now = bps.iloc[-1] if not bps.empty else None

        # 3년 평균 PER/PBR
        per_avg = per.mean() if not per.empty else None
        pbr_avg = pbr.mean() if not pbr.empty else None

        # 적정가 = 현재 EPS × 평균 PER, 현재 BPS × 평균 PBR
        per_fair = eps_now * per_avg if eps_now and per_avg else None
        pbr_fair = bps_now * pbr_avg if bps_now and pbr_avg else None

        return {
            "per_now": per_now, "per_avg": per_avg, "per_fair": per_fair,
            "pbr_now": pbr_now, "pbr_avg": pbr_avg, "pbr_fair": pbr_fair,
            "eps_now": eps_now, "bps_now": bps_now,
        }

    @staticmethod
    def _updown(fair_val, current_price: int) -> str:
        if not fair_val or fair_val <= 0:
            return "N/A"
        diff = ((fair_val - current_price) / current_price) * 100
        if diff > 0:
            return f"▲ {diff:.1f}% 저평가"
        return f"▼ {abs(diff):.1f}% 고평가"
