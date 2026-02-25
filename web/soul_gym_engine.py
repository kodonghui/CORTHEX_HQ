"""Soul Gym 엔진 — 에이전트 소울 경쟁 진화 시스템.

비유: 운동 선수 훈련장. 에이전트의 매뉴얼(소울)을 약간씩 바꿔서
      같은 시험(모의투자 분석)을 치르게 하고, 가장 잘하는 버전을 채택.

논문 기반:
- EvoPrompt (ICLR 2024): 변이 생성 + 토너먼트 선택
- OPRO (Google DeepMind): 메타프롬프트에 히스토리 포함
- DGM (Sakana AI): 모든 변이 기록 보존 (다양성 유지)

이원화 구조:
- Gym 실행: gemini-2.5-flash (저비용)
- 실사용: 대표님 선호 모델 (변경 없음)
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger("corthex.soul_gym")
KST = ZoneInfo("Asia/Seoul")
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
SOULS_DIR = BASE_DIR.parent / "souls" / "agents"

# ── 설정 ──
GYM_MODEL = "gemini-2.5-flash"       # Gym 전용 모델 (저비용)
JUDGE_MODEL = "gemini-2.5-flash"     # 채점 모델
VARIANT_MODEL = "gemini-2.5-flash"   # 변이 생성 모델
MIN_IMPROVEMENT = 3.0                # 최소 개선폭 (전 종목 평균 기준)
COST_CAP_USD = 20.0                  # 1회 전체 진화 비용 상한
MAX_SOUL_SNIPPET = 1500              # 소울 스니펫 길이

# 벤치마크가 모의투자 분석이므로, 투자팀장만 대상
GYM_TARGET_AGENTS = ["cio_manager"]


def _load_agents_yaml() -> list[dict]:
    """config/agents.yaml에서 에이전트 목록 로드."""
    config_dir = BASE_DIR.parent / "config"
    try:
        import yaml
        path = config_dir / "agents.yaml"
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else data.get("agents", [])
    except Exception as e:
        logger.debug("agents.yaml 로드 실패: %s", e)
    return []


def _load_current_soul(agent_id: str) -> str:
    """에이전트의 현재 소울을 로드합니다. DB 오버라이드 > 파일."""
    from db import load_setting
    db_soul = load_setting(f"soul_{agent_id}")
    if db_soul:
        return db_soul
    soul_path = SOULS_DIR / f"{agent_id}.md"
    if soul_path.exists():
        try:
            return soul_path.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


def _load_watchlist() -> list[dict]:
    """관심종목 로드."""
    from db import load_setting
    return load_setting("trading_watchlist", [])


def _load_warnings(agent_id: str) -> str:
    """에이전트의 반복 실수 기록(warnings)을 로드합니다."""
    from db import load_setting
    mem = load_setting(f"memory_categorized_{agent_id}", {})
    return mem.get("warnings", "").strip() if isinstance(mem, dict) else ""


def _load_gym_history(agent_id: str, limit: int = 5) -> list[dict]:
    """최근 진화 히스토리 로드 (OPRO 메타프롬프트용)."""
    from db import get_soul_gym_history
    return get_soul_gym_history(agent_id=agent_id, limit=limit)


# ══════════════════════════════════════════════════════════════
# 1. 변이 생성 (EvoPrompt + OPRO)
# ══════════════════════════════════════════════════════════════

async def generate_variants(
    agent_id: str,
    soul_current: str,
    warnings: str,
    history: list[dict],
) -> dict:
    """소울 변이 A/B/C를 생성합니다.

    - Variant A: 규칙 추가형 (새 규칙 1~2줄)
    - Variant B: 표현 강화형 (기존 모호한 규칙을 구체화)
    - Variant C: 교차형 (A+B 장점 결합)
    """
    from ai_handler import ask_ai

    # OPRO: 이전 진화 기록 테이블
    history_table = ""
    if history:
        history_table = "## 과거 진화 기록 (참고: 효과 없었던 방향 피하기)\n"
        history_table += "| 라운드 | 채택 | 점수변화 | 변경요약 |\n|---|---|---|---|\n"
        for h in history[:5]:
            vj = json.loads(h.get("variants_json", "{}")) if isinstance(h.get("variants_json"), str) else h.get("variants_json", {})
            summary = vj.get("winner_summary", "정보 없음")[:60]
            history_table += f"| R{h['round_num']} | {h['winner']} | {h['score_before']:.0f}→{h['score_after']:.0f} | {summary} |\n"
        history_table += "\n"

    warnings_section = f"## 반복 실수 기록 (warnings)\n{warnings}\n\n" if warnings else ""
    soul_snippet = soul_current[:MAX_SOUL_SNIPPET]

    total_cost = 0.0
    variants = {}

    for variant_type, instruction in [
        ("variant_A", (
            "Variant A (규칙 추가형)를 생성하세요.\n"
            "- 기존 소울 내용을 삭제하지 마세요\n"
            "- 구체적이고 행동 가능한 규칙 1~2개를 맨 끝에 추가하세요\n"
            "- 추가 내용은 100자 이내로 간결하게\n"
            "- 반드시 변경된 소울 전체를 출력하세요"
        )),
        ("variant_B", (
            "Variant B (표현 강화형)를 생성하세요.\n"
            "- 기존 소울에서 모호한 규칙을 찾아 더 구체적으로 수정하세요\n"
            "- 삭제하지 말고, 기존 문장을 더 명확하게 다듬으세요\n"
            "- 수정은 2~3곳 이내\n"
            "- 반드시 변경된 소울 전체를 출력하세요"
        )),
        ("variant_C", (
            "Variant C (교차형)를 생성하세요.\n"
            "- Variant A의 규칙 추가 + Variant B의 표현 강화를 동시에 적용하세요\n"
            "- 단, 과도한 변경은 피하세요 (전체 변경량 150자 이내)\n"
            "- 반드시 변경된 소울 전체를 출력하세요"
        )),
    ]:
        prompt = f"""당신은 AI 에이전트 소울(시스템 프롬프트) 진화 전문가입니다.

