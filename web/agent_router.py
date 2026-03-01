"""
CORTHEX HQ - 에이전트 라우팅 시스템 (P8 리팩토링)

CEO 명령 → 라우팅(분류) → 팀장 위임 → 전문가 병렬 호출 → QA → 종합 보고서
arm_server.py에서 분리된 에이전트 위임/라우팅/QA/노션/도구 로직 모듈.

주요 함수:
  _process_ai_command()  — CEO 명령 최상위 라우팅
  _call_agent()          — 단일 에이전트 AI 호출 (도구 자동호출 포함)
  _manager_with_delegation() — 팀장 독자분석 + 전문가 병렬 → 종합
  _broadcast_to_managers()   — Level 1~4 스마트 라우팅
  _init_tool_pool()      — ToolPool 초기화
  _load_agent_prompt()   — 에이전트 소울/프롬프트 로드
"""
import asyncio
import json
import logging
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 같은 폴더 모듈 ──
from ws_manager import wm
from state import app_state
from db import (
    save_activity_log, save_archive, save_setting, load_setting,
    get_today_cost, update_task, save_quality_review, get_connection,
    load_conversation_messages, load_conversation_messages_by_id,
)
from config_loader import (
    _log, _diag, _extract_title_summary, logger,
    KST, BASE_DIR, CONFIG_DIR, _load_config,
    _AGENTS_DETAIL, _TOOLS_LIST,
    _load_data, _save_data, _PROJECT_ROOT,
    AGENTS,
)

try:
    from ai_handler import (
        ask_ai, select_model, classify_task, get_available_providers,
        _load_tool_schemas,
    )
except ImportError:
    async def ask_ai(*a, **kw): return {"error": "ai_handler 미설치"}
    def select_model(t, override=None): return override or "claude-sonnet-4-6"
    async def classify_task(t): return {"agent_id": "chief_of_staff", "reason": "ai_handler 미설치", "cost_usd": 0}
    def get_available_providers(): return {"anthropic": False, "google": False, "openai": False}
    def _load_tool_schemas(allowed_tools=None): return {}

# batch_system 참조 (QA 재작업에서 _save_chain 사용 — 현재 QA 비활성)
try:
    from batch_system import _save_chain, _flush_batch_api_queue
except ImportError:
    def _save_chain(chain): pass
    async def _flush_batch_api_queue(): return {"error": "batch_system 미설치"}

# 품질검수 모듈 (CEO 지시로 비활성화됨)
_QUALITY_GATE_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════
# 상수 / 매핑 테이블
# ══════════════════════════════════════════════════════════════════

# 부서별 키워드 라우팅 테이블
_ROUTING_KEYWORDS: dict[str, list[str]] = {
    "leet_strategist": [
        "시장", "경쟁사", "사업계획", "매출", "예측", "전략",
        "비즈니스", "BM", "수익", "사업", "기획", "성장",
    ],
    "leet_legal": [
        "저작권", "특허", "상표", "약관", "계약", "법률", "소송", "IP",
        "규제", "라이선스", "법적", "법무",
    ],
    "leet_marketer": [
        "마케팅", "광고", "SNS", "인스타", "유튜브", "고객",
        "설문", "브랜딩", "콘텐츠", "홍보", "프로모션", "캠페인",
    ],
    "fin_analyst": [
        "삼성", "애플", "주식", "투자", "종목", "차트", "시황",
        "코스피", "나스닥", "포트폴리오", "금리", "환율", "채권",
        "ETF", "펀드", "배당", "테슬라", "엔비디아",
        "매수", "매도", "자동매매", "키움", "백테스트", "전략",
        "손절", "익절", "시가총액", "PER", "RSI", "MACD",
    ],
    "leet_publisher": [
        "기록", "빌딩로그", "연대기", "블로그", "출판", "편집", "회고",
        "아카이브", "문서화", "회의록",
    ],
}

# 에이전트 ID → 한국어 이름 매핑
_AGENT_NAMES: dict[str, str] = {
    "chief_of_staff": "비서실장",
    "leet_strategist": "전략팀장",
    "leet_legal": "법무팀장",
    "leet_marketer": "마케팅팀장",
    "fin_analyst": "금융분석팀장",
    "leet_publisher": "콘텐츠팀장",
}

# 한국어 이름 → 에이전트 ID 역매핑 (명시적 지시 파싱용)
_AGENT_NAME_TO_ID: dict[str, str] = {v: k for k, v in _AGENT_NAMES.items()}


def _can_command(session_role: str, agent_id: str) -> bool:
    """v5: CLI 라우팅 보호 — session_role과 cli_owner가 일치할 때만 허용.
    chief_of_staff는 CEO 전용. 그 외 에이전트는 cli_owner 기준."""
    if agent_id == "chief_of_staff":
        return session_role == "ceo"
    detail = _AGENTS_DETAIL.get(agent_id, {})
    cli_owner = detail.get("cli_owner", "ceo")
    return session_role == cli_owner


def _parse_explicit_target(text: str) -> str | None:
    """'~팀장에게 지시/질문' 패턴에서 팀장 ID 추출. 명시적 지시 최우선."""
    for name, agent_id in _AGENT_NAME_TO_ID.items():
        if name in text:
            return agent_id
    return None

# 브로드캐스트 키워드 (모든 부서에 동시 전달하는 명령)
_BROADCAST_KEYWORDS = [
    "전체", "모든 부서", "출석", "회의", "현황 보고",
    "총괄", "전원", "각 부서", "출석체크", "브리핑",
]

# 팀장/비서실장 → 소속 전문가 매핑
# 2026-02-25: 전문가 전원 동면 → 팀장 단독 분석 체제.
# 재도입 시점: 팀장 혼자 30분+ & 병렬이 의미 있을 때 (CLAUDE.md 규칙)
_MANAGER_SPECIALISTS: dict[str, list[str]] = {
    "chief_of_staff": [],
    "leet_strategist": [],
    "leet_legal": [],
    "leet_marketer": [],
    "fin_analyst": [],
    "leet_publisher": [],
}

# 매니저 → 부서 매핑 (품질검수 루브릭 조회용)
_MANAGER_DIVISION: dict[str, str] = {
    "chief_of_staff": "secretary",
    "leet_strategist": "leet_master.strategy",
    "leet_legal": "leet_master.legal",
    "leet_marketer": "leet_master.marketing",
    "fin_analyst": "finance.investment",
    "leet_publisher": "publishing",
}

# 동면 부서 (품질검수 제외)
_DORMANT_MANAGERS: set[str] = set()

# 에이전트 ID → 부서명 매핑 (AGENTS 리스트에서 자동 구축)
_AGENT_DIVISION: dict[str, str] = {}
for _a in AGENTS:
    if _a.get("division"):
        _AGENT_DIVISION[_a["agent_id"]] = _a["division"]

# B안: 전문가별 역할 prefix — 전문가 전원 제거 (2026-02-26). 재도입 시 여기에 추가.
_SPECIALIST_ROLE_PREFIX: dict[str, str] = {}

# 전문가 ID → 한국어 이름 (AGENTS 리스트에서 자동 구축)
_SPECIALIST_NAMES: dict[str, str] = {}
for _a in AGENTS:
    if _a["role"] == "specialist":
        _SPECIALIST_NAMES[_a["agent_id"]] = _a["name_ko"]

# 텔레그램 직원코드 매핑 (agents.yaml의 telegram_code 필드에서 자동 구축)
_TELEGRAM_CODES: dict[str, str] = {}
for _a in AGENTS:
    if _a.get("telegram_code"):
        _TELEGRAM_CODES[_a["agent_id"]] = _a["telegram_code"]

# 순차 협업 트리거 키워드
_SEQUENTIAL_KEYWORDS = ["순차", "협업", "순서대로", "단계별", "릴레이", "연계"]

# 토론 발언 순서 로테이션
DEBATE_ROTATION = [
    ["fin_analyst", "cto_manager", "leet_strategist", "leet_marketer", "leet_legal", "leet_publisher"],
    ["cto_manager", "leet_strategist", "fin_analyst", "leet_legal", "leet_marketer", "leet_publisher"],
    ["leet_strategist", "leet_marketer", "cto_manager", "fin_analyst", "leet_publisher", "leet_legal"],
]

# 팀장별 토론 관점 — 1라운드에서 각자 무엇을 분석해야 하는지 구체적으로 지시
_DEBATE_LENSES: dict[str, str] = {
    "fin_analyst": (
        "투자/재무 관점에서 분석하세요:\n"
        "- 이 주제가 회사 재무에 미치는 영향 (매출, 비용, ROI 수치 추정)\n"
        "- 실행 시 재무 리스크와 기회비용\n"
        "- 시장/경쟁 환경에서 타이밍이 적절한지 근거 제시"
    ),
    "cto_manager": (
        "기술 실현 가능성 관점에서 분석하세요:\n"
        "- 현재 기술 스택으로 구현 가능한지, 추가 필요한 기술은 무엇인지\n"
        "- 개발 리소스 (인력, 시간, 비용) 현실적 추정\n"
        "- 기술적 리스크 (확장성, 유지보수, 보안) 구체적으로"
    ),
    "leet_strategist": (
        "사업 전략 관점에서 분석하세요:\n"
        "- 시장 규모와 경쟁 구도 (구체적 수치나 사례 인용)\n"
        "- 우리의 차별화 포인트가 무엇이고 경쟁 우위가 지속 가능한지\n"
        "- 실행 전략의 단계와 우선순위"
    ),
    "leet_marketer": (
        "마케팅/고객 관점에서 분석하세요:\n"
        "- 타겟 고객이 이것을 정말 원하는지, 어떤 근거가 있는지\n"
        "- 고객 획득 비용(CAC)과 채널 전략의 현실성\n"
        "- 브랜드/포지셔닝에 미치는 영향"
    ),
    "leet_legal": (
        "법무/리스크 관점에서 분석하세요:\n"
        "- 법적 리스크와 규제 이슈 (구체적 법령이나 판례 인용)\n"
        "- 지식재산권 보호 방안 또는 침해 위험\n"
        "- 계약/약관/개인정보 관련 주의사항"
    ),
    "leet_publisher": (
        "제품/콘텐츠 관점에서 분석하세요:\n"
        "- 사용자 경험과 제품 완성도에 미치는 영향\n"
        "- 콘텐츠 전략 및 지식 자산으로서의 가치\n"
        "- 실행 시 품질 기준과 기록/문서화 방안"
    ),
}


# ══════════════════════════════════════════════════════════════════
# 노션 API 연동 (에이전트 산출물 자동 저장)
# ══════════════════════════════════════════════════════════════════

_TITLE_SKIP_WORDS = {"죄송", "오류", "에러", "실패", "sorry", "error", "안녕하세요", "네,", "네!"}
_TITLE_CMD_ENDINGS = ("해줘", "해주세요", "해봐", "하세요", "할까요", "알려줘", "알려주세요",
                      "보고해", "분석해", "조사해", "만들어줘", "작성해", "정리해")


def _extract_notion_title(content: str, fallback: str = "보고서",
                          user_query: str = "") -> str:
    """AI 응답 본문에서 깔끔한 제목을 추출합니다.
    금지어(사과/에러 문구), CEO 명령문 패턴, user_query 반복 줄은 건너뜁니다."""
    if not content:
        return fallback
    q_norm = user_query.strip().replace("**", "").replace("*", "")[:20] if user_query else ""
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        line = line.lstrip("#").strip()
        line = line.replace("**", "").replace("*", "")
        if len(line) < 3 or line.startswith("---") or line.startswith("```"):
            continue
        low = line[:10].lower()
        if any(low.startswith(w) for w in _TITLE_SKIP_WORDS):
            continue
        if any(line.rstrip(".,!? ").endswith(e) for e in _TITLE_CMD_ENDINGS):
            continue
        if q_norm and len(q_norm) > 5 and line[:20].startswith(q_norm[:15]):
            continue
        return line[:100]
    return fallback


_NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
_NOTION_DB_SECRETARY = os.getenv("NOTION_DB_SECRETARY", "30a56b49-78dc-8153-bac1-dee5d04d6a74")
_NOTION_DB_OUTPUT = os.getenv("NOTION_DB_OUTPUT", "30a56b49-78dc-81ce-aaca-ef3fc90a6fba")
_NOTION_DB_ARCHIVE = os.getenv("NOTION_DB_ARCHIVE", "31256b49-78dc-81c9-9ad2-e31a076d0d97")
_NOTION_DB_ID = os.getenv("NOTION_DEFAULT_DB_ID", _NOTION_DB_OUTPUT)

_notion_log = app_state.notion_log


def _add_notion_log(status: str, title: str, db: str = "", url: str = "", error: str = ""):
    """노션 작업 로그를 저장합니다 (최근 500개)."""
    _notion_log.append({
        "time": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "title": title[:60],
        "db": db,
        "url": url,
        "error": error[:200] if error else "",
    })
    if len(_notion_log) > 500:
        del _notion_log[:-500]


