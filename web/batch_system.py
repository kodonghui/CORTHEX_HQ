# ── web/batch_system.py ──────────────────────────────────────────
# 배치 시스템 + 배치 체인 오케스트레이터
# arm_server.py P5 리팩토링으로 분리 (2026-02-28)
# ─────────────────────────────────────────────────────────────────

import asyncio
import json
import logging
import os
import sys
from datetime import datetime

from state import app_state
from config_loader import KST, MODEL_MAX_TOKENS_MAP, _log, logger
from db import (
    create_task, get_today_cost, load_setting,
    save_activity_log, save_archive, save_setting, update_task,
)
from ws_manager import wm

try:
    from ai_handler import (
        ask_ai, batch_check, batch_retrieve, batch_submit,
        batch_submit_grouped, get_available_providers, select_model,
    )
except ImportError:
    pass

from fastapi import APIRouter, Request

batch_router = APIRouter(tags=["batch"])


def _ms():
    """arm_server 모듈 참조 (순환 import 방지)."""
    return sys.modules.get("arm_server") or sys.modules.get("web.arm_server")


# ── 배치 모드 전용 시스템 프롬프트 접미사 (도구 호출 방지) ──
_BATCH_MODE_SUFFIX = (
    "\n\n[배치 모드 안내] 이 요청은 배치 처리입니다. "
    "도구(함수)를 직접 호출할 수 없습니다. "
    "보유한 지식과 분석 능력만으로 텍스트 기반 답변을 작성하세요. "
    "코드 블록이나 함수 호출 형태(예: await, function() 등)로 답변하지 마세요."
)


# ── 배치 명령 (여러 명령 한번에 실행) ──

# → app_state로 이동. alias (list는 공유 참조)
_batch_queue = app_state.batch_queue
_batch_api_queue = app_state.batch_api_queue
# app_state.batch_running은 primitive → app_state.batch_running 직접 사용


@batch_router.get("/api/batch/queue")
async def get_batch_queue():
    """배치 대기열 조회."""
    return {"queue": _batch_queue, "running": app_state.batch_running}


@batch_router.post("/api/batch")
async def submit_batch(request: Request):
    """배치 명령 제출 — 여러 명령을 한번에 접수합니다."""
    body = await request.json()
    commands = body.get("commands", [])
    mode = body.get("mode", "sequential")  # sequential 또는 parallel

    if not commands:
        return {"success": False, "error": "명령 목록이 비어있습니다"}

    batch_id = f"batch_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}"
    batch_items = []
    for i, cmd in enumerate(commands):
        item = {
            "batch_id": batch_id,
            "index": i,
            "command": cmd if isinstance(cmd, str) else cmd.get("command", ""),
            "status": "pending",
            "result": None,
            "task_id": None,
        }
        batch_items.append(item)
        _batch_queue.append(item)

    # 백그라운드에서 배치 실행
    asyncio.create_task(_run_batch(batch_id, batch_items, mode))

    return {"success": True, "batch_id": batch_id, "count": len(commands), "mode": mode}


async def _run_batch(batch_id: str, items: list, mode: str):
    """배치 명령을 실행합니다."""

    app_state.batch_running = True

    try:
        if mode == "parallel":
            # 병렬 실행
            tasks = []
            for item in items:
                tasks.append(_run_batch_item(item))
            await asyncio.gather(*tasks)
        else:
            # 순차 실행
            for item in items:
                await _run_batch_item(item)
    finally:
        app_state.batch_running = False
        # 완료된 배치 항목은 10분 후 정리
        await asyncio.sleep(600)
        for item in items:
            if item in _batch_queue:
                _batch_queue.remove(item)


async def _run_batch_item(item: dict):
    """배치 내 개별 명령을 실행합니다."""
    item["status"] = "running"
    try:
        task = create_task(item["command"], source="batch")
        item["task_id"] = task["task_id"]

        # AI 처리
        result = await _ms()._process_ai_command(item["command"], task["task_id"])

        item["status"] = "completed"
        item["result"] = result.get("content", "")[:200] if isinstance(result, dict) else str(result)[:200]
        # R-3: 전력분석 데이터용 agent_id 기록
        agent_id = result.get("agent_id", "chief_of_staff") if isinstance(result, dict) else "chief_of_staff"
        update_task(task["task_id"], agent_id=agent_id)
    except Exception as e:
        item["status"] = "failed"
        item["result"] = str(e)[:200]


@batch_router.delete("/api/batch/queue")
async def clear_batch_queue():
    """배치 대기열을 비웁니다."""
    _batch_queue[:] = [item for item in _batch_queue if item.get("status") == "running"]
    return {"success": True}


# ══════════════════════════════════════════════════════════════
# ── AI Batch API 시스템 (PENDING 추적 + 자동 결과 수집) ──
# ══════════════════════════════════════════════════════════════
#
# CEO가 여러 명령을 AI Batch API로 보내면:
#   1) 각 명령이 PENDING 상태로 DB에 저장됨
#   2) 프로바이더의 Batch API에 한꺼번에 제출 (실시간보다 ~50% 저렴)
#   3) 백그라운드 폴러가 60초마다 상태를 확인
#   4) 완료되면 자동으로 결과를 수집하고, 에이전트에게 위임하여 보고서 작성
#   5) WebSocket으로 CEO에게 실시간 알림

# app_state.batch_poller_task → app_state.batch_poller_task 직접 사용


@batch_router.post("/api/batch/ai")
async def submit_ai_batch(request: Request):
    """AI Batch API로 여러 요청을 한꺼번에 제출합니다.

    요청 body:
    {
        "requests": [
            {"message": "삼성전자 분석해줘", "system_prompt": "...", "agent_id": "cio_manager"},
            {"message": "특허 검색해줘", "system_prompt": "...", "agent_id": "clo_manager"},
        ],
        "model": "claude-sonnet-4-6",  // 기본 모델 (선택)
        "auto_delegate": true  // 결과를 에이전트에게 자동 위임할지 (기본: true)
    }

    응답: {"batch_id": "...", "count": N, "status": "submitted"}
    """
    body = await request.json()
    requests_list = body.get("requests", [])
    model = body.get("model")
    auto_delegate = body.get("auto_delegate", True)

    if not requests_list:
        return {"success": False, "error": "요청 목록이 비어있습니다"}

    # 각 요청에 custom_id 자동 부여
    now_str = datetime.now(KST).strftime('%Y%m%d_%H%M%S')
    for i, req in enumerate(requests_list):
        if "custom_id" not in req:
            req["custom_id"] = f"batch_{now_str}_{i}"
        # 에이전트 소울(시스템 프롬프트)을 자동으로 로드
        agent_id = req.get("agent_id")
        if agent_id and not req.get("system_prompt"):
            req["system_prompt"] = _ms()._load_agent_prompt(agent_id)

    # Batch API 제출
    result = await batch_submit(requests_list, model=model)

    if "error" in result:
        return {"success": False, "error": result["error"]}

    batch_id = result["batch_id"]
    provider = result["provider"]

    # DB에 PENDING 상태로 저장
    pending_data = {
        "batch_id": batch_id,
        "provider": provider,
        "model": model,
        "status": "pending",
        "auto_delegate": auto_delegate,
        "submitted_at": datetime.now(KST).isoformat(),
        "requests": [
            {
                "custom_id": r.get("custom_id"),
                "message": r.get("message", "")[:200],
                "agent_id": r.get("agent_id", ""),
            }
            for r in requests_list
        ],
        "results": [],
    }

    # 기존 pending_batches 목록에 추가
    pending_batches = load_setting("pending_batches") or []
    pending_batches.append(pending_data)
    save_setting("pending_batches", pending_batches)

    # 각 요청을 task로도 생성 (PENDING 상태)
    for req in requests_list:
        task = create_task(
            req.get("message", "배치 요청"),
            source="batch_api",
            agent_id=req.get("agent_id", "chief_of_staff"),
        )
        update_task(task["task_id"], status="pending",
                    result_summary=f"[PENDING] 배치 처리 중 (batch_id: {batch_id[:20]}...)")

    # WebSocket 알림
    await wm.broadcast("batch_submitted", {
        "batch_id": batch_id,
        "provider": provider,
        "count": len(requests_list),
    })

    _log(f"[BATCH] AI 배치 제출 완료: {batch_id} ({len(requests_list)}개 요청, {provider})")

    # 폴러가 안 돌고 있으면 시작
    _ensure_batch_poller()

    return {
        "success": True,
        "batch_id": batch_id,
        "provider": provider,
        "count": len(requests_list),
        "status": "submitted",
    }


@batch_router.get("/api/batch/pending")
async def get_pending_batches():
    """PENDING 상태인 배치 목록을 조회합니다."""
    pending_batches = load_setting("pending_batches") or []
    # pending과 processing만 반환
    active = [b for b in pending_batches if b.get("status") in ("pending", "processing")]
    return {"pending": active, "total": len(pending_batches)}


