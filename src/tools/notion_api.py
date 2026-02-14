"""
노션 연동 Tool.

Notion API를 사용하여 페이지 생성/수정, 데이터베이스 쿼리를 수행합니다.

사용 방법:
  - action="create_page": 노션 페이지 생성
  - action="update_page": 페이지 수정
  - action="query_db": 데이터베이스 쿼리
  - action="list_pages": 페이지 목록 조회

필요 환경변수:
  - NOTION_API_KEY: 노션 인테그레이션 (https://www.notion.so/my-integrations) 무료
  - NOTION_DEFAULT_DB_ID: 기본 데이터베이스 ID (선택)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.notion_api")


def _import_notion():
    """notion-client 라이브러리 임포트."""
    try:
        from notion_client import Client
        return Client
    except ImportError:
        return None


class NotionApiTool(BaseTool):
    """노션 페이지/데이터베이스 관리 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "create_page")

        if action == "create_page":
            return await self._create_page(kwargs)
        elif action == "update_page":
            return await self._update_page(kwargs)
        elif action == "query_db":
            return await self._query_db(kwargs)
        elif action == "list_pages":
            return await self._list_pages(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "create_page, update_page, query_db, list_pages 중 하나를 사용하세요."
            )

    # ── 페이지 생성 ──

    async def _create_page(self, kwargs: dict[str, Any]) -> str:
        client = self._get_client()
        if isinstance(client, str):
            return client

        title = kwargs.get("title", "")
        content = kwargs.get("content", "")
        database_id = kwargs.get("database_id", os.getenv("NOTION_DEFAULT_DB_ID", ""))

        if not title:
            return "제목(title)을 입력해주세요."

        if not database_id:
            return (
                "database_id가 필요합니다.\n"
                "노션 데이터베이스 ID를 직접 지정하거나,\n"
                "NOTION_DEFAULT_DB_ID를 .env에 설정하세요."
            )

        # 마크다운 → 노션 블록 변환
        children = self._markdown_to_blocks(content) if content else []

        properties = {
            "title": {
                "title": [{"text": {"content": title}}]
            }
        }

        # 태그가 있으면 추가
        tags = kwargs.get("tags", "")
        if tags:
            tag_list = [t.strip() for t in tags.split(",")]
            properties["태그"] = {
                "multi_select": [{"name": t} for t in tag_list]
            }

        try:
            page = await asyncio.to_thread(
                client.pages.create,
                parent={"database_id": database_id},
                properties=properties,
                children=children,
            )
            page_url = page.get("url", "URL 없음")
            return f"노션 페이지 생성 완료!\n  제목: {title}\n  URL: {page_url}"
        except Exception as e:
            return f"노션 페이지 생성 실패: {e}"

    # ── 페이지 수정 ──

    async def _update_page(self, kwargs: dict[str, Any]) -> str:
        client = self._get_client()
        if isinstance(client, str):
            return client

        page_id = kwargs.get("page_id", "")
        if not page_id:
            return "page_id를 입력해주세요."

        content = kwargs.get("content", "")
        title = kwargs.get("title", "")

        try:
            if title:
                await asyncio.to_thread(
                    client.pages.update,
                    page_id=page_id,
                    properties={
                        "title": {"title": [{"text": {"content": title}}]}
                    },
                )

            if content:
                children = self._markdown_to_blocks(content)
                # 기존 블록 위에 추가
                await asyncio.to_thread(
                    client.blocks.children.append,
                    block_id=page_id,
                    children=children,
                )

            return f"노션 페이지 수정 완료! (page_id: {page_id})"
        except Exception as e:
            return f"노션 페이지 수정 실패: {e}"

    # ── 데이터베이스 쿼리 ──

    async def _query_db(self, kwargs: dict[str, Any]) -> str:
        client = self._get_client()
        if isinstance(client, str):
            return client

        database_id = kwargs.get("database_id", os.getenv("NOTION_DEFAULT_DB_ID", ""))
        if not database_id:
            return "database_id가 필요합니다."

        page_size = int(kwargs.get("size", 10))

        try:
            results = await asyncio.to_thread(
                client.databases.query,
                database_id=database_id,
                page_size=page_size,
            )
        except Exception as e:
            return f"노션 데이터베이스 쿼리 실패: {e}"

        pages = results.get("results", [])
        if not pages:
            return "데이터베이스에 페이지가 없습니다."

        lines = [f"### 노션 데이터베이스 ({len(pages)}건)"]
        for page in pages:
            props = page.get("properties", {})
            # 제목 추출
            title = "제목 없음"
            for prop_val in props.values():
                if prop_val.get("type") == "title":
                    title_items = prop_val.get("title", [])
                    if title_items:
                        title = title_items[0].get("plain_text", "제목 없음")
                    break

            url = page.get("url", "")
            created = page.get("created_time", "")[:10]
            lines.append(f"  - {title} ({created}) {url}")

        return "\n".join(lines)

    # ── 페이지 목록 (검색) ──

    async def _list_pages(self, kwargs: dict[str, Any]) -> str:
        client = self._get_client()
        if isinstance(client, str):
            return client

        query = kwargs.get("query", "")
        page_size = int(kwargs.get("size", 10))

        try:
            results = await asyncio.to_thread(
                client.search,
                query=query,
                page_size=page_size,
            )
        except Exception as e:
            return f"노션 검색 실패: {e}"

        pages = results.get("results", [])
        if not pages:
            return f"'{query}' 관련 페이지를 찾을 수 없습니다." if query else "페이지가 없습니다."

        lines = [f"### 노션 페이지 목록" + (f" (검색: '{query}')" if query else "")]
        for page in pages:
            obj_type = page.get("object", "")
            if obj_type == "page":
                props = page.get("properties", {})
                title = "제목 없음"
                for prop_val in props.values():
                    if prop_val.get("type") == "title":
                        title_items = prop_val.get("title", [])
                        if title_items:
                            title = title_items[0].get("plain_text", "제목 없음")
                        break
                lines.append(f"  [페이지] {title} — {page.get('url', '')}")
            elif obj_type == "database":
                title_items = page.get("title", [])
                title = title_items[0].get("plain_text", "제목 없음") if title_items else "제목 없음"
                lines.append(f"  [DB] {title} — {page.get('url', '')}")

        return "\n".join(lines)

    # ── 마크다운 → 노션 블록 변환 ──

    @staticmethod
    def _markdown_to_blocks(md_text: str) -> list[dict]:
        """간단한 마크다운을 Notion 블록 리스트로 변환."""
        blocks: list[dict] = []
        lines = md_text.split("\n")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 제목
            if stripped.startswith("### "):
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"text": {"content": stripped[4:]}}]
                    },
                })
            elif stripped.startswith("## "):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": stripped[3:]}}]
                    },
                })
            elif stripped.startswith("# "):
                blocks.append({
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"text": {"content": stripped[2:]}}]
                    },
                })
            # 불릿
            elif stripped.startswith("- ") or stripped.startswith("* "):
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"text": {"content": stripped[2:]}}]
                    },
                })
            # 번호 목록
            elif re.match(r"^\d+\.\s", stripped):
                text = re.sub(r"^\d+\.\s", "", stripped)
                blocks.append({
                    "object": "block",
                    "type": "numbered_list_item",
                    "numbered_list_item": {
                        "rich_text": [{"text": {"content": text}}]
                    },
                })
            # 구분선
            elif stripped in ("---", "***", "___"):
                blocks.append({
                    "object": "block",
                    "type": "divider",
                    "divider": {},
                })
            # 일반 텍스트
            else:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": stripped}}]
                    },
                })

        return blocks

    # ── 유틸 ──

    def _get_client(self) -> Any:
        """Notion 클라이언트 생성. 실패하면 에러 메시지(str) 반환."""
        NotionClient = _import_notion()
        if NotionClient is None:
            return (
                "notion-client 라이브러리가 설치되지 않았습니다.\n"
                "설치: pip install notion-client"
            )

        api_key = os.getenv("NOTION_API_KEY", "")
        if not api_key:
            return (
                "NOTION_API_KEY가 설정되지 않았습니다.\n"
                "노션 인테그레이션(https://www.notion.so/my-integrations)에서 "
                "인테그레이션을 만들고, Internal Integration Token을 .env에 추가하세요.\n"
                "예: NOTION_API_KEY=secret_your-token"
            )

        return NotionClient(auth=api_key)
