#!/bin/bash
# v5 에이전트 ID 리네임 스크립트
# 실행: bash scripts/rename_agents.sh (프로젝트 루트에서)
#
# 리네임 매핑:
#   cso_manager  → leet_strategist
#   clo_manager  → leet_legal
#   cmo_manager  → leet_marketer
#   cio_manager  → fin_analyst
#   cpo_manager  → leet_publisher

set -e

TARGETS=(
  "config/apply_souls.py"
  "config/quality_rules.yaml"
  "config/soul_gym_benchmarks.yaml"
  "config/tools.yaml"
  "config/workflows.yaml"
  "src/core/report_saver.py"
  "src/tools/log_analyzer.py"
  "src/tools/sns/sns_manager.py"
  "src/tools/trading_executor.py"
  "src/tools/trading_settings_control.py"
  "tests/test_rework.py"
  "tests/test_spawn_filter.py"
  "web/agent_router.py"
  "web/ai_handler.py"
  "web/config_loader.py"
  "web/handlers/argos_handler.py"
  "web/handlers/trading_handler.py"
  "web/soul_gym_engine.py"
  "web/static/js/corthex-app.js"
  "web/templates/index.html"
  "web/trading_engine.py"
)

for f in "${TARGETS[@]}"; do
  if [ -f "$f" ]; then
    sed -i \
      -e 's/\bcso_manager\b/leet_strategist/g' \
      -e 's/\bclo_manager\b/leet_legal/g' \
      -e 's/\bcmo_manager\b/leet_marketer/g' \
      -e 's/\bcio_manager\b/fin_analyst/g' \
      -e 's/\bcpo_manager\b/leet_publisher/g' \
      "$f"
    echo "✅ $f"
  else
    echo "⚠️  $f (없음, 스킵)"
  fi
done

# Soul 파일 리네임 (git mv)
git mv souls/agents/cso_manager.md souls/agents/leet_strategist.md 2>/dev/null && echo "✅ souls/agents/leet_strategist.md" || echo "⚠️  cso_manager.md 없음"
git mv souls/agents/clo_manager.md souls/agents/leet_legal.md 2>/dev/null && echo "✅ souls/agents/leet_legal.md" || echo "⚠️  clo_manager.md 없음"
git mv souls/agents/cmo_manager.md souls/agents/leet_marketer.md 2>/dev/null && echo "✅ souls/agents/leet_marketer.md" || echo "⚠️  cmo_manager.md 없음"
git mv souls/agents/cio_manager.md souls/agents/fin_analyst.md 2>/dev/null && echo "✅ souls/agents/fin_analyst.md" || echo "⚠️  cio_manager.md 없음"
git mv souls/agents/cpo_manager.md souls/agents/leet_publisher.md 2>/dev/null && echo "✅ souls/agents/leet_publisher.md" || echo "⚠️  cpo_manager.md 없음"

echo ""
echo "=== 검증 (결과 0줄이어야 배포 허용) ==="
grep -rn "cso_manager\|clo_manager\|cmo_manager\|cio_manager\|cpo_manager" \
  --include="*.py" --include="*.yaml" --include="*.html" --include="*.js" \
  --exclude-dir=".venv" --exclude-dir=".claude" --exclude-dir=".git" \
  "${TARGETS[@]}" souls/ 2>/dev/null || echo "✅ 레거시 ID 없음"
