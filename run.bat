@echo off
cd /d "%~dp0"

echo ================================================
echo Parking Management System Launcher
echo ================================================
echo.

set "PYTHON_CMD=D:\ProgramData\anaconda3\python.exe"

echo Checking dependencies...
"%PYTHON_CMD%" -c "import uvicorn" >nul 2>&1
if %errorlevel% neq 0 (
    echo Dependencies not found, installing...
    "%PYTHON_CMD%" -m pip install --upgrade pip
    "%PYTHON_CMD%" -m pip install fastapi uvicorn sqlalchemy jinja2 python-multipart itsdangerous openpyxl
    if %errorlevel% neq 0 (
        echo.
        echo Dependency installation failed!
        echo Please install manually:
        echo   pip install fastapi uvicorn sqlalchemy jinja2 python-multipart itsdangerous openpyxl
        echo.
        pause
        exit /b 1
    )
)

echo.
echo Starting application...
echo Python: %PYTHON_CMD%
echo.

"%PYTHON_CMD%" run.py

echo.
echo Application stopped
pause