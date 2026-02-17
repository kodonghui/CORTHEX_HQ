"""
apply_souls.py
새로운 Soul(system_prompt) 파일 4개를 agents.yaml에 적용하는 스크립트.

적용 대상 (총 28명):
  Group A: chief_of_staff, report_specialist, schedule_specialist, relay_specialist,
           cpo_manager, chronicle_specialist, editor_specialist, archive_specialist
  Group B: cio_manager, market_condition_specialist, stock_analysis_specialist,
           technical_analysis_specialist, risk_management_specialist
  Group C: cto_manager, frontend_specialist, backend_specialist, infra_specialist,
           ai_model_specialist, clo_manager, copyright_specialist, patent_specialist
  Group D: cso_manager, market_research_specialist, business_plan_specialist,
           financial_model_specialist, cmo_manager, survey_specialist, content_specialist

제외 (기존 Soul 유지):
  community_specialist (Soul 파일에 포함되지 않음)
"""

import yaml
import os
import sys
import io

# Windows 콘솔 UTF-8 강제 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

SOUL_FILES = {
    "A": os.path.join(PROJECT_ROOT, "docs", "updates", "new_souls_groupA.yaml"),
    "B": os.path.join(PROJECT_ROOT, "docs", "updates", "new_souls_groupB.yaml"),
    "C": os.path.join(PROJECT_ROOT, "docs", "updates", "new_souls_groupC.yaml"),
    "D": os.path.join(PROJECT_ROOT, "docs", "updates", "new_souls_groupD.yaml"),
}
AGENTS_YAML = os.path.join(BASE_DIR, "agents.yaml")


def load_soul_file(path, group_name):
    """YAML Soul 파일을 읽어서 {agent_id: system_prompt} 딕셔너리 반환"""
    print(f"  [읽기] Group {group_name}: {os.path.basename(path)}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        print(f"  [경고] Group {group_name} 파일이 비어있습니다!")
        return {}
    print(f"         → {len(data)}개 에이전트 Soul 로드")
    return data


def main():
    print("=" * 60)
    print("CORTHEX HQ Soul 적용 스크립트")
    print("=" * 60)

    # 1단계: 모든 Soul 파일 읽기
    print("\n[1단계] Soul 파일 읽기")
    all_new_souls = {}
    for group, path in SOUL_FILES.items():
        if not os.path.exists(path):
            print(f"  [오류] 파일 없음: {path}")
            sys.exit(1)
        souls = load_soul_file(path, group)
        # 중복 키 체크
        overlap = set(all_new_souls.keys()) & set(souls.keys())
        if overlap:
            print(f"  [경고] Group {group}에서 중복 agent_id 발견: {overlap}")
        all_new_souls.update(souls)

    print(f"\n  ✓ 총 {len(all_new_souls)}개 Soul 로드 완료")
    print(f"  로드된 agent_id 목록: {sorted(all_new_souls.keys())}")

    # 2단계: agents.yaml 읽기
    print(f"\n[2단계] agents.yaml 읽기: {AGENTS_YAML}")
    if not os.path.exists(AGENTS_YAML):
        print(f"  [오류] agents.yaml 없음: {AGENTS_YAML}")
        sys.exit(1)

    with open(AGENTS_YAML, "r", encoding="utf-8") as f:
        agents_data = yaml.safe_load(f)

    if agents_data is None or "agents" not in agents_data:
        print("  [오류] agents.yaml 구조가 올바르지 않습니다 (agents 키 없음)")
        sys.exit(1)

    total_agents = len(agents_data["agents"])
    print(f"  ✓ {total_agents}개 에이전트 발견")

    # 3단계: system_prompt 교체
    print("\n[3단계] system_prompt 교체")
    updated_count = 0
    skipped_count = 0
    not_found = []

    for agent in agents_data["agents"]:
        agent_id = agent.get("agent_id", "")
        if agent_id in all_new_souls:
            old_prompt_preview = (agent.get("system_prompt", "") or "")[:60].replace("\n", " ")
            agent["system_prompt"] = all_new_souls[agent_id]
            new_prompt_preview = all_new_souls[agent_id][:60].replace("\n", " ")
            print(f"  ✓ [{agent_id}] 교체 완료")
            print(f"       이전: {old_prompt_preview}...")
            print(f"       이후: {new_prompt_preview}...")
            updated_count += 1
        else:
            print(f"  - [{agent_id}] Soul 없음 → 기존 유지")
            skipped_count += 1

    # Soul 파일에 있지만 agents.yaml에 없는 agent_id 확인
    yaml_agent_ids = {a.get("agent_id") for a in agents_data["agents"]}
    for soul_id in all_new_souls.keys():
        if soul_id not in yaml_agent_ids:
            not_found.append(soul_id)

    if not_found:
        print(f"\n  [경고] Soul 파일에는 있으나 agents.yaml에 없는 agent_id: {not_found}")

    print(f"\n  교체 완료: {updated_count}개 / 기존 유지: {skipped_count}개")

    # 4단계: agents.yaml 저장
    print(f"\n[4단계] agents.yaml 저장")
    with open(AGENTS_YAML, "w", encoding="utf-8") as f:
        yaml.dump(
            agents_data,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            indent=2,
            width=10000,  # 긴 문자열이 줄바꿈되지 않도록
        )
    print(f"  ✓ 저장 완료: {AGENTS_YAML}")

    # 5단계: 결과 검증
    print(f"\n[5단계] 결과 검증 (저장된 파일 재읽기)")
    with open(AGENTS_YAML, "r", encoding="utf-8") as f:
        verify_data = yaml.safe_load(f)

    verified_count = 0
    for agent in verify_data["agents"]:
        agent_id = agent.get("agent_id", "")
        if agent_id in all_new_souls:
            stored_prompt = agent.get("system_prompt", "")
            expected_prompt = all_new_souls[agent_id]
            if stored_prompt.strip() == expected_prompt.strip():
                verified_count += 1
            else:
                print(f"  [경고] [{agent_id}] 저장 내용이 불일치!")

    print(f"  ✓ {verified_count}/{updated_count}개 검증 통과")

    print("\n" + "=" * 60)
    print(f"완료! {updated_count}개 에이전트 Soul 갱신 성공")
    print("=" * 60)
    return updated_count


if __name__ == "__main__":
    count = main()
    sys.exit(0 if count > 0 else 1)
