@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run install.bat first.
  echo.
  pause
  exit /b 1
)
if "%~1"=="" (
  ".venv\Scripts\python.exe" -m ip_finder.cli extract --help
  echo.
  echo Drag and drop report files or folders onto extract.bat, or run: extract.bat report.pptx
  echo.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m ip_finder.cli extract %*
echo.
pause
exit /b %ERRORLEVEL%
