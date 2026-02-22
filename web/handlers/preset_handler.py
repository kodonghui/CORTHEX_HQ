"""프리셋(Preset) 관리 API — 사용자 설정 프리셋 CRUD.

비유: 옷장 — 자주 쓰는 설정 조합을 이름 붙여 보관하는 곳.
"""
from fastapi import APIRouter, Request

from db import load_setting, save_setting

router = APIRouter(prefix="/api/presets", tags=["presets"])


def _load_data(name: str, default=None):
    """DB에서 설정 데이터 로드."""
    val = load_setting(name)
    if val is not None:
        return val
    return default if default is not None else {}


def _save_data(name: str, data) -> None:
    """DB에 설정 데이터 저장."""
    save_setting(name, data)


@router.get("")
async def get_presets():
    return _load_data("presets", [])


@router.post("")
async def save_preset(request: Request):
    """프리셋 저장."""
    body = await request.json()
    presets = _load_data("presets", [])
    name = body.get("name", "")
    # 같은 이름이 있으면 덮어쓰기
    presets = [p for p in presets if p.get("name") != name]
    presets.append(body)
    _save_data("presets", presets)
    return {"success": True}


@router.delete("/{name}")
async def delete_preset(name: str):
    """프리셋 삭제."""
    presets = _load_data("presets", [])
    presets = [p for p in presets if p.get("name") != name]
    _save_data("presets", presets)
    return {"success": True}
