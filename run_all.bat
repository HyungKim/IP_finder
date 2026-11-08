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
  echo Usage: run_all.bat RESULT_FOLDER REPORT_OR_FOLDER [more reports...] [--on SWITCH ...] [--classifier NAME]
  echo   Example: run_all.bat results\s0-baseline D:\reports
  echo            run_all.bat results\s1-all D:\reports --on all
  echo   Runs every report with one setting into RESULT_FOLDER. Compare two folders with compare_runs.bat.
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
".venv\Scripts\python.exe" -m ip_finder.cli run-all %ARGS% --out "%OUT%"
echo.
pause
exit /b %ERRORLEVEL%