async def _save_to_notion(agent_id: str, title: str, content: str,
                          report_type: str = "보고서",
                          db_target: str = "output") -> str | None:
    """에이전트 산출물을 노션 DB에 저장합니다.

    db_target: "output" = 에이전트 산출물 DB, "secretary" = 비서실 DB
    Python 기본 라이브러리(urllib)만 사용 — 추가 패키지 불필요.
    실패해도 에러만 로깅하고 None 반환 (서버 동작에 영향 없음).
    """
    if not _NOTION_API_KEY:
        _add_notion_log("SKIP", title, error="API 키 없음")
        return None

    db_id = _NOTION_DB_SECRETARY if db_target == "secretary" else _NOTION_DB_OUTPUT
    db_name = "비서실" if db_target == "secretary" else "산출물"

    division = _AGENT_DIVISION.get(agent_id, "")
    agent_name = _AGENT_NAMES.get(agent_id, _SPECIALIST_NAMES.get(agent_id, agent_id))
    now_str = datetime.now(KST).strftime("%Y-%m-%d")

    properties: dict = {
        "Name": {"title": [{"text": {"content": title[:100]}}]},
    }
    if db_target == "secretary":
        if agent_name:
            properties["담당자"] = {"select": {"name": agent_name}}
        properties["카테고리"] = {"select": {"name": "보고서"}}
        if content:
            properties["내용"] = {"rich_text": [{"text": {"content": content[:2000]}}]}
    else:
        if agent_name:
            properties["에이전트"] = {"select": {"name": agent_name}}
        if report_type:
            properties["보고유형"] = {"select": {"name": report_type}}
        _div_map = {
            "secretary": "비서실",
            "leet_master.tech": "LEET MASTER",
            "leet_master.strategy": "LEET MASTER",
            "leet_master.legal": "LEET MASTER",
            "leet_master.marketing": "LEET MASTER",
            "finance.investment": "투자분석",
            "publishing": "출판기록",
        }
        notion_div = _div_map.get(division, "")
        if notion_div:
            properties["부서"] = {"select": {"name": notion_div}}
    properties["상태"] = {"select": {"name": "완료"}}
    properties["날짜"] = {"date": {"start": now_str}}

    children = []
    text_chunks = [content[i:i+1900] for i in range(0, min(len(content), 8000), 1900)]
    for chunk in text_chunks:
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": chunk}}]},
        })

    body = json.dumps({
        "parent": {"database_id": db_id},
        "properties": properties,
        "children": children,
    }).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {_NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    def _do_request():
        req = urllib.request.Request(
            "https://api.notion.com/v1/pages",
            data=body, headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:300]
            _log(f"[Notion] HTTP {e.code} 오류 ({db_name}): {err_body}")
            return {"_error": f"HTTP {e.code}: {err_body}"}
        except Exception as e:
            _log(f"[Notion] 요청 실패 ({db_name}): {e}")
            return {"_error": str(e)}

    try:
        result = await asyncio.to_thread(_do_request)
        if result and "_error" in result:
            _add_notion_log("FAIL", title, db=db_name, error=result["_error"])
            return None
        if result and result.get("url"):
            _log(f"[Notion] 저장 완료 ({db_name}): {title[:50]} → {result['url']}")
            _add_notion_log("OK", title, db=db_name, url=result["url"])
            return result["url"]
        elif result:
            resp_snippet = str(result)[:200]
            _log(f"[Notion] 응답에 URL 없음 ({db_name}): {resp_snippet}")
            _add_notion_log("FAIL", title, db=db_name, error=f"응답에 URL 없음: {resp_snippet}")
        else:
            _add_notion_log("FAIL", title, db=db_name, error="응답 없음(None)")
    except Exception as e:
        _log(f"[Notion] 비동기 실행 실패: {e}")
        _add_notion_log("FAIL", title, db=db_name, error=str(e))

    return None


# ══════════════════════════════════════════════════════════════════
# 품질검수 (QA) 시스템 — CEO 지시로 비활성화 (2026-02-27)
# ══════════════════════════════════════════════════════════════════

def _init_quality_gate():
    """품질검수 게이트 초기화."""
    if not _QUALITY_GATE_AVAILABLE:
        _log("[QA] QualityGate 모듈 미설치 — 품질검수 비활성")
        return
    config_path = Path(__file__).parent.parent / "config" / "quality_rules.yaml"
    app_state.quality_gate = QualityGate(config_path)
    _log("[QA] 품질검수 게이트 초기화 완료")


class _QAModelRouter:
    """ask_ai()를 ModelRouter.complete() 인터페이스로 감싸는 어댑터 (품질검수용)."""

    async def complete(self, model_name="", messages=None,
                       temperature=0.0, max_tokens=4096,
                       agent_id="", **kwargs):
        from src.llm.base import LLMResponse
        messages = messages or []
        system_prompt = ""
        user_message = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg["content"]
            elif msg.get("role") == "user":
                user_message = msg["content"]
        result = await ask_ai(user_message, system_prompt, model_name)
        if "error" in result:
            return LLMResponse(
                content=f"[QA 오류] {result['error']}",
                model=model_name,
                input_tokens=0, output_tokens=0,
                cost_usd=0.0, provider="unknown",
            )
        return LLMResponse(
            content=result["content"],
            model=result.get("model", model_name),
            input_tokens=result.get("input_tokens", 0),
            output_tokens=result.get("output_tokens", 0),
            cost_usd=result.get("cost_usd", 0.0),
            provider=result.get("provider", "unknown"),
        )

_qa_router = _QAModelRouter()


async def _quality_review_specialists(
    chain: dict,
    previous_reviews: dict | None = None,
) -> list[dict]:
    """전문가 결과를 매니저 모델로 개별 검수. 불합격 목록 반환."""
    if not app_state.quality_gate or not _QUALITY_GATE_AVAILABLE:
        return []

    target_id = chain.get("target_id", "chief_of_staff")
    if target_id in _DORMANT_MANAGERS:
        return []

    division = _MANAGER_DIVISION.get(target_id, "default")
    reviewer_model = _get_model_override(target_id) or "claude-sonnet-4-6"
    task_desc = chain.get("original_command", "")[:500]
    failed = []

    _spec_ids = list(chain.get("results", {}).get("specialists", {}).keys())
    if _spec_ids:
        _spec_names = ", ".join(_AGENT_NAMES.get(s, _SPECIALIST_NAMES.get(s, s)) for s in _spec_ids[:4])
        _qa_start_log = save_activity_log(
            target_id, f"🔍 검수 시작: {_spec_names} ({len(_spec_ids)}명)", level="qa_start"
        )
        await wm.send_activity_log(_qa_start_log)

    for agent_id, result_data in chain.get("results", {}).get("specialists", {}).items():
        content = result_data.get("content", "")

        if previous_reviews and agent_id not in previous_reviews:
            continue

        if result_data.get("error"):
            failed.append({
                "agent_id": agent_id,
                "review": None,
                "content": content,
                "reason": f"에러 응답: {result_data.get('error', '')[:100]}",
            })
            continue

        _qa_content = content
        _spec_tools = result_data.get("tools_used", [])
        if _spec_tools:
            _unique_tools = list(dict.fromkeys(_spec_tools))
            from collections import Counter as _Counter
            _tool_counts = _Counter(_spec_tools)
            _tool_detail = ", ".join(f"{t}({c}회)" for t, c in _tool_counts.most_common())
            _qa_content += (
                f"\n\n---\n## 사용한 도구 (총 {len(_spec_tools)}회 호출, 고유 {len(_unique_tools)}종)\n"
                f"{_tool_detail}\n"
                f"※ 위 도구들은 실시간 API를 호출하여 분석 당일의 최신 데이터를 가져온 것입니다.\n"
                f"※ 도구가 반환한 수치(주가, 재무제표, 거시지표 등)는 정확한 실시간 데이터입니다."
            )

        try:
            _prev_review = (previous_reviews or {}).get(agent_id)
            if _prev_review is not None:
                review = await app_state.quality_gate.targeted_hybrid_review(
                    result_data=_qa_content,
                    task_description=task_desc,
                    model_router=_qa_router,
                    previous_review=_prev_review,
                    reviewer_id=target_id,
                    reviewer_model=reviewer_model,
                    division=division,
                    target_agent_id=agent_id,
                )
            else:
                review = await app_state.quality_gate.hybrid_review(
                    result_data=_qa_content,
                    task_description=task_desc,
                    model_router=_qa_router,
                    reviewer_id=target_id,
                    reviewer_model=reviewer_model,
                    division=division,
                    target_agent_id=agent_id,
                )
            app_state.quality_gate.record_review(review, target_id, agent_id, task_desc)
            chain["total_cost_usd"] += getattr(review, "_cost", 0)

            _spec_name = _SPECIALIST_NAMES.get(agent_id, agent_id)
            _qa_parts = []
            for ci in review.checklist_results:
                _ico = "✅" if ci.passed else "❌"
                _req = "[필]" if ci.required else ""
                _qa_parts.append(f"{ci.id}{_ico}{_req}")
            for si in review.score_results:
                _crit = "⬇" if si.critical and si.score == 1 else ""
                _qa_parts.append(f"{si.id}:{si.score}{_crit}")
            _pass_icon = "✅" if review.passed else "❌"
            _pass_text = "합격" if review.passed else "부합격"
            _qa_summary = f"{_pass_icon} {_spec_name} {_pass_text}({review.weighted_average:.1f}) {' '.join(_qa_parts)}"
            _qa_unified_log = save_activity_log(
                agent_id, _qa_summary, level="qa_detail"
            )
            await wm.send_activity_log(_qa_unified_log)

            import json as _json
            try:
                save_quality_review(
                    chain_id=chain.get("chain_id", ""),
                    reviewer_id=target_id,
                    target_id=agent_id,
                    division=division,
                    passed=review.passed,
                    weighted_score=review.weighted_average,
                    checklist_json=_json.dumps(
                        [{"id": c.id, "passed": c.passed, "required": c.required}
                         for c in review.checklist_results], ensure_ascii=False
                    ),
                    scores_json=_json.dumps(
                        [{"id": s.id, "score": s.score, "weight": s.weight}
                         for s in review.score_results], ensure_ascii=False
                    ),
                    feedback=review.feedback[:500],
                    rejection_reasons=" / ".join(review.rejection_reasons)[:500] if review.rejection_reasons else "",
                    review_model=review.review_model,
                )
            except Exception as e:
                logger.debug("검수 결과 DB 저장 실패: %s", e)

            chain.setdefault("qa_reviews", []).append({
                "agent_id": agent_id,
                "passed": review.passed,
                "weighted_average": review.weighted_average,
                "review_dict": review.to_dict(),
            })

            if not review.passed:
                reason = " / ".join(review.rejection_reasons) if review.rejection_reasons else "품질 기준 미달"
                failed.append({
                    "agent_id": agent_id,
                    "review": review,
                    "content": content,
                    "reason": reason,
                })
                _log(f"[QA] ❌ 불합격: {agent_id} (점수={review.weighted_average:.1f}, 사유={reason[:80]})")
                qa_log = save_activity_log(
                    agent_id,
                    f"❌ [{agent_id}] 불합격 (점수 {review.weighted_average:.1f}) — {reason[:60]}",
                    level="qa_fail"
                )
                await wm.send_activity_log(qa_log)

                _spec_name_rej = _SPECIALIST_NAMES.get(agent_id, agent_id)
                _rej_comms = {
                    "id": f"rej_{chain.get('chain_id', '')[:6]}_{agent_id[:8]}",
                    "sender": target_id,
                    "receiver": agent_id,
                    "message": f"❌ {_spec_name_rej} 반려: {reason[:200]}",
                    "log_type": "delegation",
                    "source": "qa_rejection",
                    "status": "반려",
                    "created_at": datetime.now().isoformat(),
                }
                await wm.broadcast_sse(_rej_comms)

                from datetime import datetime as _dt_rej
                _rej_date = _dt_rej.now().strftime("%Y%m%d_%H%M")
                _rej_filename = f"반려사유_{_spec_name_rej}_{_rej_date}.md"
                _rej_detail = []
                for ci in review.checklist_results:
                    if not ci.passed:
                        _rej_detail.append(f"- {ci.id} {ci.label}: ❌ 불통과{' [필수]' if ci.required else ''}")
                for si in review.score_results:
                    if si.score <= 3:
                        _fb = f" — {si.feedback}" if si.feedback else ""
                        _rej_detail.append(f"- {si.id} {si.label}: {si.score}점/5{_fb}")
                _rej_content = (
                    f"# 반려사유 — {_spec_name_rej}\n\n"
                    f"**점수**: {review.weighted_average:.1f}/5.0\n"
                    f"**사유**: {reason}\n\n"
                    f"## 항목별 문제점\n" + "\n".join(_rej_detail) + "\n\n"
                    f"## 피드백\n{review.feedback[:500]}\n"
                )
                try:
                    save_archive(division, _rej_filename, _rej_content,
                                 correlation_id=chain.get("chain_id", ""),
                                 agent_id=target_id)
                except Exception as _ae:
                    logger.debug("반려사유 기밀문서 저장 실패: %s", _ae)

                try:
                    _mem_key = f"memory_categorized_{agent_id}"
                    _existing_mem = load_setting(_mem_key, {})
                    _warning_lesson = f"{_dt_rej.now().strftime('%m/%d')}: {reason[:100]}"
                    _prev_warnings = _existing_mem.get("warnings", "")
                    _existing_mem["warnings"] = (
                        (_prev_warnings + " | " + _warning_lesson).strip(" |")
                        if _prev_warnings else _warning_lesson
                    )
                    save_setting(_mem_key, _existing_mem)
                    _log(f"[QA] 반려 학습 저장: {agent_id} ← {_warning_lesson[:60]}")
                except Exception as _me:
                    logger.debug("반려 학습 저장 실패: %s", _me)
            else:
                _log(f"[QA] ✅ 합격: {agent_id} (점수={review.weighted_average:.1f})")
                qa_log = save_activity_log(
                    agent_id,
                    f"✅ [{agent_id}] 합격 (점수 {review.weighted_average:.1f})",
                    level="qa_pass"
                )
                await wm.send_activity_log(qa_log)

        except Exception as e:
            _log(f"[QA] 검수 오류 ({agent_id}): {e}")

    return failed


async def _handle_specialist_rework(chain: dict, failed_specs: list[dict], attempt: int = 1):
    """불합격 전문가에게 재작업 지시 → 재검수."""
    max_retry = app_state.quality_gate.max_retry if app_state.quality_gate else 2
    if attempt > max_retry:
        for spec in failed_specs:
            agent_id = spec["agent_id"]
            _log(f"[QA] ⚠️ 재작업 {max_retry}회 초과 — {agent_id} 결과를 경고 포함 채 종합 진행")
            existing = chain["results"]["specialists"].get(agent_id, {})
            existing["quality_warning"] = spec.get("reason", "품질 기준 미달")[:200]
            chain["results"]["specialists"][agent_id] = existing
        return

    target_id = chain.get("target_id", "chief_of_staff")
    target_name = _AGENT_NAMES.get(target_id, target_id)
    task_desc = chain.get("original_command", "")[:500]

    try:
        from batch_system import _broadcast_chain_status
        await _broadcast_chain_status(
            chain,
            f"🔄 품질검수 불합격 {len(failed_specs)}건 → 재작업 지시 (시도 {attempt}/{max_retry})"
        )
    except ImportError:
        pass

    async def _do_single_rework(spec: dict) -> None:
        agent_id = spec["agent_id"]
        reason = spec.get("reason", "품질 기준 미달")
        original_content = spec.get("content", "")

        agent_name = _AGENT_NAMES.get(agent_id, agent_id)
        await _broadcast_status(agent_id, "working", 0.5, f"{agent_name} 재작업 중...")

        _review = spec.get("review")
        _detail_lines = []
        _failed_ids: list[str] = []
        if _review:
            from src.core.quality_gate import QualityGate as _QG
            _failed_ids = _QG.get_failed_item_ids(_review)
            for ci in _review.checklist_results:
                if not ci.passed:
                    _rq = " [필수]" if ci.required else ""
                    _fb = f" — {ci.feedback}" if ci.feedback else ""
                    _detail_lines.append(f"- ❌ {ci.id} {ci.label}{_rq}{_fb}")
            for si in _review.score_results:
                if si.score <= 1:
                    _crit = " ⚠️치명적" if si.critical else ""
                    _fb = f" — {si.feedback}" if si.feedback else ""
                    _detail_lines.append(f"- ❌ {si.id} {si.label}: {si.score}점/5{_crit}{_fb}")
        _detail_block = "\n".join(_detail_lines) if _detail_lines else "(상세 항목 없음)"
        _failed_ids_str = ", ".join(_failed_ids) if _failed_ids else "(전체)"

        rework_prompt = (
            f"[재작업 요청 #{attempt}] 당신의 보고서가 품질검수에서 불합격되었습니다.\n\n"
            f"## 반려 항목 ID: {_failed_ids_str}\n"
            f"⚠️ 위 항목만 수정하세요. 통과한 항목은 수정하지 마세요.\n"
            f"⚠️ 재검수 시 위 항목만 재채점됩니다. 나머지는 이전 점수가 유지됩니다.\n\n"
            f"## 원래 업무 지시\n{task_desc}\n\n"
            f"## 불합격 사유\n{reason}\n\n"
            f"## 항목별 검수 결과\n{_detail_block}\n\n"
            f"## 당신의 이전 보고서 (전문)\n{original_content}\n\n"
            f"## 지시사항\n"
            f"⚠️ 반려된 항목만 수정하고 나머지는 그대로 유지하세요.\n"
            f"- 정확했던 수치(매출, PER, 주가 등)를 변경하지 마세요.\n"
            f"- 지적된 부분만 보완하세요 (도구 재호출하여 최신 데이터 확인).\n"
            f"- 보고서 전체를 다시 쓰지 말고, 문제 항목을 정확히 수정하세요."
        )

        try:
            spec_model = _get_model_override(agent_id) or "claude-sonnet-4-6"
            spec_soul = _load_agent_prompt(agent_id)
            rework_tool_schemas = None
            rework_tool_executor = None
            rework_tools_used: list[str] = []
            _rw_detail = _AGENTS_DETAIL.get(agent_id, {})
            _rw_allowed = _rw_detail.get("allowed_tools", [])
            if _rw_allowed:
                _rw_schemas = _load_tool_schemas(allowed_tools=_rw_allowed)
                if _rw_schemas.get("anthropic"):
                    rework_tool_schemas = _rw_schemas["anthropic"]
                    _rw_max = int(_rw_detail.get("max_tool_calls", 5))
                    _captured_id = agent_id
                    _captured_name = agent_name

                    async def _rework_executor(tool_name: str, tool_input: dict,
                                               _aid=_captured_id, _aname=_captured_name):
                        rework_tools_used.append(tool_name)
                        _cnt = len(rework_tools_used)
                        await _broadcast_status(
                            _aid, "working", 0.5 + min(_cnt / _rw_max, 1.0) * 0.3,
                            f"{tool_name} 실행 중... (재작업)",
                        )
                        _rw_log = save_activity_log(
                            _aid,
                            f"🔧 [{_aname}] {tool_name} 호출 ({_cnt}회) [재작업#{attempt}]",
                            level="tool",
                        )
                        await wm.send_activity_log(_rw_log)
                        pool = _init_tool_pool()
                        if pool:
                            return await pool.invoke(tool_name, caller_id=_aid, **tool_input)
                        return f"도구 '{tool_name}'을(를) 찾을 수 없습니다."

                    rework_tool_executor = _rework_executor

            result = await ask_ai(
                user_message=rework_prompt,
                system_prompt=spec_soul,
                model=spec_model,
                tools=rework_tool_schemas,
                tool_executor=rework_tool_executor,
                reasoning_effort=_get_agent_reasoning_effort(agent_id),
            )

            if "error" not in result:
                chain["results"]["specialists"][agent_id] = {
                    "content": result["content"],
                    "model": result.get("model", spec_model),
                    "cost_usd": result.get("cost_usd", 0),
                    "rework_attempt": attempt,
                    "tools_used": result.get("tools_used", []),
                }
                chain["total_cost_usd"] += result.get("cost_usd", 0)
                _log(f"[QA] 재작업 완료: {agent_id} (시도 {attempt})")

                from datetime import datetime as _dt_rw
                _rw_date = _dt_rw.now().strftime("%Y%m%d_%H%M")
                _rw_div = _AGENT_DIVISION.get(agent_id, "default")
                _rw_filename = f"{agent_name}_보고서_재작업v{attempt}_{_rw_date}.md"
                try:
                    save_archive(
                        _rw_div, _rw_filename, result["content"],
                        correlation_id=chain.get("chain_id", ""),
                        agent_id=agent_id,
                    )
                except Exception as _ae2:
                    logger.debug("재작업 기밀문서 저장 실패: %s", _ae2)
                _rw_log = save_activity_log(
                    agent_id,
                    f"🔄 [{agent_name}] 재작업 보고서 제출 (v{attempt})",
                    level="info",
                )
                await wm.send_activity_log(_rw_log)
            else:
                _log(f"[QA] 재작업 실패: {agent_id} — {result.get('error', '')[:100]}")

        except Exception as e:
            _log(f"[QA] 재작업 오류 ({agent_id}): {e}")

        await _broadcast_status(agent_id, "done", 1.0, "재작업 완료")

    await asyncio.gather(*[_do_single_rework(spec) for spec in failed_specs])

    _prev_reviews = {}
    for spec in failed_specs:
        _rv = spec.get("review")
        if _rv is not None:
            _prev_reviews[spec["agent_id"]] = _rv

    _save_chain(chain)
    still_failed = await _quality_review_specialists(chain, previous_reviews=_prev_reviews)

    if still_failed:
        await _handle_specialist_rework(chain, still_failed, attempt + 1)
    else:
        _log(f"[QA] 재작업 후 전원 합격 (시도 {attempt})")


# ══════════════════════════════════════════════════════════════════
# 헬퍼 함수
# ══════════════════════════════════════════════════════════════════

def _tg_code(agent_id: str) -> str:
    """agent_id → 텔레그램 코드명 (없으면 name_ko 폴백)."""
    return _TELEGRAM_CODES.get(
        agent_id,
        _AGENT_NAMES.get(agent_id, _SPECIALIST_NAMES.get(agent_id, agent_id))
    )


def _tg_convert_names(text: str) -> str:
    """텍스트 내 에이전트 이름을 텔레그램 코드명으로 변환합니다."""
    for aid, code in _TELEGRAM_CODES.items():
        name = _AGENT_NAMES.get(aid, _SPECIALIST_NAMES.get(aid, ""))
        if name and name in text:
            text = text.replace(name, code)
    return text


def _is_broadcast_command(text: str) -> bool:
    """브로드캐스트 명령인지 확인합니다."""
    return any(kw in text for kw in _BROADCAST_KEYWORDS)


async def _broadcast_status(agent_id: str, status: str, progress: float, detail: str = ""):
    """에이전트 상태를 모든 WebSocket 클라이언트에게 전송합니다."""
    await wm.send_agent_status(agent_id, status, progress, detail)


async def _broadcast_comms(msg_data: dict):
    """SSE 클라이언트들에게 내부통신 메시지 broadcast."""
    await wm.broadcast_sse(msg_data)


async def _extract_and_save_memory(agent_id: str, task: str, response: str):
    """대화 후 기억할 정보 추출 → save_setting에 저장 (비동기 백그라운드)."""
    try:
        extraction_prompt = (
            "아래 대화에서 에이전트가 기억해야 할 정보가 있으면 JSON으로 추출해라. "
            "없으면 빈 dict {} 반환.\n\n"
            f"[대화]\n사용자: {task[:400]}\n에이전트: {response[:400]}\n\n"
            "[추출 항목]\n"
            "- ceo_preferences: CEO가 선호하거나 싫어하는 것 (있으면)\n"
            "- decisions: '~하기로 결정', '~로 확정' 등 중요 결정 (있으면)\n"
            "- warnings: 이 방법은 안 됨, CEO가 싫다고 함 등 주의사항 (있으면)\n"
            "- context: 프로젝트 상태, 거래처, 일정 등 중요 맥락 (있으면)\n\n"
            "JSON만 반환 (설명 없이):"
        )

        from ai_handler import _USE_CLI_FOR_CLAUDE
        _mem_providers = get_available_providers()
        if _mem_providers.get("google"):
            _mem_model = "gemini-2.5-flash"
        elif _mem_providers.get("openai"):
            _mem_model = "gpt-5-mini"
        elif _USE_CLI_FOR_CLAUDE:
            _mem_model = "claude-haiku-4-5-20251001"  # CLI 라우팅 → API 크레딧 소진 방지
        else:
            _mem_model = "claude-sonnet-4-6"
        result = await ask_ai(
            user_message=extraction_prompt,
            model=_mem_model,
            max_tokens=400,
            system_prompt="JSON만 반환. 설명 없이."
        )

        text_resp = result.get("content", "") if isinstance(result, dict) else str(result)
        text_resp = text_resp.strip()
        if "```" in text_resp:
            text_resp = text_resp.split("```")[1].strip()
            if text_resp.startswith("json"):
                text_resp = text_resp[4:].strip()

        new_facts = json.loads(text_resp)
        if new_facts and isinstance(new_facts, dict):
            existing = load_setting(f"memory_categorized_{agent_id}", {})
            for key, val in new_facts.items():
                if val and val not in ("null", "없음", ""):
                    prev = existing.get(key, "")
                    existing[key] = (prev + " | " + str(val)).strip(" |") if prev else str(val)
            save_setting(f"memory_categorized_{agent_id}", existing)
    except Exception as e:
        logger.debug(f"기억 추출 건너뜀 ({agent_id}): {e}")


def _is_sequential_command(text: str) -> bool:
    """순차 협업 명령인지 확인합니다."""
    return any(kw in text for kw in _SEQUENTIAL_KEYWORDS)


def _classify_by_keywords(text: str) -> str | None:
    """키워드 기반 빠른 분류. 매칭 실패 시 None 반환."""
    for agent_id, keywords in _ROUTING_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return agent_id
    return None


async def _route_task(text: str) -> dict:
    """CEO 명령을 적합한 에이전트에게 라우팅합니다.

    0단계: 명시적 팀장 지시 파싱 ("~팀장에게 지시") — 최우선
    1단계: 키워드 매칭 (무료, 즉시)
    2단계: AI 분류 (Haiku/Flash, ~$0.001)
    3단계: 폴백 → 비서실장
    """
    # 0단계: "~팀장에게 지시" 명시적 파싱 — 최우선
    explicit_id = _parse_explicit_target(text)
    if explicit_id:
        return {"agent_id": explicit_id, "method": "명시적지시", "cost_usd": 0.0, "reason": f"명시적 팀장 지시"}

    agent_id = _classify_by_keywords(text)
    if agent_id:
        return {"agent_id": agent_id, "method": "키워드", "cost_usd": 0.0, "reason": "키워드 매칭"}

    result = await classify_task(text)
    if result.get("agent_id") and result["agent_id"] != "chief_of_staff":
        return {
            "agent_id": result["agent_id"],
            "method": "AI분류",
            "cost_usd": result.get("cost_usd", 0),
            "reason": result.get("reason", "AI 분류"),
        }

    return {
        "agent_id": "chief_of_staff",
        "method": "직접",
        "cost_usd": result.get("cost_usd", 0),
        "reason": result.get("reason", "비서실장 직접 처리"),
    }


def _get_tool_descriptions(agent_id: str) -> str:
    """에이전트에 할당된 도구 설명을 생성합니다."""
    detail = _AGENTS_DETAIL.get(agent_id, {})
    allowed = detail.get("allowed_tools", [])
    if not allowed:
        return ""

    tool_map = {t.get("tool_id"): t for t in _TOOLS_LIST}
    descs = []
    for tid in allowed:
        t = tool_map.get(tid)
        if t:
            name = t.get("name_ko") or t.get("name", tid)
            desc = t.get("description", "")[:150]
            descs.append(f"- **{name}**: {desc}")

    if not descs:
        return ""

    return (
        "\n\n## 사용 가능한 전문 도구\n"
        "아래 도구의 기능을 활용하여 더 정확하고 전문적인 답변을 제공하세요.\n"
        + "\n".join(descs)
    )


# ══════════════════════════════════════════════════════════════════
# 프롬프트 / 모델 / 대화 기록
# ══════════════════════════════════════════════════════════════════

def _load_agent_prompt(agent_id: str, *, include_tools: bool = True) -> str:
    """에이전트의 시스템 프롬프트(소울) + 도구 정보를 로드합니다.

    우선순위: DB 오버라이드 > souls/*.md 파일 > agents.yaml system_prompt > 기본값
    """
    prompt = ""

    soul = load_setting(f"soul_{agent_id}")
    if soul:
        prompt = soul
    else:
        soul_path = Path(BASE_DIR).parent / "souls" / "agents" / f"{agent_id}.md"
        if soul_path.exists():
            try:
                prompt = soul_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.debug("소울 파일 읽기 실패 (%s): %s", agent_id, e)

    if not prompt:
        detail = _AGENTS_DETAIL.get(agent_id, {})
        if detail.get("system_prompt"):
            prompt = detail["system_prompt"]

    if not prompt:
        name = _AGENT_NAMES.get(agent_id, _SPECIALIST_NAMES.get(agent_id, agent_id))
        prompt = (
            f"당신은 CORTHEX HQ의 {name}입니다. "
            "CEO의 업무 지시를 받아 처리하고, 명확하고 간결하게 한국어로 답변합니다. "
            "항상 존댓말을 사용하고, 구체적이고 실행 가능한 답변을 제공합니다."
        )

    if include_tools:
        tools_desc = _get_tool_descriptions(agent_id)
        if tools_desc:
            prompt += tools_desc

    return prompt


def _load_chief_prompt() -> None:
    """비서실장 시스템 프롬프트를 로드합니다 (서버 시작 시 캐시)."""
    app_state.chief_prompt = _load_agent_prompt("chief_of_staff")
    _log("[AI] 비서실장 프롬프트 로드 완료")


def _get_model_override(agent_id: str) -> str | None:
    """에이전트에 지정된 모델을 반환합니다.

    우선순위: DB 오버라이드 > agents.yaml > AGENTS 리스트 > 글로벌 오버라이드
    """
    overrides = _load_data("agent_overrides", {})
    if agent_id in overrides and "model_name" in overrides[agent_id]:
        return overrides[agent_id]["model_name"]
    detail = _AGENTS_DETAIL.get(agent_id, {})
    agent_model = detail.get("model_name")
    if agent_model:
        return agent_model
    for a in AGENTS:
        if a["agent_id"] == agent_id and a.get("model_name"):
            return a["model_name"]
    global_override = load_setting("model_override")
    if global_override:
        return global_override
    return None


def _get_agent_reasoning_effort(agent_id: str) -> str:
    """에이전트의 reasoning_effort를 agent_overrides DB → AGENTS 목록 순서로 조회."""
    overrides = _load_data("agent_overrides", {})
    if agent_id in overrides and "reasoning_effort" in overrides[agent_id]:
        return overrides[agent_id]["reasoning_effort"]
    for a in AGENTS:
        if a["agent_id"] == agent_id:
            return a.get("reasoning_effort", "")
    return ""


def _build_conv_history(conversation_id: str | None, current_text: str) -> list | None:
    """대화 세션에서 AI conversation_history를 구성합니다."""
    try:
        if conversation_id:
            recent = load_conversation_messages_by_id(conversation_id, limit=200)
        else:
            recent = load_conversation_messages(limit=100)

        tail = recent[-20:] if len(recent) > 20 else recent
        if not tail:
            return None

        conv_history = []
        for m in tail:
            if m["type"] == "user" and m.get("text"):
                conv_history.append({"role": "user", "content": m["text"][:2000]})
            elif m["type"] == "result" and m.get("content"):
                conv_history.append({"role": "assistant", "content": m["content"][:2000]})

        if (conv_history and conv_history[-1].get("role") == "user"
                and conv_history[-1].get("content", "").strip() == current_text[:2000].strip()):
            conv_history.pop()

        return conv_history if conv_history else None
    except Exception as e:
        logger.debug("대화 기록 로드 실패 (무시): %s", e)
        return None


# ══════════════════════════════════════════════════════════════════
# 에이전트 AI 호출 코어
# ══════════════════════════════════════════════════════════════════

async def _call_agent(agent_id: str, text: str, conversation_id: str | None = None) -> dict:
    """단일 에이전트에게 AI 호출을 수행합니다 (상태 이벤트 + 활동 로그 + 도구 자동호출 포함)."""
    agent_name = _AGENT_NAMES.get(agent_id, _SPECIALIST_NAMES.get(agent_id, agent_id))
    await _broadcast_status(agent_id, "working", 0.1, f"{agent_name} 작업 준비 중...")

    log_entry = save_activity_log(agent_id, f"[{agent_name}] 작업 시작: {text[:40]}...")
    await wm.send_activity_log(log_entry)

    soul = _load_agent_prompt(agent_id)

    # 에이전트 기억 주입 (카테고리별 기억 → system_prompt 앞에 삽입)
    mem = load_setting(f"memory_categorized_{agent_id}", {})
    if mem:
        mem_lines = []
        if mem.get("ceo_preferences"):
            mem_lines.append(f"- CEO 취향/선호: {mem['ceo_preferences']}")
        if mem.get("decisions"):
            mem_lines.append(f"- 주요 결정: {mem['decisions']}")
        if mem.get("warnings"):
            mem_lines.append(f"- 주의사항: {mem['warnings']}")
        if mem.get("context"):
            mem_lines.append(f"- 중요 맥락: {mem['context']}")
        if mem_lines:
            memory_block = "[에이전트 기억]\n" + "\n".join(mem_lines) + "\n\n"
            soul = memory_block + soul

    override = _get_model_override(agent_id)
    model = select_model(text, override=override)

    # 도구 자동호출 (Function Calling)
    tool_schemas = None
    tool_executor_fn = None
    tools_used: list[str] = []
    detail = _AGENTS_DETAIL.get(agent_id, {})
    allowed = detail.get("allowed_tools", [])
    if allowed:
        schemas = _load_tool_schemas(allowed_tools=allowed)
        if schemas.get("anthropic"):
            tool_schemas = schemas["anthropic"]

            _MAX_TOOL_CALLS = int(detail.get("max_tool_calls", 5))

            async def _tool_executor(tool_name: str, tool_input: dict):
                """ToolPool을 통해 도구를 실행합니다."""
                tools_used.append(tool_name)
                call_count = len(tools_used)
                tool_progress = 0.3 + min(call_count / _MAX_TOOL_CALLS, 1.0) * 0.35
                tool_progress_pct = int(tool_progress * 100)

                await wm.send_agent_status(
                    agent_id, "working", round(tool_progress, 2),
                    f"{tool_name} 실행 중...",
                    tool_calls=call_count, max_calls=_MAX_TOOL_CALLS, tool_name=tool_name,
                )

                tool_log = save_activity_log(
                    agent_id, f"🔧 [{agent_name}] {tool_name} 호출 ({call_count}회)",
                    level="tool"
                )
                await wm.send_activity_log(tool_log)

                pool = _init_tool_pool()
                if pool:
                    try:
                        return await pool.invoke(tool_name, caller_id=agent_id, **tool_input)
                    except Exception as e:
                        if "ToolNotFoundError" in type(e).__name__ or tool_name in str(e):
                            return f"도구 '{tool_name}'을(를) 찾을 수 없습니다."
                        raise
                return f"도구 '{tool_name}'을(를) 찾을 수 없습니다."

            tool_executor_fn = _tool_executor

    # 최근 대화 기록 로드
    conv_history = _build_conv_history(conversation_id, text)

    # v5: 에이전트별 cli_owner 확인 (saju 본부 에이전트 → sister 계정)
    _agent_cli_owner = _AGENTS_DETAIL.get(agent_id, {}).get("cli_owner", "ceo")

    await _broadcast_status(agent_id, "working", 0.3, "AI 응답 생성 중...")
    result = await ask_ai(text, system_prompt=soul, model=model,
                          tools=tool_schemas, tool_executor=tool_executor_fn,
                          reasoning_effort=_get_agent_reasoning_effort(agent_id),
                          conversation_history=conv_history,
                          # CLI 모드: Claude 호출을 CLI(Max 구독)로 라우팅
                          use_cli=True,
                          cli_caller_id=agent_id,
                          cli_allowed_tools=allowed,
                          cli_owner=_agent_cli_owner)
    await _broadcast_status(agent_id, "working", 0.7, "응답 처리 중...")

    if "error" in result:
        try:
            from db import save_agent_call
            save_agent_call(
                agent_id=agent_id, model=model or "error",
                provider="", cost_usd=0, input_tokens=0, output_tokens=0, time_seconds=0,
            )
        except Exception:
            pass
        await _broadcast_status(agent_id, "done", 1.0, "오류 발생")
        log_err = save_activity_log(agent_id, f"[{agent_name}] ❌ 오류: {result['error'][:80]}", "warning")
        await wm.send_activity_log(log_err)
        return {"agent_id": agent_id, "name": agent_name, "error": result["error"], "cost_usd": 0}

    # agent_calls 테이블에 AI 호출 기록 저장
    try:
        from db import save_agent_call
        save_agent_call(
            agent_id=agent_id,
            model=result.get("model", model) if isinstance(result, dict) else model,
            provider=result.get("provider", "") if isinstance(result, dict) else "",
            cost_usd=result.get("cost_usd", 0) if isinstance(result, dict) else 0,
            input_tokens=result.get("input_tokens", 0) if isinstance(result, dict) else 0,
            output_tokens=result.get("output_tokens", 0) if isinstance(result, dict) else 0,
            time_seconds=result.get("time_seconds", 0) if isinstance(result, dict) else 0,
        )
    except Exception as e:
        _log(f"[AGENT_CALL] 기록 실패: {e}")

    await _broadcast_status(agent_id, "working", 0.9, "저장 완료...")
    await _broadcast_status(agent_id, "done", 1.0, "완료")

    cost = result.get("cost_usd", 0)
    content = result.get("content", "")
    log_done = save_activity_log(agent_id, f"[{agent_name}] 작업 완료 (${cost:.4f})")
    await wm.send_activity_log(log_done)

    # 비용 업데이트 브로드캐스트
    try:
        today_cost = get_today_cost()
    except Exception:
        today_cost = cost
    await wm.send_cost_update(today_cost)

    # 기억 자동 추출 (비동기 백그라운드)
    if content and len(content) > 30:
        asyncio.create_task(_extract_and_save_memory(agent_id, text, content))

    # 산출물 저장 (노션 + 아카이브 DB)
    if content and len(content) > 20:
        asyncio.create_task(_save_to_notion(
            agent_id=agent_id,
            title=_extract_notion_title(content, f"[{agent_name}] 보고서", user_query=text),
            content=content,
            db_target="secretary" if _AGENT_DIVISION.get(agent_id) == "secretary" else "output",
        ))
        division = _AGENT_DIVISION.get(agent_id, "secretary")
        now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        if tools_used:
            unique_tools = list(dict.fromkeys(tools_used))
            content += f"\n\n---\n🔧 **사용한 도구**: {', '.join(unique_tools)}"

        _title = _extract_notion_title(content, text[:40], user_query=text)
        _safe_title = re.sub(r'[\\/:*?"<>|\n\r]', '', _title)[:30].strip()
        archive_content = f"# [{agent_name}] {_safe_title}\n\n{content}"
        save_archive(
            division=division,
            filename=f"{agent_id}_{_safe_title}_{now_str}.md",
            content=archive_content,
            agent_id=agent_id,
        )

    return {
        "agent_id": agent_id,
        "name": agent_name,
        "content": content,
        "cost_usd": cost,
        "model": result.get("model", ""),
        "time_seconds": result.get("time_seconds", 0),
        "input_tokens": result.get("input_tokens", 0),
        "output_tokens": result.get("output_tokens", 0),
        "tools_used": tools_used,
    }


async def _chief_qa_review(report_content: str, team_leader_name: str) -> tuple[bool, str]:
    """비서실장이 팀장 보고서를 QA합니다. (승인/반려)"""
    if not report_content or len(report_content.strip()) < 50:
        return False, "보고서 내용이 너무 짧습니다 (50자 미만)"

    qa_prompt = f"""당신은 비서실장입니다. {team_leader_name}의 보고서를 검수하세요.

## 보고서
{report_content[:8000]}

## 검수 기준 (5항목, 각 통과/미달)
1. **결론 존재**: 매수/매도/관망 시그널이 명확한가?
2. **근거 제시**: 시그널에 데이터 기반 근거가 있는가? (숫자, 지표)
3. **리스크 언급**: 손절가/최대손실/주의사항이 있는가?
4. **형식 준수**: [시그널] 형식으로 종목별 결과가 있는가?
5. **논리 일관성**: 분석과 결론이 모순되지 않는가?

## 응답 형식 (반드시 첫 줄에 이 형식만)
판정: PASS 또는 FAIL
사유: [1줄 요약]"""

    try:
        soul = _load_agent_prompt("chief_of_staff")
        override = _get_model_override("chief_of_staff")
        model = select_model(qa_prompt, override=override)
        result = await ask_ai(
            qa_prompt,
            system_prompt=soul,
            model=model,
            reasoning_effort=_get_agent_reasoning_effort("chief_of_staff"),
        )
        qa_text = result.get("content", "")

        qa_upper = qa_text.upper()
        if "PASS" in qa_upper and "FAIL" not in qa_upper:
            passed = True
        elif "FAIL" in qa_upper:
            passed = False
        else:
            passed = "승인" in qa_text and "반려" not in qa_text[:200]
        reason = ""
        for line in qa_text.split("\n"):
            if "사유" in line and ":" in line:
                reason = line.split(":", 1)[-1].strip()
                break
        if not reason:
            reason = "승인" if passed else "기준 미달"

        return passed, reason
    except Exception as e:
        logger.warning("비서실장 QA 실패 (기본 승인): %s", e)
        return True, f"QA 시스템 오류로 기본 승인: {str(e)[:60]}"


# ══════════════════════════════════════════════════════════════════
# 팀장 위임 시스템 (CEO 핵심 아이디어: 팀장 = 5번째 분석가)
# ══════════════════════════════════════════════════════════════════

async def _delegate_to_specialists(manager_id: str, text: str) -> list[dict]:
    """팀장이 소속 전문가들에게 병렬로 위임합니다."""
    specialists = _MANAGER_SPECIALISTS.get(manager_id, [])
    if not specialists:
        return []

    try:
        from db import save_delegation_log
        mgr_name = _AGENT_NAMES.get(manager_id, manager_id)
        _deleg_title = _extract_notion_title(text, text[:30])[:40]
        for spec_id in specialists:
            spec_name = _SPECIALIST_NAMES.get(spec_id, spec_id)
            row_id = save_delegation_log(
                sender=mgr_name,
                receiver=spec_name,
                message=text[:500],
                log_type="delegation",
            )
            _log_data = {
                "id": row_id,
                "sender": mgr_name,
                "receiver": spec_name,
                "title": _deleg_title,
                "message": text[:300],
                "log_type": "delegation",
                "created_at": time.time(),
            }
            await wm.send_delegation_log(_log_data)
    except Exception as e:
        logger.debug("위임 로그 브로드캐스트 실패: %s", e)

    tasks = [_call_agent(spec_id, _SPECIALIST_ROLE_PREFIX.get(spec_id, "") + text) for spec_id in specialists]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed = []
    for i, r in enumerate(results):
        spec_id = specialists[i]
        if isinstance(r, Exception):
            processed.append({"agent_id": spec_id, "name": _SPECIALIST_NAMES.get(spec_id, spec_id), "error": str(r)[:100], "cost_usd": 0})
        else:
            try:
                from db import save_delegation_log
                spec_name = _SPECIALIST_NAMES.get(spec_id, spec_id)
                mgr_name = _AGENT_NAMES.get(manager_id, manager_id)
                content_preview = r.get("content", "")[:300] if isinstance(r, dict) else str(r)[:300]
                _tools = r.get("tools_used", []) if isinstance(r, dict) else []
                _tools_unique = list(dict.fromkeys(_tools))[:5]
                _tools_str = ",".join(_tools_unique) if _tools_unique else ""
                _rpt_title = _extract_notion_title(
                    r.get("content", "") if isinstance(r, dict) else str(r),
                    f"{spec_name} 보고", user_query=text
                )[:40]
                row_id = save_delegation_log(
                    sender=spec_name,
                    receiver=mgr_name,
                    message=content_preview,
                    log_type="report",
                    tools_used=_tools_str,
                )
                _log_data = {
                    "id": row_id,
                    "sender": spec_name,
                    "receiver": mgr_name,
                    "title": _rpt_title,
                    "message": content_preview,
                    "log_type": "report",
                    "tools_used": _tools_unique,
                    "created_at": time.time(),
                }
                await wm.send_delegation_log(_log_data)
            except Exception as e:
                logger.debug("보고 로그 브로드캐스트 실패: %s", e)
            processed.append(r)
    return processed


async def _manager_with_delegation(manager_id: str, text: str, conversation_id: str | None = None) -> dict:
    """팀장이 전문가에게 위임 → 결과 종합(검수) → 보고서 작성.

    CEO 핵심 아이디어: 팀장 = 5번째 분석가 (독자분석 + 전문가 병렬)
    """
    mgr_name = _AGENT_NAMES.get(manager_id, manager_id)
    specialists = _MANAGER_SPECIALISTS.get(manager_id, [])
    spec_names = [_SPECIALIST_NAMES.get(s, s) for s in specialists]

    # 전문가가 없으면 팀장이 직접 처리
    if not specialists:
        return await _call_agent(manager_id, text, conversation_id=conversation_id)

    # ── 팀장 독자 분석 함수 (CEO 아이디어: 팀장 = 5번째 분석가) ──
    async def _manager_self_analysis():
        log_self = save_activity_log(manager_id,
            f"[{mgr_name}] 🔧 독자 분석 시작 (5번째 분석가)", "info")
        await wm.send_activity_log(log_self)
        self_prompt = (
            f"당신은 {mgr_name}입니다. 전문가들과 별개로 독자적 분석을 수행하세요.\n"
            f"반드시 도구(API)를 사용하여 실시간 데이터를 직접 조회하고 분석하세요.\n"
            f"전문가 결과는 무시하세요 — 당신만의 독립적 관점을 제시하세요.\n\n"
            f"## 분석 요청\n{text}\n"
        )
        self_result = await _call_agent(manager_id, self_prompt, conversation_id=conversation_id)
        log_done = save_activity_log(manager_id,
            f"[{mgr_name}] ✅ 독자 분석 완료", "info")
        await wm.send_activity_log(log_done)
        return self_result

    await _broadcast_status(manager_id, "working", 0.1, "독자 분석 + 전문가 위임 중...")
    log_mgr = save_activity_log(manager_id,
        f"[{mgr_name}] 🔧 독자 분석 + 전문가 {len(specialists)}명 위임: {', '.join(spec_names)}")
    await wm.send_activity_log(log_mgr)

    # 팀장 독자분석 + 전문가 병렬 실행
    _mgr_self_task = _manager_self_analysis()
    _spec_task = _delegate_to_specialists(manager_id, text)
    _parallel = await asyncio.gather(_mgr_self_task, _spec_task, return_exceptions=True)
    manager_self_result = _parallel[0] if not isinstance(_parallel[0], Exception) else {"error": str(_parallel[0])[:200]}
    spec_results = _parallel[1] if not isinstance(_parallel[1], Exception) else []
    if isinstance(_parallel[1], Exception):
        log_spec_err = save_activity_log(manager_id,
            f"[{mgr_name}] ⚠️ 전문가 위임 실패: {str(_parallel[1])[:100]}", "warning")
        await wm.send_activity_log(log_spec_err)

    # Phase 8: 독자분석 기밀문서 저장
    _p8_div = _MANAGER_DIVISION.get(manager_id, "default")
    _p8_date = datetime.now(KST).strftime("%Y%m%d_%H%M")
    if isinstance(manager_self_result, dict) and "error" not in manager_self_result:
        try:
            save_archive(
                _p8_div,
                f"{mgr_name}_보고서1_독자분석_{_p8_date}.md",
                manager_self_result.get("content", ""),
                agent_id=manager_id,
            )
        except Exception as _ae_p8:
            logger.debug("Phase8 독자분석 기밀문서 저장 실패: %s", _ae_p8)

    # Phase 8: 전문가 보고서 각각 기밀문서 저장
    for _p8r in (spec_results or []):
        if isinstance(_p8r, dict) and "error" not in _p8r:
            _p8_spec_id = _p8r.get("agent_id", "unknown")
            _p8_spec_name = _SPECIALIST_NAMES.get(_p8_spec_id, _p8_spec_id)
            try:
                save_archive(
                    _p8_div,
                    f"{_p8_spec_name}_보고서1_{_p8_date}.md",
                    _p8r.get("content", ""),
                    agent_id=_p8_spec_id,
                )
            except Exception as _ae_p8s:
                logger.debug("Phase8 전문가 기밀문서 저장 실패: %s", _ae_p8s)

    # ── 품질검수 제거됨 (2026-02-27) ──
    if False:  # 품질검수 비활성화
        await _broadcast_status(manager_id, "working", 0.45, "전문가 결과 품질검수 중...")

        _qa_chain = {
            "chain_id": f"trading_{manager_id}_{int(time.time())}",
            "target_id": manager_id,
            "original_command": text[:500],
            "total_cost_usd": 0,
            "results": {"specialists": {}},
        }
        for r in spec_results:
            if "error" not in r:
                _qa_chain["results"]["specialists"][r.get("agent_id", "unknown")] = {
                    "content": r.get("content", ""),
                    "model": r.get("model", ""),
                    "cost_usd": r.get("cost_usd", 0),
                    "tools_used": r.get("tools_used", []),
                }

        _qa_valid_count = len(_qa_chain["results"]["specialists"])
        _qa_error_count = len(spec_results) - _qa_valid_count

        if _qa_valid_count == 0:
            log_err = save_activity_log(manager_id,
                f"[{mgr_name}] ⚠️ 전문가 {_qa_error_count}명 전원 에러 — 품질검수 불가 (유효 보고서 0건)", "warning")
            await wm.send_activity_log(log_err)
        else:
            _qa_note = f" (에러 {_qa_error_count}명 제외)" if _qa_error_count else ""
            log_qa = save_activity_log(manager_id,
                f"[{mgr_name}] 전문가 {_qa_valid_count}명 결과 품질검수 시작{_qa_note}", "info")
            await wm.send_activity_log(log_qa)

        failed_specs = await _quality_review_specialists(_qa_chain) if _qa_valid_count > 0 else []

        if failed_specs:
            for fs in failed_specs:
                _fs_name = _SPECIALIST_NAMES.get(fs["agent_id"], fs["agent_id"])
                log_reject = save_activity_log(manager_id,
                    f"[{mgr_name}] ❌ {_fs_name} 보고서 반려: {fs.get('reason', '품질 미달')[:80]}", "warning")
                await wm.send_activity_log(log_reject)

            await _handle_specialist_rework(_qa_chain, failed_specs)

            for r in spec_results:
                _aid = r.get("agent_id", "unknown")
                if _aid in _qa_chain["results"]["specialists"]:
                    updated = _qa_chain["results"]["specialists"][_aid]
                    r["content"] = updated.get("content", r.get("content", ""))
                    r["cost_usd"] = r.get("cost_usd", 0) + updated.get("cost_usd", 0)
                    if updated.get("rework_attempt"):
                        r["rework_attempt"] = updated["rework_attempt"]
                        log_rework = save_activity_log(_aid,
                            f"[{_SPECIALIST_NAMES.get(_aid, _aid)}] 재작업 완료 (시도 {updated['rework_attempt']}회)")
                        await wm.send_activity_log(log_rework)
                    if updated.get("quality_warning"):
                        r["quality_warning"] = updated["quality_warning"]
                    if updated.get("tools_used"):
                        r["tools_used"] = r.get("tools_used", []) + updated["tools_used"]
        elif _qa_valid_count > 0:
            log_pass = save_activity_log(manager_id,
                f"[{mgr_name}] ✅ 전문가 {_qa_valid_count}명 품질검수 합격", "info")
            await wm.send_activity_log(log_pass)

        _qa_reviews = _qa_chain.get("qa_reviews", [])
        if _qa_reviews:
            try:
                _now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
                _qa_lines = [f"# 품질검수 보고서 — {mgr_name} ({_now_str})\n"]
                _qa_lines.append(f"검수 대상: {_qa_valid_count}명 | 불합격: {len(failed_specs)}명\n")
                for qr in _qa_reviews:
                    _qr_name = _SPECIALIST_NAMES.get(qr["agent_id"], qr["agent_id"])
                    _qr_pass = "✅ 합격" if qr["passed"] else "❌ 불합격"
                    _qa_lines.append(f"## {_qr_name} — {qr['weighted_average']:.1f}점 {_qr_pass}\n")
                    _rd = qr.get("review_dict", {})
                    for ci in _rd.get("checklist", []):
                        _st = "✅" if ci["passed"] else "❌"
                        _rq = " [필수]" if ci.get("required") else ""
                        _fb = f" — {ci['feedback']}" if ci.get("feedback") and not ci["passed"] else ""
                        _qa_lines.append(f"- 📋 {ci['id']} {ci.get('label','')}: {_st}{_rq}{_fb}")
                    for si in _rd.get("scores", []):
                        _cr = " ⚠️치명적" if si.get("critical") and si["score"] == 1 else ""
                        _fb = f" — {si['feedback']}" if si.get("feedback") and si["score"] <= 3 else ""
                        _qa_lines.append(f"- 📊 {si['id']} {si.get('label','')}: {si['score']}점/5 (가중 {si.get('weight',0)}%){_cr}{_fb}")
                    _rej = _rd.get("rejection_reasons", [])
                    if _rej:
                        _qa_lines.append(f"\n**반려 사유**: {' / '.join(_rej)}")
                    _qa_lines.append("")
                _qa_content = "\n".join(_qa_lines)
                _qa_filename = f"QA_{mgr_name}_{datetime.now(KST).strftime('%Y%m%d_%H%M')}.md"
                _division = _MANAGER_DIVISION.get(manager_id, "default")
                save_archive(
                    division=_division,
                    filename=_qa_filename,
                    content=_qa_content,
                    correlation_id=_qa_chain.get("chain_id", ""),
                    agent_id=manager_id,
                )
                _log(f"[QA] 품질검수 보고서 기밀문서 저장: {_qa_filename}")
            except Exception as e:
                _log(f"[QA] 기밀문서 저장 실패: {e}")

    # 전문가 결과 취합
    spec_parts = []
    spec_cost = 0.0
    spec_time = 0.0
    for r in spec_results:
        name = r.get("name", r.get("agent_id", "?"))
        if "error" in r:
            spec_parts.append(f"[{name}] 오류: {r['error'][:80]}")
        else:
            spec_parts.append(f"[{name}]\n{r.get('content', '응답 없음')}")
            spec_cost += r.get("cost_usd", 0)
            spec_time = max(spec_time, r.get("time_seconds", 0))

    # 팀장 독자분석 결과 취합
    manager_self_content = ""
    mgr_self_tools: list[str] = []
    if isinstance(manager_self_result, dict) and "error" not in manager_self_result:
        manager_self_content = manager_self_result.get("content", "")
        mgr_self_tools = manager_self_result.get("tools_used", [])
        spec_cost += manager_self_result.get("cost_usd", 0)
        spec_time = max(spec_time, manager_self_result.get("time_seconds", 0))

    _spec_ok_count = len([r for r in spec_results if "error" not in r])
    _spec_err_count = len(spec_results) - _spec_ok_count

    synthesis_prompt = (
        f"당신은 {mgr_name}입니다.\n"
        f"아래 분석 결과(당신의 독자 분석 + 전문가)를 종합하여 최종 보고서를 작성하세요.\n"
        f"도구를 다시 사용할 필요 없습니다 — 결과를 취합만 하세요.\n\n"
        f"## CEO 원본 명령\n{text}\n\n"
        f"## 팀장 독자 분석\n{manager_self_content or '(분석 실패)'}\n\n"
        f"## 전문가 분석 결과\n" + "\n\n".join(spec_parts)
    )

    soul = _load_agent_prompt(manager_id)
    override = _get_model_override(manager_id)
    model = select_model(synthesis_prompt, override=override)

    await _broadcast_status(manager_id, "working", 0.7, "독자분석 + 전문가 결과 종합 중...")
    synthesis = await ask_ai(synthesis_prompt, system_prompt=soul, model=model,
                             tools=None, tool_executor=None,
                             reasoning_effort=_get_agent_reasoning_effort(manager_id))

    await _broadcast_status(manager_id, "done", 1.0, "보고 완료")

    if "error" in synthesis:
        _spec_ok = len([r for r in spec_results if "error" not in r])
        content = f"**{mgr_name} 독자 분석**\n\n{manager_self_content or '(분석 실패)'}\n\n---\n\n**전문가 분석 결과**\n\n" + "\n\n---\n\n".join(spec_parts)
        _all_spec_tools = [t for r in spec_results if isinstance(r, dict) and "error" not in r for t in r.get("tools_used", [])]
        return {"agent_id": manager_id, "name": mgr_name, "content": content, "cost_usd": spec_cost, "specialists_used": _spec_ok, "tools_used": mgr_self_tools + _all_spec_tools}

    total_cost = spec_cost + synthesis.get("cost_usd", 0)
    specialists_used = len([r for r in spec_results if "error" not in r])
    synth_content = synthesis.get("content", "")

    # 전문가 개별 산출물 노션 저장
    for r in spec_results:
        if "error" not in r and r.get("content") and len(r["content"]) > 20:
            _sid = r.get("agent_id", "unknown")
            _sname = r.get("name", _sid)
            asyncio.create_task(_save_to_notion(
                agent_id=_sid,
                title=_extract_notion_title(r["content"], f"[{_sname}] 분석보고", user_query=text),
                content=r["content"],
                report_type="전문가보고서",
                db_target="output",
            ))

    # 종합 보고서 저장 (노션 + 아카이브)
    if synth_content and len(synth_content) > 20:
        asyncio.create_task(_save_to_notion(
            agent_id=manager_id,
            title=_extract_notion_title(synth_content, f"[{mgr_name}] 종합보고", user_query=text),
            content=synth_content,
            report_type="종합보고서",
            db_target="secretary" if _AGENT_DIVISION.get(manager_id) == "secretary" else "output",
        ))
        division = _AGENT_DIVISION.get(manager_id, "secretary")
        now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        _synth_title = _extract_notion_title(synth_content, text[:40], user_query=text)
        _safe_synth = re.sub(r'[\\/:*?"<>|\n\r]', '', _synth_title)[:30].strip()
        archive_content = f"# [{mgr_name}] 종합보고: {_safe_synth}\n\n{synth_content}"
        save_archive(
            division=division,
            filename=f"{manager_id}_{_safe_synth}_{now_str}.md",
            content=archive_content,
            agent_id=manager_id,
        )

    if mgr_self_tools:
        _unique_self = list(dict.fromkeys(mgr_self_tools))
        log_tools = save_activity_log(manager_id,
            f"[{mgr_name}] 🔧 독자 분석 도구 {len(mgr_self_tools)}건 사용 (고유 {len(_unique_self)}개): {', '.join(_unique_self[:5])}", "tool")
        await wm.send_activity_log(log_tools)

    return {
        "agent_id": manager_id,
        "name": mgr_name,
        "content": synth_content,
        "cost_usd": total_cost,
        "model": synthesis.get("model", ""),
        "time_seconds": round(spec_time + synthesis.get("time_seconds", 0), 2),
        "specialists_used": specialists_used,
        "tools_used": mgr_self_tools,
    }


def _determine_routing_level(text: str) -> tuple[int, str | None]:
    """질문 복잡도에 따라 Level 1~4와 대상 팀장 ID 반환."""
    t = text.lower()

    SIMPLE_KEYWORDS = ["안녕", "안녕하세요", "고마워", "감사합니다", "일정", "뭐야",
                       "언제야", "뭔가요", "알려줘", "찾아줘", "확인해줘"]
    if len(text) < 50 and any(k in t for k in SIMPLE_KEYWORDS):
        return (1, None)

    MANAGER_KEYWORDS = {
        "cto_manager": ["기술", "개발", "코드", "api", "서버", "앱", "웹", "프론트", "백엔드", "인프라", "ai 모델", "데이터베이스"],
        "leet_strategist": ["사업", "시장", "재무", "전략", "비즈니스", "계획", "수익", "매출", "투자 계획"],
        "leet_legal": ["법", "계약", "저작권", "특허", "약관", "법률", "ip"],
        "leet_marketer": ["마케팅", "고객", "콘텐츠", "sns", "광고", "커뮤니티", "브랜딩"],
        "fin_analyst": ["투자", "주식", "코스피", "시황", "종목", "리스크", "포트폴리오", "etf", "채권"],
        "leet_publisher": ["기록", "출판", "블로그", "연대기", "회고", "편집", "아카이브"],
    }

    matched_manager = None
    for mgr_id, keywords in MANAGER_KEYWORDS.items():
        if any(k in t for k in keywords):
            matched_manager = mgr_id
            break

    if matched_manager:
        DEEP_KEYWORDS = ["분석", "보고서", "전략", "계획서", "검토", "평가", "비교", "예측", "전망"]
        if any(k in t for k in DEEP_KEYWORDS):
            return (3, matched_manager)
        return (2, matched_manager)

    return (4, None)


async def _manager_with_delegation_autonomous(manager_id: str, text: str, conversation_id: str | None = None) -> dict:
    """팀장이 spawn_agent 도구로 필요한 전문가만 자율 선택하여 호출 (Level 3용)."""
    agent_cfg = next((a for a in AGENTS if a.get("agent_id") == manager_id), None)
    if not agent_cfg:
        return {"content": f"에이전트 설정을 찾을 수 없습니다: {manager_id}", "error": True}

    soul = _load_agent_prompt(manager_id)
    specialists_pool = _MANAGER_SPECIALISTS.get(manager_id, [])

    spawn_tool = {
        "name": "spawn_agent",
        "description": (
            f"소속 전문가를 호출하여 특정 분석을 수행합니다. "
            f"사용 가능한 전문가 ID: {', '.join(specialists_pool)}"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "호출할 전문가 에이전트 ID", "enum": specialists_pool},
                "task": {"type": "string", "description": "전문가에게 지시할 구체적인 작업 내용"},
            },
            "required": ["agent_id", "task"]
        }
    }

    specialist_results: dict[str, str] = {}

    async def _spawn_executor(tool_name: str, tool_input: dict) -> str:
        if tool_name == "spawn_agent":
            sid = tool_input.get("agent_id", "")
            task = tool_input.get("task", "")
            if sid in specialists_pool:
                logger.info("spawn_agent: %s → %s", manager_id, sid)
                await _broadcast_status(manager_id, "working", 0.5, f"전문가 {_SPECIALIST_NAMES.get(sid, sid)} 호출 중...")
                result = await _call_agent(sid, task, conversation_id=conversation_id)
                content = result.get("content", "")
                specialist_results[sid] = content
                return content
        return "알 수 없는 도구입니다."

    mgr_name = _AGENT_NAMES.get(manager_id, manager_id)
    await _broadcast_status(manager_id, "working", 0.2, f"{mgr_name} 분석 중 (자율 전문가 선택)...")

    override = _get_model_override(manager_id)
    model = select_model(text, override=override)

    result = await ask_ai(text, system_prompt=soul, model=model,
                          tools=[spawn_tool], tool_executor=_spawn_executor)

    await _broadcast_status(manager_id, "done", 1.0, "보고 완료")

    return {
        "content": result.get("content", ""),
        "specialist_results": specialist_results,
        "manager_id": manager_id,
        "cost_usd": result.get("cost_usd", 0),
        "time_seconds": result.get("time_seconds", 0),
    }


