@echo off
chcp 65001 >nul
title Anki Article Pipeline - 测试运行

echo ========================================
echo   Anki 文章分析管道 - 测试运行
echo ========================================
echo.

cd /d "%~dp0"

REM 检查 Python 虚拟环境
if exist "backend\.venv\Scripts\python.exe" (
    set PYTHON=backend\.venv\Scripts\python.exe
) else if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
) else (
    echo [错误] 找不到 Python 虚拟环境，请先创建: python -m venv backend\.venv
    pause
    exit /b 1
)

echo 使用 Python: %PYTHON%
echo.

REM 默认参数：每个源最多1篇文章，先预览（dry-run）
echo [1] 预览模式（不写入数据库）...
echo.
%PYTHON% article_pipeline.py --dry-run --max-articles 1

echo.
echo ========================================
echo.

set /p CONFIRM="是否正式导入？(y/N): "
if /i "%CONFIRM%"=="y" (
    echo.
    echo [2] 正式运行，导入到数据库...
    echo.
    %PYTHON% article_pipeline.py --max-articles 1
) else (
    echo 已取消导入。
)

echo.
echo ========================================
echo 运行完毕！
echo ========================================
pause
