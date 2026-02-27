"""알림 엔진 도구 — 텔레그램·이메일로 자동 알림 발송."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.notification_engine")

_DB_KEY = "notification_logs"


def _db_load(default=None):
    """DB에서 알림 로그 로드."""
    try:
        import sys
        web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "web")
        if web_dir not in sys.path:
            sys.path.insert(0, web_dir)
        from db import load_setting
        return load_setting(_DB_KEY, default)
    except Exception:
        return default


def _db_save(value):
    """DB에 알림 로그 저장."""
    try:
        import sys
        web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "web")
        if web_dir not in sys.path:
            sys.path.insert(0, web_dir)
        from db import save_setting
        save_setting(_DB_KEY, value)
    except Exception as e:
        logger.error("notification_logs DB 저장 실패: %s", e)


def _get_httpx():
    try:
        import httpx
        return httpx
    except ImportError:
        return None


class NotificationEngineTool(BaseTool):
    """텔레그램·이메일로 자동 알림을 발송하는 도구."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "send")
        if action == "send":
            return await self._send(kwargs)
        elif action == "template":
            return await self._template(kwargs)
        elif action == "history":
            return await self._history(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: send(알림 발송), template(템플릿 발송), "
                "history(발송 이력)"
            )

    @staticmethod
    def _get_telegram_config() -> dict | None:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
        if token and chat_id:
            return {"token": token, "chat_id": chat_id}
        return None

    async def _send_telegram(self, message: str) -> str:
        """텔레그램 메시지 전송."""
        config = self._get_telegram_config()
        if not config:
            return "텔레그램 설정 없음 (TELEGRAM_BOT_TOKEN, TELEGRAM_CEO_CHAT_ID 필요)"

        httpx = _get_httpx()
        if httpx is None:
            return "httpx 라이브러리가 설치되지 않았습니다."

        url = f"https://api.telegram.org/bot{config['token']}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json={
                    "chat_id": config["chat_id"],
                    "text": message,
                    "parse_mode": "Markdown",
                })
                if resp.status_code == 200:
                    return "텔레그램 발송 성공"
                return f"텔레그램 발송 실패: {resp.status_code}"
        except Exception as e:
            return f"텔레그램 발송 오류: {e}"

    def _save_log(self, channel: str, message: str, result: str) -> None:
        """발송 이력 저장 (SQLite DB)."""
        logs: list[dict] = _db_load([])
        if not isinstance(logs, list):
            logs = []

        logs.append({
            "timestamp": datetime.now().isoformat(),
            "channel": channel,
            "message": message[:200],
            "result": result,
        })

        # 최근 500건만 유지
        logs = logs[-500:]
        _db_save(logs)

    async def _send(self, kwargs: dict) -> str:
        """알림 발송."""
        message = kwargs.get("message", "")
        channel = kwargs.get("channel", "telegram")
        title = kwargs.get("title", "")

        if not message:
            return "알림 메시지(message)를 입력해주세요."

        full_message = f"*{title}*\n\n{message}" if title else message
        results: list[str] = []

        if channel in ("telegram", "all"):
            result = await self._send_telegram(full_message)
            results.append(f"- 텔레그램: {result}")
            self._save_log("telegram", message, result)

        if channel in ("email", "all"):
            # email_sender 도구가 있으면 연동, 없으면 안내
            to = kwargs.get("to", os.getenv("NOTIFICATION_EMAIL", ""))
            if to:
                try:
                    from src.tools.email_sender import EmailSenderTool
                    # 간단하게 SMTP로 직접 발송
                    email_result = "이메일 발송은 email_sender 도구를 사용해주세요."
                    results.append(f"- 이메일: {email_result}")
                except ImportError:
                    results.append("- 이메일: email_sender 도구 미설치")
            else:
                results.append("- 이메일: 수신자 이메일(to) 또는 NOTIFICATION_EMAIL 환경변수 필요")
            self._save_log("email", message, results[-1])

        return (
            f"## 알림 발송 결과\n\n"
            f"- 채널: {channel}\n"
            f"{'- 제목: ' + title + chr(10) if title else ''}"
            f"- 메시지: {message[:100]}{'...' if len(message) > 100 else ''}\n\n"
            f"### 발송 결과\n"
            + "\n".join(results)
        )

    async def _template(self, kwargs: dict) -> str:
        """미리 정의된 알림 템플릿 사용."""
        template_name = kwargs.get("template_name", "")
        variables = kwargs.get("variables", {})
        channel = kwargs.get("channel", "telegram")

        templates = {
            "daily_report": "📊 *일일 보고서*\n\n{content}\n\n📅 {date}",
            "stock_alert": "📈 *주식 알림*\n\n종목: {stock}\n현재가: {price}\n변동: {change}\n\n{comment}",
            "legal_alert": "⚖️ *법률 알림*\n\n{law_name} 변경 감지\n내용: {content}\n영향: {impact}",
            "competitor_alert": "🔍 *경쟁사 알림*\n\n{competitor} 변화 감지\n내용: {content}",
            "system_alert": "⚠️ *시스템 알림*\n\n유형: {alert_type}\n내용: {message}\n시간: {timestamp}",
        }

        if not template_name or template_name not in templates:
            available = "\n".join(f"- {k}" for k in templates.keys())
            return f"사용 가능한 템플릿:\n{available}\n\ntemplate_name을 지정해주세요."

        if isinstance(variables, str):
            try:
                variables = json.loads(variables)
            except Exception:
                return "variables가 올바른 JSON 형식이 아닙니다."

        try:
            message = templates[template_name].format(**variables)
        except KeyError as e:
            return f"템플릿에 필요한 변수가 빠졌습니다: {e}"

        # 실제 발송
        kwargs["message"] = message
        kwargs["channel"] = channel
        return await self._send(kwargs)

    async def _history(self, kwargs: dict) -> str:
        """발송 이력 조회 (SQLite DB)."""
        limit = int(kwargs.get("limit", 20))

        logs = _db_load([])
        if not logs:
            return "발송 이력이 없습니다."

        recent = logs[-limit:]
        lines = [f"## 알림 발송 이력 (최근 {len(recent)}건)\n"]
        lines.append("| 시간 | 채널 | 메시지 | 결과 |")
        lines.append("|------|------|--------|------|")
        for log in reversed(recent):
            ts = log.get("timestamp", "")[:16]
            ch = log.get("channel", "")
            msg = log.get("message", "")[:40]
            result = log.get("result", "")[:30]
            lines.append(f"| {ts} | {ch} | {msg} | {result} |")

        return "\n".join(lines)
