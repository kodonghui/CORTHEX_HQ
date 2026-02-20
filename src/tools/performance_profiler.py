"""
성능 프로파일링 도구 (Performance Profiler) -- 시스템 성능을 학술적 프레임워크로 분석합니다.

USE Method(Utilization/Saturation/Errors), Big-O 복잡도, Amdahl의 법칙,
Universal Scalability Law, Jeff Dean 레이턴시 모델을 적용하여 성능을 종합 진단합니다.

학술 근거:
  - Brendan Gregg, "Systems Performance" (2nd ed., 2020) -- USE Method
  - Donald Knuth, "The Art of Computer Programming" (1968-2011) -- 알고리즘 복잡도
  - Neil J. Gunther, "Guerrilla Capacity Planning" (2007) -- Universal Scalability Law
  - Jeff Dean, "Numbers Every Programmer Should Know" (2009) -- 레이턴시 벤치마크
  - Gene Amdahl, "Validity of the single processor approach..." (1967) -- Amdahl's Law

사용 방법:
  - action="analyze"     : 성능 종합 분석 (USE Method)
  - action="complexity"  : 알고리즘 복잡도 분석 (Big-O)
  - action="bottleneck"  : 병목 지점 탐지 (Amdahl의 법칙)
  - action="memory"      : 메모리 사용 패턴 분석 (힙/스택/GC)
  - action="scalability" : 확장성 분석 (USL)
  - action="database"    : DB 성능 분석 (쿼리 최적화, 인덱스, N+1)
  - action="api"         : API 지연시간 분석 (P50/P95/P99)
  - action="optimize"    : 최적화 제안 (CPU/메모리/IO/네트워크)
  - action="full"        : 전체 종합 (병렬 실행)

필요 환경변수: 없음 (AI 분석 기반)
필요 라이브러리: 없음 (표준 라이브러리만 사용)
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.performance_profiler")

# ─── Big-O 시간복잡도 레퍼런스 (Knuth TAOCP 기준) ─────────────────

_BIGO_REFERENCE: dict[str, dict] = {
    "O(1)":      {"name": "상수 시간",     "example": "해시맵 조회",           "n_100": "1",             "n_10k": "1",             "n_1m": "1",           "verdict": "최적"},
    "O(log n)":  {"name": "로그 시간",     "example": "이진 탐색, B-Tree",     "n_100": "7",             "n_10k": "14",            "n_1m": "20",          "verdict": "우수"},
    "O(n)":      {"name": "선형 시간",     "example": "배열 순회",             "n_100": "100",           "n_10k": "10,000",        "n_1m": "1,000,000",   "verdict": "양호"},
    "O(n log n)":{"name": "선형로그",      "example": "병합정렬, 팀소트",       "n_100": "664",           "n_10k": "132,877",       "n_1m": "19,931,568",  "verdict": "양호"},
    "O(n^2)":    {"name": "이차 시간",     "example": "중첩 루프, 버블정렬",    "n_100": "10,000",        "n_10k": "100,000,000",   "n_1m": "10^12",       "verdict": "주의"},
    "O(n^3)":    {"name": "삼차 시간",     "example": "행렬곱(naive)",          "n_100": "1,000,000",     "n_10k": "10^12",         "n_1m": "10^18",       "verdict": "위험"},
    "O(2^n)":    {"name": "지수 시간",     "example": "부분집합 열거",          "n_100": "1.27x10^30",    "n_10k": "불가능",        "n_1m": "불가능",      "verdict": "위험"},
    "O(n!)":     {"name": "팩토리얼",      "example": "순열 전수탐색",          "n_100": "9.33x10^157",   "n_10k": "불가능",        "n_1m": "불가능",      "verdict": "금지"},
}

# ─── Brendan Gregg USE Method 체크리스트 ──────────────────────────

_USE_METRICS: dict[str, dict] = {
    "CPU":     {"utilization": "CPU 사용률 -- top, mpstat",        "saturation": "런큐 길이 -- vmstat r",      "errors": "MCE 로그",          "tools": ["top","mpstat","perf"], "threshold_warn": 70, "threshold_critical": 90},
    "Memory":  {"utilization": "메모리 사용률 -- free -m",         "saturation": "스왑/OOM -- vmstat si/so",    "errors": "ECC/OOM -- dmesg",  "tools": ["free","vmstat","pmap"], "threshold_warn": 75, "threshold_critical": 90},
    "Disk_IO": {"utilization": "디스크 %util -- iostat",           "saturation": "대기큐 -- iostat avgqu-sz",   "errors": "smartctl 오류",     "tools": ["iostat","iotop","fio"], "threshold_warn": 60, "threshold_critical": 85},
    "Network": {"utilization": "대역폭 사용률 -- sar",             "saturation": "TCP 재전송 -- ss",            "errors": "ip -s link 에러",   "tools": ["sar","iftop","ss"],    "threshold_warn": 50, "threshold_critical": 80},
}

# ─── Jeff Dean 레이턴시 수치 (2023 업데이트 반영) ─────────────────

_LATENCY_TABLE: dict[str, dict] = {
    "L1_cache_ref":        {"latency_ns": 0.5,          "desc": "L1 캐시 참조",                "relative": "1x (기준)"},
    "branch_mispredict":   {"latency_ns": 5,            "desc": "분기 예측 실패",              "relative": "10x"},
    "L2_cache_ref":        {"latency_ns": 7,            "desc": "L2 캐시 참조",                "relative": "14x"},
    "mutex_lock":          {"latency_ns": 25,           "desc": "뮤텍스 잠금/해제",            "relative": "50x"},
    "main_memory_ref":     {"latency_ns": 100,          "desc": "메인 메모리(DRAM) 참조",      "relative": "200x"},
    "compress_1kb":        {"latency_ns": 3_000,        "desc": "1KB Snappy 압축",             "relative": "6,000x"},
    "send_1kb_1gbps":      {"latency_ns": 10_000,       "desc": "1Gbps로 1KB 전송",            "relative": "20,000x"},
    "read_4kb_ssd":        {"latency_ns": 150_000,      "desc": "SSD 4KB 랜덤 읽기",           "relative": "300,000x"},
    "read_1mb_memory":     {"latency_ns": 250_000,      "desc": "메모리 1MB 순차 읽기",        "relative": "500,000x"},
    "dc_roundtrip":        {"latency_ns": 500_000,      "desc": "데이터센터 내 왕복",          "relative": "1,000,000x"},
    "disk_seek":           {"latency_ns": 10_000_000,   "desc": "HDD 디스크 탐색",             "relative": "20,000,000x"},
    "read_1mb_disk":       {"latency_ns": 20_000_000,   "desc": "HDD 1MB 순차 읽기",           "relative": "40,000,000x"},
    "us_roundtrip":        {"latency_ns": 150_000_000,  "desc": "미국 대륙 횡단 왕복",         "relative": "300,000,000x"},
}

# ─── DB 안티패턴 (8가지) ──────────────────────────────────────────

_DB_ANTIPATTERNS: dict[str, dict] = {
    "N+1_query":           {"name": "N+1 쿼리",       "severity": "critical", "impact": "1+N번 DB 호출",             "fix": "JOIN/IN 절, eager loading"},
    "missing_index":       {"name": "인덱스 부재",     "severity": "critical", "impact": "Full Table Scan O(n)",      "fix": "EXPLAIN 후 복합 인덱스 추가"},
    "select_star":         {"name": "SELECT * 남용",   "severity": "high",     "impact": "불필요 I/O, 인덱스 무효",   "fix": "필요 컬럼만 명시 SELECT"},
    "no_pagination":       {"name": "페이지네이션 없음","severity": "high",     "impact": "메모리 폭증, OOM",          "fix": "커서 기반 페이지네이션"},
    "cartesian_join":      {"name": "카테시안 곱",     "severity": "critical", "impact": "M*N 행 생성",               "fix": "JOIN 조건 명시"},
    "implicit_conversion": {"name": "암시적 타입변환", "severity": "medium",   "impact": "인덱스 무효화",             "fix": "타입 일치"},
    "unbounded_query":     {"name": "무제한 쿼리",     "severity": "high",     "impact": "전체 스캔+메모리 폭증",     "fix": "WHERE+LIMIT 명시"},
    "over_normalization":  {"name": "과도한 정규화",   "severity": "medium",   "impact": "다중 JOIN 오버헤드",        "fix": "비정규화/materialized view"},
}


class PerformanceProfilerTool(BaseTool):
    """성능 프로파일링 도구 -- USE Method, Big-O, Amdahl, USL 기반 종합 성능 분석.

    Brendan Gregg의 Systems Performance 방법론, Knuth의 알고리즘 복잡도 이론,
    Gunther의 Universal Scalability Law, Jeff Dean의 레이턴시 계층 모델을
    통합 적용하여 시스템 성능을 과학적으로 진단합니다.
    """

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "analyze")
        actions = {
            "analyze": self._analyze_use,
            "complexity": self._complexity_analysis,
            "bottleneck": self._bottleneck_detection,
            "memory": self._memory_analysis,
            "scalability": self._scalability_analysis,
            "database": self._database_analysis,
            "api": self._api_latency_analysis,
            "optimize": self._optimization_suggestions,
            "full": self._full_profiling,
        }
        handler = actions.get(action)
        if handler:
            return await handler(kwargs)
        return (
            f"알 수 없는 action: {action}. "
            "analyze, complexity, bottleneck, memory, scalability, "
            "database, api, optimize, full 중 하나를 사용하세요."
        )

    # ── 헬퍼: 레이턴시 포맷 ──────────────────────────────────────

    @staticmethod
    def _fmt_ns(ns: float) -> str:
        if ns >= 1_000_000:
            return f"{ns / 1_000_000:.1f}ms"
        if ns >= 1_000:
            return f"{ns / 1_000:.1f}us"
        return f"{ns:.1f}ns"

    # ── 1. USE Method 성능 종합 분석 ──────────────────────────────

    async def _analyze_use(self, p: dict) -> str:
        target, desc = p.get("target", "시스템"), p.get("description", "")
        lines = [
            f"# USE Method 성능 종합 분석: {target}", "",
            "> Brendan Gregg USE Method (2020) -- Utilization / Saturation / Errors", "",
            "| 리소스 | Utilization | Saturation | Errors | 경고/위험 |",
            "|--------|------------|------------|--------|----------|",
        ]
        for res, m in _USE_METRICS.items():
            lines.append(f"| {res} | {m['utilization']} | {m['saturation']} | {m['errors']} | {m['threshold_warn']}%/{m['threshold_critical']}% |")
        analysis = await self._llm_call(
            "Brendan Gregg 수준의 시스템 성능 전문가로서 USE Method를 적용하여 "
            "CPU/Memory/Disk/Network 각 리소스의 상태를 진단하고 개선안을 제시하세요. 한국어 마크다운.",
            f"대상: {target}\n설명: {desc}\n측정값: {p.get('metrics', '')}",
        )
        lines.extend(["", "## AI 분석", "", analysis])
        return "\n".join(lines)

    # ── 2. 알고리즘 복잡도 분석 (Big-O) ──────────────────────────

    async def _complexity_analysis(self, p: dict) -> str:
        code, algorithm = p.get("code", ""), p.get("algorithm", "")
        lines = [
            "# 알고리즘 복잡도 분석 (Big-O)", "",
            "> Donald Knuth, 'The Art of Computer Programming' (1968-2011)", "",
            "| 복잡도 | 분류 | n=100 | n=10K | n=1M | 판정 |",
            "|--------|------|-------|-------|------|------|",
        ]
        for cplx, info in _BIGO_REFERENCE.items():
            lines.append(f"| {cplx} | {info['name']} | {info['n_100']} | {info['n_10k']} | {info['n_1m']} | {info['verdict']} |")
        if code or algorithm:
            analysis = await self._llm_call(
                "Knuth 수준 알고리즘 분석 전문가로서 시간/공간 복잡도를 분석하세요.\n"
                "Best/Average/Worst 케이스, 상수 계수 지적, 더 나은 알고리즘 제안. 한국어 마크다운.",
                f"코드:\n{code}\n알고리즘: {algorithm}\n데이터 크기: {p.get('data_size', '')}",
            )
            lines.extend(["", "## AI 분석", "", analysis])
        return "\n".join(lines)

    # ── 3. 병목 탐지 (Amdahl의 법칙) ─────────────────────────────

    async def _bottleneck_detection(self, p: dict) -> str:
        pf = float(p.get("parallel_fraction", 0.0))
        nproc = int(p.get("num_processors", 4))
        desc = p.get("description", "")
        lines = [
            "# 병목 지점 탐지 (Amdahl의 법칙)", "",
            "> S(N) = 1 / ((1-P) + P/N) -- Gene Amdahl (1967)", "",
        ]
        if pf > 0:
            sf = 1.0 - pf
            lines.extend([
                f"병렬화 비율 P={pf:.1%}, 직렬 비율 1-P={sf:.1%}", "",
                "| N (코어) | 속도향상 | 효율 |",
                "|----------|---------|------|",
            ])
            for n in [1, 2, 4, 8, 16, 32, 64]:
                sp = 1.0 / (sf + pf / n)
                marker = " <--" if n == nproc else ""
                lines.append(f"| {n} | {sp:.2f}x | {sp/n:.1%}{marker} |")
            max_sp = 1.0 / sf if sf > 0 else float("inf")
            lines.extend([
                "", f"**이론적 최대: {max_sp:.1f}x** (직렬 {sf:.1%}가 천장)",
                f"**핵심**: 코어 추가보다 직렬 구간 축소가 효과적",
            ])
        if desc:
            analysis = await self._llm_call(
                "Amdahl 법칙 기반 병목 분석 전문가로서 직렬 구간 식별, "
                "해소 방법(비동기/캐싱/배치), 예상 개선 효과를 제시하세요. 한국어 마크다운.",
                f"설명: {desc}\n처리시간: {p.get('current_time', '')}",
            )
            lines.extend(["", "## AI 분석", "", analysis])
        return "\n".join(lines)

    # ── 4. 메모리 사용 패턴 분석 ──────────────────────────────────

    async def _memory_analysis(self, p: dict) -> str:
        lang = p.get("language", "Python")
        gc_models = {
            "Python":     {"gc": "RefCount + Generational GC (gen0/1/2)", "trigger": "gen0 임계치 700", "tuning": "gc.set_threshold()"},
            "Java":       {"gc": "G1GC/ZGC/Shenandoah",                  "trigger": "Eden 가득->Minor, Old 임계->Major", "tuning": "-Xmx, -XX:MaxGCPauseMillis"},
            "Go":         {"gc": "Concurrent Tri-color Mark-Sweep",       "trigger": "힙 2배 도달 (GOGC=100)", "tuning": "GOGC 환경변수"},
            "JavaScript": {"gc": "V8 Generational (Scavenge+Mark-Compact)","trigger": "New Space 가득->Scavenge", "tuning": "--max-old-space-size"},
        }
        gc = gc_models.get(lang, gc_models["Python"])
        lines = [
            "# 메모리 사용 패턴 분석", "",
            f"## {lang} GC 모델", "",
            f"| 항목 | 내용 |\n|------|------|\n| 수집기 | {gc['gc']} |\n| 트리거 | {gc['trigger']} |\n| 튜닝 | {gc['tuning']} |", "",
            "## 메모리 계층 (Jeff Dean)", "",
            "| 계층 | 레이턴시 | 배수 |",
            "|------|---------|------|",
        ]
        for key in ["L1_cache_ref", "L2_cache_ref", "main_memory_ref", "read_4kb_ssd", "disk_seek"]:
            ref = _LATENCY_TABLE[key]
            lines.append(f"| {ref['desc']} | {self._fmt_ns(ref['latency_ns'])} | {ref['relative']} |")
        lines.extend(["", "## 주요 문제 패턴", "",
            "| 문제 | 증상 | 해결책 |", "|------|------|--------|",
            "| 메모리 누수 | RSS 지속 증가 | 참조 해제, WeakRef |",
            "| 과도한 GC | CPU 스파이크 | 객체 풀링, 재사용 |",
            "| OOM | 프로세스 킬 | 스트리밍, 배치 분할 |",
            "| 힙 단편화 | 할당 실패 | jemalloc, 메모리 풀 |",
        ])
        if p.get("description") or p.get("target"):
            analysis = await self._llm_call(
                f"{lang} 메모리 최적화 전문가로서 누수 진단, GC 압력 평가, "
                "힙/스택 최적화, 코드 레벨 개선을 제안하세요. 한국어 마크다운.",
                f"대상: {p.get('target','')}\n설명: {p.get('description','')}\n힙: {p.get('heap_size','')}\nGC: {p.get('gc_info','')}",
            )
            lines.extend(["", "## AI 분석", "", analysis])
        return "\n".join(lines)

    # ── 5. 확장성 분석 (USL) ──────────────────────────────────────

    async def _scalability_analysis(self, p: dict) -> str:
        sigma = float(p.get("sigma", 0.02))
        kappa = float(p.get("kappa", 0.001))
        cur = int(p.get("current_users", 100))
        lines = [
            "# 확장성 분석 (Universal Scalability Law)", "",
            "> C(N) = N / (1 + sigma*(N-1) + kappa*N*(N-1)) -- Neil Gunther (2007)", "",
            f"sigma(경합)={sigma}, kappa(일관성)={kappa}, 현재 N={cur}", "",
            "| N | C(N) | 효율 |",
            "|---|------|------|",
        ]
        for n in [1, 2, 5, 10, 50, 100, 500, 1000, 5000]:
            d = 1 + sigma * (n - 1) + kappa * n * (n - 1)
            c = n / d if d > 0 else 0
            marker = " <--" if n == cur else ""
            lines.append(f"| {n:,} | {c:.1f} | {c/n:.1%}{marker} |")
        if kappa > 0:
            opt_n = math.sqrt((1 - sigma) / kappa) if (1 - sigma) / kappa > 0 else 0
            opt_c = opt_n / (1 + sigma * (opt_n - 1) + kappa * opt_n * (opt_n - 1)) if opt_n > 0 else 0
        else:
            opt_n, opt_c = float("inf"), float("inf")
        lines.extend(["", f"**최적 N*={opt_n:,.0f}, 최대 C(N*)={opt_c:,.1f}**"])
        if p.get("description"):
            analysis = await self._llm_call(
                "USL 전문가로서 sigma(경합) 감소(lock-free/sharding/caching), "
                "kappa(일관성) 감소(eventual consistency/CQRS) 방안을 제시하세요. 한국어 마크다운.",
                f"설명: {p['description']}\nsigma={sigma}, kappa={kappa}, N={cur}",
            )
            lines.extend(["", "## AI 분석", "", analysis])
        return "\n".join(lines)

    # ── 6. DB 성능 분석 ───────────────────────────────────────────

    async def _database_analysis(self, p: dict) -> str:
        lines = [
            "# DB 성능 분석", "",
            f"## 안티패턴 체크리스트 ({len(_DB_ANTIPATTERNS)}가지)", "",
            "| # | 안티패턴 | 심각도 | 영향 | 해결책 |",
            "|---|---------|--------|------|--------|",
        ]
        sev_map = {"critical": "심각", "high": "높음", "medium": "중간"}
        for i, (_, info) in enumerate(_DB_ANTIPATTERNS.items(), 1):
            lines.append(f"| {i} | {info['name']} | {sev_map.get(info['severity'],'?')} | {info['impact']} | {info['fix']} |")
        lines.extend(["", "## 최적화 원칙", "",
            "1. EXPLAIN ANALYZE 먼저 | 2. WHERE/JOIN 컬럼 인덱스",
            "3. 서브쿼리->JOIN | 4. 커서 기반 페이지네이션 | 5. 연결 풀링",
        ])
        query, schema, desc = p.get("query", ""), p.get("schema", ""), p.get("description", "")
        if query or schema or desc:
            analysis = await self._llm_call(
                "DBA 전문가로서 안티패턴 식별, EXPLAIN 분석, 인덱스 제안, "
                "쿼리 리라이팅, 정량적 개선 효과를 제시하세요. 한국어 마크다운.",
                f"DB: {p.get('db_type','SQLite')}\n쿼리:\n{query}\n스키마:\n{schema}\n설명: {desc}",
            )
            lines.extend(["", "## AI 분석", "", analysis])
        return "\n".join(lines)

    # ── 7. API 지연시간 분석 ──────────────────────────────────────

    async def _api_latency_analysis(self, p: dict) -> str:
        endpoint = p.get("endpoint", "")
        p50, p95, p99 = float(p.get("p50", 0)), float(p.get("p95", 0)), float(p.get("p99", 0))
        rps, err_rate = float(p.get("rps", 0)), float(p.get("error_rate", 0))
        lines = [
            "# API 지연시간 분석", "",
            "> 'P99가 사용자 경험을 결정한다' -- Jeff Dean", "",
            "## 레이턴시 레퍼런스", "",
            "| 연산 | 레이턴시 | 배수 |",
            "|------|---------|------|",
        ]
        for ref in _LATENCY_TABLE.values():
            lines.append(f"| {ref['desc']} | {self._fmt_ns(ref['latency_ns'])} | {ref['relative']} |")
        if p50 > 0 or p95 > 0 or p99 > 0:
            slo = {"P50": 200, "P95": 500, "P99": 1000}
            lines.extend(["", f"## 엔드포인트: {endpoint or '(미지정)'}", "",
                "| 백분위 | 응답(ms) | SLO | 판정 |", "|--------|---------|-----|------|"])
            for label, val in [("P50", p50), ("P95", p95), ("P99", p99)]:
                if val > 0:
                    t = slo[label]
                    lines.append(f"| {label} | {val:.0f} | <{t}ms | {'PASS' if val <= t else 'FAIL'} |")
            if rps > 0:
                lines.append(f"\n처리량: {rps:,.0f} RPS")
            if err_rate > 0:
                lines.append(f"에러율: {err_rate:.2%}")
            if p50 > 0 and p99 > 0:
                ratio = p99 / p50
                verdict = "경고(>10x)" if ratio > 10 else "주의(>5x)" if ratio > 5 else "양호"
                lines.append(f"\nP99/P50 = {ratio:.1f}x -- {verdict}")
        if p.get("description") or endpoint:
            analysis = await self._llm_call(
                "API 성능 전문가로서 응답시간 분해, 테일 레이턴시 원인, "
                "개선안(캐싱/비동기/CDN), SLO 권장을 제시하세요. 한국어 마크다운.",
                f"엔드포인트: {endpoint}\nP50:{p50}ms P95:{p95}ms P99:{p99}ms\nRPS:{rps} 에러:{err_rate}\n설명: {p.get('description','')}",
            )
            lines.extend(["", "## AI 분석", "", analysis])
        return "\n".join(lines)

    # ── 8. 최적화 제안 ────────────────────────────────────────────

    async def _optimization_suggestions(self, p: dict) -> str:
        bt = p.get("bottleneck_type", "general")
        opt_matrix = {
            "cpu":     [("알고리즘 개선","높음","높음","O(n^2)->O(n log n)"), ("캐싱","높음","낮음","LRU/Redis"), ("비동기","중간","중간","asyncio"), ("프로파일링","높음","낮음","cProfile/py-spy"), ("C확장","높음","높음","Cython")],
            "memory":  [("제너레이터","높음","낮음","리스트->제너레이터"), ("객체풀링","중간","중간","재사용"), ("__slots__","중간","낮음","40%절약"), ("스트리밍","높음","중간","chunk처리"), ("WeakRef","중간","낮음","GC지원")],
            "io":      [("배치처리","높음","낮음","일괄I/O"), ("비동기I/O","높음","중간","aiohttp"), ("버퍼링","중간","낮음","블록합치기"), ("연결풀링","높음","낮음","DB/HTTP재사용"), ("압축","중간","낮음","gzip/snappy")],
            "network": [("CDN","높음","낮음","Cloudflare"), ("HTTP/2","중간","낮음","멀티플렉싱"), ("gRPC","높음","높음","프로토버프"), ("캐시헤더","높음","낮음","ETag"), ("Keep-Alive","중간","낮음","TCP절감")],
        }
        lines = [
            "# 최적화 제안", "",
            "> 'Premature optimization is the root of all evil' -- Knuth (1974)", "",
        ]
        cats = opt_matrix if bt == "general" else {bt: opt_matrix.get(bt, opt_matrix["cpu"])}
        cat_ko = {"cpu": "CPU", "memory": "메모리", "io": "I/O", "network": "네트워크"}
        for cat, techs in cats.items():
            lines.extend([f"## {cat_ko.get(cat, cat)}", "", "| 기법 | 효과 | 난이도 | 설명 |", "|------|------|--------|------|"])
            for t, imp, eff, d in techs:
                lines.append(f"| {t} | {imp} | {eff} | {d} |")
            lines.append("")
        if p.get("description") or p.get("target"):
            analysis = await self._llm_call(
                "성능 최적화 전문가로서 ROI 기준 상위 3개 최적화, "
                "예상 개선 수치, 구현 난이도, 전후 비교를 제시하세요. 한국어 마크다운.",
                f"대상: {p.get('target','')}\n병목: {bt}\n설명: {p.get('description','')}\n측정값: {p.get('current_metrics','')}",
            )
            lines.extend(["", "## AI 분석", "", analysis])
        return "\n".join(lines)

    # ── 9. 전체 종합 (병렬 실행) ──────────────────────────────────

    async def _full_profiling(self, p: dict) -> str:
        results = await asyncio.gather(
            self._analyze_use(p), self._complexity_analysis(p),
            self._bottleneck_detection(p), self._memory_analysis(p),
            self._scalability_analysis(p), self._database_analysis(p),
            self._api_latency_analysis(p), self._optimization_suggestions(p),
            return_exceptions=True,
        )
        names = ["USE Method", "복잡도", "병목", "메모리", "확장성", "DB", "API", "최적화"]
        lines = [
            "# 전체 성능 프로파일링 종합 보고서", "",
            "> Gregg 'Systems Performance' | Knuth 'TAOCP' | Gunther 'USL' | Dean 'Latency Numbers'", "", "---", "",
        ]
        for i, (name, result) in enumerate(zip(names, results), 1):
            lines.append(f"## Part {i}. {name}")
            lines.append(str(result) if not isinstance(result, Exception) else f"> 오류: {result}")
            lines.extend(["", "---", ""])
        lines.extend([
            "## 참고 문헌", "",
            "1. Brendan Gregg, *Systems Performance* (2nd ed., 2020)",
            "2. Donald Knuth, *The Art of Computer Programming* Vol.1-4A (1968-2011)",
            "3. Neil J. Gunther, *Guerrilla Capacity Planning* (2007)",
            "4. Jeff Dean, *Numbers Every Programmer Should Know* (2009)",
            "5. Gene Amdahl, *Validity of the single processor approach* (1967)",
        ])
        return "\n".join(lines)
