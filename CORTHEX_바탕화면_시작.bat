@echo off
chcp 65001 >nul
REM ============================================
REM CORTHEX HQ - 바탕화면 원클릭 시작
REM ============================================
REM 이 파일을 바탕화면에 두고 더블클릭하면
REM 자동으로 설치 확인 → 서버 시작됩니다.
REM ============================================
REM
REM 【사용법】
REM  1. 이 파일을 바탕화면에 복사하세요
REM  2. 아래 CORTHEX_DIR 경로를 본인의 프로젝트 폴더로 바꾸세요
REM  3. 더블클릭하면 끝!
REM ============================================

REM ★★★ 여기만 수정하세요! CORTHEX_HQ 폴더 경로 ★★★
REM 예시: C:\Users\동희\Documents\GitHub\CORTHEX_HQ
set "CORTHEX_DIR=C:\Users\%USERNAME%\Documents\GitHub\CORTHEX_HQ"

title CORTHEX HQ - CEO 관제실

echo.
echo   ╔══════════════════════════════════════════╗
echo   ║     CORTHEX HQ - 원클릭 시작 스크립트     ║
echo   ╚══════════════════════════════════════════╝
echo.

REM ── 1단계: 프로젝트 폴더 확인 ──
if not exist "%CORTHEX_DIR%" (
    echo   ❌ 프로젝트 폴더를 찾을 수 없습니다!
    echo.
    echo   현재 설정된 경로:
    echo   %CORTHEX_DIR%
    echo.
    echo   【해결 방법】
    echo   이 파일을 메모장으로 열어서
    echo   CORTHEX_DIR= 뒤의 경로를 본인의 폴더로 수정하세요.
    echo.
    echo   예시: C:\Users\동희\Documents\GitHub\CORTHEX_HQ
    echo.
    pause
    exit /b 1
)

cd /d "%CORTHEX_DIR%"
echo   [OK] 프로젝트 폴더 확인 완료
echo        %CORTHEX_DIR%
echo.

REM ── 2단계: Python 확인 ──
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   ❌ Python이 설치되어 있지 않습니다!
    echo.
    echo   아래 링크에서 Python을 먼저 설치해주세요:
    echo   https://www.python.org/downloads/
    echo.
    echo   설치할 때 "Add Python to PATH" 체크박스를 반드시 선택하세요!
    echo.
    pause
    exit /b 1
)
echo   [OK] Python 확인 완료

REM ── 3단계: 설치 확인 (처음이면 자동 설치) ──
if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo   ★ 처음 실행이네요! 자동 설치를 시작합니다...
    echo.

    echo   [1/3] 가상환경 만드는 중...
    python -m venv .venv
    echo         완료!

    echo   [2/3] 가상환경 활성화 중...
    call .venv\Scripts\activate.bat

    echo   [3/3] 필요한 프로그램 설치 중... (1~2분 걸릴 수 있어요)
    pip install --quiet --upgrade pip
    pip install --quiet -e .
    echo         완료!

    REM .env 파일 확인
    if not exist ".env" (
        if exist ".env.example" (
            copy .env.example .env >nul
            echo.
            echo   ==========================================
            echo   ⚠ 중요: API 키 설정이 필요합니다!
            echo.
            echo   1. .env 파일을 메모장으로 열어주세요
            echo   2. OPENAI_API_KEY= 뒤에 키를 붙여넣으세요
            echo   3. 저장한 후 이 파일을 다시 실행하세요
            echo   ==========================================
            echo.
            start notepad "%CORTHEX_DIR%\.env"
            pause
            exit /b 0
        )
    )

    echo.
    echo   ★ 설치가 완료되었습니다! 서버를 시작합니다...
    echo.
) else (
    echo   [OK] 설치 확인 완료 (이미 설치됨)
    call .venv\Scripts\activate.bat
)

REM ── 4단계: 서버 시작 ──
echo.
echo   ==========================================
echo      CORTHEX HQ 서버를 시작합니다!
echo.
echo      잠시 후 웹 브라우저가 자동으로 열립니다.
echo      종료하려면 이 창을 닫거나 Ctrl+C 를 누르세요.
echo   ==========================================
echo.

python run_web.py

pause
