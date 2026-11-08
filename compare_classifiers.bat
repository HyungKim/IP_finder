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
echo Compares all 7 first-stage classifiers on the gold sheets (data\gold by default) with cross-validation.
echo Output: classifier comparison xlsx + .md in the current folder (or --out PATH).
echo.
".venv\Scripts\python.exe" -m ip_finder.cli compare-classifiers %*
echo.
pause
exit /b %ERRORLEVEL%
