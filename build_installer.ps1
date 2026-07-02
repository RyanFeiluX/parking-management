[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Parking Management System - Build Installer" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$PYTHON = if (Test-Path "venv\Scripts\python.exe") { "venv\Scripts\python.exe" } else { "python.exe" }
Write-Host "Using Python: $PYTHON"

Write-Host ""
Write-Host "[1/2] Checking if exe is already built..." -ForegroundColor Yellow

$exeName = "parkman"
$exePath = "dist\$exeName.exe"
$needBuild = $false

if (-not (Test-Path $exePath)) {
    $needBuild = $true
}

if ($needBuild) {
    Write-Host "EXE not found, running PyInstaller..." -ForegroundColor Yellow
    
    Write-Host "Installing PyInstaller..."
    & $PYTHON -m pip install pyinstaller -q
    
    Write-Host "Cleaning cache..."
    Remove-Item "app\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item "app\routers\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
    
    Write-Host "Building exe..."
    & $PYTHON -m PyInstaller --onefile --console --name $exeName --add-data "app;app" --hidden-import secrets --hidden-import traceback run.py
    
    if (-not (Test-Path $exePath)) {
        Write-Host "PyInstaller build failed!" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Found $exePath" -ForegroundColor Green
}

Write-Host ""
Write-Host "[2/2] Looking for Inno Setup compiler..." -ForegroundColor Yellow

$ISCC = $null
$paths = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    "C:\Program Files\Inno Setup 5\ISCC.exe"
)

foreach ($path in $paths) {
    if (Test-Path $path) {
        $ISCC = $path
        break
    }
}

if (-not $ISCC) {
    Write-Host "[ERROR] Inno Setup compiler not found (ISCC.exe)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please download and install Inno Setup 6:" -ForegroundColor Yellow
    Write-Host "  https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Run this script again after installation." -ForegroundColor Yellow
    exit 1
}

Write-Host "Using: $ISCC" -ForegroundColor Green
& $ISCC installer.iss

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan

$installerPath = "installer\停车费管理系统_安装程序.exe"
if (Test-Path $installerPath) {
    $file = Get-Item $installerPath
    Write-Host "Installer build successful!" -ForegroundColor Green
    Write-Host "Output: $installerPath ($($file.Length) bytes)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Send this installer to end users, double-click to install." -ForegroundColor Green
} else {
    Write-Host "Installer build failed, please check error messages above." -ForegroundColor Red
}

Write-Host "================================================" -ForegroundColor Cyan