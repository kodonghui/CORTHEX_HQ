"""
SketchVibe — 스케치 + 자연어 → Mermaid 다이어그램 변환 (Phase 2)

캔버스(Drawflow JSON) + 자연어 설명 → Claude → Mermaid 코드
Phase 2: 정확도 향상 + MCP 서버 + 구현 브리지
"""
import json
import logging
import math
import os
import re
import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("corthex.sketchvibe")

router = APIRouter(prefix="/api/sketchvibe", tags=["sketchvibe"])

# ── 노드 타입 → Mermaid 형태 매핑 ──

_MERMAID_SHAPES = {
    "start": ("([{label}])", "stadium — 시작점"),
    "end": ("(({label}))", "circle — 종료점"),
    "decide": ("{{{label}}}", "diamond — 결정/분기"),
    "agent": ("[{label}]", "rectangle — 에이전트/액터"),
    "system": ("[[{label}]]", "subroutine — 시스템/서비스"),
    "api": ("[/{label}\\\\]", "parallelogram — 외부 API"),
    "note": (">{label}]", "asymmetric — 메모/주석"),
}


# ── 요청 모델 ──

class ConvertRequest(BaseModel):
    canvas_json: dict
    description: str = ""


class SaveDiagramRequest(BaseModel):
    mermaid: str
    name: str = "untitled"
    interpretation: str = ""
    canvas_json: Optional[dict] = None
    diagram_type: str = "flowchart"


# ── Drawflow JSON 파싱 (Phase 2 강화) ──

def _extract_label(html: str) -> str:
    """nexus-node div에서 사용자 편집 텍스트 추출"""
    m = re.search(r">([^<]+)<", html or "")
    return m.group(1).strip() if m else ""


def _detect_layout(nodes: dict) -> str:
    """노드 위치 분석 → LR 또는 TD 레이아웃 판단"""
    if len(nodes) < 2:
        return "TD"
    positions = [(n["pos_x"], n["pos_y"]) for n in nodes.values()]
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    x_spread = max(xs) - min(xs)
    y_spread = max(ys) - min(ys)
    return "LR" if x_spread > y_spread * 1.3 else "TD"


def _detect_groups(nodes: dict, threshold: float = 300) -> list[list[str]]:
    """공간적 근접 노드 클러스터링 → subgraph 힌트"""
    if len(nodes) < 3:
        return []

    nids = list(nodes.keys())
    visited = set()
    groups = []

    for i, nid in enumerate(nids):
        if nid in visited:
            continue
        cluster = [nid]
        visited.add(nid)
        for j in range(i + 1, len(nids)):
            other = nids[j]
            if other in visited:
                continue
            dx = nodes[nid]["pos_x"] - nodes[other]["pos_x"]
            dy = nodes[nid]["pos_y"] - nodes[other]["pos_y"]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < threshold:
                cluster.append(other)
                visited.add(other)
        if len(cluster) >= 2:
            groups.append(cluster)

    return groups


def _parse_drawflow(canvas: dict) -> str:
    """Drawflow export JSON → AI가 이해할 수 있는 구조화된 텍스트 (Phase 2 강화)"""
    data = canvas.get("drawflow", {}).get("Home", {}).get("data", {})
    if not data:
        return "빈 캔버스 (노드 없음)"

    nodes = {}
    for nid, node in data.items():
        label = _extract_label(node.get("html", ""))
        if not label:
            label = node.get("data", {}).get("label", node.get("name", f"노드{nid}"))
        node_type = node.get("name", "unknown")
        shape_info = _MERMAID_SHAPES.get(node_type, ("[{label}]", "rectangle"))
        nodes[str(nid)] = {
            "id": str(nid),
            "label": label,
            "type": node_type,
            "mermaid_shape": shape_info[0].format(label=label),
            "shape_desc": shape_info[1],
            "pos_x": node.get("pos_x", 0),
            "pos_y": node.get("pos_y", 0),
            "input_count": len(node.get("inputs", {})),
            "output_count": len(node.get("outputs", {})),
        }

    connections = []
    for nid, node in data.items():
        for port_key, port in node.get("outputs", {}).items():
            for conn in port.get("connections", []):
                target = str(conn.get("node", "?"))
                connections.append({
                    "from": str(nid),
                    "to": target,
                    "from_port": port_key,
                })

    # 레이아웃 판단
    layout = _detect_layout(nodes)

    # 그룹 감지
    groups = _detect_groups(nodes)

    # 구조화된 텍스트 생성
    lines = [f"노드 {len(nodes)}개 (레이아웃: {layout}):"]
    for n in nodes.values():
        lines.append(
            f'  [{n["id"]}] "{n["label"]}" '
            f'(타입: {n["type"]}, Mermaid: {n["mermaid_shape"]}, '
            f'입력포트: {n["input_count"]}, 출력포트: {n["output_count"]})'
        )

    if connections:
        lines.append(f"\n연결 {len(connections)}개:")
        for c in connections:
            src_l = nodes.get(c["from"], {}).get("label", c["from"])
            tgt_l = nodes.get(c["to"], {}).get("label", c["to"])
            src_type = nodes.get(c["from"], {}).get("type", "")
            port_info = ""
            if src_type == "decide" and c["from_port"]:
                port_num = c["from_port"].replace("output_", "")
                port_info = f" [분기 {port_num}]"
            lines.append(f'  "{src_l}" → "{tgt_l}"{port_info}')
    else:
        lines.append("\n연결: 없음")

    if groups:
        lines.append(f"\n공간 그룹 {len(groups)}개 (subgraph 힌트):")
        for i, g in enumerate(groups):
            labels = [nodes[nid]["label"] for nid in g if nid in nodes]
            lines.append(f'  그룹 {i + 1}: [{", ".join(labels)}]')

    return "\n".join(lines)