async def _chief_finalize(original_text: str, manager_results: dict) -> dict:
    """Level 2/3 완료 후 비서실장이 최종 보고서 1개 작성."""
    chief_cfg = next((a for a in AGENTS if a.get("agent_id") == "chief_of_staff"), None)
    if not chief_cfg:
        combined = "\n\n".join(r.get("content", "") for r in manager_results.values())
        return {"content": combined}

    results_text = "\n\n".join(
        f"[{mgr_id} 보고]\n{res.get('content', '')}"
        for mgr_id, res in manager_results.items()
    )

    synthesis_prompt = (
        f"CEO 질문: {original_text}\n\n"
        f"팀장 보고 내용:\n{results_text}\n\n"
        "위 내용을 바탕으로 CEO에게 드릴 최종 보고서를 작성하세요. "
        "핵심 결론을 먼저, 세부 내용을 뒤에 정리하세요."
    )

    soul = _load_agent_prompt("chief_of_staff")
    override = _get_model_override("chief_of_staff")
    model = select_model(synthesis_prompt, override=override)

    result = await ask_ai(synthesis_prompt, system_prompt=soul, model=model)

    return {"content": result.get("content", ""), "routing_level": "finalized", "cost_usd": result.get("cost_usd", 0)}


# ══════════════════════════════════════════════════════════════════
# 브로드캐스트 / 토론 / 순차 협업
# ══════════════════════════════════════════════════════════════════

