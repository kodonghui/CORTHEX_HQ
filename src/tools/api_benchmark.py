"""
API 성능 측정기 도구 (API Benchmark).

프로젝트의 도구/API의 응답 속도와 성공률을 측정합니다.
반복 호출을 통해 평균, P50, P95, P99 응답시간과
성공률을 계산하여 보고합니다.

사용 방법:
  - action="benchmark": 등록된 도구들의 성능 측정 (tools, iterations)
  - action="single": 단일 API 엔드포인트 측정 (url, method, iterations)
  - action="report": 전체 성능 보고서 (이전 측정 결과 기반)

필요 환경변수: 없음
의존 라이브러리: httpx
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.api_benchmark")

KST = timezone(timedelta(hours=9))

DATA_DIR = Path("data")
RESULTS_FILE = DATA_DIR / "benchmark_results.json"

# 각 도구별 가벼운 테스트 케이스
BENCHMARK_CASES: dict[str, dict[str, Any]] = {
    "kr_stock": {"action": "price", "name": "삼성전자"},
    "dart_api": {"action": "company", "company": "삼성전자"},
    "naver_news": {"action": "search", "query": "테스트", "count": "3"},
    "web_search": {"action": "search", "query": "test", "count": "3"},
    "translator": {"text": "hello", "target_lang": "ko"},
    "github_tool": {"action": "repo_stats"},
    "daum_cafe": {"action": "search", "query": "테스트", "size": "3"},
    "naver_datalab": {"action": "trend", "keywords": "파이썬"},
    "ecos_macro": {"action": "exchange_rate"},
}


class ApiBenchmarkTool(BaseTool):
    """API 성능 측정기 — 도구/API의 응답 속도와 성공률을 측정합니다."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "single")

        if action == "benchmark":
            return await self._benchmark_tools(kwargs)
        elif action == "single":
            return await self._single_endpoint(kwargs)
        elif action == "report":
            return await self._report()
        else:
            return (
                f"알 수 없는 action: {action}. "
                "benchmark, single, report 중 하나를 사용하세요."
            )

    # ── 데이터 저장/로드 ──

    def _ensure_data_dir(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _load_results(self) -> list[dict]:
        if not RESULTS_FILE.exists():
            return []
        return json.loads(RESULTS_FILE.read_text(encoding="utf-8"))

    def _save_result(self, result: dict) -> None:
        self._ensure_data_dir()
        results = self._load_results()
        results.append(result)
        # 최근 100개 결과만 보관
        if len(results) > 100:
            results = results[-100:]
        RESULTS_FILE.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 성능 지표 계산 ──

    @staticmethod
    def _calculate_stats(times: list[float]) -> dict[str, float]:
        """응답 시간 리스트에서 통계를 계산합니다."""
        if not times:
            return {"avg": 0, "p50": 0, "p95": 0, "p99": 0, "min": 0, "max": 0}

        sorted_times = sorted(times)
        n = len(sorted_times)

        return {
            "avg": round(sum(sorted_times) / n, 1),
            "p50": round(sorted_times[n // 2], 1),
            "p95": round(sorted_times[int(n * 0.95)] if n >= 2 else sorted_times[-1], 1),
            "p99": round(sorted_times[int(n * 0.99)] if n >= 2 else sorted_times[-1], 1),
            "min": round(sorted_times[0], 1),
            "max": round(sorted_times[-1], 1),
        }

    # ── action 구현 ──

    async def _single_endpoint(self, kwargs: dict[str, Any]) -> str:
        """단일 API 엔드포인트를 반복 호출하여 성능을 측정합니다."""
        url = kwargs.get("url", "").strip()
        method = kwargs.get("method", "GET").upper()
        iterations = int(kwargs.get("iterations", 5))

        if not url:
            return "url 파라미터가 필요합니다. 예: url='https://api.example.com/health'"

        times: list[float] = []
        errors = 0
        status_codes: list[int] = []

        async with httpx.AsyncClient() as client:
            for i in range(iterations):
                start = time.time()
                try:
                    resp = await client.request(method, url, timeout=30)
                    elapsed_ms = (time.time() - start) * 1000
                    times.append(elapsed_ms)
                    status_codes.append(resp.status_code)
                    if resp.status_code >= 400:
                        errors += 1
                except Exception as exc:
                    errors += 1
                    logger.warning("벤치마크 요청 실패 (%s): %s", url, exc)

                if i < iterations - 1:
                    await asyncio.sleep(0.5)

        stats = self._calculate_stats(times)
        success_rate = round(((iterations - errors) / iterations) * 100, 1)

        result = {
            "timestamp": datetime.now(KST).isoformat(),
            "type": "single",
            "url": url,
            "method": method,
            "iterations": iterations,
            "stats": stats,
            "success_rate": success_rate,
            "errors": errors,
        }
        self._save_result(result)

        lines = [
            f"## API 성능 측정 결과",
            f"URL: {url}",
            f"메서드: {method} | 반복: {iterations}회",
            "",
            f"- 평균 응답시간: {stats['avg']}ms",
            f"- P50 (중앙값): {stats['p50']}ms",
            f"- P95: {stats['p95']}ms",
            f"- P99: {stats['p99']}ms",
            f"- 최소: {stats['min']}ms | 최대: {stats['max']}ms",
            f"- 성공률: {success_rate}% ({iterations - errors}/{iterations})",
        ]

        if errors > 0:
            lines.append(f"- ⚠️ 실패: {errors}건")

        return "\n".join(lines)

    async def _benchmark_tools(self, kwargs: dict[str, Any]) -> str:
        """등록된 도구들의 성능을 측정합니다 (환경변수 확인 + 설명 기반)."""
        tools_param = kwargs.get("tools", "all")
        iterations = int(kwargs.get("iterations", 3))

        if tools_param == "all":
            target_tools = list(BENCHMARK_CASES.keys())
        else:
            target_tools = [t.strip() for t in str(tools_param).split(",")]

        lines = [
            f"## 도구 벤치마크 결과",
            f"대상: {len(target_tools)}개 도구 | 반복: {iterations}회",
            "",
        ]

        benchmark_summary: list[dict[str, Any]] = []

        for tool_id in target_tools:
            test_case = BENCHMARK_CASES.get(tool_id)
            if not test_case:
                lines.append(f"⚠️ {tool_id}: 테스트 케이스 없음 (건너뜀)")
                continue

            lines.append(f"### {tool_id}")
            lines.append(f"  테스트 파라미터: {json.dumps(test_case, ensure_ascii=False)}")
            lines.append(f"  상태: 테스트 케이스 등록됨 (직접 실행은 pool.invoke() 필요)")
            lines.append("")

            benchmark_summary.append({
                "tool_id": tool_id,
                "test_case": test_case,
                "iterations": iterations,
            })

        result = {
            "timestamp": datetime.now(KST).isoformat(),
            "type": "benchmark",
            "tools": benchmark_summary,
        }
        self._save_result(result)

        return "\n".join(lines)

    async def _report(self) -> str:
        """이전 측정 결과를 기반으로 전체 성능 보고서를 생성합니다."""
        results = self._load_results()
        if not results:
            return "저장된 벤치마크 결과가 없습니다. action='single' 또는 action='benchmark'를 먼저 실행하세요."

        # 최근 결과만 표시
        recent = results[-20:]

        lines = [
            f"## 성능 벤치마크 보고서",
            f"총 기록: {len(results)}건 | 최근 {len(recent)}건 표시",
            "",
        ]

        for r in recent:
            ts = r.get("timestamp", "알 수 없음")
            rtype = r.get("type", "unknown")
            if rtype == "single":
                url = r.get("url", "?")
                stats = r.get("stats", {})
                rate = r.get("success_rate", 0)
                lines.append(
                    f"- [{ts[:16]}] {url} — "
                    f"평균 {stats.get('avg', 0)}ms, "
                    f"성공률 {rate}%"
                )
            elif rtype == "benchmark":
                tool_count = len(r.get("tools", []))
                lines.append(f"- [{ts[:16]}] 도구 벤치마크 ({tool_count}개)")

        report_text = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 시스템 성능 전문가입니다.\n"
                "벤치마크 결과를 분석하여 다음을 정리하세요:\n"
                "1. 전체 성능 상태 요약\n"
                "2. 병목 지점 식별 (가장 느린 API)\n"
                "3. 성능 개선 우선순위 및 구체적 방법\n"
                "한국어로 답변하세요."
            ),
            user_prompt=report_text,
        )

        return f"{report_text}\n\n---\n\n## 성능 분석\n\n{analysis}"