# ── Claude 시스템 프롬프트 ──

_SYSTEM_PROMPT = """당신은 SketchVibe 변환 엔진입니다.

## 역할
사용자가 캔버스에 그린 스케치(Drawflow JSON 구조)와 자연어 설명을 동시에 받아서,
정확한 Mermaid 다이어그램 코드로 변환합니다.

## 출력 규칙
반드시 아래 JSON 형식으로만 응답하세요. JSON 외 텍스트를 포함하지 마세요.

```json
{
  "diagram_type": "flowchart | sequenceDiagram | stateDiagram | classDiagram",
  "mermaid": "Mermaid 코드 (줄바꿈은 실제 줄바꿈으로)",
  "interpretation": "한국어 1~2문장 요약"
}
```

## 다이어그램 타입 자동 판단
- **flowchart**: 순서/흐름/프로세스가 있는 것 → `flowchart TD` 또는 `flowchart LR`
- **sequenceDiagram**: 시간 순서대로 메시지가 오가는 것 → `sequenceDiagram`
- **stateDiagram**: 상태 전이가 있는 것 → `stateDiagram-v2`
- **classDiagram**: 클래스/객체 관계가 있는 것 → `classDiagram`
사용자가 타입을 몰라도 됩니다. 스케치 구조 + 설명에서 자동 판단하세요.

## 노드 타입 → Mermaid 형태 매핑
입력에 노드 타입과 Mermaid 형태가 표시됩니다. 이를 참고하세요:
| 노드 타입 | Mermaid 형태 | 의미 |
|-----------|-------------|------|
| start | ([시작]) | 프로세스 시작점 |
| end | ((종료)) | 프로세스 종료점 |
| decide | {결정} | 조건 분기 (다이아몬드) |
| agent | [에이전트] | 액터/처리자 |
| system | [[시스템]] | 내부 서비스/모듈 |
| api | [/외부 API\\] | 외부 연동 |
| note | >메모] | 주석/설명 |

## 레이아웃 힌트
입력에 `레이아웃: LR` 또는 `레이아웃: TD`가 표시됩니다.
- LR → `flowchart LR` (왼→오른)
- TD → `flowchart TD` (위→아래)

## 분기 처리
decide 타입 노드에서 나가는 연결에 `[분기 1]`, `[분기 2]`가 표시되면:
- 분기 1 → `-->|Yes|` 또는 `-->|조건A|`
- 분기 2 → `-->|No|` 또는 `-->|조건B|`
자연어 설명에서 분기 조건을 추론하세요.

## 공간 그룹 → subgraph
입력에 `공간 그룹`이 표시되면 Mermaid `subgraph`로 감싸세요.

## Mermaid 코드 규칙
- 노드 이름은 한국어 사용 가능
- 기본 스타일 (별도 style 정의 불필요)
- 사용자 스케치 구조를 최대한 유지하되 명확하게 정리
- subgraph 사용 가능 (그룹이 보이면)
- 불필요한 노드 추가 금지 — 스케치에 있는 것만 반영

## 예시 1 — 단순 흐름

입력:
- 노드: 사용자, 서버, DB (레이아웃: LR)
- 연결: 사용자→서버, 서버→DB

출력:
```json
{
  "diagram_type": "flowchart",
  "mermaid": "flowchart LR\\n    A[사용자] -->|요청| B[[서버]]\\n    B -->|쿼리| C[(DB)]\\n    C -->|결과| B\\n    B -->|응답| A",
  "interpretation": "사용자가 서버에 요청하면, 서버가 DB에서 데이터를 가져와 응답하는 흐름입니다."
}
```

## 예시 2 — 분기 + subgraph

입력:
- 노드: 시작, 검증, 성공처리, 실패처리, 종료 (레이아웃: TD)
- 연결: 시작→검증, 검증→성공처리 [분기 1], 검증→실패처리 [분기 2], 성공처리→종료, 실패처리→종료
- 그룹: [성공처리, 실패처리]

출력:
```json
{
  "diagram_type": "flowchart",
  "mermaid": "flowchart TD\\n    A([시작]) --> B{검증}\\n    subgraph 처리\\n        C[성공처리]\\n        D[실패처리]\\n    end\\n    B -->|통과| C\\n    B -->|실패| D\\n    C --> E((종료))\\n    D --> E",
  "interpretation": "시작 후 검증을 거쳐 통과/실패에 따라 분기 처리한 뒤 종료하는 흐름입니다."
}
```"""


