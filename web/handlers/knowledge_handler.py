"""지식파일(Knowledge) 관리 API — 마크다운 지식 파일 CRUD.

비유: 도서관 — 에이전트가 참고할 지식 문서를 보관하고 열람하는 곳.
"""
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

KST = timezone(timedelta(hours=9))

# knowledge/ 디렉터리: 프로젝트 루트(web 상위) 아래
KNOWLEDGE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent / "knowledge"

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("")
async def get_knowledge():
    entries = []
    if KNOWLEDGE_DIR.exists():
        for folder in sorted(KNOWLEDGE_DIR.iterdir()):
            if folder.is_dir() and not folder.name.startswith("."):
                for f in sorted(folder.iterdir()):
                    if f.is_file() and f.suffix in (".md", ".json"):
                        entries.append({
                            "folder": folder.name,
                            "filename": f.name,
                            "size": f.stat().st_size,
                            "modified": datetime.fromtimestamp(f.stat().st_mtime, KST).isoformat(),
                        })
    return {"entries": entries, "total": len(entries)}


@router.get("/{folder}/{filename}")
async def get_knowledge_file(folder: str, filename: str):
    """지식 파일 내용 읽기."""
    file_path = KNOWLEDGE_DIR / folder / filename
    if file_path.exists() and file_path.is_file():
        content = file_path.read_text(encoding="utf-8")
        return {"folder": folder, "filename": filename, "content": content}
    return {"error": "not found"}


@router.post("")
async def save_knowledge(request: Request):
    """지식 파일 저장/업로드."""
    body = await request.json()
    folder = body.get("folder", "shared")
    filename = body.get("filename", "untitled.md")
    content = body.get("content", "")
    folder_path = KNOWLEDGE_DIR / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    file_path = folder_path / filename
    file_path.write_text(content, encoding="utf-8")
    return {"success": True, "folder": folder, "filename": filename}


@router.delete("/{folder}/{filename}")
async def delete_knowledge(folder: str, filename: str):
    """지식 파일 삭제."""
    file_path = KNOWLEDGE_DIR / folder / filename
    if file_path.exists() and file_path.is_file():
        file_path.unlink()
        return {"success": True}
    return {"success": False, "error": "not found"}
