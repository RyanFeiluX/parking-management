@echo off
cd /d "%~dp0"

echo ================================================
echo  Parking Management System - Build Tool
echo ================================================
echo.

if exist "venv\Scripts\python.exe" (set "PYTHON=venv\Scripts\python.exe") else (set "PYTHON=python.exe")

echo Using Python: %PYTHON%
"%PYTHON%" -m pip install pyinstaller -q

echo Cleaning cache...
rd /s /q app\__pycache__ app\routers\__pycache__ 2>nul

echo.
echo Building as single exe file...
echo.

"%PYTHON%" -m PyInstaller --onefile --console ^
  --name "parkman" ^
  --add-data "app;app" ^
  --hidden-import secrets ^
  --hidden-import traceback ^
  --hidden-import passlib.handlers.bcrypt ^
  --hidden-import passlib.handlers.sha2_crypt ^
  --hidden-import bcrypt ^
  --collect-all passlib ^
  run.py

echo.
echo ================================================
if exist "dist\parkman.exe" (
    echo Build succeeded!
    set "size="
    for %%I in ("dist\parkman.exe") do set "size=%%~zI"
    echo Output: dist\parkman.exe (%size% bytes)
    echo.
    echo Send this exe file to end users, double-click to run.
) else (
    echo Build failed, please check error messages above.
)
echo ================================================
pause