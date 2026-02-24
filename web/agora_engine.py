"""
AGORA Engine - AI 법학 토론 시스템 핵심 엔진

세 명의 AI 에이전트가 법학 논문에 대해 구조화된 토론을 수행합니다.
- 고동희(kodh): Claude Opus - 블루팀 (논문 저자, 자기 주장 옹호)
- 박성범(psb): GPT-5.2 xhigh - 레드팀 (철학적 반박)
- 권대옥(kdw): GPT-5.2 xhigh / Claude Sonnet (역할별 모델 전환)
"""

import asyncio
import difflib
import html
import json
import logging
import time
from typing import Any

from ai_handler import ask_ai
from db import (
    agora_create_session,
    agora_get_session,
    agora_update_session,
    agora_create_issue,
    agora_get_issues,
    agora_update_issue,
    agora_save_round,
    agora_get_rounds,
    agora_save_paper_version,
    agora_get_paper_latest,
    agora_save_chapter,
    agora_get_book,
)
from ws_manager import wm

logger = logging.getLogger("agora")

# ──────────────────────────────────────────────
# 에이전트 설정
# ──────────────────────────────────────────────

AGENTS = {
    "kodh": {
        "name": "고동희",
        "role": "blue",
        "model": "claude-opus-4-6",
        "reasoning_effort": "",
        "description": "블루팀 (논문 저자, 자기 주장 옹호)",
    },
    "psb": {
        "name": "박성범",
        "role": "red",
        "model": "gpt-5.2",
        "reasoning_effort": "xhigh",
        "description": "레드팀 (철학적 반박)",
    },
    "kdw": {
        "name": "권대옥",
        "role": "moderator",
        "models": {
            "reasoning": {"model": "gpt-5.2", "reasoning_effort": "xhigh"},
            "writing": {"model": "claude-sonnet-4-6", "reasoning_effort": ""},
        },
        "description": "사회자 (쟁점 생성/합의 판단/논문 수정/대화록 편찬)",
    },
}

MAX_ROUNDS_PER_ISSUE = 20

# ──────────────────────────────────────────────
# 시스템 프롬프트
# ──────────────────────────────────────────────

_HALLUCINATION_GUARD = (
    "근거 없는 주장을 절대 하지 마십시오. "
    "학술적 논거를 제시할 때 반드시 저자명, 논문명/저서명, 연도를 명시하십시오. "
    "출처를 특정할 수 없는 주장은 '일반적으로 ~로 논의된다' 등으로 한정하십시오."
)

