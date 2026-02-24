"""Phase 2 스폰 필터링 테스트.

테스트 대상:
  - register_valid_agents(): 에이전트 등록 (dict + str 호환)
  - _resolve_agent_id(): 별칭 → 실제 ID 매핑
  - dormant 에이전트 차단
  - 같은 부서 직접 스폰 / 다른 부서 처장 리다이렉트
"""
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (import 해결)
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# 모듈 자체를 임포트 (global 재할당 추적을 위해)
import src.tools.cross_agent_protocol as cap


# ── 테스트 픽스처 ──

def _setup_test_agents():
    """테스트용 에이전트 환경 설정."""
    cap.register_valid_agents([
        # CIO 부서 (투자분석)
        {"agent_id": "cio_manager", "division": "finance.investment", "superior_id": "", "dormant": False},
        {"agent_id": "stock_analysis_specialist", "division": "finance.investment", "superior_id": "cio_manager", "dormant": False},
        {"agent_id": "technical_analysis_specialist", "division": "finance.investment", "superior_id": "cio_manager", "dormant": False},
        # CMO 부서 (마케팅)
        {"agent_id": "cmo_manager", "division": "leet_master.marketing", "superior_id": "", "dormant": False},
        {"agent_id": "community_specialist", "division": "leet_master.marketing", "superior_id": "cmo_manager", "dormant": False},
        # CTO 부서 (기술) — dormant
        {"agent_id": "cto_manager", "division": "leet_master.tech", "superior_id": "", "dormant": True},
        {"agent_id": "frontend_specialist", "division": "leet_master.tech", "superior_id": "cto_manager", "dormant": True},
    ])


# ── register_valid_agents 테스트 ──

def test_register_dict_agents():
    """dict 기반 등록 시 agent_id, division, dormant가 올바르게 저장되는지."""
    _setup_test_agents()
    assert "cio_manager" in cap._valid_agent_ids
    assert "stock_analysis_specialist" in cap._valid_agent_ids
    assert cap._agent_info["cio_manager"]["division"] == "finance.investment"
    assert cap._agent_info["cto_manager"]["dormant"] is True


def test_register_str_agents():
    """하위호환 str 등록 시 기본값으로 저장되는지."""
    cap.register_valid_agents(["agent_a", "agent_b"])
    assert "agent_a" in cap._valid_agent_ids
    assert cap._agent_info["agent_a"]["division"] == ""
    assert cap._agent_info["agent_a"]["dormant"] is False
    # 원래 테스트 에이전트로 복원
    _setup_test_agents()


# ── _resolve_agent_id 테스트 ──

def test_resolve_exact_id():
    """정확한 에이전트 ID는 그대로 반환."""
    _setup_test_agents()
    assert cap._resolve_agent_id("cio_manager") == "cio_manager"
    assert cap._resolve_agent_id("stock_analysis_specialist") == "stock_analysis_specialist"


def test_resolve_alias():
    """별칭(alias) 테이블이 올바르게 매핑되는지."""
    assert cap._AGENT_ALIAS.get("risk_manager") == "risk_management_specialist"
    assert cap._AGENT_ALIAS.get("fundamental_analyst") == "stock_analysis_specialist"


def test_resolve_partial_match():
    """부분 문자열 매칭이 작동하는지."""
    _setup_test_agents()
    resolved = cap._resolve_agent_id("stock_analysis")
    assert resolved == "stock_analysis_specialist"


def test_resolve_unknown_returns_original():
    """매핑 불가 ID는 원본 그대로 반환."""
    _setup_test_agents()
    assert cap._resolve_agent_id("totally_unknown_agent_xyz") == "totally_unknown_agent_xyz"


# ── dormant 차단 테스트 ──

def test_dormant_agent_info():
    """dormant 에이전트가 agent_info에 올바르게 표시되는지."""
    _setup_test_agents()
    assert cap._agent_info["cto_manager"]["dormant"] is True
    assert cap._agent_info["frontend_specialist"]["dormant"] is True
    assert cap._agent_info["cio_manager"]["dormant"] is False


# ── 부서 기반 라우팅 테스트 ──

def test_same_division_info():
    """같은 부서 에이전트 정보가 일치하는지."""
    _setup_test_agents()
    cio_div = cap._agent_info["cio_manager"]["division"]
    stock_div = cap._agent_info["stock_analysis_specialist"]["division"]
    assert cio_div == stock_div == "finance.investment"


def test_different_division_info():
    """다른 부서 에이전트 정보가 다른지."""
    _setup_test_agents()
    cio_div = cap._agent_info["cio_manager"]["division"]
    cmo_div = cap._agent_info["cmo_manager"]["division"]
    assert cio_div != cmo_div


def test_redirect_target_has_superior():
    """다른 부서 에이전트가 리다이렉트 대상의 처장(superior)을 가지는지."""
    _setup_test_agents()
    community_info = cap._agent_info["community_specialist"]
    assert community_info["superior_id"] == "cmo_manager"
    assert community_info["division"] == "leet_master.marketing"


def test_redirect_would_occur():
    """CIO→마케팅 요청 시 리다이렉트 조건이 성립하는지 검증."""
    _setup_test_agents()
    caller_div = cap._agent_info["cio_manager"]["division"]
    target_div = cap._agent_info["community_specialist"]["division"]
    target_superior = cap._agent_info["community_specialist"]["superior_id"]

    assert caller_div != target_div
    assert target_superior == "cmo_manager"
    assert target_superior in cap._valid_agent_ids
    assert not cap._agent_info[target_superior].get("dormant")


# ── 통합 시나리오 테스트 ──

def test_alias_table_coverage():
    """별칭 테이블의 모든 값이 유효한 에이전트 ID 형식인지."""
    for alias, real_id in cap._AGENT_ALIAS.items():
        assert isinstance(alias, str) and len(alias) > 0
        assert isinstance(real_id, str) and len(real_id) > 0
        assert real_id.endswith("_specialist") or real_id.endswith("_manager"), \
            f"별칭 '{alias}' → '{real_id}': 유효하지 않은 에이전트 ID 형식"


def test_agent_count():
    """등록된 에이전트 수가 정확한지."""
    _setup_test_agents()
    assert len(cap._valid_agent_ids) == 7
    assert len(cap._agent_info) == 7


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
