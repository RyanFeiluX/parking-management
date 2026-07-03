# Parking Management System

小区包月制停车费管理系统 — 一户多车、车辆按序定档收费、三权分立权限管理。

## Tech Stack

- **Backend:** FastAPI (Python)
- **Database:** SQLite (单机，无需安装)
- **Template:** Jinja2 + Bootstrap 5
- **Auth:** Session-based (itsdangerous)

## Quick Start

### 面向最终用户

#### Option 1: Windows 安装包（推荐）

运行 `installer\ParkManSetup.exe` 一键安装，自动创建开始菜单和桌面快捷方式，自带卸载程序。

**制作安装包：** 需要先安装 [Inno Setup 6](https://jrsoftware.org/isdl.php)，然后双击：
```cmd
build_installer.bat
```

#### Option 2: 单文件 exe 便携版

直接双击 `dist\parkman.exe`，无需安装，等待数秒即可在浏览器中自动打开系统。
- 无需安装 Python
- 数据库自动创建在用户数据目录（`%APPDATA%\停车费管理系统\parking.db`）
- 关闭控制台窗口即停止服务

### 面向开发者

#### 第一步：搭建开发环境

首次使用，双击 `dev_setup.bat`，自动完成：
1. 用 Python 3.12 创建虚拟环境 `venv`
2. 从 `requirements.txt` 安装所有依赖

#### 第二步：启动应用
```cmd
双击 start.bat
```
Open http://127.0.0.1:8080

### 重新打包

修改源码后：
| 命令 | 产物 |
|------|------|
| `build_exe.bat` | `dist\parkman.exe` |
| `build_installer.bat` | `installer\ParkManSetup.exe` |

## Default Login

| Username | Password | Role |
|----------|----------|------|
| admin | password123 | super_admin |

## Features

| Module | Description | Access |
|--------|-------------|--------|
| Dashboard | 首页仪表盘，车辆状态/收费统计 | all |
| Residents | 住户管理（房号/业主/电话） | admin+ |
| Vehicles | 车辆管理（一户多车/排序） | admin+ |
| Payments | 包月缴费（月/季/年），金额自动计算 | all |
| Fee Tiers | 收费档位配置（版本化管理） | admin+ |
| Discounts | 优惠策略配置（新能源折扣/免费等） | admin+ |
| **Invoices** | **开票管理（抬头/类型/金额，状态流转）** | **all** |
| Stats | 统计报表 | all |
| Users | 用户管理（operator/admin/super_admin） | super_admin |
| Settings | 系统设置（宽限期/临时费率/发票抬头预设） | super_admin |
| Logs | 操作日志审计 | super_admin |

## Invoicing

- 每次交费最多关联一个开票条目（`payment_id` UNIQUE 约束）
- 三种状态：**开票等待中** → **开票已完成** / **申请已取消**
- 支持普票/专票（专票可填纳税人识别号）
- 发票抬头可从预设列表选择（系统设置中维护）
- 入口：缴费记录、车辆状态页、住户详情

## Project Structure

```
parking-management/
├── start.bat                  # 启动应用（自动检测 venv）
├── dev_setup.bat              # 一键搭建开发环境（创建 venv + 安装依赖）
├── build_exe.bat              # 打包为单文件 exe
├── build_installer.bat        # 制作 Windows 安装包
├── installer.iss              # Inno Setup 安装脚本
├── run.py                     # Python 入口
├── requirements.txt           # 依赖列表
├── data/                      # 用户数据目录（自动创建，开发模式）
│   ├── parking.db             # SQLite 数据库
│   └── config.json            # 数据库路径配置
├── dist/                      # exe 输出目录
│   └── parkman.exe
├── 启动说明.md
├── 停车费管理系统_规格说明书.md
├── app/
│   ├── __init__.py
│   ├── _path.py               # 路径辅助（资源目录/用户数据目录/配置读写）
│   ├── migration.py            # Schema 迁移框架
│   ├── main.py                # FastAPI 应用
│   ├── jinja.py               # Jinja2 模板引擎
│   ├── models.py              # SQLAlchemy ORM 模型
│   ├── schemas.py             # Pydantic 校验
│   ├── database.py            # DB 引擎 & Session
│   ├── auth.py                # 密码哈希 & Session
│   ├── deps.py                # 依赖注入（权限检查）
│   ├── utils.py               # 业务逻辑
│   ├── routers/               # 路由处理器
│   │   ├── invoices.py
│   │   ├── payments.py
│   │   ├── residents.py
│   │   ├── vehicles.py
│   │   ├── fee_tiers.py
│   │   ├── discounts.py
│   │   ├── users.py
│   │   ├── settings.py
│   │   ├── stats.py
│   │   ├── logs.py
│   │   └── api.py
│   ├── static/
│   │   ├── favicon.svg
│   │   └── js/notification.js
│   └── templates/             # Jinja2 模板
```

## Troubleshooting

**"No module named 'uvicorn'"** → 运行 `dev_setup.bat` 重建虚拟环境。

**Port 8080 in use** → 编辑 `run.py`，将 `port=8080` 改为其他端口。

## Data Management

**Database location:**
- **Packaged mode (exe/installer):** `%APPDATA%\停车费管理系统\parking.db`
- **Development mode:** `./data/parking.db`

The data directory is **never deleted** during uninstall, so reinstalling the app preserves all data.

**Custom database path:**
1. Login as `super_admin`
2. Go to ⚙️ System Settings → Database Management
3. Enter a custom path for the SQLite database file
4. Save and restart the app

**Environment variable override:**
```cmd
set PARKING_DB_URL=sqlite:///D:\data\my_parking.db
python run.py
```

**Schema upgrades:** The app auto-applies schema migrations on startup, so upgrading the app version preserves existing data without manual intervention.
