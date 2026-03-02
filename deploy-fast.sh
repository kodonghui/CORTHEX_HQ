#!/bin/bash
# ── CORTHEX 빠른 배포 스크립트 ──
# 사용법: bash deploy-fast.sh
# GitHub Actions(3분) 대신 SSH 직접 배포(30초)
# 단, env 파일은 갱신 안 됨 (새 API 키 추가 시엔 GitHub Actions 사용)

set -e

echo "🚀 빠른 배포 시작..."

# 1. 현재 브랜치가 main인지 확인
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
  echo "❌ main 브랜치에서만 실행하세요. 현재: $BRANCH"
  exit 1
fi

# 2. 로컬 변경사항 push
echo "📤 push 중..."
git push origin main

# 3. 서버에서 git pull + 재시작
echo "🖥️  서버 업데이트 중..."
ssh corthex-hq.com "
  cd /home/ubuntu/CORTHEX_HQ &&
  git fetch origin main &&
  git reset --hard origin/main &&
  echo '✅ 코드 업데이트 완료' &&
  sudo systemctl restart corthex &&
  echo '✅ 서버 재시작 완료'
"

# 4. 헬스체크
echo "🔍 헬스체크..."
sleep 3
curl -s https://corthex-hq.com/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('✅ 서버 정상:', d.get('status','?'))" 2>/dev/null || echo "⚠️ 헬스체크 실패 (서버 시작 중일 수 있음)"

echo "🎉 배포 완료!"
