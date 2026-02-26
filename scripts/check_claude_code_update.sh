#!/bin/bash
# ─── Claude Code 업데이트 체크 → 텔레그램 알림 ───
# 크론: 매일 09:00 KST 실행
# 0 0 * * * /home/ubuntu/CORTHEX_HQ/scripts/check_claude_code_update.sh

set -euo pipefail

# 환경변수 로드
ENV_FILE="/home/ubuntu/corthex.env"
if [ -f "$ENV_FILE" ]; then
  source "$ENV_FILE"
fi

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${TELEGRAM_CEO_CHAT_ID:-}"
CACHE_FILE="/home/ubuntu/.claude_code_version_cache"

if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then
  echo "[ERROR] TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CEO_CHAT_ID 없음"
  exit 1
fi

# npm registry에서 최신 버전 조회
LATEST=$(curl -s "https://registry.npmjs.org/@anthropic-ai/claude-code/latest" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version',''))" 2>/dev/null)

if [ -z "$LATEST" ]; then
  echo "[ERROR] npm registry 조회 실패"
  exit 1
fi

# 이전 버전 읽기
PREV=""
if [ -f "$CACHE_FILE" ]; then
  PREV=$(cat "$CACHE_FILE")
fi

# 버전 비교
if [ "$LATEST" = "$PREV" ]; then
  echo "[OK] 변경 없음: v${LATEST}"
  exit 0
fi

# 변경 감지 — 체인지로그 가져오기
CHANGELOG=""
CHANGELOG_URL="https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md"
CHANGELOG=$(curl -s "$CHANGELOG_URL" | head -80 2>/dev/null || echo "")

# 메시지 생성
if [ -z "$PREV" ]; then
  MSG="🔔 *Claude Code 버전 추적 시작*

현재 최신: \`v${LATEST}\`
매일 09:00 KST 업데이트 체크합니다."
else
  MSG="🚀 *Claude Code 업데이트 감지!*

\`v${PREV}\` → \`v${LATEST}\`

📦 업데이트: \`npm update -g @anthropic-ai/claude-code\`
📋 변경로그: https://github.com/anthropics/claude-code/releases"

  # 체인지로그에서 새 버전 섹션 추출 (있으면)
  if [ -n "$CHANGELOG" ]; then
    SECTION=$(echo "$CHANGELOG" | sed -n "/## ${LATEST}/,/## [0-9]/p" | head -20 | sed '$d')
    if [ -n "$SECTION" ]; then
      MSG="${MSG}

\`\`\`
${SECTION}
\`\`\`"
    fi
  fi
fi

# 텔레그램 발송
curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -d chat_id="$CHAT_ID" \
  -d parse_mode="Markdown" \
  --data-urlencode "text=${MSG}" \
  > /dev/null

# 버전 캐시 업데이트
echo "$LATEST" > "$CACHE_FILE"

echo "[SENT] v${PREV:-없음} → v${LATEST}"
