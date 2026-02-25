import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('c:/Users/elddl/Desktop/PJ0_CORTHEX/CORTHEX_HQ/CORTHEX_HQ/config/agents.yaml', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find block boundaries (1-indexed line numbers)
block_starts = []
for i, line in enumerate(lines):
    if line.startswith('- agent_id:'):
        agent_id = line.replace('- agent_id:', '').strip()
        block_starts.append((i, agent_id))

print('Total agent blocks found:', len(block_starts))
for idx, (line_num, agent_id) in enumerate(block_starts):
    end_line = block_starts[idx+1][0] if idx+1 < len(block_starts) else len(lines)
    print(f'  lines {line_num+1}-{end_line}: {agent_id}')
