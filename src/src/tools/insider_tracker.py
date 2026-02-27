"""
내부자 거래 추적기 Tool (Insider Tracker).

금융감독원 DART API를 사용하여 대주주/임원의 자사주 매매를 감지합니다.
임원·주요주주 소유보고(elestock) 및 대량보유 상황보고(majorstock) 엔드포인트를 활용합니다.

사용 방법:
  - action="track": 특정 기업의 내부자 거래 조회
    - company: 기업명
    - days: 최근 N일 (기본: 90)
  - action="scan": 전체 시장에서 대규모 내부자 거래 스캔
    - min_amount: 최소 거래금액 (기본: 10억원)
    - days: 최근 N일 (기본: 30)
  - action="alert": 주목할 만한 내부자 거래 패턴 분석

필요 환경변수:
  - DART_API_KEY: 금융감독원 DART (https://opendart.fss.or.kr/) 무료 발급
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.insider_tracker")

DART_BASE = "https://opendart.fss.or.kr/api"
CORP_CODE_CACHE = Path("data/dart_corp_codes.json")


class InsiderTrackerTool(BaseTool):
    """대주주/임원 내부자 거래 추적 도구."""

    _corp_codes: dict[str, str] | None = None

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "track")

        if action == "track":
            return await self._track(kwargs)
        elif action == "scan":
            return await self._scan(kwargs)
        elif action == "alert":
            return await self._alert(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "track, scan, alert 중 하나를 사용하세요."
            )

    # ── 특정 기업 내부자 거래 조회 ──

    async def _track(self, kwargs: dict[str, Any]) -> str:
        api_key = self._check_api_key()
        if not api_key:
            return self._key_msg()

        company = kwargs.get("company", "")
        if not company:
            return "기업명(company)을 입력해주세요. 예: company='삼성전자'"

        corp_code = await self._resolve_corp_code(api_key, company)
        if not corp_code:
            return f"'{company}'에 해당하는 기업을 DART에서 찾을 수 없습니다."

        # 임원·주요주주 소유보고 조회
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{DART_BASE}/elestock.json",
                    params={
                        "crtfc_key": api_key,
                        "corp_code": corp_code,
                    },
                    timeout=15,
                )
        except httpx.HTTPError as e:
            return f"DART API 호출 실패: {e}"

        if resp.status_code != 200:
            return f"DART API 오류 ({resp.status_code}): {resp.text[:200]}"

        data = resp.json()
        status = data.get("status", "")

        if status == "013":
            return f"'{company}'의 임원·주요주주 소유보고 데이터가 없습니다."
        if status != "000":
            msg = data.get("message", "알 수 없는 오류")
            return f"DART 오류 ({status}): {msg}"

        items = data.get("list", [])
        if not items:
            return f"'{company}'의 내부자 거래 데이터가 없습니다."

        # 변동 내역 정리
        lines = [f"### {company} 내부자 거래 현황"]
        lines.append(f"  (임원·주요주주 소유보고 기준, 최근 {len(items)}건)")
        lines.append("")

        buy_count = 0
        sell_count = 0
        raw_data: list[str] = []

        for i, item in enumerate(items[:20], 1):  # 최대 20건
            name = item.get("repror", "")  # 보고자
            relation = item.get("isu_exctv_rgist_at", "")  # 임원등록여부
            stock_type = item.get("stkqy_irds_knd", "")  # 증감사유
            change = item.get("stkqy_irds", "")  # 증감수량
            after = item.get("trmend_posesn_stkqy", "")  # 기말잔량
            report_date = item.get("rcept_dt", "")  # 접수일

            # 매수/매도 분류
            change_type = "변동"
            if "취득" in stock_type or "매수" in stock_type:
                change_type = "매수"
                buy_count += 1
            elif "처분" in stock_type or "매도" in stock_type:
                change_type = "매도"
                sell_count += 1

            lines.append(
                f"  [{i}] {name} | {change_type} | 사유: {stock_type}\n"
                f"       변동수량: {change} | 잔량: {after} | 접수일: {report_date}"
            )
            raw_data.append(
                f"{name} - {change_type} - {stock_type} - 변동:{change} 잔량:{after} ({report_date})"
            )

        lines.insert(2, f"  매수 {buy_count}건 / 매도 {sell_count}건")

        formatted = "\n".join(lines)

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 내부자 거래 분석 전문가입니다.\n"
                "내부자(임원/대주주) 거래 데이터를 분석하여 다음을 정리하세요:\n"
                "1. 매수/매도 패턴 요약 (누가, 얼마나, 왜)\n"
                "2. 내부자 거래가 시사하는 점 (경영진의 자사주 신뢰도)\n"
                "3. 투자자가 참고할 시그널 (긍정적/부정적/중립)\n"
                "한국어로 간결하게 답변하세요."
            ),
            user_prompt=f"{company} 내부자 거래:\n" + "\n".join(raw_data),
        )

        return f"## 내부자 거래 추적\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 시장 전체 대규모 거래 스캔 ──

    async def _scan(self, kwargs: dict[str, Any]) -> str:
        api_key = self._check_api_key()
        if not api_key:
            return self._key_msg()

        days = int(kwargs.get("days", 30))
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        # 최근 주요 공시 중 임원·주요주주 관련 공시 검색
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{DART_BASE}/list.json",
                    params={
                        "crtfc_key": api_key,
                        "bgn_de": start_date,
                        "end_de": end_date,
                        "pblntf_ty": "I",  # 지분공시
                        "page_count": 50,
                        "sort": "date",
                        "sort_mth": "desc",
                    },
                    timeout=15,
                )
        except httpx.HTTPError as e:
            return f"DART API 호출 실패: {e}"

        data = resp.json()
        if data.get("status") != "000":
            return f"DART 오류: {data.get('message', '공시 데이터가 없습니다')}"

        items = data.get("list", [])
        if not items:
            return f"최근 {days}일간 주요 지분 변동 공시가 없습니다."

        lines = [f"### 시장 전체 지분 변동 공시 스캔 (최근 {days}일, {len(items)}건)"]
        for i, item in enumerate(items[:30], 1):
            lines.append(
                f"  [{i}] {item.get('corp_name', '')} — {item.get('report_nm', '')}\n"
                f"       날짜: {item.get('rcept_dt', '')} | 유형: {item.get('corp_cls', '')}"
            )

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 내부자 거래 스캐너입니다.\n"
                "지분 변동 공시 목록을 분석하여 다음을 정리하세요:\n"
                "1. 가장 주목할 만한 공시 5개 (대규모 지분 변동 우선)\n"
                "2. 업종/섹터별 지분 변동 패턴\n"
                "3. 투자자가 주의 깊게 볼 기업\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 내부자 거래 스캔\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 패턴 분석 알림 ──

    async def _alert(self, kwargs: dict[str, Any]) -> str:
        api_key = self._check_api_key()
        if not api_key:
            return self._key_msg()

        # 최근 7일간의 지분공시를 분석
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{DART_BASE}/list.json",
                    params={
                        "crtfc_key": api_key,
                        "bgn_de": start_date,
                        "end_de": end_date,
                        "pblntf_ty": "I",
                        "page_count": 100,
                        "sort": "date",
                        "sort_mth": "desc",
                    },
                    timeout=15,
                )
        except httpx.HTTPError as e:
            return f"DART API 호출 실패: {e}"

        data = resp.json()
        if data.get("status") != "000":
            return "최근 지분 공시 데이터가 없습니다."

        items = data.get("list", [])
        if not items:
            return "최근 7일간 주목할 지분 공시가 없습니다."

        # 기업별 공시 횟수 집계
        corp_counts: dict[str, int] = {}
        for item in items:
            corp = item.get("corp_name", "")
            corp_counts[corp] = corp_counts.get(corp, 0) + 1

        # 2건 이상 공시된 기업 = 주목 대상
        hot_corps = {k: v for k, v in corp_counts.items() if v >= 2}

        lines = [f"### 내부자 거래 패턴 알림 (최근 7일)"]
        lines.append(f"  총 지분 공시: {len(items)}건 / 기업 수: {len(corp_counts)}개")

        if hot_corps:
            lines.append("\n  ▶ 집중 감시 대상 (복수 공시)")
            for corp, count in sorted(hot_corps.items(), key=lambda x: -x[1]):
                lines.append(f"    - {corp}: {count}건")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 시장 감시 전문가입니다.\n"
                "최근 내부자 거래 패턴을 분석하여 다음을 판단하세요:\n"
                "1. 복수 공시가 발생한 기업의 의미 (경영권 변동? 자사주 매입? 블록딜?)\n"
                "2. 시장 전체적으로 내부자 매수/매도 흐름\n"
                "3. 투자자에게 보내는 알림 메시지 (주의/관심/무시)\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## 내부자 거래 알림\n\n{formatted}\n\n---\n\n## 패턴 분석\n\n{analysis}"

    # ── 기업코드 변환 ──

    async def _resolve_corp_code(self, api_key: str, company_name: str) -> str:
        """기업명 → DART corp_code 변환."""
        if InsiderTrackerTool._corp_codes is None:
            InsiderTrackerTool._corp_codes = self._load_corp_codes_cache()

        if not InsiderTrackerTool._corp_codes:
            InsiderTrackerTool._corp_codes = await self._download_corp_codes(api_key)

        if not InsiderTrackerTool._corp_codes:
            return ""

        if company_name in InsiderTrackerTool._corp_codes:
            return InsiderTrackerTool._corp_codes[company_name]

        for name, code in InsiderTrackerTool._corp_codes.items():
            if company_name in name or name in company_name:
                return code

        return ""

    def _load_corp_codes_cache(self) -> dict[str, str]:
        if CORP_CODE_CACHE.exists():
            try:
                with open(CORP_CODE_CACHE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    async def _download_corp_codes(self, api_key: str) -> dict[str, str]:
        import io
        import zipfile
        from xml.etree import ElementTree

        logger.info("[InsiderTracker] 기업코드 목록 다운로드 중...")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{DART_BASE}/corpCode.xml",
                    params={"crtfc_key": api_key},
                    timeout=30,
                )
        except httpx.HTTPError as e:
            logger.error("[InsiderTracker] 기업코드 다운로드 실패: %s", e)
            return {}

        if resp.status_code != 200:
            return {}

        try:
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
            xml_name = zf.namelist()[0]
            xml_data = zf.read(xml_name)
            root = ElementTree.fromstring(xml_data)

            codes: dict[str, str] = {}
            for corp in root.iter("list"):
                name_el = corp.find("corp_name")
                code_el = corp.find("corp_code")
                if name_el is not None and code_el is not None:
                    name = (name_el.text or "").strip()
                    code = (code_el.text or "").strip()
                    if name and code:
                        codes[name] = code

            CORP_CODE_CACHE.parent.mkdir(parents=True, exist_ok=True)
            with open(CORP_CODE_CACHE, "w") as f:
                json.dump(codes, f, ensure_ascii=False)

            logger.info("[InsiderTracker] 기업코드 %d개 캐싱 완료", len(codes))
            return codes
        except Exception as e:
            logger.error("[InsiderTracker] 기업코드 파싱 실패: %s", e)
            return {}

    @staticmethod
    def _check_api_key() -> str:
        return os.getenv("DART_API_KEY", "")

    @staticmethod
    def _key_msg() -> str:
        return (
            "DART_API_KEY가 설정되지 않았습니다.\n"
            "금융감독원 DART(https://opendart.fss.or.kr/)에서 "
            "무료 인증키를 발급받은 뒤 .env에 추가하세요.\n"
            "예: DART_API_KEY=your-dart-api-key"
        )
