"""
시장 감성 분석 도구 — Fear & Greed, Short Interest, 뉴스 감성, 소셜 버즈.

학술/실무 근거:
  - CNN Fear & Greed Index: 7개 지표 종합 (VIX, 모멘텀, 신고가/신저가,
    P/C Ratio, 정크본드 스프레드, 시장폭, 안전자산 수요). 0=극공포, 100=극탐욕
  - Short Interest Ratio (Days to Cover):
    공매도 잔고 ÷ 일평균 거래량. 10일 이상 = Short Squeeze 위험
    GameStop(2021) 사태: SI% > 140% → 대규모 숏스퀴즈
  - Baker & Wurgler(2006) "Investor Sentiment and the Cross-Section of Stock Returns":
    감성 지표가 특히 소형·투기적·무배당 주식의 수익률 예측에 유효
  - Antweiler & Frank(2004): 인터넷 게시글 감성이 거래량과 변동성 예측
  - Tetlock(2007): 미디어 비관론이 높으면 다음 날 주가 하락, 이후 반전
    → 극도의 비관 = 역투자 매수 기회
  - Institutional vs Retail Flow:
    기관(Dark Pool, 13F) vs 개인(소액 주문, Reddit) 자금흐름 방향 차이

사용 방법:
  - action="fear_greed": Fear & Greed 유사 지표 종합
  - action="short_interest": 공매도 분석 (Short Squeeze 가능성)
  - action="social": 소셜/뉴스 감성 분석 (yfinance 뉴스 기반)
  - action="full": 전체 감성 분석

필요 환경변수: 없음 (SERPAPI_KEY 있으면 뉴스 확장 가능)
의존 라이브러리: yfinance
"""
from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.sentiment_nlp")


def _yf():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        return None