SYSTEM_PROMPTS = {
    "kodh": (
        "당신은 고동희 교수입니다. 법학 논문의 저자로서, 자신의 학술적 주장을 열정적으로 방어합니다.\n\n"
        "## 성격과 논증 스타일\n"
        "- 법학 논증체로 작성: 체계적이고 논리적이며, 판례와 학설을 근거로 제시\n"
        "- 자신의 논문에 대한 깊은 애정과 확신을 가지고 강하게 방어\n"
        "- 반박에 대해 감정적으로 대응하지 않되, 학문적 열정은 드러냄\n"
        "- 양보할 부분은 인정하되, 핵심 논지는 끝까지 지킴\n\n"
        f"## 할루시네이션 방지\n{_HALLUCINATION_GUARD}\n\n"
        "## 출력 형식\n"
        "- 마크다운 형식으로 작성\n"
        "- 인용 시 [저자명, 논문명, 연도] 형식 사용\n"
        "- 발언 끝에 '---' 후 핵심 논점 1~2줄 요약"
    ),
    "psb": (
        "당신은 박성범 교수입니다. 법철학 전문가로서, 제출된 논문에 대해 철학적 관점에서 반박합니다.\n\n"
        "## 성격과 논증 스타일\n"
        "- 존재론적 질문을 던지며 논문의 전제를 흔듦\n"
        "- 독일 법철학(칸트, 헤겔, 라드브루흐)과 영미 법철학(하트, 드워킨, 라즈)을 자유롭게 활용\n"
        "- 논문의 맹점, 논리적 비약, 전제의 취약성을 정확히 지적\n"
        "- 비판은 날카롭되, 학문적 예의를 갖춤\n"
        "- 대안적 시각을 반드시 제시 (비판만 하지 않음)\n\n"
        f"## 할루시네이션 방지\n{_HALLUCINATION_GUARD}\n\n"
        "## 출력 형식\n"
        "- 마크다운 형식으로 작성\n"
        "- 인용 시 [저자명, 논문명, 연도] 형식 사용\n"
        "- 발언 끝에 '---' 후 핵심 반박 포인트 1~2줄 요약"
    ),
    "kdw_issue_extract": (
        "당신은 권대옥 교수입니다. 법학 토론의 공정한 사회자로서, 논문에서 핵심 쟁점을 추출합니다.\n\n"
        "## 임무\n"
        "주어진 법학 논문을 분석하여 토론할 가치가 있는 핵심 쟁점을 추출하십시오.\n\n"
        "## 쟁점 추출 기준\n"
        "- 논문의 핵심 주장과 전제에서 논쟁 가능한 포인트\n"
        "- 법철학적으로 깊이 있는 토론이 가능한 주제\n"
        "- 실무적 함의가 큰 쟁점 우선\n\n"
        f"## 할루시네이션 방지\n{_HALLUCINATION_GUARD}\n\n"
        '## 출력 형식 (반드시 JSON 배열)\n'
        '```json\n'
        '[\n'
        '  {"title": "쟁점 제목", "description": "쟁점 설명 (2~3문장)"},\n'
        '  ...\n'
        ']\n'
        '```\n'
        "3~7개 쟁점을 추출하십시오. JSON 외 다른 텍스트를 출력하지 마십시오."
    ),
    "kdw_consensus": (
        "당신은 권대옥 교수입니다. 법학 토론의 공정한 사회자입니다.\n\n"
        "## 임무\n"
        "고동희 교수(블루팀)와 박성범 교수(레드팀)의 토론을 관찰하고,\n"
        "합의에 도달했는지 판단하십시오.\n\n"
        "## 합의 판단 기준\n"
        "- 양측이 핵심 논점에 대해 수렴하는 결론에 도달했는가\n"
        "- 더 이상 새로운 논거가 제시되지 않고 반복되는가\n"
        "- 한쪽이 상대의 핵심 논거를 수용했는가\n\n"
        '## 출력 형식 (반드시 JSON)\n'
        '```json\n'
        '{\n'
        '  "consensus": true 또는 false,\n'
        '  "resolution": "합의 내용 또는 현재까지의 쟁점 정리 (3~5문장)",\n'
        '  "next_direction": "합의 미달 시 다음 라운드에서 집중할 논점"\n'
        '}\n'
        '```\n'
        "JSON 외 다른 텍스트를 출력하지 마십시오."
    ),
    "kdw_paper_revision": (
        "당신은 권대옥 교수입니다. 토론 결과를 바탕으로 논문을 수정합니다.\n\n"
        "## 임무\n"
        "토론에서 합의된 내용을 반영하여 원본 논문을 수정하십시오.\n\n"
        "## 수정 원칙\n"
        "- 합의된 내용만 반영 (한쪽 주장만 수용하지 않음)\n"
        "- 원문의 문체와 구조를 최대한 유지\n"
        "- 수정 부분에 각주로 토론 근거 표시\n"
        "- 삭제보다는 보완/확장 우선\n\n"
        "## 출력 형식\n"
        "수정된 논문 전문을 마크다운으로 출력하십시오.\n"
        "수정된 부분은 **볼드**로 표시하십시오.\n"
        "논문 전문만 출력하고, 부가 설명은 하지 마십시오."
    ),
    "kdw_chapter": (
        "당신은 권대옥 교수입니다. 토론 대화록을 학술 서적의 한 챕터로 편찬합니다.\n\n"
        "## 임무\n"
        "쟁점에 대한 토론 기록을 읽기 좋은 학술 대화록 챕터로 재구성하십시오.\n\n"
        "## 편찬 원칙\n"
        "- 발언 순서와 핵심 논거를 충실히 반영\n"
        "- 학술 서적의 대담/좌담 형식\n"
        "- 각 발언자의 논증 스타일을 살림\n"
        "- 챕터 시작에 쟁점 요약, 끝에 결론 정리\n\n"
        "## 출력 형식\n"
        "마크다운 형식의 챕터 본문만 출력하십시오."
    ),
    "kdw_derived_issues": (
        "당신은 권대옥 교수입니다. 토론에서 파생된 새로운 쟁점을 판단합니다.\n\n"
        "## 임무\n"
        "이번 쟁점 토론 과정에서 새롭게 떠오른 파생 쟁점이 있는지 판단하십시오.\n\n"
        "## 판단 기준\n"
        "- 기존 쟁점과 충분히 구별되는 독립적 논점인가\n"
        "- 토론할 학술적 가치가 있는가\n"
        "- 이미 논의된 쟁점의 반복이 아닌가\n\n"
        '## 출력 형식 (반드시 JSON)\n'
        '```json\n'
        '{\n'
        '  "has_derived": true 또는 false,\n'
        '  "issues": [\n'
        '    {"title": "파생 쟁점 제목", "description": "설명 (2~3문장)"}\n'
        '  ]\n'
        '}\n'
        '```\n'
        "파생 쟁점이 없으면 issues를 빈 배열로 하십시오.\n"
        "JSON 외 다른 텍스트를 출력하지 마십시오."
    ),
}