@batch_router.post("/api/batch/check/{batch_id}")
async def check_batch_status(batch_id: str):
    """특정 배치의 상태를 수동으로 확인합니다."""
    pending_batches = load_setting("pending_batches") or []
    batch_info = next((b for b in pending_batches if b["batch_id"] == batch_id), None)

    if not batch_info:
        return {"error": f"배치 '{batch_id}'를 찾을 수 없습니다"}

    provider = batch_info["provider"]
    status_result = await batch_check(batch_id, provider)

    if "error" in status_result:
        return status_result

    # 상태 업데이트
    batch_info["status"] = status_result["status"]
    batch_info["progress"] = status_result.get("progress", {})
    save_setting("pending_batches", pending_batches)

    # 완료되었으면 결과 수집
    if status_result["status"] == "completed":
        await _collect_batch_results(batch_info, pending_batches)

    return status_result


@batch_router.post("/api/batch/resume")
async def resume_all_pending():
    """모든 PENDING 배치의 상태를 확인하고, 완료된 것은 결과를 수집합니다."""
    pending_batches = load_setting("pending_batches") or []
    active = [b for b in pending_batches if b.get("status") in ("pending", "processing")]

    if not active:
        return {"message": "처리 중인 배치가 없습니다", "checked": 0}

    checked = 0
    collected = 0
    for batch_info in active:
        batch_id = batch_info["batch_id"]
        provider = batch_info["provider"]

        status_result = await batch_check(batch_id, provider)
        if "error" not in status_result:
            batch_info["status"] = status_result["status"]
            batch_info["progress"] = status_result.get("progress", {})
            checked += 1

            if status_result["status"] == "completed":
                await _collect_batch_results(batch_info, pending_batches)
                collected += 1

    save_setting("pending_batches", pending_batches)
    return {"checked": checked, "collected": collected, "remaining": len(active) - collected}


@batch_router.get("/api/batch/history")
async def get_batch_history():
    """모든 배치의 히스토리를 조회합니다 (완료된 것 포함)."""
    all_batches = load_setting("pending_batches") or []
    return {"batches": all_batches[-50:], "total": len(all_batches)}  # 최근 50개만


async def _collect_batch_results(batch_info: dict, all_batches: list):
    """완료된 배치의 결과를 수집하고, 필요시 에이전트에게 위임합니다."""
    batch_id = batch_info["batch_id"]
    provider = batch_info["provider"]

    _log(f"[BATCH] 결과 수집 시작: {batch_id}")

    # 결과 가져오기
    result = await batch_retrieve(batch_id, provider)
    if "error" in result:
        _log(f"[BATCH] 결과 수집 실패: {result['error']}")
        return

    results = result.get("results", [])
    batch_info["results"] = results
    batch_info["status"] = "completed"
    batch_info["completed_at"] = datetime.now(KST).isoformat()

    # 총 비용 계산
    total_cost = sum(r.get("cost_usd", 0) for r in results if r.get("cost_usd"))
    batch_info["total_cost_usd"] = round(total_cost, 6)

    save_setting("pending_batches", all_batches)

    # 에이전트에게 자동 위임 (auto_delegate=true인 경우)
    if batch_info.get("auto_delegate"):
        req_map = {r["custom_id"]: r for r in batch_info.get("requests", [])}
        for res in results:
            if res.get("error"):
                continue
            custom_id = res.get("custom_id", "")
            req_info = req_map.get(custom_id, {})
            agent_id = req_info.get("agent_id")
            message = req_info.get("message", "")

            if agent_id and res.get("content"):
                # 결과를 활동 로그에 기록
                agent_name = _ms()._AGENT_NAMES.get(agent_id, agent_id)
                log_entry = save_activity_log(
                    agent_id,
                    f"[배치 완료] {agent_name}: {message[:40]}... → {res['content'][:60]}..."
                )
                await wm.send_activity_log(log_entry)

                # 아카이브에 저장
                division = _ms()._AGENT_DIVISION.get(agent_id, "secretary")
                now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
                archive_content = f"# [배치] [{agent_name}] {message[:60]}\n\n{res['content']}"
                save_archive(
                    division=division,
                    filename=f"batch_{agent_id}_{now_str}.md",
                    content=archive_content,
                    agent_id=agent_id,
                )

    # WebSocket으로 완료 알림
    await wm.broadcast("batch_completed", {
        "batch_id": batch_id,
        "provider": provider,
        "count": len(results),
        "total_cost_usd": total_cost,
        "succeeded": sum(1 for r in results if not r.get("error")),
        "failed": sum(1 for r in results if r.get("error")),
    })

    _log(f"[BATCH] 결과 수집 완료: {batch_id} ({len(results)}개, ${total_cost:.4f})")


async def _flush_batch_api_queue():
    """배치 대기열에 쌓인 요청을 Batch API에 제출합니다."""
    if not _batch_api_queue:
        return {"message": "대기열이 비어있습니다"}

    queue_copy = list(_batch_api_queue)
    _batch_api_queue.clear()

    _log(f"[BATCH] 대기열 {len(queue_copy)}건 → Batch API 제출 중...")

    # 각 요청에 에이전트 라우팅 (시스템 프롬프트 결정)
    for req in queue_copy:
        if not req.get("system_prompt"):
            routing = await _ms()._route_task(req.get("message", ""))
            agent_id = routing.get("agent_id", "chief_of_staff")
            req["agent_id"] = agent_id
            req["system_prompt"] = _ms()._load_agent_prompt(agent_id)

    # Batch API 제출 — 프로바이더별로 자동 그룹화 (Claude/GPT/Gemini 요청이 섞여도 각각 올바른 API로 전송)
    batch_results = await batch_submit_grouped(queue_copy)

    # 전부 실패한 경우 대기열에 복구
    all_failed = all("error" in br for br in batch_results)
    if all_failed:
        first_error = batch_results[0].get("error", "알 수 없는 오류") if batch_results else "결과 없음"
        _log(f"[BATCH] 제출 실패 (전체): {first_error}")
        _batch_api_queue.extend(queue_copy)
        return {"error": first_error}

    # 성공한 배치들을 DB에 PENDING 상태로 저장
    pending_batches = load_setting("pending_batches") or []
    submitted_ids = []
    for result in batch_results:
        if "error" in result:
            _log(f"[BATCH] 프로바이더 {result.get('provider','?')} 제출 실패: {result['error']}")
            continue

        batch_id = result["batch_id"]
        provider = result["provider"]
        custom_ids_in_batch = result.get("custom_ids", [])

        # 이 배치에 포함된 요청만 필터링
        reqs_in_batch = [r for r in queue_copy if r.get("custom_id", r.get("task_id", "")) in custom_ids_in_batch]

        pending_data = {
            "batch_id": batch_id,
            "provider": provider,
            "status": "pending",
            "auto_delegate": True,
            "submitted_at": datetime.now(KST).isoformat(),
            "requests": [
                {
                    "custom_id": r.get("custom_id", r.get("task_id", "")),
                    "message": r.get("message", "")[:200],
                    "agent_id": r.get("agent_id", ""),
                    "task_id": r.get("task_id", ""),
                }
                for r in reqs_in_batch
            ],
            "results": [],
        }
        pending_batches.append(pending_data)
        submitted_ids.append(batch_id)

        # 각 task를 PENDING 상태로 업데이트
        for req in reqs_in_batch:
            task_id = req.get("task_id")
            if task_id:
                update_task(task_id, status="pending",
                            result_summary=f"[PENDING] Batch API 제출됨 ({batch_id[:20]}...)")

        # WebSocket 알림
        await wm.broadcast("batch_submitted", {"batch_id": batch_id, "provider": provider, "count": len(reqs_in_batch)})

        _log(f"[BATCH] Batch API 제출 완료: {batch_id} ({len(reqs_in_batch)}건, {provider})")

    save_setting("pending_batches", pending_batches)
    _ensure_batch_poller()

    # 첫 번째 성공 결과를 반환 (하위 호환성 유지)
    first_success = next((r for r in batch_results if "error" not in r), batch_results[0] if batch_results else {})
    return first_success


@batch_router.post("/api/batch/flush")
async def flush_batch_queue():
    """배치 대기열에 쌓인 요청을 즉시 Batch API에 제출합니다."""
    if not _batch_api_queue:
        return {"success": False, "message": "대기열이 비어있습니다"}
    result = await _flush_batch_api_queue()
    return {"success": "error" not in result, **result}


def _ensure_batch_poller():
    """배치 폴러가 돌고 있는지 확인하고, 안 돌면 시작합니다."""

    if app_state.batch_poller_task is None or app_state.batch_poller_task.done():
        app_state.batch_poller_task = asyncio.create_task(_batch_poller_loop())
        _log("[BATCH] 배치 폴러 시작됨 (60초 간격)")


