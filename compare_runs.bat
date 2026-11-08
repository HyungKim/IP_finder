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
  echo Usage: compare_runs.bat RESULT_A RESULT_B [--out compare.xlsx] [--gold data\gold]
  echo   RESULT_A / RESULT_B: a *_result xlsx file or a folder of them (A = before, B = after).
  echo   Example: compare_runs.bat results\s0-baseline results\s1-all
  echo.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m ip_finder.cli compare-runs %*
echo.
pause
exit /b %ERRORLEVEL%
