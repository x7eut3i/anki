@echo off
setlocal enabledelayedexpansion
REM ============================================================
REM deploy.bat — Build & deploy Anki Flashcard App (Windows)
REM
REM Usage:
REM   deploy.bat          Build and run locally via docker compose
REM   deploy.bat build    Build image only
REM ============================================================

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

set "IMAGE_NAME=anki-app"
set "IMAGE_TAG=latest"

if "%~1"=="" goto :run_local
if /i "%~1"=="build" goto :build_only
echo Usage: %~nx0 [build]
exit /b 1

:build_only
echo === Building Docker image: %IMAGE_NAME%:%IMAGE_TAG% ===
docker build -t %IMAGE_NAME%:%IMAGE_TAG% .
if errorlevel 1 (echo ERROR: Docker build failed & exit /b 1)
echo [OK] Image built: %IMAGE_NAME%:%IMAGE_TAG%
goto :eof

:run_local
if not exist "ai_config.json" (
    echo ERROR: ai_config.json not found. Copy ai_config.json.example and fill in your API key.
    exit /b 1
)

echo === Starting services via docker compose ===
docker compose up -d --build
if errorlevel 1 (echo ERROR: docker compose failed & exit /b 1)

set "PORT=8000"
echo.
echo [OK] App running at http://localhost:%PORT%
echo.
echo   Useful commands:
echo     docker compose logs -f        Follow logs
echo     docker compose down            Stop
echo     docker compose up -d --build   Rebuild ^& restart
goto :eof
