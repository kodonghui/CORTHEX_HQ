"""
사용자 인증 + 권한 관리.

부트스트랩 모드: 사용자가 0명이면 인증 없이 모든 기능 사용 가능 (기존과 동일).
사용자가 1명 이상 등록되면 인증 활성화.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("corthex.auth")

# JWT 대용 간단 토큰 (외부 라이브러리 의존 없이)
_TOKEN_SECRET = secrets.token_hex(32)


class User:
    """사용자 정보."""

    def __init__(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        role: str = "viewer",  # ceo, manager, viewer
        division: str = "",
        display_name: str = "",
    ) -> None:
        self.user_id = user_id
        self.username = username
        self.password_hash = password_hash
        self.role = role
        self.division = division
        self.display_name = display_name or username

    def to_dict(self, include_hash: bool = False) -> dict:
        d = {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "division": self.division,
            "display_name": self.display_name,
        }
        if include_hash:
            d["password_hash"] = self.password_hash
        return d

    @classmethod
    def from_dict(cls, d: dict) -> User:
        return cls(
            user_id=d.get("user_id", str(uuid.uuid4())[:8]),
            username=d["username"],
            password_hash=d["password_hash"],
            role=d.get("role", "viewer"),
            division=d.get("division", ""),
            display_name=d.get("display_name", d["username"]),
        )


def _hash_password(password: str) -> str:
    """SHA-256 기반 간단 해시 (bcrypt 없이)."""
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{h}"


def _verify_password(password: str, stored_hash: str) -> bool:
    parts = stored_hash.split(":", 1)
    if len(parts) != 2:
        return False
    salt, expected = parts
    h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return hmac.compare_digest(h, expected)


def _create_token(user: User) -> str:
    """간단한 HMAC 기반 토큰 생성."""
    payload = f"{user.user_id}:{user.username}:{user.role}:{int(time.time()) + 86400 * 7}"
    sig = hmac.new(_TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}:{sig}"


def _verify_token(token: str) -> Optional[dict]:
    """토큰 검증 → 사용자 정보 반환."""
    parts = token.rsplit(":", 1)
    if len(parts) != 2:
        return None
    payload, sig = parts
    expected_sig = hmac.new(_TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(sig, expected_sig):
        return None
    fields = payload.split(":")
    if len(fields) != 4:
        return None
    user_id, username, role, exp_str = fields
    try:
        if int(exp_str) < int(time.time()):
            return None  # 토큰 만료
    except ValueError:
        return None
    return {"user_id": user_id, "username": username, "role": role}


class AuthManager:
    """사용자 인증 관리자."""

    def __init__(self, data_path: Path) -> None:
        self._data_path = data_path
        self._users: list[User] = []
        self._load()

    def _load(self) -> None:
        if not self._data_path.exists():
            self._users = []
            return
        try:
            raw = json.loads(self._data_path.read_text(encoding="utf-8"))
            self._users = [User.from_dict(u) for u in raw]
        except Exception as e:
            logger.warning("사용자 데이터 로드 실패: %s", e)
            self._users = []

    def _save(self) -> None:
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        self._data_path.write_text(
            json.dumps([u.to_dict(include_hash=True) for u in self._users],
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def bootstrap_mode(self) -> bool:
        """사용자가 0명이면 부트스트랩 모드 (인증 불필요)."""
        return len(self._users) == 0

    def register(
        self,
        username: str,
        password: str,
        role: str = "viewer",
        division: str = "",
        display_name: str = "",
    ) -> dict:
        """새 사용자 등록."""
        # 중복 체크
        if any(u.username == username for u in self._users):
            return {"error": "이미 존재하는 사용자명입니다"}

        # 첫 번째 사용자는 자동으로 CEO
        if len(self._users) == 0:
            role = "ceo"

        user = User(
            user_id=str(uuid.uuid4())[:8],
            username=username,
            password_hash=_hash_password(password),
            role=role,
            division=division,
            display_name=display_name or username,
        )
        self._users.append(user)
        self._save()
        logger.info("사용자 등록: %s (역할: %s)", username, role)

        token = _create_token(user)
        return {"success": True, "token": token, "user": user.to_dict()}

    def login(self, username: str, password: str) -> dict:
        """로그인."""
        for u in self._users:
            if u.username == username:
                if _verify_password(password, u.password_hash):
                    token = _create_token(u)
                    return {"success": True, "token": token, "user": u.to_dict()}
                return {"error": "비밀번호가 틀렸습니다"}
        return {"error": "존재하지 않는 사용자입니다"}

    def verify_token(self, token: str) -> Optional[dict]:
        """토큰 검증."""
        return _verify_token(token)

    def get_status(self) -> dict:
        """인증 상태."""
        return {
            "bootstrap_mode": self.bootstrap_mode,
            "user_count": len(self._users),
            "users": [u.to_dict() for u in self._users],
        }

    def check_permission(self, token_info: dict, action: str, division: str = "") -> bool:
        """권한 확인."""
        role = token_info.get("role", "viewer")

        if role == "ceo":
            return True  # CEO는 모든 권한

        if role == "manager":
            if action in ("execute_command", "view_tasks"):
                # Manager는 자기 부서만
                user = next((u for u in self._users if u.user_id == token_info.get("user_id")), None)
                if user and user.division and division:
                    return user.division == division
                return True  # 부서 미지정이면 허용
            if action in ("manage_presets", "manage_schedules", "manage_workflows", "manage_agents"):
                return False
            return True  # 기타 읽기 허용

        if role == "viewer":
            if action in ("view_tasks", "view_performance", "view_dashboard"):
                return True
            return False

        return False
