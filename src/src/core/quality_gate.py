"""
Quality Gate: 매니저급 에이전트가 부하의 보고서를 검수하는 시스템.

하이브리드 루브릭 (2026-02-22 재설계):
1. 규칙 기반 사전 필터 (LLM 호출 없음, 비용 0원)
   - 빈 응답/에러/길이 부족 → 즉시 불합격
2. LLM 하이브리드 검수 (매니저 자기 모델 1회 호출)
   - 체크리스트: 필수(required) 전부 통과 필요
   - 점수: 1/3/5 가중 평균 ≥ 3.0 필요
3. 불합격 시 최대 2회 재작업 (피드백 포함)
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

import yaml
from pathlib import Path

if TYPE_CHECKING:
    from src.core.quality_rules_manager import QualityRulesManager
    from src.llm.router import ModelRouter

logger = logging.getLogger("corthex.quality_gate")


# ─────────────────────────────────────────────
# 데이터 구조
# ─────────────────────────────────────────────

@dataclass
class ChecklistItem:
    """체크리스트 항목 결과."""
    id: str
    label: str
    passed: bool
    required: bool
    feedback: str = ""


@dataclass
class ScoreItem:
    """점수 항목 결과."""
    id: str
    label: str
    score: int  # 1, 3, 5
    weight: int  # 가중치 (%)
    critical: bool = False  # ★치명적 항목 (1점이면 전체 점수 제한)
    feedback: str = ""


@dataclass
class HybridReviewResult:
    """하이브리드 검수 결과 (체크리스트 + 점수)."""
    passed: bool
    checklist_results: list[ChecklistItem] = field(default_factory=list)
    score_results: list[ScoreItem] = field(default_factory=list)
    weighted_average: float = 0.0  # 1~5 스케일
    feedback: str = ""
    rejection_reasons: list[str] = field(default_factory=list)
    reviewer_id: str = ""
    target_agent_id: str = ""
    review_model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "weighted_average": round(self.weighted_average, 2),
            "feedback": self.feedback,
            "rejection_reasons": self.rejection_reasons,
            "reviewer_id": self.reviewer_id,
            "target_agent_id": self.target_agent_id,
            "review_model": self.review_model,
            "checklist": [
                {"id": c.id, "label": c.label, "passed": c.passed,
                 "required": c.required, "feedback": c.feedback}
                for c in self.checklist_results
            ],
            "scores": [
                {"id": s.id, "label": s.label, "score": s.score,
                 "weight": s.weight, "critical": s.critical,
                 "feedback": s.feedback}
                for s in self.score_results
            ],
        }


@dataclass
class ReviewResult:
    """품질 검수 결과 (레거시 호환)."""
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


# ─────────────────────────────────────────────
# 메인 품질 게이트
# ─────────────────────────────────────────────

class QualityGate:
    """매니저가 부하 결과를 검수하는 품질 게이트."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.stats = QualityStats()
        self._rules: dict[str, Any] = self._default_rules()
        self._rubrics: dict[str, Any] = {}
        self._common_checklist: dict[str, list[dict]] = {"required": [], "optional": []}
        self._pass_criteria: dict[str, Any] = {
            "all_required_pass": True,
            "min_average_score": 3.0,
        }
        self._rules_manager: QualityRulesManager | None = None
        self._config_path = config_path

        if config_path and config_path.exists():
            self._load_config(config_path)

    def _load_config(self, config_path: Path) -> None:
        """YAML 설정 파일 로드."""
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if not loaded or not isinstance(loaded, dict):
                return
            self._rules.update(loaded.get("rules", {}))
            self._rubrics = loaded.get("rubrics", {})
            self._common_checklist = loaded.get("common_checklist", self._common_checklist)
            self._pass_criteria = loaded.get("pass_criteria", self._pass_criteria)
        except Exception as e:
            logger.warning("품질 규칙 로드 실패: %s", e)

    def reload_config(self) -> None:
        """설정 파일을 다시 로드한다 (웹 UI에서 수정 후 반영)."""
        if self._config_path and self._config_path.exists():
            self._load_config(self._config_path)

    @staticmethod
    def _default_rules() -> dict[str, Any]:
        return {
            "min_length": 50,
            "max_retry": 2,
            "check_hallucination": True,
            "check_relevance": True,
        }

    @property
    def max_retry(self) -> int:
        return self._rules.get("max_retry", 2)

    def set_rules_manager(self, manager: QualityRulesManager) -> None:
        """QualityRulesManager를 연결하여 동적 루브릭/모델 조회를 활성화한다."""
        self._rules_manager = manager

    # ─────────────────────────────────────────
    # 루브릭 조회
    # ─────────────────────────────────────────

    def get_rubric(self, division: str) -> dict[str, Any]:
        """부서별 루브릭 반환. 없으면 default."""
        if division and division in self._rubrics:
            return self._rubrics[division]
        return self._rubrics.get("default", {})

    def _build_checklist_items(self, division: str) -> list[dict]:
        """공통 + 부서별 체크리스트 항목 병합.

        부서 rubric에 exclude_common 리스트가 있으면 해당 ID의 공통 항목을 제외.
        예: exclude_common: ["C1"] → C1을 부서 전용 항목(D1)으로 대체.
        """
        rubric = self.get_rubric(division)
        dept_cl = rubric.get("department_checklist", {})
        exclude_ids = set(dept_cl.get("exclude_common", []))

        items = []
        # 공통 필수 (exclude_common에 있으면 건너뜀)
        for item in self._common_checklist.get("required", []):
            if item.get("id") in exclude_ids:
                continue
            items.append({**item, "required": True, "source": "common"})
        # 공통 선택
        for item in self._common_checklist.get("optional", []):
            if item.get("id") in exclude_ids:
                continue
            items.append({**item, "required": False, "source": "common"})
        # 부서별
        for item in dept_cl.get("required", []):
            items.append({**item, "required": True, "source": "department"})
        for item in dept_cl.get("optional", []):
            items.append({**item, "required": False, "source": "department"})
        return items

    def _build_scoring_items(self, division: str) -> list[dict]:
        """부서별 점수 항목 반환."""
        rubric = self.get_rubric(division)
        return rubric.get("scoring", [])

    # ─────────────────────────────────────────
    # 규칙 기반 사전 필터
    # ─────────────────────────────────────────

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

    # ─────────────────────────────────────────
    # 하이브리드 LLM 검수 (핵심)
    # ─────────────────────────────────────────

    async def hybrid_review(
        self,
        result_data: Any,
        task_description: str,
        model_router: "ModelRouter",
        reviewer_id: str = "",
        reviewer_model: str = "",
        division: str = "",
        target_agent_id: str = "",
    ) -> HybridReviewResult:
        """하이브리드 품질 검수: 체크리스트 + 1/3/5 점수."""

        text = str(result_data or "")

        # 1. 규칙 기반 사전 필터
        pre_check = self.rule_based_check(result_data, task_description)
        if not pre_check.passed:
            return HybridReviewResult(
                passed=False,
                weighted_average=0.0,
                feedback=pre_check.rejection_reason,
                rejection_reasons=pre_check.issues,
                reviewer_id=reviewer_id,
                target_agent_id=target_agent_id,
                review_model="rule_based",
            )

        # 2. 체크리스트 + 점수 항목 구성
        checklist_items = self._build_checklist_items(division)
        scoring_items = self._build_scoring_items(division)

        # 3. LLM 프롬프트 생성
        prompt = self._build_hybrid_prompt(
            task_description, text[:3000], checklist_items, scoring_items,
            division=division,
        )

        # 4. 매니저 자기 모델로 호출
        model_to_use = reviewer_model or "claude-sonnet-4-6"
        try:
            response = await model_router.complete(
                model_name=model_to_use,
                messages=[
                    {"role": "system", "content": (
                        "당신은 보고서 품질 검수관입니다. "
                        "반드시 요청된 JSON 형식으로만 응답하세요. "
                        "불합격/감점 항목에는 '뭘 고쳐야 하는지' 구체적으로 피드백하세요. "
                        "예: '최근 FOMC 결과를 분석에 반영하고 종목 영향을 연결해야 함' "
                        "(나쁜 예: '시의성 부족'). "
                        "보고서에 도구(dart_api, kr_stock 등)로 가져온 데이터가 포함된 경우, "
                        "해당 수치는 실시간 API의 정확한 데이터이므로 '확인 불가'로 감점하지 마세요."
                    )},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                agent_id=reviewer_id or "quality_gate",
            )
            result = self._parse_hybrid_response(
                response.content, checklist_items, scoring_items,
                reviewer_id, target_agent_id, model_to_use,
                original_text=text,
            )
            logger.info(
                "[QA] %s → %s | 모델=%s | 점수=%.1f | %s",
                reviewer_id, target_agent_id, model_to_use,
                result.weighted_average,
                "합격" if result.passed else "불합격",
            )
            return result

        except Exception as e:
            logger.warning("[QA] LLM 검수 실패 (%s→%s): %s", reviewer_id, target_agent_id, e)
            # LLM 실패 시 통과 처리 (업무 차단 방지)
            return HybridReviewResult(
                passed=True,
                weighted_average=3.0,
                feedback=f"LLM 검수 실패 ({e}). 자동 통과 처리됨.",
                reviewer_id=reviewer_id,
                target_agent_id=target_agent_id,
                review_model=model_to_use,
            )

    def _build_hybrid_prompt(
        self,
        task_description: str,
        text: str,
        checklist_items: list[dict],
        scoring_items: list[dict],
        division: str = "",
    ) -> str:
        """하이브리드 검수 프롬프트 생성."""

        # 체크리스트 파트
        cl_lines = []
        for item in checklist_items:
            req_tag = "[필수]" if item.get("required") else "[선택]"
            cl_lines.append(f"  - {item['id']}: {req_tag} {item['label']}")
        checklist_text = "\n".join(cl_lines)

        # 점수 파트
        sc_lines = []
        for item in scoring_items:
            criteria = item.get("criteria", {})
            c_desc = ", ".join(f"{k}점={v}" for k, v in sorted(criteria.items()))
            critical_tag = " ★치명적" if item.get("critical") else ""
            sc_lines.append(
                f"  - {item['id']}: {item['label']}{critical_tag} (가중치 {item.get('weight', 33)}%)\n"
                f"    판정 기준: {c_desc}"
            )
        scoring_text = "\n".join(sc_lines)

        # 전체 항목 ID 목록 (JSON 예시용)
        cl_ids = [item["id"] for item in checklist_items]
        sc_ids = [item["id"] for item in scoring_items]

        cl_example = ", ".join(f'"{cid}": true' for cid in cl_ids)
        sc_example = ", ".join(f'"{sid}": 3' for sid in sc_ids)

        # 도구 사용 데이터 신뢰 규칙 추가
        # 투자 분석 부서(finance.investment)는 전문가가 도구(API)로 데이터를 가져오므로 무조건 적용
        is_investment = division.startswith("finance") if division else False
        has_tools = "사용한 도구" in text
        tool_trust_section = ""
        if is_investment or has_tools:
            tool_trust_section = (
                "\n\n## ⚠️ 도구 데이터 신뢰 규칙 (필독!)\n"
                "이 보고서의 전문가는 실시간 API 도구(DART/KRX/ECOS/증권사 등)를 사용하여 데이터를 가져옵니다.\n"
                "- 도구로 가져온 수치(주가, 재무제표, 거시지표, 기술지표 등)는 **정확한 것으로 간주**하세요.\n"
                "- '수치 확인 불가', '출처 불명', '할루시네이션' 등을 이유로 감점하지 마세요.\n"
                "- 데이터 자체가 아닌, 데이터를 기반으로 한 **분석 논리와 완결성**을 평가하세요.\n"
            )
            if has_tools:
                tool_trust_section += (
                    "\n### ★ Q1 시의성 판정 보조 규칙\n"
                    "보고서 하단에 '사용한 도구' 섹션이 있다면, 이 전문가는 **분석 당일 실시간 API로 최신 데이터를 확보**한 것입니다.\n"
                    "- Q1 시의성에서 **최소 3점 이상**을 부여하세요.\n"
                    "- 1점은 '도구를 호출했으나 가져온 데이터를 보고서에 전혀 활용하지 않은' 극단적 경우에만 부여하세요.\n"
                    "- 도구 데이터를 적극 인용하고 시장 이벤트와 연결했다면 5점을 부여하세요.\n"
                )

        # 피드백 예시 생성 (불합격 항목만 구체적 피드백 필수)
        cl_fb_example = ", ".join(
            f'"{cid}": "불통과 시 구체적 사유"' for cid in cl_ids[:2]
        )
        sc_fb_example = ", ".join(
            f'"{sid}": "3점 이하 시 구체적 감점 사유와 개선 방향"' for sid in sc_ids[:2]
        )

        return (
            f"## 업무 지시\n{task_description}\n\n"
            f"## 제출된 보고서\n{text}\n\n"
            f"{tool_trust_section}"
            f"## 체크리스트 (통과=true, 불통과=false)\n{checklist_text}\n\n"
            f"## 점수 항목 (1/3/5 중 선택)\n{scoring_text}\n\n"
            "## 응답 형식\n"
            "반드시 아래 JSON 형식으로만 답하세요. JSON 외 텍스트는 쓰지 마세요.\n"
            "★ 불합격/감점 항목에는 반드시 **구체적 피드백**을 작성하세요.\n"
            "  - 나쁜 예: 'Q1 시의성 부족' (뭘 고쳐야 하는지 모름)\n"
            "  - 좋은 예: '2026-02-24 FOMC 결과, 삼성전자 4Q 실적 등 최근 이벤트를 구체적으로 언급하고 종목과 연결해야 함'\n"
            "```json\n"
            "{\n"
            f'  "checklist": {{{cl_example}}},\n'
            f'  "scores": {{{sc_example}}},\n'
            f'  "checklist_feedback": {{{cl_fb_example}}},\n'
            f'  "score_feedback": {{{sc_fb_example}}},\n'
            '  "feedback": "종합 피드백 (1~2문장)"\n'
            "}\n"
            "```"
        )

    def _parse_hybrid_response(
        self,
        response: str,
        checklist_items: list[dict],
        scoring_items: list[dict],
        reviewer_id: str,
        target_agent_id: str,
        model_used: str,
        original_text: str = "",
    ) -> HybridReviewResult:
        """LLM 하이브리드 응답 파싱."""

        parsed = self._extract_json(response)

        if parsed is None:
            logger.warning("[QA] JSON 파싱 실패, 정규식 폴백 시도")
            parsed = self._regex_fallback(response, checklist_items, scoring_items)

        if parsed is None:
            logger.warning("[QA] 정규식 폴백도 실패, 자동 통과 처리")
            return HybridReviewResult(
                passed=True,
                weighted_average=3.0,
                feedback="검수 응답 파싱 실패. 자동 통과 처리됨.",
                reviewer_id=reviewer_id,
                target_agent_id=target_agent_id,
                review_model=model_used,
            )

        # 항목별 피드백 추출
        cl_feedback_data = parsed.get("checklist_feedback", {})
        sc_feedback_data = parsed.get("score_feedback", {})

        # 체크리스트 결과 구성
        cl_data = parsed.get("checklist", {})
        checklist_results = []
        for item in checklist_items:
            item_passed = cl_data.get(item["id"], True)
            if isinstance(item_passed, str):
                item_passed = item_passed.lower() in ("true", "yes", "통과")
            item_fb = cl_feedback_data.get(item["id"], "") if not item_passed else ""
            checklist_results.append(ChecklistItem(
                id=item["id"],
                label=item["label"],
                passed=bool(item_passed),
                required=item.get("required", False),
                feedback=str(item_fb)[:200],
            ))

        # 점수 결과 구성
        sc_data = parsed.get("scores", {})
        score_results = []
        for item in scoring_items:
            raw_score = sc_data.get(item["id"], 3)
            try:
                score_val = int(raw_score)
            except (ValueError, TypeError):
                score_val = 3
            # 1/3/5 범위 보정
            if score_val <= 1:
                score_val = 1
            elif score_val <= 3:
                score_val = 3
            else:
                score_val = 5
            item_fb = sc_feedback_data.get(item["id"], "") if score_val <= 3 else ""
            score_results.append(ScoreItem(
                id=item["id"],
                label=item["label"],
                score=score_val,
                weight=item.get("weight", 33),
                critical=item.get("critical", False),
                feedback=str(item_fb)[:200],
            ))

        # ★ Q1 안전장치: 도구를 사용한 보고서에서 Q1이 1점이면 3점으로 보정
        # (도구 사용 여부는 코드에서 구조적으로 확인 — LLM 판정에 의존하지 않음)
        if original_text and "사용한 도구" in original_text:
            for s in score_results:
                if s.id == "Q1" and s.score == 1:
                    logger.info(
                        "[QA] ★Q1 안전장치 발동: '사용한 도구' 섹션 확인됨 → Q1 1점→3점 보정 (%s)",
                        target_agent_id,
                    )
                    s.score = 3
                    s.feedback = (s.feedback or "") + " [안전장치: 도구 사용 확인됨, 1점→3점 보정]"

        # 가중 평균 계산
        weighted_average = self._calc_weighted_average(score_results)

        # ★ 치명적 항목 연동: critical 항목이 1점이면 가중 평균 제한
        critical_cap = self._pass_criteria.get("critical_cap", 2.0)
        critical_failed = [
            s for s in score_results if s.critical and s.score == 1
        ]
        if critical_failed:
            original_avg = weighted_average
            weighted_average = min(weighted_average, critical_cap)
            failed_labels = ", ".join(f"[{s.id}] {s.label}" for s in critical_failed)
            logger.info(
                "[QA] ★치명적 항목 1점 감지: %s | 가중평균 %.1f → %.1f (cap=%.1f)",
                failed_labels, original_avg, weighted_average, critical_cap,
            )

        # 합격 판정
        feedback = parsed.get("feedback", "")
        rejection_reasons = []

        # 치명적 항목 불합격 사유 추가 (구체적 피드백 포함)
        for s in critical_failed:
            reason = f"★치명적 [{s.id}] {s.label} 1점"
            if s.feedback:
                reason += f": {s.feedback}"
            else:
                reason += f" → 전체 점수 {critical_cap} 이하로 제한"
            rejection_reasons.append(reason)

        # 필수 체크리스트 확인 (구체적 피드백 포함)
        all_required_pass = self._pass_criteria.get("all_required_pass", True)
        if all_required_pass:
            for cl in checklist_results:
                if cl.required and not cl.passed:
                    reason = f"필수항목 불통과: [{cl.id}] {cl.label}"
                    if cl.feedback:
                        reason += f" — {cl.feedback}"
                    rejection_reasons.append(reason)

        # 점수 기준 확인 — 낮은 점수 항목의 구체적 피드백도 포함
        min_avg = self._pass_criteria.get("min_average_score", 3.0)
        if weighted_average < min_avg:
            low_items = [s for s in score_results if s.score <= 1 and s.feedback]
            if low_items:
                details = "; ".join(f"[{s.id}] {s.feedback}" for s in low_items)
                rejection_reasons.append(
                    f"가중 평균 {weighted_average:.1f} < 기준 {min_avg} — {details}"
                )
            else:
                rejection_reasons.append(
                    f"가중 평균 {weighted_average:.1f} < 기준 {min_avg}"
                )

        passed = len(rejection_reasons) == 0

        return HybridReviewResult(
            passed=passed,
            checklist_results=checklist_results,
            score_results=score_results,
            weighted_average=weighted_average,
            feedback=feedback,
            rejection_reasons=rejection_reasons,
            reviewer_id=reviewer_id,
            target_agent_id=target_agent_id,
            review_model=model_used,
        )

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """응답에서 JSON 추출."""
        # ```json ... ``` 블록 먼저 시도
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 전체 텍스트에서 첫 번째 { ... } 시도
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _regex_fallback(
        text: str,
        checklist_items: list[dict],
        scoring_items: list[dict],
    ) -> dict | None:
        """JSON 파싱 실패 시 정규식으로 값 추출 시도."""
        result: dict[str, Any] = {"checklist": {}, "scores": {}, "feedback": ""}

        for item in checklist_items:
            # "C1: true" 또는 "C1: 통과" 패턴
            pattern = rf'{item["id"]}\s*[:=]\s*(true|false|통과|불통과)'
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                val = m.group(1).lower()
                result["checklist"][item["id"]] = val in ("true", "통과")

        for item in scoring_items:
            # "S1: 3" 또는 "S1 = 5" 패턴
            pattern = rf'{item["id"]}\s*[:=]\s*(\d)'
            m = re.search(pattern, text)
            if m:
                result["scores"][item["id"]] = int(m.group(1))

        # 최소한 하나라도 찾았으면 성공
        if result["checklist"] or result["scores"]:
            return result
        return None

    @staticmethod
    def _calc_weighted_average(score_results: list[ScoreItem]) -> float:
        """가중 평균 계산 (1~5 스케일)."""
        if not score_results:
            return 3.0
        total_weight = sum(s.weight for s in score_results)
        if total_weight == 0:
            return 3.0
        weighted_sum = sum(s.score * s.weight for s in score_results)
        return weighted_sum / total_weight

    # ─────────────────────────────────────────
    # 사유 특정 재검수 (반려 항목만 재평가)
    # ─────────────────────────────────────────

    @staticmethod
    def get_failed_item_ids(review: "HybridReviewResult") -> list[str]:
        """반려된 항목 ID 추출 — 체크리스트 불통과 + 점수 1점 항목.

        Returns: ["D1", "Q3", "Q4"] 형태의 ID 리스트.
        """
        failed: list[str] = []
        for cl in review.checklist_results:
            if not cl.passed:
                failed.append(cl.id)
        for sc in review.score_results:
            if sc.score <= 1:
                failed.append(sc.id)
        return failed

    async def targeted_hybrid_review(
        self,
        result_data: Any,
        task_description: str,
        model_router: "ModelRouter",
        previous_review: "HybridReviewResult",
        failed_ids: list[str] | None = None,
        reviewer_id: str = "",
        reviewer_model: str = "",
        division: str = "",
        target_agent_id: str = "",
    ) -> "HybridReviewResult":
        """사유 특정 재검수: 반려 항목만 LLM 재평가, 나머지는 이전 점수 유지.

        비유: '수학만 다시 풀어라' → 수학만 채점, 국영사과는 이전 점수 유지.
        """
        text = str(result_data or "")

        # 1. 규칙 기반 사전 필터 (기본 검증은 여전히 필요)
        pre_check = self.rule_based_check(result_data, task_description)
        if not pre_check.passed:
            return HybridReviewResult(
                passed=False,
                weighted_average=0.0,
                feedback=pre_check.rejection_reason,
                rejection_reasons=pre_check.issues,
                reviewer_id=reviewer_id,
                target_agent_id=target_agent_id,
                review_model="rule_based",
            )

        # 2. 반려 항목 ID 결정
        if not failed_ids:
            failed_ids = self.get_failed_item_ids(previous_review)
        if not failed_ids:
            # 반려 항목 없음 → 이전 결과 그대로 반환 (이미 합격)
            return previous_review

        # 3. 반려 항목만 추출
        all_checklist = self._build_checklist_items(division)
        all_scoring = self._build_scoring_items(division)
        failed_checklist = [c for c in all_checklist if c["id"] in failed_ids]
        failed_scoring = [s for s in all_scoring if s["id"] in failed_ids]

        if not failed_checklist and not failed_scoring:
            return previous_review

        # 4. 반려 항목만 포함하는 프롬프트 생성
        prompt = self._build_targeted_prompt(
            task_description, text[:3000],
            failed_checklist, failed_scoring,
            failed_ids, division,
        )

        # 5. LLM 호출
        model_to_use = reviewer_model or "claude-sonnet-4-6"
        try:
            response = await model_router.complete(
                model_name=model_to_use,
                messages=[
                    {"role": "system", "content": (
                        "당신은 보고서 재검수관입니다. "
                        "이전 검수에서 불합격된 특정 항목만 재평가합니다. "
                        "나열된 항목만 평가하세요. 나열되지 않은 항목은 평가하지 마세요. "
                        "반드시 요청된 JSON 형식으로만 응답하세요. "
                        "보고서에 도구(dart_api, kr_stock 등)로 가져온 데이터가 포함된 경우, "
                        "해당 수치는 실시간 API의 정확한 데이터이므로 '확인 불가'로 감점하지 마세요."
                    )},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                agent_id=reviewer_id or "quality_gate",
            )

            # 6. 반려 항목 파싱
            new_partial = self._parse_hybrid_response(
                response.content, failed_checklist, failed_scoring,
                reviewer_id, target_agent_id, model_to_use,
                original_text=text,
            )

            # 7. 이전 합격 결과와 머지
            merged = self._merge_reviews(previous_review, new_partial, failed_ids)

            logger.info(
                "[QA] ★사유 특정 재검수: %s → %s | 반려항목=%s | 점수 %.1f→%.1f | %s",
                reviewer_id, target_agent_id, ",".join(failed_ids),
                previous_review.weighted_average, merged.weighted_average,
                "합격" if merged.passed else "불합격",
            )
            return merged

        except Exception as e:
            logger.warning("[QA] 사유 특정 재검수 LLM 실패 (%s→%s): %s", reviewer_id, target_agent_id, e)
            return HybridReviewResult(
                passed=True,
                weighted_average=3.0,
                feedback=f"재검수 LLM 실패 ({e}). 자동 통과.",
                reviewer_id=reviewer_id,
                target_agent_id=target_agent_id,
                review_model=model_to_use,
            )

    def _build_targeted_prompt(
        self,
        task_description: str,
        text: str,
        failed_checklist: list[dict],
        failed_scoring: list[dict],
        failed_ids: list[str],
        division: str = "",
    ) -> str:
        """사유 특정 재검수용 프롬프트 — 반려 항목만 포함."""

        # 체크리스트 파트 (반려 항목만)
        cl_lines = []
        for item in failed_checklist:
            req_tag = "[필수]" if item.get("required") else "[선택]"
            cl_lines.append(f"  - {item['id']}: {req_tag} {item['label']}")
        checklist_text = "\n".join(cl_lines) if cl_lines else "(해당 없음)"

        # 점수 파트 (반려 항목만)
        sc_lines = []
        for item in failed_scoring:
            criteria = item.get("criteria", {})
            c_desc = ", ".join(f"{k}점={v}" for k, v in sorted(criteria.items()))
            critical_tag = " ★치명적" if item.get("critical") else ""
            sc_lines.append(
                f"  - {item['id']}: {item['label']}{critical_tag} (가중치 {item.get('weight', 33)}%)\n"
                f"    판정 기준: {c_desc}"
            )
        scoring_text = "\n".join(sc_lines) if sc_lines else "(해당 없음)"

        # JSON 예시
        cl_ids = [item["id"] for item in failed_checklist]
        sc_ids = [item["id"] for item in failed_scoring]
        cl_example = ", ".join(f'"{cid}": true' for cid in cl_ids) if cl_ids else ""
        sc_example = ", ".join(f'"{sid}": 3' for sid in sc_ids) if sc_ids else ""

        # 도구 신뢰 규칙
        has_tools = "사용한 도구" in text
        tool_trust = ""
        if has_tools:
            tool_trust = (
                "\n## ⚠️ 도구 데이터 신뢰 규칙\n"
                "이 전문가는 실시간 API 도구를 사용하여 데이터를 가져왔습니다.\n"
                "- 도구 수치는 정확한 것으로 간주하세요.\n"
                "- 데이터 자체가 아닌, 분석 논리와 완결성을 평가하세요.\n"
            )

        parts = [
            f"## 재검수 대상 항목\n"
            f"이전 검수에서 불합격된 항목: **{', '.join(failed_ids)}**\n"
            f"⚠️ 아래 나열된 항목만 재평가하세요. 다른 항목은 이미 통과되었습니다.\n\n"
            f"## 업무 지시\n{task_description}\n\n"
            f"## 제출된 보고서 (재작업 후)\n{text}\n"
            f"{tool_trust}\n"
        ]

        if cl_lines:
            parts.append(f"## 재평가 체크리스트 (통과=true, 불통과=false)\n{checklist_text}\n\n")
        if sc_lines:
            parts.append(f"## 재평가 점수 항목 (1/3/5 중 선택)\n{scoring_text}\n\n")

        # JSON 형식
        json_parts = []
        if cl_example:
            json_parts.append(f'  "checklist": {{{cl_example}}}')
        if sc_example:
            json_parts.append(f'  "scores": {{{sc_example}}}')
        if cl_ids:
            cl_fb = ", ".join(f'"{cid}": "불통과 시 사유"' for cid in cl_ids)
            json_parts.append(f'  "checklist_feedback": {{{cl_fb}}}')
        if sc_ids:
            sc_fb = ", ".join(f'"{sid}": "3점 이하 시 감점 사유"' for sid in sc_ids)
            json_parts.append(f'  "score_feedback": {{{sc_fb}}}')
        json_parts.append('  "feedback": "재검수 종합 피드백"')

        parts.append(
            "## 응답 형식\n"
            "반드시 아래 JSON 형식으로만 답하세요. JSON 외 텍스트는 쓰지 마세요.\n"
            "```json\n{\n" + ",\n".join(json_parts) + "\n}\n```"
        )

        return "\n".join(parts)

    def _merge_reviews(
        self,
        original: "HybridReviewResult",
        new_partial: "HybridReviewResult",
        failed_ids: list[str],
    ) -> "HybridReviewResult":
        """이전 합격 결과 + 재검수 결과 머지.

        반려 항목 → 새 점수, 통과 항목 → 이전 점수 유지.
        """
        # 체크리스트 머지
        new_cl_map = {c.id: c for c in new_partial.checklist_results}
        merged_cl: list[ChecklistItem] = []
        for cl in original.checklist_results:
            if cl.id in failed_ids and cl.id in new_cl_map:
                merged_cl.append(new_cl_map[cl.id])
            else:
                merged_cl.append(cl)

        # 점수 머지
        new_sc_map = {s.id: s for s in new_partial.score_results}
        merged_sc: list[ScoreItem] = []
        for sc in original.score_results:
            if sc.id in failed_ids and sc.id in new_sc_map:
                merged_sc.append(new_sc_map[sc.id])
            else:
                merged_sc.append(sc)

        # 가중 평균 재계산
        weighted_average = self._calc_weighted_average(merged_sc)

        # 치명적 항목 체크
        critical_cap = self._pass_criteria.get("critical_cap", 2.0)
        critical_failed = [s for s in merged_sc if s.critical and s.score == 1]
        if critical_failed:
            weighted_average = min(weighted_average, critical_cap)

        # 합격 판정
        rejection_reasons: list[str] = []
        all_required_pass = self._pass_criteria.get("all_required_pass", True)
        if all_required_pass:
            for cl in merged_cl:
                if cl.required and not cl.passed:
                    reason = f"필수항목 불통과: [{cl.id}] {cl.label}"
                    if cl.feedback:
                        reason += f" — {cl.feedback}"
                    rejection_reasons.append(reason)

        min_avg = self._pass_criteria.get("min_average_score", 3.0)
        if weighted_average < min_avg:
            low_items = [s for s in merged_sc if s.score <= 1 and s.feedback]
            if low_items:
                details = "; ".join(f"[{s.id}] {s.feedback}" for s in low_items)
                rejection_reasons.append(f"가중 평균 {weighted_average:.1f} < 기준 {min_avg} — {details}")
            else:
                rejection_reasons.append(f"가중 평균 {weighted_average:.1f} < 기준 {min_avg}")

        for s in critical_failed:
            reason = f"★치명적 [{s.id}] {s.label} 1점"
            if s.feedback:
                reason += f": {s.feedback}"
            rejection_reasons.append(reason)

        return HybridReviewResult(
            passed=len(rejection_reasons) == 0,
            checklist_results=merged_cl,
            score_results=merged_sc,
            weighted_average=weighted_average,
            feedback=new_partial.feedback or original.feedback,
            rejection_reasons=rejection_reasons,
            reviewer_id=new_partial.reviewer_id or original.reviewer_id,
            target_agent_id=new_partial.target_agent_id or original.target_agent_id,
            review_model=new_partial.review_model or original.review_model,
        )

    # ─────────────────────────────────────────
    # 레거시 LLM 검수 (호환용)
    # ─────────────────────────────────────────

    def _get_rubric_prompt(self, division: str) -> str:
        """부서별 루브릭 프롬프트를 반환한다 (레거시)."""
        if self._rules_manager:
            return self._rules_manager.get_rubric_prompt(division)
        return (
            "다음 기준으로 검수하세요:\n"
            "1. 관련성: 업무 지시에 실제로 답하고 있는가? (0-30점)\n"
            "2. 구체성: 막연한 일반론이 아닌 구체적 내용이 있는가? (0-30점)\n"
            "3. 신뢰성: 출처 없는 숫자, 존재하지 않는 사실 등 "
            "할루시네이션 징후가 있는가? (0-40점)"
        )

    async def llm_review(
        self,
        result_data: Any,
        task_description: str,
        model_router: "ModelRouter",
        reviewer_id: str = "",
        division: str = "",
    ) -> ReviewResult:
        """LLM 기반 품질 검수 (레거시 — hybrid_review 사용 권장)."""
        text = str(result_data or "")[:3000]

        if self._rules_manager:
            review_model = self._rules_manager.review_model
        else:
            review_model = self._rules.get("review_model", "claude-sonnet-4-6")

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
            return ReviewResult(passed=True, score=70, issues=["LLM 검수 불가"])

    def _parse_review(self, response: str, reviewer_id: str) -> ReviewResult:
        """LLM 검수 응답 파싱 (레거시)."""
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

    # ─────────────────────────────────────────
    # 통계 기록
    # ─────────────────────────────────────────

    def record_review(
        self,
        review: ReviewResult | HybridReviewResult,
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
            self.stats.rejections_by_agent[target_agent_id] = (
                self.stats.rejections_by_agent.get(target_agent_id, 0) + 1
            )
            self.stats.rejections_by_reviewer[reviewer_id] = (
                self.stats.rejections_by_reviewer.get(reviewer_id, 0) + 1
            )
            # rejection_reason 추출
            if isinstance(review, HybridReviewResult):
                reason = " / ".join(review.rejection_reasons) if review.rejection_reasons else "품질 기준 미달"
                score_val = review.weighted_average
            else:
                reason = review.rejection_reason
                score_val = review.score

            self.stats.recent_rejections.append({
                "reviewer": reviewer_id,
                "target": target_agent_id,
                "task": task_desc[:80],
                "score": score_val,
                "reason": reason,
            })
            if len(self.stats.recent_rejections) > 20:
                self.stats.recent_rejections = self.stats.recent_rejections[-20:]

        if is_retry:
            self.stats.total_retried += 1
