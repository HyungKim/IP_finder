@echo off
setlocal
cd /d "%~dp0.."
rem Run this on a Windows PC with internet access. It collects wheels for the
rem company PC into the wheels\ folder. Default target: Python 3.12, 64-bit.
rem Usage: tools\download_wheels.bat [python-version]   e.g. tools\download_wheels.bat 3.13
set "PYVER=%~1"
if "%PYVER%"=="" set "PYVER=3.12"
echo Downloading wheels for Python %PYVER% / win_amd64 into wheels\ ...
py -3 -m pip download -r requirements-windows.txt -d wheels --only-binary=:all: --platform win_amd64 --python-version %PYVER% --implementation cp
if errorlevel 1 (
  echo [ERROR] Download failed. Check the internet connection and the Python installation.
  echo.
  pause
  exit /b 1
)
echo.
echo Done. Copy the wheels folder next to install.bat on the company PC, then run install.bat.
echo.
pause
