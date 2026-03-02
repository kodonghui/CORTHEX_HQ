"""
SketchVibe — 캔버스 ↔ Claude Code 양방향 MCP 구조 (Phase 3)

서버는 데이터 저장/전달만 담당. 변환은 Claude Code가 직접 수행.
MCP → REST API → SSE → 브라우저 실시간 렌더링.
"""
import asyncio
import json
import logging
import os
import time
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("corthex.sketchvibe")

router = APIRouter(prefix="/api/sketchvibe", tags=["sketchvibe"])

# ── SSE 이벤트 큐 (MCP → 브라우저 브릿지) ──

_sse_clients: list[asyncio.Queue] = []

# ── 요청 모델 ──

class SaveCanvasRequest(BaseModel):
    mermaid_code: str = ""
    direction: str = "LR"
    filename: str = ""


class SaveDiagramRequest(BaseModel):
    mermaid: str
    name: str = "untitled"
    interpretation: str = ""
    canvas_json: Optional[dict] = None
    diagram_type: str = "flowchart"


class UpdateCanvasRequest(BaseModel):
    mermaid_code: str
    description: str = ""


class ApprovalRequest(BaseModel):
    message: str = "다이어그램을 확인해주세요"


# (Drawflow 파싱 코드 제거됨 — 2026-03-02 Mermaid 네이티브 전환)


# ── SSE 브로드캐스트 헬퍼 ──

async def _broadcast_sse(event_data: dict) -> int:
    """모든 SSE 클라이언트에 이벤트 전송. 전송 수 반환."""
    sent = 0
    for q in _sse_clients[:]:
        try:
            await q.put(event_data)
            sent += 1
        except Exception:
            pass
    return sent


# ── API 엔드포인트 ──


@router.post("/save-canvas")
async def save_canvas(req: SaveCanvasRequest):
    """Mermaid 코드를 SQLite에 저장. Claude Code에서 read_canvas로 읽기."""
    try:
        from db import save_setting
        save_setting("sketchvibe:current_canvas", {
            "mermaid_code": req.mermaid_code,
            "direction": req.direction,
            "filename": req.filename,
            "saved_at": time.time(),
        })
        return {"status": "saved"}
    except Exception as e:
        logger.error("캔버스 저장 실패: %s", e)
        return {"error": str(e)}


@router.post("/push-event")
async def push_event(req: UpdateCanvasRequest):
    """MCP 서버가 호출 — Mermaid 코드를 SSE로 브라우저에 전송."""
    event = {
        "type": "canvas_update",
        "mermaid": req.mermaid_code,
        "description": req.description,
        "timestamp": time.time(),
    }
    # DB에도 최근 Mermaid 저장 (새로고침 시 복원용)
    try:
        from db import save_setting
        save_setting("sketchvibe:latest_mermaid", event)
    except Exception:
        pass

    sent = await _broadcast_sse(event)
    return {"status": "pushed", "sse_clients": sent}


@router.post("/request-approval")
async def request_approval(req: ApprovalRequest):
    """MCP 서버가 호출 — 대표님에게 확인 요청 알림 전송."""
    event = {
        "type": "approval_request",
        "message": req.message,
        "timestamp": time.time(),
    }
    sent = await _broadcast_sse(event)
    return {"status": "waiting", "message": req.message, "sse_clients": sent}


@router.post("/approve")
async def approve_diagram():
    """브라우저에서 '맞아' 클릭 시 호출 — 승인 이벤트 발행."""
    event = {
        "type": "approved",
        "timestamp": time.time(),
    }
    await _broadcast_sse(event)
    return {"status": "approved"}


@router.get("/stream")
async def sse_stream():
    """SSE 엔드포인트 — 브라우저가 구독하여 실시간 업데이트 수신."""
    queue: asyncio.Queue = asyncio.Queue()
    _sse_clients.append(queue)

    async def event_generator():
        try:
            yield f"event: connected\ndata: {json.dumps({'status': 'ok'})}\n\n"
            # 2분 이내에 그린 것만 복원 (새로고침 직후 복원용, 오래된 건 자동표시 안 함)
            try:
                from db import load_setting
                latest = load_setting("sketchvibe:latest_mermaid", None)
                if latest and latest.get("mermaid") and (time.time() - latest.get("timestamp", 0) < 120):
                    yield f"event: sketchvibe\ndata: {json.dumps(latest, ensure_ascii=False)}\n\n"
            except Exception:
                pass
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: sketchvibe\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in _sse_clients:
                _sse_clients.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/canvas")