class SentimentNlpTool(BaseTool):
    """시장 감성 분석 — Fear & Greed, 공매도, 소셜 버즈."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "full")
        if "query" in kwargs and "symbol" not in kwargs:
            kwargs["symbol"] = kwargs["query"]

        dispatch = {
            "fear_greed": self._fear_greed,
            "short_interest": self._short_interest,
            "social": self._social_sentiment,
            "full": self._full,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"알 수 없는 action: {action}\n사용 가능: fear_greed, short_interest, social, full"
        return await handler(kwargs)

    # ── 1. Fear & Greed 유사 지표 ──
    async def _fear_greed(self, kw: dict) -> str:
        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        try:
            scores = {}

            # 1) VIX (변동성)
            vix_t = yf.Ticker("^VIX")
            vix_h = vix_t.history(period="5d")
            if not vix_h.empty:
                vix = float(vix_h["Close"].iloc[-1])
                if vix <= 12:
                    scores["VIX"] = {"score": 95, "label": "극탐욕", "val": vix}
                elif vix <= 15:
                    scores["VIX"] = {"score": 75, "label": "탐욕", "val": vix}
                elif vix <= 20:
                    scores["VIX"] = {"score": 55, "label": "중립", "val": vix}
                elif vix <= 30:
                    scores["VIX"] = {"score": 30, "label": "공포", "val": vix}
                else:
                    scores["VIX"] = {"score": 10, "label": "극공포", "val": vix}

            # 2) 시장 모멘텀 (S&P500 vs 125일 MA)
            spy_t = yf.Ticker("SPY")
            spy_h = spy_t.history(period="1y")
            if not spy_h.empty and len(spy_h) >= 125:
                current = float(spy_h["Close"].iloc[-1])
                ma125 = float(spy_h["Close"].tail(125).mean())
                pct_above = (current - ma125) / ma125 * 100
                if pct_above > 8:
                    scores["모멘텀"] = {"score": 90, "label": "극탐욕", "val": f"{pct_above:+.1f}%"}
                elif pct_above > 3:
                    scores["모멘텀"] = {"score": 70, "label": "탐욕", "val": f"{pct_above:+.1f}%"}
                elif pct_above > -3:
                    scores["모멘텀"] = {"score": 50, "label": "중립", "val": f"{pct_above:+.1f}%"}
                elif pct_above > -8:
                    scores["모멘텀"] = {"score": 30, "label": "공포", "val": f"{pct_above:+.1f}%"}
                else:
                    scores["모멘텀"] = {"score": 10, "label": "극공포", "val": f"{pct_above:+.1f}%"}

            # 3) 안전자산 수요 (금/SPY 상대 성과)
            gld_t = yf.Ticker("GLD")
            gld_h = gld_t.history(period="1mo")
            spy_1m = spy_t.history(period="1mo")
            if not gld_h.empty and not spy_1m.empty:
                gld_ret = float(gld_h["Close"].iloc[-1] / gld_h["Close"].iloc[0] - 1) * 100
                spy_ret = float(spy_1m["Close"].iloc[-1] / spy_1m["Close"].iloc[0] - 1) * 100
                safe_haven = gld_ret - spy_ret
                if safe_haven > 5:
                    scores["안전자산"] = {"score": 15, "label": "극공포", "val": f"금-SPY: {safe_haven:+.1f}%"}
                elif safe_haven > 2:
                    scores["안전자산"] = {"score": 35, "label": "공포", "val": f"금-SPY: {safe_haven:+.1f}%"}
                elif safe_haven > -2:
                    scores["안전자산"] = {"score": 50, "label": "중립", "val": f"금-SPY: {safe_haven:+.1f}%"}
                else:
                    scores["안전자산"] = {"score": 75, "label": "탐욕", "val": f"금-SPY: {safe_haven:+.1f}%"}

            # 4) 정크본드 스프레드 (HYG vs LQD)
            hyg_t = yf.Ticker("HYG")
            lqd_t = yf.Ticker("LQD")
            hyg_h = hyg_t.history(period="1mo")
            lqd_h = lqd_t.history(period="1mo")
            if not hyg_h.empty and not lqd_h.empty:
                hyg_ret = float(hyg_h["Close"].iloc[-1] / hyg_h["Close"].iloc[0] - 1) * 100
                lqd_ret = float(lqd_h["Close"].iloc[-1] / lqd_h["Close"].iloc[0] - 1) * 100
                junk_spread = hyg_ret - lqd_ret
                if junk_spread > 2:
                    scores["정크본드"] = {"score": 80, "label": "탐욕", "val": f"HYG-LQD: {junk_spread:+.1f}%"}
                elif junk_spread > 0:
                    scores["정크본드"] = {"score": 60, "label": "약간 탐욕", "val": f"HYG-LQD: {junk_spread:+.1f}%"}
                elif junk_spread > -2:
                    scores["정크본드"] = {"score": 40, "label": "약간 공포", "val": f"HYG-LQD: {junk_spread:+.1f}%"}
                else:
                    scores["정크본드"] = {"score": 20, "label": "공포", "val": f"HYG-LQD: {junk_spread:+.1f}%"}

            # 5) 시장 폭 (Market Breadth - Advance/Decline)
            # Russell2000 vs S&P500 상대 성과로 근사
            iwm_t = yf.Ticker("IWM")
            iwm_h = iwm_t.history(period="1mo")
            if not iwm_h.empty and not spy_1m.empty:
                iwm_ret = float(iwm_h["Close"].iloc[-1] / iwm_h["Close"].iloc[0] - 1) * 100
                spy_ret_1m = float(spy_1m["Close"].iloc[-1] / spy_1m["Close"].iloc[0] - 1) * 100
                breadth = iwm_ret - spy_ret_1m
                if breadth > 3:
                    scores["시장폭"] = {"score": 80, "label": "탐욕", "val": f"IWM-SPY: {breadth:+.1f}%"}
                elif breadth > 0:
                    scores["시장폭"] = {"score": 60, "label": "약간 탐욕", "val": f"IWM-SPY: {breadth:+.1f}%"}
                elif breadth > -3:
                    scores["시장폭"] = {"score": 40, "label": "약간 공포", "val": f"IWM-SPY: {breadth:+.1f}%"}
                else:
                    scores["시장폭"] = {"score": 20, "label": "공포", "val": f"IWM-SPY: {breadth:+.1f}%"}

            if not scores:
                return "시장 데이터 조회 실패"

            # 종합 점수
            avg_score = sum(s["score"] for s in scores.values()) / len(scores)

            if avg_score >= 80:
                overall = "🔴 극도의 탐욕 (Extreme Greed)"
                advice = "과열! 포지션 축소 또는 헤지 강화 고려. Buffett: \"남들이 탐욕스러울 때 두려워하라\""
            elif avg_score >= 60:
                overall = "🟡 탐욕 (Greed)"
                advice = "시장 낙관적. 신규 매수 시 밸류에이션 점검 필수"
            elif avg_score >= 40:
                overall = "⚪ 중립 (Neutral)"
                advice = "균형 잡힌 시장. 펀더멘털 기반 종목 선별"
            elif avg_score >= 20:
                overall = "🟡 공포 (Fear)"
                advice = "시장 비관적. 양질 종목 분할 매수 기회 탐색"
            else:
                overall = "🟢 극도의 공포 (Extreme Fear)"
                advice = "역투자 매수 최적기. Buffett: \"남들이 두려워할 때 탐욕스러워라\""

            lines = [
                "## Fear & Greed 지수 (CORTHEX 방식)\n",
                f"### 종합 점수: **{avg_score:.0f}/100** — {overall}\n",
                f"💡 _{advice}_\n",
                "### 세부 지표",
                "| 지표 | 점수 | 판정 | 값 |",
                "|------|------|------|-----|",
            ]

            for name, s in scores.items():
                bar = "█" * int(s["score"] / 10) + "░" * (10 - int(s["score"] / 10))
                lines.append(f"| {name} | {bar} {s['score']} | {s['label']} | {s['val']} |")

            lines.append("\n### CNN Fear & Greed 참고 해석")
            lines.append("| 구간 | 의미 | 전략 |")
            lines.append("|------|------|------|")
            lines.append("| 0~25 | 극공포 | 역투자 매수 (역사적 최적 매수 시점) |")
            lines.append("| 25~45 | 공포 | 양질 종목 분할 매수 |")
            lines.append("| 45~55 | 중립 | 현 포지션 유지 |")
            lines.append("| 55~75 | 탐욕 | 신규 매수 자제, 이익 실현 고려 |")
            lines.append("| 75~100 | 극탐욕 | 위험 관리 강화, 헤지 |")

            return "\n".join(lines)
        except Exception as e:
            return f"Fear & Greed 분석 실패: {e}"

    # ── 2. 공매도 분석 ──
    async def _short_interest(self, kw: dict) -> str:
        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            name = info.get("longName") or symbol
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

            lines = [
                f"## {name} ({symbol}) — 공매도 분석\n",
            ]

            # Short Interest 데이터
            shares_short = info.get("sharesShort", 0) or 0
            short_ratio = info.get("shortRatio", 0) or 0  # Days to Cover
            short_pct = info.get("shortPercentOfFloat", 0) or 0
            shares_outstanding = info.get("sharesOutstanding", 0) or 0
            float_shares = info.get("floatShares", 0) or 0
            avg_volume = info.get("averageVolume", 0) or 0

            if shares_short > 0:
                lines.append("### 공매도 현황")
                lines.append("| 항목 | 값 |")
                lines.append("|------|-----|")
                lines.append(f"| 공매도 잔고 | {shares_short:,.0f}주 |")
                if short_pct > 0:
                    lines.append(f"| 유통주식 대비 공매도 비율 | **{short_pct*100:.1f}%** |")
                if short_ratio > 0:
                    lines.append(f"| Days to Cover | **{short_ratio:.1f}일** |")
                if float_shares > 0:
                    lines.append(f"| 유통주식 수 | {float_shares:,.0f}주 |")
                if avg_volume > 0:
                    lines.append(f"| 일평균 거래량 | {avg_volume:,.0f}주 |")

                # Short Squeeze 가능성 판정
                lines.append(f"\n### Short Squeeze 가능성")

                squeeze_score = 0
                reasons = []

                if short_pct > 0.2:
                    squeeze_score += 3
                    reasons.append(f"공매도 비율 {short_pct*100:.1f}% > 20% (매우 높음)")
                elif short_pct > 0.1:
                    squeeze_score += 2
                    reasons.append(f"공매도 비율 {short_pct*100:.1f}% > 10% (높음)")
                elif short_pct > 0.05:
                    squeeze_score += 1
                    reasons.append(f"공매도 비율 {short_pct*100:.1f}% > 5% (보통)")

                if short_ratio > 10:
                    squeeze_score += 3
                    reasons.append(f"Days to Cover {short_ratio:.1f}일 > 10 (매우 높음)")
                elif short_ratio > 5:
                    squeeze_score += 2
                    reasons.append(f"Days to Cover {short_ratio:.1f}일 > 5 (높음)")
                elif short_ratio > 3:
                    squeeze_score += 1
                    reasons.append(f"Days to Cover {short_ratio:.1f}일 > 3 (보통)")

                # 최근 주가 방향 (상승 중이면 squeeze 압력)
                hist = t.history(period="5d")
                if not hist.empty and len(hist) >= 2:
                    recent_change = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
                    if recent_change > 5:
                        squeeze_score += 2
                        reasons.append(f"최근 5일 +{recent_change:.1f}% 급등 → 숏커버 압력")
                    elif recent_change > 2:
                        squeeze_score += 1
                        reasons.append(f"최근 5일 +{recent_change:.1f}% 상승")

                for r in reasons:
                    lines.append(f"- {r}")

                if squeeze_score >= 6:
                    lines.append(f"\n🔥 **Short Squeeze 위험 높음** (점수: {squeeze_score}/8)")
                    lines.append("- GameStop(2021) 패턴: 높은 SI% + 상승 모멘텀 + 소셜 버즈")
                    lines.append("- 전략: 매수 포지션 유지 또는 OTM 콜 매수로 Squeeze 참여")
                elif squeeze_score >= 4:
                    lines.append(f"\n🟡 **Short Squeeze 가능성 있음** (점수: {squeeze_score}/8)")
                    lines.append("- 촉매제(실적 서프라이즈, 뉴스) 발생 시 급등 가능")
                elif squeeze_score >= 2:
                    lines.append(f"\n⚪ **보통 수준** (점수: {squeeze_score}/8)")
                else:
                    lines.append(f"\n🟢 **공매도 리스크 낮음** (점수: {squeeze_score}/8)")
            else:
                lines.append("공매도 데이터 없음 (yfinance에서 제공하지 않는 종목)")

            lines.append("\n### 공매도 해석 가이드")
            lines.append("| 기준 | 의미 |")
            lines.append("|------|------|")
            lines.append("| SI% > 20% | 극도로 높음. Short Squeeze 최고 위험 |")
            lines.append("| SI% 10~20% | 높음. 숏커버 시 급등 가능 |")
            lines.append("| Days to Cover > 10 | 공매도 청산에 10일+ 소요 → 유동성 함정 |")
            lines.append("| 주가 상승 + 높은 SI% | Short Squeeze 진행 시그널 |")

            return "\n".join(lines)
        except Exception as e:
            return f"공매도 분석 실패: {e}"

    # ── 3. 소셜/뉴스 감성 ──
    async def _social_sentiment(self, kw: dict) -> str:
        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            name = info.get("longName") or symbol

            lines = [
                f"## {name} ({symbol}) — 뉴스/소셜 감성 분석\n",
                "### Tetlock(2007): 미디어 비관론 극단 → 주가 반전 기회\n",
            ]

            # yfinance 뉴스
            news = t.news
            if news and len(news) > 0:
                lines.append(f"### 최근 뉴스 ({len(news[:10])}건)")
                lines.append("| 날짜 | 제목 | 감성(키워드) |")
                lines.append("|------|------|-------------|")

                positive_count = 0
                negative_count = 0

                positive_words = [
                    "surge", "soar", "beat", "upgrade", "bullish", "rally", "jump",
                    "record", "growth", "profit", "strong", "gain", "rise", "up",
                    "outperform", "positive", "optimistic", "exceed", "boom",
                ]
                negative_words = [
                    "crash", "plunge", "miss", "downgrade", "bearish", "fall",
                    "drop", "loss", "weak", "decline", "cut", "risk", "fear",
                    "warning", "layoff", "lawsuit", "bankruptcy", "recession", "sell",
                ]

                for article in news[:10]:
                    title = article.get("title", "제목 없음")
                    pub = article.get("providerPublishTime", 0)
                    publisher = article.get("publisher", "")

                    from datetime import datetime
                    date_str = datetime.fromtimestamp(pub).strftime("%m/%d") if pub else "?"

                    # 키워드 기반 감성 분류
                    title_lower = title.lower()
                    pos_found = [w for w in positive_words if w in title_lower]
                    neg_found = [w for w in negative_words if w in title_lower]

                    if len(pos_found) > len(neg_found):
                        sentiment = f"🟢 긍정 ({', '.join(pos_found[:2])})"
                        positive_count += 1
                    elif len(neg_found) > len(pos_found):
                        sentiment = f"🔴 부정 ({', '.join(neg_found[:2])})"
                        negative_count += 1
                    else:
                        sentiment = "⚪ 중립"

                    # 제목 30자 제한
                    short_title = title[:50] + "..." if len(title) > 50 else title
                    lines.append(f"| {date_str} | {short_title} | {sentiment} |")

                total = positive_count + negative_count
                if total > 0:
                    pos_ratio = positive_count / total * 100
                    lines.append(f"\n### 뉴스 감성 요약")
                    lines.append(f"- 긍정: {positive_count}건 / 부정: {negative_count}건")
                    lines.append(f"- 긍정 비율: {pos_ratio:.0f}%")

                    if pos_ratio >= 80:
                        lines.append("- 🟡 **과도한 낙관** — Tetlock(2007): 극단 낙관 후 하락 주의")
                    elif pos_ratio >= 60:
                        lines.append("- 🟢 전반적 긍정 — 상승 모멘텀 유지")
                    elif pos_ratio >= 40:
                        lines.append("- ⚪ 혼조 — 뉴스만으로 방향 판단 어려움")
                    elif pos_ratio >= 20:
                        lines.append("- 🔴 부정적 — 추가 하락 가능, 그러나 역투자 기회도")
                    else:
                        lines.append("- 🟢 **극도의 비관** — Tetlock: 극단 비관 후 반등 가능!")
            else:
                lines.append("최근 뉴스 데이터 없음")

            # 분석가 추천
            rec = info.get("recommendationKey", "")
            target_price = info.get("targetMeanPrice", 0)
            num_analysts = info.get("numberOfAnalystOpinions", 0)

            if rec:
                lines.append(f"\n### 분석가 컨센서스")
                rec_map = {
                    "strong_buy": "🟢 적극 매수",
                    "buy": "🟢 매수",
                    "hold": "⚪ 보유",
                    "sell": "🔴 매도",
                    "strong_sell": "🔴 적극 매도",
                }
                rec_ko = rec_map.get(rec, rec)
                lines.append(f"- 컨센서스: **{rec_ko}** ({num_analysts}명)")
                if target_price:
                    price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                    upside = (target_price - price) / price * 100 if price else 0
                    lines.append(f"- 목표가: ${target_price:,.2f} (현재가 대비 {upside:+.1f}%)")

            lines.append("\n### Baker & Wurgler(2006) 감성 투자 원칙")
            lines.append("- 감성 극단(공포/탐욕)은 특히 **소형주, 투기주, 무배당주**에 영향 큼")
            lines.append("- 고감성 시기 → 이런 주식 과대평가 → 이후 저조한 수익")
            lines.append("- 저감성 시기 → 이런 주식 과소평가 → 이후 높은 수익")

            return "\n".join(lines)
        except Exception as e:
            return f"감성 분석 실패: {e}"

    # ── 전체 분석 ──
    async def _full(self, kw: dict) -> str:
        parts = []
        # Fear & Greed는 symbol 불필요
        try:
            parts.append(await self._fear_greed(kw))
        except Exception as e:
            parts.append(f"[Fear & Greed 실패: {e}]")

        # symbol 필요한 것들
        symbol = (kw.get("symbol") or "").upper().strip()
        if symbol:
            for fn in [self._short_interest, self._social_sentiment]:
                try:
                    parts.append(await fn(kw))
                except Exception as e:
                    parts.append(f"[분석 일부 실패: {e}]")
        else:
            parts.append("_종목별 공매도/감성 분석은 symbol 파라미터 필요_")

        return "\n\n---\n\n".join(parts)