async def _broadcast_to_managers_all(text: str, task_id: str, conversation_id: str | None = None) -> dict:
    """Level 4: 활성 팀장 병렬 호출 (브로드캐스트)."""
    managers = [m for m in ["leet_strategist", "leet_legal", "leet_marketer", "fin_analyst", "leet_publisher"]
                if m not in _DORMANT_MANAGERS]
    staff_specialists = []

    await _broadcast_status("chief_of_staff", "working", 0.1, f"{len(managers)}개 부서 팀장에게 명령 하달 중...")

    log_entry = save_activity_log("chief_of_staff", f"[비서실장] {len(managers)}개 팀장에게 명령 전달: {text[:40]}...")
    await wm.send_activity_log(log_entry)

    mgr_tasks = [_manager_with_delegation(mgr_id, text, conversation_id=conversation_id) for mgr_id in managers]
    staff_tasks = [_call_agent(spec_id, text, conversation_id=conversation_id) for spec_id in staff_specialists]
    all_results = await asyncio.gather(*(mgr_tasks + staff_tasks), return_exceptions=True)

    mgr_results = all_results[:len(managers)]
    staff_results = all_results[len(managers):]

    mgr_summaries = []
    total_cost = 0.0
    total_time = 0.0
    success_count = 0
    total_specialists = 0

    for i, result in enumerate(mgr_results):
        mgr_id = managers[i]
        mgr_name = _AGENT_NAMES.get(mgr_id, mgr_id)

        if isinstance(result, Exception):
            mgr_summaries.append(f"[{mgr_name}] 오류: {str(result)[:100]}")
        elif "error" in result:
            mgr_summaries.append(f"[{mgr_name}] 오류: {result['error'][:200]}")
        else:
            specs = result.get("specialists_used", 0)
            total_specialists += specs
            mgr_summaries.append(f"[{mgr_name}] (전문가 {specs}명)\n{result.get('content', '응답 없음')}")
            total_cost += result.get("cost_usd", 0)
            total_time = max(total_time, result.get("time_seconds", 0))
            success_count += 1

    staff_summaries = []
    for i, result in enumerate(staff_results):
        spec_id = staff_specialists[i]
        spec_name = _SPECIALIST_NAMES.get(spec_id, spec_id)

        if isinstance(result, Exception):
            staff_summaries.append(f"[{spec_name}] 오류: {str(result)[:100]}")
        elif "error" in result:
            staff_summaries.append(f"[{spec_name}] 오류: {result['error'][:200]}")
        else:
            staff_summaries.append(f"[{spec_name}]\n{result.get('content', '응답 없음')}")
            total_cost += result.get("cost_usd", 0)
            total_time = max(total_time, result.get("time_seconds", 0))

    # 비서실장 종합 보고서 작성
    await _broadcast_status("chief_of_staff", "working", 0.8, "종합 보고서 작성 중...")

    synthesis_input = (
        f"CEO 원본 명령: {text}\n\n"
        f"## 6개 부서 팀장 보고서\n\n"
        + "\n\n---\n\n".join(mgr_summaries)
        + f"\n\n## 비서실 보좌관 보고\n\n"
        + "\n\n".join(staff_summaries)
    )

    synthesis_system = (
        "당신은 비서실장입니다. 6개 부서 팀장과 비서실 보좌관 3명의 보고를 검토하고, "
        "CEO에게 종합 보고서를 작성하세요.\n\n"
        "## 반드시 아래 구조를 따를 것\n\n"
        "### 핵심 요약\n(전체 상황을 1~2문장으로 요약)\n\n"
        "### 부서별 한줄 요약\n| 부서 | 핵심 내용 | 상태 |\n|------|----------|------|\n"
        "| CTO (기술개발) | ... | 정상/주의/위험 |\n(6개 부서 전부)\n\n"
        "### CEO 결재/결정 필요 사항\n"
        "(각 팀장 보고서에서 CEO가 결정해야 할 것만 추출. 체크리스트 형태)\n"
        "- [ ] 부서명: 결정 사항 — 배경 설명\n"
        "(결재할 것이 없으면 '현재 결재 대기 사항 없음')\n\n"
        "### 특이사항 / 리스크\n(각 보고서에서 리스크 요소만 추출. 없으면 '특이사항 없음')\n\n"
        "### 비서실 보좌관 보고\n- 기록 보좌관: (1줄 요약)\n"
        "- 일정 보좌관: (1줄 요약)\n- 소통 보좌관: (1줄 요약)\n\n"
        "## 규칙\n- 한국어로 작성\n- 간결하게. CEO가 30초 안에 핵심을 파악할 수 있게\n"
        "- 중요한 숫자/데이터는 반드시 포함\n- 팀장 보고서를 그대로 복사하지 말고, 핵심만 추출하여 재구성\n"
    )

    soul = _load_agent_prompt("chief_of_staff")
    override = _get_model_override("chief_of_staff")
    model = select_model(synthesis_input, override=override)

    chief_synthesis = await ask_ai(
        synthesis_input,
        system_prompt=synthesis_system + "\n\n" + soul,
        model=model,
    )

    await _broadcast_status("chief_of_staff", "done", 1.0, "종합 보고 완료")

    if "error" not in chief_synthesis:
        total_cost += chief_synthesis.get("cost_usd", 0)

    if "error" in chief_synthesis:
        chief_content = "⚠️ 비서실장 종합 보고서 작성 실패\n\n" + "\n\n---\n\n".join(
            f"**{_AGENT_NAMES.get(managers[i], managers[i])}**: "
            + (mgr_results[i].get("content", "")[:100] + "..." if not isinstance(mgr_results[i], Exception) else "오류")
            for i in range(len(managers))
        )
    else:
        chief_content = chief_synthesis.get("content", "")

    final_content = (
        f"📋 **비서실장 종합 보고** "
        f"(6개 팀장 + 전문가 {total_specialists}명 + 보좌관 3명 동원)\n\n"
        f"{chief_content}\n\n"
        f"---\n\n"
        f"📂 **상세 보고서 {success_count}건이 기밀문서에 저장되었습니다.** "
        f"기밀문서 탭에서 부서별 필터로 각 팀장의 전체 보고서를 확인할 수 있습니다."
    )

    now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    save_archive(
        division="secretary",
        filename=f"chief_of_staff_broadcast_{now_str}.md",
        content=f"# [비서실장] 종합 보고: {text[:50]}\n\n{chief_content}",
        agent_id="chief_of_staff",
    )

    update_task(task_id, status="completed",
                result_summary=f"브로드캐스트 완료 ({success_count}/{len(managers)} 부서, 전문가 {total_specialists}명, 보좌관 3명)",
                result_data=final_content,
                success=1,
                cost_usd=total_cost,
                time_seconds=round(total_time, 2),
                agent_id="chief_of_staff")

    return {
        "content": final_content,
        "agent_id": "chief_of_staff",
        "handled_by": "비서실장 → 6개 팀장 + 보좌관 3명",
        "delegation": "비서실장 → 팀장 → 전문가",
        "total_cost_usd": round(total_cost, 6),
        "time_seconds": round(total_time, 2),
        "model": "multi-agent",
        "routing_method": "브로드캐스트",
    }


