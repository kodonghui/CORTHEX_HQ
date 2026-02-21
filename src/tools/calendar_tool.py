"""캘린더 도구 — Google Calendar 연동 (OAuth 방식)."""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.calendar_tool")

_GCAL_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_google_calendar():
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        return build, Credentials
    except ImportError:
        return None, None


def _load_calendar_creds():
    """DB에서 Google Calendar OAuth 인증 정보를 로드합니다."""
    try:
        web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "web")
        if web_dir not in sys.path:
            sys.path.insert(0, web_dir)
        from db import load_setting
        return load_setting("google_calendar_credentials")
    except Exception:
        return None


def _save_calendar_creds(creds_info: dict):
    """DB에 Google Calendar OAuth 인증 정보를 저장합니다."""
    try:
        web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "web")
        if web_dir not in sys.path:
            sys.path.insert(0, web_dir)
        from db import save_setting
        save_setting("google_calendar_credentials", creds_info)
    except Exception as e:
        logger.error("캘린더 인증 정보 DB 저장 실패: %s", e)


class CalendarTool(BaseTool):
    """Google Calendar 연동 — 일정 조회·생성·수정·삭제."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "list")
        if action == "list":
            return await self._list(kwargs)
        elif action == "create":
            return await self._create(kwargs)
        elif action == "update":
            return await self._update(kwargs)
        elif action == "delete":
            return await self._delete(kwargs)
        elif action == "search":
            return await self._search(kwargs)
        elif action == "free":
            return await self._free(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: list(조회), create(생성), update(수정), "
                "delete(삭제), search(검색), free(빈 시간)"
            )

    def _get_service(self):
        """Google Calendar API 서비스 생성 (DB 저장된 OAuth 토큰 사용)."""
        build, Credentials = _get_google_calendar()
        if build is None:
            return None, (
                "google-api-python-client 라이브러리가 설치되지 않았습니다.\n"
                "pip install google-api-python-client google-auth-oauthlib"
            )

        # DB에서 OAuth 토큰 로드
        creds_info = _load_calendar_creds()
        if not creds_info or not creds_info.get("refresh_token"):
            return None, (
                "Google Calendar 연동이 필요합니다.\n"
                "CEO님이 https://corthex-hq.com/api/google-calendar/setup 을 "
                "한 번 방문하여 Google 계정을 연결해주세요."
            )

        try:
            creds = Credentials(
                token=creds_info.get("token"),
                refresh_token=creds_info.get("refresh_token"),
                client_id=creds_info.get("client_id", os.getenv("GOOGLE_CLIENT_ID", "")),
                client_secret=creds_info.get("client_secret", os.getenv("GOOGLE_CLIENT_SECRET", "")),
                token_uri=creds_info.get("token_uri", "https://oauth2.googleapis.com/token"),
                scopes=_GCAL_SCOPES,
            )

            # 토큰 만료 시 자동 갱신
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                # 갱신된 토큰을 DB에 저장
                creds_info["token"] = creds.token
                _save_calendar_creds(creds_info)

            service = build("calendar", "v3", credentials=creds)
            return service, None
        except Exception as e:
            return None, f"Google Calendar 인증 실패: {e}"

    async def _list(self, kwargs: dict) -> str:
        """일정 조회."""
        service, err = self._get_service()
        if err:
            return err

        days = int(kwargs.get("days", 7))
        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days)).isoformat() + "Z"

        try:
            events_result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=50,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = events_result.get("items", [])

            if not events:
                return f"향후 {days}일간 일정이 없습니다."

            lines = [f"## 일정 목록 (향후 {days}일)\n"]
            lines.append("| 날짜/시간 | 일정 | 장소 |")
            lines.append("|---------|------|------|")

            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date", ""))
                summary = event.get("summary", "(제목 없음)")
                location = event.get("location", "-")
                # 시간 포맷팅
                if "T" in start:
                    dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    start_str = dt.strftime("%m/%d %H:%M")
                else:
                    start_str = start
                lines.append(f"| {start_str} | {summary} | {location} |")

            return "\n".join(lines)

        except Exception as e:
            return f"일정 조회 실패: {e}"

    async def _create(self, kwargs: dict) -> str:
        """새 일정 생성."""
        service, err = self._get_service()
        if err:
            return err

        title = kwargs.get("title", "")
        start = kwargs.get("start", "")
        end = kwargs.get("end", "")
        description = kwargs.get("description", "")
        location = kwargs.get("location", "")

        if not title or not start:
            return (
                "일정 생성에 필요한 인자:\n"
                "- title: 일정 제목\n"
                "- start: 시작 시간 (예: 2026-02-15T10:00:00+09:00)\n"
                "- end: 종료 시간 (선택, 기본 1시간)\n"
                "- description: 설명 (선택)\n"
                "- location: 장소 (선택)"
            )

        event_body = {
            "summary": title,
            "start": {"dateTime": start, "timeZone": "Asia/Seoul"},
            "description": description,
            "location": location,
        }

        if end:
            event_body["end"] = {"dateTime": end, "timeZone": "Asia/Seoul"}
        else:
            # 종료 시간 미지정 시 1시간 후
            try:
                start_dt = datetime.fromisoformat(start)
                end_dt = start_dt + timedelta(hours=1)
                event_body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Seoul"}
            except Exception:
                event_body["end"] = event_body["start"]

        try:
            event = service.events().insert(calendarId="primary", body=event_body).execute()
            event_id = event.get("id", "")
            link = event.get("htmlLink", "")
            return (
                f"## 일정 생성 완료\n\n"
                f"- 제목: {title}\n"
                f"- 시작: {start}\n"
                f"- 종료: {end or '1시간 후'}\n"
                f"- ID: {event_id}\n"
                f"- 링크: {link}"
            )
        except Exception as e:
            return f"일정 생성 실패: {e}"

    async def _update(self, kwargs: dict) -> str:
        """기존 일정 수정."""
        service, err = self._get_service()
        if err:
            return err

        event_id = kwargs.get("event_id", "")
        if not event_id:
            return "수정할 일정 ID(event_id)를 입력해주세요."

        try:
            event = service.events().get(calendarId="primary", eventId=event_id).execute()

            if "title" in kwargs:
                event["summary"] = kwargs["title"]
            if "start" in kwargs:
                event["start"] = {"dateTime": kwargs["start"], "timeZone": "Asia/Seoul"}
            if "end" in kwargs:
                event["end"] = {"dateTime": kwargs["end"], "timeZone": "Asia/Seoul"}
            if "description" in kwargs:
                event["description"] = kwargs["description"]
            if "location" in kwargs:
                event["location"] = kwargs["location"]

            updated = service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
            return f"## 일정 수정 완료\n\n- 제목: {updated.get('summary')}\n- ID: {event_id}"

        except Exception as e:
            return f"일정 수정 실패: {e}"

    async def _delete(self, kwargs: dict) -> str:
        """일정 삭제."""
        service, err = self._get_service()
        if err:
            return err

        event_id = kwargs.get("event_id", "")
        if not event_id:
            return "삭제할 일정 ID(event_id)를 입력해주세요."

        try:
            service.events().delete(calendarId="primary", eventId=event_id).execute()
            return f"## 일정 삭제 완료\n\n- ID: {event_id}"
        except Exception as e:
            return f"일정 삭제 실패: {e}"

    async def _search(self, kwargs: dict) -> str:
        """키워드로 일정 검색."""
        service, err = self._get_service()
        if err:
            return err

        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요."

        try:
            events_result = service.events().list(
                calendarId="primary",
                q=query,
                maxResults=20,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = events_result.get("items", [])

            if not events:
                return f"'{query}' 관련 일정을 찾을 수 없습니다."

            lines = [f"## 일정 검색: {query}\n"]
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date", ""))
                summary = event.get("summary", "(제목 없음)")
                event_id = event.get("id", "")
                lines.append(f"- **{summary}** ({start}) [ID: {event_id}]")

            return "\n".join(lines)

        except Exception as e:
            return f"일정 검색 실패: {e}"

    async def _free(self, kwargs: dict) -> str:
        """빈 시간대 조회."""
        service, err = self._get_service()
        if err:
            return err

        days = int(kwargs.get("days", 3))
        work_start = int(kwargs.get("work_start", 9))
        work_end = int(kwargs.get("work_end", 18))

        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days)).isoformat() + "Z"

        try:
            events_result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = events_result.get("items", [])

            return (
                f"## 빈 시간대 조회 (향후 {days}일)\n\n"
                f"- 업무 시간: {work_start}:00 ~ {work_end}:00\n"
                f"- 기존 일정: {len(events)}건\n\n"
                f"> 상세한 빈 시간 계산은 Google Calendar FreeBusy API로 구현 예정"
            )

        except Exception as e:
            return f"빈 시간 조회 실패: {e}"
