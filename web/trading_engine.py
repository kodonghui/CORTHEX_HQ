# ── web/trading_engine.py ────────────────────────────────────────
# 트레이딩 엔진 + CIO 신뢰도 학습 + 자동매매 시스템
# arm_server.py P6 리팩토링으로 분리 (2026-02-28)
# ─────────────────────────────────────────────────────────────────

import asyncio
import json
import logging
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta

from state import app_state
from config_loader import (
    KST, MODEL_MAX_TOKENS_MAP, _log, logger,
    _load_data, _save_data, _save_config_file,
)
from db import (
    create_task, get_connection, get_today_cost, load_setting,
    save_activity_log, save_archive, save_setting, update_task,
    upsert_analyst_elo, save_elo_history,
    upsert_calibration_bucket, get_all_calibration_buckets,
    upsert_tool_effectiveness, get_tool_effectiveness_all,
    upsert_error_pattern, get_active_error_patterns,
    get_all_analyst_elos,
)
from ws_manager import wm

try:
    from ai_handler import (
        ask_ai, select_model, get_available_providers,
        batch_submit, batch_check, batch_retrieve, batch_submit_grouped,
    )
except ImportError:
    pass

try:
    from kis_client import (
        get_current_price as _kis_price,
        place_order as _kis_order,
        get_balance as _kis_balance,
        is_configured as _kis_configured,
        get_overseas_price as _kis_us_price,
        place_overseas_order as _kis_us_order,
        place_mock_order as _kis_mock_order,
        place_mock_overseas_order as _kis_mock_us_order,
        get_mock_balance as _kis_mock_balance,
        is_mock_configured as _kis_mock_configured,
        KIS_IS_MOCK,
    )
    _KIS_AVAILABLE = True
except ImportError:
    _KIS_AVAILABLE = False
    KIS_IS_MOCK = True
    async def _kis_price(ticker): return 0
    async def _kis_order(ticker, action, qty, price=0): return {"success": False, "message": "kis_client 미설치", "order_no": ""}
    async def _kis_balance(): return {"success": False, "cash": 0, "holdings": [], "total_eval": 0}
    def _kis_configured(): return False
    async def _kis_us_price(symbol, exchange=""): return {"success": False, "price": 0}
    async def _kis_us_order(symbol, action, qty, price=0, exchange=""): return {"success": False, "message": "kis_client 미설치", "order_no": ""}
    async def _kis_mock_order(ticker, action, qty, price=0): return {"success": False, "message": "kis_client 미설치", "order_no": ""}
    async def _kis_mock_us_order(symbol, action, qty, price=0, exchange=""): return {"success": False, "message": "kis_client 미설치", "order_no": ""}
    async def _kis_mock_balance(): return {"success": False, "cash": 0, "holdings": [], "total_eval": 0}
    def _kis_mock_configured(): return False

try:
    from argos_collector import _build_argos_context_section
except ImportError:
    async def _build_argos_context_section(*a, **kw): return ""

try:
    from agent_router import _init_tool_pool
except ImportError:
    def _init_tool_pool(): return None

from fastapi import APIRouter, Request

trading_router = APIRouter(tags=["trading-engine"])


def _ms():
    """arm_server 모듈 참조 (순환 import 방지)."""
    return sys.modules.get("arm_server") or sys.modules.get("web.arm_server")



# ────────────────────────────────────────────────────────────────
# 신뢰도 검증 파이프라인 — 학습 엔진
# ────────────────────────────────────────────────────────────────

_CIO_ANALYSTS = [
    "fin_analyst", "market_condition_specialist", "stock_analysis_specialist",
    "technical_analysis_specialist", "risk_management_specialist",
]


def _run_confidence_learning_pipeline(verified_7d_ids: list[int]) -> None:
    """7일 검증 완료된 예측에 대해 학습 파이프라인 실행.
    ① ELO 업데이트 → ② 칼리브레이션 갱신 → ③ 도구 효과 → ④ 오답 패턴 탐지
    """
    _lp = logging.getLogger("corthex.confidence")
    try:
        for pred_id in verified_7d_ids:
            _update_analyst_elos_for_prediction(pred_id)
        _lp.info("[학습] ELO 업데이트 완료: %d건", len(verified_7d_ids))
    except Exception as e:
        _lp.warning("[학습] ELO 업데이트 실패: %s", e)

    try:
        _rebuild_calibration_buckets()
        _lp.info("[학습] 칼리브레이션 버킷 갱신 완료")
    except Exception as e:
        _lp.warning("[학습] 칼리브레이션 갱신 실패: %s", e)

    try:
        for pred_id in verified_7d_ids:
            _update_tool_effectiveness_for_prediction(pred_id)
        _lp.info("[학습] 도구 효과 업데이트 완료")
    except Exception as e:
        _lp.warning("[학습] 도구 효과 업데이트 실패: %s", e)

    try:
        _detect_error_patterns()
        _lp.info("[학습] 오답 패턴 탐지 완료")
    except Exception as e:
        _lp.warning("[학습] 오답 패턴 탐지 실패: %s", e)


def _update_analyst_elos_for_prediction(prediction_id: int) -> None:
    """단일 예측에 대해 5명 전문가 ELO를 업데이트합니다."""
    import math
    from db import (
        get_prediction_specialists, get_analyst_elo, upsert_analyst_elo,
        save_elo_history,
    )

    conn = get_connection()
    try:
        pred = conn.execute(
            "SELECT correct_7d, return_pct_7d, direction, confidence "
            "FROM cio_predictions WHERE id=?", (prediction_id,)
        ).fetchone()
    finally:
        conn.close()
    if not pred or pred[0] is None:
        return

    correct_7d = pred[0]
    return_pct = pred[1] or 0.0
    direction = pred[2]

    # 전문가 데이터
    spec_data = get_prediction_specialists(prediction_id)
    spec_map = {s["agent_id"]: s for s in spec_data}

    # 현재 ELO 조회 + 평균 ELO 계산
    elos = {aid: get_analyst_elo(aid) for aid in _CIO_ANALYSTS}
    avg_elo = sum(e["elo_rating"] for e in elos.values()) / len(elos)

    for agent_id in _CIO_ANALYSTS:
        current = elos[agent_id]
        agent_elo = current["elo_rating"]
        total = current["total_predictions"]

        # 전문가가 이 예측에 참여했는지 확인
        spec_info = spec_map.get(agent_id)
        if spec_info:
            # 개별 전문가의 추천이 실제 결과와 일치하는지
            rec = spec_info.get("recommendation", "HOLD")
            if rec in ("BUY", "SELL"):
                agent_correct = 1 if (
                    (rec == direction and correct_7d == 1) or
                    (rec != direction and correct_7d == 0)
                ) else 0
                outcome = 1.0 if agent_correct else 0.0
                # 부분적중: 방향 맞으나 수익 < 0.5%
                if agent_correct and abs(return_pct) < 0.5:
                    outcome = 0.5
            else:
                # HOLD 추천 → 관망은 약간의 보상/패널티
                outcome = 0.5
        else:
            # 전문가 데이터 없으면 전체 결과 사용
            outcome = 1.0 if correct_7d else 0.0

        # K-factor: 첫 30건은 K=48 (빠른 조정), 이후 K=32
        k = 48 if total < 30 else 32

        # ELO 변동 계산
        expected = 1.0 / (1.0 + math.pow(10, (avg_elo - agent_elo) / 400.0))
        elo_change = round(k * (outcome - expected), 2)
        new_elo = round(agent_elo + elo_change, 1)

        # DB 업데이트
        new_total = total + 1
        new_correct = current["correct_predictions"] + (1 if outcome >= 0.75 else 0)
        # 이동 평균 수익률
        old_avg_ret = current["avg_return_pct"]
        new_avg_ret = round(
            (old_avg_ret * total + return_pct) / new_total if new_total > 0 else 0, 2
        )

        upsert_analyst_elo(agent_id, new_elo, new_total, new_correct, new_avg_ret)
        save_elo_history(agent_id, prediction_id, agent_elo, new_elo, elo_change,
                         1 if outcome >= 0.75 else 0, return_pct)


