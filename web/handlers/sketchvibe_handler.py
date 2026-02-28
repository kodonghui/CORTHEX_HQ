"""
SketchVibe — 스케치 + 자연어 → Mermaid 다이어그램 변환

캔버스(Drawflow JSON) + 자연어 설명 → Claude → Mermaid 코드
"""
import json
import logging
import os
import re

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("corthex.sketchvibe")

router = APIRouter(prefix="/api/sketchvibe", tags=["sketchvibe"])


# ── 요청 모델 ──

class ConvertRequest(BaseModel):
    canvas_json: dict
    description: str = ""


class SaveDiagramRequest(BaseModel):
    mermaid: str
    name: str = "untitled"
    interpretation: str = ""


# ── Drawflow JSON 파싱 ──

def _extract_label(html: str) -> str:
    """nexus-node div에서 사용자 편집 텍스트 추출"""
    m = re.search(r">([^<]+)<", html or "")
    return m.group(1).strip() if m else ""


def _parse_drawflow(canvas: dict) -> str:
    """Drawflow export JSON → AI가 이해할 수 있는 구조화된 텍스트"""
    data = canvas.get("drawflow", {}).get("Home", {}).get("data", {})
    if not data:
        return "빈 캔버스 (노드 없음)"

    nodes = {}
    for nid, node in data.items():
        label = _extract_label(node.get("html", ""))
        if not label:
            label = node.get("data", {}).get("label", node.get("name", f"노드{nid}"))
        nodes[str(nid)] = {
            "id": str(nid),
            "label": label,
            "type": node.get("name", "unknown"),
        }

    connections = []
    for nid, node in data.items():
        for port in node.get("outputs", {}).values():
            for conn in port.get("connections", []):
                target = str(conn.get("node", "?"))
                connections.append((str(nid), target))

    lines = [f"노드 {len(nodes)}개:"]
    for n in nodes.values():
        lines.append(f'  [{n["id"]}] "{n["label"]}" (타입: {n["type"]})')

    if connections:
        lines.append(f"\n연결 {len(connections)}개:")
        for src, tgt in connections:
            src_l = nodes.get(src, {}).get("label", src)
            tgt_l = nodes.get(tgt, {}).get("label", tgt)
            lines.append(f'  "{src_l}" → "{tgt_l}"')
    else:
        lines.append("\n연결: 없음")

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
  "diagram_type": "flowchart 또는 graph",
  "mermaid": "Mermaid 코드 (줄바꿈은 실제 줄바꿈으로)",
  "interpretation": "한국어 1~2문장 요약"
}
```

## 다이어그램 타입 자동 판단
- **flowchart**: 순서/흐름/프로세스가 있는 것. Mermaid: `flowchart TD` 또는 `flowchart LR`
- **graph**: 관계/구조/연결을 보여주는 것. Mermaid: `graph TD` 또는 `graph LR`
사용자가 타입을 몰라도 됩니다. 스케치 구조 + 설명에서 자동 판단하세요.

## Mermaid 코드 규칙
- 노드 이름은 한국어 사용 가능
- 기본 스타일 (별도 style 정의 불필요)
- 사용자 스케치 구조를 최대한 유지하되 명확하게 정리
- subgraph 사용 가능 (그룹이 보이면)
- 불필요한 노드 추가 금지 — 스케치에 있는 것만 반영

## 예시

입력:
- 노드: 사용자, 서버, DB
- 연결: 사용자→서버, 서버→DB
- 설명: "요청→처리→응답 흐름"

출력:
```json
{
  "diagram_type": "flowchart",
  "mermaid": "flowchart LR\\n    A[사용자] -->|요청| B[서버]\\n    B -->|쿼리| C[(DB)]\\n    C -->|결과| B\\n    B -->|응답| A",
  "interpretation": "이렇게 이해했습니다: 사용자가 서버에 요청하면, 서버가 DB에서 데이터를 가져와 응답하는 흐름입니다."
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
            model="claude-sonnet-4-6",
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
    """확인된 다이어그램을 .md + .html 뷰어로 저장"""
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

    return {
        "saved": True,
        "md_path": f"knowledge/sketchvibe/{safe_name}.md",
        "html_path": f"knowledge/sketchvibe/{safe_name}.html",
    }


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
