"""CORTHEX 핵심 기능 E2E 테스트.

비유: 배포 전 체크리스트 자동화.
실서버(corthex-hq.com)에서 핵심 흐름 5개를 자동 검증한다.

실행법:
  # 기본 (기본 비밀번호 corthex2026)
  pytest tests/e2e/ -v

  # 비밀번호가 변경된 경우
  E2E_PASSWORD=내비밀번호 pytest tests/e2e/ -v
"""
import time
import httpx
import pytest

from tests.e2e.conftest import BASE_URL, TEST_PASSWORD


# ════════════════════════════════════════════
# 1. 로그인
# ════════════════════════════════════════════

class TestLogin:
    def test_login_success(self):
        """올바른 비밀번호로 로그인하면 토큰을 받아야 한다."""
        resp = httpx.post(
            f"{BASE_URL}/api/auth/login",
            json={"password": TEST_PASSWORD, "role": "ceo"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "token" in data
        assert data["user"]["role"] == "ceo"

    def test_login_wrong_password(self):
        """틀린 비밀번호로 로그인하면 401을 받아야 한다."""
        resp = httpx.post(
            f"{BASE_URL}/api/auth/login",
            json={"password": "wrong_password_xyz", "role": "ceo"},
            timeout=10,
        )
        assert resp.status_code == 401
        assert resp.json()["success"] is False

    def test_auth_check(self, client):
        """발급받은 토큰으로 /api/auth/check 하면 authenticated=True여야 한다."""
        resp = client.get("/api/auth/check")
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is True


# ════════════════════════════════════════════
# 2. 피드백 핀 저장 → 조회
# ════════════════════════════════════════════

class TestFeedbackPin:
    _pin_id = None  # 생성된 핀 ID (정리용)

    def test_save_pin(self, client):
        """피드백 핀을 저장하면 success=True와 id를 반환해야 한다."""
        resp = client.post("/api/feedback/ui", json={
            "x": 100,
            "y": 200,
            "tab": "home",
            "viewMode": "chat",
            "comment": "[E2E 테스트] 자동 생성 핀 - 무시하세요",
            "url": f"{BASE_URL}/",
            "screen": {"w": 1440, "h": 900},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "item" in data
        TestFeedbackPin._pin_id = data["item"]["id"]

    def test_pin_appears_in_list(self, client):
        """저장한 핀이 목록 조회에서 보여야 한다. (이게 버그 재현 테스트)"""
        assert TestFeedbackPin._pin_id is not None, "이전 테스트(저장)가 먼저 성공해야 합니다"
        resp = client.get("/api/feedback/ui")
        assert resp.status_code == 200
        data = resp.json()
        ids = [item["id"] for item in data.get("items", [])]
        assert TestFeedbackPin._pin_id in ids, (
            f"저장한 핀(id={TestFeedbackPin._pin_id})이 목록에 없습니다! "
            f"현재 목록 ids: {ids}"
        )

    def test_cleanup_pin(self, client):
        """테스트 핀 삭제."""
        if TestFeedbackPin._pin_id:
            resp = client.delete(f"/api/feedback/ui/{TestFeedbackPin._pin_id}")
            assert resp.status_code == 200


# ════════════════════════════════════════════
# 3. 에이전트 목록 확인
# ════════════════════════════════════════════

class TestAgents:
    def test_agents_loaded(self, client):
        """에이전트 목록이 존재해야 한다 (최소 1명)."""
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.json()
        agents = data if isinstance(data, list) else data.get("agents", [])
        assert len(agents) >= 1, "에이전트가 0명입니다"

    def test_dashboard_responds(self, client):
        """대시보드 API가 응답해야 한다."""
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200


# ════════════════════════════════════════════
# 4. 피드백 좋아요/아쉬워요 (응답 품질 피드백)
# ════════════════════════════════════════════

class TestFeedbackRating:
    def test_send_good_feedback(self, client):
        """좋아요 피드백 전송이 성공해야 한다."""
        resp = client.post("/api/feedback", json={
            "rating": "good",
            "action": "send",
            "task_id": "e2e_test",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["good"] >= 1

    def test_cancel_good_feedback(self, client):
        """좋아요 취소가 성공해야 한다."""
        resp = client.post("/api/feedback", json={
            "rating": "good",
            "action": "cancel",
            "task_id": "e2e_test",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_get_feedback_stats(self, client):
        """피드백 통계 조회가 성공해야 한다."""
        resp = client.get("/api/feedback")
        assert resp.status_code == 200
        data = resp.json()
        assert "good" in data
        assert "bad" in data
        assert "total" in data


# ════════════════════════════════════════════
# 5. 서버 헬스체크
# ════════════════════════════════════════════

class TestHealth:
    def test_server_online(self):
        """서버가 응답해야 한다."""
        resp = httpx.get(f"{BASE_URL}/api/health", timeout=10)
        assert resp.status_code == 200

    def test_activity_logs_accessible(self, client):
        """활동 로그 API가 응답해야 한다."""
        resp = client.get("/api/activity-logs?limit=1")
        assert resp.status_code == 200