async def get_canvas_state():
    """MCP용 — Mermaid 코드 직접 반환 (SQLite 우선, 파일 폴백)"""
    # 1) SQLite에서 조회
    try:
        from db import load_setting
        saved = load_setting("sketchvibe:current_canvas", None)
        if saved and saved.get("mermaid_code"):
            return {
                "mermaid_code": saved["mermaid_code"],
                "direction": saved.get("direction", "LR"),
                "filename": saved.get("filename", ""),
            }
    except Exception:
        pass

    # 2) 파일 폴백 (knowledge/flowcharts에서 최신 파일)
    knowledge_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "knowledge", "flowcharts",
    )
    if not os.path.isdir(knowledge_dir):
        return {"mermaid_code": None, "message": "저장된 캔버스 없음"}

    files = sorted(
        [f for f in os.listdir(knowledge_dir) if f.endswith(".json")],
        key=lambda f: os.path.getmtime(os.path.join(knowledge_dir, f)),
        reverse=True,
    )
    if not files:
        return {"mermaid_code": None, "message": "저장된 캔버스 없음"}

    with open(os.path.join(knowledge_dir, files[0]), "r", encoding="utf-8") as f:
        data = json.load(f)

    # 신규 포맷 (Mermaid)
    if data.get("mermaid"):
        return {
            "mermaid_code": data["mermaid"],
            "direction": data.get("direction", "LR"),
            "filename": files[0],
        }

    # 레거시 Drawflow JSON은 더 이상 파싱하지 않음
    return {"mermaid_code": None, "message": "레거시 Drawflow 파일 (Mermaid 변환 필요)"}


