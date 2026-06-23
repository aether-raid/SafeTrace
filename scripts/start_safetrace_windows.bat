@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

cd /d "%REPO_ROOT%" || (
  echo [SafeTrace] Could not change to repo root: "%REPO_ROOT%"
  exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
  echo [SafeTrace] Missing virtual environment: "%REPO_ROOT%\.venv\Scripts\activate.bat"
  echo [SafeTrace] Create or restore the local .venv before starting SafeTrace.
  exit /b 1
)

if not exist "frontend-react\package.json" (
  echo [SafeTrace] Missing React frontend package: "%REPO_ROOT%\frontend-react\package.json"
  exit /b 1
)

set "KMP_DUPLICATE_LIB_OK=TRUE"
set "OMP_NUM_THREADS=1"
set "SAFETRACE_CHAT_ENABLED=auto"
set "SAFETRACE_CHAT_PROVIDER=packaged_llamacpp"
set "SAFETRACE_CHAT_SPEED_PROFILE=fast"

if not defined SAFETRACE_CHAT_MODEL_PATH (
  set "SAFETRACE_CHAT_MODEL_PATH=models\chat\safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf"
)

echo [SafeTrace] Repo root: "%REPO_ROOT%"
echo [SafeTrace] Backend URL:  http://127.0.0.1:8000/api/health
echo [SafeTrace] Frontend URL: http://127.0.0.1:5173
echo [SafeTrace] Chat provider: %SAFETRACE_CHAT_PROVIDER%
echo [SafeTrace] Chat model: %SAFETRACE_CHAT_MODEL_PATH%
echo.
echo [SafeTrace] Opening backend and frontend terminals. Keep both windows open.

start "SafeTrace Backend" /D "%REPO_ROOT%" cmd /k "call .venv\Scripts\activate.bat && python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --log-level info"
start "SafeTrace Frontend" /D "%REPO_ROOT%\frontend-react" cmd /k "npm.cmd run dev -- --host 127.0.0.1 --port 5173"

echo [SafeTrace] Waiting briefly before opening the browser...
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:5173"

echo [SafeTrace] Launcher finished. Backend/frontend logs are in the opened terminals.
endlocal