async def _batch_poller_loop():
    """백그라운드에서 60초마다 PENDING 배치 + 배치 체인을 확인합니다."""
    while True:
        try:
            await asyncio.sleep(60)

            has_work = False

            # ── (A) 기존 단독 배치 확인 ──
            pending_batches = load_setting("pending_batches") or []
            active = [b for b in pending_batches if b.get("status") in ("pending", "processing")]

            if active:
                has_work = True
                for batch_info in active:
                    batch_id = batch_info["batch_id"]
                    provider = batch_info["provider"]

                    try:
                        status_result = await batch_check(batch_id, provider)
                        if "error" not in status_result:
                            batch_info["status"] = status_result["status"]
                            batch_info["progress"] = status_result.get("progress", {})

                            if status_result["status"] == "completed":
                                await _collect_batch_results(batch_info, pending_batches)
                            elif status_result["status"] in ("failed", "expired"):
                                batch_info["status"] = status_result["status"]
                                _log(f"[BATCH] 배치 실패/만료: {batch_id}")
                    except Exception as e:
                        _log(f"[BATCH] 배치 확인 실패 ({batch_id}): {e}")

                save_setting("pending_batches", pending_batches)

            # ── (B) 배치 체인 확인 + 자동 진행 ──
            chains = load_setting("batch_chains") or []
            active_chains = [c for c in chains if c.get("status") in ("running", "pending")]

            if active_chains:
                has_work = True
                for chain in active_chains:
                    try:
                        await _advance_batch_chain(chain["chain_id"])
                    except Exception as e:
                        _log(f"[CHAIN] 체인 진행 오류 ({chain['chain_id']}): {e}")

            if not has_work:
                _log("[BATCH] 처리 중인 배치/체인 없음 — 폴러 종료")
                break

        except asyncio.CancelledError:
            break
        except Exception as e:
            _log(f"[BATCH] 폴러 오류: {e}")
            await asyncio.sleep(30)  # 에러 시 30초 대기 후 재시도


# ══════════════════════════════════════════════════════════════
# ── 배치 체인 오케스트레이터 ──
# ══════════════════════════════════════════════════════════════
#
# CEO가 📦 배치 모드로 명령을 보내면 위임 체인 전체가 Batch API로 돌아감:
#
#   [1단계] 비서실장 분류 → Batch 제출 → PENDING → 결과: "CIO에게 위임"
#   [2단계] 전문가 N명 → 프로바이더별 묶어서 Batch 제출 → PENDING → 전부 대기
#   [3단계] 팀장 종합보고서 → Batch 제출 → PENDING → 결과: 종합 보고서
#   [4단계] CEO에게 전달 + 아카이브 저장
#
# 매 단계마다 Batch API 사용 → 비용 ~50% 절감
# 프로바이더별 자동 그룹화 (Claude + GPT + Gemini 에이전트 혼합 가능)

# 분류용 시스템 프롬프트 (배치 체인에서 사용)
_BATCH_CLASSIFY_PROMPT = """당신은 업무 분류 전문가입니다.
CEO의 명령을 읽고 어느 부서가 처리해야 하는지 판단하세요.

## 부서 목록
- cto_manager: 기술개발 (코드, 웹사이트, API, 서버, 배포, 프론트엔드, 백엔드, 버그, UI, 디자인, 데이터베이스)
- cso_manager: 사업기획 (시장조사, 사업계획, 매출 예측, 비즈니스모델, 수익, 경쟁사)
- clo_manager: 법무IP (저작권, 특허, 상표, 약관, 계약, 법률, 소송)
- cmo_manager: 마케팅고객 (마케팅, 광고, SNS, 인스타그램, 유튜브, 콘텐츠, 브랜딩, 설문)
- cio_manager: 투자분석 (주식, 투자, 종목, 시황, 포트폴리오, 코스피, 나스닥, 차트, 금리)
- cpo_manager: 출판기록 (회사기록, 연대기, 블로그, 출판, 편집, 회고, 빌딩로그)
- chief_of_staff: 일반 질문, 요약, 일정 관리, 기타 (위 부서에 해당하지 않는 경우)

## 출력 형식
반드시 아래 JSON 형식으로만 답하세요. 다른 텍스트는 쓰지 마세요.
{"agent_id": "부서ID", "reason": "한줄 이유"}"""


def _save_chain(chain: dict):
    """배치 체인 상태를 DB에 저장합니다."""
    chains = load_setting("batch_chains") or []
    # 같은 chain_id가 있으면 업데이트, 없으면 추가
    found = False
    for i, c in enumerate(chains):
        if c["chain_id"] == chain["chain_id"]:
            chains[i] = chain
            found = True
            break
    if not found:
        chains.append(chain)
    # 최근 50개만 유지 (오래된 완료/실패 체인 정리)
    if len(chains) > 50:
        active = [c for c in chains if c.get("status") in ("running", "pending")]
        done = [c for c in chains if c.get("status") not in ("running", "pending")]
        chains = active + done[-20:]
    save_setting("batch_chains", chains)


def _load_chain(chain_id: str) -> dict | None:
    """DB에서 배치 체인 상태를 로드합니다."""
    chains = load_setting("batch_chains") or []
    for c in chains:
        if c["chain_id"] == chain_id:
            return c
    return None


async def _broadcast_chain_status(chain: dict, message: str):
    """배치 체인 진행 상황을 WebSocket으로 CEO에게 알립니다."""
    step_labels = {
        "classify": "1단계: 분류",
        "delegation": "2단계: 팀장 지시서",
        "specialists": "3단계: 전문가 분석",
        "synthesis": "4단계: 종합 보고서",
        "completed": "완료",
        "failed": "실패",
        "direct": "비서실장 직접 처리",
    }
    step_label = step_labels.get(chain.get("step", ""), chain.get("step", ""))
    await wm.broadcast("batch_chain_progress", {
        "chain_id": chain["chain_id"],
        "step": chain.get("step", ""),
        "step_label": step_label,
        "status": chain.get("status", ""),
        "message": message,
        "mode": chain.get("mode", "single"),
        "target_id": chain.get("target_id"),
    })

    # 텔레그램으로도 진행 상태 전달
    if app_state.telegram_app:
        ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
        if ceo_id:
            try:
                await app_state.telegram_app.bot.send_message(
                    chat_id=int(ceo_id),
                    text=f"📦 {message}",
                )
            except Exception as e:
                logger.debug("TG 배치 진행 전송 실패: %s", e)


async def _start_batch_chain(text: str, task_id: str) -> dict:
    """배치 체인을 시작합니다.

    CEO 명령을 받아서 위임 체인 전체를 Batch API로 처리합니다.
    키워드 매칭이 되면 분류 단계를 건너뛰고 바로 전문가 단계로 진행합니다.
    """
    chain_id = f"chain_{datetime.now(KST).strftime('%Y%m%d_%H%M%S')}_{task_id[:8]}"

    correlation_id = f"batch_{chain_id}"

    chain = {
        "chain_id": chain_id,
        "task_id": task_id,
        "correlation_id": correlation_id,
        "text": text,
        "mode": "broadcast" if _ms()._is_broadcast_command(text) else "single",
        "step": "classify",
        "status": "running",
        "target_id": None,
        "batches": {"classify": None, "specialists": [], "synthesis": []},
        "results": {"classify": None, "specialists": {}, "synthesis": {}},
        "custom_id_map": {},  # custom_id → {"agent_id", "step"} 역매핑
        "delegation_instructions": {},  # 팀장 지시서 (단일 부서)
        "broadcast_delegations": {},  # 팀장 지시서 (브로드캐스트)
        "total_cost_usd": 0.0,
        "created_at": datetime.now(KST).isoformat(),
        "completed_at": None,
    }

    # task에 correlation_id 연결
    update_task(task_id, correlation_id=correlation_id)

    # 예산 확인
    limit = float(load_setting("daily_budget_usd") or 7.0)
    today = get_today_cost()
    if today >= limit:
        update_task(task_id, status="failed",
                    result_summary=f"일일 예산 초과 (${today:.2f}/${limit:.0f})",
                    success=0)
        return {"error": f"일일 예산을 초과했습니다 (${today:.2f}/${limit:.0f})"}

    # ── 브로드캐스트 모드 → 분류 건너뛰고 팀장 지시서 → 전 부서 전문가 ──
    if chain["mode"] == "broadcast":
        chain["step"] = "delegation"
        chain["target_id"] = "broadcast"
        _save_chain(chain)

        await _broadcast_chain_status(chain, "📦 배치 체인 시작 (브로드캐스트: 6개 부서 → 팀장 지시서 생성 중)")
        await _chain_create_delegation_broadcast(chain)
        return {"chain_id": chain_id, "status": "started", "mode": "broadcast", "step": chain["step"]}

    # ── 키워드 분류 시도 (무료, 즉시) ──
    keyword_match = _ms()._classify_by_keywords(text)
    if keyword_match:
        chain["target_id"] = keyword_match
        chain["results"]["classify"] = {
            "agent_id": keyword_match,
            "method": "키워드",
            "cost_usd": 0,
        }

        if keyword_match == "chief_of_staff":
            # 비서실장 직접 처리 → 바로 종합(=직접 답변) 단계
            chain["step"] = "synthesis"
            _save_chain(chain)
            await _broadcast_chain_status(chain, "📦 키워드 분류 → 비서실장 직접 처리")
            await _chain_submit_synthesis(chain)
        else:
            # 팀장 부서로 위임 → 팀장 지시서 → 전문가 호출 단계
            chain["step"] = "delegation"
            _save_chain(chain)
            target_name = _ms()._AGENT_NAMES.get(keyword_match, keyword_match)
            await _broadcast_chain_status(chain, f"📦 키워드 분류 → {target_name} 지시서 생성 중")
            await _chain_create_delegation(chain)

        return {"chain_id": chain_id, "status": "started", "step": chain["step"]}

    # ── AI 분류가 필요 → Batch API로 분류 요청 제출 ──
    # 가장 저렴한 사용 가능 모델 선택 (Gemini Flash → GPT Mini → Claude)
    providers = get_available_providers()
    if providers.get("google"):
        classify_model = "gemini-2.5-flash"
    elif providers.get("openai"):
        classify_model = "gpt-5-mini"
    elif providers.get("anthropic"):
        classify_model = "claude-sonnet-4-6"
    else:
        # AI 없음 → 비서실장 직접
        chain["target_id"] = "chief_of_staff"
        chain["step"] = "synthesis"
        chain["results"]["classify"] = {"agent_id": "chief_of_staff", "method": "폴백"}
        _save_chain(chain)
        await _chain_submit_synthesis(chain)
        return {"chain_id": chain_id, "status": "started", "step": "synthesis"}

    classify_custom_id = f"{chain_id}_classify"
    classify_req = {
        "custom_id": classify_custom_id,
        "message": text,
        "system_prompt": _BATCH_CLASSIFY_PROMPT,
        "model": classify_model,
        "max_tokens": 1024,
    }

    result = await batch_submit([classify_req], model=classify_model)

    if "error" in result:
        # 배치 실패 → 폴백으로 비서실장 직접 처리
        _log(f"[CHAIN] 분류 배치 실패: {result['error']} → 비서실장 폴백")
        chain["target_id"] = "chief_of_staff"
        chain["step"] = "synthesis"
        chain["results"]["classify"] = {"agent_id": "chief_of_staff", "method": "폴백", "error": result["error"]}
        _save_chain(chain)
        await _chain_submit_synthesis(chain)
        return {"chain_id": chain_id, "status": "started", "step": "synthesis"}

    chain["batches"]["classify"] = {
        "batch_id": result["batch_id"],
        "provider": result["provider"],
        "status": "pending",
    }
    chain["status"] = "pending"
    chain["custom_id_map"][classify_custom_id] = {"agent_id": "classify", "step": "classify"}
    _save_chain(chain)

    _ensure_batch_poller()
    update_task(task_id, status="pending",
                result_summary="📦 [배치 체인] 1단계: 분류 요청 제출됨")
    await _broadcast_chain_status(chain, "📦 배치 체인 시작 — 1단계: 분류 요청 제출됨")

    _log(f"[CHAIN] 시작: {chain_id} — 분류 배치 제출 (batch_id: {result['batch_id']})")
    return {"chain_id": chain_id, "status": "pending", "step": "classify"}


