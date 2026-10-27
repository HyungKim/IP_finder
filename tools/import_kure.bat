@echo off
setlocal
cd /d "%~dp0kure"
echo ==================================================
echo  Import KURE-v1 (Korean embedding model) into Ollama
echo ==================================================
if not exist "kure-v1-q8_0.gguf" (
  echo [ERROR] kure-v1-q8_0.gguf not found in %CD%
  echo   Download it from https://huggingface.co/Bingsu/KURE-v1-Q8_0-GGUF
  echo   ^(file: kure-v1-q8_0.gguf, about 635 MB^) and put it in this folder.
  echo   On a PC without internet: download on another PC and copy the file.
  echo.
  pause
  exit /b 1
)
ollama create kure-v1 -f Modelfile
if errorlevel 1 (
  echo [ERROR] ollama create failed. Is Ollama installed and running?
  echo.
  pause
  exit /b 1
)
echo.
echo [OK] Model "kure-v1" is ready. Use it with:  --embed-model kure-v1
echo      or set  embed_model = "kure-v1"  in ip_finder.toml (UI: embedding model box).
echo      A trained classifier is tied to one embedding model: run train again after switching.
echo.
pause
