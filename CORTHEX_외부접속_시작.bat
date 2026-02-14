@echo off
chcp 65001 >nul 2>&1
REM ============================================
REM CORTHEX HQ - 외부 접속 (Cloudflare Tunnel)
REM ============================================
REM
REM 이 파일을 더블클릭하면:
REM   1. CORTHEX 서버가 시작됩니다
REM   2. 외부에서 접속할 수 있는 주소가 만들어집니다
REM   3. 그 주소를 아무 컴퓨터/핸드폰 브라우저에 치면 접속됩니다
REM
REM 종료하려면: 두 개의 검은 창을 모두 닫으세요 (또는 Ctrl+C)
REM ============================================

title CORTHEX HQ - 외부 접속

echo.
echo   ==========================================
echo     CORTHEX HQ - 외부 접속 시작
echo   ==========================================
echo.

REM -- 자동으로 컴퓨터 감지 (회사/개인) --
if exist "C:\Users\USER\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ" (
    set "CORTHEX_DIR=C:\Users\USER\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ"
    echo   [OK] 회사노트북 감지됨
) else if exist "C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ" (
    set "CORTHEX_DIR=C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ"
    echo   [OK] 개인노트북 감지됨
) else (
    echo   [실패] CORTHEX 폴더를 찾을 수 없습니다!
    echo.
    echo   이 파일을 메모장으로 열어서
    echo   위의 경로를 수정하세요.
    echo.
    pause
    exit /b 1
)
echo        %CORTHEX_DIR%
echo.

REM -- 1단계: cloudflared 설치 확인 --
cloudflared --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   ============================================================
    echo   [!] cloudflared 가 설치되어 있지 않습니다!
    echo.
    echo   아래 순서대로 설치해주세요 (1번만 하면 됩니다):
    echo.
    echo   1. 아래 주소를 브라우저에 복사해서 열기:
    echo      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.msi
    echo.
    echo   2. 다운로드된 파일 더블클릭해서 설치 (다음 다음 누르면 끝)
    echo.
    echo   3. 설치 끝나면 이 파일을 다시 더블클릭하세요!
    echo   ============================================================
    echo.
    pause
    exit /b 1
)
echo   [OK] cloudflared 설치 확인 완료
echo.

REM -- 2단계: Python 확인 --
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   [실패] Python이 설치되어 있지 않습니다!
    echo   https://www.python.org/downloads/ 에서 설치해주세요.
    pause
    exit /b 1
)
echo   [OK] Python 확인 완료
echo.

REM -- 3단계: 가상환경 확인 --
cd /d "%CORTHEX_DIR%"
if not exist ".venv\Scripts\activate.bat" (
    echo   [!] 가상환경이 없습니다. 먼저 CORTHEX_회사노트북_시작.bat 을
    echo       한 번 실행해서 초기 설치를 완료해주세요.
    echo.
    pause
    exit /b 1
)
echo   [OK] 가상환경 확인 완료
echo.

REM -- 4단계: CORTHEX 서버를 별도 창에서 시작 --
echo   [....] CORTHEX 서버 시작 중...
start "CORTHEX 서버" cmd /c "cd /d "%CORTHEX_DIR%" && call .venv\Scripts\activate.bat && python run_web.py"

REM 서버가 켜질 때까지 5초 대기
echo   [....] 서버가 켜질 때까지 5초 기다리는 중...
timeout /t 5 /nobreak >nul
echo   [OK] 서버 시작 완료
echo.

REM -- 5단계: Cloudflare Tunnel 시작 --
echo   ==========================================
echo     외부 접속 통로를 여는 중...
echo.
echo     아래에 접속 주소가 나옵니다!
echo     그 주소를 복사해서 아무 브라우저에 붙여넣으세요.
echo.
echo     (주소는 https://xxxxx.trycloudflare.com 형태입니다)
echo   ==========================================
echo.

cloudflared tunnel --url http://localhost:8000

REM -- 종료 시 --
echo.
echo   CORTHEX 외부 접속이 종료되었습니다.
echo   CORTHEX 서버 창도 닫아주세요.
echo.
pause