def _rebuild_calibration_buckets() -> None:
    """cio_predictions 전체 데이터를 기반으로 칼리브레이션 버킷을 재계산합니다."""
    import math
    from db import upsert_calibration_bucket

    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT
                 CASE
                   WHEN confidence < 60 THEN '50-60'
                   WHEN confidence < 70 THEN '60-70'
                   WHEN confidence < 80 THEN '70-80'
                   WHEN confidence < 90 THEN '80-90'
                   ELSE '90-100'
                 END as bucket,
                 COUNT(*) as total,
                 SUM(CASE WHEN correct_7d=1 THEN 1 ELSE 0 END) as correct
               FROM cio_predictions
               WHERE correct_7d IS NOT NULL
               GROUP BY bucket"""
        ).fetchall()
    finally:
        conn.close()

    for r in rows:
        bucket, total, correct = r[0], r[1], r[2]
        # Beta 분포: 사전분포 Beta(1,1) + 데이터
        alpha = 1.0 + correct
        beta_val = 1.0 + (total - correct)
        actual_rate = round(alpha / (alpha + beta_val), 4)
        # 95% CI: 정규 근사 (scipy 불필요)
        ab = alpha + beta_val
        var = (alpha * beta_val) / (ab * ab * (ab + 1))
        std = math.sqrt(var) if var > 0 else 0
        ci_lower = round(max(0, actual_rate - 1.96 * std), 4)
        ci_upper = round(min(1, actual_rate + 1.96 * std), 4)

        upsert_calibration_bucket(
            bucket, total, correct, actual_rate, alpha, beta_val, ci_lower, ci_upper
        )


def _update_tool_effectiveness_for_prediction(prediction_id: int) -> None:
    """단일 예측에 대해 도구별 효과를 업데이트합니다."""
    import json as _json_te
    from db import get_prediction_specialists, upsert_tool_effectiveness, get_tool_effectiveness_all

    conn = get_connection()
    try:
        pred = conn.execute(
            "SELECT correct_7d FROM cio_predictions WHERE id=?", (prediction_id,)
        ).fetchone()
    finally:
        conn.close()
    if not pred or pred[0] is None:
        return

    correct = pred[0] == 1
    spec_data = get_prediction_specialists(prediction_id)

    # 기존 도구 효과 캐시
    existing = {t["tool_name"]: t for t in get_tool_effectiveness_all()}

    tools_seen = set()
    for spec in spec_data:
        try:
            tools = _json_te.loads(spec.get("tools_used", "[]"))
        except (ValueError, TypeError):
            tools = []
        for tool in tools:
            if tool in tools_seen:
                continue
            tools_seen.add(tool)
            e = existing.get(tool, {"used_correct": 0, "used_incorrect": 0, "total_uses": 0})
            new_correct = e["used_correct"] + (1 if correct else 0)
            new_incorrect = e["used_incorrect"] + (0 if correct else 1)
            new_total = e["total_uses"] + 1
            eff = round(new_correct / new_total, 4) if new_total > 0 else 0.5
            upsert_tool_effectiveness(tool, new_correct, new_incorrect, new_total, eff)


def _detect_error_patterns() -> None:
    """검증된 예측에서 오답 패턴을 탐지합니다."""
    from db import upsert_error_pattern

    conn = get_connection()
    try:
        # 패턴 1: 신뢰도 구간별 과신 탐지
        overconf_rows = conn.execute(
            """SELECT
                 CASE WHEN confidence >= 80 THEN 'high_confidence_overfit'
                      WHEN confidence >= 70 THEN 'mid_confidence_overfit'
                      ELSE NULL END as ptype,
                 COUNT(*) as total,
                 SUM(CASE WHEN correct_7d=1 THEN 1 ELSE 0 END) as correct
               FROM cio_predictions
               WHERE correct_7d IS NOT NULL AND confidence >= 70
               GROUP BY ptype HAVING ptype IS NOT NULL"""
        ).fetchall()
        for r in overconf_rows:
            ptype, total, correct = r[0], r[1], r[2]
            miss = total - correct
            hit_rate = round(correct / total * 100, 1) if total > 0 else 0
            if total >= 5 and hit_rate < 60:
                conf_range = "80%+" if "high" in ptype else "70-80%"
                upsert_error_pattern(
                    ptype,
                    f"신뢰도 {conf_range} 시그널의 실제 적중률이 {hit_rate}%로 낮음 ({correct}/{total}건)",
                    correct, miss, hit_rate,
                )

        # 패턴 2: 같은 종목 연속 오답 (3회+)
        streak_rows = conn.execute(
            """SELECT ticker, ticker_name, COUNT(*) as miss_streak
               FROM cio_predictions
               WHERE correct_7d = 0
               GROUP BY ticker HAVING miss_streak >= 3
               ORDER BY miss_streak DESC LIMIT 5"""
        ).fetchall()
        for r in streak_rows:
            ticker, name, streak = r[0], r[1] or r[0], r[2]
            # 해당 종목의 전체 기록
            ticker_total = conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN correct_7d=1 THEN 1 ELSE 0 END) "
                "FROM cio_predictions WHERE ticker=? AND correct_7d IS NOT NULL",
                (ticker,),
            ).fetchone()
            t_total = ticker_total[0] or 0
            t_correct = ticker_total[1] or 0
            hit_rate = round(t_correct / t_total * 100, 1) if t_total > 0 else 0
            upsert_error_pattern(
                f"ticker_streak_{ticker}",
                f"{name}({ticker}) 연속 {streak}회 오답, 전체 적중률 {hit_rate}% ({t_correct}/{t_total})",
                t_correct, t_total - t_correct, hit_rate,
            )

        # 패턴 3: 매수/매도 편향
        dir_rows = conn.execute(
            """SELECT direction, COUNT(*) as total,
                      SUM(CASE WHEN correct_7d=1 THEN 1 ELSE 0 END) as correct
               FROM cio_predictions WHERE correct_7d IS NOT NULL
               GROUP BY direction"""
        ).fetchall()
        for r in dir_rows:
            direction, total, correct = r[0], r[1], r[2]
            miss = total - correct
            hit_rate = round(correct / total * 100, 1) if total > 0 else 0
            if total >= 5 and hit_rate < 45:
                upsert_error_pattern(
                    f"direction_bias_{direction.lower()}",
                    f"{direction} 시그널 적중률 {hit_rate}% ({correct}/{total}건) — 편향 주의",
                    correct, miss, hit_rate,
                )
    finally:
        conn.close()


def _capture_specialist_contributions_sync(
    parsed_signals: list[dict],
    spec_results: list[dict],
    cio_solo_content: str,
    sig_id: str,
) -> None:
    """전문가별 기여를 prediction_specialist_data 테이블에 기록합니다.

    parsed_signals에서 예측 ID를 찾고, spec_results에서 각 전문가의
    추천(BUY/SELL/HOLD)을 파싱하여 저장합니다.
    """
    import json as _json_cap
    import re as _re_cap
    from db import save_prediction_specialist, get_connection

    if not parsed_signals or not spec_results:
        return

    try:
        conn = get_connection()
        # sig_id(task_id)로 저장된 예측 ID들 조회
        pred_rows = conn.execute(
            "SELECT id, ticker, direction FROM cio_predictions WHERE task_id=? ORDER BY id DESC",
            (sig_id,),
        ).fetchall()
        conn.close()

        if not pred_rows:
            logger.debug("[신뢰도] 예측 ID 조회 실패 (sig_id=%s)", sig_id)
            return

        # 전문가별 추천 추출 패턴
        _buy_pat = _re_cap.compile(r"(?:매수|BUY|buy|강력\s*매수|적극\s*매수)", _re_cap.IGNORECASE)
        _sell_pat = _re_cap.compile(r"(?:매도|SELL|sell|강력\s*매도)", _re_cap.IGNORECASE)

        for pred_row in pred_rows:
            pred_id = pred_row[0]

            # CIO 팀장 독자분석 기여 저장
            if cio_solo_content:
                cio_rec = "HOLD"
                if _buy_pat.search(cio_solo_content[:500]):
                    cio_rec = "BUY"
                elif _sell_pat.search(cio_solo_content[:500]):
                    cio_rec = "SELL"
                save_prediction_specialist(
                    prediction_id=pred_id,
                    agent_id="fin_analyst",
                    recommendation=cio_rec,
                    confidence=0.0,
                    tools_used="[]",
                    cost_usd=0.0,
                )

            # 각 전문가 기여 저장
            for r in spec_results:
                if not isinstance(r, dict) or "error" in r:
                    continue
                agent_id = r.get("agent_id", "unknown")
                content = r.get("content", "")
                tools = r.get("tools_used", [])
                cost = r.get("cost_usd", 0)

                # 추천 추출
                rec = "HOLD"
                snippet = content[:800] if content else ""
                if _buy_pat.search(snippet):
                    rec = "BUY"
                elif _sell_pat.search(snippet):
                    rec = "SELL"

                save_prediction_specialist(
                    prediction_id=pred_id,
                    agent_id=agent_id,
                    recommendation=rec,
                    confidence=0.0,
                    tools_used=_json_cap.dumps(tools[:20]) if tools else "[]",
                    cost_usd=cost or 0.0,
                )

        logger.info("[신뢰도] 전문가 기여 %d건 × %d예측 캡처 완료",
                     len(spec_results) + (1 if cio_solo_content else 0), len(pred_rows))
    except Exception as e:
        logger.warning("[신뢰도] 전문가 기여 캡처 실패: %s", e)


# ────────────────────────────────────────────────────────────────
# CIO 자기학습 크론 + Shadow Trading 알림
# ────────────────────────────────────────────────────────────────

async def _cio_prediction_verifier():
    """CIO 예측 사후검증: 3일·7일 경과한 예측의 실제 주가 조회 → 맞음/틀림 DB 저장 (매일 KST 03:00)."""
    import pytz as _pytz_v
    _KST_v = _pytz_v.timezone("Asia/Seoul")
    _logger_v = logging.getLogger("corthex.cio_verify")
    _logger_v.info("[CIO검증] 주가 사후검증 루프 시작")

    while True:
        try:
            now = datetime.now(_KST_v)
            # 매일 03:00 KST에 실행
            target = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= target:
                target = target + timedelta(days=1)
            wait_sec = (target - now).total_seconds()
            await asyncio.sleep(wait_sec)

            _logger_v.info("[CIO검증] 사후검증 시작")
            try:
                from db import get_pending_verifications, update_cio_prediction_result
                from kis_client import get_current_price

                verified_count = 0
                verified_results = []

                verified_7d_ids = []  # 7일 검증 완료된 prediction_id (학습 파이프라인용)

                for days in [3, 7]:
                    pending = get_pending_verifications(days_threshold=days)
                    for p in pending:
                        try:
                            price = await get_current_price(p["ticker"])
                            if days == 3:
                                result = update_cio_prediction_result(p["id"], actual_price_3d=price)
                                correct = bool(result.get("correct_3d"))
                                verified_results.append({
                                    "correct_3d": correct, "ticker": p["ticker"],
                                    "direction": p.get("direction", "BUY"),
                                })
                                verified_count += 1
                            else:
                                result = update_cio_prediction_result(p["id"], actual_price_7d=price)
                                if result:
                                    verified_7d_ids.append(p["id"])
                            _logger_v.info("[CIO검증] %s %d일 검증 완료: %d원", p["ticker"], days, price)
                        except Exception as e:
                            _logger_v.warning("[CIO검증] %s 주가 조회 실패: %s", p["ticker"], e)

                save_activity_log("system", f"✅ CIO 예측 사후검증 완료 (3일 {verified_count}건, 7일 {len(verified_7d_ids)}건)", "info")

                # ── 신뢰도 학습 파이프라인 (7일 검증 완료된 건에 대해) ──
                if verified_7d_ids:
                    try:
                        _run_confidence_learning_pipeline(verified_7d_ids)
                        _logger_v.info("[CIO학습] 신뢰도 학습 파이프라인 완료: %d건", len(verified_7d_ids))
                    except Exception as le:
                        _logger_v.warning("[CIO학습] 학습 파이프라인 실패: %s", le)

                # 검증 완료 후 텔레그램 알림 (수정: direction 버그 수정)
                if verified_count > 0:
                    try:
                        ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
                        if app_state.telegram_app and ceo_id:
                            correct_count = sum(1 for r in verified_results if r.get("correct_3d"))
                            accuracy = round(correct_count / verified_count * 100) if verified_count > 0 else 0
                            # ELO 요약 추가
                            from db import get_all_analyst_elos, get_cio_performance_summary
                            elo_data = get_all_analyst_elos()
                            perf = get_cio_performance_summary()
                            elo_section = "\n".join(
                                f"  {e['agent_id'].split('_')[0]}: {e['elo_rating']:.0f}"
                                for e in elo_data[:5]
                            ) if elo_data else "  (초기화 대기 중)"
                            brier_text = f"\nBrier Score: {perf.get('avg_brier_score', '-')}" if perf.get('avg_brier_score') else ""
                            msg = (
                                f"📊 CIO 자기학습 검증 완료\n"
                                f"오늘 검증: {verified_count}건\n"
                                f"3일 정확도: {accuracy}% ({correct_count}/{verified_count})\n"
                                f"전체 7일 정확도: {perf.get('overall_accuracy', '-')}%{brier_text}\n"
                                f"전문가 ELO:\n{elo_section}"
                            )
                            await app_state.telegram_app.bot.send_message(
                                chat_id=int(ceo_id),
                                text=msg,
                            )
                    except Exception as te:
                        _logger_v.warning("[CIO검증] 텔레그램 알림 실패: %s", te)

            except ImportError as e:
                _logger_v.warning("[CIO검증] 필요 함수 미구현 — 스킵: %s", e)
        except Exception as e:
            _logger_v.error("[CIO검증] 에러: %s", e)
            await asyncio.sleep(3600)  # 에러 시 1시간 후 재시도


async def _cio_weekly_soul_update():
    """매주 일요일 KST 02:00: CLO가 CIO 오류 패턴 분석 → fin_analyst.md 자동 업데이트."""
    import pytz as _pytz_s
    import re as _re_s
    _KST_s = _pytz_s.timezone("Asia/Seoul")
    _logger_s = logging.getLogger("corthex.cio_soul")
    _logger_s.info("[CIO소울] 주간 soul 업데이트 루프 시작")

    while True:
        try:
            now = datetime.now(_KST_s)
            # 다음 일요일 02:00 KST 계산 (weekday: 월=0, 일=6)
            days_until_sunday = (6 - now.weekday()) % 7
            if days_until_sunday == 0 and now.hour >= 2:
                days_until_sunday = 7
            target = (now + timedelta(days=days_until_sunday)).replace(
                hour=2, minute=0, second=0, microsecond=0
            )
            wait_sec = (target - now).total_seconds()
            await asyncio.sleep(wait_sec)

            try:
                from db import load_cio_predictions, get_cio_performance_summary
                summary = get_cio_performance_summary()
                recent = load_cio_predictions(limit=20)
            except ImportError as e:
                _logger_s.warning("[CIO소울] 필요 함수 미구현 — 스킵: %s", e)
                continue

            # 검증된 예측(7일 결과 있는 것)만 필터링
            verified = [p for p in recent if p.get("correct_7d") is not None]
            if len(verified) < 3:
                _logger_s.info(
                    "[CIO소울] 검증된 예측 %d건 — 업데이트 스킵 (최소 3건 필요)", len(verified)
                )
                continue

            predictions_text = "\n".join([
                f"- {p['ticker']}({p.get('ticker_name', '')}) {p['direction']}: "
                f"{'✅맞음' if p['correct_7d'] == 1 else '❌틀림'} "
                f"(예측가 {p.get('predicted_price', '-')}원 → 7일후 {p.get('actual_price_7d', '-')}원)"
                for p in verified
            ])

            analysis_prompt = (
                "당신은 CLO(준법감시인)입니다. CIO(투자팀장)의 최근 투자 예측 결과를 분석하여,\n"
                "반복되는 오류 패턴을 찾고 fin_analyst.md에 추가할 규칙을 제안하세요.\n\n"
                f"## CIO 최근 예측 결과\n"
                f"전체 정확도: {summary.get('overall_accuracy', '-')}%\n"
                f"최근 20건 정확도: {summary.get('recent_20_accuracy', '-')}%\n"
                f"매수 정확도: {summary.get('buy_accuracy', '-')}%\n"
                f"매도 정확도: {summary.get('sell_accuracy', '-')}%\n\n"
                f"## 개별 예측 결과\n{predictions_text}\n\n"
                "## 요청\n"
                "1. 반복 오류 패턴 3가지 분석 (예: '반도체 섹터 과대평가 경향')\n"
                "2. 각 패턴에 대한 개선 규칙 제안 (fin_analyst.md에 추가할 마크다운 형식)\n"
                "3. 답변은 반드시 아래 형식:\n"
                "---SOUL_UPDATE_START---\n"
                "[마크다운 형식의 규칙 내용]\n"
                "---SOUL_UPDATE_END---"
            )

            try:
                result_dict = await _ms()._call_agent("leet_legal", analysis_prompt)
                result = result_dict.get("content", "") if isinstance(result_dict, dict) else str(result_dict)
                if not result:
                    _logger_s.warning("[CIO소울] CLO 응답 없음")
                    continue

                match = _re_s.search(
                    r"---SOUL_UPDATE_START---\n(.*?)\n---SOUL_UPDATE_END---",
                    result,
                    _re_s.DOTALL,
                )
                if not match:
                    _logger_s.warning("[CIO소울] soul 업데이트 내용 추출 실패")
                    continue

                new_content = match.group(1).strip()
                soul_path = os.path.normpath(
                    os.path.join(os.path.dirname(__file__), "..", "souls", "agents", "fin_analyst.md")
                )

                if os.path.exists(soul_path):
                    update_date = datetime.now(_KST_s).strftime("%Y-%m-%d")
                    update_section = (
                        f"\n\n## 자동 학습 업데이트 ({update_date})\n\n{new_content}"
                    )
                    with open(soul_path, "a", encoding="utf-8") as _f:
                        _f.write(update_section)
                    _logger_s.info("[CIO소울] soul 업데이트 완료 (%s)", update_date)
                    save_activity_log("system", f"CIO soul 주간 업데이트 완료 ({update_date})", "info")
                else:
                    _logger_s.warning("[CIO소울] soul 파일 없음: %s", soul_path)
            except Exception as e:
                _logger_s.error("[CIO소울] CLO 분석 실패: %s", e)

        except Exception as e:
            _logger_s.error("[CIO소울] 에러: %s", e)
            await asyncio.sleep(3600)


async def _shadow_trading_alert():
    """Shadow Trading 알림: 모의투자 2주 수익률 +5% 달성 시 텔레그램으로 실거래 전환 추천 (매일 KST 09:00)."""
    _pytz_a = __import__("pytz")
    _KST_a = _pytz_a.timezone("Asia/Seoul")
    _logger_a = logging.getLogger("corthex.shadow_alert")
    _logger_a.info("[Shadow알림] Shadow Trading 알림 루프 시작")

    while True:
        try:
            now = datetime.now(_KST_a)
            # 매일 09:00 KST에 실행
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= target:
                target = target + timedelta(days=1)
            wait_sec = (target - now).total_seconds()
            await asyncio.sleep(wait_sec)

            try:
                from kis_client import get_shadow_comparison
                shadow = await get_shadow_comparison()
            except (ImportError, Exception) as e:
                _logger_a.warning("[Shadow알림] shadow 데이터 조회 실패 — 스킵: %s", e)
                continue

            mock_data = shadow.get("mock", {})
            if not mock_data.get("available"):
                continue

            # 2주 수익률 히스토리 추적 (DB에 보관)
            mock_history = load_setting("shadow_mock_history") or []
            today_entry = {
                "date": now.strftime("%Y-%m-%d"),
                "total_eval": mock_data.get("total_eval", 0),
                "cash": mock_data.get("cash", 0),
            }
            mock_history.append(today_entry)
            mock_history = mock_history[-30:]  # 30일치만 보관
            save_setting("shadow_mock_history", mock_history)

            # 2주(14일) 전 데이터와 비교
            if len(mock_history) >= 14:
                old_entry = mock_history[-14]
                old_eval = old_entry.get("total_eval", 0)
                new_eval = today_entry.get("total_eval", 0)

                if old_eval > 0:
                    profit_rate = (new_eval - old_eval) / old_eval * 100

                    if profit_rate >= 5.0:  # B안: 2주 +5% 이상 기준
                        msg = (
                            f"[Shadow Trading 알림]\n\n"
                            f"모의투자 2주 수익률: +{profit_rate:.1f}% 달성!\n"
                            f"기준: 2주 +5% 이상 -> 실거래 전환 추천\n\n"
                            f"모의 현재 평가액: {new_eval:,}원\n"
                            f"2주 전 평가액: {old_eval:,}원\n\n"
                            f"전략실 -> '실거래/모의 비교' 탭에서 확인하세요."
                        )
                        if app_state.telegram_app:
                            ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
                            if ceo_id:
                                try:
                                    await app_state.telegram_app.bot.send_message(
                                        chat_id=int(ceo_id),
                                        text=msg,
                                    )
                                    _logger_a.info(
                                        "[Shadow알림] 실거래 전환 추천 알림 발송 (수익률 %.1f%%)", profit_rate
                                    )
                                    save_activity_log(
                                        "system",
                                        f"Shadow Trading 알림: +{profit_rate:.1f}%",
                                        "info",
                                    )
                                except Exception as e:
                                    _logger_a.error("[Shadow알림] 텔레그램 발송 실패: %s", e)

        except Exception as e:
            _logger_a.error("[Shadow알림] 에러: %s", e)
            await asyncio.sleep(3600)

# ── 실시간 환율 갱신 ──
_FX_UPDATE_INTERVAL = 3600  # 1시간마다 갱신
# app_state.last_fx_update → app_state.last_fx_update 직접 사용

async def _update_fx_rate():
    """yfinance로 USD/KRW 실시간 환율을 가져와 DB에 저장합니다."""

    try:
        import yfinance as yf
        ticker = yf.Ticker("USDKRW=X")
        hist = ticker.history(period="1d")
        if not hist.empty:
            rate = round(float(hist.iloc[-1]["Close"]), 2)
            if 1000 < rate < 2000:  # 비정상 값 필터
                old_rate = _get_fx_rate()
                save_setting("fx_rate_usd_krw", rate)
                app_state.last_fx_update = time.time()
                if abs(rate - old_rate) >= 1:
                    _log(f"[FX] 환율 갱신: ${1} = ₩{rate:,.2f} (이전: ₩{old_rate:,.2f})")
                    save_activity_log("system", f"💱 환율 갱신: ₩{rate:,.2f}/$ (이전 ₩{old_rate:,.2f})", "info")
                return rate
    except ImportError:
        _log("[FX] yfinance 미설치 — 환율 갱신 불가")
    except Exception as e:
        _log(f"[FX] 환율 갱신 실패: {e}")
    return None


def _get_fx_rate() -> float:
    """USD/KRW 환율 반환. DB 설정값 우선, 없으면 1450 폴백.

    모든 환율 참조에서 이 함수를 사용합니다 (하드코딩 방지).
    """
    try:
        rate = load_setting("fx_rate_usd_krw", 1450)
        if isinstance(rate, (int, float)) and 1000 < rate < 2000:
            return float(rate)
    except Exception as e:
        logger.debug("환율 조회 실패: %s", e)
    return 1450.0



# ── 자동매매 시스템 (KIS 한국투자증권 프레임워크) ──

# app_state.trading_bot_active, app_state.trading_bot_task → app_state 직접 사용

# ── 시세 캐시 → app_state 사용 ──
_price_cache = app_state.price_cache
_price_cache_lock = app_state.price_cache_lock


async def _auto_refresh_prices():
    """관심종목 시세를 1분마다 자동 갱신."""
    while True:
        try:
            await asyncio.sleep(60)
            watchlist = _load_data("trading_watchlist", [])
            if not watchlist:
                continue

            new_cache = {}
            kr_tickers = [w for w in watchlist if w.get("market", "KR") == "KR"]
            us_tickers = [w for w in watchlist if w.get("market") == "US"]

            # 한국 주식 (pykrx)
            if kr_tickers:
                try:
                    from pykrx import stock as pykrx_stock
                    today = datetime.now(KST).strftime("%Y%m%d")
                    start = (datetime.now(KST) - timedelta(days=7)).strftime("%Y%m%d")
                    for w in kr_tickers:
                        try:
                            df = await asyncio.to_thread(
                                pykrx_stock.get_market_ohlcv_by_date, start, today, w["ticker"]
                            )
                            if df is not None and not df.empty:
                                latest = df.iloc[-1]
                                prev = df.iloc[-2] if len(df) >= 2 else latest
                                close = int(latest["종가"])
                                prev_close = int(prev["종가"])
                                change = close - prev_close
                                change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
                                new_cache[w["ticker"]] = {
                                    "price": close,
                                    "change_pct": change_pct,
                                    "updated_at": datetime.now(KST).isoformat(),
                                }
                        except Exception as e:
                            logger.debug("국내 종목 시세 파싱 실패 (%s): %s", w.get("ticker"), e)
                except Exception as e:
                    logger.debug("pykrx 시세 조회 실패: %s", e)

            # 미국 주식 (yfinance)
            if us_tickers:
                try:
                    import yfinance as yf
                    for w in us_tickers:
                        try:
                            ticker_obj = yf.Ticker(w["ticker"])
                            hist = await asyncio.to_thread(
                                lambda t=ticker_obj: t.history(period="5d")
                            )
                            if hist is not None and not hist.empty:
                                latest = hist.iloc[-1]
                                prev = hist.iloc[-2] if len(hist) >= 2 else latest
                                close = round(float(latest["Close"]), 2)
                                prev_close = round(float(prev["Close"]), 2)
                                change = round(close - prev_close, 2)
                                change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
                                new_cache[w["ticker"]] = {
                                    "price": close,
                                    "change_pct": change_pct,
                                    "updated_at": datetime.now(KST).isoformat(),
                                }
                        except Exception as e:
                            logger.debug("해외 종목 시세 파싱 실패 (%s): %s", w.get("ticker"), e)
                except Exception as e:
                    logger.debug("yfinance 시세 조회 실패: %s", e)

            if new_cache:
                async with _price_cache_lock:
                    _price_cache.update(new_cache)
                _log(f"[PRICE] 시세 자동 갱신 완료 — {len(new_cache)}종목")
        except Exception as e:
            _log(f"[PRICE] 시세 자동 갱신 오류: {e}")
            await asyncio.sleep(60)


def _default_portfolio() -> dict:
    """기본 포트폴리오 데이터."""
    return {
        "cash": 50_000_000,    # 초기 현금 (5천만원)
        "initial_cash": 50_000_000,
        "holdings": [],        # [{ticker, name, qty, avg_price, current_price}]
        "updated_at": datetime.now(KST).isoformat(),
    }


# ── 투자 성향 시스템 (CEO B안 승인: 성향 + CIO 자율) ──

# 성향별 안전 범위 — CIO가 이 범위 안에서만 자유롭게 변경 가능
RISK_PROFILES = {
    "aggressive": {
        "label": "공격적", "emoji": "🔥",
        "cash_reserve":       {"min": 5,  "max": 20,  "default": 10},
        "max_position_pct":   {"min": 15, "max": 35,  "default": 30},
        "min_confidence":     {"min": 50, "max": 75,  "default": 55},
        "default_stop_loss":  {"min": -12,"max": -3,  "default": -8},
        "default_take_profit":{"min": 5,  "max": 40,  "default": 15},
        "max_daily_trades":   {"min": 5,  "max": 20,  "default": 15},
        "max_daily_loss_pct": {"min": 2,  "max": 8,   "default": 5},
        "order_size":         {"min": 0,  "max": 10_000_000, "default": 0},
    },
    "balanced": {
        "label": "균형", "emoji": "⚖️",
        "cash_reserve":       {"min": 15, "max": 35,  "default": 20},
        "max_position_pct":   {"min": 10, "max": 25,  "default": 20},
        "min_confidence":     {"min": 55, "max": 80,  "default": 65},
        "default_stop_loss":  {"min": -8, "max": -2,  "default": -5},
        "default_take_profit":{"min": 5,  "max": 25,  "default": 10},
        "max_daily_trades":   {"min": 3,  "max": 15,  "default": 10},
        "max_daily_loss_pct": {"min": 1,  "max": 5,   "default": 3},
        "order_size":         {"min": 0,  "max": 5_000_000, "default": 0},
    },
    "conservative": {
        "label": "보수적", "emoji": "🐢",
        "cash_reserve":       {"min": 30, "max": 60,  "default": 40},
        "max_position_pct":   {"min": 5,  "max": 15,  "default": 10},
        "min_confidence":     {"min": 65, "max": 90,  "default": 75},
        "default_stop_loss":  {"min": -5, "max": -1,  "default": -3},
        "default_take_profit":{"min": 3,  "max": 15,  "default": 8},
        "max_daily_trades":   {"min": 1,  "max": 8,   "default": 5},
        "max_daily_loss_pct": {"min": 1,  "max": 3,   "default": 2},
        "order_size":         {"min": 0,  "max": 2_000_000, "default": 0},
    },
}


def _get_risk_profile() -> str:
    """현재 투자 성향 조회 (DB에서)."""
    return load_setting("trading_risk_profile", "aggressive")


def _clamp_setting(key: str, value, profile: str = None) -> float | int:
    """설정값을 현재 투자 성향의 안전 범위 내로 클램핑합니다."""
    if profile is None:
        profile = _get_risk_profile()
    ranges = RISK_PROFILES.get(profile, RISK_PROFILES["balanced"])
    r = ranges.get(key)
    if r is None:
        return value
    return max(r["min"], min(r["max"], value))


def _default_trading_settings() -> dict:
    """기본 자동매매 설정."""
    return {
        "max_position_pct": 20,       # 종목당 최대 비중 (%)
        "max_daily_trades": 10,       # 일일 최대 거래 횟수
        "max_daily_loss_pct": 3,      # 일일 최대 손실 (%)
        "default_stop_loss_pct": -5,  # 기본 손절 (%)
        "default_take_profit_pct": 10, # 기본 익절 (%)
        "order_size": 0,              # 0 = CIO 비중 자율
        "trading_hours_kr": {"start": "09:00", "end": "15:20"},   # 한국 장 시간
        "trading_hours_us": {"start": "22:30", "end": "05:00"},   # 미국 장 시간 (KST 기준, 서머타임 시 23:30)
        "trading_hours": {"start": "09:00", "end": "15:20"},      # 하위호환
        "auto_stop_loss": True,       # 자동 손절 활성화
        "auto_take_profit": True,     # 자동 익절 활성화
        "auto_execute": False,        # CIO 시그널 기반 자동 주문 실행 (안전장치: 기본 OFF)
        # --- 신뢰도 임계값 (연구 기반 조정) ---
        # 근거: LLM은 실제 정확도보다 10~20% 과신 (FinGPT 2023, GPT-4 Trading 2024 논문)
        # 한국장 손익비 1:2 (손절 -5%, 익절 +10%) → 손익분기 승률 ≒ 33%
        # LLM 실제 방향성 예측 정확도 55~65% → 임계값 65% = 과신 할인 적용 후 최소 수익선
        "min_confidence": 65,         # 자동매매 최소 신뢰도 (%, 연구 기반: 기존 70→65)
        "kis_connected": False,       # KIS(한국투자증권) API 연결 여부
        "paper_trading": True,        # 모의투자 모드 (실거래 전)
        "enable_real": True,          # 실거래 계좌에 주문
        "enable_mock": False,         # 모의투자 계좌에 주문
        # --- AI 자기보정(Self-Calibration) ---
        # 원리: Platt Scaling 단순화 — 실제 승률/예측 신뢰도 비율로 보정 계수 계산
        # factor < 1.0: AI 과신 → 유효 신뢰도 하향 보정 / factor > 1.0: AI 겸손 → 상향
        "calibration_enabled": True,  # AI 자기보정 활성화
        "calibration_lookback": 20,   # 보정 계산에 사용할 최근 거래 수
    }


def _compute_calibration_factor(lookback: int = 20) -> dict:
    """실제 승률 vs 예측 신뢰도 비율로 AI 자기보정 계수를 계산합니다.

    방법론: Platt Scaling 단순화 버전
    - LLM은 예측 신뢰도를 실제 정확도보다 과대 보고하는 경향이 있음
      (FinGPT 2023 / GPT-4 Trading 2024 논문에서 10~20% 과신 확인)
    - 보정 계수(factor) = 실제 승률 / 예측 평균 신뢰도
    - factor < 1: AI 과신 → 유효 신뢰도 하향 / factor > 1: AI 겸손 → 상향
    - 안전 범위: 0.5 ~ 1.5 (극단적 보정 방지)
    """
    import re as _re
    history = _load_data("trading_history", [])
    bot_trades = [
        h for h in history
        if h.get("auto_bot", False) or "신뢰도" in h.get("strategy", "")
    ]
    recent = bot_trades[:lookback]

    if len(recent) < 5:
        return {
            "factor": 1.0, "win_rate": None, "avg_confidence": None,
            "n": len(recent), "note": f"데이터 부족 ({len(recent)}건, 최소 5건 필요) — 보정 미적용",
        }

    closed = [h for h in recent if h.get("action") == "sell" and "pnl" in h]
    if not closed:
        return {
            "factor": 1.0, "win_rate": None, "avg_confidence": None,
            "n": 0, "note": "평가 가능한 매도 기록 없음 — 보정 미적용",
        }

    wins = sum(1 for t in closed if t.get("pnl", 0) > 0)
    actual_win_rate = wins / len(closed)

    confidences = []
    for t in closed:
        m = _re.search(r"신뢰도\s*(\d+)", t.get("strategy", ""))
        if m:
            confidences.append(int(m.group(1)) / 100.0)

    if not confidences:
        return {
            "factor": 1.0, "win_rate": round(actual_win_rate * 100, 1),
            "avg_confidence": None, "n": len(closed),
            "note": "신뢰도 기록 없음 — 보정 미적용",
        }

    avg_confidence = sum(confidences) / len(confidences)
    raw_factor = actual_win_rate / avg_confidence if avg_confidence > 0 else 1.0
    factor = round(max(0.5, min(1.5, raw_factor)), 3)

    diff = actual_win_rate * 100 - avg_confidence * 100
    if diff < -5:
        note = f"AI 과신 (예측 {avg_confidence*100:.0f}% → 실제 {actual_win_rate*100:.0f}%) → 신뢰도 {factor:.2f}배 하향 보정"
    elif diff > 5:
        note = f"AI 겸손 (예측 {avg_confidence*100:.0f}% → 실제 {actual_win_rate*100:.0f}%) → 신뢰도 {factor:.2f}배 상향 보정"
    else:
        note = f"AI 보정 미미 (예측≒실제, factor={factor:.2f})"

    return {
        "factor": factor,
        "win_rate": round(actual_win_rate * 100, 1),
        "avg_confidence": round(avg_confidence * 100, 1),
        "n": len(closed),
        "note": note,
    }


def _build_calibration_prompt_section(settings: dict | None = None) -> str:
    """CIO 분석 프롬프트에 삽입할 자기학습 보정 섹션을 구축합니다.

    포함 항목:
    1. 기존 Platt Scaling 보정 (호환성)
    2. 베이지안 구간별 보정 데이터
    3. 전문가 ELO 가중치
    4. 오답 패턴 경고
    5. 도구 추천/경고
    """
    from db import (
        get_all_calibration_buckets, get_all_analyst_elos,
        get_active_error_patterns, get_tool_effectiveness_all,
    )

    if settings is None:
        settings = {}

    parts = []

    # ─ 1. 베이지안 구간별 보정 ─
    try:
        buckets = get_all_calibration_buckets()
        if buckets:
            rows = []
            for b in buckets:
                total = b.get("total_count", 0)
                if total < 3:
                    continue
                actual = b.get("actual_rate", 0)
                ci_lo = b.get("ci_lower", 0)
                ci_hi = b.get("ci_upper", 1)
                actual_pct = round(actual * 100, 1)
                ci_lo_pct = round(ci_lo * 100)
                ci_hi_pct = round(ci_hi * 100)
                # 보정 방향 판단
                bucket_label = b["bucket"]
                mid = 0.5  # 기본
                try:
                    lo, hi = bucket_label.split("-")
                    mid = (int(lo) + int(hi)) / 200.0
                except Exception:
                    pass
                if actual < mid - 0.05:
                    direction = "↓ 하향 보정 필요"
                elif actual > mid + 0.05:
                    direction = "↑ 상향 가능"
                else:
                    direction = "≈ 적정"
                rows.append(f"| {bucket_label}% | {total}건 | {actual_pct}% | [{ci_lo_pct}-{ci_hi_pct}%] | {direction} |")

            if rows:
                parts.append(
                    "\n## 📊 신뢰도 보정 데이터 (Bayesian Calibration)\n"
                    "| 구간 | 예측 횟수 | 실제 적중률 | 95% CI | 보정 방향 |\n"
                    "|------|----------|-----------|--------|----------|\n"
                    + "\n".join(rows)
                    + "\n→ 위 데이터를 참고하여 신뢰도 수치를 보정하세요."
                )
    except Exception:
        pass

    # ─ 2. 전문가 ELO 가중치 ─
    try:
        elos = get_all_analyst_elos()
        if elos and len(elos) >= 2:
            elo_rows = []
            for e in sorted(elos, key=lambda x: x.get("elo_rating", 1500), reverse=True):
                agent = e["agent_id"].replace("_specialist", "").replace("_", " ").title()
                rating = round(e.get("elo_rating", 1500))
                total = e.get("total_predictions", 0)
                correct = e.get("correct_predictions", 0)
                hit = round(correct / total * 100) if total > 0 else 0
                weight = "★★★" if rating >= 1560 else ("★★" if rating >= 1520 else "★")
                elo_rows.append(f"| {agent} | {rating} | {hit}% ({correct}/{total}) | {weight} |")

            if elo_rows:
                parts.append(
                    "\n## 🏆 전문가 신뢰 가중치 (ELO 기반)\n"
                    "| 전문가 | ELO | 적중률 | 가중치 |\n"
                    "|--------|-----|--------|--------|\n"
                    + "\n".join(elo_rows)
                    + "\n→ ELO 높은 전문가의 의견에 더 높은 가중치를 부여하세요."
                )
    except Exception:
        pass

    # ─ 3. 오답 패턴 경고 ─
    try:
        patterns = get_active_error_patterns()
        if patterns:
            warns = []
            for p in patterns[:5]:
                warns.append(f"- {p['description']}")
            parts.append(
                "\n## ⚠️ 주의 패턴 (최근 오류에서 학습)\n"
                + "\n".join(warns)
            )
    except Exception:
        pass

    # ─ 4. 도구 추천/경고 ─
    try:
        tools = get_tool_effectiveness_all()
        if tools and len(tools) >= 3:
            good = [t for t in tools if t.get("total_uses", 0) >= 3 and t.get("eff_score", 0.5) >= 0.6]
            bad = [t for t in tools if t.get("total_uses", 0) >= 3 and t.get("eff_score", 0.5) < 0.45]
            tool_lines = []
            if good:
                good_s = sorted(good, key=lambda x: x["eff_score"], reverse=True)[:4]
                names = ", ".join(f"{t['tool_name']}({round(t['eff_score']*100)}%)" for t in good_s)
                tool_lines.append(f"- 우수: {names}")
            if bad:
                bad_s = sorted(bad, key=lambda x: x["eff_score"])[:3]
                names = ", ".join(f"{t['tool_name']}({round(t['eff_score']*100)}%)" for t in bad_s)
                tool_lines.append(f"- 부진: {names} — 분석 참고만, 결정 기반 금지")
            if tool_lines:
                parts.append(
                    "\n## 🔧 도구 추천 (성과 기반)\n"
                    + "\n".join(tool_lines)
                )
    except Exception:
        pass

    # ─ 5. 기존 Platt Scaling 보정 (하위 호환) ─
    if settings.get("calibration_enabled", True):
        calibration = _compute_calibration_factor(settings.get("calibration_lookback", 20))
        if calibration.get("win_rate") is not None:
            diff = calibration["win_rate"] - (calibration.get("avg_confidence") or calibration["win_rate"])
            direction = "보수적으로" if diff < -5 else ("적극적으로" if diff > 5 else "현재 수준으로")
            parts.append(
                f"\n## 📈 매매 성과 보정 (Platt Scaling)\n"
                f"- 최근 {calibration['n']}건 실제 승률: {calibration['win_rate']}%\n"
                f"- 평균 예측 신뢰도: {calibration.get('avg_confidence', 'N/A')}%\n"
                f"- {calibration['note']}\n"
                f"→ 이번 신뢰도를 {direction} 설정하세요."
            )

    return "\n".join(parts) if parts else ""


# ── [QUANT SCORE] 정량 신뢰도 계산 (RSI/MACD/볼린저밴드/거래량/이동평균) ──

async def _compute_quant_score(ticker: str, market: str = "KR", lookback: int = 60) -> dict:
    """RSI(14)/MACD(12,26,9)/볼린저밴드(20,2σ)/거래량/이동평균으로 정량 신뢰도 계산.

    LLM이 신뢰도를 직접 찍는 대신, 이 함수 계산값을 기준으로 ±20%p 조정만 허용.
    반환: {ticker, direction, quant_confidence(0-99), components, summary, error}
    """
    _err = {
        "ticker": ticker, "direction": "neutral", "quant_confidence": 50,
        "components": {}, "summary": "정량 데이터 없음 — AI 판단 사용", "error": None,
    }
    try:
        closes: list = []
        volumes: list = []

        if market == "KR":
            try:
                from pykrx import stock as _pykrx
                _today = datetime.now(KST).strftime("%Y%m%d")
                _start = (datetime.now(KST) - timedelta(days=lookback + 30)).strftime("%Y%m%d")
                df = await asyncio.to_thread(_pykrx.get_market_ohlcv_by_date, _start, _today, ticker)
                if df is None or df.empty or len(df) < 20:
                    return {**_err, "error": f"pykrx 데이터 부족 ({0 if df is None else len(df)}일)"}
                closes = df["종가"].astype(float).tolist()
                volumes = df["거래량"].astype(float).tolist()
            except Exception as e:
                return {**_err, "error": f"pykrx: {str(e)[:60]}"}
        else:
            try:
                import yfinance as yf
                _t = yf.Ticker(ticker)
                hist = await asyncio.to_thread(lambda: _t.history(period="3mo"))
                if hist is None or hist.empty or len(hist) < 20:
                    return {**_err, "error": "yfinance 데이터 부족"}
                closes = hist["Close"].astype(float).tolist()
                volumes = hist["Volume"].astype(float).tolist()
            except Exception as e:
                return {**_err, "error": f"yfinance: {str(e)[:60]}"}

        n = len(closes)

        # ── RSI(14) ──
        def _rsi(prices, p=14):
            if len(prices) < p + 1:
                return 50.0
            d = [prices[i] - prices[i-1] for i in range(1, len(prices))]
            g = [max(x, 0.0) for x in d[-p:]]
            l = [abs(min(x, 0.0)) for x in d[-p:]]
            ag, al = sum(g)/p, sum(l)/p
            return 100.0 if al == 0 else 100 - 100/(1 + ag/al)

        rsi = _rsi(closes)

        # ── RSI → 방향 투표 (방향과 신뢰도 분리) ──
        if   rsi < 30: rsi_dir, rsi_str, rsi_sig = "buy",  0.8, f"과매도({rsi:.1f})"
        elif rsi < 40: rsi_dir, rsi_str, rsi_sig = "buy",  0.5, f"매수우호({rsi:.1f})"
        elif rsi < 45: rsi_dir, rsi_str, rsi_sig = "neutral", 0.2, f"중립({rsi:.1f})"
        elif rsi < 55: rsi_dir, rsi_str, rsi_sig = "neutral", 0.1, f"중립({rsi:.1f})"
        elif rsi < 60: rsi_dir, rsi_str, rsi_sig = "neutral", 0.2, f"중립({rsi:.1f})"
        elif rsi < 70: rsi_dir, rsi_str, rsi_sig = "sell", 0.5, f"매도우호({rsi:.1f})"
        else:          rsi_dir, rsi_str, rsi_sig = "sell", 0.8, f"과매수({rsi:.1f})"

        # ── MACD(12, 26, 9) → 방향 투표 ──
        def _ema(prices, p):
            if len(prices) < p:
                return [prices[-1]]
            k = 2 / (p + 1)
            vals = [sum(prices[:p]) / p]
            for x in prices[p:]:
                vals.append(x * k + vals[-1] * (1 - k))
            return vals

        macd_dir, macd_str, macd_sig = "neutral", 0.1, "데이터부족"
        if n >= 27:
            e12 = _ema(closes, 12)
            e26 = _ema(closes, 26)
            ml = min(len(e12), len(e26))
            macd_line = [e12[i] - e26[i] for i in range(-ml, 0)]
            if len(macd_line) >= 9:
                sig_line = _ema(macd_line, 9)
                if sig_line:
                    mv, sv = macd_line[-1], sig_line[-1]
                    mv2 = macd_line[-2] if len(macd_line) >= 2 else mv
                    sv2 = sig_line[-2] if len(sig_line) >= 2 else sv
                    if   mv2 < sv2 and mv > sv:           macd_dir, macd_str, macd_sig = "buy",  0.9, "골든크로스↑"
                    elif mv2 > sv2 and mv < sv:           macd_dir, macd_str, macd_sig = "sell", 0.9, "데드크로스↓"
                    elif mv > sv and (mv-sv) > (mv2-sv2): macd_dir, macd_str, macd_sig = "buy",  0.6, "MACD>시그널상승"
                    elif mv > sv:                         macd_dir, macd_str, macd_sig = "buy",  0.3, "MACD>시그널"
                    elif mv < sv and (mv-sv) < (mv2-sv2): macd_dir, macd_str, macd_sig = "sell", 0.6, "MACD<시그널하락"
                    else:                                 macd_dir, macd_str, macd_sig = "sell", 0.3, "MACD<시그널"

        # ── 볼린저밴드(20, 2σ) → 방향 투표 ──
        bb_dir, bb_str, bb_sig, pct_b = "neutral", 0.1, "데이터부족", 0.5
        if n >= 20:
            sma = sum(closes[-20:]) / 20
            std = (sum((c - sma)**2 for c in closes[-20:]) / 20) ** 0.5
            bw = 4 * std
            if bw > 0:
                pct_b = (closes[-1] - (sma - 2*std)) / bw
                if   pct_b <= 0.10: bb_dir, bb_str, bb_sig = "buy",  0.9, f"하단돌파(%B={pct_b:.2f})"
                elif pct_b <= 0.25: bb_dir, bb_str, bb_sig = "buy",  0.6, f"하단근접(%B={pct_b:.2f})"
                elif pct_b <= 0.40: bb_dir, bb_str, bb_sig = "buy",  0.2, f"중하단(%B={pct_b:.2f})"
                elif pct_b <= 0.60: bb_dir, bb_str, bb_sig = "neutral", 0.1, f"중간(%B={pct_b:.2f})"
                elif pct_b <= 0.75: bb_dir, bb_str, bb_sig = "sell", 0.2, f"중상단(%B={pct_b:.2f})"
                elif pct_b <= 0.90: bb_dir, bb_str, bb_sig = "sell", 0.6, f"상단근접(%B={pct_b:.2f})"
                else:               bb_dir, bb_str, bb_sig = "sell", 0.9, f"상단돌파(%B={pct_b:.2f})"

        # ── 거래량 (방향 아닌 확신 보정용) ──
        vol_adj, vol_sig = 0, "보통"
        vol_ratio = 1.0
        if n >= 20 and len(volumes) >= 20:
            avg_v = sum(volumes[-20:-1]) / 19
            if avg_v > 0:
                vol_ratio = volumes[-1] / avg_v
                if   vol_ratio >= 2.0: vol_adj, vol_sig = 8,  f"급증({vol_ratio:.1f}x)"
                elif vol_ratio >= 1.5: vol_adj, vol_sig = 5,  f"증가({vol_ratio:.1f}x)"
                elif vol_ratio < 0.8:  vol_adj, vol_sig = -5, f"감소({vol_ratio:.1f}x)"
                else:                  vol_sig = f"보통({vol_ratio:.1f}x)"

        # ── 이동평균 추세 → 방향 투표 ──
        ma5  = round(sum(closes[-5:]) /5)  if n >= 5  else 0
        ma20 = round(sum(closes[-20:])/20) if n >= 20 else 0
        ma60 = round(sum(closes[-60:])/60) if n >= 60 else 0
        if ma5 and ma20 and ma60:
            if   ma5 > ma20 > ma60: tr_dir, tr_str, tr_sig = "buy",  0.8, "상승정렬(5>20>60)"
            elif ma5 > ma20:        tr_dir, tr_str, tr_sig = "buy",  0.4, "단기반등"
            elif ma5 < ma20 < ma60: tr_dir, tr_str, tr_sig = "sell", 0.8, "하락정렬(5<20<60)"
            else:                   tr_dir, tr_str, tr_sig = "neutral", 0.2, "혼조세"
        elif ma5 and ma20:
            if ma5 > ma20: tr_dir, tr_str, tr_sig = "buy",  0.4, "단기상승"
            else:          tr_dir, tr_str, tr_sig = "sell", 0.4, "단기하락"
        else:
            tr_dir, tr_str, tr_sig = "neutral", 0.1, "데이터부족"

        # ── 종합: 방향 = 다수결, 신뢰도 = 합의율 ──
        votes = [
            ("RSI",  rsi_dir,  rsi_str),
            ("MACD", macd_dir, macd_str),
            ("BB",   bb_dir,   bb_str),
            ("MA",   tr_dir,   tr_str),
        ]
        buy_votes  = [(nm, st) for nm, d, st in votes if d == "buy"]
        sell_votes = [(nm, st) for nm, d, st in votes if d == "sell"]
        n_votes = len(votes)

        if len(buy_votes) > len(sell_votes):
            direction = "buy"
            winner_count = len(buy_votes)
            winner_avg_str = sum(s for _, s in buy_votes) / len(buy_votes)
        elif len(sell_votes) > len(buy_votes):
            direction = "sell"
            winner_count = len(sell_votes)
            winner_avg_str = sum(s for _, s in sell_votes) / len(sell_votes)
        else:
            direction = "neutral"
            winner_count = 0
            winner_avg_str = 0.3

        # 합의율 → 기본 신뢰도 (30~90% 범위)
        if direction == "neutral":
            base_conf = 50
        else:
            consensus = winner_count / n_votes  # 0.25~1.0
            base_conf = 35 + consensus * 55     # 1/4→49, 2/4→63, 3/4→76, 4/4→90
            # 강도 보정: 같은 3/4라도 신호 강도가 다름
            strength_adj = (winner_avg_str - 0.5) * 10  # -5 ~ +4
            base_conf += strength_adj

        qconf = int(max(30, min(95, base_conf + vol_adj)))
        dir_kr = {"buy": "매수", "sell": "매도", "neutral": "관망"}[direction]
        vote_detail = " / ".join(
            f"{nm}→{'매수' if d == 'buy' else '매도' if d == 'sell' else '중립'}"
            for nm, d, _ in votes
        )
        summary = (
            f"RSI {rsi:.0f} / MACD {macd_sig} / BB {bb_sig} / 거래량 {vol_sig}"
            f" → 투표 [{vote_detail}] = {winner_count}/{n_votes} 합의"
            f" → 정량신뢰도 {qconf}%({dir_kr})"
        )
        return {
            "ticker": ticker, "direction": direction, "quant_confidence": qconf,
            "components": {
                "rsi":       {"value": round(rsi, 1), "direction": rsi_dir, "strength": rsi_str, "signal": rsi_sig},
                "macd":      {"direction": macd_dir, "strength": macd_str, "signal": macd_sig},
                "bollinger": {"pct_b": round(pct_b, 2), "direction": bb_dir, "strength": bb_str, "signal": bb_sig},
                "volume":    {"ratio": round(vol_ratio, 1), "adj": vol_adj, "signal": vol_sig},
                "trend":     {"ma5": ma5, "ma20": ma20, "ma60": ma60, "direction": tr_dir, "strength": tr_str, "signal": tr_sig},
            },
            "votes": {"buy": len(buy_votes), "sell": len(sell_votes), "neutral": n_votes - len(buy_votes) - len(sell_votes)},
            "summary": summary, "error": None,
        }
    except Exception as e:
        return {**_err, "error": f"계산오류: {str(e)[:80]}"}


async def _build_quant_prompt_section(market_watchlist: list, market: str = "KR") -> str:
    """관심종목 전체 정량지표를 병렬 계산 → 프롬프트 삽입용 테이블 반환."""
    if not market_watchlist:
        return ""
    try:
        tasks = [_compute_quant_score(w["ticker"], market) for w in market_watchlist]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        rows = []
        for w, r in zip(market_watchlist, results):
            if isinstance(r, Exception) or (isinstance(r, dict) and r.get("error")):
                rows.append(
                    f"| {w['name']}({w['ticker']}) | 조회실패 | — | — | — | — | — | **50% 판단불가** |"
                )
                continue
            c = r["components"]
            d_kr = {"buy": "매수", "sell": "매도", "neutral": "관망"}[r["direction"]]
            v = r.get("votes", {})
            vote_str = f"매수{v.get('buy',0)}:매도{v.get('sell',0)}:중립{v.get('neutral',0)}"
            rows.append(
                f"| {w['name']}({w['ticker']}) "
                f"| {c['rsi']['signal']} "
                f"| {c['macd']['signal']} "
                f"| {c['bollinger']['signal']} "
                f"| {c['volume']['signal']} "
                f"| {c['trend']['signal']} "
                f"| {vote_str} "
                f"| **{r['quant_confidence']}% {d_kr}** |"
            )
        return (
            "\n\n## 📐 정량지표 사전분석 (서버 자동계산 — 지표 합의 방식)\n"
            "| 종목 | RSI(14) | MACD | 볼린저밴드 | 거래량 | 추세(MA) | 지표투표 | 합의신뢰도 |\n"
            "|------|---------|------|-----------|--------|---------|---------|------------|\n"
            + "\n".join(rows)
            + "\n\n⚠️ 위 합의신뢰도는 4개 기술지표의 방향 합의율입니다."
            " 뉴스/실적/수급/매크로 등 정성분석을 반영하여 **±20%p 범위 내**에서 조정하세요."
            " 근거를 반드시 명시하세요."
        )
    except Exception as e:
        return f"\n\n## 📐 정량지표 (계산 실패: {str(e)[:60]})\n"


async def _build_dcf_risk_prompt_section(market_watchlist: list, market: str = "KR") -> str:
    """종목별 DCF 가치평가 + 리스크 분석을 서버가 사전 계산하여 프롬프트에 주입.

    pool.invoke()로 Python 계산 도구를 직접 실행합니다 (AI 호출 아님).
    """
    pool = _init_tool_pool()
    if not pool:
        return ""

    async def _calc_one(w):
        ticker = w["ticker"]
        name = w["name"]
        try:
            if market == "KR":
                dcf_r, risk_r = await asyncio.gather(
                    pool.invoke("dcf_valuator", caller_id="fin_analyst", action="all", ticker=ticker),
                    pool.invoke("risk_calculator", caller_id="fin_analyst", action="full", ticker=ticker),
                )
            else:
                dcf_r, risk_r = await asyncio.gather(
                    pool.invoke("us_financial_analyzer", caller_id="fin_analyst", action="dcf", ticker=ticker),
                    pool.invoke("risk_calculator", caller_id="fin_analyst", action="full", ticker=ticker),
                )
            # 결과를 종목당 800자로 요약 (프롬프트 토큰 절약)
            return f"### {name}({ticker})\n**[DCF 가치평가]**\n{str(dcf_r)[:800]}\n**[리스크 분석]**\n{str(risk_r)[:800]}"
        except Exception as e:
            return f"### {name}({ticker})\n사전계산 오류: {str(e)[:100]}"

    try:
        tasks = [_calc_one(w) for w in market_watchlist]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r for r in results if isinstance(r, str)]
        if not valid:
            return ""
        return (
            "\n\n## 📊 [서버 사전계산] DCF 가치평가 + 리스크 분석\n"
            "아래 결과는 서버가 Python으로 직접 계산한 것입니다. 이 수치를 기반으로 판단하세요.\n\n"
            + "\n\n".join(valid)
        )
    except Exception as e:
        logger.warning("[DCF/Risk 사전계산] 오류: %s", e)
        return ""


# ── [PRICE TRIGGERS] 목표가/손절/익절 자동 주문 ──

def _register_position_triggers(
    ticker: str, name: str, buy_price: float, qty: int,
    market: str, settings: dict, source_id: str = "",
) -> None:
    """매수 체결 후 자동 손절/익절 트리거 등록."""
    if buy_price <= 0 or qty <= 0:
        return
    sl_pct = settings.get("default_stop_loss_pct", -5)
    tp_pct = settings.get("default_take_profit_pct", 10)
    stop_price = round(buy_price * (1 + sl_pct / 100))
    take_price = round(buy_price * (1 + tp_pct / 100))
    now_str = datetime.now(KST).isoformat()
    base_id = f"{ticker}_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}"
    new_triggers = [
        {
            "id": f"sl_{base_id}", "ticker": ticker, "name": name,
            "type": "stop_loss", "trigger_price": stop_price, "qty": qty,
            "market": market, "active": True, "created_at": now_str,
            "source": "auto_buy", "source_id": source_id,
            "note": f"매수가 {buy_price:,.0f} × {1+sl_pct/100:.2f} = {stop_price:,.0f} 손절",
        },
        {
            "id": f"tp_{base_id}", "ticker": ticker, "name": name,
            "type": "take_profit", "trigger_price": take_price, "qty": qty,
            "market": market, "active": True, "created_at": now_str,
            "source": "auto_buy", "source_id": source_id,
            "note": f"매수가 {buy_price:,.0f} × {1+tp_pct/100:.2f} = {take_price:,.0f} 익절",
        },
    ]
    triggers = _load_data("price_triggers", [])
    triggers = new_triggers + triggers
    if len(triggers) > 500:
        triggers = triggers[:500]
    _save_data("price_triggers", triggers)
    save_activity_log(
        "fin_analyst",
        f"🎯 트리거 등록: {name} 손절 {stop_price:,.0f} / 익절 {take_price:,.0f} ({sl_pct}%/{tp_pct}%)",
        "info",
    )


async def _check_price_triggers() -> None:
    """1분마다 가격 모니터링 → 목표가 도달 시 자동 주문 실행."""
    triggers = _load_data("price_triggers", [])
    active = [t for t in triggers if t.get("active", True)]
    if not active:
        return

    settings = _load_data("trading_settings", _default_trading_settings())
    enable_real = settings.get("enable_real", False)
    enable_mock = settings.get("enable_mock", False)
    use_kis = _KIS_AVAILABLE and _kis_configured() and enable_real
    use_mock_kis = (not use_kis) and enable_mock and _KIS_AVAILABLE and _kis_mock_configured()

    async with _price_cache_lock:
        prices_snapshot = dict(_price_cache)

    triggered_ids: set = set()
    for t in active:
        ticker = t["ticker"]
        if ticker not in prices_snapshot:
            continue
        current_price = prices_snapshot[ticker]["price"]
        tp_val = t["trigger_price"]
        ttype  = t["type"]

        if   ttype == "stop_loss"   and current_price <= tp_val: pass
        elif ttype == "take_profit" and current_price >= tp_val: pass
        elif ttype == "buy_limit"   and current_price <= tp_val: pass
        else: continue

        action    = "buy" if ttype == "buy_limit" else "sell"
        action_kr = "매수" if action == "buy" else "매도"
        type_kr   = {"stop_loss": "🔴 손절", "take_profit": "✅ 익절", "buy_limit": "🎯 목표매수"}[ttype]
        name      = t.get("name", ticker)
        qty       = t.get("qty", 1)
        market    = t.get("market", "KR")
        is_us     = market == "US"

        save_activity_log(
            "fin_analyst",
            f"{type_kr} 발동: {name}({ticker}) 현재가 {current_price:,.0f} / 목표 {tp_val:,.0f} → {action_kr} {qty}주",
            "info",
        )
        try:
            order_result = {"success": False, "message": "미실행", "order_no": ""}
            if use_kis:
                order_result = await (
                    _kis_us_order(ticker, action, qty, price=current_price) if is_us
                    else _kis_order(ticker, action, qty, price=0)
                )
            elif use_mock_kis:
                order_result = await (
                    _kis_mock_us_order(ticker, action, qty, price=current_price) if is_us
                    else _kis_mock_order(ticker, action, qty, price=0)
                )
            else:
                portfolio = _load_data("trading_portfolio", _default_portfolio())
                if action == "sell":
                    holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
                    if holding and holding["qty"] >= qty:
                        sell_qty = min(qty, holding["qty"])
                        holding["qty"] -= sell_qty
                        if holding["qty"] == 0:
                            portfolio["holdings"] = [h for h in portfolio["holdings"] if h["ticker"] != ticker]
                        portfolio["cash"] += sell_qty * current_price
                        portfolio["updated_at"] = datetime.now(KST).isoformat()
                        _save_data("trading_portfolio", portfolio)
                        order_result = {"success": True, "order_no": "virtual"}
                elif action == "buy" and portfolio.get("cash", 0) >= current_price * qty:
                    holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
                    if holding:
                        old_total = holding["avg_price"] * holding["qty"]
                        holding["qty"] += qty
                        holding["avg_price"] = int((old_total + current_price * qty) / holding["qty"])
                        holding["current_price"] = int(current_price)
                    else:
                        portfolio["holdings"].append({
                            "ticker": ticker, "name": name, "qty": qty,
                            "avg_price": int(current_price), "current_price": int(current_price),
                            "market": market,
                        })
                    portfolio["cash"] -= current_price * qty
                    portfolio["updated_at"] = datetime.now(KST).isoformat()
                    _save_data("trading_portfolio", portfolio)
                    order_result = {"success": True, "order_no": "virtual"}

            if order_result["success"]:
                triggered_ids.add(t["id"])
                mode = "실거래" if use_kis else ("모의투자" if use_mock_kis else "가상")
                history = _load_data("trading_history", [])
                history.insert(0, {
                    "id": f"trigger_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}",
                    "date": datetime.now(KST).isoformat(),
                    "ticker": ticker, "name": name, "action": action,
                    "qty": qty, "price": current_price, "total": qty * current_price, "pnl": 0,
                    "strategy": f"{type_kr} 자동실행 ({mode})",
                    "status": "executed", "market": market,
                    "order_no": order_result.get("order_no", ""),
                })
                _save_data("trading_history", history)
                save_activity_log(
                    "fin_analyst",
                    f"✅ {type_kr} 자동{action_kr} 완료: {name} {qty}주 @ {current_price:,.0f} ({mode})",
                    "info",
                )
                if action == "buy":
                    _register_position_triggers(ticker, name, current_price, qty, market, settings,
                                                source_id=t["id"])
                # 반대쪽 트리거 비활성화 (손절 발동 → 익절 제거, 익절 발동 → 손절 제거)
                pair_prefix = "tp_" if ttype == "stop_loss" else ("sl_" if ttype == "take_profit" else "")
                base_key = t["id"].split("_", 1)[1] if "_" in t["id"] else ""
                if pair_prefix and base_key:
                    for other in triggers:
                        if other.get("active") and other["id"] == f"{pair_prefix}{base_key}":
                            other["active"] = False
            else:
                save_activity_log(
                    "fin_analyst",
                    f"❌ {type_kr} 주문 실패: {name} — {order_result.get('message','원인 불명')[:80]}",
                    "error",
                )
        except Exception as ex:
            save_activity_log(
                "fin_analyst",
                f"❌ {type_kr} 트리거 오류: {name} — {str(ex)[:80]}",
                "error",
            )

    if triggered_ids:
        for t in triggers:
            if t["id"] in triggered_ids:
                t["active"] = False
                t["triggered_at"] = datetime.now(KST).isoformat()
        _save_data("price_triggers", triggers)


# ── 트레이딩 CRUD 엔드포인트 → handlers/trading_handler.py로 분리 ──
# summary, portfolio, strategies, watchlist, prices, chart, order,
# history, signals, decisions (CRUD) 등은 trading_handler.py에서 제공


@trading_router.post("/api/trading/signals/generate")
async def generate_trading_signals():
    """투자팀장이 관심종목을 분석 → 매매 시그널 생성.

    흐름:
    1. 시황분석 Specialist → 거시경제/시장 분위기 분석
    2. 종목분석 Specialist → 재무제표/실적/밸류에이션 분석
    3. 기술적분석 Specialist → RSI/MACD/볼린저밴드/이평선 분석
    4. 리스크관리 Specialist → 손절/포지션/리스크 평가
    5. CIO가 4명 결과 취합 → 종목별 매수/매도/관망 판단
    """
    watchlist = _load_data("trading_watchlist", [])
    strategies = _load_data("trading_strategies", [])
    active_strategies = [s for s in strategies if s.get("active")]

    if not watchlist and not active_strategies:
        return {"success": False, "error": "관심종목이나 활성 전략이 없습니다"}

    # 종목 정보 정리 (한국/미국 구분)
    kr_tickers = [w for w in watchlist if w.get("market", "KR") == "KR"]
    us_tickers = [w for w in watchlist if w.get("market") == "US"]
    tickers_info = ", ".join([f"{w['name']}({w['ticker']})" for w in watchlist])
    strats_info = ", ".join([s["name"] for s in active_strategies[:5]])

    # 투자 성향 정보
    _profile = _get_risk_profile()
    _profile_info = RISK_PROFILES.get(_profile, RISK_PROFILES["balanced"])
    _profile_label = f"{_profile_info['label']} ({_profile})"
    _max_pos = _profile_info["max_position_pct"]["max"]
    _cash_reserve = _profile_info["cash_reserve"]["default"]

    # 정량지표 사전분석 (병렬 계산)
    _auto_market = "US" if (len(us_tickers) > len(kr_tickers)) else "KR"
    save_activity_log("fin_analyst", "📐 정량지표 사전계산 시작 (자동매매)...", "info")
    quant_section_auto = await _build_quant_prompt_section(watchlist, _auto_market)

    # ARGOS DB 수집 데이터 주입 (자동매매)
    save_activity_log("fin_analyst", "📡 ARGOS 수집 데이터 로딩 (자동매매)...", "info")
    argos_section_auto = await _build_argos_context_section(watchlist, _auto_market)

    # CIO에게 보내는 분석 명령
    prompt = f"""[자동매매 시스템] 관심종목 종합 분석을 요청합니다.

