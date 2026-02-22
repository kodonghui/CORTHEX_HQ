"""
CORTHEX HQ 전역 상태 관리 모듈.

서버 런타임 중 변하는 모든 상태를 AppState 클래스 하나로 관리합니다.
읽기 전용 설정(상수, 매핑 테이블)은 여기에 넣지 않습니다.

사용법:
    from state import app_state

    # 읽기
    if app_state.trading_bot_active:
        ...

    # 쓰기
    app_state.trading_bot_active = True

비유: 관리사무소 — 모든 공유 정보(열쇠, 택배, 공지)가 한 곳에.
     이전에는 사무실 44곳에 흩어져 있어서 "내가 어디에 뒀지?" 상태였음.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("corthex.state")


class AppState:
    """서버 전체가 공유하는 변경 가능 상태.

    모든 mutable 상태를 여기에 모아서:
    1. 어떤 상태가 있는지 한눈에 파악 가능
    2. 필요한 곳에 Lock 추가 가능
    3. 테스트 시 상태 초기화 쉬움
    """

    def __init__(self) -> None:
        # ── 진단 ──
        self.diag: dict[str, Any] = {
            "env_loaded": False,
            "env_path": "",
            "ai_init": False,
        }

        # ── 백그라운드 태스크 관리 ──
        self.bg_tasks: dict[str, asyncio.Task] = {}       # task_id → asyncio.Task
        self.bg_results: dict[str, dict] = {}             # task_id → 완료된 결과 캐시
        self.bg_current_task_id: str | None = None        # 현재 실행 중인 task_id

        # ── 배치 처리 ──
        self.batch_queue: list[dict] = []     # 배치 대기열 (로컬 순차/병렬)
        self.batch_running: bool = False      # 배치 실행 중 플래그
        self.batch_api_queue: list[dict] = [] # Batch API 대기열 (프로바이더 배치)
        self.batch_poller_task: asyncio.Task | None = None  # 배치 폴러 루프 태스크

        # ── 크론 스케줄러 ──
        self.cron_task: asyncio.Task | None = None  # 크론 루프 태스크

        # ── 자동매매 시스템 ──
        self.trading_bot_active: bool = False     # 자동매매 ON/OFF
        self.trading_bot_task: asyncio.Task | None = None  # 자동매매 봇 asyncio Task

        # ── 시세 캐시 ──
        self.price_cache: dict = {}               # {ticker: {price, change_pct, updated_at}}
        self.price_cache_lock: asyncio.Lock = asyncio.Lock()

        # ── 환율 갱신 ──
        self.last_fx_update: float = 0            # 마지막 환율 갱신 시각

        # ── 인증 세션 ──
        self.sessions: dict[str, float] = {}      # token → 만료 시간

        # ── 노션 작업 로그 ──
        self.notion_log: list[dict] = []          # 최근 20개

        # ── 외부 서비스 인스턴스 (서버 시작 시 초기화) ──
        self.telegram_app: Any = None             # telegram.ext.Application
        self.quality_gate: Any = None             # QualityGate 인스턴스
        self.tool_pool: Any = None                # ToolPool 인스턴스 (None=미초기화, False=실패)

        # ── 캐시된 프롬프트 ──
        self.chief_prompt: str = ""               # 비서실장 시스템 프롬프트


# ── 싱글턴 인스턴스 ──
app_state = AppState()