# ── 팀장 지시서 생성 프롬프트 ──
_DELEGATION_PROMPT = """당신은 {mgr_name}입니다. CEO로부터 아래 업무 지시를 받았습니다.

소속 전문가들에게 각각 구체적인 작업 지시를 내려야 합니다.
각 전문가의 전문 분야에 맞게 CEO 명령을 세부 업무로 분해하세요.

## 소속 전문가
{spec_list}

## CEO 명령
{text}

## 출력 형식
반드시 아래 JSON 형식으로만 답하세요. 다른 텍스트는 쓰지 마세요.
각 전문가 ID를 키로, 구체적인 작업 지시(2~4문장)를 값으로 작성하세요.

{json_example}"""


async def _chain_create_delegation(chain: dict):
    """배치 체인 — 팀장이 전문가별 지시서를 작성합니다 (실시간 API 1회 호출).

    분류 완료 후, 전문가 배치 제출 전에 호출됩니다.
    팀장에게 CEO 명령을 전달하고, 각 전문가에게 내릴 구체적 지시서를 받습니다.
    """
    target_id = chain["target_id"]
    text = chain["text"]
    specialists = _ms()._MANAGER_SPECIALISTS.get(target_id, [])

    if not specialists:
        # 전문가 없음 → 지시서 생성 불필요
        await _chain_submit_specialists(chain)
        return

    mgr_name = _ms()._AGENT_NAMES.get(target_id, target_id)

    # 전문가 목록 텍스트 생성
    spec_list_parts = []
    json_example_parts = []
    for s_id in specialists:
        s_name = _ms()._SPECIALIST_NAMES.get(s_id, s_id)
        spec_list_parts.append(f"- {s_id}: {s_name}")
        json_example_parts.append(f'  "{s_id}": "구체적인 작업 지시 내용"')

    spec_list = "\n".join(spec_list_parts)
    json_example = "{\n" + ",\n".join(json_example_parts) + "\n}"

    delegation_prompt = _DELEGATION_PROMPT.format(
        mgr_name=mgr_name,
        spec_list=spec_list,
        text=text,
        json_example=json_example,
    )

    # 가장 저렴한 모델로 실시간 API 호출 (Gemini Flash → GPT Mini → Claude)
    providers = get_available_providers()
    if providers.get("google"):
        deleg_model = "gemini-2.5-flash"
    elif providers.get("openai"):
        deleg_model = "gpt-5-mini"
    elif providers.get("anthropic"):
        deleg_model = "claude-sonnet-4-6"
    else:
        deleg_model = None

    if deleg_model:
        # 팀장 초록불 켜기
        await _ms()._broadcast_status(target_id, "working", 0.2, f"{mgr_name} 지시서 작성 중...")
        try:
            result = await ask_ai(
                user_message=delegation_prompt,
                model=deleg_model,
                max_tokens=2048,
            )
            response_text = result.get("content", "") or result.get("text", "")

            # JSON 파싱 시도
            _json = json
            # JSON 블록 추출 (```json ... ``` 또는 { ... })
            json_text = response_text.strip()
            if "```" in json_text:
                # 코드 블록에서 추출
                start = json_text.find("{")
                end = json_text.rfind("}") + 1
                if start >= 0 and end > start:
                    json_text = json_text[start:end]
            elif json_text.startswith("{"):
                pass  # 이미 JSON
            else:
                # { 찾기
                start = json_text.find("{")
                end = json_text.rfind("}") + 1
                if start >= 0 and end > start:
                    json_text = json_text[start:end]

            instructions = _json.loads(json_text)
            if isinstance(instructions, dict):
                chain["delegation_instructions"] = instructions
                chain["results"]["delegation"] = {
                    "agent_id": target_id,
                    "instructions": instructions,
                    "model": deleg_model,
                    "cost_usd": result.get("cost_usd", 0),
                }
                chain["total_cost_usd"] += result.get("cost_usd", 0)
                _log(f"[CHAIN] {chain['chain_id']} — {mgr_name} 지시서 생성 완료 ({len(instructions)}명)")
            else:
                _log(f"[CHAIN] {chain['chain_id']} — 지시서 파싱 실패 (dict 아님)")
        except Exception as e:
            _log(f"[CHAIN] {chain['chain_id']} — 지시서 생성 실패: {e}")
            # 실패해도 진행 (지시서 없이 원본 명령으로)

    # 지시서 상태 업데이트 + 팀장 초록불 끄기
    has_instructions = bool(chain.get("delegation_instructions"))
    deleg_status = f"✅ {mgr_name} 지시서 생성 완료" if has_instructions else f"⚠️ 지시서 없이 진행"
    await _ms()._broadcast_status(target_id, "done", 0.5, deleg_status)
    update_task(chain["task_id"], status="pending",
                result_summary=f"📦 [배치 체인] 2단계: {deleg_status}")
    await _broadcast_chain_status(chain, f"📦 2단계: {deleg_status}")

    _save_chain(chain)

    # 전문가 배치 제출로 진행
    await _chain_submit_specialists(chain)


async def _chain_create_delegation_broadcast(chain: dict):
    """배치 체인 — 브로드캐스트: 6개 팀장이 각각 지시서를 작성합니다."""
    text = chain["text"]
    all_managers = ["cto_manager", "cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]

    # 가장 저렴한 모델 선택 (Gemini Flash → GPT Mini → Claude)
    providers = get_available_providers()
    if providers.get("google"):
        deleg_model = "gemini-2.5-flash"
    elif providers.get("openai"):
        deleg_model = "gpt-5-mini"
    elif providers.get("anthropic"):
        deleg_model = "claude-sonnet-4-6"
    else:
        deleg_model = None

    broadcast_delegations = {}

    if deleg_model:
        _asyncio = asyncio

        async def _get_delegation(mgr_id: str) -> tuple[str, dict]:
            specialists = _ms()._MANAGER_SPECIALISTS.get(mgr_id, [])
            if not specialists:
                return mgr_id, {}
            mgr_name = _ms()._AGENT_NAMES.get(mgr_id, mgr_id)
            spec_list_parts = []
            json_example_parts = []
            for s_id in specialists:
                s_name = _ms()._SPECIALIST_NAMES.get(s_id, s_id)
                spec_list_parts.append(f"- {s_id}: {s_name}")
                json_example_parts.append(f'  "{s_id}": "구체적인 작업 지시 내용"')

            prompt = _DELEGATION_PROMPT.format(
                mgr_name=mgr_name,
                spec_list="\n".join(spec_list_parts),
                text=text,
                json_example="{\n" + ",\n".join(json_example_parts) + "\n}",
            )
            try:
                result = await ask_ai(user_message=prompt, model=deleg_model)
                response_text = result.get("content", "") or result.get("text", "")
                _json = json
                json_text = response_text.strip()
                start = json_text.find("{")
                end = json_text.rfind("}") + 1
                if start >= 0 and end > start:
                    json_text = json_text[start:end]
                instructions = _json.loads(json_text)
                chain["total_cost_usd"] += result.get("cost_usd", 0)
                return mgr_id, instructions if isinstance(instructions, dict) else {}
            except Exception as e:
                _log(f"[CHAIN] 브로드캐스트 지시서 실패 ({mgr_id}): {e}")
                return mgr_id, {}

        # 6개 팀장에게 동시에 지시서 요청
        tasks = [_get_delegation(m) for m in all_managers]
        results = await _asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, tuple):
                mgr_id, instructions = r
                if instructions:
                    broadcast_delegations[mgr_id] = instructions

    chain["broadcast_delegations"] = broadcast_delegations
    chain["results"]["delegation"] = {
        "mode": "broadcast",
        "delegations": broadcast_delegations,
    }

    deleg_count = sum(1 for d in broadcast_delegations.values() if d)
    _log(f"[CHAIN] {chain['chain_id']} — 브로드캐스트 지시서 {deleg_count}/6 완료")
    update_task(chain["task_id"], status="pending",
                result_summary=f"📦 [배치 체인] 2단계: 팀장 지시서 {deleg_count}/6 완료")
    await _broadcast_chain_status(chain, f"📦 2단계: 팀장 지시서 {deleg_count}/6 완료")
    _save_chain(chain)

    # 전문가 배치 제출로 진행
    await _chain_submit_specialists_broadcast(chain)


