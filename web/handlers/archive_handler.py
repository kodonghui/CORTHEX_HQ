"""기밀문서(Archive) API — 에이전트 산출물 보관·조회·삭제·내보내기.

비유: 기밀문서실 — 에이전트가 작성한 보고서를 보관하고 관리하는 곳.
"""
import io
import json as _json
import logging
import re
import zipfile
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from db import (
    save_archive,
    list_archives,
    get_archive as db_get_archive,
    delete_archive as db_delete_archive,
    delete_all_archives,
    save_activity_log,
)

logger = logging.getLogger("corthex")

KST = timezone(timedelta(hours=9))

router = APIRouter(prefix="/api/archive", tags=["archive"])


# ── 헬퍼 함수 ──

def _parse_archive_frontmatter(content: str) -> dict:
    """아카이브 content의 YAML 프론트매터에서 importance/tags를 추출합니다.

    프론트매터 형식:
    ---
    importance: 중요
    tags: ["태그1", "태그2"]
    ---
    (본문)
    """
    meta = {"importance": "일반", "tags": []}
    if not content or not content.startswith("---"):
        return meta
    try:
        end = content.find("\n---", 3)
        if end == -1:
            return meta
        front = content[3:end].strip()
        for line in front.splitlines():
            if line.startswith("importance:"):
                meta["importance"] = line.split(":", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("tags:"):
                raw = line.split(":", 1)[1].strip()
                if raw.startswith("["):
                    try:
                        meta["tags"] = _json.loads(raw)
                    except Exception:
                        meta["tags"] = []
                elif raw:
                    meta["tags"] = [t.strip() for t in raw.split(",") if t.strip()]
    except Exception as e:
        logger.debug("아카이브 메타데이터 파싱 실패: %s", e)
    return meta


def _build_archive_frontmatter(importance: str = "일반", tags: list = None) -> str:
    """importance/tags를 YAML 프론트매터 문자열로 변환합니다."""
    tags = tags or []
    return f"---\nimportance: {importance}\ntags: {_json.dumps(tags, ensure_ascii=False)}\n---\n"


# ── 엔드포인트 ──

@router.delete("/all")
async def delete_all_archives_api():
    """모든 기밀문서를 삭제합니다."""
    try:
        count = delete_all_archives()
        save_activity_log("system", f"\U0001f5d1\ufe0f 기밀문서 전체 삭제: {count}건", "warning")
        return {"success": True, "deleted": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("")
async def get_archive_list(division: str = None, limit: int = 100, org: str = ""):
    docs = list_archives(division=division, limit=limit)
    # v5: org 스코프 필터 (ADR-7 — 탭 숨김 아닌 데이터 스코프)
    if org:
        docs = [d for d in docs if d.get("division", "").startswith(org)]
    for doc in docs:
        doc.setdefault("importance", "일반")
        doc.setdefault("tags", [])
    return docs


@router.post("")
async def create_archive_api(request: Request):
    """기밀문서를 직접 저장합니다. importance/tags 필드를 지원합니다."""
    try:
        body = await request.json()
        division = body.get("division", "general")
        filename = body.get("filename", "")
        content = body.get("content", "")
        agent_id = body.get("agent_id", "")
        importance = body.get("importance", "일반")
        tags = body.get("tags", [])
        if not filename or not content:
            return {"success": False, "error": "filename과 content는 필수입니다"}
        # importance/tags를 YAML 프론트매터로 content 앞에 삽입
        front = _build_archive_frontmatter(importance=importance, tags=tags)
        full_content = front + content
        row_id = save_archive(
            division=division,
            filename=filename,
            content=full_content,
            agent_id=agent_id or None,
        )
        save_activity_log("system", f"\U0001f4c1 기밀문서 저장: {division}/{filename} [중요도: {importance}]", "info")
        return {"success": True, "id": row_id, "importance": importance, "tags": tags}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/export-zip")
async def export_archive_zip(division: str = None, tier: str = None, limit: int = 500, files: str = None):
    """현재 필터 조건에 맞는 기밀문서를 ZIP으로 다운로드합니다."""
    # files 파라미터가 있으면 선택된 파일만 개별 조회
    if files:
        file_list = files.split(",")
        docs = []
        for fp in file_list:
            parts = fp.strip().split("/", 1)
            if len(parts) == 2:
                doc = db_get_archive(parts[0], parts[1])
                if doc:
                    docs.append(doc)
    else:
        docs = list_archives(division=division, limit=limit)

    # tier 필터 (executive/specialist/staff)
    def _get_tier(agent_id: str) -> str:
        if not agent_id:
            return "staff"
        aid = agent_id.lower()
        if any(x in aid for x in ["cto", "cfo", "cmo", "clo", "coo", "ceo", "chief"]):
            return "executive"
        if any(x in aid for x in ["manager", "lead", "head"]):
            return "specialist"
        return "staff"

    if tier and tier != "all":
        docs = [d for d in docs if _get_tier(d.get("agent_id", "")) == tier]

    if not docs:
        return JSONResponse({"error": "내보낼 문서가 없습니다"}, status_code=404)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc in docs:
            raw_div = doc.get("division", "unknown")
            safe_div = re.sub(r"[^\w\-]", "_", raw_div)
            safe_fn = re.sub(r"[^\w\-\.]", "_", doc.get("filename", "report.md"))
            # content가 없으면 개별 조회
            content = doc.get("content") or ""
            if not content:
                full_doc = db_get_archive(doc.get("division", ""), doc.get("filename", ""))
                content = full_doc.get("content", "") if full_doc else ""
            zf.writestr(f"{safe_div}/{safe_fn}", content)

    buf.seek(0)
    date_str = datetime.now(KST).strftime("%Y%m%d")
    zip_name = f"corthex-archive-{date_str}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@router.get("/{division}/{filename}")
async def get_archive_file(division: str, filename: str):
    doc = db_get_archive(division, filename)
    if not doc:
        return {"error": "not found"}
    # content에서 importance/tags 파싱
    meta = _parse_archive_frontmatter(doc.get("content", ""))
    doc["importance"] = meta.get("importance", "일반")
    doc["tags"] = meta.get("tags", [])
    return doc


@router.delete("/{division}/{filename}")
async def delete_archive_api(division: str, filename: str):
    """기밀문서 보고서를 삭제합니다."""
    ok = db_delete_archive(division, filename)
    if not ok:
        return {"success": False, "error": "보고서를 찾을 수 없습니다"}
    save_activity_log("system", f"\U0001f5d1 기밀문서 삭제: {division}/{filename}", "info")
    return {"success": True}
