"""
DART 기업 재무제표 Tool.

금융감독원 전자공시시스템(DART) OpenAPI를 사용하여
기업 재무제표, 기업정보, 최신 공시를 조회합니다.

사용 방법:
  - action="financial": 재무제표 (매출, 영업이익, 순이익 등)
  - action="company": 기업 기본정보 (대표자, 업종, 주소 등)
  - action="disclosure": 최신 공시 목록

필요 환경변수:
  - DART_API_KEY: 금융감독원 DART (https://opendart.fss.or.kr/) 무료 발급
"""
from __future__ import annotations

import io
import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.dart_api")

DART_BASE = "https://opendart.fss.or.kr/api"
CORP_CODE_CACHE = Path("data/dart_corp_codes.json")


class DartApiTool(BaseTool):
    """DART 기업 재무제표 및 공시 조회 도구."""

    _corp_codes: dict[str, str] | None = None  # 기업명 → corp_code 매핑

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "financial")

        if action == "financial":
            return await self._get_financial(kwargs)
        elif action == "company":
            return await self._get_company(kwargs)
        elif action == "disclosure":
            return await self._get_disclosure(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "financial, company, disclosure 중 하나를 사용하세요."
            )

    # ── 재무제표 조회 ──

    async def _get_financial(self, kwargs: dict[str, Any]) -> str:
        api_key = self._check_api_key()
        if not api_key:
            return self._key_msg()

        company = kwargs.get("company", "")
        if not company:
            return "기업명(company)을 입력해주세요. 예: company='삼성전자'"

        corp_code = await self._resolve_corp_code(api_key, company)
        if not corp_code:
            return f"'{company}'에 해당하는 기업을 DART에서 찾을 수 없습니다."

        year = kwargs.get("year", "2024")
        report_code = kwargs.get("report_code", "11011")  # 11011=사업보고서

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{DART_BASE}/fnlttSinglAcntAll.json",
                    params={
                        "crtfc_key": api_key,
                        "corp_code": corp_code,
                        "bsns_year": year,
                        "reprt_code": report_code,
                        "fs_div": "CFS",  # 연결재무제표
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
            return f"'{company}'의 {year}년 재무제표가 아직 공시되지 않았습니다."
        if status != "000":
            msg = data.get("message", "알 수 없는 오류")
            return f"DART 오류 ({status}): {msg}"

        items = data.get("list", [])
        if not items:
            return f"'{company}'의 {year}년 재무제표 데이터가 없습니다."

        # 핵심 항목 추출
        key_accounts = [
            "매출액", "영업이익", "당기순이익", "자산총계",
            "부채총계", "자본총계", "영업활동현금흐름",
        ]
        lines = [f"### {company} {year}년 재무제표"]

        for item in items:
            name = item.get("account_nm", "")
            if name in key_accounts:
                current = item.get("thstrm_amount", "")
                prev = item.get("frmtrm_amount", "")
                lines.append(f"  {name}: {self._format_amount(current)} (전년: {self._format_amount(prev)})")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 기업 재무 분석 전문가입니다.\n"
                "재무제표를 분석하여 다음을 정리하세요:\n"
                "1. 매출/영업이익/순이익 추이 (성장/감소)\n"
                "2. 수익성 분석 (영업이익률, 순이익률)\n"
                "3. 재무 건전성 (부채비율)\n"
                "4. 종합 투자 의견\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"## DART 재무제표\n\n{formatted}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 기업 기본정보 ──

    async def _get_company(self, kwargs: dict[str, Any]) -> str:
        api_key = self._check_api_key()
        if not api_key:
            return self._key_msg()

        company = kwargs.get("company", "")
        if not company:
            return "기업명(company)을 입력해주세요."

        corp_code = await self._resolve_corp_code(api_key, company)
        if not corp_code:
            return f"'{company}'에 해당하는 기업을 찾을 수 없습니다."

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{DART_BASE}/company.json",
                    params={"crtfc_key": api_key, "corp_code": corp_code},
                    timeout=15,
                )
        except httpx.HTTPError as e:
            return f"DART API 호출 실패: {e}"

        if resp.status_code != 200:
            return f"DART API 오류: {resp.status_code}"

        data = resp.json()
        if data.get("status") != "000":
            return f"DART 오류: {data.get('message', '')}"

        lines = [f"### {company} 기업 정보"]
        fields = {
            "corp_name": "기업명",
            "corp_name_eng": "영문명",
            "ceo_nm": "대표자",
            "induty_code": "업종코드",
            "est_dt": "설립일",
            "stock_name": "종목명",
            "stock_code": "종목코드",
            "adres": "주소",
            "hm_url": "홈페이지",
            "acc_mt": "결산월",
        }
        for key, label in fields.items():
            val = data.get(key, "")
            if val:
                lines.append(f"  {label}: {val}")

        return "\n".join(lines)

    # ── 최신 공시 ──

    async def _get_disclosure(self, kwargs: dict[str, Any]) -> str:
        api_key = self._check_api_key()
        if not api_key:
            return self._key_msg()

        company = kwargs.get("company", "")
        corp_code = ""
        if company:
            corp_code = await self._resolve_corp_code(api_key, company)

        page_count = int(kwargs.get("count", 10))

        params: dict[str, Any] = {
            "crtfc_key": api_key,
            "page_count": page_count,
            "sort": "date",
            "sort_mth": "desc",
        }
        if corp_code:
            params["corp_code"] = corp_code

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{DART_BASE}/list.json", params=params, timeout=15,
                )
        except httpx.HTTPError as e:
            return f"DART API 호출 실패: {e}"

        data = resp.json()
        if data.get("status") != "000":
            return f"DART 오류: {data.get('message', '')}"

        items = data.get("list", [])
        if not items:
            return "최신 공시가 없습니다."

        target = f" ({company})" if company else ""
        lines = [f"### 최신 공시 목록{target}"]
        for i, item in enumerate(items, 1):
            lines.append(
                f"  [{i}] {item.get('report_nm', '')}\n"
                f"      기업: {item.get('corp_name', '')} | "
                f"날짜: {item.get('rcept_dt', '')} | "
                f"유형: {item.get('corp_cls', '')}"
            )

        return "\n".join(lines)

    # ── 기업코드 변환 ──

    async def _resolve_corp_code(self, api_key: str, company_name: str) -> str:
        """기업명 → DART corp_code 변환. 캐시 파일 활용."""
        # 캐시 로드
        if DartApiTool._corp_codes is None:
            DartApiTool._corp_codes = await self._load_or_download_corp_codes(api_key)

        if not DartApiTool._corp_codes:
            return ""

        # 정확 매칭
        if company_name in DartApiTool._corp_codes:
            return DartApiTool._corp_codes[company_name]

        # 부분 매칭
        for name, code in DartApiTool._corp_codes.items():
            if company_name in name or name in company_name:
                return code

        return ""

    async def _load_or_download_corp_codes(self, api_key: str) -> dict[str, str]:
        """캐시 파일이 있으면 로드, 없으면 DART에서 다운로드."""
        # 캐시 파일 확인
        if CORP_CODE_CACHE.exists():
            try:
                with open(CORP_CODE_CACHE) as f:
                    return json.load(f)
            except Exception:
                pass

        # DART에서 기업코드 ZIP 다운로드
        logger.info("[DART] 기업코드 목록 다운로드 중...")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{DART_BASE}/corpCode.xml",
                    params={"crtfc_key": api_key},
                    timeout=30,
                )
        except httpx.HTTPError as e:
            logger.error("[DART] 기업코드 다운로드 실패: %s", e)
            return {}

        if resp.status_code != 200:
            logger.error("[DART] 기업코드 HTTP %d", resp.status_code)
            return {}

        # ZIP 해제 → XML 파싱
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

            # 캐시 저장
            CORP_CODE_CACHE.parent.mkdir(parents=True, exist_ok=True)
            with open(CORP_CODE_CACHE, "w") as f:
                json.dump(codes, f, ensure_ascii=False)

            logger.info("[DART] 기업코드 %d개 캐싱 완료", len(codes))
            return codes

        except Exception as e:
            logger.error("[DART] 기업코드 파싱 실패: %s", e)
            return {}

    # ── 유틸 ──

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

    @staticmethod
    def _format_amount(value: str) -> str:
        """금액을 읽기 쉬운 형태로 변환 (억 원 단위)."""
        if not value or value == "-":
            return "-"
        try:
            num = int(value.replace(",", ""))
            if abs(num) >= 1_0000_0000:
                return f"{num / 1_0000_0000:,.0f}억원"
            elif abs(num) >= 1_0000:
                return f"{num / 1_0000:,.0f}만원"
            else:
                return f"{num:,}원"
        except ValueError:
            return value