async def _call_agent_debate(agent_id: str, topic: str, history: str, extra_instruction: str) -> str:
    """토론용 에이전트 호출."""
    prompt = (
        f"[임원 토론 모드]\n"
        f"지금은 CEO가 소집한 임원 토론입니다. 보고서가 아니라 \"토론 발언\"으로 답하세요.\n"
        f"형식적인 보고서 틀(## 팀장 의견, ## 팀원 보고서 요약 등)은 사용하지 마세요.\n"
        f"대신 당신의 핵심 주장을 명확히 밝히고, 근거를 들어 설득하세요.\n\n"
        f"[토론 주제]\n{topic}\n\n"
        f"[이전 발언들]\n{history if history else '(첫 발언입니다. 다른 팀장의 의견 없이 독립적으로 발언하세요.)'}\n\n"
        f"{extra_instruction}"
    )
    result = await _call_agent(agent_id, prompt)
    return result.get("content", str(result)) if isinstance(result, dict) else str(result)


async def _broadcast_with_debate(ceo_message: str, rounds: int = 2) -> dict:
    """임원 회의 방식 토론 — CEO 메시지를 팀장들이 다단계 토론 후 비서실장이 종합."""
    debate_history = ""

    all_managers = ["fin_analyst", "cto_manager", "leet_strategist", "leet_marketer", "leet_legal", "leet_publisher"]
    manager_ids = [m for m in all_managers if m in _AGENTS_DETAIL]

    for round_num in range(1, rounds + 1):
        rotation_idx = (round_num - 1) % len(DEBATE_ROTATION)
        ordered_managers = [m for m in DEBATE_ROTATION[rotation_idx] if m in manager_ids]

        if round_num == 1:
            tasks = []
            for mid in ordered_managers:
                lens = _DEBATE_LENSES.get(mid, "당신의 전문 분야 관점에서 구체적으로 분석하세요.")
                r1_instruction = (
                    f"\n\n[1라운드 — 독립 의견 제시]\n"
                    f"{lens}\n\n"
                    f"[발언 규칙]\n"
                    f"- 결론을 먼저 한 문장으로 제시한 뒤 근거를 대세요\n"
                    f"- \"~할 수 있다\", \"~이 좋을 것이다\" 같은 모호한 표현 금지. 구체적 수치, 사례, 기한을 넣으세요\n"
                    f"- CEO가 의사결정할 수 있는 정보를 주세요. 교과서 내용 복붙이 아니라 이 상황에 맞는 판단을 하세요\n"
                    f"- 300자 이상 800자 이하로 핵심만"
                )
                tasks.append(_call_agent_debate(mid, ceo_message, "", r1_instruction))
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for mid, resp in zip(ordered_managers, responses):
                if not isinstance(resp, Exception):
                    mgr_name = _AGENT_NAMES.get(mid, mid)
                    debate_history += f"\n[{mgr_name}의 1라운드 의견]\n{resp}\n"
        else:
            rebuttal_instruction = (
                f"\n\n[{round_num}라운드 — 반박 및 보강]\n"
                "위 발언들을 읽고 아래 3가지를 반드시 수행하세요:\n\n"
                "1. **반박**: 다른 팀장 의견 중 가장 취약한 논리나 빠진 관점을 구체적으로 지적하세요.\n"
                "   - 누구의 어떤 주장이 왜 틀렸거나 부족한지 이름을 거론하여 명확히 밝히세요.\n"
                "   - \"일리 있지만\"으로 시작하는 빈 양보 표현 금지.\n\n"
                "2. **새로운 정보 추가**: 1라운드에서 아무도 언급하지 않은 새로운 관점, 데이터, 리스크를 하나 이상 제시하세요.\n\n"
                "3. **입장 표명**: 이 주제에 대한 당신의 최종 입장을 한 문장으로 명확히 밝히세요.\n"
                "   찬성/반대/조건부 찬성 중 하나를 선택하고 그 이유를 대세요.\n\n"
                "- '동의합니다', '좋은 의견입니다', '각 팀장의 의견을 존중합니다' 같은 빈 동의/예의 표현은 절대 금지\n"
                "- 300자 이상 800자 이하로 핵심만"
            )
            for mid in ordered_managers:
                mgr_name = _AGENT_NAMES.get(mid, mid)
                resp = await _call_agent_debate(mid, ceo_message, debate_history, rebuttal_instruction)
                debate_history += f"\n[{mgr_name}의 {round_num}라운드 발언]\n{resp}\n"

    # 비서실장 토론 종합
    synthesis_prompt = (
        f"[임원 토론 종합 보고]\n\n"
        f"[토론 주제]\n{ceo_message}\n\n"
        f"[팀장들의 토론 내용]\n{debate_history}\n\n"
        "위 토론을 바탕으로 CEO에게 보고하세요. 아래 형식을 따르세요:\n\n"
        "## 한줄 결론\n(이 토론의 결론을 CEO가 즉시 이해할 수 있는 한 문장으로)\n\n"
        "## 핵심 쟁점 (팀장 간 실제로 대립한 것만)\n"
        "| 쟁점 | 찬성 측 | 반대 측 | 판정 |\n"
        "(형식적으로 이견이 없는 항목은 제외. 실제 의견 충돌만 기록)\n\n"
        "## 전원 합의 사항\n(팀장들이 실제로 공통 동의한 핵심 포인트만. 없으면 '없음')\n\n"
        "## CEO 결정 필요 사항\n(CEO가 결정해야 할 구체적 선택지를 A/B 형태로 제시. 각 선택지의 장단점 1줄씩)\n\n"
        "## 비서실장 권고\n(당신의 판단으로 어떤 방향이 나은지, 그 이유와 함께)"
    )

    final_result = await _call_agent("chief_of_staff", synthesis_prompt)
    final_content = final_result.get("content", str(final_result)) if isinstance(final_result, dict) else str(final_result)

    return {
        "content": (
            f"## 임원 토론 결과 ({rounds}라운드)\n\n"
            f"{final_content}\n\n"
            f"---\n\n"
            f"<details><summary>전체 토론 내역 보기</summary>\n\n{debate_history}\n</details>"
        ),
        "debate_rounds": rounds,
        "participants": manager_ids,
        "agent_id": "chief_of_staff",
        "handled_by": f"임원 토론 ({rounds}라운드, {len(manager_ids)}명 참여)",
    }


