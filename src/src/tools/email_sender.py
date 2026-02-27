"""이메일 발송기 도구 — SMTP를 통한 이메일 자동 발송."""
from __future__ import annotations

import json
import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.email_sender")


def _get_aiosmtplib():
    try:
        import aiosmtplib
        return aiosmtplib
    except ImportError:
        return None


class EmailSenderTool(BaseTool):
    """이메일 자동 발송 도구 — 텍스트/HTML 이메일, 초안 작성, 대량 발송."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "send")
        if action == "send":
            return await self._send(kwargs)
        elif action == "draft":
            return await self._draft(kwargs)
        elif action == "template":
            return await self._template(kwargs)
        elif action == "bulk":
            return await self._bulk(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: send(발송), draft(초안 작성), "
                "template(템플릿 발송), bulk(대량 발송)"
            )

    @staticmethod
    def _get_smtp_config() -> dict | str:
        """SMTP 설정 로드. 성공 시 dict, 실패 시 에러 문자열."""
        host = os.getenv("SMTP_HOST", "")
        port = os.getenv("SMTP_PORT", "587")
        user = os.getenv("SMTP_USER", "")
        password = os.getenv("SMTP_PASS", "")

        if not host or not user or not password:
            return (
                "SMTP 설정이 필요합니다. .env에 다음을 추가하세요:\n"
                "SMTP_HOST=smtp.gmail.com\n"
                "SMTP_PORT=587\n"
                "SMTP_USER=your_email@gmail.com\n"
                "SMTP_PASS=your_app_password"
            )
        return {"host": host, "port": int(port), "user": user, "password": password}

    async def _send_email(self, to: str, subject: str, body: str, html: bool = False,
                          attachments: list[str] | None = None) -> str:
        """실제 이메일 발송 로직."""
        aiosmtplib = _get_aiosmtplib()
        if aiosmtplib is None:
            return "aiosmtplib 라이브러리가 설치되지 않았습니다. pip install aiosmtplib"

        config = self._get_smtp_config()
        if isinstance(config, str):
            return config

        msg = MIMEMultipart()
        msg["From"] = config["user"]
        msg["To"] = to
        msg["Subject"] = subject

        content_type = "html" if html else "plain"
        msg.attach(MIMEText(body, content_type, "utf-8"))

        # 첨부파일 처리
        if attachments:
            for filepath in attachments:
                if not os.path.isfile(filepath):
                    continue
                part = MIMEBase("application", "octet-stream")
                with open(filepath, "rb") as f:
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                filename = os.path.basename(filepath)
                part.add_header("Content-Disposition", f"attachment; filename={filename}")
                msg.attach(part)

        try:
            await aiosmtplib.send(
                msg,
                hostname=config["host"],
                port=config["port"],
                username=config["user"],
                password=config["password"],
                use_tls=True,
            )
            logger.info("이메일 발송 완료: %s → %s", subject, to)
            return f"이메일 발송 성공: {to}"
        except Exception as e:
            logger.error("이메일 발송 실패: %s", e)
            return f"이메일 발송 실패: {e}"

    async def _send(self, kwargs: dict) -> str:
        """단일 이메일 발송."""
        to = kwargs.get("to", "")
        subject = kwargs.get("subject", "")
        body = kwargs.get("body", "")
        html = kwargs.get("html", False)
        attachments = kwargs.get("attachments", [])

        if not to:
            return "수신자 이메일(to)을 입력해주세요."
        if not subject:
            return "제목(subject)을 입력해주세요."
        if not body:
            return "본문(body)을 입력해주세요."

        result = await self._send_email(to, subject, body, html, attachments)

        return (
            f"## 이메일 발송 결과\n\n"
            f"- 수신자: {to}\n"
            f"- 제목: {subject}\n"
            f"- 형식: {'HTML' if html else '텍스트'}\n"
            f"- 결과: {result}"
        )

    async def _draft(self, kwargs: dict) -> str:
        """AI가 이메일 초안 작성."""
        purpose = kwargs.get("purpose", "")
        recipient_type = kwargs.get("recipient_type", "일반")
        tone = kwargs.get("tone", "비즈니스")
        key_points = kwargs.get("key_points", "")

        if not purpose:
            return "이메일 목적(purpose)을 입력해주세요. 예: '프로젝트 진행 상황 보고'"

        draft = await self._llm_call(
            system_prompt=(
                "당신은 비즈니스 이메일 작성 전문가입니다. "
                "요청에 맞는 이메일 초안을 한국어로 작성하세요.\n"
                "형식: 제목, 인사, 본문, 마무리 인사를 포함하세요."
            ),
            user_prompt=(
                f"이메일 목적: {purpose}\n"
                f"수신자 유형: {recipient_type}\n"
                f"톤: {tone}\n"
                f"핵심 내용: {key_points}"
            ),
        )

        return f"## 이메일 초안\n\n{draft}\n\n---\n> 이 초안을 수정한 뒤 send action으로 발송할 수 있습니다."

    async def _template(self, kwargs: dict) -> str:
        """템플릿 기반 이메일 생성."""
        template_name = kwargs.get("template_name", "")
        variables = kwargs.get("variables", {})
        to = kwargs.get("to", "")

        templates = {
            "weekly_report": {
                "subject": "주간 보고서 - {date}",
                "body": "안녕하세요.\n\n{date} 기준 주간 보고서를 공유드립니다.\n\n{content}\n\n감사합니다.",
            },
            "newsletter": {
                "subject": "[CORTHEX] {title}",
                "body": "<h1>{title}</h1>\n<p>{content}</p>\n<hr>\n<p>CORTHEX HQ</p>",
            },
            "alert": {
                "subject": "[알림] {alert_type}: {message}",
                "body": "중요 알림\n\n유형: {alert_type}\n내용: {message}\n시간: {timestamp}",
            },
        }

        if not template_name or template_name not in templates:
            available = ", ".join(templates.keys())
            return f"사용 가능한 템플릿: {available}\ntemplate_name을 지정해주세요."

        if isinstance(variables, str):
            try:
                variables = json.loads(variables)
            except Exception:
                return "variables가 올바른 JSON 형식이 아닙니다."

        template = templates[template_name]
        subject = template["subject"].format(**variables)
        body = template["body"].format(**variables)

        if to:
            html = "<" in body
            result = await self._send_email(to, subject, body, html)
            return f"## 템플릿 이메일 발송\n\n- 템플릿: {template_name}\n- 수신자: {to}\n- 결과: {result}"

        return (
            f"## 템플릿 이메일 미리보기\n\n"
            f"**제목:** {subject}\n\n**본문:**\n{body}\n\n"
            f"> to 파라미터를 추가하면 바로 발송됩니다."
        )

    async def _bulk(self, kwargs: dict) -> str:
        """대량 이메일 발송."""
        recipients = kwargs.get("recipients", [])
        subject = kwargs.get("subject", "")
        body = kwargs.get("body", "")

        if isinstance(recipients, str):
            try:
                recipients = json.loads(recipients)
            except Exception:
                recipients = [r.strip() for r in recipients.split(",")]

        if not recipients:
            return "수신자 목록(recipients)을 입력해주세요. 예: [\"a@b.com\", \"c@d.com\"]"
        if not subject or not body:
            return "제목(subject)과 본문(body)을 입력해주세요."

        import asyncio
        results = []
        for i, to in enumerate(recipients):
            result = await self._send_email(to, subject, body)
            results.append(f"- {to}: {result}")
            if i < len(recipients) - 1:
                await asyncio.sleep(1)  # 레이트 리밋 방지

        success = sum(1 for r in results if "성공" in r)

        return (
            f"## 대량 발송 결과\n\n"
            f"- 총 수신자: {len(recipients)}명\n"
            f"- 성공: {success}명\n"
            f"- 실패: {len(recipients) - success}명\n\n"
            + "\n".join(results)
        )
