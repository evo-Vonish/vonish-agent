@echo off
chcp 65001 >nul
title VonishAgent

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "VENV_PYTHON=%BACKEND%\.venv\Scripts\python.exe"
set "URL=http://127.0.0.1:8000"

echo ============================================
echo   VonishAgent 启动中...
echo ============================================

:: Check Python venv
if not exist "%VENV_PYTHON%" (
    echo [错误] 虚拟环境未找到: %VENV_PYTHON%
    echo 请先执行: cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

:: Check if already running on port 8000
netstat -ano | findstr ":8000.*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [信息] 后端已在运行 (端口 8000)
    goto OPEN_BROWSER
)

echo [启动] 后端服务...
start "VonishAgent-Backend" /MIN "%VENV_PYTHON%" "%BACKEND%\main.py"

:: Wait for backend to be ready
echo [等待] 后端就绪...
for /L %%i in (1,1,30) do (
    curl -s http://127.0.0.1:8000/health >nul 2>&1
    if not errorlevel 1 goto BACKEND_READY
    timeout /t 1 /nobreak >nul
)
echo [警告] 后端启动超时，继续打开浏览器...

:BACKEND_READY
echo [就绪] 后端已启动

:OPEN_BROWSER
echo [打开] 浏览器...
start "" "%URL%"
echo ============================================
echo   VonishAgent 已启动
echo   浏览器地址: %URL%
echo   关闭此窗口不会停止后端
echo ============================================
pause >nul