async def _broadcast_to_managers(text: str, task_id: str, target_agent_id: str | None = None, conversation_id: str | None = None) -> dict:
    """스마트 라우팅: Level에 따라 적절한 에이전트만 호출."""
    if target_agent_id:
        logger.info("CEO 직접 개입: → %s", target_agent_id)
        return await _call_agent(target_agent_id, text, conversation_id=conversation_id)

    level, manager_id = _determine_routing_level(text)
    logger.info("스마트 라우팅 Level %d, 팀장: %s", level, manager_id)

    if level == 1:
        return await _call_agent("chief_of_staff", text, conversation_id=conversation_id)
    elif level == 2:
        mgr_result = await _call_agent(manager_id, text, conversation_id=conversation_id)
        return await _chief_finalize(text, {manager_id: mgr_result})
    elif level == 3:
        mgr_result = await _manager_with_delegation_autonomous(manager_id, text, conversation_id=conversation_id)
        return await _chief_finalize(text, {manager_id: mgr_result})
    else:
        return await _broadcast_to_managers_all(text, task_id, conversation_id=conversation_id)


async def _sequential_collaboration(text: str, task_id: str, agent_order: list[str] | None = None) -> dict:
    """에이전트 간 순차 협업."""
    await _broadcast_status("chief_of_staff", "working", 0.1, "순차 협업 계획 수립 중...")

    if not agent_order:
        order_prompt = (
            f"CEO 명령: {text}\n\n"
            "이 작업을 처리하기 위해 어떤 부서가 어떤 순서로 작업해야 하는지 결정하세요.\n"
            "가능한 부서: cto_manager(기술), leet_strategist(사업), leet_legal(법무), "
            "leet_marketer(마케팅), fin_analyst(투자), leet_publisher(기획)\n\n"
            "JSON 형식으로 답변:\n"
            '{"order": ["첫번째_agent_id", "두번째_agent_id"], "reason": "이유"}\n'
            "최소 2개, 최대 4개 부서만 선택하세요. 관련 없는 부서는 제외."
        )
        soul = _load_agent_prompt("chief_of_staff")
        override = _get_model_override("chief_of_staff")
        model = select_model(order_prompt, override=override)
        plan_result = await ask_ai(order_prompt, system_prompt=soul, model=model)

        if "error" not in plan_result:
            try:
                raw = plan_result.get("content", "")
                if "```" in raw:
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                parsed = json.loads(raw)
                agent_order = parsed.get("order", [])
            except (json.JSONDecodeError, IndexError):
                pass

        if not agent_order:
            agent_order = ["cto_manager", "leet_strategist"]

    valid_agents = set(_AGENT_NAMES.keys())
    agent_order = [a for a in agent_order if a in valid_agents]
    if not agent_order:
        agent_order = ["chief_of_staff"]

    chain_context = f"CEO 원본 명령: {text}"
    results = []
    total_cost = 0.0
    total_time = 0.0

    for i, agent_id in enumerate(agent_order):
        agent_name = _AGENT_NAMES.get(agent_id, agent_id)
        step_label = f"[{i+1}/{len(agent_order)}]"

        await _broadcast_status("chief_of_staff", "working", (i + 0.5) / len(agent_order),
                                f"순차 협업 {step_label} {agent_name} 작업 중...")

        if i == 0:
            agent_input = text
        else:
            prev_results = "\n\n".join(
                f"[{r['name']}의 작업 결과]\n{r['content'][:500]}"
                for r in results
            )
            agent_input = (
                f"{text}\n\n"
                f"## 이전 단계 작업 결과 (참고하여 작업하세요)\n{prev_results}"
            )

        result = await _manager_with_delegation(agent_id, agent_input)

        if isinstance(result, Exception):
            results.append({"agent_id": agent_id, "name": agent_name, "content": f"오류: {result}", "cost_usd": 0})
        elif "error" in result:
            results.append({"agent_id": agent_id, "name": agent_name, "content": f"오류: {result['error']}", "cost_usd": 0})
        else:
            results.append(result)
            total_cost += result.get("cost_usd", 0)
            total_time += result.get("time_seconds", 0)

    await _broadcast_status("chief_of_staff", "working", 0.9, "순차 협업 종합 보고서 작성 중...")

    chain_summary = "\n\n---\n\n".join(
        f"### {i+1}단계: {r.get('name', r.get('agent_id', '?'))}\n{r.get('content', '결과 없음')}"
        for i, r in enumerate(results)
    )

    synthesis_prompt = (
        f"CEO 명령: {text}\n\n"
        f"아래는 {len(results)}개 부서가 순차적으로 작업한 결과입니다.\n"
        f"이전 단계의 결과를 다음 단계가 참고하여 작업했습니다.\n\n"
        f"{chain_summary}\n\n"
        f"위 순차 협업 결과를 종합하여 CEO에게 간결한 최종 보고서를 작성하세요."
    )

    soul = _load_agent_prompt("chief_of_staff")
    override = _get_model_override("chief_of_staff")
    model = select_model(synthesis_prompt, override=override)
    synthesis = await ask_ai(synthesis_prompt, system_prompt=soul, model=model)

    await _broadcast_status("chief_of_staff", "done", 1.0, "순차 협업 완료")

    if "error" in synthesis:
        chief_content = f"⚠️ 종합 보고서 작성 실패\n\n{chain_summary}"
    else:
        chief_content = synthesis.get("content", "")
        total_cost += synthesis.get("cost_usd", 0)

    order_names = " → ".join(_AGENT_NAMES.get(a, a) for a in agent_order)
    final_content = (
        f"🔗 **순차 협업 보고** ({order_names})\n\n"
        f"{chief_content}\n\n---\n\n"
        f"📂 상세 보고서 {len(results)}건이 기밀문서에 저장되었습니다."
    )

    now_str = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    save_archive(
        division="secretary",
        filename=f"sequential_collab_{now_str}.md",
        content=f"# [순차 협업] {text[:50]}\n\n작업 순서: {order_names}\n\n{chain_summary}",
        agent_id="chief_of_staff",
    )

    update_task(task_id, status="completed",
                result_summary=f"순차 협업 완료 ({order_names})",
                result_data=final_content,
                success=1, cost_usd=total_cost,
                time_seconds=round(total_time, 2),
                agent_id="chief_of_staff")

    return {
        "content": final_content,
        "agent_id": "chief_of_staff",
        "handled_by": f"비서실장 → {order_names}",
        "delegation": f"순차 협업: {order_names}",
        "total_cost_usd": round(total_cost, 6),
        "time_seconds": round(total_time, 2),
        "model": "multi-agent-sequential",
        "routing_method": "순차 협업",
    }


