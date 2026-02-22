"""미디어 서빙/삭제 API — 이미지·영상 파일 관리.

비유: 사진관 — 에이전트가 만든 이미지/영상을 보여주고 정리하는 곳.
"""
import os

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(prefix="/api/media", tags=["media"])

_MEDIA_BASE = os.path.join(os.getcwd(), "output")


@router.get("/images/{filename}")
async def serve_image(filename: str):
    """생성된 이미지 파일 서빙."""
    safe_name = os.path.basename(filename)
    filepath = os.path.join(_MEDIA_BASE, "images", safe_name)
    if not os.path.isfile(filepath):
        return JSONResponse({"error": "파일을 찾을 수 없습니다"}, status_code=404)
    return FileResponse(filepath, media_type="image/png")


@router.get("/videos/{filename}")
async def serve_video(filename: str):
    """생성된 영상 파일 서빙."""
    safe_name = os.path.basename(filename)
    filepath = os.path.join(_MEDIA_BASE, "videos", safe_name)
    if not os.path.isfile(filepath):
        return JSONResponse({"error": "파일을 찾을 수 없습니다"}, status_code=404)
    return FileResponse(filepath, media_type="video/mp4")


@router.get("/list")
async def list_media():
    """생성된 미디어 파일 목록."""
    images_dir = os.path.join(_MEDIA_BASE, "images")
    videos_dir = os.path.join(_MEDIA_BASE, "videos")
    images = sorted(os.listdir(images_dir), reverse=True) if os.path.isdir(images_dir) else []
    videos = sorted(os.listdir(videos_dir), reverse=True) if os.path.isdir(videos_dir) else []
    return {
        "images": [{"filename": f, "url": f"/api/media/images/{f}"} for f in images if f.endswith(".png")],
        "videos": [{"filename": f, "url": f"/api/media/videos/{f}"} for f in videos if f.endswith(".mp4")],
    }


@router.delete("/{media_type}/{filename}")
async def delete_media_file(media_type: str, filename: str):
    """미디어 파일 개별 삭제."""
    if media_type not in ("images", "videos"):
        return JSONResponse({"error": "잘못된 미디어 타입"}, status_code=400)
    safe_name = os.path.basename(filename)
    filepath = os.path.join(_MEDIA_BASE, media_type, safe_name)
    if not os.path.isfile(filepath):
        return JSONResponse({"error": "파일을 찾을 수 없습니다"}, status_code=404)
    os.remove(filepath)
    return {"success": True, "deleted": safe_name}


@router.delete("/{media_type}")
async def delete_all_media(media_type: str):
    """미디어 파일 전체 삭제 (images 또는 videos)."""
    if media_type not in ("images", "videos"):
        return JSONResponse({"error": "잘못된 미디어 타입"}, status_code=400)
    target_dir = os.path.join(_MEDIA_BASE, media_type)
    if not os.path.isdir(target_dir):
        return {"success": True, "deleted": 0}
    ext = ".png" if media_type == "images" else ".mp4"
    count = 0
    for f in os.listdir(target_dir):
        if f.endswith(ext):
            os.remove(os.path.join(target_dir, f))
            count += 1
    return {"success": True, "deleted": count}


@router.post("/delete-batch")
async def delete_media_batch(request: Request):
    """미디어 파일 선택 삭제. body: {"files": [{"type": "images", "filename": "xxx.png"}, ...]}"""
    body = await request.json()
    files = body.get("files", [])
    deleted = 0
    errors = []
    for f in files:
        media_type = f.get("type", "")
        filename = os.path.basename(f.get("filename", ""))
        if media_type not in ("images", "videos") or not filename:
            errors.append(f"잘못된 항목: {f}")
            continue
        filepath = os.path.join(_MEDIA_BASE, media_type, filename)
        if os.path.isfile(filepath):
            os.remove(filepath)
            deleted += 1
        else:
            errors.append(f"파일 없음: {filename}")
    return {"success": True, "deleted": deleted, "errors": errors}