@router.post("/save-diagram")
async def save_diagram(req: SaveDiagramRequest):
    """확인된 다이어그램을 .md + .html 뷰어로 저장 + DB에 confirmed 등록"""
    if not req.mermaid:
        return {"error": "Mermaid 코드가 없습니다"}

    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "knowledge", "sketchvibe",
    )
    os.makedirs(base, exist_ok=True)

    safe_name = re.sub(r"[^\w가-힣\-]", "_", req.name)

    # .md 저장
    md = f"# {req.name}\n\n> {req.interpretation}\n\n```mermaid\n{req.mermaid}\n```\n"
    with open(os.path.join(base, f"{safe_name}.md"), "w", encoding="utf-8") as f:
        f.write(md)

    # .html 뷰어 저장
    html = _gen_html_viewer(req.name, req.mermaid, req.interpretation)
    with open(os.path.join(base, f"{safe_name}.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # DB에 confirmed 다이어그램으로 등록 (MCP 서버에서 조회용)
    try:
        from db import save_setting, load_setting
        confirmed_list = load_setting("sketchvibe:confirmed_list", {})
        confirmed_list[safe_name] = {
            "name": req.name,
            "safe_name": safe_name,
            "mermaid": req.mermaid,
            "interpretation": req.interpretation,
            "diagram_type": req.diagram_type,
            "canvas_json": req.canvas_json,
            "confirmed_at": time.time(),
            "implementation_status": "pending",
        }
        save_setting("sketchvibe:confirmed_list", confirmed_list)
    except Exception as e:
        logger.warning("SketchVibe confirmed DB 저장 실패 (파일 저장은 성공): %s", e)

    return {
        "saved": True,
        "confirmed": True,
        "md_path": f"knowledge/sketchvibe/{safe_name}.md",
        "html_path": f"api/sketchvibe/viewer/{safe_name}",
    }


@router.get("/viewer/{name}")
async def viewer(name: str):
    """확인된 다이어그램의 HTML 뷰어 반환 (브라우저에서 직접 열기)"""
    from fastapi.responses import HTMLResponse
    safe_name = re.sub(r"[^\w가-힣\-]", "_", name)
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "knowledge", "sketchvibe",
    )
    html_file = os.path.join(base, f"{safe_name}.html")
    if not os.path.isfile(html_file):
        return HTMLResponse("<h1>다이어그램을 찾을 수 없습니다</h1>", status_code=404)
    with open(html_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.get("/confirmed")
async def list_confirmed_diagrams():
    """확인된 다이어그램 목록 반환 (MCP 서버용)"""
    try:
        from db import load_setting
        confirmed = load_setting("sketchvibe:confirmed_list", {})
        items = []
        for key, val in confirmed.items():
            items.append({
                "name": val.get("name", key),
                "safe_name": key,
                "diagram_type": val.get("diagram_type", "flowchart"),
                "interpretation": val.get("interpretation", ""),
                "confirmed_at": val.get("confirmed_at", 0),
                "implementation_status": val.get("implementation_status", "pending"),
            })
        items.sort(key=lambda x: x["confirmed_at"], reverse=True)
        return {"diagrams": items, "count": len(items)}
    except Exception as e:
        logger.error("confirmed 목록 조회 실패: %s", e)
        return {"diagrams": [], "count": 0}


@router.get("/confirmed/{name}")
async def get_confirmed_diagram(name: str):
    """특정 확인된 다이어그램 상세 반환 (MCP 서버용)"""
    try:
        from db import load_setting
        confirmed = load_setting("sketchvibe:confirmed_list", {})
        safe_name = re.sub(r"[^\w가-힣\-]", "_", name)
        diagram = confirmed.get(safe_name) or confirmed.get(name)
        if not diagram:
            return {"error": f"'{name}' 다이어그램을 찾을 수 없습니다"}
        return {
            "name": diagram.get("name", name),
            "mermaid": diagram.get("mermaid", ""),
            "interpretation": diagram.get("interpretation", ""),
            "diagram_type": diagram.get("diagram_type", "flowchart"),
            "canvas_json": diagram.get("canvas_json"),
            "confirmed_at": diagram.get("confirmed_at", 0),
            "implementation_status": diagram.get("implementation_status", "pending"),
        }
    except Exception as e:
        logger.error("confirmed 다이어그램 조회 실패: %s", e)
        return {"error": str(e)}


@router.delete("/confirmed/{name}")
async def delete_confirmed_diagram(name: str):
    """확인된 다이어그램 삭제 (DB + 파일)"""
    try:
        from db import load_setting, save_setting
        safe_name = re.sub(r"[^\w가-힣\-]", "_", name)
        confirmed_list = load_setting("sketchvibe:confirmed_list", {})
        if safe_name not in confirmed_list:
            return {"error": "다이어그램을 찾을 수 없습니다"}
        del confirmed_list[safe_name]
        save_setting("sketchvibe:confirmed_list", confirmed_list)
        # 파일도 삭제
        base = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "knowledge", "sketchvibe",
        )
        for ext in [".md", ".html"]:
            f = os.path.join(base, f"{safe_name}{ext}")
            if os.path.isfile(f):
                os.remove(f)
        return {"deleted": True, "name": safe_name}
    except Exception as e:
        logger.error("confirmed 다이어그램 삭제 실패: %s", e)
        return {"error": str(e)}


def _gen_html_viewer(title: str, mermaid_code: str, interpretation: str) -> str:
    """mermaid.js CDN + dark 테마 + useMaxWidth: false HTML 뷰어 생성"""
    mermaid_json = json.dumps(mermaid_code)
    title_safe = title.replace("<", "&lt;").replace(">", "&gt;")
    interp_safe = interpretation.replace("<", "&lt;").replace(">", "&gt;")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SketchVibe — {title_safe}</title>
<style>
body {{ margin:0; background:#060a14; color:#e2e8f0; font-family:Pretendard,system-ui,sans-serif; }}
.container {{ max-width:1200px; margin:0 auto; padding:2rem; }}
.card {{ background:#0a0f1a; border:1px solid rgba(255,255,255,0.1); border-radius:12px; padding:1.5rem; margin-bottom:1.5rem; }}
.title {{ font-size:1.5rem; font-weight:700; color:#34d399; margin-bottom:0.5rem; }}
.subtitle {{ font-size:0.875rem; color:rgba(255,255,255,0.5); }}
.diagram {{ background:#0c1220; border:1px solid rgba(255,255,255,0.1); border-radius:8px; padding:1.5rem; overflow:auto; }}
.diagram svg {{ max-width:none !important; }}
.tip {{ font-size:0.75rem; color:rgba(255,255,255,0.3); margin-top:1rem; text-align:center; }}
.badge {{ display:inline-block; background:rgba(52,211,153,0.15); color:#34d399; padding:0.15rem 0.5rem; border-radius:4px; font-size:0.75rem; font-weight:600; margin-left:0.5rem; }}
</style>
</head>
<body>
<div class="container">
  <div class="card">
    <div class="title">{title_safe}<span class="badge">SketchVibe</span></div>
    <div class="subtitle">{interp_safe}</div>
  </div>
  <div class="card diagram">
    <div id="diagram"></div>
  </div>
  <div class="tip">Ctrl + 스크롤로 확대/축소</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
mermaid.initialize({{
  startOnLoad: false,
  theme: 'dark',
  flowchart: {{ useMaxWidth: false, htmlLabels: true }},
  themeVariables: {{
    primaryColor: '#1e1b4b', primaryTextColor: '#e2e8f0',
    primaryBorderColor: '#6366f1', lineColor: '#6366f1',
    fontFamily: 'Pretendard, system-ui, sans-serif'
  }}
}});
const code = {mermaid_json};
mermaid.render('sv-svg', code).then(({{ svg }}) => {{
  document.getElementById('diagram').innerHTML = svg;
}}).catch(e => {{
  document.getElementById('diagram').innerHTML =
    '<pre style="color:#ef4444;font-size:0.75rem">렌더링 실패: ' + e.message + '</pre>';
}});
</script>
</body>
</html>"""
