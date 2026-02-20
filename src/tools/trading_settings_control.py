"""
자동매매 설정 제어 Tool (Trading Settings Control).

CIO가 자동매매 설정값을 조회하거나 변경할 수 있는 도구입니다.
CEO 투자 성향별 안전 범위 내에서만 변경 가능합니다.

사용 방법:
  - action="get_settings": 현재 자동매매 설정 조회
  - action="update_settings": 설정 변경 (changes + reason 필수)
  - action="get_risk_profile": 투자 성향 및 안전 범위 조회
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger(__name__)


class TradingSettingsControlTool(BaseTool):
    """CIO가 자동매매 설정을 조회/변경하는 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "get_settings")

        if action == "get_settings":
            return await self._get_settings()
        elif action == "update_settings":
            changes = kwargs.get("changes", {})
            reason = kwargs.get("reason", "")
            if not changes:
                return "❌ 변경할 항목(changes)이 없습니다."
            if not reason:
                return "❌ 변경 사유(reason)를 입력해주세요."
            return await self._update_settings(changes, reason)
        elif action == "get_risk_profile":
            return await self._get_risk_profile()
        else:
            return f"❌ 알 수 없는 action: {action}. get_settings / update_settings / get_risk_profile 중 선택하세요."

    async def _get_settings(self) -> str:
        try:
            import importlib
            ms = importlib.import_module("web.mini_server")
            settings = ms._load_data("trading_settings", ms._default_trading_settings())
            profile = ms._get_risk_profile()
            ranges = ms.RISK_PROFILES.get(profile, {})
            return (
                f"## 현재 자동매매 설정\n"
                f"**투자 성향**: {ranges.get('label', profile)} {ranges.get('emoji', '')}\n\n"
                f"| 항목 | 현재값 | 안전 범위 |\n"
                f"|------|--------|----------|\n"
                f"| 종목당 최대 비중 | {settings.get('max_position_pct')}% | {ranges.get('max_position_pct', {})} |\n"
                f"| 최소 신뢰도 | {settings.get('min_confidence')}% | {ranges.get('min_confidence', {})} |\n"
                f"| 손절 | {settings.get('default_stop_loss_pct')}% | {ranges.get('default_stop_loss', {})} |\n"
                f"| 익절 | {settings.get('default_take_profit_pct')}% | {ranges.get('default_take_profit', {})} |\n"
                f"| 일일 최대 거래 | {settings.get('max_daily_trades')} | {ranges.get('max_daily_trades', {})} |\n"
                f"| 일일 최대 손실 | {settings.get('max_daily_loss_pct')}% | {ranges.get('max_daily_loss_pct', {})} |\n"
                f"| 주문 금액 | {settings.get('order_size')} | {ranges.get('order_size', {})} |\n"
            )
        except Exception as e:
            return f"❌ 설정 조회 실패: {e}"

    async def _update_settings(self, changes: dict, reason: str) -> str:
        try:
            import importlib
            ms = importlib.import_module("web.mini_server")
            profile = ms._get_risk_profile()
            settings = ms._load_data("trading_settings", ms._default_trading_settings())
            applied = {}
            rejected = {}

            _key_map = {
                "default_stop_loss": "default_stop_loss_pct",
                "default_take_profit": "default_take_profit_pct",
            }

            for key, value in changes.items():
                setting_key = _key_map.get(key, key)
                clamped = ms._clamp_setting(key, value, profile)
                if clamped != value:
                    rejected[key] = f"{value} → {clamped} (안전 범위로 조정됨)"
                settings[setting_key] = clamped
                applied[key] = clamped

            ms._save_data("trading_settings", settings)

            # 변경 이력 기록
            from web.mini_server import load_setting, save_setting, save_activity_log, KST
            from datetime import datetime
            history = load_setting("trading_settings_history", [])
            history.append({
                "changed_at": datetime.now(KST).isoformat(),
                "changed_by": "CIO",
                "action": "도구를 통한 설정 변경",
                "detail": reason,
                "applied": applied,
                "rejected": rejected,
            })
            if len(history) > 100:
                history = history[-100:]
            save_setting("trading_settings_history", history)
            save_activity_log("cio_manager", f"⚙️ CIO 설정 변경: {', '.join(f'{k}={v}' for k, v in applied.items())} | {reason}", "info")

            result = f"✅ 설정 변경 완료 ({reason})\n\n"
            if applied:
                result += "**적용된 변경:**\n" + "\n".join(f"- {k}: {v}" for k, v in applied.items()) + "\n"
            if rejected:
                result += "\n**안전 범위 조정:**\n" + "\n".join(f"- {k}: {v}" for k, v in rejected.items()) + "\n"
            return result
        except Exception as e:
            return f"❌ 설정 변경 실패: {e}"

    async def _get_risk_profile(self) -> str:
        try:
            import importlib
            ms = importlib.import_module("web.mini_server")
            profile = ms._get_risk_profile()
            ranges = ms.RISK_PROFILES.get(profile, {})
            result = f"## 투자 성향: {ranges.get('label', profile)} {ranges.get('emoji', '')}\n\n"
            result += "| 항목 | 최소 | 기본 | 최대 |\n|------|------|------|------|\n"
            for key, vals in ranges.items():
                if isinstance(vals, dict) and "min" in vals:
                    result += f"| {key} | {vals['min']} | {vals['default']} | {vals['max']} |\n"
            return result
        except Exception as e:
            return f"❌ 성향 조회 실패: {e}"
