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
".venv\Scripts\python.exe" -c "import tkinter" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] tkinter is missing. Reinstall Python from python.org with "tcl/tk and IDLE" checked.
  echo.
  pause
  exit /b 1
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m ip_finder.ui
) else (
  ".venv\Scripts\python.exe" -m ip_finder.ui
)
