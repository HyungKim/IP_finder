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
if "%~2"=="" (
  echo Usage: ladder.bat RESULT_FOLDER REPORT_OR_FOLDER [more reports...] [--ladder ladders\switches.toml] [--mode single]
  echo   Example: ladder.bat results\ladder_switches D:\reports
  echo   Turns the switches on one by one (baseline first) and compares each step. Output: RESULT_FOLDER\ladder_*.xlsx + .md
  echo.
  pause
  exit /b 1
)
set "OUT=%~1"
shift
set "ARGS="
:loop
if "%~1"=="" goto run
set "ARGS=%ARGS% %1"
shift
goto loop
:run
".venv\Scripts\python.exe" -m ip_finder.cli ladder %ARGS% --out "%OUT%"
echo.
pause
exit /b %ERRORLEVEL%