## CEO 투자 성향: {_profile_label} {_profile_info['emoji']}
- 종목당 최대 비중: {_max_pos}%
- 현금 유보: {_cash_reserve}%
- 전 종목 비중 합계 ≤ {100 - _cash_reserve}% (현금 유보분 제외)
- Kelly Criterion, 현대 포트폴리오 이론, 분산투자 원칙을 기반으로 비중을 산출하세요

## 관심종목 ({len(watchlist)}개)
{tickers_info or '없음'}
{f'- 한국 주식: {len(kr_tickers)}개' if kr_tickers else ''}
{f'- 미국 주식: {len(us_tickers)}개' if us_tickers else ''}

## 활성 매매 전략
{strats_info or '기본 전략 (RSI/MACD 기반)'}{quant_section_auto}{argos_section_auto}

## 분석 요청사항 (추가 데이터 수집 불필요 — 위 서버 제공 데이터만 활용)
아래 분석을 수행하세요:
- **시황분석**: 위 매크로 지표/뉴스를 기반으로 시장 분위기, 금리/환율 동향, 업종별 흐름 해석
- **종목분석**: 위 공시/뉴스/주가 데이터를 기반으로 재무 건전성, PER/PBR, 실적 전망 해석
- **기술적분석**: 위 정량지표(RSI/MACD 등)와 최근 주가 흐름을 종합하여 방향성 판단
- **리스크관리**: 포지션 크기 적정성, 손절가, 전체 포트폴리오 리스크