async def _chain_submit_specialists(chain: dict):
    """배치 체인 — 단일 부서의 전문가들에게 배치 제출합니다."""
    target_id = chain["target_id"]
    text = chain["text"]
    specialists = _ms()._MANAGER_SPECIALISTS.get(target_id, [])

    if not specialists:
        # 전문가 없음 → 바로 종합(팀장 직접 처리) 단계
        chain["step"] = "synthesis"
        _save_chain(chain)
        await _chain_submit_synthesis(chain)
        return

    # 팀장 지시서가 있으면 전문가에게 함께 전달
    delegation = chain.get("delegation_instructions", {})

    requests = []
    for spec_id in specialists:
        # 전문가 초록불 켜기
        spec_name = _ms()._SPECIALIST_NAMES.get(spec_id, spec_id)
        await _ms()._broadcast_status(spec_id, "working", 0.3, f"{spec_name} 배치 처리 중...")

        soul = _ms()._load_agent_prompt(spec_id, include_tools=False) + _BATCH_MODE_SUFFIX
        override = _ms()._get_model_override(spec_id)
        model = select_model(text, override=override)
        custom_id = f"{chain['chain_id']}_spec_{spec_id}"

        # 팀장 지시서가 있으면 전문가에게 함께 전달
        spec_instruction = delegation.get(spec_id, "")
        if spec_instruction:
            message = (
                f"## 팀장 지시\n{spec_instruction}\n\n"
                f"## CEO 원본 명령\n{text}"
            )
        else:
            message = text

        requests.append({
            "custom_id": custom_id,
            "message": message,
            "system_prompt": soul,
            "model": model,
            "max_tokens": min(MODEL_MAX_TOKENS_MAP.get(model, 8192), 16384),
            "reasoning_effort": _ms()._get_agent_reasoning_effort(spec_id),
        })
        chain["custom_id_map"][custom_id] = {"agent_id": spec_id, "step": "specialists"}

    # 프로바이더별 그룹화하여 배치 제출
    batch_results = await batch_submit_grouped(requests)

    chain["batches"]["specialists"] = []
    for br in batch_results:
        chain["batches"]["specialists"].append({
            "batch_id": br.get("batch_id", ""),
            "provider": br.get("provider", ""),
            "status": "pending" if "error" not in br else "failed",
            "custom_ids": br.get("custom_ids", []),
            "error": br.get("error"),
        })

    chain["step"] = "specialists"
    chain["status"] = "pending"
    _save_chain(chain)

    _ensure_batch_poller()
    spec_count = len(specialists)
    provider_count = len(batch_results)
    target_name = _ms()._AGENT_NAMES.get(target_id, target_id)
    update_task(chain["task_id"], status="pending",
                result_summary=f"📦 [배치 체인] 3단계: {target_name} 전문가 {spec_count}명 배치 제출 ({provider_count}개 프로바이더)")
    await _broadcast_chain_status(chain, f"📦 3단계: {target_name} 전문가 {spec_count}명 → {provider_count}개 프로바이더별 배치 제출")

    _log(f"[CHAIN] {chain['chain_id']} — 전문가 {spec_count}명 배치 제출 ({provider_count}개 프로바이더)")