# ══════════════════════════════════════════════════════════════════
# 최상위 라우팅 + ToolPool
# ══════════════════════════════════════════════════════════════════

async def _process_ai_command(text: str, task_id: str, target_agent_id: str | None = None,
                              conversation_id: str | None = None,
                              session_role: str = "ceo") -> dict:
    """CEO/Sister 명령을 적합한 에이전트에게 위임하고 AI 결과를 반환합니다."""
    # 1) 예산 확인
    limit = float(load_setting("daily_budget_usd") or 7.0)
    today = get_today_cost()
    if today >= limit:
        update_task(task_id, status="failed",
                    result_summary=f"일일 예산 초과 (${today:.2f}/${limit:.0f})",
                    success=0)
        return {"error": f"일일 예산을 초과했습니다 (${today:.2f}/${limit:.0f})"}

    # ── 슬래시 명령어 시스템 ──
    text_lower = text.strip().lower()
    text_stripped = text.strip()

    if text_lower in ("/명령어", "/도움말", "/help", "/commands"):
        content = (
            "📋 **사용 가능한 명령어**\n\n"
            "| 명령어 | 설명 |\n"
            "|--------|------|\n"
            "| `/토론 [주제]` | 임원 토론 (2라운드: 독립 의견 → 재반박) |\n"
            "| `/심층토론 [주제]` | 심층 임원 토론 (3라운드: 더 깊은 반박) |\n"
            "| `/전체 [메시지]` | 29명 에이전트 동시 가동 (브로드캐스트) |\n"
            "| `/순차 [메시지]` | 에이전트 릴레이 (순서대로 작업) |\n"
            f"| `/도구점검` | {len(_TOOLS_LIST)}개 도구 상태 점검 |\n"
            "| `/배치실행` | 대기 중인 배치 작업 실행 |\n"
            "| `/배치상태` | 배치 처리 현황 |\n"
            "| `/명령어` | 이 도움말 |\n\n"
            "**일반 메시지**는 비서실장이 자동으로 적합한 부서에 위임합니다."
        )
        update_task(task_id, status="completed", result_summary=content[:500], success=1)
        return {"content": content, "handled_by": "비서실장", "agent_id": "chief_of_staff"}

    if text_stripped.startswith("/토론"):
        topic = text_stripped[len("/토론"):].strip() or "CORTHEX 전략 방향"
        result = await _broadcast_with_debate(topic, rounds=2)
        update_task(task_id, status="completed", result_summary="임원 토론 완료 (2라운드)", success=1)
        result["handled_by"] = result.get("handled_by", "임원 토론")
        return result

    if text_stripped.startswith("/심층토론"):
        topic = text_stripped[len("/심층토론"):].strip() or "CORTHEX 전략 방향"
        result = await _broadcast_with_debate(topic, rounds=3)
        update_task(task_id, status="completed", result_summary="심층 임원 토론 완료 (3라운드)", success=1)
        result["handled_by"] = result.get("handled_by", "심층 임원 토론")
        return result

    if text_stripped.startswith("/전체"):
        broadcast_text = text_stripped[len("/전체"):].strip()
        if not broadcast_text:
            broadcast_text = "전체 출석 보고"
        return await _broadcast_to_managers_all(broadcast_text, task_id)

    if text_stripped.startswith("/순차"):
        seq_text = text_stripped[len("/순차"):].strip()
        if not seq_text:
            content = "⚠️ `/순차` 뒤에 작업 내용을 입력해주세요.\n\n예: `/순차 CORTHEX 웹사이트 기술→보안→사업성 분석`"
            update_task(task_id, status="completed", result_summary=content[:500], success=1)
            return {"content": content, "handled_by": "비서실장", "agent_id": "chief_of_staff"}
        return await _sequential_collaboration(seq_text, task_id)

    if text_lower in ("/도구점검", "/도구상태", "/tools_health", "전체 도구 점검", "도구 점검", "도구 상태"):
        import urllib.request as _ur
        try:
            req = _ur.Request("http://127.0.0.1:8000/api/tools/health")
            with _ur.urlopen(req, timeout=10) as resp:
                health = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            health = {"total": 0, "ready": 0, "missing_key": 0, "not_loaded": 0, "tools": [], "error": str(e)}

        content = f"🔧 **전체 도구 점검 결과**\n\n"
        content += f"| 항목 | 수량 |\n|------|------|\n"
        content += f"| 전체 도구 | {health.get('total', 0)}개 |\n"
        content += f"| 정상 (ready) | {health.get('ready', 0)}개 |\n"
        content += f"| API 키 미설정 | {health.get('missing_key', 0)}개 |\n"
        content += f"| 미로드 | {health.get('not_loaded', 0)}개 |\n"
        content += f"| ToolPool | {health.get('pool_status', 'unknown')} |\n\n"

        missing = [t for t in health.get("tools", []) if t.get("status") == "missing_key"]
        if missing:
            content += "### ⚠️ API 키 필요한 도구\n"
            for t in missing[:10]:
                content += f"- **{t['name']}** (`{t['tool_id']}`) — 환경변수: `{t.get('api_key_env', '?')}`\n"

        ready = [t for t in health.get("tools", []) if t.get("status") == "ready"]
        if ready:
            content += f"\n### ✅ 정상 작동 도구 ({len(ready)}개 중 상위 10개)\n"
            for t in ready[:10]:
                content += f"- {t['name']} (`{t['tool_id']}`)\n"

        update_task(task_id, status="completed", result_summary=content[:500], success=1)
        return {"content": content, "handled_by": "비서실장", "agent_id": "chief_of_staff"}

    if text_lower in ("/배치실행", "/batch_flush", "배치실행", "배치 실행"):
        result = await _flush_batch_api_queue()
        content = f"📦 **배치 실행 결과**\n\n"
        if "error" in result:
            content += f"❌ 실패: {result['error']}"
        elif result.get("batch_id"):
            content += f"✅ Batch API 제출 완료\n- batch_id: `{result['batch_id']}`\n- 건수: {result.get('count', 0)}건\n- 프로바이더: {result.get('provider', '?')}"
        else:
            content += result.get("message", "처리 완료")
        update_task(task_id, status="completed", result_summary=content[:500], success=1)
        return {"content": content, "handled_by": "비서실장", "agent_id": "chief_of_staff"}

    if text_lower in ("/배치상태", "/batch_status", "배치상태", "배치 상태"):
        pending_batches = load_setting("pending_batches") or []
        active = [b for b in pending_batches if b.get("status") in ("pending", "processing")]
        try:
            _batch_queue = app_state.batch_api_queue
            queue_count = len(_batch_queue)
        except Exception:
            queue_count = 0
        content = f"📦 **배치 상태**\n\n"
        content += f"- 대기열: {queue_count}건\n"
        content += f"- 처리 중인 배치: {len(active)}건\n"
        for b in active:
            prog = b.get("progress", {})
            content += f"  - `{b['batch_id'][:20]}...` ({b['provider']}) — {prog.get('completed', '?')}/{prog.get('total', '?')} 완료\n"
        update_task(task_id, status="completed", result_summary=content[:500], success=1)
        return {"content": content, "handled_by": "비서실장", "agent_id": "chief_of_staff"}

    # ── 키워드 기반 브로드캐스트 (기존 호환) ──
    if _is_broadcast_command(text):
        return await _broadcast_to_managers(text, task_id, target_agent_id=target_agent_id, conversation_id=conversation_id)

    # 3) @에이전트 직접 지정 (CLI 라우팅 보호 적용)
    if target_agent_id:
        if not _can_command(session_role, target_agent_id):
            blocked_msg = f"⚠️ 접근 거부: {session_role} 계정은 `{target_agent_id}` 에이전트를 직접 호출할 수 없습니다."
            update_task(task_id, status="failed", result_summary=blocked_msg[:200], success=0)
            return {"error": blocked_msg, "agent_id": target_agent_id, "handled_by": "시스템"}
        logger.info("직접 지정: %s → %s", session_role, target_agent_id)
        target_id = target_agent_id
        routing = {"agent_id": target_id, "method": "ceo_direct", "cost_usd": 0}
        routing_cost = 0

        is_specialist = target_id in _SPECIALIST_NAMES
        if is_specialist or target_id not in _AGENT_NAMES:
            direct_result = await _call_agent(target_id, text, conversation_id=conversation_id)
            direct_name = _SPECIALIST_NAMES.get(target_id, _AGENT_NAMES.get(target_id, target_id))
            if "error" in direct_result:
                update_task(task_id, status="failed",
                            result_summary=f"오류: {direct_result['error'][:100]}",
                            success=0, agent_id=target_id)
                direct_result["handled_by"] = direct_name
                return direct_result
            total_cost = routing_cost + direct_result.get("cost_usd", 0)
            update_task(task_id, status="completed",
                        result_summary=direct_result.get("content", "")[:500],
                        result_data=direct_result.get("content", ""),
                        success=1, cost_usd=total_cost,
                        tokens_used=direct_result.get("input_tokens", 0) + direct_result.get("output_tokens", 0),
                        time_seconds=direct_result.get("time_seconds", 0),
                        agent_id=target_id)
            direct_result["handled_by"] = direct_name
            direct_result["delegation"] = ""
            direct_result["agent_id"] = target_id
            direct_result["routing_method"] = "ceo_direct"
            direct_result["total_cost_usd"] = total_cost
            return direct_result
    else:
        routing = await _route_task(text)
        target_id = routing["agent_id"]
        routing_cost = routing.get("cost_usd", 0)

    # 4) 비서실장 직접 처리
    if target_id == "chief_of_staff":
        await _broadcast_status("chief_of_staff", "working", 0.2, "직접 처리 중...")
        soul = app_state.chief_prompt if app_state.chief_prompt else _load_agent_prompt("chief_of_staff")
        override = _get_model_override("chief_of_staff")
        model = select_model(text, override=override)
        _chief_history = _build_conv_history(conversation_id, text)
        result = await ask_ai(text, system_prompt=soul, model=model,
                              conversation_history=_chief_history)

        await _broadcast_status("chief_of_staff", "done", 1.0, "완료")

        if "error" in result:
            update_task(task_id, status="failed",
                        result_summary=f"AI 오류: {result['error'][:100]}",
                        success=0, agent_id="chief_of_staff")
            result["handled_by"] = "비서실장"
            return result

        total_cost = routing_cost + result.get("cost_usd", 0)
        update_task(task_id, status="completed",
                    result_summary=result["content"][:500],
                    result_data=result["content"],
                    success=1, cost_usd=total_cost,
                    tokens_used=result.get("input_tokens", 0) + result.get("output_tokens", 0),
                    time_seconds=result.get("time_seconds", 0),
                    agent_id="chief_of_staff")
        result["handled_by"] = "비서실장"
        result["delegation"] = ""
        result["agent_id"] = "chief_of_staff"
        result["routing_method"] = routing["method"]
        result["total_cost_usd"] = total_cost
        return result

    # 5) 부서 위임
    target_name = _AGENT_NAMES.get(target_id, target_id)
    await _broadcast_status("chief_of_staff", "working", 0.1, f"{target_name}에게 위임 중...")

    delegation_result = await _manager_with_delegation(target_id, text, conversation_id=conversation_id)
    await _broadcast_status("chief_of_staff", "done", 1.0, "위임 완료")

    if "error" in delegation_result:
        update_task(task_id, status="failed",
                    result_summary=f"위임 오류: {delegation_result['error'][:100]}",
                    success=0, agent_id=target_id)
        delegation_result["handled_by"] = target_name
        return delegation_result

    # 6) 결과 정리
    total_cost = routing_cost + delegation_result.get("cost_usd", 0)
    specs_used = delegation_result.get("specialists_used", 0)
    delegation_label = f"비서실장 → {target_name}"
    if specs_used:
        delegation_label += f" → 전문가 {specs_used}명"

    content = delegation_result.get("content", "")
    header = f"📋 **{target_name}** 보고"
    if specs_used:
        header += f" (소속 전문가 {specs_used}명 동원)"
    content = f"{header}\n\n---\n\n{content}"

    update_task(task_id, status="completed",
                result_summary=content[:500],
                result_data=content,
                success=1, cost_usd=total_cost,
                time_seconds=delegation_result.get("time_seconds", 0),
                agent_id=target_id)

    return {
        "content": content,
        "agent_id": target_id,
        "handled_by": target_name,
        "delegation": delegation_label,
        "total_cost_usd": round(total_cost, 6),
        "time_seconds": delegation_result.get("time_seconds", 0),
        "model": delegation_result.get("model", ""),
        "routing_method": routing["method"],
    }


