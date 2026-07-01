@echo off
setlocal

cd /d "%~dp0.."

if not exist "frontend-react\package.json" (
  echo ERROR: frontend-react\package.json not found.
  exit /b 1
)

cd frontend-react

echo Installing frontend dependencies...
call npm.cmd install
if errorlevel 1 exit /b 1

echo Building frontend...
call npm.cmd run build
if errorlevel 1 exit /b 1

echo Deploying to Vercel production...
echo If this is the first run, Vercel CLI may ask you to log in and link the project.
call npx.cmd vercel --prod
exit /b %errorlevel%
