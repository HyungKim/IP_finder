@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 먼저 install.bat 를 실행하세요.
  pause
  exit /b 1
)
if "%~1"=="" (
  echo 사용법: extract.bat 파일또는폴더 [파일또는폴더 ...]
  echo   예:  extract.bat C:\보고서\3분기_개선보고.pptx
  echo        extract.bat C:\보고서\           ^(폴더 전체, 하위 폴더 포함^)
  echo   파일이나 폴더를 이 배치 파일 위로 끌어다 놓아도 됩니다.
  echo   결과: 원본 옆에 "이름_검토후보.xlsx"
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m ip_finder.cli extract %*
echo.
pause
endlocal
