@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ================================================
echo  Parking Management System - Build Installer
echo ================================================
echo.

REM === Find Python ===
if exist "venv\Scripts\python.exe" (set "PYTHON=venv\Scripts\python.exe") else (set "PYTHON=python.exe")
echo Using Python: %PYTHON%

echo.
echo [1/2] Checking if exe is already built...

REM === Check if exe exists, build if not ===
if not exist "dist\parkman.exe" (
    echo EXE not found, running PyInstaller...
    echo.
    echo Installing PyInstaller...
    "%PYTHON%" -m pip install pyinstaller -q

    echo Cleaning cache...
    rd /s /q app\__pycache__ app\routers\__pycache__ 2>nul

    echo Building exe...
    "%PYTHON%" -m PyInstaller --onefile --console --name "parkman" --add-data "app;app" --hidden-import secrets --hidden-import traceback --hidden-import passlib.handlers.bcrypt --hidden-import passlib.handlers.sha2_crypt --hidden-import bcrypt --collect-all passlib run.py

    if not exist "dist\parkman.exe" (
        echo PyInstaller build failed!
        pause
        exit /b 1
    )
) else (
    echo Found dist\parkman.exe
)

echo.
echo [2/2] Looking for Inno Setup compiler...

REM === Find ISCC.exe ===
set "ISCC="

REM 1. Try PATH
for /f "delims=" %%i in ('where ISCC.exe 2^>nul') do (
    set "ISCC=%%i"
    goto :found_iscc
)

REM 2. Try registry (works regardless of install location)
if not defined ISCC (
    for %%K in (
        "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
        "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
        "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
        "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 5_is1"
        "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 5_is1"
    ) do (
        for /f "tokens=2*" %%a in ('reg query %%K /v InstallLocation 2^>nul ^| findstr "REG_SZ"') do (
            if exist "%%b\ISCC.exe" (
                set "ISCC=%%b\ISCC.exe"
                goto :found_iscc
            )
        )
    )
)

REM 3. Fallback to common install locations
if not defined ISCC (
    for %%P in (
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        "C:\Program Files\Inno Setup 6\ISCC.exe"
        "C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
        "C:\Program Files\Inno Setup 5\ISCC.exe"
    ) do (
        if exist %%P (
            set "ISCC=%%~P"
            goto :found_iscc
        )
    )
)

:found_iscc
if not defined ISCC (
    echo [ERROR] Inno Setup compiler not found ^(ISCC.exe^)
    echo.
    echo Please download and install Inno Setup 6:
    echo   https://jrsoftware.org/isdl.php
    echo.
    echo Run this script again after installation.
    pause
    exit /b 1
)

REM === Read version from app/__init__.py ===
set "APP_VERSION="
set "VERSION_RAW="
for /f "tokens=2 delims==" %%v in ('findstr /b "VERSION" app\__init__.py') do set "VERSION_RAW=%%v"
if defined VERSION_RAW (
    set "APP_VERSION=!VERSION_RAW: =!"
    set "APP_VERSION=!APP_VERSION:"=!"
)

echo Using: %ISCC%
if defined APP_VERSION (
    echo Version: %APP_VERSION% ^(from app/__init__.py^)
    set "OUTPUT_NAME=ParkMan_Setup_v%APP_VERSION%"
    "%ISCC%" /DMyAppVersion="%APP_VERSION%" /DMyOutputBaseFileName="!OUTPUT_NAME!" installer.iss
) else (
    echo Warning: could not parse version from app/__init__.py, using default
    "%ISCC%" installer.iss
)

echo.
echo ================================================

REM === Check for output ===
set "INSTALLER_NAME="
for /f "delims=" %%f in ('dir /b /o-d installer\*.exe 2^>nul') do (
    set "INSTALLER_NAME=%%f"
    goto :show_result
)

:show_result
if defined INSTALLER_NAME (
    for %%I in ("installer\%INSTALLER_NAME%") do set "INSTALLER_SIZE=%%~zI"
    echo Installer build successful!
    echo Output: installer\%INSTALLER_NAME% ^(!INSTALLER_SIZE! bytes^)
    echo.
    echo Send this installer to end users, double-click to install.
) else (
    echo Installer build failed, please check error messages above.
)

echo ================================================
endlocal