## 최종 산출물 (반드시 아래 형식 그대로 — 예시처럼 정확히)
[시그널] 삼성전자 (005930) | 매수 | 신뢰도 72% | 비중 15% | 목표가 85000 | 반도체 수요 회복 + RSI 과매도 구간
[시그널] 카카오 (035720) | 매도 | 신뢰도 61% | 비중 0% | 목표가 42000 | PER 과대평가, 금리 민감 섹터 약세
[시그널] LG에너지솔루션 (373220) | 관망 | 신뢰도 45% | 비중 5% | 목표가 0 | 혼조세, 방향성 불명확

※ 신뢰도는 정량기준값 ±20%p 범위 내에서 결정. 반드시 0~100 숫자 + % 기호.
※ 비중: 포트폴리오 내 해당 종목 비중(%). 매도 종목은 0%. 전 종목 비중 합계 ≤ {100 - _cash_reserve}%.
※ 목표가: 매수 종목은 목표 매도가, 매도 종목은 목표 재진입가, 관망은 0. 반드시 숫자만 (쉼표 없이)."""

    if not is_ai_ready():
        # AI 미연결 시 더미 시그널
        signals = _load_data("trading_signals", [])
        for w in watchlist[:5]:
            signal = {
                "id": f"sig_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{w['ticker']}",
                "date": datetime.now(KST).isoformat(),
                "ticker": w["ticker"],
                "name": w["name"],
                "market": w.get("market", "KR"),
                "action": "hold",
                "confidence": 50,
                "reason": "AI 미연결 — 분석 불가 (API 키 등록 필요)",
                "strategy": "auto",
                "analyzed_by": "system",
            }
            signals.insert(0, signal)
        if len(signals) > 200:
            signals = signals[:200]
        _save_data("trading_signals", signals)
        return {"success": True, "signals": signals[:20]}

    # CIO + 4명 전문가에게 위임 (실제 도구 사용 + 병렬 분석)
    save_activity_log("fin_analyst", f"📊 자동매매 시그널 생성 — {len(watchlist)}개 종목 분석 시작", "info")

    # 1단계: 투자팀장 독자 분석 + 도구 활용 (P2-4: 병렬화)
    cio_solo_prompt = (
        f"CEO 투자 성향: {_profile_label}. 관심종목 독자 분석을 작성하세요:\n{tickers_info or '없음'}\n\n"
        f"활성 전략: {strats_info or '기본 전략'}\n\n"
        f"각 종목에 대해 현재 시장 환경, 섹터 동향, 밸류에이션 관점에서 독립적으로 판단하고 "
        f"매수/매도/관망 + 포트폴리오 비중(%) + 목표가를 제시하세요. 최종 산출물은 반드시 아래 형식으로:\n"
        f"[시그널] 삼성전자 (005930) | 매수 | 신뢰도 72% | 비중 15% | 목표가 85000 | 반도체 수요 회복 신호\n"
        f"[시그널] 카카오 (035720) | 관망 | 신뢰도 48% | 비중 5% | 목표가 0 | 방향성 불명확\n"
        f"※ 신뢰도는 종목별로 독립적으로 0~100 숫자 + % 기호. 비중은 전 종목 합계 ≤ {100 - _cash_reserve}%. 목표가는 숫자만."
    )
    cio_soul = _ms()._load_agent_prompt("fin_analyst")
    cio_solo_model = select_model(cio_solo_prompt, override=_ms()._get_model_override("fin_analyst"))
    save_activity_log("fin_analyst", "📊 CIO 독자 분석 + 전문가 위임 병렬 시작", "info")
    # CIO 독자 분석 시작 교신 로그
    try:
        from db import save_delegation_log as _sdl
        _sdl(sender="투자팀장", receiver="CIO 독자 분석", message="전문가 위임과 병렬로 독립 판단 시작", log_type="delegation")
    except Exception as e:
        logger.debug("CIO 위임 로그 저장 실패: %s", e)

    # CIO 독자 분석용 도구 로드
    cio_detail = _AGENTS_DETAIL.get("fin_analyst", {})
    cio_allowed = cio_detail.get("allowed_tools", [])
    cio_solo_tools = None
    cio_solo_executor = None
    cio_solo_tools_used: list[str] = []
    if cio_allowed:
        cio_schemas = _load_tool_schemas(allowed_tools=cio_allowed)
        if cio_schemas.get("anthropic"):
            cio_solo_tools = cio_schemas["anthropic"]
            async def cio_solo_executor(tool_name: str, tool_input: dict):
                cio_solo_tools_used.append(tool_name)
                pool = _init_tool_pool()
                if pool:
                    return await pool.execute(tool_name, tool_input)
                return {"error": f"도구 풀 미초기화: {tool_name}"}

    # CIO 독자 분석과 전문가 위임을 동시에 실행 (asyncio.gather)
    async def _cio_solo_analysis():
        result = await ask_ai(cio_solo_prompt, system_prompt=cio_soul, model=cio_solo_model,
                              tools=cio_solo_tools, tool_executor=cio_solo_executor)
        content = result.get("content", "") if isinstance(result, dict) else ""
        cost = result.get("cost_usd", 0) if isinstance(result, dict) else 0
        # 교신 로그 기록
        try:
            preview = content[:300] if content else "분석 결과 없음"
            _sdl(sender="CIO 독자 분석", receiver="투자팀장", message=preview, log_type="report")
            await _broadcast_comms({"id": f"cio_solo_{datetime.now(KST).strftime('%H%M%S')}", "sender": "CIO 독자 분석", "receiver": "투자팀장", "message": preview, "log_type": "report", "source": "delegation", "created_at": datetime.now(KST).isoformat()})
        except Exception as e:
            logger.debug("CIO 독자 분석 교신 로그 실패: %s", e)
        return {"content": content, "cost_usd": cost}

    # 병렬 실행: CIO 독자 분석 + 전문가 위임
    await _ms()._broadcast_status("fin_analyst", "working", 0.1, "투자팀장 분석 진행 중...")
    cio_solo_task = _cio_solo_analysis()
    spec_task = _delegate_to_specialists("fin_analyst", prompt)
    cio_solo_result, spec_results = await asyncio.gather(cio_solo_task, spec_task)

    cio_solo_content = cio_solo_result.get("content", "")
    cio_solo_cost = cio_solo_result.get("cost_usd", 0)

    # 2단계: CIO가 독자 분석 + 전문가 결과를 종합
    spec_parts = []
    spec_cost = 0.0
    for r in (spec_results or []):
        name = r.get("name", r.get("agent_id", "?"))
        if "error" in r:
            spec_parts.append(f"[{name}] 오류: {r['error'][:80]}")
        else:
            spec_parts.append(f"[{name}]\n{r.get('content', '응답 없음')}")
            spec_cost += r.get("cost_usd", 0)

    mgr_name = _ms()._AGENT_NAMES.get("fin_analyst", "CIO")
    synthesis_prompt = (
        f"당신은 {mgr_name}입니다. 아래 두 가지 분석을 종합하여 최종 시그널을 결정하세요.\n\n"
        f"## CEO 원본 명령\n{prompt}\n\n"
        f"## CIO 독자 사전 분석 (전문가 보고서 참고 전 작성한 독립 판단)\n"
        f"{cio_solo_content[:1000] if cio_solo_content else '분석 없음'}\n\n"
        f"## 전문가 분석 결과\n" + "\n\n".join(spec_parts) + "\n\n"
        f"위 독자 분석과 전문가 보고서를 모두 반영하여 최종 시그널을 결정하세요."
    )
    override = _ms()._get_model_override("fin_analyst")
    synth_model = select_model(synthesis_prompt, override=override)
    await _ms()._broadcast_status("fin_analyst", "working", 0.7, "독자 분석 + 전문가 결과 종합 중...")
    synthesis = await ask_ai(synthesis_prompt, system_prompt=cio_soul, model=synth_model)
    await _ms()._broadcast_status("fin_analyst", "done", 1.0, "보고 완료")

    specialists_used = len([r for r in (spec_results or []) if "error" not in r])
    if "error" in synthesis:
        content = f"**{mgr_name} 전문가 분석 결과**\n\n" + "\n\n---\n\n".join(spec_parts)
    else:
        content = synthesis.get("content", "")
    cost = spec_cost + cio_solo_cost + synthesis.get("cost_usd", 0)

    # CIO 분석 결과에서 시그널 파싱
    parsed_signals = _parse_cio_signals(content, watchlist)

    signals = _load_data("trading_signals", [])
    new_signal = {
        "id": f"sig_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}",
        "date": datetime.now(KST).isoformat(),
        "analysis": content,
        "tickers": [w["ticker"] for w in watchlist],
        "parsed_signals": parsed_signals,
        "strategy": "cio_analysis",
        "analyzed_by": f"CIO 포함 {specialists_used + 1}명",
        "cost_usd": cost,
    }
    signals.insert(0, new_signal)
    if len(signals) > 200:
        signals = signals[:200]
    _save_data("trading_signals", signals)

    buy_count = len([s for s in parsed_signals if s.get("action") == "buy"])
    sell_count = len([s for s in parsed_signals if s.get("action") == "sell"])
    save_activity_log("fin_analyst",
        f"📊 CIO 시그널 완료: {len(watchlist)}개 종목 (매수 {buy_count}, 매도 {sell_count}, 비용 ${cost:.4f})",
        "info")

    # CIO 성과 추적: 예측을 cio_predictions 테이블에 저장
    try:
        from db import save_cio_prediction
        sig_id = new_signal["id"]
        for sig in parsed_signals:
            action_raw = sig.get("action", "hold")
            if action_raw in ("buy", "sell"):
                direction = "BUY" if action_raw == "buy" else "SELL"
                # 현재가 조회 (검증 기준가 — 3일/7일 후 비교용)
                current_price = 0
                try:
                    from kis_client import get_overseas_price as _gop
                    _pd = await _gop(sig["ticker"])
                    current_price = int(float(_pd.get("price", 0) or 0))
                except Exception as e:
                    logger.debug("현재가 조회 실패 (%s): %s", sig.get("ticker"), e)
                save_cio_prediction(
                    ticker=sig.get("ticker", ""),
                    direction=direction,
                    ticker_name=sig.get("name", ""),
                    confidence=sig.get("confidence", 0),
                    predicted_price=current_price or None,
                    target_price=sig.get("target_price"),
                    analysis_summary=sig.get("reason", ""),
                    task_id=sig_id,
                )
        logger.info("[CIO성과] %d건 예측 저장 완료 (sig_id=%s)", len([s for s in parsed_signals if s.get("action") in ("buy", "sell")]), sig_id)
    except Exception as e:
        logger.warning("[CIO성과] 예측 저장 실패: %s", e)

    # 신뢰도 파이프라인: 전문가 기여 캡처
    _capture_specialist_contributions_sync(
        parsed_signals, spec_results or [], cio_solo_content or "", sig_id if 'sig_id' in dir() else ""
    )

    # P2-7: CIO 목표가 → 관심종목 자동 반영
    try:
        _wl = _load_data("trading_watchlist", [])
        _updated = 0
        for sig in parsed_signals:
            tp = sig.get("target_price", 0)
            if not tp or tp <= 0:
                continue
            for w in _wl:
                if w.get("ticker") == sig.get("ticker"):
                    w["target_price"] = tp
                    _updated += 1
                    break
        if _updated > 0:
            _save_data("trading_watchlist", _wl)
            logger.info("[P2-7] 관심종목 목표가 %d건 자동 갱신", _updated)
    except Exception as e:
        logger.warning("[P2-7] 관심종목 목표가 반영 실패: %s", e)

    # 기밀문서 자동 저장 (CIO 독자분석 + 전체 분석 포함)
    try:
        now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        archive_lines = [f"# CIO 매매 시그널 분석 — {now_str}\n"]
        # CIO 독자 분석 내용 포함
        if cio_solo_content:
            archive_lines.append("## CIO 독자 사전 분석 (전문가 보고 전 독립 판단)\n")
            archive_lines.append(cio_solo_content[:2000])
            archive_lines.append("\n---\n")
        # CIO 최종 종합 분석 전문
        archive_lines.append("## CIO 최종 종합 분석\n")
        archive_lines.append(content[:3000] if content else "분석 내용 없음")
        archive_lines.append("\n---\n")
        # 종목별 시그널 요약
        archive_lines.append("## 종목별 시그널 요약\n")
        for sig in parsed_signals:
            ticker = sig.get("ticker", "")
            name = sig.get("name", ticker)
            action_raw = sig.get("action", "hold")
            action_label = "매수" if action_raw == "buy" else ("매도" if action_raw == "sell" else "관망")
            conf = sig.get("confidence", 0)
            reason = sig.get("reason", "")
            archive_lines.append(f"### {name} ({ticker}) — {action_label}")
            archive_lines.append(f"- 신뢰도: {conf}%")
            archive_lines.append(f"- 분석: {reason}\n")
        if len(parsed_signals) == 0:
            archive_lines.append("### 종목별 시그널 파싱 결과 없음\n")
            archive_lines.append(content[:2000] if content else "")
        archive_content = "\n".join(archive_lines)
        filename = f"CIO_시그널_{datetime.now(KST).strftime('%Y%m%d_%H%M')}.md"
        save_archive(
            division="finance",
            filename=filename,
            content=archive_content,
            agent_id="fin_analyst",
        )
    except Exception as e:
        logger.debug("CIO 아카이브 저장 실패: %s", e)

    # 매매 결정 일지 저장
    _save_decisions(parsed_signals)

    return {"success": True, "signal": new_signal, "parsed_signals": parsed_signals}


def _save_decisions(parsed_signals: list) -> None:
    """시그널을 매매 결정 일지(trading_decisions)에 저장합니다.

    P2-1 수정: 수동 분석(run_trading_now), 자동봇(_trading_bot_loop),
    스케줄 분석(generate_trading_signals) 모두에서 호출.
    """
    try:
        decisions = load_setting("trading_decisions", [])
        for sig in parsed_signals:
            action_raw = sig.get("action", "hold")
            action_label = "매수" if action_raw == "buy" else ("매도" if action_raw == "sell" else "관망")
            decision = {
                "id": str(_uuid.uuid4()),
                "created_at": datetime.now(KST).isoformat(),
                "ticker": sig.get("ticker", ""),
                "ticker_name": sig.get("name", sig.get("ticker", "")),
                "action": action_label,
                "confidence": sig.get("confidence", 0),
                "reason": sig.get("reason", ""),
                "expert_opinions": sig.get("expert_opinions", []),
                "executed": False,
            }
            decisions.append(decision)
        if len(decisions) > 50:
            decisions = decisions[-50:]
        save_setting("trading_decisions", decisions)
    except Exception as e:
        logger.debug("매매 결정 저장 실패: %s", e)


def _cio_confidence_weight(confidence: float) -> float:
    """CIO 신뢰도 기반 포트폴리오 비중 폴백 (CIO가 비중을 산출하지 않은 경우).
    75%+ → 20%, 65%+ → 15%, 55%+ → 10%, 기타 → 5%
    """
    if confidence >= 75:
        return 0.20
    elif confidence >= 65:
        return 0.15
    elif confidence >= 55:
        return 0.10
    return 0.05


def _get_signal_weight(sig: dict, fallback_conf: float = 50) -> float:
    """시그널에서 비중(0~1 비율)을 가져옵니다. CIO 비중 우선, 없으면 신뢰도 기반 폴백."""
    w = sig.get("weight", 0)
    if w and w > 0:
        return w / 100.0
    return _cio_confidence_weight(fallback_conf)


def _parse_cio_signals(content: str, watchlist: list) -> list:
    """CIO 분석 결과에서 종목별 매수/매도/관망 시그널을 추출합니다."""
    import re
    parsed = []
    seen_tickers = set()

    # [시그널] 패턴 — 비중 + 목표가 포함 (최신 형식)
    # 예: [시그널] 삼성전자 (005930) | 매수 | 신뢰도 72% | 비중 15% | 목표가 85000 | 이유
    pattern = r'\[시그널\]\s*(.+?)\s*[\(（]([A-Za-z0-9]+)[\)）]\s*\|\s*[^\|]*?(매수|매도|관망|buy|sell|hold)\b[^\|]*\|\s*(?:신뢰도[:\s]*)?\s*(\d+)\s*%?\s*\|\s*(?:비중\s*(\d+)\s*%?\s*\|\s*)?(?:목표가\s*(\d+)\s*\|\s*)?(.*)'
    matches = re.findall(pattern, content, re.IGNORECASE)

    # 기존 형식 (비중/목표가 없는 것) 호환용 폴백
    if not matches:
        pattern_legacy = r'\[시그널\]\s*(.+?)\s*[\(（]([A-Za-z0-9]+)[\)）]\s*\|\s*[^\|]*?(매수|매도|관망|buy|sell|hold)\b[^\|]*\|\s*(?:신뢰도[:\s]*)?\s*(\d+)\s*%?\s*\|?\s*()()(.*)'
        matches = re.findall(pattern_legacy, content, re.IGNORECASE)

    for name, ticker, action, confidence, weight_str, target_price_str, reason in matches:
        ticker = ticker.strip()
        if ticker in seen_tickers:
            continue  # 같은 종목 중복 시그널 방지 (요약 섹션 중복)
        seen_tickers.add(ticker)
        action_map = {"매수": "buy", "매도": "sell", "관망": "hold", "buy": "buy", "sell": "sell", "hold": "hold"}
        market = "US" if any(c.isalpha() and c.isupper() for c in ticker) and not ticker.isdigit() else "KR"
        # 이유가 빈 줄이면 시그널 다음 줄에서 추출
        reason_text = reason.strip()
        if not reason_text:
            sig_pos = content.find(f"[시그널] {name.strip()}")
            if sig_pos >= 0:
                after = content[sig_pos:sig_pos + 500]
                lines = after.split("\n")
                for line in lines[1:4]:  # 다음 1~3줄에서 이유 찾기
                    line = line.strip()
                    if line and not line.startswith("[시그널]") and not line.startswith("━"):
                        reason_text = line
                        break
        parsed.append({
            "ticker": ticker,
            "name": name.strip(),
            "market": market,
            "action": action_map.get(action.lower(), "hold"),
            "confidence": int(confidence),
            "weight": int(weight_str) if weight_str and weight_str.isdigit() else 0,
            "target_price": int(target_price_str) if target_price_str and target_price_str.isdigit() else 0,
            "reason": reason_text or "CIO 종합 분석 참조",
        })

    # 비중 안전장치: 종목당 최대 비중 + 총합 제한 (투자 성향 기반)
    if parsed:
        _profile = _get_risk_profile()
        _ranges = RISK_PROFILES.get(_profile, RISK_PROFILES["balanced"])
        _max_pos = _ranges["max_position_pct"]["max"]
        _cash_reserve = _ranges["cash_reserve"]["default"]
        _max_total = 100 - _cash_reserve
        # 종목당 클램핑
        for sig in parsed:
            if sig["weight"] > _max_pos:
                sig["weight"] = _max_pos
        # 총합 제한
        total_weight = sum(s["weight"] for s in parsed)
        if total_weight > _max_total and total_weight > 0:
            ratio = _max_total / total_weight
            for sig in parsed:
                sig["weight"] = max(1, int(sig["weight"] * ratio))

    # [시그널] 패턴이 없으면 관심종목 기반으로 키워드 파싱 (종목별 개별 컨텍스트 기준)
    if not parsed:
        for w in watchlist:
            action = "hold"
            confidence = 50
            reason = ""
            name = w.get("name", w["ticker"])
            ticker = w["ticker"]
            # 이 종목이 보고서에 언급됐는지 확인
            name_idx = content.find(name)
            ticker_idx = content.find(ticker)
            ref_idx = name_idx if name_idx >= 0 else ticker_idx
            if ref_idx < 0:
                continue  # 언급 안 된 종목은 제외
            # 해당 종목 주변 300자만 컨텍스트로 사용 (전체 보고서 X)
            ctx = content[ref_idx:ref_idx + 300]
            if any(k in ctx for k in ["매수", "적극 매수", "buy", "진입"]):
                action = "buy"
            elif any(k in ctx for k in ["매도", "sell", "청산", "익절"]):
                action = "sell"
            # 컨텍스트에서 신뢰도 숫자 추출 (예: "신뢰도 72%" / "72%")
            conf_match = re.search(r'신뢰도[:\s]*(\d+)\s*%?', ctx)
            if conf_match:
                confidence = int(conf_match.group(1))
            else:
                pct_match = re.search(r'(\d{2,3})\s*%', ctx)
                if pct_match:
                    confidence = int(pct_match.group(1))
            # 근거 추출
            reason = ctx.split("\n")[0].strip()
            parsed.append({
                "ticker": ticker,
                "name": name,
                "market": w.get("market", "KR"),
                "action": action,
                "confidence": confidence,
                "reason": reason or "CIO 종합 분석 참조",
            })

    return parsed


# ── settings, risk-profile, cio-update → handlers/trading_handler.py로 분리 ──

@trading_router.post("/api/trading/bot/toggle")
async def toggle_trading_bot():
    """자동매매 봇 ON/OFF 토글."""


    app_state.trading_bot_active = not app_state.trading_bot_active
    # DB에 상태 저장 → 배포/재시작 후에도 유지
    save_setting("trading_bot_active", app_state.trading_bot_active)

    if app_state.trading_bot_active:
        if app_state.trading_bot_task is None or app_state.trading_bot_task.done():
            app_state.trading_bot_task = asyncio.create_task(_trading_bot_loop())
        save_activity_log("system", "🤖 자동매매 봇 가동 시작!", "info")
        _log("[TRADING] 자동매매 봇 시작 ✅")
    else:
        save_activity_log("system", "⏹️ 자동매매 봇 중지", "info")
        _log("[TRADING] 자동매매 봇 중지")

    return {"success": True, "bot_active": app_state.trading_bot_active}


# ── bot/status, calibration → handlers/trading_handler.py로 분리 ──

@trading_router.post("/api/trading/watchlist/analyze-selected")
async def analyze_selected_watchlist(request: Request):
    """관심종목 중 선택한 종목만 즉시 분석 + 자동매매."""
    body = await request.json()
    tickers = body.get("tickers", [])
    if not tickers:
        return {"success": False, "message": "분석할 종목을 선택하세요."}

    existing = app_state.bg_tasks.get("trading_run_now")
    if existing and not existing.done():
        return {"success": True, "message": "CIO 분석이 이미 진행 중입니다.", "already_running": True}

    async def _bg():
        try:
            result = await _run_trading_now_inner(selected_tickers=tickers)
            app_state.bg_results["trading_run_now"] = {**result, "_completed_at": __import__("time").time()}
        except Exception as e:
            logger.error("[선택 분석] 백그라운드 오류: %s", e, exc_info=True)
            app_state.bg_results["trading_run_now"] = {
                "success": False, "message": f"분석 중 오류: {str(e)[:200]}",
                "signals": [], "signals_count": 0, "orders_triggered": 0,
                "_completed_at": __import__("time").time(),
            }
        finally:
            result = app_state.bg_results.get("trading_run_now", {})
            await wm.broadcast({"type": "trading_run_complete",
                "success": result.get("success", False),
                "signals_count": result.get("signals_count", 0),
                "orders_triggered": result.get("orders_triggered", 0)})

    app_state.bg_tasks["trading_run_now"] = asyncio.create_task(_bg())
    return {"success": True, "message": f"{len(tickers)}개 종목 분석 시작됨.", "background": True}


@trading_router.post("/api/trading/bot/run-now")
async def run_trading_now():
    """지금 즉시 CIO 분석 + 매매 판단 실행 (장 시간 무관, 수동 트리거).

    봇 ON/OFF 상태와 무관하게 즉시 1회 분석을 실행합니다.
    수동 실행이므로 auto_execute 설정 무관하게 항상 매매까지 진행합니다.

    Cloudflare 100초 타임아웃 대응: 즉시 응답 + 백그라운드 실행.
    프론트엔드는 CIO SSE + 폴링으로 실시간 추적.
    """
    # 이미 실행 중이면 중복 방지
    existing = app_state.bg_tasks.get("trading_run_now")
    if existing and not existing.done():
        return {"success": True, "message": "CIO 분석이 이미 진행 중입니다. 잠시 기다려주세요.", "already_running": True}

    async def _bg_run_trading():
        try:
            result = await _run_trading_now_inner()
            app_state.bg_results["trading_run_now"] = {
                **result, "_completed_at": __import__("time").time()
            }
        except Exception as e:
            logger.error("[수동 분석] 백그라운드 오류: %s", e, exc_info=True)
            signals = _load_data("trading_signals", [])
            latest = signals[0] if signals else {}
            app_state.bg_results["trading_run_now"] = {
                "success": False,
                "message": f"분석 중 오류: {str(e)[:200]}",
                "signals": latest.get("parsed_signals", []),
                "signals_count": len(latest.get("parsed_signals", [])),
                "orders_triggered": 0,
                "error": str(e)[:200],
                "_completed_at": __import__("time").time(),
            }
        finally:
            # 완료 알림 브로드캐스트
            result = app_state.bg_results.get("trading_run_now", {})
            await wm.broadcast({
                "type": "trading_run_complete",
                "success": result.get("success", False),
                "signals_count": result.get("signals_count", 0),
                "orders_triggered": result.get("orders_triggered", 0),
            })

    app_state.bg_tasks["trading_run_now"] = asyncio.create_task(_bg_run_trading())
    return {"success": True, "message": "CIO 분석 시작됨. 실시간 진행 상황은 화면에서 확인하세요.", "background": True}


@trading_router.get("/api/trading/bot/run-status")
async def get_trading_run_status():
    """백그라운드 CIO 분석 진행 상태 확인."""
    task = app_state.bg_tasks.get("trading_run_now")
    result = app_state.bg_results.get("trading_run_now")

    if task and not task.done():
        return {"status": "running", "message": "CIO 분석 진행 중..."}
    elif result:
        return {"status": "completed", **result}
    else:
        return {"status": "idle", "message": "실행 대기 중"}


@trading_router.post("/api/trading/bot/stop")
async def stop_trading_now():
    """진행 중인 CIO 분석을 즉시 중지합니다."""
    task = app_state.bg_tasks.get("trading_run_now")
    if task and not task.done():
        task.cancel()
        save_activity_log("fin_analyst", "🛑 CEO가 수동으로 분석을 중지했습니다.", "info")
        await wm.broadcast({"type": "trading_run_complete", "success": False, "stopped": True, "signals_count": 0, "orders_triggered": 0})
        return {"success": True, "message": "분석이 중지되었습니다."}
    return {"success": False, "message": "진행 중인 분석이 없습니다."}


async def _run_trading_now_inner(selected_tickers: list[str] | None = None, *, auto_bot: bool = False):
    """run_trading_now의 실제 로직 (에러 핸들링은 호출자가 담당).

    selected_tickers: 지정 시 해당 종목만 분석. None이면 전체 관심종목.
    auto_bot: True면 자동매매 봇에서 호출 (auto_execute 설정 체크, 시그널에 auto_bot 마킹).
    """
    settings = _load_data("trading_settings", _default_trading_settings())
    watchlist = _load_data("trading_watchlist", [])

    if not watchlist:
        return {"success": False, "message": "관심종목이 없습니다. 먼저 종목을 추가하세요."}

    # 장 시간 확인 (수동 실행은 강제 실행 — 장 마감이어도 진행)
    is_open, market = _is_market_open(settings)
    if not is_open:
        market = "KR"  # 장 마감 시 한국장 기준으로 분석
    market_watchlist = [w for w in watchlist if w.get("market", "KR") == market] or watchlist

    # 선택 종목 필터링 (selected_tickers 지정 시)
    if selected_tickers:
        upper_sel = [t.upper() for t in selected_tickers]
        market_watchlist = [w for w in watchlist if w.get("ticker", "").upper() in upper_sel]
        if not market_watchlist:
            return {"success": False, "message": f"선택한 종목({', '.join(selected_tickers)})이 관심종목에 없습니다."}
        # 선택 종목의 마켓 자동 결정
        markets = set(w.get("market", "KR") for w in market_watchlist)
        market = "US" if "US" in markets else "KR"

    # 자기학습 보정 섹션 (베이지안 + ELO + 오답패턴 + Platt Scaling 통합)
    cal_section = _build_calibration_prompt_section(settings)

    # 정량지표 사전분석 (RSI/MACD/볼린저/거래량/추세 — 병렬 계산)
    save_activity_log("fin_analyst", "📐 정량지표 사전계산 시작...", "info")
    quant_section = await _build_quant_prompt_section(market_watchlist, market)

    # ARGOS DB 수집 데이터 주입 (주가/매크로/공시/뉴스 — 서버가 직접 제공)
    save_activity_log("fin_analyst", "📡 ARGOS 수집 데이터 로딩...", "info")
    argos_section = await _build_argos_context_section(market_watchlist, market)

    # DCF 가치평가 + 리스크 분석 — 서버가 Python으로 사전 계산 (AI 호출 아님)
    save_activity_log("fin_analyst", "📊 DCF/리스크 사전계산 중...", "info")
    dcf_risk_section = await _build_dcf_risk_prompt_section(market_watchlist, market)

    tickers_info = ", ".join([f"{w['name']}({w['ticker']})" for w in market_watchlist])
    strategies = _load_data("trading_strategies", [])
    active_strats = [s for s in strategies if s.get("active")]
    strats_info = ", ".join([s["name"] for s in active_strats[:5]]) or "기본 전략"

    market_label = "한국" if market == "KR" else "미국"
    prompt = f"""[수동 즉시 분석 요청 — {market_label}장]

