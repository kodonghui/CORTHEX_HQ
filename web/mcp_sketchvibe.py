"""
SketchVibe MCP Server — Claude Code가 캔버스/다이어그램에 접근하는 MCP 도구

사용법:
  .mcp.json에 등록 → Claude Code가 자동으로 이 서버를 시작
  수동 테스트: python web/mcp_sketchvibe.py

도구 (읽기):
  - read_canvas: 현재 NEXUS 캔버스 스케치 상태 읽기
  - list_confirmed_diagrams: "맞아"로 확인된 다이어그램 목록
  - get_confirmed_diagram: 특정 다이어그램의 Mermaid 코드 + 해석

도구 (쓰기):
  - update_canvas: Mermaid 코드를 브라우저 캔버스에 실시간 렌더링
  - request_approval: 대표님에게 확인 요청 알림 전송

의존성: pip install fastmcp httpx
"""

import os

import httpx
from fastmcp import FastMCP

mcp = FastMCP(name="sketchvibe")

CORTHEX_URL = os.getenv("CORTHEX_URL", "https://corthex-hq.com")
_TIMEOUT = 30


# ── MCP 도구 ──


@mcp.tool
async def read_canvas() -> str:
    """현재 NEXUS 캔버스의 Mermaid 코드를 읽습니다."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{CORTHEX_URL}/api/sketchvibe/canvas")
        data = resp.json()

    mermaid = data.get("mermaid_code")
    if not mermaid:
        return "캔버스가 비어있거나 저장된 캔버스가 없습니다."

    filename = data.get("filename", "unknown")
    direction = data.get("direction", "LR")
    return f"파일: {filename}\n방향: {direction}\n\n```mermaid\n{mermaid}\n```"


@mcp.tool
async def list_confirmed_diagrams() -> str:
    """대표님이 '맞아'로 확인한 다이어그램 목록을 반환합니다.
    각 다이어그램의 이름, 타입, 해석, 구현 상태가 포함됩니다.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{CORTHEX_URL}/api/sketchvibe/confirmed")
        data = resp.json()

    diagrams = data.get("diagrams", [])
    if not diagrams:
        return "확인된 다이어그램이 없습니다."

    lines = [f"확인된 다이어그램 {len(diagrams)}개:\n"]
    for d in diagrams:
        status = d.get("implementation_status", "pending")
        status_icon = {"pending": "⬜", "in_progress": "🔄", "done": "✅"}.get(status, "⬜")
        lines.append(
            f"  {status_icon} [{d['safe_name']}] {d['name']}\n"
            f"      타입: {d['diagram_type']} | {d['interpretation']}"
        )

    return "\n".join(lines)


@mcp.tool
async def get_confirmed_diagram(name: str) -> str:
    """특정 확인된 다이어그램의 상세 정보를 반환합니다.
    Mermaid 코드, AI 해석, 캔버스 JSON이 포함됩니다.
    구현 착수 시 이 도구로 다이어그램을 읽어서 코드를 생성하세요.

    Args:
        name: 다이어그램 이름 (list_confirmed_diagrams에서 확인)
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{CORTHEX_URL}/api/sketchvibe/confirmed/{name}")
        data = resp.json()

    if data.get("error"):
        return f"오류: {data['error']}"

    lines = [
        f"# {data.get('name', name)}",
        f"타입: {data.get('diagram_type', 'flowchart')}",
        f"해석: {data.get('interpretation', '')}",
        f"구현 상태: {data.get('implementation_status', 'pending')}",
        "",
        "## Mermaid 코드",
        "```mermaid",
        data.get("mermaid", ""),
        "```",
    ]

    canvas = data.get("canvas_json")
    if canvas:
        node_count = len(
            canvas.get("drawflow", {}).get("Home", {}).get("data", {})
        )
        lines.extend(["", f"## 원본 캔버스 (노드 {node_count}개)", "캔버스 JSON 보존됨"])

    return "\n".join(lines)


# ── MCP 쓰기 도구 ──


@mcp.tool
async def update_canvas(mermaid_code: str, description: str = "") -> str:
    """Claude Code가 생성/수정한 Mermaid 코드를 NEXUS 캔버스에 실시간 렌더링합니다.
    브라우저에서 다이어그램이 즉시 표시됩니다.

    Args:
        mermaid_code: 완성된 Mermaid 다이어그램 코드
        description: 수정 내용 설명 (선택)
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{CORTHEX_URL}/api/sketchvibe/push-event",
            json={"mermaid_code": mermaid_code, "description": description},
        )
        data = resp.json()

    if data.get("status") == "pushed":
        clients = data.get("sse_clients", 0)
        if clients > 0:
            return f"캔버스 업데이트 완료 (브라우저 {clients}개 연결됨)\n미리보기: {CORTHEX_URL}/nexus"
        return "캔버스 업데이트 저장됨 (현재 브라우저 연결 없음 — NEXUS 캔버스를 열어주세요)"
    return f"오류: {data}"


@mcp.tool
async def request_approval(message: str = "다이어그램을 확인해주세요") -> str:
    """대표님에게 다이어그램 확인을 요청합니다.
    브라우저 NEXUS 캔버스에 알림이 표시됩니다.

    Args:
        message: 확인 요청 메시지
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{CORTHEX_URL}/api/sketchvibe/request-approval",
            json={"message": message},
        )
        data = resp.json()

    if data.get("status") == "waiting":
        return f"확인 요청 전송 완료: \"{message}\"\n대표님이 NEXUS 캔버스에서 '맞아' 또는 '다시 해줘'를 선택할 때까지 대기합니다."
    return f"오류: {data}"


# ── MCP 리소스 ──


@mcp.resource("sketchvibe://canvas")
async def canvas_resource() -> str:
    """현재 캔버스 상태 (리소스)"""
    return await read_canvas()


@mcp.resource("sketchvibe://confirmed")
async def confirmed_resource() -> str:
    """확인된 다이어그램 목록 (리소스)"""
    return await list_confirmed_diagrams()


if __name__ == "__main__":
    mcp.run()
