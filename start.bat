@echo off
setlocal

echo ================================================
echo Parking Management System
echo ================================================
echo.

set "VENV_PYTHON=venv\Scripts\python.exe"
set "SCRIPT=run.py"

if not exist "%VENV_PYTHON%" (
    echo [INFO] Virtual environment not found, using system Python...
    set "VENV_PYTHON=python.exe"
)

echo Starting application...
echo Python: %VENV_PYTHON%
echo.

"%VENV_PYTHON%" "%SCRIPT%"

echo.
echo Application stopped
pause
