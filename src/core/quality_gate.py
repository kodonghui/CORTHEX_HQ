"""
Quality Gate: 매니저급 에이전트가 부하의 보고서를 검수하는 시스템.

기능:
1. 규칙 기반 검사 (LLM 호출 없음, 비용 0원)
   - 결과가 너무 짧은가?
   - 실패한 결과인가?
   - 빈 응답인가?

2. LLM 기반 검사 (gpt-5-mini 1회 호출, 저비용)
   - 질문에 실제로 답하고 있는가?
   - 할루시네이션 징후가 있는가?
   - 구체적 근거가 있는가?

반려된 작업은 1회 재시도 (피드백 포함).
최대 1회만 재시도하여 비용 폭주를 방지합니다.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

import yaml
from pathlib import Path

if TYPE_CHECKING:
    from src.core.quality_rules_manager import QualityRulesManager
    from src.llm.router import ModelRouter

logger = logging.getLogger("corthex.quality_gate")


@dataclass
class ReviewResult:
    """품질 검수 결과."""
    passed: bool
    score: int  # 0~100
    issues: list[str] = field(default_factory=list)
    reviewer_id: str = ""
    target_agent_id: str = ""
    task_description: str = ""
    rejection_reason: str = ""


@dataclass
class QualityStats:
    """품질 게이트 누적 통계."""
    total_reviewed: int = 0
    total_passed: int = 0
    total_rejected: int = 0
    total_retried: int = 0
    total_retry_passed: int = 0
    rejections_by_agent: dict[str, int] = field(default_factory=dict)
    rejections_by_reviewer: dict[str, int] = field(default_factory=dict)
    recent_rejections: list[dict[str, Any]] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if self.total_reviewed == 0:
            return 100.0
        return round(self.total_passed / self.total_reviewed * 100, 1)

    @property
    def retry_success_rate(self) -> float:
        if self.total_retried == 0:
            return 0.0
        return round(self.total_retry_passed / self.total_retried * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_reviewed": self.total_reviewed,
            "total_passed": self.total_passed,
            "total_rejected": self.total_rejected,
            "total_retried": self.total_retried,
            "total_retry_passed": self.total_retry_passed,
            "pass_rate": self.pass_rate,
            "retry_success_rate": self.retry_success_rate,
            "rejections_by_agent": self.rejections_by_agent,
            "rejections_by_reviewer": self.rejections_by_reviewer,
            "recent_rejections": self.recent_rejections[-10:],
        }


class QualityGate:
    """매니저가 부하 결과를 검수하는 품질 게이트."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.stats = QualityStats()
        self._rules = self._default_rules()
        self._rules_manager: QualityRulesManager | None = None

        if config_path and config_path.exists():
            try:
                loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                if loaded and isinstance(loaded, dict):
                    self._rules.update(loaded.get("rules", {}))
            except Exception as e:
                logger.warning("품질 규칙 로드 실패: %s", e)

    @staticmethod
    def _default_rules() -> dict[str, Any]:
        return {
            "min_length": 50,
            "max_retry": 1,
            "check_hallucination": True,
            "check_relevance": True,
            "review_model": "gpt-5-mini",
        }

    def set_rules_manager(self, manager: QualityRulesManager) -> None:
        """QualityRulesManager를 연결하여 동적 루브릭/모델 조회를 활성화한다."""
        self._rules_manager = manager

    def _get_rubric_prompt(self, division: str) -> str:
        """부서별 루브릭 프롬프트를 반환한다. rules_manager가 없으면 기본값."""
        if self._rules_manager:
            return self._rules_manager.get_rubric_prompt(division)
        return (
            "다음 기준으로 검수하세요:\n"
            "1. 관련성: 업무 지시에 실제로 답하고 있는가? (0-30점)\n"
            "2. 구체성: 막연한 일반론이 아닌 구체적 내용이 있는가? (0-30점)\n"
            "3. 신뢰성: 출처 없는 숫자, 존재하지 않는 사실 등 "
            "할루시네이션 징후가 있는가? (0-40점)"
        )

    def rule_based_check(self, result_data: Any, task_description: str) -> ReviewResult:
        """규칙 기반 검사 (LLM 호출 없음)."""
        issues = []
        text = str(result_data or "")

        # 빈 응답
        if not text.strip():
            issues.append("빈 응답")
            return ReviewResult(
                passed=False, score=0, issues=issues,
                rejection_reason="결과가 비어있습니다. 다시 작성해주세요.",
            )

        # 너무 짧음
        min_len = self._rules.get("min_length", 50)
        if len(text.strip()) < min_len:
            issues.append(f"응답 길이 부족 ({len(text.strip())}자 < {min_len}자)")

        # 에러 응답
        if isinstance(result_data, dict) and "error" in result_data:
            issues.append("에러 응답")
            return ReviewResult(
                passed=False, score=10, issues=issues,
                rejection_reason="에러가 발생했습니다. 다시 시도해주세요.",
            )

        # 의미없는 반복 패턴
        words = text.split()
        if len(words) > 10:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.3:
                issues.append("반복 패턴 감지")

        if issues:
            score = max(0, 60 - len(issues) * 20)
            return ReviewResult(
                passed=False, score=score, issues=issues,
                rejection_reason=" / ".join(issues) + ". 보완하여 다시 작성해주세요.",
            )

        return ReviewResult(passed=True, score=80, issues=[])

    async def llm_review(
        self,
        result_data: Any,
        task_description: str,
        model_router: ModelRouter,
        reviewer_id: str = "",
        division: str = "",
    ) -> ReviewResult:
        """LLM 기반 품질 검수. 모델과 루브릭은 QualityRulesManager에서 동적 조회."""
        text = str(result_data or "")[:3000]

        # 동적 모델 조회: rules_manager > _rules > 기본값
        if self._rules_manager:
            review_model = self._rules_manager.review_model
        else:
            review_model = self._rules.get("review_model", "gpt-5-mini")

        # 부서별 루브릭 조회
        rubric_text = self._get_rubric_prompt(division)

        prompt = (
            "당신은 보고서 품질 검수관입니다. 아래 보고서를 검수하세요.\n\n"
            f"## 원래 업무 지시\n{task_description}\n\n"
            f"## 제출된 보고서\n{text}\n\n"
            f"{rubric_text}\n\n"
            "반드시 아래 형식으로만 답하세요:\n"
            "점수: [0-100]\n"
            "통과: [예/아니오]\n"
            "문제점: [없으면 '없음', 있으면 구체적 설명]"
        )

        try:
            response = await model_router.complete(
                model_name=review_model,
                messages=[
                    {"role": "system", "content": "보고서 품질 검수관. 간결하게 판정."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                agent_id=reviewer_id or "quality_gate",
            )
            return self._parse_review(response.content, reviewer_id)
        except Exception as e:
            logger.warning("LLM 품질 검수 실패: %s", e)
            # LLM 실패 시 통과 처리 (검수 불능으로 업무 차단하지 않음)
            return ReviewResult(passed=True, score=70, issues=["LLM 검수 불가"])

    def _parse_review(self, response: str, reviewer_id: str) -> ReviewResult:
        """LLM 검수 응답 파싱."""
        lines = response.strip().split("\n")
        score = 70
        passed = True
        issues = []

        for line in lines:
            line = line.strip()
            if line.startswith("점수:"):
                try:
                    score = int(line.split(":")[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass
            elif line.startswith("통과:"):
                val = line.split(":")[1].strip()
                passed = val.startswith("예")
            elif line.startswith("문제점:"):
                issue_text = line.split(":", 1)[1].strip()
                if issue_text and issue_text != "없음":
                    issues.append(issue_text)

        # 점수가 50 미만이면 강제 반려
        if score < 50:
            passed = False

        rejection_reason = ""
        if not passed:
            rejection_reason = " / ".join(issues) if issues else "품질 기준 미달"

        return ReviewResult(
            passed=passed,
            score=score,
            issues=issues,
            reviewer_id=reviewer_id,
            rejection_reason=rejection_reason,
        )

    def record_review(
        self,
        review: ReviewResult,
        reviewer_id: str,
        target_agent_id: str,
        task_desc: str,
        is_retry: bool = False,
    ) -> None:
        """검수 결과를 통계에 기록."""
        self.stats.total_reviewed += 1

        if review.passed:
            self.stats.total_passed += 1
            if is_retry:
                self.stats.total_retry_passed += 1
        else:
            self.stats.total_rejected += 1
            # 에이전트별 반려 횟수
            self.stats.rejections_by_agent[target_agent_id] = (
                self.stats.rejections_by_agent.get(target_agent_id, 0) + 1
            )
            self.stats.rejections_by_reviewer[reviewer_id] = (
                self.stats.rejections_by_reviewer.get(reviewer_id, 0) + 1
            )
            # 최근 반려 기록
            self.stats.recent_rejections.append({
                "reviewer": reviewer_id,
                "target": target_agent_id,
                "task": task_desc[:80],
                "score": review.score,
                "reason": review.rejection_reason,
            })
            # 최대 20건 유지
            if len(self.stats.recent_rejections) > 20:
                self.stats.recent_rejections = self.stats.recent_rejections[-20:]

        if is_retry:
            self.stats.total_retried += 1