async def _chain_submit_specialists_broadcast(chain: dict):
    """배치 체인 — 브로드캐스트: 6개 부서 전체 전문가에게 배치 제출합니다."""
    text = chain["text"]
    all_managers = ["cto_manager", "cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]

    # 브로드캐스트 모드의 팀장별 지시서
    broadcast_delegations = chain.get("broadcast_delegations", {})

    requests = []
    for mgr_id in all_managers:
        specialists = _ms()._MANAGER_SPECIALISTS.get(mgr_id, [])
        mgr_delegation = broadcast_delegations.get(mgr_id, {})
        for spec_id in specialists:
            soul = _ms()._load_agent_prompt(spec_id, include_tools=False) + _BATCH_MODE_SUFFIX
            override = _ms()._get_model_override(spec_id)
            model = select_model(text, override=override)
            custom_id = f"{chain['chain_id']}_spec_{spec_id}"

            # 팀장 지시서가 있으면 전문가에게 함께 전달
            spec_instruction = mgr_delegation.get(spec_id, "")
            if spec_instruction:
                message = (
                    f"## 팀장 지시\n{spec_instruction}\n\n"
                    f"## CEO 원본 명령\n{text}"
                )
            else:
                message = text

            requests.append({
                "custom_id": custom_id,
                "message": message,
                "system_prompt": soul,
                "model": model,
                "max_tokens": min(MODEL_MAX_TOKENS_MAP.get(model, 8192), 16384),
                "reasoning_effort": _ms()._get_agent_reasoning_effort(spec_id),
            })
            chain["custom_id_map"][custom_id] = {"agent_id": spec_id, "step": "specialists"}

    if not requests:
        chain["step"] = "synthesis"
        _save_chain(chain)
        await _chain_submit_synthesis(chain)
        return

    # 프로바이더별 그룹화하여 배치 제출
    batch_results = await batch_submit_grouped(requests)

    chain["batches"]["specialists"] = []
    for br in batch_results:
        chain["batches"]["specialists"].append({
            "batch_id": br.get("batch_id", ""),
            "provider": br.get("provider", ""),
            "status": "pending" if "error" not in br else "failed",
            "custom_ids": br.get("custom_ids", []),
            "error": br.get("error"),
        })

    chain["step"] = "specialists"
    chain["status"] = "pending"
    _save_chain(chain)

    _ensure_batch_poller()
    spec_count = len(requests)
    provider_count = len(batch_results)
    update_task(chain["task_id"], status="pending",
                result_summary=f"📦 [배치 체인] 2단계: 전체 {spec_count}명 전문가 배치 제출 ({provider_count}개 프로바이더)")
    await _broadcast_chain_status(chain, f"📦 2단계: 6개 부서 전문가 {spec_count}명 → {provider_count}개 프로바이더별 배치 제출")

    _log(f"[CHAIN] {chain['chain_id']} — 브로드캐스트 전문가 {spec_count}명 배치 제출")


async def _chain_submit_synthesis(chain: dict):
    """배치 체인 — 팀장(들)이 전문가 결과를 종합하는 배치를 제출합니다."""
    text = chain["text"]

    requests = []

    if chain["mode"] == "broadcast":
        # 브로드캐스트: 6개 팀장이 각각 자기 팀 결과를 종합
        all_managers = ["cto_manager", "cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]
        for mgr_id in all_managers:
            specialists = _ms()._MANAGER_SPECIALISTS.get(mgr_id, [])
            spec_parts = []
            for s_id in specialists:
                s_res = chain["results"]["specialists"].get(s_id, {})
                name = _ms()._SPECIALIST_NAMES.get(s_id, s_id)
                content = s_res.get("content", "응답 없음")
                if s_res.get("error"):
                    content = f"오류: {s_res['error'][:100]}"
                spec_parts.append(f"[{name}]\n{content}")

            mgr_name = _ms()._AGENT_NAMES.get(mgr_id, mgr_id)
            synthesis_prompt = (
                f"당신은 {mgr_name}입니다. 소속 전문가들이 아래 분석 결과를 제출했습니다.\n"
                f"이를 검수하고 종합하여 CEO에게 보고할 간결한 보고서를 작성하세요.\n"
                f"전문가 의견 중 부족하거나 잘못된 부분이 있으면 지적하고 보완하세요.\n\n"
                f"## CEO 원본 명령\n{text}\n\n"
                f"## 전문가 분석 결과\n" + "\n\n".join(spec_parts)
            )

            soul = _ms()._load_agent_prompt(mgr_id, include_tools=False) + _BATCH_MODE_SUFFIX
            override = _ms()._get_model_override(mgr_id)
            model = select_model(synthesis_prompt, override=override)
            custom_id = f"{chain['chain_id']}_synth_{mgr_id}"

            requests.append({
                "custom_id": custom_id,
                "message": synthesis_prompt,
                "system_prompt": soul,
                "model": model,
                "max_tokens": min(MODEL_MAX_TOKENS_MAP.get(model, 8192), 16384),
                "reasoning_effort": _ms()._get_agent_reasoning_effort(mgr_id),
            })
            chain["custom_id_map"][custom_id] = {"agent_id": mgr_id, "step": "synthesis"}

    elif chain["target_id"] == "chief_of_staff":
        # 비서실장 직접 처리 (분류 결과가 chief_of_staff인 경우)
        soul = _ms()._load_agent_prompt("chief_of_staff", include_tools=False) + _BATCH_MODE_SUFFIX
        override = _ms()._get_model_override("chief_of_staff")
        model = select_model(text, override=override)
        custom_id = f"{chain['chain_id']}_synth_chief_of_staff"

        requests.append({
            "custom_id": custom_id,
            "message": text,
            "system_prompt": soul,
            "model": model,
            "max_tokens": min(MODEL_MAX_TOKENS_MAP.get(model, 8192), 16384),
            "reasoning_effort": _ms()._get_agent_reasoning_effort("chief_of_staff"),
        })
        chain["custom_id_map"][custom_id] = {"agent_id": "chief_of_staff", "step": "synthesis"}

    else:
        # 단일 부서: 팀장이 전문가 결과를 종합
        target_id = chain["target_id"]
        specialists = _ms()._MANAGER_SPECIALISTS.get(target_id, [])

        if not specialists or not chain["results"]["specialists"]:
            # 전문가 결과 없음 → 팀장이 직접 답변
            soul = _ms()._load_agent_prompt(target_id, include_tools=False) + _BATCH_MODE_SUFFIX
            override = _ms()._get_model_override(target_id)
            model = select_model(text, override=override)
            custom_id = f"{chain['chain_id']}_synth_{target_id}"

            requests.append({
                "custom_id": custom_id,
                "message": text,
                "system_prompt": soul,
                "model": model,
                "max_tokens": min(MODEL_MAX_TOKENS_MAP.get(model, 8192), 16384),
                "reasoning_effort": _ms()._get_agent_reasoning_effort(target_id),
            })
            chain["custom_id_map"][custom_id] = {"agent_id": target_id, "step": "synthesis"}
        else:
            # 전문가 결과 취합 → 팀장에게 종합 요청
            spec_parts = []
            for s_id in specialists:
                s_res = chain["results"]["specialists"].get(s_id, {})
                name = _ms()._SPECIALIST_NAMES.get(s_id, s_id)
                content = s_res.get("content", "응답 없음")
                if s_res.get("error"):
                    content = f"오류: {s_res['error'][:100]}"
                spec_parts.append(f"[{name}]\n{content}")

            mgr_name = _ms()._AGENT_NAMES.get(target_id, target_id)
            synthesis_prompt = (
                f"당신은 {mgr_name}입니다. 소속 전문가들이 아래 분석 결과를 제출했습니다.\n"
                f"이를 검수하고 종합하여 CEO에게 보고할 간결한 보고서를 작성하세요.\n"
                f"전문가 의견 중 부족하거나 잘못된 부분이 있으면 지적하고 보완하세요.\n\n"
                f"## CEO 원본 명령\n{text}\n\n"
                f"## 전문가 분석 결과\n" + "\n\n".join(spec_parts)
            )

            soul = _ms()._load_agent_prompt(target_id, include_tools=False) + _BATCH_MODE_SUFFIX
            override = _ms()._get_model_override(target_id)
            model = select_model(synthesis_prompt, override=override)
            custom_id = f"{chain['chain_id']}_synth_{target_id}"

            requests.append({
                "custom_id": custom_id,
                "message": synthesis_prompt,
                "system_prompt": soul,
                "model": model,
                "max_tokens": min(MODEL_MAX_TOKENS_MAP.get(model, 8192), 16384),
                "reasoning_effort": _ms()._get_agent_reasoning_effort(target_id),
            })
            chain["custom_id_map"][custom_id] = {"agent_id": target_id, "step": "synthesis"}

    if not requests:
        # 요청 없음 → 바로 완료
        await _deliver_chain_result(chain)
        return

    # 프로바이더별 그룹화하여 배치 제출
    batch_results = await batch_submit_grouped(requests)

    chain["batches"]["synthesis"] = []
    for br in batch_results:
        chain["batches"]["synthesis"].append({
            "batch_id": br.get("batch_id", ""),
            "provider": br.get("provider", ""),
            "status": "pending" if "error" not in br else "failed",
            "custom_ids": br.get("custom_ids", []),
            "error": br.get("error"),
        })

    chain["step"] = "synthesis"
    chain["status"] = "pending"
    _save_chain(chain)

    _ensure_batch_poller()

    if chain["mode"] == "broadcast":
        update_task(chain["task_id"], status="pending",
                    result_summary="📦 [배치 체인] 4단계: 6개 팀장 종합보고서 배치 제출")
        await _broadcast_chain_status(chain, "📦 4단계: 6개 팀장이 종합보고서 작성 중 (배치)")
    else:
        target_name = _ms()._AGENT_NAMES.get(chain["target_id"], chain["target_id"])
        update_task(chain["task_id"], status="pending",
                    result_summary=f"📦 [배치 체인] 4단계: {target_name} 종합보고서 배치 제출")
        await _broadcast_chain_status(chain, f"📦 4단계: {target_name} 종합보고서 작성 중 (배치)")

    _log(f"[CHAIN] {chain['chain_id']} — 종합보고서 배치 제출 ({len(requests)}건)")


async def _send_batch_result_to_telegram(content: str, cost: float):
    """배치 체인 결과를 텔레그램 CEO에게 전달합니다."""
    if not app_state.telegram_app:
        return
    ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
    if not ceo_id:
        return
    try:
        # 텔레그램 코드명 변환
        content = _ms()._tg_convert_names(content)
        # 텔레그램 메시지 길이 제한 (4096자)
        if len(content) > 3800:
            content = content[:3800] + "\n\n... (전체 결과는 웹에서 확인)"
        await app_state.telegram_app.bot.send_message(
            chat_id=int(ceo_id),
            text=f"📦 배치 체인 완료\n\n{content}\n\n─────\n💰 ${cost:.4f}",
        )
    except Exception as e:
        _log(f"[TG] 배치 결과 전송 실패: {e}")



async def _synthesis_realtime_fallback(chain: dict):
    """종합 배치 실패 시 실시간 ask_ai()로 종합보고서를 대신 생성합니다."""
    text = chain["text"]
    _log(f"[CHAIN] {chain['chain_id']} — 실시간 폴백 시작")

    if chain["mode"] == "broadcast":
        all_managers = ["cto_manager", "cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]
        for mgr_id in all_managers:
            if mgr_id in chain["results"]["synthesis"]:
                continue  # 이미 있으면 skip
            specialists = _ms()._MANAGER_SPECIALISTS.get(mgr_id, [])
            spec_parts = []
            for s_id in specialists:
                s_res = chain["results"]["specialists"].get(s_id, {})
                name = _ms()._SPECIALIST_NAMES.get(s_id, s_id)
                content = s_res.get("content", "응답 없음")
                spec_parts.append(f"[{name}]\n{content}")

            mgr_name = _ms()._AGENT_NAMES.get(mgr_id, mgr_id)
            if spec_parts:
                synthesis_prompt = (
                    f"당신은 {mgr_name}입니다. 소속 전문가들의 분석 결과를 종합하여 CEO에게 보고하세요.\n\n"
                    f"## CEO 원본 명령\n{text}\n\n"
                    f"## 전문가 분석 결과\n" + "\n\n".join(spec_parts)
                )
            else:
                synthesis_prompt = text
            soul = _ms()._load_agent_prompt(mgr_id, include_tools=False)
            try:
                result = await ask_ai(user_message=synthesis_prompt, system_prompt=soul)
                chain["results"]["synthesis"][mgr_id] = {
                    "content": result.get("content", ""),
                    "model": result.get("model", ""),
                    "cost_usd": result.get("cost_usd", 0),
                    "error": result.get("error"),
                }
                chain["total_cost_usd"] += result.get("cost_usd", 0)
            except Exception as e:
                _log(f"[CHAIN] 실시간 폴백 실패 ({mgr_id}): {e}")
                chain["results"]["synthesis"][mgr_id] = {"content": "", "error": str(e)[:100]}
    else:
        target_id = chain.get("target_id", "chief_of_staff")
        if target_id not in chain["results"]["synthesis"]:
            soul = _ms()._load_agent_prompt(target_id, include_tools=False)
            try:
                result = await ask_ai(user_message=text, system_prompt=soul)
                chain["results"]["synthesis"][target_id] = {
                    "content": result.get("content", ""),
                    "model": result.get("model", ""),
                    "cost_usd": result.get("cost_usd", 0),
                    "error": result.get("error"),
                }
                chain["total_cost_usd"] += result.get("cost_usd", 0)
            except Exception as e:
                _log(f"[CHAIN] 실시간 폴백 실패 ({target_id}): {e}")
                chain["results"]["synthesis"][target_id] = {"content": "", "error": str(e)[:100]}

    target_id = chain.get("target_id", "chief_of_staff")
    await _ms()._broadcast_status(target_id, "done", 1.0, "보고 완료")
    _save_chain(chain)
    await _deliver_chain_result(chain)


async def _deliver_chain_result(chain: dict):
    """배치 체인 최종 결과를 CEO에게 전달합니다."""
    # ── 중복 전달 방지 ──
    if chain.get("delivered"):
        _log(f"[CHAIN] {chain.get('chain_id', '?')} — 이미 전달됨, 중복 방지")
        return
    chain["delivered"] = True
    # 즉시 completed 상태로 변경 → 폴러가 재진입 못하게 방지
    chain["step"] = "completed"
    chain["status"] = "completed"
    chain["completed_at"] = datetime.now(KST).isoformat()
    _save_chain(chain)

    task_id = chain["task_id"]
    text = chain["text"]
    total_cost = chain.get("total_cost_usd", 0)

    if chain["mode"] == "broadcast":
        # 브로드캐스트: 6개 팀장 종합 결과를 모아서 전달
        all_managers = ["cto_manager", "cso_manager", "clo_manager", "cmo_manager", "cio_manager", "cpo_manager"]
        parts = []
        total_specialists = 0
        for mgr_id in all_managers:
            synth = chain["results"]["synthesis"].get(mgr_id, {})
            mgr_name = _ms()._AGENT_NAMES.get(mgr_id, mgr_id)
            content = synth.get("content", "")
            # 종합보고서가 비었으면 전문가 원본 결과를 폴백으로 사용
            if not content or content == "응답 없음":
                specialists = _ms()._MANAGER_SPECIALISTS.get(mgr_id, [])
                fallback_parts = []
                for s_id in specialists:
                    s_res = chain["results"].get("specialists", {}).get(s_id, {})
                    s_content = s_res.get("content", "")
                    if s_content:
                        s_name = _ms()._SPECIALIST_NAMES.get(s_id, s_id)
                        fallback_parts.append(f"**{s_name}**: {s_content[:300]}")
                if fallback_parts:
                    content = "(종합 배치 실패 — 전문가 원본 결과)\n" + "\n".join(fallback_parts)
                else:
                    content = "응답 없음 (배치 처리 중 오류 발생)"
            specs = len(_ms()._MANAGER_SPECIALISTS.get(mgr_id, []))
            total_specialists += specs
            spec_label = f" (전문가 {specs}명 동원)" if specs else ""
            parts.append(f"### 📋 {mgr_name}{spec_label}\n{content}")

        compiled = (
            f"📢 **배치 체인 결과** (6개 부서 + 전문가 {total_specialists}명 동원)\n"
            f"💰 총 비용: ${total_cost:.4f} (배치 할인 ~50% 적용)\n\n---\n\n"
            + "\n\n---\n\n".join(parts)
        )

        update_task(task_id, status="completed",
                    result_summary=compiled[:500],
                    result_data=compiled,
                    success=1, cost_usd=total_cost,
                    agent_id="chief_of_staff")

        # WebSocket으로 최종 결과 전달
        await wm.broadcast("result", {
            "content": compiled,
            "sender_id": "chief_of_staff",
            "handled_by": "비서실장 → 6개 팀장",
            "delegation": "비서실장 → 팀장 → 전문가 (배치)",
            "time_seconds": 0,
            "cost": total_cost,
            "model": "multi-agent-batch",
            "routing_method": "배치 체인 (브로드캐스트)",
        })

    else:
        # 단일 부서 결과
        target_id = chain.get("target_id", "chief_of_staff")
        synth = chain["results"]["synthesis"].get(
            target_id,
            chain["results"]["synthesis"].get("chief_of_staff", {})
        )
        content = synth.get("content", "")
        target_name = _ms()._AGENT_NAMES.get(target_id, target_id)

        # 위임 정보 구성
        specs_count = len(_ms()._MANAGER_SPECIALISTS.get(target_id, []))
        if target_id == "chief_of_staff":
            delegation = ""
            handled_by = "비서실장"
            header = "📋 **비서실장** (배치 처리)"
        else:
            delegation = f"비서실장 → {target_name}"
            if specs_count:
                delegation += f" → 전문가 {specs_count}명"
            handled_by = target_name
            header = f"📋 **{target_name}** 보고 (배치 체인)"
            if specs_count:
                header += f" (소속 전문가 {specs_count}명 동원)"

        final_content = f"{header}\n💰 비용: ${total_cost:.4f} (배치 할인 ~50% 적용)\n\n---\n\n{content}"

        update_task(task_id, status="completed",
                    result_summary=final_content[:500],
                    result_data=final_content,
                    success=1, cost_usd=total_cost,
                    agent_id=target_id)

        # WebSocket으로 최종 결과 전달
        await wm.broadcast("result", {
            "content": final_content,
            "sender_id": target_id,
            "handled_by": handled_by,
            "delegation": delegation,
            "time_seconds": 0,
            "cost": total_cost,
            "model": synth.get("model", "batch"),
            "routing_method": "배치 체인",
        })

    # 텔레그램으로도 결과 전달
    tg_content = compiled if chain["mode"] == "broadcast" else final_content
    await _send_batch_result_to_telegram(tg_content, total_cost)

    # 아카이브에 저장
    synth_content = ""
    if chain["mode"] == "broadcast":
        synth_content = compiled
    else:
        synth_content = content

    if synth_content and len(synth_content) > 20:
        division = _ms()._AGENT_DIVISION.get(chain.get("target_id", "chief_of_staff"), "secretary")
        now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        save_archive(
            division=division,
            filename=f"batch_chain_{now_str}.md",
            content=f"# [배치 체인] {text[:60]}\n\n{synth_content}",
            agent_id=chain.get("target_id", "chief_of_staff"),
        )

    _save_chain(chain)

    await _broadcast_chain_status(chain, "✅ 배치 체인 완료 — 최종 보고서 전달됨")
    _log(f"[CHAIN] {chain['chain_id']} — 완료! 비용: ${total_cost:.4f}")


async def _advance_batch_chain(chain_id: str):
    """배치 체인의 현재 단계를 확인하고, 완료되었으면 다음 단계로 진행합니다.

    배치 폴러(_batch_poller_loop)에서 60초마다 호출됩니다.
    """
    chain = _load_chain(chain_id)
    if not chain or chain.get("status") not in ("running", "pending"):
        return

    step = chain.get("step", "")

    # ── 1단계: 분류 ──
    if step == "classify":
        batch_info = chain["batches"].get("classify")
        if not batch_info:
            return

        status_result = await batch_check(batch_info["batch_id"], batch_info["provider"])
        if "error" in status_result:
            return

        batch_info["status"] = status_result["status"]

        if status_result["status"] == "completed":
            # 분류 결과 가져오기
            result = await batch_retrieve(batch_info["batch_id"], batch_info["provider"])
            if "error" in result:
                chain["status"] = "failed"
                _save_chain(chain)
                return

            # JSON 파싱 — {"agent_id": "cio_manager", "reason": "..."}
            results_list = result.get("results", [])
            if results_list:
                raw_content = results_list[0].get("content", "").strip()
                cost = results_list[0].get("cost_usd", 0)
                chain["total_cost_usd"] += cost

                try:
                    if "```" in raw_content:
                        raw_content = raw_content.split("```")[1]
                        if raw_content.startswith("json"):
                            raw_content = raw_content[4:]
                    parsed = json.loads(raw_content)
                    target_id = parsed.get("agent_id", "chief_of_staff")
                    reason = parsed.get("reason", "")
                except (json.JSONDecodeError, IndexError):
                    _log(f"[CHAIN] 분류 JSON 파싱 실패: {raw_content[:100]}")
                    target_id = "chief_of_staff"
                    reason = "분류 결과 파싱 실패"
            else:
                target_id = "chief_of_staff"
                reason = "분류 결과 없음"

            chain["target_id"] = target_id
            chain["results"]["classify"] = {
                "agent_id": target_id,
                "reason": reason,
                "method": "AI분류 (배치)",
                "cost_usd": cost if results_list else 0,
            }

            target_name = _ms()._AGENT_NAMES.get(target_id, target_id)
            _log(f"[CHAIN] {chain['chain_id']} — 분류 완료: {target_name} ({reason})")

            if target_id == "chief_of_staff":
                # 비서실장 직접 → 종합 단계
                chain["step"] = "synthesis"
                _save_chain(chain)
                await _broadcast_chain_status(chain, f"📦 분류 완료: 비서실장 직접 처리")
                await _chain_submit_synthesis(chain)
            else:
                # 팀장 지시서 → 전문가 단계로 진행
                chain["step"] = "delegation"
                _save_chain(chain)
                await _broadcast_chain_status(chain, f"📦 분류 완료: {target_name} 지시서 생성 중")
                await _chain_create_delegation(chain)

        elif status_result["status"] in ("failed", "expired"):
            # 분류 배치 실패 → 비서실장 폴백
            chain["target_id"] = "chief_of_staff"
            chain["step"] = "synthesis"
            chain["results"]["classify"] = {"agent_id": "chief_of_staff", "method": "폴백"}
            _save_chain(chain)
            await _chain_submit_synthesis(chain)

    # ── delegation 안전망 ──
    # delegation은 실시간 API로 즉시 처리되므로 폴러가 관여할 일이 없음.
    # 하지만 _chain_create_delegation() 중 에러로 step이 "delegation"에 멈춰있으면
    # 여기서 복구하여 전문가 단계를 재시도합니다.
    elif step == "delegation":
        # 이미 전문가 배치가 제출된 상태면 → specialists로 전환
        if chain["batches"].get("specialists"):
            chain["step"] = "specialists"
            _save_chain(chain)
            _log(f"[CHAIN] {chain_id} — delegation 안전망: specialists로 전환")
        else:
            # 전문가 배치가 아직 제출 안 됨 → 지시서 생성부터 재시도
            _log(f"[CHAIN] {chain_id} — delegation 안전망: 지시서 생성 재시도")
            try:
                await _chain_create_delegation(chain)
            except Exception as e:
                _log(f"[CHAIN] {chain_id} — delegation 재시도 실패: {e}")
                # 실패 시 지시서 없이 전문가에게 직접 전달
                chain["step"] = "specialists"
                _save_chain(chain)
                await _chain_submit_specialists(chain)
        return

    # ── 3단계: 전문가 ──
    elif step == "specialists":
        all_done = True
        batch_errors = []  # 오류 추적
        for batch_info in chain["batches"].get("specialists", []):
            if batch_info.get("status") in ("pending", "processing"):
                try:
                    status_result = await batch_check(batch_info["batch_id"], batch_info["provider"])
                    if "error" not in status_result:
                        batch_info["status"] = status_result["status"]
                    else:
                        err = status_result.get("error", "배치 상태 확인 실패")
                        _log(f"[CHAIN] 전문가 배치 확인 오류 ({batch_info['provider']}): {err}")
                        batch_errors.append(f"{batch_info['provider']}: {err[:80]}")
                except Exception as e:
                    _log(f"[CHAIN] 전문가 배치 확인 예외 ({batch_info.get('provider','?')}): {e}")
                    batch_errors.append(f"{batch_info.get('provider','?')}: {str(e)[:80]}")

            if batch_info.get("status") not in ("completed", "failed"):
                all_done = False

        _save_chain(chain)

        if not all_done:
            # ── 배치 처리 대기 중 → 초록불 유지 (맥박 효과) ──
            # Anthropic/OpenAI/Google 프로바이더 무관, 결과 없는 전문가에게 초록불
            target_id = chain.get("target_id", "")
            specialists = _ms()._MANAGER_SPECIALISTS.get(target_id, [])
            for spec_id in specialists:
                spec_res = chain["results"].get("specialists", {}).get(spec_id)
                if spec_res is None:
                    spec_name = _ms()._SPECIALIST_NAMES.get(spec_id, spec_id)
                    await _ms()._broadcast_status(spec_id, "working", 0.5, f"{spec_name} 배치 처리 중...")
            return

        if all_done:
            # 모든 전문가 배치 완료 → 결과 수집
            retrieve_errors = []
            for batch_info in chain["batches"]["specialists"]:
                if batch_info.get("status") != "completed":
                    if batch_info.get("status") == "failed":
                        err_detail = batch_info.get("error", "배치 실패")
                        retrieve_errors.append(f"{batch_info['provider']}: {err_detail[:80]}")
                    continue

                result = await batch_retrieve(batch_info["batch_id"], batch_info["provider"])
                if "error" in result:
                    retrieve_errors.append(f"{batch_info['provider']}: {result['error'][:80]}")
                    _log(f"[CHAIN] 전문가 결과 수집 실패 ({batch_info['provider']}): {result['error']}")
                    continue

                for r in result.get("results", []):
                    custom_id = r.get("custom_id", "")
                    mapping = chain["custom_id_map"].get(custom_id, {})
                    agent_id = mapping.get("agent_id", custom_id)

                    chain["results"]["specialists"][agent_id] = {
                        "content": r.get("content", ""),
                        "model": r.get("model", ""),
                        "cost_usd": r.get("cost_usd", 0),
                        "error": r.get("error"),
                    }
                    chain["total_cost_usd"] += r.get("cost_usd", 0)
                    # 전문가 초록불 끄기
                    await _ms()._broadcast_status(agent_id, "done", 1.0, "완료")

            spec_count = len(chain["results"]["specialists"])
            _log(f"[CHAIN] {chain['chain_id']} — 전문가 {spec_count}명 결과 수집 완료")

            # 결과가 없으면 오류 원인을 텔레그램으로 전달
            if spec_count == 0:
                all_errors = batch_errors + retrieve_errors
                if all_errors:
                    error_summary = " | ".join(all_errors[:3])
                    await _broadcast_chain_status(chain, f"⚠️ 전문가 배치 실패 — 원인: {error_summary}")
                else:
                    await _broadcast_chain_status(chain, "⚠️ 전문가 배치 결과 없음 — 팀장 직접 처리로 전환")

            # ── 품질검수 제거됨 (2026-02-27) ──

            # 종합 단계로 진행 — 팀장 초록불 켜기
            target_id = chain.get("target_id", "chief_of_staff")
            target_name = _ms()._AGENT_NAMES.get(target_id, target_id)
            await _ms()._broadcast_status(target_id, "working", 0.7, f"{target_name} 종합보고서 작성 중...")

            chain["step"] = "synthesis"
            _save_chain(chain)
            await _broadcast_chain_status(chain, f"📦 전문가 {spec_count}명 완료 → 종합보고서 작성 시작")
            await _chain_submit_synthesis(chain)

    # ── 4단계: 종합보고서 ──
    elif step == "synthesis":
        all_done = True
        synth_errors = []  # 오류 추적
        for batch_info in chain["batches"].get("synthesis", []):
            if batch_info.get("status") in ("pending", "processing"):
                try:
                    status_result = await batch_check(batch_info["batch_id"], batch_info["provider"])
                    if "error" not in status_result:
                        batch_info["status"] = status_result["status"]
                    else:
                        err = status_result.get("error", "배치 상태 확인 실패")
                        _log(f"[CHAIN] 종합 배치 확인 오류 ({batch_info['provider']}): {err}")
                        synth_errors.append(f"{batch_info['provider']}: {err[:80]}")
                except Exception as e:
                    _log(f"[CHAIN] 종합 배치 확인 예외 ({batch_info.get('provider','?')}): {e}")
                    synth_errors.append(f"{batch_info.get('provider','?')}: {str(e)[:80]}")

            if batch_info.get("status") not in ("completed", "failed"):
                all_done = False

        _save_chain(chain)

        if not all_done:
            # ── 종합보고서 배치 대기 중 → 팀장 초록불 유지 ──
            target_id = chain.get("target_id", "chief_of_staff")
            target_name = _ms()._AGENT_NAMES.get(target_id, target_id)
            await _ms()._broadcast_status(target_id, "working", 0.8, f"{target_name} 종합보고서 작성 중...")
            return

        if all_done:
            # 종합보고서 결과 수집
            retrieve_errors = []
            for batch_info in chain["batches"]["synthesis"]:
                if batch_info.get("status") != "completed":
                    if batch_info.get("status") == "failed":
                        err_detail = batch_info.get("error", "배치 실패")
                        retrieve_errors.append(f"{batch_info['provider']}: {err_detail[:80]}")
                    continue

                result = await batch_retrieve(batch_info["batch_id"], batch_info["provider"])
                if "error" in result:
                    retrieve_errors.append(f"{batch_info['provider']}: {result['error'][:80]}")
                    _log(f"[CHAIN] 종합 결과 수집 실패 ({batch_info['provider']}): {result['error']}")
                    continue

                for r in result.get("results", []):
                    custom_id = r.get("custom_id", "")
                    mapping = chain["custom_id_map"].get(custom_id, {})
                    agent_id = mapping.get("agent_id", custom_id)

                    chain["results"]["synthesis"][agent_id] = {
                        "content": r.get("content", ""),
                        "model": r.get("model", ""),
                        "cost_usd": r.get("cost_usd", 0),
                        "error": r.get("error"),
                    }
                    chain["total_cost_usd"] += r.get("cost_usd", 0)

            synth_count = len(chain["results"]["synthesis"])
            _log(f"[CHAIN] {chain['chain_id']} — 종합보고서 {synth_count}개 완료")

            # 종합 결과가 없으면 오류 원인 알림 + 실시간 폴백
            if synth_count == 0:
                all_errors = synth_errors + retrieve_errors
                if all_errors:
                    error_summary = " | ".join(all_errors[:3])
                    await _broadcast_chain_status(chain, f"⚠️ 종합 배치 실패 — 실시간으로 재처리: {error_summary}")
                else:
                    await _broadcast_chain_status(chain, "⚠️ 종합 배치 결과 없음 — 실시간으로 재처리")

                # 실시간 폴백: ask_ai()로 직접 종합보고서 생성
                await _synthesis_realtime_fallback(chain)
                return

            # ── 품질검수 제거됨 (2026-02-27) ──

            # 팀장 초록불 끄기
            target_id = chain.get("target_id", "chief_of_staff")
            await _ms()._broadcast_status(target_id, "done", 1.0, "보고 완료")

            # 최종 전달
            await _deliver_chain_result(chain)


@batch_router.get("/api/batch/chains")
async def get_batch_chains():
    """진행 중인 배치 체인 목록을 조회합니다."""
    chains = load_setting("batch_chains") or []
    active = [c for c in chains if c.get("status") in ("running", "pending")]
    recent_done = [c for c in chains if c.get("status") in ("completed", "failed")][-10:]
    return {"active": active, "recent": recent_done}

