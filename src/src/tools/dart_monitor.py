"""
공시 알리미 Tool (DART Monitor).

금융감독원 전자공시시스템(DART) OpenAPI를 사용하여
관심 기업의 새 공시를 자동으로 감지하고 알림합니다.

사용 방법:
  - action="watch": 관심 기업 등록 (company 파라미터)
  - action="unwatch": 관심 기업 해제 (company 파라미터)
  - action="check": 등록된 모든 관심 기업의 새 공시 확인
  - action="list": 현재 감시 중인 기업 목록 조회

필요 환경변수:
  - DART_API_KEY: 금융감독원 DART (https://opendart.fss.or.kr/) 무료 발급
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.dart_monitor")

DART_BASE = "https://opendart.fss.or.kr/api"
WATCHLIST_PATH = Path("data/dart_watchlist.json")  # 레거시 — 마이그레이션용
LAST_CHECK_PATH = Path("data/dart_last_check.json")  # 레거시
CORP_CODE_CACHE = Path("data/dart_corp_codes.json")  # 기업코드 캐시 (대량 데이터, JSON 유지)
_WATCHLIST_KEY = "dart_watchlist"
_LAST_CHECK_KEY = "dart_last_check"


class DartMonitorTool(BaseTool):
    """DART 공시 감시 및 알림 도구."""

    _corp_codes: dict[str, str] | None = None  # 기업명 → corp_code 매핑 캐시

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "check")

        if action == "watch":
            return await self._watch(kwargs)
        elif action == "unwatch":
            return await self._unwatch(kwargs)
        elif action == "check":
            return await self._check(kwargs)
        elif action == "list":
            return self._list_watchlist()
        else:
            return (
                f"알 수 없는 action: {action}. "
                "watch, unwatch, check, list 중 하나를 사용하세요."
            )

    # ── 관심 기업 등록 ──

    async def _watch(self, kwargs: dict[str, Any]) -> str:
        company = kwargs.get("company", "")
        if not company:
            return "기업명(company)을 입력해주세요. 예: company='삼성전자'"

        api_key = self._check_api_key()
        if not api_key:
            return self._key_msg()

        # 기업코드 확인
        corp_code = await self._resolve_corp_code(api_key, company)
        if not corp_code:
            return f"'{company}'에 해당하는 기업을 DART에서 찾을 수 없습니다."

        watchlist = self._load_watchlist()

        if company in watchlist:
            return f"'{company}'는 이미 감시 목록에 있습니다."

        watchlist[company] = {
            "corp_code": corp_code,
            "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._save_watchlist(watchlist)

        return f"'{company}' (코드: {corp_code})를 감시 목록에 추가했습니다. 현재 {len(watchlist)}개 기업 감시 중."

    # ── 관심 기업 해제 ──

    async def _unwatch(self, kwargs: dict[str, Any]) -> str:
        company = kwargs.get("company", "")
        if not company:
            return "기업명(company)을 입력해주세요."

        watchlist = self._load_watchlist()

        if company not in watchlist:
            # 부분 매칭 시도
            matched = [k for k in watchlist if company in k or k in company]
            if matched:
                company = matched[0]
            else:
                return f"'{company}'는 감시 목록에 없습니다."

        del watchlist[company]
        self._save_watchlist(watchlist)

        return f"'{company}'를 감시 목록에서 제거했습니다. 현재 {len(watchlist)}개 기업 감시 중."

    # ── 새 공시 확인 ──

    async def _check(self, kwargs: dict[str, Any]) -> str:
        api_key = self._check_api_key()
        if not api_key:
            return self._key_msg()

        watchlist = self._load_watchlist()
        if not watchlist:
            return "감시 중인 기업이 없습니다. action='watch', company='기업명'으로 먼저 등록하세요."

        last_check = self._load_last_check()
        now = datetime.now()
        all_new_disclosures: list[str] = []
        raw_disclosures: list[str] = []

        for company, info in watchlist.items():
            corp_code = info["corp_code"]
            last_dt = last_check.get(company, "")

            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{DART_BASE}/list.json",
                        params={
                            "crtfc_key": api_key,
                            "corp_code": corp_code,
                            "page_count": 10,
                            "sort": "date",
                            "sort_mth": "desc",
                        },
                        timeout=15,
                    )
            except httpx.HTTPError as e:
                all_new_disclosures.append(f"  [{company}] API 호출 실패: {e}")
                continue

            if resp.status_code != 200:
                all_new_disclosures.append(f"  [{company}] HTTP 오류: {resp.status_code}")
                continue

            data = resp.json()
            if data.get("status") != "000":
                all_new_disclosures.append(f"  [{company}] DART 오류: {data.get('message', '')}")
                continue

            items = data.get("list", [])
            new_items = []
            for item in items:
                rcept_dt = item.get("rcept_dt", "")
                if last_dt and rcept_dt <= last_dt:
                    break
                new_items.append(item)

            if new_items:
                all_new_disclosures.append(f"\n  ### {company} — 새 공시 {len(new_items)}건")
                for i, item in enumerate(new_items, 1):
                    report_nm = item.get("report_nm", "")
                    rcept_dt = item.get("rcept_dt", "")
                    all_new_disclosures.append(
                        f"    [{i}] {report_nm} ({rcept_dt})"
                    )
                    raw_disclosures.append(f"{company}: {report_nm} ({rcept_dt})")
            else:
                all_new_disclosures.append(f"  [{company}] 새 공시 없음")

            # 마지막 확인 시각 업데이트
            if items:
                last_check[company] = items[0].get("rcept_dt", "")

        # 마지막 확인 저장
        self._save_last_check(last_check)

        header = f"## 공시 알리미 — 확인 시각: {now.strftime('%Y-%m-%d %H:%M')}"
        body = "\n".join(all_new_disclosures)

        # 새 공시가 있으면 LLM 분석 추가
        if raw_disclosures:
            analysis = await self._llm_call(
                system_prompt=(
                    "당신은 공시 분석 전문가입니다.\n"
                    "아래 새로운 공시 목록을 분석하여 다음을 정리하세요:\n"
                    "1. 각 공시의 핵심 내용 (공시 제목으로 유형 판단)\n"
                    "2. 주가에 미칠 수 있는 영향 (호재/악재/중립)\n"
                    "3. 투자자가 주목해야 할 공시 우선순위\n"
                    "한국어로 간결하게 답변하세요."
                ),
                user_prompt="\n".join(raw_disclosures),
            )
            return f"{header}\n\n{body}\n\n---\n\n## 공시 영향 분석\n\n{analysis}"

        return f"{header}\n\n{body}"

    # ── 감시 목록 조회 ──

    def _list_watchlist(self) -> str:
        watchlist = self._load_watchlist()
        if not watchlist:
            return "감시 중인 기업이 없습니다. action='watch', company='기업명'으로 등록하세요."

        lines = [f"### 공시 감시 목록 ({len(watchlist)}개 기업)"]
        for i, (company, info) in enumerate(watchlist.items(), 1):
            lines.append(
                f"  {i}. {company} (코드: {info['corp_code']}, "
                f"등록일: {info.get('added_at', '-')})"
            )
        return "\n".join(lines)

    # ── 기업코드 변환 (DartApiTool 로직 재사용) ──

    async def _resolve_corp_code(self, api_key: str, company_name: str) -> str:
        """기업명 → DART corp_code 변환. 캐시 파일 활용."""
        if DartMonitorTool._corp_codes is None:
            DartMonitorTool._corp_codes = self._load_corp_codes_cache()

        if not DartMonitorTool._corp_codes:
            # 캐시가 없으면 DART API에서 다운로드 시도
            DartMonitorTool._corp_codes = await self._download_corp_codes(api_key)

        if not DartMonitorTool._corp_codes:
            return ""

        # 정확 매칭
        if company_name in DartMonitorTool._corp_codes:
            return DartMonitorTool._corp_codes[company_name]

        # 부분 매칭
        for name, code in DartMonitorTool._corp_codes.items():
            if company_name in name or name in company_name:
                return code

        return ""

    def _load_corp_codes_cache(self) -> dict[str, str]:
        """data/dart_corp_codes.json 캐시 파일 로드."""
        if CORP_CODE_CACHE.exists():
            try:
                with open(CORP_CODE_CACHE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    async def _download_corp_codes(self, api_key: str) -> dict[str, str]:
        """DART에서 기업코드 ZIP 다운로드 후 캐시."""
        import io
        import zipfile
        from xml.etree import ElementTree

        logger.info("[DartMonitor] 기업코드 목록 다운로드 중...")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{DART_BASE}/corpCode.xml",
                    params={"crtfc_key": api_key},
                    timeout=30,
                )
        except httpx.HTTPError as e:
            logger.error("[DartMonitor] 기업코드 다운로드 실패: %s", e)
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

            logger.info("[DartMonitor] 기업코드 %d개 캐싱 완료", len(codes))
            return codes
        except Exception as e:
            logger.error("[DartMonitor] 기업코드 파싱 실패: %s", e)
            return {}

    # ── 파일 I/O 유틸 (SQLite DB) ──

    @staticmethod
    def _load_watchlist() -> dict[str, Any]:
        """감시 목록을 DB에서 로드합니다. DB에 없으면 레거시 JSON 마이그레이션."""
        try:
            from web.db import load_setting
            result = load_setting(_WATCHLIST_KEY, None)
            if result is not None:
                return result
        except Exception:
            pass
        # 레거시 JSON 마이그레이션
        if WATCHLIST_PATH.exists():
            try:
                with open(WATCHLIST_PATH) as f:
                    data = json.load(f)
                DartMonitorTool._save_watchlist(data)
                return data
            except Exception:
                pass
        return {}

    @staticmethod
    def _save_watchlist(watchlist: dict[str, Any]) -> None:
        """감시 목록을 DB에 저장합니다."""
        try:
            from web.db import save_setting
            save_setting(_WATCHLIST_KEY, watchlist)
        except Exception:
            pass

    @staticmethod
    def _load_last_check() -> dict[str, str]:
        """마지막 확인 시각을 DB에서 로드합니다."""
        try:
            from web.db import load_setting
            result = load_setting(_LAST_CHECK_KEY, None)
            if result is not None:
                return result
        except Exception:
            pass
        # 레거시 JSON 마이그레이션
        if LAST_CHECK_PATH.exists():
            try:
                with open(LAST_CHECK_PATH) as f:
                    data = json.load(f)
                DartMonitorTool._save_last_check(data)
                return data
            except Exception:
                pass
        return {}

    @staticmethod
    def _save_last_check(last_check: dict[str, str]) -> None:
        """마지막 확인 시각을 DB에 저장합니다."""
        try:
            from web.db import save_setting
            save_setting(_LAST_CHECK_KEY, last_check)
        except Exception:
            pass

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