# ── JSON 추출 ──

def _extract_json(text: str) -> dict | None:
    """AI 응답에서 JSON 블록 추출"""
    # 1) ```json ... ``` 블록
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 2) 중첩 {} 추적
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    start = -1

    # 3) 전체가 JSON
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


# ── API 엔드포인트 ──

def _get_sketchvibe_model() -> str:
    """SketchVibe 변환용 모델 조회 (DB 설정 → 기본값)"""
    try:
        from db import load_setting
        return load_setting("sketchvibe_model", "claude-sonnet-4-6")
    except Exception:
        return "claude-sonnet-4-6"


@router.post("/convert")
async def convert_sketch(req: ConvertRequest):
    """캔버스 스케치 + 자연어 → Mermaid 다이어그램 변환"""
    from ai_handler import ask_ai

    canvas_text = _parse_drawflow(req.canvas_json)

    user_msg = f"""## 캔버스 스케치 구조
{canvas_text}

## 사용자 설명
{req.description or '(설명 없음 — 스케치 구조에서 판단해주세요)'}

위 스케치를 Mermaid 다이어그램으로 변환해주세요. JSON으로만 응답."""

    try:
        result = await ask_ai(
            user_message=user_msg,
            system_prompt=_SYSTEM_PROMPT,
            model=_get_sketchvibe_model(),
            reasoning_effort="medium",
        )

        if "error" in result:
            return {"error": result["error"]}

        content = result.get("content", "")
        parsed = _extract_json(content)

        if parsed and "mermaid" in parsed:
            return {
                "mermaid": parsed["mermaid"],
                "interpretation": parsed.get("interpretation", ""),
                "diagram_type": parsed.get("diagram_type", "flowchart"),
                "model": result.get("model", ""),
                "cost_usd": result.get("cost_usd", 0),
            }
        else:
            return {
                "error": "AI 응답에서 Mermaid 코드를 추출할 수 없습니다",
                "raw": content[:500],
            }

    except Exception as e:
        logger.error("SketchVibe 변환 실패: %s", e, exc_info=True)
        return {"error": f"변환 실패: {str(e)}"}


@router.get("/canvas")
async def get_canvas_state():
    """MCP용 — 최근 저장된 캔버스 상태 반환"""
    knowledge_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "knowledge", "flowcharts",
    )
    if not os.path.isdir(knowledge_dir):
        return {"canvas": None, "message": "저장된 캔버스 없음"}

    files = sorted(
        [f for f in os.listdir(knowledge_dir) if f.endswith(".json")],
        key=lambda f: os.path.getmtime(os.path.join(knowledge_dir, f)),
        reverse=True,
    )
    if not files:
        return {"canvas": None, "message": "저장된 캔버스 없음"}

    with open(os.path.join(knowledge_dir, files[0]), "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "canvas": data,
        "filename": files[0],
        "parsed": _parse_drawflow(data),
    }


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
        "html_path": f"knowledge/sketchvibe/{safe_name}.html",
    }


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
