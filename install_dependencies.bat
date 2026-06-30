@echo off
cd /d "%~dp0"

echo ================================================
echo 停车费管理系统 - 依赖安装器
echo ================================================
echo.

echo 正在升级 pip...
python -m pip install --upgrade pip

echo.
echo 正在安装核心依赖...
python -m pip install fastapi uvicorn sqlalchemy jinja2

echo.
echo 正在安装可选依赖...
python -m pip install python-multipart itsdangerous openpyxl

echo.
echo ================================================
echo 安装完成！
echo ================================================
echo.
echo 现在可以运行 start.bat 或 quick-start.bat 启动应用
echo.
pause