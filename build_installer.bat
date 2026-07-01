@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo  停车费管理系统 - 制作安装包
echo ================================================
echo.

rem 1. 确保 exe 已打包
if not exist "dist\停车管理系统.exe" (
    echo [1/2] 未找到 exe，先执行 PyInstaller 打包...
    call build_exe.bat
) else (
    echo [1/2] 已找到 dist\停车管理系统.exe
)

rem 2. 查找 Inno Setup 编译器
set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
if exist "C:\Program Files\Inno Setup 5\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 5\ISCC.exe"

if "%ISCC%"=="" (
    echo [2/2] [错误] 未找到 Inno Setup 编译器 (ISCC.exe)
    echo.
    echo 请先下载并安装 Inno Setup 6：
    echo   https://jrsoftware.org/isdl.php
    echo.
    echo 安装后重新运行本脚本。
    pause
    exit /b 1
)

echo [2/2] 使用: %ISCC%
"%ISCC%" installer.iss

echo.
echo ================================================
if exist "installer\停车费管理系统_安装程序.exe" (
    echo 安装包制作成功！
    for %%I in ("installer\停车费管理系统_安装程序.exe") do @echo 输出: installer\停车费管理系统_安装程序.exe (%%~zI 字节)
    echo.
    echo 将此安装包发给最终用户，运行后即完成安装。
) else (
    echo 安装包制作失败，请查看上方错误信息。
)
echo ================================================
pause
