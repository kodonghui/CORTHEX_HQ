@echo off
chcp 65001 >nul
REM ============================================
REM CORTHEX HQ - Windows 원클릭 설치 스크립트
REM ============================================
REM 이 파일을 더블클릭하면 자동으로 설치됩니다.
REM ============================================

echo.
echo   ==========================================
echo      CORTHEX HQ 자동 설치를 시작합니다
echo   ==========================================
echo.

REM 1. Python 확인
echo [1/4] Python 버전 확인 중...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   ❌ Python이 설치되어 있지 않습니다!
    echo.
    echo   아래 링크에서 Python을 먼저 설치해주세요:
    echo   https://www.python.org/downloads/
    echo.
    echo   설치 시 "Add Python to PATH" 체크박스를 반드시 선택하세요!
    pause
    exit /b 1
)
python --version
echo   OK

REM 2. 가상환경 생성
echo.
echo [2/4] 가상환경 생성 중...
if not exist ".venv" (
    python -m venv .venv
    echo   가상환경 생성 완료
) else (
    echo   가상환경이 이미 존재합니다
)

REM 3. 가상환경 활성화 & 의존성 설치
echo.
echo [3/4] 의존성 설치 중... (1-2분 소요)
call .venv\Scripts\activate.bat
pip install --quiet --upgrade pip
pip install --quiet -e .
echo   모든 의존성 설치 완료

REM 4. .env 파일 생성
echo.
echo [4/4] 환경 설정 파일 확인 중...
if not exist ".env" (
    copy .env.example .env >nul
    echo.
    echo   ==========================================
    echo   중요: .env 파일에 API 키를 입력해야 합니다!
    echo.
    echo   1. .env 파일을 메모장으로 열어주세요
    echo   2. OPENAI_API_KEY= 뒤에 키를 붙여넣으세요
    echo   3. 저장 후 run_web.py를 실행하세요
    echo   ==========================================
) else (
    echo   .env 파일이 이미 존재합니다
)

echo.
echo   ==========================================
echo      설치가 완료되었습니다!
echo.
echo   실행 방법:
echo      python run_web.py
echo.
echo   그러면 웹 브라우저가 자동으로 열립니다.
echo   ==========================================
echo.
pause
