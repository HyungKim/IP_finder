@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
cd /d "%~dp0"

echo ==================================================
echo  IP Finder setup for Windows
echo  Korean messages start after Python is found.
echo ==================================================
echo.

rem ---- 1. find Python 3.11 or newer (py launcher first, then python) ----
set "PY="
for %%V in (3.12 3.11 3.13 3.14 3) do (
  if not defined PY (
    py -%%V -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [ERROR] Python 3.11 or newer was not found.
  echo   Install Python 3.12 64-bit from https://www.python.org/downloads/windows/
  echo   and check "Add python.exe to PATH" during setup. Then run install.bat again.
  echo.
  pause
  exit /b 1
)
echo [OK] Python found: %PY%

rem ---- 2. virtual environment ----
if not exist ".venv\Scripts\python.exe" (
  echo [..] Creating virtual environment .venv
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Could not create the virtual environment.
    echo.
    pause
    exit /b 1
  )
)

rem ---- 3. everything else runs in Python: packages, Ollama, model, check ----
".venv\Scripts\python.exe" tools\setup_windows.py %*
set "RC=%ERRORLEVEL%"
echo.
pause
exit /b %RC%
