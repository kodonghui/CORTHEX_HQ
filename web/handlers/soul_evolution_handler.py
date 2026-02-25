"""Soul 자동 진화 API — 반려 학습(warnings) 분석 → 소울 변경 제안 → 자동 적용.

비유: 인사팀이 직원들의 반복 실수 패턴을 분석해서
      매뉴얼(소울)을 자동으로 개선 + 경고(warnings) 초기화.
      대표님은 결과만 확인. (2026-02-25 대표님 지시: "귀찮아 알아서 해라")
"""
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request

from db import load_setting, save_setting, save_activity_log

logger = logging.getLogger("corthex.soul_evolution")
router = APIRouter(tags=["soul-evolution"])

KST = ZoneInfo("Asia/Seoul")
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent  # web/
SOULS_DIR = BASE_DIR.parent / "souls" / "agents"

# DB 키
_PROPOSALS_KEY = "soul_evolution_proposals"
_HISTORY_KEY = "soul_evolution_history"


# ── 유틸리티 ──

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
    """에이전트의 현재 소울(시스템 프롬프트)을 로드합니다.

    우선순위: DB 오버라이드 > souls/*.md 파일
    """
    # 1순위: DB 오버라이드
    db_soul = load_setting(f"soul_{agent_id}")
    if db_soul:
        return db_soul
    # 2순위: 파일
    soul_path = SOULS_DIR / f"{agent_id}.md"
    if soul_path.exists():
        try:
            return soul_path.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


# ── 핵심: warnings 분석 → 제안 생성 ──

async def run_soul_evolution_analysis() -> dict:
    """모든 에이전트의 warnings 메모리를 분석하여 소울 변경을 제안합니다.

    비유: 인사팀이 전 직원의 '빨간펜 메모장'을 모아서 읽고,
          매뉴얼 개선이 필요한 직원의 리스트 + 구체적 변경안을 보고서로 작성.
    """
    from ai_handler import ask_ai  # 지연 임포트 (순환 방지)

    agents = _load_agents_yaml()
    if not agents:
        return {"status": "error", "message": "agents.yaml 로드 실패"}

    # 1) 전 에이전트 warnings 수집
    warnings_by_agent: dict[str, str] = {}
    for agent in agents:
        aid = agent.get("agent_id", "")
        if not aid or agent.get("dormant"):
            continue
        mem = load_setting(f"memory_categorized_{aid}", {})
        w = mem.get("warnings", "").strip()
        if w:
            warnings_by_agent[aid] = w

    if not warnings_by_agent:
        logger.info("Soul 진화: 분석할 warnings 없음")
        return {"status": "no_warnings", "proposals": 0}

    # 2) Sonnet으로 패턴 분석 + 소울 변경 제안
    proposals: list[dict] = []
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    for aid, warnings in warnings_by_agent.items():
        current_soul = _load_current_soul(aid)
        agent_name = next(
            (a.get("name_ko", aid) for a in agents if a.get("agent_id") == aid), aid
        )

        prompt = f"""다음은 '{agent_name}' ({aid}) 에이전트의 반려 학습 기록(warnings)입니다:

{warnings}

현재 소울(시스템 프롬프트) 앞부분:
{current_soul[:1500]}

위 반려 패턴을 분석하여 소울 개선안을 제안하세요.

반드시 아래 형식으로만 답변하세요:

## 패턴 분석
(반복되는 문제 1~3줄 요약)

## 추가할 텍스트
(소울 파일에 그대로 추가할 마크다운 텍스트. 기존 내용과 중복되면 안 됨)

## 근거
(이 변경이 반려 감소에 도움되는 이유 1줄)

반려 기록이 1~2건뿐이거나 패턴이 불명확하면 "변경 불필요"라고만 답하세요."""

        try:
            result = await ask_ai(
                user_message=prompt,
                system_prompt="당신은 AI 에이전트 소울(시스템 프롬프트) 최적화 전문가입니다. "
                              "반려 패턴에서 반복되는 문제를 찾아 구체적이고 실용적인 소울 변경을 제안합니다.",
                model="claude-sonnet-4-6",
                reasoning_effort="medium",
            )
        except Exception as e:
            logger.warning("Soul 진화 분석 실패 (%s): %s", aid, e)
            continue

        content = result.get("content", "")
        if not content or "변경 불필요" in content:
            continue

        proposal = {
            "id": str(uuid.uuid4())[:8],
            "agent_id": aid,
            "agent_name": agent_name,
            "warnings": warnings,
            "current_soul_snippet": current_soul[:300] + ("..." if len(current_soul) > 300 else ""),
            "proposed_change": content,
            "status": "auto_approved",
            "created_at": now_str,
            "approved_at": now_str,
            "cost_usd": result.get("cost_usd", 0),
        }

        # 자동 적용: 소울 업데이트 + warnings 초기화
        add_text = _extract_addition_text(content)
        if add_text:
            updated_soul = current_soul.rstrip() + "\n\n" + add_text
            save_setting(f"soul_{aid}", updated_soul)
            logger.info("Soul 진화 자동 적용: %s — 소울 업데이트 완료", aid)

            # warnings 초기화
            mem_key = f"memory_categorized_{aid}"
            mem = load_setting(mem_key, {})
            proposal["cleared_warnings"] = mem.get("warnings", "")
            mem["warnings"] = ""
            save_setting(mem_key, mem)

        proposals.append(proposal)

    # 3) 제안 저장 + 히스토리 자동 기록
    save_setting(_PROPOSALS_KEY, proposals)
    if proposals:
        history = load_setting(_HISTORY_KEY, [])
        for p in proposals:
            history.insert(0, p)
        if len(history) > 100:
            history = history[:100]
        save_setting(_HISTORY_KEY, history)
    save_activity_log("system", f"🧬 Soul 진화 자동 적용 완료: {len(warnings_by_agent)}명 분석 → {len(proposals)}건 적용", "info")

    # 4) 텔레그램 알림
    if proposals:
        await _send_telegram_notification(proposals, len(warnings_by_agent))

    return {"status": "completed", "analyzed": len(warnings_by_agent), "proposals": len(proposals)}


