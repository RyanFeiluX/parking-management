# Parking Management System

小区包月制停车费管理系统 — 一户多车、车辆按序定档收费、三权分立权限管理。

## Tech Stack

- **Backend:** FastAPI (Python)
- **Database:** SQLite (单机，无需安装)
- **Template:** Jinja2 + Bootstrap 5
- **Auth:** Session-based (itsdangerous)

## Quick Start

### Option 1: `start.bat` (Recommended)

优先使用虚拟环境 `venv`，自动检查依赖，启动更稳妥。

```cmd
双击 start.bat
```

### Option 2: `quick-start.bat`

直接 `python run.py`，不做检查，最快启动。适合已装好依赖的环境。

```cmd
双击 quick-start.bat
```

### Manual

```bash
pip install -r requirements_simple.txt
python run.py
```

Open http://127.0.0.1:8080

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
├── README.md                  # This file
├── start.bat                  # [Recommended] Start script (venv + dep check)
├── quick-start.bat            # Quick start (direct python run.py)
├── run.py                     # Python entry point (uvicorn)
├── requirements.txt           # Full dependencies
├── requirements_simple.txt    # Minimal dependencies
├── parking.db                 # SQLite database (auto-created)
├── 启动说明.md                 # Startup guide (Chinese)
├── 停车费管理系统_规格说明书.md    # Full spec (Chinese)
└── app/
    ├── main.py                # FastAPI app & routes registration
    ├── models.py              # SQLAlchemy ORM models
    ├── schemas.py             # Pydantic validation schemas
    ├── database.py            # DB engine & session
    ├── auth.py                # Password hash & session management
    ├── deps.py                # FastAPI dependencies (auth/role check)
    ├── utils.py               # Business logic (payment calc, status)
    ├── routers/               # Route handlers
    │   ├── invoices.py        # Invoicing CRUD
    │   ├── payments.py        # Payment processing
    │   ├── residents.py       # Resident management
    │   ├── vehicles.py        # Vehicle management
    │   ├── fee_tiers.py       # Fee tier configuration
    │   ├── discounts.py       # Discount policy configuration
    │   ├── users.py           # User management (super_admin)
    │   ├── settings.py        # System settings
    │   ├── stats.py           # Dashboard statistics
    │   ├── logs.py            # Operation logs
    │   └── api.py             # External API (vehicle status)
    └── templates/             # Jinja2 HTML templates
```

## Troubleshooting

**"No module named 'uvicorn'"** → Run `pip install -r requirements_simple.txt` or use `start.bat`.

**Port 8080 in use** → Edit `run.py`, change `port=8080` to another number.