# ── 도구 실행 파이프라인 ──

def _init_tool_pool():
    """ToolPool 초기화 — src/tools/ 모듈을 동적으로 로드합니다."""
    if app_state.tool_pool is not None:
        return app_state.tool_pool if app_state.tool_pool else None

    try:
        from src.tools.pool import ToolPool
        from src.llm.base import LLMResponse

        class _MiniModelRouter:
            """ask_ai()를 ModelRouter.complete() 인터페이스로 감싸는 어댑터."""

            class cost_tracker:
                @staticmethod
                def record(*args, **kwargs):
                    pass

            async def complete(self, model_name="", messages=None,
                             temperature=0.3, max_tokens=32768,
                             agent_id="", reasoning_effort=None,
                             use_batch=False):
                messages = messages or []
                system_prompt = ""
                user_message = ""
                for msg in messages:
                    if msg.get("role") == "system":
                        system_prompt = msg["content"]
                    elif msg.get("role") == "user":
                        user_message = msg["content"]

                result = await ask_ai(user_message, system_prompt, model_name)

                if "error" in result:
                    return LLMResponse(
                        content=f"[도구 LLM 오류] {result['error']}",
                        model=model_name,
                        input_tokens=0, output_tokens=0,
                        cost_usd=0.0, provider="unknown",
                    )
                return LLMResponse(
                    content=result["content"],
                    model=result.get("model", model_name),
                    input_tokens=result.get("input_tokens", 0),
                    output_tokens=result.get("output_tokens", 0),
                    cost_usd=result.get("cost_usd", 0.0),
                    provider=result.get("provider", "unknown"),
                )

            async def close(self):
                pass

        router = _MiniModelRouter()
        pool = ToolPool(router)

        tools_config = _load_config("tools")
        pool.build_from_config(tools_config)

        loaded = len(pool._tools)
        app_state.tool_pool = pool
        for a in AGENTS:
            _temp = _AGENTS_DETAIL.get(a["agent_id"], {}).get("temperature", 0.7)
            pool.set_agent_model(a["agent_id"], a.get("model_name", "claude-sonnet-4-6"), temperature=_temp)
        try:
            overrides = _load_data("agent_overrides", {})
            for agent_id, vals in overrides.items():
                if "model_name" in vals:
                    _temp = _AGENTS_DETAIL.get(agent_id, {}).get("temperature", 0.7)
                    pool.set_agent_model(agent_id, vals["model_name"], temperature=_temp)
        except Exception as e:
            logger.debug("에이전트 모델 오버라이드 실패: %s", e)
        _log(f"[TOOLS] ToolPool 초기화 완료: {loaded}개 도구 로드 ✅")
        return pool

    except Exception as e:
        _log(f"[TOOLS] ToolPool 초기화 실패 (도구 목록만 표시): {e}")
        app_state.tool_pool = False
        return None
