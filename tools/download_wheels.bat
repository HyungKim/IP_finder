@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
rem 인터넷이 되는 윈도우 PC에서 실행합니다. 회사 PC와 같은 Python 버전(기본 3.12, 64비트)의 wheel을 wheels\ 폴더에 모읍니다.
rem 사용: tools\download_wheels.bat [파이썬버전]   예: tools\download_wheels.bat 3.12
set "PYVER=%~1"
if "%PYVER%"=="" set "PYVER=3.12"
echo Python %PYVER% / win_amd64 용 wheel을 wheels\ 에 내려받습니다...
py -3 -m pip download -r requirements-windows.txt -d wheels --only-binary=:all: --platform win_amd64 --python-version %PYVER% --implementation cp
if errorlevel 1 (
  echo [오류] 다운로드에 실패했습니다. 인터넷 연결과 Python 설치를 확인하세요.
  pause
  exit /b 1
)
echo.
echo 완료. wheels 폴더를 회사 PC의 IP_finder 폴더에 복사한 뒤 install.bat 를 실행하세요.
pause
endlocal