{history_table}{warnings_section}## 현재 소울
{soul_snippet}

## 지시
{instruction}"""

        try:
            result = await ask_ai(
                user_message=prompt,
                system_prompt="소울 진화 전문가. 에이전트 성능 향상을 위한 소울 변이를 생성합니다.",
                model=VARIANT_MODEL,
            )
            variants[variant_type] = result.get("content", "")
            total_cost += result.get("cost_usd", 0)
        except Exception as e:
            logger.warning("변이 생성 실패 (%s, %s): %s", agent_id, variant_type, e)
            variants[variant_type] = ""

    return {"variants": variants, "cost_usd": total_cost}


# ══════════════════════════════════════════════════════════════
# 2. 벤치마크 실행 (모의투자 분석)
# ══════════════════════════════════════════════════════════════

async def run_benchmark(agent_id: str, soul: str, watchlist: list[dict]) -> dict:
    """주어진 소울로 watchlist 전 종목을 모의투자 분석하고 점수를 받습니다.

    실제 _manager_with_delegation() 대신 ask_ai()로 직접 실행.
    Gym은 flash2.5로 돌리므로 실사용 모델과 분리됨.
    """
    from ai_handler import ask_ai

    if not watchlist:
        return {"score": 0, "cost_usd": 0, "details": []}

    tickers_info = ", ".join([f"{w.get('name', '')}({w.get('ticker', '')})" for w in watchlist[:15]])
    market_label = "한국" if watchlist[0].get("market", "KR") == "KR" else "미국"

    prompt = f"""[Soul Gym 벤치마크 — {market_label}장 모의투자 분석]

## 분석 대상 ({len(watchlist)}개 종목)
{tickers_info}

## 분석 요청
각 종목에 대해 아래 분석을 수행하세요:
- **시황분석**: 지수 흐름, 외국인/기관 동향, 금리/환율
- **종목분석**: 재무 건전성, PER/PBR, 최근 실적
- **기술적분석**: RSI, MACD, 이동평균선
- **리스크관리**: 손절가, 적정 포지션 크기

## 최종 산출물 (반드시 아래 형식으로)
[시그널] 종목명 (티커) | 매수/매도/관망 | 신뢰도 N% | 근거 1줄
"""

    try:
        result = await ask_ai(
            user_message=prompt,
            system_prompt=soul,
            model=GYM_MODEL,
        )
        content = result.get("content", "")
        cost = result.get("cost_usd", 0)

        # 채점
        score = await judge_response(content, tickers_info, len(watchlist))
        return {"score": score, "cost_usd": cost, "content_preview": content[:300]}
    except Exception as e:
        logger.warning("벤치마크 실행 실패 (%s): %s", agent_id, e)
        return {"score": 0, "cost_usd": 0, "error": str(e)[:100]}


# ══════════════════════════════════════════════════════════════
# 3. 채점 (LLM-as-Judge)
# ══════════════════════════════════════════════════════════════

async def judge_response(response: str, tickers_info: str, num_stocks: int) -> float:
    """Sonnet/Flash가 투자 분석 결과를 0~100 채점합니다."""
    from ai_handler import ask_ai

    prompt = f"""아래는 {num_stocks}개 종목({tickers_info}) 투자 분석 결과입니다.

## 분석 결과
{response[:3000]}

