"""scheduler.py — 크론 실행 엔진 + 워크플로우 실행 + Soul Gym 루프

arm_server.py P7 리팩토링으로 분리 (2026-02-28).
- 크론 표현식 파서/매처
- 1분 주기 크론 루프 (예약 실행, ARGOS 수집, 가격 트리거)
- 기본 스케줄 자동 등록
- 워크플로우 순차 실행 + WebSocket 진행 알림
- Soul Gym 24/7 상시 진화 루프
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime

from fastapi import APIRouter

from state import app_state
from config_loader import KST, AGENTS, _log, _load_data, _save_data
from db import (
    create_task,
    load_setting,
    save_activity_log,
    update_task,
)
from ws_manager import wm

# ── 외부 모듈 (이미 분리된 것들) ──
from trading_engine import (
    _update_fx_rate,
    _check_price_triggers,
    _auto_refresh_prices,
    _trading_bot_loop,
    _shadow_trading_alert,
    _cio_prediction_verifier,
    _cio_weekly_soul_update,
    _FX_UPDATE_INTERVAL,
)
from argos_collector import (
    _argos_sequential_collect,
    _argos_monthly_rl_analysis,
    _build_argos_context_section,
)

logger = logging.getLogger("corthex")

scheduler_router = APIRouter(tags=["scheduler"])


def _ms():
    """arm_server 모듈 참조 (순환 임포트 방지)"""
    return sys.modules.get("arm_server") or sys.modules.get("web.arm_server")


# ── 크론 실행 엔진 (asyncio 기반 스케줄러) ──

# app_state.cron_task → app_state.cron_task 직접 사용



def _parse_cron_preset(preset: str) -> dict:
    """크론 프리셋을 실행 조건으로 변환합니다."""
    presets = {
        "every_minute": {"interval_seconds": 60},
        "every_5min": {"interval_seconds": 300},
        "every_30min": {"interval_seconds": 1800},
        "hourly": {"interval_seconds": 3600},
        "daily_9am": {"hour": 9, "minute": 0},
        "daily_6pm": {"hour": 18, "minute": 0},
        "weekday_9am": {"hour": 9, "minute": 0, "weekday_only": True},
        "monday_9am": {"hour": 9, "minute": 0, "day_of_week": 0},
    }
    return presets.get(preset, {"interval_seconds": 3600})


def _match_cron_field(field: str, value: int, max_val: int) -> bool:
    """크론 필드 하나를 매칭합니다. (예: "1-5" → 월~금, "*/10" → 0,10,20,30,40,50)"""
    if field == "*":
        return True
    for part in field.split(","):
        part = part.strip()
        if "/" in part:
            base, step = part.split("/", 1)
            step = int(step)
            if base == "*":
                if value % step == 0:
                    return True
            else:
                start = int(base)
                if value >= start and (value - start) % step == 0:
                    return True
        elif "-" in part:
            lo, hi = part.split("-", 1)
            if int(lo) <= value <= int(hi):
                return True
        else:
            if int(part) == value:
                return True
    return False


def _match_cron_expr(cron: str, now: datetime) -> bool:
    """5필드 크론 표현식과 현재 시간을 매칭합니다.
    형식: 분 시 일 월 요일 (0=일, 1=월 ... 6=토 / 또는 0=월 ... 6=일 리눅스 표준)
    여기서는 리눅스 표준: 0=일, 1=월, ..., 6=토
    """
    fields = cron.strip().split()
    if len(fields) != 5:
        return False
    minute, hour, dom, month, dow = fields
    # Python weekday(): 0=월 → 크론 변환: (python_weekday + 1) % 7 → 0=일
    cron_dow = (now.weekday() + 1) % 7
    return (
        _match_cron_field(minute, now.minute, 59)
        and _match_cron_field(hour, now.hour, 23)
        and _match_cron_field(dom, now.day, 31)
        and _match_cron_field(month, now.month, 12)
        and _match_cron_field(dow, cron_dow, 6)
    )


def _should_run_schedule(schedule: dict, now: datetime) -> bool:
    """현재 시간에 이 예약을 실행해야 하는지 확인합니다."""
    if not schedule.get("enabled", False):
        return False

    # 마지막 실행 시간 확인
    last_run = schedule.get("last_run_ts", 0)
    elapsed = now.timestamp() - last_run

    # 1순위: 실제 크론 표현식이 있으면 그걸로 판단
    cron_expr = schedule.get("cron", "")
    if cron_expr and cron_expr.strip().count(" ") >= 3:
        if _match_cron_expr(cron_expr, now):
            return elapsed >= 55  # 중복 실행 방지
        return False

    # 2순위: 프리셋 기반 (하위호환)
    preset = schedule.get("cron_preset", "")
    cron_config = _parse_cron_preset(preset)

    if "interval_seconds" in cron_config:
        return elapsed >= cron_config["interval_seconds"]

    # 시/분 기반 스케줄
    if now.hour == cron_config.get("hour", -1) and now.minute == cron_config.get("minute", -1):
        if cron_config.get("weekday_only") and now.weekday() >= 5:
            return False
        if "day_of_week" in cron_config and now.weekday() != cron_config["day_of_week"]:
            return False
        # 같은 시각에 중복 실행 방지 (최소 55초 간격)
        return elapsed >= 55
    return False



# ── ARGOS 수집 → argos_collector.py로 분리 (P4 리팩토링) ──


async def _cron_loop():
    """1분마다 예약된 작업을 확인하고 실행합니다."""
    logger = logging.getLogger("corthex.cron")
    logger.info("크론 실행 엔진 시작")

    # 서버 시작 시 환율 즉시 갱신
    await _update_fx_rate()

    while True:
        try:
            await asyncio.sleep(60)  # 1분마다 체크

            # 환율 주기적 갱신 (1시간마다)
            if time.time() - app_state.last_fx_update > _FX_UPDATE_INTERVAL:
                asyncio.create_task(_update_fx_rate())

            # Soul 자동 진화: 매주 일요일 03:00 KST
            _now_cron = datetime.now(KST)
            if _now_cron.weekday() == 6 and _now_cron.hour == 3 and _now_cron.minute == 0:
                logger.info("🧬 주간 Soul 진화 크론 실행")
                save_activity_log("system", "🧬 주간 Soul 진화 분석 시작 (크론)", "info")
                from handlers.soul_evolution_handler import run_soul_evolution_analysis
                asyncio.create_task(run_soul_evolution_analysis())

            # Soul Gym 24/7 상시 진화 — _soul_gym_loop()로 이관 (서버 시작 시 자동 실행)

            # ── ARGOS: 자동 데이터 수집 레이어 → argos_collector.py ──
            _now_ts = time.time()
            asyncio.create_task(_argos_sequential_collect(_now_ts))

            # 월간 강화학습 패턴 분석 (Phase 6-9)
            import argos_collector as _ac
            if _now_ts - _ac._ARGOS_LAST_MONTHLY_RL > _ac._ARGOS_MONTHLY_INTERVAL:
                _ac._ARGOS_LAST_MONTHLY_RL = _now_ts
                asyncio.create_task(_argos_monthly_rl_analysis())

            schedules = _load_data("schedules", [])
            now = datetime.now(KST)

            for schedule in schedules:
                if _should_run_schedule(schedule, now):
                    command = schedule.get("command", "")
                    if not command:
                        continue

                    logger.info("크론 실행: %s — %s", schedule.get("name", ""), command)
                    save_activity_log("system", f"⏰ 예약 실행: {schedule.get('name', '')} — {command[:50]}", "info")

                    # 실행 시간 기록
                    schedule["last_run"] = now.strftime("%Y-%m-%d %H:%M")
                    schedule["last_run_ts"] = now.timestamp()
                    _save_data("schedules", schedules)

                    # 백그라운드에서 명령 실행
                    asyncio.create_task(_run_scheduled_command(command, schedule.get("name", "")))

            # 가격 트리거 체크 (1분마다 — 손절/익절/목표매수 자동 실행)
            asyncio.create_task(_check_price_triggers())

        except Exception as e:
            logger.error("크론 루프 에러: %s", e)


def _register_default_schedules():
    """서버 시작 시 기본 스케줄이 없으면 자동 등록합니다.
    대표님이 삭제한 크론은 deleted_schedules에 기록 → 서버 재시작 시 복원하지 않음.
    """
    schedules = _load_data("schedules", [])
    deleted_ids: set = set(_load_data("deleted_schedules", []))  # 대표님이 삭제한 기본 크론 ID 목록
    existing_ids = {s.get("id") for s in schedules}

    # 마이그레이션: 기존 CSO 주식분석 크론 → CIO로 교체 (주식분석은 CIO 업무)
    _old_ids = {"default_cso_morning", "default_cso_weekly"}
    before_count = len(schedules)
    schedules = [s for s in schedules if s.get("id") not in _old_ids]
    _migrated = before_count - len(schedules)
    if _migrated:
        existing_ids = {s.get("id") for s in schedules}
        deleted_ids -= _old_ids  # 기존 CSO 삭제 기록 제거 (새 CIO ID로 대체)
        _log(f"[CRON] 기존 CSO 주식분석 크론 {_migrated}개 제거 → CIO로 교체 예정")

    defaults = [
        {
            "id": "default_cio_morning",
            "name": "CIO 일일 시장 분석",
            "command": "@금융분석팀장 오늘 한국 주식시장 주요 동향과 섹터별 분석을 보고해주세요. 주요 이슈와 투자 관점 포함.",
            "cron": "30 8 * * 1-5",  # 평일 08:30
            "enabled": True,
        },
        {
            "id": "default_cio_weekly",
            "name": "CIO 주간 시장 리뷰",
            "command": "@금융분석팀장 이번 주 시장 총평과 다음 주 전망을 종합 보고서로 작성해주세요.",
            "cron": "0 18 * * 5",  # 금요일 18:00
            "enabled": True,
        },
    ]

    added = 0
    for d in defaults:
        # 대표님이 삭제한 기본 크론은 다시 등록하지 않음
        if d["id"] in deleted_ids:
            continue
        if d["id"] not in existing_ids:
            d["last_run"] = ""
            d["last_run_ts"] = 0
            d["created_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
            schedules.append(d)
            added += 1

    if added or _migrated:
        _save_data("schedules", schedules)
        _log(f"[CRON] 기본 스케줄 {added}개 등록, {_migrated}개 마이그레이션 ✅")


async def _run_scheduled_command(command: str, schedule_name: str):
    """예약된 명령을 실행하고, 결과를 텔레그램 CEO에게 발송합니다."""
    try:
        # @멘션 파싱 — 텔레그램과 동일 로직 (크론 명령에서도 target_agent_id 지정)
        target_agent_id = None
        actual_command = command
        stripped = command.strip()
        if stripped.startswith("@"):
            parts = stripped.split(None, 1)
            if len(parts) >= 2:
                mention = parts[0][1:]
                mention_lower = mention.lower()
                for a in AGENTS:
                    aid = a.get("agent_id", "").lower()
                    aname = a.get("name_ko", "")
                    tcode = a.get("telegram_code", "").lstrip("@")
                    if (aid == mention_lower or aid.startswith(mention_lower)
                            or mention_lower in aname.lower() or mention == tcode):
                        target_agent_id = a["agent_id"]
                        actual_command = parts[1]  # @멘션 제거
                        break
                if not target_agent_id:
                    logger.warning("[CRON] @멘션 '%s' 매칭 실패, 스마트 라우팅으로 진행", mention)

        task = create_task(actual_command, source="cron")
        result = await _ms()._process_ai_command(actual_command, task["task_id"], target_agent_id=target_agent_id)
        # R-3: 전력분석 데이터용 agent_id 기록
        update_task(task["task_id"], agent_id=result.get("agent_id", target_agent_id or "chief_of_staff"))
        save_activity_log("system", f"✅ 예약 완료: {schedule_name}", "info")

        # 크론 결과를 텔레그램 CEO에게 발송
        content = result.get("content", "")
        if content and app_state.telegram_app:
            ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
            if ceo_id:
                try:
                    who = result.get("handled_by", "시스템")
                    msg = f"⏰ [{schedule_name}]\n\n{content}"
                    if len(msg) > 3900:
                        msg = msg[:3900] + "\n\n... (전체는 웹에서 확인)"
                    await app_state.telegram_app.bot.send_message(chat_id=int(ceo_id), text=msg)
                except Exception as tg_err:
                    logger.warning("크론 결과 텔레그램 발송 실패: %s", tg_err)
    except Exception as e:
        save_activity_log("system", f"❌ 예약 실패: {schedule_name} — {str(e)[:100]}", "error")

# ── 워크플로우 실행 (AI 의존 — arm_server.py에 유지) ──

@scheduler_router.post("/api/workflows/{wf_id}/run")
async def run_workflow(wf_id: str):
    """워크플로우를 실행합니다 — 스텝을 순서대로 AI로 처리합니다."""
    workflows = _load_data("workflows", [])
    wf = None
    for w in workflows:
        if w.get("id") == wf_id:
            wf = w
            break
    if not wf:
        return {"success": False, "error": "워크플로우를 찾을 수 없습니다"}

    steps = wf.get("steps", [])
    if not steps:
        return {"success": False, "error": "워크플로우에 실행할 단계가 없습니다"}

    if not _ms().is_ai_ready():
        return {"success": False, "error": "AI가 연결되지 않아 워크플로우를 실행할 수 없습니다"}

    # 백그라운드에서 순차 실행
    asyncio.create_task(_run_workflow_steps(wf_id, wf.get("name", ""), steps))
    return {"success": True, "message": f"워크플로우 '{wf.get('name', '')}' 실행을 시작합니다 ({len(steps)}단계)"}


async def _run_workflow_steps(wf_id: str, wf_name: str, steps: list):
    """워크플로우 스텝을 순차 실행합니다."""
    save_activity_log("system", f"🔄 워크플로우 시작: {wf_name} ({len(steps)}단계)", "info")
    results = []
    prev_result = ""

    for i, step in enumerate(steps):
        step_name = step.get("name", f"단계 {i+1}")
        command = step.get("command", "")
        if not command:
            continue

        # 이전 단계 결과를 참조할 수 있도록 명령에 컨텍스트 추가
        if prev_result and i > 0:
            command = f"[이전 단계 결과 참고: {prev_result[:500]}]\n\n{command}"

        save_activity_log("system", f"▶ {wf_name} — {step_name} 실행 중", "info")
        # 웹소켓으로 단계 시작 알림
        await _broadcast_workflow_progress(i, len(steps), "running", step_name, "", workflow_id=wf_id)

        try:
            task = create_task(command, source="workflow")
            result = await _ms()._process_ai_command(command, task["task_id"])
            # R-3: 전력분석 데이터용 agent_id 기록
            wf_agent = result.get("agent_id", "chief_of_staff") if isinstance(result, dict) else "chief_of_staff"
            update_task(task["task_id"], agent_id=wf_agent)
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            prev_result = content[:500]
            results.append({"step": step_name, "status": "completed", "result": content[:200]})
            save_activity_log("system", f"✅ {wf_name} — {step_name} 완료", "info")
            # 웹소켓으로 단계 완료 알림
            await _broadcast_workflow_progress(i, len(steps), "completed", step_name, content[:300], workflow_id=wf_id)
        except Exception as e:
            results.append({"step": step_name, "status": "failed", "error": str(e)[:200]})
            save_activity_log("system", f"❌ {wf_name} — {step_name} 실패: {str(e)[:100]}", "error")
            await _broadcast_workflow_progress(i, len(steps), "failed", step_name, str(e)[:200], workflow_id=wf_id)
            break  # 실패 시 중단

    # 전체 완료 알림
    final_result = "\n\n".join([f"**{r['step']}**: {r.get('result', r.get('error', ''))}" for r in results])
    await _broadcast_workflow_progress(-1, len(steps), "done", "", final_result, workflow_done=True, workflow_id=wf_id)
    save_activity_log("system", f"🏁 워크플로우 완료: {wf_name} — {len(results)}/{len(steps)} 단계 처리", "info")


async def _broadcast_workflow_progress(step_index: int, total_steps: int, status: str,
                                        step_name: str, result: str, workflow_done: bool = False,
                                        workflow_id: str = ""):
    """워크플로우 진행 상태를 웹소켓으로 전송합니다."""
    msg = {
        "event": "workflow_progress",
        "data": {
            "workflow_id": workflow_id,
            "step_index": step_index,
            "total_steps": total_steps,
            "status": status,
            "step_name": step_name,
            "result": result,
            "workflow_done": workflow_done,
            "final_result": result if workflow_done else "",
        },
    }
    await wm.broadcast(msg["event"], msg["data"])
# ── Soul Gym 24/7 상시 루프 ──

_soul_gym_lock = asyncio.Lock()  # 중복 실행 방지 Lock

async def _soul_gym_loop():
    """Soul Gym 상시 진화 루프 — 한 라운드 끝나면 5분 쉬고 다음 라운드.

    비유: 24시간 운영 헬스장. 선수가 운동 끝나면 5분 쉬고 다시 시작.
    """
    if _soul_gym_lock.locked():
        logger.warning("[SOUL GYM] 이미 루프 실행 중 — 중복 방지")
        return
    async with _soul_gym_lock:
        INTERVAL_SECONDS = 1800  # 라운드 간 대기 (30분, 6팀장 순차 실행 고려)

        try:
            from soul_gym_engine import evolve_all as _evolve_all
        except ImportError:
            logger.error("[SOUL GYM] soul_gym_engine 임포트 실패")
            return

        round_num = 0
        while True:
            try:
                round_num += 1
                _evo_msg = f"🧬 Soul Gym 라운드 #{round_num} 시작"
                logger.info(_evo_msg)
                save_activity_log("system", _evo_msg, "info")
                await _ms()._broadcast_evolution_log(_evo_msg, "info")
                result = await _evolve_all()
                _evo_msg = f"🧬 Soul Gym 라운드 #{round_num} 완료 — {result.get('status', '')}"
                logger.info("🧬 Soul Gym 라운드 #%d 완료: %s", round_num, result.get("status", "unknown"))
                save_activity_log("system", _evo_msg, "info")
                await _ms()._broadcast_evolution_log(_evo_msg, "info")
            except Exception as e:
                _evo_msg = f"🧬 Soul Gym 라운드 #{round_num} 에러: {e}"
                logger.error(_evo_msg)
                save_activity_log("system", _evo_msg, "error")
                await _ms()._broadcast_evolution_log(_evo_msg, "error")

            await asyncio.sleep(INTERVAL_SECONDS)


# ── 백그라운드 태스크 일괄 시작 (on_startup에서 호출) ──

async def start_background_tasks():
    """서버 시작 시 모든 주기적 백그라운드 태스크를 시작합니다.
    arm_server.py on_startup()에서 호출.
    """
    # 크론 실행 엔진
    app_state.cron_task = asyncio.create_task(_cron_loop())
    _log("[CRON] 크론 실행 엔진 시작 ✅")
    _register_default_schedules()

    # 자동매매 봇 상태 DB에서 복원
    app_state.trading_bot_active = bool(load_setting("trading_bot_active", False))
    if app_state.trading_bot_active:
        app_state.trading_bot_task = asyncio.create_task(_trading_bot_loop())
        _log("[TRADING] 자동매매 봇 DB 상태 복원 → 자동 재시작 ✅")

    # 관심종목 시세 1분 자동 갱신
    asyncio.create_task(_auto_refresh_prices())
    _log("[PRICE] 시세 자동 갱신 태스크 시작 ✅ (1분 간격)")

    # KIS 토큰 매일 오전 7시 자동 갱신
    from kis_client import start_daily_token_renewal
    asyncio.create_task(start_daily_token_renewal())
    _log("[KIS] 토큰 자동 갱신 스케줄러 시작 ✅ (매일 KST 07:00)")

    # CIO 예측 사후검증 (매일 03:00)
    asyncio.create_task(_cio_prediction_verifier())
    _log("[CIO] 예측 사후검증 스케줄러 시작 ✅ (매일 KST 03:00)")

    # CIO 주간 soul 자동 업데이트 (매주 일요일 02:00)
    asyncio.create_task(_cio_weekly_soul_update())
    _log("[CIO] 주간 soul 자동 업데이트 스케줄러 시작 ✅ (매주 일요일 KST 02:00)")

    # Shadow Trading 알림 (매일 09:00)
    asyncio.create_task(_shadow_trading_alert())
    _log("[Shadow] Shadow Trading 알림 스케줄러 시작 ✅ (매일 KST 09:00, +5% 기준)")

    # 메모리 정리 (10분마다)
    app_state._cleanup_task = asyncio.create_task(app_state.periodic_cleanup())
    _log("[CLEANUP] 메모리 자동 정리 태스크 시작 ✅ (10분 간격)")

    # Soul Gym 24/7 상시 루프
    asyncio.create_task(_soul_gym_loop())
    _log("[SOUL GYM] 24/7 상시 진화 루프 시작 ✅ (라운드당 ~$0.012)")

    # PENDING 배치 또는 진행 중인 체인 있으면 폴러 시작
    pending_batches = load_setting("pending_batches") or []
    # v5: batch_system 제거됨 — 미완료 배치 폴러 비활성
