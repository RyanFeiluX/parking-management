@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -NoProfile -File build_installer.ps1
pause