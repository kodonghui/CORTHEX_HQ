"""
Quality Rules Manager for CORTHEX HQ.

CEO가 웹 UI에서 품질 게이트 설정(검수 모델, 부서별 루브릭)을
관리할 수 있게 한다. 변경사항은 config/quality_rules.yaml에 저장된다.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("corthex.quality_rules")

# agents.yaml에 정의된 부서 목록
KNOWN_DIVISIONS = [
    "secretary",
    "leet_master.tech",
    "leet_master.strategy",
    "leet_master.legal",
    "leet_master.marketing",
    "finance.investment",
    "publishing",
]

DIVISION_LABELS = {
    "default": "기본 (전체 공통)",
    "secretary": "비서실",
    "leet_master.tech": "기술개발팀 (CTO)",
    "leet_master.strategy": "전략기획팀 (CSO)",
    "leet_master.legal": "법무팀 (CLO)",
    "leet_master.marketing": "마케팅팀 (CMO)",
    "finance.investment": "금융분석팀 (CIO)",
    "publishing": "콘텐츠팀 (CPO)",
}

DEFAULT_RUBRIC_PROMPT = (
    "다음 기준으로 검수하세요:\n"
    "1. 관련성: 업무 지시에 실제로 답하고 있는가? (0-30점)\n"
    "2. 구체성: 막연한 일반론이 아닌 구체적 내용이 있는가? (0-30점)\n"
    "3. 신뢰성: 출처 없는 숫자, 존재하지 않는 사실 등 "
    "할루시네이션 징후가 있는가? (0-40점)"
)


class QualityRulesManager:
    """품질 게이트 설정을 YAML 파일로 관리한다."""

    def __init__(self, config_path: Path) -> None:
        self._path = config_path
        self._rules: dict[str, Any] = {}
        self._rubrics: dict[str, dict[str, str]] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        """YAML 파일에서 규칙과 루브릭을 로드한다."""
        if self._path.exists():
            try:
                raw = yaml.safe_load(
                    self._path.read_text(encoding="utf-8")
                )
                if isinstance(raw, dict):
                    self._rules = raw.get("rules", {})
                    self._rubrics = raw.get("rubrics", {})
                logger.info("품질 규칙 로드: %s", self._path)
            except Exception as e:
                logger.warning("품질 규칙 로드 실패: %s", e)

        # 기본 루브릭이 없으면 생성
        if "default" not in self._rubrics:
            self._rubrics["default"] = {
                "name": "기본 검수 기준",
                "prompt": DEFAULT_RUBRIC_PROMPT,
            }

    def _save(self) -> None:
        """메모리 상태를 YAML 파일에 저장한다."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "rules": self._rules,
            "rubrics": self._rubrics,
        }
        self._path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    # ── 검수 모델 설정 ──────────────────────────────

    @property
    def review_model(self) -> str:
        return self._rules.get("review_model", "gpt-5-mini")

    def set_review_model(self, model_name: str) -> None:
        self._rules["review_model"] = model_name
        self._save()
        logger.info("검수 모델 변경: %s", model_name)

    def get_rules(self) -> dict[str, Any]:
        return dict(self._rules)

    # ── 루브릭 CRUD ─────────────────────────────────

    def get_rubric(self, division: str) -> dict[str, str]:
        """부서별 루브릭을 반환한다. 없으면 default로 폴백."""
        return self._rubrics.get(division, self._rubrics["default"])

    def get_rubric_prompt(self, division: str) -> str:
        """부서별 루브릭 프롬프트 텍스트만 반환한다."""
        rubric = self.get_rubric(division)
        return rubric.get("prompt", DEFAULT_RUBRIC_PROMPT)

    def set_rubric(self, division: str, name: str, prompt: str) -> None:
        """부서별 루브릭을 설정/업데이트한다."""
        self._rubrics[division] = {"name": name, "prompt": prompt}
        self._save()
        logger.info("루브릭 저장: %s (%s)", division, name)

    def delete_rubric(self, division: str) -> bool:
        """부서별 루브릭을 삭제한다. 'default'는 삭제 불가."""
        if division == "default":
            return False
        if division in self._rubrics:
            del self._rubrics[division]
            self._save()
            logger.info("루브릭 삭제: %s", division)
            return True
        return False

    def list_rubrics(self) -> dict[str, dict[str, str]]:
        return dict(self._rubrics)

    # ── API 응답용 ──────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "rules": self.get_rules(),
            "rubrics": self.list_rubrics(),
            "known_divisions": KNOWN_DIVISIONS,
            "division_labels": DIVISION_LABELS,
        }
