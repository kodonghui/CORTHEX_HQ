@echo off
REM ============================================
REM CORTHEX HQ - 원클릭 시작 (모든 컴퓨터 공용)
REM ============================================

REM 이 bat파일이 있는 폴더로 이동 (pushd가 가장 안정적)
pushd "%~dp0"
set "CORTHEX_DIR=%CD%"

REM 한글 표시를 위한 UTF-8 설정 (폴더 이동 후에 해야 안전)
chcp 65001 >nul 2>&1

title CORTHEX HQ

echo.
echo   ==========================================
echo     CORTHEX HQ - 원클릭 시작
echo   ==========================================
echo.

REM -- 1단계: 프로젝트 폴더 확인 --
if not exist "%CORTHEX_DIR%\pyproject.toml" (
    echo   [실패] 프로젝트 폴더를 찾을 수 없습니다!
    echo.
    echo   이 bat 파일을 CORTHEX_HQ 폴더 안에 넣어주세요.
    echo   ^(pyproject.toml 파일이 있는 폴더^)
    echo.
    pause
    popd
    exit /b 1
)
echo   [OK] 프로젝트 폴더 확인 완료
echo        %CORTHEX_DIR%
echo.

REM -- 2단계: 호환되는 Python 찾기 (3.13 → 3.12 → 3.11 순서) --
set "PYTHON_CMD="
set "PY_VER="

REM py 런처로 3.13 확인
py -3.13 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=py -3.13"
    goto :get_py_ver
)

REM py 런처로 3.12 확인
py -3.12 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=py -3.12"
    goto :get_py_ver
)

REM py 런처로 3.11 확인
py -3.11 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=py -3.11"
    goto :get_py_ver
)

REM py 런처가 없으면 기본 python 확인
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 goto :install_python

REM 기본 python 버전이 호환되는지 확인 (3.11~3.13)
python -c "import sys; exit(0 if (3,11) <= sys.version_info < (3,14) else 1)" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=python"
    goto :get_py_ver
)

REM -- 호환 버전 없음: Python 3.13 자동 설치 --
:install_python
echo   [!] 호환되는 Python(3.11~3.13)을 찾지 못했습니다.
echo.
echo   Python 3.13을 자동으로 설치합니다...
echo   (약 30MB 다운로드, 1~2분 걸릴 수 있어요)
echo.

set "PY_INSTALLER=%TEMP%\python-3.13.1-amd64.exe"

REM 다운로드 시도 (curl → PowerShell 순서)
curl -L -o "%PY_INSTALLER%" "https://www.python.org/ftp/python/3.13.1/python-3.13.1-amd64.exe" 2>nul
if not exist "%PY_INSTALLER%" (
    echo   curl 실패, PowerShell로 재시도...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.1/python-3.13.1-amd64.exe' -OutFile '%PY_INSTALLER%'" 2>nul
)

if not exist "%PY_INSTALLER%" (
    echo   [실패] Python 다운로드에 실패했습니다.
    echo   인터넷 연결을 확인하세요.
    echo.
    echo   수동 설치: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo   다운로드 완료! 설치 중... (진행 바가 나타납니다)
"%PY_INSTALLER%" /passive InstallAllUsers=0 PrependPath=1 Include_launcher=1
if %ERRORLEVEL% NEQ 0 (
    echo   [실패] Python 설치에 실패했습니다.
    del "%PY_INSTALLER%" >nul 2>&1
    pause
    exit /b 1
)
del "%PY_INSTALLER%" >nul 2>&1

echo   [OK] Python 3.13 설치 완료!
echo.

REM 새로 설치된 Python 찾기
set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if exist "%PYTHON_CMD%" goto :get_py_ver

REM py 런처로 다시 시도
py -3.13 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=py -3.13"
    goto :get_py_ver
)

echo   [!] Python을 설치했지만 바로 인식이 안 됩니다.
echo   이 창을 닫고 다시 더블클릭해주세요.
echo.
pause
exit /b 0

:get_py_ver
for /f "tokens=2" %%v in ('%PYTHON_CMD% --version 2^>^&1') do set "PY_VER=%%v"

:python_ok
echo   [OK] Python %PY_VER% 확인 완료
echo.

REM -- 2.5단계: 호환되지 않는 Python 3.14 자동 제거 --
py -3.14 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   [!] 호환되지 않는 Python 3.14 발견 - 자동 제거 중...
    powershell -ExecutionPolicy Bypass -Command "& { $paths = @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'); foreach($p in $paths) { Get-ItemProperty $p -EA SilentlyContinue | Where-Object {$_.DisplayName -like 'Python 3.14*'} | ForEach-Object { if($_.QuietUninstallString) { Start-Process cmd.exe -ArgumentList '/c', $_.QuietUninstallString -Wait -WindowStyle Hidden } } } }" >nul 2>&1
    py -3.14 --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo   [!] 자동 제거가 안 됩니다. (관리자 권한 필요)
        echo       Windows 설정 → 앱 → 'Python 3.14' 검색 → 제거 해주세요.
    ) else (
        echo   [OK] Python 3.14 제거 완료
    )
    echo.
)

REM -- 3단계: 가상환경 확인 --
REM 기존 가상환경이 호환되지 않는 Python이면 삭제 후 다시 만들기
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -c "import sys; exit(0 if (3,11) <= sys.version_info < (3,14) else 1)" >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo   [!] 기존 가상환경이 호환되지 않는 Python 버전입니다.
        echo   [!] 가상환경을 새로 만듭니다...
        echo.
        rmdir /s /q .venv >nul 2>&1
    )
)

if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo   * 처음 실행입니다. 자동 설치를 시작합니다...
    echo.

    echo   [1/3] 가상환경 만드는 중...
    %PYTHON_CMD% -m venv .venv
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

popd
pause
