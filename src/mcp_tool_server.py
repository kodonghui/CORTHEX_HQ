"""CORTHEX 도구 MCP 프록시 서버.

Claude CLI가 --mcp-config로 이 서버를 시작하면,
에이전트가 CORTHEX의 모든 도구를 사용할 수 있습니다.

도구 실행은 메인 CORTHEX 서버(localhost:8000)에 HTTP로 위임하여
ToolPool 중복 로드 없이 동작합니다.

Usage (claude CLI가 자동 실행):
  claude -p --mcp-config config.json "message"
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
logger = logging.getLogger("corthex.mcp")

# ── 환경 변수 ──
_CALLER_ID = os.getenv("MCP_CALLER_ID", "cli_agent")
_ALLOWED_TOOLS = os.getenv("MCP_ALLOWED_TOOLS", "")
_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000")


def _load_tool_schemas() -> dict[str, dict]:
    """tools.yaml에서 도구 스키마 로드 (경량 — import 없음)."""
    schemas: dict[str, dict] = {}
    config_path = os.path.join(PROJECT_ROOT, "config", "tools.yaml")
    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)
        for tool_def in config.get("tools", []):
            tid = tool_def.get("tool_id", "")
            if tid:
                schemas[tid] = tool_def
    except Exception as e:
        logger.error("tools.yaml 로드 실패: %s", e)
    return schemas


async def main():
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

    tool_schemas = _load_tool_schemas()
    allowed = set(_ALLOWED_TOOLS.split(",")) if _ALLOWED_TOOLS else None

    server = Server("corthex-tools")

    @server.list_tools()
    async def list_tools():
        tools = []
        for tid, schema in tool_schemas.items():
            if allowed and tid not in allowed:
                continue
            input_schema = schema.get("parameters", {"type": "object", "properties": {}})
            if not isinstance(input_schema, dict):
                input_schema = {"type": "object", "properties": {}}
            tools.append(Tool(
                name=tid,
                description=schema.get("description", schema.get("name_ko", tid))[:200],
                inputSchema=input_schema,
            ))
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """CORTHEX 서버에 HTTP로 도구 실행 위임."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(
                    f"{_SERVER_URL}/api/internal/tool-invoke",
                    json={
                        "tool_name": name,
                        "arguments": arguments,
                        "caller_id": _CALLER_ID,
                    },
                )
                data = resp.json()
                result = data.get("result", data.get("error", "알 수 없는 오류"))
                text = json.dumps(result, ensure_ascii=False, default=str) if isinstance(result, (dict, list)) else str(result)
                return [TextContent(type="text", text=text)]
        except httpx.ConnectError:
            return [TextContent(type="text", text=f"CORTHEX 서버 연결 불가 ({_SERVER_URL}). 서버가 실행 중인지 확인하세요.")]
        except Exception as e:
            return [TextContent(type="text", text=f"도구 '{name}' 실행 오류: {e}")]

    logger.warning("CORTHEX MCP 서버 시작 (도구 %d개, caller=%s)", len(tool_schemas), _CALLER_ID)
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
