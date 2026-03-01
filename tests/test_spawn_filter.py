"""Phase 2 스폰 필터링 테스트.

테스트 대상:
  - register_valid_agents(): 에이전트 등록 (dict + str 호환)
  - _resolve_agent_id(): 별칭 → 실제 ID 매핑
  - 같은 부서 직접 스폰 / 다른 부서 팀장 리다이렉트
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
    """테스트용 에이전트 환경 설정 — 6명 팀장 체제."""
    cap.register_valid_agents([
        {"agent_id": "chief_of_staff", "division": "secretary", "superior_id": "", "dormant": False},
        {"agent_id": "leet_strategist", "division": "leet_master.strategy", "superior_id": "chief_of_staff", "dormant": False},
        {"agent_id": "leet_legal", "division": "leet_master.legal", "superior_id": "chief_of_staff", "dormant": False},
        {"agent_id": "leet_marketer", "division": "leet_master.marketing", "superior_id": "chief_of_staff", "dormant": False},
        {"agent_id": "fin_analyst", "division": "finance.investment", "superior_id": "chief_of_staff", "dormant": False},
        {"agent_id": "leet_publisher", "division": "publishing", "superior_id": "chief_of_staff", "dormant": False},
    ])


# ── register_valid_agents 테스트 ──

def test_register_dict_agents():
    """dict 기반 등록 시 agent_id, division, dormant가 올바르게 저장되는지."""
    _setup_test_agents()
    assert "fin_analyst" in cap._valid_agent_ids
    assert "leet_strategist" in cap._valid_agent_ids
    assert cap._agent_info["fin_analyst"]["division"] == "finance.investment"
    assert cap._agent_info["fin_analyst"]["dormant"] is False


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
    assert cap._resolve_agent_id("fin_analyst") == "fin_analyst"
    assert cap._resolve_agent_id("leet_marketer") == "leet_marketer"


def test_resolve_unknown_returns_original():
    """매핑 불가 ID는 원본 그대로 반환."""
    _setup_test_agents()
    assert cap._resolve_agent_id("totally_unknown_agent_xyz") == "totally_unknown_agent_xyz"


# ── 부서 기반 라우팅 테스트 ──

def test_different_division_info():
    """다른 부서 에이전트 정보가 다른지."""
    _setup_test_agents()
    cio_div = cap._agent_info["fin_analyst"]["division"]
    cmo_div = cap._agent_info["leet_marketer"]["division"]
    assert cio_div != cmo_div


def test_all_managers_active():
    """모든 팀장이 active(non-dormant) 상태인지."""
    _setup_test_agents()
    for aid in ["chief_of_staff", "leet_strategist", "leet_legal", "leet_marketer", "fin_analyst", "leet_publisher"]:
        assert cap._agent_info[aid]["dormant"] is False


# ── 통합 시나리오 테스트 ──

def test_alias_table_empty():
    """전문가 제거 후 별칭 테이블이 비어있는지."""
    assert len(cap._AGENT_ALIAS) == 0


def test_agent_count():
    """등록된 에이전트 수가 정확한지 — 6명."""
    _setup_test_agents()
    assert len(cap._valid_agent_ids) == 6
    assert len(cap._agent_info) == 6


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
