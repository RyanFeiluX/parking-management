@echo off
setlocal

echo ================================================
echo 停车费管理系统启动器
echo ================================================
echo.

set "VENV_PYTHON=venv\bin\python.exe"
set "SCRIPT=run.py"

if not exist "%VENV_PYTHON%" (
    echo 错误: 虚拟环境Python不存在
    echo 尝试使用系统Python...
    set "VENV_PYTHON=python.exe"
)

echo 启动应用...
echo Python路径: %VENV_PYTHON%
echo.

"%VENV_PYTHON%" "%SCRIPT%"

echo.
echo 应用已停止
pause