## 채점 기준 (총 100점)
1. **BLUF 형식** (20점): 각 종목 결론이 명확하게 먼저 나오는가?
2. **전문성** (30점): PER/PBR/ROE 등 재무지표가 정확하고 논리적인가?
3. **구체성** (30점): 목표가/손절가가 숫자로 제시되고 시나리오가 있는가?
4. **구조** (20점): 가독성 좋고, 종목별로 구분되어 있는가?

## 응답 형식 (반드시 이 형식만)
BLUF: [0-20]
전문성: [0-30]
구체성: [0-30]
구조: [0-20]
총점: [0-100]"""

    try:
        result = await ask_ai(
            user_message=prompt,
            system_prompt="당신은 투자 분석 품질 심사관입니다. 엄격하고 일관된 채점을 합니다.",
            model=JUDGE_MODEL,
        )
        content = result.get("content", "")
        # 총점 파싱
        for line in content.split("\n"):
            if "총점" in line:
                import re
                nums = re.findall(r"\d+", line)
                if nums:
                    score = float(nums[-1])
                    return min(100.0, max(0.0, score))
        return 0.0
    except Exception as e:
        logger.warning("채점 실패: %s", e)
        return 0.0


# ══════════════════════════════════════════════════════════════
# 4. 메인 진화 함수
# ══════════════════════════════════════════════════════════════

async def evolve_agent(agent_id: str, dry_run: bool = False) -> dict:
    """에이전트 1명의 소울 진화를 실행합니다.

    1. 현재 소울 + warnings + 히스토리 로드
    2. 변이 A/B/C 생성 (flash2.5)
    3. 원본 + 변이들 벤치마크 실행 (watchlist 전 종목)
    4. 채점 → 최고 점수 선택
    5. +3점 이상이면 자동 채택, 아니면 원본 유지
    """
    from db import save_setting, save_soul_gym_round, get_soul_gym_next_round, save_activity_log

    start_time = time.time()
    agents = _load_agents_yaml()
    agent_cfg = next((a for a in agents if a.get("agent_id") == agent_id), None)
    agent_name = agent_cfg.get("name_ko", agent_id) if agent_cfg else agent_id

    soul_current = _load_current_soul(agent_id)
    if not soul_current:
        return {"status": "error", "message": f"{agent_name}: 소울 없음"}

    warnings = _load_warnings(agent_id)
    history = _load_gym_history(agent_id)
    watchlist = _load_watchlist()
    if not watchlist:
        return {"status": "error", "message": "관심종목 없음"}

    round_num = get_soul_gym_next_round(agent_id)
    total_cost = 0.0

    logger.info("🧬 Soul Gym 시작: %s (R%d) — watchlist %d종목", agent_name, round_num, len(watchlist))
    save_activity_log("system", f"🧬 Soul Gym: {agent_name} R{round_num} 시작 ({len(watchlist)}종목)", "info")

    # ── Step 1: 변이 생성 ──
    gen_result = await generate_variants(agent_id, soul_current, warnings, history)
    variants = gen_result["variants"]
    total_cost += gen_result["cost_usd"]

    valid_variants = {k: v for k, v in variants.items() if v.strip()}
    if not valid_variants:
        return {"status": "error", "message": f"{agent_name}: 변이 생성 실패"}

    # ── Step 2: 벤치마크 실행 (원본 + 변이들) ──
    candidates = {"original": soul_current}
    candidates.update(valid_variants)

    scores = {}
    for name, soul in candidates.items():
        bench = await run_benchmark(agent_id, soul, watchlist)
        scores[name] = bench["score"]
        total_cost += bench.get("cost_usd", 0)
        logger.info("  %s: %.1f점", name, bench["score"])

    # ── Step 3: 최고 점수 선택 ──
    best_name = max(scores, key=scores.get)
    score_before = scores.get("original", 0)
    score_after = scores[best_name]
    improvement = score_after - score_before

    # ── Step 4: 채택 판정 ──
    adopted = False
    winner = "original"
    soul_after_text = ""

    if best_name != "original" and improvement >= MIN_IMPROVEMENT:
        winner = best_name
        soul_after_text = valid_variants.get(best_name, "")
        adopted = True

        if not dry_run:
            save_setting(f"soul_{agent_id}", soul_after_text)
            logger.info("🧬 %s 소울 채택: %s (+%.1f점)", agent_name, winner, improvement)
            save_activity_log(
                "system",
                f"🧬 Soul Gym 채택: {agent_name} {winner} — {score_before:.0f}→{score_after:.0f} (+{improvement:.0f}점)",
                "info",
            )
    else:
        save_activity_log(
            "system",
            f"🧬 Soul Gym 유지: {agent_name} 원본 최고 — 최고변이 {best_name} +{improvement:.1f}점 (임계값 {MIN_IMPROVEMENT}점 미달)",
            "info",
        )

    elapsed = time.time() - start_time

    # ── Step 5: 결과 기록 (모든 변이 보존 — DGM 방식) ──
    record = {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "round_num": round_num,
        "soul_before": soul_current[:500],
        "soul_after": soul_after_text[:500] if adopted else "",
        "winner": winner,
        "score_before": score_before,
        "score_after": score_after if adopted else score_before,
        "improvement": improvement if adopted else 0,
        "cost_usd": total_cost,
        "variants_json": json.dumps({
            "scores": scores,
            "adopted": adopted,
            "winner_summary": f"{winner}: {improvement:+.1f}점",
            "elapsed_seconds": round(elapsed, 1),
        }, ensure_ascii=False),
        "benchmark_json": json.dumps({
            "watchlist_count": len(watchlist),
            "model": GYM_MODEL,
            "min_improvement": MIN_IMPROVEMENT,
        }, ensure_ascii=False),
    }

    if not dry_run:
        save_soul_gym_round(record)

    return {
        "status": "adopted" if adopted else "retained",
        "agent_id": agent_id,
        "agent_name": agent_name,
        "round_num": round_num,
        "winner": winner,
        "score_before": score_before,
        "score_after": score_after,
        "improvement": improvement,
        "adopted": adopted,
        "cost_usd": round(total_cost, 4),
        "elapsed_seconds": round(elapsed, 1),
        "scores": scores,
        "dry_run": dry_run,
    }


# ══════════════════════════════════════════════════════════════
# 5. 전체 에이전트 진화
# ══════════════════════════════════════════════════════════════

async def evolve_all(dry_run: bool = False) -> dict:
    """투자팀장 진화. 벤치마크가 모의투자 분석이므로 투자팀장만 대상.

    다른 팀장은 부서별 벤치마크 추가 시 확장 가능.
    """
    from db import save_activity_log

    agents = _load_agents_yaml()
    managers = [a for a in agents if a.get("agent_id") in GYM_TARGET_AGENTS and not a.get("dormant")]

    if not managers:
        return {"status": "error", "message": "진화 대상 에이전트 없음 (투자팀장 확인)"}

    logger.info("🧬 Soul Gym 전체 진화 시작: %d명", len(managers))
    save_activity_log("system", f"🧬 Soul Gym 전체 진화 시작: {len(managers)}명", "info")

    results = []
    total_cost = 0.0

    for agent_cfg in managers:
        aid = agent_cfg["agent_id"]

        # 비용 캡 체크
        if total_cost >= COST_CAP_USD:
            logger.warning("🧬 비용 캡 도달 ($%.2f >= $%.2f), 중단", total_cost, COST_CAP_USD)
            save_activity_log("system", f"🧬 Soul Gym 비용 캡 도달 (${total_cost:.2f}), 중단", "warning")
            break

        try:
            result = await evolve_agent(aid, dry_run=dry_run)
            results.append(result)
            total_cost += result.get("cost_usd", 0)
        except Exception as e:
            logger.error("🧬 %s 진화 실패: %s", aid, e)
            results.append({"agent_id": aid, "status": "error", "message": str(e)[:100]})

    # 텔레그램 알림
    adopted_count = sum(1 for r in results if r.get("adopted"))
    summary = f"🧬 Soul Gym 완료: {len(results)}명 진화, {adopted_count}명 채택, 비용 ${total_cost:.2f}"
    save_activity_log("system", summary, "info")

    if not dry_run:
        await _send_telegram_summary(results, total_cost)

    return {
        "status": "completed",
        "total_agents": len(results),
        "adopted_count": adopted_count,
        "total_cost_usd": round(total_cost, 4),
        "results": results,
        "dry_run": dry_run,
    }


async def _send_telegram_summary(results: list[dict], total_cost: float):
    """진화 결과를 텔레그램으로 대표님에게 전송합니다."""
    try:
        from state import app_state
        if not app_state.telegram_app:
            return
        ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
        if not ceo_id:
            return

        adopted = [r for r in results if r.get("adopted")]
        retained = [r for r in results if not r.get("adopted") and r.get("status") != "error"]

        msg = f"🧬 Soul Gym 주간 진화 결과\n\n"
        if adopted:
            msg += f"✅ 채택 ({len(adopted)}명):\n"
            for r in adopted:
                msg += f"  • {r['agent_name']}: {r['score_before']:.0f}→{r['score_after']:.0f} (+{r['improvement']:.0f}점) [{r['winner']}]\n"
        if retained:
            msg += f"\n⬜ 원본 유지 ({len(retained)}명):\n"
            for r in retained:
                msg += f"  • {r['agent_name']}: {r.get('score_before', 0):.0f}점\n"
        msg += f"\n💰 총 비용: ${total_cost:.2f}"

        await app_state.telegram_app.bot.send_message(chat_id=int(ceo_id), text=msg)
    except Exception as e:
        logger.warning("Soul Gym 텔레그램 발송 실패: %s", e)
