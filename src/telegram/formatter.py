"""
텔레그램 메시지 포맷터.

CORTHEX 보고서를 텔레그램 메시지 제한(4096자)에 맞게 변환합니다.
Markdown 깨짐 없이 안전하게 분할합니다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.message import TaskResult

# 텔레그램 메시지 최대 길이 (여유분 확보)
_MAX_LEN = 4000


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
        lines.append(f"\n\U0001f4c1 *{div}*")
        for m in members:
            role_icon = {
                "manager": "\U0001f451",
                "specialist": "\U0001f4bc",
                "worker": "\U0001f528",
            }.get(m.get("role", ""), "\u2022")
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
