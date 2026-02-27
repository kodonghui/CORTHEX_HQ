"""
Token Budget Management for CORTHEX HQ.

Provides daily/monthly budget limits with warning thresholds.
CEO can check remaining budget via '예산' command.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from src.llm.cost_tracker import CostTracker

logger = logging.getLogger("corthex.budget")

_DEFAULT_CONFIG = {
    "daily_limit_usd": 5.0,
    "monthly_limit_usd": 100.0,
    "warn_threshold_pct": 80,
}


@dataclass
class BudgetStatus:
    daily_limit: float
    monthly_limit: float
    daily_used: float
    monthly_used: float
    warn_threshold_pct: int

    @property
    def daily_remaining(self) -> float:
        return max(0.0, self.daily_limit - self.daily_used)

    @property
    def monthly_remaining(self) -> float:
        return max(0.0, self.monthly_limit - self.monthly_used)

    @property
    def daily_pct(self) -> float:
        if self.daily_limit <= 0:
            return 0.0
        return min(100.0, self.daily_used / self.daily_limit * 100)

    @property
    def monthly_pct(self) -> float:
        if self.monthly_limit <= 0:
            return 0.0
        return min(100.0, self.monthly_used / self.monthly_limit * 100)

    @property
    def daily_warning(self) -> bool:
        return self.daily_pct >= self.warn_threshold_pct

    @property
    def monthly_warning(self) -> bool:
        return self.monthly_pct >= self.warn_threshold_pct

    @property
    def daily_exceeded(self) -> bool:
        return self.daily_used >= self.daily_limit

    @property
    def monthly_exceeded(self) -> bool:
        return self.monthly_used >= self.monthly_limit

    def to_dict(self) -> dict:
        return {
            "daily_limit": self.daily_limit,
            "monthly_limit": self.monthly_limit,
            "daily_used": round(self.daily_used, 6),
            "monthly_used": round(self.monthly_used, 6),
            "daily_remaining": round(self.daily_remaining, 6),
            "monthly_remaining": round(self.monthly_remaining, 6),
            "daily_pct": round(self.daily_pct, 1),
            "monthly_pct": round(self.monthly_pct, 1),
            "daily_warning": self.daily_warning,
            "monthly_warning": self.monthly_warning,
            "daily_exceeded": self.daily_exceeded,
            "monthly_exceeded": self.monthly_exceeded,
        }


class BudgetManager:
    """Manages token budget based on CostTracker records."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._config = dict(_DEFAULT_CONFIG)
        if config_path and config_path.exists():
            try:
                raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._config.update(raw)
                logger.info("예산 설정 로드: %s", config_path)
            except Exception as e:
                logger.warning("예산 설정 로드 실패, 기본값 사용: %s", e)

    @property
    def daily_limit(self) -> float:
        return float(self._config["daily_limit_usd"])

    @property
    def monthly_limit(self) -> float:
        return float(self._config["monthly_limit_usd"])

    @property
    def warn_threshold_pct(self) -> int:
        return int(self._config["warn_threshold_pct"])

    def get_status(self, cost_tracker: CostTracker) -> BudgetStatus:
        """Calculate current budget status from cost records."""
        today = date.today()
        current_month = today.month
        current_year = today.year

        daily_cost = 0.0
        monthly_cost = 0.0

        for record in cost_tracker._records:
            record_date = record.timestamp.date()
            # 이번 달 비용만 합산
            if record_date.year == current_year and record_date.month == current_month:
                monthly_cost += record.cost_usd
            # 오늘 비용만 합산
            if record_date == today:
                daily_cost += record.cost_usd

        return BudgetStatus(
            daily_limit=self.daily_limit,
            monthly_limit=self.monthly_limit,
            daily_used=daily_cost,
            monthly_used=monthly_cost,
            warn_threshold_pct=self.warn_threshold_pct,
        )

    def check_warning(self, cost_tracker: CostTracker) -> Optional[str]:
        """Return a warning message if budget threshold is reached, else None."""
        status = self.get_status(cost_tracker)

        if status.daily_exceeded:
            return (
                f"일일 예산 초과! (${status.daily_used:.4f} / ${status.daily_limit:.2f})"
            )
        if status.monthly_exceeded:
            return (
                f"월간 예산 초과! (${status.monthly_used:.4f} / ${status.monthly_limit:.2f})"
            )
        if status.daily_warning:
            return (
                f"일일 예산 {status.daily_pct:.0f}% 소진 "
                f"(${status.daily_used:.4f} / ${status.daily_limit:.2f})"
            )
        if status.monthly_warning:
            return (
                f"월간 예산 {status.monthly_pct:.0f}% 소진 "
                f"(${status.monthly_used:.4f} / ${status.monthly_limit:.2f})"
            )
        return None

    def save_config(self, config_path: Path) -> None:
        """Save current config to YAML file."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.dump(self._config, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        logger.info("예산 설정 저장: %s", config_path)

    def update_config(self, **kwargs: float) -> None:
        """Update budget config values."""
        for key, value in kwargs.items():
            if key in self._config:
                self._config[key] = value
