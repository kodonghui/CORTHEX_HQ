"""
SEC EDGAR 공시 조회 도구 — 미국 증권거래위원회 전자공시 시스템.

학술/실무 근거:
  - 10-K(연간)/10-Q(분기) 재무보고서는 GAAP 기준 감사 재무제표
  - 8-K(수시공시)는 중대사건(M&A, 임원변동, 실적 사전발표) 실시간 공개
  - Form 4(내부자 거래): Lakonishok & Lee(2001) — 내부자 매수 클러스터 후 12개월 +7.4% 초과수익
  - 13F(기관보유): 분기별 $100M+ 기관투자자 보유종목 공개 (Buffett, Soros 등)
  - SEC EDGAR FULL-TEXT Search API: 무료, API키 불필요, User-Agent 필수

사용 방법:
  - action="filings": 기업의 최근 공시 목록 (10-K, 10-Q, 8-K 등)
  - action="insider": 내부자 거래 (Form 4) — 최근 매수/매도 내역
  - action="institutional": 기관투자자 보유 (13F) — 대형 펀드 보유종목
  - action="search": EDGAR 전문 검색 (키워드로 공시 내용 검색)

필요 환경변수: 없음 (SEC EDGAR API는 완전 무료)
의존 라이브러리: httpx, yfinance
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.sec_edgar")

# SEC EDGAR API 엔드포인트
EDGAR_BASE = "https://efts.sec.gov/LATEST"
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions"
SEC_HEADERS = {
    "User-Agent": "CORTHEX-HQ/1.0 (corthex-hq.com; admin@corthex-hq.com)",
    "Accept": "application/json",
}

# Form 4 거래 코드 해석 (SEC 공식)
TRANSACTION_CODES = {
    "P": "시장매수 (Open Market Purchase)",
    "S": "시장매도 (Open Market Sale)",
    "A": "부여/수여 (Grant/Award)",
    "D": "처분 (Disposition to Issuer)",
    "F": "세금 원천징수 (Tax Withholding)",
    "M": "옵션 행사 (Option Exercise)",
    "C": "전환 (Conversion)",
    "G": "선물 (Gift)",
    "J": "기타 취득 (Other Acquisition)",
    "K": "기타 처분 (Other Disposition)",
}

# 내부자 직책 분류 (학술 연구: Seyhun(1998), Jeng et al(2003))
INSIDER_ROLES_KO = {
    "CEO": "최고경영자",
    "CFO": "최고재무책임자",
    "COO": "최고운영책임자",
    "CTO": "최고기술책임자",
    "Director": "이사",
    "10% Owner": "10% 이상 대주주",
    "VP": "부사장",
    "SVP": "수석부사장",
    "EVP": "전무이사",
    "Officer": "임원",
    "General Counsel": "법무담당임원",
}


def _httpx():
    try:
        import httpx
        return httpx
    except ImportError:
        return None


def _yf():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        return None


class SecEdgarTool(BaseTool):
    """SEC EDGAR 공시 조회 도구 — 10-K/10-Q/8-K, Form 4, 13F."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "filings")
        if "query" in kwargs and "symbol" not in kwargs:
            kwargs["symbol"] = kwargs["query"]

        dispatch = {
            "filings": self._filings,
            "insider": self._insider,
            "institutional": self._institutional,
            "search": self._search,
        }
        handler = dispatch.get(action)
        if not handler:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능: filings(공시 목록), insider(내부자 거래), "
                "institutional(기관 보유), search(전문 검색)"
            )
        return await handler(kwargs)

    # ── CIK 번호 조회 (ticker → CIK) ──
    async def _get_cik(self, symbol: str) -> str | None:
        """SEC CIK 번호 조회 (회사 고유 식별번호)."""
        httpx = _httpx()
        if not httpx:
            return None
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    "https://efts.sec.gov/LATEST/search-index?q="
                    f'"{symbol}"&dateRange=custom&startdt=2020-01-01&forms=10-K',
                    headers=SEC_HEADERS,
                )
                # 대안: tickers.json에서 조회
                r2 = await c.get(
                    "https://www.sec.gov/files/company_tickers.json",
                    headers=SEC_HEADERS,
                )
                if r2.status_code == 200:
                    data = r2.json()
                    for _, v in data.items():
                        if v.get("ticker", "").upper() == symbol.upper():
                            return str(v["cik_str"]).zfill(10)
        except Exception as e:
            logger.warning("[SEC] CIK 조회 실패: %s", e)
        return None

    # ── 1. 공시 목록 (10-K, 10-Q, 8-K 등) ──
    async def _filings(self, kw: dict) -> str:
        """최근 SEC 공시 목록 조회."""
        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다. 예: symbol='AAPL'"

        form_type = kw.get("form_type", "")  # 특정 서식만 필터
        limit = min(int(kw.get("limit", 15)), 30)

        # yfinance에서 SEC filings 조회 (간편)
        yf = _yf()
        if yf:
            try:
                t = yf.Ticker(symbol)
                info = t.info or {}
                name = info.get("longName") or info.get("shortName") or symbol

                lines = [f"## {name} ({symbol}) — SEC 공시 현황\n"]

                # SEC filings from yfinance
                sec_filings = getattr(t, "sec_filings", None)
                if sec_filings is not None and hasattr(sec_filings, "iterrows"):
                    lines.append("| 날짜 | 서식 | 제목 |")
                    lines.append("|------|------|------|")
                    count = 0
                    for _, row in sec_filings.iterrows():
                        ft = str(row.get("type", ""))
                        if form_type and form_type.upper() not in ft.upper():
                            continue
                        date = str(row.get("date", ""))[:10]
                        title = str(row.get("title", ""))[:80]
                        link = str(row.get("edgarUrl", ""))
                        lines.append(f"| {date} | {ft} | {title} |")
                        count += 1
                        if count >= limit:
                            break
                    if count == 0:
                        lines.append("최근 공시 없음")
                else:
                    # EDGAR API 직접 조회
                    cik = await self._get_cik(symbol)
                    if cik:
                        lines.append(await self._fetch_edgar_filings(cik, form_type, limit))
                    else:
                        lines.append(f"SEC EDGAR에서 {symbol}의 CIK를 찾을 수 없습니다.")

                # 주요 공시 유형 설명
                lines.append("\n### 📋 공시 유형 가이드")
                lines.append("| 서식 | 의미 | 투자 중요도 |")
                lines.append("|------|------|-----------|")
                lines.append("| 10-K | 연간 보고서 (감사 완료 재무제표) | ★★★★★ |")
                lines.append("| 10-Q | 분기 보고서 (미감사 재무제표) | ★★★★ |")
                lines.append("| 8-K | 수시 공시 (중대사건 즉시 보고) | ★★★★★ |")
                lines.append("| DEF 14A | 주주총회 위임장 (임원 보수 공개) | ★★★ |")
                lines.append("| S-1 | IPO 등록신고서 | ★★★★ |")
                lines.append("| 13F | 기관투자자 보유 보고 | ★★★ |")

                return "\n".join(lines)
            except Exception as e:
                logger.warning("[SEC] yfinance 공시 조회 실패: %s", e)

        return f"{symbol}의 SEC 공시를 조회할 수 없습니다. yfinance를 확인하세요."

    async def _fetch_edgar_filings(self, cik: str, form_type: str, limit: int) -> str:
        """EDGAR submissions API로 직접 조회."""
        httpx = _httpx()
        if not httpx:
            return "httpx 미설치"
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    f"{EDGAR_SUBMISSIONS}/CIK{cik}.json",
                    headers=SEC_HEADERS,
                )
                if r.status_code != 200:
                    return f"EDGAR API 응답 오류: {r.status_code}"
                data = r.json()
                recent = data.get("filings", {}).get("recent", {})
                forms = recent.get("form", [])
                dates = recent.get("filingDate", [])
                descs = recent.get("primaryDocDescription", [])
                accessions = recent.get("accessionNumber", [])

                lines = ["| 날짜 | 서식 | 설명 |", "|------|------|------|"]
                count = 0
                for i in range(min(len(forms), 50)):
                    if form_type and form_type.upper() not in forms[i].upper():
                        continue
                    lines.append(f"| {dates[i]} | {forms[i]} | {descs[i] if i < len(descs) else ''} |")
                    count += 1
                    if count >= limit:
                        break
                return "\n".join(lines) if count > 0 else "해당 유형의 공시 없음"
        except Exception as e:
            return f"EDGAR API 오류: {e}"

    # ── 2. 내부자 거래 (Form 4) ──
    async def _insider(self, kw: dict) -> str:
        """내부자 거래 조회 — Lakonishok & Lee(2001) 연구 기반 시그널 포함."""
        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다. 예: symbol='NVDA'"

        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            name = info.get("longName") or info.get("shortName") or symbol

            lines = [
                f"## {name} ({symbol}) — 내부자 거래 분석\n",
                "### 학술 근거",
                "- Lakonishok & Lee (2001): 내부자 매수 클러스터 → 12개월 +7.4% 초과수익",
                "- Seyhun (1998): C-suite(CEO/CFO) 거래가 일반 임원보다 정보 가치 높음",
                "- Jeng et al (2003): 내부자 매수 포트폴리오 연 +11.2% 초과수익\n",
            ]

            # insider_purchases / insider_transactions
            purchases = getattr(t, "insider_purchases", None)
            transactions = getattr(t, "insider_transactions", None)

            if transactions is not None and hasattr(transactions, "iterrows") and len(transactions) > 0:
                lines.append("### 최근 내부자 거래")
                lines.append("| 날짜 | 이름 | 직책 | 유형 | 주수 | 가격 |")
                lines.append("|------|------|------|------|------|------|")
                buy_count, sell_count = 0, 0
                buy_shares, sell_shares = 0, 0
                for _, row in transactions.head(20).iterrows():
                    date = str(row.get("Start Date", ""))[:10]
                    insider = str(row.get("Insider Trading", row.get("Text", "")))[:25]
                    position = str(row.get("Position", row.get("Insider Relation", "")))[:20]
                    txn = str(row.get("Transaction", ""))
                    shares = row.get("Shares", 0)
                    value = row.get("Value", 0)

                    is_buy = "Purchase" in txn or "Buy" in txn
                    is_sell = "Sale" in txn or "Sell" in txn
                    txn_ko = "매수" if is_buy else ("매도" if is_sell else txn[:10])

                    if is_buy:
                        buy_count += 1
                        buy_shares += int(shares or 0)
                    elif is_sell:
                        sell_count += 1
                        sell_shares += int(shares or 0)

                    shares_str = f"{int(shares):,}" if shares else "-"
                    value_str = f"${float(value):,.0f}" if value else "-"
                    lines.append(f"| {date} | {insider} | {position} | {txn_ko} | {shares_str} | {value_str} |")

                # 시그널 분석 (학술 기반)
                lines.append("\n### 📊 내부자 시그널 분석")
                lines.append(f"- 매수 건수: {buy_count}건 ({buy_shares:,}주)")
                lines.append(f"- 매도 건수: {sell_count}건 ({sell_shares:,}주)")

                if buy_count > sell_count * 2:
                    lines.append("- **🟢 강한 매수 시그널** — 내부자 매수 클러스터 감지")
                    lines.append("  - Lakonishok & Lee(2001): 이 패턴 후 12개월 평균 +7.4% 초과수익")
                elif buy_count > sell_count:
                    lines.append("- 🟡 약한 매수 시그널 — 매수 > 매도 (단, C-suite 여부 확인 필요)")
                elif sell_count > buy_count * 3:
                    lines.append("- **🔴 주의: 내부자 대량 매도** — 다만 스톡옵션 행사 후 매도일 수 있음")
                    lines.append("  - Jeng(2003): 옵션 행사 매도는 정보적 가치 낮음. 시장매도(Open Market)만 경계")
                else:
                    lines.append("- ⚪ 중립 — 내부자 거래에서 뚜렷한 방향성 없음")
            else:
                lines.append("최근 내부자 거래 데이터 없음 (yfinance 기준)")

            # 기관 보유 비율 (참고)
            holders = getattr(t, "institutional_holders", None)
            if holders is not None and hasattr(holders, "shape") and len(holders) > 0:
                inst_pct = info.get("heldPercentInstitutions", 0)
                lines.append(f"\n참고: 기관 보유 비율 {inst_pct*100:.1f}%" if inst_pct else "")

            return "\n".join(lines)
        except Exception as e:
            return f"내부자 거래 조회 실패: {e}"

    # ── 3. 기관투자자 보유 (13F) ──
    async def _institutional(self, kw: dict) -> str:
        """13F 기반 기관투자자 보유 현황."""
        symbol = (kw.get("symbol") or "").upper().strip()
        if not symbol:
            return "symbol 파라미터가 필요합니다."

        yf = _yf()
        if not yf:
            return "yfinance 미설치"

        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            name = info.get("longName") or info.get("shortName") or symbol

            lines = [
                f"## {name} ({symbol}) — 기관투자자 보유 분석 (13F 기반)\n",
                "### 13F 보고서란?",
                "- SEC Rule: 운용자산 $100M 이상 기관투자자는 분기별 보유 종목을 SEC에 보고",
                "- 보고 지연: 분기말 기준 45일 이내 공개 (정보 시차 주의)\n",
            ]

            inst_holders = getattr(t, "institutional_holders", None)
            if inst_holders is not None and hasattr(inst_holders, "iterrows") and len(inst_holders) > 0:
                lines.append("### 주요 기관투자자 TOP 15")
                lines.append("| 기관명 | 보유주수 | 보유가치 | 비중 변화 |")
                lines.append("|--------|---------|---------|----------|")
                for _, row in inst_holders.head(15).iterrows():
                    holder = str(row.get("Holder", ""))[:35]
                    shares = row.get("Shares", 0)
                    value = row.get("Value", 0)
                    pct_change = row.get("% Change", row.get("pctChange", 0))

                    shares_str = f"{int(shares):,}" if shares else "-"
                    value_str = f"${float(value)/1e6:,.1f}M" if value and float(value) > 1e6 else (
                        f"${float(value):,.0f}" if value else "-")
                    chg_str = f"{float(pct_change):+.1f}%" if pct_change else "-"
                    lines.append(f"| {holder} | {shares_str} | {value_str} | {chg_str} |")

                # 기관 보유 요약
                inst_pct = info.get("heldPercentInstitutions", 0)
                insider_pct = info.get("heldPercentInsiders", 0)
                lines.append(f"\n### 지분 구조 요약")
                lines.append(f"- 기관투자자 보유: {inst_pct*100:.1f}%")
                lines.append(f"- 내부자 보유: {insider_pct*100:.1f}%")
                lines.append(f"- 일반 투자자: {(1-inst_pct-insider_pct)*100:.1f}%")

                if inst_pct > 0.8:
                    lines.append("\n⚠️ 기관 보유 80% 초과 — 개인 투자자 영향력 제한적, 대량 매도 시 급락 위험")
                elif inst_pct > 0.6:
                    lines.append("\n✅ 기관 보유 60~80% — 안정적 수급 구조")
            else:
                lines.append("기관투자자 데이터 없음")

            # 뮤추얼 펀드 보유
            mf_holders = getattr(t, "mutualfund_holders", None)
            if mf_holders is not None and hasattr(mf_holders, "iterrows") and len(mf_holders) > 0:
                lines.append("\n### 주요 뮤추얼펀드 TOP 10")
                lines.append("| 펀드명 | 보유주수 | 보유가치 |")
                lines.append("|--------|---------|---------|")
                for _, row in mf_holders.head(10).iterrows():
                    holder = str(row.get("Holder", ""))[:40]
                    shares = row.get("Shares", 0)
                    value = row.get("Value", 0)
                    shares_str = f"{int(shares):,}" if shares else "-"
                    value_str = f"${float(value)/1e6:,.1f}M" if value and float(value) > 1e6 else "-"
                    lines.append(f"| {holder} | {shares_str} | {value_str} |")

            return "\n".join(lines)
        except Exception as e:
            return f"기관보유 조회 실패: {e}"

    # ── 4. EDGAR 전문 검색 ──
    async def _search(self, kw: dict) -> str:
        """SEC EDGAR FULL-TEXT 검색."""
        query = kw.get("query") or kw.get("symbol") or ""
        if not query:
            return "query 파라미터가 필요합니다. 예: query='NVDA revenue guidance'"

        form_type = kw.get("form_type", "")
        limit = min(int(kw.get("limit", 10)), 20)

        httpx = _httpx()
        if not httpx:
            return "httpx 미설치"

        try:
            params = {
                "q": query,
                "dateRange": "custom",
                "startdt": (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
                "enddt": datetime.now().strftime("%Y-%m-%d"),
            }
            if form_type:
                params["forms"] = form_type

            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    f"{EDGAR_BASE}/search-index",
                    params=params,
                    headers=SEC_HEADERS,
                )
                if r.status_code != 200:
                    return f"EDGAR 검색 API 오류: {r.status_code}"

                data = r.json()
                hits = data.get("hits", {}).get("hits", [])

                if not hits:
                    return f"'{query}'에 대한 SEC 검색 결과 없음"

                lines = [
                    f"## SEC EDGAR 검색: '{query}'\n",
                    f"총 {data.get('hits', {}).get('total', {}).get('value', 0)}건 중 상위 {limit}건\n",
                    "| 날짜 | 회사 | 서식 | 내용 요약 |",
                    "|------|------|------|----------|",
                ]
                for hit in hits[:limit]:
                    src = hit.get("_source", {})
                    date = str(src.get("file_date", ""))[:10]
                    company = str(src.get("display_names", [""])[0] if src.get("display_names") else "")[:25]
                    form = src.get("form_type", "")
                    desc = str(src.get("display_description", ""))[:50]
                    lines.append(f"| {date} | {company} | {form} | {desc} |")

                return "\n".join(lines)
        except Exception as e:
            return f"EDGAR 검색 실패: {e}"
