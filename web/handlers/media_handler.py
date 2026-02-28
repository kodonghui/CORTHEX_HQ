"""미디어 서빙/삭제 API — 이미지·영상 파일 관리.

비유: 사진관 — 에이전트가 만든 이미지/영상을 보여주고 정리하는 곳.
"""
import io
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, Response

router = APIRouter(prefix="/api/media", tags=["media"])
logger = logging.getLogger("corthex.media")

# 프로젝트 루트의 output/ 디렉토리 (os.getcwd() 의존 제거 — 서버 cwd와 무관)
_MEDIA_BASE = str(Path(__file__).resolve().parent.parent.parent / "output")
_THUMB_DIR = os.path.join(_MEDIA_BASE, "thumbs")
_THUMB_SIZE = (300, 300)


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


@router.get("/thumbs/{filename}")
async def serve_thumbnail(filename: str):
    """이미지 썸네일 서빙 (300x300, 자동 생성)."""
    safe_name = os.path.basename(filename)
    thumb_path = os.path.join(_THUMB_DIR, safe_name)

    # 캐시된 썸네일 있으면 바로 서빙
    if os.path.isfile(thumb_path):
        return FileResponse(thumb_path, media_type="image/jpeg")

    # 원본에서 썸네일 생성
    original = os.path.join(_MEDIA_BASE, "images", safe_name)
    if not os.path.isfile(original):
        return JSONResponse({"error": "원본 파일 없음"}, status_code=404)

    try:
        from PIL import Image
        os.makedirs(_THUMB_DIR, exist_ok=True)
        img = Image.open(original)
        img.thumbnail(_THUMB_SIZE, Image.LANCZOS)
        # JPEG로 저장 (PNG 대비 ~90% 용량 감소)
        thumb_jpeg = thumb_path.rsplit(".", 1)[0] + ".jpg"
        img = img.convert("RGB")
        img.save(thumb_jpeg, "JPEG", quality=75)
        return FileResponse(thumb_jpeg, media_type="image/jpeg")
    except Exception as e:
        logger.warning("[Media] 썸네일 생성 실패 %s: %s", safe_name, e)
        # 실패 시 원본 서빙
        return FileResponse(original, media_type="image/png")


@router.get("/list")
async def list_media():
    """생성된 미디어 파일 목록 (썸네일 URL 포함)."""
    images_dir = os.path.join(_MEDIA_BASE, "images")
    videos_dir = os.path.join(_MEDIA_BASE, "videos")
    images = sorted(os.listdir(images_dir), reverse=True) if os.path.isdir(images_dir) else []
    videos = sorted(os.listdir(videos_dir), reverse=True) if os.path.isdir(videos_dir) else []
    return {
        "images": [
            {"filename": f, "url": f"/api/media/images/{f}", "thumb": f"/api/media/thumbs/{f}"}
            for f in images if f.endswith(".png")
        ],
        "videos": [
            {"filename": f, "url": f"/api/media/videos/{f}"}
            for f in videos if f.endswith(".mp4")
        ],
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
