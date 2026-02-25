# -*- coding: utf-8 -*-
"""
agents.yaml에서 specialist 블록을 전부 삭제하고
manager의 name/name_ko를 변경하는 스크립트
"""

YAML_PATH = r'c:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ\config\agents.yaml'

# Remove specialist agent IDs
SPECIALIST_IDS = {
    'report_specialist',
    'schedule_specialist',
    'relay_specialist',
    'frontend_specialist',
    'backend_specialist',
    'infra_specialist',
    'ai_model_specialist',
    'market_research_specialist',
    'business_plan_specialist',
    'financial_model_specialist',
    'copyright_specialist',
    'patent_specialist',
    'survey_specialist',
    'content_specialist',
    'community_specialist',
    'market_condition_specialist',
    'stock_analysis_specialist',
    'technical_analysis_specialist',
    'risk_management_specialist',
    'chronicle_specialist',
    'editor_specialist',
    'archive_specialist',
}

# Manager name/name_ko changes: {agent_id: (new_name, new_name_ko)}
MANAGER_RENAMES = {
    'cso_manager': ('Strategy Lead', '전략팀장'),
    'clo_manager': ('Legal Lead', '법무팀장'),
    'cmo_manager': ('Marketing Lead', '마케팅팀장'),
    'cio_manager': ('Investment Lead', '투자팀장'),
    'cpo_manager': ('Content Lead', '콘텐츠팀장'),
}


def main():
    with open(YAML_PATH, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Step 1: Find block boundaries
    block_starts = []
    for i, line in enumerate(lines):
        if line.startswith('- agent_id:'):
            agent_id = line.replace('- agent_id:', '').strip()
            block_starts.append((i, agent_id))

    print(f"Total agent blocks found: {len(block_starts)}")

    # Step 2: Build ranges to KEEP
    keep_ranges = []
    for idx, (start, agent_id) in enumerate(block_starts):
        end = block_starts[idx + 1][0] if idx + 1 < len(block_starts) else len(lines)
        if agent_id not in SPECIALIST_IDS:
            keep_ranges.append((start, end, agent_id))
        else:
            print(f"  REMOVING: {agent_id} (lines {start+1}-{end})")

    # Step 3: Build new content
    new_lines = ['agents:\n']  # First line always kept
    for start, end, agent_id in keep_ranges:
        new_lines.extend(lines[start:end])

    # Step 4: Rename managers
    # We need to do string replacement on the new content
    new_content = ''.join(new_lines)

    # Apply renames
    # Find each manager block and replace name/name_ko
    import re

    for agent_id, (new_name, new_name_ko) in MANAGER_RENAMES.items():
        # Match the block starting with this agent_id
        # Find the agent_id line and then name/name_ko lines
        pattern_name = rf'(- agent_id: {re.escape(agent_id)}\n  name: )[^\n]+'
        pattern_name_ko = None

        # We'll do it line by line in the block
        pass

    # Simpler approach: find and replace name/name_ko for each manager
    # We use a state machine approach
    result_lines = new_content.splitlines(keepends=True)
    in_target_agent = None
    name_done = False
    name_ko_done = False

    final_lines = []
    for line in result_lines:
        if line.startswith('- agent_id:'):
            current_id = line.replace('- agent_id:', '').strip()
            if current_id in MANAGER_RENAMES:
                in_target_agent = current_id
                name_done = False
                name_ko_done = False
            else:
                in_target_agent = None
            final_lines.append(line)
        elif in_target_agent and not name_done and line.startswith('  name: '):
            new_name, _ = MANAGER_RENAMES[in_target_agent]
            final_lines.append(f'  name: {new_name}\n')
            name_done = True
        elif in_target_agent and not name_ko_done and line.startswith('  name_ko: '):
            _, new_name_ko = MANAGER_RENAMES[in_target_agent]
            final_lines.append(f'  name_ko: {new_name_ko}\n')
            name_ko_done = True
        else:
            final_lines.append(line)

    final_content = ''.join(final_lines)

    with open(YAML_PATH, 'w', encoding='utf-8') as f:
        f.write(final_content)

    print("\nDone! Verifying remaining agents:")
    for line in final_lines:
        if line.startswith('- agent_id:'):
            agent_id = line.replace('- agent_id:', '').strip()
            print(f"  {agent_id}")


if __name__ == '__main__':
    main()
