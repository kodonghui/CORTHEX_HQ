#!/bin/bash
# safety-guard.sh — 위험 명령 차단 훅
# PreToolUse Bash 훅으로 자동 실행

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

if [ -z "$COMMAND" ]; then
  exit 0
fi

# 절대 금지 패턴
BLOCKED_PATTERNS="git push --force.*main|git push --force.*master|git push -f.*main|git push -f.*master|rm -rf /|DROP DATABASE|TRUNCATE TABLE|git reset --hard.*main|git reset --hard.*master"

if echo "$COMMAND" | grep -E "$BLOCKED_PATTERNS" > /dev/null 2>&1; then
  echo "🚨 [safety-guard] 위험 명령 감지됨. 대표님 명시적 승인 필요." >&2
  echo "명령: $COMMAND" >&2
  exit 2
fi

exit 0
