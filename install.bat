@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "PYTHONUTF8=1"
cd /d "%~dp0"
set "MODEL=qwen3:4b-instruct"

echo ==================================================
echo  IP Finder 설치 (윈도우)
echo ==================================================
echo.

rem ---------- 1. Python 3.11 이상 찾기 ----------
set "PY="
for %%V in (3.12 3.11 3.13 3) do (
  if not defined PY (
    py -%%V -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [오류] Python 3.11 이상을 찾지 못했습니다.
  echo   https://www.python.org/downloads/windows/ 에서 Python 3.12 ^(64비트^)를 설치하세요.
  echo   설치 화면에서 "Add python.exe to PATH" 를 반드시 체크하세요.
  pause
  exit /b 1
)
for /f "delims=" %%I in ('%PY% -c "import sys; print(sys.version.split()[0])"') do set "PYVER=%%I"
echo [1/5] Python %PYVER% 사용

rem ---------- 2. 가상환경 ----------
if exist ".venv\Scripts\python.exe" (
  echo [2/5] 가상환경 있음 ^(.venv^)
) else (
  echo [2/5] 가상환경 생성 중...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [오류] 가상환경을 만들지 못했습니다.
    pause
    exit /b 1
  )
)
set "VPY=.venv\Scripts\python.exe"

rem ---------- 3. 패키지 설치 (wheels 폴더가 있으면 오프라인) ----------
if exist "wheels\*.whl" (
  echo [3/5] 오프라인 설치: wheels 폴더의 패키지 사용
  "%VPY%" -m pip install --no-index --find-links wheels -r requirements-windows.txt
) else (
  echo [3/5] 온라인 설치: PyPI에서 패키지 받기
  "%VPY%" -m pip install --upgrade pip >nul 2>&1
  "%VPY%" -m pip install -r requirements-windows.txt
)
if errorlevel 1 (
  echo.
  echo [오류] 패키지 설치에 실패했습니다.
  echo   인터넷이 막힌 PC라면: GitHub 릴리스 페이지의 wheel 번들^(zip^)을 받아 풀어 생긴 wheels 폴더를
  echo   이 폴더에 두거나, 인터넷이 되는 윈도우 PC에서 tools\download_wheels.bat 를 실행해 wheels 폴더를
  echo   만들어 복사한 뒤 install.bat 를 다시 실행하세요.
  pause
  exit /b 1
)

rem ---------- 4. Ollama와 모델 ----------
where ollama >nul 2>&1
if errorlevel 1 (
  echo.
  echo [4/5] Ollama가 설치되어 있지 않습니다.
  echo   https://ollama.com/download/windows 에서 설치한 뒤 install.bat 를 다시 실행하세요.
  pause
  exit /b 1
)
curl -s -o nul http://127.0.0.1:11434/api/tags 2>nul
if errorlevel 1 (
  echo [4/5] Ollama 서버 시작 중...
  start "Ollama" /min ollama serve
  timeout /t 6 /nobreak >nul
)
ollama list 2>nul | findstr /C:"%MODEL%" >nul
if errorlevel 1 (
  echo [4/5] 모델 %MODEL% 내려받는 중 ^(약 2.5GB^)...
  ollama pull %MODEL%
  if errorlevel 1 (
    echo.
    echo [오류] 모델을 받지 못했습니다.
    echo   인터넷이 막힌 PC라면 다른 PC에서 "ollama pull %MODEL%" 을 실행한 뒤
    echo   %%USERPROFILE%%\.ollama\models 폴더를 이 PC의 같은 위치로 복사하세요.
    pause
    exit /b 1
  )
) else (
  echo [4/5] 모델 %MODEL% 있음
)

rem ---------- 5. 확인 ----------
echo [5/5] 환경 확인
"%VPY%" -m ip_finder.cli check
echo.
echo 설치가 끝났습니다. 사용법:
echo   extract.bat 보고서.pptx           ^(파일이나 폴더를 extract.bat 위로 끌어다 놓아도 됩니다^)
echo   결과는 원본 옆에 "이름_검토후보.xlsx" 로 생깁니다.
echo.
pause
endlocal