async def _send_telegram_notification(proposals: list[dict], analyzed_count: int):
    """대표님에게 텔레그램으로 Soul 진화 제안 알림을 보냅니다."""
    from state import app_state

    if not app_state.telegram_app:
        return
    ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
    if not ceo_id:
        return

    msg = f"🧬 주간 Soul 진화 제안 도착\n\n"
    msg += f"분석 대상: {analyzed_count}명\n"
    msg += f"변경 제안: {len(proposals)}건\n\n"
    for p in proposals[:5]:
        msg += f"• {p['agent_name']} ({p['agent_id']})\n"
    if len(proposals) > 5:
        msg += f"  ... 외 {len(proposals) - 5}건\n"
    msg += f"\n웹에서 확인: https://corthex-hq.com\n(에이전트 탭 → Soul 진화)"

    try:
        await app_state.telegram_app.bot.send_message(chat_id=int(ceo_id), text=msg)
    except Exception as e:
        logger.warning("Soul 진화 텔레그램 발송 실패: %s", e)


# ── API 엔드포인트 ──

@router.get("/api/soul-evolution/proposals")
async def get_proposals():
    """현재 대기 중인 Soul 변경 제안 목록을 반환합니다."""
    proposals = load_setting(_PROPOSALS_KEY, [])
    return {"proposals": proposals, "count": len(proposals)}


@router.post("/api/soul-evolution/run")
async def trigger_evolution():
    """Soul 진화 분석을 수동으로 즉시 실행합니다."""
    import asyncio
    task = asyncio.create_task(run_soul_evolution_analysis())
    return {"success": True, "message": "Soul 진화 분석을 시작합니다. 완료 시 텔레그램으로 알림됩니다."}


