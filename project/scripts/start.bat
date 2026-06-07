@echo off
chcp 65001 >nul
title VonishAgent

set "ROOT=%~dp0.."
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "VENV_PYTHON=%BACKEND%\.venv\Scripts\python.exe"
set "FRONTEND_PORT=18473"
set "BACKEND_PORT=18480"
set "URL=http://127.0.0.1:%FRONTEND_PORT%"

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

:: Check if already running on backend port
netstat -ano | findstr ":%BACKEND_PORT%.*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [信息] 后端已在运行 (端口 %BACKEND_PORT%)
    goto OPEN_BROWSER
)

echo [启动] 后端服务...
start "VonishAgent-Backend" /MIN "%VENV_PYTHON%" "%BACKEND%\main.py"

:: Wait for backend to be ready
echo [等待] 后端就绪...
for /L %%i in (1,1,30) do (
    curl -s http://127.0.0.1:%BACKEND_PORT%/health >nul 2>&1
    if not errorlevel 1 goto BACKEND_READY
    timeout /t 1 /nobreak >nul
)
echo [警告] 后端启动超时，继续打开浏览器...

:BACKEND_READY
echo [就绪] 后端已启动

:OPEN_BROWSER
netstat -ano | findstr ":%FRONTEND_PORT%.*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [信息] 前端已在运行 (端口 %FRONTEND_PORT%)
    goto OPEN_URL
)

echo [启动] 前端服务...
start "VonishAgent-Frontend" /MIN cmd /c "cd /d ""%FRONTEND%"" && npm.cmd run dev"

echo [等待] 前端就绪...
for /L %%i in (1,1,30) do (
    curl -s http://127.0.0.1:%FRONTEND_PORT%/ >nul 2>&1
    if not errorlevel 1 goto FRONTEND_READY
    timeout /t 1 /nobreak >nul
)
echo [警告] 前端启动超时，继续打开浏览器...

:FRONTEND_READY
echo [就绪] 前端已启动

:OPEN_URL
echo [打开] 浏览器...
start "" "%URL%"
echo ============================================
echo   VonishAgent 已启动
echo   浏览器地址: %URL%
echo   关闭此窗口不会停止后端
echo ============================================
pause >nul
