"""Phase 3 반려/재작업 + Phase 12 협업 로그 테스트.

테스트 대상:
  - DB: save_collaboration_log / get_collaboration_logs / get_collaboration_summary
  - DB: get_quality_scores_timeline / get_top_rejection_reasons
  - DB: save_setting / load_setting (memory_categorized 패턴)
  - soul_evolution_handler: _extract_addition_text
"""
import sys
import os
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "web"))

# 테스트용 임시 DB 경로 설정
_TEST_DB = str(Path(__file__).parent / "_test_rework.db")
os.environ["CORTHEX_DB_PATH"] = _TEST_DB

from db import (
    init_db,
    save_setting,
    load_setting,
    save_quality_review,
    get_quality_scores_timeline,
    get_top_rejection_reasons,
    save_collaboration_log,
    get_collaboration_logs,
    get_collaboration_summary,
)


# ── 픽스처 ──

def setup_module():
    """테스트 모듈 시작 시 DB 초기화."""
    if os.path.exists(_TEST_DB):
        os.remove(_TEST_DB)
    init_db()


def teardown_module():
    """테스트 모듈 종료 시 임시 DB 삭제."""
    try:
        os.remove(_TEST_DB)
    except OSError:
        pass


# ── save_setting / load_setting (메모리 패턴) ──

def test_save_load_memory():
    """에이전트 메모리 저장/로드가 올바르게 작동하는지."""
    mem = {
        "ceo_preferences": "간결한 보고서 선호",
        "decisions": "매수 비중 30% 이하",
        "warnings": "02/25: Q4 반려 - 진입가 미명시",
    }
    save_setting("memory_categorized_test_agent", mem)
    loaded = load_setting("memory_categorized_test_agent", {})
    assert loaded["warnings"] == "02/25: Q4 반려 - 진입가 미명시"
    assert loaded["ceo_preferences"] == "간결한 보고서 선호"


def test_warnings_append():
    """반려 학습 warnings 누적 패턴이 올바른지."""
    mem = load_setting("memory_categorized_test_agent", {})
    prev = mem.get("warnings", "")
    new_lesson = "02/26: C3 반려 - 출처 미명시"
    mem["warnings"] = (
        (prev + " | " + new_lesson).strip(" |")
        if prev else new_lesson
    )
    save_setting("memory_categorized_test_agent", mem)

    reloaded = load_setting("memory_categorized_test_agent", {})
    assert "02/25:" in reloaded["warnings"]
    assert "02/26:" in reloaded["warnings"]
    assert " | " in reloaded["warnings"]


# ── quality_reviews 테스트 ──

def test_save_quality_review():
    """품질 검수 저장이 성공하는지."""
    rid = save_quality_review(
        chain_id="test_chain_1",
        reviewer_id="fin_analyst",
        target_id="stock_analysis_specialist",
        division="finance.investment",
        passed=True,
        weighted_score=3.5,
        scores_json='{"Q1": 4, "Q2": 3}',
        feedback="좋은 분석",
    )
    assert rid > 0


def test_save_quality_review_failed():
    """불합격 검수 저장 + 반려사유."""
    rid = save_quality_review(
        chain_id="test_chain_2",
        reviewer_id="fin_analyst",
        target_id="stock_analysis_specialist",
        division="finance.investment",
        passed=False,
        weighted_score=2.1,
        scores_json='{"Q1": 2, "Q4": 1}',
        rejection_reasons="Q4: 진입가/목표가 미명시",
    )
    assert rid > 0


def test_quality_scores_timeline():
    """타임라인 조회가 저장된 데이터를 반환하는지."""
    timeline = get_quality_scores_timeline(days=30)
    assert len(timeline) >= 2
    assert timeline[0]["target_id"] == "stock_analysis_specialist"


def test_quality_scores_timeline_filter():
    """에이전트 필터가 작동하는지."""
    timeline = get_quality_scores_timeline(days=30, agent_id="stock_analysis_specialist")
    assert all(t["target_id"] == "stock_analysis_specialist" for t in timeline)


def test_top_rejection_reasons():
    """반려 사유 Top N 조회."""
    reasons = get_top_rejection_reasons(limit=5)
    assert len(reasons) >= 1
    assert reasons[0]["target_id"] == "stock_analysis_specialist"


# ── collaboration_logs 테스트 ──

def test_save_collaboration_log():
    """협업 로그 저장이 성공하는지."""
    rid = save_collaboration_log(
        from_division="finance.investment",
        to_division="leet_master.marketing",
        from_agent="fin_analyst",
        to_agent="community_specialist",
        redirected_to="leet_marketer",
        task_summary="마케팅 데이터 요청",
    )
    assert rid > 0


def test_get_collaboration_logs():
    """협업 로그 조회."""
    logs = get_collaboration_logs(days=30, limit=10)
    assert len(logs) >= 1
    assert logs[0]["from_division"] == "finance.investment"
    assert logs[0]["to_division"] == "leet_master.marketing"


def test_get_collaboration_summary():
    """협업 빈도 요약."""
    summary = get_collaboration_summary(days=30)
    assert len(summary) >= 1
    assert summary[0]["from"] == "finance.investment"
    assert summary[0]["count"] >= 1


# ── _extract_addition_text 로직 테스트 (fastapi 의존 없이 직접 구현 복사) ──

def _extract_addition_text(proposed_change: str) -> str:
    """제안에서 '## 추가할 텍스트' 섹션만 추출합니다. (테스트용 복제)"""
    lines = proposed_change.split("\n")
    capture = False
    result = []
    for line in lines:
        if "추가할 텍스트" in line and line.strip().startswith("#"):
            capture = True
            continue
        if capture and line.strip().startswith("## "):
            break
        if capture:
            result.append(line)
    text = "\n".join(result).strip()
    if not text:
        text = f"<!-- Soul 진화 제안 -->\n{proposed_change}"
    return text


def test_extract_addition_text():
    """'## 추가할 텍스트' 섹션 추출이 올바른지."""
    proposed = """## 패턴 분석
반복적으로 진입가를 누락합니다.

## 추가할 텍스트
- [필수] 보고서에 진입가, 목표가, 손절가를 반드시 포함할 것
- 비중 제안 시 근거를 함께 제시

## 근거
Q4 반려가 3회 연속 발생"""

    result = _extract_addition_text(proposed)
    assert "진입가" in result
    assert "비중 제안" in result
    assert "패턴 분석" not in result
    assert "Q4 반려가 3회" not in result  # "## 근거" 섹션의 내용이 포함 안 되어야 함


def test_extract_addition_text_fallback():
    """추가할 텍스트 섹션이 없으면 폴백 처리."""
    proposed = "그냥 텍스트만 있는 경우"
    result = _extract_addition_text(proposed)
    assert "그냥 텍스트만 있는 경우" in result


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
