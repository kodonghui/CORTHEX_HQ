"""
텔레그램 메시지 포맷터.

CORTHEX 보고서를 텔레그램 메시지 제한(4096자)에 맞게 변환합니다.
Markdown 깨짐 없이 안전하게 분할합니다.

포맷 종류:
  - 부서별 보고서 (format_department_report)
  - 단일 결과 보고서 (format_result) — 하위 호환
  - 진행 상황 (format_agent_working / format_progress_update / format_agent_done)
  - 작업 목록 (format_task_list / format_task_detail)
  - 에이전트/비용/헬스 (기존)
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.message import TaskResult
    from src.core.task_store import StoredTask

# 텔레그램 메시지 최대 길이 (여유분 확보)
_MAX_LEN = 4000

# ─── 부서 한국어 이름 매핑 ───

DIVISION_NAMES: dict[str, str] = {
    "secretary": "비서실",
    "leet_master": "LEET Master 본부",
    "leet_master.tech": "기술개발처",
    "leet_master.strategy": "사업기획처",
    "leet_master.legal": "법무처",
    "leet_master.marketing": "마케팅처",
    "finance": "투자분석 본부",
    "finance.investment": "투자분석처",
    "publishing": "출판/기록 본부",
}

_ROLE_ICONS: dict[str, str] = {
    "manager": "\U0001f451",      # 👑
    "specialist": "\U0001f4bc",   # 💼
    "worker": "\U0001f528",       # 🔨
}


def _div_display(division: str) -> str:
    """부서 코드를 한국어 이름으로 변환."""
    if division in DIVISION_NAMES:
        return DIVISION_NAMES[division]
    top = division.split(".")[0]
    return DIVISION_NAMES.get(top, division)


def _escape_md(text: str) -> str:
    """텔레그램 Markdown에서 깨질 수 있는 문자를 안전하게 처리."""
    # 텔레그램 Markdown v1에서 문제되는 문자: _ * [ ` 를 백슬래시 이스케이프
    # 단, 이미 우리가 의도적으로 넣은 마크다운은 제외하기 어려우므로
    # 사용자 입력(result_data 등)에만 적용
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


# ─── 1단계: 부서별 보고서 ───


def format_department_report(
    result: TaskResult,
    dept_data: dict[str, list[dict]],
    command: str = "",
) -> list[str]:
    """부서별로 정리된 보고서를 텔레그램 메시지 리스트로 변환.

    Args:
        result: 최종 TaskResult (비서실장 종합 보고)
        dept_data: {부서코드: [{agent_id, name_ko, division, summary, ...}, ...]}
        command: CEO가 내린 원래 명령
    """
    messages: list[str] = []

    # ── 메시지 1: 총괄 헤더 ──
    icon = "\u2705" if result.success else "\u274c"
    total_agents = sum(len(agents) for agents in dept_data.values())
    dept_count = len(dept_data)

    header = (
        f"{icon} *CORTHEX 보고서*\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
    )
    if command:
        header += f"\U0001f4ac CEO 지시: {command[:80]}\n"
    header += (
        f"\U0001f3e2 참여 부서: {dept_count}개 | "
        f"\U0001f464 참여 에이전트: {total_agents}명 | "
        f"\u23f1 총 {result.execution_time_seconds:.1f}초\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
    )
    messages.append(header)

    # ── 메시지 2+: 부서별 상세 ──
    for div_code in sorted(dept_data.keys()):
        agents = dept_data[div_code]
        div_name = _div_display(div_code)

        lines = [f"\U0001f3e2 *{div_name}* ({len(agents)}명 참여)\n"]
        for a in agents:
            a_icon = "\u2705" if a.get("success", True) else "\u274c"
            name = a.get("name_ko", a.get("agent_id", "?"))
            time_s = a.get("execution_time", 0)
            summary = a.get("summary", "")
            if summary:
                summary = summary[:200] + ("..." if len(summary) > 200 else "")
                lines.append(f"  {a_icon} *{name}* ({time_s:.0f}초)")
                lines.append(f"      {summary}")
            else:
                lines.append(f"  {a_icon} *{name}* ({time_s:.0f}초)")

        dept_text = "\n".join(lines)
        # 부서 하나가 4000자 넘으면 분할
        for part in _split_message(dept_text):
            messages.append(part)

    # ── 메시지 마지막: 최종 요약 ──
    synthesis = str(result.result_data or result.summary)
    if synthesis:
        # 요약은 2000자까지만 보여주고, 전체는 /detail 로 유도
        if len(synthesis) > 2000:
            short = synthesis[:2000] + "\n\n..."
            summary_msg = (
                f"\U0001f4ca *최종 요약*\n"
                f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
                f"{short}\n\n"
                f"\U0001f4a1 전체 보고서: /detail 입력"
            )
        else:
            summary_msg = (
                f"\U0001f4ca *최종 요약*\n"
                f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
                f"{synthesis}"
            )
        for part in _split_message(summary_msg):
            messages.append(part)

    return messages


# ─── 2단계: 실시간 진행 상황 ───


def format_agent_working(agent_id: str, name_ko: str, division: str) -> str:
    """에이전트 작업 시작 메시지."""
    div_name = _div_display(division)
    return f"\u2699\ufe0f *{div_name}* | {name_ko} 작업 시작"


def format_progress_update(
    name_ko: str,
    division: str,
    progress_pct: float = 0.0,
    current_step: str = "",
    detail: str = "",
) -> str:
    """에이전트 진행 상황 메시지 (기존 메시지를 수정하는 용도)."""
    div_name = _div_display(division)
    bar = _progress_bar(progress_pct)
    lines = [f"\u2699\ufe0f *{div_name}* | {name_ko}", bar]
    if current_step:
        lines.append(f"  {current_step}")
    if detail:
        lines.append(f"  {detail[:100]}")
    return "\n".join(lines)


def format_agent_done(name_ko: str, division: str, time_seconds: float = 0.0) -> str:
    """에이전트 작업 완료 메시지."""
    div_name = _div_display(division)
    return f"\U0001f7e2 *{div_name}* | {name_ko} 완료 ({time_seconds:.0f}초)"


def _progress_bar(pct: float) -> str:
    """진행률 바 생성. 0.0~1.0 범위."""
    pct = max(0.0, min(1.0, pct))
    filled = int(pct * 10)
    empty = 10 - filled
    bar = "\u2588" * filled + "\u2591" * empty
    return f"  {bar} {int(pct * 100)}%"


# ─── 2단계: 작업 목록 조회 ───


def format_task_list(tasks: list[StoredTask]) -> str:
    """최근 작업 목록을 텔레그램 메시지로 포맷."""
    if not tasks:
        return "\U0001f4cb 최근 작업이 없습니다."

    status_icons = {
        "completed": "\u2705",
        "running": "\u2699\ufe0f",
        "failed": "\u274c",
        "queued": "\u23f3",
    }

    lines = ["*\U0001f4cb 최근 작업 목록*\n"]
    for t in tasks[:10]:
        icon = status_icons.get(t.status.value, "\u2753")
        from datetime import timezone, timedelta
        kst = timezone(timedelta(hours=9))
        time_str = t.created_at.astimezone(kst).strftime("%m/%d %H:%M")
        cmd_preview = t.command[:40] + ("..." if len(t.command) > 40 else "")
        time_info = f"{t.execution_time_seconds:.0f}초" if t.execution_time_seconds else "진행중"
        lines.append(
            f"{icon} `{t.task_id}` {cmd_preview}\n"
            f"    {time_str} | {time_info} | ${t.cost_usd:.4f}"
        )

    lines.append(f"\n\U0001f50d 상세 보기: /task [작업ID]")
    return "\n".join(lines)


def format_task_detail(task: StoredTask) -> list[str]:
    """특정 작업의 상세 정보를 메시지 리스트로 변환."""
    from datetime import timezone, timedelta
    kst = timezone(timedelta(hours=9))

    status_icons = {
        "completed": "\u2705 완료",
        "running": "\u2699\ufe0f 진행중",
        "failed": "\u274c 실패",
        "queued": "\u23f3 대기중",
    }
    status_text = status_icons.get(task.status.value, task.status.value)

    header = (
        f"*\U0001f4c4 작업 상세*\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f194 작업 ID: `{task.task_id}`\n"
        f"\U0001f4ac 명령: {task.command[:200]}\n"
        f"\U0001f4ca 상태: {status_text}\n"
        f"\U0001f4c5 시작: {task.created_at.astimezone(kst).strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"\u23f1 소요: {task.execution_time_seconds:.1f}초\n"
        f"\U0001f4b0 비용: ${task.cost_usd:.4f}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
    )

    messages = [header]

    # 결과 본문
    body = task.result_summary or task.result_data or "(결과 없음)"
    body = str(body)
    if body and body != "(결과 없음)":
        for part in _split_message(body):
            messages.append(part)

    return messages


# ─── 기존 포맷 함수 (하위 호환) ───


def format_result(result: TaskResult) -> list[str]:
    """TaskResult를 텔레그램 메시지 리스트로 변환 (자동 분할)."""
    icon = "\u2705" if result.success else "\u274c"
    header = (
        f"{icon} *CORTHEX 보고서*\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
    )

    body = str(result.result_data or result.summary)

    footer = (
        f"\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\u23f1 {result.execution_time_seconds}s"
    )

    full_text = header + body + footer
    return _split_message(full_text)


def format_processing(command: str) -> str:
    """명령 처리 시작 메시지."""
    preview = command[:100] + ("..." if len(command) > 100 else "")
    return f"\u2699\ufe0f *처리 중...*\n\n`{preview}`\n\n25개 에이전트가 작업을 시작합니다."


def format_agent_status(agent_id: str, status: str) -> str:
    """에이전트 상태 한 줄 요약."""
    icons = {"working": "\U0001f7e1", "done": "\U0001f7e2", "error": "\U0001f534", "idle": "\u26aa"}
    icon = icons.get(status, "\u26aa")
    return f"{icon} `{agent_id}` {status}"


def format_agent_list(agents: list[dict]) -> str:
    """에이전트 목록 포맷."""
    lines = ["*CORTHEX HQ \uc5d0\uc774\uc804\ud2b8 \ud604\ud669*\n"]
    by_div: dict[str, list[dict]] = {}
    for a in agents:
        div = a.get("division", "unknown")
        by_div.setdefault(div, []).append(a)

    for div, members in sorted(by_div.items()):
        div_name = _div_display(div)
        lines.append(f"\n\U0001f4c1 *{div_name}*")
        for m in members:
            role_icon = _ROLE_ICONS.get(m.get("role", ""), "\u2022")
            lines.append(f"  {role_icon} {m['name_ko']} (`{m['agent_id']}`)")

    lines.append(f"\n\uc804\uccb4 {len(agents)}\uba85")
    return "\n".join(lines)


def format_cost_summary(cost_data: dict) -> str:
    """비용 요약 포맷."""
    total = cost_data.get("total_cost", 0)
    tokens = cost_data.get("total_tokens", 0)
    calls = cost_data.get("total_calls", 0)
    return (
        f"\U0001f4b0 *\ube44\uc6a9 \ud604\ud669*\n\n"
        f"\u2022 \ucd1d \ube44\uc6a9: ${total:.4f}\n"
        f"\u2022 \ucd1d \ud1a0\ud070: {tokens:,}\n"
        f"\u2022 API \ud638\ucd9c: {calls}\ud68c"
    )


def format_health(health_data: dict) -> str:
    """헬스체크 결과 포맷."""
    overall = health_data.get("overall", "unknown")
    icons = {"healthy": "\U0001f7e2", "degraded": "\U0001f7e1", "error": "\U0001f534"}
    icon = icons.get(overall, "\u2753")
    lines = [f"{icon} *\uc2dc\uc2a4\ud15c \uc0c1\ud0dc: {overall}*\n"]
    for check in health_data.get("checks", []):
        name = check.get("name", "")
        status = check.get("status", "")
        c_icon = icons.get(status, "\u2753")
        lines.append(f"  {c_icon} {name}: {status}")
    return "\n".join(lines)


# ─── 모델 목록 포맷 ───


# CLAUDE.md 기준 실제 존재하는 모델 목록
_AVAILABLE_MODELS = [
    ("claude-sonnet-4-6", "Claude Sonnet 4.6", "기본 (대부분 에이전트)"),
    ("claude-opus-4-6", "Claude Opus 4.6", "최고급 (CLO, CSO)"),
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5", "경량 Anthropic"),
    ("gpt-5.2-pro", "GPT-5.2 Pro", "CIO (투자분석처장)"),
    ("gpt-5.2", "GPT-5.2", "투자 분석가들"),
    ("gpt-5", "GPT-5", "일반 OpenAI"),
    ("gpt-5-mini", "GPT-5 Mini", "경량 OpenAI"),
    ("gemini-3-pro-preview", "Gemini 3.0 Pro", "CMO, 콘텐츠, 설문"),
    ("gemini-2.5-pro", "Gemini 2.5 Pro", "Gemini 고급"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash", "경량 Gemini"),
]


def format_models_list() -> str:
    """사용 가능한 모델 목록을 텔레그램 메시지로 포맷."""
    lines = ["*\U0001f916 사용 가능한 AI 모델*\n"]

    lines.append("*Anthropic*")
    for mid, name, usage in _AVAILABLE_MODELS:
        if mid.startswith("claude"):
            lines.append(f"  \u2022 `{mid}`\n    {name} \u2014 {usage}")

    lines.append("\n*OpenAI*")
    for mid, name, usage in _AVAILABLE_MODELS:
        if mid.startswith("gpt"):
            lines.append(f"  \u2022 `{mid}`\n    {name} \u2014 {usage}")

    lines.append("\n*Google*")
    for mid, name, usage in _AVAILABLE_MODELS:
        if mid.startswith("gemini"):
            lines.append(f"  \u2022 `{mid}`\n    {name} \u2014 {usage}")

    lines.append(f"\n\uc804\uccb4 {len(_AVAILABLE_MODELS)}\uac1c \ubaa8\ub378")
    return "\n".join(lines)


def format_running_tasks(tasks: list) -> str:
    """현재 실행 중인 작업 목록을 텔레그램 메시지로 포맷."""
    if not tasks:
        return "\u2699\ufe0f \ud604\uc7ac \uc2e4\ud589 \uc911\uc778 \uc791\uc5c5\uc774 \uc5c6\uc2b5\ub2c8\ub2e4."

    lines = ["*\u2699\ufe0f \uc2e4\ud589 \uc911\uc778 \uc791\uc5c5*\n"]
    for t in tasks[:10]:
        task_id = t.task_id if hasattr(t, "task_id") else str(t.get("task_id", "?"))
        cmd = t.command if hasattr(t, "command") else str(t.get("command", ""))
        cmd_preview = cmd[:40] + ("..." if len(cmd) > 40 else "")
        lines.append(f"\u2699\ufe0f `{task_id}` {cmd_preview}")

    lines.append(f"\n\U0001f50d \uc0c1\uc138 \ubcf4\uae30: /result [\uc791\uc5c5ID]")
    return "\n".join(lines)


def format_debate_start(topic: str, models: list[str]) -> str:
    """토론 시작 메시지를 포맷."""
    lines = [
        f"\U0001f4ac *AI \ud1a0\ub860 \uc2dc\uc791*",
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
        f"\U0001f4dd \uc8fc\uc81c: {topic}",
        f"\U0001f916 \ucc38\uc5ec AI: {len(models)}\uac1c",
    ]
    for m in models:
        lines.append(f"  \u2022 `{m}`")
    lines.append(f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    lines.append("\u23f3 \uac01 AI\uc758 \uc758\uacac\uc744 \uc218\uc9d1 \uc911...")
    return "\n".join(lines)


def format_debate_result(topic: str, opinions: list[dict]) -> list[str]:
    """토론 결과를 텔레그램 메시지 리스트로 포맷.

    Args:
        topic: 토론 주제
        opinions: [{"model": "...", "opinion": "..."}, ...]
    """
    header = (
        f"\U0001f4ac *AI \ud1a0\ub860 \uacb0\uacfc*\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f4dd \uc8fc\uc81c: {topic}\n"
        f"\U0001f916 \ucc38\uc5ec AI: {len(opinions)}\uac1c\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
    )
    messages = [header]

    for op in opinions:
        model = op.get("model", "?")
        opinion = op.get("opinion", "(응답 없음)")
        # 의견이 너무 길면 자르기
        if len(opinion) > 1500:
            opinion = opinion[:1500] + "\n..."
        msg = f"\U0001f4a1 *{model}*\n{opinion}"
        for part in _split_message(msg):
            messages.append(part)

    return messages


# ─── 유틸리티 ───


def _split_message(text: str) -> list[str]:
    """긴 텍스트를 4096자 단위로 분할. 줄바꿈 기준으로 자른다."""
    if len(text) <= _MAX_LEN:
        return [text]

    parts: list[str] = []
    while text:
        if len(text) <= _MAX_LEN:
            parts.append(text)
            break

        # 줄바꿈 기준으로 최대한 잘라냄
        cut = text.rfind("\n", 0, _MAX_LEN)
        if cut < _MAX_LEN // 2:
            # 줄바꿈이 너무 앞쪽이면 공백 기준
            cut = text.rfind(" ", 0, _MAX_LEN)
        if cut < _MAX_LEN // 2:
            # 그래도 안 되면 하드컷
            cut = _MAX_LEN

        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")

    return parts
