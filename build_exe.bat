@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo  停车费管理系统 - 打包工具
echo ================================================
echo.

if exist "venv\Scripts\python.exe" (set "PYTHON=venv\Scripts\python.exe") else (set "PYTHON=python.exe")

echo 使用 Python: %PYTHON%
"%PYTHON%" -m pip install pyinstaller -q

echo.
echo 正在打包为单文件 exe...
echo.

"%PYTHON%" -m PyInstaller --onefile --console ^
  --name "停车管理系统" ^
  --add-data "app;app" ^
  --hidden-import passlib.handlers.bcrypt ^
  --hidden-import passlib.handlers.sha2_crypt ^
  --hidden-import bcrypt ^
  --collect-all passlib ^
  run.py

echo.
echo ================================================
if exist "dist\停车管理系统.exe" (
    echo 打包成功！
    for %%I in ("dist\停车管理系统.exe") do @echo 输出: dist\停车管理系统.exe (%%~zI 字节)
    echo.
    echo 将此 exe 文件发给最终用户，双击即可运行。
) else (
    echo 打包失败，请查看上方错误信息。
)
echo ================================================
pause
