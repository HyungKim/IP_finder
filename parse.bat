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
  echo Usage: parse.bat REPORT_OR_FOLDER [more...]   (or drag and drop files onto parse.bat)
  echo   Writes NAME_parse-check.html next to each report and opens it in the browser.
  echo   Shows every page image next to the lines the reader extracted (layout analysis / raw), no classifier needed.
  echo.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m ip_finder.cli parse %* --open
echo.
pause
exit /b %ERRORLEVEL%
