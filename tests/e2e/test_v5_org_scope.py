"""v5 org 스코프 E2E 테스트.

비유: 사무실에 CEO 출입증과 인턴(누나) 출입증이 따로 있는지 확인.
- sister 로그인 → saju org 데이터만 접근 가능
- CEO 로그인 → 전체 데이터 접근 가능
- org 필터 파라미터 → 서버가 올바르게 걸러주는지 검증

실행법:
  pytest tests/e2e/test_v5_org_scope.py -v
  E2E_SISTER_PASSWORD=내비번호 pytest tests/e2e/test_v5_org_scope.py -v
"""
import httpx
import pytest

from tests.e2e.conftest import BASE_URL, SISTER_PASSWORD


# ════════════════════════════════════════════
# 1. sister 로그인
# ════════════════════════════════════════════

class TestSisterLogin:
    def test_sister_login_success(self):
        """올바른 비밀번호로 sister 로그인하면 role=sister 토큰을 받아야 한다."""
        resp = httpx.post(
            f"{BASE_URL}/api/auth/login",
            json={"password": SISTER_PASSWORD, "role": "sister"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "token" in data
        assert data["user"]["role"] == "sister"

    def test_sister_login_wrong_password(self):
        """틀린 비밀번호로 sister 로그인 시 401을 받아야 한다."""
        resp = httpx.post(
            f"{BASE_URL}/api/auth/login",
            json={"password": "wrong_xyz_999", "role": "sister"},
            timeout=10,
        )
        assert resp.status_code == 401
        assert resp.json()["success"] is False

    def test_sister_auth_check(self, sister_client):
        """발급받은 sister 토큰으로 /api/auth/check 하면 authenticated=True여야 한다."""
        resp = sister_client.get("/api/auth/check")
        assert resp.status_code == 200
        data = resp.json()
        assert data["authenticated"] is True


# ════════════════════════════════════════════
# 2. 대화 세션 org 스코프 (FR-5)
# ════════════════════════════════════════════

class TestConversationOrgScope:
    _saju_conv_id = None

    def test_create_saju_conversation(self, client):
        """org=saju 대화 세션을 생성할 수 있어야 한다."""
        resp = client.post("/api/conversation/sessions", json={
            "title": "[E2E] saju 테스트 대화",
            "org": "saju",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "session" in data
        # API 응답: session.conversation_id (not id)
        TestConversationOrgScope._saju_conv_id = data["session"]["conversation_id"]

    def test_org_filter_returns_saju_only(self, client):
        """?org=saju 필터로 조회하면 방금 만든 saju 세션이 포함되어야 한다."""
        assert TestConversationOrgScope._saju_conv_id is not None, "이전 생성 테스트 먼저 실행 필요"
        resp = client.get("/api/conversation/sessions?org=saju&limit=50")
        assert resp.status_code == 200
        sessions = resp.json()
        assert isinstance(sessions, list)
        ids = [s["conversation_id"] for s in sessions]
        assert TestConversationOrgScope._saju_conv_id in ids, (
            f"생성한 saju 세션(id={TestConversationOrgScope._saju_conv_id})이 org 필터 결과에 없습니다"
        )

    def test_no_org_filter_returns_all(self, client):
        """org 필터 없이 조회하면 saju 세션도 포함해서 반환해야 한다."""
        assert TestConversationOrgScope._saju_conv_id is not None
        resp = client.get("/api/conversation/sessions?limit=100")
        assert resp.status_code == 200
        sessions = resp.json()
        ids = [s["conversation_id"] for s in sessions]
        assert TestConversationOrgScope._saju_conv_id in ids

    def test_cleanup_saju_conversation(self, client):
        """테스트용 saju 대화 세션 삭제."""
        if TestConversationOrgScope._saju_conv_id:
            resp = client.delete(f"/api/conversation/sessions/{TestConversationOrgScope._saju_conv_id}")
            assert resp.status_code == 200
            assert resp.json()["success"] is True


# ════════════════════════════════════════════
# 3. 기밀문서 org 스코프 (FR-6)
# ════════════════════════════════════════════

class TestArchiveOrgScope:
    def test_archive_org_filter_returns_list(self, client):
        """?org=saju 필터로 기밀문서 조회 시 리스트가 반환되어야 한다 (비어 있어도 OK)."""
        resp = client.get("/api/archive?org=saju")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_archive_org_filter_excludes_other_divisions(self, client):
        """?org=saju 필터로 조회 시 saju로 시작하지 않는 division은 포함되지 않아야 한다."""
        resp = client.get("/api/archive?org=saju")
        assert resp.status_code == 200
        docs = resp.json()
        for doc in docs:
            assert doc.get("division", "").startswith("saju"), (
                f"saju org 필터에 다른 division 문서가 포함됨: {doc.get('division')}"
            )

    def test_archive_no_filter_includes_all(self, client):
        """org 필터 없이 조회 시 모든 문서가 반환되어야 한다."""
        resp = client.get("/api/archive")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ════════════════════════════════════════════
# 4. SNS 계정 org 스코프 (FR-9)
# ════════════════════════════════════════════

class TestSNSAccountsOrgScope:
    def test_sns_accounts_saju_returns_instagram(self, client):
        """?org=saju 조회 시 사주냥 Instagram 계정이 반환되어야 한다."""
        resp = client.get("/api/sns/accounts?org=saju")
        assert resp.status_code == 200
        accounts = resp.json()
        assert isinstance(accounts, list)
        assert len(accounts) >= 1, "saju org에 SNS 계정이 없습니다"
        platforms = [a["platform"] for a in accounts]
        assert "instagram" in platforms, f"instagram 계정이 없습니다. 현재: {platforms}"

    def test_sns_accounts_all_org_returns_list(self, client):
        """org 필터 없이 조회해도 리스트가 반환되어야 한다."""
        resp = client.get("/api/sns/accounts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_sns_accounts_org_filter_correct(self, client):
        """?org=saju 결과는 모두 org=saju인 계정이어야 한다."""
        resp = client.get("/api/sns/accounts?org=saju")
        assert resp.status_code == 200
        for account in resp.json():
            assert account.get("org") == "saju", (
                f"saju 필터에 다른 org 계정이 포함됨: {account.get('org')}"
            )


# ════════════════════════════════════════════
# 5. 활동 로그 org 스코프 (FR-10)
# ════════════════════════════════════════════

class TestActivityLogOrgScope:
    def test_activity_logs_org_filter_returns_list(self, client):
        """?org=saju 활동 로그 조회 시 리스트가 반환되어야 한다 (비어 있어도 OK)."""
        resp = client.get("/api/activity-logs?org=saju&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_activity_logs_org_filter_saju_agents_only(self, client):
        """?org=saju 필터 결과는 모두 saju_ 접두사 에이전트 로그여야 한다."""
        resp = client.get("/api/activity-logs?org=saju&limit=50")
        assert resp.status_code == 200
        logs = resp.json()
        for log in logs:
            agent_id = log.get("agent_id", "")
            assert agent_id.startswith("saju"), (
                f"saju org 필터에 다른 에이전트 로그가 포함됨: {agent_id}"
            )

    def test_activity_logs_no_filter_accessible(self, client):
        """org 필터 없이 활동 로그 조회가 정상 동작해야 한다."""
        resp = client.get("/api/activity-logs?limit=5")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ════════════════════════════════════════════
# 6. sister 클라이언트 데이터 격리
# ════════════════════════════════════════════

class TestSisterDataIsolation:
    """sister 로그인 후 API 접근이 정상 동작하는지 확인."""

    def test_sister_can_access_sns_accounts(self, sister_client):
        """sister가 /api/sns/accounts?org=saju 조회할 수 있어야 한다."""
        resp = sister_client.get("/api/sns/accounts?org=saju")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_sister_can_access_activity_logs(self, sister_client):
        """sister가 /api/activity-logs?org=saju 조회할 수 있어야 한다."""
        resp = sister_client.get("/api/activity-logs?org=saju&limit=5")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_sister_can_access_archive(self, sister_client):
        """sister가 /api/archive?org=saju 조회할 수 있어야 한다."""
        resp = sister_client.get("/api/archive?org=saju")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_sister_can_access_conversation_sessions(self, sister_client):
        """sister가 /api/conversation/sessions?org=saju 조회할 수 있어야 한다."""
        resp = sister_client.get("/api/conversation/sessions?org=saju&limit=10")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
