"""E2E 테스트 공통 설정.

비유: 테스트 출발 전 준비물 챙기기.
- BASE_URL: corthex-hq.com (실서버)
- auth_token: 테스트용 로그인 토큰 (CEO)
- sister_token: sister(누나) 로그인 토큰
"""
import os
import pytest
import httpx


BASE_URL = os.getenv("E2E_BASE_URL", "https://corthex-hq.com")
TEST_PASSWORD = os.getenv("E2E_PASSWORD", "corthex2026")
SISTER_PASSWORD = os.getenv("E2E_SISTER_PASSWORD", "sister2026")


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def auth_token():
    """세션 시작 시 1회 로그인 → 토큰 반환."""
    resp = httpx.post(
        f"{BASE_URL}/api/auth/login",
        json={"password": TEST_PASSWORD, "role": "ceo"},
        timeout=10,
    )
    assert resp.status_code == 200, f"로그인 실패: {resp.text}"
    data = resp.json()
    assert data.get("success"), f"로그인 실패: {data}"
    return data["token"]


@pytest.fixture(scope="session")
def client(auth_token):
    """인증 토큰이 자동으로 붙는 HTTP 클라이언트 (CEO)."""
    with httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=30,
    ) as c:
        yield c


@pytest.fixture(scope="session")
def sister_token():
    """sister 계정 로그인 → 토큰 반환."""
    resp = httpx.post(
        f"{BASE_URL}/api/auth/login",
        json={"password": SISTER_PASSWORD, "role": "sister"},
        timeout=10,
    )
    assert resp.status_code == 200, f"sister 로그인 실패: {resp.text}"
    data = resp.json()
    assert data.get("success"), f"sister 로그인 실패: {data}"
    return data["token"]


@pytest.fixture(scope="session")
def sister_client(sister_token):
    """sister 인증 토큰이 자동으로 붙는 HTTP 클라이언트."""
    with httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {sister_token}"},
        timeout=30,
    ) as c:
        yield c
