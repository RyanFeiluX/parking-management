# 停车费管理系统启动脚本
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "停车费管理系统启动器" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$pythonCmd = "python"

# 检查虚拟环境
if (Test-Path "venv\bin\python.exe") {
    Write-Host "使用虚拟环境 Python..." -ForegroundColor Green
    $pythonCmd = "venv\bin\python.exe"
}

# 检查依赖
try {
    & $pythonCmd -c "import uvicorn" 2>&1 | Out-Null
    Write-Host "依赖检查通过" -ForegroundColor Green
} catch {
    Write-Host "依赖未安装，正在安装..." -ForegroundColor Yellow
    
    # 升级 pip
    & $pythonCmd -m pip install --upgrade pip
    
    # 安装依赖
    & $pythonCmd -m pip install fastapi uvicorn sqlalchemy jinja2 python-multipart itsdangerous openpyxl
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "依赖安装失败！" -ForegroundColor Red
        Write-Host "请尝试以下方法:" -ForegroundColor Yellow
        Write-Host "  方法 1: 运行 pip install fastapi uvicorn sqlalchemy jinja2" -ForegroundColor White
        Write-Host "  方法 2: 双击 run_simple.bat 使用系统 Python" -ForegroundColor White
        Write-Host ""
        Read-Host "按任意键退出"
        exit 1
    }
}

Write-Host ""
Write-Host "启动应用..." -ForegroundColor Green
Write-Host "Python路径: $pythonCmd" -ForegroundColor Gray
Write-Host ""

& $pythonCmd run.py

Write-Host ""
Write-Host "应用已停止" -ForegroundColor Gray
Read-Host "按任意键退出"