## 분석 대상 ({len(market_watchlist)}개 종목)
{tickers_info}

## 활성 전략: {strats_info}{cal_section}{quant_section}{argos_section}{dcf_risk_section}

## 분석 요청 (도구 호출 불필요 — 위 서버 제공 데이터만으로 판단)
아래 분석을 수행하세요:
- **시황분석**: 위 매크로 지표/뉴스를 기반으로 {'코스피/코스닥 흐름, 외국인/기관 동향, 금리/환율' if market == 'KR' else 'S&P500/나스닥, 미국 금리/고용지표, 달러 강세'} 해석
- **종목분석**: 위 공시/뉴스/주가 데이터를 기반으로 재무 건전성, PER/PBR, 실적 방향 해석
- **기술적분석**: 위 정량지표(RSI/MACD 등)와 주가 흐름을 종합하여 방향성 판단
- **리스크관리**: 손절가, 적정 포지션 크기, 전체 포트폴리오 리스크

## 최종 산출물 (반드시 아래 형식 그대로 — 예시처럼 정확히)
[시그널] 삼성전자 (005930) | 매수 | 신뢰도 72% | 비중 15% | 목표가 78000 | 반도체 수요 회복 + RSI 과매도 구간
[시그널] 카카오 (035720) | 매도 | 신뢰도 61% | 비중 10% | 목표가 0 | PER 과대평가, 금리 민감 섹터 약세
[시그널] LG에너지솔루션 (373220) | 관망 | 신뢰도 45% | 비중 0% | 목표가 390000 | 혼조세, 이 가격 도달 시 진입 검토

