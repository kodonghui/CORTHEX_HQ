"""노션(Notion) 로그 조회 API — 노션 저장 로그를 확인하는 곳.

비유: 우체국 수발신 기록 — 노션에 보낸 데이터가 잘 전달됐는지 확인하는 창구.
"""
import asyncio
import json
import logging
import os
import urllib.request
import urllib.error

from fastapi import APIRouter, Query

from state import app_state

router = APIRouter(tags=["notion"])
logger = logging.getLogger("corthex.notion")


@router.get("/api/notion-log")
async def get_notion_log():
    """노션 저장 로그 조회 (최근 20건)."""
    _notion_log = app_state.notion_log
    _NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
    _NOTION_DB_SECRETARY = os.getenv("NOTION_DB_SECRETARY", "30a56b49-78dc-8153-bac1-dee5d04d6a74")
    _NOTION_DB_OUTPUT = os.getenv("NOTION_DB_OUTPUT", "30a56b49-78dc-81ce-aaca-ef3fc90a6fba")
    _NOTION_DB_ID = os.getenv("NOTION_DEFAULT_DB_ID", _NOTION_DB_OUTPUT)
    return {
        "logs": _notion_log,
        "total": len(_notion_log),
        "api_key_set": bool(_NOTION_API_KEY),
        "db_secretary": _NOTION_DB_SECRETARY[:8] + "..." if _NOTION_DB_SECRETARY else "(미설정)",
        # _NOTION_DB_ID는 NOTION_DEFAULT_DB_ID 환경변수 → 없으면 NOTION_DB_OUTPUT 폴백
        "db_output_active": _NOTION_DB_ID[:8] + "..." if _NOTION_DB_ID else "(미설정)",
        "db_output_fallback": _NOTION_DB_OUTPUT[:8] + "..." if _NOTION_DB_OUTPUT else "(미설정)",
        "db_id_source": "NOTION_DEFAULT_DB_ID" if os.getenv("NOTION_DEFAULT_DB_ID") else "NOTION_DB_OUTPUT(폴백)",
    }


@router.get("/api/debug/notion-db-schema")
async def get_notion_db_schema(db: str = Query("output", description="secretary 또는 output")):
    """노션 DB의 실제 속성(property) 이름과 타입을 조회합니다.

    비유: 엑셀 시트의 열(컬럼) 이름과 데이터 타입을 확인하는 것.
    """
    api_key = os.getenv("NOTION_API_KEY", "")
    if not api_key:
        return {"error": "NOTION_API_KEY 미설정"}

    db_secretary = os.getenv("NOTION_DB_SECRETARY", "30a56b49-78dc-8153-bac1-dee5d04d6a74")
    db_output = os.getenv("NOTION_DB_OUTPUT", "30a56b49-78dc-81ce-aaca-ef3fc90a6fba")
    db_default = os.getenv("NOTION_DEFAULT_DB_ID", db_output)

    db_id = db_secretary if db == "secretary" else db_default
    db_name = "비서실" if db == "secretary" else "산출물"

    def _fetch_schema():
        url = f"https://api.notion.com/v1/databases/{db_id}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
        }
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            return {"_error": f"HTTP {e.code}: {err_body}"}
        except Exception as e:
            return {"_error": str(e)}

    result = await asyncio.to_thread(_fetch_schema)

    if "_error" in result:
        return {"error": result["_error"], "db": db_name, "db_id": db_id[:8] + "..."}

    # 속성 목록 추출
    properties = result.get("properties", {})
    schema = {}
    for prop_name, prop_val in properties.items():
        prop_type = prop_val.get("type", "unknown")
        info = {"type": prop_type}
        # select/multi_select 옵션 목록도 포함
        if prop_type == "select":
            options = prop_val.get("select", {}).get("options", [])
            info["options"] = [o.get("name") for o in options]
        elif prop_type == "multi_select":
            options = prop_val.get("multi_select", {}).get("options", [])
            info["options"] = [o.get("name") for o in options]
        schema[prop_name] = info

    title_items = result.get("title", [])
    db_title = title_items[0].get("plain_text", "") if title_items else "(제목 없음)"

    return {
        "db": db_name,
        "db_id": db_id[:8] + "...",
        "db_title": db_title,
        "properties": schema,
    }


