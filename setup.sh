#!/bin/bash
# ============================================
# CORTHEX HQ - 원클릭 설치 스크립트
# ============================================
# 이 스크립트를 실행하면 필요한 모든 것이 자동으로 설치됩니다.
#
# 실행 방법 (터미널에 아래 한 줄을 복사-붙여넣기):
#   bash setup.sh
# ============================================

set -e

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║     CORTHEX HQ 자동 설치를 시작합니다     ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# 1. Python 확인
echo "[1/4] Python 버전 확인 중..."
if command -v python3 &> /dev/null; then
    PY=python3
elif command -v python &> /dev/null; then
    PY=python
else
    echo "❌ Python이 설치되어 있지 않습니다!"
    echo ""
    echo "Python을 먼저 설치해주세요:"
    echo "  - Windows: https://www.python.org/downloads/ 에서 다운로드"
    echo "  - Mac: brew install python3"
    echo "  - Linux: sudo apt install python3 python3-pip"
    exit 1
fi

PY_VERSION=$($PY --version 2>&1)
echo "  ✅ $PY_VERSION"

# 2. 가상환경 생성
echo ""
echo "[2/4] 가상환경 생성 중..."
if [ ! -d ".venv" ]; then
    $PY -m venv .venv
    echo "  ✅ 가상환경 생성 완료"
else
    echo "  ✅ 가상환경이 이미 존재합니다"
fi

# 3. 가상환경 활성화 & 의존성 설치
echo ""
echo "[3/4] 의존성 설치 중... (1-2분 소요)"
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
fi

pip install --quiet --upgrade pip
pip install --quiet -e .
echo "  ✅ 모든 의존성 설치 완료"

# 4. .env 파일 생성
echo ""
echo "[4/4] 환경 설정 파일 확인 중..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  ⚠️  .env 파일이 생성되었습니다!"
    echo ""
    echo "  ╔══════════════════════════════════════════════════╗"
    echo "  ║  중요: .env 파일에 API 키를 입력해야 합니다!     ║"
    echo "  ║                                                  ║"
    echo "  ║  1. .env 파일을 메모장으로 열어주세요             ║"
    echo "  ║  2. OPENAI_API_KEY= 뒤에 키를 붙여넣으세요       ║"
    echo "  ║  3. 저장 후 run_web.py를 실행하세요              ║"
    echo "  ╚══════════════════════════════════════════════════╝"
else
    echo "  ✅ .env 파일이 이미 존재합니다"
fi

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║         🎉 설치가 완료되었습니다!         ║"
echo "  ╠══════════════════════════════════════════╣"
echo "  ║                                          ║"
echo "  ║  실행 방법:                               ║"
echo "  ║    python run_web.py                     ║"
echo "  ║                                          ║"
echo "  ║  그러면 웹 브라우저가 자동으로 열립니다.   ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""
