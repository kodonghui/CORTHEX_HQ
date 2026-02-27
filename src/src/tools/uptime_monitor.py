"""
웹사이트 상태 모니터 도구 (Uptime Monitor).

등록된 웹사이트가 정상 작동하는지 확인하고,
응답 속도를 측정하여 이력을 관리합니다.
다운된 사이트를 빠르게 감지하여 보고합니다.

사용 방법:
  - action="add": 모니터링 대상 추가 (url, name, expected_status)
  - action="remove": 대상 제거 (url)
  - action="check": 등록된 모든 사이트 상태 즉시 확인
  - action="list": 모니터링 목록 조회
  - action="history": 특정 사이트의 응답 시간 이력 (url, hours)

필요 환경변수: 없음
의존 라이브러리: httpx
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.uptime_monitor")

KST = timezone(timedelta(hours=9))

DATA_DIR = Path("data")  # 레거시 — 하위 호환용으로 보존
_WATCHLIST_KEY = "uptime_watchlist"
_HISTORY_KEY = "uptime_history"

# 응답 느림 경고 기준 (초)
SLOW_THRESHOLD = 2.0
# 이력 최대 보관 건수 (사이트당)
MAX_HISTORY = 1000


class UptimeMonitorTool(BaseTool):
    """웹사이트 상태 모니터 도구 — 등록된 사이트의 가동 상태와 응답 속도를 측정합니다."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "check")

        if action == "add":
            return self._add_site(kwargs)
        elif action == "remove":
            return self._remove_site(kwargs)
        elif action == "check":
            return await self._check_all()
        elif action == "list":
            return self._list_sites()
        elif action == "history":
            return await self._show_history(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "add, remove, check, list, history 중 하나를 사용하세요."
            )

    # ── 데이터 로드/저장 헬퍼 (SQLite DB) ──

    def _load_watchlist(self) -> list[dict]:
        """감시 목록을 DB에서 로드합니다."""
        try:
            from web.db import load_setting
            result = load_setting(_WATCHLIST_KEY, None)
            if result is not None:
                return result
        except Exception:
            pass
        return []

    def _save_watchlist(self, watchlist: list[dict]) -> None:
        """감시 목록을 DB에 저장합니다."""
        try:
            from web.db import save_setting
            save_setting(_WATCHLIST_KEY, watchlist)
        except Exception as e:
            logger.warning("감시 목록 DB 저장 실패: %s", e)

    def _load_history(self) -> dict[str, list[dict]]:
        """응답 이력을 DB에서 로드합니다."""
        try:
            from web.db import load_setting
            result = load_setting(_HISTORY_KEY, None)
            if result is not None:
                return result
        except Exception:
            pass
        return {}

    def _save_history(self, history: dict[str, list[dict]]) -> None:
        """응답 이력을 DB에 저장합니다."""
        try:
            from web.db import save_setting
            save_setting(_HISTORY_KEY, history)
        except Exception as e:
            logger.warning("응답 이력 DB 저장 실패: %s", e)

    # ── action 구현 ──

    def _add_site(self, kwargs: dict[str, Any]) -> str:
        """모니터링 대상 사이트 추가."""
        url = kwargs.get("url", "").strip()
        name = kwargs.get("name", url)
        expected_status = int(kwargs.get("expected_status", 200))

        if not url:
            return "url 파라미터가 필요합니다. 예: url='https://corthex.com'"

        watchlist = self._load_watchlist()
        for site in watchlist:
            if site["url"] == url:
                return f"이미 등록된 URL입니다: {url}"

        watchlist.append({
            "url": url,
            "name": name,
            "expected_status": expected_status,
            "added_at": datetime.now(KST).isoformat(),
        })
        self._save_watchlist(watchlist)
        logger.info("모니터링 대상 추가: %s (%s)", name, url)
        return f"✅ 모니터링 대상 추가 완료: {name} ({url})\n기대 상태 코드: {expected_status}"

    def _remove_site(self, kwargs: dict[str, Any]) -> str:
        """모니터링 대상 사이트 제거."""
        url = kwargs.get("url", "").strip()
        if not url:
            return "url 파라미터가 필요합니다."

        watchlist = self._load_watchlist()
        new_list = [s for s in watchlist if s["url"] != url]
        if len(new_list) == len(watchlist):
            return f"등록되지 않은 URL입니다: {url}"

        self._save_watchlist(new_list)
        logger.info("모니터링 대상 제거: %s", url)
        return f"✅ 모니터링 대상에서 제거했습니다: {url}"

    async def _check_all(self) -> str:
        """등록된 모든 사이트의 상태를 즉시 확인합니다."""
        watchlist = self._load_watchlist()
        if not watchlist:
            return "모니터링 대상이 없습니다. action='add'로 사이트를 먼저 추가하세요."

        history = self._load_history()
        now = datetime.now(KST).isoformat()
        results: list[str] = []
        ok_count = 0
        fail_count = 0

        async with httpx.AsyncClient() as client:
            for site in watchlist:
                url = site["url"]
                name = site["name"]
                expected = site.get("expected_status", 200)

                record: dict[str, Any] = {"timestamp": now}
                start = time.time()
                try:
                    resp = await client.head(url, timeout=10, follow_redirects=True)
                    elapsed = time.time() - start
                    elapsed_ms = round(elapsed * 1000)
                    status = resp.status_code
                    record.update({
                        "status": status,
                        "response_ms": elapsed_ms,
                        "ok": status == expected,
                    })

                    if status != expected:
                        results.append(
                            f"❌ {name} — {status} (기대: {expected}) "
                            f"(응답: {elapsed:.2f}초)"
                        )
                        fail_count += 1
                    elif elapsed >= SLOW_THRESHOLD:
                        results.append(
                            f"⚠️ {name} — {status} OK "
                            f"(응답: {elapsed:.2f}초, 느림 경고)"
                        )
                        ok_count += 1
                    else:
                        results.append(
                            f"✅ {name} — {status} OK (응답: {elapsed:.2f}초)"
                        )
                        ok_count += 1

                except Exception as exc:
                    record.update({
                        "status": None,
                        "response_ms": None,
                        "ok": False,
                        "error": str(exc),
                    })
                    results.append(f"❌ {name} — 연결 실패 ({exc})")
                    fail_count += 1

                # 이력 기록
                if url not in history:
                    history[url] = []
                history[url].append(record)
                # 최대 건수 유지
                if len(history[url]) > MAX_HISTORY:
                    history[url] = history[url][-MAX_HISTORY:]

        self._save_history(history)

        header = f"## 웹사이트 상태 확인 결과\n확인 시각: {now}\n총 {len(watchlist)}개 | ✅ {ok_count}개 정상 | ❌ {fail_count}개 이상\n"
        return header + "\n".join(results)

    def _list_sites(self) -> str:
        """등록된 모니터링 목록 조회."""
        watchlist = self._load_watchlist()
        if not watchlist:
            return "등록된 모니터링 대상이 없습니다."

        lines = [f"## 모니터링 목록 (총 {len(watchlist)}개)"]
        for i, site in enumerate(watchlist, 1):
            lines.append(
                f"{i}. **{site['name']}**\n"
                f"   URL: {site['url']}\n"
                f"   기대 상태: {site.get('expected_status', 200)}\n"
                f"   등록일: {site.get('added_at', '알 수 없음')}"
            )
        return "\n".join(lines)

    async def _show_history(self, kwargs: dict[str, Any]) -> str:
        """특정 사이트의 응답 시간 이력 분석."""
        url = kwargs.get("url", "").strip()
        hours = int(kwargs.get("hours", 24))

        if not url:
            return "url 파라미터가 필요합니다."

        history = self._load_history()
        records = history.get(url, [])
        if not records:
            return f"'{url}'에 대한 이력이 없습니다."

        # 최근 N시간 필터
        cutoff = datetime.now(KST) - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()
        filtered = [r for r in records if r.get("timestamp", "") >= cutoff_str]

        if not filtered:
            return f"최근 {hours}시간 내 '{url}' 이력이 없습니다."

        # 통계 계산
        response_times = [
            r["response_ms"] for r in filtered
            if r.get("response_ms") is not None
        ]
        ok_count = sum(1 for r in filtered if r.get("ok"))
        total = len(filtered)
        uptime_pct = round((ok_count / total) * 100, 1) if total else 0

        stats_lines = [
            f"## {url} — 최근 {hours}시간 이력",
            f"- 총 확인 횟수: {total}건",
            f"- 가용률: {uptime_pct}%",
        ]

        if response_times:
            avg_ms = round(sum(response_times) / len(response_times))
            min_ms = min(response_times)
            max_ms = max(response_times)
            stats_lines.extend([
                f"- 평균 응답시간: {avg_ms}ms",
                f"- 최소 응답시간: {min_ms}ms",
                f"- 최대 응답시간: {max_ms}ms",
            ])

        # 다운타임 구간 계산
        down_periods = [r for r in filtered if not r.get("ok")]
        if down_periods:
            stats_lines.append(f"- 장애 발생 횟수: {len(down_periods)}건")
            latest_down = down_periods[-1]
            stats_lines.append(
                f"- 마지막 장애: {latest_down.get('timestamp', '')} "
                f"(에러: {latest_down.get('error', latest_down.get('status', '알 수 없음'))})"
            )

        return "\n".join(stats_lines)
