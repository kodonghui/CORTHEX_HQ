@echo off
chcp 65001 >nul
REM ============================================
REM CORTHEX HQ - 서버 실행
REM ============================================
REM 이 파일을 더블클릭하면 서버가 시작됩니다.
REM ============================================

echo.
echo   ==========================================
echo      CORTHEX HQ 서버를 시작합니다
echo   ==========================================
echo.

REM 가상환경 확인 & 활성화
if not exist ".venv\Scripts\activate.bat" (
    echo   가상환경이 없습니다. setup.bat을 먼저 실행해주세요.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

REM 서버 시작
echo   웹 브라우저가 자동으로 열립니다.
echo   종료하려면 이 창을 닫거나 Ctrl+C 를 누르세요.
echo.

python run_web.py

pause
