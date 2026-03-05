@echo off
setlocal enabledelayedexpansion
REM ============================================================
REM build.bat — Build and run Anki Flashcard App (Windows)
REM Usage:
REM   build.bat          Build frontend + backend, then start server
REM   build.bat build    Build only (no server start)
REM   build.bat run      Start server only (assumes already built)
REM ============================================================

set "ROOT_DIR=%~dp0"
set "FRONTEND_DIR=%ROOT_DIR%frontend"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "STATIC_DIR=%BACKEND_DIR%\static"

if "%~1"=="" goto :all
if /i "%~1"=="build" goto :build_only
if /i "%~1"=="run" goto :run_only
if /i "%~1"=="all" goto :all
echo Usage: %~nx0 [build^|run^|all]
exit /b 1

:build_only
call :build_frontend
call :copy_static
call :install_backend
echo.
echo [OK] Build complete. Run 'build.bat run' to start the server.
goto :eof

:run_only
call :start_server
goto :eof

:all
call :build_frontend
call :copy_static
call :install_backend
call :start_server
goto :eof

REM ---- Subroutines ----

:build_frontend
echo === [1/3] Building frontend ===
cd /d "%FRONTEND_DIR%"
call npm install --no-audit --no-fund
if errorlevel 1 (echo ERROR: npm ci failed & exit /b 1)
call npm run build
if errorlevel 1 (echo ERROR: npm build failed & exit /b 1)
echo     Frontend built -^> frontend\out\
exit /b 0

:copy_static
echo === [2/3] Copying frontend -^> backend\static\ ===
if exist "%STATIC_DIR%" rmdir /s /q "%STATIC_DIR%"
xcopy /E /I /Q /Y "%FRONTEND_DIR%\out" "%STATIC_DIR%" >nul
echo     Static files ready.
exit /b 0

:install_backend
echo === [3/3] Installing backend dependencies ===
cd /d "%BACKEND_DIR%"
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -e ".[dev]"
echo     Backend dependencies installed.
exit /b 0

:start_server
cd /d "%BACKEND_DIR%"
call .venv\Scripts\activate.bat

if not exist "data" mkdir data

set "HOST=%HOST%"
set "PORT=%PORT%"
if "%HOST%"=="" set "HOST=127.0.0.1"
if "%PORT%"=="" set "PORT=8000"

echo.
echo === Server starting at http://%HOST%:%PORT% ===
echo     Press Ctrl+C to stop.
echo.
python -m uvicorn app.main:app --host %HOST% --port %PORT%
exit /b 0