# ──────────────────────────────────────────────
# Diff HTML 생성 유틸리티
# ──────────────────────────────────────────────

def _generate_diff_html(original: str, revised: str) -> str:
    """unified_diff를 빨간/초록 HTML로 변환합니다."""
    original_lines = original.splitlines(keepends=True)
    revised_lines = revised.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        revised_lines,
        fromfile="수정 전",
        tofile="수정 후",
        lineterm="",
    )

    html_parts = []
    for line in diff:
        escaped = html.escape(line.rstrip("\n"))
        if line.startswith("+++") or line.startswith("---"):
            html_parts.append(f'<div class="diff-hdr">{escaped}</div>')
        elif line.startswith("@@"):
            html_parts.append(f'<div class="diff-hdr">{escaped}</div>')
        elif line.startswith("+"):
            html_parts.append(f'<div class="diff-add">{escaped}</div>')
        elif line.startswith("-"):
            html_parts.append(f'<div class="diff-del">{escaped}</div>')
        else:
            html_parts.append(f'<div class="diff-ctx">{escaped}</div>')
    return "\n".join(html_parts)


# ──────────────────────────────────────────────
# JSON 파싱 유틸리티
# ──────────────────────────────────────────────

def _parse_json_response(text: str) -> Any:
    """AI 응답에서 JSON을 추출하여 파싱합니다.

    ```json ... ``` 코드 블록 안에 있거나 순수 JSON인 경우 모두 처리합니다.
    """
    text = text.strip()

    # 코드 블록 안의 JSON 추출
    if "```" in text:
        start = text.find("```")
        # ```json 또는 ``` 뒤의 내용 찾기
        content_start = text.find("\n", start)
        if content_start == -1:
            content_start = start + 3
        end = text.find("```", content_start)
        if end == -1:
            end = len(text)
        text = text[content_start:end].strip()

    return json.loads(text)


# ──────────────────────────────────────────────
# AgoraEngine
# ──────────────────────────────────────────────