※ 주의:
- 신뢰도는 위 정량기준값 ±20%p 범위 내에서 결정. 종목별로 독립적으로, 0~100 숫자 + % 기호로 표기
- 목표가(권장 매수 진입가): 매수/관망 종목은 반드시 입력. 현재가보다 낮은 목표 진입가 설정. 미국 주식은 USD 단위. 매도 종목은 0
- 목표가 도달 시 서버가 자동으로 매수 실행 — 신중하게 설정할 것"""

    save_activity_log("fin_analyst", f"🔍 수동 즉시 분석 시작: {market_label}장 {len(market_watchlist)}개 종목", "info")
    cio_result = await _ms()._call_agent("fin_analyst", prompt)
    content = cio_result.get("content", "")
    cost = cio_result.get("cost_usd", 0)

    # ── STEP2 강제 실행 (서버 보장) — 팀장이 생략해도 서버가 직접 실행 ──
    step2_section = ""
    try:
        pool = _init_tool_pool()
        if pool:
            tickers_str = ",".join([w["ticker"] for w in market_watchlist])
            symbols_str = " ".join([w["ticker"] for w in market_watchlist])

            # 2-A: correlation_analyzer tail_risk
            _l = save_activity_log("fin_analyst", "🎯 [STEP2 서버강제] correlation_analyzer tail_risk 실행 중...", "tool")
            await wm.send_activity_log(_l)
            corr_input = {"action": "tail_risk", "symbols": tickers_str if market == "KR" else symbols_str}
            corr_result = await pool.invoke("correlation_analyzer", caller_id="fin_analyst", **corr_input)

            # 2-B: portfolio_optimizer_v2 optimize
            _l = save_activity_log("fin_analyst", "🎯 [STEP2 서버강제] portfolio_optimizer_v2 optimize 실행 중...", "tool")
            await wm.send_activity_log(_l)
            port_input = ({"action": "optimize", "tickers": tickers_str, "risk_tolerance": "moderate"}
                          if market == "KR" else
                          {"action": "optimize", "symbols": symbols_str, "risk_tolerance": "moderate"})
            port_result = await pool.invoke("portfolio_optimizer_v2", caller_id="fin_analyst", **port_input)

            step2_section = (
                "\n\n---\n\n## [STEP2 — 포트폴리오 레벨 분석]\n\n"
                f"### 종목 간 동시 하락 위험 (correlation_analyzer)\n{corr_result}\n\n"
                f"### 최적 포트폴리오 비중 (portfolio_optimizer_v2)\n{port_result}"
            )
            _l = save_activity_log("fin_analyst", "✅ [STEP2 서버강제] correlation_analyzer + portfolio_optimizer_v2 완료", "info")
            await wm.send_activity_log(_l)
    except Exception as _step2_err:
        logger.warning("[STEP2 강제실행] 오류: %s", _step2_err)
        _l = save_activity_log("fin_analyst", f"⚠️ [STEP2 서버강제] 오류: {str(_step2_err)[:80]}", "warning")
        await wm.send_activity_log(_l)

    if step2_section:
        content += step2_section

    # ── QA 검수 제거됨 (2026-02-27) — 분석 완료 즉시 매매 실행 ──
    parsed_signals = _parse_cio_signals(content, market_watchlist)

    # 신호 저장
    signals = _load_data("trading_signals", [])
    new_signal = {
        "id": f"sig_manual_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}",
        "date": datetime.now(KST).isoformat(),
        "market": market,
        "analysis": content,
        "tickers": [w["ticker"] for w in market_watchlist[:10]],
        "parsed_signals": parsed_signals,
        "strategy": "cio_bot_analysis" if auto_bot else "cio_manual_analysis",
        "analyzed_by": "금융분석팀장 단독 분석 (자동봇)" if auto_bot else "금융분석팀장 단독 분석 (수동 실행)",
        "cost_usd": cost,
        "auto_bot": auto_bot,
        "manual_run": not auto_bot,
    }
    signals.insert(0, new_signal)
    if len(signals) > 200:
        signals = signals[:200]
    _save_data("trading_signals", signals)

    _save_decisions(parsed_signals)

    # 매매 실행: 수동=항상 실행 / 자동봇=auto_execute 설정 체크
    min_confidence = settings.get("min_confidence", 65)
    order_size = settings.get("order_size", 0)  # 0 = CIO 비중 자율, >0 = 고정 금액
    orders_triggered = 0
    account_balance = 0  # buy_limit 트리거에서도 사용 — should_execute 밖에서 참조

    # 자기보정 계수 계산 (Platt Scaling) — 미정의 시 NameError 방지
    calibration = _compute_calibration_factor(settings.get("calibration_lookback", 20))
    calibration_factor = calibration.get("factor", 1.0)
    if calibration.get("win_rate") is not None:
        save_activity_log("fin_analyst",
            f"📊 자기보정 적용: factor={calibration_factor} ({calibration.get('note', '')})", "info")

    # 자동봇 모드: auto_execute 꺼져있으면 매매 건너뜀
    should_execute = True
    if auto_bot:
        auto_execute = settings.get("auto_execute", False)
        if not auto_execute:
            save_activity_log("fin_analyst",
                "🚫 자동봇 분석 완료 — auto_execute=OFF이므로 매매 건너뜀", "info")
            should_execute = False

    if should_execute:
        # 실거래 주문은 enable_real=True일 때만 실행
        enable_real = settings.get("enable_real", False)
        enable_mock = settings.get("enable_mock", False)
        use_kis = _KIS_AVAILABLE and _kis_configured() and enable_real
        use_mock_kis = (not use_kis) and enable_mock and _KIS_AVAILABLE and _kis_mock_configured()
        paper_mode = not use_kis and not use_mock_kis  # 둘 다 불가할 때만 가상 모드

        # CIO 비중 기반 매수(B안): order_size=0이면 잔고×비중으로 자동 산출
        account_balance = 0
        if order_size == 0:
            try:
                if use_kis:
                    _bal = await _kis_balance()
                    account_balance = _bal.get("cash", 0) if _bal.get("success") else 0
                elif use_mock_kis:
                    _bal = await _kis_mock_balance()
                    account_balance = _bal.get("cash", 0) if _bal.get("success") else 0
                else:
                    _port = _load_data("trading_portfolio", _default_portfolio())
                    account_balance = _port.get("cash", 0)
            except Exception as e:
                logger.debug("잔고 조회 실패: %s", e)
            if account_balance <= 0:
                account_balance = 1_000_000
                save_activity_log("fin_analyst", "CIO 비중 모드: 잔고 조회 실패, 기본 100만원 사용", "warning")
            save_activity_log("fin_analyst",
                f"CIO 비중 모드: 계좌잔고 {account_balance:,.0f}원 기준 자동 주수 산출", "info")

        mode_label = ("실거래" if not KIS_IS_MOCK else "모의투자") if use_kis else ("모의투자" if use_mock_kis else "가상")
        save_activity_log("fin_analyst",
            f"📋 매매 실행 시작: 시그널 {len(parsed_signals)}건, 최소신뢰도 {min_confidence}%, order_size={order_size}, KIS={use_kis}, MOCK={use_mock_kis}, 모드={mode_label}", "info")

        for sig in parsed_signals:
            if sig["action"] not in ("buy", "sell"):
                continue
            effective_conf = sig.get("confidence", 0) * calibration_factor
            if effective_conf < min_confidence:
                save_activity_log("fin_analyst",
                    f"[수동] {sig.get('name', sig['ticker'])} 신뢰도 부족 ({effective_conf:.0f}% < {min_confidence}%) — 건너뜀",
                    "info")
                continue

            ticker = sig["ticker"]
            sig_market = sig.get("market", market)
            is_us = sig_market.upper() in ("US", "USA", "OVERSEAS") or (ticker.isalpha() and len(ticker) <= 5)
            action_kr = "매수" if sig["action"] == "buy" else "매도"
            save_activity_log("fin_analyst",
                f"🎯 {action_kr} 시도: {sig.get('name', ticker)} ({ticker}) 신뢰도 {effective_conf:.0f}% 비중 {sig.get('weight', 0)}%", "info")

            try:
                # 현재가 조회
                if is_us:
                    if _KIS_AVAILABLE and _kis_configured():
                        us_price_data = await _kis_us_price(ticker)
                        price = us_price_data.get("price", 0) if us_price_data.get("success") else 0
                        save_activity_log("fin_analyst", f"  💵 {ticker} 현재가: ${price:.2f} (KIS 조회)", "info")
                    else:
                        target_w = next((w for w in market_watchlist if w.get("ticker", "").upper() == ticker.upper()), None)
                        price = float(target_w.get("target_price", 0)) if target_w else 0
                    if price <= 0:
                        save_activity_log("fin_analyst", f"[수동/US] {ticker} 현재가 조회 실패 (price={price}) — 건너뜀", "warning")
                        continue
                    _fx = _get_fx_rate()
                    _sig_weight = _get_signal_weight(sig, effective_conf)
                    _order_amt = order_size if order_size > 0 else int(account_balance * _sig_weight)
                    qty = max(1, int(_order_amt / (price * _fx)))
                    save_activity_log("fin_analyst",
                        f"  📐 주문 계산: 잔고 {account_balance:,.0f}원 × 비중 {_sig_weight:.1%} = {_order_amt:,.0f}원 → ${price:.2f} × ₩{_fx:.0f} = {qty}주", "info")
                else:
                    if _KIS_AVAILABLE and _kis_configured():
                        price = await _kis_price(ticker)
                    else:
                        target_w = next((w for w in market_watchlist if w["ticker"] == ticker), None)
                        price = target_w.get("target_price", 0) if target_w else 0
                    if price <= 0:
                        price = 50000
                    _order_amt = order_size if order_size > 0 else int(account_balance * _get_signal_weight(sig, effective_conf))
                    qty = max(1, int(_order_amt / price))

                if use_kis:
                    mode_str = "실거래" if not KIS_IS_MOCK else "모의투자(KIS)"
                    save_activity_log("fin_analyst",
                        f"  🚀 KIS 주문 전송: {action_kr} {ticker} {qty}주 @ {'$'+str(round(price,2)) if is_us else str(price)+'원'} ({mode_str})", "info")
                    if is_us:
                        order_result = await _kis_us_order(ticker, sig["action"], qty, price=price)
                    else:
                        order_result = await _kis_order(ticker, sig["action"], qty, price=0)
                    save_activity_log("fin_analyst",
                        f"  📨 KIS 응답: success={order_result.get('success')}, msg={order_result.get('message', '')[:100]}", "info")
                    if order_result["success"]:
                        orders_triggered += 1
                        save_activity_log("fin_analyst",
                            f"✅ [수동/{mode_str}] {action_kr} 성공: {sig.get('name', ticker)} {qty}주 (신뢰도 {effective_conf:.0f}%)",
                            "info")
                        history = _load_data("trading_history", [])
                        _h_id = f"manual_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}"
                        history.insert(0, {
                            "id": _h_id,
                            "date": datetime.now(KST).isoformat(),
                            "ticker": ticker, "name": sig.get("name", ticker),
                            "action": sig["action"], "qty": qty, "price": price,
                            "total": qty * price, "pnl": 0,
                            "strategy": f"CIO 수동분석 ({mode_str}, 신뢰도 {sig['confidence']}%)",
                            "status": "executed", "market": "US" if is_us else "KR",
                            "order_no": order_result.get("order_no", ""),
                        })
                        _save_data("trading_history", history)
                        if sig["action"] == "buy":
                            _register_position_triggers(ticker, sig.get("name", ticker), price, qty,
                                                        "US" if is_us else "KR", settings, source_id=_h_id)
                    else:
                        save_activity_log("fin_analyst",
                            f"❌ [수동/{mode_str}] 주문 실패: {sig.get('name', ticker)} — {order_result.get('message', '원인 불명')}", "error")
                elif use_mock_kis:
                    # ── KIS 모의투자 계좌로 실제 주문 ──
                    save_activity_log("fin_analyst",
                        f"  🚀 KIS 모의투자 주문 전송: {action_kr} {ticker} {qty}주 @ {'$'+str(round(price,2)) if is_us else str(price)+'원'}", "info")
                    if is_us:
                        order_result = await _kis_mock_us_order(ticker, sig["action"], qty, price=price)
                    else:
                        order_result = await _kis_mock_order(ticker, sig["action"], qty, price=0)
                    save_activity_log("fin_analyst",
                        f"  📨 KIS 모의투자 응답: success={order_result.get('success')}, msg={order_result.get('message', '')[:100]}", "info")
                    if order_result["success"]:
                        orders_triggered += 1
                        save_activity_log("fin_analyst",
                            f"✅ [수동/모의투자] {action_kr} 성공: {sig.get('name', ticker)} {qty}주 (신뢰도 {effective_conf:.0f}%)", "info")
                        history = _load_data("trading_history", [])
                        _h_id2 = f"mock_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}"
                        history.insert(0, {
                            "id": _h_id2,
                            "date": datetime.now(KST).isoformat(),
                            "ticker": ticker, "name": sig.get("name", ticker),
                            "action": sig["action"], "qty": qty, "price": price,
                            "total": qty * price, "pnl": 0,
                            "strategy": f"CIO 수동분석 (모의투자, 신뢰도 {sig['confidence']}%)",
                            "status": "mock_executed", "market": "US" if is_us else "KR",
                            "order_no": order_result.get("order_no", ""),
                        })
                        _save_data("trading_history", history)
                        if sig["action"] == "buy":
                            _register_position_triggers(ticker, sig.get("name", ticker), price, qty,
                                                        "US" if is_us else "KR", settings, source_id=_h_id2)
                    else:
                        save_activity_log("fin_analyst",
                            f"❌ [수동/모의투자] 주문 실패: {sig.get('name', ticker)} — {order_result.get('message', '원인 불명')}", "error")
                else:
                    # 가상 포트폴리오 (paper trading)
                    portfolio = _load_data("trading_portfolio", _default_portfolio())
                    if sig["action"] == "buy" and portfolio["cash"] >= price * qty:
                        holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
                        total_amount = qty * price
                        if holding:
                            old_total = holding["avg_price"] * holding["qty"]
                            holding["qty"] += qty
                            holding["avg_price"] = int((old_total + total_amount) / holding["qty"])
                            holding["current_price"] = price
                        else:
                            portfolio["holdings"].append({
                                "ticker": ticker, "name": sig.get("name", ticker),
                                "qty": qty, "avg_price": price, "current_price": price,
                                "market": sig.get("market", market),
                            })
                        portfolio["cash"] -= total_amount
                        portfolio["updated_at"] = datetime.now(KST).isoformat()
                        _save_data("trading_portfolio", portfolio)
                        orders_triggered += 1
                        history = _load_data("trading_history", [])
                        _h_id3 = f"manual_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}"
                        history.insert(0, {
                            "id": _h_id3,
                            "date": datetime.now(KST).isoformat(),
                            "ticker": ticker, "name": sig.get("name", ticker),
                            "action": "buy", "qty": qty, "price": price,
                            "total": total_amount, "pnl": 0,
                            "strategy": f"CIO 수동분석 (가상, 신뢰도 {sig['confidence']}%)",
                            "status": "executed", "market": sig.get("market", market),
                        })
                        _save_data("trading_history", history)
                        save_activity_log("fin_analyst",
                            f"[수동/가상] 매수: {sig.get('name', ticker)} {qty}주 x {price:,.0f}원 (신뢰도 {effective_conf:.0f}%)", "info")
                        _register_position_triggers(ticker, sig.get("name", ticker), price, qty,
                                                    sig.get("market", market), settings, source_id=_h_id3)
                    elif sig["action"] == "sell":
                        holding = next((h for h in portfolio["holdings"] if h["ticker"] == ticker), None)
                        if holding and holding["qty"] > 0:
                            sell_qty = min(qty, holding["qty"])
                            total_amount = sell_qty * price
                            pnl = (price - holding["avg_price"]) * sell_qty
                            holding["qty"] -= sell_qty
                            if holding["qty"] == 0:
                                portfolio["holdings"] = [h for h in portfolio["holdings"] if h["ticker"] != ticker]
                            portfolio["cash"] += total_amount
                            portfolio["updated_at"] = datetime.now(KST).isoformat()
                            _save_data("trading_portfolio", portfolio)
                            orders_triggered += 1
                            history = _load_data("trading_history", [])
                            history.insert(0, {
                                "id": f"manual_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}_{ticker}",
                                "date": datetime.now(KST).isoformat(),
                                "ticker": ticker, "name": sig.get("name", ticker),
                                "action": "sell", "qty": sell_qty, "price": price,
                                "total": total_amount, "pnl": pnl,
                                "strategy": f"CIO 수동분석 (가상, 신뢰도 {sig['confidence']}%)",
                                "status": "executed", "market": sig.get("market", market),
                            })
                            _save_data("trading_history", history)
                            pnl_str = f"{'+'if pnl>=0 else ''}{pnl:,.0f}원"
                            save_activity_log("fin_analyst",
                                f"[수동/가상] 매도: {sig.get('name', ticker)} {sell_qty}주 x {price:,.0f}원 (손익 {pnl_str})", "info")
            except Exception as order_err:
                import traceback
                _tb = traceback.format_exc()
                logger.error("[수동 분석] 자동주문 오류 (%s): %s\n%s", ticker, order_err, _tb)
                save_activity_log("fin_analyst", f"❌ [수동] 주문 오류: {ticker} — {order_err}", "error")

    # ── CIO 목표가 기반 buy_limit 트리거 자동 등록 (수동 즉시분석) ──
    _today_str2 = datetime.now(KST).strftime("%Y%m%d")
    for sig in parsed_signals:
        _tp = sig.get("target_price", 0)
        if _tp <= 0 or sig["action"] not in ("buy", "hold"):
            continue
        _bl2_ticker = sig["ticker"]
        _bl2_name = sig.get("name", _bl2_ticker)
        _bl2_market = sig.get("market", market)
        _bl2_is_us = _bl2_market.upper() in ("US", "USA", "OVERSEAS") or (
            _bl2_ticker.isalpha() and len(_bl2_ticker) <= 5
        )
        _all2 = _load_data("price_triggers", [])
        _all2 = [
            t for t in _all2
            if not (
                t.get("type") == "buy_limit"
                and t.get("ticker") == _bl2_ticker
                and t.get("created_at", "").startswith(_today_str2)
            )
        ]
        _w2 = _get_signal_weight(sig, sig.get("confidence", 50))
        _amt2 = int(account_balance * _w2) if account_balance > 0 else 500_000
        _fx2 = _get_fx_rate()
        _qty2 = max(1, int(_amt2 / (_tp * _fx2))) if _bl2_is_us else max(1, int(_amt2 / _tp))
        _all2.insert(0, {
            "id": f"bl_{_bl2_ticker}_{datetime.now(KST).strftime('%Y%m%d%H%M%S')}",
            "ticker": _bl2_ticker, "name": _bl2_name,
            "type": "buy_limit", "trigger_price": _tp, "qty": _qty2,
            "market": _bl2_market, "active": True,
            "created_at": datetime.now(KST).isoformat(),
            "source": "cio_auto" if auto_bot else "cio_manual", "source_id": new_signal["id"],
            "note": f"CIO 목표매수: {_tp:,.0f} ({sig.get('confidence', 0)}% 신뢰도) — {sig.get('reason', '')[:60]}",
        })
        if len(_all2) > 500:
            _all2 = _all2[:500]
        _save_data("price_triggers", _all2)
        save_activity_log(
            "fin_analyst",
            f"🎯 목표매수 자동등록: {_bl2_name}({_bl2_ticker}) 목표가 {_tp:,.0f} × {_qty2}주",
            "info",
        )

    _mode_log = "자동봇" if auto_bot else "수동"
    save_activity_log("fin_analyst",
        f"✅ {_mode_log} 분석 완료: {len(parsed_signals)}개 시그널 (주문 {orders_triggered}건, 비용 ${cost:.4f})", "info")

    return {
        "success": True,
        "market": market_label,
        "signals_count": len(parsed_signals),
        "signals": parsed_signals,
        "orders_triggered": orders_triggered,
        "calibration": calibration,
        "calibration_factor": calibration_factor,
        "cost_usd": cost,
        "analysis_preview": content[:500] + "..." if len(content) > 500 else content,
    }


def _is_us_dst() -> bool:
    """미국 서머타임(EDT) 여부 판정 — 3월 둘째 일요일 02:00 ~ 11월 첫째 일요일 02:00 (ET).
    한국은 서머타임이 없으므로 날짜 기준 근사 판정."""
    now = datetime.now(KST)
    y = now.year
    # 3월 둘째 일요일 (weekday: 0=Mon, 6=Sun)
    mar1_wd = datetime(y, 3, 1).weekday()
    second_sun_mar = 1 + (6 - mar1_wd) % 7 + 7
    # 11월 첫째 일요일
    nov1_wd = datetime(y, 11, 1).weekday()
    first_sun_nov = 1 + (6 - nov1_wd) % 7
    mar_date = datetime(y, 3, second_sun_mar, tzinfo=KST)
    nov_date = datetime(y, 11, first_sun_nov, tzinfo=KST)
    return mar_date <= now < nov_date


def _us_market_hours_kst() -> tuple[str, str]:
    """미국 정규장 KST 시작/종료 시각 (서머타임 자동 반영).
    EST(겨울): 23:30~06:00 KST | EDT(여름): 22:30~05:00 KST"""
    if _is_us_dst():
        return "22:30", "05:00"
    return "23:30", "06:00"


def _is_market_open(settings: dict) -> tuple[bool, str]:
    """한국/미국 장 시간인지 확인합니다. (둘 중 하나라도 열려있으면 True)
    주말(토/일)에는 무조건 False. 미국 장 시간은 서머타임(DST) 자동 반영."""
    now = datetime.now(KST)

    # 주말 체크 (월=0 ~ 금=4 평일, 토=5 일=6 주말)
    if now.weekday() >= 5:
        return False, ""

    now_min = now.hour * 60 + now.minute

    # 한국 장 (09:00 ~ 15:20 KST, 평일만)
    kr = settings.get("trading_hours_kr", settings.get("trading_hours", {}))
    kr_start = sum(int(x) * m for x, m in zip(kr.get("start", "09:00").split(":"), [60, 1]))
    kr_end = sum(int(x) * m for x, m in zip(kr.get("end", "15:20").split(":"), [60, 1]))
    if kr_start <= now_min < kr_end:
        return True, "KR"

    # 미국 장 (서머타임 자동 반영, 평일만)
    # 금요일 밤~토요일 새벽은 미국장 오픈이지만, 토요일 새벽(weekday=5)은 위에서 이미 차단됨
    us_default_start, us_default_end = _us_market_hours_kst()
    us = settings.get("trading_hours_us", {})
    us_start = sum(int(x) * m for x, m in zip(us.get("start", us_default_start).split(":"), [60, 1]))
    us_end = sum(int(x) * m for x, m in zip(us.get("end", us_default_end).split(":"), [60, 1]))
    if us_start <= now_min or now_min < us_end:  # 자정 넘김 처리
        return True, "US"

    return False, ""


def _us_analysis_time_kst() -> tuple[int, int]:
    """미국장 분석 실행 시각 (KST, 장 오픈 10분 후).
    EST(겨울): 23:40 KST | EDT(여름): 22:40 KST"""
    return (22, 40) if _is_us_dst() else (23, 40)


def _next_trading_run_time():
    """다음 실행 시각 계산 (09:10 KST 한국장 / 23:40 또는 22:40 KST 미국장).

    미국장 시간은 서머타임(DST) 자동 반영.
    주말(토/일)은 건너뛰고 다음 평일(월요일)로 이동.
    """
    now = datetime.now(KST)
    us_h, us_m = _us_analysis_time_kst()

    # 오늘부터 최대 7일 탐색 (주말 건너뛰기)
    for offset in range(7):
        day = now.date() + timedelta(days=offset)
        # 주말 건너뛰기 (토=5, 일=6)
        if day.weekday() >= 5:
            continue
        run_times = [
            datetime(day.year, day.month, day.day, 9, 10, tzinfo=KST),
            datetime(day.year, day.month, day.day, us_h, us_m, tzinfo=KST),
        ]
        for t in run_times:
            if t > now:
                return t

    # 폴백 (도달하면 안 되지만 안전장치)
    tomorrow = now.date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, 9, 10, tzinfo=KST)


async def _trading_bot_loop():
    """자동매매 봇 루프 — 투자팀장이 분석 → 자동 매매.

    흐름:
    1. 하루 2회 정해진 시각에 실행 (09:10 KST, 14:50 KST)
    2. 관심종목이 있으면 CIO 팀에게 분석 위임
    3. CIO가 4명 전문가 결과를 취합하여 매수/매도/관망 판단
    4. 신뢰도 70% 이상 시그널만 자동 주문 실행 (auto_execute=True일 때만)
    5. 모의투자 모드(paper_trading=True)에서는 가상 포트폴리오만 업데이트
    """
    logger = logging.getLogger("corthex.trading")
    us_h, us_m = _us_analysis_time_kst()
    logger.info("자동매매 봇 루프 시작 (CIO 연동 — 하루 2회: 09:10 한국장 + %02d:%02d 미국장 KST)", us_h, us_m)

    while app_state.trading_bot_active:
        try:
            next_run = _next_trading_run_time()
            now = datetime.now(KST)
            sleep_seconds = (next_run - now).total_seconds()
            logger.info("[TRADING BOT] 다음 실행 예약: %s (약 %.0f초 후)",
                        next_run.strftime("%Y-%m-%d %H:%M KST"), sleep_seconds)
            if sleep_seconds > 0:
                await asyncio.sleep(sleep_seconds)
            if not app_state.trading_bot_active:
                break

            settings = _load_data("trading_settings", _default_trading_settings())
            is_open, market = _is_market_open(settings)

            if not is_open:
                continue

            # 관심종목 확인
            watchlist = _load_data("trading_watchlist", [])
            if not watchlist:
                continue

            # 해당 시장의 관심종목만 필터 (한국 장이면 한국 종목, 미국 장이면 미국 종목)
            market_watchlist = [w for w in watchlist if w.get("market", "KR") == market]
            if not market_watchlist:
                continue

            market_name = "한국" if market == "KR" else "미국"
            logger.info("[TRADING BOT] %s장 오픈 — %d개 종목 분석 시작", market_name, len(market_watchlist))
            save_activity_log("fin_analyst",
                f"🤖 자동매매 봇: {market_name}장 {len(market_watchlist)}개 종목 분석+매매 시작",
                "info")

            # ── 수동 실행과 동일한 로직 사용 (서버 사전계산 + QA + 매매 실행) ──
            tickers_for_bot = [w["ticker"] for w in market_watchlist]
            try:
                result = await _run_trading_now_inner(selected_tickers=tickers_for_bot, auto_bot=True)
                _sig_count = result.get("signals_count", 0)
                _orders = result.get("orders_triggered", 0)
                _cost = result.get("cost_usd", 0)
                logger.info("[TRADING BOT] 분석 완료: 시그널 %d건, 주문 %d건, 비용 $%.4f", _sig_count, _orders, _cost)
                save_activity_log("fin_analyst",
                    f"✅ 자동매매 봇 완료: 시그널 {_sig_count}건, 주문 {_orders}건 (비용 ${_cost:.4f})", "info")
            except Exception as inner_err:
                logger.error("[TRADING BOT] _run_trading_now_inner 오류: %s", inner_err)
                save_activity_log("fin_analyst",
                    f"❌ 자동매매 봇 분석 오류: {inner_err}", "error")

        except Exception as e:
            logger.error("[TRADING BOT] 에러: %s", e)

    logger.info("자동매매 봇 루프 종료")
