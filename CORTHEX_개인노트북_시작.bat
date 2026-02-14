@echo off
chcp 65001 >nul 2>&1
REM ============================================
REM CORTHEX HQ - 개인노트북 원클릭 시작
REM ============================================

REM CORTHEX_HQ 폴더 경로 (개인노트북용)
set "CORTHEX_DIR=C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ"

title CORTHEX HQ

echo.
echo   ==========================================
echo     CORTHEX HQ - 원클릭 시작 (개인노트북)
echo   ==========================================
echo.

REM -- 1단계: 프로젝트 폴더 확인 --
if not exist "%CORTHEX_DIR%" (
    echo   [실패] 프로젝트 폴더를 찾을 수 없습니다!
    echo.
    echo   현재 설정된 경로:
    echo   %CORTHEX_DIR%
    echo.
    echo   이 파일을 메모장으로 열어서
    echo   CORTHEX_DIR= 뒤의 경로를 수정하세요.
    echo.
    pause
    exit /b 1
)

cd /d "%CORTHEX_DIR%"
echo   [OK] 프로젝트 폴더 확인 완료
echo        %CORTHEX_DIR%
echo.

REM -- 2단계: Python 확인 --
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   [실패] Python이 설치되어 있지 않습니다!
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

REM -- 3단계: 설치 확인 (처음이면 자동 설치) --
if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo   * 처음 실행입니다. 자동 설치를 시작합니다...
    echo.

    echo   [1/3] 가상환경 만드는 중...
    python -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        echo   [실패] 가상환경 생성에 실패했습니다.
        pause
        exit /b 1
    )
    echo         완료!

    echo   [2/3] 가상환경 활성화 중...
    call .venv\Scripts\activate.bat

    echo   [3/3] 필요한 프로그램 설치 중... (1-2분 걸릴 수 있어요)
    python -m pip install --quiet --upgrade pip setuptools
    python -m pip install --quiet -e .
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo   [실패] 프로그램 설치 중 오류가 발생했습니다.
        echo   인터넷 연결을 확인하고 다시 시도해주세요.
        pause
        exit /b 1
    )
    echo         완료!

    REM .env.local 파일 확인 (.env.local 권장 - AnySign4PC가 .env를 잠글 수 있음)
    if not exist ".env.local" (
        if exist ".env.example" (
            copy .env.example .env.local >nul
            echo.
            echo   ==========================================
            echo   중요: API 키 설정이 필요합니다!
            echo.
            echo   1. .env.local 파일이 메모장으로 열립니다
            echo   2. OPENAI_API_KEY= 뒤에 키를 붙여넣으세요
            echo   3. 저장한 후 이 파일을 다시 실행하세요
            echo   ==========================================
            echo.
            start notepad "%CORTHEX_DIR%\.env.local"
            pause
            exit /b 0
        )
    )

    echo.
    echo   * 설치 완료! 서버를 시작합니다...
    echo.
) else (
    echo   [OK] 설치 확인 완료
    call .venv\Scripts\activate.bat

    REM 혹시 이전에 설치가 덜 됐을 경우를 대비해서 확인
    python -c "import uvicorn" >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo   [!] 일부 프로그램이 누락되어 재설치합니다...
        python -m pip install --quiet --upgrade pip setuptools
        python -m pip install --quiet -e .
    )
)

REM -- 4단계: 서버 시작 --
echo.
echo   ==========================================
echo     CORTHEX HQ 서버를 시작합니다!
echo.
echo     잠시 후 웹 브라우저가 자동으로 열립니다.
echo     종료하려면 이 창을 닫거나 Ctrl+C 를 누르세요.
echo   ==========================================
echo.

python run_web.py

pause
