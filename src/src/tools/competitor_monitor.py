"""
경쟁사 웹사이트 변화 감지기 Tool.

경쟁사 웹사이트의 변경사항을 자동으로 감지하여 알려줍니다.
감시 대상 URL을 등록하면, 이전 스냅샷과 현재 상태를 비교하여
변경 여부를 판별하고 변경 내용의 사업적 의미를 분석합니다.

사용 방법:
  - action="add": 감시 대상 웹사이트 추가
  - action="remove": 감시 대상 해제
  - action="check": 등록된 모든 사이트 변경사항 확인
  - action="list": 현재 감시 중인 사이트 목록
  - action="diff": 특정 사이트의 이전/현재 차이점 상세 보기

필요 환경변수: 없음
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.competitor_monitor")

WATCHLIST_PATH = Path("data/competitor_watchlist.json")  # 레거시 — 마이그레이션용
SNAPSHOT_DIR = Path("data/competitor_snapshots")
_WATCHLIST_KEY = "competitor_watchlist"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class CompetitorMonitorTool(BaseTool):
    """경쟁사 웹사이트 변경사항 자동 감지 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "list")

        if action == "add":
            return await self._add_site(kwargs)
        elif action == "remove":
            return self._remove_site(kwargs)
        elif action == "check":
            return await self._check_all(kwargs)
        elif action == "list":
            return self._list_sites()
        elif action == "diff":
            return await self._show_diff(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "add, remove, check, list, diff 중 하나를 사용하세요."
            )

    # ── 내부: 감시 목록 관리 (SQLite DB) ──

    def _load_watchlist(self) -> list[dict]:
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
                data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
                self._save_watchlist(data)  # DB로 이전
                return data
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save_watchlist(self, watchlist: list[dict]) -> None:
        """감시 목록을 DB에 저장합니다."""
        try:
            from web.db import save_setting
            save_setting(_WATCHLIST_KEY, watchlist)
        except Exception as e:
            logger.warning("경쟁사 감시 목록 DB 저장 실패: %s", e)

    @staticmethod
    def _url_hash(url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()[:12]

    # ── action: add ──

    async def _add_site(self, kwargs: dict[str, Any]) -> str:
        url = kwargs.get("url", "").strip()
        name = kwargs.get("name", "").strip()
        selector = kwargs.get("selector", "").strip()

        if not url:
            return "감시할 URL을 입력해주세요. 예: url='https://www.megastudy.net'"
        if not name:
            return "경쟁사 이름(name)을 입력해주세요. 예: name='메가로스쿨'"

        watchlist = self._load_watchlist()

        # 이미 등록되어 있는지 확인
        for item in watchlist:
            if item["url"] == url:
                return f"이미 감시 중인 URL입니다: {url} ({item['name']})"

        # 초기 스냅샷 저장
        text = await self._fetch_page_text(url, selector)
        if text is None:
            return f"URL에 접근할 수 없습니다: {url}\nURL이 올바른지 확인해주세요."

        text_hash = hashlib.md5(text.encode()).hexdigest()
        now = datetime.now().isoformat()

        # 스냅샷 파일 저장
        self._save_snapshot(url, text, now)

        entry = {
            "url": url,
            "name": name,
            "selector": selector,
            "last_hash": text_hash,
            "last_check": now,
            "last_text": text[:5000],
        }
        watchlist.append(entry)
        self._save_watchlist(watchlist)

        return (
            f"## 감시 대상 추가 완료\n\n"
            f"- **경쟁사**: {name}\n"
            f"- **URL**: {url}\n"
            f"- **감시 영역**: {selector if selector else '전체 페이지'}\n"
            f"- **등록 시각**: {now[:19]}\n"
            f"- **초기 스냅샷**: 저장 완료 (텍스트 {len(text)}자)"
        )

    # ── action: remove ──

    def _remove_site(self, kwargs: dict[str, Any]) -> str:
        url = kwargs.get("url", "").strip()
        if not url:
            return "해제할 URL을 입력해주세요."

        watchlist = self._load_watchlist()
        new_list = [item for item in watchlist if item["url"] != url]

        if len(new_list) == len(watchlist):
            return f"감시 목록에 없는 URL입니다: {url}"

        self._save_watchlist(new_list)
        return f"감시 해제 완료: {url}"

    # ── action: list ──

    def _list_sites(self) -> str:
        watchlist = self._load_watchlist()
        if not watchlist:
            return (
                "현재 감시 중인 사이트가 없습니다.\n"
                "action='add'로 감시 대상을 추가하세요."
            )

        lines = ["## 현재 감시 중인 사이트 목록\n"]
        for i, item in enumerate(watchlist, 1):
            selector_info = item.get("selector") or "전체 페이지"
            last_check = item.get("last_check", "")[:19]
            lines.append(
                f"**{i}. {item['name']}**\n"
                f"   - URL: {item['url']}\n"
                f"   - 감시 영역: {selector_info}\n"
                f"   - 마지막 확인: {last_check}"
            )

        lines.append(f"\n총 {len(watchlist)}개 사이트 감시 중")
        return "\n\n".join(lines)

    # ── action: check ──

    async def _check_all(self, kwargs: dict[str, Any]) -> str:
        watchlist = self._load_watchlist()
        if not watchlist:
            return "감시 중인 사이트가 없습니다. action='add'로 추가하세요."

        results = []
        changed_count = 0

        for item in watchlist:
            url = item["url"]
            name = item["name"]
            selector = item.get("selector", "")
            old_hash = item.get("last_hash", "")

            text = await self._fetch_page_text(url, selector)
            if text is None:
                results.append(f"- **{name}**: ⚠ 접근 실패 ({url})")
                continue

            new_hash = hashlib.md5(text.encode()).hexdigest()
            now = datetime.now().isoformat()

            if new_hash != old_hash:
                changed_count += 1
                results.append(f"- **{name}**: 🔴 변경 감지! ({url})")

                # 스냅샷 저장 + 감시 목록 갱신
                self._save_snapshot(url, text, now)
                item["last_hash"] = new_hash
                item["last_check"] = now
                item["last_text"] = text[:5000]
            else:
                results.append(f"- **{name}**: 변경 없음 ({url})")
                item["last_check"] = now

        self._save_watchlist(watchlist)

        summary = (
            f"## 경쟁사 웹사이트 변경 감지 결과\n\n"
            f"확인 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"감시 대상: {len(watchlist)}개 | 변경 감지: {changed_count}개\n\n"
            + "\n".join(results)
        )

        # 변경이 있으면 LLM 분석
        if changed_count > 0:
            analysis = await self._llm_call(
                system_prompt=(
                    "당신은 경쟁사 분석 전문가입니다.\n"
                    "경쟁사 웹사이트의 변경 감지 결과를 분석하여 다음을 정리하세요:\n"
                    "1. 어떤 변경이 사업적으로 의미 있는지\n"
                    "2. 경쟁사의 전략 변화 가능성\n"
                    "3. 우리가 대응해야 할 사항\n"
                    "한국어로 간결하게 보고하세요."
                ),
                user_prompt=summary,
            )
            summary += f"\n\n---\n\n## 분석\n\n{analysis}"

        return summary

    # ── action: diff ──

    async def _show_diff(self, kwargs: dict[str, Any]) -> str:
        url = kwargs.get("url", "").strip()
        if not url:
            return "비교할 사이트 URL을 입력해주세요."

        watchlist = self._load_watchlist()
        entry = next((item for item in watchlist if item["url"] == url), None)
        if not entry:
            return f"감시 목록에 없는 URL입니다: {url}"

        selector = entry.get("selector", "")
        old_text = entry.get("last_text", "")

        # 현재 페이지 가져오기
        new_text = await self._fetch_page_text(url, selector)
        if new_text is None:
            return f"현재 페이지에 접근할 수 없습니다: {url}"

        if not old_text:
            return "이전 스냅샷이 없습니다. action='check'를 먼저 실행하세요."

        # difflib로 차이점 생성
        import difflib

        old_lines = old_text.splitlines()
        new_lines = new_text[:5000].splitlines()

        diff = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile="이전 버전",
            tofile="현재 버전",
            lineterm="",
        ))

        if not diff:
            return f"**{entry['name']}**: 이전 스냅샷과 동일합니다. 변경 사항 없음."

        diff_text = "\n".join(diff[:200])  # 최대 200줄

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 경쟁사 분석 전문가입니다.\n"
                "웹사이트의 이전/현재 차이점(diff)을 분석하여 다음을 정리하세요:\n"
                "1. 주요 변경 내용 요약\n"
                "2. 변경의 사업적 의미 (가격 변동, 신제품, 이벤트 등)\n"
                "3. 대응 전략 제안\n"
                "한국어로 간결하게 보고하세요."
            ),
            user_prompt=(
                f"경쟁사: {entry['name']}\n"
                f"URL: {url}\n\n"
                f"변경 내역 (diff):\n```\n{diff_text}\n```"
            ),
        )

        return (
            f"## {entry['name']} 변경 상세 비교\n\n"
            f"URL: {url}\n\n"
            f"### 변경 내역 (diff)\n```\n{diff_text}\n```\n\n"
            f"---\n\n### 분석\n\n{analysis}"
        )

    # ── 유틸: 페이지 텍스트 가져오기 ──

    async def _fetch_page_text(self, url: str, selector: str = "") -> str | None:
        """URL의 텍스트를 가져온다. 실패하면 None 반환."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("beautifulsoup4가 설치되지 않음")
            return None

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=20,
                )
                if resp.status_code != 200:
                    logger.warning("HTTP %d: %s", resp.status_code, url)
                    return None
        except httpx.HTTPError as e:
            logger.warning("HTTP 오류: %s — %s", url, e)
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # script, style 제거
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        if selector:
            target = soup.select_one(selector)
            if target:
                text = target.get_text(separator="\n", strip=True)
            else:
                text = soup.body.get_text(separator="\n", strip=True) if soup.body else ""
        else:
            text = soup.body.get_text(separator="\n", strip=True) if soup.body else ""

        # 공백 정리
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    # ── 유틸: 스냅샷 저장 ──

    def _save_snapshot(self, url: str, text: str, timestamp: str) -> None:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        url_h = self._url_hash(url)
        ts = timestamp.replace(":", "").replace("-", "")[:15]
        filename = f"{url_h}_{ts}.txt"
        filepath = SNAPSHOT_DIR / filename
        filepath.write_text(text[:10000], encoding="utf-8")
        logger.debug("스냅샷 저장: %s", filepath)
