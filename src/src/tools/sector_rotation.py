"""
섹터 로테이션 분석 도구 — 경기 사이클별 섹터 강도, RS(상대강도), ETF 자금흐름.

학술/실무 근거:
  - Fidelity Sector Rotation Model: 경기 사이클 4단계(초기회복→확장→둔화→침체)별
    수혜/피해 섹터 매핑. 1940년대 이후 S&P500 데이터 검증
  - Relative Strength (RS) by Levy(1967): 개별 자산 수익률 ÷ 벤치마크 수익률.
    RS > 1.0 = 시장 대비 아웃퍼폼. 모멘텀 전략의 핵심 지표
  - Sector ETF Fund Flow: 기관 자금 유출입 → 스마트머니 방향 추적.
    SPDR Select Sector ETF 시리즈 (XLK, XLF, XLE 등) 활용
  - Mebane Faber(2007) "A Quantitative Approach to Tactical Asset Allocation":
    10개월 이동평균 위/아래로 매수/매도 → 섹터 타이밍에 적용
  - GICS (Global Industry Classification Standard): S&P/MSCI 11개 섹터 분류 표준

사용 방법:
  - action="map": 경기 사이클별 섹터 맵 (현재 위치 추정)
  - action="relative_strength": 11개 섹터 상대강도 순위
  - action="flow": 섹터 ETF 자금흐름 + 가격 변화
  - action="full": 전체 섹터 로테이션 분석

필요 환경변수: 없음
의존 라이브러리: yfinance
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.sector_rotation")


def _yf():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        return None


# GICS 11개 섹터 → SPDR Select Sector ETF 매핑
SECTOR_ETFS = {
    "XLK": {"name": "Technology", "name_ko": "기술", "gics": "정보기술"},
    "XLF": {"name": "Financials", "name_ko": "금융", "gics": "금융"},
    "XLV": {"name": "Health Care", "name_ko": "헬스케어", "gics": "헬스케어"},
    "XLY": {"name": "Consumer Disc.", "name_ko": "경기소비재", "gics": "경기관련소비재"},
    "XLP": {"name": "Consumer Staples", "name_ko": "필수소비재", "gics": "필수소비재"},
    "XLE": {"name": "Energy", "name_ko": "에너지", "gics": "에너지"},
    "XLI": {"name": "Industrials", "name_ko": "산업재", "gics": "산업재"},
    "XLB": {"name": "Materials", "name_ko": "소재", "gics": "소재"},
    "XLRE": {"name": "Real Estate", "name_ko": "부동산", "gics": "부동산"},
    "XLU": {"name": "Utilities", "name_ko": "유틸리티", "gics": "유틸리티"},
    "XLC": {"name": "Communication", "name_ko": "커뮤니케이션", "gics": "커뮤니케이션서비스"},
}

# Fidelity 경기 사이클 모델: 각 단계별 수혜/피해 섹터
CYCLE_MAP = {
    "초기 회복 (Early Recovery)": {
        "desc": "경기침체 바닥 → 회복 초입. 금리 인하 막바지, 재고 최저, 기업 이익 반등 시작",
        "leaders": ["XLF", "XLY", "XLI", "XLRE"],
        "laggards": ["XLE", "XLU", "XLP"],
        "indicators": "실업률 피크 후 하락, ISM 50 상향 돌파, 수익률 곡선 가팔라짐",
    },
    "확장 (Expansion)": {
        "desc": "경기 확장기. 기업이익 성장, 소비/투자 활발, 금리 점진적 인상",
        "leaders": ["XLK", "XLI", "XLB", "XLE"],
        "laggards": ["XLU", "XLP", "XLRE"],
        "indicators": "GDP 성장률 상승, 임금 상승, PMI > 50 지속, 신용 확대",
    },
    "둔화 (Slowdown)": {
        "desc": "경기 정점 부근. 금리 높음, 이익 증가세 둔화, 인플레 압력",
        "leaders": ["XLE", "XLP", "XLV"],
        "laggards": ["XLK", "XLY", "XLF"],
        "indicators": "금리 피크 접근, PMI 하락 추세, 재고 증가, 신용 긴축 시작",
    },
    "침체 (Contraction)": {
        "desc": "경기 수축. 기업이익 감소, 실업 증가, 금리 인하 시작",
        "leaders": ["XLU", "XLP", "XLV", "XLRE"],
        "laggards": ["XLY", "XLI", "XLF", "XLB"],
        "indicators": "ISM < 50, 수익률 곡선 역전 후 정상화, VIX 급등, 대규모 해고",
    },
}


class SectorRotationTool(BaseTool):
    """섹터 로테이션 분석 — 경기 사이클, 상대강도, ETF 자금흐름."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "full")
        dispatch = {
            "map": self._cycle_map,
            "relative_strength": self._relative_strength,
            "flow": self._sector_flow,
            "full": self._full,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"알 수 없는 action: {action}\n사용 가능: map, relative_strength, flow, full"
        return await handler(kwargs)

    # ── 1. 경기 사이클 섹터 맵 ──
    async def _cycle_map(self, kw: dict) -> str:
        lines = [
            "## 경기 사이클별 섹터 로테이션 맵\n",
            "### Fidelity Sector Rotation Model (1940년대~ S&P500 검증)\n",
        ]

        for phase, info in CYCLE_MAP.items():
            leaders = ", ".join(
                f"**{SECTOR_ETFS[s]['name_ko']}**({s})" for s in info["leaders"]
            )
            laggards = ", ".join(
                f"{SECTOR_ETFS[s]['name_ko']}({s})" for s in info["laggards"]
            )
            lines.append(f"#### {phase}")
            lines.append(f"_{info['desc']}_\n")
            lines.append(f"- 🟢 수혜 섹터: {leaders}")
            lines.append(f"- 🔴 피해 섹터: {laggards}")
            lines.append(f"- 📊 주요 지표: {info['indicators']}\n")

        # 현재 시장 데이터로 사이클 추정
        yf = _yf()
        if yf:
            cycle_score = await self._estimate_cycle(yf)
            if cycle_score:
                lines.append("---\n")
                lines.append(cycle_score)

        return "\n".join(lines)

    async def _estimate_cycle(self, yf) -> str:
        """시장 데이터 기반 현재 경기 사이클 추정."""
        try:
            signals = []

            # VIX 수준
            vix_t = yf.Ticker("^VIX")
            vix_h = vix_t.history(period="5d")
            if not vix_h.empty:
                vix = float(vix_h["Close"].iloc[-1])
                if vix >= 30:
                    signals.append(("침체", "VIX ≥ 30 (공포)"))
                elif vix >= 20:
                    signals.append(("둔화", "VIX 20~30 (경계)"))
                else:
                    signals.append(("확장", f"VIX {vix:.1f} (안정)"))

            # 10Y-2Y 스프레드
            t10 = yf.Ticker("^TNX")
            h10 = t10.history(period="5d")
            t2 = yf.Ticker("2YY=F")
            h2 = t2.history(period="5d")
            if not h10.empty and not h2.empty:
                y10 = float(h10["Close"].iloc[-1])
                y2 = float(h2["Close"].iloc[-1])
                spread = y10 - y2
                if spread < 0:
                    signals.append(("둔화", f"수익률 곡선 역전 ({spread:+.2f}%)"))
                elif spread < 0.3:
                    signals.append(("둔화", f"수익률 곡선 평탄 ({spread:+.2f}%)"))
                elif spread > 1.0:
                    signals.append(("초기 회복", f"수익률 곡선 가파름 ({spread:+.2f}%)"))
                else:
                    signals.append(("확장", f"수익률 곡선 정상 ({spread:+.2f}%)"))

            # 방어적 vs 공격적 섹터 상대 성과 (3개월)
            xlp_t = yf.Ticker("XLP")
            xly_t = yf.Ticker("XLY")
            xlp_h = xlp_t.history(period="3mo")
            xly_h = xly_t.history(period="3mo")
            if not xlp_h.empty and not xly_h.empty:
                xlp_ret = (xlp_h["Close"].iloc[-1] / xlp_h["Close"].iloc[0] - 1) * 100
                xly_ret = (xly_h["Close"].iloc[-1] / xly_h["Close"].iloc[0] - 1) * 100
                if xlp_ret > xly_ret + 3:
                    signals.append(("침체", f"방어적(XLP) > 경기민감(XLY) {xlp_ret-xly_ret:+.1f}%p"))
                elif xly_ret > xlp_ret + 3:
                    signals.append(("확장", f"경기민감(XLY) > 방어적(XLP) {xly_ret-xlp_ret:+.1f}%p"))
                else:
                    signals.append(("둔화", "방어적 ≈ 경기민감 (전환기)"))

            if not signals:
                return ""

            # 가장 많은 투표를 받은 사이클
            from collections import Counter
            votes = Counter(s[0] for s in signals)
            estimated = votes.most_common(1)[0][0]

            # 해당 사이클 정보 매칭
            cycle_key = {
                "초기 회복": "초기 회복 (Early Recovery)",
                "확장": "확장 (Expansion)",
                "둔화": "둔화 (Slowdown)",
                "침체": "침체 (Contraction)",
            }[estimated]
            info = CYCLE_MAP[cycle_key]

            lines = [
                f"### 현재 추정 사이클: **{cycle_key}**\n",
                "| 근거 지표 | 시그널 |",
                "|-----------|--------|",
            ]
            for phase, reason in signals:
                emoji = "✅" if phase == estimated else "⚠️"
                lines.append(f"| {emoji} {reason} | {phase} |")

            leaders = ", ".join(
                f"**{SECTOR_ETFS[s]['name_ko']}**({s})" for s in info["leaders"]
            )
            lines.append(f"\n🟢 **현재 사이클 수혜 섹터**: {leaders}")
            lines.append(f"\n_주의: 사이클 추정은 참고용이며, 복수 지표 교차 확인 필수_")

            return "\n".join(lines)
        except Exception as e:
            logger.warning("사이클 추정 실패: %s", e)
            return ""

    # ── 2. 섹터 상대강도 (RS) 순위 ──
    async def _relative_strength(self, kw: dict) -> str:
        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        period = kw.get("period", "3mo")
        if period not in ("1mo", "3mo", "6mo", "1y"):
            period = "3mo"

        try:
            # S&P500 벤치마크
            spy_t = yf.Ticker("SPY")
            spy_h = spy_t.history(period=period)
            if spy_h.empty:
                return "SPY 데이터 조회 실패"
            spy_ret = float(spy_h["Close"].iloc[-1] / spy_h["Close"].iloc[0] - 1) * 100

            results = []
            for etf, info in SECTOR_ETFS.items():
                try:
                    t = yf.Ticker(etf)
                    h = t.history(period=period)
                    if h.empty:
                        continue
                    ret = float(h["Close"].iloc[-1] / h["Close"].iloc[0] - 1) * 100
                    rs = ret / spy_ret if spy_ret != 0 else 1.0
                    price = float(h["Close"].iloc[-1])

                    # Faber 10개월 MA 시그널 (근사: 200일 MA)
                    h200 = t.history(period="1y")
                    above_ma = True
                    if not h200.empty and len(h200) >= 200:
                        ma200 = float(h200["Close"].tail(200).mean())
                        above_ma = price > ma200

                    results.append({
                        "etf": etf,
                        "name_ko": info["name_ko"],
                        "ret": ret,
                        "rs": rs,
                        "price": price,
                        "above_ma": above_ma,
                    })
                except Exception:
                    continue

            if not results:
                return "섹터 데이터 조회 실패"

            # RS 순으로 정렬
            results.sort(key=lambda x: x["rs"], reverse=True)

            period_label = {"1mo": "1개월", "3mo": "3개월", "6mo": "6개월", "1y": "1년"}[period]

            lines = [
                f"## 섹터 상대강도(RS) 순위 — {period_label}\n",
                f"### Levy(1967) RS: 섹터 수익률 ÷ S&P500 수익률\n",
                f"S&P 500 (SPY) {period_label} 수익률: **{spy_ret:+.2f}%**\n",
                "| 순위 | 섹터 | ETF | 수익률 | RS | 200일MA | 판정 |",
                "|------|------|-----|--------|-----|---------|------|",
            ]

            for i, r in enumerate(results, 1):
                ma_icon = "🟢" if r["above_ma"] else "🔴"
                if r["rs"] > 1.2:
                    verdict = "💪 강한 아웃퍼폼"
                elif r["rs"] > 1.0:
                    verdict = "✅ 아웃퍼폼"
                elif r["rs"] > 0.8:
                    verdict = "⚪ 중립"
                else:
                    verdict = "🔻 언더퍼폼"
                lines.append(
                    f"| {i} | {r['name_ko']} | {r['etf']} | "
                    f"{r['ret']:+.2f}% | {r['rs']:.2f} | "
                    f"{ma_icon} {'위' if r['above_ma'] else '아래'} | {verdict} |"
                )

            # 요약
            top3 = results[:3]
            bottom3 = results[-3:]
            lines.append(f"\n### 요약")
            lines.append(f"- 🏆 상위 3: {', '.join(r['name_ko'] for r in top3)}")
            lines.append(f"- 🔻 하위 3: {', '.join(r['name_ko'] for r in bottom3)}")

            if top3[0]["rs"] > 1.5:
                lines.append(f"\n⚠️ {top3[0]['name_ko']}의 RS {top3[0]['rs']:.2f} — 과열 가능성 점검 필요")

            # Faber 200일 MA 시그널
            above_count = sum(1 for r in results if r["above_ma"])
            lines.append(f"\n### Faber(2007) 200일 MA 시그널")
            lines.append(f"- 200일MA 위: {above_count}/{len(results)}개 섹터")
            if above_count >= 9:
                lines.append("- 🟢 대부분 섹터 상승 추세 — 강세장")
            elif above_count >= 6:
                lines.append("- 🟡 혼조 — 섹터 선별 중요")
            else:
                lines.append("- 🔴 다수 섹터 하락 추세 — 방어적 포지션 권장")

            return "\n".join(lines)
        except Exception as e:
            return f"상대강도 분석 실패: {e}"

    # ── 3. 섹터 ETF 자금흐름 ──
    async def _sector_flow(self, kw: dict) -> str:
        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        try:
            results = []
            for etf, info in SECTOR_ETFS.items():
                try:
                    t = yf.Ticker(etf)
                    hist = t.history(period="3mo")
                    if hist.empty:
                        continue

                    price = float(hist["Close"].iloc[-1])
                    ret_1m = 0
                    ret_3m = float(hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100

                    # 1개월 수익률 근사 (최근 21거래일)
                    if len(hist) >= 21:
                        ret_1m = float(
                            hist["Close"].iloc[-1] / hist["Close"].iloc[-21] - 1
                        ) * 100

                    # 거래량 변화 (최근 5일 vs 20일 평균)
                    vol_5d = float(hist["Volume"].tail(5).mean()) if len(hist) >= 5 else 0
                    vol_20d = float(hist["Volume"].tail(20).mean()) if len(hist) >= 20 else 0
                    vol_ratio = vol_5d / vol_20d if vol_20d > 0 else 1.0

                    # 기관 비율은 yfinance info에서 추출 시도
                    inst_pct = 0
                    try:
                        tinfo = t.info or {}
                        inst_pct = tinfo.get("heldPercentInstitutions", 0) or 0
                    except Exception:
                        pass

                    results.append({
                        "etf": etf,
                        "name_ko": info["name_ko"],
                        "price": price,
                        "ret_1m": ret_1m,
                        "ret_3m": ret_3m,
                        "vol_ratio": vol_ratio,
                        "inst_pct": inst_pct,
                    })
                except Exception:
                    continue

            if not results:
                return "섹터 ETF 데이터 조회 실패"

            # 3개월 수익률 순 정렬
            results.sort(key=lambda x: x["ret_3m"], reverse=True)

            lines = [
                "## 섹터 ETF 자금흐름 분석\n",
                "### SPDR Select Sector ETF 시리즈 (11개 GICS 섹터)\n",
                "| 섹터 | ETF | 가격 | 1개월 | 3개월 | 거래량비 | 판정 |",
                "|------|-----|------|-------|-------|---------|------|",
            ]

            for r in results:
                # 거래량 비율 해석 (5일/20일)
                if r["vol_ratio"] > 1.5:
                    vol_tag = "🔥급증"
                elif r["vol_ratio"] > 1.1:
                    vol_tag = "📈증가"
                elif r["vol_ratio"] < 0.7:
                    vol_tag = "📉감소"
                else:
                    vol_tag = "→평균"

                # 종합 판정
                if r["ret_3m"] > 5 and r["vol_ratio"] > 1.1:
                    verdict = "🟢 자금유입"
                elif r["ret_3m"] < -5 and r["vol_ratio"] > 1.1:
                    verdict = "🔴 자금유출"
                elif r["ret_3m"] > 3:
                    verdict = "✅ 강세"
                elif r["ret_3m"] < -3:
                    verdict = "🔻 약세"
                else:
                    verdict = "⚪ 중립"

                lines.append(
                    f"| {r['name_ko']} | {r['etf']} | ${r['price']:,.2f} | "
                    f"{r['ret_1m']:+.1f}% | {r['ret_3m']:+.1f}% | "
                    f"{r['vol_ratio']:.2f}x {vol_tag} | {verdict} |"
                )

            # 자금흐름 요약
            inflow = [r for r in results if r["ret_3m"] > 3 and r["vol_ratio"] > 1.0]
            outflow = [r for r in results if r["ret_3m"] < -3 and r["vol_ratio"] > 1.0]

            lines.append(f"\n### 자금흐름 요약")
            if inflow:
                lines.append(f"- 🟢 **자금 유입**: {', '.join(r['name_ko'] for r in inflow)}")
            if outflow:
                lines.append(f"- 🔴 **자금 유출**: {', '.join(r['name_ko'] for r in outflow)}")

            # 로테이션 패턴 감지
            top_sector = results[0]
            bottom_sector = results[-1]
            gap = top_sector["ret_3m"] - bottom_sector["ret_3m"]
            lines.append(f"\n### 로테이션 패턴")
            lines.append(f"- 최강 섹터: {top_sector['name_ko']} ({top_sector['ret_3m']:+.1f}%)")
            lines.append(f"- 최약 섹터: {bottom_sector['name_ko']} ({bottom_sector['ret_3m']:+.1f}%)")
            lines.append(f"- 섹터간 스프레드: {gap:.1f}%p")

            if gap > 20:
                lines.append("- ⚠️ **극단적 편차** — 로테이션 전환 임박 가능")
            elif gap > 10:
                lines.append("- 🟡 섹터간 차별화 뚜렷 — 모멘텀 추종 유리")
            else:
                lines.append("- ⚪ 섹터간 차별화 적음 — 인덱스 투자 유리")

            return "\n".join(lines)
        except Exception as e:
            return f"섹터 자금흐름 분석 실패: {e}"

    # ── 전체 분석 ──
    async def _full(self, kw: dict) -> str:
        parts = []
        for fn in [self._cycle_map, self._relative_strength, self._sector_flow]:
            try:
                parts.append(await fn(kw))
            except Exception as e:
                parts.append(f"[분석 일부 실패: {e}]")
        return "\n\n---\n\n".join(parts)