@router.post("/api/soul-evolution/approve/{proposal_id}")
async def approve_proposal(proposal_id: str):
    """Soul 변경 제안을 승인합니다.

    승인 시:
    1. 현재 소울에 제안 텍스트 추가 → DB에 저장 (soul_{agent_id})
    2. 해당 에이전트의 warnings 초기화
    3. 히스토리에 기록
    """
    proposals = load_setting(_PROPOSALS_KEY, [])
    target = None
    for p in proposals:
        if p.get("id") == proposal_id:
            target = p
            break

    if not target:
        return {"success": False, "error": "제안을 찾을 수 없습니다"}

    aid = target["agent_id"]

    # 1) 현재 소울 로드 + 제안 추가
    current_soul = _load_current_soul(aid)
    proposed = target.get("proposed_change", "")

    # "## 추가할 텍스트" 섹션만 추출
    add_text = _extract_addition_text(proposed)
    if add_text:
        updated_soul = current_soul.rstrip() + "\n\n" + add_text
        save_setting(f"soul_{aid}", updated_soul)
        logger.info("Soul 진화 승인: %s — DB에 소울 업데이트 완료", aid)
    else:
        logger.warning("Soul 진화: %s — 추가할 텍스트 추출 실패", aid)

    # 2) warnings 초기화
    mem_key = f"memory_categorized_{aid}"
    mem = load_setting(mem_key, {})
    cleared_warnings = mem.get("warnings", "")
    mem["warnings"] = ""
    save_setting(mem_key, mem)

    # 3) 상태 업데이트 + 히스토리
    target["status"] = "approved"
    target["approved_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    target["cleared_warnings"] = cleared_warnings
    save_setting(_PROPOSALS_KEY, proposals)

    history = load_setting(_HISTORY_KEY, [])
    history.insert(0, target)
    if len(history) > 100:
        history = history[:100]
    save_setting(_HISTORY_KEY, history)

    save_activity_log("system", f"🧬 Soul 진화 승인: {target.get('agent_name', aid)} — 소울 업데이트 완료", "info")

    return {"success": True, "agent_id": aid, "message": f"{target.get('agent_name', aid)} 소울 업데이트 + warnings 초기화 완료"}


@router.post("/api/soul-evolution/reject/{proposal_id}")
async def reject_proposal(proposal_id: str):
    """Soul 변경 제안을 거부합니다. warnings는 유지됩니다."""
    proposals = load_setting(_PROPOSALS_KEY, [])
    target = None
    for p in proposals:
        if p.get("id") == proposal_id:
            target = p
            break

    if not target:
        return {"success": False, "error": "제안을 찾을 수 없습니다"}

    target["status"] = "rejected"
    target["rejected_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    save_setting(_PROPOSALS_KEY, proposals)

    history = load_setting(_HISTORY_KEY, [])
    history.insert(0, target)
    if len(history) > 100:
        history = history[:100]
    save_setting(_HISTORY_KEY, history)

    save_activity_log("system", f"🧬 Soul 진화 거부: {target.get('agent_name', target['agent_id'])}", "info")

    return {"success": True, "message": "제안이 거부되었습니다. warnings는 유지됩니다."}


@router.get("/api/soul-evolution/history")
async def get_history():
    """승인/거부된 Soul 변경 히스토리를 반환합니다."""
    history = load_setting(_HISTORY_KEY, [])
    return {"history": history, "count": len(history)}


# ── 유틸리티 ──

def _extract_addition_text(proposed_change: str) -> str:
    """제안에서 '## 추가할 텍스트' 섹션만 추출합니다."""
    lines = proposed_change.split("\n")
    capture = False
    result = []
    for line in lines:
        if "추가할 텍스트" in line and line.strip().startswith("#"):
            capture = True
            continue
        if capture and line.strip().startswith("## "):
            break
        if capture:
            result.append(line)
    text = "\n".join(result).strip()
    if not text:
        # 폴백: 전체 제안을 주석으로 래핑
        text = f"<!-- Soul 진화 제안 -->\n{proposed_change}"
    return text