@router.post("/api/debug/notion-archive-migrate")
async def run_archive_migration():
    """비서실 + 에이전트 산출물 DB의 모든 페이지를 아카이브 DB로 이전.
    1회성 관리자 작업용 엔드포인트.
    """
    api_key = os.getenv("NOTION_API_KEY", "")
    if not api_key:
        return {"error": "NOTION_API_KEY 미설정"}

    db_secretary = os.getenv("NOTION_DB_SECRETARY", "30a56b49-78dc-8153-bac1-dee5d04d6a74")
    db_output    = os.getenv("NOTION_DB_OUTPUT",    "30a56b49-78dc-81ce-aaca-ef3fc90a6fba")
    db_archive   = os.getenv("NOTION_DB_ARCHIVE",   "31256b49-78dc-81c9-9ad2-e31a076d0d97")
    headers = {"Authorization": f"Bearer {api_key}", "Notion-Version": "2022-06-28",
               "Content-Type": "application/json"}

    def _req(method, url, data=None):
        body = json.dumps(data).encode() if data else None
        r = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(r, timeout=20) as resp:
                return json.loads(resp.read())
        except Exception as e:
            return {"_error": str(e)}

    def _query_all(db_id):
        pages, cursor = [], None
        for _ in range(20):  # 최대 2000개
            body = {"page_size": 100}
            if cursor: body["start_cursor"] = cursor
            d = _req("POST", f"https://api.notion.com/v1/databases/{db_id}/query", body)
            if "_error" in d or "results" not in d: break
            pages.extend(d["results"])
            if not d.get("has_more"): break
            cursor = d.get("next_cursor")
        return pages

    def _extract(page, title_key="Name"):
        props = page.get("properties", {})
        t = props.get(title_key, {}).get("title", [])
        title = t[0]["plain_text"] if t else "(no title)"
        rt = props.get("내용", {}).get("rich_text", [])
        content = rt[0]["plain_text"] if rt else ""
        sel_date = props.get("날짜", {}).get("date")
        date = sel_date["start"] if sel_date else ""
        author = ""
        for k in ("담당자", "에이전트"):
            s = props.get(k, {}).get("select")
            if s: author = s["name"]; break
        return title, content, date, author

    def _archive(title, content, date, author, source_label):
        p = {"제목": {"title": [{"text": {"content": title[:100]}}]},
             "카테고리": {"select": {"name": source_label}}}
        if date: p["날짜"] = {"date": {"start": date}}
        if content: p["내용"] = {"rich_text": [{"text": {"content": content[:1900]}}]}
        if author: p["작성자"] = {"select": {"name": author[:100]}}
        r = _req("POST", "https://api.notion.com/v1/pages",
                 {"parent": {"database_id": db_archive}, "properties": p})
        return "_error" not in r

    def _trash(pid):
        _req("PATCH", f"https://api.notion.com/v1/pages/{pid}", {"archived": True})

    results = {}
    for db_id, label in [(db_secretary, "비서실"), (db_output, "에이전트산출물")]:
        pages = await asyncio.to_thread(_query_all, db_id)
        ok = fail = 0
        for pg in pages:
            title, content, date, author = await asyncio.to_thread(_extract, pg)
            moved = await asyncio.to_thread(_archive, title, content, date, author, label)
            if moved:
                await asyncio.to_thread(_trash, pg["id"])
                ok += 1
            else:
                fail += 1
        results[label] = {"total": len(pages), "ok": ok, "fail": fail}
        logger.info(f"[아카이브 이전] {label}: {ok}/{len(pages)}")

    return {"status": "완료", "results": results}