class AgoraEngine:
    """AI 법학 토론 엔진.

    세 명의 AI 에이전트가 법학 논문에 대해 구조화된 토론을 수행하고,
    합의 결과를 논문에 반영하며, 토론 대화록을 학술 서적으로 편찬합니다.
    """

    def __init__(self) -> None:
        self._paused: bool = False
        self._active_session_id: int | None = None
        self._total_cost_usd: float = 0.0
        self._task: asyncio.Task | None = None

    # ── 제어 API ─────────────────────────────

    def pause(self) -> None:
        """토론을 일시정지합니다. 현재 라운드 완료 후 멈춥니다."""
        self._paused = True
        logger.info("토론 일시정지 요청됨")

    def resume(self) -> None:
        """일시정지된 토론을 재개합니다."""
        self._paused = False
        logger.info("토론 재개")

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def active_session_id(self) -> int | None:
        return self._active_session_id

    @property
    def total_cost_usd(self) -> float:
        return self._total_cost_usd

    # ── 세션 생성 ────────────────────────────

    async def create_session(self, title: str, paper_text: str) -> int:
        """새 토론 세션을 생성합니다.

        Returns:
            생성된 세션 ID
        """
        session_id = agora_create_session(title, paper_text)
        # 초기 논문 버전 저장 (version 0 = 원본)
        agora_save_paper_version(
            session_id=session_id,
            version_num=0,
            full_text=paper_text,
            diff_html="",
            change_summary="원본 논문",
        )
        logger.info("토론 세션 생성: id=%d, title=%s", session_id, title)
        return session_id

    # ── 토론 시작 (비동기 태스크) ──────────────

    async def start_debate(self, session_id: int) -> None:
        """토론을 시작합니다. 백그라운드 태스크로 실행됩니다."""
        session = agora_get_session(session_id)
        if not session:
            raise ValueError(f"세션을 찾을 수 없습니다: {session_id}")

        if self.is_running:
            raise RuntimeError("이미 진행 중인 토론이 있습니다")

        self._paused = False
        self._active_session_id = session_id
        self._total_cost_usd = 0.0

        agora_update_session(session_id, status="in_progress")

        self._task = asyncio.create_task(self._run_debate(session_id))
        self._task.add_done_callback(self._on_debate_done)

    def _on_debate_done(self, task: asyncio.Task) -> None:
        """토론 태스크 완료 콜백."""
        self._active_session_id = None
        if task.exception():
            logger.error("토론 중 오류 발생: %s", task.exception())

    # ── 메인 토론 루프 ───────────────────────

    async def _run_debate(self, session_id: int) -> None:
        """토론의 전체 흐름을 실행합니다."""
        session = agora_get_session(session_id)
        paper_text = session["paper_text"]

        try:
            # 1단계: 쟁점 추출
            await self._broadcast("debate_start", {
                "session_id": session_id,
                "title": session["title"],
            })

            issues = await self._extract_issues(session_id, paper_text)

            if not issues:
                logger.warning("쟁점이 추출되지 않았습니다")
                agora_update_session(session_id, status="completed")
                await self._broadcast("debate_complete", {
                    "session_id": session_id,
                    "message": "추출된 쟁점이 없어 토론을 종료합니다.",
                    "total_cost_usd": self._total_cost_usd,
                })
                return

            # 2단계: 각 쟁점별 토론
            issue_queue = list(issues)  # 파생 쟁점이 추가될 수 있음
            chapter_num = 0

            while issue_queue:
                issue = issue_queue.pop(0)
                issue_id = issue["id"]

                # 일시정지 체크
                await self._wait_if_paused()

                # 2a: 토론 라운드
                resolution = await self._debate_issue(session_id, issue)

                # 2b: 합의 후 논문 수정
                if resolution:
                    paper_text = await self._revise_paper(session_id, issue, paper_text, resolution)

                # 2c: 대화록 챕터 작성
                chapter_num += 1
                await self._write_chapter(session_id, issue, chapter_num)

                # 2d: 파생 쟁점 판단
                derived = await self._check_derived_issues(session_id, issue)
                if derived:
                    issue_queue.extend(derived)

                agora_update_issue(issue_id, status="completed")

            # 3단계: 세션 완료
            agora_update_session(
                session_id,
                status="completed",
                total_cost_usd=self._total_cost_usd,
            )

            book = agora_get_book(session_id)
            await self._broadcast("debate_complete", {
                "session_id": session_id,
                "total_issues": len(issues),
                "total_chapters": len(book),
                "total_cost_usd": self._total_cost_usd,
            })

            logger.info(
                "토론 완료: session=%d, cost=$%.4f",
                session_id,
                self._total_cost_usd,
            )

        except asyncio.CancelledError:
            agora_update_session(session_id, status="paused")
            logger.info("토론이 취소되었습니다: session=%d", session_id)
            raise
        except Exception:
            agora_update_session(session_id, status="error")
            logger.exception("토론 중 예외 발생: session=%d", session_id)
            raise

    # ── 1단계: 쟁점 추출 ─────────────────────

    async def _extract_issues(self, session_id: int, paper_text: str) -> list[dict]:
        """권대옥(GPT-5.2 xhigh)이 논문에서 쟁점을 추출합니다."""
        logger.info("쟁점 추출 시작: session=%d", session_id)

        result = await self._call_ai(
            agent_key="kdw",
            model_role="reasoning",
            system_prompt=SYSTEM_PROMPTS["kdw_issue_extract"],
            user_message=f"다음 법학 논문에서 토론 쟁점을 추출하십시오.\n\n---\n\n{paper_text}",
        )

        if "error" in result:
            logger.error("쟁점 추출 실패: %s", result["error"])
            return []

        try:
            raw_issues = _parse_json_response(result["content"])
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("쟁점 JSON 파싱 실패: %s | content: %s", e, result.get("content", "")[:200])
            return []

        # DB에 저장
        db_issues = []
        for item in raw_issues:
            issue_id = agora_create_issue(
                session_id=session_id,
                title=item["title"],
                description=item.get("description", ""),
            )
            db_issue = {"id": issue_id, "title": item["title"], "description": item.get("description", "")}
            db_issues.append(db_issue)

            await self._broadcast("issue_created", {
                "session_id": session_id,
                "issue_id": issue_id,
                "title": item["title"],
                "description": item.get("description", ""),
            })

        logger.info("쟁점 %d개 추출 완료", len(db_issues))
        return db_issues

    # ── 2a: 쟁점별 토론 라운드 ───────────────

    async def _debate_issue(self, session_id: int, issue: dict) -> str | None:
        """하나의 쟁점에 대해 블루팀/레드팀 토론을 진행합니다.

        Returns:
            합의된 경우 resolution 문자열, 아니면 None
        """
        issue_id = issue["id"]
        issue_title = issue["title"]
        issue_desc = issue.get("description", "")

        agora_update_issue(issue_id, status="in_progress")

        session = agora_get_session(session_id)
        paper_text = session["paper_text"]

        # 대화 기록 (에이전트 간 맥락 공유)
        conversation: list[dict] = []
        context_msg = (
            f"## 토론 쟁점: {issue_title}\n\n"
            f"{issue_desc}\n\n"
            f"## 관련 논문 원문\n\n{paper_text}"
        )

        resolution = None

        for round_num in range(1, MAX_ROUNDS_PER_ISSUE + 1):
            await self._wait_if_paused()

            await self._broadcast("round_start", {
                "session_id": session_id,
                "issue_id": issue_id,
                "round_num": round_num,
            })

            logger.info(
                "라운드 %d 시작: issue=%d (%s)",
                round_num,
                issue_id,
                issue_title,
            )

            # ── 고동희 발언 (블루팀) ──
            kodh_prompt = context_msg if round_num == 1 else (
                f"## 토론 쟁점: {issue_title}\n\n"
                f"이전 토론 내용을 바탕으로 당신의 입장을 이어가십시오."
            )

            kodh_result = await self._call_ai(
                agent_key="kodh",
                system_prompt=SYSTEM_PROMPTS["kodh"],
                user_message=kodh_prompt,
                conversation_history=conversation,
            )

            kodh_content = kodh_result.get("content", "[발언 실패]")
            kodh_cost = kodh_result.get("cost_usd", 0)

            conversation.append({"role": "assistant", "content": f"[고동희 교수]\n{kodh_content}"})
            conversation.append({"role": "user", "content": "박성범 교수, 반박해 주십시오."})

            agora_save_round(
                issue_id=issue_id,
                round_num=round_num,
                speaker="kodh",
                speaker_model=kodh_result.get("model", AGENTS["kodh"]["model"]),
                content=kodh_content,
                citations="[]",
                cost_usd=kodh_cost,
            )

            await self._broadcast("round_complete", {
                "session_id": session_id,
                "issue_id": issue_id,
                "round_num": round_num,
                "speaker": "kodh",
                "speaker_name": "고동희",
                "content_preview": kodh_content[:200],
                "cost_usd": kodh_cost,
            })

            # ── 박성범 반박 (레드팀) ──
            psb_prompt = (
                f"## 토론 쟁점: {issue_title}\n\n"
                f"고동희 교수의 주장에 대해 철학적 관점에서 반박하십시오."
            )

            psb_result = await self._call_ai(
                agent_key="psb",
                system_prompt=SYSTEM_PROMPTS["psb"],
                user_message=psb_prompt,
                conversation_history=conversation,
            )

            psb_content = psb_result.get("content", "[반박 실패]")
            psb_cost = psb_result.get("cost_usd", 0)

            conversation.append({"role": "assistant", "content": f"[박성범 교수]\n{psb_content}"})
            conversation.append({"role": "user", "content": "권대옥 교수, 합의 여부를 판단해 주십시오."})

            agora_save_round(
                issue_id=issue_id,
                round_num=round_num,
                speaker="psb",
                speaker_model=psb_result.get("model", AGENTS["psb"]["model"]),
                content=psb_content,
                citations="[]",
                cost_usd=psb_cost,
            )

            await self._broadcast("round_complete", {
                "session_id": session_id,
                "issue_id": issue_id,
                "round_num": round_num,
                "speaker": "psb",
                "speaker_name": "박성범",
                "content_preview": psb_content[:200],
                "cost_usd": psb_cost,
            })

            # ── 권대옥 합의 판단 ──
            consensus_prompt = (
                f"## 토론 쟁점: {issue_title}\n\n"
                f"현재 라운드: {round_num}/{MAX_ROUNDS_PER_ISSUE}\n\n"
                f"지금까지의 토론을 분석하고 합의 여부를 판단하십시오."
            )

            consensus_result = await self._call_ai(
                agent_key="kdw",
                model_role="reasoning",
                system_prompt=SYSTEM_PROMPTS["kdw_consensus"],
                user_message=consensus_prompt,
                conversation_history=conversation,
            )

            consensus_content = consensus_result.get("content", "")
            consensus_cost = consensus_result.get("cost_usd", 0)

            agora_save_round(
                issue_id=issue_id,
                round_num=round_num,
                speaker="kdw",
                speaker_model=consensus_result.get("model", "gpt-5.2"),
                content=consensus_content,
                citations="[]",
                cost_usd=consensus_cost,
            )

            try:
                judgment = _parse_json_response(consensus_content)
            except (json.JSONDecodeError, KeyError):
                logger.warning("합의 판단 JSON 파싱 실패, 토론 계속: round=%d", round_num)
                conversation.append({
                    "role": "assistant",
                    "content": f"[권대옥 교수 - 사회]\n{consensus_content}",
                })
                conversation.append({
                    "role": "user",
                    "content": "고동희 교수, 이어서 발언해 주십시오.",
                })
                continue

            is_consensus = judgment.get("consensus", False)
            resolution_text = judgment.get("resolution", "")
            next_direction = judgment.get("next_direction", "")

            await self._broadcast("consensus", {
                "session_id": session_id,
                "issue_id": issue_id,
                "round_num": round_num,
                "consensus": is_consensus,
                "resolution": resolution_text,
                "cost_usd": consensus_cost,
            })

            if is_consensus:
                resolution = resolution_text
                agora_update_issue(
                    issue_id,
                    resolution=resolution,
                    rounds_taken=round_num,
                )
                logger.info("합의 도달: issue=%d, round=%d", issue_id, round_num)
                break

            # 합의 미달 → 다음 라운드 맥락에 방향 추가
            conversation.append({
                "role": "assistant",
                "content": f"[권대옥 교수 - 사회]\n합의에 이르지 못했습니다.\n\n{resolution_text}\n\n다음 라운드 방향: {next_direction}",
            })
            conversation.append({
                "role": "user",
                "content": f"고동희 교수, 사회자의 지적을 반영하여 다음 논점에 집중해 주십시오: {next_direction}",
            })

        else:
            # MAX_ROUNDS 도달 (합의 미달)
            resolution = f"[최대 라운드({MAX_ROUNDS_PER_ISSUE}) 도달] 최종 정리: {resolution_text if resolution_text else '합의 미달'}"
            agora_update_issue(
                issue_id,
                resolution=resolution,
                rounds_taken=MAX_ROUNDS_PER_ISSUE,
            )
            logger.info("최대 라운드 도달: issue=%d", issue_id)

        return resolution

    # ── 2b: 논문 수정 ────────────────────────

    async def _revise_paper(
        self,
        session_id: int,
        issue: dict,
        current_paper: str,
        resolution: str,
    ) -> str:
        """권대옥(Sonnet)이 합의 결과를 반영하여 논문을 수정합니다."""
        issue_id = issue["id"]

        # 토론 라운드 가져오기
        rounds = agora_get_rounds(issue_id)
        debate_summary = "\n\n".join(
            f"[{r['speaker']}] (라운드 {r['round_num']})\n{r['content']}"
            for r in rounds
        )

        revision_prompt = (
            f"## 토론 쟁점: {issue['title']}\n\n"
            f"## 합의 내용\n{resolution}\n\n"
            f"## 토론 기록 요약\n{debate_summary}\n\n"
            f"## 현재 논문\n{current_paper}\n\n"
            f"위 합의 내용을 반영하여 논문을 수정하십시오."
        )

        result = await self._call_ai(
            agent_key="kdw",
            model_role="writing",
            system_prompt=SYSTEM_PROMPTS["kdw_paper_revision"],
            user_message=revision_prompt,
        )

        revised_text = result.get("content", current_paper)
        revision_cost = result.get("cost_usd", 0)

        if "error" in result:
            logger.error("논문 수정 실패: %s", result["error"])
            return current_paper

        # Diff 생성
        diff_html = _generate_diff_html(current_paper, revised_text)

        # 버전 번호 결정
        latest = agora_get_paper_latest(session_id)
        version_num = (latest["version_num"] + 1) if latest else 1

        agora_save_paper_version(
            session_id=session_id,
            version_num=version_num,
            full_text=revised_text,
            diff_html=diff_html,
            change_summary=f"쟁점 '{issue['title']}' 합의 반영",
            issue_id=issue_id,
        )

        # 세션의 paper_text도 갱신
        agora_update_session(session_id, paper_text=revised_text)

        await self._broadcast("paper_updated", {
            "session_id": session_id,
            "issue_id": issue_id,
            "version_num": version_num,
            "change_summary": f"쟁점 '{issue['title']}' 합의 반영",
            "cost_usd": revision_cost,
        })

        logger.info("논문 수정 완료: version=%d", version_num)
        return revised_text

    # ── 2c: 대화록 챕터 작성 ─────────────────

    async def _write_chapter(
        self,
        session_id: int,
        issue: dict,
        chapter_num: int,
    ) -> None:
        """권대옥(Sonnet)이 토론 대화록을 학술 챕터로 편찬합니다."""
        issue_id = issue["id"]

        rounds = agora_get_rounds(issue_id)
        if not rounds:
            logger.warning("라운드 기록 없음, 챕터 건너뜀: issue=%d", issue_id)
            return

        debate_log = "\n\n---\n\n".join(
            f"### [{r['speaker']}] 라운드 {r['round_num']}\n\n{r['content']}"
            for r in rounds
        )

        chapter_prompt = (
            f"## 챕터 {chapter_num}: {issue['title']}\n\n"
            f"## 쟁점 설명\n{issue.get('description', '')}\n\n"
            f"## 토론 전문 기록\n\n{debate_log}\n\n"
            f"위 토론 기록을 학술 대화록 챕터로 편찬하십시오."
        )

        result = await self._call_ai(
            agent_key="kdw",
            model_role="writing",
            system_prompt=SYSTEM_PROMPTS["kdw_chapter"],
            user_message=chapter_prompt,
        )

        chapter_content = result.get("content", "")
        chapter_cost = result.get("cost_usd", 0)

        if "error" in result:
            logger.error("챕터 작성 실패: %s", result["error"])
            return

        chapter_title = f"제{chapter_num}장: {issue['title']}"
        agora_save_chapter(
            session_id=session_id,
            issue_id=issue_id,
            chapter_num=chapter_num,
            title=chapter_title,
            content=chapter_content,
        )

        await self._broadcast("chapter_written", {
            "session_id": session_id,
            "issue_id": issue_id,
            "chapter_num": chapter_num,
            "title": chapter_title,
            "cost_usd": chapter_cost,
        })

        logger.info("챕터 작성 완료: chapter=%d", chapter_num)

    # ── 2d: 파생 쟁점 판단 ───────────────────

    async def _check_derived_issues(
        self,
        session_id: int,
        parent_issue: dict,
    ) -> list[dict]:
        """권대옥(GPT-5.2 xhigh)이 파생 쟁점 여부를 판단합니다."""
        issue_id = parent_issue["id"]

        rounds = agora_get_rounds(issue_id)
        debate_summary = "\n".join(
            f"[{r['speaker']}] {r['content'][:300]}..."
            for r in rounds
        )

        # 기존 쟁점 목록 (중복 방지)
        existing_issues = agora_get_issues(session_id)
        existing_titles = [iss["title"] for iss in existing_issues]

        derived_prompt = (
            f"## 완료된 쟁점: {parent_issue['title']}\n\n"
            f"## 토론 요약\n{debate_summary}\n\n"
            f"## 기존 쟁점 목록 (중복 금지)\n"
            + "\n".join(f"- {t}" for t in existing_titles)
            + "\n\n파생 쟁점이 있는지 판단하십시오."
        )

        result = await self._call_ai(
            agent_key="kdw",
            model_role="reasoning",
            system_prompt=SYSTEM_PROMPTS["kdw_derived_issues"],
            user_message=derived_prompt,
        )

        derived_cost = result.get("cost_usd", 0)

        if "error" in result:
            logger.error("파생 쟁점 판단 실패: %s", result["error"])
            return []

        try:
            parsed = _parse_json_response(result.get("content", ""))
        except (json.JSONDecodeError, KeyError):
            logger.warning("파생 쟁점 JSON 파싱 실패")
            return []

        if not parsed.get("has_derived", False):
            return []

        new_issues = []
        for item in parsed.get("issues", []):
            title = item.get("title", "")
            if title in existing_titles:
                logger.info("중복 파생 쟁점 건너뜀: %s", title)
                continue

            new_issue_id = agora_create_issue(
                session_id=session_id,
                title=title,
                description=item.get("description", ""),
                parent_id=issue_id,
            )

            new_issue = {
                "id": new_issue_id,
                "title": title,
                "description": item.get("description", ""),
            }
            new_issues.append(new_issue)

            await self._broadcast("derived_issue", {
                "session_id": session_id,
                "parent_issue_id": issue_id,
                "issue_id": new_issue_id,
                "title": title,
                "description": item.get("description", ""),
                "cost_usd": derived_cost,
            })

        if new_issues:
            logger.info(
                "파생 쟁점 %d개 추가: %s",
                len(new_issues),
                ", ".join(i["title"] for i in new_issues),
            )

        return new_issues

    # ── AI 호출 래퍼 ─────────────────────────

    async def _call_ai(
        self,
        agent_key: str,
        system_prompt: str,
        user_message: str,
        model_role: str = "",
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """에이전트별 AI 호출을 수행하고 비용을 추적합니다."""
        agent = AGENTS[agent_key]

        # 모델/reasoning_effort 결정
        if agent_key == "kdw":
            # 권대옥은 역할에 따라 모델이 다름
            role_config = agent["models"].get(model_role, agent["models"]["reasoning"])
            model = role_config["model"]
            reasoning_effort = role_config["reasoning_effort"]
        else:
            model = agent["model"]
            reasoning_effort = agent.get("reasoning_effort", "")

        start_time = time.time()

        try:
            result = await ask_ai(
                user_message=user_message,
                system_prompt=system_prompt,
                model=model,
                reasoning_effort=reasoning_effort,
                conversation_history=conversation_history,
            )
        except Exception as e:
            logger.error("AI 호출 실패 [%s/%s]: %s", agent_key, model, e)
            return {"error": str(e)}

        elapsed = time.time() - start_time

        # 비용 누적
        cost = result.get("cost_usd", 0)
        self._total_cost_usd += cost

        # 비용 업데이트 브로드캐스트
        if self._active_session_id:
            await self._broadcast("cost_update", {
                "session_id": self._active_session_id,
                "agent": agent_key,
                "agent_name": agent["name"],
                "model": result.get("model", model),
                "cost_usd": cost,
                "total_cost_usd": self._total_cost_usd,
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "time_seconds": round(elapsed, 2),
            })

            # DB 세션 비용 갱신
            agora_update_session(
                self._active_session_id,
                total_cost_usd=self._total_cost_usd,
            )

        logger.info(
            "AI 호출 완료: agent=%s, model=%s, cost=$%.4f, time=%.1fs",
            agent_key,
            result.get("model", model),
            cost,
            elapsed,
        )

        return result

    # ── 유틸리티 ─────────────────────────────

    async def _wait_if_paused(self) -> None:
        """일시정지 상태이면 재개될 때까지 대기합니다."""
        while self._paused:
            await asyncio.sleep(0.5)

    async def _broadcast(self, event_type: str, data: dict) -> None:
        """SSE 이벤트를 브로드캐스트합니다."""
        try:
            await wm.broadcast_sse({
                "type": f"agora_{event_type}",
                "data": data,
            })
        except Exception as e:
            logger.warning("SSE 브로드캐스트 실패 [%s]: %s", event_type, e)

    # ── 세션 취소 ────────────────────────────

    async def cancel_debate(self) -> None:
        """진행 중인 토론을 취소합니다."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._paused = False
        logger.info("토론 취소됨")


# ──────────────────────────────────────────────
# 글로벌 인스턴스
# ──────────────────────────────────────────────

agora_engine = AgoraEngine()
