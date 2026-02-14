#!/bin/bash
# ============================================
# CORTHEX HQ - 웹 세션 시작 시 .env 자동 생성
# ============================================
# GitHub Codespaces Secrets에 저장된 환경변수를 읽어서
# .env.local 파일을 자동으로 만들어주는 스크립트
#
# CEO가 할 일:
# 1. GitHub → Settings → Secrets → Codespaces 에 API 키 추가
# 2. 웹에서 Claude Code 세션을 열면 자동으로 .env.local 생성됨

ENV_FILE="$(git rev-parse --show-toplevel 2>/dev/null || echo '.')/.env.local"

# 이미 .env.local이 있으면 건너뛰기
if [ -f "$ENV_FILE" ]; then
    echo "[setup-env] .env.local 이미 존재합니다. 건너뜁니다."
    exit 0
fi

# 환경변수 목록 (GitHub Secrets에 등록된 이름과 동일해야 함)
ENV_VARS=(
    # 기본 설정
    "OPENAI_API_KEY"
    "ANTHROPIC_API_KEY"
    # 카카오
    "KAKAO_REST_API_KEY"
    "KAKAO_ID"
    "KAKAO_PW"
    # 네이버
    "NAVER_CLIENT_ID"
    "NAVER_CLIENT_SECRET"
    "NAVER_ID"
    "NAVER_PW"
    "NAVER_BLOG_ID"
    "NAVER_CAFE_CLUB_ID"
    "NAVER_CAFE_MENU_ID"
    # 구글/유튜브
    "GOOGLE_CLIENT_ID"
    "GOOGLE_CLIENT_SECRET"
    # 인스타그램
    "INSTAGRAM_APP_ID"
    "INSTAGRAM_APP_SECRET"
    "INSTAGRAM_USER_ID"
    # 링크드인
    "LINKEDIN_CLIENT_ID"
    "LINKEDIN_CLIENT_SECRET"
    "LINKEDIN_MEMBER_ID"
    # 다음 카페
    "DAUM_CAFE_ID"
    "DAUM_CAFE_BOARD_ID"
    # 텔레그램
    "TELEGRAM_BOT_TOKEN"
    "TELEGRAM_CEO_CHAT_ID"
    # 투자분석 (CIO)
    "DART_API_KEY"
    "ECOS_API_KEY"
    # 사업기획 (CSO)
    "PUBLIC_DATA_API_KEY"
    # 법무IP (CLO)
    "KIPRIS_API_KEY"
    "LAW_API_KEY"
    # 기술개발 (CTO)
    "GITHUB_TOKEN"
    # 출판기록 (CPO)
    "NOTION_API_KEY"
    "NOTION_DEFAULT_DB_ID"
    # 웹 검색
    "SERPAPI_KEY"
    # 이메일
    "SMTP_USER"
    "SMTP_PASS"
    "NOTIFICATION_EMAIL"
)

# 환경변수가 하나라도 있는지 확인
FOUND=0
for VAR in "${ENV_VARS[@]}"; do
    if [ -n "${!VAR}" ]; then
        FOUND=1
        break
    fi
done

if [ "$FOUND" -eq 0 ]; then
    echo "[setup-env] GitHub Secrets에 등록된 환경변수가 없습니다."
    echo "[setup-env] GitHub → Settings → Secrets → Codespaces 에서 API 키를 추가하세요."
    exit 0
fi

# .env.local 파일 생성
echo "# CORTHEX HQ - 자동 생성됨 ($(date '+%Y-%m-%d %H:%M:%S KST'))" > "$ENV_FILE"
echo "# GitHub Codespaces Secrets에서 불러온 환경변수" >> "$ENV_FILE"
echo "" >> "$ENV_FILE"

COUNT=0
for VAR in "${ENV_VARS[@]}"; do
    if [ -n "${!VAR}" ]; then
        echo "${VAR}=${!VAR}" >> "$ENV_FILE"
        COUNT=$((COUNT + 1))
    fi
done

# 고정값 추가 (Secrets에 안 넣어도 되는 것들)
cat >> "$ENV_FILE" << 'FIXED'

# 고정 설정값
DEFAULT_MODEL=gpt-4o-mini
MANAGER_MODEL=gpt-4o
SPECIALIST_MODEL=gpt-4o-mini
WORKER_MODEL=gpt-4o-mini
LOG_LEVEL=INFO
CORTHEX_AUTO_UPLOAD=1
GITHUB_REPO=kodonghui/CORTHEX_HQ
TELEGRAM_ENABLED=0
SNS_BROWSER_HEADLESS=true
GOOGLE_REDIRECT_URI=http://localhost:8000/oauth/callback/youtube
INSTAGRAM_REDIRECT_URI=http://localhost:8000/oauth/callback/instagram
LINKEDIN_REDIRECT_URI=http://localhost:8000/oauth/callback/linkedin
NAVER_REDIRECT_URI=http://localhost/callback
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
FIXED

echo "[setup-env] .env.local 생성 완료! (API 키 ${COUNT}개 로드됨)"
