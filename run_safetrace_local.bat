@echo off
setlocal

cd /d "%~dp0"

set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=1

echo Starting SafeTrace FastAPI backend on http://127.0.0.1:8000 ...
start "SafeTrace Backend" cmd /k "set KMP_DUPLICATE_LIB_OK=TRUE && set OMP_NUM_THREADS=1 && python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --log-level info"

echo Starting SafeTrace React frontend on http://127.0.0.1:5173 ...
start "SafeTrace React" cmd /k "cd /d ""%~dp0frontend-react"" && npm.cmd run dev -- --host 127.0.0.1"

timeout /t 4 /nobreak >nul
start "" "http://127.0.0.1:5173"

endlocal
