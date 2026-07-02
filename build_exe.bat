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
  --name "parking-management" ^
  --add-data "app;app" ^
  --hidden-import secrets ^
  --hidden-import traceback ^
  run.py

echo.
echo ================================================
if exist "dist\parking-management.exe" (
    echo Build succeeded!
    set "size="
    for %%I in ("dist\parking-management.exe") do set "size=%%~zI"
    echo Output: dist\parking-management.exe (%size% bytes)
    echo.
    echo Send this exe file to end users, double-click to run.
) else (
    echo Build failed, please check error messages above.
)
echo ================================================
pause
