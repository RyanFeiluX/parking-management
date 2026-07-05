@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo  停车费管理系统 - 开发环境搭建
echo ================================================
echo.

rem 使用 uv 管理的 Python 3.12（纯净 python.org 版本）
set "PYTHON=C:\Users\looe_\AppData\Roaming\uv\python\cpython-3.12.12-windows-x86_64-none\python.exe"

if not exist "%PYTHON%" (
    echo [错误] 未找到 Python 3.12
    echo 请从 https://www.python.org/downloads/ 下载安装 Python 3.12
    pause
    exit /b 1
)

echo 使用 Python: %PYTHON%
"%PYTHON%" --version

echo.
echo [1/3] 创建虚拟环境...
"%PYTHON%" -m venv venv
if %ERRORLEVEL% neq 0 (
    echo 创建 venv 失败！
    pause
    exit /b 1
)

echo [2/3] 升级 pip...
.\venv\Scripts\python.exe -m pip install --upgrade pip -q

echo [3/3] 安装依赖...
.\venv\Scripts\python.exe -m pip install -r requirements.txt -q

echo.
echo ================================================
echo  开发环境搭建完成！
echo ================================================
echo.
echo  启动应用: 双击 start.bat
echo  打包 exe: 双击 build_exe.bat
echo  制作安装包: 双击 build-installer.bat
echo.
pause
